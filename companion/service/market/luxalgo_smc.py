"""
LuxAlgo Smart Money Concepts (SMC) — Python Port for Companion Chart Drawings.

Attribution & License:
  Ported from LuxAlgo "Smart Money Concepts [LuxAlgo]" (Pine Script v5),
  licensed under CC BY-NC-SA 4.0 © LuxAlgo.
  This is a read-only visualization/detection port for the Companion chart.
  It NEVER mutates trading strategy state, execution logic, or risk rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

BULLISH_LEG = 1
BEARISH_LEG = 0

BULLISH = 1
BEARISH = -1
NEUTRAL = 0

MAX_STORED_ORDER_BLOCKS = 100
MAX_OBJECTS_PER_KIND = 500


@dataclass
class SmcConfig:
    """Parameters mirroring LuxAlgo Smart Money Concepts Pine v5 Inputs."""

    mode: Literal["Historical", "Present"] = "Historical"
    swing_length: int = 50
    internal_length: int = 5
    swing_points_length: int = 50
    internal_confluence_filter: bool = False
    ob_filter: Literal["Atr", "Cumulative Mean Range"] = "Atr"
    ob_mitigation: Literal["High/Low", "Close"] = "High/Low"
    internal_ob_count: int = 5
    swing_ob_count: int = 5
    eqh_bars_confirmation: int = 3
    eqh_threshold: float = 0.1
    fvg_auto_threshold: bool = True
    fvg_extend: int = 1


@dataclass
class _Pivot:
    current_level: Optional[float] = None
    last_level: Optional[float] = None
    crossed: bool = False
    bar_time: int = 0
    bar_index: int = 0


@dataclass
class _OrderBlock:
    bar_high: float
    bar_low: float
    bar_time: int
    bar_index: int
    bias: int  # BULLISH (+1) or BEARISH (-1)
    tier: Literal["INTERNAL", "SWING"]


@dataclass
class _FairValueGap:
    top: float
    bottom: float
    bias: int  # BULLISH (+1) or BEARISH (-1)
    bar_time: int
    bar_index: int


@dataclass
class SmcDetectionResult:
    internal_structures: List[Dict[str, Any]] = field(default_factory=list)
    swing_structures: List[Dict[str, Any]] = field(default_factory=list)
    swing_points: List[Dict[str, Any]] = field(default_factory=list)
    internal_order_blocks: List[Dict[str, Any]] = field(default_factory=list)
    swing_order_blocks: List[Dict[str, Any]] = field(default_factory=list)
    equal_highs_lows: List[Dict[str, Any]] = field(default_factory=list)
    fair_value_gaps: List[Dict[str, Any]] = field(default_factory=list)
    strong_weak_levels: List[Dict[str, Any]] = field(default_factory=list)
    premium_discount_zones: List[Dict[str, Any]] = field(default_factory=list)
    candle_trends: List[int] = field(default_factory=list)
    swing_trend: int = NEUTRAL
    internal_trend: int = NEUTRAL


def _compute_atr_rma(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 200) -> List[float]:
    """Wilder's RMA ATR(period) matching Pine's ta.atr(200)."""
    n = len(highs)
    if n == 0:
        return []
    tr = [0.0] * n
    tr[0] = max(0.0, highs[0] - lows[0])
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    atr = [0.0] * n
    alpha = 1.0 / float(period)
    running = tr[0]
    atr[0] = running
    for i in range(1, n):
        if i < period:
            running = ((running * i) + tr[i]) / float(i + 1)
        else:
            running = alpha * tr[i] + (1.0 - alpha) * running
        atr[i] = running
    return atr


def _compute_cum_mean_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[float]:
    """Cumulative Mean Range matching Pine's ta.cum(ta.tr) / bar_index."""
    n = len(highs)
    if n == 0:
        return []
    out = [0.0] * n
    cum_tr = 0.0
    for i in range(n):
        if i == 0:
            tr = max(0.0, highs[0] - lows[0])
        else:
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        cum_tr += tr
        out[i] = cum_tr / float(i + 1)
    return out


