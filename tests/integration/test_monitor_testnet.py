"""Integration tests for strategy.monitor against the real Bittensor testnet.

SKIPPED BY DEFAULT. Tests run when these env vars are set:

  BT_TESTNET_WALLET   — wallet name under ~/.bittensor/wallets/ (required)
  BT_TESTNET_HOTKEY   — hotkey name under that wallet            (default: "default")
  BT_TESTNET_NETUID   — netuid the wallet is registered to       (required)

Costs: zero TAO. All tests are read-only chain queries against
`bt.Subtensor(network="test")`. No transactions, no weight setting.

What this catches that unit tests cannot:
  - Metagraph field shape changes across bittensor SDK versions
  - Axon attribute naming drift (ip, ip_str, etc.)
  - Tensor vs. scalar inconsistencies in .S, .Tv, .last_update
  - `take_snapshot()` returning nonsense values for a live UID

Run:
    BT_TESTNET_WALLET=mywallet BT_TESTNET_HOTKEY=validator BT_TESTNET_NETUID=1 \\
      python -m pytest tests/integration/test_monitor_testnet.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import bittensor as bt
import pytest
from strategy.monitor import (
    MonitorDB,
    NotRegisteredError,
    detect_anomalies,
    take_snapshot,
)

WALLET_NAME = os.environ.get("BT_TESTNET_WALLET")
HOTKEY_NAME = os.environ.get("BT_TESTNET_HOTKEY", "default")
NETUID_ENV = os.environ.get("BT_TESTNET_NETUID")
NETUID = int(NETUID_ENV) if NETUID_ENV else None

needs_wallet = pytest.mark.skipif(
    not WALLET_NAME,
    reason="BT_TESTNET_WALLET not set; skipping monitor testnet integration tests",
)
needs_netuid = pytest.mark.skipif(
    NETUID is None,
    reason="BT_TESTNET_NETUID not set; skipping monitor testnet integration tests",
)


@pytest.fixture(scope="module")
def subtensor() -> bt.Subtensor:
    return bt.Subtensor(network="test")


@pytest.fixture(scope="module")
def hotkey_ss58() -> str:
    wallet = bt.Wallet(name=WALLET_NAME, hotkey=HOTKEY_NAME)
    return wallet.hotkey.ss58_address


@pytest.fixture(scope="module")
def live_snapshot(subtensor: bt.Subtensor, hotkey_ss58: str):
    assert NETUID is not None
    return take_snapshot(subtensor, hotkey_ss58, netuid=NETUID, network="test")


@needs_wallet
@needs_netuid
def test_take_snapshot_returns_snapshot(live_snapshot) -> None:
    """take_snapshot() succeeds against the real testnet."""
    from strategy.monitor import ValidatorSnapshot
    assert isinstance(live_snapshot, ValidatorSnapshot)


@needs_wallet
@needs_netuid
def test_snapshot_uid_is_non_negative(live_snapshot) -> None:
    assert live_snapshot.uid >= 0


@needs_wallet
@needs_netuid
def test_snapshot_netuid_matches(live_snapshot) -> None:
    assert live_snapshot.netuid == NETUID


@needs_wallet
@needs_netuid
def test_snapshot_network_is_test(live_snapshot) -> None:
    assert live_snapshot.network == "test"


@needs_wallet
@needs_netuid
def test_snapshot_current_block_advancing(live_snapshot) -> None:
    assert live_snapshot.current_block > 0


@needs_wallet
@needs_netuid
def test_snapshot_axon_fields_are_strings(live_snapshot) -> None:
    """Axon IP and port are extracted as expected types (SDK drift guard)."""
    assert isinstance(live_snapshot.axon_ip, str)
    assert isinstance(live_snapshot.axon_port, int)


@needs_wallet
@needs_netuid
def test_snapshot_stake_is_non_negative(live_snapshot) -> None:
    assert live_snapshot.stake_tao >= 0.0


@needs_wallet
@needs_netuid
def test_snapshot_vtrust_in_range(live_snapshot) -> None:
    assert 0.0 <= live_snapshot.validator_trust <= 1.0


@needs_wallet
@needs_netuid
def test_snapshot_captured_at_is_iso(live_snapshot) -> None:
    assert "T" in live_snapshot.captured_at


@needs_wallet
@needs_netuid
def test_detect_anomalies_runs_on_real_snapshot(live_snapshot) -> None:
    """detect_anomalies() accepts a real snapshot without crashing."""
    alerts = detect_anomalies(live_snapshot)
    assert isinstance(alerts, list)
    for a in alerts:
        assert a.severity in ("warning", "critical")
        assert a.code
        assert a.message


@needs_wallet
@needs_netuid
def test_unregistered_hotkey_raises(subtensor: bt.Subtensor) -> None:
    """take_snapshot() raises NotRegisteredError for a hotkey not in the metagraph."""
    assert NETUID is not None
    fake_hotkey = "5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM"
    with pytest.raises(NotRegisteredError):
        take_snapshot(subtensor, fake_hotkey, netuid=NETUID, network="test")


@needs_wallet
@needs_netuid
def test_monitordb_roundtrip_with_real_snapshot(
    live_snapshot, tmp_path: Path
) -> None:
    """A real snapshot survives a record → load_history roundtrip."""
    db = MonitorDB(tmp_path / "monitor.db")
    db.record(live_snapshot)
    history = db.load_history(live_snapshot.hotkey, netuid=NETUID, limit=5)
    assert len(history) == 1
    r = history[0]
    assert r.uid == live_snapshot.uid
    assert r.netuid == live_snapshot.netuid
    assert r.axon_ip == live_snapshot.axon_ip
    assert r.axon_port == live_snapshot.axon_port
    assert abs(r.stake_tao - live_snapshot.stake_tao) < 1e-6
    assert abs(r.validator_trust - live_snapshot.validator_trust) < 1e-6
    assert r.validator_permit == live_snapshot.validator_permit
    assert r.last_update_block == live_snapshot.last_update_block
    assert r.current_block == live_snapshot.current_block
