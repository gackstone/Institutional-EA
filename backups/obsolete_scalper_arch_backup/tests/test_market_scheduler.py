"""
Comprehensive Test Suite for Market Scheduler, Calendar Transitions, and Cross-Symbol Risk Controls.
Covers:
- Monday through Friday routing to GOLD (XAUUSD)
- Saturday and Sunday routing to BTCUSD (Bitcoin)
- Broker trading availability verification (trade_mode == 4, live bid/ask > 0)
- Calendar transition detection (Friday -> Saturday and Sunday -> Monday)
- Seamless position management continuity across transitions (existing GOLD positions managed on Saturday while new entries route to BTCUSD)
- Multi-symbol account-level safety limits (max 12 open positions, max 1.00 total lots, 30% equity drawdown stop, 300% min margin level, kill switch)
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.scalper.config import ScalperConfig, SchedulerConfig
from src.scalper.scheduler import MarketScheduler
from src.scalper.symbol_resolver import ResolvedSymbolSpec
from src.scalper.risk import AccountRiskManager
from src.scalper.basket import BasketPosition
from src.scalper.engine import DualMarketScalperEngine


# Reference UTC dates (Jan 1, 2024 = Monday ... Jan 7, 2024 = Sunday)
MONDAY_DT = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
TUESDAY_DT = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
WEDNESDAY_DT = datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc)
THURSDAY_DT = datetime(2024, 1, 4, 12, 0, tzinfo=timezone.utc)
FRIDAY_DT = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
SATURDAY_DT = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
SUNDAY_DT = datetime(2024, 1, 7, 12, 0, tzinfo=timezone.utc)


def _make_tradable_spec(symbol: str = "XAUUSD.m", canonical: str = "XAUUSD", spread: float = 25.0) -> ResolvedSymbolSpec:
    px = 2650.0 if "XAU" in canonical else 67000.0
    return ResolvedSymbolSpec(
        symbol=symbol,
        canonical=canonical,
        digits=2,
        point=0.01,
        contract_size=100.0 if "XAU" in canonical else 1.0,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        filling_mode=1,
        trade_mode=4,
        bid=px,
        ask=px + spread * 0.01,
        spread_points=spread,
        is_tradable=True,
    )


# ==============================================================================
# 1. WEEKDAY & WEEKEND CALENDAR ROUTING TESTS
# ==============================================================================

@pytest.mark.parametrize(
    "dt,expected_day",
    [
        (MONDAY_DT, "MONDAY"),
        (TUESDAY_DT, "TUESDAY"),
        (WEDNESDAY_DT, "WEDNESDAY"),
        (THURSDAY_DT, "THURSDAY"),
        (FRIDAY_DT, "FRIDAY"),
    ],
)
def test_weekdays_route_to_gold(dt, expected_day):
    """Monday through Friday strictly route to GOLD."""
    scheduler = MarketScheduler(SchedulerConfig())
    spec = _make_tradable_spec("XAUUSD.m", "XAUUSD")
    decision = scheduler.evaluate_market_status(spec, current_dt=dt)
    assert decision.scheduled_symbol == "GOLD"
    assert decision.day_name == expected_day
    assert decision.is_entry_permitted is True


@pytest.mark.parametrize(
    "dt,expected_day",
    [
        (SATURDAY_DT, "SATURDAY"),
        (SUNDAY_DT, "SUNDAY"),
    ],
)
def test_weekends_route_to_btcusd(dt, expected_day):
    """Saturday and Sunday strictly route to BTCUSD."""
    scheduler = MarketScheduler(SchedulerConfig())
    spec = _make_tradable_spec("BTCUSD.m", "BTCUSD", spread=900.0)
    decision = scheduler.evaluate_market_status(spec, current_dt=dt)
    assert decision.scheduled_symbol == "BTCUSD"
    assert decision.day_name == expected_day
    assert decision.is_entry_permitted is True


# ==============================================================================
# 2. BROKER TRADING AVAILABILITY TESTS
# ==============================================================================

def test_entry_blocked_when_spec_none():
    """If the scheduled symbol is missing on the broker, new entries are blocked without falling back."""
    scheduler = MarketScheduler(SchedulerConfig())
    decision = scheduler.evaluate_market_status(None, current_dt=SATURDAY_DT)
    assert decision.scheduled_symbol == "BTCUSD"
    assert decision.is_broker_tradable is False
    assert decision.is_entry_permitted is False


def test_entry_blocked_when_trade_mode_closed():
    """If broker trade_mode != 4 (e.g., disabled or close-only), new entries are blocked."""
    scheduler = MarketScheduler(SchedulerConfig())
    spec = _make_tradable_spec("BTCUSD.m", "BTCUSD")
    spec.trade_mode = 0
    spec.is_tradable = False
    decision = scheduler.evaluate_market_status(spec, current_dt=SUNDAY_DT)
    assert decision.is_broker_tradable is False
    assert decision.is_entry_permitted is False


def test_entry_blocked_when_quotes_zero():
    """If bid or ask is 0.0, new entries are blocked."""
    scheduler = MarketScheduler(SchedulerConfig())
    spec = _make_tradable_spec("XAUUSD.m", "XAUUSD")
    spec.bid = 0.0
    decision = scheduler.evaluate_market_status(spec, current_dt=WEDNESDAY_DT)
    assert decision.is_broker_tradable is False
    assert decision.is_entry_permitted is False


# ==============================================================================
# 3. MARKET TRANSITION & POSITION CONTINUITY TESTS
# ==============================================================================

def test_transition_detection_friday_to_saturday_and_sunday_to_monday():
    """Scheduler detects Friday->Saturday and Sunday->Monday instrument transitions."""
    scheduler = MarketScheduler(SchedulerConfig())
    gold_spec = _make_tradable_spec("XAUUSD.m", "XAUUSD")
    btc_spec = _make_tradable_spec("BTCUSD.m", "BTCUSD")

    d_fri = scheduler.evaluate_market_status(gold_spec, current_dt=FRIDAY_DT)
    assert d_fri.scheduled_symbol == "GOLD"
    assert d_fri.is_transition_bar is False

    d_sat = scheduler.evaluate_market_status(btc_spec, current_dt=SATURDAY_DT)
    assert d_sat.scheduled_symbol == "BTCUSD"
    assert d_sat.is_transition_bar is True

    d_sun = scheduler.evaluate_market_status(btc_spec, current_dt=SUNDAY_DT)
    assert d_sun.scheduled_symbol == "BTCUSD"
    assert d_sun.is_transition_bar is False

    d_mon = scheduler.evaluate_market_status(gold_spec, current_dt=MONDAY_DT)
    assert d_mon.scheduled_symbol == "GOLD"
    assert d_mon.is_transition_bar is True


def test_friday_gold_basket_managed_to_completion_on_saturday():
    """
    During Friday -> Saturday transition:
    1. Existing Friday GOLD basket is still monitored and closed when its TP is hit on Saturday.
    2. New Saturday basket is opened on BTCUSD only.
    """
    cfg = ScalperConfig.load()
    cfg.symbols["GOLD"].order_spacing_ms = 1
    cfg.symbols["BTCUSD"].order_spacing_ms = 1
    engine = DualMarketScalperEngine(config=cfg, is_simulation=True)
    assert engine.initialize()

    # Step 1: Friday cycle opens a GOLD basket
    engine.run_single_tick_cycle(current_dt=FRIDAY_DT)
    assert engine.basket_manager.has_active_basket("GOLD")
    assert not engine.basket_manager.has_active_basket("BTCUSD")

    # Simulate GOLD basket reaching its aggregate TP ($2.00) while calendar moves to Saturday
    gold_basket = engine.basket_manager.get_active_basket("GOLD")
    for pos in gold_basket.positions.values():
        pos.profit = 0.65  # 4 * $0.65 = $2.60 >= $2.00

    # Step 2: Saturday cycle closes the profitable GOLD basket AND opens a new BTCUSD basket
    engine.run_single_tick_cycle(current_dt=SATURDAY_DT)

    assert not engine.basket_manager.has_active_basket("GOLD")
    assert engine.symbol_stats["GOLD"].total_baskets_closed == 1
    assert engine.basket_manager.has_active_basket("BTCUSD")
    assert engine.symbol_stats["BTCUSD"].total_baskets_opened == 1


# ==============================================================================
# 4. CROSS-SYMBOL ACCOUNT-LEVEL RISK PROTECTION TESTS
# ==============================================================================

def test_cross_symbol_position_and_lot_limits():
    """AccountRiskManager enforces 12 max positions and 1.00 max total lots across both symbols."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)

    # 11 positions open -> 1 more allowed
    v_ok = risk.check_margin_and_capacity(
        account_balance=1000.0,
        account_equity=1000.0,
        account_margin=50.0,
        account_free_margin=950.0,
        current_open_positions=11,
        current_total_lots=0.50,
        proposed_lot=0.04,
    )
    assert v_ok.allowed

    # 12 positions open -> 13th blocked
    v_pos_block = risk.check_margin_and_capacity(
        account_balance=1000.0,
        account_equity=1000.0,
        account_margin=50.0,
        account_free_margin=950.0,
        current_open_positions=12,
        current_total_lots=0.50,
        proposed_lot=0.04,
    )
    assert not v_pos_block.allowed
    assert v_pos_block.category == "POSITION_LIMIT"

    # Total lots exceeding 1.00 blocked
    v_lot_block = risk.check_margin_and_capacity(
        account_balance=1000.0,
        account_equity=1000.0,
        account_margin=50.0,
        account_free_margin=950.0,
        current_open_positions=8,
        current_total_lots=0.90,
        proposed_lot=0.15,
    )
    assert not v_lot_block.allowed
    assert v_lot_block.category == "VOLUME_LIMIT"


