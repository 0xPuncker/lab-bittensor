"""Fetch subnet data from a connected Bittensor Subtensor.

The killer call is `Subtensor.get_all_metagraphs_info()` — one RPC returns
`MetagraphInfo` for every netuid. Plus `Subtensor.get_subnet_prices()` for
the current Alpha→TAO price dict in one more call. So fetching the full
landscape is two RPCs, not one-per-subnet.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import bittensor as bt

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubnetSnapshot:
    """Immutable snapshot of one subnet's on-chain state at a point in time.

    Held opaquely as `metagraph_info` to avoid leaking SDK details into
    `strategy.scoring` — scoring reads only the fields it cares about.
    """

    netuid: int
    metagraph_info: Any  # bt.MetagraphInfo at runtime; Any here so tests can fake
    alpha_price_tao: float
    fetched_at: float  # Unix timestamp when the snapshot was taken


def fetch_all_subnets(subtensor: "bt.Subtensor") -> list[SubnetSnapshot]:
    """Fetch every live subnet's metagraph info + alpha price.

    Two RPC calls total:
    1. `subtensor.get_all_metagraphs_info()` → list[MetagraphInfo]
    2. `subtensor.get_subnet_prices()` → dict[netuid, Balance]

    Per-subnet snapshot construction failures are logged and skipped (graceful
    degradation) so one bad netuid doesn't kill the whole fetch.

    Returns an empty list if the chain returns nothing or both RPC calls fail.
    """
    fetched_at = time.time()

    metagraphs = subtensor.get_all_metagraphs_info()
    if not metagraphs:
        log.warning("get_all_metagraphs_info returned empty/None")
        return []

    try:
        prices = subtensor.get_subnet_prices()
    except Exception as exc:
        log.warning("get_subnet_prices failed; defaulting all to 0: %s", exc)
        prices = {}

    snapshots: list[SubnetSnapshot] = []
    for mi in metagraphs:
        try:
            netuid = mi.netuid
            price = prices.get(netuid)
            alpha_price_tao = float(price.tao) if price is not None else 0.0
            snapshots.append(
                SubnetSnapshot(
                    netuid=netuid,
                    metagraph_info=mi,
                    alpha_price_tao=alpha_price_tao,
                    fetched_at=fetched_at,
                )
            )
        except Exception as exc:
            netuid_str = getattr(mi, "netuid", "?")
            log.warning("skipping netuid %s — failed to build snapshot: %s", netuid_str, exc)
            continue

    return snapshots
