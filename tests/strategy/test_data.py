"""Tests for strategy.data — most coverage is in tests/integration/ (live mainnet)."""

from __future__ import annotations

import dataclasses

import pytest
from strategy.data import SubnetSnapshot


def test_subnet_snapshot_is_frozen() -> None:
    """SubnetSnapshot must be immutable so scoring can't accidentally mutate it."""
    snap = SubnetSnapshot(
        netuid=1,
        metagraph_info=None,
        alpha_price_tao=0.0,
        fetched_at=0.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.netuid = 2  # type: ignore[misc]
