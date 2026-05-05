#!/usr/bin/env bash
# Run testnet integration tests for strategy.monitor.
#
# The registered validator hotkey lives in the k8s Secret (not the local WSL
# wallet), so this script defaults to the known SS58 address for UID 103.
# Override any value via env vars before invoking.
#
# Usage (from Windows terminal — no extra config needed):
#   MSYS_NO_PATHCONV=1 wsl bash /mnt/c/Users/User/Documents/Claude/lab-bittensor/scripts/run-testnet-integration.sh
#
# Override env vars:
#   BT_TESTNET_HOTKEY_SS58  hotkey SS58 address   (default: UID 103's registered key)
#   BT_TESTNET_NETUID       subnet netuid          (default: 1)
#   PYTEST_ARGS             extra pytest flags     (e.g. "-k test_snapshot")
#
# If local wallet files ARE present and you prefer wallet-file lookup:
#   BT_TESTNET_WALLET=testnet-validator BT_TESTNET_HOTKEY=default \
#     MSYS_NO_PATHCONV=1 wsl bash scripts/run-testnet-integration.sh
set -euo pipefail

PROJECT=/mnt/c/Users/User/Documents/Claude/lab-bittensor
PY=/home/spectrum/val-bittensor-venv/bin/python

# UID 103 on testnet netuid 1 — the running validator's registered hotkey.
# Update this if the validator is re-registered with a new hotkey.
KNOWN_UID103_SS58="5GeZk5v8JPwNE8CVXrSLkkPnEE1UpBvfuqApBALS7SLPmh1i"

BT_TESTNET_NETUID="${BT_TESTNET_NETUID:-1}"

# Resolve hotkey SS58: explicit override > known registered key > wallet file lookup
if [[ -n "${BT_TESTNET_HOTKEY_SS58:-}" ]]; then
    MODE="ss58-direct"
elif [[ -n "${BT_TESTNET_WALLET:-}" ]]; then
    MODE="wallet-file"
else
    # Default: use the known registered SS58 for our deployment
    BT_TESTNET_HOTKEY_SS58="$KNOWN_UID103_SS58"
    MODE="ss58-default"
fi

echo "Network: testnet (wss://test.finney.opentensor.ai)"
echo "Netuid:  $BT_TESTNET_NETUID"

case "$MODE" in
    ss58-default)
        echo "Hotkey:  $BT_TESTNET_HOTKEY_SS58  (UID 103 registered key — default)"
        ;;
    ss58-direct)
        echo "Hotkey:  $BT_TESTNET_HOTKEY_SS58  (BT_TESTNET_HOTKEY_SS58 override)"
        ;;
    wallet-file)
        BT_TESTNET_HOTKEY="${BT_TESTNET_HOTKEY:-default}"
        WALLETS_DIR=/home/spectrum/.bittensor/wallets
        HOTKEY_PATH="$WALLETS_DIR/$BT_TESTNET_WALLET/hotkeys/$BT_TESTNET_HOTKEY"
        if [[ ! -f "$HOTKEY_PATH" ]]; then
            echo "ERROR: hotkey file not found: $HOTKEY_PATH" >&2
            echo "Available hotkeys in $WALLETS_DIR/$BT_TESTNET_WALLET/hotkeys/:" >&2
            ls "$WALLETS_DIR/$BT_TESTNET_WALLET/hotkeys/" 2>/dev/null >&2
            exit 1
        fi
        echo "Wallet:  $BT_TESTNET_WALLET / $BT_TESTNET_HOTKEY  (wallet-file lookup)"
        export BT_TESTNET_WALLET BT_TESTNET_HOTKEY
        ;;
esac

echo ""

cd "$PROJECT"

export BT_TESTNET_HOTKEY_SS58
export BT_TESTNET_NETUID

exec "$PY" -m pytest tests/integration/test_monitor_testnet.py \
    -v \
    ${PYTEST_ARGS:-}
