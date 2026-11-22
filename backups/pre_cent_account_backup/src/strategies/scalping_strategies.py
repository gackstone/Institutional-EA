"""
Modular Multi-Strategy Scalping Engine.
Implements 7 independent, configurable, and testable strategies:
- Strategy A: EMA Trend Scalping
- Strategy B: RSI Momentum Scalping
- Strategy C: MACD Momentum Scalping
- Strategy D: Bollinger Band Scalping
- Strategy E: ATR & Volatility Scalping
- Strategy F: Price Action & Candle Analysis
- Strategy G: Directional Efficiency
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import Candle, OrderType, Timeframe, TrendBias
from src.engine.market_intelligence import (
    MarketIntelligenceEngine,
    MarketSnapshot,
    DetailedMarketRegime,
    CandlePatternType,
)


@dataclass
class StrategySignal:
    strategy_name: str
    direction: Optional[OrderType]
    buy_strength: float           # 0.0 to 100.0
    sell_strength: float          # 0.0 to 100.0
    confidence: float             # 0.0 to 100.0
    market_condition: str
    recommended_entry_context: str
    suggested_sl_distance: float  # Absolute price distance
    suggested_tp_distance: float  # Absolute price distance
    signal_timestamp: datetime
    data_quality_healthy: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseScalpingStrategy(ABC):
    """Abstract base class for all independent scalping strategies."""

    def __init__(self, name: str, weight: float = 1.0, enabled: bool = True):
        self.name = name
        self.weight = weight
        self.enabled = enabled

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        """Evaluates market data and produces directional strengths and context."""
        pass


# =====================================================================
# Strategy A: EMA Trend Scalping
# =====================================================================
class EmaTrendScalpingStrategy(BaseScalpingStrategy):
    """
    Evaluates fast/slow EMA relationships, EMA slope, price positioning,
    pullbacks to EMA support/resistance zones, and momentum continuation.
    """

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        trend_period: int = 50,
        weight: float = 0.15,
        enabled: bool = True,
    ):
        super().__init__("EMA_TREND", weight=weight, enabled=enabled)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < 20:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Not enough bars for EMA evaluation",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        closes = [c.close for c in candles]
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        ema_fast = snapshot.ema_fast
        ema_slow = snapshot.ema_slow
        ema_trend = snapshot.ema_trend

        # Measure EMA slopes over last 3 bars
        fast_slope = (closes[-1] - closes[-4]) / (3 * atr) if len(closes) >= 4 else 0.0

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        # 1. Alignment check
        if ema_fast > ema_slow:
            buy_score += 40.0
            if ema_slow > ema_trend:
                buy_score += 20.0
                notes.append("Full EMA stack (Fast>Slow>Trend)")
            else:
                buy_score += 10.0
        elif ema_fast < ema_slow:
            sell_score += 40.0
            if ema_slow < ema_trend:
                sell_score += 20.0
                notes.append("Full EMA stack (Fast<Slow<Trend)")
            else:
                sell_score += 10.0

        # 2. Price positioning relative to EMAs
        if last.close > ema_fast:
            buy_score += 15.0
        elif last.close < ema_fast:
            sell_score += 15.0

        # 3. Pullback to EMA zone [ema_slow, ema_fast]
        is_bull_pullback = (last.low <= ema_fast + 0.1 * atr) and (last.close >= ema_slow - 0.1 * atr) and (ema_fast > ema_slow)
        is_bear_pullback = (last.high >= ema_fast - 0.1 * atr) and (last.close <= ema_slow + 0.1 * atr) and (ema_fast < ema_slow)

        if is_bull_pullback:
            buy_score += 15.0
            notes.append("Pullback into EMA zone with bullish defense")
        if is_bear_pullback:
            sell_score += 15.0
            notes.append("Pullback into EMA zone with bearish rejection")

        # 4. Momentum continuation slope
        if fast_slope > 0.15:
            buy_score += 10.0
        elif fast_slope < -0.15:
            sell_score += 10.0

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.2 * atr
        tp_dist = 1.8 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"EMA_SLOPE_{fast_slope:.2f}",
            recommended_entry_context="; ".join(notes) if notes else "EMA neutral",
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"fast": ema_fast, "slow": ema_slow, "trend": ema_trend},
        )


# =====================================================================
# Strategy B: RSI Momentum Scalping
# =====================================================================
class RsiMomentumScalpingStrategy(BaseScalpingStrategy):
    """
    Evaluates RSI momentum, velocity acceleration, and trend-aware momentum interpretation.
    Does NOT blindly fade overbought/oversold levels during trending regimes.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        ob_level: float = 75.0,
        os_level: float = 25.0,
        weight: float = 0.10,
        enabled: bool = True,
    ):
        super().__init__("RSI_MOMENTUM", weight=weight, enabled=enabled)
        self.rsi_period = rsi_period
        self.ob_level = ob_level
        self.os_level = os_level

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < self.rsi_period + 5:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for RSI",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        rsi = snapshot.rsi
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        # Measure 3-bar RSI velocity
        prev_candles = candles[:-3]
        prev_rsi = MarketIntelligenceEngine.compute_rsi(prev_candles, self.rsi_period) if len(prev_candles) > self.rsi_period else 50.0
        rsi_delta = rsi - prev_rsi

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        is_trending_bull = snapshot.direction in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)
        is_trending_bear = snapshot.direction in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH)
        is_ranging = snapshot.direction == TrendBias.RANGING

        # 1. Bullish momentum regime (45 <= RSI <= 70 with upward velocity)
        if 48.0 <= rsi <= 68.0:
            buy_score += 45.0
            if rsi_delta > 2.0:
                buy_score += 25.0
                notes.append(f"RSI bullish acceleration (RSI={rsi:.1f}, delta=+{rsi_delta:.1f})")
            else:
                buy_score += 10.0
        elif rsi > 68.0 and rsi < self.ob_level:
            if is_trending_bull:
                buy_score += 55.0  # Trend-riding
                notes.append("RSI high momentum trend continuation")
            else:
                buy_score += 20.0
        elif rsi >= self.ob_level:
            # Overbought context: if ranging, potential mean reversion sell
            if is_ranging:
                sell_score += 65.0
                notes.append(f"RSI overbought ({rsi:.1f}) in ranging market -> Mean Reversion")
            else:
                # In strong trend, reduce buy score slightly (anti-chase) but don't blindly short
                buy_score += 20.0
                notes.append("RSI overbought in trend -> potential pause")

        # 2. Bearish momentum regime (32 <= RSI <= 52 with downward velocity)
        if 32.0 <= rsi <= 52.0:
            sell_score += 45.0
            if rsi_delta < -2.0:
                sell_score += 25.0
                notes.append(f"RSI bearish acceleration (RSI={rsi:.1f}, delta={rsi_delta:.1f})")
            else:
                sell_score += 10.0
        elif rsi < 32.0 and rsi > self.os_level:
            if is_trending_bear:
                sell_score += 55.0  # Trend-riding
                notes.append("RSI low momentum bearish continuation")
            else:
                sell_score += 20.0
        elif rsi <= self.os_level:
            # Oversold context
            if is_ranging:
                buy_score += 65.0
                notes.append(f"RSI oversold ({rsi:.1f}) in ranging market -> Mean Reversion")
            else:
                sell_score += 20.0
                notes.append("RSI oversold in trend -> potential pause")

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.0 * atr
        tp_dist = 1.6 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"RSI_{rsi:.1f}_VEL_{rsi_delta:+.1f}",
            recommended_entry_context="; ".join(notes) if notes else "RSI neutral",
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"rsi": rsi, "rsi_delta": rsi_delta},
        )


