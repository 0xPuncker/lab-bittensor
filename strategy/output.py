"""Render SubnetMetrics as CLI table or structured JSON."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from strategy.scoring import SubnetMetrics

if TYPE_CHECKING:
    pass


def render_table(metrics: list[SubnetMetrics], console: Console | None = None) -> None:
    """Print a ranked table of subnets to stdout."""
    console = console or Console()
    table = Table(title="Bittensor subnets — ranked by emission/epoch")
    table.add_column("netuid", justify="right", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("emission/epoch (τ)", justify="right")
    table.add_column("saturation", justify="right")
    table.add_column("perm threshold (τ)", justify="right")
    table.add_column("top-N stake (τ)", justify="right")
    table.add_column("reg cost (τ)", justify="right")
    table.add_column("alpha (τ)", justify="right")
    table.add_column("notes")

    for m in metrics:
        table.add_row(
            str(m.netuid),
            m.name,
            f"{m.subnet_emission_tao:.4f}",
            f"{m.saturation * 100:.1f}%",
            f"{m.validator_permit_threshold_tao:.2f}",
            f"{m.top_validator_stake_tao:.2f}",
            f"{m.registration_cost_tao:.4f}",
            f"{m.alpha_price_tao:.6f}",
            ", ".join(m.notes) if m.notes else "",
        )

    console.print(table)


def write_json(metrics: list[SubnetMetrics], path: Path) -> None:
    """Write a structured JSON file with all metric fields.

    Use `default=str` so any unexpected types serialize via str() instead of
    raising. SubnetMetrics is plain dataclass so asdict() works directly.
    """
    payload = {
        "metrics": [asdict(m) for m in metrics],
        "count": len(metrics),
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
