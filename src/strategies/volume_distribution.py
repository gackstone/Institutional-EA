"""
Volume‑Price Distribution (VPD) filter module.
Computes a rolling tick‑volume SMA and flags a leg as an
"accumulation" when volume > avg * threshold.
Used as a filter/modifier for existing SMC signals.
"""

from __future__ import annotations

from typing import Optional, List

from src.strategies.base import FilterModule, StrategyContext, FilterResult
from src.core.contracts import Candle, OrderType

class VolumeDistributionFilter(FilterModule):
    """Reject signals on legs with insufficient volume.

    Parameters are configurable via ``config.strategy.volume_distribution``.
    """

    def __init__(self, config):
        vcfg = getattr(config.strategy, "volume_distribution", {})
        self.window: int = int(vcfg.get("volume_window", 14))
        self.threshold: float = float(vcfg.get("volume_multiplier", 1.5))
        # Reuse existing volume field in Candle (tick volume proxy)

    def _average_volume(self, candles: List[Candle]) -> float:
        if not candles:
            return 0.0
        total = sum(c.volume for c in candles[-self.window :])
        return total / min(len(candles), self.window)

    def filter_signal(self, signal, ctx: StrategyContext) -> FilterResult:
        # Use the last completed candle of the symbol's M15 series
        candles = ctx.m15_candles
        if not candles:
            return FilterResult(passed=False, reason_code="NO_CANDLES", details="No M15 candles")
        avg_vol = self._average_volume(candles)
        current_vol = candles[-1].volume
        if current_vol < avg_vol * self.threshold:
            return FilterResult(
                passed=False,
                reason_code="VOLUME_LOW",
                details=f"Current volume {current_vol:.0f} < {self.threshold:.1f}× avg {avg_vol:.0f}",
                real_numbers={"avg_vol": avg_vol, "cur_vol": current_vol},
            )
        return FilterResult(passed=True, details="Volume distribution satisfactory")
