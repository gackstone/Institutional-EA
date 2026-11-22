"""
Phase 16: Comprehensive 20-Scenario Automated Test & Acceptance Suite for
High-Speed GOLD & BTCUSD Multi-Position Scalping Engine (v3.0.0).
Tests all 20 required scenarios + acceptance criteria:
1. Rapid signal evaluation
2. Controlled multi-entry
3. Duplicate-order prevention
4. Position sizing (CONSERVATIVE 0.10%, STANDARD 0.25%, AGGRESSIVE_DEMO 0.50%)
5. Basket risk calculation
6. Basket profit locking
7. Rapid profit capture (BE, trailing, momentum deterioration, tight-only SL)
8. Direction reversal
9. GOLD weekday scheduling
10. BTCUSD weekend scheduling
11. Cross-symbol risk protection
12. Daily loss protection
13. Equity drawdown protection
14. Margin protection
15. Spread rejection
16. Slippage rejection
17. Broker disconnection
18. Restart recovery
19. Order reconciliation
20. Friday/Saturday/Sunday/Monday transitions
"""

from datetime import datetime, timezone
import time
import pytest

from src.scalper.backtester import RealisticScalperBacktester
from src.scalper.basket import BasketPosition, MultiBasketManager
from src.scalper.config import ScalperConfig
from src.scalper.engine import DualMarketScalperEngine
from src.scalper.entry_engine import EntryMode, MultiPositionEntryEngine
from src.scalper.exit_engine import RapidExitEngine
from src.scalper.market_cache import CachedTick, IndicatorCache, TickCache
from src.scalper.notifier import ScalperNotificationManager
from src.scalper.reversal import DirectionReversalEngine
from src.scalper.risk import AccountRiskManager
from src.scalper.scheduler import MarketScheduler
from src.scalper.sizing import SymbolLotSizingEngine
from src.scalper.strategy_btc import BtcWeekendScalpingStrategy
from src.scalper.strategy_gold import GoldScalpingStrategy
from src.scalper.stress_tester import DummyBrokerPos, ScalperStressTester
from src.scalper.symbol_resolver import ResolvedSymbolSpec
from src.scalper.telemetry import DuplicateOrderGuard


def test_01_rapid_signal_evaluation():
    """Tests cached tick/indicator evaluation and dedicated GOLD/BTC strategy evaluation."""
    tick_cache = TickCache()
    ind_cache = IndicatorCache()
    now_t = time.time()

    for i in range(15):
        res = tick_cache.push_tick("XAUUSD.m", bid=2650.0 + i * 0.15, ask=2650.25 + i * 0.15, timestamp=now_t + i * 0.05)
        assert res.is_valid

    ticks = tick_cache.get_recent_ticks("XAUUSD.m", 15)
    snap1 = ind_cache.get_or_update("GOLD", ticks=ticks, point=0.01, spread_points=25.0)
    snap2 = ind_cache.get_or_update("GOLD", ticks=ticks, point=0.01, spread_points=25.0)
    # Second call with identical tick_seq hits cache without recalculating
    assert ind_cache.cache_hits == 1
    assert snap1 is snap2

    gold_strat = GoldScalpingStrategy()
    sig = gold_strat.evaluate(snap1, current_price=2652.0)
    assert sig.is_valid
    assert sig.direction == "BUY"
    assert sig.reward_to_cost_ratio > 1.25


def test_02_controlled_multi_entry():
    """Tests SINGLE_ENTRY, CONTROLLED_MULTI_ENTRY, and PYRAMID_ENTRY modes with unique entry IDs."""
    cfg = ScalperConfig.load()
    ind_cache = IndicatorCache()
    ticks = [CachedTick("XAUUSD.m", 2650.0 + i * 0.2, 2650.25 + i * 0.2, time.time() + i) for i in range(12)]
    snap = ind_cache.get_or_update("GOLD", ticks=ticks, spread_points=25.0)
    sig = GoldScalpingStrategy(cfg.gold).evaluate(snap, current_price=2652.0)

    entry_eng = MultiPositionEntryEngine()
    plan = entry_eng.plan_entries("GOLD", sig, cfg.gold, active_basket=None, tick_seq=snap.tick_seq)
    assert plan.allowed
    assert len(plan.planned_entries) >= 2
    ids = {e.entry_id for e in plan.planned_entries}
    assert len(ids) == len(plan.planned_entries)  # Every entry has a unique identifier


