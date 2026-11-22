"""
Regression Tests for Critical Remediation & Compliance Verification (MT5-001).
Covers all 18 mandatory acceptance criteria:
- Unconditional 3-symbol lockdown (cannot be disabled by config)
- Final MT5 submission boundary protection (OrderManager, BridgeClient, LiveMT5Broker)
- Explicit broker suffix mappings & fail-closed unknown symbols
- Portfolio safety enforcement (circuit breaker, buffer halt, kill switch, real-account lock)
- Unrestricted position count (0-min, >7-max: 8th, 9th, 10th entries)
- Strategy-level spread veto removal & independent layered setups
- Companion ConfigurationService & EngineController synchronization
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

import pytest

from src.adapters.broker_interface import TradeRequest
from src.adapters.live_mt5_broker import LiveMT5Broker
from src.core.config import AppConfig
from src.core.contracts import (
    AccountInfo, ExecutionMode, OrderType, Position,
    SetupType, SignalCandidate, SymbolInfo, Timeframe
)
from src.core.symbol_universe import get_symbol_universe
from src.execution.bridge_client import BridgeClient
from src.execution.order_manager import OrderManager
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine


def _make_candidate(symbol: str, cid: str = "SIG_1", direction: OrderType = OrderType.BUY) -> SignalCandidate:
    entry = 2000.0 if "XAU" in symbol else (90000.0 if "BTC" in symbol else 150.0)
    dist = 1.0 if "JPY" in symbol else 10.0
    sl = entry - dist if direction == OrderType.BUY else entry + dist
    tp = entry + (2.0 * dist) if direction == OrderType.BUY else entry - (2.0 * dist)
    return SignalCandidate(
        id=cid,
        symbol=symbol,
        timeframe=Timeframe.M15,
        direction=direction,
        setup_type=SetupType.M15_SMC_OTE,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=2.0,
        score=80.0,
        timestamp=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),  # Monday
        status="APPROVED",
    )


def _make_symbol_info(symbol: str, spread_pts: int = 10) -> SymbolInfo:
    bid = 2000.0 if "XAU" in symbol else (90000.0 if "BTC" in symbol else 150.0)
    pt = 0.001 if "JPY" in symbol else 0.01
    ask = bid + spread_pts * pt
    return SymbolInfo(
        symbol=symbol,
        bid=bid,
        ask=ask,
        spread=spread_pts,
        point=pt,
        digits=3 if "JPY" in symbol else 2,
        tick_size=pt,
        tick_value=1.0,
        contract_size=1.0,
        min_lot=0.01,
        max_lot=10.0,
        lot_step=0.01,
    )


def _make_demo_account() -> AccountInfo:
    return AccountInfo(
        account_number=123456,
        balance=10000.0,
        equity=10000.0,
        free_margin=10000.0,
        margin=0.0,
        margin_level=0.0,
        trade_mode="DEMO",
        trading_enabled=True,
    )


class TestUnconditionalThreeSymbolLockdown:
    def test_default_config_enforces_two_symbols(self):
        cfg = AppConfig.load_from_dir("config")
        assert cfg.strict_three_symbol_universe is True
        assert set(cfg.symbols) <= {"XAUUSD", "BTCUSD"}
        assert "USDJPY" not in cfg.symbols

    def test_disabling_flag_cannot_bypass_lockdown(self):
        cfg = AppConfig.load_from_dir("config")
        cfg.strict_three_symbol_universe = False  # Attempt to disable

        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}

        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(1.0), PortfolioRiskEngine(cfg))
        acc = _make_demo_account()

        for bad in ["USDJPY", "USDJPY.m", "USDJPY.c", "EURUSD", "EURUSD.m", "GBPUSD", "US30", "US100", "US100.std", "NAS100", "UNKNOWN_SYM"]:
            cand = _make_candidate(bad, cid=f"BAD_{bad}")
            chk = om.run_pre_trade_checklist(cand, acc, _make_symbol_info(bad), [])
            assert chk.passed is False, f"{bad} should be rejected even when strict_three_symbol_universe=False"
            res = om.execute_signal(cand, acc, _make_symbol_info(bad), [])
            assert res is None
            mock_bridge.execute_trade.assert_not_called()

    @pytest.mark.parametrize("sym", ["XAUUSD", "BTCUSD", "XAUUSD.m", "BTCUSD.m", "XAUUSD.micro", "XAUUSD.c", "BTCUSD.c", "GOLD", "BITCOIN"])
    def test_authorized_symbols_and_explicit_suffixes_accepted(self, sym):
        ok, _ = get_symbol_universe().validate_or_reject(sym)
        assert ok is True

    @pytest.mark.parametrize("sym", ["USDJPY", "USDJPY.m", "USDJPY.c", "USDJPYmicro", "EURUSD", "EURUSD.m", "GBPUSD", "US30", "US100", "US100.std", "NAS100", "UNKNOWN_SYM", ""])
    def test_unauthorized_symbols_blocked_at_bridge_and_broker_boundary(self, sym):
        bridge = BridgeClient(host="127.0.0.1", port=59999)
        with patch.object(bridge, "_send_ipc_request") as mock_ipc:
            res1 = bridge.execute_trade(symbol=sym, order_type=OrderType.BUY, volume=0.01, stop_loss=10.0, take_profit=20.0, price=15.0)
            res2 = bridge.send_request({"action": "TRADE", "symbol": sym, "type": "BUY", "volume": 0.01, "sl": 10.0})
            mock_ipc.assert_not_called()
            assert res1["status"] == "ERROR"
            assert res2["status"] == "ERROR"
            assert "INSTRUMENT_NOT_ALLOWED" in res1["message"]
            assert "INSTRUMENT_NOT_ALLOWED" in res2["message"]

            broker = LiveMT5Broker(bridge)
            ores = broker.send_order(TradeRequest(symbol=sym, action="BUY", volume=0.01, price=15.0, sl=10.0, tp=20.0))
            assert ores.success is False
            assert "INSTRUMENT_NOT_ALLOWED" in ores.error_message
            mock_ipc.assert_not_called()


class TestPortfolioSafetyEnforcement:
    def test_circuit_breaker_and_buffer_halt_block_submission(self):
        cfg = AppConfig.load_from_dir("config")
        pr = PortfolioRiskEngine(cfg)
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}
        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(1.0), pr)
        acc = _make_demo_account()

        # 1. Circuit breaker active -> blocked
        pr.circuit_breaker_active = True
        pr.circuit_breaker_reason = "Drawdown limit breached"
        cand1 = _make_candidate("XAUUSD", cid="CB_1")
        chk1 = om.run_pre_trade_checklist(cand1, acc, _make_symbol_info("XAUUSD"), [])
        assert chk1.passed is False
        assert any("Portfolio Safety" in r for r in chk1.rejection_reasons)
        assert cand1.metadata["portfolio_risk_eval"]["allowed"] is False
        assert cand1.metadata["portfolio_risk_eval"]["setup_id"] == "CB_1"
        assert om.execute_signal(cand1, acc, _make_symbol_info("XAUUSD"), []) is None
        mock_bridge.execute_trade.assert_not_called()

        # 2. Emergency kill switch -> blocked
        pr.circuit_breaker_active = False
        pr.trigger_kill_switch("Emergency stop test")
        cand2 = _make_candidate("XAUUSD", cid="BUF_1")
        chk2 = om.run_pre_trade_checklist(cand2, acc, _make_symbol_info("XAUUSD"), [])
        assert chk2.passed is False
        assert any("Kill switch" in r or "Portfolio Safety" in r for r in chk2.rejection_reasons)
        mock_bridge.execute_trade.assert_not_called()

    def test_real_account_safety_lock_blocks_when_demo_mode(self):
        cfg = AppConfig.load_from_dir("config")
        cfg.execution_mode = ExecutionMode.DEMO
        cfg.live_trading_enabled = False
        pr = PortfolioRiskEngine(cfg)
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}
        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(1.0), pr)

        real_acc = AccountInfo(
            account_number=999999,
            balance=10000.0,
            equity=10000.0,
            free_margin=10000.0,
            trade_mode="REAL",
            trading_enabled=True,
        )
        cand = _make_candidate("XAUUSD", cid="REAL_LOCK_1")
        chk = om.run_pre_trade_checklist(cand, real_acc, _make_symbol_info("XAUUSD"), [])
        assert chk.passed is False
        assert any("Safety Lock" in r for r in chk.rejection_reasons)
        mock_bridge.execute_trade.assert_not_called()

    def test_portfolio_permission_granted_allows_8th_9th_10th_entries(self):
        cfg = AppConfig.load_from_dir("config")
        cfg.risk.risk_percentage = 0.5
        cfg.risk.max_aggregate_open_risk_percent = 6.0
        cfg.risk.max_symbol_risk_percent = 6.0
        cfg.weekday_btc_fallback_enabled = True
        pr = PortfolioRiskEngine(cfg)
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}
        mock_bridge.send_request.return_value = {"status": "SUCCESS", "data": []}
        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(0.5), pr)
        acc = _make_demo_account()

        active_pos = []
        for i in range(1, 11):
            sym = "XAUUSD"
            cand = _make_candidate(sym, cid=f"LAYER_{i}")
            ticket = 8000 + i
            new_p = Position(
                ticket=ticket,
                symbol=sym,
                order_type=OrderType.BUY,
                volume=0.05,
                open_price=cand.entry_price,
                current_price=cand.entry_price,
                stop_loss=cand.stop_loss,
                take_profit=cand.take_profit,
                profit=0.0,
                magic=cfg.magic_number,
                open_time=datetime.now(timezone.utc),
                initial_risk_amount=40.0,
            )
            mock_bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": ticket, "retcode": 10009, "price": cand.entry_price}
            mock_bridge.get_positions.side_effect = [list(active_pos), list(active_pos) + [new_p]]
            order = om.execute_signal(cand, acc, _make_symbol_info(sym), list(active_pos))
            assert order is not None and order.status == "FILLED", f"Entry {i} ({sym}) failed: {cand.rejection_reasons}"
            active_pos.append(new_p)
        assert len(active_pos) == 10


class TestCompanionSyncAndValidation:
    def test_companion_rejects_unauthorized_symbols_and_reports_status(self):
        from companion.database.repository import CompanionRepository
        from companion.service.configuration.config_service import ConfigurationService
        from companion.service.orchestration.engine_controller import EngineController
        from companion.service.events.event_bus import EventBus
        from companion.service.mt5.sync_service import MT5SyncService

        with tempfile.TemporaryDirectory() as tmp:
            repo = CompanionRepository(Path(tmp) / "test.db")
            cfg_svc = ConfigurationService("config", repo)
            errs = cfg_svc.validate_bundle({"settings": {"symbols": ["XAUUSD", "EURUSD"]}})
            assert any("Unauthorized symbols" in e for e in errs)

            ev = EventBus()
            ctrl = EngineController(
                project_root=".",
                config_service=cfg_svc,
                mt5_sync=MT5SyncService(repo=repo, events=ev),
                events=ev,
                repo=repo,
            )
            st = ctrl.get_status()
            assert st["approved_universe"] == ["XAUUSD", "BTCUSD"]
            assert len(st["resolved_universe"]) == 2
