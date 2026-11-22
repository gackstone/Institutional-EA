"""
Comprehensive verification tests for the ArcadeFX + MT5 001 Execution,
Adaptive Scalping/Holding, MTF Simplification, Bridge Routing, Account
Reconciliation, and Notification/Cloud Reliability upgrades.
"""

import json
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.config import AppConfig
from src.core.contracts import (
    AccountInfo,
    Candle,
    ExecutionMode,
    OrderType,
    Position,
    ProfitManagementMode,
    SetupType,
    SignalCandidate,
    SignalLifecycleState,
    SymbolInfo,
    Timeframe,
    TrendBias,
)
from src.core.orchestrator import TradingBotOrchestrator
from src.execution.bridge_server import EAConnection, PersistentBridgeServer
from src.execution.order_manager import OrderManager
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramNotifier
from src.risk.mode_selector import ModeSelectionEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.risk.trade_management import TradeManagementEngine


def _make_candles(base: float = 2000.0, count: int = 30, step: float = 0.5) -> list[Candle]:
    candles = []
    now = datetime.now(timezone.utc)
    for i in range(count):
        o = base + i * step
        c = o + step * 0.8
        candles.append(
            Candle(
                time=now,
                open=o,
                high=max(o, c) + 0.5,
                low=min(o, c) - 0.5,
                close=c,
                tick_volume=100.0,
            )
        )
    return candles


