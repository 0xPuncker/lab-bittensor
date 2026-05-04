#!/usr/bin/env python3
"""
Bittensor testnet k3s monitoring dashboard.

Usage:
  python scripts/bt-monitor.py            # one-shot snapshot
  python scripts/bt-monitor.py --watch    # refresh every 60s
  python scripts/bt-monitor.py -w -i 30  # refresh every 30s
  python scripts/bt-monitor.py --no-chain # skip on-chain fetch (fast mode)

Requirements: kubectl configured and pointing at the k3s cluster.
"""
import argparse
import re
import subprocess
import sys
import time
from datetime import datetime

# Windows console needs UTF-8 encoding to handle box-drawing characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

NAMESPACE = "bittensor-testnet"
VALIDATOR_POD = "bt-validator-0"
MINER_POD = "bt-miner-0"
SCORE_PATH = (
    "/home/valbittensor/.bittensor/miners"
    "/testnet-validator/default/netuid1/validator/state.npz"
)

# Fetches chain + score data from inside the validator pod.
# Metagraph sync takes ~10-25s — skipped with --no-chain.
CHAIN_SCRIPT = f"""
import bittensor as bt, numpy as np, sys
try:
    sub = bt.Subtensor(network='test')
    m = bt.Metagraph(netuid=1, network='test', lite=False)
    m.sync(subtensor=sub)
    axon = m.axons[103]
    serving = sum(1 for a in m.axons if a.is_serving)
    block = sub.get_current_block()
    data = np.load('{SCORE_PATH}')
    scores = data['scores']
    nonzero = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
    print(f"BLOCK={{block}}")
    print(f"TOTAL_UIDS={{len(m.uids)}}")
    print(f"SERVING_UIDS={{serving}}")
    print(f"UID103_IP={{axon.ip}}:{{axon.port}}")
    print(f"UID103_SERVING={{axon.is_serving}}")
    print(f"UID103_SCORE={{scores[103]:.6f}}")
    print(f"NONZERO_SCORES={{len(nonzero)}}")
except Exception as e:
    print(f"ERROR={{e}}", file=sys.stderr)
    raise
"""

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return ANSI.sub("", s)


def kubectl(*args) -> str:
    result = subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def get_pods() -> dict:
    out = kubectl("get", "pods", "-n", NAMESPACE, "--no-headers")
    pods = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name, ready, status = parts[0], parts[1], parts[2]
        # kubectl appends "(Nm ago)" to restarts when restarts > 0:
        # e.g. "1 (75m ago) 76m"  → parts[3]="1" parts[4]="(75m" parts[5]="ago)" parts[6]="76m"
        if len(parts) >= 7 and parts[4].startswith("("):
            restarts, age = parts[3], parts[6]
        elif len(parts) >= 6 and parts[4].startswith("("):
            restarts, age = parts[3], parts[5]
        else:
            restarts, age = parts[3], parts[4]
        pods[name] = {"ready": ready, "status": status, "restarts": restarts, "age": age}
    return pods


def get_logs(pod: str, tail: int = 6) -> list[str]:
    out = kubectl("logs", pod, "-n", NAMESPACE, f"--tail={tail}")
    return [strip_ansi(line) for line in out.splitlines() if line.strip()]


def get_chain_data() -> dict:
    out = kubectl(
        "exec", VALIDATOR_POD, "-n", NAMESPACE,
        "--", "python3", "-c", CHAIN_SCRIPT,
    )
    data = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def status_icon(pod: dict) -> str:
    parts = pod["ready"].split("/")
    all_ready = len(parts) == 2 and parts[0] == parts[1]
    if pod["status"] == "Running" and all_ready:
        return "✓"
    if pod["status"] in ("CrashLoopBackOff", "Error", "OOMKilled"):
        return "✗"
    return "~"


def hr(width: int = 60) -> None:
    print("─" * width)


def render(pods: dict, chain: dict, logs: dict) -> None:
    W = 62
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=" * W)
    print(f"  Bittensor Testnet Monitor   {now}")
    print("=" * W)

    # ── Chain ──────────────────────────────────────────────────
    print()
    print("  CHAIN  wss://test.finney.opentensor.ai:443")
    if "ERROR" in chain:
        print(f"  [chain fetch failed: {chain['ERROR']}]")
    elif chain:
        print(
            f"  Block {chain.get('BLOCK', '?')}   "
            f"netuid=1   "
            f"{chain.get('TOTAL_UIDS', '?')} UIDs   "
            f"{chain.get('SERVING_UIDS', '?')} serving"
        )
    else:
        print("  [chain data not fetched — run without --no-chain]")

    # ── UID 103 ────────────────────────────────────────────────
    print()
    hr(W)
    print("  UID 103  (our miner)")
    if chain and "BLOCK" in chain:
        score = chain.get("UID103_SCORE", "?")
        serving = chain.get("UID103_SERVING", "?")
        axon = chain.get("UID103_IP", "?")
        score_bar = ""
        try:
            pct = float(score)
            filled = int(pct * 20)
            score_bar = f"  [{'█' * filled}{'░' * (20 - filled)}] {pct:.3f}"
        except ValueError:
            pass
        print(f"  Axon:       {axon}")
        print(f"  is_serving: {serving}")
        print(f"  Score:      {score_bar or score}")
        print(f"  Non-zero scores in metagraph: {chain.get('NONZERO_SCORES', '?')}")

    # ── Pods ───────────────────────────────────────────────────
    print()
    hr(W)
    print(f"  {'POD':<36} {'READY':<7} {'STATUS':<14} {'RESTARTS':<10} AGE")
    hr(W)
    for name, info in pods.items():
        icon = status_icon(info)
        print(
            f"  {icon} {name:<34} {info['ready']:<7} {info['status']:<14}"
            f" {info['restarts']:<10} {info['age']}"
        )

    # ── Logs ───────────────────────────────────────────────────
    for label, lines in logs.items():
        print()
        hr(W)
        print(f"  {label} (last {len(lines)} lines)")
        hr(W)
        for line in lines:
            display = line if len(line) <= 110 else line[:107] + "..."
            print(f"  {display}")

    print()
    print("=" * W)


def find_strategy_pod(pods: dict) -> str | None:
    return next((p for p in pods if p.startswith("bt-strategy")), None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bittensor testnet k3s monitoring dashboard"
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Continuously refresh the dashboard",
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=60,
        help="Refresh interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--no-chain",
        action="store_true",
        help="Skip on-chain metagraph fetch (fast mode, no chain data)",
    )
    parser.add_argument(
        "--log-lines",
        type=int,
        default=6,
        help="Number of log lines to show per pod (default: 6)",
    )
    args = parser.parse_args()

    try:
        while True:
            pods = get_pods()
            if not pods:
                print("ERROR: no pods found — is kubectl configured correctly?", file=sys.stderr)
                sys.exit(1)

            strategy_pod = find_strategy_pod(pods)

            chain: dict = {}
            if not args.no_chain:
                print("  Fetching on-chain data...", end="", flush=True)
                try:
                    chain = get_chain_data()
                    print(" done")
                except Exception as exc:
                    chain = {"ERROR": str(exc)}
                    print(f" failed ({exc})")

            logs = {
                "VALIDATOR  bt-validator-0": get_logs(VALIDATOR_POD, args.log_lines),
                "MINER      bt-miner-0": get_logs(MINER_POD, 4),
            }
            if strategy_pod:
                logs[f"STRATEGY   {strategy_pod}"] = get_logs(strategy_pod, 4)

            render(pods, chain, logs)

            if not args.watch:
                break

            print(f"  Refreshing in {args.interval}s — Ctrl+C to stop\n")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
