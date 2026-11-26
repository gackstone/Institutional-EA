"""
Comprehensive Unit, Time/DST, Mirror, Negative, and Safety Tests for the
16 Forex-Video Strategies (Primitives P1-P11, Setups S1-S10, Trade Management,
Knowledge Export, and Telegram Template).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

import pytest

from src.core.contracts import Candle, OrderType, Position, SymbolInfo, Timeframe
from src.core.sessions import TradingSessionEngine
from src.core.symbol_universe import DATA_ONLY_REFERENCE_SYMBOLS, SpecializedSymbolUniverse
from src.manual_mgmt.assessor import ManualPositionAssessor
from src.manual_mgmt.contracts import ManualMgmtConfig, ManualPositionRecord
from src.notifications.events import TradeSetupEvent
from src.notifications.templates.default_templates import TemplateRenderer
from src.risk.trade_management import TradeManagementEngine
from src.smc.session_liquidity import SessionKeyLevels, SessionLiquidityEngine
from src.smc.video_primitives import (
    StopClusterPool,
    classify_sweep_vs_breakout,
    compute_bos_anchored_ote,
    detect_confirmed_sweep,
    detect_equal_clusters,
    detect_flipped_breakers,
    detect_ifvg_candidates,
    detect_mss_with_displacement,
    evaluate_smt_divergence_video,
    evaluate_three_point_turn,
    get_draw_on_liquidity,
    validate_draw_on_liquidity,
)
from src.smc.video_setups import (
    VideoConfigValidationError,
    VideoSetupEngine,
    validate_video_setups_config,
)


# ============================================================================
# SYNTHETIC CANDLE FIXTURE HELPERS
# ============================================================================

def mk_candle(
    t: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    vol: int = 100,
) -> Candle:
    return Candle(time=t, open=o, high=h, low=l, close=c, tick_volume=vol, complete=True)


def build_bullish_raid_shift_fvg(
    start_dt: datetime,
    step_minutes: int = 5,
    base: float = 2650.0,
) -> Tuple[List[Candle], List[Candle]]:
    """
    Draws:
      - Swing high (BSL target above at base+16)
      - Equal lows (EQL at base)
      - Confirmed sweep below base (low=base-2.0, close=base+0.5)
      - Displacement MSS candle closing above opposing swing high leaving a clean Bullish FVG
      - Mirrored USDJPY inverse series that FAILS to make a new higher high at the sweep (valid SMT!)
    """
    specs = [
        # (o, h, l, c)
        (base + 10, base + 13.0, base + 9.0,  base + 12.0),  # 0: lead-in so index 2 is a left=2 swing high
        (base + 12, base + 16.0, base + 11.0, base + 14.0),  # 1: approach to BSL
        (base + 14, base + 17.5, base + 12.0, base + 13.0),  # 2: BSL swing high (17.5, untapped draw!)
        (base + 13, base + 14.0, base + 8.0,  base + 9.0),   # 3
        (base + 9,  base + 10.0, base + 4.0,  base + 5.0),   # 4
        (base + 5,  base + 6.0,  base + 0.0,  base + 2.0),   # 5: EQL touch #1 (low=base)
        (base + 2,  base + 4.5,  base + 1.5,  base + 4.0),   # 6: minor bounce
        (base + 4,  base + 5.0,  base + 2.5,  base + 3.0),   # 7: opposing swing high (5.0)
        (base + 3,  base + 3.5,  base + 1.0,  base + 1.5),   # 8
        (base + 1.5, base + 2.5, base + 0.05, base + 2.0),   # 9: EQL touch #2 (within 0.10*ATR)
        (base + 2.0, base + 3.5, base + 1.5,  base + 3.0),   # 10
        (base + 3.0, base + 3.8, base + 2.0,  base + 2.2),   # 11: corrective approach
        (base + 2.2, base + 2.8, base + 1.2,  base + 1.6),   # 12: corrective approach
        (base + 1.6, base + 2.0, base - 2.2,  base + 0.8),   # 13: SWEEP below EQL, closes back above!
        (base + 0.8, base + 1.5, base + 0.4,  base + 1.2),   # 14: c1 of FVG (high=1.5)
        (base + 1.2, base + 7.2, base + 1.1,  base + 7.0),   # 15: DISPLACEMENT MSS above 5.0!
        (base + 7.0, base + 8.0, base + 5.2,  base + 6.5),   # 16: c3 of FVG (low=5.2 > c1.high=1.5 -> FVG [1.5..5.2], CE=3.35)
    ]
    xau: List[Candle] = []
    usdjpy: List[Candle] = []
    jpy_base = 155.0
    for i, (o, h, l, c) in enumerate(specs):
        t = start_dt + timedelta(minutes=i * step_minutes)
        xau.append(mk_candle(t, o, h, l, c))
        # Inverse correlated USDJPY: moves opposite to XAUUSD, EXCEPT at index 13 fails to make new high!
        inv_o = jpy_base - (o - base) * 0.15
        inv_c = jpy_base - (c - base) * 0.15
        inv_h = max(inv_o, inv_c) + 0.15
        inv_l = min(inv_o, inv_c) - 0.15
        if i == 5:
            inv_h = jpy_base + 0.80  # Earlier JPY high
        if i == 13:
            inv_h = jpy_base + 0.40  # Fails to break 155.80 -> valid inverse SMT!
        usdjpy.append(mk_candle(t, inv_o, inv_h, inv_l, inv_c))
    return xau, usdjpy


def build_bearish_raid_shift_fvg(
    start_dt: datetime,
    step_minutes: int = 5,
    base: float = 2650.0,
) -> Tuple[List[Candle], List[Candle]]:
    """Exact short mirror of build_bullish_raid_shift_fvg."""
    xau_bull, jpy_bull = build_bullish_raid_shift_fvg(start_dt, step_minutes, base)
    # Mirror prices around `base`
    xau_bear = [
        mk_candle(c.time, 2 * base - c.open, 2 * base - c.low, 2 * base - c.high, 2 * base - c.close)
        for c in xau_bull
    ]
    jpy_mid = 155.0
    jpy_bear = [
        mk_candle(c.time, 2 * jpy_mid - c.open, 2 * jpy_mid - c.low, 2 * jpy_mid - c.high, 2 * jpy_mid - c.close)
        for c in jpy_bull
    ]
    return xau_bear, jpy_bear


# ============================================================================
# 1. TIME & DST TESTS (MARCH SPRING-FORWARD & NOVEMBER FALL-BACK)
# ============================================================================

def test_ny_ict_windows_dst_transitions_and_broker_offset():
    eng = TradingSessionEngine()

    # Winter (EST = UTC-5): 10:15 NY AM = 15:15 UTC -> inside Silver Bullet NY AM (10-11) & outside Macro 1 (9:50-10:10)
    win_est = eng.get_active_ict_windows(datetime(2026, 2, 10, 15, 15, tzinfo=timezone.utc))
    assert win_est["is_dst"] is False
    assert win_est["is_silver_bullet"] is True
    assert "silver_bullet_ny_am" in win_est["active_windows"]
    assert win_est["is_ny_macro"] is False

    # Summer after March DST spring-forward (EDT = UTC-4): 10:00 NY AM = 14:00 UTC -> inside Silver Bullet NY AM + NY Macro 1
    win_edt = eng.get_active_ict_windows(datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc))
    assert win_edt["is_dst"] is True
    assert "silver_bullet_ny_am" in win_edt["active_windows"]
    assert "ny_macro_1" in win_edt["active_windows"]
    assert win_edt["primary_context"] == "NY_MACRO"

    # After November DST fall-back (EST = UTC-5): 03:30 NY = 08:30 UTC -> Silver Bullet London
    win_nov = eng.get_active_ict_windows(datetime(2026, 11, 10, 8, 30, tzinfo=timezone.utc))
    assert win_nov["is_dst"] is False
    assert "silver_bullet_london" in win_nov["active_windows"]

    # Broker server time (+2h offset = +7200s): 17:05 broker = 15:05 UTC = 10:05 NY (EST) -> NY Macro 1 + Silver Bullet NY AM
    broker_dt = datetime(2026, 1, 15, 17, 5)
    win_broker = eng.get_active_ict_windows(broker_dt, broker_utc_offset_sec=7200)
    assert "ny_macro_1" in win_broker["active_windows"]
    assert "silver_bullet_ny_am" in win_broker["active_windows"]

    # Window expiry check: placed at 10:00 NY (15:00 UTC EST), checked at 10:11 NY (15:11 UTC) -> expired!
    assert eng.is_window_expired(
        "ny_macro_1",
        datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 15, 15, 11, tzinfo=timezone.utc),
    ) is True


def test_session_key_levels_computes_asia_london_pd_mid_morning():
    s_eng = SessionLiquidityEngine()
    day1 = datetime(2026, 1, 14, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    candles = [
        mk_candle(day1, 2600, 2620, 2580, 2610),                          # Prev day: H=2620, L=2580 -> PD Mid=2600
        mk_candle(day2 + timedelta(hours=2), 2605, 2612, 2598, 2608),     # Asia
        mk_candle(day2 + timedelta(hours=8), 2608, 2618, 2602, 2615),     # London
        mk_candle(day2 + timedelta(hours=13), 2615, 2625, 2609, 2620),    # NY Morning (08:00 NY EST)
    ]
    kl = s_eng.compute_session_key_levels("XAUUSD", candles)
    assert kl is not None
    assert kl.pdh == 2620 and kl.pdl == 2580 and kl.pd_mid == 2600.0
    assert kl.asian_high == 2612 and kl.asian_low == 2598
    assert kl.london_high == 2618 and kl.london_low == 2602
    assert kl.morning_high == 2625 and kl.morning_low == 2609
    zones = kl.to_liquidity_zones()
    assert any(z.level_type == "PD_MID" and z.price == 2600.0 for z in zones)


# ============================================================================
# 2. PRIMITIVES P1-P11 TESTS (VALID + MIRROR + NEGATIVE)
# ============================================================================

def test_p1_p3_p4_p5_clusters_sweep_mss_fvg_ce():
    t0 = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    xau, _ = build_bullish_raid_shift_fvg(t0)
    pools = detect_equal_clusters("XAUUSD", Timeframe.M5, xau, atr_tolerance_mult=0.10)
    eqls = [p for p in pools if p.level_type == "EQL"]
    assert len(eqls) >= 1
    assert eqls[0].status == "taken"  # Swept at bar 12

    sweep = detect_confirmed_sweep(xau, eqls[0].price, "EQL", start_index=eqls[0].formation_index + 1)
    assert sweep is not None
    assert sweep.direction == OrderType.BUY
    assert sweep.classification.kind == "SWEEP"

    mss = detect_mss_with_displacement("XAUUSD", Timeframe.M5, xau, after_index=sweep.reclaim_index, direction=OrderType.BUY)
    assert mss is not None
    assert mss.fvg.direction == OrderType.BUY
    assert mss.ce_price == pytest.approx((mss.fvg.top + mss.fvg.bottom) / 2.0)


def test_p2_breakout_candles_must_not_classify_as_sweep():
    t0 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    # Impulsive low-overlap rally smashing above resistance 2660 and closing strongly above
    candles = [
        mk_candle(t0 + timedelta(minutes=0), 2645, 2649, 2644.5, 2648.5),
        mk_candle(t0 + timedelta(minutes=5), 2648.5, 2653, 2648.0, 2652.5),
        mk_candle(t0 + timedelta(minutes=10), 2652.5, 2657, 2652.0, 2656.5),
        mk_candle(t0 + timedelta(minutes=15), 2656.5, 2660, 2656.0, 2659.8),
        mk_candle(t0 + timedelta(minutes=20), 2659.8, 2666.0, 2659.5, 2665.5),  # event bar: full displacement close above 2660
        mk_candle(t0 + timedelta(minutes=25), 2665.5, 2670.0, 2665.0, 2669.0),  # follow-through above 2660
    ]
    res = classify_sweep_vs_breakout(candles, level_price=2660.0, side="HIGH", event_index=4)
    assert res.kind == "BREAKOUT"
    assert res.score >= 50.0


def test_p6_p7_ifvg_and_breaker_positive_and_negative():
    t0 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    # Bearish FVG between bar 0 (low=2660) and bar 2 (high=2654) -> [2654..2660]
    # Then bar 4 CLOSES above 2660 -> inverts into Bullish IFVG; bar 5 retests [2654..2660]
    candles_inv = [
        mk_candle(t0 + timedelta(minutes=0), 2664, 2665, 2660, 2661),
        mk_candle(t0 + timedelta(minutes=5), 2661, 2661.5, 2653, 2653.5),
        mk_candle(t0 + timedelta(minutes=10), 2653.5, 2654, 2650, 2651),
        mk_candle(t0 + timedelta(minutes=15), 2651, 2655, 2648, 2654),  # stop hunt low
        mk_candle(t0 + timedelta(minutes=20), 2654, 2663, 2653.5, 2662.5),  # closes ABOVE 2660 -> inverts!
        mk_candle(t0 + timedelta(minutes=25), 2662.5, 2663, 2657, 2661),    # retest of IFVG
    ]
    cands = detect_ifvg_candidates("XAUUSD", Timeframe.M5, candles_inv, OrderType.BUY, stop_hunt_index=3)
    assert len(cands) >= 1
    assert cands[0].ifvg.is_inverse is True
    assert cands[0].is_first_before_stop_hunt is True
    assert cands[0].retested is True

    # Negative case: FVG NOT closed through (only wicked into 2658, closed at 2655) -> no IFVG!
    candles_no_close = candles_inv[:4] + [mk_candle(t0 + timedelta(minutes=20), 2654, 2659, 2653, 2655)]
    assert detect_ifvg_candidates("XAUUSD", Timeframe.M5, candles_no_close, OrderType.BUY) == []

    # P7 Breaker: Bullish OB (down candle at bar 1, low=2650) smashed by close below 2650 -> Bearish Breaker
    br_candles = [
        mk_candle(t0 + timedelta(minutes=0), 2656, 2657, 2653, 2654),
        mk_candle(t0 + timedelta(minutes=5), 2654, 2655, 2650, 2651),   # bearish candle (Bullish OB)
        mk_candle(t0 + timedelta(minutes=10), 2651, 2660, 2650.5, 2659),
        mk_candle(t0 + timedelta(minutes=15), 2659, 2662, 2658, 2661),
        mk_candle(t0 + timedelta(minutes=20), 2661, 2661.5, 2647, 2648),  # closes below 2650 -> flips to SELL breaker!
    ]
    breakers = detect_flipped_breakers("XAUUSD", Timeframe.M5, br_candles, direction=OrderType.SELL)
    assert len(breakers) >= 1
    assert breakers[0].is_breaker is True and breakers[0].direction == OrderType.SELL


def test_p8_bos_anchored_fib_zooms_out_and_rejects_minor_pullback():
    t0 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    # Major origin low=2600 -> BOS above swing high 2620 -> peak 2660 (leg=60), with a small pullback at 2635..2640
    specs = [
        (2615, 2618, 2610, 2612),
        (2612, 2614, 2600, 2605),  # major swing origin = 2600
        (2605, 2616, 2604, 2615),
        (2615, 2620, 2614, 2618),  # swing high = 2620
        (2618, 2619, 2612, 2614),
        (2614, 2616, 2610, 2615),
        (2615, 2640, 2615, 2638),  # BOS close > 2620!
        (2638, 2642, 2635, 2636),  # minor pullback (must NOT anchor here!)
        (2636, 2660, 2636, 2658),  # impulse extreme = 2660
        (2658, 2659, 2640, 2642),
        (2620, 2628, 2617, 2626),  # retraces into 0.705 (2617.7) and closes bullish!
    ]
    candles = [mk_candle(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(specs)]
    ote = compute_bos_anchored_ote("XAUUSD", Timeframe.M5, candles, OrderType.BUY)
    assert ote is not None
    assert ote.anchor_origin == 2600.0  # Zoomed out to major origin, NOT minor 2635!
    assert ote.anchor_extreme == 2660.0
    assert ote.ote_sweet_spot == pytest.approx(2660.0 - 0.705 * 60.0, abs=0.05)
    assert ote.tap_and_close_triggered is True


def test_p9_p10_p11_draw_on_liquidity_and_three_point_turn():
    t0 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    taken_pool = StopClusterPool("p1", "XAUUSD", Timeframe.M5, "BSL", 2680.0, 1, 1, t0, "taken")
    untapped_pool = StopClusterPool("p2", "XAUUSD", Timeframe.M5, "EQH", 2690.0, 2, 2, t0, "untapped")

    # Only taken pool -> no draw!
    assert get_draw_on_liquidity(OrderType.BUY, 2655.0, [taken_pool]) is None
    ok, _, reason = validate_draw_on_liquidity(OrderType.BUY, 2655.0, 2650.0, None, min_rr=2.0)
    assert ok is False and "NO_DRAW" in reason

    # Untapped pool -> valid draw with R:R = (2690-2655)/(2655-2650) = 7.0
    draw = get_draw_on_liquidity(OrderType.BUY, 2655.0, [taken_pool, untapped_pool])
    assert draw is not None and draw.price == 2690.0
    ok2, rr2, _ = validate_draw_on_liquidity(OrderType.BUY, 2655.0, 2650.0, draw, min_rr=2.0)
    assert ok2 is True and rr2 == pytest.approx(7.0)

    # P11 grading: A+ vs B vs INVALID (2 of 3 fails when SMT fails)
    assert evaluate_three_point_turn(True, True, "CONFIRMED").grade == "A+"
    assert evaluate_three_point_turn(True, True, "UNKNOWN").grade == "B"
    assert evaluate_three_point_turn(True, True, "FAILED").grade == "INVALID"
    assert evaluate_three_point_turn(True, False, "CONFIRMED").grade == "INVALID"


# ============================================================================
# 3. NAMED SETUPS S1-S10 TESTS (LONG + SHORT MIRROR + NEGATIVE)
# ============================================================================

def test_s1_s2_s3_long_short_mirror_and_negative_cases():
    eng = VideoSetupEngine()
    # 10:00 NY AM (EST = 15:00 UTC) -> inside Silver Bullet NY AM + NY Macro 1
    sb_start = datetime(2026, 1, 15, 13, 45, tzinfo=timezone.utc)  # last bar (idx 16) at 15:05 UTC = 10:05 NY!
    xau_bull, jpy_bull = build_bullish_raid_shift_fvg(sb_start)
    xau_bear, jpy_bear = build_bearish_raid_shift_fvg(sb_start)

    # S1 Long + Short Mirror (A+ with inverse SMT)
    sig_l = eng.detect_s1_raid_shift_fvg_ce(
        "XAUUSD", Timeframe.M5, xau_bull, OrderType.BUY,
        correlated_symbol="USDJPY", correlated_candles=jpy_bull, inverse_pair=True,
    )
    assert sig_l is not None
    assert sig_l.setup_id == "S1_RAID_SHIFT_FVG_CE"
    assert sig_l.three_point_grade == "A+"
    assert sig_l.entry_model == "CE"
    assert sig_l.risk_reward >= 2.0

    sig_s = eng.detect_s1_raid_shift_fvg_ce(
        "XAUUSD", Timeframe.M5, xau_bear, OrderType.SELL,
        correlated_symbol="USDJPY", correlated_candles=jpy_bear, inverse_pair=True,
    )
    assert sig_s is not None and sig_s.direction == OrderType.SELL and sig_s.three_point_grade == "A+"

    # S2 Silver Bullet inside window -> PASS; outside window (12:30 NY = 17:30 UTC) -> None!
    sig_sb = eng.detect_s2_silver_bullet(
        "XAUUSD", Timeframe.M5, xau_bull,
        correlated_symbol="USDJPY", correlated_candles=jpy_bull, inverse_pair=True,
    )
    assert sig_sb is not None and sig_sb.setup_id == "S2_SILVER_BULLET" and sig_sb.context == "SILVER_BULLET"

    off_window, off_jpy = build_bullish_raid_shift_fvg(datetime(2026, 1, 15, 16, 15, tzinfo=timezone.utc))
    assert eng.detect_s2_silver_bullet("XAUUSD", Timeframe.M5, off_window, correlated_symbol="USDJPY", correlated_candles=off_jpy) is None

    # S3 NY Macro inside 09:50-10:10 NY -> PASS; outside -> None!
    sig_mac = eng.detect_s3_ny_macro(
        "XAUUSD", Timeframe.M5, xau_bull,
        correlated_symbol="USDJPY", correlated_candles=jpy_bull, inverse_pair=True,
    )
    assert sig_mac is not None and sig_mac.setup_id == "S3_NY_MACRO" and sig_mac.metadata["cancel_on_window_end"] is True
    assert eng.detect_s3_ny_macro("XAUUSD", Timeframe.M5, off_window, correlated_symbol="USDJPY", correlated_candles=off_jpy) is None

    # Negative: S1 without SMT when allow_b_grade=False -> rejected!
    assert eng.detect_s1_raid_shift_fvg_ce("XAUUSD", Timeframe.M5, xau_bull, OrderType.BUY) is None


def test_s4_judas_and_s5_asian_sd_and_s10_session_sweep():
    eng = VideoSetupEngine(config={"setups": {
        "S4_LONDON_JUDAS_SWING": {"enabled": True, "min_rr": 1.5, "allow_b_grade": True},
        "S5_ASIAN_SD_REVERSAL": {"enabled": True, "min_rr": 1.5, "allow_b_grade": True},
        "S10_SESSION_SWEEP_REVERSAL": {"enabled": True, "min_rr": 1.5, "allow_b_grade": True},
    }})
    t0 = datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)
    xau_bull, _ = build_bullish_raid_shift_fvg(t0, base=2650.0)
    xau_bear, _ = build_bearish_raid_shift_fvg(t0, base=2650.0)

    # S4 Judas Long (sweeps Asian Low 2650.0 -> targets Asian High 2668.0) & Short Mirror
    s4_l = eng.detect_s4_london_judas("XAUUSD", Timeframe.M5, xau_bull, asian_high=2668.0, asian_low=2650.0)
    assert s4_l is not None and s4_l.direction == OrderType.BUY and s4_l.take_profit == 2668.0
    s4_s = eng.detect_s4_london_judas("XAUUSD", Timeframe.M5, xau_bear, asian_high=2650.0, asian_low=2632.0)
    assert s4_s is not None and s4_s.direction == OrderType.SELL and s4_s.take_profit == 2632.0
    # Negative S4: invalid range
    assert eng.detect_s4_london_judas("XAUUSD", Timeframe.M5, xau_bull, asian_high=2640.0, asian_low=2650.0) is None

    # S5 Asian SD: Asian range 2664..2671 (rng=7) -> -2 SD = 2650, -2.5 SD = 2646.5 -> sweep low=2647.8 is in [-2.5..-2] SD, R:R > 1.5!
    s5_l = eng.detect_s5_asian_sd_reversal("XAUUSD", Timeframe.M5, xau_bull, asian_high=2671.0, asian_low=2664.0)
    assert s5_l is not None and s5_l.setup_id == "S5_ASIAN_SD_REVERSAL" and s5_l.take_profit == 2664.0
    assert s5_l.metadata["runner_enabled"] is True

    # S10 Session Sweep: PDL=2650 swept -> targets PD Mid=2665.0
    kl = SessionKeyLevels(symbol="XAUUSD", date="2026-01-15", pdh=2680.0, pdl=2650.0, pd_mid=2665.0)
    s10_l = eng.detect_s10_session_sweep_reversal("XAUUSD", Timeframe.M5, xau_bull, kl)
    assert s10_l is not None and s10_l.setup_id == "S10_SESSION_SWEEP_REVERSAL" and s10_l.take_profit == 2665.0


def test_s6_ifvg_s7_breaker_overlap_s8_ote_s9_hidden_demand():
    eng = VideoSetupEngine(config={"setups": {
        "S6_IFVG_STOP_HUNT": {"enabled": True, "min_rr": 1.2, "allow_b_grade": True},
        "S7_STACKED_BREAKER_IFVG": {"enabled": True, "min_rr": 1.2, "allow_b_grade": True},
        "S8_OTE_STOP_HUNT_BOS": {"enabled": True, "min_rr": 1.2, "allow_b_grade": True},
        "S9_HIDDEN_DEMAND_SUPPLY": {"enabled": True, "min_rr": 1.2, "allow_b_grade": True},
    }})
    t0 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    kl_draw_high = SessionKeyLevels(symbol="XAUUSD", date="2026-01-15", pdh=2690.0, pdl=2620.0)

    # S6 IFVG after stop hunt (SSL equal lows at 2650 -> bearish FVG before stop hunt -> sweep below 2650 -> close above FVG top)
    s6_specs = [
        (2662, 2664, 2660, 2661),    # 0: lead-in for left=2 swing low
        (2660, 2662, 2658, 2659),    # 1
        (2659, 2661, 2650.0, 2656),  # 2: EQL #1 at 2650
        (2656, 2660, 2655, 2659),    # 3
        (2659, 2661, 2654, 2657),    # 4
        (2657, 2660, 2650.1, 2656),  # 5: EQL #2 at 2650.1 (left=2, right=2)
        (2656, 2658, 2655, 2656),    # 6: c0 for bearish FVG (low=2655)
        (2656, 2656.5, 2650.5, 2651),  # 7: impulse down
        (2651, 2652, 2650.2, 2651),  # 8: c2 high=2652 < 2655 -> bearish FVG [2652..2655]
        (2651, 2652, 2647.5, 2651.5),  # 9: stop hunt sweep below 2650 + reclaim!
        (2651.5, 2660, 2651, 2659),  # 10: closes decisively above 2655 -> bullish IFVG!
        (2659, 2659.5, 2654, 2658),  # 11: retest of IFVG
    ]
    c_s6 = [mk_candle(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(s6_specs)]
    s6 = eng.detect_s6_ifvg_stop_hunt("XAUUSD", Timeframe.M5, c_s6, key_levels=kl_draw_high)
    assert s6 is not None and s6.setup_id == "S6_IFVG_STOP_HUNT" and s6.direction == OrderType.BUY
    assert s6.entry_model == "IFVG_RETEST"
    # Negative S6: too few candles -> None
    assert eng.detect_s6_ifvg_stop_hunt("XAUUSD", Timeframe.M5, c_s6[:4], key_levels=kl_draw_high) is None

    # S7 Stacked Breaker + IFVG Overlap (SELL: bullish FVG + bullish OB in same [2654..2658] zone both broken downward)
    s7_specs = [
        (2650, 2652, 2649, 2651),
        (2651, 2654, 2650, 2653.5),  # c0 for bullish FVG (high=2654)
        (2653.5, 2659, 2653, 2658.5),  # impulse up
        (2658.5, 2663, 2657.5, 2662),  # c2 low=2657.5 > 2654 -> bullish FVG [2654..2657.5]
        (2662, 2663, 2655.0, 2656.0),  # bearish candle (Bullish OB [2655..2663]) overlapping FVG!
        (2656, 2665, 2655.5, 2664),
        (2664, 2667, 2663, 2666),    # 2nd bullish impulse bar confirming Bullish OB
        (2666, 2666.5, 2648, 2649),  # closes below 2654 -> flips BOTH Bullish OB -> Bearish Breaker & FVG -> Bearish IFVG!
        (2649, 2656, 2648, 2650),    # retest of overlap zone
    ]
    c_s7 = [mk_candle(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(s7_specs)]
    s7 = eng.detect_s7_stacked_breaker_ifvg("XAUUSD", Timeframe.M5, c_s7, key_levels=kl_draw_high)
    assert s7 is not None and s7.setup_id == "S7_STACKED_BREAKER_IFVG" and s7.direction == OrderType.SELL
    assert s7.entry_model == "BREAKER_OVERLAP"
    # Negative S7: no draw on liquidity -> None
    assert eng.detect_s7_stacked_breaker_ifvg("XAUUSD", Timeframe.M5, c_s7, key_levels=None) is None

    # S8 OTE Long
    specs_ote = [
        (2615, 2618, 2610, 2612),
        (2612, 2614, 2600, 2605),
        (2605, 2616, 2604, 2615),
        (2615, 2620, 2614, 2618),
        (2618, 2619, 2612, 2614),
        (2614, 2616, 2610, 2615),
        (2615, 2640, 2615, 2638),
        (2638, 2642, 2635, 2636),
        (2636, 2660, 2636, 2658),
        (2658, 2659, 2640, 2642),
        (2642, 2643, 2617, 2624),
    ]
    c_ote = [mk_candle(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(specs_ote)]
    s8 = eng.detect_s8_ote_stop_hunt_bos("XAUUSD", Timeframe.M5, c_ote)
    assert s8 is not None and s8.setup_id == "S8_OTE_STOP_HUNT_BOS" and s8.entry_model == "OTE"

    # S9 Hidden Demand (H1 wick-to-wick gap behind BOS -> M5 LTF OB refinement)
    htf = [
        mk_candle(t0 + timedelta(hours=0), 2610, 2615, 2608, 2612),
        mk_candle(t0 + timedelta(hours=1), 2612, 2614, 2609, 2611),
        mk_candle(t0 + timedelta(hours=2), 2611, 2616, 2610, 2613),  # c_prev high=2616
        mk_candle(t0 + timedelta(hours=3), 2613, 2626, 2612.5, 2625),  # BOS impulse > 2616
        mk_candle(t0 + timedelta(hours=4), 2625, 2645, 2622, 2642),  # c_next low=2622 > c_prev.high=2616 -> hidden gap [2616..2622]
        mk_candle(t0 + timedelta(hours=5), 2642, 2648, 2635, 2640),
    ]
    ltf = [
        mk_candle(t0 + timedelta(hours=3, minutes=0), 2620, 2621, 2617, 2618),  # bearish LTF OB inside [2616..2622]!
        mk_candle(t0 + timedelta(hours=3, minutes=5), 2618, 2624, 2617.5, 2623),
        mk_candle(t0 + timedelta(hours=3, minutes=10), 2623, 2628, 2622, 2627),
        mk_candle(t0 + timedelta(hours=3, minutes=15), 2627, 2633, 2626, 2632),
        mk_candle(t0 + timedelta(hours=3, minutes=20), 2632, 2638, 2631, 2636),
    ]
    s9 = eng.detect_s9_hidden_demand_supply("XAUUSD", htf, ltf)
    assert s9 is not None and s9.setup_id == "S9_HIDDEN_DEMAND_SUPPLY" and s9.entry_model == "LTF_OB_LIMIT"
    assert s9.metadata["ltf_ob_refined"] is True


# ============================================================================
# 4. SAFETY, TRADE MANAGEMENT, CONFIG, TELEGRAM & KNOWLEDGE EXPORT TESTS
# ============================================================================

def test_safety_reference_symbols_can_never_be_traded():
    uni = SpecializedSymbolUniverse()
    for ref in DATA_ONLY_REFERENCE_SYMBOLS:
        assert uni.is_reference_only(ref) is True
        assert uni.is_approved(ref) is False
        ok, err = uni.validate_or_reject(ref)
        assert ok is False and err is not None
    # Approved tradable universe unchanged
    assert uni.is_approved("XAUUSD") is True
    assert uni.is_approved("BTCUSD") is True


def test_safety_tighten_only_runner_and_invalidation_exit():
    mgr = TradeManagementEngine()
    pos = Position(
        ticket=9001, symbol="XAUUSD", order_type=OrderType.BUY,
        volume=0.10, open_price=2650.0, current_price=2662.0,
        stop_loss=2645.0, take_profit=2675.0, profit=120.0,
    )
    # Rule R9.3: widening stop (2640 < 2645) MUST be rejected
    assert mgr.is_tighter_stop(OrderType.BUY, 2645.0, 2640.0) is False
    assert mgr.is_tighter_stop(OrderType.BUY, 2645.0, 0.0) is False
    assert mgr.is_tighter_stop(OrderType.BUY, 2645.0, 2650.5) is True

    # Runner TP1 hit -> partial 50% + BE move (strictly tighter than 2645.0)
    actions = mgr.evaluate_video_runner_management(
        pos, current_price=2662.0, first_target_price=2660.0, partial_pct=0.50, cost_buffer=0.5
    )
    types = [a.action_type for a in actions]
    assert "PARTIAL_CLOSE" in types and "MODIFY_SL" in types
    sl_act = next(a for a in actions if a.action_type == "MODIFY_SL")
    assert sl_act.new_sl == 2650.5 and sl_act.new_sl > pos.stop_loss

    # Invalidation exit when bar closes below invalidation_price
    bad_bar = mk_candle(datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc), 2649, 2650, 2643, 2644.0)
    inv_act = mgr.evaluate_invalidation_exit(pos, bad_bar, invalidation_price=2645.0)
    assert inv_act is not None and inv_act.action_type == "FULL_CLOSE"


def test_config_validator_fails_closed_on_bad_values():
    with pytest.raises(VideoConfigValidationError):
        validate_video_setups_config({"execution_mode_for_new_setups": "LIVE_REAL"})
    with pytest.raises(VideoConfigValidationError):
        validate_video_setups_config({"setups": {"S1_RAID_SHIFT_FVG_CE": {"min_rr": 0.1}}})
    with pytest.raises(VideoConfigValidationError):
        validate_video_setups_config({"setups": {"S1_RAID_SHIFT_FVG_CE": {"partial_pct": 1.5}}})


def test_telegram_trade_setup_line_and_knowledge_export_schema():
    renderer = TemplateRenderer()
    ev = TradeSetupEvent(
        symbol="XAUUSD", direction="BUY", entry_price=2653.35, stop_loss=2647.50,
        take_profit=2667.00, rr_ratio=2.33, lots=0.05, risk_pct=0.5,
        setup_id="S2_SILVER_BULLET", context="SILVER_BULLET",
        three_point_grade="A+", entry_model="CE", draw_on_liquidity="BSL@2667.00",
    )
    html_msg = renderer.render(ev)
    assert "S2_SILVER_BULLET" in html_msg
    assert "Grade A+" in html_msg
    assert "BSL@2667.00" in html_msg

    # Verify knowledge JSON export schema
    export_path = Path("knowledge/exports/video_skills_2026-11.json")
    assert export_path.exists()
    data = json.loads(export_path.read_text(encoding="utf-8"))
    assert len(data["primitives"]) == 11
    assert len(data["setups"]) == 10
    assert len(data["documented_failure_modes"]) == 4
    assert "EDUCATIONAL" in data["disclaimer"].upper()
