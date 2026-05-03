#!/bin/bash
# Deploy bt-validator to Kubernetes (ArgoCD-managed)

set -e

NAMESPACE="bittensor-testnet"

echo "🚀 Deploying Bittensor Validator via ArgoCD..."
echo ""

echo "Step 1: Creating namespace $NAMESPACE..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

echo "Step 2: Creating wallet secret..."
WALLET_DIR="${HOME}/.bittensor/wallets/testnet-validator"
kubectl create secret generic bt-wallet -n "$NAMESPACE" \
  --from-file=coldkey="${WALLET_DIR}/coldkey" \
  --from-file=coldkeypub.txt="${WALLET_DIR}/coldkeypub.txt" \
  --from-file=hotkey-default="${WALLET_DIR}/hotkeys/default" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Step 3: Deploying ArgoCD application..."
kubectl apply -f k8s/argocd-application.yaml

echo "Step 4: Waiting for ArgoCD sync..."
echo "   (This may take a few minutes for first deployment)"
sleep 10

echo ""
echo "✅ Deployment initiated via ArgoCD!"
echo ""
echo "To check ArgoCD status:"
echo "  kubectl get application bittensor-testnet -n argocd"
echo ""
echo "To check pods:"
echo "  kubectl get pods -n $NAMESPACE"
echo ""
echo "To view validator logs:"
echo "  kubectl logs -n $NAMESPACE bt-validator-0 -f"
echo ""
echo "To view strategy logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/component=strategy -f"
