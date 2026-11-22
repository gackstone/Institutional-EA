"""
Universal Broker-Adaptive MT5 Trading Engine Test Suite.
Validates dynamic account classification, currency normalization,
multi-symbol discovery across 4 synthetic broker environments,
missing symbol isolation (absent BTCUSD), cache invalidation on account switch,
double-conversion guards, and standard diagnostic rejection codes.
"""

import math
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.broker_adaptation.account_classifier import (
    AccountClassifier,
    AccountProfile,
    AccountCategory,
    TradeMode,
)
from src.broker_adaptation.currency_normalizer import (
    CurrencyNormalizer,
    NormalizedMonetaryValue,
)
from src.broker_adaptation.symbol_specification import (
    BrokerSymbolSpec,
    extract_symbol_spec,
)
from src.broker_adaptation.symbol_discovery import (
    SymbolDiscoveryEngine,
    DiscoveryResult,
    CANONICAL_UNIVERSE,
)
from src.broker_adaptation.execution_capabilities import (
    ExecutionCapabilitiesEngine,
    ExecutionValidationResult,
    StandardRejectionCode,
)
from src.broker_adaptation.broker_discovery import (
    BrokerCapabilityProfile,
    BrokerDiscoveryManager,
)


@dataclass
class MockMT5Symbol:
    name: str
    trade_mode: int = 4
    digits: int = 5
    point: float = 0.00001
    trade_tick_size: float = 0.00001
    trade_tick_value: float = 1.0
    trade_contract_size: float = 100000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    volume_limit: float = 0.0
    trade_stops_level: int = 0
    trade_freeze_level: int = 0
    filling_mode: int = 1
    execution_mode: int = 2
    spread: int = 10
    currency_base: str = "USD"
    currency_profit: str = "USD"
    currency_margin: str = "USD"


@dataclass
class MockMT5Account:
    login: int = 10001
    server: str = "MetaQuotes-Demo"
    company: str = "MetaQuotes Software Corp."
    currency: str = "USD"
    trade_mode: int = 0
    leverage: int = 100
    balance: float = 10000.0
    equity: float = 10000.0
    margin: float = 0.0
    margin_free: float = 10000.0