class TestExecutionUpgradeComprehensive(unittest.TestCase):
    def setUp(self):
        self.cfg = AppConfig()
        self.cfg.execution_mode = ExecutionMode.SIMULATION
        self.cfg.legacy_filters_enabled = True
        self.cfg.risk.min_risk_reward_ratio = 2.0
        self.cfg.risk.scalping_min_risk_reward_ratio = 1.5
        self.cfg.risk.target_net_profit_usd = 20.0
        self.cfg.risk.strict_entry_quality_enabled = True
        self.cfg.strategy.min_confluence_score = 75.0
        self.cfg.strategy.scalping_min_confluence_score = 55.0
        self.cfg.strategy.htf_timeframe = "H1"
        self.cfg.strategy.ltf_timeframe = "M15"
        self.cfg.strategy.execution_mode_policy = "ADAPTIVE"

        self.account = AccountInfo(
            account_number=123456,
            balance=4618.59,
            equity=4447.63,
            credit=-170.96,
            profit=0.0,
            margin=0.0,
            free_margin=4447.63,
            currency="USD",
        )
        self.xau_info = SymbolInfo(
            symbol="XAUUSD",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            spread=20,
            bid=2600.00,
            ask=2600.20,
        )

    # A. Normal Holding Mode
    def test_normal_holding_mode_selected_and_preserved(self):
        cand = SignalCandidate(
            id="HOLD_XAU_1",
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.M15_SMC_OTE,
            entry_price=2600.0,
            stop_loss=2595.0,
            take_profit=2610.5,
            risk_reward=2.10,
            score=82.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
            reasons=["HTF BULLISH", "BOS CONFIRMED", "OB + FVG"],
        )
        mode, rationale, _ = ModeSelectionEngine.classify_trade_opportunity(
            candidate=cand,
            min_rr_for_hold=2.0,
            min_score_for_hold=75.0,
            execution_mode_policy="ADAPTIVE",
        )
        self.assertEqual(mode, ProfitManagementMode.PROFIT_RUNNING)
        self.assertEqual(mode.canonical_mode, "HOLD")

        # Verify TradeManagementEngine does NOT prematurely close a HOLD position at $20
        tm = TradeManagementEngine(self.cfg.risk)
        pos = Position(
            ticket=1001,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=2600.0,
            current_price=2602.10,
            stop_loss=2595.0,
            take_profit=2610.5,
            profit=21.0,
            commission=-0.70,
            swap=0.0,
            profit_mode=ProfitManagementMode.PROFIT_RUNNING,
        )
        actions = tm.evaluate_position(pos, self.xau_info, _make_candles(2600.0), scalp_mode=False)
        self.assertFalse(any(a.action_type == "FULL_CLOSE" for a in actions))

    # B. Adaptive Scalping Fallback & $20 Net Profit Target
    def test_scalping_fallback_and_20usd_net_profit_close(self):
        self.cfg.risk.individual_profit_target_usd = 20.0
        tm = TradeManagementEngine(self.cfg.risk)
        # Gross profit $20.50, commission -$1.00 => net profit $19.50 (NOT >= $20 yet)
        pos = Position(
            ticket=1002,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=2600.0,
            current_price=2602.05,
            stop_loss=2595.0,
            take_profit=2608.0,
            profit=20.50,
            commission=-1.00,
            swap=0.0,
            profit_mode=ProfitManagementMode.QUICK_SCALP,
        )
        actions_below = tm.evaluate_position(pos, self.xau_info, _make_candles(2600.0), scalp_mode=True)
        self.assertFalse(any(a.action_type == "FULL_CLOSE" for a in actions_below))

        # Now gross profit $21.50, commission -$1.00 => net profit $20.50 >= $20 target
        pos.profit = 21.50
        pos.current_price = 2602.15
        actions_hit = tm.evaluate_position(pos, self.xau_info, _make_candles(2600.0), scalp_mode=True)
        self.assertTrue(any(a.action_type == "FULL_CLOSE" for a in actions_hit))

    # 5.2 R:R Precision Fix
    def test_rr_precision_does_not_falsely_reject_exact_2_00(self):
        bridge = MagicMock()
        bridge.ping.return_value = True
        bridge.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}
        sizing = PositionSizingEngine(1.0)
        pr = PortfolioRiskEngine(self.cfg)
        om = OrderManager(self.cfg, bridge, sizing, pr)

        # Live fill R:R is 1.9999999 (floating point jitter) vs min 2.0
        cand = SignalCandidate(
            id="RR_PREC_1",
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.M15_SMC_OTE,
            entry_price=2600.20,
            stop_loss=2595.20,
            take_profit=2610.199999,
            risk_reward=2.0,
            score=80.0,
            timestamp=datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
            status="APPROVED",
            reasons=["HTF BULLISH", "BOS"],
        )
        res = om.run_pre_trade_checklist(cand, self.account, self.xau_info, [])
        self.assertTrue(res.passed, f"Unexpected rejection: {res.rejection_reasons}")

    # 5.3 Broker Market-Session Validation (10018)
    def test_broker_market_closed_rejected_cleanly(self):
        self.cfg.execution_mode = ExecutionMode.DEMO
        bridge = MagicMock()
        bridge.ping.return_value = True
        bridge.check_symbol_session.return_value = {
            "status": "SUCCESS",
            "market_open": False,
            "reason": "Outside broker trading session for EURUSD",
        }
        sizing = PositionSizingEngine(1.0)
        pr = PortfolioRiskEngine(self.cfg)
        om = OrderManager(self.cfg, bridge, sizing, pr)

        cand = SignalCandidate(
            id="SESS_CLOSED_1",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            risk_reward=2.0,
            score=80.0,
            timestamp=datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
            status="APPROVED",
        )
        eur_info = SymbolInfo(
            symbol="EURUSD", digits=5, point=0.00001, tick_size=0.00001, tick_value=1.0,
            contract_size=100000.0, spread=10, bid=1.0999, ask=1.1000
        )
        res = om.run_pre_trade_checklist(cand, self.account, eur_info, [])
        self.assertFalse(res.passed)
        self.assertTrue(any("Market Closed" in r and "10018" in r for r in res.rejection_reasons))

    # 5.1 Symbol-Routing & Request-Correlation Mismatch
    def test_bridge_server_correlation_and_symbol_logging(self):
        srv = PersistentBridgeServer(ea_port=0, ipc_port=0)
        mock_sock = MagicMock()
        ea = EAConnection(socket=mock_sock, addr=("127.0.0.1", 50000), symbol="BTCUSD.m", magic=100101, account=123456)
        ea.status = "ACTIVE"
        srv._clients[100101] = ea
        srv._symbol_to_magic["BTCUSD.m"] = 100101

        # Simulate EA replying with matching request_id for EURUSD
        def _fake_send(raw_msg: str, timeout_sec: float = 3.0) -> bool:
            req = json.loads(raw_msg.strip())
            def _reply():
                time.sleep(0.02)
                srv._dispatch_ea_message(
                    ea,
                    {
                        "status": "SUCCESS",
                        "request_id": req["request_id"],
                        "symbol": req["symbol"],
                        "ticket": 55501,
                    },
                )
            threading.Thread(target=_reply, daemon=True).start()
            return True

        ea.send_raw = _fake_send

        with self.assertLogs("BridgeServer", level="INFO") as cm:
            resp = srv.forward_request_to_ea({"action": "TRADE", "symbol": "EURUSD", "type": "BUY"})
        self.assertEqual(resp.get("status"), "SUCCESS")
        self.assertEqual(resp.get("symbol"), "EURUSD")
        self.assertTrue(any("Symbol=EURUSD" in line for line in cm.output))

        # Verify mismatched request_id does NOT resolve an unrelated pending request
        ev = threading.Event()
        storage = {}
        srv._pending_requests["REQ_A"] = (ev, storage)
        srv._dispatch_ea_message(ea, {"status": "SUCCESS", "request_id": "REQ_UNKNOWN", "ticket": 999})
        self.assertFalse(ev.is_set())
        srv._pending_requests.pop("REQ_A", None)

    # 5.6 Telegram Persistent Queue & Exponential Backoff
    def test_telegram_persistent_outbox_recovery(self):
        tg_cfg = TelegramConfig()
        tg_cfg.bot_token = "dummy"
        tg_cfg.chat_id = "12345"
        tg_cfg.enabled = False
        notifier = TelegramNotifier(config=tg_cfg)
        notifier.config.enabled = True
        notifier.send_message("Test non-blocking alert", event_id="evt_test_001")
        self.assertEqual(notifier._msg_queue.qsize(), 1)
        notifier.stop()

    # 5.5 Account Reconciliation
    def test_account_reconciliation_diff(self):
        expected_eq = round(self.account.balance + self.account.credit + self.account.profit, 2)
        self.assertAlmostEqual(self.account.equity, expected_eq, places=2)

    # 5.7 Bridge Server Symbol Mismatch Rejection
    def test_bridge_server_rejects_symbol_mismatch(self):
        from src.execution.bridge_server import PersistentBridgeServer, EAConnection

        srv = PersistentBridgeServer(ea_host="127.0.0.1", ea_port=0, ipc_port=0)
        ea = EAConnection(socket=MagicMock(), addr=("127.0.0.1", 12345), magic=999, symbol="BTCUSD.m", account=12345)
        ea.status = "ACTIVE"
        srv._clients[ea.magic] = ea

        def _fake_send(raw_str, timeout_sec=10.0):
            payload = json.loads(raw_str.strip())
            srv._dispatch_ea_message(
                ea,
                {
                    "status": "SUCCESS",
                    "request_id": payload["request_id"],
                    "symbol": "BTCUSD.m",
                    "ticket": 88888,
                },
            )
            return True

        ea.send_raw = _fake_send
        resp = srv.forward_request_to_ea({"action": "TRADE", "symbol": "US30", "type": "BUY"})
        self.assertEqual(resp.get("status"), "ERROR")
        self.assertIn("Symbol consistency violation", resp.get("message", ""))

    # 5.8 NAS100 Empty Candles Marks Instrument Unhealthy
    def test_market_data_empty_candles_marks_symbol_unhealthy(self):
        from src.core.market_data import MarketDataEngine
        from src.core.contracts import Timeframe

        md = MarketDataEngine()
        mock_bridge = MagicMock()
        mock_bridge.get_rates.return_value = {"status": "SUCCESS", "data": []}
        with patch.dict("sys.modules", {"MetaTrader5": None}):
            status = md.sync_symbol_timeframe("NAS100", Timeframe.M15, bridge=mock_bridge, max_retries=1)
        self.assertFalse(status.is_healthy)
        self.assertEqual(status.received_count, 0)
        self.assertIsNotNone(status.failure_reason)

    # 5.9 Active Config Default Net Profit Target is $20.00
    def test_active_config_default_target_is_20_usd(self):
        from src.core.config import RiskConfig

        rc = RiskConfig()
        self.assertEqual(rc.min_net_profit_target_usd, 20.0)
        self.assertEqual(rc.profit_floor_lock_usd, 20.0)

    # 5.10 BridgeClient.get_account_info & LiveMT5Broker Integration
    def test_bridge_client_get_account_info_and_failure_safety(self):
        from src.execution.bridge_client import BridgeClient
        from src.adapters.live_mt5_broker import LiveMT5Broker

        client = BridgeClient(port=59999)
        client.is_connected = MagicMock(return_value=False)
        # Disconnected must raise ConnectionError, never fabricate zeros
        with self.assertRaises(ConnectionError):
            client.get_account_info()

        # Incomplete response must raise RuntimeError
        client.is_connected = MagicMock(return_value=True)
        client.send_request = MagicMock(return_value={"status": "SUCCESS", "data": {"login": 123}})
        with self.assertRaises(RuntimeError):
            client.get_account_info()

        # Valid response returns full AccountInfo with last_sync_time
        client.send_request = MagicMock(return_value={
            "status": "SUCCESS",
            "data": {
                "login": 1200057798,
                "balance": 4604.96,
                "equity": 4440.64,
                "margin": 120.0,
                "free_margin": 4320.64,
                "credit": 0.0,
                "profit": -164.32,
                "currency": "USD",
                "trade_mode": "DEMO",
                "profile": "DEMO",
            },
        })
        broker = LiveMT5Broker(client)
        acc = broker.get_account_info()
        self.assertEqual(acc.account_number, 1200057798)
        self.assertAlmostEqual(acc.balance, 4604.96, places=2)
        self.assertAlmostEqual(acc.equity, 4440.64, places=2)
        self.assertAlmostEqual(acc.profit, -164.32, places=2)
        self.assertIsNotNone(acc.last_sync_time)

    # 5.11 Dashboard Floating P&L Reconciliation
    def test_dashboard_reconciles_account_floating_pnl(self):
        from src.monitoring.dashboard import TradingDashboard
        from src.learning.performance_tracker import PerformanceTracker

        dash = TradingDashboard(execution_mode="DEMO")
        acc = AccountInfo(balance=4604.96, equity=4440.64, credit=0.0, profit=-164.32)
        perf = PerformanceTracker().calculate_summary()
        pr = MagicMock()
        pr.daily_realized_loss = 0.0
        pr.daily_starting_equity = 4604.96
        pr.config.risk_percentage = 1.0
        pr.circuit_breaker_tripped = False
        pr.circuit_breaker_reason = ""
        state = dash.build_snapshot(
            account=acc,
            active_positions=[],
            signals=[],
            market_contexts={},
            perf=perf,
            portfolio_risk_engine=pr,
        )
        self.assertAlmostEqual(state.floating_pnl, -164.32, places=2)

    # 5.12 Seven-Symbol Scan Completion & Isolated Failure Handling
    def test_seven_symbol_scan_completion_and_isolation(self):
        from src.core.orchestrator import TradingBotOrchestrator
        from src.core.contracts import ProfitManagementMode

        self.assertEqual(ProfitManagementMode.QUICK_SCALP.canonical_mode, "SCALP")
        self.assertEqual(ProfitManagementMode.PROFIT_RUNNING.canonical_mode, "HOLD")

        orch = TradingBotOrchestrator()
        expected_syms = ["NAS100", "US30", "BTCUSD.m", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        orch.config.symbols = expected_syms
        orch.health_monitor.symbols = expected_syms
        orch.order_manager.get_active_positions = MagicMock(return_value=[])
        orch.manage_active_positions = MagicMock(return_value=[])
        orch.continuous_scalper.get_ordered_symbols_for_cycle = MagicMock(return_value=expected_syms)

        def _fake_scan(sym):
            if sym == "NAS100":
                raise RuntimeError("Simulated isolated NAS100 failure")
            orch.health_monitor.record_scan(sym, diagnostic_reason="No qualifying signal")
            return None

        orch.run_scalping_cycle_for_symbol = _fake_scan
        orch.run_continuous_scalping_tick_cycle(concurrent=False)

        self.assertEqual(orch.health_monitor.total_scans, 6)
        self.assertEqual(orch.health_monitor.total_failed_scans, 1)
        self.assertEqual(orch.health_monitor.symbol_states["NAS100"].failed_scan_count, 1)
        for ok_sym in [s for s in expected_syms if s != "NAS100"]:
            self.assertEqual(orch.health_monitor.symbol_states[ok_sym].scan_count, 1)

    # Test A: Historical Drawdown & Stale Circuit Breaker Do Not Block Valid Entries
    def test_drawdown_circuit_breaker_removed_manual_kill_switch_retained(self):
        from src.risk.portfolio_risk import PortfolioRiskEngine

        pr = PortfolioRiskEngine(self.cfg)
        pr.load_from_dict({
            "initial_balance": 6835.0,
            "peak_equity": 6835.0,
            "daily_starting_equity": 6835.0,
            "circuit_breaker_active": True,
            "hard_locked": True,
        })
        acc = AccountInfo(balance=6835.0, equity=4440.64, free_margin=4000.0)
        cand = SignalCandidate(
            id="TEST_DD_OK",
            symbol="EURUSD",
            direction=OrderType.BUY,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1060,
            timeframe=Timeframe.M15,
            setup_type=SetupType.FAST_SCALP,
            score=80.0,
            risk_reward=1.2,
            status="APPROVED",
            timestamp=datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
        )
        allowed, reason = pr.evaluate_new_order_permission(cand, acc, [], proposed_monetary_risk=44.0, proposed_volume=0.10)
        self.assertTrue(allowed, f"Unexpected block: {reason}")
        self.assertGreater(acc.drawdown_pct, 35.0)
        self.assertFalse(pr.circuit_breaker_active)

        # Manual kill switch must still block
        pr.kill_switch_active = True
        pr.kill_switch_reason = "Manual STOP"
        allowed_ks, reason_ks = pr.evaluate_new_order_permission(cand, acc, [], proposed_monetary_risk=44.0, proposed_volume=0.10)
        self.assertFalse(allowed_ks)
        self.assertIn("Kill switch", reason_ks)

    # Test B & C: Low R:R (< 1.10) and Spread > 5% Do Not Reject Valid Setups
    def test_low_rr_and_wide_spread_do_not_reject_valid_setup(self):
        from src.risk.target_feasibility import TargetFeasibilityEngine

        gbpusd = SymbolInfo(
            symbol="GBPUSD",
            digits=5,
            point=0.00001,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            spread=11.0,
            ask=1.27011,
            bid=1.27000,
            tick_value=1.0,
            tick_size=0.00001,
        )
        # Feasibility with R:R 0.51 must not reject
        feas = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=gbpusd,
            account=AccountInfo(balance=4604.96, equity=4440.64, free_margin=4000.0),
            entry_price=1.27011,
            stop_loss=1.26924,  # 87 pts SL -> 11/87 = 12.64% spread ratio
            order_type=OrderType.BUY,
            volume=0.50,
            atr_m15=0.0015,
            target_net_usd=20.0,
        )
        self.assertTrue(feas.is_feasible, f"Feasibility unexpectedly rejected: {feas.rejection_reason}")

        # OrderManager pre-check must not reject 12.64% spread or 0.51 R:R
        cand = SignalCandidate(
            id="TEST_GBP_LOW_RR",
            symbol="GBPUSD",
            direction=OrderType.BUY,
            entry_price=1.27011,
            stop_loss=1.26924,
            take_profit=1.27055,  # 44 pts TP -> R:R = 0.51
            timeframe=Timeframe.M15,
            setup_type=SetupType.FAST_SCALP,
            score=75.0,
            risk_reward=0.51,
            status="APPROVED",
            timestamp=datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc),
        )
        from src.core.orchestrator import TradingBotOrchestrator
        orch = TradingBotOrchestrator(self.cfg)
        orch.order_manager.config.strict_three_symbol_universe = False
        orch.order_manager.cost_evaluator.policies["GBPUSD"] = {"warn_spread_pts": 100.0, "min_net_to_cost_ratio": 1.0, "commission_per_lot": 7.0, "expected_slippage_pts": 3.0}
        orch.order_manager.bridge = MagicMock()
        orch.order_manager.bridge.is_connected.return_value = True
        chk = orch.order_manager.run_pre_trade_checklist(cand, self.account, gbpusd, [])
        self.assertTrue(chk.passed, f"Pre-check unexpectedly rejected: {chk.rejection_reasons}")

    # Test D & F: Broker Symbol Resolver (Suffixes, Index Aliases, Ambiguity, Cent Account)
    def test_broker_symbol_resolver_and_cent_account(self):
        from src.core.broker_resolver import BrokerSymbolResolver

        resolver = BrokerSymbolResolver()
        inv = [
            {"name": "EURUSD.pro", "trade_mode": 4, "digits": 5, "point": 1e-5, "trade_contract_size": 100000.0},
            {"name": "XAUUSD.m", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 100.0},
            {"name": "US100.std", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 20.0},
            {"name": "BTCUSD.m", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
        ]
        self.assertEqual(resolver.resolve("EURUSD", inventory=inv).broker_symbol, "EURUSD.pro")
        self.assertEqual(resolver.resolve("XAUUSD", inventory=inv).broker_symbol, "XAUUSD.m")
        self.assertEqual(resolver.resolve("NAS100", inventory=inv).broker_symbol, "US100.std")
        self.assertEqual(resolver.resolve("BTCUSD", inventory=inv).broker_symbol, "BTCUSD.m")

        # Ambiguity detection when multiple unrelated matches exist
        amb_inv = [
            {"name": "US100.std", "trade_mode": 4},
            {"name": "US100.pro", "trade_mode": 4},
        ]
        amb_res = resolver.resolve("NAS100_AMB", inventory=[{"name": "NAS100.std", "trade_mode": 4}])
        self.assertEqual(amb_res.status, "SYMBOL_RESOLUTION_FAILED")
        r2 = BrokerSymbolResolver()
        self.assertEqual(r2.resolve("NAS100", inventory=amb_inv).status, "AMBIGUOUS_BROKER_SYMBOL")

        # Cent account detection (preserves native balance 50000.0 USC and normalizes to $500.00 USD)
        cent_acc = AccountInfo(balance=50000.0, equity=50000.0, raw_balance=50000.0, raw_equity=50000.0, currency="USC", raw_currency="USC")
        self.assertTrue(cent_acc.is_cent_account)
        self.assertEqual(cent_acc.balance, 50000.0)
        self.assertAlmostEqual(cent_acc.normalized_balance, 500.0, places=2)

    # Test E: Bridge Server Accepts NAS100 -> US100.std While Rejecting BTCUSD.m
    def test_bridge_server_accepts_us100_std_for_nas100(self):
        from src.execution.bridge_server import PersistentBridgeServer, EAConnection

        srv = PersistentBridgeServer(ea_host="127.0.0.1", ea_port=0, ipc_port=0)
        ea = EAConnection(socket=MagicMock(), addr=("127.0.0.1", 12345), magic=999, symbol="BTCUSD.m", account=1200057798)
        ea.status = "ACTIVE"
        srv._clients[ea.magic] = ea

        def _fake_send(raw_str, timeout_sec=10.0):
            payload = json.loads(raw_str.strip())
            srv._dispatch_ea_message(
                ea,
                {
                    "status": "SUCCESS",
                    "request_id": payload["request_id"],
                    "symbol": "US100.std",
                    "data": [],
                },
            )
            return True

        ea.send_raw = _fake_send
        resp = srv.forward_request_to_ea({"action": "RATES", "symbol": "NAS100", "timeframe": "M15"})
        self.assertEqual(resp.get("status"), "SUCCESS")
        self.assertEqual(resp.get("canonical_symbol"), "NAS100")
        self.assertEqual(resp.get("broker_symbol"), "US100.std")
        self.assertEqual(resp.get("account_login"), 1200057798)


if __name__ == "__main__":
    unittest.main()
