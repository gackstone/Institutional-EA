"""
Advanced ICT/SMC Market Intelligence Engine (Videos 0010–0019).

Extends Institutional-EA's existing SMC architecture (`WeeklyDailyEngine`, `LiquidityEngine`,
`FvgObEngine`, `video_primitives`, `SpecializedSymbolUniverse`) without duplicating or weakening
existing execution, risk management, DEMO locks, or Rule R9.3 (tighten-only stops).

Modules implemented:
  - Module A: Higher-Timeframe Liquidity & Quarterly Context (0010, 0012) — PDH/PDL, PWH/PWL, 60-day H/L, 3-4m quarterly range
  - Module B: Liquidity Sweep Detection (0010–0015) — 4-way classification, closed-candle only
  - Module C: Market Structure Intelligence (0010, 0012, 0013) — BOS vs MSS vs wick-only penetration vs pullback
  - Module D: Displacement Quality & FVG/CE Intelligence (0013, 0015) — 7-factor displacement score + CE midpoint
  - Module E: Advanced Order Block Intelligence (0015–0019) — Order Block, Breaker, Mitigation, Propulsion, Rejection + Failed Setup transitions
  - Module F: ICT Unicorn Model (0011) — Sweep + Displacement through OB -> Breaker + FVG overlap
  - Module G: Optimal Trade Entry (0014) — BOS-anchored 62%–79% (70.5% sweet spot) gated by displacement & context
  - Module H: Liquidity-Based Take-Profit & Fibonacci Extensions (0012, 0013) — -2.0 extension + structural liquidity barriers
  - Scoring, 5-State Lifecycle, 11 Rejection Codes, Shadow Mode (default), and Per-Model Performance Tracking.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.contracts import (
    Candle,
    FairValueGap,
    LiquidityZone,
    OrderBlock,
    OrderType,
    SetupType,
    SignalCandidate,
    Timeframe,
    TrendBias,
)
from src.smc.video_primitives import (
    AnchoredFibOte,
    ConfirmedSweep,
    StopClusterPool,
    classify_sweep_vs_breakout,
    compute_atr,
    compute_bos_anchored_ote,
    detect_equal_clusters,
    detect_fvgs_with_ce,
    find_swings,
)
from src.smc.weekly_daily import WeeklyDailyEngine

logger = logging.getLogger("ICTIntelligence")


# ============================================================================
# CONFIGURATION & FAIL-CLOSED VALIDATION
# ============================================================================

class ICTConfigValidationError(ValueError):
    """Raised when ict_intelligence configuration violates safety or range bounds."""


DEFAULT_ICT_INTELLIGENCE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "mode": "SHADOW",  # "OFF" | "SHADOW" | "DEMO_EXECUTE" (LIVE forbidden)
    "allow_live_orders": False,
    "never_scale_lot_by_score": True,
    "liquidity_lookback_days": 60,
    "quarterly_lookback_days": 90,
    "swing_left": 2,
    "swing_right": 2,
    "eqh_tolerance_atr": 0.10,
    "min_pierce_atr": 0.05,
    "max_bars_to_reclaim": 3,
    "displacement_min_body_ratio": 0.55,
    "displacement_min_atr_mult": 1.0,
    "displacement_min_expansion_ratio": 1.25,
    "displacement_min_score": 55.0,
    "fvg_min_atr": 0.15,
    "ob_requires_displacement": True,
    "ob_requires_fvg_or_bos": True,
    "rejection_min_wick_ratio": 0.45,
    "ote_low_ratio": 0.62,
    "ote_high_ratio": 0.79,
    "ote_sweet_spot": 0.705,
    "fib_extension_levels": [-1.0, -1.5, -2.0, -2.5],
    "primary_fib_extension": -2.0,
    "min_rr": 2.0,
    "max_entry_distance_atr": 1.5,
    "max_spread_atr_ratio": 0.35,
    "max_data_age_seconds": 3600,
    "stop_buffer_atr": 0.05,
    "confirmed_score_threshold": 55.0,
    "high_quality_score_threshold": 72.0,
    "scoring_weights": {
        "htf_context": 15.0,
        "sweep_quality": 12.0,
        "displacement": 15.0,
        "structure_break": 12.0,
        "fvg_quality": 10.0,
        "zone_validity": 12.0,
        "entry_precision": 8.0,
        "target_rr": 10.0,
        "regime_execution": 6.0,
    },
    "models": {
        "LIQUIDITY_SWEEP_MSS": {"enabled": True},
        "UNICORN": {"enabled": True},
        "OTE": {"enabled": True},
        "FVG_RETEST": {"enabled": True},
        "BREAKER_BLOCK": {"enabled": True},
        "MITIGATION_BLOCK": {"enabled": True},
        "PROPULSION_BLOCK": {"enabled": True},
        "REJECTION_BLOCK": {"enabled": True},
    },
}


def validate_ict_intelligence_config(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merges with safe defaults and fails closed on unsafe or out-of-range parameters."""
    merged = copy.deepcopy(DEFAULT_ICT_INTELLIGENCE_CONFIG)
    if cfg:
        for k, v in cfg.items():
            if k in ("scoring_weights", "models") and isinstance(v, dict):
                merged[k].update(v)
            else:
                merged[k] = v

    mode = str(merged.get("mode", "SHADOW")).upper()
    if mode not in ("OFF", "SHADOW", "DEMO_EXECUTE"):
        raise ICTConfigValidationError(
            f"Invalid ict_intelligence.mode={mode!r}; must be OFF, SHADOW, or DEMO_EXECUTE (LIVE forbidden)."
        )
    merged["mode"] = mode

    if bool(merged.get("allow_live_orders", False)):
        raise ICTConfigValidationError("ict_intelligence.allow_live_orders MUST remain False.")
    if not bool(merged.get("never_scale_lot_by_score", True)):
        raise ICTConfigValidationError("ict_intelligence.never_scale_lot_by_score MUST remain True.")

    if float(merged["min_rr"]) < 0.5 or float(merged["min_rr"]) > 20.0:
        raise ICTConfigValidationError(f"min_rr out of bounds: {merged['min_rr']}")
    if not (0.1 <= float(merged["displacement_min_body_ratio"]) <= 0.95):
        raise ICTConfigValidationError("displacement_min_body_ratio must be in [0.1, 0.95]")
    if float(merged["fvg_min_atr"]) < 0.0 or float(merged["fvg_min_atr"]) > 5.0:
        raise ICTConfigValidationError("fvg_min_atr must be in [0.0, 5.0]")
    if not (0.50 <= float(merged["ote_low_ratio"]) < float(merged["ote_high_ratio"]) <= 0.95):
        raise ICTConfigValidationError("Invalid OTE retracement boundaries.")
    if int(merged["liquidity_lookback_days"]) < 5:
        raise ICTConfigValidationError("liquidity_lookback_days must be >= 5.")
    if int(merged["quarterly_lookback_days"]) < 30:
        raise ICTConfigValidationError("quarterly_lookback_days must be >= 30.")

    weight_sum = sum(float(x) for x in merged["scoring_weights"].values())
    if weight_sum <= 0 or any(float(x) < 0 for x in merged["scoring_weights"].values()):
        raise ICTConfigValidationError("scoring_weights must be non-negative with positive sum.")

    return merged


# ============================================================================
# ENUMS & CORE DATA CONTRACTS
# ============================================================================

class SweepState(str, Enum):
    CONFIRMED_SWEEP = "CONFIRMED_SWEEP"
    POTENTIAL_SWEEP = "POTENTIAL_SWEEP"
    GENUINE_BREAKOUT = "GENUINE_BREAKOUT"
    UNCONFIRMED_RAID = "UNCONFIRMED_RAID"


class StructureEventKind(str, Enum):
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    STRUCTURAL_BREAKOUT = "STRUCTURAL_BREAKOUT"
    DIRECTIONAL_TRANSITION = "DIRECTIONAL_TRANSITION"
    TEMPORARY_PULLBACK = "TEMPORARY_PULLBACK"
    WICK_ONLY_PENETRATION = "WICK_ONLY_PENETRATION"


class InstitutionalZoneType(str, Enum):
    ORDER_BLOCK = "ORDER_BLOCK"
    BREAKER_BLOCK = "BREAKER_BLOCK"
    MITIGATION_BLOCK = "MITIGATION_BLOCK"
    PROPULSION_BLOCK = "PROPULSION_BLOCK"
    REJECTION_BLOCK = "REJECTION_BLOCK"


class SetupLifecycleStage(str, Enum):
    POTENTIAL = "POTENTIAL"
    DEVELOPING = "DEVELOPING"
    CONFIRMED = "CONFIRMED"
    HIGH_QUALITY = "HIGH_QUALITY"
    INVALIDATED = "INVALIDATED"


class RejectionCode(str, Enum):
    NO_DISPLACEMENT = "NO_DISPLACEMENT"
    WEAK_CANDLES_NO_IMBALANCE = "WEAK_CANDLES_NO_IMBALANCE"
    FVG_TOO_SMALL = "FVG_TOO_SMALL"
    WICK_ONLY_BREAK = "WICK_ONLY_BREAK"
    OB_INVALIDATED = "OB_INVALIDATED"
    ENTRY_TOO_FAR_FROM_ZONE = "ENTRY_TOO_FAR_FROM_ZONE"
    TARGET_ALREADY_REACHED = "TARGET_ALREADY_REACHED"
    INSUFFICIENT_RR = "INSUFFICIENT_RR"
    UNACCEPTABLE_SPREAD_OR_VOLATILITY = "UNACCEPTABLE_SPREAD_OR_VOLATILITY"
    STALE_OR_INCOMPLETE_DATA = "STALE_OR_INCOMPLETE_DATA"
    UNFINISHED_CANDLE = "UNFINISHED_CANDLE"


def _closed_candles(candles: Sequence[Candle]) -> List[Candle]:
    """Strictly filters to closed candles only (anti-repainting / no look-ahead)."""
    return [c for c in candles if getattr(c, "complete", True)]


# ============================================================================
# MODULE A: HIGHER-TIMEFRAME LIQUIDITY & QUARTERLY CONTEXT (0010, 0012)
# ============================================================================

