#!/usr/bin/env bash
# seed-wallet-secret.sh - Create Kubernetes Secret from local Bittensor wallet
#
# Usage:
#   ./scripts/seed-wallet-secret.sh <wallet-name> [--dry-run] [--namespace <ns>]
#
# Requirements:
#   - kubectl configured for target cluster
#   - Local wallet at ~/.bittensor/wallets/<wallet-name>/
#   - Wallet files MUST be unencrypted (no password)
#
# This script creates a Secret with keys for:
#   - coldkey: private key file (for signing transactions)
#   - coldkeypub.txt: public key (for address derivation)
#   - hotkey-<name>: each hotkey under the wallet

set -euo pipefail

WALLET_NAME=""
DRY_RUN=""
NAMESPACE="bittensor-testnet"
SECRET_NAME="bt-wallet"
BITTENSOR_DIR="${HOME}/.bittensor/wallets"

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)
      DRY_RUN="--dry-run=client"
      shift
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      WALLET_NAME="$1"
      shift
      ;;
  esac
done

if [[ -z "${WALLET_NAME}" ]]; then
  echo "Usage: $0 <wallet-name-or-full-path> [--dry-run] [--namespace <ns>]" >&2
  exit 1
fi

# Accept absolute path directly (e.g. /home/spectrum/.bittensor/wallets/testnet-validator)
# or a plain wallet name resolved under BITTENSOR_DIR
if [[ "${WALLET_NAME}" == /* ]]; then
  WALLET_PATH="${WALLET_NAME}"
  WALLET_NAME="$(basename "${WALLET_NAME}")"
else
  WALLET_PATH="${BITTENSOR_DIR}/${WALLET_NAME}"
fi

if [[ ! -d "${WALLET_PATH}" ]]; then
  echo "Error: Wallet directory not found: ${WALLET_PATH}" >&2
  exit 1
fi

# Check for coldkey
if [[ ! -f "${WALLET_PATH}/coldkey" ]]; then
  echo "Error: coldkey file not found in ${WALLET_PATH}" >&2
  exit 1
fi

# Check for coldkeypub.txt
if [[ ! -f "${WALLET_PATH}/coldkeypub.txt" ]]; then
  echo "Error: coldkeypub.txt file not found in ${WALLET_PATH}" >&2
  exit 1
fi

# Find all hotkeys
HOTKEYS=($(find "${WALLET_PATH}/hotkeys" -mindepth 1 -maxdepth 1 -type f -exec basename {} \; 2>/dev/null || true))

if [[ ${#HOTKEYS[@]} -eq 0 ]]; then
  echo "Warning: No hotkeys found in ${WALLET_PATH}/hotkeys/" >&2
fi

# Build kubectl create secret command
CMD=(kubectl create secret generic "${SECRET_NAME}" -n "${NAMESPACE}")

# Add coldkey
CMD+=(--from-file="coldkey=${WALLET_PATH}/coldkey")
CMD+=(--from-file="coldkeypub.txt=${WALLET_PATH}/coldkeypub.txt")

# Add hotkeys
for hotkey in "${HOTKEYS[@]}"; do
  hotkey_path="${WALLET_PATH}/hotkeys/${hotkey}"
  if [[ -f "${hotkey_path}" ]]; then
    CMD+=(--from-file="hotkey-${hotkey}=${hotkey_path}")
  fi
done

# Add dry-run flag if requested
CMD+=(${DRY_RUN})

echo "Creating Secret '${SECRET_NAME}' in namespace '${NAMESPACE}'"
echo "Wallet: ${WALLET_NAME}"
echo "Hotkeys: ${HOTKEYS[*]:-none}"
if [[ -n "${DRY_RUN}" ]]; then
  echo "[DRY-RUN] Command:"
  echo "${CMD[*]}"
else
  echo "Running:"
  "${CMD[@]}"
  echo "Secret created successfully!"
  echo ""
  echo "Verify with:"
  echo "  kubectl get secret ${SECRET_NAME} -n ${NAMESPACE} -o yaml"
fi
