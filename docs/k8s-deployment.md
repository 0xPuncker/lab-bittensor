# Kubernetes Deployment Guide

Deploy val-bittensor to Kubernetes via raw manifests + ArgoCD GitOps. The CI/CD pipeline
builds and pushes Docker images, updates `k8s/bittensor-testnet.yaml` with the new tag,
and ArgoCD auto-syncs the cluster from this repo.

---

## Architecture

```
push to main
    └─▶ GitHub Actions (build-and-deploy.yaml)
            ├─ sensors: mypy · ruff · pytest · pip-audit · bandit
            ├─ docker build + push → ghcr.io/0xpuncker/val-bittensor:<branch-sha>
            └─ sed k8s/bittensor-testnet.yaml → commit + push [ci skip]
                    └─▶ ArgoCD watches k8s/ in this repo
                                └─▶ kubectl apply → bittensor-testnet namespace
```

**Resources in `k8s/bittensor-testnet.yaml`:**
- `ServiceAccount` — `bt`
- `Service` (headless) — `bt-validator` (required by StatefulSet)
- `ConfigMap` — `bt-strategy-config`
- `StatefulSet` — `bt-validator` (1 replica, PVC for chain state)
- `PersistentVolumeClaim` — `bt-strategy-data` (1 Gi, for alpha_history.db)
- `Deployment` — `bt-strategy` (scheduler, reads PVC at /app/.data)

---

## Go-Live Checklist

### Step 1 — Push ArgoCD Application (operator, one-time)

```bash
kubectl apply -f k8s/argocd-application.yaml
```

Verify ArgoCD sees the app:
```bash
kubectl get application bittensor-testnet -n argocd
```

### Step 2 — Create the wallet Secret (operator, one-time)

Wallet files must be **unencrypted** (Bittensor SDK does not support passwords in
headless/pod environments). Generate or copy from your local wallet:

```bash
# From WSL: wallet lives under ~/.bittensor/wallets/<name>/
WALLET_DIR="$HOME/.bittensor/wallets/testnet-validator"

kubectl create namespace bittensor-testnet 2>/dev/null || true

kubectl create secret generic bt-wallet \
  -n bittensor-testnet \
  --from-file=coldkey="${WALLET_DIR}/coldkey" \
  --from-file=coldkeypub.txt="${WALLET_DIR}/coldkeypub.txt" \
  --from-file=hotkey-default="${WALLET_DIR}/hotkeys/default"
```

> **Security warning:** this Secret stores plaintext private key material.
> Use sealed-secrets or external-secrets-operator for production hardening.

Verify the secret exists:
```bash
kubectl get secret bt-wallet -n bittensor-testnet
# Decode coldkeypub (safe to view):
kubectl get secret bt-wallet -n bittensor-testnet \
  -o jsonpath='{.data.coldkeypub\.txt}' | base64 -d
```

### Step 3 — Create a testnet subnet (operator, one-time)

Create the subnet on testnet (~100 test TAO burned). See `docs/testnet-validation.md`
for the full runbook. Quick reference:

```bash
# From WSL with btcli in venv
btcli subnet create --subtensor.network test --wallet.name testnet-validator
# Note the assigned netuid
```

Register the validator hotkey on the new subnet:
```bash
btcli subnet register \
  --netuid <YOUR_NETUID> \
  --subtensor.network test \
  --wallet.name testnet-validator \
  --wallet.hotkey default
```

Then update the netuid in the StatefulSet command in `k8s/bittensor-testnet.yaml`:
```yaml
command:
  - python
  - neurons/validator.py
  - --netuid
  - "<YOUR_NETUID>"    # ← set your actual netuid here
```

### Step 4 — Trigger first CI build

Push any commit to `main` (or run the workflow manually via GitHub Actions UI).
The pipeline will:
1. Build and push `ghcr.io/0xpuncker/val-bittensor:main-<sha>`
2. Update `k8s/bittensor-testnet.yaml` with the new tag
3. Commit + push (ArgoCD detects this and syncs the cluster)

Monitor the run:
```bash
gh run list --workflow="Build and Deploy"
gh run view <run-id> --log
```

### Step 5 — Verify deployment

```bash
# Check all resources
kubectl get all,pvc,secret -n bittensor-testnet

# StatefulSet validator pod (bt-validator-0)
kubectl logs -n bittensor-testnet bt-validator-0 --tail=50 -f

# Strategy deployment pod
kubectl logs -n bittensor-testnet \
  -l app.kubernetes.io/component=strategy --tail=50 -f

# Describe if a pod won't start
kubectl describe pod -n bittensor-testnet bt-validator-0
```

---

## On-Chain Verification with verify_validator

Once the validator pod is running, confirm it is registered and participating on-chain:

```bash
python -m strategy.verify_validator \
  --hotkey <YOUR_HOTKEY_SS58> \
  --netuid <YOUR_NETUID> \
  --network test
```

Sample output:
```
┌─────────────────────────────────────────────────────┐
│    Validator status — netuid 42 (test)              │
├────────────────────┬────────────────────────────────┤
│ Hotkey             │ 5Grw...abc                     │
│ UID                │ 7                               │
│ Axon endpoint      │ 1.2.3.4:8091                   │
│ Stake (τ)          │ 100.0000                        │
│ Rank               │ 0.012345                        │
│ Trust              │ 0.999000                        │
│ Validator trust    │ 0.875000                        │
│ Validator permit   │ ✓                               │
│ Last update (block)│ 3456789                         │
└────────────────────┴────────────────────────────────┘

taoswap.org explorer: https://taoswap.org/explore?netuid=42
Hotkey to search:     5Grw...abc
```

Open `https://taoswap.org/explore?netuid=<YOUR_NETUID>` in a browser and search
for your hotkey to confirm it is visible in the explorer.

Export as JSON for monitoring pipelines:
```bash
python -m strategy.verify_validator \
  --hotkey <HOTKEY> --netuid <NETUID> --network test \
  --json /tmp/validator-status.json
```

---

## ArgoCD Monitoring

```bash
# Application status
argocd app get bittensor-testnet

# Trigger manual sync
argocd app sync bittensor-testnet

# View in ArgoCD UI
# https://argocd.bifrostlabs.xyz/applications/bittensor-testnet
```

Common ArgoCD issues:
- **OutOfSync after manifest push:** auto-sync polls every ~3 min; trigger manually if urgent
- **ImagePullBackOff:** confirm the image tag in `k8s/bittensor-testnet.yaml` matches
  what was pushed to `ghcr.io/0xpuncker/val-bittensor`; check GHCR package visibility (must be public or add imagePullSecrets)
- **Pod CrashLoopBackOff:** validator exits if wallet files missing — verify `bt-wallet`
  secret exists with correct key names (`coldkey`, `coldkeypub.txt`, `hotkey-default`)

---

## Rollback

```bash
# ArgoCD revision history rollback
argocd app history bittensor-testnet
argocd app rollback bittensor-testnet <REVISION>

# Or revert the manifest commit and let ArgoCD re-sync:
git revert HEAD  # reverts the last chore(k8s) image-tag commit
git push
```

> **Note:** The validator StatefulSet uses `updateStrategy: OnDelete`. To apply a
> manifest change, delete the pod manually after ArgoCD syncs:
> `kubectl delete pod bt-validator-0 -n bittensor-testnet`

---

## Teardown

```bash
kubectl delete application bittensor-testnet -n argocd
kubectl delete namespace bittensor-testnet  # deletes all resources + PVCs
```
