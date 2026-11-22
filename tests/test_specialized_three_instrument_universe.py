"""
Tests for Institutional EA Three-Instrument Trading Specialization:
1. Strict Three-Symbol Universe (XAUUSD, BTCUSD, USDJPY)
2. Broker-Aware Symbol Resolution (.m, .pro, .raw, etc.)
3. Weekday XAUUSD Primary Trading Mode (Priority 1: Gold, Priority 2: USDJPY)
4. Inverse Directional Coordination (Gold BUY -> USDJPY SELL; Gold SELL -> USDJPY BUY)
5. Weekend BTCUSD Exclusive Trading Mode (24/7 crypto scanning, forex/gold new entries blocked)
6. Position Management Retention Across Schedule Transitions
"""

from datetime import datetime, timezone
import pytest

from src.core.contracts import (
    AccountInfo,
    Candle,
    DecisionOutcomeType,
    ExecutionMode,
    OrderType,
    Position,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)
from src.core.config import AppConfig
from src.core.symbol_universe import (
    SpecializedSymbolUniverse,
    APPROVED_CANONICAL_SYMBOLS,
    APPROVED_CANONICAL_ALIASES,
    get_symbol_universe,
)
from src.core.trading_schedule import (
    TradingScheduleManager,
    OperatingMode,
    get_trading_schedule,
)
from src.strategy.inverse_coordination import (
    InverseDirectionCoordinator,
    CorrelationRegime,
)
from src.execution.order_manager import OrderManager
from src.risk.position_sizing import PositionSizingEngine
from src.risk.portfolio_risk import PortfolioRiskEngine


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

def make_candle(close_price: float, t: datetime) -> Candle:
    return Candle(
        time=t,
        open=close_price,
        high=close_price + 1.0,
        low=close_price - 1.0,
        close=close_price,
        volume=100.0,
    )


def make_signal(
    symbol: str = "XAUUSD",
    direction: OrderType = OrderType.BUY,
    score: float = 75.0,
    entry: float = 2650.0,
    sl: float = 2640.0,
    tp: float = 2670.0,
    dt: datetime = None,
) -> SignalCandidate:
    now = dt or datetime.now(timezone.utc)
    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 2.0
    return SignalCandidate(
        id=f"TEST_{symbol}_{int(now.timestamp())}",
        symbol=symbol,
        setup_type=SetupType.M15_SMC_OTE,
        timeframe=Timeframe.M15,
        timestamp=now,
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=rr,
        score=score,
        reasons=["TEST_CONFLUENCE"],
        status="APPROVED",
    )


# ---------------------------------------------------------------------------
# 1. Strict Three-Symbol Universe & Rejection Tests
# ---------------------------------------------------------------------------

class TestStrictSymbolUniverse:
    def test_canonical_symbols_approved(self):
        universe = SpecializedSymbolUniverse()
        assert universe.is_approved("XAUUSD") is True
        assert universe.is_approved("BTCUSD") is True
        assert universe.is_approved("USDJPY") is False

    def test_broker_suffix_variants_approved(self):
        universe = SpecializedSymbolUniverse()
        assert universe.is_approved("XAUUSD.m") is True
        assert universe.is_approved("BTCUSD.m") is True
        assert universe.is_approved("USDJPY.m") is False
        assert universe.is_approved("USDJPY.c") is False
        assert universe.is_approved("XAUUSD.pro") is True
        assert universe.is_approved("BTCUSD.raw") is True
        assert universe.is_approved("GOLD") is True
        assert universe.is_approved("BITCOIN") is True

    def test_unauthorized_symbols_rejected(self):
        universe = SpecializedSymbolUniverse()
        unauthorized = ["EURUSD", "GBPUSD", "USDJPY", "USDJPY.m", "USDJPY.c", "USDJPYmicro", "NAS100", "US30", "AUDUSD", "ETHUSD", "GER40"]
        for sym in unauthorized:
            assert universe.is_approved(sym) is False, f"{sym} should be rejected"
            is_ok, reason = universe.validate_or_reject(sym)
            assert is_ok is False
            assert reason is not None
            assert "INSTRUMENT_NOT_ALLOWED" in reason
            assert universe.get_canonical_symbol(sym) is None

    def test_validate_or_reject_returns_canonical(self):
        universe = SpecializedSymbolUniverse()
        ok_gold, _ = universe.validate_or_reject("XAUUSD.m")
        assert ok_gold is True
        assert universe.get_canonical_symbol("XAUUSD.m") == "XAUUSD"

        ok_btc, _ = universe.validate_or_reject("BTCUSD.pro")
        assert ok_btc is True
        assert universe.get_canonical_symbol("BTCUSD.pro") == "BTCUSD"

        ok_jpy, reason_jpy = universe.validate_or_reject("USDJPY.m")
        assert ok_jpy is False
        assert "INSTRUMENT_NOT_ALLOWED" in reason_jpy
        assert universe.get_canonical_symbol("USDJPY.m") is None


