#!/bin/bash
# Setup Tailscale connectivity for Kubernetes cluster

set -e

echo "🌐 Setting up Tailscale connectivity for Kubernetes..."
echo ""

# Check Tailscale status
echo "Step 1: Checking Tailscale status..."
if tailscale status &>/dev/null; then
    echo "✓ Tailscale is connected"
    tailscale status -json | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'  Tailscale IP: {data.get(\"TailscaleIPs\", [\"Not available\"])[0]}')" 2>/dev/null || true
else
    echo "✗ Tailscale is not connected"
    echo "  Please run: sudo tailscale up"
    exit 1
fi

echo ""
echo "Step 2: Checking Kubernetes connectivity..."
# Test basic connectivity to cluster nodes
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "  Cluster node IP: $NODE_IP"

echo ""
echo "Step 3: Testing external access..."
# Check if LoadBalancer services are accessible via Tailscale
echo "  Checking ArgoCD LoadBalancer..."
ARGOCD_URL=$(kubectl get svc argocd-server -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "  ArgoCD LoadBalancer: Pending (normal during setup)")

echo ""
echo "Step 4: Current kubeconfig context..."
kubectl config current-context
echo "  Cluster: $(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"

echo ""
echo "Step 5: Testing cluster API connectivity..."
if kubectl get nodes &>/dev/null; then
    echo "✓ Successfully connected to cluster"
else
    echo "✗ Cannot connect to cluster"
    exit 1
fi

echo ""
echo "✅ Tailscale connectivity setup complete!"
echo ""
echo "To access services via Tailscale:"
echo "  ArgoCD URL: https://argocd.bifrostlabs.xyz (when LoadBalancer is ready)"
echo "  Or use: kubectl port-forward -n argocd svc/argocd-server 8080:443"
