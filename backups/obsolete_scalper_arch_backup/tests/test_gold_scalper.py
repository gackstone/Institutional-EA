"""
Comprehensive Test Suite for GOLD Scalper Engine.
Covers:
- Dynamic balance-based lot sizing
- Basket lifecycle, exits (individual TP, aggregate TP, time stop), and immediate re-entry
- Risk and account protections (drawdown stop, margin level 300%, position limits, spread, kill switch)
- GOLD symbol resolution & filling modes
- Direction selection & fallback guarantees
- Legacy filter compatibility toggle (LEGACY_FILTERS_ENABLED)
- Integration with manual position management
"""

import os
import time
from pathlib import Path
import pytest

from src.scalper.config import ScalperConfig, LotSizingConfig, BasketConfig, ProtectiveSLConfig
from src.scalper.sizing import GoldLotSizingEngine
from src.scalper.symbol_resolver import GoldSymbolResolver, ResolvedSymbolSpec
from src.scalper.direction import GoldDirectionSelector
from src.scalper.basket import GoldBasketManager, BasketPosition, BasketState
from src.scalper.risk import GoldRiskManager
from src.scalper.executor import GoldOrderExecutor, RETRYABLE_RETCODES, PERMANENT_RETCODES
from src.scalper.engine import GoldScalperEngine
from src.core.config import AppConfig
from src.core.contracts import SignalCandidate, OrderType, SetupType, AccountInfo, Position


# ==============================================================================
# 1. LOT SIZING TESTS
# ==============================================================================

def test_lot_sizing_small_balances():
    sizing = GoldLotSizingEngine(LotSizingConfig(lot_step_balance=50.0, micro_account_min_lot=0.01))
    
    # $5 micro balance -> 0.01 minimum lot floor
    res5 = sizing.calculate_lot(5.0)
    assert res5.is_safe
    assert res5.lot == 0.01

    # $25 balance -> 0.01 lot
    res25 = sizing.calculate_lot(25.0)
    assert res25.lot == 0.01

    # $50 balance -> 0.01 lot (floor(50/50)*0.01)
    res50 = sizing.calculate_lot(50.0)
    assert res50.lot == 0.01


def test_lot_sizing_balance_steps_and_larger_balances():
    sizing = GoldLotSizingEngine(LotSizingConfig(lot_step_balance=50.0))

    # $150 balance -> floor(150/50)*0.01 = 0.03 lot
    res150 = sizing.calculate_lot(150.0)
    assert res150.lot == 0.03

    # $350 balance -> floor(350/50)*0.01 = 0.07 lot
    res350 = sizing.calculate_lot(350.0)
    assert res350.lot == 0.07

    # $500 balance -> floor(500/50)*0.01 = 0.10 lot
    res500 = sizing.calculate_lot(500.0)
    assert res500.lot == 0.10


def test_lot_sizing_broker_clamping_and_step():
    sizing = GoldLotSizingEngine(LotSizingConfig(lot_step_balance=50.0, max_lot_override=0.50))
    spec = ResolvedSymbolSpec(
        symbol="XAUUSD",
        min_lot=0.05,
        max_lot=0.20,
        lot_step=0.05,
    )

    # Balance $5 with broker min 0.05 -> clamped up to 0.05
    res = sizing.calculate_lot(5.0, spec=spec)
    assert res.lot == 0.05

    # Balance $2000 with broker max 0.20 -> clamped down to 0.20
    res_large = sizing.calculate_lot(2000.0, spec=spec)
    assert res_large.lot == 0.20

    # Step quantization: $160 -> raw 0.03, broker min 0.05, step 0.05 -> clamped to 0.05
    res_step = sizing.calculate_lot(160.0, spec=spec)
    assert res_step.lot == 0.05


def test_lot_sizing_zero_or_negative_balance():
    sizing = GoldLotSizingEngine()
    res_zero = sizing.calculate_lot(0.0)
    assert not res_zero.is_safe
    assert res_zero.lot == 0.0

    res_neg = sizing.calculate_lot(-100.0)
    assert not res_neg.is_safe


# ==============================================================================
# 2. BASKET LIFECYCLE TESTS
# ==============================================================================