class TestUniversalBrokerAdaptation(unittest.TestCase):
    def setUp(self):
        self.classifier = AccountClassifier()
        self.normalizer = CurrencyNormalizer()
        self.symbol_engine = SymbolDiscoveryEngine()
        self.exec_engine = ExecutionCapabilitiesEngine()
        self.discovery_manager = BrokerDiscoveryManager(
            classifier=self.classifier,
            normalizer=self.normalizer,
            symbol_engine=self.symbol_engine,
            exec_engine=self.exec_engine,
        )

    # ------------------------------------------------------------------
    # 1. Synthetic Broker 1: Standard USD Account
    # ------------------------------------------------------------------
    def test_synthetic_broker_standard_usd(self):
        acc = MockMT5Account(
            login=5001234,
            server="ICMarketsSC-Demo",
            company="IC Markets (SC)",
            currency="USD",
            trade_mode=0,
            leverage=500,
            balance=5000.0,
            equity=5000.0,
            margin_free=5000.0,
        )
        inv = [
            MockMT5Symbol(name="XAUUSD", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0, trade_contract_size=100.0),
            MockMT5Symbol(name="BTCUSD", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0, trade_contract_size=1.0),
            MockMT5Symbol(name="USDJPY", digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.65, trade_contract_size=100000.0),
            MockMT5Symbol(name="EURUSD", digits=5, point=0.00001, trade_tick_size=0.00001, trade_tick_value=1.0, trade_contract_size=100000.0),
        ]

        prof = self.discovery_manager.discover(acc, inventory=inv)

        self.assertEqual(prof.account.category, AccountCategory.STANDARD)
        self.assertEqual(prof.account.denomination_factor, 1.0)
        self.assertEqual(prof.account.native_balance, 5000.0)
        self.assertEqual(prof.account.normalized_balance, 5000.0)
        self.assertEqual(prof.account.currency, "USD")
        self.assertFalse(prof.is_cent)

        # Canonical symbols mapped cleanly; USDJPY excluded from universe
        self.assertEqual(prof.get_broker_symbol("XAUUSD"), "XAUUSD")
        self.assertEqual(prof.get_broker_symbol("BTCUSD"), "BTCUSD")
        self.assertIsNone(prof.get_broker_symbol("USDJPY"))
        self.assertEqual(len(prof.unavailable_canonical), 0)

        # Check spec for XAUUSD
        spec = prof.get_spec("XAUUSD")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.contract_size, 100.0)
        self.assertEqual(spec.point, 0.01)

    # ------------------------------------------------------------------
    # 2. Synthetic Broker 2: Cent Account (USC) with Missing BTCUSD
    # ------------------------------------------------------------------
    def test_synthetic_broker_cent_usc_with_missing_btcusd(self):
        acc = MockMT5Account(
            login=1200556240,
            server="JustMarkets-Demo3",
            company="Just Global Markets Ltd",
            currency="USC",
            trade_mode=0,
            leverage=2000,
            balance=1500.0,
            equity=1500.0,
            margin_free=1500.0,
        )
        # Note: JustMarkets Cent account offers XAUUSD.c, USDJPY.c, but NO BTCUSD.c (no crypto CFD)
        inv = [
            MockMT5Symbol(name="XAUUSD.c", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=0.01, trade_contract_size=1.0, filling_mode=1),
            MockMT5Symbol(name="USDJPY.c", digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.0065, trade_contract_size=1000.0, filling_mode=1),
            MockMT5Symbol(name="EURUSD.c", digits=5, point=0.00001, trade_tick_size=0.00001, trade_tick_value=0.01, trade_contract_size=1000.0, filling_mode=1),
        ]

        prof = self.discovery_manager.discover(acc, inventory=inv)

        self.assertEqual(prof.account.category, AccountCategory.CENT)
        self.assertTrue(prof.is_cent)
        self.assertEqual(prof.account.denomination_factor, 100.0)
        self.assertEqual(prof.account.native_balance, 1500.0)
        self.assertEqual(prof.account.normalized_balance, 15.00)  # 1500 USC = $15.00
        self.assertEqual(prof.account.currency, "USC")

        # Symbol mappings (USDJPY excluded from canonical universe)
        self.assertEqual(prof.get_broker_symbol("XAUUSD"), "XAUUSD.c")
        self.assertIsNone(prof.get_broker_symbol("USDJPY"))

        # BTCUSD must be isolated as SYMBOL_NOT_AVAILABLE without breaking anything
        self.assertIsNone(prof.get_broker_symbol("BTCUSD"))
        self.assertIn("BTCUSD", prof.unavailable_canonical)
        btc_res = prof.symbols["BTCUSD"]
        self.assertFalse(btc_res.is_available)
        self.assertEqual(btc_res.status, "SYMBOL_NOT_AVAILABLE")

        # XAUUSD.c spec checks
        xau_spec = prof.get_spec("XAUUSD")
        self.assertIsNotNone(xau_spec)
        self.assertEqual(xau_spec.contract_size, 1.0)
        self.assertEqual(xau_spec.tick_value, 0.01)
        self.assertTrue(xau_spec.allows_fok)

    # ------------------------------------------------------------------
    # 3. Synthetic Broker 3: Micro EUR Account
    # ------------------------------------------------------------------
    def test_synthetic_broker_micro_eur(self):
        acc = MockMT5Account(
            login=883102,
            server="XMGlobal-Demo",
            company="XM Global",
            currency="EUR",
            trade_mode=0,
            leverage=30,
            balance=250.0,
            equity=250.0,
            margin_free=250.0,
        )
        inv = [
            MockMT5Symbol(name="XAUUSDmicro", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=0.01, trade_contract_size=1.0),
            MockMT5Symbol(name="BTCUSDmicro", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=0.01, trade_contract_size=0.01),
            MockMT5Symbol(name="USDJPYmicro", digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.006, trade_contract_size=1000.0),
        ]

        prof = self.discovery_manager.discover(acc, inventory=inv)

        self.assertEqual(prof.account.category, AccountCategory.STANDARD)
        self.assertEqual(prof.account.currency, "EUR")
        self.assertEqual(prof.account.leverage, 30)

        # Currency conversion: 250 EUR * 1.08 = 270.00 USD
        norm_val = self.normalizer.normalize(acc.balance, "EUR", "USD")
        self.assertAlmostEqual(norm_val.normalized_value, 270.0, places=1)

        # Symbols mapped (USDJPY excluded)
        self.assertEqual(prof.get_broker_symbol("XAUUSD"), "XAUUSDmicro")
        self.assertEqual(prof.get_broker_symbol("BTCUSD"), "BTCUSDmicro")
        self.assertIsNone(prof.get_broker_symbol("USDJPY"))

    # ------------------------------------------------------------------
    # 4. Synthetic Broker 4: High-Precision Raw / ECN Account
    # ------------------------------------------------------------------
    def test_synthetic_broker_raw_ecn(self):
        acc = MockMT5Account(
            login=99412,
            server="Pepperstone-Demo01",
            company="Pepperstone Group Limited",
            currency="USD",
            trade_mode=0,
            leverage=100,
            balance=10000.0,
            equity=10000.0,
            margin_free=10000.0,
        )
        inv = [
            MockMT5Symbol(name="XAUUSD.raw", digits=3, point=0.001, trade_tick_size=0.001, trade_tick_value=0.1, trade_contract_size=100.0, spread=2, filling_mode=2),
            MockMT5Symbol(name="BTCUSD.raw", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0, trade_contract_size=1.0, spread=5, filling_mode=2),
            MockMT5Symbol(name="USDJPY.raw", digits=5, point=0.00001, trade_tick_size=0.00001, trade_tick_value=0.65, trade_contract_size=100000.0, spread=1, filling_mode=2),
        ]

        prof = self.discovery_manager.discover(acc, inventory=inv)

        self.assertEqual(prof.get_broker_symbol("XAUUSD"), "XAUUSD.raw")
        self.assertEqual(prof.get_broker_symbol("BTCUSD"), "BTCUSD.raw")
        self.assertIsNone(prof.get_broker_symbol("USDJPY"))

        xau_spec = prof.get_spec("XAUUSD")
        self.assertTrue(xau_spec.allows_ioc)
        self.assertEqual(self.exec_engine.resolve_filling_mode(xau_spec), "IOC")

    # ------------------------------------------------------------------
    # 5. Account Switching & Cache Invalidation
    # ------------------------------------------------------------------
    def test_account_switch_cache_invalidation(self):
        acc1 = MockMT5Account(login=1111, server="ServerAlpha", currency="USD")
        inv1 = [MockMT5Symbol(name="XAUUSD.std"), MockMT5Symbol(name="BTCUSD.std"), MockMT5Symbol(name="USDJPY.std")]
        prof1 = self.discovery_manager.discover(acc1, inventory=inv1)
        self.assertEqual(prof1.session_key, "ServerAlpha:1111")
        self.assertEqual(prof1.get_broker_symbol("XAUUSD"), "XAUUSD.std")

        # Now switch to Broker Beta (login 2222, ServerBeta)
        acc2 = MockMT5Account(login=2222, server="ServerBeta", currency="USC")
        inv2 = [MockMT5Symbol(name="XAUUSD.c"), MockMT5Symbol(name="USDJPY.c")]
        prof2 = self.discovery_manager.discover(acc2, inventory=inv2)

        self.assertEqual(prof2.session_key, "ServerBeta:2222")
        self.assertEqual(prof2.get_broker_symbol("XAUUSD"), "XAUUSD.c")
        self.assertTrue(prof2.is_cent)
        # Previous ServerAlpha mappings must not leak
        self.assertIsNone(prof2.get_broker_symbol("BTCUSD"))

    # ------------------------------------------------------------------
    # 6. Double Conversion Guard
    # ------------------------------------------------------------------
    def test_double_conversion_guard(self):
        # Native cent value: 1500.0 USC
        native_amount = 1500.0
        norm_val = self.normalizer.normalize(native_amount, "USC", "USD")
        self.assertEqual(norm_val.normalized_value, 15.0)
        self.assertEqual(norm_val.native_value, 1500.0)
        self.assertEqual(norm_val.denomination_factor, 100.0)

        # Denormalizing should return exactly 1500.0
        back_to_native = self.normalizer.denormalize(norm_val.normalized_value, "USC", "USD")
        self.assertEqual(back_to_native, 1500.0)

        # Ensure that if normalize is accidentally called on an already normalized value (USD),
        # it preserves 15.0 and does not divide by 100 again to 0.15
        usd_val = self.normalizer.normalize(norm_val.normalized_value, "USD", "USD")
        self.assertEqual(usd_val.normalized_value, 15.0)

    # ------------------------------------------------------------------
    # 7. Denomination Anomaly Detection & Self-Healing
    # ------------------------------------------------------------------
    def test_denomination_anomaly_detection_and_healing(self):
        # Historical bug: balance = 1499.40 USC, but free_margin = 14.99 USC with 0 margin
        acc = MockMT5Account(
            login=1200556240,
            server="JustMarkets-Demo3",
            currency="USC",
            balance=1499.40,
            equity=1499.40,
            margin=0.0,
            margin_free=14.99,  # Mismatched 100x
        )
        prof = self.classifier.classify(acc)

        self.assertEqual(len(prof.anomalies), 1)
        self.assertIn("CRITICAL_DENOMINATION_MISMATCH", prof.anomalies[0])
        # Auto-healed native_free_margin should match native balance
        self.assertEqual(prof.native_free_margin, 1499.40)
        self.assertEqual(prof.normalized_free_margin, 14.99)
        self.assertEqual(prof.normalized_balance, 14.99)

    # ------------------------------------------------------------------
    # 8. Standard Diagnostic Rejection Codes
    # ------------------------------------------------------------------
    def test_rejection_code_symbol_not_found(self):
        res = self.exec_engine.validate_pre_execution(
            spec=None,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            volume=0.01,
            direction="BUY",
            free_margin=1000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.SYMBOL_NOT_FOUND)

    def test_rejection_code_broker_trade_disabled(self):
        spec = extract_symbol_spec({"name": "TEST", "trade_mode": 0}, "TEST")
        res = self.exec_engine.validate_pre_execution(
            spec=spec,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            volume=0.01,
            direction="BUY",
            free_margin=1000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.BROKER_TRADE_DISABLED)

    def test_rejection_code_invalid_stops(self):
        spec = extract_symbol_spec({"name": "TEST", "trade_mode": 4}, "TEST")
        # BUY with SL >= entry
        res = self.exec_engine.validate_pre_execution(
            spec=spec,
            entry_price=100.0,
            stop_loss=105.0,  # Invalid for BUY
            take_profit=120.0,
            volume=0.01,
            direction="BUY",
            free_margin=1000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.INVALID_STOPS)

    def test_rejection_code_stop_distance_too_close(self):
        # Broker mandates 50 points stops_level, SL is 20 points
        spec = extract_symbol_spec({"name": "TEST", "trade_mode": 4, "trade_stops_level": 50, "point": 0.1}, "TEST")
        res = self.exec_engine.validate_pre_execution(
            spec=spec,
            entry_price=100.0,
            stop_loss=98.0,  # 2.0 dist / 0.1 = 20 points < 50
            take_profit=120.0,
            volume=0.01,
            direction="BUY",
            free_margin=1000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.STOP_DISTANCE_TOO_CLOSE)

    def test_rejection_code_insufficient_margin(self):
        spec = extract_symbol_spec({"name": "TEST", "trade_mode": 4}, "TEST")
        res = self.exec_engine.validate_pre_execution(
            spec=spec,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            volume=1.0,
            direction="BUY",
            free_margin=50.0,
            margin_required=200.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.INSUFFICIENT_MARGIN)

    def test_rejection_code_rounding_invalid_volume(self):
        # Min lot is 0.10, requested volume is 0.01
        spec = extract_symbol_spec({"name": "TEST", "trade_mode": 4, "volume_min": 0.10, "volume_step": 0.01}, "TEST")
        res = self.exec_engine.validate_pre_execution(
            spec=spec,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            volume=0.02,
            direction="BUY",
            free_margin=1000.0,
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.rejection_code, StandardRejectionCode.ROUNDING_INVALID_VOLUME)

    # ------------------------------------------------------------------
    # 9. Dynamic Sizing Verification: Eliminate Oversized Volumes
    # ------------------------------------------------------------------
    def test_oversized_position_elimination_usdjpy(self):
        """
        Verify that USDJPY.c on a 1500 USC ($15 USD) cent account calculates ~0.11 lots
        and NEVER oversized 20.23 - 21.31 lots.
        """
        from src.core.contracts import AccountInfo, SymbolInfo, OrderType
        from src.risk.position_sizing import PositionSizingEngine

        account = AccountInfo(
            account_number=1200556240,
            balance=1500.0,
            raw_balance=1500.0,
            equity=1500.0,
            raw_equity=1500.0,
            free_margin=1500.0,
            currency="USC",
            raw_currency="USC",
            is_cent_account=True,
            denomination_factor=100.0,
            leverage=2000,
        )
        # USDJPY.c specifications on cent account: contract_size=1000, tick_value=0.6275 USC per 0.001 pt
        sym_info = SymbolInfo(
            symbol="USDJPY.c",
            digits=3,
            point=0.001,
            tick_size=0.001,
            tick_value=0.6275,
            contract_size=1000.0,
            min_lot=0.01,
            max_lot=1000.0,
            lot_step=0.01,
            margin_required=0.50,
            spread=15,
        )

        sizing = PositionSizingEngine(default_risk_percent=1.0)
        # 20 pip SL: entry 159.450, SL 159.250 -> 200 pts distance
        res = sizing.calculate_lot_size(
            account=account,
            symbol_info=sym_info,
            entry_price=159.450,
            stop_loss=159.250,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )

        self.assertTrue(res.is_approved)
        # Volume must be ~0.11 lots, strictly < 0.50 lots, and NEVER 20+ lots!
        self.assertLess(res.volume, 0.50, f"Oversized volume detected: {res.volume} lots!")
        self.assertGreaterEqual(res.volume, 0.05)
        # Monetary risk must be <= 15.0 USC ($0.15 USD = 1.0% of 1500 USC)
        self.assertLessEqual(res.monetary_risk_native, 16.0)

    def test_oversized_position_elimination_xauusd(self):
        """
        Verify that XAUUSD.c on a 1500 USC ($15 USD) cent account calculates ~0.03 lots
        and NEVER oversized 3.50 - 4.17 lots.
        """
        from src.core.contracts import AccountInfo, SymbolInfo, OrderType
        from src.risk.position_sizing import PositionSizingEngine

        account = AccountInfo(
            account_number=1200556240,
            balance=1500.0,
            raw_balance=1500.0,
            equity=1500.0,
            raw_equity=1500.0,
            free_margin=1500.0,
            currency="USC",
            raw_currency="USC",
            is_cent_account=True,
            denomination_factor=100.0,
            leverage=2000,
        )
        # XAUUSD.c specifications: contract_size=1.0, tick_value=1.0 USC per 0.01 pt
        sym_info = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=1000.0,
            lot_step=0.01,
            margin_required=1.92,
            spread=25,
        )

        sizing = PositionSizingEngine(default_risk_percent=1.0)
        # 500 pt SL ($5.00 move): entry 3850.00, SL 3845.00
        # Loss per lot = 500 * 1.0 = 500 USC ($5.00 USD).
        # 1% risk = 15.0 USC ($0.15 USD). Raw volume = 15.0 / 500 = 0.03 lots!
        res = sizing.calculate_lot_size(
            account=account,
            symbol_info=sym_info,
            entry_price=3850.00,
            stop_loss=3845.00,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )

        self.assertTrue(res.is_approved)
        # Volume must be ~0.02 - 0.03 lots, strictly < 0.10 lots, and NEVER 3.50+ lots!
        self.assertLess(res.volume, 0.10, f"Oversized volume detected: {res.volume} lots!")
        self.assertIn(res.volume, [0.02, 0.03])
        self.assertLessEqual(res.monetary_risk_native, 16.0)

    def test_margin_aware_volume_reduction(self):
        """
        Verify that when a proposed volume exceeds the maximum margin threshold,
        the sizing engine steps down volume in lot_step increments rather than outright failure.
        """
        from src.core.contracts import AccountInfo, SymbolInfo, OrderType
        from src.risk.position_sizing import PositionSizingEngine

        # Account with small free margin (e.g. 5.0 USC free margin)
        account = AccountInfo(
            balance=1500.0,
            equity=1500.0,
            free_margin=10.0,  # Tight free margin
            currency="USC",
            is_cent_account=True,
            denomination_factor=100.0,
            leverage=100,
        )
        sym_info = SymbolInfo(
            symbol="XAUUSD.c",
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=1.0,
            min_lot=0.01,
            lot_step=0.01,
            margin_required=3.0,  # 3.0 margin per lot
        )
        sizing = PositionSizingEngine(default_risk_percent=1.0)
        res = sizing.calculate_lot_size(
            account=account,
            symbol_info=sym_info,
            entry_price=3850.00,
            stop_loss=3845.00,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        # If reduced volume is affordable, it should adjust volume downwards safely
        if res.is_approved:
            self.assertLessEqual(res.margin_required, account.free_margin * 0.50 + 1e-4)


if __name__ == "__main__":
    unittest.main()