@dataclass(frozen=True)
class EnrichedLiquidityLevel:
    id: str
    symbol: str
    timeframe: Timeframe
    price: float
    formation_time: datetime
    level_class: str  # PDH, PDL, PWH, PWL, D60_HIGH, D60_LOW, EQH, EQL, BSL, SSL
    scope: str        # "EXTERNAL" | "INTERNAL"
    swept: bool
    distance_price: float
    distance_atr: float
    relevance_to_bias: str  # "PRIMARY_TARGET" | "SWEEP_CANDIDATE" | "NEUTRAL" | "MITIGATED"
    priority: int = 1       # Higher = more significant institutional pool


@dataclass(frozen=True)
class QuarterlyContext:
    symbol: str
    lookback_days: int
    quarterly_high: float
    quarterly_low: float
    equilibrium: float
    current_price: float
    position_pct: float  # 0.0 (at quarterly low) .. 1.0 (at quarterly high)
    quadrant: str        # "DEEP_DISCOUNT" | "DISCOUNT" | "PREMIUM" | "DEEP_PREMIUM"
    d60_high: float
    d60_low: float
    d60_high_swept: bool
    d60_low_swept: bool
    contextual_bias: TrendBias  # Contextual only; never a standalone entry signal
    note: str = "Contextual quarterly filter only — does not auto-generate entries."


class HTFLiquidityAnalyzer:
    """
    Module A [VIDEOS 0010, 0012]:
    Computes enriched HTF liquidity levels (PDH/PDL, PWH/PWL, 60-day highs/lows,
    significant swings, EQH/EQL) and 3–4 month quarterly context.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.cfg = validate_ict_intelligence_config(config)
        self.wd_engine = WeeklyDailyEngine()

    def build_quarterly_context(
        self,
        symbol: str,
        daily_candles: Sequence[Candle],
        current_price: Optional[float] = None,
    ) -> Optional[QuarterlyContext]:
        closed = _closed_candles(daily_candles)
        if len(closed) < 5:
            return None

        px = float(current_price if current_price is not None else closed[-1].close)
        q_days = min(len(closed), int(self.cfg["quarterly_lookback_days"]))
        d60_days = min(len(closed), int(self.cfg["liquidity_lookback_days"]))

        q_slice = closed[-q_days:]
        d60_slice = closed[-d60_days:]
        prior_d60 = d60_slice[:-1] if len(d60_slice) > 1 else d60_slice

        q_high = max(c.high for c in q_slice)
        q_low = min(c.low for c in q_slice)
        eq = (q_high + q_low) / 2.0
        rng = max(q_high - q_low, 1e-9)
        pos_pct = max(0.0, min(1.0, (px - q_low) / rng))

        if pos_pct >= 0.80:
            quad = "DEEP_PREMIUM"
        elif pos_pct >= 0.50:
            quad = "PREMIUM"
        elif pos_pct <= 0.20:
            quad = "DEEP_DISCOUNT"
        else:
            quad = "DISCOUNT"

        d60_high = max(c.high for c in prior_d60)
        d60_low = min(c.low for c in prior_d60)
        last_bar = closed[-1]
        d60_high_swept = last_bar.high > d60_high
        d60_low_swept = last_bar.low < d60_low

        # Contextual bias based on quarterly progression (first vs second half close)
        mid_idx = len(q_slice) // 2
        if q_slice[-1].close > q_slice[mid_idx].close and pos_pct > 0.50:
            ctx_bias = TrendBias.WEAK_BULLISH if pos_pct >= 0.85 else TrendBias.STRONG_BULLISH
        elif q_slice[-1].close < q_slice[mid_idx].close and pos_pct < 0.50:
            ctx_bias = TrendBias.WEAK_BEARISH if pos_pct <= 0.15 else TrendBias.STRONG_BEARISH
        else:
            ctx_bias = TrendBias.RANGING

        return QuarterlyContext(
            symbol=symbol,
            lookback_days=q_days,
            quarterly_high=round(q_high, 5),
            quarterly_low=round(q_low, 5),
            equilibrium=round(eq, 5),
            current_price=round(px, 5),
            position_pct=round(pos_pct, 4),
            quadrant=quad,
            d60_high=round(d60_high, 5),
            d60_low=round(d60_low, 5),
            d60_high_swept=d60_high_swept,
            d60_low_swept=d60_low_swept,
            contextual_bias=ctx_bias,
        )

    def collect_liquidity_levels(
        self,
        symbol: str,
        ltf_candles: Sequence[Candle],
        ltf_timeframe: Timeframe = Timeframe.M15,
        daily_candles: Optional[Sequence[Candle]] = None,
        weekly_candles: Optional[Sequence[Candle]] = None,
        directional_bias: Optional[OrderType] = None,
    ) -> List[EnrichedLiquidityLevel]:
        closed_ltf = _closed_candles(ltf_candles)
        if not closed_ltf:
            return []

        px = closed_ltf[-1].close
        atr = max(compute_atr(closed_ltf, 14), 1e-6)
        levels: List[EnrichedLiquidityLevel] = []

        def _relevance(is_high: bool, swept: bool) -> str:
            if swept:
                return "MITIGATED"
            if directional_bias is None:
                return "NEUTRAL"
            if directional_bias == OrderType.BUY:
                return "PRIMARY_TARGET" if is_high else "SWEEP_CANDIDATE"
            return "PRIMARY_TARGET" if not is_high else "SWEEP_CANDIDATE"

        def _add(
            lid: str,
            tf: Timeframe,
            price: float,
            ts: datetime,
            lclass: str,
            scope: str,
            is_high: bool,
            swept: bool,
            priority: int,
        ) -> None:
            dist = abs(price - px)
            levels.append(
                EnrichedLiquidityLevel(
                    id=lid,
                    symbol=symbol,
                    timeframe=tf,
                    price=round(price, 5),
                    formation_time=ts,
                    level_class=lclass,
                    scope=scope,
                    swept=swept,
                    distance_price=round(dist, 5),
                    distance_atr=round(dist / atr, 3),
                    relevance_to_bias=_relevance(is_high, swept),
                    priority=priority,
                )
            )

        # 1. Daily & Weekly levels (reusing WeeklyDailyEngine) + 60-day highs/lows
        closed_d = _closed_candles(daily_candles or [])
        closed_w = _closed_candles(weekly_candles or [])
        if len(closed_d) >= 2:
            prev_d = closed_d[-2]
            curr_d = closed_d[-1]
            _add(f"{symbol}_PDH", Timeframe.D1, prev_d.high, prev_d.time, "PDH", "EXTERNAL", True, curr_d.high > prev_d.high, 4)
            _add(f"{symbol}_PDL", Timeframe.D1, prev_d.low, prev_d.time, "PDL", "EXTERNAL", False, curr_d.low < prev_d.low, 4)

            d60_n = min(len(closed_d), int(self.cfg["liquidity_lookback_days"]))
            prior_60 = closed_d[-d60_n:-1] if d60_n > 1 else closed_d[-d60_n:]
            if prior_60:
                max_bar = max(prior_60, key=lambda c: c.high)
                min_bar = min(prior_60, key=lambda c: c.low)
                _add(f"{symbol}_D60_HIGH", Timeframe.D1, max_bar.high, max_bar.time, "D60_HIGH", "EXTERNAL", True, curr_d.high > max_bar.high, 5)
                _add(f"{symbol}_D60_LOW", Timeframe.D1, min_bar.low, min_bar.time, "D60_LOW", "EXTERNAL", False, curr_d.low < min_bar.low, 5)

        if len(closed_w) >= 2:
            prev_w = closed_w[-2]
            curr_w = closed_w[-1]
            _add(f"{symbol}_PWH", Timeframe.W1, prev_w.high, prev_w.time, "PWH", "EXTERNAL", True, curr_w.high > prev_w.high, 5)
            _add(f"{symbol}_PWL", Timeframe.W1, prev_w.low, prev_w.time, "PWL", "EXTERNAL", False, curr_w.low < prev_w.low, 5)

        # 2. LTF Equal Highs/Lows & Swings (reusing video_primitives.detect_equal_clusters)
        pools = detect_equal_clusters(
            symbol,
            ltf_timeframe,
            closed_ltf,
            atr_tolerance_mult=float(self.cfg["eqh_tolerance_atr"]),
            swing_left=int(self.cfg["swing_left"]),
            swing_right=int(self.cfg["swing_right"]),
        )
        max_ltf_high = max(c.high for c in closed_ltf)
        min_ltf_low = min(c.low for c in closed_ltf)
        for p in pools:
            is_high = p.level_type in ("EQH", "BSL")
            is_ext = (
                p.level_type in ("EQH", "EQL")
                or (is_high and abs(p.price - max_ltf_high) <= 0.25 * atr)
                or (not is_high and abs(p.price - min_ltf_low) <= 0.25 * atr)
            )
            prio = 3 if p.level_type in ("EQH", "EQL") else (2 if is_ext else 1)
            _add(
                p.id,
                ltf_timeframe,
                p.price,
                p.formation_time,
                p.level_type,
                "EXTERNAL" if is_ext else "INTERNAL",
                is_high,
                p.status == "taken",
                prio,
            )

        levels.sort(key=lambda lv: (-lv.priority, lv.distance_price))
        return levels


# ============================================================================
# MODULE D: DISPLACEMENT QUALITY ASSESSMENT (0015) — defined before B/C/E
# ============================================================================

@dataclass(frozen=True)
class DisplacementAssessment:
    is_valid: bool
    direction: OrderType
    candle_index: int
    quality_score: float       # 0.0 .. 100.0
    body_to_range: float
    size_to_atr: float
    expansion_ratio: float
    close_location: float      # 1.0 = closed right at directional extreme
    directional_consistency: float
    created_fvg: Optional[FairValueGap]
    broke_structure: bool
    reasons: List[str] = field(default_factory=list)


def assess_displacement_quality(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    candle_index: int,
    direction: OrderType,
    config: Optional[Dict[str, Any]] = None,
    broken_level: Optional[float] = None,
    pip_size: float = 0.01,
) -> DisplacementAssessment:
    """
    Module D [VIDEO 0015]:
    Evaluates institutional displacement quality across 7 measurable factors:
      1. Body relative to total range
      2. Candle size relative to ATR
      3. Directional consistency (consecutive same-direction bars)
      4. Close location within candle (near high for BUY, near low for SELL)
      5. Expansion relative to preceding 5 candles' average range
      6. Resulting 3-candle FVG imbalance
      7. Structural level broken by candle close
    Rejects weak/small candles without meaningful imbalance.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    if candle_index < 0 or candle_index >= len(closed):
        return DisplacementAssessment(
            is_valid=False, direction=direction, candle_index=candle_index,
            quality_score=0.0, body_to_range=0.0, size_to_atr=0.0,
            expansion_ratio=0.0, close_location=0.0, directional_consistency=0.0,
            created_fvg=None, broke_structure=False,
            reasons=[RejectionCode.STALE_OR_INCOMPLETE_DATA.value],
        )

    c = closed[candle_index]
    is_buy = direction == OrderType.BUY
    correct_dir = (c.close > c.open) if is_buy else (c.close < c.open)
    rng = max(c.range, 1e-9)
    body_ratio = c.body / rng
    atr = max(compute_atr(closed[: candle_index + 1], 14), 1e-6)
    size_to_atr = c.body / atr

    prev_slice = closed[max(0, candle_index - 5): candle_index]
    avg_prev_range = (sum(x.range for x in prev_slice) / len(prev_slice)) if prev_slice else rng
    expansion = rng / max(avg_prev_range, 1e-9)

    close_loc = ((c.close - c.low) / rng) if is_buy else ((c.high - c.close) / rng)

    # Directional consistency over [candle_index - 1 .. candle_index + 1]
    win = closed[max(0, candle_index - 1): min(len(closed), candle_index + 2)]
    same_dir = sum(1 for x in win if ((x.close > x.open) if is_buy else (x.close < x.open)))
    dir_consistency = same_dir / max(len(win), 1)

    # Check if this candle is the middle impulse candle of a valid 3-candle FVG
    created_fvg: Optional[FairValueGap] = None
    if 1 <= candle_index <= len(closed) - 2:
        c0 = closed[candle_index - 1]
        c2 = closed[candle_index + 1]
        min_gap = float(cfg["fvg_min_atr"]) * atr
        if is_buy and c2.low > c0.high and (c2.low - c0.high) >= min_gap:
            created_fvg = FairValueGap(
                id=f"{symbol}_{timeframe.value}_{c.time.isoformat()}_BULL_FVG",
                symbol=symbol, timeframe=timeframe, direction=OrderType.BUY,
                top=c2.low, bottom=c0.high, midpoint=(c2.low + c0.high) / 2.0,
                formation_time=c.time,
            )
        elif (not is_buy) and c2.high < c0.low and (c0.low - c2.high) >= min_gap:
            created_fvg = FairValueGap(
                id=f"{symbol}_{timeframe.value}_{c.time.isoformat()}_BEAR_FVG",
                symbol=symbol, timeframe=timeframe, direction=OrderType.SELL,
                top=c0.low, bottom=c2.high, midpoint=(c0.low + c2.high) / 2.0,
                formation_time=c.time,
            )

    broke_struct = False
    if broken_level is not None:
        broke_struct = (c.close > broken_level) if is_buy else (c.close < broken_level)

    reasons: List[str] = []
    if not correct_dir:
        reasons.append(RejectionCode.NO_DISPLACEMENT.value)

    min_body = float(cfg["displacement_min_body_ratio"])
    min_atr = float(cfg["displacement_min_atr_mult"])
    min_exp = float(cfg["displacement_min_expansion_ratio"])

    pts = 0.0
    if correct_dir:
        pts += min(20.0, 20.0 * (body_ratio / max(min_body, 1e-6)))
        pts += min(20.0, 20.0 * (size_to_atr / max(min_atr, 1e-6)))
        pts += min(15.0, 15.0 * (expansion / max(min_exp, 1e-6)))
        pts += 10.0 * max(0.0, min(1.0, close_loc))
        pts += 10.0 * dir_consistency
        if created_fvg is not None:
            pts += 15.0
        if broke_struct:
            pts += 10.0

    if body_ratio < min_body or size_to_atr < min_atr * 0.75:
        reasons.append(RejectionCode.WEAK_CANDLES_NO_IMBALANCE.value)
    if created_fvg is None and not broke_struct:
        reasons.append(RejectionCode.FVG_TOO_SMALL.value)

    score = round(min(100.0, max(0.0, pts)), 2)
    is_valid = (
        correct_dir
        and score >= float(cfg["displacement_min_score"])
        and body_ratio >= min_body * 0.85
        and size_to_atr >= min_atr * 0.75
        and (created_fvg is not None or broke_struct)
    )
    if not is_valid and not reasons:
        reasons.append(RejectionCode.NO_DISPLACEMENT.value)

    return DisplacementAssessment(
        is_valid=is_valid,
        direction=direction,
        candle_index=candle_index,
        quality_score=score,
        body_to_range=round(body_ratio, 4),
        size_to_atr=round(size_to_atr, 4),
        expansion_ratio=round(expansion, 4),
        close_location=round(close_loc, 4),
        directional_consistency=round(dir_consistency, 4),
        created_fvg=created_fvg,
        broke_structure=broke_struct,
        reasons=reasons,
    )