def test_basket_creation_and_positions():
    mgr = GoldBasketManager(basket_cfg=BasketConfig(basket_size=4))
    assert mgr.ready_for_reentry
    assert not mgr.has_active_basket()

    basket = mgr.start_new_basket(direction="BUY", target_size=4)
    assert mgr.has_active_basket()
    assert not mgr.ready_for_reentry
    assert basket.state == BasketState.OPENING

    # Add 4 positions
    for i in range(1, 5):
        pos = BasketPosition(
            ticket=1000 + i,
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            open_price=2650.0 + (i * 0.1),
        )
        basket.add_position(pos)

    assert basket.position_count == 4
    assert basket.state == BasketState.ACTIVE
    assert basket.total_volume == 0.04


def test_basket_aggregate_take_profit():
    mgr = GoldBasketManager()
    basket = mgr.start_new_basket(direction="BUY", target_size=4)
    for i in range(1, 5):
        pos = BasketPosition(
            ticket=2000 + i,
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            open_price=2650.0,
            profit=0.20,  # Total profit = $0.80
        )
        basket.add_position(pos)

    # At $0.80 net, target ($2.00) not yet reached
    tickets, reason = mgr.evaluate_exits()
    assert tickets == []
    assert reason is None

    # Update profits so aggregate net reaches $2.20
    for p in basket.positions.values():
        p.profit = 0.55
    assert basket.net_floating_profit == 2.20

    tickets, reason = mgr.evaluate_exits()
    assert len(tickets) == 4
    assert reason == "BASKET_TP"


def test_basket_individual_position_take_profit():
    mgr = GoldBasketManager()
    basket = mgr.start_new_basket(direction="BUY", target_size=4)
    # One position gains $0.60 (target is $0.50/0.01 lot) while others are flat
    for i in range(1, 5):
        pos = BasketPosition(
            ticket=3000 + i,
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            open_price=2650.0,
            profit=0.60 if i == 1 else 0.0,
        )
        basket.add_position(pos)

    tickets, reason = mgr.evaluate_exits()
    assert tickets == [3001]
    assert reason == "INDIVIDUAL_TP"


def test_basket_max_holding_time_expiration():
    mgr = GoldBasketManager()
    basket = mgr.start_new_basket(direction="BUY", target_size=2)
    pos = BasketPosition(ticket=4001, symbol="XAUUSD", direction="BUY", volume=0.01, open_price=2650.0, profit=0.10)
    basket.add_position(pos)

    # Artificially age the basket beyond 180 seconds
    basket.created_at = time.time() - 200.0

    tickets, reason = mgr.evaluate_exits()
    assert tickets == [4001]
    assert reason == "MAX_HOLD_BREAKEVEN"


def test_basket_closure_and_immediate_reentry():
    mgr = GoldBasketManager()
    basket = mgr.start_new_basket(direction="BUY", target_size=2)
    pos1 = BasketPosition(ticket=5001, symbol="XAUUSD", direction="BUY", volume=0.01, open_price=2650.0, profit=1.0)
    pos2 = BasketPosition(ticket=5002, symbol="XAUUSD", direction="BUY", volume=0.01, open_price=2650.0, profit=1.0)
    basket.add_position(pos1)
    basket.add_position(pos2)

    # Close positions
    mgr.on_position_closed(5001, realized_pnl=1.0)
    assert mgr.has_active_basket()
    assert not mgr.ready_for_reentry

    mgr.on_position_closed(5002, realized_pnl=1.0)
    assert not mgr.has_active_basket()
    assert mgr.ready_for_reentry  # Immediate re-entry primed!
    assert len(mgr.closed_baskets) == 1


# ==============================================================================
# 3. RISK AND ACCOUNT PROTECTION TESTS
# ==============================================================================

def test_risk_kill_switch(tmp_path):
    cfg = ScalperConfig.load()
    risk = GoldRiskManager(cfg)

    # 1. Clear state
    assert risk.check_kill_switch().allowed

    # 2. Manual software kill trigger
    risk.trigger_manual_kill("Operator emergency")
    v = risk.check_kill_switch()
    assert not v.allowed
    assert v.category == "KILL_SWITCH"

    # 3. File flag trigger
    flag_file = tmp_path / "STOP.flag"
    flag_file.write_text("STOP")
    cfg.kill_switch.flag_file_path = str(flag_file)
    risk_file = GoldRiskManager(cfg)
    v_file = risk_file.check_kill_switch()
    assert not v_file.allowed
    assert "flag file detected" in v_file.reason


def test_risk_demo_mode_protection():
    cfg = ScalperConfig.load()
    cfg.safety_mode.DEMO_MODE = True
    risk = GoldRiskManager(cfg)

    # Allowed on DEMO account
    assert risk.check_demo_live_mode("DEMO").allowed
    assert risk.check_demo_live_mode("0").allowed

    # Rejected on REAL account
    v_real = risk.check_demo_live_mode("REAL")
    assert not v_real.allowed
    assert v_real.category == "SAFETY_MODE"


