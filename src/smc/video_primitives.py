"""
Core SMC Primitives (P1-P11) extracted from 16 educational forex video strategies.

Epistemic & provenance notice:
- Numeric thresholds (ATR multiples, overlap ratios, lookbacks) are engineering starting
  defaults for replay calibration, not validated edges.
- P2's third confirmation slot defaults to HTF-bias alignment because the source clip
  (chart__tactix-20261113-0001) ends after announcing the second confirmation; this slot
  is explicitly flagged as *not from the video*.
- Reuses existing FvgObEngine, LiquidityEngine, InverseDirectionCoordinator, and contracts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.contracts import (
    Candle,
    FairValueGap,
    LiquidityZone,
    OrderBlock,
    OrderType,
    Timeframe,
)
from src.smc.fvg_ob import FvgObEngine
from src.strategy.inverse_coordination import CorrelationRegime, InverseDirectionCoordinator


# ============================================================================
# SHARED ATR & SWING HELPERS
# ============================================================================

def compute_atr(candles: Sequence[Candle], period: int = 14) -> float:
    """Computes simple Average True Range over up to `period` bars."""
    return FvgObEngine.compute_atr(list(candles), period=period)


def find_swings(
    candles: Sequence[Candle],
    left: int = 2,
    right: int = 2,
) -> Tuple[List[Tuple[int, Candle]], List[Tuple[int, Candle]]]:
    """Non-repainting swing high / swing low indices with configurable fractal lookback."""
    n = len(candles)
    highs: List[Tuple[int, Candle]] = []
    lows: List[Tuple[int, Candle]] = []
    if n < left + right + 1:
        return highs, lows
    for i in range(left, n - right):
        c = candles[i]
        if all(c.high > candles[j].high for j in range(i - left, i)) and all(
            c.high >= candles[j].high for j in range(i + 1, i + right + 1)
        ):
            highs.append((i, c))
        if all(c.low < candles[j].low for j in range(i - left, i)) and all(
            c.low <= candles[j].low for j in range(i + 1, i + right + 1)
        ):
            lows.append((i, c))
    return highs, lows


# ============================================================================
# P1: EQUAL HIGHS / EQUAL LOWS AS STOP CLUSTERS
# ============================================================================

@dataclass(frozen=True)
class StopClusterPool:
    id: str
    symbol: str
    timeframe: Timeframe
    level_type: str  # "EQH" | "EQL" | "BSL" | "SSL" | "PD_MID"
    price: float
    touch_count: int
    formation_index: int
    formation_time: datetime
    status: str  # "untapped" | "taken"
    taken_index: Optional[int] = None

    def to_liquidity_zone(self, tol: float = 0.0) -> LiquidityZone:
        return LiquidityZone(
            id=self.id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            level_type=self.level_type,
            price=self.price,
            high=self.price + tol if self.level_type in ("EQH", "BSL") else self.price,
            low=self.price - tol if self.level_type in ("EQL", "SSL") else self.price,
            formation_time=self.formation_time,
            swept=(self.status == "taken"),
        )


def detect_equal_clusters(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    atr_tolerance_mult: float = 0.10,
    swing_left: int = 2,
    swing_right: int = 2,
    include_single_swings: bool = True,
) -> List[StopClusterPool]:
    """
    P1 [VIDEO: keepssy_fx-20261126-0002, keepssy_fx-20261126-0003]:
    Detects 2+ swing highs/lows within `atr_tolerance_mult * ATR(14)` as EQH/EQL stop clusters.
    Marks each pool as `untapped` or `taken` based on subsequent candles.
    """
    n = len(candles)
    if n < swing_left + swing_right + 1:
        return []
    atr = max(compute_atr(candles, 14), 1e-9)
    tol = atr_tolerance_mult * atr
    swing_highs, swing_lows = find_swings(candles, left=swing_left, right=swing_right)
    pools: List[StopClusterPool] = []

    def _status_after(level_type: str, price: float, start_idx: int) -> Tuple[str, Optional[int]]:
        for k in range(start_idx + 1, n):
            if level_type in ("EQH", "BSL") and candles[k].high > price:
                return "taken", k
            if level_type in ("EQL", "SSL") and candles[k].low < price:
                return "taken", k
        return "untapped", None

    # Cluster swing highs into EQH
    used_h: set[int] = set()
    for i in range(len(swing_highs)):
        if i in used_h:
            continue
        cluster = [swing_highs[i]]
        for j in range(i + 1, len(swing_highs)):
            if j in used_h:
                continue
            if abs(swing_highs[j][1].high - swing_highs[i][1].high) <= tol:
                cluster.append(swing_highs[j])
                used_h.add(j)
        if len(cluster) >= 2:
            used_h.add(i)
            last_idx, last_c = cluster[-1]
            lvl_price = max(c.high for _, c in cluster)
            st, taken_idx = _status_after("EQH", lvl_price, last_idx)
            pools.append(
                StopClusterPool(
                    id=f"{symbol}_{timeframe.value}_EQH_{last_idx}",
                    symbol=symbol,
                    timeframe=timeframe,
                    level_type="EQH",
                    price=lvl_price,
                    touch_count=len(cluster),
                    formation_index=last_idx,
                    formation_time=last_c.time,
                    status=st,
                    taken_index=taken_idx,
                )
            )

    # Cluster swing lows into EQL
    used_l: set[int] = set()
    for i in range(len(swing_lows)):
        if i in used_l:
            continue
        cluster = [swing_lows[i]]
        for j in range(i + 1, len(swing_lows)):
            if j in used_l:
                continue
            if abs(swing_lows[j][1].low - swing_lows[i][1].low) <= tol:
                cluster.append(swing_lows[j])
                used_l.add(j)
        if len(cluster) >= 2:
            used_l.add(i)
            last_idx, last_c = cluster[-1]
            lvl_price = min(c.low for _, c in cluster)
            st, taken_idx = _status_after("EQL", lvl_price, last_idx)
            pools.append(
                StopClusterPool(
                    id=f"{symbol}_{timeframe.value}_EQL_{last_idx}",
                    symbol=symbol,
                    timeframe=timeframe,
                    level_type="EQL",
                    price=lvl_price,
                    touch_count=len(cluster),
                    formation_index=last_idx,
                    formation_time=last_c.time,
                    status=st,
                    taken_index=taken_idx,
                )
            )

    if include_single_swings:
        for idx, c in swing_highs:
            st, taken_idx = _status_after("BSL", c.high, idx)
            pools.append(
                StopClusterPool(
                    id=f"{symbol}_{timeframe.value}_BSL_{idx}",
                    symbol=symbol,
                    timeframe=timeframe,
                    level_type="BSL",
                    price=c.high,
                    touch_count=1,
                    formation_index=idx,
                    formation_time=c.time,
                    status=st,
                    taken_index=taken_idx,
                )
            )
        for idx, c in swing_lows:
            st, taken_idx = _status_after("SSL", c.low, idx)
            pools.append(
                StopClusterPool(
                    id=f"{symbol}_{timeframe.value}_SSL_{idx}",
                    symbol=symbol,
                    timeframe=timeframe,
                    level_type="SSL",
                    price=c.low,
                    touch_count=1,
                    formation_index=idx,
                    formation_time=c.time,
                    status=st,
                    taken_index=taken_idx,
                )
            )

    return pools


# ============================================================================
# P2: SWEEP VS BREAKOUT CLASSIFIER
# ============================================================================

@dataclass(frozen=True)
class SweepBreakoutClassification:
    kind: str  # "SWEEP" | "BREAKOUT" | "UNDECIDED"
    score: float  # 0-100 confidence in classified kind
    evidence: Dict[str, Any] = field(default_factory=dict)


def classify_sweep_vs_breakout(
    candles: Sequence[Candle],
    level_price: float,
    side: str,  # "HIGH" (BSL/EQH) or "LOW" (SSL/EQL)
    event_index: int,
    approach_bars: int = 5,
    htf_bias_supports_reversal: Optional[bool] = None,
    use_third_confirmation_slot: bool = True,
) -> SweepBreakoutClassification:
    """
    P2 [VIDEO: chart__tactix-20261113-0001]:
    Classifies a trade beyond `level_price` as SWEEP, BREAKOUT, or UNDECIDED using:
      1. Candle formation after taking liquidity (rejection wick + close back inside vs
         displacement body closing beyond level).
      2. Approach quality (last N bars ATR-normalised body/range, overlap ratio, slope).
      3. Configurable 3rd confirmation slot (default = HTF-bias alignment; explicitly flagged
         as NOT FROM THE VIDEO because the source clip ends after the 2nd confirmation).
    """
    n = len(candles)
    if n == 0 or event_index < 0 or event_index >= n:
        return SweepBreakoutClassification(kind="UNDECIDED", score=0.0, evidence={"error": "invalid_index"})

    atr = max(compute_atr(candles[: event_index + 1], 14), 1e-9)
    ev_c = candles[event_index]
    next_c = candles[event_index + 1] if (event_index + 1) < n else None
    side_u = side.upper()

    # 1. Candle formation reaction (sweep_pts vs breakout_pts, max ~55 pts)
    sweep_pts = 0.0
    breakout_pts = 0.0
    if side_u == "HIGH":
        pierced = ev_c.high > level_price
        closed_inside = ev_c.close < level_price
        next_closed_inside = next_c is not None and next_c.close < level_price
        next_closed_beyond = next_c is not None and next_c.close > level_price
        wick_ratio = (ev_c.upper_wick / ev_c.range) if ev_c.range > 0 else 0.0
        body_beyond = max(0.0, ev_c.close - level_price) / atr
    else:
        pierced = ev_c.low < level_price
        closed_inside = ev_c.close > level_price
        next_closed_inside = next_c is not None and next_c.close > level_price
        next_closed_beyond = next_c is not None and next_c.close < level_price
        wick_ratio = (ev_c.lower_wick / ev_c.range) if ev_c.range > 0 else 0.0
        body_beyond = max(0.0, level_price - ev_c.close) / atr

    if not pierced:
        return SweepBreakoutClassification(
            kind="UNDECIDED",
            score=0.0,
            evidence={"pierced": False},
        )

    if closed_inside:
        sweep_pts += 40.0 + min(15.0, wick_ratio * 25.0)
    elif next_closed_inside:
        sweep_pts += 32.0
    else:
        # Closed beyond the level with body
        body_ratio = (ev_c.body / ev_c.range) if ev_c.range > 0 else 0.0
        breakout_pts += 35.0 + min(15.0, body_beyond * 20.0) + (10.0 if body_ratio >= 0.55 else 0.0)
        if next_closed_beyond:
            breakout_pts += 15.0

    # 2. Approach analysis over last `approach_bars` preceding event_index (max ~35 pts)
    start_idx = max(0, event_index - approach_bars)
    app_slice = list(candles[start_idx:event_index])
    overlap_ratio = 0.0
    avg_body_atr = 0.0
    slope_atr = 0.0
    if len(app_slice) >= 2:
        overlaps = 0
        for k in range(1, len(app_slice)):
            prev_b, cur_b = app_slice[k - 1], app_slice[k]
            ov = min(prev_b.high, cur_b.high) - max(prev_b.low, cur_b.low)
            if ov > 0:
                overlaps += 1
        overlap_ratio = overlaps / (len(app_slice) - 1)
        avg_body_atr = sum(c.body for c in app_slice) / (len(app_slice) * atr)
        slope_atr = abs(app_slice[-1].close - app_slice[0].open) / (len(app_slice) * atr)

        # Corrective/overlapping slow approach -> favors sweep
        if overlap_ratio >= 0.55 and avg_body_atr < 0.75:
            sweep_pts += 25.0
        elif overlap_ratio >= 0.40:
            sweep_pts += 12.0

        # Impulsive, low-overlap, steep approach -> favors breakout
        if avg_body_atr >= 0.85 and overlap_ratio < 0.45:
            breakout_pts += 25.0
        elif slope_atr >= 0.70:
            breakout_pts += 12.0

    # 3. Configurable 3rd confirmation slot (NOT from video; default = HTF bias)
    third_slot_note = "disabled"
    if use_third_confirmation_slot and htf_bias_supports_reversal is not None:
        third_slot_note = "htf_bias_alignment (not_from_video)"
        if htf_bias_supports_reversal:
            sweep_pts += 10.0
        else:
            breakout_pts += 10.0

    diff = sweep_pts - breakout_pts
    if diff >= 15.0:
        kind = "SWEEP"
        score = min(100.0, round(sweep_pts, 1))
    elif diff <= -15.0:
        kind = "BREAKOUT"
        score = min(100.0, round(breakout_pts, 1))
    else:
        kind = "UNDECIDED"
        score = min(100.0, round(max(sweep_pts, breakout_pts) * 0.5, 1))

    return SweepBreakoutClassification(
        kind=kind,
        score=score,
        evidence={
            "sweep_pts": round(sweep_pts, 2),
            "breakout_pts": round(breakout_pts, 2),
            "closed_inside": closed_inside,
            "wick_ratio": round(wick_ratio, 3),
            "overlap_ratio": round(overlap_ratio, 3),
            "avg_body_atr": round(avg_body_atr, 3),
            "slope_atr": round(slope_atr, 3),
            "third_slot": third_slot_note,
        },
    )


# ============================================================================
# P3: CONFIRMED SWEEP
# ============================================================================

@dataclass(frozen=True)
class ConfirmedSweep:
    level_price: float
    level_type: str  # "BSL" | "EQH" | "SSL" | "EQL" | session level
    direction: OrderType  # BUY after low sweep, SELL after high sweep
    pierce_index: int
    reclaim_index: int
    sweep_extreme: float
    pierce_distance: float
    pierce_time: datetime
    reclaim_time: datetime
    classification: SweepBreakoutClassification


def detect_confirmed_sweep(
    candles: Sequence[Candle],
    level_price: float,
    level_type: str,
    start_index: int = 0,
    min_pierce_atr: float = 0.05,
    max_bars_to_reclaim: int = 3,
    htf_bias_supports_reversal: Optional[bool] = None,
) -> Optional[ConfirmedSweep]:
    """
    P3 [VIDEO: keepssy_fx-20261126-0002]:
    A sweep counts only when a wick pierces the pool by >= `min_pierce_atr * ATR`
    and a candle CLOSES back beyond the level within `max_bars_to_reclaim` bars,
    and P2 does not classify the event as BREAKOUT.
    """
    n = len(candles)
    if n < 3 or start_index >= n:
        return None
    is_high_pool = level_type.upper() in ("BSL", "EQH", "HIGH", "ASIA_HIGH", "LONDON_HIGH", "PDH", "MORNING_HIGH")
    side = "HIGH" if is_high_pool else "LOW"
    direction = OrderType.SELL if is_high_pool else OrderType.BUY

    for i in range(max(0, start_index), n):
        c = candles[i]
        atr = max(compute_atr(candles[: i + 1], 14), 1e-9)
        min_pierce = min_pierce_atr * atr
        pierce_dist = (c.high - level_price) if is_high_pool else (level_price - c.low)
        if pierce_dist < min_pierce:
            continue

        # Search up to max_bars_to_reclaim (inclusive of bar i) for close back beyond level
        end_j = min(n, i + max(1, max_bars_to_reclaim))
        sweep_extreme = c.high if is_high_pool else c.low
        for j in range(i, end_j):
            cj = candles[j]
            if is_high_pool:
                sweep_extreme = max(sweep_extreme, cj.high)
                reclaimed = cj.close < level_price
            else:
                sweep_extreme = min(sweep_extreme, cj.low)
                reclaimed = cj.close > level_price
            if reclaimed:
                cls_res = classify_sweep_vs_breakout(
                    candles=candles,
                    level_price=level_price,
                    side=side,
                    event_index=i,
                    htf_bias_supports_reversal=htf_bias_supports_reversal,
                )
                if cls_res.kind == "BREAKOUT":
                    return None
                return ConfirmedSweep(
                    level_price=level_price,
                    level_type=level_type,
                    direction=direction,
                    pierce_index=i,
                    reclaim_index=j,
                    sweep_extreme=sweep_extreme,
                    pierce_distance=pierce_dist,
                    pierce_time=c.time,
                    reclaim_time=cj.time,
                    classification=cls_res,
                )
    return None


# ============================================================================
# P4 & P5: MSS / BOS WITH DISPLACEMENT + FVG WITH CE (50% MIDPOINT)
# ============================================================================

@dataclass(frozen=True)
class MssDisplacementResult:
    direction: OrderType
    break_index: int
    break_time: datetime
    broken_swing_price: float
    displacement_body_ratio: float
    displacement_atr_ratio: float
    fvg: FairValueGap
    ce_price: float


def detect_fvgs_with_ce(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    fvg_min_atr: float = 0.15,
    pip_size: float = 0.01,
) -> List[FairValueGap]:
    """P5 [VIDEO: all keepssy]: Standard 3-candle FVG with CE (midpoint) & configurable min ATR."""
    engine = FvgObEngine(min_fvg_pips=0.0, pip_size=pip_size, fvg_min_atr=fvg_min_atr)
    return engine.detect_fvgs(symbol, timeframe, list(candles))


def detect_mss_with_displacement(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    after_index: int,
    direction: OrderType,
    fvg_min_atr: float = 0.15,
    min_body_avg_mult: float = 1.0,
    min_body_atr_mult: float = 0.8,
    pip_size: float = 0.01,
) -> Optional[MssDisplacementResult]:
    """
    P4 [VIDEO: keepssy_fx-20261126-0002, 0003, 0006]:
    After a confirmed sweep (`after_index`), finds a candle CLOSING beyond the last opposing
    swing with displacement (`body >= 1.0 * avg_body` OR `body >= 0.8 * ATR`) that leaves an FVG.
    """
    n = len(candles)
    if after_index < 2 or after_index >= n - 1:
        return None

    # Find last opposing swing at or before after_index
    prior_slice = candles[max(0, after_index - 15): after_index + 1]
    if not prior_slice:
        return None
    if direction == OrderType.BUY:
        swing_highs, _ = find_swings(prior_slice, left=1, right=1)
        broken_level = swing_highs[-1][1].high if swing_highs else max(c.high for c in prior_slice[:-1] or prior_slice)
    else:
        _, swing_lows = find_swings(prior_slice, left=1, right=1)
        broken_level = swing_lows[-1][1].low if swing_lows else min(c.low for c in prior_slice[:-1] or prior_slice)

    fvgs = detect_fvgs_with_ce(symbol, timeframe, candles, fvg_min_atr=fvg_min_atr, pip_size=pip_size)
    matching_fvgs = [
        f for f in fvgs
        if not f.is_inverse
        and f.direction == direction
        and f.formation_time >= candles[after_index].time
    ]
    if not matching_fvgs:
        return None

    for i in range(after_index, n):
        c = candles[i]
        broke = (c.close > broken_level) if direction == OrderType.BUY else (c.close < broken_level)
        if not broke:
            continue

        lookback = candles[max(0, i - 14): i]
        avg_body = (sum(x.body for x in lookback) / len(lookback)) if lookback else max(c.body, 1e-9)
        atr = max(compute_atr(candles[: i + 1], 14), 1e-9)
        body_avg_ratio = c.body / max(avg_body, 1e-9)
        body_atr_ratio = c.body / atr

        if body_avg_ratio < min_body_avg_mult and body_atr_ratio < min_body_atr_mult:
            continue

        # Pair with the first matching FVG formed on or near the displacement leg
        leg_fvg = matching_fvgs[0]
        return MssDisplacementResult(
            direction=direction,
            break_index=i,
            break_time=c.time,
            broken_swing_price=broken_level,
            displacement_body_ratio=round(body_avg_ratio, 3),
            displacement_atr_ratio=round(body_atr_ratio, 3),
            fvg=leg_fvg,
            ce_price=leg_fvg.midpoint,
        )

    return None


# ============================================================================
# P6: INVERSION FVG (IFVG) + "FIRST FVG BEFORE STOP HUNT" PRIORITY
# ============================================================================

@dataclass(frozen=True)
class InvertedFvgCandidate:
    ifvg: FairValueGap
    original_fvg: FairValueGap
    inversion_index: int
    is_first_before_stop_hunt: bool
    retested: bool
    retest_index: Optional[int] = None


def detect_ifvg_candidates(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: OrderType,
    stop_hunt_index: Optional[int] = None,
    fvg_min_atr: float = 0.15,
    pip_size: float = 0.01,
) -> List[InvertedFvgCandidate]:
    """
    P6 [VIDEO: keepssy_fx-20261126-0004, keepssy_fx-20261126-0005]:
    Finds FVGs whose original direction was opposite to `direction` that price CLOSED THROUGH,
    inverting them into support (BUY) or resistance (SELL). Flags the last FVG formed before
    `stop_hunt_index` as highest-priority ("first FVG before the stop hunt").
    """
    n = len(candles)
    if n < 4:
        return []
    opposite_dir = OrderType.SELL if direction == OrderType.BUY else OrderType.BUY
    all_fvgs = detect_fvgs_with_ce(symbol, timeframe, candles, fvg_min_atr=fvg_min_atr, pip_size=pip_size)
    orig_fvgs = [f for f in all_fvgs if not f.is_inverse and f.direction == opposite_dir]
    if not orig_fvgs:
        return []

    time_to_idx = {c.time: idx for idx, c in enumerate(candles)}
    candidates: List[InvertedFvgCandidate] = []

    # Identify the closest FVG formed prior to the stop hunt (ICT's most sensitive FVG)
    first_before_id: Optional[str] = None
    if stop_hunt_index is not None and 0 <= stop_hunt_index < n:
        sh_time = candles[stop_hunt_index].time
        prior = [f for f in orig_fvgs if f.formation_time <= sh_time]
        if prior:
            first_before_id = prior[-1].id

    for orig in orig_fvgs:
        form_idx = time_to_idx.get(orig.formation_time, 0)
        inv_idx: Optional[int] = None
        for k in range(form_idx + 2, n):
            ck = candles[k]
            if direction == OrderType.BUY and ck.close > orig.top:
                inv_idx = k
                break
            if direction == OrderType.SELL and ck.close < orig.bottom:
                inv_idx = k
                break
        if inv_idx is None:
            continue

        # Check subsequent retest of the inverted zone without full re-invalidation
        retested = False
        retest_idx: Optional[int] = None
        invalidated = False
        for k in range(inv_idx + 1, n):
            ck = candles[k]
            if direction == OrderType.BUY:
                if ck.close < orig.bottom:
                    invalidated = True
                    break
                if ck.low <= orig.top and ck.close >= orig.bottom:
                    retested = True
                    retest_idx = k
                    break
            else:
                if ck.close > orig.top:
                    invalidated = True
                    break
                if ck.high >= orig.bottom and ck.close <= orig.top:
                    retested = True
                    retest_idx = k
                    break
        if invalidated:
            continue

        inv_fvg = FairValueGap(
            id=f"{orig.id}_INV_{inv_idx}",
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            top=orig.top,
            bottom=orig.bottom,
            midpoint=orig.midpoint,
            formation_time=candles[inv_idx].time,
            mitigated=retested,
            mitigation_time=candles[retest_idx].time if retest_idx is not None else None,
            is_inverse=True,
        )
        candidates.append(
            InvertedFvgCandidate(
                ifvg=inv_fvg,
                original_fvg=orig,
                inversion_index=inv_idx,
                is_first_before_stop_hunt=(orig.id == first_before_id),
                retested=retested,
                retest_index=retest_idx,
            )
        )

    candidates.sort(key=lambda x: (not x.is_first_before_stop_hunt, -x.inversion_index))
    return candidates


# ============================================================================
# P7: BREAKER BLOCK (BIDIRECTIONAL OB FLIP ON CLOSE THROUGH)
# ============================================================================

def detect_flipped_breakers(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: Optional[OrderType] = None,
    pip_size: float = 0.01,
) -> List[OrderBlock]:
    """
    P7 [VIDEO: keepssy_fx-20261126-0004]:
    An order block that price CLOSES THROUGH flips into a breaker block of the opposite bias:
    - Bullish OB (last down candle) smashed by a close below OB.low => Bearish Breaker (SELL)
    - Bearish OB (last up candle) smashed by a close above OB.high => Bullish Breaker (BUY)
    """
    n = len(candles)
    if n < 5:
        return []
    ob_engine = FvgObEngine(
        min_fvg_pips=0.0,
        pip_size=pip_size,
        ob_requires_displacement=False,
        ob_requires_bos=False,
    )
    raw_obs = ob_engine.detect_order_blocks(symbol, timeframe, list(candles))
    time_to_idx = {c.time: idx for idx, c in enumerate(candles)}
    breakers: List[OrderBlock] = []

    for ob in raw_obs:
        ob_idx = time_to_idx.get(ob.formation_time, -1)
        if ob_idx < 0:
            continue
        flipped_dir = OrderType.SELL if ob.direction == OrderType.BUY else OrderType.BUY
        if direction is not None and flipped_dir != direction:
            continue

        for k in range(ob_idx + 2, n):
            ck = candles[k]
            smashed = (
                (ob.direction == OrderType.BUY and ck.close < ob.low)
                or (ob.direction == OrderType.SELL and ck.close > ob.high)
            )
            if smashed:
                breakers.append(
                    OrderBlock(
                        id=f"{ob.id}_BREAKER_{k}",
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=flipped_dir,
                        high=ob.high,
                        low=ob.low,
                        open_price=ob.open_price,
                        close_price=ob.close_price,
                        formation_time=ck.time,
                        mitigated=False,
                        is_breaker=True,
                        strength_score=ob.strength_score,
                    )
                )
                break

    return breakers


# ============================================================================
# P8: FIBONACCI WITH BOS SWING ANCHORING + OTE (0.62 - 0.79, 0.705 SWEET SPOT)
# ============================================================================

@dataclass(frozen=True)
class AnchoredFibOte:
    direction: OrderType
    anchor_origin: float       # Fib 1.0 (swing origin that started the BOS push; stop invalidation)
    anchor_extreme: float      # Fib 0.0 (BOS impulse extreme)
    origin_index: int
    extreme_index: int
    levels: Dict[str, float]   # 0, 0.236, 0.382, 0.5, 0.618, 0.62, 0.705, 0.786, 0.79, 1.0
    ote_low: float
    ote_high: float
    ote_sweet_spot: float      # 0.705
    overlapping_fvg: Optional[FairValueGap] = None
    tap_and_close_triggered: bool = False


def compute_bos_anchored_ote(
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
    direction: OrderType,
    fvgs: Optional[Sequence[FairValueGap]] = None,
    entry_level: float = 0.705,
    pip_size: float = 0.01,
) -> Optional[AnchoredFibOte]:
    """
    P8 [VIDEO: algovistra-20261125-0001, keepssy_fx-20261126-0003]:
    Anchors Fibonacci to the LARGER swing leg that actually broke structure ("zoom out",
    never to a minor internal pullback). Computes full standard grid + OTE 0.62-0.79
    (sweet spot 0.705), detects FVG overlapping OTE, and checks tap + directional close.
    """
    n = len(candles)
    if n < 8:
        return None

    swing_highs, swing_lows = find_swings(candles, left=2, right=2)
    if not swing_highs or not swing_lows:
        return None

    # Find the largest BOS leg in trade direction ("zoom out" rule)
    best_leg: Optional[Tuple[float, int, float, int, float]] = None  # (leg_size, orig_idx, orig_px, ext_idx, ext_px)

    if direction == OrderType.BUY:
        # Look for a swing high broken by a later candle close, anchored to the lowest low before that break
        for sh_idx, sh_c in swing_highs:
            # Find first close above sh_c.high after sh_idx
            break_idx = next((k for k in range(sh_idx + 1, n) if candles[k].close > sh_c.high), None)
            if break_idx is None:
                continue
            # Origin = lowest low in [max(0, sh_idx - 20) .. break_idx]
            orig_slice = list(range(max(0, sh_idx - 20), break_idx))
            if not orig_slice:
                continue
            orig_idx = min(orig_slice, key=lambda idx: candles[idx].low)
            # Impulse extreme = highest high from break_idx onward (prior to current retrace)
            ext_slice = list(range(break_idx, n))
            ext_idx = max(ext_slice, key=lambda idx: candles[idx].high)
            orig_px = candles[orig_idx].low
            ext_px = candles[ext_idx].high
            leg_size = ext_px - orig_px
            if leg_size > 0 and (best_leg is None or leg_size > best_leg[0]):
                best_leg = (leg_size, orig_idx, orig_px, ext_idx, ext_px)
    else:
        for sl_idx, sl_c in swing_lows:
            break_idx = next((k for k in range(sl_idx + 1, n) if candles[k].close < sl_c.low), None)
            if break_idx is None:
                continue
            orig_slice = list(range(max(0, sl_idx - 20), break_idx))
            if not orig_slice:
                continue
            orig_idx = max(orig_slice, key=lambda idx: candles[idx].high)
            ext_slice = list(range(break_idx, n))
            ext_idx = min(ext_slice, key=lambda idx: candles[idx].low)
            orig_px = candles[orig_idx].high
            ext_px = candles[ext_idx].low
            leg_size = orig_px - ext_px
            if leg_size > 0 and (best_leg is None or leg_size > best_leg[0]):
                best_leg = (leg_size, orig_idx, orig_px, ext_idx, ext_px)

    if best_leg is None:
        return None

    leg_size, orig_idx, orig_px, ext_idx, ext_px = best_leg

    def _retr(ratio: float) -> float:
        if direction == OrderType.BUY:
            return round(ext_px - ratio * leg_size, 5)
        return round(ext_px + ratio * leg_size, 5)

    levels = {
        "0": _retr(0.0),
        "0.236": _retr(0.236),
        "0.382": _retr(0.382),
        "0.5": _retr(0.5),
        "0.618": _retr(0.618),
        "0.62": _retr(0.62),
        "0.705": _retr(entry_level),
        "0.786": _retr(0.786),
        "0.79": _retr(0.79),
        "1.0": _retr(1.0),
    }
    ote_a, ote_b = levels["0.62"], levels["0.79"]
    ote_low, ote_high = min(ote_a, ote_b), max(ote_a, ote_b)

    all_fvgs = list(fvgs) if fvgs is not None else detect_fvgs_with_ce(symbol, timeframe, candles, pip_size=pip_size)
    overlapping_fvg: Optional[FairValueGap] = None
    for f in reversed(all_fvgs):
        if f.is_inverse or f.direction != direction:
            continue
        if max(f.bottom, ote_low) <= min(f.top, ote_high):
            overlapping_fvg = f
            break

    # Trigger check: after extreme, price taps OTE/FVG zone and closes in trade direction
    tap_and_close = False
    zone_low = overlapping_fvg.bottom if overlapping_fvg else ote_low
    zone_high = overlapping_fvg.top if overlapping_fvg else ote_high
    for k in range(ext_idx + 1, n):
        ck = candles[k]
        tapped = ck.low <= zone_high and ck.high >= zone_low
        if tapped:
            if (direction == OrderType.BUY and ck.is_bullish) or (direction == OrderType.SELL and ck.is_bearish):
                tap_and_close = True
                break

    return AnchoredFibOte(
        direction=direction,
        anchor_origin=orig_px,
        anchor_extreme=ext_px,
        origin_index=orig_idx,
        extreme_index=ext_idx,
        levels=levels,
        ote_low=ote_low,
        ote_high=ote_high,
        ote_sweet_spot=levels["0.705"],
        overlapping_fvg=overlapping_fvg,
        tap_and_close_triggered=tap_and_close,
    )


# ============================================================================
# P9 & P10: DRAW ON LIQUIDITY & "NO DRAW, NO TRADE"
# ============================================================================

@dataclass(frozen=True)
class DrawOnLiquidity:
    price: float
    pool_type: str
    pool_id: str
    distance: float


def get_draw_on_liquidity(
    direction: OrderType,
    current_price: float,
    pools: Sequence[StopClusterPool],
    key_level_zones: Optional[Sequence[LiquidityZone]] = None,
    prefer_level_type: Optional[str] = None,
) -> Optional[DrawOnLiquidity]:
    """
    P9: Selects the nearest UNTAPPED opposing liquidity pool in the trade direction.
    """
    candidates: List[DrawOnLiquidity] = []

    for p in pools:
        if p.status != "untapped":
            continue
        if direction == OrderType.BUY and p.price > current_price and p.level_type in ("BSL", "EQH", "PD_MID"):
            candidates.append(DrawOnLiquidity(price=p.price, pool_type=p.level_type, pool_id=p.id, distance=p.price - current_price))
        elif direction == OrderType.SELL and p.price < current_price and p.level_type in ("SSL", "EQL", "PD_MID"):
            candidates.append(DrawOnLiquidity(price=p.price, pool_type=p.level_type, pool_id=p.id, distance=current_price - p.price))

    for z in key_level_zones or []:
        if z.swept:
            continue
        if direction == OrderType.BUY and z.price > current_price and z.level_type in ("BSL", "EQH", "PD_MID"):
            candidates.append(DrawOnLiquidity(price=z.price, pool_type=z.level_type, pool_id=z.id, distance=z.price - current_price))
        elif direction == OrderType.SELL and z.price < current_price and z.level_type in ("SSL", "EQL", "PD_MID"):
            candidates.append(DrawOnLiquidity(price=z.price, pool_type=z.level_type, pool_id=z.id, distance=current_price - z.price))

    if not candidates:
        return None

    if prefer_level_type:
        preferred = [c for c in candidates if c.pool_type == prefer_level_type]
        if preferred:
            preferred.sort(key=lambda x: x.distance)
            return preferred[0]

    candidates.sort(key=lambda x: x.distance)
    return candidates[0]


def validate_draw_on_liquidity(
    direction: OrderType,
    entry_price: float,
    stop_loss: float,
    draw: Optional[DrawOnLiquidity],
    min_rr: float = 2.0,
) -> Tuple[bool, float, str]:
    """
    P10 [VIDEO: keepssy_fx-20261126-0009]:
    "No draw, no trade": rejects if no untapped target pool exists or R:R < min_rr.
    Returns (is_valid, rr, reason).
    """
    if draw is None:
        return False, 0.0, "NO_DRAW_ON_LIQUIDITY: target pool missing or already taken"
    risk = abs(entry_price - stop_loss)
    if risk <= 1e-9:
        return False, 0.0, "INVALID_RISK_DISTANCE"
    reward = (draw.price - entry_price) if direction == OrderType.BUY else (entry_price - draw.price)
    if reward <= 0:
        return False, 0.0, "DRAW_BEHIND_ENTRY"
    rr = round(reward / risk, 3)
    if rr < min_rr:
        return False, rr, f"INSUFFICIENT_RR: {rr:.2f} < {min_rr:.2f}"
    return True, rr, "OK"


# ============================================================================
# P11: 3-POINT TURN VALIDATOR (SWEEP + SMT DIVERGENCE + MSS)
# ============================================================================

@dataclass(frozen=True)
class ThreePointTurnResult:
    grade: str  # "A+" | "B" | "INVALID"
    has_sweep: bool
    has_mss: bool
    smt_status: str  # "CONFIRMED" | "FAILED" | "UNKNOWN"
    smt_source: str  # "XAUUSD_USDJPY_INVERSE" | "REFERENCE_SYMBOL" | "NONE"
    correlation_regime: str
    reason: str


def evaluate_smt_divergence_video(
    primary_symbol: str,
    primary_candles: Sequence[Candle],
    direction: OrderType,
    sweep_index: int,
    correlated_symbol: Optional[str] = None,
    correlated_candles: Optional[Sequence[Candle]] = None,
    inverse_pair: bool = True,
    coordinator: Optional[InverseDirectionCoordinator] = None,
    lookback_swings: int = 12,
) -> Tuple[str, str, str]:
    """
    Evaluates SMT divergence at `sweep_index` [VIDEO: keepssy_fx-20261126-0006]:
    - Source A (inverse_pair=True, e.g. XAUUSD <-> USDJPY): trusted ONLY when rolling regime is
      INVERSE_STRONG or INVERSE_MODERATE; if POSITIVE_BREAKDOWN / UNCORRELATED -> UNKNOWN.
      For bullish XAUUSD low sweep: valid SMT = USDJPY fails to make a mirrored new high.
      For bearish XAUUSD high sweep: valid SMT = USDJPY fails to make a mirrored new low.
    - Source B (inverse_pair=False, e.g. XAUUSD <-> XAGUSD or BTCUSD <-> ETHUSD):
      For bullish low sweep: valid SMT = reference fails to make a new lower low.
      For bearish high sweep: valid SMT = reference fails to make a new higher high.
    Returns: (smt_status: CONFIRMED|FAILED|UNKNOWN, smt_source, regime_str)
    """
    if not correlated_candles or sweep_index < 3 or sweep_index >= len(primary_candles):
        return "UNKNOWN", "NONE", "UNAVAILABLE"

    n_corr = len(correlated_candles)
    idx_b = min(sweep_index, n_corr - 1)
    if idx_b < 3:
        return "UNKNOWN", "NONE", "UNAVAILABLE"

    source_tag = "XAUUSD_USDJPY_INVERSE" if inverse_pair else f"REFERENCE:{correlated_symbol or 'REF'}"
    regime_str = "DIRECT_POSITIVE"

    if inverse_pair:
        coord = coordinator or InverseDirectionCoordinator()
        if len(primary_candles) >= 6 and n_corr >= 6:
            r = coord.compute_rolling_correlation(
                list(primary_candles[: sweep_index + 1]),
                list(correlated_candles[: idx_b + 1]),
                lookback=min(30, sweep_index + 1, idx_b + 1),
            )
            if r < coord.strong_inverse_threshold:
                regime = CorrelationRegime.INVERSE_STRONG
            elif r < coord.moderate_inverse_threshold:
                regime = CorrelationRegime.INVERSE_MODERATE
            elif r > coord.positive_breakdown_threshold:
                regime = CorrelationRegime.POSITIVE_BREAKDOWN
            else:
                regime = CorrelationRegime.UNCORRELATED
        else:
            regime = coord.state.correlation_regime
        regime_str = regime.value
        if regime not in (CorrelationRegime.INVERSE_STRONG, CorrelationRegime.INVERSE_MODERATE):
            return "UNKNOWN", source_tag, regime_str

    win_start_a = max(0, sweep_index - lookback_swings)
    win_start_b = max(0, idx_b - lookback_swings)
    prior_a = primary_candles[win_start_a:sweep_index]
    prior_b = correlated_candles[win_start_b:idx_b]
    if not prior_a or not prior_b:
        return "UNKNOWN", source_tag, regime_str

    cur_a = primary_candles[sweep_index]
    cur_b = correlated_candles[idx_b]

    if direction == OrderType.BUY:
        # Primary swept a lower low
        a_made_new_low = cur_a.low < min(c.low for c in prior_a)
        if not a_made_new_low:
            return "UNKNOWN", source_tag, regime_str
        if inverse_pair:
            # Inverse pair (USDJPY) should FAIL to make a new higher high
            b_made_mirrored_high = cur_b.high > max(c.high for c in prior_b)
            return ("FAILED" if b_made_mirrored_high else "CONFIRMED"), source_tag, regime_str
        else:
            # Positive pair (XAGUSD/ETHUSD) should FAIL to make a new lower low
            b_made_new_low = cur_b.low < min(c.low for c in prior_b)
            return ("FAILED" if b_made_new_low else "CONFIRMED"), source_tag, regime_str
    else:
        # Primary swept a higher high
        a_made_new_high = cur_a.high > max(c.high for c in prior_a)
        if not a_made_new_high:
            return "UNKNOWN", source_tag, regime_str
        if inverse_pair:
            # Inverse pair (USDJPY) should FAIL to make a new lower low
            b_made_mirrored_low = cur_b.low < min(c.low for c in prior_b)
            return ("FAILED" if b_made_mirrored_low else "CONFIRMED"), source_tag, regime_str
        else:
            # Positive pair should FAIL to make a new higher high
            b_made_new_high = cur_b.high > max(c.high for c in prior_b)
            return ("FAILED" if b_made_new_high else "CONFIRMED"), source_tag, regime_str


def evaluate_three_point_turn(
    has_sweep: bool,
    has_mss: bool,
    smt_status: str,
    smt_source: str = "NONE",
    correlation_regime: str = "UNAVAILABLE",
) -> ThreePointTurnResult:
    """
    P11 [VIDEO: keepssy_fx-20261126-0006]:
    "2 out of 3 isn't enough."
    - A+      = sweep + MSS + SMT CONFIRMED
    - B       = sweep + MSS + SMT UNKNOWN (correlated data absent or regime broken)
    - INVALID = missing sweep, missing MSS, or SMT explicitly FAILED (correlated market
                also made a new extreme at the same time)
    """
    if not has_sweep or not has_mss:
        return ThreePointTurnResult(
            grade="INVALID",
            has_sweep=has_sweep,
            has_mss=has_mss,
            smt_status=smt_status,
            smt_source=smt_source,
            correlation_regime=correlation_regime,
            reason="Missing required sweep or MSS",
        )
    if smt_status == "CONFIRMED":
        return ThreePointTurnResult(
            grade="A+",
            has_sweep=True,
            has_mss=True,
            smt_status="CONFIRMED",
            smt_source=smt_source,
            correlation_regime=correlation_regime,
            reason="3-point turn confirmed (Sweep + SMT + MSS)",
        )
    if smt_status == "FAILED":
        return ThreePointTurnResult(
            grade="INVALID",
            has_sweep=True,
            has_mss=True,
            smt_status="FAILED",
            smt_source=smt_source,
            correlation_regime=correlation_regime,
            reason="SMT failed: correlated market made mirrored new extreme (2 of 3 not enough)",
        )
    return ThreePointTurnResult(
        grade="B",
        has_sweep=True,
        has_mss=True,
        smt_status="UNKNOWN",
        smt_source=smt_source,
        correlation_regime=correlation_regime,
        reason="Sweep + MSS confirmed; SMT unavailable/uncorrelated (Grade B)",
    )
