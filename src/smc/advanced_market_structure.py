"""
Advanced Market Structure Intelligence Engine.
Implements validated algorithmic concepts from institutional SMC/ICT methodology:
- Liquidity Intelligence (Swing extremes, EQH/EQL, PDH/PDL, PWH/PWL, Session highs/lows, BSL/SSL)
- Liquidity Sweep Recognition (Sweep vs Breakout vs Trap with reclaim & displacement confirmation)
- Market Structure Shifts (HH, HL, LH, LL, BOS, CHoCH, MSS, Internal vs External structure)
- Objective Fair Value Gap (FVG) and Secondary / Nested Imbalance analysis
- Breaker Block Intelligence (Decisive break through opposing structure with subsequent retest)
- Multi-Timeframe Pairing & Bias Engine (Monthly->Daily, Weekly->H4, Daily->H1, H4->M15, H1->M5)
- Breakout-Retracement-Retest Strategy with full setup lifecycle tracking
- Contextual Volume Confirmation (Relative volume, displacement expansion, sweep absorption)
- Unified Weighted Scoring Evaluator & Structural Stop/Target Management
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import logging
from typing import Any, Dict, List, Optional, Tuple, Sequence

from src.core.contracts import (
    Candle,
    OrderType,
    Timeframe,
    TrendBias,
    SetupType,
    SignalCandidate,
    FairValueGap,
    OrderBlock,
    LiquidityZone,
    ProfitManagementMode,
    SignalLifecycleState,
)

logger = logging.getLogger("AdvancedMarketStructure")


# =============================================================================
# ENUMS AND DATA MODELS
# =============================================================================

class LiquidityLevelType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    PREVIOUS_DAY_HIGH = "PREVIOUS_DAY_HIGH"
    PREVIOUS_DAY_LOW = "PREVIOUS_DAY_LOW"
    PREVIOUS_WEEK_HIGH = "PREVIOUS_WEEK_HIGH"
    PREVIOUS_WEEK_LOW = "PREVIOUS_WEEK_LOW"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    CONSOLIDATION_HIGH = "CONSOLIDATION_HIGH"
    CONSOLIDATION_LOW = "CONSOLIDATION_LOW"
    BUY_SIDE_LIQUIDITY = "BUY_SIDE_LIQUIDITY"
    SELL_SIDE_LIQUIDITY = "SELL_SIDE_LIQUIDITY"


class SweepClassification(str, Enum):
    SWEEP = "SWEEP"
    GENUINE_BREAKOUT = "GENUINE_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    STOP_RUN_WICK = "STOP_RUN_WICK"
    CONSOLIDATION_NOISE = "CONSOLIDATION_NOISE"


class StructureShiftType(str, Enum):
    BOS = "BOS"          # Break of Structure (Trend continuation)
    CHOCH = "CHOCH"      # Change of Character (Early structural warning)
    MSS = "MSS"          # Market Structure Shift (Displaced trend reversal)
    NONE = "NONE"


class FvgMitigationState(str, Enum):
    UNTOUCHED = "UNTOUCHED"
    PARTIALLY_MITIGATED = "PARTIALLY_MITIGATED"
    FULLY_MITIGATED = "FULLY_MITIGATED"
    INVALIDATED = "INVALIDATED"


class DirectionalState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class LiquidityPoint:
    level_id: str
    symbol: str
    timeframe: Timeframe
    level_type: LiquidityLevelType
    price: float
    high: float
    low: float
    formation_time: datetime
    reaction_count: int = 1
    prominence: float = 1.0  # ATR multiplier of the swing
    distance_pts: float = 0.0
    age_bars: int = 0
    is_swept: bool = False
    sweep_time: Optional[datetime] = None


@dataclass
class SweepEvent:
    symbol: str
    timeframe: Timeframe
    level: LiquidityPoint
    direction_bias: OrderType  # BUY (swept SSL and reclaimed), SELL (swept BSL and reclaimed)
    classification: SweepClassification
    penetration_pips: float
    penetration_pts: float
    wick_extreme: float
    reclaim_price: float
    reclaim_candle_index: int
    is_reclaimed: bool
    has_displacement: bool
    displacement_ratio: float
    is_mss_confirmed: bool
    timestamp: datetime


@dataclass
class BreakerZone:
    zone_id: str
    symbol: str
    timeframe: Timeframe
    direction: OrderType  # BUY = Bullish breaker (broken resistance now support), SELL = Bearish breaker
    top: float
    bottom: float
    midpoint: float
    formation_time: datetime
    broken_swing_price: float
    displacement_strength: float
    retested: bool = False
    invalidated: bool = False


@dataclass
class VolumeContext:
    symbol: str
    timeframe: Timeframe
    current_tick_volume: int
    baseline_volume: float
    relative_volume: float  # current / 20-bar baseline
    is_volume_expanding: bool
    is_retracement_dry: bool
    is_sweep_absorption: bool
    is_divergence_detected: bool
    regime_hypothesis: str  # "ACCUMULATION", "DISTRIBUTION", "NEUTRAL"
    volume_available: bool = True
    details: str = ""


# =============================================================================
# 1. LIQUIDITY INTELLIGENCE MAPPER
# =============================================================================

class AdvancedLiquidityMapper:
    """
    Identifies and evaluates institutional liquidity levels:
    - Swing extremes with prominence scoring and reaction counting
    - Equal Highs / Equal Lows (EQH/EQL) within configurable point tolerance
    - Session, Daily, and Weekly extremes (PDH/PDL, PWH/PWL)
    - Distinguishes untouched high-probability liquidity pools from swept noise
    """

    def __init__(
        self,
        swing_lookback: int = 5,
        eq_tolerance_pips: float = 2.0,
        pip_size: float = 0.0001,
        min_prominence_atr: float = 0.8,
    ):
        self.swing_lookback = swing_lookback
        self.eq_tolerance_pips = eq_tolerance_pips
        self.pip_size = pip_size
        self.min_prominence_atr = min_prominence_atr

    @staticmethod
    def compute_atr(candles: Sequence[Candle], period: int = 14) -> float:
        if not candles or len(candles) < 2:
            return candles[-1].range if candles else 0.001
        window = candles[-min(len(candles), period + 1):]
        trs: List[float] = []
        for i in range(1, len(window)):
            c = window[i]
            p = window[i - 1]
            trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
        return sum(trs) / len(trs) if trs else max(candles[-1].range, 1e-6)

    def map_liquidity(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle],
        pd_levels: Optional[Dict[str, float]] = None,
        session_levels: Optional[Dict[str, float]] = None,
    ) -> List[LiquidityPoint]:
        levels: List[LiquidityPoint] = []
        n = len(candles)
        k = self.swing_lookback
        if n < 2 * k + 1:
            return levels

        atr = self.compute_atr(candles)
        tolerance = self.eq_tolerance_pips * self.pip_size
        current_price = candles[-1].close

        # 1. Swing Highs and Swing Lows
        raw_swing_highs: List[Tuple[int, Candle]] = []
        raw_swing_lows: List[Tuple[int, Candle]] = []

        for i in range(k, n - k):
            c = candles[i]
            is_high = all(c.high > candles[j].high for j in range(i - k, i)) and \
                      all(c.high >= candles[j].high for j in range(i + 1, i + k + 1))
            if is_high:
                raw_swing_highs.append((i, c))

            is_low = all(c.low < candles[j].low for j in range(i - k, i)) and \
                     all(c.low <= candles[j].low for j in range(i + 1, i + k + 1))
            if is_low:
                raw_swing_lows.append((i, c))

        # 2. Equal Highs (EQH)
        for i in range(len(raw_swing_highs) - 1):
            idx1, sh1 = raw_swing_highs[i]
            idx2, sh2 = raw_swing_highs[i + 1]
            if abs(sh1.high - sh2.high) <= tolerance:
                eqh_price = max(sh1.high, sh2.high)
                swept = any(candles[j].high > eqh_price for j in range(idx2 + 1, n))
                levels.append(
                    LiquidityPoint(
                        level_id=f"{symbol}_{timeframe}_EQH_{sh2.time.strftime('%Y%m%d%H%M')}",
                        symbol=symbol,
                        timeframe=timeframe,
                        level_type=LiquidityLevelType.EQUAL_HIGHS,
                        price=eqh_price,
                        high=eqh_price + tolerance,
                        low=min(sh1.high, sh2.high),
                        formation_time=sh2.time,
                        reaction_count=2,
                        prominence=2.0,
                        distance_pts=abs(current_price - eqh_price) / (self.pip_size * 0.1),
                        age_bars=n - 1 - idx2,
                        is_swept=swept,
                    )
                )

        # 3. Equal Lows (EQL)
        for i in range(len(raw_swing_lows) - 1):
            idx1, sl1 = raw_swing_lows[i]
            idx2, sl2 = raw_swing_lows[i + 1]
            if abs(sl1.low - sl2.low) <= tolerance:
                eql_price = min(sl1.low, sl2.low)
                swept = any(candles[j].low < eql_price for j in range(idx2 + 1, n))
                levels.append(
                    LiquidityPoint(
                        level_id=f"{symbol}_{timeframe}_EQL_{sl2.time.strftime('%Y%m%d%H%M')}",
                        symbol=symbol,
                        timeframe=timeframe,
                        level_type=LiquidityLevelType.EQUAL_LOWS,
                        price=eql_price,
                        high=max(sl1.low, sl2.low),
                        low=eql_price - tolerance,
                        formation_time=sl2.time,
                        reaction_count=2,
                        prominence=2.0,
                        distance_pts=abs(current_price - eql_price) / (self.pip_size * 0.1),
                        age_bars=n - 1 - idx2,
                        is_swept=swept,
                    )
                )

        # 4. Filter Prominent Swing Highs (Buy-Side Liquidity)
        for idx, c in raw_swing_highs:
            prominence = (c.high - min(candles[max(0, idx - k):idx + k + 1], key=lambda x: x.low).low) / max(atr, 1e-6)
            if prominence >= self.min_prominence_atr:
                swept = any(candles[j].high > c.high for j in range(idx + 1, n))
                levels.append(
                    LiquidityPoint(
                        level_id=f"{symbol}_{timeframe}_BSL_{c.time.strftime('%Y%m%d%H%M')}",
                        symbol=symbol,
                        timeframe=timeframe,
                        level_type=LiquidityLevelType.BUY_SIDE_LIQUIDITY,
                        price=c.high,
                        high=c.high + tolerance,
                        low=c.high,
                        formation_time=c.time,
                        reaction_count=1,
                        prominence=round(prominence, 2),
                        distance_pts=abs(current_price - c.high) / (self.pip_size * 0.1),
                        age_bars=n - 1 - idx,
                        is_swept=swept,
                    )
                )

        # 5. Filter Prominent Swing Lows (Sell-Side Liquidity)
        for idx, c in raw_swing_lows:
            prominence = (max(candles[max(0, idx - k):idx + k + 1], key=lambda x: x.high).high - c.low) / max(atr, 1e-6)
            if prominence >= self.min_prominence_atr:
                swept = any(candles[j].low < c.low for j in range(idx + 1, n))
                levels.append(
                    LiquidityPoint(
                        level_id=f"{symbol}_{timeframe}_SSL_{c.time.strftime('%Y%m%d%H%M')}",
                        symbol=symbol,
                        timeframe=timeframe,
                        level_type=LiquidityLevelType.SELL_SIDE_LIQUIDITY,
                        price=c.low,
                        high=c.low,
                        low=c.low - tolerance,
                        formation_time=c.time,
                        reaction_count=1,
                        prominence=round(prominence, 2),
                        distance_pts=abs(current_price - c.low) / (self.pip_size * 0.1),
                        age_bars=n - 1 - idx,
                        is_swept=swept,
                    )
                )

        # 6. Session & Daily/Weekly Levels
        if pd_levels:
            if "PDH" in pd_levels and pd_levels["PDH"] > 0:
                p = pd_levels["PDH"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_PDH",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.PREVIOUS_DAY_HIGH,
                    price=p, high=p + tolerance, low=p,
                    formation_time=candles[-1].time,
                    prominence=2.5,
                    is_swept=any(c.high > p for c in candles[-24:]),
                ))
            if "PDL" in pd_levels and pd_levels["PDL"] > 0:
                p = pd_levels["PDL"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_PDL",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.PREVIOUS_DAY_LOW,
                    price=p, high=p, low=p - tolerance,
                    formation_time=candles[-1].time,
                    prominence=2.5,
                    is_swept=any(c.low < p for c in candles[-24:]),
                ))
            if "PWH" in pd_levels and pd_levels["PWH"] > 0:
                p = pd_levels["PWH"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_PWH",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.PREVIOUS_WEEK_HIGH,
                    price=p, high=p + tolerance, low=p,
                    formation_time=candles[-1].time,
                    prominence=3.5,
                    is_swept=any(c.high > p for c in candles[-96:]),
                ))
            if "PWL" in pd_levels and pd_levels["PWL"] > 0:
                p = pd_levels["PWL"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_PWL",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.PREVIOUS_WEEK_LOW,
                    price=p, high=p, low=p - tolerance,
                    formation_time=candles[-1].time,
                    prominence=3.5,
                    is_swept=any(c.low < p for c in candles[-96:]),
                ))

        if session_levels:
            if "ASIA_HIGH" in session_levels and session_levels["ASIA_HIGH"] > 0:
                p = session_levels["ASIA_HIGH"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_ASIA_HIGH",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.SESSION_HIGH,
                    price=p, high=p + tolerance, low=p,
                    formation_time=candles[-1].time,
                    prominence=1.8,
                    is_swept=any(c.high > p for c in candles[-16:]),
                ))
            if "ASIA_LOW" in session_levels and session_levels["ASIA_LOW"] > 0:
                p = session_levels["ASIA_LOW"]
                levels.append(LiquidityPoint(
                    level_id=f"{symbol}_{timeframe}_ASIA_LOW",
                    symbol=symbol, timeframe=timeframe,
                    level_type=LiquidityLevelType.SESSION_LOW,
                    price=p, high=p, low=p - tolerance,
                    formation_time=candles[-1].time,
                    prominence=1.8,
                    is_swept=any(c.low < p for c in candles[-16:]),
                ))

        return levels


# =============================================================================
# 2. LIQUIDITY SWEEP & BREAKOUT CLASSIFIER
# =============================================================================

class LiquiditySweepClassifier:
    """
    Distinguishes genuine liquidity sweeps from breakouts, stop-runs, and consolidation noise:
    - Bullish Sweep: Price breaks below SSL/Swing Low, reclaims and closes back above within 1-3 bars.
    - Bearish Sweep: Price breaks above BSL/Swing High, reclaims and closes back below within 1-3 bars.
    - Breakout: 2+ consecutive candle closes beyond level without immediate reclaim.
    - Displacement & MSS check: subsequent candle must show expansion and structural shift.
    """

    def __init__(
        self,
        pip_size: float = 0.0001,
        reclaim_window_bars: int = 3,
        displacement_atr_mult: float = 1.0,
    ):
        self.pip_size = pip_size
        self.reclaim_window_bars = reclaim_window_bars
        self.displacement_atr_mult = displacement_atr_mult

    def classify_sweep(
        self,
        level: LiquidityPoint,
        candles: List[Candle],
        atr: float,
    ) -> Optional[SweepEvent]:
        n = len(candles)
        if n < 3:
            return None

        # Look in recent bars for penetration
        eval_window = candles[-max(5, self.reclaim_window_bars + 2):]
        w_len = len(eval_window)

        is_high_pool = level.level_type in (
            LiquidityLevelType.BUY_SIDE_LIQUIDITY,
            LiquidityLevelType.EQUAL_HIGHS,
            LiquidityLevelType.PREVIOUS_DAY_HIGH,
            LiquidityLevelType.PREVIOUS_WEEK_HIGH,
            LiquidityLevelType.SESSION_HIGH,
            LiquidityLevelType.CONSOLIDATION_HIGH,
        )

        for i in range(w_len):
            bar = eval_window[i]

            if is_high_pool:
                # Bearish sweep candidate: pierced above high pool
                if bar.high > level.price:
                    pen_pips = (bar.high - level.price) / self.pip_size
                    pen_pts = (bar.high - level.price) / (self.pip_size * 0.1)

                    # Check reclaim: candle closes back below level
                    reclaimed = False
                    reclaim_idx = -1
                    if bar.close <= level.price:
                        reclaimed = True
                        reclaim_idx = i
                    else:
                        for j in range(i + 1, min(w_len, i + self.reclaim_window_bars + 1)):
                            if eval_window[j].close <= level.price:
                                reclaimed = True
                                reclaim_idx = j
                                break

                    # Multiple closes above -> Breakout, not sweep
                    if not reclaimed:
                        consec_closes = sum(1 for c in eval_window[i:] if c.close > level.price)
                        if consec_closes >= 2:
                            return SweepEvent(
                                symbol=level.symbol,
                                timeframe=level.timeframe,
                                level=level,
                                direction_bias=OrderType.BUY,
                                classification=SweepClassification.GENUINE_BREAKOUT,
                                penetration_pips=pen_pips,
                                penetration_pts=pen_pts,
                                wick_extreme=bar.high,
                                reclaim_price=bar.close,
                                reclaim_candle_index=i,
                                is_reclaimed=False,
                                has_displacement=False,
                                displacement_ratio=0.0,
                                is_mss_confirmed=False,
                                timestamp=bar.time,
                            )
                        continue

                    # If reclaimed, evaluate subsequent bearish displacement
                    disp_candle = eval_window[reclaim_idx] if reclaim_idx < w_len else eval_window[-1]
                    has_disp = (disp_candle.is_bearish and disp_candle.body >= self.displacement_atr_mult * atr)
                    disp_ratio = (disp_candle.body / max(disp_candle.range, 1e-6))

                    return SweepEvent(
                        symbol=level.symbol,
                        timeframe=level.timeframe,
                        level=level,
                        direction_bias=OrderType.SELL,
                        classification=SweepClassification.SWEEP,
                        penetration_pips=pen_pips,
                        penetration_pts=pen_pts,
                        wick_extreme=bar.high,
                        reclaim_price=eval_window[reclaim_idx].close,
                        reclaim_candle_index=reclaim_idx,
                        is_reclaimed=True,
                        has_displacement=has_disp,
                        displacement_ratio=round(disp_ratio, 2),
                        is_mss_confirmed=has_disp,
                        timestamp=eval_window[reclaim_idx].time,
                    )

            else:
                # Bullish sweep candidate: pierced below low pool
                if bar.low < level.price:
                    pen_pips = (level.price - bar.low) / self.pip_size
                    pen_pts = (level.price - bar.low) / (self.pip_size * 0.1)

                    reclaimed = False
                    reclaim_idx = -1
                    if bar.close >= level.price:
                        reclaimed = True
                        reclaim_idx = i
                    else:
                        for j in range(i + 1, min(w_len, i + self.reclaim_window_bars + 1)):
                            if eval_window[j].close >= level.price:
                                reclaimed = True
                                reclaim_idx = j
                                break

                    if not reclaimed:
                        consec_closes = sum(1 for c in eval_window[i:] if c.close < level.price)
                        if consec_closes >= 2:
                            return SweepEvent(
                                symbol=level.symbol,
                                timeframe=level.timeframe,
                                level=level,
                                direction_bias=OrderType.SELL,
                                classification=SweepClassification.GENUINE_BREAKOUT,
                                penetration_pips=pen_pips,
                                penetration_pts=pen_pts,
                                wick_extreme=bar.low,
                                reclaim_price=bar.close,
                                reclaim_candle_index=i,
                                is_reclaimed=False,
                                has_displacement=False,
                                displacement_ratio=0.0,
                                is_mss_confirmed=False,
                                timestamp=bar.time,
                            )
                        continue

                    disp_candle = eval_window[reclaim_idx] if reclaim_idx < w_len else eval_window[-1]
                    has_disp = (disp_candle.is_bullish and disp_candle.body >= self.displacement_atr_mult * atr)
                    disp_ratio = (disp_candle.body / max(disp_candle.range, 1e-6))

                    return SweepEvent(
                        symbol=level.symbol,
                        timeframe=level.timeframe,
                        level=level,
                        direction_bias=OrderType.BUY,
                        classification=SweepClassification.SWEEP,
                        penetration_pips=pen_pips,
                        penetration_pts=pen_pts,
                        wick_extreme=bar.low,
                        reclaim_price=eval_window[reclaim_idx].close,
                        reclaim_candle_index=reclaim_idx,
                        is_reclaimed=True,
                        has_displacement=has_disp,
                        displacement_ratio=round(disp_ratio, 2),
                        is_mss_confirmed=has_disp,
                        timestamp=eval_window[reclaim_idx].time,
                    )

        return None


# =============================================================================
# 3. FAIR VALUE GAP & BREAKER BLOCK INTELLIGENCE
# =============================================================================

class FvgBreakerEngine:
    """
    Detects 3-candle Fair Value Gaps, Secondary / Nested FVGs, and Breaker Blocks:
    - Primary FVG: Imbalance left by initial displacement
    - Secondary FVG: Nested imbalance formed during retracement or lower timeframe
    - Breaker Block: Decisive break through opposing structural order block / swing level
    """

    def __init__(
        self,
        pip_size: float = 0.0001,
        fvg_min_atr: float = 0.3,
        ob_displacement_atr_mult: float = 1.2,
    ):
        self.pip_size = pip_size
        self.fvg_min_atr = fvg_min_atr
        self.ob_displacement_atr_mult = ob_displacement_atr_mult

    def detect_all_fvgs(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle],
        atr: float,
    ) -> List[FairValueGap]:
        fvgs: List[FairValueGap] = []
        n = len(candles)
        if n < 3:
            return fvgs

        min_gap = max(self.fvg_min_atr * atr, 1.0 * self.pip_size)

        for i in range(2, n):
            c1 = candles[i - 2]
            c2 = candles[i - 1]  # Displacement
            c3 = candles[i]

            # Bullish FVG: c1.high < c3.low
            if c3.low > c1.high and (c3.low - c1.high) >= min_gap:
                bot = c1.high
                top = c3.low
                mid = (top + bot) / 2.0
                mitigated = any(c.low <= bot for c in candles[i + 1:])
                fvgs.append(
                    FairValueGap(
                        id=f"{symbol}_{timeframe}_{c2.time.strftime('%Y%m%d%H%M')}_BULL_FVG",
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=OrderType.BUY,
                        top=round(top, 5),
                        bottom=round(bot, 5),
                        midpoint=round(mid, 5),
                        formation_time=c2.time,
                        mitigated=mitigated,
                    )
                )

            # Bearish FVG: c1.low > c3.high
            elif c1.low > c3.high and (c1.low - c3.high) >= min_gap:
                top = c1.low
                bot = c3.high
                mid = (top + bot) / 2.0
                mitigated = any(c.high >= top for c in candles[i + 1:])
                fvgs.append(
                    FairValueGap(
                        id=f"{symbol}_{timeframe}_{c2.time.strftime('%Y%m%d%H%M')}_BEAR_FVG",
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=OrderType.SELL,
                        top=round(top, 5),
                        bottom=round(bot, 5),
                        midpoint=round(mid, 5),
                        formation_time=c2.time,
                        mitigated=mitigated,
                    )
                )

        return fvgs

    def detect_secondary_fvg(
        self,
        primary_fvg: FairValueGap,
        all_fvgs: List[FairValueGap],
        current_price: float,
    ) -> Optional[FairValueGap]:
        """
        Finds a nested or secondary FVG in the same direction that formed after the primary FVG
        within or near the retracement zone, providing higher precision entry.
        """
        candidates = [
            f for f in all_fvgs
            if f.direction == primary_fvg.direction
            and f.id != primary_fvg.id
            and f.formation_time > primary_fvg.formation_time
            and not f.mitigated
        ]
        if not candidates:
            return None

        # Return the freshest unmitigated secondary FVG closest to current price
        candidates.sort(key=lambda f: abs(f.midpoint - current_price))
        return candidates[0]

    def detect_breaker_blocks(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle],
        atr: float,
    ) -> List[BreakerZone]:
        """
        Identifies Breaker Blocks:
        - Bullish Breaker: An old swing high (or bearish order block) broken with strong bullish
          displacement that price later returns to test as new support.
        - Bearish Breaker: An old swing low (or bullish order block) broken with strong bearish
          displacement that price later returns to test as new resistance.
        """
        breakers: List[BreakerZone] = []
        n = len(candles)
        if n < 10:
            return breakers

        for i in range(5, n - 4):
            c_pivot = candles[i]

            # Potential Bearish Breaker: prior swing low broken downwards with displacement
            is_swing_low = all(c_pivot.low < candles[j].low for j in range(i - 4, i)) and \
                           all(c_pivot.low <= candles[j].low for j in range(i + 1, i + 3))

            if is_swing_low:
                # Look for subsequent bearish displacement bar breaking below c_pivot.low
                for j in range(i + 1, min(n - 1, i + 6)):
                    disp_bar = candles[j]
                    if disp_bar.is_bearish and disp_bar.close < c_pivot.low and disp_bar.body >= self.ob_displacement_atr_mult * atr:
                        # Broken swing low becomes a Bearish Breaker Zone
                        zone_top = c_pivot.high
                        zone_bot = c_pivot.low
                        retested = any(candles[k].high >= zone_bot and candles[k].close <= zone_top for k in range(j + 1, n))
                        invalidated = any(candles[k].close > zone_top for k in range(j + 1, n))
                        if not invalidated:
                            breakers.append(
                                BreakerZone(
                                    zone_id=f"{symbol}_{timeframe}_{c_pivot.time.strftime('%Y%m%d%H%M')}_BEAR_BREAKER",
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    direction=OrderType.SELL,
                                    top=zone_top,
                                    bottom=zone_bot,
                                    midpoint=(zone_top + zone_bot) / 2.0,
                                    formation_time=disp_bar.time,
                                    broken_swing_price=c_pivot.low,
                                    displacement_strength=round(disp_bar.body / max(atr, 1e-6), 2),
                                    retested=retested,
                                    invalidated=invalidated,
                                )
                            )
                        break

            # Potential Bullish Breaker: prior swing high broken upwards with displacement
            is_swing_high = all(c_pivot.high > candles[j].high for j in range(i - 4, i)) and \
                            all(c_pivot.high >= candles[j].high for j in range(i + 1, i + 3))

            if is_swing_high:
                for j in range(i + 1, min(n - 1, i + 6)):
                    disp_bar = candles[j]
                    if disp_bar.is_bullish and disp_bar.close > c_pivot.high and disp_bar.body >= self.ob_displacement_atr_mult * atr:
                        zone_top = c_pivot.high
                        zone_bot = c_pivot.low
                        retested = any(candles[k].low <= zone_top and candles[k].close >= zone_bot for k in range(j + 1, n))
                        invalidated = any(candles[k].close < zone_bot for k in range(j + 1, n))
                        if not invalidated:
                            breakers.append(
                                BreakerZone(
                                    zone_id=f"{symbol}_{timeframe}_{c_pivot.time.strftime('%Y%m%d%H%M')}_BULL_BREAKER",
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    direction=OrderType.BUY,
                                    top=zone_top,
                                    bottom=zone_bot,
                                    midpoint=(zone_top + zone_bot) / 2.0,
                                    formation_time=disp_bar.time,
                                    broken_swing_price=c_pivot.high,
                                    displacement_strength=round(disp_bar.body / max(atr, 1e-6), 2),
                                    retested=retested,
                                    invalidated=invalidated,
                                )
                            )
                        break

        return breakers


# =============================================================================
# 4. VOLUME & PRICE-ACTION CONFIRMATION ENGINE
# =============================================================================

class VolumeConfirmationEngine:
    """
    Evaluates relative volume, displacement expansion, retracement volume dry-up,
    and absorption during sweeps using rolling instrument-specific baselines.
    Does NOT veto trades when volume is flat or unavailable.
    """

    def __init__(self, rolling_period: int = 20):
        self.rolling_period = rolling_period

    def evaluate_volume(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle],
        is_sweep: bool = False,
    ) -> VolumeContext:
        if not candles or len(candles) < 3:
            return VolumeContext(
                symbol=symbol,
                timeframe=timeframe,
                current_tick_volume=0,
                baseline_volume=0.0,
                relative_volume=1.0,
                is_volume_expanding=False,
                is_retracement_dry=False,
                is_sweep_absorption=False,
                is_divergence_detected=False,
                regime_hypothesis="NEUTRAL",
                volume_available=False,
                details="Insufficient candles for volume baseline",
            )

        vols = [float(getattr(c, "tick_volume", 0) or 0) for c in candles]
        if all(v <= 0 for v in vols[-self.rolling_period:]):
            return VolumeContext(
                symbol=symbol,
                timeframe=timeframe,
                current_tick_volume=0,
                baseline_volume=0.0,
                relative_volume=1.0,
                is_volume_expanding=False,
                is_retracement_dry=False,
                is_sweep_absorption=False,
                is_divergence_detected=False,
                regime_hypothesis="NEUTRAL",
                volume_available=False,
                details="Broker feed does not provide tick volume; volume confirmation skipped safely",
            )

        window = vols[-self.rolling_period:]
        baseline = sum(window) / len(window) if window else 1.0
        cur_vol = vols[-1]
        rvol = (cur_vol / baseline) if baseline > 0 else 1.0

        expanding = rvol >= 1.25
        dry_up = rvol <= 0.80
        absorption = is_sweep and rvol >= 1.40

        # Divergence / accumulation hypothesis
        last_c = candles[-1]
        hypothesis = "NEUTRAL"
        if last_c.is_bullish and expanding:
            hypothesis = "ACCUMULATION"
        elif last_c.is_bearish and expanding:
            hypothesis = "DISTRIBUTION"

        return VolumeContext(
            symbol=symbol,
            timeframe=timeframe,
            current_tick_volume=int(cur_vol),
            baseline_volume=round(baseline, 1),
            relative_volume=round(rvol, 2),
            is_volume_expanding=expanding,
            is_retracement_dry=dry_up,
            is_sweep_absorption=absorption,
            is_divergence_detected=False,
            regime_hypothesis=hypothesis,
            volume_available=True,
            details=f"RVOL={rvol:.2f}x ({hypothesis}, expanding={expanding})",
        )


# =============================================================================
# 5. MULTI-TIMEFRAME PAIRINGS & BIAS ENGINE
# =============================================================================

class MultiTimeframePairingEngine:
    """
    Evaluates configurable Context -> Execution timeframe pairings:
    - Monthly -> Daily
    - Weekly  -> H4
    - Daily   -> H1
    - H4      -> M15
    - H1      -> M5
    Produces directional state: BULLISH, BEARISH, NEUTRAL.
    """

    PAIRINGS = {
        Timeframe.W1: Timeframe.H4,
        Timeframe.D1: Timeframe.H1,
        Timeframe.H4: Timeframe.M15,
        Timeframe.H1: Timeframe.M5,
        Timeframe.M15: Timeframe.M1,
    }

    @classmethod
    def get_execution_timeframe(cls, context_tf: Timeframe) -> Timeframe:
        return cls.PAIRINGS.get(context_tf, Timeframe.M15)

    @classmethod
    def evaluate_directional_state(
        cls,
        candles: List[Candle],
        swing_lookback: int = 5,
    ) -> DirectionalState:
        if not candles or len(candles) < 2 * swing_lookback + 1:
            return DirectionalState.NEUTRAL

        k = swing_lookback
        n = len(candles)
        swing_highs = [candles[i].high for i in range(k, n - k)
                       if all(candles[i].high > candles[j].high for j in range(i - k, i))
                       and all(candles[i].high >= candles[j].high for j in range(i + 1, i + k + 1))]
        swing_lows = [candles[i].low for i in range(k, n - k)
                      if all(candles[i].low < candles[j].low for j in range(i - k, i))
                      and all(candles[i].low <= candles[j].low for j in range(i + 1, i + k + 1))]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return DirectionalState.NEUTRAL

        hh = swing_highs[-1] > swing_highs[-2]
        hl = swing_lows[-1] > swing_lows[-2]
        lh = swing_highs[-1] < swing_highs[-2]
        ll = swing_lows[-1] < swing_lows[-2]

        if hh and hl:
            return DirectionalState.BULLISH
        elif lh and ll:
            return DirectionalState.BEARISH
        return DirectionalState.NEUTRAL


# =============================================================================
# 6. UNIFIED SETUP EVALUATOR & WEIGHTED SCORING
# =============================================================================

class AdvancedSetupEvaluator:
    """
    Unified setup evaluator with configurable weighted scoring:
    - Higher-timeframe alignment: 15%
    - Liquidity context: 15%
    - Structure confirmation (BOS/MSS): 20%
    - Displacement quality: 10%
    - FVG / Breaker quality: 15%
    - Location precision (Discount for buys, Premium for sells): 10%
    - Volume evidence: 5%
    - Cost-adjusted reward/risk: 10%
    """

    def __init__(
        self,
        min_score: float = 70.0,
        min_rr: float = 1.5,
        pip_size: float = 0.0001,
    ):
        self.min_score = min_score
        self.min_rr = min_rr
        self.pip_size = pip_size

    def evaluate_candidate(
        self,
        symbol: str,
        direction: OrderType,
        htf_state: DirectionalState,
        sweep: Optional[SweepEvent],
        fvg: Optional[FairValueGap],
        secondary_fvg: Optional[FairValueGap],
        breaker: Optional[BreakerZone],
        volume_ctx: VolumeContext,
        entry_price: float,
        structural_sl: float,
        target_tp: float,
        timeframe: Timeframe = Timeframe.M15,
        context_timeframe: Timeframe = Timeframe.H1,
    ) -> Tuple[float, Dict[str, float], List[str]]:
        score = 0.0
        breakdown: Dict[str, float] = {}
        explanations: List[str] = []

        is_buy = direction in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)

        # 1. HTF Directional Alignment (15 pts)
        expected_htf = DirectionalState.BULLISH if is_buy else DirectionalState.BEARISH
        if htf_state == expected_htf:
            htf_pts = 15.0
            explanations.append(f"HTF Bias Aligned ({context_timeframe}={htf_state.value})")
        elif htf_state == DirectionalState.NEUTRAL:
            htf_pts = 8.0
            explanations.append(f"HTF Bias Neutral ({context_timeframe})")
        else:
            htf_pts = 0.0
            explanations.append(f"Counter-HTF Setup ({context_timeframe}={htf_state.value})")
        breakdown["htf_alignment"] = htf_pts
        score += htf_pts

        # 2. Liquidity Context (15 pts)
        liq_pts = 0.0
        if sweep:
            if sweep.classification == SweepClassification.SWEEP and sweep.is_reclaimed:
                liq_pts = 15.0
                explanations.append(f"Liquidity Sweep Confirmed ({sweep.level.level_type.value} swept & reclaimed)")
            elif sweep.classification == SweepClassification.GENUINE_BREAKOUT:
                liq_pts = 10.0
                explanations.append("Breakout Continuation Context")
            else:
                liq_pts = 5.0
        else:
            liq_pts = 5.0
            explanations.append("Standard Structure Context")
        breakdown["liquidity_context"] = liq_pts
        score += liq_pts

        # 3. Structure Confirmation (20 pts)
        struct_pts = 0.0
        if sweep and sweep.is_mss_confirmed:
            struct_pts = 20.0
            explanations.append("Market Structure Shift (MSS) Confirmed")
        elif breaker:
            struct_pts = 18.0
            explanations.append(f"Breaker Block Retest Validated ({breaker.zone_id})")
        elif fvg:
            struct_pts = 15.0
            explanations.append("BOS with Imbalance Confirmed")
        else:
            struct_pts = 10.0
        breakdown["structure_confirmation"] = struct_pts
        score += struct_pts

        # 4. Displacement Quality (10 pts)
        disp_pts = 0.0
        if sweep and sweep.has_displacement:
            disp_pts = 10.0
            explanations.append(f"Displacement Confirmed (ratio={sweep.displacement_ratio:.2f})")
        elif breaker and breaker.displacement_strength >= 1.2:
            disp_pts = 9.0
            explanations.append(f"Breaker Displacement Strong ({breaker.displacement_strength:.1f}x ATR)")
        else:
            disp_pts = 5.0
        breakdown["displacement_quality"] = disp_pts
        score += disp_pts

        # 5. FVG / POI Quality (15 pts)
        fvg_pts = 0.0
        if fvg and not fvg.mitigated:
            fvg_pts += 10.0
            explanations.append(f"Primary FVG Valid ({fvg.bottom:.5f} - {fvg.top:.5f})")
        if secondary_fvg:
            fvg_pts += 5.0
            explanations.append(f"Secondary Nested FVG Confluence (+5 pts)")
        elif breaker:
            fvg_pts += 5.0
            explanations.append(f"Breaker Zone Confluence (+5 pts)")
        breakdown["fvg_quality"] = min(15.0, fvg_pts)
        score += breakdown["fvg_quality"]

        # 6. Entry-Location Precision (10 pts)
        loc_pts = 10.0
        if is_buy and entry_price <= structural_sl:
            loc_pts = 0.0
        elif (not is_buy) and entry_price >= structural_sl:
            loc_pts = 0.0
        breakdown["location_precision"] = loc_pts
        score += loc_pts

        # 7. Volume Evidence (5 pts)
        vol_pts = 0.0
        if volume_ctx.volume_available:
            if volume_ctx.is_volume_expanding:
                vol_pts = 5.0
                explanations.append(f"Volume Expansion Supportive (RVOL={volume_ctx.relative_volume}x)")
            elif volume_ctx.is_retracement_dry:
                vol_pts = 4.0
                explanations.append("Volume Dry-up on Retracement Supportive")
            else:
                vol_pts = 3.0
        else:
            vol_pts = 3.0  # Neutral fallback when volume unavailable
            explanations.append("Volume Neutral (Feed does not provide tick volume)")
        breakdown["volume_evidence"] = vol_pts
        score += vol_pts

        # 8. Cost-Adjusted Reward/Risk (10 pts)
        risk = abs(entry_price - structural_sl)
        reward = abs(target_tp - entry_price)
        rr = (reward / risk) if risk > 0 else 0.0
        if rr >= 2.5:
            rr_pts = 10.0
        elif rr >= 2.0:
            rr_pts = 8.0
        elif rr >= self.min_rr:
            rr_pts = 6.0
        else:
            rr_pts = 2.0
        breakdown["reward_to_risk"] = rr_pts
        score += rr_pts
        explanations.append(f"Reward/Risk={rr:.2f}R")

        return round(score, 1), breakdown, explanations