# ---------------------------------------------------------------------------
# 2. Broker Symbol Resolution Tests
# ---------------------------------------------------------------------------

class TestBrokerSymbolResolution:
    class MockBridgeClient:
        def __init__(self, available_symbols):
            self._symbols = available_symbols

        def get_all_symbols(self):
            return self._symbols

    def test_resolve_with_broker_suffix(self):
        universe = SpecializedSymbolUniverse()
        mock_bridge = self.MockBridgeClient(["XAUUSD.m", "BTCUSD.m", "USDJPY.m", "EURUSD.m"])
        resolved = universe.resolve_universe(bridge_client=mock_bridge)

        assert resolved["XAUUSD"] == "XAUUSD.m"
        assert resolved["BTCUSD"] == "BTCUSD.m"
        assert "USDJPY" not in resolved
        assert "EURUSD.m" not in resolved.values()

    def test_resolve_fallback_to_standard(self):
        universe = SpecializedSymbolUniverse()
        mock_bridge = self.MockBridgeClient(["EURUSD", "GBPUSD"])  # None of our 2 instruments in broker list
        resolved = universe.resolve_universe(bridge_client=mock_bridge)

        assert resolved["XAUUSD"] == "XAUUSD"
        assert resolved["BTCUSD"] == "BTCUSD"
        assert "USDJPY" not in resolved


# ---------------------------------------------------------------------------
# 3. Weekday XAUUSD Priority & Operating Schedule Tests
# ---------------------------------------------------------------------------

class TestTradingScheduleAndPriority:
    def test_weekday_mode_detected_on_tuesday(self):
        scheduler = TradingScheduleManager(weekday_btc_fallback_enabled=False)
        # Tuesday 14:00 UTC
        tuesday_dt = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
        mode = scheduler.get_operating_mode(tuesday_dt)
        assert mode == OperatingMode.WEEKDAY_GOLD_MODE

    def test_weekday_priority_order(self):
        scheduler = TradingScheduleManager(weekday_btc_fallback_enabled=False)
        tuesday_dt = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
        priority = scheduler.get_scanning_priority_order(tuesday_dt)
        assert len(priority) == 1
        assert "XAUUSD" in priority[0]  # Gold must be Priority 1
        assert not any("JPY" in s for s in priority)  # USDJPY excluded
        assert not any("BTC" in s for s in priority)  # BTC disabled on normal weekday without fallback

    def test_weekday_btc_fallback_when_enabled(self):
        scheduler = TradingScheduleManager(weekday_btc_fallback_enabled=True)
        tuesday_dt = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
        priority = scheduler.get_scanning_priority_order(tuesday_dt)
        assert len(priority) == 2
        assert "XAUUSD" in priority[0]
        assert "BTCUSD" in priority[1]  # BTCUSD appended as fallback
        assert not any("JPY" in s for s in priority)

    def test_weekday_eligibility(self):
        scheduler = TradingScheduleManager(weekday_btc_fallback_enabled=False)
        tuesday_dt = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)

        ok_gold, _ = scheduler.is_instrument_eligible_for_new_entry("XAUUSD", tuesday_dt)
        assert ok_gold is True

        ok_jpy, reason_jpy = scheduler.is_instrument_eligible_for_new_entry("USDJPY", tuesday_dt)
        assert ok_jpy is False
        assert "INSTRUMENT_NOT_ALLOWED" in reason_jpy

        ok_btc, reason_btc = scheduler.is_instrument_eligible_for_new_entry("BTCUSD", tuesday_dt)
        assert ok_btc is False
        assert "inactive" in reason_btc.lower() or "weekday" in reason_btc.lower()


# ---------------------------------------------------------------------------
# 4. Weekend BTCUSD Exclusive Trading Mode Tests
# ---------------------------------------------------------------------------