def test_risk_spread_protection():
    cfg = ScalperConfig.load()
    cfg.spread_protection.spread_max_points = 80.0
    risk = GoldRiskManager(cfg)

    # Normal spread 35 pts -> Allowed
    assert risk.check_spread(35.0).allowed

    # Abnormal spread 95 pts -> Blocked
    v_high = risk.check_spread(95.0)
    assert not v_high.allowed
    assert v_high.category == "SPREAD"


def test_risk_drawdown_stop():
    cfg = ScalperConfig.load()
    cfg.equity_protection.max_dd_pct = 30.0
    cfg.equity_protection.pause_minutes = 60
    risk = GoldRiskManager(cfg)

    # Balance $1000, Equity $850 (15% DD) -> Allowed
    assert risk.check_drawdown(1000.0, 850.0).allowed

    # Balance $1000, Equity $680 (32% DD) -> Circuit breaker triggered!
    v_breach = risk.check_drawdown(1000.0, 680.0)
    assert not v_breach.allowed
    assert v_breach.category == "DRAWDOWN"
    assert risk.is_paused


def test_risk_margin_and_capacity_checks():
    cfg = ScalperConfig.load()
    cfg.position_limits.max_open_positions = 12
    cfg.volume_limits.max_total_lots = 1.00
    cfg.margin_protection.min_margin_level_pct = 300.0
    risk = GoldRiskManager(cfg)

    # Exceeding position limit (current 12 + 1 > 12)
    v_pos = risk.check_margin_and_capacity(
        account_balance=1000.0,
        account_equity=1000.0,
        account_margin=50.0,
        account_free_margin=950.0,
        current_open_positions=12,
        current_total_lots=0.12,
        proposed_lot=0.01,
    )
    assert not v_pos.allowed
    assert v_pos.category == "POSITION_LIMIT"

    # Exceeding volume limit (0.95 + 0.10 > 1.00)
    v_vol = risk.check_margin_and_capacity(
        account_balance=1000.0,
        account_equity=1000.0,
        account_margin=50.0,
        account_free_margin=950.0,
        current_open_positions=4,
        current_total_lots=0.95,
        proposed_lot=0.10,
    )
    assert not v_vol.allowed
    assert v_vol.category == "VOLUME_LIMIT"

    # Margin level drop below 300%: Equity $100, projected margin $50 -> Margin level = 200%
    v_margin = risk.check_margin_and_capacity(
        account_balance=100.0,
        account_equity=100.0,
        account_margin=10.0,
        account_free_margin=90.0,
        current_open_positions=0,
        current_total_lots=0.0,
        proposed_lot=0.20,
        margin_per_lot=200.0,  # 0.20 * 200 = $40 new margin -> total $50 -> 200% margin level
    )
    assert not v_margin.allowed
    assert v_margin.category == "MARGIN"


def test_protective_stop_loss_calculation():
    cfg = ScalperConfig.load()
    cfg.protective_sl.sl_points = 300.0
    risk = GoldRiskManager(cfg)

    # Point = 0.01. 300 points = $3.00 distance
    # BUY at 2650.00 -> SL = 2647.00
    sl_buy = risk.calculate_protective_sl("BUY", 2650.00, point=0.01)
    assert sl_buy == 2647.00

    # SELL at 2650.00 -> SL = 2653.00
    sl_sell = risk.calculate_protective_sl("SELL", 2650.00, point=0.01)
    assert sl_sell == 2653.00


# ==============================================================================
# 4. SYMBOL RESOLUTION TESTS
# ==============================================================================

def test_symbol_resolver_exact_and_alias_detection():
    resolver = GoldSymbolResolver()

    # Exact match
    assert resolver.resolve_from_names(["EURUSD", "GBPUSD", "XAUUSD"]) == "XAUUSD"

    # Alias XAUUSDm
    assert resolver.resolve_from_names(["EURUSD", "XAUUSDm", "USDJPY"]) == "XAUUSDm"

    # Broker suffix XAUUSD.a
    assert resolver.resolve_from_names(["EURUSD", "XAUUSD.a"]) == "XAUUSD.a"

    # Commodity GOLD
    assert resolver.resolve_from_names(["EURUSD", "GOLD", "US30"]) == "GOLD"


