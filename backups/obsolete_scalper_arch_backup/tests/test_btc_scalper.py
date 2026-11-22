"""
Comprehensive Automated Test Suite for BTCUSD (Bitcoin) Weekend Scalping Engine.
Covers:
- BTCUSD symbol resolution across broker aliases (BTCUSD, BTCUSDm, BTCUSD.m, BTCUSD.a, BTCUSD#, BTCUSDpro)
- BTCUSD contract specifications (contract_size=1.0, volume normalization)
- BTCUSD dynamic balance-based lot sizing & step clamping
- BTCUSD basket lifecycle, magic number isolation (777002), and independence from GOLD (777001)
- BTCUSD individual take profit, aggregate basket take profit, and maximum holding time exits
- BTCUSD spread protection (spread_max_points=3000.0) and protective stop-loss (sl_points=5000.0)
- BTCUSD direction selection & velocity fallback with $25.00 saturation scale
"""

import time
from dataclasses import dataclass
import pytest

from src.scalper.config import ScalperConfig, InstrumentScalperConfig, LotSizingConfig
from src.scalper.symbol_resolver import BtcSymbolResolver, MultiSymbolResolver, ResolvedSymbolSpec
from src.scalper.sizing import SymbolLotSizingEngine
from src.scalper.basket import MultiBasketManager, ScalperBasket, BasketPosition, BasketState
from src.scalper.risk import AccountRiskManager
from src.scalper.direction import SymbolDirectionSelector


@dataclass
class DummyTick:
    bid: float
    ask: float = 0.0


@dataclass
class DummyCandle:
    open: float
    close: float
    high: float = 0.0
    low: float = 0.0


# ==============================================================================
# 1. BTC SYMBOL RESOLUTION TESTS
# ==============================================================================

def test_btc_exact_match():
    """Exact 'BTCUSD' match is preferred when present in broker symbols."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["EURUSD", "XAUUSD", "BTCUSD", "ETHUSD"])
    assert resolved == "BTCUSD"


def test_btc_m_suffix():
    """Resolves 'BTCUSDm' when exact 'BTCUSD' is absent."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["EURUSDm", "XAUUSDm", "BTCUSDm"])
    assert resolved == "BTCUSDm"


def test_btc_dot_m_suffix():
    """Resolves 'BTCUSD.m' (JustMarkets broker variation)."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["EURUSD.m", "XAUUSD.m", "BTCUSD.m"])
    assert resolved == "BTCUSD.m"


def test_btc_hash_suffix():
    """Resolves 'BTCUSD#' broker suffix."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["XAUUSD#", "BTCUSD#"])
    assert resolved == "BTCUSD#"


def test_btc_a_suffix():
    """Resolves 'BTCUSD.a' broker suffix."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["XAUUSD.a", "BTCUSD.a"])
    assert resolved == "BTCUSD.a"


def test_btc_pro_suffix():
    """Resolves 'BTCUSDpro' broker suffix."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["XAUUSDpro", "BTCUSDpro"])
    assert resolved == "BTCUSDpro"


def test_btc_fuzzy_prefix():
    """Resolves non-standard broker suffix via fuzzy BTC*USD match."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["EURUSD.ecn", "BTCUSD.ecn_zero"])
    assert resolved == "BTCUSD.ecn_zero"


def test_btc_prefers_exact_over_alias():
    """Prefers exact 'BTCUSD' even when aliases appear earlier in the broker list."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["BTCUSD.m", "BTCUSDm", "BTCUSD"])
    assert resolved == "BTCUSD"


def test_btc_unresolvable():
    """Returns None gracefully when no Bitcoin symbol exists on the broker."""
    resolver = BtcSymbolResolver()
    resolved = resolver.resolve_from_names(["EURUSD", "GBPUSD", "XAUUSD.m"])
    assert resolved is None


def test_btc_spec_contract_size_and_normalization():
    """Verifies BTCUSD contract_size=1.0 and broker volume step normalization."""
    spec = ResolvedSymbolSpec(
        symbol="BTCUSD.m",
        canonical="BTCUSD",
        digits=2,
        point=0.01,
        contract_size=1.0,
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        filling_mode=1,
        trade_mode=4,
        bid=67000.0,
        ask=67010.0,
        spread_points=1000.0,
        is_tradable=True,
    )
    assert spec.contract_size == 1.0
    assert spec.normalize_volume(0.001) == 0.01
    assert spec.normalize_volume(0.034) == 0.03
    assert spec.normalize_volume(100.0) == 50.0


# ==============================================================================
# 2. BTC LOT SIZING TESTS
# ==============================================================================

def test_btc_sizing_micro_balance():
    """$5 micro account receives 0.01 minimum lot floor on BTCUSD."""
    sizing = SymbolLotSizingEngine()
    cfg = ScalperConfig.load()
    btc_cfg = cfg.symbols["BTCUSD"]
    res = sizing.calculate_lot(5.0, instrument_config=btc_cfg)
    assert res.is_safe
    assert res.lot == 0.01