class TestWeekendBtcMode:
    def test_weekend_mode_detected_on_saturday(self):
        scheduler = TradingScheduleManager()
        # Saturday 15:00 UTC
        saturday_dt = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
        mode = scheduler.get_operating_mode(saturday_dt)
        assert mode == OperatingMode.WEEKEND_BTC_MODE

    def test_weekend_mode_detected_on_sunday(self):
        scheduler = TradingScheduleManager()
        # Sunday 12:00 UTC
        sunday_dt = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        mode = scheduler.get_operating_mode(sunday_dt)
        assert mode == OperatingMode.WEEKEND_BTC_MODE

    def test_weekend_priority_is_btc_only(self):
        scheduler = TradingScheduleManager()
        saturday_dt = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
        priority = scheduler.get_scanning_priority_order(saturday_dt)
        assert len(priority) == 1
        assert "BTCUSD" in priority[0]

    def test_weekend_new_entries_for_gold_and_jpy_blocked(self):
        scheduler = TradingScheduleManager()
        saturday_dt = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)

        ok_btc, _ = scheduler.is_instrument_eligible_for_new_entry("BTCUSD", saturday_dt)
        assert ok_btc is True

        ok_gold, reason_gold = scheduler.is_instrument_eligible_for_new_entry("XAUUSD", saturday_dt)
        assert ok_gold is False
        assert "weekend" in reason_gold.lower()

        ok_jpy, reason_jpy = scheduler.is_instrument_eligible_for_new_entry("USDJPY", saturday_dt)
        assert ok_jpy is False
        assert "INSTRUMENT_NOT_ALLOWED" in reason_jpy


# ---------------------------------------------------------------------------
# 5. Inverse Directional Coordination Tests
# ---------------------------------------------------------------------------

class TestInverseDirectionCoordination:
    def test_xauusd_buy_sets_preferred_usdjpy_sell(self):
        coordinator = InverseDirectionCoordinator(enabled=True)
        gold_sig = make_signal("XAUUSD", OrderType.BUY, score=80.0)
        coordinator.update_xauusd_signal(gold_sig)

        assert coordinator.preferred_usdjpy_direction == OrderType.SELL
        assert coordinator.xauusd_bias == OrderType.BUY

    def test_xauusd_sell_sets_preferred_usdjpy_buy(self):
        coordinator = InverseDirectionCoordinator(enabled=True)
        gold_sig = make_signal("XAUUSD", OrderType.SELL, score=80.0)
        coordinator.update_xauusd_signal(gold_sig)

        assert coordinator.preferred_usdjpy_direction == OrderType.BUY
        assert coordinator.xauusd_bias == OrderType.SELL

    def test_usdjpy_candidate_always_rejected_by_allowlist(self):
        coordinator = InverseDirectionCoordinator(enabled=True)
        coordinator.current_correlation = -0.75
        coordinator.regime = CorrelationRegime.INVERSE_STRONG

        gold_sig = make_signal("XAUUSD", OrderType.BUY, score=80.0)
        coordinator.update_xauusd_signal(gold_sig)

        # USDJPY is universally rejected from execution under the 2-instrument directive
        jpy_sig = make_signal("USDJPY", OrderType.SELL, score=95.0, entry=154.50, sl=154.80, tp=153.90)
        res = coordinator.evaluate_usdjpy_candidate(jpy_sig)

        assert res.is_approved is False
        assert "INSTRUMENT_NOT_ALLOWED" in res.rationale

    def test_usdjpy_candidate_rejected_under_all_regimes(self):
        coordinator = InverseDirectionCoordinator(enabled=True)
        coordinator.current_correlation = 0.40
        coordinator.regime = CorrelationRegime.POSITIVE_BREAKDOWN

        gold_sig = make_signal("XAUUSD", OrderType.BUY, score=80.0)
        coordinator.update_xauusd_signal(gold_sig)

        jpy_sig = make_signal("USDJPY", OrderType.BUY, score=95.0, entry=154.50, sl=154.20, tp=155.10)
        res = coordinator.evaluate_usdjpy_candidate(jpy_sig)

        assert res.is_approved is False
        assert "INSTRUMENT_NOT_ALLOWED" in res.rationale

    def test_independent_validation_invariant(self):
        """USDJPY is never forced into a trade without its own valid setup."""
        coordinator = InverseDirectionCoordinator(enabled=True)
        gold_sig = make_signal("XAUUSD", OrderType.BUY, score=85.0)
        coordinator.update_xauusd_signal(gold_sig)

        assert coordinator.preferred_usdjpy_direction == OrderType.SELL
        assert coordinator.evaluate_usdjpy_candidate(None).is_approved is False
        assert "INSTRUMENT_NOT_ALLOWED" in coordinator.evaluate_usdjpy_candidate(None).rationale


# ---------------------------------------------------------------------------
# 6. OrderManager Pre-Trade Checklist Enforcement
# ---------------------------------------------------------------------------

