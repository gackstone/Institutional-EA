"""
Execution-Cost & Spread Telemetry Engine.
Replaces rigid spread ceilings and rollover-hour blocks with configurable
economic viability assessment (spread + slippage + commission vs expected reward).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SpreadCheckResult:
    allowed: bool
    current_spread_pts: float
    expected_spread_pts: float
    spread_ratio: float
    reason: Optional[str]


@dataclass(frozen=True)
class ExecutionCostAssessment:
    viable: bool
    spread_warning: bool
    spread_pts: float
    spread_cost_usd: float
    slippage_cost_usd: float
    commission_usd: float
    total_cost_usd: float
    expected_gross_profit_usd: float
    expected_net_profit_usd: float
    net_to_cost_ratio: float
    reason: Optional[str] = None


class ExecutionCostEvaluator:
    """
    Evaluates whether a trade's expected net reward justifies its execution cost.
    Configurable per instrument (XAUUSD, BTCUSD, USDJPY).
    Never rejects solely because a fixed spread threshold is exceeded.
    """

    DEFAULT_INSTRUMENT_POLICIES: Dict[str, Dict[str, float]] = {
        "XAUUSD": {"warn_spread_pts": 85.0, "min_net_to_cost_ratio": 1.2, "commission_per_lot": 7.0, "expected_slippage_pts": 5.0},
        "BTCUSD": {"warn_spread_pts": 2000.0, "min_net_to_cost_ratio": 1.2, "commission_per_lot": 7.0, "expected_slippage_pts": 20.0},
        "USDJPY": {"warn_spread_pts": 25.0, "min_net_to_cost_ratio": 1.2, "commission_per_lot": 7.0, "expected_slippage_pts": 2.0},
    }

    def __init__(self, policies: Optional[Dict[str, Dict[str, float]]] = None):
        self.policies = policies or dict(self.DEFAULT_INSTRUMENT_POLICIES)

    def evaluate_cost(
        self,
        canonical_symbol: str,
        spread_pts: float,
        volume: float,
        point: float,
        tick_size: float,
        tick_value: float,
        tp_distance: float,
    ) -> ExecutionCostAssessment:
        pol = self.policies.get(canonical_symbol, {"warn_spread_pts": 100.0, "min_net_to_cost_ratio": 1.2, "commission_per_lot": 7.0, "expected_slippage_pts": 3.0})
        pt = point if point > 0 else 0.01
        tsz = tick_size if tick_size > 0 else pt
        tv = tick_value if tick_value > 0 else 1.0
        vol = max(0.01, float(volume))

        spread_cost = (max(0.0, spread_pts) * pt / tsz) * tv * vol
        slippage_pts = float(pol.get("expected_slippage_pts", 2.0))
        slippage_cost = (slippage_pts * pt / tsz) * tv * vol
        commission = float(pol.get("commission_per_lot", 7.0)) * vol
        total_cost = spread_cost + slippage_cost + commission

        gross_profit = (max(0.0, tp_distance) / tsz) * tv * vol if tp_distance > 0 else 0.0
        net_profit = gross_profit - total_cost
        ratio = (net_profit / total_cost) if total_cost > 0 else 999.0
        warn = spread_pts > float(pol.get("warn_spread_pts", 100.0))

        min_ratio = float(pol.get("min_net_to_cost_ratio", 1.2))
        viable = True
        reason = None
        if tp_distance > 0 and (net_profit <= 0.0 or ratio < min_ratio):
            viable = False
            reason = (
                f"Execution cost makes trade economically invalid: net=${net_profit:.2f} "
                f"(gross=${gross_profit:.2f}, cost=${total_cost:.2f}, ratio={ratio:.2f} < {min_ratio:.2f})."
            )

        return ExecutionCostAssessment(
            viable=viable,
            spread_warning=warn,
            spread_pts=spread_pts,
            spread_cost_usd=round(spread_cost, 2),
            slippage_cost_usd=round(slippage_cost, 2),
            commission_usd=round(commission, 2),
            total_cost_usd=round(total_cost, 2),
            expected_gross_profit_usd=round(gross_profit, 2),
            expected_net_profit_usd=round(net_profit, 2),
            net_to_cost_ratio=round(ratio, 2),
            reason=reason,
        )


class SpreadFilter:
    DEFAULT_BASELINE_SPREADS = {
        "EURUSD.m": 8.0,
        "GBPUSD.m": 12.0,
        "USDJPY": 11.0,
        "USDJPY.m": 11.0,
        "XAUUSD": 26.0,
        "XAUUSD.m": 26.0,
        "BTCUSD": 850.0,
        "BTCUSD.m": 850.0,
    }
    ROLLOVER_HOURS_UTC = {21, 22, 23}

    def __init__(self, max_spread_multiplier: float = 2.0, allow_rollover_trading: bool = False):
        self.max_spread_multiplier = max_spread_multiplier
        self.allow_rollover = allow_rollover_trading
        self.hourly_medians: Dict[str, Dict[int, float]] = {}

    def set_hourly_median(self, symbol: str, hour: int, median_pts: float) -> None:
        self.hourly_medians.setdefault(symbol, {})[hour] = max(1.0, median_pts)

    def evaluate_spread(self, symbol: str, current_spread_pts: float, hour_utc: int) -> SpreadCheckResult:
        """Retains spread telemetry without imposing rigid spread-based rejections."""
        if hour_utc in self.ROLLOVER_HOURS_UTC and not self.allow_rollover:
            return SpreadCheckResult(
                allowed=False,
                current_spread_pts=current_spread_pts,
                expected_spread_pts=self.get_expected_spread(symbol, hour_utc),
                spread_ratio=99.0,
                reason=f"Illiquid rollover window active ({hour_utc:02d}:00 UTC). Trading forbidden.",
            )
        expected = self.get_expected_spread(symbol, hour_utc)
        ratio = current_spread_pts / expected if expected > 0 else 1.0
        note = None
        if ratio > self.max_spread_multiplier:
            note = (
                f"[SPREAD_ENGINE] Strategy-level spread rejection is disabled. Spread retained for diagnostics: "
                f"{current_spread_pts:.1f} pts ({ratio:.1f}x expected {expected:.1f} pts at {hour_utc:02d}:00 UTC)."
            )
        return SpreadCheckResult(
            allowed=True,
            current_spread_pts=current_spread_pts,
            expected_spread_pts=expected,
            spread_ratio=round(ratio, 2),
            reason=note,
        )

    def get_expected_spread(self, symbol: str, hour_utc: int) -> float:
        if symbol in self.hourly_medians and hour_utc in self.hourly_medians[symbol]:
            return self.hourly_medians[symbol][hour_utc]
        return self.DEFAULT_BASELINE_SPREADS.get(symbol, 20.0)