def test_btc_sizing_hundred_balance():
    """$100 balance with lot_step_balance=50.0 yields 0.02 lot."""
    sizing = SymbolLotSizingEngine()
    cfg = ScalperConfig.load()
    btc_cfg = cfg.symbols["BTCUSD"]
    res = sizing.calculate_lot(100.0, instrument_config=btc_cfg)
    assert res.is_safe
    assert res.lot == 0.02


def test_btc_sizing_custom_step_balance():
    """Custom lot_step_balance=200.0 scales conservatively for higher BTC volatility."""
    sizing = SymbolLotSizingEngine()
    custom_btc = InstrumentScalperConfig(
        canonical="BTCUSD",
        lot_step_balance=200.0,
        min_lot=0.01,
        max_lot=0.25,
        micro_account_min_lot=0.01,
    )
    res_150 = sizing.calculate_lot(150.0, instrument_config=custom_btc)
    assert res_150.lot == 0.01
    res_600 = sizing.calculate_lot(600.0, instrument_config=custom_btc)
    assert res_600.lot == 0.03


def test_btc_sizing_clamped_to_max():
    """Large balance is strictly clamped to BTCUSD max_lot."""
    sizing = SymbolLotSizingEngine()
    cfg = ScalperConfig.load()
    btc_cfg = cfg.symbols["BTCUSD"]
    res = sizing.calculate_lot(50000.0, instrument_config=btc_cfg)
    assert res.is_safe
    assert res.lot == btc_cfg.max_lot


def test_btc_sizing_negative_balance():
    """Zero or negative balance fails closed with is_safe=False."""
    sizing = SymbolLotSizingEngine()
    res = sizing.calculate_lot(0.0)
    assert not res.is_safe
    assert res.lot == 0.0


# ==============================================================================
# 3. BTC BASKET LIFECYCLE & ISOLATION TESTS
# ==============================================================================

def test_btc_basket_magic_number_and_key():
    """BTCUSD baskets use magic number 777002 and symbol_key 'BTCUSD'."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket(
        symbol_key="BTCUSD",
        symbol="BTCUSD.m",
        direction="BUY",
        target_size=4,
        magic_number=777002,
        basket_tp_usd=2.00,
        tp_usd_per_min_lot=0.50,
        max_hold_seconds=180,
    )
    assert basket.symbol_key == "BTCUSD"
    assert basket.symbol == "BTCUSD.m"
    assert basket.magic_number == 777002
    assert basket.state == BasketState.OPENING


def test_btc_basket_state_transitions():
    """BTCUSD basket transitions from OPENING to ACTIVE once target_size positions are added, and CLOSED when emptied."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket(
        symbol_key="BTCUSD",
        symbol="BTCUSD.m",
        direction="SELL",
        target_size=3,
        magic_number=777002,
    )
    for i in range(3):
        basket.add_position(
            BasketPosition(
                ticket=2000 + i,
                symbol="BTCUSD.m",
                direction="SELL",
                volume=0.01,
                open_price=67000.0,
                magic=777002,
                symbol_key="BTCUSD",
            )
        )
    assert basket.state == BasketState.ACTIVE
    assert basket.position_count == 3
    assert basket.total_volume == 0.03

    for i in range(3):
        mgr.on_position_closed(2000 + i, realized_pnl=0.70, symbol_key="BTCUSD")

    assert not mgr.has_active_basket("BTCUSD")
    assert mgr.is_reentry_ready("BTCUSD")
    assert len(mgr.closed_baskets) == 1
    assert mgr.closed_baskets[0].realized_profit == pytest.approx(2.10)


def test_btc_basket_isolated_from_gold():
    """GOLD and BTCUSD baskets are tracked independently without cross-contamination."""
    mgr = MultiBasketManager()
    gold_b = mgr.start_new_basket("GOLD", "XAUUSD.m", "BUY", target_size=2, magic_number=777001, basket_tp_usd=2.0)
    btc_b = mgr.start_new_basket("BTCUSD", "BTCUSD.m", "SELL", target_size=2, magic_number=777002, basket_tp_usd=2.5)

    gold_b.add_position(BasketPosition(ticket=101, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0, profit=0.30, magic=777001, symbol_key="GOLD"))
    btc_b.add_position(BasketPosition(ticket=201, symbol="BTCUSD.m", direction="SELL", volume=0.01, open_price=67000.0, profit=2.60, magic=777002, symbol_key="BTCUSD"))

    assert mgr.has_active_basket("GOLD")
    assert mgr.has_active_basket("BTCUSD")
    assert len(mgr.get_all_active_baskets()) == 2

    # BTCUSD hit its aggregate TP ($2.60 >= $2.50), while GOLD has not ($0.30 < $2.00)
    exits = mgr.evaluate_all_exits()
    assert len(exits) == 1
    sym_k, tickets, reason = exits[0]
    assert sym_k == "BTCUSD"
    assert tickets == [201]
    assert reason == "BASKET_TP"