def _detect_leg_series(highs: Sequence[float], lows: Sequence[float], size: int) -> List[int]:
    """
    Exact Pine v5 leg(size) implementation:
      newLegHigh = high[size] > ta.highest(size)
      newLegLow  = low[size]  < ta.lowest(size)
      if newLegHigh -> BEARISH_LEG (0)
      elif newLegLow -> BULLISH_LEG (1)
      else -> previous leg
    """
    n = len(highs)
    legs = [BEARISH_LEG] * n
    if size < 1 or n <= size:
        return legs

    cur_leg = BEARISH_LEG
    for i in range(size, n):
        pivot_h = highs[i - size]
        pivot_l = lows[i - size]
        window_max_h = max(highs[i - size + 1 : i + 1])
        window_min_l = min(lows[i - size + 1 : i + 1])
        if pivot_h > window_max_h:
            cur_leg = BEARISH_LEG
        elif pivot_l < window_min_l:
            cur_leg = BULLISH_LEG
        legs[i] = cur_leg
    return legs


def detect_luxalgo_smc(
    candles: Sequence[Dict[str, Any]],
    config: Optional[SmcConfig] = None,
) -> SmcDetectionResult:
    """
    Runs the full LuxAlgo Smart Money Concepts detection pipeline on OHLC candles.
    Each candle dict must have numeric keys: time (unix sec), open, high, low, close.
    """
    cfg = config or SmcConfig()
    result = SmcDetectionResult()
    n = len(candles)
    if n < 3:
        return result

    times: List[int] = []
    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []

    for c in candles:
        try:
            t = int(c["time"])
            o = float(c["open"])
            h = float(c["high"])
            l = float(c["low"])
            cl = float(c["close"])
            if not all(math.isfinite(x) for x in (o, h, l, cl)):
                continue
            times.append(t)
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(cl)
        except Exception:
            continue

    n = len(times)
    if n < 3:
        return result

    atr200 = _compute_atr_rma(highs, lows, closes, period=200)
    cum_mean = _compute_cum_mean_range(highs, lows, closes)
    vol_measure = atr200 if cfg.ob_filter == "Atr" else cum_mean

    # Parsed highs/lows (swap high/low on high-volatility bars: range >= 2 * volatilityMeasure)
    parsed_highs = [0.0] * n
    parsed_lows = [0.0] * n
    for i in range(n):
        rng = highs[i] - lows[i]
        is_high_vol = vol_measure[i] > 0.0 and rng >= 2.0 * vol_measure[i]
        parsed_highs[i] = lows[i] if is_high_vol else highs[i]
        parsed_lows[i] = highs[i] if is_high_vol else lows[i]

    swing_len = max(2, int(cfg.swing_length))
    internal_len = max(2, int(cfg.internal_length))
    swing_pts_len = max(2, int(cfg.swing_points_length))
    eqh_len = max(1, int(cfg.eqh_bars_confirmation))

    swing_legs = _detect_leg_series(highs, lows, swing_len)
    internal_legs = _detect_leg_series(highs, lows, internal_len)
    eqh_legs = _detect_leg_series(highs, lows, eqh_len)
    swing_pts_legs = swing_legs if swing_pts_len == swing_len else _detect_leg_series(highs, lows, swing_pts_len)

    swing_high = _Pivot()
    swing_low = _Pivot()
    internal_high = _Pivot()
    internal_low = _Pivot()
    eqh_pivot = _Pivot()
    eql_pivot = _Pivot()
    sp_high = _Pivot()
    sp_low = _Pivot()

    swing_trend = NEUTRAL
    internal_trend = NEUTRAL

    # Trailing swing extremes
    trailing_top: Optional[float] = None
    trailing_bottom: Optional[float] = None
    trailing_top_time: int = times[0]
    trailing_bottom_time: int = times[0]

    internal_obs: List[_OrderBlock] = []
    swing_obs: List[_OrderBlock] = []
    active_fvgs: List[_FairValueGap] = []

    candle_trends: List[int] = [NEUTRAL] * n
    cum_abs_delta = 0.0

    def _store_ob(pivot: _Pivot, break_idx: int, bias: int, tier: Literal["INTERNAL", "SWING"]) -> None:
        start_i = max(0, pivot.bar_index)
        end_i = max(start_i + 1, break_idx)
        if start_i >= end_i or end_i > n:
            return
        if bias == BEARISH:
            best_idx = start_i
            best_val = parsed_highs[start_i]
            for k in range(start_i + 1, end_i):
                if parsed_highs[k] > best_val:
                    best_val = parsed_highs[k]
                    best_idx = k
        else:
            best_idx = start_i
            best_val = parsed_lows[start_i]
            for k in range(start_i + 1, end_i):
                if parsed_lows[k] < best_val:
                    best_val = parsed_lows[k]
                    best_idx = k

        ob_top = max(parsed_highs[best_idx], parsed_lows[best_idx])
        ob_bot = min(parsed_highs[best_idx], parsed_lows[best_idx])
        if ob_top <= ob_bot:
            ob_top = highs[best_idx]
            ob_bot = lows[best_idx]
        if ob_top <= ob_bot:
            return

        ob = _OrderBlock(
            bar_high=ob_top,
            bar_low=ob_bot,
            bar_time=times[best_idx],
            bar_index=best_idx,
            bias=bias,
            tier=tier,
        )
        target_list = internal_obs if tier == "INTERNAL" else swing_obs
        target_list.insert(0, ob)
        if len(target_list) > MAX_STORED_ORDER_BLOCKS:
            target_list.pop()

    for i in range(n):
        # 1. Swing pivots (size = swing_len)
        if i > swing_len:
            leg_diff = swing_legs[i] - swing_legs[i - 1]
            if leg_diff == 1:  # startOfBullishLeg -> confirmed pivot LOW at i - swing_len
                p_idx = i - swing_len
                swing_low.last_level = swing_low.current_level
                swing_low.current_level = lows[p_idx]
                swing_low.crossed = False
                swing_low.bar_time = times[p_idx]
                swing_low.bar_index = p_idx
                trailing_bottom = swing_low.current_level
                trailing_bottom_time = swing_low.bar_time
            elif leg_diff == -1:  # startOfBearishLeg -> confirmed pivot HIGH at i - swing_len
                p_idx = i - swing_len
                swing_high.last_level = swing_high.current_level
                swing_high.current_level = highs[p_idx]
                swing_high.crossed = False
                swing_high.bar_time = times[p_idx]
                swing_high.bar_index = p_idx
                trailing_top = swing_high.current_level
                trailing_top_time = swing_high.bar_time

        # Update trailing extremes on every bar
        if trailing_top is None or highs[i] >= trailing_top:
            trailing_top = highs[i]
            trailing_top_time = times[i]
        if trailing_bottom is None or lows[i] <= trailing_bottom:
            trailing_bottom = lows[i]
            trailing_bottom_time = times[i]

        # 2. Swing point labels (HH/HL/LH/LL) with own length
        if i > swing_pts_len:
            sp_diff = swing_pts_legs[i] - swing_pts_legs[i - 1]
            if sp_diff == 1:
                p_idx = i - swing_pts_len
                sp_low.last_level = sp_low.current_level
                sp_low.current_level = lows[p_idx]
                sp_low.bar_time = times[p_idx]
                sp_low.bar_index = p_idx
                if sp_low.last_level is not None:
                    tag = "LL" if sp_low.current_level < sp_low.last_level else "HL"
                    result.swing_points.append(
                        {
                            "tag": tag,
                            "price": round(sp_low.current_level, 5),
                            "time": sp_low.bar_time,
                            "bar_index": sp_low.bar_index,
                            "direction": "BULLISH",
                            "irl_erl": "ERL",
                        }
                    )
            elif sp_diff == -1:
                p_idx = i - swing_pts_len
                sp_high.last_level = sp_high.current_level
                sp_high.current_level = highs[p_idx]
                sp_high.bar_time = times[p_idx]
                sp_high.bar_index = p_idx
                if sp_high.last_level is not None:
                    tag = "HH" if sp_high.current_level > sp_high.last_level else "LH"
                    result.swing_points.append(
                        {
                            "tag": tag,
                            "price": round(sp_high.current_level, 5),
                            "time": sp_high.bar_time,
                            "bar_index": sp_high.bar_index,
                            "direction": "BEARISH",
                            "irl_erl": "ERL",
                        }
                    )

        # 3. Internal pivots (size = internal_len)
        if i > internal_len:
            i_diff = internal_legs[i] - internal_legs[i - 1]
            if i_diff == 1:
                p_idx = i - internal_len
                internal_low.last_level = internal_low.current_level
                internal_low.current_level = lows[p_idx]
                internal_low.crossed = False
                internal_low.bar_time = times[p_idx]
                internal_low.bar_index = p_idx
            elif i_diff == -1:
                p_idx = i - internal_len
                internal_high.last_level = internal_high.current_level
                internal_high.current_level = highs[p_idx]
                internal_high.crossed = False
                internal_high.bar_time = times[p_idx]
                internal_high.bar_index = p_idx

        # 4. EQH / EQL detection (size = eqh_len)
        if i > eqh_len:
            e_diff = eqh_legs[i] - eqh_legs[i - 1]
            thresh = float(cfg.eqh_threshold) * atr200[i]
            if e_diff == -1:  # Pivot High
                p_idx = i - eqh_len
                lvl = highs[p_idx]
                if eqh_pivot.current_level is not None and abs(lvl - eqh_pivot.current_level) < thresh:
                    result.equal_highs_lows.append(
                        {
                            "tag": "EQH",
                            "start_time": eqh_pivot.bar_time,
                            "end_time": times[p_idx],
                            "start_price": round(eqh_pivot.current_level, 5),
                            "end_price": round(lvl, 5),
                            "price": round((eqh_pivot.current_level + lvl) / 2.0, 5),
                            "direction": "BEARISH",
                            "irl_erl": "ERL",
                        }
                    )
                eqh_pivot.last_level = eqh_pivot.current_level
                eqh_pivot.current_level = lvl
                eqh_pivot.bar_time = times[p_idx]
                eqh_pivot.bar_index = p_idx
            elif e_diff == 1:  # Pivot Low
                p_idx = i - eqh_len
                lvl = lows[p_idx]
                if eql_pivot.current_level is not None and abs(lvl - eql_pivot.current_level) < thresh:
                    result.equal_highs_lows.append(
                        {
                            "tag": "EQL",
                            "start_time": eql_pivot.bar_time,
                            "end_time": times[p_idx],
                            "start_price": round(eql_pivot.current_level, 5),
                            "end_price": round(lvl, 5),
                            "price": round((eql_pivot.current_level + lvl) / 2.0, 5),
                            "direction": "BULLISH",
                            "irl_erl": "ERL",
                        }
                    )
                eql_pivot.last_level = eql_pivot.current_level
                eql_pivot.current_level = lvl
                eql_pivot.bar_time = times[p_idx]
                eql_pivot.bar_index = p_idx

        # 5. Structure breaks (crossover / crossunder of CLOSE over active pivot)
        if i >= 1:
            prev_close = closes[i - 1]
            cur_close = closes[i]

            # Confluence filter wick logic
            bullish_bar = True
            bearish_bar = True
            if cfg.internal_confluence_filter:
                upper_wick = highs[i] - max(cur_close, opens[i])
                lower_wick = min(cur_close, opens[i]) - lows[i]
                bullish_bar = upper_wick > lower_wick
                bearish_bar = upper_wick < lower_wick

            # 5a. Internal Bullish break
            if (
                internal_high.current_level is not None
                and not internal_high.crossed
                and cur_close > internal_high.current_level
                and prev_close <= internal_high.current_level
                and internal_high.current_level != swing_high.current_level
                and bullish_bar
            ):
                tag = "CHoCH" if internal_trend == BEARISH else "BOS"
                internal_high.crossed = True
                internal_trend = BULLISH
                result.internal_structures.append(
                    {
                        "tag": tag,
                        "tier": "INTERNAL",
                        "direction": "BULLISH",
                        "price": round(internal_high.current_level, 5),
                        "start_time": internal_high.bar_time,
                        "end_time": times[i],
                        "start_index": internal_high.bar_index,
                        "end_index": i,
                        "irl_erl": "IRL",
                    }
                )
                _store_ob(internal_high, i, BULLISH, "INTERNAL")

            # 5b. Internal Bearish break
            if (
                internal_low.current_level is not None
                and not internal_low.crossed
                and cur_close < internal_low.current_level
                and prev_close >= internal_low.current_level
                and internal_low.current_level != swing_low.current_level
                and bearish_bar
            ):
                tag = "CHoCH" if internal_trend == BULLISH else "BOS"
                internal_low.crossed = True
                internal_trend = BEARISH
                result.internal_structures.append(
                    {
                        "tag": tag,
                        "tier": "INTERNAL",
                        "direction": "BEARISH",
                        "price": round(internal_low.current_level, 5),
                        "start_time": internal_low.bar_time,
                        "end_time": times[i],
                        "start_index": internal_low.bar_index,
                        "end_index": i,
                        "irl_erl": "IRL",
                    }
                )
                _store_ob(internal_low, i, BEARISH, "INTERNAL")

            # 5c. Swing Bullish break
            if (
                swing_high.current_level is not None
                and not swing_high.crossed
                and cur_close > swing_high.current_level
                and prev_close <= swing_high.current_level
            ):
                tag = "CHoCH" if swing_trend == BEARISH else "BOS"
                swing_high.crossed = True
                swing_trend = BULLISH
                result.swing_structures.append(
                    {
                        "tag": tag,
                        "tier": "SWING",
                        "direction": "BULLISH",
                        "price": round(swing_high.current_level, 5),
                        "start_time": swing_high.bar_time,
                        "end_time": times[i],
                        "start_index": swing_high.bar_index,
                        "end_index": i,
                        "irl_erl": "ERL",
                    }
                )
                _store_ob(swing_high, i, BULLISH, "SWING")

            # 5d. Swing Bearish break
            if (
                swing_low.current_level is not None
                and not swing_low.crossed
                and cur_close < swing_low.current_level
                and prev_close >= swing_low.current_level
            ):
                tag = "CHoCH" if swing_trend == BULLISH else "BOS"
                swing_low.crossed = True
                swing_trend = BEARISH
                result.swing_structures.append(
                    {
                        "tag": tag,
                        "tier": "SWING",
                        "direction": "BEARISH",
                        "price": round(swing_low.current_level, 5),
                        "start_time": swing_low.bar_time,
                        "end_time": times[i],
                        "start_index": swing_low.bar_index,
                        "end_index": i,
                        "irl_erl": "ERL",
                    }
                )
                _store_ob(swing_low, i, BEARISH, "SWING")

        # 6. Order Block mitigation (remove mitigated OBs)
        bear_src = closes[i] if cfg.ob_mitigation == "Close" else highs[i]
        bull_src = closes[i] if cfg.ob_mitigation == "Close" else lows[i]
        if internal_obs:
            internal_obs = [
                ob
                for ob in internal_obs
                if not (
                    (ob.bias == BEARISH and bear_src > ob.bar_high)
                    or (ob.bias == BULLISH and bull_src < ob.bar_low)
                )
            ]
        if swing_obs:
            swing_obs = [
                ob
                for ob in swing_obs
                if not (
                    (ob.bias == BEARISH and bear_src > ob.bar_high)
                    or (ob.bias == BULLISH and bull_src < ob.bar_low)
                )
            ]

        # 7. Fair Value Gaps (mitigate first, then detect new)
        if active_fvgs:
            active_fvgs = [
                fvg
                for fvg in active_fvgs
                if not (
                    (fvg.bias == BULLISH and lows[i] < fvg.bottom)
                    or (fvg.bias == BEARISH and highs[i] > fvg.top)
                )
            ]
        if i >= 2:
            c1_open = opens[i - 1]
            c1_close = closes[i - 1]
            bar_delta_pct = (c1_close - c1_open) / c1_open if c1_open != 0.0 else 0.0
            cum_abs_delta += abs(bar_delta_pct)
            fvg_thresh = (cum_abs_delta / float(i + 1)) * 2.0 if cfg.fvg_auto_threshold else 0.0

            if lows[i] > highs[i - 2] and c1_close > highs[i - 2] and bar_delta_pct > fvg_thresh:
                active_fvgs.insert(
                    0,
                    _FairValueGap(
                        top=lows[i],
                        bottom=highs[i - 2],
                        bias=BULLISH,
                        bar_time=times[i],
                        bar_index=i,
                    ),
                )
            elif highs[i] < lows[i - 2] and c1_close < lows[i - 2] and (-bar_delta_pct) > fvg_thresh:
                active_fvgs.insert(
                    0,
                    _FairValueGap(
                        top=lows[i - 2],
                        bottom=highs[i],
                        bias=BEARISH,
                        bar_time=times[i],
                        bar_index=i,
                    ),
                )
            if len(active_fvgs) > MAX_OBJECTS_PER_KIND:
                active_fvgs.pop()

        candle_trends[i] = internal_trend if internal_trend != NEUTRAL else swing_trend

    # Mode: Present keeps only the most recent structure per tier & EQH/EQL
    if cfg.mode == "Present":
        result.internal_structures = result.internal_structures[-1:]
        result.swing_structures = result.swing_structures[-1:]
        result.equal_highs_lows = result.equal_highs_lows[-1:]
    else:
        result.internal_structures = result.internal_structures[-MAX_OBJECTS_PER_KIND:]
        result.swing_structures = result.swing_structures[-MAX_OBJECTS_PER_KIND:]
        result.equal_highs_lows = result.equal_highs_lows[-MAX_OBJECTS_PER_KIND:]

    result.swing_points = result.swing_points[-MAX_OBJECTS_PER_KIND:]

    int_ob_limit = max(1, min(20, int(cfg.internal_ob_count)))
    sw_ob_limit = max(1, min(20, int(cfg.swing_ob_count)))

    result.internal_order_blocks = [
        {
            "top": round(ob.bar_high, 5),
            "bottom": round(ob.bar_low, 5),
            "midpoint": round((ob.bar_high + ob.bar_low) / 2.0, 5),
            "start_time": ob.bar_time,
            "bar_index": ob.bar_index,
            "direction": "BULLISH" if ob.bias == BULLISH else "BEARISH",
            "tier": "INTERNAL",
            "irl_erl": "IRL",
        }
        for ob in internal_obs[:int_ob_limit]
    ]

    result.swing_order_blocks = [
        {
            "top": round(ob.bar_high, 5),
            "bottom": round(ob.bar_low, 5),
            "midpoint": round((ob.bar_high + ob.bar_low) / 2.0, 5),
            "start_time": ob.bar_time,
            "bar_index": ob.bar_index,
            "direction": "BULLISH" if ob.bias == BULLISH else "BEARISH",
            "tier": "SWING",
            "irl_erl": "ERL",
        }
        for ob in swing_obs[:sw_ob_limit]
    ]

    result.fair_value_gaps = [
        {
            "top": round(fvg.top, 5),
            "bottom": round(fvg.bottom, 5),
            "midpoint": round((fvg.top + fvg.bottom) / 2.0, 5),
            "start_time": fvg.bar_time,
            "bar_index": fvg.bar_index,
            "direction": "BULLISH" if fvg.bias == BULLISH else "BEARISH",
            "extend_bars": max(0, int(cfg.fvg_extend)),
            "irl_erl": "IRL",
        }
        for fvg in active_fvgs[:MAX_OBJECTS_PER_KIND]
    ]

    # Strong / Weak High & Low + Premium / Equilibrium / Discount zones
    if trailing_top is not None and trailing_bottom is not None and trailing_top > trailing_bottom:
        result.strong_weak_levels = [
            {
                "kind": "HIGH",
                "label": "Strong High" if swing_trend == BEARISH else "Weak High",
                "is_strong": swing_trend == BEARISH,
                "price": round(trailing_top, 5),
                "start_time": trailing_top_time,
                "direction": "BEARISH",
                "irl_erl": "ERL",
            },
            {
                "kind": "LOW",
                "label": "Strong Low" if swing_trend == BULLISH else "Weak Low",
                "is_strong": swing_trend == BULLISH,
                "price": round(trailing_bottom, 5),
                "start_time": trailing_bottom_time,
                "direction": "BULLISH",
                "irl_erl": "ERL",
            },
        ]

        zone_start = min(trailing_top_time, trailing_bottom_time)
        result.premium_discount_zones = [
            {
                "kind": "PREMIUM",
                "label": "Premium",
                "top": round(trailing_top, 5),
                "bottom": round(0.95 * trailing_top + 0.05 * trailing_bottom, 5),
                "start_time": zone_start,
                "irl_erl": "ERL",
            },
            {
                "kind": "EQUILIBRIUM",
                "label": "Equilibrium",
                "top": round(0.525 * trailing_top + 0.475 * trailing_bottom, 5),
                "bottom": round(0.525 * trailing_bottom + 0.475 * trailing_top, 5),
                "start_time": zone_start,
                "irl_erl": "IRL",
            },
            {
                "kind": "DISCOUNT",
                "label": "Discount",
                "top": round(0.95 * trailing_bottom + 0.05 * trailing_top, 5),
                "bottom": round(trailing_bottom, 5),
                "start_time": zone_start,
                "irl_erl": "ERL",
            },
        ]

    result.candle_trends = candle_trends
    result.swing_trend = swing_trend
    result.internal_trend = internal_trend
    return result