class TestOrderManagerUniverseEnforcement:
    class MockBridge:
        def ping(self):
            return True

    def test_unauthorized_symbol_rejected_when_strict_universe_active(self):
        config = AppConfig()
        config.strict_three_symbol_universe = True

        order_manager = OrderManager(
            config=config,
            bridge=self.MockBridge(),
            sizing_engine=PositionSizingEngine(1.0),
            portfolio_risk=PortfolioRiskEngine(config),
        )

        unauthorized_cand = make_signal("EURUSD", OrderType.BUY, score=80.0, entry=1.0500, sl=1.0480, tp=1.0540)
        sym_info = SymbolInfo(symbol="EURUSD", bid=1.0500, ask=1.0502, point=0.0001, spread=2)
        account = AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)

        result = order_manager.run_pre_trade_checklist(
            candidate=unauthorized_cand,
            account=account,
            symbol_info=sym_info,
            active_positions=[],
        )

        assert result.passed is False
        assert any("INSTRUMENT_NOT_ALLOWED" in r or "Universe Restriction" in r for r in result.rejection_reasons)

    def test_authorized_gold_passes_when_strict_universe_active(self):
        config = AppConfig()
        config.strict_three_symbol_universe = True

        order_manager = OrderManager(
            config=config,
            bridge=self.MockBridge(),
            sizing_engine=PositionSizingEngine(1.0),
            portfolio_risk=PortfolioRiskEngine(config),
        )

        # Set weekday timestamp for candidate (Tuesday 14:00 UTC)
        tuesday_dt = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
        # Entry 2650, SL 2649 (1.0 distance), TP 2652 (2.0 distance) -> R:R 2.0
        gold_cand = make_signal("XAUUSD", OrderType.BUY, score=80.0, entry=2650.0, sl=2649.0, tp=2652.0, dt=tuesday_dt)
        sym_info = SymbolInfo(
            symbol="XAUUSD",
            bid=2650.0,
            ask=2650.3,
            point=0.01,
            spread=30,
            contract_size=100.0,
            tick_size=0.01,
            tick_value=1.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
        )
        account = AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)

        result = order_manager.run_pre_trade_checklist(
            candidate=gold_cand,
            account=account,
            symbol_info=sym_info,
            active_positions=[],
        )

        assert result.passed is True
        assert len(result.rejection_reasons) == 0

    def test_weekend_gold_order_rejected_by_schedule(self):
        config = AppConfig()
        config.strict_three_symbol_universe = True

        order_manager = OrderManager(
            config=config,
            bridge=self.MockBridge(),
            sizing_engine=PositionSizingEngine(1.0),
            portfolio_risk=PortfolioRiskEngine(config),
        )

        # Set Saturday timestamp for candidate
        saturday_dt = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)
        gold_cand = make_signal("XAUUSD", OrderType.BUY, score=80.0, entry=2650.0, sl=2649.0, tp=2652.0, dt=saturday_dt)
        sym_info = SymbolInfo(
            symbol="XAUUSD",
            bid=2650.0,
            ask=2650.3,
            point=0.01,
            spread=30,
            contract_size=100.0,
            tick_size=0.01,
            tick_value=1.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
        )
        account = AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)

        result = order_manager.run_pre_trade_checklist(
            candidate=gold_cand,
            account=account,
            symbol_info=sym_info,
            active_positions=[],
        )

        assert result.passed is False
        assert any("Schedule Mode" in r for r in result.rejection_reasons)


# ---------------------------------------------------------------------------
# 7. Orchestrator Integration Tests
# ---------------------------------------------------------------------------

class TestOrchestratorSpecializationIntegration:
    def test_orchestrator_rejects_unauthorized_symbol_with_outcome(self):
        from src.core.orchestrator import TradingBotOrchestrator

        config = AppConfig()
        config.dry_run = True
        config.strict_three_symbol_universe = True
        orchestrator = TradingBotOrchestrator(config=config)

        res = orchestrator.run_scalping_cycle_for_symbol("EURUSD")
        assert res is None

        # Check recorded decision outcome
        assert "EURUSD" in orchestrator.last_decision_outcomes
        outcome = orchestrator.last_decision_outcomes["EURUSD"]
        assert outcome.reason_code == "UNAUTHORIZED_SYMBOL"
        assert outcome.outcome_type == DecisionOutcomeType.NO_SETUP

    def test_orchestrator_skips_schedule_inactive_symbol(self):
        from src.core.orchestrator import TradingBotOrchestrator

        config = AppConfig()
        config.dry_run = True
        orchestrator = TradingBotOrchestrator(config=config)

        # Force weekend schedule on scheduler
        saturday_dt = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)
        # In weekend mode, XAUUSD is inactive
        is_eligible, _ = orchestrator.trading_scheduler.is_instrument_eligible_for_new_entry("XAUUSD", saturday_dt)
        assert is_eligible is False

    def test_orchestrator_dashboard_state_includes_specialized_metadata(self):
        from src.core.orchestrator import TradingBotOrchestrator

        config = AppConfig()
        config.dry_run = True
        orchestrator = TradingBotOrchestrator(config=config)

        state = orchestrator.get_dashboard_state()
        assert hasattr(state, "active_universe")
        assert "XAUUSD" in state.active_universe
        assert hasattr(state, "schedule_mode")
        assert hasattr(state, "correlation_regime")