# ============================================================================
# MODULE B: LIQUIDITY SWEEP DETECTION (0010–0015)
# ============================================================================

@dataclass(frozen=True)
class LiquiditySweepEvent:
    state: SweepState
    direction: OrderType       # Post-sweep reversal direction (SELL after BSL sweep, BUY after SSL sweep)
    level_price: float
    level_type: str
    pierce_index: int
    reclaim_index: Optional[int]
    sweep_extreme: float
    wick_penetration: float
    wick_penetration_atr: float
    rejection_ratio: float
    displacement: Optional[DisplacementAssessment]
    reason: str


def detect_liquidity_sweep(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    level_price: float,
    level_type: str,
    start_index: int = 1,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[LiquiditySweepEvent]:
    """
    Module B [VIDEOS 0010–0015]:
    Detects and differentiates:
      - CONFIRMED_SWEEP: pierce + close back inside + subsequent valid displacement
      - POTENTIAL_SWEEP: pierce + close back inside, awaiting displacement
      - GENUINE_BREAKOUT: decisive acceptance/close beyond level without reclaim
      - UNCONFIRMED_RAID: wick pierced too shallowly or failed to reclaim within window
    Uses closed candles only.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 4 or start_index >= n:
        return None

    is_bsl = level_type.upper() in ("BSL", "EQH", "PDH", "PWH", "D60_HIGH", "ASIA_HIGH", "LONDON_HIGH")
    rev_dir = OrderType.SELL if is_bsl else OrderType.BUY
    atr = max(compute_atr(closed, 14), 1e-6)
    min_pierce = float(cfg["min_pierce_atr"]) * atr
    max_reclaim = int(cfg["max_bars_to_reclaim"])

    for i in range(max(1, start_index), n):
        c = closed[i]
        pierced = (c.high > level_price) if is_bsl else (c.low < level_price)
        if not pierced:
            continue

        pen = (c.high - level_price) if is_bsl else (level_price - c.low)
        pen_atr = pen / atr
        if pen < min_pierce:
            return LiquiditySweepEvent(
                state=SweepState.UNCONFIRMED_RAID,
                direction=rev_dir, level_price=level_price, level_type=level_type,
                pierce_index=i, reclaim_index=None,
                sweep_extreme=c.high if is_bsl else c.low,
                wick_penetration=round(pen, 5), wick_penetration_atr=round(pen_atr, 4),
                rejection_ratio=0.0, displacement=None,
                reason=f"Pierce {pen_atr:.3f} ATR below minimum {cfg['min_pierce_atr']} ATR",
            )

        # Check reclaim within max_reclaim closed bars
        reclaim_idx: Optional[int] = None
        extreme = c.high if is_bsl else c.low
        for j in range(i, min(n, i + max_reclaim + 1)):
            cj = closed[j]
            extreme = max(extreme, cj.high) if is_bsl else min(extreme, cj.low)
            closed_inside = (cj.close < level_price) if is_bsl else (cj.close > level_price)
            if closed_inside:
                reclaim_idx = j
                break

        cls = classify_sweep_vs_breakout(closed, level_price, level_type, i)
        if reclaim_idx is None or (reclaim_idx > i and cls.kind == "BREAKOUT"):
            return LiquiditySweepEvent(
                state=SweepState.GENUINE_BREAKOUT,
                direction=OrderType.BUY if is_bsl else OrderType.SELL,
                level_price=level_price, level_type=level_type,
                pierce_index=i, reclaim_index=None, sweep_extreme=extreme,
                wick_penetration=round(pen, 5), wick_penetration_atr=round(pen_atr, 4),
                rejection_ratio=0.0, displacement=None,
                reason="Decisive acceptance beyond level without reclaim (genuine breakout, not sweep)",
            )

        rc = closed[reclaim_idx]
        rej_wick = (rc.high - max(rc.open, rc.close)) if is_bsl else (min(rc.open, rc.close) - rc.low)
        rej_ratio = rej_wick / max(rc.range, 1e-9)

        # Look for subsequent displacement in rev_dir
        best_disp: Optional[DisplacementAssessment] = None
        for k in range(reclaim_idx, min(n, reclaim_idx + 6)):
            da = assess_displacement_quality(symbol, timeframe, closed, k, rev_dir, config=cfg)
            if da.is_valid:
                best_disp = da
                break

        if best_disp is not None:
            return LiquiditySweepEvent(
                state=SweepState.CONFIRMED_SWEEP,
                direction=rev_dir, level_price=level_price, level_type=level_type,
                pierce_index=i, reclaim_index=reclaim_idx, sweep_extreme=extreme,
                wick_penetration=round(pen, 5), wick_penetration_atr=round(pen_atr, 4),
                rejection_ratio=round(rej_ratio, 4), displacement=best_disp,
                reason=f"Confirmed sweep + displacement (score={best_disp.quality_score:.1f})",
            )

        return LiquiditySweepEvent(
            state=SweepState.POTENTIAL_SWEEP,
            direction=rev_dir, level_price=level_price, level_type=level_type,
            pierce_index=i, reclaim_index=reclaim_idx, sweep_extreme=extreme,
            wick_penetration=round(pen, 5), wick_penetration_atr=round(pen_atr, 4),
            rejection_ratio=round(rej_ratio, 4), displacement=None,
            reason="Sweep reclaimed inside level; awaiting institutional displacement confirmation",
        )

    return None


# ============================================================================
# MODULE C: MARKET STRUCTURE INTELLIGENCE (0010, 0012, 0013)
# ============================================================================

@dataclass(frozen=True)
class MarketStructureEvent:
    kind: StructureEventKind
    label: str                 # "MSS" | "BOS" | "WICK_ONLY" | "PULLBACK"
    direction: OrderType
    broken_level: float
    break_index: int
    displacement: Optional[DisplacementAssessment]
    is_valid_break: bool
    reason: str


def analyze_market_structure_transition(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: OrderType,
    after_index: int = 0,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[MarketStructureEvent]:
    """
    Module C [VIDEOS 0010, 0012, 0013]:
    Distinguishes:
      - DIRECTIONAL_TRANSITION (MSS with body-close + institutional displacement)
      - STRUCTURAL_BREAKOUT (body-close BOS without full displacement)
      - WICK_ONLY_PENETRATION (wick exceeded level but closed back — NOT a valid break!)
      - TEMPORARY_PULLBACK (no opposing swing broken)
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 6:
        return None

    shs, sls = find_swings(closed, left=int(cfg["swing_left"]), right=int(cfg["swing_right"]))
    is_buy = direction == OrderType.BUY

    if is_buy:
        prior = [c.high for idx, c in shs if idx <= max(after_index, n - 3)]
        if not prior:
            prior = [max(c.high for c in closed[max(0, after_index - 5): max(1, after_index + 1)])]
        ref_level = prior[-1]
    else:
        prior = [c.low for idx, c in sls if idx <= max(after_index, n - 3)]
        if not prior:
            prior = [min(c.low for c in closed[max(0, after_index - 5): max(1, after_index + 1)])]
        ref_level = prior[-1]

    wick_only_idx: Optional[int] = None
    for k in range(max(1, after_index), n):
        ck = closed[k]
        body_broke = (ck.close > ref_level) if is_buy else (ck.close < ref_level)
        wick_broke = (ck.high > ref_level) if is_buy else (ck.low < ref_level)
        if body_broke:
            disp = assess_displacement_quality(
                symbol, timeframe, closed, k, direction, config=cfg, broken_level=ref_level
            )
            if disp.is_valid:
                return MarketStructureEvent(
                    kind=StructureEventKind.DIRECTIONAL_TRANSITION,
                    label="MSS",
                    direction=direction,
                    broken_level=round(ref_level, 5),
                    break_index=k,
                    displacement=disp,
                    is_valid_break=True,
                    reason=f"Body-close MSS with displacement (score={disp.quality_score:.1f}) beyond {ref_level:.5f}",
                )
            return MarketStructureEvent(
                kind=StructureEventKind.STRUCTURAL_BREAKOUT,
                label="BOS",
                direction=direction,
                broken_level=round(ref_level, 5),
                break_index=k,
                displacement=disp,
                is_valid_break=True,
                reason=f"Body-close BOS beyond {ref_level:.5f} (weak displacement score={disp.quality_score:.1f})",
            )
        elif wick_broke and wick_only_idx is None:
            wick_only_idx = k

    if wick_only_idx is not None:
        return MarketStructureEvent(
            kind=StructureEventKind.WICK_ONLY_PENETRATION,
            label="WICK_ONLY",
            direction=direction,
            broken_level=round(ref_level, 5),
            break_index=wick_only_idx,
            displacement=None,
            is_valid_break=False,
            reason=f"Wick-only penetration of {ref_level:.5f} without candle close (not a valid structural break)",
        )

    return MarketStructureEvent(
        kind=StructureEventKind.TEMPORARY_PULLBACK,
        label="PULLBACK",
        direction=direction,
        broken_level=round(ref_level, 5),
        break_index=n - 1,
        displacement=None,
        is_valid_break=False,
        reason="Price remained inside prior structural range (temporary pullback)",
    )


# ============================================================================
# MODULE E: ADVANCED ORDER BLOCK INTELLIGENCE (0015–0019)
# ============================================================================

@dataclass(frozen=True)
class InstitutionalZone:
    id: str
    zone_type: InstitutionalZoneType
    symbol: str
    timeframe: Timeframe
    direction: OrderType       # Trade direction supported by this zone
    high: float
    low: float
    midpoint: float            # Mean threshold / midpoint for precision entry
    formation_index: int
    formation_time: datetime
    invalidated: bool = False
    invalidation_index: Optional[int] = None
    mitigated: bool = False
    trapped_traders: bool = False
    parent_zone_id: Optional[str] = None
    reason: str = ""


@dataclass(frozen=True)
class FailedSetupTransition:
    original_zone_id: str
    original_direction: OrderType
    invalidation_index: int
    invalidation_price: float
    new_zone_type: InstitutionalZoneType  # BREAKER_BLOCK or MITIGATION_BLOCK
    new_direction: OrderType
    had_prior_liquidity_sweep: bool
    trapped_side: str  # "TRAPPED_BUYERS" | "TRAPPED_SELLERS"
    reason: str


def detect_validated_order_blocks(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[InstitutionalZone]:
    """
    Module E.1 [VIDEO 0015]:
    Identifies Bullish & Bearish Order Blocks validated by subsequent institutional displacement.
    Explicitly marks failed OBs as `invalidated=True` when price closes beyond their defining boundary.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 5:
        return []

    dirs = [direction] if direction is not None else [OrderType.BUY, OrderType.SELL]
    zones: List[InstitutionalZone] = []

    for d in dirs:
        is_buy = d == OrderType.BUY
        for i in range(1, n - 2):
            c = closed[i]
            is_opposing = (c.close < c.open) if is_buy else (c.close > c.open)
            if not is_opposing:
                continue

            # Require qualifying displacement within next 2 closed bars
            disp_ok = False
            for j in range(i + 1, min(n, i + 3)):
                da = assess_displacement_quality(
                    symbol, timeframe, closed, j, d, config=cfg,
                    broken_level=c.high if is_buy else c.low,
                )
                if da.is_valid:
                    disp_ok = True
                    break
            if not disp_ok:
                continue

            # Check invalidation & mitigation on subsequent closed bars
            invalidated = False
            inv_idx: Optional[int] = None
            mitigated = False
            for k in range(i + 2, n):
                ck = closed[k]
                if is_buy:
                    if ck.low <= c.high and ck.high >= c.low:
                        mitigated = True
                    if ck.close < c.low:
                        invalidated = True
                        inv_idx = k
                        break
                else:
                    if ck.high >= c.low and ck.low <= c.high:
                        mitigated = True
                    if ck.close > c.high:
                        invalidated = True
                        inv_idx = k
                        break

            zones.append(
                InstitutionalZone(
                    id=f"{symbol}_{timeframe.value}_OB_{d.value}_{i}",
                    zone_type=InstitutionalZoneType.ORDER_BLOCK,
                    symbol=symbol, timeframe=timeframe, direction=d,
                    high=c.high, low=c.low, midpoint=(c.high + c.low) / 2.0,
                    formation_index=i, formation_time=c.time,
                    invalidated=invalidated, invalidation_index=inv_idx,
                    mitigated=mitigated,
                    reason=f"Displacement-validated {d.value} Order Block"
                    + (" [INVALIDATED]" if invalidated else ""),
                )
            )
    return zones


def detect_breaker_and_mitigation_blocks(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[InstitutionalZone], List[InstitutionalZone], List[FailedSetupTransition]]:
    """
    Module E.2 & E.3 [VIDEOS 0018, 0019]:
    Tracks failed Order Blocks and cleanly separates:
      - Breaker Blocks (0019): Prior external liquidity sweep occurred before the OB was decisively smashed.
      - Mitigation Blocks (0018): OB failed via decisive close-through WITHOUT a prior external sweep.
    Both flag `trapped_traders=True` and emit `FailedSetupTransition` records.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 6:
        return [], [], []

    breakers: List[InstitutionalZone] = []
    mitigations: List[InstitutionalZone] = []
    transitions: List[FailedSetupTransition] = []

    dirs = [direction] if direction is not None else [OrderType.SELL, OrderType.BUY]
    for target_dir in dirs:
        # A bearish breaker/mitigation comes from a FAILED bullish OB (down candle before up move, then closed below)
        orig_dir = OrderType.BUY if target_dir == OrderType.SELL else OrderType.SELL
        orig_is_buy = orig_dir == OrderType.BUY

        for i in range(1, n - 2):
            ob_c = closed[i]
            is_orig_ob_candle = (ob_c.close < ob_c.open) if orig_is_buy else (ob_c.close > ob_c.open)
            if not is_orig_ob_candle:
                continue

            # Must have at least 1 opposing reaction candle in orig_dir before failing
            peak_idx: Optional[int] = None
            peak_px = ob_c.high if orig_is_buy else ob_c.low
            inv_idx: Optional[int] = None
            for k in range(i + 1, n):
                ck = closed[k]
                if orig_is_buy:
                    if ck.high > peak_px and inv_idx is None:
                        peak_px = ck.high
                        peak_idx = k
                    if ck.close < ob_c.low and peak_idx is not None:
                        inv_idx = k
                        break
                else:
                    if ck.low < peak_px and inv_idx is None:
                        peak_px = ck.low
                        peak_idx = k
                    if ck.close > ob_c.high and peak_idx is not None:
                        inv_idx = k
                        break

            if inv_idx is None or peak_idx is None:
                continue

            # Determine if peak_px swept a prior high (for bearish breaker) or prior low (for bullish breaker)
            prior_bars = closed[:i]
            had_sweep = False
            if prior_bars:
                if orig_is_buy:
                    had_sweep = peak_px > max(x.high for x in prior_bars)
                else:
                    had_sweep = peak_px < min(x.low for x in prior_bars)

            z_type = InstitutionalZoneType.BREAKER_BLOCK if had_sweep else InstitutionalZoneType.MITIGATION_BLOCK
            trapped = "TRAPPED_BUYERS" if orig_is_buy else "TRAPPED_SELLERS"
            orig_id = f"{symbol}_{timeframe.value}_OB_{orig_dir.value}_{i}"

            # Check if retested after invalidation
            retested = any(
                (closed[m].high >= ob_c.low and closed[m].low <= ob_c.high)
                for m in range(inv_idx + 1, n)
            )

            zone = InstitutionalZone(
                id=f"{symbol}_{timeframe.value}_{z_type.value}_{target_dir.value}_{i}",
                zone_type=z_type,
                symbol=symbol, timeframe=timeframe, direction=target_dir,
                high=ob_c.high, low=ob_c.low, midpoint=(ob_c.high + ob_c.low) / 2.0,
                formation_index=inv_idx, formation_time=closed[inv_idx].time,
                invalidated=False, mitigated=retested, trapped_traders=True,
                parent_zone_id=orig_id,
                reason=(
                    f"{z_type.value} ({trapped}): failed {orig_dir.value} OB closed through at bar {inv_idx}"
                    + (" after liquidity sweep" if had_sweep else " without external sweep")
                ),
            )
            trans = FailedSetupTransition(
                original_zone_id=orig_id,
                original_direction=orig_dir,
                invalidation_index=inv_idx,
                invalidation_price=ob_c.low if orig_is_buy else ob_c.high,
                new_zone_type=z_type,
                new_direction=target_dir,
                had_prior_liquidity_sweep=had_sweep,
                trapped_side=trapped,
                reason=zone.reason,
            )
            transitions.append(trans)
            if had_sweep:
                breakers.append(zone)
            else:
                mitigations.append(zone)

    return breakers, mitigations, transitions


def detect_propulsion_blocks(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[InstitutionalZone]:
    """
    Module E.4 [VIDEO 0016]:
    Detects Propulsion Blocks:
      1. Identify a valid parent Order Block.
      2. Observe a subsequent opposing candle trading INTO the parent OB (without invalidating it).
      3. Confirm strong displacement away from that opposing candle in the trade direction.
      4. Compute mean threshold (50% midpoint) of the propulsion candle for retest entries.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 7:
        return []

    parent_obs = [
        z for z in detect_validated_order_blocks(symbol, timeframe, closed, direction=direction, config=cfg)
        if not z.invalidated
    ]
    propulsions: List[InstitutionalZone] = []

    for ob in parent_obs:
        is_buy = ob.direction == OrderType.BUY
        for k in range(ob.formation_index + 2, n - 1):
            ck = closed[k]
            is_opposing = (ck.close < ck.open) if is_buy else (ck.close > ck.open)
            if not is_opposing:
                continue
            # Must dip into parent OB without closing beyond parent OB invalidation
            if is_buy:
                dipped_in = ck.low <= ob.high and ck.close >= ob.low
            else:
                dipped_in = ck.high >= ob.low and ck.close <= ob.high
            if not dipped_in:
                continue

            # Require subsequent displacement away from the propulsion candle
            disp_ok = False
            for m in range(k + 1, min(n, k + 3)):
                da = assess_displacement_quality(
                    symbol, timeframe, closed, m, ob.direction, config=cfg,
                    broken_level=ck.high if is_buy else ck.low,
                )
                if da.is_valid:
                    disp_ok = True
                    break
            if not disp_ok:
                continue

            mean_threshold = (ck.high + ck.low) / 2.0
            propulsions.append(
                InstitutionalZone(
                    id=f"{symbol}_{timeframe.value}_PROPULSION_{ob.direction.value}_{k}",
                    zone_type=InstitutionalZoneType.PROPULSION_BLOCK,
                    symbol=symbol, timeframe=timeframe, direction=ob.direction,
                    high=ck.high, low=ck.low, midpoint=round(mean_threshold, 5),
                    formation_index=k, formation_time=ck.time,
                    parent_zone_id=ob.id,
                    reason=f"Propulsion Block anchored to parent {ob.id}; mean threshold={mean_threshold:.5f}",
                )
            )
            break

    return propulsions


def detect_rejection_blocks(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[InstitutionalZone]:
    """
    Module E.5 [VIDEO 0017]:
    Identifies Rejection Blocks formed by pronounced wicks around swing liquidity:
      - Bearish Rejection Block: long upper wick at swing high -> zone [highest_body_top, wick_high], midpoint entry.
      - Bullish Rejection Block: long lower wick at swing low -> zone [wick_low, lowest_body_bottom], midpoint entry.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 5:
        return []

    min_wick = float(cfg["rejection_min_wick_ratio"])
    dirs = [direction] if direction is not None else [OrderType.SELL, OrderType.BUY]
    rejections: List[InstitutionalZone] = []

    for d in dirs:
        is_sell = d == OrderType.SELL
        for i in range(2, n - 1):
            c = closed[i]
            rng = max(c.range, 1e-9)
            body_top = max(c.open, c.close)
            body_bot = min(c.open, c.close)

            if is_sell:
                upper_wick = c.high - body_top
                if upper_wick / rng < min_wick:
                    continue
                # Must be near/above local liquidity high
                local_max = max(x.high for x in closed[max(0, i - 4): i])
                if c.high < local_max:
                    continue
                z_low, z_high = body_top, c.high
            else:
                lower_wick = body_bot - c.low
                if lower_wick / rng < min_wick:
                    continue
                local_min = min(x.low for x in closed[max(0, i - 4): i])
                if c.low > local_min:
                    continue
                z_low, z_high = c.low, body_bot

            if z_high <= z_low:
                continue

            # Check if invalidated by subsequent close beyond wick extreme
            invalidated = any(
                (closed[m].close > z_high if is_sell else closed[m].close < z_low)
                for m in range(i + 1, n)
            )
            rejections.append(
                InstitutionalZone(
                    id=f"{symbol}_{timeframe.value}_REJECTION_{d.value}_{i}",
                    zone_type=InstitutionalZoneType.REJECTION_BLOCK,
                    symbol=symbol, timeframe=timeframe, direction=d,
                    high=round(z_high, 5), low=round(z_low, 5),
                    midpoint=round((z_high + z_low) / 2.0, 5),
                    formation_index=i, formation_time=c.time,
                    invalidated=invalidated,
                    reason=f"{d.value} Rejection Block (wick ratio={(upper_wick if is_sell else lower_wick)/rng:.2f})",
                )
            )

    return rejections


# ============================================================================
# MODULE F: ICT UNICORN MODEL (0011)
# ============================================================================

@dataclass(frozen=True)
class UnicornSetup:
    symbol: str
    timeframe: Timeframe
    direction: OrderType
    sweep: LiquiditySweepEvent
    breaker: InstitutionalZone
    fvg: FairValueGap
    overlap_low: float
    overlap_high: float
    entry_price: float
    invalidation_stop: float
    reason: str


def detect_unicorn_setup(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
    pip_size: float = 0.01,
) -> Optional[UnicornSetup]:
    """
    Module F [VIDEO 0011]:
    True ICT Unicorn Model — NEVER fires from an arbitrary OB+FVG overlap.
    Requires ALL 5 conditions:
      1. BSL/SSL liquidity sweep (with reclaim)
      2. Opposing displacement smashing through prior OB -> Breaker Block
      3. Fresh FVG formed by that displacement
      4. Spatial overlap between the Breaker Block and the FVG
      5. Entry inside the overlap zone, invalidation SL beyond the sweep extreme.
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    n = len(closed)
    if n < 8:
        return None

    atr = max(compute_atr(closed, 14), 1e-6)
    buf = float(cfg["stop_buffer_atr"]) * atr
    dirs = [direction] if direction is not None else [OrderType.SELL, OrderType.BUY]

    for d in dirs:
        breakers, _, _ = detect_breaker_and_mitigation_blocks(symbol, timeframe, closed, direction=d, config=cfg)
        if not breakers:
            continue
        fvgs = [
            f for f in detect_fvgs_with_ce(symbol, timeframe, closed, fvg_min_atr=float(cfg["fvg_min_atr"]), pip_size=pip_size)
            if f.direction == d
        ]
        if not fvgs:
            continue

        for br in reversed(breakers):
            # Verify liquidity sweep occurred prior to breaker formation
            prior_slice = closed[: max(1, br.formation_index)]
            is_sell = d == OrderType.SELL
            if len(prior_slice) < 3:
                continue
            ref_level = max(x.high for x in prior_slice[:-1]) if is_sell else min(x.low for x in prior_slice[:-1])
            sweep = detect_liquidity_sweep(
                symbol, timeframe, closed,
                level_price=ref_level, level_type="BSL" if is_sell else "SSL",
                start_index=1, config=cfg,
            )
            if sweep is None or sweep.state not in (SweepState.CONFIRMED_SWEEP, SweepState.POTENTIAL_SWEEP):
                continue

            for fvg in reversed(fvgs):
                ov_low = max(br.low, fvg.bottom)
                ov_high = min(br.high, fvg.top)
                if ov_low <= ov_high:
                    entry = (ov_low + ov_high) / 2.0
                    sl = (sweep.sweep_extreme + buf) if is_sell else (sweep.sweep_extreme - buf)
                    return UnicornSetup(
                        symbol=symbol, timeframe=timeframe, direction=d,
                        sweep=sweep, breaker=br, fvg=fvg,
                        overlap_low=round(ov_low, 5), overlap_high=round(ov_high, 5),
                        entry_price=round(entry, 5), invalidation_stop=round(sl, 5),
                        reason=f"ICT Unicorn {d.value}: sweep@{sweep.sweep_extreme:.5f} + Breaker/FVG overlap [{ov_low:.5f}..{ov_high:.5f}]",
                    )
    return None


# ============================================================================
# MODULE G: OPTIMAL TRADE ENTRY (0014)
# ============================================================================

@dataclass(frozen=True)
class OTESetup:
    symbol: str
    timeframe: Timeframe
    direction: OrderType
    anchored_ote: AnchoredFibOte
    displacement: DisplacementAssessment
    entry_price: float
    invalidation_stop: float
    reason: str


def detect_ote_setup(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    config: Optional[Dict[str, Any]] = None,
    pip_size: float = 0.01,
) -> Optional[OTESetup]:
    """
    Module G [VIDEO 0014]:
    Reuses `compute_bos_anchored_ote` (62%–79%, 70.5% sweet spot), gated by
    institutional displacement on the BOS impulse leg (never enters on a blind 70.5% touch).
    """
    cfg = validate_ict_intelligence_config(config)
    closed = _closed_candles(candles)
    if len(closed) < 9:
        return None

    atr = max(compute_atr(closed, 14), 1e-6)
    buf = float(cfg["stop_buffer_atr"]) * atr
    dirs = [direction] if direction is not None else [OrderType.BUY, OrderType.SELL]

    for d in dirs:
        ote = compute_bos_anchored_ote(
            symbol, timeframe, closed, direction=d,
            entry_level=float(cfg["ote_sweet_spot"]), pip_size=pip_size,
        )
        if ote is None:
            continue

        # Validate that the BOS impulse leg contained genuine institutional displacement
        best_disp: Optional[DisplacementAssessment] = None
        for idx in range(ote.origin_index + 1, min(len(closed), ote.extreme_index + 1)):
            da = assess_displacement_quality(symbol, timeframe, closed, idx, d, config=cfg)
            if da.is_valid:
                best_disp = da
                break
        if best_disp is None:
            continue

        is_buy = d == OrderType.BUY
        sl = (ote.anchor_origin - buf) if is_buy else (ote.anchor_origin + buf)
        return OTESetup(
            symbol=symbol, timeframe=timeframe, direction=d,
            anchored_ote=ote, displacement=best_disp,
            entry_price=round(ote.ote_sweet_spot, 5),
            invalidation_stop=round(sl, 5),
            reason=f"BOS-anchored OTE {d.value} @ 70.5% ({ote.ote_sweet_spot:.5f}), disp={best_disp.quality_score:.1f}",
        )
    return None


# ============================================================================
# MODULE H: LIQUIDITY-BASED TAKE-PROFIT & FIBONACCI EXTENSIONS (0012, 0013)
# ============================================================================

@dataclass(frozen=True)
class FibExtensionProjection:
    direction: OrderType
    anchor_origin: float
    anchor_extreme: float
    extensions: Dict[str, float]  # "-1.0", "-1.5", "-2.0", "-2.5"
    primary_target: float         # -2.0 extension


@dataclass(frozen=True)
class TargetSelection:
    selected_price: float
    source: str                   # e.g. "PDH", "D60_HIGH", "BSL", "FIB_EXT_-2.0"
    reward_to_risk: float
    net_reward_to_risk: float     # After spread/transaction cost
    fib_projection: Optional[FibExtensionProjection]
    earlier_liquidity_barrier: Optional[EnrichedLiquidityLevel]
    reason: str


def compute_fib_extensions(
    direction: OrderType,
    anchor_origin: float,
    anchor_extreme: float,
    levels: Sequence[float] = (-1.0, -1.5, -2.0, -2.5),
    primary_level: float = -2.0,
) -> FibExtensionProjection:
    """
    Module H [VIDEO 0013]:
    Consistent documented directional anchoring convention:
      - Impulse leg = abs(anchor_extreme - anchor_origin)
      - For BUY (anchor_origin = swing low, anchor_extreme = impulse high):
          extension(-k) = anchor_extreme + k * leg
      - For SELL (anchor_origin = swing high, anchor_extreme = impulse low):
          extension(-k) = anchor_extreme - k * leg
    """
    leg = abs(anchor_extreme - anchor_origin)
    is_buy = direction == OrderType.BUY
    exts: Dict[str, float] = {}
    for lv in levels:
        mult = abs(float(lv))
        px = (anchor_extreme + mult * leg) if is_buy else (anchor_extreme - mult * leg)
        exts[f"{float(lv):.1f}"] = round(px, 5)
    prim_key = f"{float(primary_level):.1f}"
    prim_px = exts.get(
        prim_key,
        round((anchor_extreme + abs(primary_level) * leg) if is_buy else (anchor_extreme - abs(primary_level) * leg), 5),
    )
    return FibExtensionProjection(
        direction=direction,
        anchor_origin=round(anchor_origin, 5),
        anchor_extreme=round(anchor_extreme, 5),
        extensions=exts,
        primary_target=prim_px,
    )


def select_liquidity_target(
    direction: OrderType,
    entry_price: float,
    stop_loss: float,
    liquidity_levels: Sequence[EnrichedLiquidityLevel],
    fib_projection: Optional[FibExtensionProjection] = None,
    spread_cost: float = 0.0,
    min_rr: float = 2.0,
) -> Optional[TargetSelection]:
    """
    Module H [VIDEOS 0012, 0013]:
    Selects realistic liquidity-based take-profit targets.
    Prefers an earlier untapped opposing liquidity pool (PDH/PDL, PWH/PWL, D60, EQH/EQL, BSL/SSL)
    when it already satisfies `min_rr`, rather than forcing a distant Fibonacci extension.
    """
    risk = abs(entry_price - stop_loss)
    if risk <= 1e-9:
        return None
    is_buy = direction == OrderType.BUY

    valid_pools = [
        lv for lv in liquidity_levels
        if not lv.swept
        and ((lv.price > entry_price) if is_buy else (lv.price < entry_price))
    ]
    valid_pools.sort(key=lambda lv: abs(lv.price - entry_price))

    # Check if an earlier opposing liquidity barrier already meets min_rr
    for lv in valid_pools:
        rew = abs(lv.price - entry_price)
        rr = rew / risk
        net_rr = max(0.0, (rew - spread_cost) / risk)
        if rr >= min_rr:
            return TargetSelection(
                selected_price=lv.price,
                source=lv.level_class,
                reward_to_risk=round(rr, 3),
                net_reward_to_risk=round(net_rr, 3),
                fib_projection=fib_projection,
                earlier_liquidity_barrier=lv,
                reason=f"Selected untapped liquidity pool {lv.level_class}@{lv.price:.5f} (RR={rr:.2f})",
            )

    # Otherwise check Fibonacci -2.0 extension if provided
    if fib_projection is not None:
        fp = fib_projection.primary_target
        if (is_buy and fp > entry_price) or ((not is_buy) and fp < entry_price):
            rew = abs(fp - entry_price)
            rr = rew / risk
            net_rr = max(0.0, (rew - spread_cost) / risk)
            if rr >= min_rr:
                return TargetSelection(
                    selected_price=fp,
                    source="FIB_EXT_-2.0",
                    reward_to_risk=round(rr, 3),
                    net_reward_to_risk=round(net_rr, 3),
                    fib_projection=fib_projection,
                    earlier_liquidity_barrier=valid_pools[0] if valid_pools else None,
                    reason=f"Selected Fibonacci -2.0 extension @{fp:.5f} (RR={rr:.2f})",
                )

    return None


# ============================================================================
# PHASES 3-5, 9-10: SCORING, LIFECYCLE, REJECTION, SHADOW MODE & TRACKER
# ============================================================================

@dataclass(frozen=True)
class ICTSetupEvaluation:
    setup_id: str
    model_name: str            # LIQUIDITY_SWEEP_MSS | UNICORN | OTE | FVG_RETEST | BREAKER_BLOCK | MITIGATION_BLOCK | PROPULSION_BLOCK | REJECTION_BLOCK
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    direction: OrderType
    lifecycle_stage: SetupLifecycleStage
    decision: str              # "SHADOW_APPROVED" | "DEMO_CANDIDATE" | "REJECTED" | "MONITORING"
    shadow_only: bool
    score: float
    score_breakdown: Dict[str, float]
    entry_price: float
    stop_loss: float
    take_profit: float
    reward_to_risk: float
    liquidity_level: Optional[str] = None
    sweep_state: Optional[str] = None
    displacement_score: float = 0.0
    structure_status: Optional[str] = None
    fvg_bounds: Optional[Tuple[float, float]] = None
    zone_type: Optional[str] = None
    zone_bounds: Optional[Tuple[float, float]] = None
    ote_sweet_spot: Optional[float] = None
    quarterly_quadrant: Optional[str] = None
    rejection_codes: List[str] = field(default_factory=list)
    explanation: str = ""

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "setup_id": self.setup_id,
            "model": self.model_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "lifecycle_stage": self.lifecycle_stage.value,
            "decision": self.decision,
            "shadow_only": self.shadow_only,
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "entry": self.entry_price,
            "sl": self.stop_loss,
            "tp": self.take_profit,
            "rr": self.reward_to_risk,
            "liquidity_level": self.liquidity_level,
            "sweep_state": self.sweep_state,
            "displacement_score": self.displacement_score,
            "structure_status": self.structure_status,
            "fvg_bounds": self.fvg_bounds,
            "zone_type": self.zone_type,
            "zone_bounds": self.zone_bounds,
            "ote_sweet_spot": self.ote_sweet_spot,
            "quarterly_quadrant": self.quarterly_quadrant,
            "rejection_codes": list(self.rejection_codes),
            "explanation": self.explanation,
        }


class ICTModelPerformanceTracker:
    """
    Tracks performance separately per setup model, per session, and per volatility regime.
    """

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def record_outcome(
        self,
        model_name: str,
        pnl_r: float,
        session: str = "UNKNOWN",
        volatility_regime: str = "NORMAL",
        entry_precision_atr: float = 0.0,
        mitigated: bool = True,
    ) -> None:
        self._records.append({
            "model": model_name,
            "pnl_r": float(pnl_r),
            "session": session,
            "regime": volatility_regime,
            "entry_precision_atr": float(entry_precision_atr),
            "mitigated": bool(mitigated),
        })

    @staticmethod
    def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(rows)
        if n == 0:
            return {"trades": 0, "win_rate": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0}
        wins = [r["pnl_r"] for r in rows if r["pnl_r"] > 0]
        losses = [r["pnl_r"] for r in rows if r["pnl_r"] <= 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        pf = (gross_win / gross_loss) if gross_loss > 1e-9 else (gross_win if gross_win > 0 else 0.0)
        return {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / n, 4),
            "expectancy_r": round(sum(r["pnl_r"] for r in rows) / n, 4),
            "profit_factor": round(pf, 3),
            "avg_win_r": round(sum(wins) / len(wins), 3) if wins else 0.0,
            "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else 0.0,
        }

    def summary_by_model(self) -> Dict[str, Dict[str, Any]]:
        models = sorted({r["model"] for r in self._records})
        return {m: self._aggregate([r for r in self._records if r["model"] == m]) for m in models}

    def summary_by_session(self) -> Dict[str, Dict[str, Any]]:
        sessions = sorted({r["session"] for r in self._records})
        return {s: self._aggregate([r for r in self._records if r["session"] == s]) for s in sessions}

    def summary_by_regime(self) -> Dict[str, Dict[str, Any]]:
        regimes = sorted({r["regime"] for r in self._records})
        return {rg: self._aggregate([r for r in self._records if r["regime"] == rg]) for rg in regimes}


class ICTIntelligenceEngine:
    """
    Unified ICT/SMC Intelligence Orchestrator (Videos 0010–0019).
    Runs in SHADOW MODE by default (`mode="SHADOW"`), prevents duplicate signals,
    enforces closed-candle anti-repainting, explains every score and rejection,
    and never weakens risk limits or scales lot sizes by confidence score.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = validate_ict_intelligence_config(config)
        self.htf_analyzer = HTFLiquidityAnalyzer(self.cfg)
        self.performance_tracker = ICTModelPerformanceTracker()
        self._seen_signal_keys: set[str] = set()
        self.evaluation_log: List[Dict[str, Any]] = []

    def reset_dedup_cache(self) -> None:
        self._seen_signal_keys.clear()

    def _compute_score(
        self,
        *,
        htf_aligned: bool,
        quarterly_aligned: bool,
        sweep_state: Optional[SweepState],
        displacement_score: float,
        structure_event: Optional[MarketStructureEvent],
        has_fvg: bool,
        zone_type: Optional[InstitutionalZoneType],
        is_unicorn: bool,
        has_ote_or_ce: bool,
        rr: float,
        spread_ok: bool,
        regime_ok: bool,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Normalized explainable score (0..100) with explicit anti-double-counting:
        MSS and BOS from the same structural break share ONE `structure_break` budget.
        """
        w = self.cfg["scoring_weights"]
        bd: Dict[str, float] = {}

        htf_frac = (0.65 if htf_aligned else 0.20) + (0.35 if quarterly_aligned else 0.0)
        bd["htf_context"] = round(float(w["htf_context"]) * min(1.0, htf_frac), 2)

        if sweep_state == SweepState.CONFIRMED_SWEEP:
            bd["sweep_quality"] = round(float(w["sweep_quality"]), 2)
        elif sweep_state == SweepState.POTENTIAL_SWEEP:
            bd["sweep_quality"] = round(float(w["sweep_quality"]) * 0.55, 2)
        else:
            bd["sweep_quality"] = 0.0

        bd["displacement"] = round(float(w["displacement"]) * max(0.0, min(1.0, displacement_score / 100.0)), 2)

        # Anti-double-counting: single structure_break budget for MSS or BOS
        if structure_event and structure_event.is_valid_break:
            mult = 1.0 if structure_event.kind == StructureEventKind.DIRECTIONAL_TRANSITION else 0.65
            bd["structure_break"] = round(float(w["structure_break"]) * mult, 2)
        else:
            bd["structure_break"] = 0.0

        bd["fvg_quality"] = round(float(w["fvg_quality"]) if has_fvg else 0.0, 2)

        if is_unicorn:
            bd["zone_validity"] = round(float(w["zone_validity"]), 2)
        elif zone_type is not None:
            bd["zone_validity"] = round(float(w["zone_validity"]) * 0.85, 2)
        else:
            bd["zone_validity"] = 0.0

        bd["entry_precision"] = round(float(w["entry_precision"]) if has_ote_or_ce else 0.0, 2)

        min_rr = float(self.cfg["min_rr"])
        rr_frac = max(0.0, min(1.0, rr / max(min_rr * 1.5, 1.0))) if rr >= min_rr else 0.0
        bd["target_rr"] = round(float(w["target_rr"]) * rr_frac, 2)

        reg_frac = (0.5 if spread_ok else 0.0) + (0.5 if regime_ok else 0.0)
        bd["regime_execution"] = round(float(w["regime_execution"]) * reg_frac, 2)

        total = round(min(100.0, sum(bd.values())), 2)
        return total, bd

    def evaluate_market(
        self,
        symbol: str,
        timeframe: Timeframe,
        ltf_candles: Sequence[Candle],
        *,
        daily_candles: Optional[Sequence[Candle]] = None,
        weekly_candles: Optional[Sequence[Candle]] = None,
        spread_price: float = 0.0,
        volatility_regime: str = "NORMAL",
        now_utc: Optional[datetime] = None,
        pip_size: float = 0.01,
    ) -> List[ICTSetupEvaluation]:
        """
        Evaluates all enabled ICT models on the latest CLOSED candle bar.
        Returns a list of explainable `ICTSetupEvaluation` objects (including rejections
        when data is unfinished/stale or setups fail hard criteria).
        """
        if not self.cfg["enabled"] or self.cfg["mode"] == "OFF":
            return []

        shadow_only = self.cfg["mode"] != "DEMO_EXECUTE"

        # Guard 1: Empty / insufficient data
        if not ltf_candles or len(ltf_candles) < 8:
            ev = ICTSetupEvaluation(
                setup_id=f"{symbol}_DATA_CHECK",
                model_name="SYSTEM_GUARD",
                symbol=symbol, timeframe=timeframe,
                timestamp=now_utc or datetime.now(timezone.utc),
                direction=OrderType.BUY,
                lifecycle_stage=SetupLifecycleStage.INVALIDATED,
                decision="REJECTED", shadow_only=True, score=0.0, score_breakdown={},
                entry_price=0.0, stop_loss=0.0, take_profit=0.0, reward_to_risk=0.0,
                rejection_codes=[RejectionCode.STALE_OR_INCOMPLETE_DATA.value],
                explanation="Insufficient candle history (< 8 bars)",
            )
            self.evaluation_log.append(ev.to_log_dict())
            return [ev]

        # Guard 2: Unfinished latest candle check (anti-repainting)
        if not getattr(ltf_candles[-1], "complete", True):
            ev = ICTSetupEvaluation(
                setup_id=f"{symbol}_UNFINISHED_{ltf_candles[-1].time.isoformat()}",
                model_name="SYSTEM_GUARD",
                symbol=symbol, timeframe=timeframe,
                timestamp=ltf_candles[-1].time,
                direction=OrderType.BUY,
                lifecycle_stage=SetupLifecycleStage.INVALIDATED,
                decision="REJECTED", shadow_only=True, score=0.0, score_breakdown={},
                entry_price=0.0, stop_loss=0.0, take_profit=0.0, reward_to_risk=0.0,
                rejection_codes=[RejectionCode.UNFINISHED_CANDLE.value],
                explanation="Latest candle is not closed; closed candles required to prevent repainting.",
            )
            self.evaluation_log.append(ev.to_log_dict())
            return [ev]

        closed = _closed_candles(ltf_candles)
        last_bar = closed[-1]
        atr = max(compute_atr(closed, 14), 1e-6)

        # Guard 3: Stale market data check
        if now_utc is not None:
            age_sec = (now_utc - last_bar.time).total_seconds()
            if age_sec > float(self.cfg["max_data_age_seconds"]):
                ev = ICTSetupEvaluation(
                    setup_id=f"{symbol}_STALE_{last_bar.time.isoformat()}",
                    model_name="SYSTEM_GUARD",
                    symbol=symbol, timeframe=timeframe,
                    timestamp=last_bar.time, direction=OrderType.BUY,
                    lifecycle_stage=SetupLifecycleStage.INVALIDATED,
                    decision="REJECTED", shadow_only=True, score=0.0, score_breakdown={},
                    entry_price=0.0, stop_loss=0.0, take_profit=0.0, reward_to_risk=0.0,
                    rejection_codes=[RejectionCode.STALE_OR_INCOMPLETE_DATA.value],
                    explanation=f"Market data stale ({age_sec:.0f}s > {self.cfg['max_data_age_seconds']}s)",
                )
                self.evaluation_log.append(ev.to_log_dict())
                return [ev]

        spread_ok = (spread_price / atr) <= float(self.cfg["max_spread_atr_ratio"])
        regime_ok = volatility_regime.upper() not in ("EXTREME_CHAOS", "NO_TRADE")
        q_ctx = self.htf_analyzer.build_quarterly_context(symbol, daily_candles or [], current_price=last_bar.close)
        liq_levels = self.htf_analyzer.collect_liquidity_levels(
            symbol, closed, ltf_timeframe=timeframe,
            daily_candles=daily_candles, weekly_candles=weekly_candles,
        )

        evaluations: List[ICTSetupEvaluation] = []

        def _finalize(
            model_name: str,
            direction: OrderType,
            entry: float,
            sl: float,
            anchor_origin: float,
            anchor_extreme: float,
            *,
            sweep: Optional[LiquiditySweepEvent] = None,
            disp_score: float = 0.0,
            struct_ev: Optional[MarketStructureEvent] = None,
            fvg: Optional[FairValueGap] = None,
            zone: Optional[InstitutionalZone] = None,
            is_unicorn: bool = False,
            ote_sweet: Optional[float] = None,
            extra_rejections: Optional[List[str]] = None,
            base_note: str = "",
        ) -> Optional[ICTSetupEvaluation]:
            dedup_key = f"{symbol}:{timeframe.value}:{model_name}:{direction.value}:{last_bar.time.isoformat()}"
            if dedup_key in self._seen_signal_keys:
                return None

            rejections: List[str] = list(extra_rejections or [])
            if not spread_ok or not regime_ok:
                rejections.append(RejectionCode.UNACCEPTABLE_SPREAD_OR_VOLATILITY.value)

            # Entry distance guard
            if abs(last_bar.close - entry) > float(self.cfg["max_entry_distance_atr"]) * atr * 4.0:
                rejections.append(RejectionCode.ENTRY_TOO_FAR_FROM_ZONE.value)

            if struct_ev and struct_ev.kind == StructureEventKind.WICK_ONLY_PENETRATION:
                rejections.append(RejectionCode.WICK_ONLY_BREAK.value)
            if zone and zone.invalidated:
                rejections.append(RejectionCode.OB_INVALIDATED.value)

            fib_ext = compute_fib_extensions(
                direction, anchor_origin, anchor_extreme,
                levels=self.cfg["fib_extension_levels"],
                primary_level=float(self.cfg["primary_fib_extension"]),
            )
            tgt = select_liquidity_target(
                direction, entry, sl, liq_levels,
                fib_projection=fib_ext, spread_cost=spread_price,
                min_rr=float(self.cfg["min_rr"]),
            )
            if tgt is None:
                rejections.append(RejectionCode.INSUFFICIENT_RR.value)
                tp_px = fib_ext.primary_target
                rr = abs(tp_px - entry) / max(abs(entry - sl), 1e-9)
                tgt_label = "NONE"
            else:
                tp_px = tgt.selected_price
                rr = tgt.reward_to_risk
                tgt_label = tgt.source
                # Check if price already reached intended liquidity target
                already_hit = (last_bar.high >= tp_px) if direction == OrderType.BUY else (last_bar.low <= tp_px)
                if already_hit:
                    rejections.append(RejectionCode.TARGET_ALREADY_REACHED.value)

            is_buy = direction == OrderType.BUY
            htf_aligned = True
            q_aligned = False
            if q_ctx is not None:
                q_aligned = (
                    (is_buy and q_ctx.quadrant in ("DISCOUNT", "DEEP_DISCOUNT"))
                    or ((not is_buy) and q_ctx.quadrant in ("PREMIUM", "DEEP_PREMIUM"))
                )
                htf_aligned = (
                    (is_buy and q_ctx.contextual_bias in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH, TrendBias.RANGING))
                    or ((not is_buy) and q_ctx.contextual_bias in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH, TrendBias.RANGING))
                )

            score, breakdown = self._compute_score(
                htf_aligned=htf_aligned,
                quarterly_aligned=q_aligned,
                sweep_state=sweep.state if sweep else None,
                displacement_score=disp_score,
                structure_event=struct_ev,
                has_fvg=fvg is not None,
                zone_type=zone.zone_type if zone else None,
                is_unicorn=is_unicorn,
                has_ote_or_ce=(ote_sweet is not None or fvg is not None),
                rr=rr,
                spread_ok=spread_ok,
                regime_ok=regime_ok,
            )

            if rejections:
                stage = SetupLifecycleStage.INVALIDATED
                decision = "REJECTED"
            elif score >= float(self.cfg["high_quality_score_threshold"]):
                stage = SetupLifecycleStage.HIGH_QUALITY
                decision = "SHADOW_APPROVED" if shadow_only else "DEMO_CANDIDATE"
            elif score >= float(self.cfg["confirmed_score_threshold"]):
                stage = SetupLifecycleStage.CONFIRMED
                decision = "SHADOW_APPROVED" if shadow_only else "DEMO_CANDIDATE"
            elif disp_score > 0 or (struct_ev and struct_ev.is_valid_break):
                stage = SetupLifecycleStage.DEVELOPING
                decision = "MONITORING"
            else:
                stage = SetupLifecycleStage.POTENTIAL
                decision = "MONITORING"

            self._seen_signal_keys.add(dedup_key)
            ev = ICTSetupEvaluation(
                setup_id=f"{model_name}_{symbol}_{direction.value}_{last_bar.time.strftime('%Y%m%d%H%M')}",
                model_name=model_name,
                symbol=symbol, timeframe=timeframe, timestamp=last_bar.time,
                direction=direction, lifecycle_stage=stage, decision=decision,
                shadow_only=shadow_only, score=score, score_breakdown=breakdown,
                entry_price=round(entry, 5), stop_loss=round(sl, 5),
                take_profit=round(tp_px, 5), reward_to_risk=round(rr, 3),
                liquidity_level=tgt_label,
                sweep_state=sweep.state.value if sweep else None,
                displacement_score=round(disp_score, 2),
                structure_status=struct_ev.kind.value if struct_ev else None,
                fvg_bounds=(round(fvg.bottom, 5), round(fvg.top, 5)) if fvg else None,
                zone_type=zone.zone_type.value if zone else None,
                zone_bounds=(round(zone.low, 5), round(zone.high, 5)) if zone else None,
                ote_sweet_spot=round(ote_sweet, 5) if ote_sweet is not None else None,
                quarterly_quadrant=q_ctx.quadrant if q_ctx else None,
                rejection_codes=rejections,
                explanation=base_note or f"{model_name} {direction.value} stage={stage.value} score={score:.1f}",
            )
            self.evaluation_log.append(ev.to_log_dict())
            return ev

        models_cfg = self.cfg["models"]
        buf = float(self.cfg["stop_buffer_atr"]) * atr

        # 1. ICT UNICORN MODEL (0011)
        if models_cfg.get("UNICORN", {}).get("enabled", True):
            uni = detect_unicorn_setup(symbol, timeframe, closed, config=self.cfg, pip_size=pip_size)
            if uni is not None:
                st = analyze_market_structure_transition(symbol, timeframe, closed, uni.direction, after_index=uni.sweep.pierce_index, config=self.cfg)
                ev = _finalize(
                    "UNICORN", uni.direction, uni.entry_price, uni.invalidation_stop,
                    uni.sweep.sweep_extreme, uni.fvg.bottom if uni.direction == OrderType.SELL else uni.fvg.top,
                    sweep=uni.sweep,
                    disp_score=uni.sweep.displacement.quality_score if uni.sweep.displacement else 70.0,
                    struct_ev=st, fvg=uni.fvg, zone=uni.breaker, is_unicorn=True, base_note=uni.reason,
                )
                if ev:
                    evaluations.append(ev)

        # 2. OTE MODEL (0014)
        if models_cfg.get("OTE", {}).get("enabled", True):
            ote = detect_ote_setup(symbol, timeframe, closed, config=self.cfg, pip_size=pip_size)
            if ote is not None:
                st = analyze_market_structure_transition(symbol, timeframe, closed, ote.direction, after_index=ote.anchored_ote.origin_index, config=self.cfg)
                ev = _finalize(
                    "OTE", ote.direction, ote.entry_price, ote.invalidation_stop,
                    ote.anchored_ote.anchor_origin, ote.anchored_ote.anchor_extreme,
                    disp_score=ote.displacement.quality_score, struct_ev=st,
                    fvg=ote.anchored_ote.overlapping_fvg, ote_sweet=ote.anchored_ote.ote_sweet_spot,
                    base_note=ote.reason,
                )
                if ev:
                    evaluations.append(ev)

        # 3. PROPULSION BLOCK (0016)
        if models_cfg.get("PROPULSION_BLOCK", {}).get("enabled", True):
            props = detect_propulsion_blocks(symbol, timeframe, closed, config=self.cfg)
            if props:
                pr = props[-1]
                sl = (pr.low - buf) if pr.direction == OrderType.BUY else (pr.high + buf)
                ev = _finalize(
                    "PROPULSION_BLOCK", pr.direction, pr.midpoint, sl,
                    pr.low if pr.direction == OrderType.BUY else pr.high,
                    max(c.high for c in closed[pr.formation_index:]) if pr.direction == OrderType.BUY else min(c.low for c in closed[pr.formation_index:]),
                    disp_score=70.0, zone=pr, base_note=pr.reason,
                )
                if ev:
                    evaluations.append(ev)

        # 4. REJECTION BLOCK (0017)
        if models_cfg.get("REJECTION_BLOCK", {}).get("enabled", True):
            rejs = [r for r in detect_rejection_blocks(symbol, timeframe, closed, config=self.cfg) if not r.invalidated]
            if rejs:
                rj = rejs[-1]
                sl = (rj.high + buf) if rj.direction == OrderType.SELL else (rj.low - buf)
                ev = _finalize(
                    "REJECTION_BLOCK", rj.direction, rj.midpoint, sl,
                    rj.high if rj.direction == OrderType.SELL else rj.low,
                    rj.low if rj.direction == OrderType.SELL else rj.high,
                    disp_score=60.0, zone=rj, base_note=rj.reason,
                )
                if ev:
                    evaluations.append(ev)

        # 5. BREAKER & MITIGATION BLOCKS (0018, 0019)
        breakers, mitigations, _ = detect_breaker_and_mitigation_blocks(symbol, timeframe, closed, config=self.cfg)
        if models_cfg.get("BREAKER_BLOCK", {}).get("enabled", True) and breakers:
            br = breakers[-1]
            sl = (br.high + buf) if br.direction == OrderType.SELL else (br.low - buf)
            ev = _finalize(
                "BREAKER_BLOCK", br.direction, br.midpoint, sl,
                br.high if br.direction == OrderType.SELL else br.low,
                closed[-1].low if br.direction == OrderType.SELL else closed[-1].high,
                disp_score=65.0, zone=br, base_note=br.reason,
            )
            if ev:
                evaluations.append(ev)

        if models_cfg.get("MITIGATION_BLOCK", {}).get("enabled", True) and mitigations:
            mt = mitigations[-1]
            sl = (mt.high + buf) if mt.direction == OrderType.SELL else (mt.low - buf)
            ev = _finalize(
                "MITIGATION_BLOCK", mt.direction, mt.midpoint, sl,
                mt.high if mt.direction == OrderType.SELL else mt.low,
                closed[-1].low if mt.direction == OrderType.SELL else closed[-1].high,
                disp_score=60.0, zone=mt, base_note=mt.reason,
            )
            if ev:
                evaluations.append(ev)

        return evaluations
