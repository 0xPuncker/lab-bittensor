"""CLI: append one snapshot of all-subnet Alpha prices to local SQLite history.

Intended to be wired to a cron / systemd timer so a price trajectory accumulates.

Run with:
    python -m strategy.alpha_snapshot
    python -m strategy.alpha_snapshot --network finney --db .data/alpha_history.db
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import bittensor as bt

from strategy.data import fetch_all_subnets
from strategy.history import record_snapshot

log = logging.getLogger("strategy.alpha_snapshot")

_DEFAULT_DB = Path(".data/alpha_history.db")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="strategy.alpha_snapshot",
        description="Append one snapshot of all-subnet Alpha→TAO prices to a local SQLite history.",
    )
    parser.add_argument("--network", default="finney", help="bittensor network (default: finney).")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB, help=f"SQLite path (default: {_DEFAULT_DB}).")
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

    inserted = record_snapshot(snapshots, args.db)
    print(f"recorded {inserted} snapshots to {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
