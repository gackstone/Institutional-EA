"""
Direction Selection and Bias Provider for Dual-Market Scalping.
Converts strategy, structure, pattern, and momentum modules into
non-blocking directional scorers for GOLD and BTCUSD. Incorporates instrument-specific
tick and M1 momentum fallbacks guaranteeing that direction selection always returns BUY or SELL.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from src.scalper.config import DirectionSelectionConfig, InstrumentScalperConfig

logger = logging.getLogger("SymbolDirectionSelector")


@dataclass
class DirectionScoreDetail:
    smc_score: float = 0.0          # Positive = BUY bias, Negative = SELL bias [-1.0, 1.0]
    momentum_score: float = 0.0     # Positive = BUY bias, Negative = SELL bias [-1.0, 1.0]
    patterns_score: float = 0.0     # Positive = BUY bias, Negative = SELL bias [-1.0, 1.0]
    fallback_score: float = 0.0     # Tick/M1 velocity score [-1.0, 1.0]
    composite_bias: float = 0.0
    selected_direction: str = "BUY"  # "BUY" or "SELL"
    decision_source: str = "COMPOSITE" # "COMPOSITE", "MOMENTUM_FALLBACK", "DEFAULT_FLAT"


class SymbolDirectionSelector:
    def __init__(self, config: Optional[DirectionSelectionConfig] = None):
        self.config = config or DirectionSelectionConfig()

    def _score_tick_velocity(
        self,
        ticks: Sequence[Any],
        canonical: str = "XAUUSD",
        lookback_ticks: int = 20,
    ) -> float:
        """Computes price drift and velocity across the last N ticks."""
        if not ticks or len(ticks) < 2:
            return 0.0
        n = min(len(ticks), lookback_ticks)
        subset = ticks[-n:]
        first_px = getattr(subset[0], "bid", getattr(subset[0], "price", 0.0))
        last_px = getattr(subset[-1], "bid", getattr(subset[-1], "price", 0.0))
        if first_px <= 0 or last_px <= 0:
            return 0.0
        diff = last_px - first_px

        # Instrument-aware saturation scale
        saturation = 25.0 if "BTC" in canonical.upper() else 0.50
        if diff > 0:
            return min(1.0, diff / saturation)
        elif diff < 0:
            return max(-1.0, diff / saturation)
        return 0.0

    def _score_m1_drift(
        self,
        candles: Sequence[Any],
        canonical: str = "XAUUSD",
        m1_lookback: int = 5,
    ) -> float:
        """Computes net price drift across recent M1 bars."""
        if not candles or len(candles) < 2:
            return 0.0
        n = min(len(candles), m1_lookback)
        subset = candles[-n:]
        first_open = getattr(subset[0], "open", 0.0)
        last_close = getattr(subset[-1], "close", 0.0)
        if first_open <= 0 or last_close <= 0:
            return 0.0
        diff = last_close - first_open

        saturation = 50.0 if "BTC" in canonical.upper() else 1.00
        if diff > 0:
            return min(1.0, diff / saturation)
        elif diff < 0:
            return max(-1.0, diff / saturation)
        return 0.0

    def _score_momentum(
        self,
        candles: Sequence[Any],
        canonical: str = "XAUUSD",
        momentum_period: int = 10,
    ) -> float:
        """Computes lightweight momentum (EMA or price ROC)."""
        if not candles or len(candles) < 3:
            return 0.0
        closes = [float(getattr(c, "close", 0.0)) for c in candles if getattr(c, "close", 0.0) > 0]
        if len(closes) < 3:
            return 0.0
        p = min(len(closes), momentum_period)
        roc = closes[-1] - closes[-p]

        saturation = 50.0 if "BTC" in canonical.upper() else 1.00
        if roc > 0:
            return min(1.0, roc / saturation)
        elif roc < 0:
            return max(-1.0, roc / saturation)
        return 0.0

    def select_direction(
        self,
        ticks: Optional[Sequence[Any]] = None,
        m1_candles: Optional[Sequence[Any]] = None,
        strategy_bias: Optional[float] = None,
        patterns_bias: Optional[float] = None,
        canonical: str = "XAUUSD",
        instrument_config: Optional[InstrumentScalperConfig] = None,
    ) -> DirectionScoreDetail:
        """
        Determines trade direction for the next basket.
        Combines strategy intelligence scores and falls back to tick/M1 momentum.
        ALWAYS returns BUY or SELL.
        """
        w_smc = self.config.scoring_weight_smc
        w_mom = self.config.scoring_weight_momentum
        w_pat = self.config.scoring_weight_patterns
        min_thresh = self.config.min_bias_threshold

        lookback_ticks = (
            instrument_config.fallback_lookback_ticks
            if instrument_config
            else self.config.fallback.lookback_ticks
        )
        m1_lookback = (
            instrument_config.fallback_m1_candles
            if instrument_config
            else self.config.fallback.m1_candle_lookback
        )
        mom_period = (
            instrument_config.fallback_momentum_period
            if instrument_config
            else self.config.fallback.momentum_period
        )

        # 1. Strategy components
        s_smc = float(strategy_bias) if strategy_bias is not None else 0.0
        s_pat = float(patterns_bias) if patterns_bias is not None else 0.0

        # 2. Momentum & velocity components
        s_tick_vel = self._score_tick_velocity(ticks or [], canonical=canonical, lookback_ticks=lookback_ticks)
        s_m1_drift = self._score_m1_drift(m1_candles or [], canonical=canonical, m1_lookback=m1_lookback)
        s_mom_calc = self._score_momentum(candles=m1_candles or [], canonical=canonical, momentum_period=mom_period)
        combined_mom = (0.5 * s_tick_vel) + (0.3 * s_m1_drift) + (0.2 * s_mom_calc)

        # 3. Weighted composite
        composite = (w_smc * s_smc) + (w_mom * combined_mom) + (w_pat * s_pat)

        # 4. Direction decision
        if abs(composite) >= min_thresh:
            direction = "BUY" if composite > 0 else "SELL"
            source = "COMPOSITE"
        else:
            fallback_score = combined_mom
            if fallback_score > 0:
                direction = "BUY"
                source = "MOMENTUM_FALLBACK"
            elif fallback_score < 0:
                direction = "SELL"
                source = "MOMENTUM_FALLBACK"
            else:
                direction = self.config.fallback.default_on_flat.upper()
                source = "DEFAULT_FLAT"

        return DirectionScoreDetail(
            smc_score=round(s_smc, 4),
            momentum_score=round(combined_mom, 4),
            patterns_score=round(s_pat, 4),
            fallback_score=round(combined_mom, 4),
            composite_bias=round(composite, 4),
            selected_direction=direction,
            decision_source=source,
        )


# Backward-compatible Gold direction selector alias
class GoldDirectionSelector(SymbolDirectionSelector):
    pass
