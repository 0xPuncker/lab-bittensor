"""Unit tests for strategy.scoring (offline, synthetic fixtures)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from strategy.data import SubnetSnapshot
from strategy.scoring import rank_subnets, score_subnet


@dataclass
class _FakeBalance:
    """Minimal Balance stand-in exposing .tao."""

    tao: float


@dataclass
class _FakeMetagraphInfo:
    """Just the MetagraphInfo fields scoring reads — keeps tests independent of bittensor SDK shape."""

    netuid: int
    name: str
    num_uids: int
    max_uids: int
    max_validators: int
    subnet_emission: _FakeBalance
    burn: _FakeBalance
    total_stake: list[_FakeBalance]
    validator_permit: list[bool]
    registration_allowed: bool = True


def _snap(
    netuid: int = 1,
    name: str = "test-subnet",
    num_uids: int = 10,
    max_uids: int = 256,
    max_validators: int = 64,
    subnet_emission_tao: float = 1.0,
    burn_tao: float = 0.5,
    alpha_price_tao: float = 0.001,
    stakes: list[float] | None = None,
    permits: list[bool] | None = None,
    registration_allowed: bool = True,
) -> SubnetSnapshot:
    """Build a SubnetSnapshot wrapping a fake MetagraphInfo."""
    if stakes is None:
        stakes = [100.0] * num_uids
    if permits is None:
        permits = [False] * num_uids

    mi = _FakeMetagraphInfo(
        netuid=netuid,
        name=name,
        num_uids=num_uids,
        max_uids=max_uids,
        max_validators=max_validators,
        subnet_emission=_FakeBalance(tao=subnet_emission_tao),
        burn=_FakeBalance(tao=burn_tao),
        total_stake=[_FakeBalance(tao=s) for s in stakes],
        validator_permit=permits,
        registration_allowed=registration_allowed,
    )
    return SubnetSnapshot(
        netuid=netuid,
        metagraph_info=mi,
        alpha_price_tao=alpha_price_tao,
        fetched_at=time.time(),
    )


# -------- Tests --------


def test_saturation_computes_correctly() -> None:
    snap = _snap(num_uids=128, max_uids=256)
    metrics = score_subnet(snap)
    assert metrics.saturation == pytest.approx(0.5)


def test_permit_threshold_zero_when_no_validators() -> None:
    snap = _snap(num_uids=10, permits=[False] * 10)
    metrics = score_subnet(snap)
    assert metrics.validator_permit_threshold_tao == 0.0
    assert metrics.top_validator_stake_tao == 0.0
    assert "no_validators" in metrics.notes


def test_permit_threshold_zero_when_under_max_validators() -> None:
    """Subnet has 5 permitted validators but max_validators=64 — not saturated."""
    stakes = [100.0, 80.0, 60.0, 40.0, 20.0] + [0.0] * 5
    permits = [True] * 5 + [False] * 5
    snap = _snap(num_uids=10, max_validators=64, stakes=stakes, permits=permits)
    metrics = score_subnet(snap)
    assert metrics.validator_permit_threshold_tao == 0.0
    # top_validator_stake_tao = lowest currently-permitted (since not saturated)
    assert metrics.top_validator_stake_tao == 20.0
    assert "no_validators" not in metrics.notes


def test_permit_threshold_when_saturated() -> None:
    """5 permitted, max_validators=3 → saturated. Threshold = 3rd-highest stake."""
    stakes = [100.0, 80.0, 60.0, 40.0, 20.0]
    permits = [True] * 5
    snap = _snap(num_uids=5, max_validators=3, stakes=stakes, permits=permits)
    metrics = score_subnet(snap)
    assert metrics.validator_permit_threshold_tao == 60.0
    assert metrics.top_validator_stake_tao == 60.0


def test_closed_to_registration_tagged() -> None:
    snap = _snap(registration_allowed=False)
    metrics = score_subnet(snap)
    assert "closed_to_registration" in metrics.notes


def test_ranking_emission_desc_then_saturation() -> None:
    """Higher emission ranks first; on ties, lower saturation wins."""
    snap_a = _snap(netuid=1, subnet_emission_tao=10.0, num_uids=128, max_uids=256)
    snap_b = _snap(netuid=2, subnet_emission_tao=10.0, num_uids=200, max_uids=256)
    snap_c = _snap(netuid=3, subnet_emission_tao=20.0, num_uids=200, max_uids=256)
    ranked = rank_subnets([score_subnet(s) for s in [snap_a, snap_b, snap_c]])
    assert [m.netuid for m in ranked] == [3, 1, 2]


def test_score_is_pure_no_rpc_needed() -> None:
    """score_subnet doesn't call out — operates only on SubnetSnapshot."""
    snap = _snap()
    metrics = score_subnet(snap)
    # If score_subnet needed a subtensor, building snap without one would have already failed.
    assert metrics.netuid == snap.netuid
