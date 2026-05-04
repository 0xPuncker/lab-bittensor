"""Unit tests for strategy.monitor (offline, synthetic fixtures)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from strategy.monitor import (
    AnomalyAlert,
    MonitorDB,
    NotRegisteredError,
    ValidatorSnapshot,
    detect_anomalies,
    take_snapshot,
)

# ---------------------------------------------------------------------------
# Shared fake bittensor objects
# ---------------------------------------------------------------------------


@dataclass
class _FakeAxon:
    ip: str = "1.2.3.4"
    port: int = 8091


class _TensorScalar:
    def __init__(self, v: float) -> None:
        self._v = v

    def item(self) -> float:
        return self._v

    def __float__(self) -> float:
        return self._v


class _FakeTensor(list):
    def __getitem__(self, idx):  # type: ignore[override]
        return _TensorScalar(super().__getitem__(idx))


def _metagraph(
    hotkeys: list[str],
    axons: list[_FakeAxon] | None = None,
    stakes: list[float] | None = None,
    vtrusts: list[float] | None = None,
    permits: list[bool] | None = None,
    last_updates: list[int] | None = None,
):
    n = len(hotkeys)
    axons = axons or [_FakeAxon() for _ in range(n)]
    stakes = stakes or [0.0] * n
    vtrusts = vtrusts or [0.0] * n
    permits = permits or [False] * n
    last_updates = last_updates or [0] * n

    class _Meta:
        pass

    m = _Meta()
    m.hotkeys = hotkeys
    m.axons = axons
    m.S = _FakeTensor(stakes)
    m.Tv = _FakeTensor(vtrusts)
    m.validator_permit = permits
    m.last_update = last_updates
    return m


class _FakeSubtensor:
    def __init__(self, meta, current_block: int = 1_000_000, raise_on: str | None = None) -> None:
        self._meta = meta
        self._block = current_block
        self._raise_on = raise_on

    def metagraph(self, netuid: int):
        if self._raise_on == "metagraph":
            raise ConnectionError("chain unreachable")
        return self._meta

    def get_current_block(self) -> int:
        if self._raise_on == "block":
            raise ConnectionError("chain unreachable")
        return self._block


HOTKEY = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"

# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------


def test_take_snapshot_happy_path():
    axon = _FakeAxon(ip="10.0.0.1", port=8092)
    meta = _metagraph(
        hotkeys=[HOTKEY],
        axons=[axon],
        stakes=[250.0],
        vtrusts=[0.88],
        permits=[True],
        last_updates=[999_000],
    )
    sub = _FakeSubtensor(meta, current_block=1_000_000)
    snap = take_snapshot(sub, HOTKEY, netuid=1, network="test")

    assert snap.uid == 0
    assert snap.axon_ip == "10.0.0.1"
    assert snap.axon_port == 8092
    assert snap.stake_tao == pytest.approx(250.0)
    assert snap.validator_trust == pytest.approx(0.88)
    assert snap.validator_permit is True
    assert snap.last_update_block == 999_000
    assert snap.current_block == 1_000_000
    assert snap.network == "test"
    assert "T" in snap.captured_at  # ISO timestamp


def test_take_snapshot_not_registered():
    meta = _metagraph(hotkeys=["5OtherKey"])
    sub = _FakeSubtensor(meta)
    with pytest.raises(NotRegisteredError, match="not registered"):
        take_snapshot(sub, HOTKEY, netuid=1, network="test")


def test_take_snapshot_rpc_error():
    meta = _metagraph(hotkeys=[HOTKEY])
    sub = _FakeSubtensor(meta, raise_on="metagraph")
    with pytest.raises(RuntimeError, match="RPC failed"):
        take_snapshot(sub, HOTKEY, netuid=1, network="test")


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------


def _snap(**kwargs) -> ValidatorSnapshot:
    defaults = dict(
        hotkey=HOTKEY,
        netuid=1,
        network="finney",
        uid=0,
        axon_ip="1.2.3.4",
        axon_port=8091,
        stake_tao=100.0,
        validator_trust=0.5,
        validator_permit=True,
        last_update_block=999_000,
        current_block=1_000_000,
        captured_at="2026-05-04T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return ValidatorSnapshot(**defaults)


def test_no_anomalies_healthy():
    alerts = detect_anomalies(_snap())
    assert alerts == []


def test_dead_axon_zero_ip():
    alerts = detect_anomalies(_snap(axon_ip="0.0.0.0"))
    codes = {a.code for a in alerts}
    assert "DEAD_AXON" in codes
    assert any(a.severity == "critical" for a in alerts if a.code == "DEAD_AXON")


def test_dead_axon_zero_port():
    alerts = detect_anomalies(_snap(axon_port=0))
    assert any(a.code == "DEAD_AXON" for a in alerts)


def test_zero_vtrust():
    alerts = detect_anomalies(_snap(validator_trust=0.0))
    codes = {a.code for a in alerts}
    assert "ZERO_VTRUST" in codes
    assert "LOW_VTRUST" not in codes


def test_low_vtrust():
    alerts = detect_anomalies(_snap(validator_trust=0.03))
    codes = {a.code for a in alerts}
    assert "LOW_VTRUST" in codes
    assert "ZERO_VTRUST" not in codes


def test_permit_lost():
    alerts = detect_anomalies(_snap(validator_permit=False))
    codes = {a.code for a in alerts}
    assert "PERMIT_LOST" in codes
    assert any(a.severity == "critical" for a in alerts if a.code == "PERMIT_LOST")


def test_stale_weights_mainnet():
    # mainnet epoch=360, threshold=4*360=1440; blocks_ago=2000 → stale
    alerts = detect_anomalies(_snap(network="finney", last_update_block=997_999, current_block=1_000_000))
    codes = {a.code for a in alerts}
    assert "STALE_WEIGHTS" in codes


def test_not_stale_weights_recent():
    # blocks_ago=100, threshold=1440 for mainnet → healthy
    alerts = detect_anomalies(_snap(network="finney", last_update_block=999_900, current_block=1_000_000))
    assert not any(a.code == "STALE_WEIGHTS" for a in alerts)


def test_stale_weights_testnet():
    # testnet epoch=100, threshold=400; blocks_ago=500 → stale
    alerts = detect_anomalies(_snap(network="test", last_update_block=999_499, current_block=1_000_000))
    assert any(a.code == "STALE_WEIGHTS" for a in alerts)


# ---------------------------------------------------------------------------
# MonitorDB
# ---------------------------------------------------------------------------


def test_monitordb_record_and_load(tmp_path):
    db = MonitorDB(tmp_path / "monitor.db")
    snap = _snap()
    db.record(snap)
    history = db.load_history(HOTKEY, netuid=1, limit=10)
    assert len(history) == 1
    r = history[0]
    assert r.uid == snap.uid
    assert r.validator_trust == pytest.approx(snap.validator_trust)
    assert r.validator_permit == snap.validator_permit


def test_monitordb_record_alerts(tmp_path):
    db = MonitorDB(tmp_path / "monitor.db")
    alerts = [
        AnomalyAlert(severity="critical", code="DEAD_AXON", message="test alert"),
        AnomalyAlert(severity="warning", code="LOW_VTRUST", message="test low"),
    ]
    db.record_alerts(HOTKEY, netuid=1, alerts=alerts)
    recent = db.load_recent_alerts(HOTKEY, netuid=1)
    assert len(recent) == 2
    codes = {a.code for a in recent}
    assert codes == {"DEAD_AXON", "LOW_VTRUST"}


def test_monitordb_load_history_empty(tmp_path):
    db = MonitorDB(tmp_path / "monitor.db")
    assert db.load_history(HOTKEY, netuid=1) == []


def test_monitordb_load_history_limit(tmp_path):
    db = MonitorDB(tmp_path / "monitor.db")
    for i in range(5):
        db.record(_snap(last_update_block=i, current_block=1000 + i))
    history = db.load_history(HOTKEY, netuid=1, limit=3)
    assert len(history) == 3
