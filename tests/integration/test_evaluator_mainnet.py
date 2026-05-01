"""Integration tests for the subnet evaluator against Bittensor mainnet (finney).

SKIPPED BY DEFAULT. Run with:
    BT_RUN_MAINNET_TESTS=1 wsl bash .adp/scripts/sensor.sh test

Costs: zero TAO. Read-only chain queries. Hits public finney RPC; takes
~10-30s for the full landscape fetch. Useful as a regression check after
any bittensor SDK upgrade or scoring change.
"""

from __future__ import annotations

import os

import bittensor as bt
import pytest
from strategy.data import fetch_all_subnets
from strategy.subnet_evaluator import main as cli_main

needs_mainnet = pytest.mark.skipif(
    os.environ.get("BT_RUN_MAINNET_TESTS") != "1",
    reason="BT_RUN_MAINNET_TESTS=1 not set; skipping mainnet integration tests",
)


@pytest.fixture(scope="module")
def subtensor() -> bt.Subtensor:
    return bt.Subtensor(network="finney")


@needs_mainnet
def test_fetch_all_subnets_against_finney(subtensor: bt.Subtensor) -> None:
    """fetch_all_subnets returns ≥10 subnets with populated core fields."""
    snapshots = fetch_all_subnets(subtensor)
    assert len(snapshots) >= 10, f"expected ≥10 subnets on finney; got {len(snapshots)}"
    for snap in snapshots:
        mi = snap.metagraph_info
        # subnet_emission must be present (it's the primary ranking key)
        assert mi.subnet_emission is not None, f"netuid {snap.netuid}: subnet_emission missing"
        # name SHOULD be present (netuid 0 is root, may have edge-case empty name)
        if snap.netuid != 0:
            assert mi.name is not None, f"netuid {snap.netuid}: name missing"


@needs_mainnet
def test_cli_renders_against_finney(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits 0, prints table headers, and at least 5 data rows."""
    exit_code = cli_main(["--network", "finney", "--log-level", "ERROR"])
    captured = capsys.readouterr()
    assert exit_code == 0, f"CLI returned {exit_code}; stderr: {captured.err}"
    # Headers should appear (rich.table prints these)
    assert "netuid" in captured.out
    assert "emission/epoch" in captured.out
    # At least 5 rows of data — rough check: lines with a digit in the first 10 chars
    data_lines = [
        line for line in captured.out.splitlines()
        if line.strip() and any(ch.isdigit() for ch in line[:10])
    ]
    assert len(data_lines) >= 5, f"expected ≥5 data rows; got {len(data_lines)}"
