"""CLI entry point for the subnet evaluator.

Run with:
    python -m strategy.subnet_evaluator                        # finney, table only
    python -m strategy.subnet_evaluator --network test         # testnet
    python -m strategy.subnet_evaluator --json out.json        # also dump JSON
    python -m strategy.subnet_evaluator --log-level INFO       # verbose logging
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import bittensor as bt

from strategy.data import fetch_all_subnets
from strategy.output import render_table, write_json
from strategy.scoring import rank_subnets, score_subnet

log = logging.getLogger("strategy.subnet_evaluator")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code (0 on success, 1 on failure)."""
    parser = argparse.ArgumentParser(
        prog="strategy.subnet_evaluator",
        description="Score and rank Bittensor subnets by on-chain validator-attractiveness metrics.",
    )
    parser.add_argument(
        "--network",
        default="finney",
        help="bittensor network: 'finney' (mainnet, default), 'test' (testnet), or a chain endpoint URL.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Also write structured JSON output to this path (in addition to printing the table).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    try:
        subtensor = bt.Subtensor(network=args.network)
    except Exception as exc:
        print(f"error: failed to connect to network '{args.network}': {exc}", file=sys.stderr)
        return 1

    try:
        snapshots = fetch_all_subnets(subtensor)
    except Exception as exc:
        print(f"error: failed to fetch subnets: {exc}", file=sys.stderr)
        return 1

    if not snapshots:
        print("error: no subnets returned by the chain", file=sys.stderr)
        return 1

    metrics = rank_subnets([score_subnet(s) for s in snapshots])

    render_table(metrics)

    if args.json:
        write_json(metrics, args.json)
        log.info("wrote %d metrics to %s", len(metrics), args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
