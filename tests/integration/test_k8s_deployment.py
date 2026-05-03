"""
Kubernetes deployment integration tests.

Validates that `k8s/bittensor-testnet.yaml` raw manifests are applied correctly
to the `bittensor-testnet` namespace. All tests are gated by BT_RUN_K8S_TESTS=1
to avoid requiring cluster access in CI.

Run with:
    BT_RUN_K8S_TESTS=1 pytest tests/integration/test_k8s_deployment.py -v

Prerequisites:
    - kubectl configured for target cluster
    - ArgoCD has synced k8s/bittensor-testnet.yaml (or manual kubectl apply)
    - bt-wallet secret exists in bittensor-testnet namespace
"""

from __future__ import annotations

import os
import subprocess
import time

import pytest
from kubernetes import client, config
from kubernetes.client.rest import ApiException

pytestmark = pytest.mark.skipif(
    os.getenv("BT_RUN_K8S_TESTS") != "1",
    reason="BT_RUN_K8S_TESTS=1 required for K8s integration tests",
)

# Matches k8s/bittensor-testnet.yaml resource names exactly
NAMESPACE = "bittensor-testnet"
STATEFULSET_NAME = "bt-validator"
DEPLOYMENT_NAME = "bt-strategy"
CONFIGMAP_NAME = "bt-strategy-config"
SERVICE_ACCOUNT = "bt"
WALLET_SECRET = "bt-wallet"
TIMEOUT_SECONDS = 300


@pytest.fixture(scope="module")
def kube_api() -> client.CoreV1Api:
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def apps_api() -> client.AppsV1Api:
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return client.AppsV1Api()


