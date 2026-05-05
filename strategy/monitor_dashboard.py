"""Validator monitoring dashboard CLI.

Connects to Bittensor, takes a validator health snapshot, persists it,
detects anomalies, and renders a rich terminal table.

Run with:
    python -m strategy.monitor_dashboard --hotkey 5Grw... --netuid 1 --network test
    python -m strategy.monitor_dashboard --hotkey 5Grw... --netuid 1 --watch
    python -m strategy.monitor_dashboard --hotkey 5Grw... --netuid 1 --alert-only
    python -m strategy.monitor_dashboard --hotkey 5Grw... --netuid 1 --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from strategy.monitor import (
    AnomalyAlert,
    MonitorDB,
    NotRegisteredError,
    ValidatorSnapshot,
    detect_anomalies,
    take_snapshot,
)

log = logging.getLogger("strategy.monitor_dashboard")

DEFAULT_DB = Path(".data/monitor.db")
DEFAULT_INTERVAL = 60


def _snapshot_table(snapshot: ValidatorSnapshot) -> Table:
    table = Table(
        title=f"Validator — netuid {snapshot.netuid} ({snapshot.network})",
        show_header=False,
        expand=True,
    )
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    permit_mark = "[green]✓[/green]" if snapshot.validator_permit else "[red]✗[/red]"
    axon_str = f"{snapshot.axon_ip}:{snapshot.axon_port}"
    axon_style = "red" if snapshot.axon_ip == "0.0.0.0" else "green"
    blocks_ago = snapshot.current_block - snapshot.last_update_block

    table.add_row("UID", str(snapshot.uid))
    table.add_row("Hotkey", snapshot.hotkey[:20] + "..." if len(snapshot.hotkey) > 23 else snapshot.hotkey)
    table.add_row("Axon", f"[{axon_style}]{axon_str}[/{axon_style}]")
    table.add_row("Stake (τ)", f"{snapshot.stake_tao:.4f}")
    table.add_row("vTrust", f"{snapshot.validator_trust:.6f}")
    table.add_row("Permit", permit_mark)
    table.add_row("Last weights", f"block {snapshot.last_update_block} ({blocks_ago} blocks ago)")
    table.add_row("Current block", str(snapshot.current_block))
    table.add_row("Captured at", snapshot.captured_at[:19].replace("T", " ") + " UTC")

    return table


def _alerts_panel(alerts: list[AnomalyAlert]) -> Panel:
    if not alerts:
        return Panel(
            "[green]✓ No anomalies detected[/green]",
            title="Anomaly alerts",
            border_style="green",
        )

    text = Text()
    for a in alerts:
        color = "red" if a.severity == "critical" else "yellow"
        text.append(f"[{a.severity.upper()}] ", style=f"bold {color}")
        text.append(f"{a.code}: {a.message}\n")

    border = "red" if any(a.severity == "critical" for a in alerts) else "yellow"
    return Panel(text, title="Anomaly alerts", border_style=border)


def _render_once(snapshot: ValidatorSnapshot, alerts: list[AnomalyAlert], console: Console) -> None:
    console.print(_snapshot_table(snapshot))
    console.print(_alerts_panel(alerts))


def _do_check(
    subtensor: object,
    hotkey: str,
    netuid: int,
    network: str,
    db: MonitorDB,
) -> tuple[ValidatorSnapshot | None, list[AnomalyAlert]]:
    try:
        snapshot = take_snapshot(subtensor, hotkey, netuid, network)  # type: ignore[arg-type]
    except NotRegisteredError as exc:
        log.error("%s", exc)
        return None, []
    except RuntimeError as exc:
        log.error("RPC error: %s", exc)
        return None, []

    alerts = detect_anomalies(snapshot)
    db.record(snapshot)
    db.record_alerts(hotkey, netuid, alerts)
    return snapshot, alerts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="strategy.monitor_dashboard",
        description="Monitor a Bittensor validator's on-chain health.",
    )
    parser.add_argument("--hotkey", required=True, help="Validator hotkey ss58 address.")
    parser.add_argument("--netuid", type=int, required=True, help="Subnet netuid.")
    parser.add_argument(
        "--network",
        default="finney",
        help="Bittensor network: 'finney' (mainnet, default), 'test', or endpoint URL.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously refresh the dashboard (Ctrl+C to stop).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Refresh interval in seconds for --watch mode (default: {DEFAULT_INTERVAL}).",
    )
    parser.add_argument(
        "--alert-only",
        action="store_true",
        help="Suppress healthy output; exit 1 if any critical anomaly is found.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_path",
        help="Write snapshot + alerts to JSON after each check.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB}).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    import bittensor as bt  # deferred so module-level import doesn't require the SDK in tests

    console = Console()

    try:
        subtensor = bt.Subtensor(network=args.network)
    except Exception as exc:
        console.print(f"[red]error:[/red] cannot connect to '{args.network}': {exc}")
        return 1

    db = MonitorDB(args.db)
    has_critical = False

    if args.watch:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                snapshot, alerts = _do_check(subtensor, args.hotkey, args.netuid, args.network, db)
                if snapshot is None:
                    live.update(Panel("[red]Failed to fetch snapshot — see logs[/red]"))
                else:
                    has_critical = any(a.severity == "critical" for a in alerts)
                    if args.alert_only and not alerts:
                        live.update(Panel("[green]✓ Healthy[/green]", title="Monitor"))
                    else:
                        live.update(
                            Columns([
                                _snapshot_table(snapshot),
                                _alerts_panel(alerts),
                            ])
                        )
                    if args.json_path:
                        _write_json(snapshot, alerts, args.json_path)

                next_check = args.interval
                for remaining in range(next_check, 0, -1):
                    time.sleep(1)
                    # Update footer with countdown but keep existing panel
                    if snapshot is not None and not (args.alert_only and not alerts):
                        live.update(
                            Columns([
                                _snapshot_table(snapshot),
                                Panel(
                                    _alerts_panel(alerts).renderable,
                                    title=f"Anomaly alerts  (next in {remaining}s)",
                                    border_style="red" if has_critical else ("yellow" if alerts else "green"),
                                ),
                            ])
                        )
    else:
        snapshot, alerts = _do_check(subtensor, args.hotkey, args.netuid, args.network, db)
        if snapshot is None:
            return 1

        has_critical = any(a.severity == "critical" for a in alerts)

        if args.alert_only:
            if alerts:
                for a in alerts:
                    color = "red" if a.severity == "critical" else "yellow"
                    console.print(f"[{color}][{a.severity.upper()}] {a.code}:[/{color}] {a.message}")
            return 1 if has_critical else 0

        _render_once(snapshot, alerts, console)

        if args.json_path:
            _write_json(snapshot, alerts, args.json_path)

    return 1 if has_critical else 0


def _write_json(snapshot: ValidatorSnapshot, alerts: list[AnomalyAlert], path: Path) -> None:
    payload = {
        "snapshot": asdict(snapshot),
        "alerts": [asdict(a) for a in alerts],
    }
    path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    sys.exit(main())
