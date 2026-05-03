#!/bin/bash
# Setup local pip cache for faster development

set -e

echo "🚀 Setting up local pip cache for faster development..."
echo ""

# Create pip cache directory if it doesn't exist
CACHE_DIR="$HOME/.cache/pip"
mkdir -p "$CACHE_DIR"

echo "✓ Cache directory: $CACHE_DIR"
echo ""

# Pre-install common dependencies to warm up cache
echo "Step 1: Installing development dependencies..."
pip install --upgrade pip
pip install mypy ruff pytest pip-audit bandit[toml] detect-secrets
echo "✓ Development tools installed"
echo ""

echo "Step 2: Installing project dependencies..."
pip install -r requirements.txt
echo "✓ Project dependencies installed"
echo ""

echo "Step 3: Installing heavy dependencies for faster subsequent runs..."
pip install --upgrade bittensor kubernetes torch
echo "✓ Heavy dependencies cached"
echo ""

echo "✅ Local cache setup complete!"
echo ""
echo "Cache benefits:"
echo "  - Faster subsequent installs"
echo "  - Reduced network calls during development"
echo "  - Consistent dependency versions"
echo ""
echo "To verify cache is working:"
echo "  pip cache info"
echo ""
echo "To clear cache if needed:"
echo "  pip cache purge"