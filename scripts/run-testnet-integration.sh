#!/usr/bin/env bash
# Run testnet integration tests using the local WSL bittensor wallet.
#
# Usage (from Windows terminal):
#   MSYS_NO_PATHCONV=1 wsl bash /mnt/c/Users/User/Documents/Claude/lab-bittensor/scripts/run-testnet-integration.sh
#
# Optional overrides (env vars, set before invoking):
#   BT_TESTNET_WALLET  — wallet name  (default: auto-detected from ~/.bittensor/wallets/)
#   BT_TESTNET_HOTKEY  — hotkey name  (default: "default")
#   BT_TESTNET_NETUID  — subnet netuid (default: 1)
#   PYTEST_ARGS        — extra pytest flags, e.g. "-v -k test_snapshot"
set -euo pipefail

PROJECT=/mnt/c/Users/User/Documents/Claude/lab-bittensor
PY=/home/spectrum/val-bittensor-venv/bin/python
WALLETS_DIR=/home/spectrum/.bittensor/wallets

# Auto-detect wallet if not provided
if [[ -z "${BT_TESTNET_WALLET:-}" ]]; then
    mapfile -t wallets < <(ls "$WALLETS_DIR" 2>/dev/null)
    if [[ ${#wallets[@]} -eq 0 ]]; then
        echo "ERROR: no wallets found in $WALLETS_DIR" >&2
        exit 1
    fi
    if [[ ${#wallets[@]} -gt 1 ]]; then
        echo "Multiple wallets found: ${wallets[*]}"
        echo "Set BT_TESTNET_WALLET=<name> to select one, or defaulting to first: ${wallets[0]}"
    fi
    BT_TESTNET_WALLET="${wallets[0]}"
fi

BT_TESTNET_HOTKEY="${BT_TESTNET_HOTKEY:-default}"
BT_TESTNET_NETUID="${BT_TESTNET_NETUID:-1}"

HOTKEY_PATH="$WALLETS_DIR/$BT_TESTNET_WALLET/hotkeys/$BT_TESTNET_HOTKEY"
if [[ ! -f "$HOTKEY_PATH" ]]; then
    echo "ERROR: hotkey file not found: $HOTKEY_PATH" >&2
    echo "Available hotkeys:" >&2
    ls "$WALLETS_DIR/$BT_TESTNET_WALLET/hotkeys/" 2>/dev/null >&2
    exit 1
fi

echo "Wallet:  $BT_TESTNET_WALLET"
echo "Hotkey:  $BT_TESTNET_HOTKEY"
echo "Netuid:  $BT_TESTNET_NETUID"
echo "Network: testnet (wss://test.finney.opentensor.ai)"
echo ""

cd "$PROJECT"

export BT_TESTNET_WALLET
export BT_TESTNET_HOTKEY
export BT_TESTNET_NETUID

exec "$PY" -m pytest tests/integration/test_monitor_testnet.py \
    -v \
    ${PYTEST_ARGS:-}
