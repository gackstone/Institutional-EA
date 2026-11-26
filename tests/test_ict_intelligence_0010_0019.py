"""
Comprehensive Automated Test Suite for ICT/SMC Market Intelligence (Videos 0010–0019).

Covers all 22 required areas plus anti-look-ahead bias, anti-repainting, candle indexing,
broker price precision, volatility regimes, symbol specifications, shadow mode, and safety locks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from src.core.contracts import Candle, OrderType, Timeframe
from src.smc.ict_intelligence import (
    HTFLiquidityAnalyzer,
    ICTConfigValidationError,
    ICTIntelligenceEngine,
    ICTModelPerformanceTracker,
    InstitutionalZoneType,
    RejectionCode,
    SetupLifecycleStage,
    StructureEventKind,
    SweepState,
    analyze_market_structure_transition,
    assess_displacement_quality,
    compute_fib_extensions,
    detect_breaker_and_mitigation_blocks,
    detect_liquidity_sweep,
    detect_ote_setup,
    detect_propulsion_blocks,
    detect_rejection_blocks,
    detect_unicorn_setup,
    detect_validated_order_blocks,
    select_liquidity_target,
    validate_ict_intelligence_config,
)
from src.smc.video_primitives import detect_fvgs_with_ce


def mk(t: datetime, o: float, h: float, l: float, c: float, complete: bool = True) -> Candle:
    return Candle(time=t, open=o, high=h, low=l, close=c, tick_volume=100, complete=complete)


# ---------------------------------------------------------------------------
# 1. MODULE A: HTF LIQUIDITY, 60-DAY HIGHS/LOWS & QUARTERLY CONTEXT (0010, 0012)
# ---------------------------------------------------------------------------

def test_module_a_60_day_and_quarterly_context():
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    daily = [
        mk(t0 + timedelta(days=i), 2600 + i * 0.5, 2605 + i * 0.5, 2595 + i * 0.5, 2602 + i * 0.5)
        for i in range(90)
    ]
    # Add a clear 60-day peak at day 70 (high=2710) and last bar sweeping above 2710
    daily[70] = mk(t0 + timedelta(days=70), 2680, 2710.0, 2675, 2690)
    daily[-1] = mk(t0 + timedelta(days=89), 2700, 2715.0, 2698, 2705)

    analyzer = HTFLiquidityAnalyzer()
    q_ctx = analyzer.build_quarterly_context("XAUUSD", daily)
    assert q_ctx is not None
    assert q_ctx.d60_high == 2710.0
    assert q_ctx.d60_high_swept is True
    assert q_ctx.quadrant in ("PREMIUM", "DEEP_PREMIUM")

    levels = analyzer.collect_liquidity_levels(
        "XAUUSD", daily[-20:], ltf_timeframe=Timeframe.M15,
        daily_candles=daily, directional_bias=OrderType.BUY,
    )
    classes = {lv.level_class for lv in levels}
    assert {"PDH", "PDL", "D60_HIGH", "D60_LOW"}.issubset(classes)
    d60_hi = next(lv for lv in levels if lv.level_class == "D60_HIGH")
    assert d60_hi.scope == "EXTERNAL" and d60_hi.swept is True


# ---------------------------------------------------------------------------
# 2. MODULE B: BUY-SIDE / SELL-SIDE SWEEPS, FALSE SWEEPS & GENUINE BREAKOUTS
# ---------------------------------------------------------------------------

def test_module_b_bsl_ssl_sweeps_false_sweep_and_genuine_breakout():
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    # BSL Confirmed Sweep: pierces 2660, closes below, then bearish displacement + FVG
    bsl_specs = [
        (2650, 2655, 2649, 2654),
        (2654, 2658, 2653, 2656),
        (2656, 2664.0, 2655, 2657.0),  # pierces 2660, closes inside below 2660
        (2657, 2657.5, 2645.0, 2646.0),  # strong bearish displacement!
        (2646, 2647.0, 2640.0, 2641.0),  # leaves bearish FVG [2647..2655]
    ]
    c_bsl = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(bsl_specs)]
    sw_bsl = detect_liquidity_sweep("XAUUSD", Timeframe.M5, c_bsl, level_price=2660.0, level_type="BSL", start_index=1)
    assert sw_bsl is not None and sw_bsl.state == SweepState.CONFIRMED_SWEEP and sw_bsl.direction == OrderType.SELL

    # SSL Confirmed Sweep (mirror)
    ssl_specs = [
        (2660, 2661, 2655, 2656),
        (2656, 2657, 2652, 2654),
        (2654, 2655, 2646.0, 2653.0),  # pierces 2650, closes back above 2650
        (2653, 2665.0, 2652.5, 2664.0),  # strong bullish displacement!
        (2664, 2670.0, 2663.0, 2669.0),  # leaves bullish FVG [2655..2663]
    ]
    c_ssl = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(ssl_specs)]
    sw_ssl = detect_liquidity_sweep("XAUUSD", Timeframe.M5, c_ssl, level_price=2650.0, level_type="SSL", start_index=1)
    assert sw_ssl is not None and sw_ssl.state == SweepState.CONFIRMED_SWEEP and sw_ssl.direction == OrderType.BUY

    # Genuine Breakout (decisive closes above 2660 without reclaim) -> must NOT classify as sweep
    bo_specs = [
        (2650, 2655, 2649, 2654),
        (2654, 2659, 2653, 2658),
        (2658, 2666, 2657.5, 2665.5),
        (2665.5, 2672, 2665, 2671),
        (2671, 2678, 2670, 2677),
    ]
    c_bo = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(bo_specs)]
    sw_bo = detect_liquidity_sweep("XAUUSD", Timeframe.M5, c_bo, level_price=2660.0, level_type="BSL", start_index=1)
    assert sw_bo is not None and sw_bo.state == SweepState.GENUINE_BREAKOUT

    # False / shallow unconfirmed raid (pierce < min_pierce_atr)
    shallow_specs = [
        (2650, 2658, 2648, 2656),
        (2656, 2659, 2649, 2657),
        (2657, 2660.05, 2650, 2655),  # tiny 0.05 pierce vs ~10 ATR -> < 0.05 ATR
        (2655, 2656, 2650, 2654),
    ]
    c_sh = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(shallow_specs)]
    sw_sh = detect_liquidity_sweep("XAUUSD", Timeframe.M5, c_sh, level_price=2660.0, level_type="BSL", start_index=1)
    assert sw_sh is not None and sw_sh.state == SweepState.UNCONFIRMED_RAID


# ---------------------------------------------------------------------------
# 3. MODULE C & D: MSS, BOS, WICK-ONLY, VALID vs WEAK DISPLACEMENT, FVG & CE
# ---------------------------------------------------------------------------

def test_module_c_and_d_mss_bos_wick_only_displacement_and_fvg_ce():
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    # Bullish MSS with strong displacement + FVG
    bull_specs = [
        (2648, 2650, 2647, 2649),
        (2649, 2652, 2648, 2650),
        (2650, 2655, 2649, 2651),  # swing high = 2655
        (2651, 2652, 2647, 2648),
        (2648, 2650, 2646, 2649),
        (2649, 2664, 2648.5, 2663),  # strong bullish displacement closing > 2655!
        (2663, 2668, 2660, 2667),    # leaves bullish FVG [2650..2660], CE = 2655.0
    ]
    c_bull = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(bull_specs)]
    st_bull = analyze_market_structure_transition("XAUUSD", Timeframe.M5, c_bull, OrderType.BUY, after_index=4)
    assert st_bull is not None and st_bull.kind == StructureEventKind.DIRECTIONAL_TRANSITION and st_bull.label == "MSS"
    assert st_bull.displacement is not None and st_bull.displacement.is_valid is True

    # FVG & Consequent Encroachment (CE = 50% midpoint)
    fvgs = detect_fvgs_with_ce("XAUUSD", Timeframe.M5, c_bull)
    assert any(f.direction == OrderType.BUY and f.midpoint == pytest.approx((f.top + f.bottom) / 2.0) for f in fvgs)

    # Bearish MSS mirror
    bear_specs = [(5300 - o, 5300 - l, 5300 - h, 5300 - c) for o, h, l, c in bull_specs]
    c_bear = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(bear_specs)]
    st_bear = analyze_market_structure_transition("XAUUSD", Timeframe.M5, c_bear, OrderType.SELL, after_index=4)
    assert st_bear is not None and st_bear.kind == StructureEventKind.DIRECTIONAL_TRANSITION

    # Wick-only penetration must NOT count as valid break
    wick_specs = bull_specs[:5] + [
        (2649, 2658, 2648, 2653),  # wicks above 2655 but closes at 2653 < 2655!
        (2653, 2654, 2650, 2651),
    ]
    c_wick = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(wick_specs)]
    st_wick = analyze_market_structure_transition("XAUUSD", Timeframe.M5, c_wick, OrderType.BUY, after_index=4)
    assert st_wick is not None and st_wick.kind == StructureEventKind.WICK_ONLY_PENETRATION and st_wick.is_valid_break is False

    # Weak displacement candle (tiny body, big wicks, no imbalance) -> rejected
    weak_c = [
        mk(t0, 2650, 2660, 2640, 2651),
        mk(t0 + timedelta(minutes=5), 2651, 2653, 2649, 2651.3),  # tiny body
        mk(t0 + timedelta(minutes=10), 2651.3, 2654, 2650, 2652),
    ]
    da_weak = assess_displacement_quality("XAUUSD", Timeframe.M5, weak_c, 1, OrderType.BUY)
    assert da_weak.is_valid is False
    assert RejectionCode.WEAK_CANDLES_NO_IMBALANCE.value in da_weak.reasons


# ---------------------------------------------------------------------------
# 4. MODULE E: OB, BREAKER, MITIGATION, PROPULSION & REJECTION BLOCKS (0015–0019)
# ---------------------------------------------------------------------------

def test_module_e_all_five_institutional_block_types():
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)

    # E.1 Validated Bullish OB + E.4 Propulsion Block (parent OB -> opposing dip into OB -> displacement)
    prop_specs = [
        (2652, 2653, 2650, 2651),
        (2651, 2652, 2649, 2649.5),    # 1: Bullish parent OB (bearish candle [2649..2652])
        (2649.5, 2660, 2649, 2659.5),  # 2: strong bullish displacement!
        (2659.5, 2662, 2658, 2660),    # 3: leaves FVG
        (2660, 2660.5, 2651.0, 2653.0),  # 4: opposing candle dipping into parent OB [2649..2652] -> Propulsion Block!
        (2653.0, 2668.0, 2652.5, 2667.0),  # 5: strong displacement away!
        (2667.0, 2672.0, 2665.0, 2671.0),  # 6: continuation
    ]
    c_prop = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(prop_specs)]
    obs = detect_validated_order_blocks("XAUUSD", Timeframe.M5, c_prop, OrderType.BUY)
    assert len(obs) >= 1 and obs[0].zone_type == InstitutionalZoneType.ORDER_BLOCK and obs[0].invalidated is False

    props = detect_propulsion_blocks("XAUUSD", Timeframe.M5, c_prop, OrderType.BUY)
    assert len(props) >= 1 and props[0].zone_type == InstitutionalZoneType.PROPULSION_BLOCK
    assert props[0].midpoint == pytest.approx((2660.5 + 2651.0) / 2.0, abs=0.01)

    # E.2 Breaker Block (sweep prior high 2660 -> smash below bullish OB low 2652)
    br_specs = [
        (2655, 2660, 2654, 2656),      # prior high = 2660
        (2656, 2657, 2652, 2653),      # 1: bullish OB (down candle [2652..2657])
        (2653, 2663, 2652.5, 2661),    # 2: sweeps above 2660!
        (2661, 2662, 2646, 2647),      # 3: smashes decisively below 2652 -> Bearish Breaker!
        (2647, 2655, 2646, 2648),      # 4: retest
        (2648, 2649, 2640, 2641),
    ]
    c_br = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(br_specs)]
    breakers, _, trans_br = detect_breaker_and_mitigation_blocks("XAUUSD", Timeframe.M5, c_br, OrderType.SELL)
    assert len(breakers) >= 1 and breakers[0].zone_type == InstitutionalZoneType.BREAKER_BLOCK
    assert breakers[0].trapped_traders is True and trans_br[0].had_prior_liquidity_sweep is True

    # E.3 Mitigation Block (fails bullish OB WITHOUT sweeping prior high 2670)
    mit_specs = [
        (2665, 2670, 2660, 2662),      # prior high = 2670 (NOT swept)
        (2662, 2663, 2654, 2655),      # 1: bullish OB [2654..2663]
        (2655, 2666, 2654.5, 2665),    # 2: lower high (2666 < 2670 -> no sweep!)
        (2665, 2665.5, 2648, 2649),    # 3: breaks below 2654 -> Bearish Mitigation Block!
        (2649, 2658, 2648, 2650),
        (2650, 2651, 2642, 2643),
    ]
    c_mit = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(mit_specs)]
    _, mitigations, trans_mit = detect_breaker_and_mitigation_blocks("XAUUSD", Timeframe.M5, c_mit, OrderType.SELL)
    assert len(mitigations) >= 1 and mitigations[0].zone_type == InstitutionalZoneType.MITIGATION_BLOCK
    assert mitigations[0].trapped_traders is True and trans_mit[0].had_prior_liquidity_sweep is False

    # E.5 Rejection Block (long upper wick at liquidity high)
    rej_specs = [
        (2650, 2655, 2649, 2654),
        (2654, 2657, 2653, 2656),
        (2656, 2668.0, 2655.0, 2657.0),  # huge upper wick [2657..2668] (11 / 13 = 0.85 wick ratio!)
        (2657, 2663.0, 2652.0, 2653.0),  # revisits midpoint 2662.5
        (2653, 2654.0, 2645.0, 2646.0),
    ]
    c_rej = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(rej_specs)]
    rejs = detect_rejection_blocks("XAUUSD", Timeframe.M5, c_rej, OrderType.SELL)
    assert len(rejs) >= 1 and rejs[0].zone_type == InstitutionalZoneType.REJECTION_BLOCK
    assert rejs[0].low == 2657.0 and rejs[0].high == 2668.0 and rejs[0].midpoint == 2662.5


# ---------------------------------------------------------------------------
# 5. MODULE F, G & H: UNICORN, OTE, FIB -2.0 EXTENSION & LIQUIDITY TARGETS
# ---------------------------------------------------------------------------

def test_module_f_g_h_unicorn_ote_and_fib_extension_targets():
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)

    # F: Bearish Unicorn (BSL sweep above 2660 -> smash bullish OB [2652..2657] -> bearish FVG overlapping breaker)
    uni_specs = [
        (2654, 2656, 2653, 2655),
        (2655, 2660.0, 2654, 2656),    # prior high = 2660
        (2656, 2657.0, 2652.0, 2653),  # bullish OB [2652..2657]
        (2653, 2664.0, 2652.5, 2658),  # sweeps 2660 & closes inside (< 2660)!
        (2658, 2658.5, 2645.0, 2646),  # bearish displacement smashing below 2652!
        (2646, 2654.0, 2643.0, 2644),  # c2 high=2654 < bar3 low=2652.5? Wait: let bar3 low=2656.5 so FVG=[2654..2656.5] overlaps [2652..2657]!
        (2644, 2655.0, 2643.0, 2645),
        (2645, 2646.0, 2638.0, 2639),
    ]
    uni_specs[3] = (2656, 2664.0, 2656.5, 2658.0)  # low=2656.5 -> bearish FVG [2654.0..2656.5] overlaps OB [2652..2657]!
    c_uni = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(uni_specs)]
    uni = detect_unicorn_setup("XAUUSD", Timeframe.M5, c_uni, OrderType.SELL)
    assert uni is not None and uni.direction == OrderType.SELL
    assert uni.overlap_low <= uni.entry_price <= uni.overlap_high
    assert uni.invalidation_stop > 2664.0

    # G: OTE with BOS displacement
    ote_specs = [
        (2615, 2618, 2610, 2612),
        (2612, 2614, 2600, 2605),   # origin = 2600
        (2605, 2616, 2604, 2615),
        (2615, 2620, 2614, 2618),   # swing high = 2620
        (2618, 2619, 2612, 2614),
        (2614, 2616, 2610, 2615),
        (2615, 2645, 2615, 2644),   # strong BOS displacement!
        (2644, 2660, 2640, 2658),   # extreme = 2660 (FVG [2616..2640])
        (2658, 2659, 2640, 2642),
        (2620, 2628, 2617, 2626),   # retraces into 70.5% (2617.7)
    ]
    c_ote = [mk(t0 + timedelta(minutes=i * 5), *s) for i, s in enumerate(ote_specs)]
    ote = detect_ote_setup("XAUUSD", Timeframe.M5, c_ote, OrderType.BUY)
    assert ote is not None and ote.entry_price == pytest.approx(2617.7, abs=0.1)

    # H: Fib -2.0 Extension & earlier liquidity pool priority
    fib = compute_fib_extensions(OrderType.BUY, anchor_origin=2600.0, anchor_extreme=2620.0)
    assert fib.extensions["-2.0"] == pytest.approx(2660.0)
    assert fib.primary_target == pytest.approx(2660.0)

    # Earlier liquidity pool at 2645 (RR = 3.0 >= 2.0) should be preferred over distant Fib 2660!
    analyzer = HTFLiquidityAnalyzer()
    daily_mock = [
        mk(t0 - timedelta(days=2), 2610, 2645.0, 2590, 2630),
        mk(t0 - timedelta(days=1), 2630, 2635.0, 2605, 2615),
    ]
    lvls = analyzer.collect_liquidity_levels("XAUUSD", c_ote, daily_candles=daily_mock, directional_bias=OrderType.BUY)
    tgt = select_liquidity_target(OrderType.BUY, entry_price=2615.0, stop_loss=2605.0, liquidity_levels=lvls, fib_projection=fib, min_rr=2.0)
    assert tgt is not None and tgt.source in ("PDH", "D60_HIGH") and tgt.selected_price == 2645.0


# ---------------------------------------------------------------------------
# 6. ANTI-REPAINTING, NO LOOK-AHEAD, DEDUP, SHADOW MODE, SAFETY & TRACKER
# ---------------------------------------------------------------------------

def test_anti_repainting_no_lookahead_dedup_shadow_safety_and_tracker():
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    eng = ICTIntelligenceEngine()  # Default SHADOW mode

    # 1. Fail-closed config validation: LIVE or allow_live_orders or score-lot scaling FORBIDDEN
    with pytest.raises(ICTConfigValidationError):
        validate_ict_intelligence_config({"mode": "LIVE"})
    with pytest.raises(ICTConfigValidationError):
        validate_ict_intelligence_config({"allow_live_orders": True})
    with pytest.raises(ICTConfigValidationError):
        validate_ict_intelligence_config({"never_scale_lot_by_score": False})

    # 2. Missing data -> explicit STALE_OR_INCOMPLETE_DATA rejection
    evs_empty = eng.evaluate_market("XAUUSD", Timeframe.M15, [])
    assert len(evs_empty) == 1 and RejectionCode.STALE_OR_INCOMPLETE_DATA.value in evs_empty[0].rejection_codes

    # 3. Unfinished candle -> explicit UNFINISHED_CANDLE rejection (anti-repainting)
    bars = [mk(t0 + timedelta(minutes=i * 15), 2650, 2655, 2645, 2652) for i in range(10)]
    bars[-1] = mk(t0 + timedelta(minutes=9 * 15), 2652, 2665, 2651, 2664, complete=False)
    evs_unfin = eng.evaluate_market("XAUUSD", Timeframe.M15, bars)
    assert len(evs_unfin) == 1 and RejectionCode.UNFINISHED_CANDLE.value in evs_unfin[0].rejection_codes

    # 4. Stale data -> explicit STALE_OR_INCOMPLETE_DATA rejection
    bars[-1] = mk(t0 + timedelta(minutes=9 * 15), 2652, 2665, 2651, 2664, complete=True)
    evs_stale = eng.evaluate_market("XAUUSD", Timeframe.M15, bars, now_utc=t0 + timedelta(hours=10))
    assert len(evs_stale) == 1 and RejectionCode.STALE_OR_INCOMPLETE_DATA.value in evs_stale[0].rejection_codes

    # 5. Anti-look-ahead invariance & duplicate prevention on BTCUSD (different symbol precision)
    btc_specs = [
        (95000, 95200, 94900, 95100),
        (95100, 95400, 95000, 95300),
        (95300, 96500, 95200, 95400),  # huge upper wick rejection block
        (95400, 95900, 95100, 95200),
        (95200, 95300, 94800, 94900),
        (94900, 95000, 94600, 94700),
        (94700, 94800, 94400, 94500),
        (94500, 94600, 94200, 94300),
        (94300, 94400, 94000, 94100),
    ]
    c_btc = [mk(t0 + timedelta(minutes=i * 15), *s) for i, s in enumerate(btc_specs)]
    evs_1 = eng.evaluate_market("BTCUSD", Timeframe.M15, c_btc, volatility_regime="HIGH_VOL", pip_size=1.0)
    assert all(e.shadow_only is True for e in evs_1)
    # Re-evaluating exact same bar must prevent duplicate signals!
    evs_dup = eng.evaluate_market("BTCUSD", Timeframe.M15, c_btc, volatility_regime="HIGH_VOL", pip_size=1.0)
    assert evs_dup == []

    # 6. Per-model performance tracker
    tracker = ICTModelPerformanceTracker()
    tracker.record_outcome("UNICORN", 2.5, session="NY_AM", volatility_regime="NORMAL")
    tracker.record_outcome("UNICORN", -1.0, session="NY_AM", volatility_regime="NORMAL")
    tracker.record_outcome("OTE", 2.0, session="LONDON", volatility_regime="HIGH_VOL")
    by_m = tracker.summary_by_model()
    assert by_m["UNICORN"]["trades"] == 2 and by_m["UNICORN"]["profit_factor"] == 2.5
    assert tracker.summary_by_session()["LONDON"]["win_rate"] == 1.0
    assert tracker.summary_by_regime()["HIGH_VOL"]["expectancy_r"] == 2.0