# =====================================================================
# Strategy C: MACD Momentum Scalping
# =====================================================================
class MacdMomentumScalpingStrategy(BaseScalpingStrategy):
    """
    Evaluates MACD line vs Signal line, crossovers, histogram expansion,
    momentum weakening, and trend continuation.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        weight: float = 0.10,
        enabled: bool = True,
    ):
        super().__init__("MACD_MOMENTUM", weight=weight, enabled=enabled)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < self.slow_period + self.signal_period + 5:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for MACD",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        closes = [c.close for c in candles]
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        macd, sig, hist = MarketIntelligenceEngine.compute_macd(
            closes, self.fast_period, self.slow_period, self.signal_period
        )
        # Prior bar MACD
        _, _, prev_hist = MarketIntelligenceEngine.compute_macd(
            closes[:-1], self.fast_period, self.slow_period, self.signal_period
        )

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        # 1. MACD line vs Signal line
        if macd > sig:
            buy_score += 40.0
            if macd > 0:
                buy_score += 15.0
                notes.append("MACD above signal and zero line")
        elif macd < sig:
            sell_score += 40.0
            if macd < 0:
                sell_score += 15.0
                notes.append("MACD below signal and zero line")

        # 2. Histogram momentum & expansion
        if hist > 0:
            if hist > prev_hist:
                buy_score += 25.0
                notes.append("Histogram expanding bullishly")
            else:
                buy_score += 5.0
                notes.append("Bullish histogram momentum waning")
        elif hist < 0:
            if hist < prev_hist:
                sell_score += 25.0
                notes.append("Histogram expanding bearishly")
            else:
                sell_score += 5.0
                notes.append("Bearish histogram momentum waning")

        # 3. Fresh crossover check (crossover in current or prior bar)
        if prev_hist <= 0 and hist > 0:
            buy_score += 20.0
            notes.append("Fresh MACD bullish crossover")
        elif prev_hist >= 0 and hist < 0:
            sell_score += 20.0
            notes.append("Fresh MACD bearish crossover")

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.1 * atr
        tp_dist = 1.7 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"MACD_HIST_{hist:.5f}",
            recommended_entry_context="; ".join(notes) if notes else "MACD neutral",
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"macd": macd, "signal": sig, "hist": hist},
        )


# =====================================================================
# Strategy D: Bollinger Band Scalping
# =====================================================================
class BollingerBandScalpingStrategy(BaseScalpingStrategy):
    """
    Evaluates Bollinger Band expansion/contraction, price interaction with bands,
    volatility breakout opportunities, and mean-reversion in ranging regimes.
    """

    def __init__(
        self,
        period: int = 20,
        deviation: float = 2.0,
        weight: float = 0.10,
        enabled: bool = True,
    ):
        super().__init__("BOLLINGER_BANDS", weight=weight, enabled=enabled)
        self.period = period
        self.deviation = deviation

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < self.period + 5:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for Bollinger Bands",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        closes = [c.close for c in candles]
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        mid, upper, lower, bandwidth = MarketIntelligenceEngine.compute_bollinger_bands(
            closes, self.period, self.deviation
        )
        is_ranging = snapshot.regime in (DetailedMarketRegime.RANGING, DetailedMarketRegime.LOW_VOLATILITY)
        is_trending_bull = snapshot.direction in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)
        is_trending_bear = snapshot.direction in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH)

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        # 1. Band interaction
        if last.close >= upper:
            if snapshot.is_volatility_expanding and is_trending_bull:
                buy_score += 65.0
                notes.append("Bollinger Band expansion breakout upper")
            elif is_ranging:
                # Mean reversion rejection at upper band
                sell_score += 60.0
                notes.append("Upper band touch in range -> Mean Reversion Sell")
            else:
                buy_score += 30.0
        elif last.close <= lower:
            if snapshot.is_volatility_expanding and is_trending_bear:
                sell_score += 65.0
                notes.append("Bollinger Band expansion breakout lower")
            elif is_ranging:
                # Mean reversion bounce at lower band
                buy_score += 60.0
                notes.append("Lower band touch in range -> Mean Reversion Buy")
            else:
                sell_score += 30.0
        else:
            # Inside the bands: check position relative to middle SMA
            if last.close > mid and is_trending_bull:
                buy_score += 35.0
                notes.append("Price riding above Bollinger middle in bull trend")
            elif last.close < mid and is_trending_bear:
                sell_score += 35.0
                notes.append("Price riding below Bollinger middle in bear trend")
            else:
                buy_score += 15.0
                sell_score += 15.0

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.2 * atr
        tp_dist = 1.8 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"BB_WIDTH_{bandwidth:.4f}",
            recommended_entry_context="; ".join(notes) if notes else "BB neutral",
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"upper": upper, "middle": mid, "lower": lower, "bandwidth": bandwidth},
        )


# =====================================================================
# Strategy E: ATR & Volatility Scalping
# =====================================================================
class AtrVolatilityScalpingStrategy(BaseScalpingStrategy):
    """
    Evaluates current vs historical ATR, expansion/compression cycles,
    dynamic stop distance recommendations, and volatility normalization.
    """

    def __init__(
        self,
        atr_period: int = 14,
        avg_lookback: int = 50,
        weight: float = 0.10,
        enabled: bool = True,
    ):
        super().__init__("ATR_VOLATILITY", weight=weight, enabled=enabled)
        self.atr_period = atr_period
        self.avg_lookback = avg_lookback

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < 20:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for ATR",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        atr = max(snapshot.current_atr, 1e-6)
        atr_ratio = snapshot.atr_ratio
        last = candles[-1]

        buy_score = 40.0
        sell_score = 40.0
        notes = []

        # Volatility condition evaluation
        if 0.90 <= atr_ratio <= 1.50:
            # Healthy scalping volatility
            buy_score += 25.0
            sell_score += 25.0
            notes.append(f"Healthy volatility condition (ATR ratio={atr_ratio:.2f})")
        elif atr_ratio > 1.50:
            # High volatility expansion: supports trend continuation and breakouts
            notes.append(f"High volatility expansion (ATR ratio={atr_ratio:.2f})")
            if snapshot.direction in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH):
                buy_score += 35.0
            elif snapshot.direction in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH):
                sell_score += 35.0
        elif atr_ratio < 0.70:
            # Low volatility compression: wait or mean-reversion
            notes.append(f"Compressed volatility (ATR ratio={atr_ratio:.2f})")
            buy_score -= 15.0
            sell_score -= 15.0

        # Spread to ATR sanity
        if snapshot.spread_atr_ratio > 0.40:
            # Spread eats > 40% of ATR bar: penalize both directions
            buy_score -= 20.0
            sell_score -= 20.0
            notes.append(f"Wide spread warning ({snapshot.spread_atr_ratio:.0%} of ATR)")

        direction = None
        if buy_score > sell_score + 10.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 10.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        # Dynamic stop distances scaled by ATR
        sl_dist = max(1.2 * atr, 1e-5)
        tp_dist = max(1.8 * atr, 1e-5)

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(max(0.0, min(100.0, buy_score)), 1),
            sell_strength=round(max(0.0, min(100.0, sell_score)), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"VOL_RATIO_{atr_ratio:.2f}",
            recommended_entry_context="; ".join(notes) if notes else "ATR normal",
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"atr": atr, "atr_ratio": atr_ratio, "spread_atr_ratio": snapshot.spread_atr_ratio},
        )


# =====================================================================
# Strategy F: Price Action & Candle Analysis
# =====================================================================
class PriceActionCandleStrategy(BaseScalpingStrategy):
    """
    Evaluates engulfing candles, rejection pins, momentum candles,
    breakout candles, and swing high/low structural levels.
    """

    def __init__(self, lookback_swing: int = 15, weight: float = 0.15, enabled: bool = True):
        super().__init__("PRICE_ACTION", weight=weight, enabled=enabled)
        self.lookback_swing = lookback_swing

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < 10:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for price action",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        analysis = snapshot.candle_analysis
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        # 1. Pattern assessment
        if analysis.pattern == CandlePatternType.BULLISH_ENGULFING:
            buy_score += 70.0
            notes.append("Bullish Engulfing candle pattern")
        elif analysis.pattern == CandlePatternType.BEARISH_ENGULFING:
            sell_score += 70.0
            notes.append("Bearish Engulfing candle pattern")
        elif analysis.pattern == CandlePatternType.BULLISH_REJECTION:
            buy_score += 65.0
            notes.append("Bullish Pin bar / rejection of lows")
        elif analysis.pattern == CandlePatternType.BEARISH_REJECTION:
            sell_score += 65.0
            notes.append("Bearish Pin bar / rejection of highs")
        elif analysis.pattern == CandlePatternType.BULLISH_MOMENTUM:
            buy_score += 60.0
            notes.append("Bullish Momentum body expansion")
        elif analysis.pattern == CandlePatternType.BEARISH_MOMENTUM:
            sell_score += 60.0
            notes.append("Bearish Momentum body expansion")
        elif analysis.pattern == CandlePatternType.BREAKOUT_CANDLE:
            if analysis.is_bullish:
                buy_score += 65.0
                notes.append("Decisive Bullish Breakout above range")
            else:
                sell_score += 65.0
                notes.append("Decisive Bearish Breakout below range")
        else:
            # Baseline: direction of candle
            if analysis.is_bullish:
                buy_score += 35.0
            elif analysis.is_bearish:
                sell_score += 35.0

        # 2. Volume expansion boost
        if analysis.relative_volume >= 1.30:
            if buy_score > sell_score:
                buy_score += 15.0
                notes.append(f"Volume expansion ({analysis.relative_volume:.1f}x)")
            elif sell_score > buy_score:
                sell_score += 15.0
                notes.append(f"Volume expansion ({analysis.relative_volume:.1f}x)")

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.0 * atr
        tp_dist = 1.6 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=analysis.pattern.value,
            recommended_entry_context="; ".join(notes) if notes else analysis.description,
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"pattern": analysis.pattern.value, "rel_vol": analysis.relative_volume},
        )


# =====================================================================
# Strategy G: Directional Efficiency
# =====================================================================
class DirectionalEfficiencyStrategy(BaseScalpingStrategy):
    """
    Evaluates Kaufman Efficiency Ratio (net directional move / total path traveled).
    Differentiates between sustained directional movement and choppy back-and-forth noise.
    """

    def __init__(self, lookback_period: int = 20, weight: float = 0.10, enabled: bool = True):
        super().__init__("DIRECTIONAL_EFFICIENCY", weight=weight, enabled=enabled)
        self.lookback_period = lookback_period

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        snapshot: MarketSnapshot,
        timeframe: Timeframe = Timeframe.M1,
    ) -> StrategySignal:
        now = datetime.now(timezone.utc)
        if not candles or len(candles) < self.lookback_period:
            return StrategySignal(
                strategy_name=self.name,
                direction=None,
                buy_strength=0.0,
                sell_strength=0.0,
                confidence=0.0,
                market_condition="INSUFFICIENT_DATA",
                recommended_entry_context="Insufficient bars for Directional Efficiency",
                suggested_sl_distance=0.0,
                suggested_tp_distance=0.0,
                signal_timestamp=now,
                data_quality_healthy=False,
            )

        efficiency = snapshot.directional_efficiency  # [0.0, 1.0]
        direction_bias = snapshot.direction
        last = candles[-1]
        atr = max(snapshot.current_atr, 1e-6)

        buy_score = 0.0
        sell_score = 0.0
        notes = []

        is_bullish = direction_bias in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)
        is_bearish = direction_bias in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH)

        # High efficiency (> 0.50): clean trend
        if efficiency >= 0.50:
            notes.append(f"High directional efficiency ({efficiency:.2f}) -> clean trend")
            if is_bullish:
                buy_score = 75.0 + (efficiency * 20.0)
                sell_score = 15.0
            elif is_bearish:
                sell_score = 75.0 + (efficiency * 20.0)
                buy_score = 15.0
            else:
                buy_score = 50.0
                sell_score = 50.0
        elif efficiency >= 0.30:
            notes.append(f"Moderate efficiency ({efficiency:.2f})")
            if is_bullish:
                buy_score = 55.0
                sell_score = 25.0
            elif is_bearish:
                sell_score = 55.0
                buy_score = 25.0
            else:
                buy_score = 35.0
                sell_score = 35.0
        else:
            # Low efficiency (< 0.30): choppy/ranging market
            notes.append(f"Low efficiency ({efficiency:.2f}) -> back-and-forth noise")
            buy_score = 25.0
            sell_score = 25.0

        direction = None
        if buy_score > sell_score + 15.0 and buy_score >= 50.0:
            direction = OrderType.BUY
        elif sell_score > buy_score + 15.0 and sell_score >= 50.0:
            direction = OrderType.SELL

        sl_dist = 1.1 * atr
        tp_dist = 1.7 * atr

        return StrategySignal(
            strategy_name=self.name,
            direction=direction,
            buy_strength=round(min(100.0, buy_score), 1),
            sell_strength=round(min(100.0, sell_score), 1),
            confidence=round(max(buy_score, sell_score), 1),
            market_condition=f"EFFICIENCY_{efficiency:.2f}",
            recommended_entry_context="; ".join(notes),
            suggested_sl_distance=round(sl_dist, 5),
            suggested_tp_distance=round(tp_dist, 5),
            signal_timestamp=last.time,
            data_quality_healthy=True,
            metadata={"efficiency": efficiency},
        )
