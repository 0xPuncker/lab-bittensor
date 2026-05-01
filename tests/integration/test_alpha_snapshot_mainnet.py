"""Integration test for the alpha_snapshot CLI against Bittensor mainnet (finney).

SKIPPED BY DEFAULT. Run with:
    BT_RUN_MAINNET_TESTS=1 wsl bash .adp/scripts/sensor.sh test

Costs: zero TAO. Read-only chain queries. Hits public finney RPC.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from strategy.alpha_snapshot import main as cli_main

needs_mainnet = pytest.mark.skipif(
    os.environ.get("BT_RUN_MAINNET_TESTS") != "1",
    reason="BT_RUN_MAINNET_TESTS=1 not set; skipping mainnet integration tests",
)


@needs_mainnet
def test_snapshot_against_finney(tmp_path: Path) -> None:
    """alpha_snapshot writes ≥10 rows when run against finney."""
    db = tmp_path / "alpha_history.db"
    exit_code = cli_main(["--network", "finney", "--db", str(db), "--log-level", "ERROR"])
    assert exit_code == 0
    with sqlite3.connect(db) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()
    assert count >= 10, f"expected ≥10 snapshot rows; got {count}"
