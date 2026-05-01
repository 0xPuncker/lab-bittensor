# Kubernetes Deployment Guide

This guide covers deploying val-bittensor to Kubernetes using Helm and ArgoCD.

## Prerequisites

- Kubernetes cluster (e.g., EX44) with kubeconfig configured
- Helm 3.x installed locally
- kubectl configured for target cluster
- Access to ghcr.io/bifrostlabs/val-bittensor image

## Quick Start

### 1. Create Namespace

```bash
kubectl create namespace val-bittensor
```

### 2. Seed Wallet Secret

**IMPORTANT:** The wallet files MUST be unencrypted (no password). The Bittensor SDK does not support encrypted wallets in headless environments.

```bash
# From val-bittensor repo:
./scripts/seed-wallet-secret.sh <wallet-name>

# Dry-run to verify:
./scripts/seed-wallet-secret.sh <wallet-name> --dry-run

# Custom namespace:
./scripts/seed-wallet-secret.sh <wallet-name> --namespace val-bittensor-prod
```

The secret creates these keys:
- `coldkey`: Private key for signing transactions
- `coldkeypub.txt`: Public key for address derivation
- `hotkey-<name>`: Each hotkey found in the wallet directory

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

## ArgoCD GitOps

### Register Application

```bash
kubectl apply -f ../helm-charts/argocd/applications/val-bittensor.yaml
```

The ArgoCD Application:
- Monitors `BifrostLabs/helm-charts` repository
- Auto-syncs changes to `charts/val-bittensor`
- Prunes resources removed from Helm chart
- Uses `values-image.yaml` for image tag (updated by CI)

### Manual Sync

```bash
# Trigger immediate sync
kubectl -n argocd patch application val-bittensor \
  --type merge -p '{"operation":{"sync":{}}}'

# Check application status
kubectl get application val-bittensor -n argocd -o yaml
```

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