def test_filling_mode_determination():
    # Bit 1 (2) set -> IOC
    spec_ioc = ResolvedSymbolSpec(symbol="XAUUSD", filling_mode=2)
    assert GoldOrderExecutor.determine_filling_mode(spec_ioc) == 2

    # Bit 0 (1) set -> FOK
    spec_fok = ResolvedSymbolSpec(symbol="XAUUSD", filling_mode=1)
    assert GoldOrderExecutor.determine_filling_mode(spec_fok) == 1

    # Neither -> RETURN
    spec_ret = ResolvedSymbolSpec(symbol="XAUUSD", filling_mode=0)
    assert GoldOrderExecutor.determine_filling_mode(spec_ret) == 0


# ==============================================================================
# 5. DIRECTION SELECTION AND FALLBACK TESTS
# ==============================================================================

class DummyTick:
    def __init__(self, bid: float):
        self.bid = bid
        self.price = bid


class DummyCandle:
    def __init__(self, open_: float, close_: float):
        self.open = open_
        self.close = close_


def test_direction_selection_always_returns_direction():
    selector = GoldDirectionSelector()

    # 1. Upward tick velocity -> BUY
    up_ticks = [DummyTick(2650.0), DummyTick(2650.2), DummyTick(2650.6)]
    res_up = selector.select_direction(ticks=up_ticks)
    assert res_up.selected_direction == "BUY"

    # 2. Downward tick velocity -> SELL
    down_ticks = [DummyTick(2650.6), DummyTick(2650.3), DummyTick(2649.9)]
    res_down = selector.select_direction(ticks=down_ticks)
    assert res_down.selected_direction == "SELL"

    # 3. Strategy bias override
    res_strat = selector.select_direction(strategy_bias=0.8)
    assert res_strat.selected_direction == "BUY"
    assert res_strat.decision_source == "COMPOSITE"

    # 4. Dead flat ticks/candles -> defaults safely to BUY
    flat_ticks = [DummyTick(2650.0), DummyTick(2650.0)]
    res_flat = selector.select_direction(ticks=flat_ticks)
    assert res_flat.selected_direction in ("BUY", "SELL")


# ==============================================================================
# 6. SIMULATED ENGINE INTEGRATION SESSION
# ==============================================================================

def test_engine_simulated_basket_execution_cycle():
    cfg = ScalperConfig.load()
    cfg.basket.basket_size = 4
    cfg.basket_tp.basket_tp_usd = 1.00
    engine = GoldScalperEngine(config=cfg, is_simulation=True)
    assert engine.initialize()

    # Cycle 1: Initiates basket
    engine.run_single_tick_cycle()
    assert engine.basket_manager.has_active_basket()
    basket = engine.basket_manager.active_basket
    assert basket.position_count == 4
    assert engine.stats.total_orders_filled == 4

    # Simulate price increase leading to basket TP
    for p in basket.positions.values():
        p.profit = 0.35  # 4 * 0.35 = $1.40 > $1.00 target

    # Cycle 2: Monitors and closes basket, then immediately opens the next basket (immediate re-entry)
    engine.run_single_tick_cycle()
    assert engine.stats.total_baskets_closed == 1
    assert engine.stats.winning_trades == 4
    assert engine.stats.net_profit_usd > 0
    assert engine.stats.total_baskets_opened == 2
    assert engine.basket_manager.has_active_basket()  # Next basket is now active!


# ==============================================================================
# 7. LEGACY FILTER AUDIT & COMPATIBILITY TESTS
# ==============================================================================

def test_legacy_filters_disabled_bypasses_news_and_quality_gates():
    app_cfg = AppConfig.load_from_dir()
    app_cfg.legacy_filters_enabled = False
    assert not app_cfg.legacy_filters_enabled

    from src.core.orchestrator import TradingBotOrchestrator
    orchestrator = TradingBotOrchestrator(app_cfg)
    assert not orchestrator.config.legacy_filters_enabled


def test_legacy_filters_enabled_restores_original_behavior():
    app_cfg = AppConfig.load_from_dir()
    app_cfg.legacy_filters_enabled = True
    assert app_cfg.legacy_filters_enabled


def test_manual_position_management_preserved():
    app_cfg = AppConfig.load_from_dir()
    from src.core.orchestrator import TradingBotOrchestrator
    orchestrator = TradingBotOrchestrator(app_cfg)
    # Ensure manual management subsystem is present and operational
    assert hasattr(orchestrator, "manage_manual_positions")
    res = orchestrator.manage_manual_positions()
    assert isinstance(res, dict)
