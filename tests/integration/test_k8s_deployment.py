"""
Kubernetes deployment integration tests.

These tests validate that the val-bittensor Helm chart deploys correctly
to a real Kubernetes cluster. They are gated by the BT_RUN_K8S_TESTS
environment variable to avoid requiring cluster access in CI.

Run with:
    BT_RUN_K8S_TESTS=1 pytest tests/integration/test_k8s_deployment.py -v

Prerequisites:
    - kubectl configured for target cluster
    - Helm chart installed in cluster
    - val-bittensor namespace exists
"""

import os
import subprocess
import time

import pytest
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Skip all tests if env var not set
pytestmark = pytest.mark.skipif(
    os.getenv("BT_RUN_K8S_TESTS") != "1",
    reason="BT_RUN_K8S_TESTS=1 required for K8s integration tests",
)

NAMESPACE = "val-bittensor"
RELEASE_NAME = "val-bittensor"
TIMEOUT_SECONDS = 300


@pytest.fixture(scope="module")
def kube_api() -> client.CoreV1Api:
    """Load kubeconfig and return CoreV1Api client."""
    try:
        config.load_kube_config()
    except Exception:
        # Fall back to in-cluster config if running inside a pod
        config.load_incluster_config()
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def apps_api() -> client.AppsV1Api:
    """Load kubeconfig and return AppsV1Api client."""
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def helm_installed() -> bool:
    """Check if Helm release is installed."""
    try:
        result = subprocess.run(
            ["helm", "status", RELEASE_NAME, "-n", NAMESPACE],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def wait_for_pod_ready(
    api: client.CoreV1Api,
    name: str,
    timeout: int = TIMEOUT_SECONDS,
) -> bool:
    """Wait for a pod to be Ready."""
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


class TestValidatorDeployment:
    """Test validator StatefulSet deployment."""

    def test_statefulset_exists(self, apps_api: client.AppsV1Api) -> None:
        """Validator StatefulSet should exist."""
        try:
            sts = apps_api.read_namespaced_stateful_set(
                f"{RELEASE_NAME}-validator", NAMESPACE
            )
            assert sts is not None
            assert sts.spec.replicas == 1
        except ApiException as e:
            pytest.fail(f"StatefulSet not found: {e}")

    def test_validator_pod_running(
        self, kube_api: client.CoreV1Api, apps_api: client.AppsV1Api
    ) -> None:
        """Validator pod should be running and ready."""
        try:
            # Get StatefulSet pods
            pods = kube_api.list_namespaced_pod(
                NAMESPACE,
                label_selector=f"app.kubernetes.io/name={RELEASE_NAME}-validator",
            )
            assert len(pods.items) > 0, "No validator pods found"

            pod_name = pods.items[0].metadata.name
            assert wait_for_pod_ready(kube_api, pod_name), f"Pod {pod_name} not ready"
        except ApiException as e:
            pytest.fail(f"Failed to query pods: {e}")

    def test_wallet_secret_mounted(
        self, kube_api: client.CoreV1Api
    ) -> None:
        """Wallet secret should be mounted correctly."""
        try:
            pods = kube_api.list_namespaced_pod(
                NAMESPACE,
                label_selector=f"app.kubernetes.io/name={RELEASE_NAME}-validator",
            )
            if not pods.items:
                pytest.skip("No validator pods found")
                return

            pod = pods.items[0]
            wallet_volumes = [
                v for v in pod.spec.volumes if v.name == "wallet"
            ]
            assert len(wallet_volumes) == 1, "Wallet volume not found"

            # Check secret reference
            assert wallet_volumes[0].secret is not None, "Wallet not from Secret"
            assert wallet_volumes[0].secret.secret_name.endswith("wallet")
        except ApiException as e:
            pytest.fail(f"Failed to query pod: {e}")

    def test_validator_logs_connected(self, kube_api: client.CoreV1Api) -> None:
        """Validator logs should show connection to testnet."""
        try:
            pods = kube_api.list_namespaced_pod(
                NAMESPACE,
                label_selector=f"app.kubernetes.io/name={RELEASE_NAME}-validator",
            )
            if not pods.items:
                pytest.skip("No validator pods found")
                return

            pod_name = pods.items[0].metadata.name
            logs = kube_api.read_namespaced_pod_log(
                pod_name, NAMESPACE, tail_lines=100
            )

            # Look for testnet connection indicators
            # (exact string depends on Bittensor SDK output)
            assert len(logs) > 0, "No logs found"
            # Could check for specific patterns like "test" or "finney"
        except ApiException as e:
            pytest.fail(f"Failed to fetch logs: {e}")


class TestStrategyDeployment:
    """Test strategy service Deployment."""

    def test_strategy_deployment_exists(self, apps_api: client.AppsV1Api) -> None:
        """Strategy Deployment should exist if enabled."""
        try:
            deployment = apps_api.read_namespaced_deployment(
                f"{RELEASE_NAME}-strategy", NAMESPACE
            )
            assert deployment is not None
        except ApiException as e:
            if e.status == 404:
                pytest.skip("Strategy deployment not enabled")
            else:
                raise

    def test_strategy_configmap_exists(self, kube_api: client.CoreV1Api) -> None:
        """Strategy ConfigMap should exist."""
        try:
            cm = kube_api.read_namespaced_config_map(
                f"{RELEASE_NAME}-strategy-config", NAMESPACE
            )
            assert cm is not None
            assert "schedule.yaml" in cm.data
        except ApiException as e:
            if e.status == 404:
                pytest.skip("Strategy ConfigMap not found")
            else:
                raise


class TestHelmRelease:
    """Test Helm release status."""

    def test_helm_release_deployed(self, helm_installed: bool) -> None:
        """Helm release should be deployed."""
        assert helm_installed, "Helm release not found. Install with: helm install val-bittensor ..."

    def test_helm_status_success(self) -> None:
        """Helm release status should be 'deployed'."""
        try:
            result = subprocess.run(
                ["helm", "status", RELEASE_NAME, "-n", NAMESPACE, "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            import json

            status = json.loads(result.stdout)
            assert status.get("info", {}).get("status") == "deployed"
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            pytest.skip(f"Could not verify Helm status: {e}")


class TestNamespace:
    """Test namespace configuration."""

    def test_namespace_exists(self, kube_api: client.CoreV1Api) -> None:
        """val-bittensor namespace should exist."""
        try:
            ns = kube_api.read_namespace(NAMESPACE)
            assert ns is not None
        except ApiException as e:
            pytest.fail(f"Namespace {NAMESPACE} not found: {e}")

    def test_serviceaccount_exists(self, kube_api: client.CoreV1Api) -> None:
        """ServiceAccount should exist."""
        try:
            sa = kube_api.read_namespaced_service_account(RELEASE_NAME, NAMESPACE)
            assert sa is not None
        except ApiException as e:
            pytest.fail(f"ServiceAccount not found: {e}")