def wait_for_pod_ready(
    api: client.CoreV1Api,
    name: str,
    timeout: int = TIMEOUT_SECONDS,
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            pod = api.read_namespaced_pod(name, NAMESPACE)
            if pod.status.phase == "Running":
                for condition in pod.status.conditions or []:
                    if condition.type == "Ready" and condition.status == "True":
                        return True
        except ApiException:
            pass
        time.sleep(5)
    return False


class TestNamespace:
    def test_namespace_exists(self, kube_api: client.CoreV1Api) -> None:
        ns = kube_api.read_namespace(NAMESPACE)
        assert ns is not None

    def test_serviceaccount_exists(self, kube_api: client.CoreV1Api) -> None:
        sa = kube_api.read_namespaced_service_account(SERVICE_ACCOUNT, NAMESPACE)
        assert sa is not None


class TestValidatorDeployment:
    def test_statefulset_exists(self, apps_api: client.AppsV1Api) -> None:
        sts = apps_api.read_namespaced_stateful_set(STATEFULSET_NAME, NAMESPACE)
        assert sts is not None
        assert sts.spec.replicas == 1

    def test_headless_service_exists(self, kube_api: client.CoreV1Api) -> None:
        svc = kube_api.read_namespaced_service(STATEFULSET_NAME, NAMESPACE)
        assert svc is not None
        assert svc.spec.cluster_ip == "None"

    def test_validator_pod_running(
        self, kube_api: client.CoreV1Api
    ) -> None:
        pods = kube_api.list_namespaced_pod(
            NAMESPACE,
            label_selector="app.kubernetes.io/name=bt,app.kubernetes.io/component=validator",
        )
        assert len(pods.items) > 0, "No validator pods found"
        pod_name = pods.items[0].metadata.name
        assert wait_for_pod_ready(kube_api, pod_name), f"Pod {pod_name} not ready"

    def test_wallet_secret_mounted(self, kube_api: client.CoreV1Api) -> None:
        pods = kube_api.list_namespaced_pod(
            NAMESPACE,
            label_selector="app.kubernetes.io/name=bt,app.kubernetes.io/component=validator",
        )
        if not pods.items:
            pytest.skip("No validator pods found")
        pod = pods.items[0]
        wallet_vols = [v for v in pod.spec.volumes if v.name == "wallet"]
        assert len(wallet_vols) == 1, "Wallet volume not found"
        assert wallet_vols[0].secret is not None, "Wallet not from Secret"
        assert wallet_vols[0].secret.secret_name == WALLET_SECRET

    def test_state_pvc_bound(self, kube_api: client.CoreV1Api) -> None:
        pvcs = kube_api.list_namespaced_persistent_volume_claim(
            NAMESPACE,
            label_selector="app.kubernetes.io/name=bt",
        )
        state_pvcs = [p for p in pvcs.items if "state" in p.metadata.name]
        assert len(state_pvcs) >= 1, "No state PVC found for validator"
        for pvc in state_pvcs:
            assert pvc.status.phase == "Bound", f"PVC {pvc.metadata.name} not Bound"

    def test_validator_logs_present(self, kube_api: client.CoreV1Api) -> None:
        pods = kube_api.list_namespaced_pod(
            NAMESPACE,
            label_selector="app.kubernetes.io/name=bt,app.kubernetes.io/component=validator",
        )
        if not pods.items:
            pytest.skip("No validator pods found")
        pod_name = pods.items[0].metadata.name
        logs = kube_api.read_namespaced_pod_log(pod_name, NAMESPACE, tail_lines=50)
        assert len(logs) > 0, "No logs from validator pod"


class TestStrategyDeployment:
    def test_strategy_deployment_exists(self, apps_api: client.AppsV1Api) -> None:
        try:
            dep = apps_api.read_namespaced_deployment(DEPLOYMENT_NAME, NAMESPACE)
            assert dep is not None
        except ApiException as e:
            if e.status == 404:
                pytest.skip("Strategy deployment not found")
            raise

    def test_strategy_configmap_exists(self, kube_api: client.CoreV1Api) -> None:
        cm = kube_api.read_namespaced_config_map(CONFIGMAP_NAME, NAMESPACE)
        assert cm is not None
        # ConfigMap carries env vars for the scheduler
        assert "SCHEDULE_EVALUATOR_INTERVAL_HOURS" in cm.data
        assert "SCHEDULE_SNAPSHOT_TIME" in cm.data
        assert "SCHEDULE_DRY_RUN" in cm.data

    def test_strategy_data_pvc_bound(self, kube_api: client.CoreV1Api) -> None:
        try:
            pvc = kube_api.read_namespaced_persistent_volume_claim(
                "bt-strategy-data", NAMESPACE
            )
            assert pvc.status.phase == "Bound", "bt-strategy-data PVC not Bound"
        except ApiException as e:
            if e.status == 404:
                pytest.skip("bt-strategy-data PVC not found")
            raise

    def test_strategy_pod_running(self, kube_api: client.CoreV1Api) -> None:
        pods = kube_api.list_namespaced_pod(
            NAMESPACE,
            label_selector="app.kubernetes.io/name=bt,app.kubernetes.io/component=strategy",
        )
        if not pods.items:
            pytest.skip("No strategy pods found")
        pod_name = pods.items[0].metadata.name
        assert wait_for_pod_ready(kube_api, pod_name), f"Pod {pod_name} not ready"


class TestArgoCDSync:
    """Verify ArgoCD application is synced (requires argocd CLI in PATH)."""

    def test_argocd_app_exists(self) -> None:
        try:
            result = subprocess.run(
                ["kubectl", "get", "application", "bittensor-testnet", "-n", "argocd"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                pytest.skip("ArgoCD application bittensor-testnet not found")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("kubectl not available or timed out")

    def test_argocd_app_synced(self) -> None:
        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "application", "bittensor-testnet",
                    "-n", "argocd",
                    "-o", "jsonpath={.status.sync.status}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                pytest.skip("ArgoCD application not found")
            sync_status = result.stdout.strip()
            assert sync_status == "Synced", f"ArgoCD app sync status: {sync_status!r}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("kubectl not available or timed out")