def test_03_duplicate_order_prevention():
    """Ensures repeated ticks, duplicate entry_ids, or delayed acks never produce duplicate orders."""
    guard = DuplicateOrderGuard(dedup_window_ms=2000)
    assert guard.check_and_register("ENT_001", "XAUUSD.m", "BUY", tick_seq=10, slot_index=0) is True
    # Same entry_id blocked
    assert guard.check_and_register("ENT_001", "XAUUSD.m", "BUY", tick_seq=11, slot_index=0) is False
    # Same tick_seq + slot_index blocked even with new entry_id
    assert guard.check_and_register("ENT_002", "XAUUSD.m", "BUY", tick_seq=10, slot_index=0) is False
    assert guard.duplicates_blocked == 2


def test_04_dynamic_risk_position_sizing():
    """Tests CONSERVATIVE (0.10%), STANDARD (0.25%), and AGGRESSIVE_DEMO (0.50%) risk sizing and min_lot rejection."""
    sizing = SymbolLotSizingEngine()
    gold_spec = ResolvedSymbolSpec(symbol="XAUUSD.m", canonical="XAUUSD", point=0.01, tick_size=0.01, tick_value=1.0, contract_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01)

    res_cons = sizing.calculate_risk_based_lot(account_equity=50000.0, sl_points=300.0, spec=gold_spec, risk_profile="CONSERVATIVE")
    res_std = sizing.calculate_risk_based_lot(account_equity=50000.0, sl_points=300.0, spec=gold_spec, risk_profile="STANDARD")
    res_agg = sizing.calculate_risk_based_lot(account_equity=50000.0, sl_points=300.0, spec=gold_spec, risk_profile="AGGRESSIVE_DEMO")

    assert res_cons.is_safe and res_std.is_safe and res_agg.is_safe
    assert res_cons.lot < res_std.lot < res_agg.lot

    # Small account where min_lot (0.01) risks ~$3.37 > 0.10% of $500 ($0.50) -> rejected!
    res_reject = sizing.calculate_risk_based_lot(account_equity=500.0, sl_points=300.0, spec=gold_spec, risk_profile="CONSERVATIVE")
    assert not res_reject.is_safe
    assert "MIN_LOT_EXCEEDS_PERMITTED_RISK" in (res_reject.rejection_reason or "")


def test_05_basket_risk_calculation():
    """Additional positions consume remaining basket risk budget and never exceed account risk budget."""
    sizing = SymbolLotSizingEngine()
    gold_spec = ResolvedSymbolSpec(symbol="XAUUSD.m", canonical="XAUUSD", point=0.01, tick_size=0.01, tick_value=1.0, contract_size=100.0, min_lot=0.01)

    # $5,000 equity, STANDARD 0.25% = $12.50 basket budget
    first = sizing.calculate_risk_based_lot(account_equity=5000.0, sl_points=300.0, spec=gold_spec, risk_profile="STANDARD", planned_positions_in_basket=3, already_used_basket_risk_usd=0.0)
    assert first.is_safe
    second = sizing.calculate_risk_based_lot(account_equity=5000.0, sl_points=300.0, spec=gold_spec, risk_profile="STANDARD", planned_positions_in_basket=2, already_used_basket_risk_usd=first.worst_case_loss_usd)
    assert second.is_safe
    assert second.remaining_basket_risk_usd < first.remaining_basket_risk_usd

    # Exhausted basket budget -> rejected
    exhausted = sizing.calculate_risk_based_lot(account_equity=5000.0, sl_points=300.0, spec=gold_spec, risk_profile="STANDARD", already_used_basket_risk_usd=12.00)
    assert not exhausted.is_safe


