"""
Market Intelligence Engine.
Provides comprehensive multi-symbol market condition analysis, regime classification,
momentum measurement, volatility evaluation, breakout/reversal detection,
and candle structure analytics across multiple timeframes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import Candle, OrderType, Timeframe, TrendBias

logger = logging.getLogger("MarketIntelligence")


class DetailedMarketRegime(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    UNCERTAIN = "UNCERTAIN"


class CandlePatternType(str, Enum):
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    BULLISH_REJECTION = "BULLISH_REJECTION"  # Pin bar / hammer rejecting lows
    BEARISH_REJECTION = "BEARISH_REJECTION"  # Pin bar / shooting star rejecting highs
    BULLISH_MOMENTUM = "BULLISH_MOMENTUM"    # Large full-body candle closing near high
    BEARISH_MOMENTUM = "BEARISH_MOMENTUM"    # Large full-body candle closing near low
    BREAKOUT_CANDLE = "BREAKOUT_CANDLE"      # Closes decisively beyond recent range
    INDECISION = "INDECISION"                # Doji / spinning top
    NORMAL = "NORMAL"


@dataclass
class CandleAnalysis:
    pattern: CandlePatternType
    body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    is_bullish: bool
    is_bearish: bool
    range_pts: float
    relative_volume: float
    description: str


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    regime: DetailedMarketRegime
    direction: TrendBias
    directional_efficiency: float  # Kaufman Efficiency Ratio: 0.0 (pure chop) to 1.0 (pure trend)
    momentum_score: float         # -100.0 (extreme bearish) to +100.0 (extreme bullish)
    current_atr: float
    atr_ratio: float              # current ATR / historical average ATR (volatility expansion)
    is_volatility_expanding: bool
    is_volatility_compressed: bool
    spread_atr_ratio: float       # spread / ATR ratio
    relative_volume: float        # current bar volume / 20-bar avg volume
    recent_high: float
    recent_low: float
    ema_fast: float
    ema_slow: float
    ema_trend: float
    rsi: float
    macd_hist: float
    candle_analysis: CandleAnalysis
    breakout_detected: bool
    breakout_direction: Optional[OrderType]
    reversal_detected: bool
    reversal_direction: Optional[OrderType]
    data_quality_healthy: bool
    details: Dict[str, Any] = field(default_factory=dict)


class MarketIntelligenceEngine:
    """
    Multi-symbol real-time market intelligence engine.
    Analyzes price series to compute regime, directional efficiency,
    volatility metrics, momentum, and structural patterns.
    """

    def __init__(
        self,
        ema_fast_period: int = 9,
        ema_slow_period: int = 21,
        ema_trend_period: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_avg_lookback: int = 50,
        efficiency_lookback: int = 20,
    ):
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.ema_trend_period = ema_trend_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.atr_avg_lookback = atr_avg_lookback
        self.efficiency_lookback = efficiency_lookback

        # Snapshot cache: (symbol, timeframe) -> (last_bar_time, MarketSnapshot)
        self._cache: Dict[Tuple[str, Timeframe], Tuple[datetime, MarketSnapshot]] = {}

    # ---------------------------------------------------------
    # Core Mathematical & Indicator Calculations
    # ---------------------------------------------------------

    @staticmethod
    def compute_ema(values: List[float], period: int) -> float:
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        k = 2.0 / (period + 1.0)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = (v * k) + (ema * (1.0 - k))
        return ema

    @staticmethod
    def compute_ema_series(values: List[float], period: int) -> List[float]:
        if not values:
            return []
        if len(values) < period:
            avg = sum(values) / len(values)
            return [avg] * len(values)
        k = 2.0 / (period + 1.0)
        out = [sum(values[:period]) / period] * period
        current = out[-1]
        for v in values[period:]:
            current = (v * k) + (current * (1.0 - k))
            out.append(current)
        return out

    @staticmethod
    def compute_atr(candles: List[Candle], period: int = 14) -> float:
        if not candles:
            return 0.0
        if len(candles) < 2:
            return max(candles[-1].range, 1e-6)
        window = candles[-(period + 1):]
        trs: List[float] = []
        for i in range(1, len(window)):
            c = window[i]
            p = window[i - 1]
            tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            trs.append(tr)
        return max(sum(trs) / len(trs) if trs else candles[-1].range, 1e-6)

    @staticmethod
    def compute_rsi(candles: List[Candle], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 50.0
        window = candles[-(period + 1):]
        gains = 0.0
        losses = 0.0
        for i in range(1, len(window)):
            chg = window[i].close - window[i - 1].close
            if chg >= 0:
                gains += chg
            else:
                losses -= chg
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss <= 1e-12:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def compute_macd(
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal_period: int = 9,
    ) -> Tuple[float, float, float]:
        """Returns (macd_line, signal_line, histogram)."""
        if len(closes) < slow + signal_period:
            return 0.0, 0.0, 0.0
        fast_ema_series = MarketIntelligenceEngine.compute_ema_series(closes, fast)
        slow_ema_series = MarketIntelligenceEngine.compute_ema_series(closes, slow)
        macd_series = [f - s for f, s in zip(fast_ema_series, slow_ema_series)]
        signal_series = MarketIntelligenceEngine.compute_ema_series(macd_series, signal_period)
        macd_line = macd_series[-1]
        sig_line = signal_series[-1]
        hist = macd_line - sig_line
        return macd_line, sig_line, hist

    @staticmethod
    def compute_bollinger_bands(
        closes: List[float],
        period: int = 20,
        mult: float = 2.0,
    ) -> Tuple[float, float, float, float]:
        """Returns (middle, upper, lower, bandwidth_ratio)."""
        if len(closes) < period:
            avg = sum(closes) / max(len(closes), 1)
            return avg, avg, avg, 0.0
        window = closes[-period:]
        mid = sum(window) / period
        variance = sum((x - mid) ** 2 for x in window) / period
        std = math.sqrt(max(variance, 1e-12))
        upper = mid + (mult * std)
        lower = mid - (mult * std)
        bandwidth = (upper - lower) / mid if mid > 1e-6 else 0.0
        return mid, upper, lower, bandwidth

    @staticmethod
    def compute_directional_efficiency(candles: List[Candle], period: int = 20) -> float:
        """
        Kaufman Efficiency Ratio:
        ER = |Close_t - Close_{t-n}| / Sum(|Close_i - Close_{i-1}| for i in t-n..t)
        Returns ratio in [0.0, 1.0]. High = smooth trend; Low = noisy chop.
        """
        if len(candles) < period + 1:
            return 0.5
        window = candles[-(period + 1):]
        net_change = abs(window[-1].close - window[0].close)
        total_path = sum(abs(window[i].close - window[i - 1].close) for i in range(1, len(window)))
        if total_path <= 1e-12:
            return 0.0
        er = net_change / total_path
        return max(0.0, min(1.0, er))

    # ---------------------------------------------------------
    # Candle Anatomy & Pattern Analysis
    # ---------------------------------------------------------

    @classmethod
    def analyze_candle_structure(
        cls,
        candles: List[Candle],
        lookback_swing: int = 15,
    ) -> CandleAnalysis:
        if not candles:
            return CandleAnalysis(
                pattern=CandlePatternType.NORMAL,
                body_ratio=0.0,
                upper_wick_ratio=0.0,
                lower_wick_ratio=0.0,
                is_bullish=False,
                is_bearish=False,
                range_pts=0.0,
                relative_volume=1.0,
                description="Empty candle history",
            )

        last = candles[-1]
        c_range = max(last.range, 1e-9)
        body = abs(last.close - last.open)
        body_ratio = body / c_range
        upper_wick = last.high - max(last.open, last.close)
        lower_wick = min(last.open, last.close) - last.low
        upper_ratio = upper_wick / c_range
        lower_ratio = lower_wick / c_range

        is_bull = last.close > last.open
        is_bear = last.close < last.open

        # Relative volume
        rel_vol = 1.0
        recent_vols = [c.tick_volume for c in candles[-21:-1] if c.tick_volume > 0]
        if recent_vols:
            avg_vol = sum(recent_vols) / len(recent_vols)
            if avg_vol > 0:
                rel_vol = last.tick_volume / avg_vol

        # Pattern identification
        pattern = CandlePatternType.NORMAL
        desc = "Standard candle"

        # Check Engulfing (requires at least 2 bars)
        if len(candles) >= 2:
            prev = candles[-2]
            prev_body = abs(prev.close - prev.open)
            # Bullish Engulfing: prev is bearish, current is bullish engulfing prev body
            if (
                is_bull
                and prev.close < prev.open
                and last.close >= prev.open
                and last.open <= prev.close
                and body > prev_body
            ):
                pattern = CandlePatternType.BULLISH_ENGULFING
                desc = "Bullish Engulfing candle"
            # Bearish Engulfing
            elif (
                is_bear
                and prev.close > prev.open
                and last.close <= prev.open
                and last.open >= prev.close
                and body > prev_body
            ):
                pattern = CandlePatternType.BEARISH_ENGULFING
                desc = "Bearish Engulfing candle"

        # Check Rejection / Pin Bar
        if pattern == CandlePatternType.NORMAL:
            if lower_ratio >= 0.55 and body_ratio <= 0.35:
                pattern = CandlePatternType.BULLISH_REJECTION
                desc = "Bullish Rejection (Hammer/Pin bar rejecting lows)"
            elif upper_ratio >= 0.55 and body_ratio <= 0.35:
                pattern = CandlePatternType.BEARISH_REJECTION
                desc = "Bearish Rejection (Shooting Star/Pin bar rejecting highs)"

        # Check Momentum Candle
        if pattern == CandlePatternType.NORMAL:
            if body_ratio >= 0.65:
                if is_bull and last.close >= (last.high - 0.15 * c_range):
                    pattern = CandlePatternType.BULLISH_MOMENTUM
                    desc = "Strong Bullish Momentum candle"
                elif is_bear and last.close <= (last.low + 0.15 * c_range):
                    pattern = CandlePatternType.BEARISH_MOMENTUM
                    desc = "Strong Bearish Momentum candle"

        # Check Indecision / Doji
        if pattern == CandlePatternType.NORMAL:
            if body_ratio <= 0.15:
                pattern = CandlePatternType.INDECISION
                desc = "Indecision Doji candle"

        # Check Breakout Candle relative to swing highs/lows
        if len(candles) > lookback_swing:
            prior = candles[-(lookback_swing + 1):-1]
            prior_high = max(c.high for c in prior)
            prior_low = min(c.low for c in prior)
            if last.close > prior_high and is_bull and body_ratio >= 0.50:
                pattern = CandlePatternType.BREAKOUT_CANDLE
                desc = f"Bullish Breakout candle closing above prior {lookback_swing}-bar high"
            elif last.close < prior_low and is_bear and body_ratio >= 0.50:
                pattern = CandlePatternType.BREAKOUT_CANDLE
                desc = f"Bearish Breakout candle closing below prior {lookback_swing}-bar low"

        return CandleAnalysis(
            pattern=pattern,
            body_ratio=round(body_ratio, 3),
            upper_wick_ratio=round(upper_ratio, 3),
            lower_wick_ratio=round(lower_ratio, 3),
            is_bullish=is_bull,
            is_bearish=is_bear,
            range_pts=round(c_range, 5),
            relative_volume=round(rel_vol, 2),
            description=desc,
        )

    # ---------------------------------------------------------
    # Comprehensive Market Inspection
    # ---------------------------------------------------------

    def inspect_market(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle],
        spread_points: float = 1.0,
        point_size: float = 0.00001,
        force_fresh: bool = False,
    ) -> MarketSnapshot:
        """
        Inspects market data for a symbol and timeframe, computing full snapshot.
        Utilizes caching when bar timestamp has not changed.
        """
        completed = [c for c in candles if getattr(c, "complete", True)]
        if len(completed) < 15:
            completed = list(candles)

        if not completed:
            # Fallback for empty data
            now = datetime.now(timezone.utc)
            return MarketSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=now,
                regime=DetailedMarketRegime.UNCERTAIN,
                direction=TrendBias.RANGING,
                directional_efficiency=0.0,
                momentum_score=0.0,
                current_atr=1e-5,
                atr_ratio=1.0,
                is_volatility_expanding=False,
                is_volatility_compressed=False,
                spread_atr_ratio=0.1,
                relative_volume=1.0,
                recent_high=0.0,
                recent_low=0.0,
                ema_fast=0.0,
                ema_slow=0.0,
                ema_trend=0.0,
                rsi=50.0,
                macd_hist=0.0,
                candle_analysis=self.analyze_candle_structure([]),
                breakout_detected=False,
                breakout_direction=None,
                reversal_detected=False,
                reversal_direction=None,
                data_quality_healthy=False,
                details={"reason": "No candle data available"},
            )

        last_bar_time = completed[-1].time
        cache_key = (symbol, timeframe)
        if not force_fresh and cache_key in self._cache:
            cached_time, cached_snapshot = self._cache[cache_key]
            if cached_time == last_bar_time:
                return cached_snapshot

        closes = [c.close for c in completed]
        last_close = closes[-1]

        # 1. EMAs
        ema_fast = self.compute_ema(closes[-30:], self.ema_fast_period)
        ema_slow = self.compute_ema(closes[-50:], self.ema_slow_period)
        ema_trend = self.compute_ema(closes[-100:], self.ema_trend_period) if len(closes) >= 30 else ema_slow

        # 2. Volatility & ATR
        current_atr = self.compute_atr(completed, self.atr_period)
        long_atr = self.compute_atr(completed, min(self.atr_avg_lookback, len(completed) - 1))
        atr_ratio = round((current_atr / long_atr) if long_atr > 1e-9 else 1.0, 2)
        is_vol_expanding = atr_ratio >= 1.25
        is_vol_compressed = atr_ratio <= 0.70

        # Bollinger Bands
        _, _, _, bb_bandwidth = self.compute_bollinger_bands(closes, 20, 2.0)

        # Spread to ATR ratio
        spread_val = spread_points * point_size if point_size > 0 else spread_points
        spread_atr_ratio = round(spread_val / current_atr if current_atr > 1e-9 else 0.0, 3)

        # 3. Momentum & RSI & MACD
        rsi = round(self.compute_rsi(completed, self.rsi_period), 2)
        _, _, macd_hist = self.compute_macd(closes)

        # Kaufman Directional Efficiency
        efficiency = round(self.compute_directional_efficiency(completed, self.efficiency_lookback), 3)

        # 4. Swing High / Low over last 20 bars
        recent_window = completed[-20:]
        recent_high = max(c.high for c in recent_window)
        recent_low = min(c.low for c in recent_window)

        # 5. Candle Analysis
        candle_analysis = self.analyze_candle_structure(completed, lookback_swing=15)

        # 6. Directional Bias
        if last_close > ema_fast > (ema_slow + 0.05 * current_atr) and ema_slow >= (ema_trend - 0.10 * current_atr):
            direction = TrendBias.STRONG_BULLISH
        elif last_close > ema_fast and ema_fast >= ema_slow:
            direction = TrendBias.WEAK_BULLISH
        elif last_close < ema_fast < (ema_slow - 0.05 * current_atr) and ema_slow <= (ema_trend + 0.10 * current_atr):
            direction = TrendBias.STRONG_BEARISH
        elif last_close < ema_fast and ema_fast <= ema_slow:
            direction = TrendBias.WEAK_BEARISH
        else:
            direction = TrendBias.RANGING

        # 7. Momentum Score calculation [-100, 100]
        # Combines RSI deviation from 50, EMA alignment slope, and MACD hist
        rsi_delta = (rsi - 50.0) * 1.5  # [-75, +75]
        ema_spread = ((ema_fast - ema_slow) / current_atr) * 20.0 if current_atr > 0 else 0.0
        hist_comp = math.copysign(min(abs(macd_hist / current_atr) * 30.0, 30.0), macd_hist) if current_atr > 0 else 0.0
        raw_momentum = rsi_delta + ema_spread + hist_comp
        momentum_score = round(max(-100.0, min(100.0, raw_momentum)), 1)

        # 8. Breakout & Reversal Detection
        breakout_detected = False
        breakout_dir: Optional[OrderType] = None
        if candle_analysis.pattern == CandlePatternType.BREAKOUT_CANDLE:
            breakout_detected = True
            breakout_dir = OrderType.BUY if candle_analysis.is_bullish else OrderType.SELL
        elif last_close > recent_high and candle_analysis.is_bullish and is_vol_expanding:
            breakout_detected = True
            breakout_dir = OrderType.BUY
        elif last_close < recent_low and candle_analysis.is_bearish and is_vol_expanding:
            breakout_detected = True
            breakout_dir = OrderType.SELL

        reversal_detected = False
        reversal_dir: Optional[OrderType] = None
        if candle_analysis.pattern == CandlePatternType.BULLISH_REJECTION and (rsi <= 35.0 or last_close <= recent_low + 0.25 * current_atr):
            reversal_detected = True
            reversal_dir = OrderType.BUY
        elif candle_analysis.pattern == CandlePatternType.BEARISH_REJECTION and (rsi >= 65.0 or last_close >= recent_high - 0.25 * current_atr):
            reversal_detected = True
            reversal_dir = OrderType.SELL
        elif candle_analysis.pattern == CandlePatternType.BULLISH_ENGULFING and rsi <= 40.0:
            reversal_detected = True
            reversal_dir = OrderType.BUY
        elif candle_analysis.pattern == CandlePatternType.BEARISH_ENGULFING and rsi >= 60.0:
            reversal_detected = True
            reversal_dir = OrderType.SELL

        # 9. Regime Classification
        if atr_ratio >= 1.80:
            regime = DetailedMarketRegime.HIGH_VOLATILITY
        elif breakout_detected and is_vol_expanding:
            regime = DetailedMarketRegime.BREAKOUT
        elif reversal_detected:
            regime = DetailedMarketRegime.REVERSAL
        elif is_vol_compressed and efficiency <= 0.25:
            regime = DetailedMarketRegime.LOW_VOLATILITY
        elif direction in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH) and efficiency >= 0.35:
            regime = DetailedMarketRegime.TRENDING_BULLISH
        elif direction in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH) and efficiency >= 0.35:
            regime = DetailedMarketRegime.TRENDING_BEARISH
        elif efficiency <= 0.30:
            regime = DetailedMarketRegime.RANGING
        else:
            regime = DetailedMarketRegime.RANGING

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=last_bar_time,
            regime=regime,
            direction=direction,
            directional_efficiency=efficiency,
            momentum_score=momentum_score,
            current_atr=round(current_atr, 6),
            atr_ratio=atr_ratio,
            is_volatility_expanding=is_vol_expanding,
            is_volatility_compressed=is_vol_compressed,
            spread_atr_ratio=spread_atr_ratio,
            relative_volume=candle_analysis.relative_volume,
            recent_high=recent_high,
            recent_low=recent_low,
            ema_fast=round(ema_fast, 5),
            ema_slow=round(ema_slow, 5),
            ema_trend=round(ema_trend, 5),
            rsi=rsi,
            macd_hist=round(macd_hist, 6),
            candle_analysis=candle_analysis,
            breakout_detected=breakout_detected,
            breakout_direction=breakout_dir,
            reversal_detected=reversal_detected,
            reversal_direction=reversal_dir,
            data_quality_healthy=len(completed) >= 20,
            details={
                "bandwidth": round(bb_bandwidth, 4),
                "pattern_desc": candle_analysis.description,
            },
        )

        self._cache[cache_key] = (last_bar_time, snapshot)
        return snapshot
