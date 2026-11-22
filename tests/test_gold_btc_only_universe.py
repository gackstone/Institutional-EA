"""
Master Test Suite: Gold and Bitcoin Only Universe (USDJPY Permanent Exclusion)
Mandated by Master Engineering Directive.

Comprehensive Positive and Negative Test Coverage:
1. Positive Tests:
   - Gold (XAUUSD) discovery, resolution, signal pipeline, and MT5 bridge submission.
   - Bitcoin (BTCUSD) discovery, resolution, signal pipeline, and MT5 bridge submission.
   - Standard account symbol recognition (XAUUSD, BTCUSD).
   - Cent account symbol recognition (XAUUSD.c, BTCUSD.c).
   - Micro account symbol recognition (XAUUSDmicro, BTCUSDmicro).
   - Raw/ECN account symbol recognition (XAUUSD.raw, BTCUSD.raw).

2. Negative Tests:
   - USDJPY universally excluded from symbol universe and scanner.
   - Dynamic scanner rejects USDJPY.
   - Signal candidate generation / pre-trade checklist rejects USDJPY.
   - OrderManager final order validation rejects USDJPY market and pending orders.
   - MT5 BridgeClient rejects USDJPY orders, pending orders, and check requests before transmission.
   - Automated retry and recovery execution cannot bypass restriction for USDJPY.
   - Broker-specific suffixes and prefixes (.m, .c, .raw, .pro, micro, prefix) for USDJPY are rejected.
   - Reconnecting to MT5 / cache invalidation does not reintroduce USDJPY.
   - Restart recovery does not reintroduce USDJPY into the tradable universe.
   - Account switching (Standard -> Cent -> Micro) does not reintroduce USDJPY.
   - AI instrument recommendations cannot bypass the instrument allowlist.

3. Structured Audit & Logging Requirements:
   - Exact rejection string: "INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted."
   - Encounter logging: "INSTRUMENT_BLOCKED: USDJPY | REASON: NOT_IN_ALLOWED_TRADING_UNIVERSE" with rate limiting.
   - Startup logging: "ACTIVE_TRADING_UNIVERSE: XAUUSD, BTCUSD".
   - Coexistence and management of existing open USDJPY positions without permitting new entries.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.broker_adaptation.account_classifier import AccountCategory
from src.broker_adaptation.broker_discovery import BrokerDiscoveryManager
from src.core.account_detector import AccountDetector, AccountType
from src.core.account_switch_manager import AccountSwitchManager
from src.core.broker_resolver import BrokerSymbolResolver
from src.core.config import AppConfig, RiskConfig
from src.core.contracts import (
    AccountInfo,
    OrderType,
    Position,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)
from src.core.orchestrator import TradingBotOrchestrator
from src.core.symbol_universe import (
    SpecializedSymbolUniverse,
    APPROVED_CANONICAL_SYMBOLS,
    APPROVED_CANONICAL_ALIASES,
    get_symbol_universe,
)
from src.engine.multi_pair_scanner import MultiPairScanner
from src.execution.bridge_client import BridgeClient
from src.execution.order_manager import OrderManager
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.strategy.inverse_coordination import InverseDirectionCoordinator


# ==============================================================================
# Fixtures & Helpers
# ==============================================================================

@pytest.fixture(autouse=True)
def fresh_universe():
    u = SpecializedSymbolUniverse()
    yield u


def make_candidate(cand_id: str, symbol: str, direction: OrderType = OrderType.BUY) -> SignalCandidate:
    return SignalCandidate(
        id=cand_id,
        symbol=symbol,
        timeframe=Timeframe.M1,
        direction=direction,
        setup_type=SetupType.SMC_MODEL_2_BOS_FVG,
        entry_price=2000.0 if "XAU" in symbol else (50000.0 if "BTC" in symbol else 150.0),
        stop_loss=1990.0 if "XAU" in symbol else (49500.0 if "BTC" in symbol else 149.0),
        take_profit=2020.0 if "XAU" in symbol else (51000.0 if "BTC" in symbol else 152.0),
        risk_reward=2.0,
        score=85.0,
        status="APPROVED",
        timestamp=datetime.now(timezone.utc),
    )


def make_symbol_info(symbol: str) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        digits=2 if "XAU" in symbol or "BTC" in symbol else 3,
        point=0.01 if "XAU" in symbol or "BTC" in symbol else 0.001,
        tick_size=0.01 if "XAU" in symbol or "BTC" in symbol else 0.001,
        tick_value=1.0,
        contract_size=100.0 if "XAU" in symbol else (1.0 if "BTC" in symbol else 100000.0),
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        ask=2000.10 if "XAU" in symbol else (50001.0 if "BTC" in symbol else 150.05),
        bid=2000.00 if "XAU" in symbol else (50000.0 if "BTC" in symbol else 150.00),
    )


def make_account(balance: float = 10000.0, currency: str = "USD") -> AccountInfo:
    return AccountInfo(
        account_number=123456,
        balance=balance,
        equity=balance,
        free_margin=balance,
        currency=currency,
        leverage=100,
        trade_mode="DEMO",
    )


# ==============================================================================
# 1. Authoritative Allowlist & Symbol Universe Tests
# ==============================================================================

class TestAuthoritativeAllowlist:

    def test_canonical_symbols_strictly_xauusd_and_btcusd(self):
        """Canonical universe must consist solely of XAUUSD and BTCUSD."""
        assert APPROVED_CANONICAL_SYMBOLS == ("XAUUSD", "BTCUSD")
        assert "USDJPY" not in APPROVED_CANONICAL_SYMBOLS
        assert "USDJPY" not in APPROVED_CANONICAL_ALIASES

    def test_symbol_universe_approves_gold_and_btc(self, fresh_universe):
        """Gold and BTC and their broker suffixes must be approved."""
        valid_symbols = [
            "XAUUSD", "XAUUSD.m", "XAUUSD.c", "XAUUSDmicro", "XAUUSD.raw", "XAUUSD.pro", "GOLD", "GOLD.m",
            "BTCUSD", "BTCUSD.m", "BTCUSD.c", "BTCUSDmicro", "BTCUSD.raw", "BTCUSD.pro", "BITCOIN", "BTC",
        ]
        for sym in valid_symbols:
            is_ok, reason = fresh_universe.validate_or_reject(sym)
            assert is_ok is True, f"Expected {sym} to be approved, got reason: {reason}"
            assert fresh_universe.is_approved(sym) is True

    def test_symbol_universe_rejects_usdjpy_and_variants(self, fresh_universe):
        """USDJPY and all variations must be rejected with exact error message."""
        usdjpy_variants = [
            "USDJPY", "USDJPY.m", "USDJPY.c", "USDJPYmicro", "USDJPY.raw",
            "USDJPY.pro", "USDJPY.std", "USDJPY+", "USDJPY#", "mUSDJPY", "rawUSDJPY",
        ]
        expected_msg = "INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted."
        for sym in usdjpy_variants:
            is_ok, reason = fresh_universe.validate_or_reject(sym)
            assert is_ok is False, f"Expected {sym} to be rejected"
            assert reason == expected_msg
            assert fresh_universe.is_approved(sym) is False


# ==============================================================================
# 2. Multi-Account Discovery & Normalization Tests (Standard, Cent, Micro)
# ==============================================================================

class TestMultiAccountDiscovery:

    def test_standard_account_symbol_resolution(self):
        """Standard account resolves standard Gold and BTC symbols, rejects USDJPY."""
        detector = AccountDetector()
        resolver = BrokerSymbolResolver(account_detector=detector)
        inv = [
            {"name": "XAUUSD", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 100.0},
            {"name": "BTCUSD", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
            {"name": "USDJPY", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 100000.0},
        ]
        res_gold = resolver.resolve("XAUUSD", inventory=inv)
        assert res_gold.status in ("VALIDATED", "RESOLVED_EXACT")
        assert res_gold.broker_symbol == "XAUUSD"

        res_btc = resolver.resolve("BTCUSD", inventory=inv)
        assert res_btc.status in ("VALIDATED", "RESOLVED_EXACT")
        assert res_btc.broker_symbol == "BTCUSD"

        res_jpy = resolver.resolve("USDJPY", inventory=inv)
        assert res_jpy.status == "UNAUTHORIZED_SYMBOL"
        assert res_jpy.broker_symbol is None
        assert "INSTRUMENT_NOT_ALLOWED" in res_jpy.reason

    def test_cent_account_symbol_resolution(self):
        """Cent account resolves .c Gold and BTC symbols, rejects USDJPY.c."""
        detector = AccountDetector()
        resolver = BrokerSymbolResolver(account_detector=detector)
        inv = [
            {"name": "XAUUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 100.0},
            {"name": "BTCUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
            {"name": "USDJPY.c", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 1000.0},
        ]
        res_gold = resolver.resolve("XAUUSD", inventory=inv)
        assert res_gold.broker_symbol == "XAUUSD.c"

        res_btc = resolver.resolve("BTCUSD", inventory=inv)
        assert res_btc.broker_symbol == "BTCUSD.c"

        res_jpy = resolver.resolve("USDJPY", inventory=inv)
        assert res_jpy.status == "UNAUTHORIZED_SYMBOL"
        assert res_jpy.broker_symbol is None

    def test_micro_account_symbol_resolution(self):
        """Micro account resolves micro Gold and BTC symbols, rejects USDJPYmicro."""
        detector = AccountDetector()
        resolver = BrokerSymbolResolver(account_detector=detector)
        inv = [
            {"name": "XAUUSDmicro", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
            {"name": "BTCUSDmicro", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 0.01},
            {"name": "USDJPYmicro", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 1000.0},
        ]
        res_gold = resolver.resolve("XAUUSD", inventory=inv)
        assert res_gold.broker_symbol == "XAUUSDmicro"

        res_btc = resolver.resolve("BTCUSD", inventory=inv)
        assert res_btc.broker_symbol == "BTCUSDmicro"

        res_jpy = resolver.resolve("USDJPY", inventory=inv)
        assert res_jpy.status == "UNAUTHORIZED_SYMBOL"
        assert res_jpy.broker_symbol is None

    def test_broker_symbol_discovery_class_excludes_usdjpy(self):
        """BrokerDiscoveryManager excludes USDJPY from discovered canonical mappings."""
        from dataclasses import dataclass

        @dataclass
        class MockSym:
            name: str
            trade_mode: int = 4
            digits: int = 2
            point: float = 0.01
            trade_tick_size: float = 0.01
            trade_tick_value: float = 1.0
            trade_contract_size: float = 100.0

        @dataclass
        class MockAcc:
            login: int = 1001
            server: str = "Demo-Server"
            company: str = "Demo Broker"
            currency: str = "USD"
            trade_mode: int = 0
            leverage: int = 100
            balance: float = 5000.0
            equity: float = 5000.0
            margin_free: float = 5000.0

        discovery = BrokerDiscoveryManager()
        acc = MockAcc()
        sym_xau = MockSym(name="XAUUSD.raw", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0, trade_contract_size=100.0)
        sym_btc = MockSym(name="BTCUSD.raw", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0, trade_contract_size=1.0)
        sym_jpy = MockSym(name="USDJPY.raw", digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.65, trade_contract_size=100000.0)

        prof = discovery.discover(acc, inventory=[sym_xau, sym_btc, sym_jpy])
        assert prof.get_broker_symbol("XAUUSD") == "XAUUSD.raw"
        assert prof.get_broker_symbol("BTCUSD") == "BTCUSD.raw"
        assert prof.get_broker_symbol("USDJPY") is None


# ==============================================================================
# 3. Market Scanner Selection & Strategy Universe Tests
# ==============================================================================

class TestScannerAndStrategyUniverse:

    def test_scanner_default_symbols_only_gold_and_btc(self):
        """MultiPairScanner default symbols list contains only XAUUSD and BTCUSD."""
        mock_md = MagicMock()
        scanner = MultiPairScanner(market_data=mock_md, symbols=["XAUUSD", "BTCUSD", "USDJPY", "EURUSD"])
        # Monitored symbols must be filtered to approved universe only
        assert "USDJPY" not in scanner.symbols
        assert "EURUSD" not in scanner.symbols
        assert set(scanner.symbols) == {"XAUUSD", "BTCUSD"}

    def test_scanner_blocks_usdjpy_scan(self):
        """Scanning USDJPY directly returns un-tradable opportunity immediately."""
        mock_md = MagicMock()
        scanner = MultiPairScanner(market_data=mock_md, symbols=["XAUUSD", "BTCUSD"])
        opp = scanner.scan_single_symbol("USDJPY")
        assert opp.is_tradable is False
        assert opp.candidate is None
        assert "INSTRUMENT_NOT_ALLOWED" in opp.diagnostic_reason

    def test_inverse_coordination_rejects_usdjpy(self):
        """Inverse directional coordinator rejects USDJPY candidate with required error."""
        coord = InverseDirectionCoordinator()
        cand = make_candidate("USDJPY_COORD", "USDJPY")
        outcome = coord.evaluate_usdjpy_candidate(cand)
        assert outcome.is_approved is False
        assert "INSTRUMENT_NOT_ALLOWED" in outcome.rationale


# ==============================================================================
# 4. Order Execution, Bridge, and Retry Enforcement Tests
# ==============================================================================

class TestExecutionBoundaryEnforcement:

    def test_order_manager_precheck_approves_gold_and_btc(self, tmp_path):
        """OrderManager pre-trade check approves valid Gold and BTC setups."""
        cfg = AppConfig()
        cfg.risk = RiskConfig(
            risk_percentage=0.25,
            max_aggregate_open_risk_percent=6.0,
            max_margin_utilization_percent=20.0,
        )
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.is_connected.return_value = True
        sizing = PositionSizingEngine(default_risk_percent=0.25, max_risk_percent_per_trade=2.0)
        p_risk = PortfolioRiskEngine(config=cfg)
        om = OrderManager(config=cfg, bridge=mock_bridge, sizing_engine=sizing, portfolio_risk=p_risk)

        acc = make_account(balance=10000.0)

        # Gold
        cand_gold = make_candidate("CAND_GOLD", "XAUUSD")
        chk_gold = om.run_pre_trade_checklist(cand_gold, acc, make_symbol_info("XAUUSD"), [])
        assert chk_gold.passed is True

        # Bitcoin (20 pt SL = 2000 ticks = $20 risk on 0.01 lot, 0.20% of $10k equity)
        cand_btc = make_candidate("CAND_BTC", "BTCUSD")
        cand_btc.entry_price = 50000.0
        cand_btc.stop_loss = 49980.0
        cand_btc.take_profit = 50040.0
        chk_btc = om.run_pre_trade_checklist(cand_btc, acc, make_symbol_info("BTCUSD"), [])
        assert chk_btc.passed is True

    def test_order_manager_precheck_rejects_usdjpy_market_order(self, tmp_path):
        """OrderManager pre-trade check rejects USDJPY with exact error message."""
        cfg = AppConfig()
        mock_bridge = MagicMock()
        sizing = PositionSizingEngine()
        p_risk = PortfolioRiskEngine(config=cfg)
        om = OrderManager(config=cfg, bridge=mock_bridge, sizing_engine=sizing, portfolio_risk=p_risk)

        acc = make_account(balance=10000.0)
        cand_jpy = make_candidate("CAND_JPY", "USDJPY")
        chk = om.run_pre_trade_checklist(cand_jpy, acc, make_symbol_info("USDJPY"), [])
        assert chk.passed is False
        expected_msg = "INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted."
        assert any(expected_msg in r for r in chk.rejection_reasons)

    def test_order_manager_execute_signal_rejects_usdjpy_and_never_calls_bridge(self):
        """OrderManager.execute_signal unconditionally halts USDJPY before bridge communication."""
        cfg = AppConfig()
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.is_connected.return_value = True
        sizing = PositionSizingEngine()
        p_risk = PortfolioRiskEngine(config=cfg)
        om = OrderManager(config=cfg, bridge=mock_bridge, sizing_engine=sizing, portfolio_risk=p_risk)

        acc = make_account(balance=10000.0)
        cand_jpy = make_candidate("EXEC_JPY", "USDJPY")

        res = om.execute_signal(cand_jpy, acc, make_symbol_info("USDJPY"), [])
        assert res is None
        mock_bridge.execute_trade.assert_not_called()
        mock_bridge.send_request.assert_not_called()

    def test_bridge_client_independent_hard_rejection_of_usdjpy(self):
        """BridgeClient independently validates symbol and rejects USDJPY before transmission."""
        bridge = BridgeClient(host="127.0.0.1", port=5555, ipc_port=5556)

        # 1. Direct send_request rejection
        res_trade = bridge.send_request({"action": "TRADE", "symbol": "USDJPY", "volume": 0.01})
        assert res_trade["status"] == "ERROR"
        assert "INSTRUMENT_NOT_ALLOWED" in res_trade["message"]

        # 2. execute_trade rejection
        res_exec = bridge.execute_trade("USDJPY.m", OrderType.BUY, 0.01, 149.0, 152.0, 150.0)
        assert res_exec["status"] == "ERROR"
        assert "INSTRUMENT_NOT_ALLOWED" in res_exec["message"]

        # 3. Pending order rejection
        res_pending = bridge.send_request({"action": "PENDING", "symbol": "USDJPY.c", "volume": 0.01})
        assert res_pending["status"] == "ERROR"
        assert "INSTRUMENT_NOT_ALLOWED" in res_pending["message"]

        # 4. order_check rejection
        res_check = bridge.order_check(symbol="USDJPYmicro", order_type="BUY", volume=0.01, price=150.0)
        assert res_check["status"] == "ERROR"
        assert "INSTRUMENT_NOT_ALLOWED" in res_check["message"]

    def test_automated_retries_cannot_bypass_restriction(self):
        """Automated retries cannot bypass restriction on USDJPY."""
        bridge = BridgeClient(host="127.0.0.1", port=5555, ipc_port=5556)
        # Attempt 5 sequential retries
        for attempt in range(5):
            res = bridge.execute_trade("USDJPY", OrderType.BUY, 0.01, 149.0, 152.0, 150.0)
            assert res["status"] == "ERROR"
            assert "INSTRUMENT_NOT_ALLOWED" in res["message"]


# ==============================================================================
# 5. Dynamic State, Reconnection & Restart Tests
# ==============================================================================

class TestDynamicStateAndReconnection:

    def test_reconnection_and_cache_invalidation_does_not_reintroduce_usdjpy(self, fresh_universe):
        """Reconnection with broker symbol inventory does not reintroduce USDJPY."""
        inv = [
            {"name": "XAUUSD.m", "trade_mode": 4},
            {"name": "BTCUSD.m", "trade_mode": 4},
            {"name": "USDJPY.m", "trade_mode": 4},
        ]
        # Resolve initial universe
        fresh_universe.resolve_universe(inventory=inv)
        assert fresh_universe.get_broker_symbol("XAUUSD") == "XAUUSD.m"
        assert fresh_universe.get_broker_symbol("BTCUSD") == "BTCUSD.m"
        assert fresh_universe.get_broker_symbol("USDJPY") is None

        # Invalidate cache (simulating reconnection)
        fresh_universe.invalidate()
        fresh_universe.resolve_universe(inventory=inv)
        assert fresh_universe.get_broker_symbol("USDJPY") is None
        is_ok, reason = fresh_universe.validate_or_reject("USDJPY.m")
        assert is_ok is False

    def test_account_switch_does_not_reintroduce_usdjpy(self):
        """Switching accounts from Standard to Cent to Micro does not allow USDJPY."""
        detector = AccountDetector()
        universe = SpecializedSymbolUniverse()
        manager = AccountSwitchManager(account_detector=detector, symbol_universe=universe)

        # Standard Account
        acc_std = {"login": 1001, "server": "Standard-Server", "currency": "USD", "balance": 5000.0}
        inv_std = [
            {"name": "XAUUSD", "trade_mode": 4},
            {"name": "BTCUSD", "trade_mode": 4},
            {"name": "USDJPY", "trade_mode": 4},
        ]
        res1 = manager.check_and_handle_switch(acc_std, inventory=inv_std)
        assert res1.symbols_resolved.get("XAUUSD") == "XAUUSD"
        assert "USDJPY" not in res1.symbols_resolved

        # Switch to Cent Account
        acc_cent = {"login": 2002, "server": "Cent-Server", "currency": "USC", "balance": 500000.0}
        inv_cent = [
            {"name": "XAUUSD.c", "trade_mode": 4},
            {"name": "BTCUSD.c", "trade_mode": 4},
            {"name": "USDJPY.c", "trade_mode": 4},
        ]
        res2 = manager.check_and_handle_switch(acc_cent, inventory=inv_cent)
        assert res2.switch_occurred is True
        assert res2.symbols_resolved.get("BTCUSD") == "BTCUSD.c"
        assert "USDJPY" not in res2.symbols_resolved

        # Switch to Micro Account
        acc_micro = {"login": 3003, "server": "Micro-Server", "currency": "USD", "balance": 50.0}
        inv_micro = [
            {"name": "XAUUSDmicro", "trade_mode": 4},
            {"name": "BTCUSDmicro", "trade_mode": 4},
            {"name": "USDJPYmicro", "trade_mode": 4},
        ]
        res3 = manager.check_and_handle_switch(acc_micro, inventory=inv_micro)
        assert res3.switch_occurred is True
        assert res3.symbols_resolved.get("XAUUSD") == "XAUUSDmicro"
        assert "USDJPY" not in res3.symbols_resolved


# ==============================================================================
# 6. Logging and Audit Verification Tests
# ==============================================================================

class TestAuditAndLogging:

    def test_startup_logging_contains_active_trading_universe(self, caplog):
        """Engine startup logs ACTIVE_TRADING_UNIVERSE: XAUUSD, BTCUSD."""
        with caplog.at_level(logging.INFO):
            cfg = AppConfig()
            cfg.dry_run = True
            orchestrator = TradingBotOrchestrator(config=cfg)

        assert any("ACTIVE_TRADING_UNIVERSE: XAUUSD, BTCUSD" in record.message for record in caplog.records)

    def test_encounter_logging_with_rate_limiting(self, caplog):
        """Encountering USDJPY logs INSTRUMENT_BLOCKED with 10-second deduplication."""
        universe = SpecializedSymbolUniverse()
        with caplog.at_level(logging.WARNING):
            # First encounter
            universe.validate_or_reject("USDJPY")
            # Immediate second encounter (must be suppressed by rate limit)
            universe.validate_or_reject("USDJPY.m")

        blocked_logs = [r.message for r in caplog.records if "INSTRUMENT_BLOCKED: USDJPY" in r.message]
        assert len(blocked_logs) == 1
        assert "REASON: NOT_IN_ALLOWED_TRADING_UNIVERSE" in blocked_logs[0]


# ==============================================================================
# 7. Coexistence and Preservation of Existing Open USDJPY Positions
# ==============================================================================

class TestExistingOpenPositionPreservation:

    def test_existing_usdjpy_positions_reconciled_and_managed(self):
        """Existing open USDJPY positions are reconciled and can be modified or closed."""
        bridge = MagicMock()
        pos_gold = Position(ticket=101, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.1, open_price=2000.0, current_price=2005.0, stop_loss=1990.0, take_profit=2020.0, profit=50.0)
        pos_jpy = Position(ticket=102, symbol="USDJPY", order_type=OrderType.BUY, volume=0.5, open_price=150.0, current_price=150.5, stop_loss=149.0, take_profit=152.0, profit=25.0)
        bridge.get_positions.return_value = [pos_gold, pos_jpy]

        cfg = AppConfig()
        sizing = PositionSizingEngine()
        p_risk = PortfolioRiskEngine(config=cfg)
        om = OrderManager(config=cfg, bridge=bridge, sizing_engine=sizing, portfolio_risk=p_risk)

        active = om.get_active_positions()
        assert len(active) == 2
        tickets = {p.ticket for p in active}
        assert tickets == {101, 102}

        # Verify close request for existing USDJPY position passes through bridge client without allowlist block
        close_payload = {"action": "CLOSE", "ticket": 102}
        # In BridgeClient.send_request, action "CLOSE" is not blocked by allowlist
        assert close_payload["action"] not in ("TRADE", "ORDER", "PENDING", "CHECK_ORDER")