# ==============================================================================
# 4. BTC TAKE PROFIT & EXIT CONDITION TESTS
# ==============================================================================

def test_btc_individual_tp_hit():
    """Individual BTCUSD position triggers INDIVIDUAL_TP when profit >= tp_usd_per_min_lot."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket("BTCUSD", "BTCUSD.m", "BUY", target_size=3, magic_number=777002, basket_tp_usd=2.00, tp_usd_per_min_lot=0.50)
    basket.add_position(BasketPosition(ticket=301, symbol="BTCUSD.m", direction="BUY", volume=0.01, open_price=67000.0, profit=0.55, magic=777002, symbol_key="BTCUSD"))
    basket.add_position(BasketPosition(ticket=302, symbol="BTCUSD.m", direction="BUY", volume=0.01, open_price=67000.0, profit=0.10, magic=777002, symbol_key="BTCUSD"))

    tickets, reason = mgr.evaluate_exits_for_symbol("BTCUSD")
    assert reason == "INDIVIDUAL_TP"
    assert tickets == [301]


def test_btc_aggregate_tp_hit():
    """Aggregate BTCUSD basket TP closes all positions in the basket when net profit >= basket_tp_usd."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket("BTCUSD", "BTCUSD.m", "BUY", target_size=4, magic_number=777002, basket_tp_usd=2.00, tp_usd_per_min_lot=0.80)
    for i in range(4):
        basket.add_position(BasketPosition(ticket=400 + i, symbol="BTCUSD.m", direction="BUY", volume=0.01, open_price=67000.0, profit=0.55, magic=777002, symbol_key="BTCUSD"))

    tickets, reason = mgr.evaluate_exits_for_symbol("BTCUSD")
    assert reason == "BASKET_TP"
    assert set(tickets) == {400, 401, 402, 403}


def test_btc_time_stop_exit():
    """BTCUSD basket triggers MAX_HOLD_BREAKEVEN or MAX_HOLD_TIMEOUT when duration >= max_hold_seconds."""
    mgr = MultiBasketManager()
    basket = mgr.start_new_basket("BTCUSD", "BTCUSD.m", "BUY", target_size=2, magic_number=777002, basket_tp_usd=2.00, max_hold_seconds=180)
    basket.created_at = time.time() - 185.0
    basket.add_position(BasketPosition(ticket=501, symbol="BTCUSD.m", direction="BUY", volume=0.01, open_price=67000.0, profit=-0.15, magic=777002, symbol_key="BTCUSD"))

    tickets, reason = mgr.evaluate_exits_for_symbol("BTCUSD")
    assert reason == "MAX_HOLD_TIMEOUT"
    assert tickets == [501]


# ==============================================================================
# 5. BTC RISK, SPREAD, SL & DIRECTION CALIBRATION TESTS
# ==============================================================================

def test_btc_protective_sl_calculation():
    """BTCUSD protective SL uses 5000 points ($50.00 distance at point=0.01)."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert cfg.symbols["BTCUSD"].sl_points == 5000.0

    buy_sl = risk.calculate_protective_sl("BTCUSD", "BUY", entry_price=67000.00, point=0.01)
    sell_sl = risk.calculate_protective_sl("BTCUSD", "SELL", entry_price=67000.00, point=0.01)
    assert buy_sl == pytest.approx(66950.00)
    assert sell_sl == pytest.approx(67050.00)


def test_btc_spread_protection():
    """BTCUSD allows typical crypto spreads (e.g., 1200 pts) up to 3000 pts and rejects wider spreads."""
    cfg = ScalperConfig.load()
    risk = AccountRiskManager(cfg)
    assert cfg.symbols["BTCUSD"].spread_max_points == 3000.0

    ok_verdict = risk.check_spread("BTCUSD", 1200.0)
    assert ok_verdict.allowed

    high_verdict = risk.check_spread("BTCUSD", 3500.0)
    assert not high_verdict.allowed
    assert high_verdict.category == "SPREAD"


def test_btc_direction_selection_and_fallback():
    """BTCUSD direction selector always returns BUY or SELL and uses crypto-calibrated velocity scaling."""
    cfg = ScalperConfig.load()
    selector = SymbolDirectionSelector(cfg.direction_selection)
    btc_cfg = cfg.symbols["BTCUSD"]

    # Upward tick velocity on BTCUSD ($67,000 -> $67,030)
    ticks_up = [DummyTick(bid=67000.0 + i * 2.0) for i in range(16)]
    res_up = selector.select_direction(ticks=ticks_up, canonical="BTCUSD", instrument_config=btc_cfg)
    assert res_up.selected_direction == "BUY"

    # Downward M1 drift on BTCUSD
    candles_down = [DummyCandle(open=67100.0 - i * 15.0, close=67085.0 - i * 15.0) for i in range(6)]
    res_down = selector.select_direction(m1_candles=candles_down, canonical="BTCUSD", instrument_config=btc_cfg)
    assert res_down.selected_direction == "SELL"
