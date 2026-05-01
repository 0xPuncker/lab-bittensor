"""CLI: compare conversion strategies head-to-head on a subnet's price history.

Run with:
    python -m strategy.alpha_economics --netuid 1
    python -m strategy.alpha_economics --netuid 1 --alpha-per-epoch 2.5 --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from strategy.history import load_history
from strategy.strategies import STRATEGIES, StrategyResult

log = logging.getLogger("strategy.alpha_economics")

_DEFAULT_DB = Path(".data/alpha_history.db")


def _render_table(netuid: int, results: list[StrategyResult], n_points: int, console: Console | None = None) -> None:
    console = console or Console()
    table = Table(title=f"Alpha→TAO conversion strategies — netuid {netuid} ({n_points} price points)")
    table.add_column("strategy", overflow="fold")
    table.add_column("tao realized", justify="right")
    table.add_column("alpha remaining", justify="right")
    table.add_column("conversions", justify="right")
    table.add_column("avg price (τ)", justify="right")
    for r in results:
        table.add_row(
            r.name,
            f"{r.tao_realized:.6f}",
            f"{r.alpha_remaining:.6f}",
            str(r.n_conversions),
            f"{r.avg_conversion_price:.6f}",
        )
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="strategy.alpha_economics",
        description="Compare Alpha→TAO conversion strategies on a subnet's local price history.",
    )
    parser.add_argument("--netuid", type=int, required=True, help="Subnet to analyse.")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB, help=f"SQLite path (default: {_DEFAULT_DB}).")
    parser.add_argument(
        "--alpha-per-epoch",
        type=float,
        default=1.0,
        help="Assumed Alpha emission per price point (default: 1.0).",
    )
    parser.add_argument("--json", type=Path, default=None, help="Also dump structured results to this path.")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    history = load_history(args.netuid, args.db)
    if not history:
        print(f"error: no history for netuid {args.netuid} in {args.db}; run alpha_snapshot first", file=sys.stderr)
        return 1

    results = [strat(args.alpha_per_epoch, history) for strat in STRATEGIES.values()]

    _render_table(args.netuid, results, len(history))

    if args.json:
        payload = {
            "netuid": args.netuid,
            "n_points": len(history),
            "ts_start": history[0].ts,
            "ts_end": history[-1].ts,
            "alpha_per_epoch": args.alpha_per_epoch,
            "results": [asdict(r) for r in results],
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2))
        log.info("wrote results to %s", args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
