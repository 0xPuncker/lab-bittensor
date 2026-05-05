"""Validator monitoring — snapshots, anomaly detection, SQLite persistence.

Captures on-chain validator health metrics periodically and detects actionable
anomalies (dead axon, zero vtrust, permit lost, stale weights).

Designed to be called from strategy/monitor_dashboard.py (CLI) and from
strategy/scheduler.py (periodic k8s cron job).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bittensor as bt

# Epoch length in blocks: testnet ~100, mainnet ~360
_EPOCH_BLOCKS: dict[str, int] = {
    "test": 100,
    "testnet": 100,
    "finney": 360,
}
_DEFAULT_EPOCH_BLOCKS = 360
_STALE_EPOCHS = 4  # flag as stale after 4 missed epochs

_LOW_VTRUST_THRESHOLD = 0.05


class NotRegisteredError(Exception):
    """Raised when a hotkey is not found in the subnet metagraph."""


@dataclass
class ValidatorSnapshot:
    """One point-in-time capture of a validator's on-chain state."""

    hotkey: str
    netuid: int
    network: str
    uid: int
    axon_ip: str
    axon_port: int
    stake_tao: float
    validator_trust: float
    validator_permit: bool
    last_update_block: int
    current_block: int
    captured_at: str  # ISO-8601 UTC timestamp


@dataclass
class AnomalyAlert:
    """An actionable anomaly detected in a ValidatorSnapshot."""

    severity: str  # "warning" | "critical"
    code: str      # DEAD_AXON | ZERO_VTRUST | LOW_VTRUST | PERMIT_LOST | STALE_WEIGHTS
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS validator_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hotkey          TEXT    NOT NULL,
    netuid          INTEGER NOT NULL,
    network         TEXT    NOT NULL,
    uid             INTEGER NOT NULL,
    axon_ip         TEXT    NOT NULL,
    axon_port       INTEGER NOT NULL,
    stake_tao       REAL    NOT NULL,
    validator_trust REAL    NOT NULL,
    validator_permit INTEGER NOT NULL,
    last_update_block INTEGER NOT NULL,
    current_block   INTEGER NOT NULL,
    captured_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vs_hotkey_netuid
    ON validator_snapshots(hotkey, netuid, captured_at DESC);

CREATE TABLE IF NOT EXISTS anomaly_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotkey      TEXT NOT NULL,
    netuid      INTEGER NOT NULL,
    severity    TEXT NOT NULL,
    code        TEXT NOT NULL,
    message     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aa_hotkey_netuid
    ON anomaly_alerts(hotkey, netuid, timestamp DESC);