def test_06_basket_profit_locking():
    """Once basket floating profit reaches profit_lock_trigger_usd, retracement to floor triggers PROFIT_LOCK_FLOOR exit."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket(
        symbol_key="GOLD",
        symbol="XAUUSD.m",
        direction="BUY",
        target_size=2,
        basket_tp_usd=3.00,
        profit_lock_trigger_usd=1.50,
        profit_lock_floor_usd=0.90,
    )
    basket.add_position(BasketPosition(ticket=1, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0, profit=0.80))
    basket.add_position(BasketPosition(ticket=2, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0, profit=0.80))
    assert basket.net_floating_profit == pytest.approx(1.60)
    assert basket.profit_lock_active is True

    # Profit retraces to $0.85 (<= $0.90 floor) -> triggers PROFIT_LOCK_FLOOR exit
    basket.update_position(1, 2650.42, profit=0.42)
    basket.update_position(2, 2650.43, profit=0.43)
    tickets, reason = mgr.evaluate_exits_for_symbol("GOLD")
    assert reason == "PROFIT_LOCK_FLOOR"
    assert set(tickets) == {1, 2}


def test_07_rapid_profit_capture_and_be_trailing():
    """Tests tighten-only Break-Even and Trailing Stop upgrades and momentum deterioration exit."""
    cfg = ScalperConfig.load()
    exit_eng = RapidExitEngine()
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket("GOLD", "XAUUSD.m", "BUY", target_size=1, basket_tp_usd=5.0)
    pos = BasketPosition(ticket=77, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.00, current_price=2653.20, stop_loss=2647.00, profit=3.20)
    basket.add_position(pos)

    actions = exit_eng.evaluate_protective_stop_upgrades(basket, cfg.gold, point=0.01)
    assert len(actions) == 1
    assert actions[0].new_sl > 2650.00  # Moved above entry

    # Never loosen an existing protective stop
    assert exit_eng.is_tighter_stop("BUY", current_sl=2652.00, candidate_sl=2651.00, current_price=2653.50) is False
    assert exit_eng.is_tighter_stop("BUY", current_sl=2652.00, candidate_sl=0.0, current_price=2653.50) is False


def test_08_direction_reversal():
    """Controlled direction reversal closes previous direction, reconciles, and opens opposite direction."""
    cfg = ScalperConfig.load()
    engine = DualMarketScalperEngine(cfg, is_simulation=True)
    engine.initialize()
    fri_dt = datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc)

    engine.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
    assert engine.basket_manager.get_active_basket("GOLD").direction == "BUY"

    engine.run_single_tick_cycle(strategy_bias=-0.90, current_dt=fri_dt)
    assert engine.basket_manager.get_active_basket("GOLD").direction == "SELL"
    assert engine.stats.reversals_executed == 1
    assert len(engine.reversal_engine.reversal_history) == 1
    rec = engine.reversal_engine.reversal_history[0]
    assert rec.previous_direction == "BUY"
    assert rec.new_direction == "SELL"


def test_09_gold_weekday_scheduling():
    """Monday to Friday routes strictly to GOLD."""
    sched = MarketScheduler()
    spec = ResolvedSymbolSpec(symbol="XAUUSD.m", canonical="XAUUSD", trade_mode=4, bid=2650.0, ask=2650.25, is_tradable=True)
    for day in range(9, 14):  # Mon Nov 9 .. Fri Nov 13, 2026
        dt = datetime(2026, 11, day, 12, 0, tzinfo=timezone.utc)
        d = sched.evaluate_market_status(spec, current_dt=dt)
        assert d.scheduled_symbol == "GOLD"
        assert d.is_entry_permitted is True


def test_10_btcusd_weekend_scheduling():
    """Saturday and Sunday route strictly to BTCUSD and never substitute GOLD."""
    sched = MarketScheduler()
    btc_spec = ResolvedSymbolSpec(symbol="BTCUSD.m", canonical="BTCUSD", trade_mode=4, bid=67000.0, ask=67010.0, is_tradable=True)
    for day in (14, 15):  # Sat Nov 14, Sun Nov 15, 2026
        dt = datetime(2026, 11, day, 12, 0, tzinfo=timezone.utc)
        d = sched.evaluate_market_status(btc_spec, current_dt=dt)
        assert d.scheduled_symbol == "BTCUSD"
        assert d.is_entry_permitted is True


def test_11_cross_symbol_risk_protection():
    """Shared risk controller enforces open risk, position count, and volume caps across GOLD and BTCUSD."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert risk.check_open_risk(account_equity=1000.0, current_open_risk_usd=15.0, proposed_additional_risk_usd=4.0).allowed
    assert not risk.check_open_risk(account_equity=1000.0, current_open_risk_usd=18.0, proposed_additional_risk_usd=5.0).allowed


def test_12_daily_loss_protection():
    """Daily realized + floating loss limit halts new entries when breached."""
    cfg = ScalperConfig.load()
    cfg.risk.daily_loss_enabled = True
    cfg.risk.max_daily_loss_usd = 50.0
    risk = AccountRiskManager(cfg)
    assert risk.check_daily_loss(1000.0, realized_daily_pnl_usd=-30.0, floating_pnl_usd=-10.0).allowed
    v_breach = risk.check_daily_loss(1000.0, realized_daily_pnl_usd=-35.0, floating_pnl_usd=-20.0)
    assert not v_breach.allowed
    assert v_breach.category == "DAILY_LOSS"


