#!/bin/bash
# Deploy val-bittensor to Kubernetes

set -e

NAMESPACE="bittensor-testnet"

echo "Creating namespace $NAMESPACE..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating wallet secret..."
kubectl create secret generic val-bt-wallet -n "$NAMESPACE" \
  --from-file=coldkey="$HOME/.bittensor-temp/coldkey" \
  --from-file=coldkeypub.txt="$HOME/.bittensor-temp/coldkeypub.txt" \
  --from-file=hotkey-default="$HOME/.bittensor-temp/hotkey-default" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Deploying validator and strategy..."
kubectl apply -f k8s/validator-statefulset.yaml

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=val-bt -n "$NAMESPACE" --timeout=300s

echo "Deployment complete!"
echo ""
echo "Validator pod:"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=validator

echo ""
echo "Strategy pod:"
kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=strategy

echo ""
echo "View validator logs:"
echo "kubectl logs -n $NAMESPACE val-bt-validator-0 -f"