"""


class MonitorDB:
    """SQLite persistence for validator snapshots and anomaly alerts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._init()

    def _init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(_SCHEMA)

    def record(self, snapshot: ValidatorSnapshot) -> None:
        """Persist a snapshot. Always inserts (no deduplication by design)."""
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO validator_snapshots
                   (hotkey, netuid, network, uid, axon_ip, axon_port,
                    stake_tao, validator_trust, validator_permit,
                    last_update_block, current_block, captured_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.hotkey, snapshot.netuid, snapshot.network,
                    snapshot.uid, snapshot.axon_ip, snapshot.axon_port,
                    snapshot.stake_tao, snapshot.validator_trust,
                    int(snapshot.validator_permit),
                    snapshot.last_update_block, snapshot.current_block,
                    snapshot.captured_at,
                ),
            )

    def record_alerts(self, hotkey: str, netuid: int, alerts: list[AnomalyAlert]) -> None:
        """Persist anomaly alerts."""
        if not alerts:
            return
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """INSERT INTO anomaly_alerts (hotkey, netuid, severity, code, message, timestamp)
                   VALUES (?,?,?,?,?,?)""",
                [(hotkey, netuid, a.severity, a.code, a.message, a.timestamp) for a in alerts],
            )

    def load_history(self, hotkey: str, netuid: int, limit: int = 20) -> list[ValidatorSnapshot]:
        """Return the N most recent snapshots, newest first."""
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                """SELECT hotkey, netuid, network, uid, axon_ip, axon_port,
                          stake_tao, validator_trust, validator_permit,
                          last_update_block, current_block, captured_at
                   FROM validator_snapshots
                   WHERE hotkey = ? AND netuid = ?
                   ORDER BY captured_at DESC LIMIT ?""",
                (hotkey, netuid, limit),
            )
            return [
                ValidatorSnapshot(
                    hotkey=r[0], netuid=r[1], network=r[2], uid=r[3],
                    axon_ip=r[4], axon_port=r[5], stake_tao=r[6],
                    validator_trust=r[7], validator_permit=bool(r[8]),
                    last_update_block=r[9], current_block=r[10], captured_at=r[11],
                )
                for r in cur.fetchall()
            ]

    def load_recent_alerts(self, hotkey: str, netuid: int, limit: int = 10) -> list[AnomalyAlert]:
        """Return the N most recent anomaly alerts, newest first."""
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                """SELECT severity, code, message, timestamp
                   FROM anomaly_alerts
                   WHERE hotkey = ? AND netuid = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (hotkey, netuid, limit),
            )
            return [
                AnomalyAlert(severity=r[0], code=r[1], message=r[2], timestamp=r[3])
                for r in cur.fetchall()
            ]


def take_snapshot(
    subtensor: "bt.Subtensor",
    hotkey_ss58: str,
    netuid: int,
    network: str,
) -> ValidatorSnapshot:
    """Query the chain and return a ValidatorSnapshot.

    Raises NotRegisteredError if the hotkey is not in the subnet metagraph.
    Raises RuntimeError on connection/RPC failure.
    """
    try:
        metagraph = subtensor.metagraph(netuid)
        current_block = subtensor.get_current_block()
    except Exception as exc:
        raise RuntimeError(f"RPC failed for netuid {netuid} on {network}: {exc}") from exc

    try:
        uid = metagraph.hotkeys.index(hotkey_ss58)
    except ValueError:
        raise NotRegisteredError(
            f"hotkey {hotkey_ss58} is not registered on netuid {netuid} ({network})"
        )

    axon = metagraph.axons[uid]

    def _f(val: object) -> float:
        return float(val.item() if hasattr(val, "item") else val)  # type: ignore[union-attr]

    def _get(obj: object, *attrs: str) -> object:
        for attr in attrs:
            v = getattr(obj, attr, None)
            if v is not None:
                return v
        return None

    vtrust_raw = _get(metagraph, "Tv", "validator_trust")
    vtrust = _f(vtrust_raw[uid]) if vtrust_raw is not None else 0.0

    return ValidatorSnapshot(
        hotkey=hotkey_ss58,
        netuid=netuid,
        network=network,
        uid=uid,
        axon_ip=getattr(axon, "ip", "0.0.0.0"),
        axon_port=getattr(axon, "port", 0),
        stake_tao=_f(metagraph.S[uid]),
        validator_trust=vtrust,
        validator_permit=bool(metagraph.validator_permit[uid]),
        last_update_block=int(metagraph.last_update[uid]),
        current_block=current_block,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


def detect_anomalies(snapshot: ValidatorSnapshot) -> list[AnomalyAlert]:
    """Return a list of anomalies found in the snapshot. Empty = healthy."""
    alerts: list[AnomalyAlert] = []

    if snapshot.axon_ip == "0.0.0.0" or snapshot.axon_port == 0:
        alerts.append(AnomalyAlert(
            severity="critical",
            code="DEAD_AXON",
            message=(
                f"Axon not serving: ip={snapshot.axon_ip} port={snapshot.axon_port}. "
                "Validator is invisible to the network."
            ),
        ))

    if not snapshot.validator_permit:
        alerts.append(AnomalyAlert(
            severity="critical",
            code="PERMIT_LOST",
            message=(
                f"Validator permit lost on netuid {snapshot.netuid}. "
                "Weights will not be accepted by Yuma Consensus."
            ),
        ))

    if snapshot.validator_trust == 0.0:
        alerts.append(AnomalyAlert(
            severity="warning",
            code="ZERO_VTRUST",
            message=(
                "Validator trust is exactly 0.0. No other validator is copying our "
                "weights, or weights have never been set successfully."
            ),
        ))
    elif snapshot.validator_trust < _LOW_VTRUST_THRESHOLD:
        alerts.append(AnomalyAlert(
            severity="warning",
            code="LOW_VTRUST",
            message=(
                f"Validator trust is low ({snapshot.validator_trust:.4f} < "
                f"{_LOW_VTRUST_THRESHOLD}). Weight influence is minimal."
            ),
        ))

    epoch_blocks = _EPOCH_BLOCKS.get(snapshot.network, _DEFAULT_EPOCH_BLOCKS)
    stale_threshold = _STALE_EPOCHS * epoch_blocks
    blocks_since_update = snapshot.current_block - snapshot.last_update_block
    if blocks_since_update > stale_threshold:
        alerts.append(AnomalyAlert(
            severity="warning",
            code="STALE_WEIGHTS",
            message=(
                f"Weights last set {blocks_since_update} blocks ago "
                f"(threshold {stale_threshold} = {_STALE_EPOCHS}×epoch). "
                "Validator may have stopped or lost connectivity."
            ),
        ))

    return alerts