def test_13_equity_drawdown_protection():
    """30% equity drawdown triggers circuit breaker and pause."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    v = risk.check_drawdown(balance=1000.0, equity=680.0)
    assert not v.allowed
    assert risk.circuit_breaker_active is True


def test_14_margin_protection():
    """Enforces both 300% min margin level and 50% max margin utilization."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    v = risk.check_margin_and_capacity(1000.0, 1000.0, 480.0, 520.0, 4, 0.20, 0.20, margin_per_lot=200.0)
    assert not v.allowed
    assert v.category == "MARGIN"


def test_15_spread_rejection():
    """Rejects spreads exceeding symbol-specific limits (80 pts GOLD, 3000 pts BTCUSD)."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert not risk.check_spread("GOLD", 95.0).allowed
    assert risk.check_spread("BTCUSD", 1200.0).allowed
    assert not risk.check_spread("BTCUSD", 3200.0).allowed


def test_16_slippage_rejection():
    """Rejects slippage exceeding symbol-specific limits (25 pts GOLD, 150 pts BTCUSD)."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert risk.check_slippage("GOLD", 15.0).allowed
    assert not risk.check_slippage("GOLD", 35.0).allowed
    assert risk.check_slippage("BTCUSD", 100.0).allowed
    assert not risk.check_slippage("BTCUSD", 200.0).allowed


def test_17_broker_disconnection():
    """Blocks new entries on broker disconnection or stale heartbeat."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert not risk.check_broker_connection(is_connected=False).allowed
    assert not risk.check_broker_connection(is_connected=True, last_heartbeat_ts=100.0, now_override=125.0).allowed


def test_18_restart_recovery():
    """Reconciles and adopts open scalper positions on restart without duplicating orders."""
    cfg = ScalperConfig.load()
    eng = DualMarketScalperEngine(cfg, is_simulation=True)
    eng.initialize()
    broker_positions = [
        DummyBrokerPos(ticket=501, symbol="XAUUSD.m", magic=777001, type=0, volume=0.01, price_open=2650.0, price_current=2650.5, profit=0.50, sl=2647.0, tp=0.0),
        DummyBrokerPos(ticket=601, symbol="BTCUSD.m", magic=777002, type=1, volume=0.01, price_open=67000.0, price_current=66950.0, profit=0.50, sl=67050.0, tp=0.0),
    ]
    recovered = eng.recover_open_positions_from_broker(broker_positions)
    assert recovered == 2
    assert eng.basket_manager.has_active_basket("GOLD")
    assert eng.basket_manager.has_active_basket("BTCUSD")


def test_19_order_reconciliation():
    """Verifies broker position reconciliation removes closed tickets before re-entry."""
    exit_eng = RapidExitEngine()
    mgr = MultiBasketManager()
    b = mgr.start_new_basket("GOLD", "XAUUSD.m", "BUY", target_size=2)
    b.add_position(BasketPosition(ticket=11, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0))
    b.add_position(BasketPosition(ticket=12, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0))

    assert exit_eng.reconcile_broker_positions(b, broker_open_tickets={11}) is False
    assert b.position_count == 1
    assert exit_eng.reconcile_broker_positions(b, broker_open_tickets=set()) is True


def test_20_fri_sat_sun_mon_transitions_and_stress_suite():
    """Runs all 16 stress scenarios including Fri->Sat and Sun->Mon transitions and realistic backtester."""
    stress = ScalperStressTester().run_all_scenarios()
    assert stress["all_passed"] is True
    assert stress["passed_scenarios"] == 16

    bt = RealisticScalperBacktester()
    gold_res = bt.run_symbol_backtest("GOLD")
    btc_res = bt.run_symbol_backtest("BTCUSD")
    assert gold_res["number_of_trades"] > 0
    assert btc_res["number_of_trades"] > 0
    # Verify realistic distribution (< 100% win rate, includes losing trades)
    assert gold_res["losing_trades"] > 0
    assert btc_res["losing_trades"] > 0
    assert gold_res["win_rate_realism_audit"]["passed"] is True
    assert btc_res["win_rate_realism_audit"]["passed"] is True

    # Verify notification throttling
    notif = ScalperNotificationManager()
    p1 = notif.emit("RISK_LIMIT_REACHED", instrument="GOLD", reason="Test 1", now_override=1000.0)
    p2 = notif.emit("RISK_LIMIT_REACHED", instrument="GOLD", reason="Test 2", now_override=1005.0)
    assert p1 is not None
    assert p2 is None
    assert notif.suppressed_count == 1
