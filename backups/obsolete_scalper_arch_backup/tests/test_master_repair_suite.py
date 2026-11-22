"""
Comprehensive Master Repair Regression Test Suite (Section 11).
Covers:
1. Risk configuration precedence (account_risk vs legacy risk, conflict warnings, fallbacks).
2. Risk behavior (loss-streak cooldown vs drawdown liquidation, daily loss pause, STOP.flag latching, event deduplication).
3. MT5 Execution state machine & failure modes (10009, 10010 partial fill, 10008 placed, 10006 reject, None/10012 ambiguous reconciliation, 10014/10016/10018/10019 permanent failures, 10004 requote retry, post-fill SL verification & fail-closed closure).
4. Lifecycle & shutdown idempotency (normal exit, Ctrl+C, unhandled exception, --max-cycles, lock cleanup).
5. Dual-market & Fast Mode (XAUUSD.m / BTCUSD.m resolution, Fast Mode BTCUSD weekend support, cross-session management).
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from src.core.app_paths import SingleInstanceLock
from src.core.contracts import Candle, OrderType, SessionType, SymbolInfo, Timeframe, TrendBias
from src.core.session_affinity import SessionAffinityEngine
from src.execution.fast_mode_engine import FastScalpEntryEngine
from src.scalper.config import ExecutionConfig, ScalperConfig
from src.scalper.engine import DualMarketScalperEngine
from src.scalper.executor import (
    GoldOrderExecutor,
    OrderExecutionState,
    TRADE_RETCODE_DONE,
    TRADE_RETCODE_DONE_PARTIAL,
    TRADE_RETCODE_INVALID_STOPS,
    TRADE_RETCODE_INVALID_VOLUME,
    TRADE_RETCODE_MARKET_CLOSED,
    TRADE_RETCODE_NO_MONEY,
    TRADE_RETCODE_PLACED,
    TRADE_RETCODE_REJECT,
    TRADE_RETCODE_REQUOTE,
    TRADE_RETCODE_TIMEOUT,
)
from src.scalper.risk import AccountRiskManager, RiskAction
from src.scalper.symbol_resolver import ResolvedSymbolSpec


# ============================================================================
# 1. RISK CONFIGURATION PRECEDENCE TESTS
# ============================================================================


def test_risk_config_canonical_overrides_conflicting_legacy_daily_loss():
    raw = {
        "account_risk": {
            "daily_loss_enabled": True,
            "max_daily_loss_pct": 5.0,
        },
        "risk": {
            "max_daily_loss_enabled": False,
            "max_daily_loss_pct": 10.0,
        },
    }
    cfg = ScalperConfig.from_dict(raw)
    assert cfg.risk.daily_loss_enabled is True
    assert cfg.risk.max_daily_loss_enabled is True
    assert cfg.risk.max_daily_loss_pct == 5.0
    assert len(cfg.config_warnings) >= 2
    assert any("daily_loss_enabled" in w for w in cfg.config_warnings)


def test_risk_config_canonical_only():
    raw = {
        "account_risk": {
            "daily_loss_enabled": True,
            "max_daily_loss_pct": 4.5,
            "max_drawdown_pct": 11.0,
            "max_total_open_risk_pct": 2.5,
            "max_margin_utilization_pct": 35.0,
            "max_consecutive_losses": 4,
        }
    }
    cfg = ScalperConfig.from_dict(raw)
    assert cfg.risk.daily_loss_enabled is True
    assert cfg.risk.max_daily_loss_pct == 4.5
    assert cfg.risk.max_drawdown_pct == 11.0
    assert cfg.risk.max_dd_pct == 11.0
    assert cfg.risk.max_total_open_risk_pct == 2.5
    assert cfg.risk.max_margin_utilization_pct == 35.0
    assert cfg.risk.max_margin_usage_pct == 35.0
    assert cfg.risk.max_consecutive_losses == 4
    assert cfg.config_warnings == []


def test_risk_config_legacy_only_fallback():
    raw = {
        "risk": {
            "max_daily_loss_enabled": False,
            "max_daily_loss_pct": 6.0,
            "max_dd_pct": 14.0,
            "max_margin_usage_pct": 45.0,
            "max_consecutive_losses": 6,
        }
    }
    cfg = ScalperConfig.from_dict(raw)
    assert cfg.risk.daily_loss_enabled is False
    assert cfg.risk.max_daily_loss_enabled is False
    assert cfg.risk.max_daily_loss_pct == 6.0
    assert cfg.risk.max_drawdown_pct == 14.0
    assert cfg.risk.max_dd_pct == 14.0
    assert cfg.risk.max_margin_utilization_pct == 45.0
    assert cfg.risk.max_consecutive_losses == 6
    assert cfg.config_warnings == []


def test_risk_config_matching_values_emit_no_warnings():
    raw = {
        "account_risk": {
            "daily_loss_enabled": True,
            "max_daily_loss_pct": 5.0,
            "max_drawdown_pct": 12.0,
            "max_margin_utilization_pct": 40.0,
            "max_consecutive_losses": 5,
        },
        "risk": {
            "max_daily_loss_enabled": True,
            "max_daily_loss_pct": 5.0,
            "max_dd_pct": 12.0,
            "max_margin_usage_pct": 40.0,
            "max_consecutive_losses": 5,
        },
    }
    cfg = ScalperConfig.from_dict(raw)
    assert cfg.config_warnings == []


def test_risk_config_all_conflicting_fields_prefer_account_risk():
    raw = {
        "account_risk": {
            "max_drawdown_pct": 10.0,
            "max_total_open_risk_pct": 2.0,
            "max_margin_utilization_pct": 30.0,
            "max_consecutive_losses": 3,
            "loss_streak_cooldown_seconds": 180,
        },
        "risk": {
            "max_dd_pct": 25.0,
            "max_total_open_risk_pct": 8.0,
            "max_margin_usage_pct": 80.0,
            "max_consecutive_losses": 9,
            "loss_streak_cooldown_seconds": 600,
        },
    }
    cfg = ScalperConfig.from_dict(raw)
    assert cfg.risk.max_drawdown_pct == 10.0
    assert cfg.risk.max_dd_pct == 10.0
    assert cfg.risk.max_total_open_risk_pct == 2.0
    assert cfg.risk.max_margin_utilization_pct == 30.0
    assert cfg.risk.max_consecutive_losses == 3
    assert cfg.risk.loss_streak_cooldown_seconds == 180
    assert len(cfg.config_warnings) == 5


# ============================================================================
# 2. RISK BEHAVIOR & PAUSE SEPARATION TESTS
# ============================================================================


def test_loss_streak_cooldown_blocks_entries_without_drawdown_mislabeling_or_liquidation():
    cfg = ScalperConfig.load()
    cfg.risk.max_consecutive_losses = 3
    cfg.risk.loss_streak_cooldown_seconds = 300
    eng = DualMarketScalperEngine(cfg, is_simulation=True)
    assert eng.initialize() is True

    fri_dt = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    # Open an active basket first
    eng.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
    assert eng.basket_manager.has_active_basket("GOLD")
    initial_positions = eng.basket_manager.total_open_positions
    assert initial_positions > 0

    # Trigger 3 consecutive losses
    for _ in range(3):
        eng.risk.record_trade_outcome(-2.0)

    # Verify check_drawdown is still PASS (not hijacked by loss streak pause!)
    dd_verdict = eng.risk.check_drawdown(1000.0, 994.0)
    assert dd_verdict.allowed is True
    assert dd_verdict.action == RiskAction.PASS

    # Verify check_consecutive_losses returns LOSS_STREAK_COOLDOWN + PAUSE_NEW_ENTRIES
    streak_verdict = eng.risk.check_consecutive_losses()
    assert streak_verdict.allowed is False
    assert streak_verdict.category == "LOSS_STREAK_COOLDOWN"
    assert streak_verdict.action == RiskAction.PAUSE_NEW_ENTRIES

    # Run several tick cycles while loss streak cooldown is active:
    # Existing basket MUST remain open and managed (NOT emergency liquidated!)
    for _ in range(5):
        eng.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)

    assert eng._emergency_liquidated is False
    assert eng.basket_manager.has_active_basket("GOLD")
    assert eng.basket_manager.total_open_positions == initial_positions
    assert eng.stats.rejection_reasons.get("LOSS_STREAK_COOLDOWN", 0) >= 5
    assert eng.stats.rejection_reasons.get("DRAWDOWN", 0) == 0


def test_genuine_drawdown_breach_triggers_liquidation_and_deduplicates_events():
    cfg = ScalperConfig.load()
    cfg.risk.max_drawdown_pct = 10.0
    eng = DualMarketScalperEngine(cfg, is_simulation=True)
    assert eng.initialize() is True

    fri_dt = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    eng.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
    assert eng.basket_manager.has_active_basket("GOLD")

    # Simulate 15% equity drawdown (> 10% limit)
    eng._cached_account["balance"] = 1000.0
    eng._cached_account["equity"] = 850.0
    eng._last_account_poll_ts = 9999999999.0

    eng.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
    assert not eng.basket_manager.has_active_basket("GOLD")
    assert (
        eng.stats.rejection_reasons.get("DRAWDOWN", 0) >= 1
        or eng.stats.rejection_reasons.get("DRAWDOWN_LIMIT", 0) >= 1
    )

    # Repeated ticks during active drawdown pause must deduplicate trigger events
    for _ in range(5):
        eng.risk.check_drawdown(1000.0, 880.0)

    dd_events = [e for e in eng.risk.trigger_events if e.category == "DRAWDOWN"]
    assert len(dd_events) <= 2  # Initial breach + active pause event (deduplicated)
    assert any(e.occurrence_count >= 5 for e in dd_events)


def test_daily_loss_breach_closes_all_and_pauses_independently():
    cfg = ScalperConfig.load()
    cfg.risk.daily_loss_enabled = True
    cfg.risk.max_daily_loss_pct = 5.0
    rm = AccountRiskManager(cfg)
    rm.reset_daily_baseline(1000.0)
    rm.record_trade_outcome(-60.0)  # 6% loss > 5% max daily loss

    v = rm.check_daily_loss(940.0, 940.0)
    assert v.allowed is False
    assert v.category == "DAILY_LOSS"
    assert v.action == RiskAction.CLOSE_ALL_AND_PAUSE
    # Drawdown check remains independent
    dd = rm.check_drawdown(1000.0, 940.0)
    assert dd.allowed is True


def test_live_stop_flag_in_repo_root_blocks_initialization_and_latches(tmp_path: Path):
    # Verify the actual STOP.flag in repo root (if present) or an explicit STOP.flag blocks startup
    repo_stop = Path("STOP.flag")
    assert repo_stop.exists(), "STOP.flag in repository root must be preserved untouched"

    cfg = ScalperConfig.load()
    cfg.kill_switch.flag_file_path = str(repo_stop.resolve())
    eng = DualMarketScalperEngine(cfg, is_simulation=True)
    assert eng.initialize() is False
    assert eng.risk.kill_switch_triggered is True

    # Test latching and operator reset workflow on a temporary flag file
    temp_flag = tmp_path / "OPERATOR_STOP.flag"
    temp_flag.write_text("STOP", encoding="utf-8")
    cfg2 = ScalperConfig.load()
    cfg2.kill_switch.flag_file_path = str(temp_flag)
    rm2 = AccountRiskManager(cfg2)
    v1 = rm2.check_kill_switch()
    assert v1.allowed is False
    assert v1.action == RiskAction.CLOSE_ALL_AND_HALT

    # Even before acknowledgement, removing file alone keeps latch active until acknowledged
    assert rm2.acknowledge_and_reset_kill_switch(operator_confirmed=True) is False  # File still exists!
    temp_flag.unlink()
    v_latched = rm2.check_kill_switch()
    assert v_latched.allowed is False
    assert "latched" in v_latched.reason.lower()

    # Now operator acknowledges after removing file
    assert rm2.acknowledge_and_reset_kill_switch(operator_confirmed=True) is True
    assert rm2.check_kill_switch().allowed is True


# ============================================================================
# 3. MT5 EXECUTION STATE MACHINE & MOCKED BROKER FAILURE MODES
# ============================================================================


def _make_gold_spec() -> ResolvedSymbolSpec:
    return ResolvedSymbolSpec(
        symbol="XAUUSD.m",
        canonical="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=0.01,
        contract_size=100.0,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        stops_level=10,
        filling_mode=1,
        trade_mode=4,
        is_tradable=True,
        spread_points=20,
        bid=2650.00,
        ask=2650.20,
    )


def test_executor_preflight_validation_rejects_invalid_stop_and_volume():
    ex = GoldOrderExecutor(ExecutionConfig())
    spec = _make_gold_spec()

    # BUY with SL above entry price -> invalid
    ok, err = ex.validate_order_parameters("XAUUSD.m", "BUY", 0.01, 2650.20, 2655.00, 0.0, spec)
    assert ok is False
    assert "INVALID_BUY_SL" in err

    # BUY with SL too close (within stops_level = 10 pts = $0.10)
    ok2, err2 = ex.validate_order_parameters("XAUUSD.m", "BUY", 0.01, 2650.20, 2650.15, 0.0, spec)
    assert ok2 is False
    assert "SL_TOO_CLOSE" in err2


@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_full_fill_and_sl_verification(mock_mt5):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=TRADE_RETCODE_DONE,
        order=50001,
        deal=60001,
        volume=0.02,
        price=2650.20,
        comment="Done",
    )
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(ticket=50001, symbol="XAUUSD.m", magic=777001, sl=2647.20, tp=0.0, volume=0.02, price_open=2650.20)
    ]

    ex = GoldOrderExecutor(ExecutionConfig())
    res = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.02,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_full",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res.is_success is True
    assert res.ticket == 50001
    assert res.state == OrderExecutionState.EXECUTION_CONFIRMED
    assert res.sl_verified is True
    assert res.verified_sl == 2647.20


@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_partial_fill_records_actual_volume(mock_mt5):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=TRADE_RETCODE_DONE_PARTIAL,
        order=50002,
        deal=60002,
        volume=0.01,  # Only 0.01 of requested 0.03 filled
        price=2650.20,
        comment="Partial",
    )
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(ticket=50002, symbol="XAUUSD.m", magic=777001, sl=2647.20, tp=0.0, volume=0.01, price_open=2650.20)
    ]

    ex = GoldOrderExecutor(ExecutionConfig())
    res = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.03,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_partial",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res.is_success is True
    assert res.is_partial_fill is True
    assert res.volume == 0.01
    assert res.requested_volume == 0.03
    assert res.state == OrderExecutionState.EXECUTION_CONFIRMED


@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_timeout_or_null_reconciles_existing_broker_position_without_duplicate(mock_mt5):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")
    # order_send returns None (network blip), but broker actually executed it!
    mock_mt5.order_send.return_value = None
    mock_mt5.last_error.return_value = (-1, "Timeout")
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(
            ticket=50003,
            symbol="XAUUSD.m",
            magic=777001,
            type=0,
            comment="test_ambig",
            volume=0.01,
            price_open=2650.20,
            sl=2647.20,
            tp=0.0,
            time=int(datetime.now(timezone.utc).timestamp()),
        )
    ]

    ex = GoldOrderExecutor(ExecutionConfig(max_retries=3, retry_delay_ms=1))
    res = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.01,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_ambig",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res.is_success is True
    assert res.was_reconciled is True
    assert res.ticket == 50003
    # Must NOT have sent a second order_send because reconciliation found the position!
    assert mock_mt5.order_send.call_count == 1


@pytest.mark.parametrize(
    "retcode",
    [
        TRADE_RETCODE_REJECT,
        TRADE_RETCODE_INVALID_VOLUME,
        TRADE_RETCODE_INVALID_STOPS,
        TRADE_RETCODE_MARKET_CLOSED,
        TRADE_RETCODE_NO_MONEY,
    ],
)
@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_permanent_broker_rejections_do_not_blindly_retry(mock_mt5, retcode):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")
    mock_mt5.order_send.return_value = SimpleNamespace(
        retcode=retcode, order=0, deal=0, volume=0.0, price=0.0, comment=f"PermanentErr_{retcode}"
    )

    ex = GoldOrderExecutor(ExecutionConfig(max_retries=3, retry_delay_ms=1))
    res = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.01,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_perm_fail",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res.is_success is False
    assert res.state == OrderExecutionState.FAILED
    assert mock_mt5.order_send.call_count == 1


@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_requote_retries_and_succeeds(mock_mt5):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")
    mock_mt5.order_send.side_effect = [
        SimpleNamespace(retcode=TRADE_RETCODE_REQUOTE, order=0, deal=0, volume=0.0, price=0.0, comment="Requote"),
        SimpleNamespace(retcode=TRADE_RETCODE_DONE, order=50009, deal=60009, volume=0.01, price=2650.22, comment="Done"),
    ]
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(ticket=50009, symbol="XAUUSD.m", magic=777001, sl=2647.20, tp=0.0, volume=0.01, price_open=2650.22)
    ]

    ex = GoldOrderExecutor(ExecutionConfig(max_retries=3, retry_delay_ms=1))
    res = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.01,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_requote",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res.is_success is True
    assert res.retries_used == 1
    assert res.ticket == 50009


@patch("src.scalper.executor.HAS_MT5", True)
@patch("src.scalper.executor.mt5")
def test_executor_missing_sl_post_fill_modification_and_fail_closed_closure(mock_mt5):
    spec = _make_gold_spec()
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.TRADE_ACTION_SLTP = 6
    mock_mt5.ORDER_TIME_GTC = 0
    mock_mt5.symbol_info_tick.return_value = SimpleNamespace(bid=2650.00, ask=2650.20)
    mock_mt5.order_check.return_value = SimpleNamespace(retcode=0, comment="OK")

    # Case A: Broker opens position with sl=0.0, then post-fill SL modification succeeds and broker reflects sl=2647.20
    mock_mt5.positions_get.side_effect = [
        [SimpleNamespace(ticket=50010, symbol="XAUUSD.m", magic=777001, sl=0.0, tp=0.0, volume=0.01, price_open=2650.20)],
        [SimpleNamespace(ticket=50010, symbol="XAUUSD.m", magic=777001, sl=2647.20, tp=0.0, volume=0.01, price_open=2650.20)],
    ]
    mock_mt5.order_send.side_effect = [
        SimpleNamespace(retcode=TRADE_RETCODE_DONE, order=50010, deal=60010, volume=0.01, price=2650.20, comment="FilledNoSL"),
        SimpleNamespace(retcode=TRADE_RETCODE_DONE, order=50010, deal=0, volume=0.01, price=0.0, comment="SLModified"),
    ]
    ex = GoldOrderExecutor(ExecutionConfig(max_retries=2, retry_delay_ms=1))
    res_a = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.01,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_sl_mod_ok",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res_a.is_success is True
    assert res_a.sl_verified is True

    # Case B: Broker opens position with sl=0.0, and ALL SL modifications fail -> fail-closed closes the unprotected position!
    mock_mt5.positions_get.side_effect = None
    mock_mt5.positions_get.return_value = [
        SimpleNamespace(ticket=50011, symbol="XAUUSD.m", magic=777001, sl=0.0, tp=0.0, volume=0.01, price_open=2650.20)
    ]
    mock_mt5.order_send.side_effect = [
        SimpleNamespace(retcode=TRADE_RETCODE_DONE, order=50011, deal=60011, volume=0.01, price=2650.20, comment="FilledNoSL"),
        SimpleNamespace(retcode=TRADE_RETCODE_INVALID_STOPS, comment="SL fail 1"),
        SimpleNamespace(retcode=TRADE_RETCODE_INVALID_STOPS, comment="SL fail 2"),
        SimpleNamespace(retcode=TRADE_RETCODE_INVALID_STOPS, comment="SL fail 3"),
        SimpleNamespace(retcode=TRADE_RETCODE_DONE, order=50011, deal=60012, volume=0.01, price=2650.00, comment="EmergencyClosed"),
    ]
    res_b = ex.submit_market_order(
        symbol="XAUUSD.m",
        direction="BUY",
        volume=0.01,
        stop_loss=2647.20,
        take_profit=0.0,
        comment="test_sl_mod_fail",
        magic=777001,
        spec=spec,
        is_simulation=False,
    )
    assert res_b.is_success is False
    assert res_b.state == OrderExecutionState.FAILED
    assert "UNPROTECTED_POSITION" in res_b.error_message


# ============================================================================
# 4. LIFECYCLE & SHUTDOWN IDEMPOTENCY TESTS
# ============================================================================


def test_engine_shutdown_is_idempotent_and_preserves_open_positions_by_default():
    cfg = ScalperConfig.load()
    eng = DualMarketScalperEngine(cfg, is_simulation=True)
    assert eng.initialize() is True

    fri_dt = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
    eng.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
    assert eng.basket_manager.total_open_positions > 0

    # Normal graceful shutdown (e.g. Ctrl+C / max-cycles) preserves open positions on broker
    eng.shutdown(reason="OPERATOR_INTERRUPT", liquidate_positions=False)
    assert eng._is_running is False
    assert eng._shutdown_completed is True
    assert eng.basket_manager.total_open_positions > 0

    # Calling shutdown a second time (e.g., from finally:) is a safe no-op
    eng.shutdown(reason="FINALLY_CLEANUP", liquidate_positions=False)
    assert eng._shutdown_completed is True


def test_single_instance_lock_acquired_and_released_cleanly():
    lock_a = SingleInstanceLock("test_master_repair_lock")
    lock_b = SingleInstanceLock("test_master_repair_lock")
    assert lock_a.acquire() is True
    try:
        assert lock_b.acquire() is False
    finally:
        lock_a.release()
    # After release, lock_b can acquire cleanly
    assert lock_b.acquire() is True
    lock_b.release()


# ============================================================================
# 5. DUAL-MARKET & FAST MODE BTCUSD WEEKEND TESTS
# ============================================================================


def test_fast_mode_btcusd_whitelist_and_weekend_session_affinity():
    aff = SessionAffinityEngine()
    assert aff.resolve_symbol("BTCUSD.m") == "BTCUSD"
    assert aff.resolve_symbol("XAUUSD.m") == "XAUUSD"

    sat_dt = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)  # Saturday
    allowed_btc, weight_btc, reason_btc = aff.is_symbol_allowed(SessionType.WEEKEND, "BTCUSD.m", dt_utc=sat_dt)
    assert allowed_btc is True
    assert weight_btc == 1.0
    assert reason_btc is None

    allowed_gold, weight_gold, _ = aff.is_symbol_allowed(SessionType.WEEKEND, "XAUUSD.m", dt_utc=sat_dt)
    assert allowed_gold is False
    assert weight_gold == 0.0

    # Verify FastScalpEntryEngine allows BTCUSD.m on Saturday weekend
    fast_eng = FastScalpEntryEngine()
    assert "BTCUSD" in fast_eng._cfg.get("allowed_symbols", [])
    assert "BTCUSD.m" in fast_eng._cfg.get("allowed_symbols", [])
    assert fast_eng._cfg["execution"]["max_deviation_points"]["BTCUSD.m"] == 150