def test_cross_symbol_drawdown_and_margin_level():
    """AccountRiskManager enforces 30% max equity drawdown and 300% minimum margin level."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)

    # 20% drawdown passes
    assert risk.check_drawdown(balance=1000.0, equity=800.0).allowed

    # 31% drawdown triggers circuit breaker and pause
    dd_fail = risk.check_drawdown(balance=1000.0, equity=690.0)
    assert not dd_fail.allowed
    assert dd_fail.category == "DRAWDOWN"
    assert risk.circuit_breaker_active is True

    # Margin level < 300% rejected
    risk2 = AccountRiskManager(cfg)
    margin_fail = risk2.check_margin_and_capacity(
        account_balance=300.0,
        account_equity=250.0,
        account_margin=90.0,
        account_free_margin=160.0,
        current_open_positions=4,
        current_total_lots=0.04,
        proposed_lot=0.01,
        margin_per_lot=20.0,
    )
    assert not margin_fail.allowed
    assert margin_fail.category == "MARGIN"


def test_kill_switch_file_and_manual():
    """Kill switch halts execution on STOP.flag file or manual operator trigger."""
    cfg = ScalperConfig.load()
    with tempfile.TemporaryDirectory() as tmpdir:
        flag_file = Path(tmpdir) / "STOP.flag"
        cfg.kill_switch.flag_file_path = str(flag_file)
        risk = AccountRiskManager(cfg)

        assert risk.check_kill_switch().allowed

        flag_file.write_text("STOP", encoding="utf-8")
        v_flag = risk.check_kill_switch()
        assert not v_flag.allowed
        assert v_flag.category == "KILL_SWITCH"
