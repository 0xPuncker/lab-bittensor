# Kubernetes Deployment Guide

This guide covers deploying val-bittensor to Kubernetes.

## Prerequisites

- Kubernetes cluster with kubeconfig configured
- kubectl configured for target cluster
- Access to ghcr.io/0xpuncker/val-bittensor image
- Bittensor wallet with unencrypted keys (SDK doesn't support passwords in headless environments)

## Quick Start

### 1. Deploy to Kubernetes

```bash
# Deploy all resources
./scripts/deploy-k8s.sh

# Or manually:
kubectl create namespace bittensor-testnet
kubectl apply -f k8s/validator-statefulset.yaml
```

### 2. Seed Wallet Secret

The wallet files MUST be unencrypted. Copy from your local wallet:

```bash
# For testnet-validator wallet
kubectl create secret generic val-bt-wallet -n bittensor-testnet \
  --from-file=coldkey=/path/to/wallet/coldkey \
  --from-file=coldkeypub.txt=/path/to/wallet/coldkeypub.txt \
  --from-file=hotkey-default=/path/to/wallet/hotkeys/default
```

### 3. Configure Environment

Edit `k8s/validator-statefulset.yaml` to configure:

**Validator settings:**
- `--wallet.name`: Your wallet name
- `--wallet.hotkey`: Hotkey to use
- `--netuid`: Subnet netuid (default: 1)
- `--subtensor.network`: "test" or "finney"

**Strategy settings (ConfigMap):**
- `SCHEDULE_EVALUATOR_INTERVAL_HOURS`: How often to run evaluation (default: 6)
- `SCHEDULE_SNAPSHOT_TIME`: When to take daily snapshot (default: "00:00")
- `SCHEDULE_ECONOMICS_TIME`: When to run economics analysis (default: "01:00")
- `SCHEDULE_DRY_RUN`: "true" for testing, "false" for production
- `LOG_LEVEL`: "DEBUG" or "INFO"

### 3. Configure Values

Edit `values.yaml` or environment-specific values:

```yaml
validator:
  enabled: true
  subnet:
    network: test  # or finney for mainnet
    netuid: 1
  wallet:
    name: "<wallet-name>"  # Must match secret
    hotkey: default
    existingSecret: val-bittensor-wallet

strategy:
  enabled: true
  schedule:
    evaluatorIntervalHours: 6
    snapshotTime: "00:00"
    economicsTime: "01:00"
    dryRun: false
```

### 4. Deploy via Helm

```bash
# Test deployment
helm install val-bittensor ../helm-charts/charts/val-bittensor \
  -n val-bittensor \
  -f ../helm-charts/charts/val-bittensor/values-test.yaml

# Production deployment
helm install val-bittensor ../helm-charts/charts/val-bittensor \
  -n val-bittensor \
  -f ../helm-charts/charts/val-bittensor/values-prod.yaml
```

### 5. Verify Deployment

```bash
# Check pods
kubectl get pods -n val-bittensor

# Check StatefulSet
kubectl get statefulset -n val-bittensor

# Check logs
kubectl logs -n val-bittensor val-bittensor-validator-0

# Describe pod for events
kubectl describe pod -n val-bittensor val-bittensor-validator-0
```

## CI/CD Pipeline

The repository includes a GitHub Actions workflow (`.github/workflows/ci-cd.yaml`) that:

1. **Builds** the Docker image on push to `main` branch
2. **Pushes** to `ghcr.io/0xpuncker/val-bittensor:<tag>`
3. **Tags** images with: branch name, commit SHA, and `latest`

**Manual workflow trigger:**
```bash
gh workflow run "Build and Push Docker Image"
```

**Monitor workflow:**
```bash
gh run list --workflow="ci-cd.yaml"
gh run view <run-id> --log
```

## ArgoCD GitOps (Production)

For production deployments, use ArgoCD for GitOps:

### Prerequisites

- ArgoCD installed in cluster
- Cluster has network access to GitHub OR SSH keys configured
- Repository accessible from cluster network

### Setup

**Option 1: Direct kubectl (Current - Development)**
```bash
kubectl apply -f k8s/validator-statefulset.yaml
```

**Option 2: ArgoCD (Production)**

Configure ArgoCD with git credentials:

```bash
# Create SSH key secret for ArgoCD
kubectl create secret generic github-ssh-key -n argocd \
  --from-file=sshPrivateKey=<path-to-private-key> \
  --from-file=known_hosts=<path-to-known-hosts>

# Update ArgoCD configmap
kubectl patch configmap argocd-cm -n argocd --type merge -p '{
  "data": {
    "repo.credentials": "- url: git@github.com:0xPuncker/lab-tao.git\n  sshPrivateKeySecret:\n    name: github-ssh-key\n    namespace: argocd"
  }
}'
```

Apply the ArgoCD application:
```bash
kubectl apply -f k8s/argocd-application.yaml
```

**Note:** If the cluster cannot access GitHub directly, consider:
- Using a git mirror accessible from the cluster network
- Using ArgoCD's `argo exec` to manually sync
- Direct kubectl deployment (current approach)

# Check application status
kubectl get application val-bittensor -n argocd -o yaml
```

### Manual Sync via ArgoCD CLI

```bash
# Login to ArgoCD
argocd login argocd.bifrostlabs.xyz --sso

# Trigger sync
argocd app sync val-bittensor

# Get application status
argocd app get val-bittensor
```

### Access ArgoCD UI

Navigate to https://argocd.bifrostlabs.xyz/ to view the val-bittensor application,
monitor deployment health, and trigger manual syncs.

## Environment Values

| File | Network | Resources | Notes |
|------|---------|-----------|-------|
| `values-dev.yaml` | test | Low (1Gi) | No persistence, strategy disabled |
| `values-test.yaml` | test | Medium (2Gi) | Dry-run mode, DEBUG logging |
| `values-prod.yaml` | finney | High (8Gi) | Live operations, INFO logging |

## Troubleshooting

### Validator Not Starting

```bash
# Check pod status
kubectl describe pod -n val-bittensor val-bittensor-validator-0

# Common issues:
# - Wallet secret not found: Verify secret exists with kubectl get secret
# - Hotkey mismatch: Check hotkey name in values.yaml matches secret key
# - Network unreachable: Verify subnet.netuid is valid for network
```

### Wallet Secret Issues

```bash
# List secret keys
kubectl get secret val-bittensor-wallet -n val-bittensor -o jsonpath='{.data}' | jq 'keys'

# Decode coldkeypub (safe to view)
kubectl get secret val-bittensor-wallet -n val-bittensor \
  -o jsonpath='{.data.coldkeypub\.txt}' | base64 -d
```

### Strategy Service Not Running

```bash
# Check deployment
kubectl get deployment -n val-bittensor val-bittensor-strategy

# Check configmap
kubectl get configmap val-bittensor-strategy-config -n val-bittensor -o yaml

# View strategy logs
kubectl logs -n val-bittensor -l app.kubernetes.io/name=val-bittensor-strategy
```

### ArgoCD Sync Issues

```bash
# Check application health and sync status via CLI
argocd app get val-bittensor --refresh

# View application details
argocd app manifest val-bittensor

# Trigger hard refresh (reconcile)
argocd app sync val-bittensor --refresh

# Check for sync errors in ArgoCD UI
# https://argocd.bifrostlabs.xyz/applications/val-bittensor
```

Common ArgoCD issues:
- **Image tag not updating**: Check that `values-image.yaml` in helm-charts was updated by CI
- **Sync failed with "manifest mismatch"**: Run `argocd app diff val-bittensor` to see what changed
- **Application "OutOfSync"**: Auto-sync may be disabled; trigger manual sync via UI or CLI
```

## Upgrading

```bash
# Helm upgrade
helm upgrade val-bittensor ../helm-charts/charts/val-bittensor \
  -n val-bittensor \
  -f ../helm-charts/charts/val-bittensor/values-test.yaml

# ArgoCD will auto-sync when values-image.yaml is updated by CI
```

## Uninstalling

```bash
# Delete Helm release
helm uninstall val-bittensor -n val-bittensor

# Delete namespace (careful!)
kubectl delete namespace val-bittensor

# Delete ArgoCD Application
kubectl delete application val-bittensor -n argocd
```
