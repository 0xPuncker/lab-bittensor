"""Score and rank subnets by on-chain attractiveness for validation.

All functions are pure with respect to their `SubnetSnapshot` input — no
RPC, no chain access. This lets us unit-test scoring exhaustively with
synthetic fixtures and reuse it under different ranking strategies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from strategy.data import SubnetSnapshot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubnetMetrics:
    """Computed metrics for one subnet.

    Pure derivation from a SubnetSnapshot — call `score_subnet(snap)` to
    produce one. All "*_tao" fields are floats in TAO units (Balance.tao
    already converts rao→tao for us).
    """

    netuid: int
    name: str
    subnet_emission_tao: float
    saturation: float
    validator_permit_threshold_tao: float
    top_validator_stake_tao: float
    registration_cost_tao: float
    alpha_price_tao: float
    num_uids: int
    max_uids: int
    max_validators: int
    notes: list[str] = field(default_factory=list)


def score_subnet(snap: SubnetSnapshot) -> SubnetMetrics:
    """Compute SubnetMetrics from a SubnetSnapshot. Pure — no RPC."""
    mi = snap.metagraph_info
    notes: list[str] = []

    saturation = mi.num_uids / mi.max_uids if mi.max_uids else 0.0
    subnet_emission_tao = float(mi.subnet_emission.tao)
    registration_cost_tao = float(mi.burn.tao)

    # Permit threshold: what stake do you need to stay in the validator top-N?
    permitted_stakes = sorted(
        (
            float(stake.tao)
            for stake, has_permit in zip(mi.total_stake, mi.validator_permit)
            if has_permit
        ),
        reverse=True,
    )
    if not permitted_stakes:
        validator_permit_threshold_tao = 0.0
        top_validator_stake_tao = 0.0
        notes.append("no_validators")
    elif len(permitted_stakes) < mi.max_validators:
        # Subnet hasn't filled its validator slots — anyone with stake > 0 can claim a permit.
        validator_permit_threshold_tao = 0.0
        top_validator_stake_tao = permitted_stakes[-1]
    else:
        # Saturated — threshold is the lowest stake among the current top-N permitted validators.
        validator_permit_threshold_tao = permitted_stakes[mi.max_validators - 1]
        top_validator_stake_tao = permitted_stakes[mi.max_validators - 1]

    if not getattr(mi, "registration_allowed", True):
        notes.append("closed_to_registration")

    return SubnetMetrics(
        netuid=mi.netuid,
        name=mi.name or f"netuid-{mi.netuid}",
        subnet_emission_tao=subnet_emission_tao,
        saturation=saturation,
        validator_permit_threshold_tao=validator_permit_threshold_tao,
        top_validator_stake_tao=top_validator_stake_tao,
        registration_cost_tao=registration_cost_tao,
        alpha_price_tao=snap.alpha_price_tao,
        num_uids=mi.num_uids,
        max_uids=mi.max_uids,
        max_validators=mi.max_validators,
        notes=notes,
    )


def rank_subnets(metrics: list[SubnetMetrics]) -> list[SubnetMetrics]:
    """Rank subnets by emission descending; tiebreaker is lower saturation.

    Higher emission = more reward to capture; on ties, less-saturated subnets
    are easier to enter and to maintain a permit on, so they're ranked higher.
    """
    return sorted(metrics, key=lambda m: (-m.subnet_emission_tao, m.saturation))
