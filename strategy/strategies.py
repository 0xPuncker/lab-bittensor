"""Pure conversion strategies over a price series.

Each strategy takes a per-point Alpha emission rate and a chronological list of
`PricePoint`s, and returns a `StrategyResult` describing realized TAO and
remaining Alpha. No I/O, no global state — comparable side-by-side.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from strategy.history import PricePoint

_WEEK_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class StrategyResult:
    """Outcome of running a strategy over a price series."""

    name: str
    tao_realized: float
    alpha_remaining: float
    n_conversions: int
    avg_conversion_price: float


def _empty_result(name: str) -> StrategyResult:
    return StrategyResult(name=name, tao_realized=0.0, alpha_remaining=0.0, n_conversions=0, avg_conversion_price=0.0)


def convert_immediately(alpha_per_point: float, prices: list[PricePoint]) -> StrategyResult:
    """Convert all newly-earned Alpha at every price point. Maximum liquidity, no upside."""
    if not prices:
        return _empty_result("convert_immediately")
    tao_realized = sum(alpha_per_point * p.alpha_price_tao for p in prices)
    total_alpha_converted = alpha_per_point * len(prices)
    avg_price = tao_realized / total_alpha_converted if total_alpha_converted > 0 else 0.0
    return StrategyResult(
        name="convert_immediately",
        tao_realized=tao_realized,
        alpha_remaining=0.0,
        n_conversions=len(prices),
        avg_conversion_price=avg_price,
    )


def hold_forever(alpha_per_point: float, prices: list[PricePoint]) -> StrategyResult:
    """Never convert. Pure Alpha accumulation; bets the subnet appreciates."""
    if not prices:
        return _empty_result("hold_forever")
    return StrategyResult(
        name="hold_forever",
        tao_realized=0.0,
        alpha_remaining=alpha_per_point * len(prices),
        n_conversions=0,
        avg_conversion_price=0.0,
    )


def dca_weekly(alpha_per_point: float, prices: list[PricePoint]) -> StrategyResult:
    """Convert all currently-held Alpha every 7 days, at the price at conversion time.

    First conversion lands on the first price point ≥7d after `prices[0]`. If the
    series is shorter than 7 days, nothing gets converted (everything sits in
    `alpha_remaining`).
    """
    if not prices:
        return _empty_result("dca_weekly")

    held = 0.0
    tao_realized = 0.0
    total_converted = 0.0
    n_conversions = 0
    last_conversion_ts = prices[0].ts

    for p in prices:
        held += alpha_per_point
        if p.ts - last_conversion_ts >= _WEEK_SECONDS and held > 0:
            tao_realized += held * p.alpha_price_tao
            total_converted += held
            held = 0.0
            n_conversions += 1
            last_conversion_ts = p.ts

    avg_price = tao_realized / total_converted if total_converted > 0 else 0.0
    return StrategyResult(
        name="dca_weekly",
        tao_realized=tao_realized,
        alpha_remaining=held,
        n_conversions=n_conversions,
        avg_conversion_price=avg_price,
    )


STRATEGIES: dict[str, Callable[[float, list[PricePoint]], StrategyResult]] = {
    "convert_immediately": convert_immediately,
    "hold_forever": hold_forever,
    "dca_weekly": dca_weekly,
}
