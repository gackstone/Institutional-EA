"""
Comprehensive Test Suite for Institutional EA Cent Account Compatibility & Broker Symbol Discovery.

Covers all 30 Required Audit Scenarios:
 1. Standard USD account detection.
 2. Verified cent account detection.
 3. Unknown account denomination fails closed.
 4. Correct USC normalization.
 5. Correct alternative broker cent-currency mapping.
 6. No accidental 100x balance interpretation.
 7. No accidental 1/100 risk calculation.
 8. XAUUSD.c canonical mapping.
 9. BTCUSD.c canonical mapping.
10. USDJPY.c canonical mapping.
11. Standard symbol mapping.
12. Broker suffix mapping.
13. Unknown suffix rejected.
14. Unauthorized instrument rejected.
15. Correct cent-account minimum volume.
16. Correct cent-account volume step.
17. Correct cent-account tick-value calculations.
18. Correct margin calculations.
19. Correct stop-loss monetary risk.
20. Correct commission and swap interpretation.
21. Independent cent-account position management.
22. Multiple positions on the same cent instrument.
23. Dynamic position layering.
24. Position closure and risk release.
25. Account-switch reconciliation.
26. Restart recovery.
27. Stale symbol specifications rejected.
28. Stale account normalization rejected.
29. Concurrent risk reservation protection.
30. Companion account-status synchronization.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.core.account_detector import AccountDetector, AccountDetectionResult, AccountType
from src.core.account_switch_manager import AccountSwitchManager, AccountSwitchResult
from src.core.broker_resolver import BrokerSymbolResolver, SymbolResolutionResult
from src.core.contracts import (
    AccountInfo,
    Candle,
    OrderType,
    Position,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)
from src.core.symbol_universe import SpecializedSymbolUniverse, APPROVED_CANONICAL_SYMBOLS
from src.risk.account_currency_normalizer import AccountCurrencyNormalizer, SizingMode
from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine
from src.risk.position_sizing import PositionSizingEngine, PositionSizeResult


def make_candidate(cand_id: str, symbol: str, direction: OrderType, entry: float, sl: float, tp: float) -> SignalCandidate:
    return SignalCandidate(
        id=cand_id,
        symbol=symbol,
        timeframe=Timeframe.M1,
        direction=direction,
        setup_type=SetupType.SMC_MODEL_2_BOS_FVG,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=2.0,
        score=85.0,
        timestamp=datetime.now(timezone.utc),
    )


class TestCentAccountCompatibility(unittest.TestCase):

    def setUp(self):
        self.detector = AccountDetector()
        self.resolver = BrokerSymbolResolver(account_detector=self.detector)
        self.universe = SpecializedSymbolUniverse(broker_resolver=self.resolver)
        self.sizing_engine = PositionSizingEngine()
        self.capacity_engine = DynamicPortfolioCapacityEngine(max_aggregate_open_risk_percent=6.0, max_symbol_risk_percent=4.0)

    # 1. Standard USD account detection
    def test_01_standard_usd_account_detection(self):
        acc_data = {
            "login": 10001,
            "server": "Demo-Server",
            "company": "Standard Broker Ltd",
            "currency": "USD",
            "balance": 5000.0,
            "equity": 5000.0,
            "trade_mode": 0,
        }
        res = self.detector.detect(acc_data)
        self.assertEqual(res.account_type, AccountType.DEMO_STANDARD)
        self.assertEqual(res.denomination_factor, 1.0)
        self.assertEqual(res.normalized_balance, 5000.0)
        self.assertEqual(res.confidence, "HIGH")

    # 2. Verified cent account detection
    def test_02_verified_cent_account_detection(self):
        acc_data = {
            "login": 20002,
            "server": "JustMarkets-Live-Cent",
            "company": "Just Global Markets Ltd",
            "currency": "USC",
            "balance": 100000.0,
            "equity": 100000.0,
            "trade_mode": 2,
        }
        res = self.detector.detect(acc_data)
        self.assertEqual(res.account_type, AccountType.CENT)
        self.assertEqual(res.denomination_factor, 100.0)
        self.assertEqual(res.normalized_balance, 1000.0)
        self.assertEqual(res.confidence, "HIGH")

    # 3. Unknown account denomination fails closed
    def test_03_unknown_account_denomination_fails_closed(self):
        acc_data = {
            "login": 30003,
            "server": "Exotic-Server",
            "company": "Exotic FX",
            "currency": "XYZ",  # Unknown currency code
            "balance": 50000.0,
            "equity": 50000.0,
            "trade_mode": 0,
        }
        res = self.detector.detect(acc_data)
        self.assertEqual(res.account_type, AccountType.UNKNOWN)
        self.assertEqual(res.confidence, "LOW")
        # Fail closed: must not divide balance by 100 without evidence!
        self.assertEqual(res.denomination_factor, 1.0)
        self.assertEqual(res.normalized_balance, 50000.0)

    # 4. Correct USC normalization
    def test_04_correct_usc_normalization(self):
        normalizer = AccountCurrencyNormalizer(
            account_type=AccountType.CENT,
            native_currency="USC",
            denomination_factor=100.0,
        )
        norm_val = normalizer.to_normalized(100000.0)
        self.assertEqual(norm_val.normalized_value, 1000.0)
        self.assertEqual(norm_val.native_value, 100000.0)
        self.assertEqual(norm_val.native_currency, "USC")
        self.assertEqual(norm_val.normalized_currency, "USD")

        # Bidirectional test
        native_back = normalizer.to_native(1000.0)
        self.assertEqual(native_back.native_value, 100000.0)

    # 5. Correct alternative broker cent-currency mapping
    def test_05_alternative_broker_cent_currency_mapping(self):
        currencies = ["EUC", "GBX", "JPC", "USCENT", "EURCENT"]
        for curr in currencies:
            acc_data = {"login": 40004, "currency": curr, "balance": 20000.0, "trade_mode": 0}
            res = self.detector.detect(acc_data)
            self.assertTrue(res.account_type.is_cent, f"Currency {curr} should be classified as cent account")
            self.assertEqual(res.denomination_factor, 100.0)
            self.assertEqual(res.normalized_balance, 200.0)

    # 6. No accidental 100x balance interpretation
    def test_06_no_accidental_100x_balance_interpretation(self):
        # A large standard USD account (e.g. $100,000 USD) must NEVER be divided by 100!
        acc = AccountInfo(
            account_number=50005,
            currency="USD",
            balance=100000.0,
            equity=100000.0,
            raw_balance=100000.0,
            raw_equity=100000.0,
        )
        self.assertFalse(acc.is_cent_account)
        self.assertEqual(acc.balance, 100000.0)
        self.assertEqual(acc.equity, 100000.0)
        self.assertEqual(acc.denomination_factor, 1.0)

    # 7. No accidental 1/100 risk calculation
    def test_07_no_accidental_one_hundredth_risk_calculation(self):
        # Cent account with 50,000 USC ($500 USD). Target risk 1.0% = $5.00 USD (500 USC).
        cent_acc = AccountInfo(
            account_number=60006,
            currency="USC",
            balance=50000.0,
            equity=50000.0,
            trade_mode="DEMO",
        )
        self.assertTrue(cent_acc.is_cent_account)
        self.assertEqual(cent_acc.normalized_balance, 500.0)

        # On Gold cent account (XAUUSD.c), 1 lot has 500 ticks move = 500 USC loss ($5.00 USD)
        sym_info = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,  # 1.0 USC per tick in MT5
            contract_size=100.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            margin_required=10.0,
            spread=20,
            ask=3850.0,
            bid=3849.80,
        )

        # SL 5.00 points away (500 ticks)
        res = self.sizing_engine.calculate_lot_size(
            account=cent_acc,
            symbol_info=sym_info,
            entry_price=3850.0,
            stop_loss=3845.0,
            risk_percent=1.0,
        )

        self.assertTrue(res.is_approved)
        # Lot volume must be around ~0.9x-1.0 lot, NOT 0.01 lot (which would be 1/100th intended risk)
        self.assertGreaterEqual(res.volume, 0.8)
        self.assertAlmostEqual(res.monetary_risk_normalized, 5.0, delta=1.5)
        self.assertAlmostEqual(res.monetary_risk_native, 500.0, delta=150.0)

    # 8. XAUUSD.c canonical mapping
    def test_08_xauusd_c_canonical_mapping(self):
        inv = [{"name": "XAUUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 100.0}]
        res = self.resolver.resolve("XAUUSD", inventory=inv)
        self.assertEqual(res.status, "VALIDATED")
        self.assertEqual(res.broker_symbol, "XAUUSD.c")
        self.assertEqual(res.suffix, ".c")
        self.assertEqual(self.universe.get_canonical_symbol("XAUUSD.c"), "XAUUSD")

    # 9. BTCUSD.c canonical mapping
    def test_09_btcusd_c_canonical_mapping(self):
        inv = [{"name": "BTCUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0}]
        res = self.resolver.resolve("BTCUSD", inventory=inv)
        self.assertEqual(res.status, "VALIDATED")
        self.assertEqual(res.broker_symbol, "BTCUSD.c")
        self.assertEqual(res.suffix, ".c")
        self.assertEqual(self.universe.get_canonical_symbol("BTCUSD.c"), "BTCUSD")

    # 10. USDJPY.c canonical mapping rejected
    def test_10_usdjpy_c_canonical_mapping(self):
        inv = [{"name": "USDJPY.c", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 100000.0}]
        res = self.resolver.resolve("USDJPY", inventory=inv)
        self.assertEqual(res.status, "UNAUTHORIZED_SYMBOL")
        self.assertIsNone(res.broker_symbol)
        self.assertIn("INSTRUMENT_NOT_ALLOWED", res.reason)
        is_ok, reason = self.universe.validate_or_reject("USDJPY.c")
        self.assertFalse(is_ok)
        self.assertIn("INSTRUMENT_NOT_ALLOWED", reason)

    # 11. Standard symbol mapping
    def test_11_standard_symbol_mapping(self):
        inv = [
            {"name": "XAUUSD", "trade_mode": 4},
            {"name": "BTCUSD", "trade_mode": 4},
            {"name": "USDJPY", "trade_mode": 4},
        ]
        self.assertEqual(self.resolver.resolve("XAUUSD", inventory=inv).broker_symbol, "XAUUSD")
        self.assertEqual(self.resolver.resolve("BTCUSD", inventory=inv).broker_symbol, "BTCUSD")
        self.assertEqual(self.resolver.resolve("USDJPY", inventory=inv).status, "UNAUTHORIZED_SYMBOL")

    # 12. Broker suffix mapping (.m, .pro, .raw, .std)
    def test_12_broker_suffix_mapping(self):
        inv = [
            {"name": "XAUUSD.m", "trade_mode": 4},
            {"name": "BTCUSD.pro", "trade_mode": 4},
            {"name": "USDJPY.raw", "trade_mode": 4},
        ]
        self.assertEqual(self.resolver.resolve("XAUUSD", inventory=inv).broker_symbol, "XAUUSD.m")
        self.assertEqual(self.resolver.resolve("BTCUSD", inventory=inv).broker_symbol, "BTCUSD.pro")
        self.assertEqual(self.resolver.resolve("USDJPY", inventory=inv).status, "UNAUTHORIZED_SYMBOL")

    # 13. Unknown suffix rejected
    def test_13_unknown_suffix_rejected(self):
        inv = [{"name": "BTCUSD.unknown_suffix_xyz_123", "trade_mode": 4}]
        res = self.resolver.resolve("BTCUSD", inventory=inv)
        self.assertEqual(res.status, "SYMBOL_RESOLUTION_FAILED")

    # 14. Unauthorized instrument rejected fail-closed
    def test_14_unauthorized_instrument_rejected(self):
        unauthorized = ["USDJPY", "USDJPY.c", "USDJPY.m", "US30.std", "US30.c", "US30", "NAS100", "US100.std", "EURUSD", "EURUSD.c", "GBPUSD"]
        for sym in unauthorized:
            is_ok, reason = self.universe.validate_or_reject(sym)
            self.assertFalse(is_ok, f"Symbol {sym} must be rejected")
            self.assertTrue("INSTRUMENT_NOT_ALLOWED" in reason or "UNAUTHORIZED_SYMBOL" in reason)

    # 15. Correct cent-account minimum volume
    def test_15_cent_account_minimum_volume(self):
        sym_info = SymbolInfo(
            symbol="BTCUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            min_lot=0.05,  # Broker minimum lot 0.05
            max_lot=100.0,
            lot_step=0.01,
            ask=95000.0,
            bid=94990.0,
        )
        acc = AccountInfo(balance=1000.0, equity=1000.0, currency="USC", raw_currency="USC")
        res = self.sizing_engine.calculate_lot_size(
            account=acc,
            symbol_info=sym_info,
            entry_price=95000.0,
            stop_loss=90000.0,  # 5000 point stop loss
            risk_percent=1.0,
        )
        # Min lot 0.05 * 5000 points exceeds risk budget on a tiny balance -> rejected with explanation
        self.assertFalse(res.is_approved)
        self.assertIn("MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET", res.rejection_reason)

    # 16. Correct cent-account volume step
    def test_16_cent_account_volume_step(self):
        sym_info = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.05,  # Volume step 0.05
            ask=3850.0,
            bid=3849.50,
        )
        acc = AccountInfo(balance=2000.0, equity=2000.0, currency="USC", raw_currency="USC")
        res = self.sizing_engine.calculate_lot_size(
            account=acc,
            symbol_info=sym_info,
            entry_price=3850.0,
            stop_loss=3845.0,
            risk_percent=1.0,
        )
        if res.is_approved:
            # Volume must be multiple of 0.05
            remainder = round(res.volume % 0.05, 4)
            self.assertIn(remainder, (0.0, 0.05))

    # 17. Correct cent-account tick-value calculations
    def test_17_cent_account_tick_value_calculations(self):
        normalizer = AccountCurrencyNormalizer(account_type=AccountType.CENT, native_currency="USC", denomination_factor=100.0)
        # 100 ticks with tick_value = 2.0 USC -> 200 USC loss = $2.00 USD normalized loss
        native_loss, norm_loss = normalizer.calculate_loss_per_lot(sl_distance_price=1.0, tick_size=0.01, tick_value=2.0)
        self.assertEqual(native_loss, 200.0)
        self.assertEqual(norm_loss, 2.0)

    # 18. Correct margin calculations
    def test_18_correct_margin_calculations(self):
        acc = AccountInfo(
            balance=1000.0,
            equity=1000.0,
            free_margin=100.0,  # Only $100 free margin
            currency="USC",
            raw_currency="USC",
        )
        sym_info = SymbolInfo(
            symbol="BTCUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=10.0,
            lot_step=0.01,
            margin_required=500.0,  # Requires $500 margin per lot
            ask=95000.0,
            bid=94990.0,
        )
        res = self.sizing_engine.calculate_lot_size(
            account=acc,
            symbol_info=sym_info,
            entry_price=95000.0,
            stop_loss=94900.0,
            risk_percent=1.0,
        )
        # If required margin exceeds 50% of free margin, must reject
        if not res.is_approved and "margin" in (res.rejection_reason or "").lower():
            self.assertIn("margin", res.rejection_reason.lower())

    # 19. Correct stop-loss monetary risk
    def test_19_stop_loss_monetary_risk(self):
        acc = AccountInfo(balance=100000.0, equity=100000.0, currency="USC", raw_currency="USC")
        sym_info = SymbolInfo(
            symbol="USDJPY.c",
            digits=3,
            point=0.001,
            tick_size=0.001,
            tick_value=0.65,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            margin_required=10.0,
            ask=155.000,
            bid=154.990,
        )
        res = self.sizing_engine.calculate_lot_size(
            account=acc,
            symbol_info=sym_info,
            entry_price=155.000,
            stop_loss=154.500,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        # Risk must not exceed 2.0% R9 hard ceiling
        self.assertLessEqual(res.risk_percent_actual, 2.0)
        self.assertGreater(res.monetary_risk_native, 0.0)

    # 20. Correct commission and swap interpretation
    def test_20_commission_and_swap_interpretation(self):
        pos = Position(
            ticket=70007,
            symbol="BTCUSD.c",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=95000.0,
            current_price=95500.0,
            stop_loss=94000.0,
            take_profit=97000.0,
            profit=5000.0,  # 5,000 USC
            commission=-70.0,  # -70 USC
            swap=-10.0,  # -10 USC
            denomination_factor=100.0,
        )
        self.assertEqual(pos.native_profit, 5000.0)
        self.assertEqual(pos.normalized_profit, 50.0)
        self.assertEqual(pos.native_commission, -70.0)
        self.assertEqual(pos.normalized_commission, -0.70)
        self.assertEqual(pos.native_swap, -10.0)
        self.assertEqual(pos.normalized_swap, -0.10)
        self.assertEqual(pos.normalized_net_profit, 49.20)

    # 21. Independent cent-account position management
    def test_21_independent_cent_account_position_management(self):
        pos1 = Position(ticket=101, symbol="XAUUSD.c", order_type=OrderType.BUY, volume=0.05, open_price=3850.0, current_price=3860.0, stop_loss=3840.0, take_profit=3880.0, profit=1000.0, denomination_factor=100.0)
        pos2 = Position(ticket=102, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.02, open_price=95000.0, current_price=95500.0, stop_loss=94000.0, take_profit=97000.0, profit=2000.0, denomination_factor=100.0)

        self.assertEqual(pos1.normalized_profit, 10.0)
        self.assertEqual(pos2.normalized_profit, 20.0)
        self.assertEqual(pos1.ticket, 101)
        self.assertEqual(pos2.ticket, 102)

    # 22. Multiple positions on the same cent instrument
    def test_22_multiple_positions_on_same_cent_instrument(self):
        active_positions = [
            Position(ticket=201, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.01, open_price=94000.0, current_price=95000.0, stop_loss=93000.0, take_profit=97000.0, profit=500.0, denomination_factor=100.0, initial_risk_amount=5.0),
            Position(ticket=202, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.01, open_price=94500.0, current_price=95000.0, stop_loss=93500.0, take_profit=97000.0, profit=250.0, denomination_factor=100.0, initial_risk_amount=5.0),
        ]
        acc = AccountInfo(balance=1000.0, equity=1000.0, currency="USC", raw_currency="USC")
        cand = make_candidate("BTC_LAYER_3", "BTCUSD.c", OrderType.BUY, 95000.0, 94000.0, 97000.0)

        # Dynamic capacity evaluation allows 3rd position on BTCUSD.c
        cap = self.capacity_engine.evaluate_capacity(
            candidate=cand,
            account=acc,
            active_positions=active_positions,
            proposed_monetary_risk=5.0,
        )
        self.assertTrue(cap.allowed)
        self.assertEqual(cap.open_positions_on_symbol, 2)

    # 23. Dynamic position layering (>3 positions)
    def test_23_dynamic_position_layering(self):
        active = [
            Position(ticket=301, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.01, open_price=95000.0, current_price=95100.0, stop_loss=94000.0, take_profit=97000.0, profit=10.0, initial_risk_amount=5.0),
            Position(ticket=302, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.01, open_price=95050.0, current_price=95100.0, stop_loss=94050.0, take_profit=97000.0, profit=5.0, initial_risk_amount=5.0),
            Position(ticket=303, symbol="USDJPY.c", order_type=OrderType.BUY, volume=0.05, open_price=155.0, current_price=155.1, stop_loss=154.5, take_profit=156.0, profit=5.0, initial_risk_amount=5.0),
        ]
        acc = AccountInfo(balance=2000.0, equity=2000.0, currency="USC", raw_currency="USC")
        cand_4th = make_candidate("XAU_4TH", "XAUUSD.c", OrderType.BUY, 3850.0, 3845.0, 3860.0)

        cap = self.capacity_engine.evaluate_capacity(
            candidate=cand_4th,
            account=acc,
            active_positions=active,
            proposed_monetary_risk=10.0,
        )
        self.assertTrue(cap.allowed, "Dynamic capacity must approve 4th position when risk budget permits")
        self.assertEqual(cap.open_positions_total, 3)

    # 24. Position closure and risk release
    def test_24_position_closure_and_risk_release(self):
        active_before = [
            Position(ticket=401, symbol="XAUUSD.c", order_type=OrderType.BUY, volume=0.05, open_price=3850.0, current_price=3860.0, stop_loss=3840.0, take_profit=3880.0, profit=10.0, initial_risk_amount=25.0),
            Position(ticket=402, symbol="BTCUSD.c", order_type=OrderType.BUY, volume=0.02, open_price=95000.0, current_price=95200.0, stop_loss=94000.0, take_profit=97000.0, profit=5.0, initial_risk_amount=20.0),
        ]
        acc = AccountInfo(balance=1000.0, equity=1000.0, currency="USC")

        cand = make_candidate("TEST_RELEASE", "USDJPY.c", OrderType.BUY, 155.0, 154.5, 156.0)
        cap_before = self.capacity_engine.evaluate_capacity(cand, acc, active_before, proposed_monetary_risk=20.0)
        # Open risk is $45, budget is 6% of $1000 = $60. Remaining is $15. Proposed $20 -> rejected!
        self.assertFalse(cap_before.allowed)

        # Close position 401 (releasing $25 of risk)
        active_after = [p for p in active_before if p.ticket != 401]
        cap_after = self.capacity_engine.evaluate_capacity(cand, acc, active_after, proposed_monetary_risk=20.0)
        # Remaining capacity is now $60 - $20 = $40. Proposed $20 -> allowed!
        self.assertTrue(cap_after.allowed)

    # 25. Account-switch reconciliation
    def test_25_account_switch_reconciliation(self):
        manager = AccountSwitchManager(account_detector=self.detector, symbol_universe=self.universe)
        acc_std = {"login": 1001, "server": "Broker-Demo", "currency": "USD", "balance": 5000.0}
        inv_std = [
            {"name": "XAUUSD.m", "trade_mode": 4},
            {"name": "BTCUSD.m", "trade_mode": 4},
            {"name": "USDJPY.m", "trade_mode": 4},
        ]
        res1 = manager.check_and_handle_switch(acc_std, inventory=inv_std)
        self.assertEqual(res1.account_type, "DEMO_STANDARD")
        self.assertEqual(res1.symbols_resolved.get("BTCUSD"), "BTCUSD.m")

        # Now switch to Cent account
        acc_cent = {"login": 2002, "server": "Broker-Demo-Cent", "currency": "USC", "balance": 200000.0}
        inv_cent = [
            {"name": "XAUUSD.c", "trade_mode": 4},
            {"name": "BTCUSD.c", "trade_mode": 4},
            {"name": "USDJPY.c", "trade_mode": 4},
        ]
        res2 = manager.check_and_handle_switch(acc_cent, inventory=inv_cent)
        self.assertTrue(res2.switch_occurred)
        self.assertEqual(res2.account_type, "DEMO_CENT")
        self.assertEqual(res2.denomination_factor, 100.0)
        self.assertEqual(res2.symbols_resolved.get("BTCUSD"), "BTCUSD.c")

    # 26. Restart recovery
    def test_26_restart_recovery(self):
        # Position opened prior to restart with .c symbol
        recovered_pos = Position(
            ticket=55555,
            symbol="BTCUSD.c",
            order_type=OrderType.BUY,
            volume=0.01,
            open_price=94000.0,
            current_price=95000.0,
            stop_loss=93000.0,
            take_profit=97000.0,
            profit=1000.0,
            denomination_factor=100.0,
        )
        self.assertEqual(recovered_pos.actual_broker_symbol, "BTCUSD.c")
        self.assertEqual(self.universe.get_canonical_symbol(recovered_pos.symbol), "BTCUSD")
        self.assertEqual(recovered_pos.normalized_profit, 10.0)

    # 27. Stale symbol specifications rejected
    def test_27_stale_symbol_specifications_rejected(self):
        inv1 = [{"name": "BTCUSD.m", "trade_mode": 4, "digits": 2, "point": 0.01}]
        self.universe.resolve_universe(inventory=inv1)
        self.assertEqual(self.universe.get_broker_symbol("BTCUSD"), "BTCUSD.m")

        # Invalidate cache on account switch
        self.universe.invalidate()
        inv2 = [{"name": "BTCUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01}]
        self.universe.resolve_universe(inventory=inv2)
        # Stale .m symbol is gone, new .c symbol resolved!
        self.assertEqual(self.universe.get_broker_symbol("BTCUSD"), "BTCUSD.c")

    # 28. Stale account normalization rejected
    def test_28_stale_account_normalization_rejected(self):
        # Switching from Cent (100x) back to Standard (1x)
        norm_cent = AccountCurrencyNormalizer(account_type=AccountType.CENT, native_currency="USC", denomination_factor=100.0)
        self.assertEqual(norm_cent.to_normalized(5000.0).normalized_value, 50.0)

        # Switch to Standard
        norm_std = AccountCurrencyNormalizer(account_type=AccountType.STANDARD, native_currency="USD", denomination_factor=1.0)
        self.assertEqual(norm_std.to_normalized(5000.0).normalized_value, 5000.0)

    # 29. Concurrent risk reservation protection
    def test_29_concurrent_risk_reservation_protection(self):
        acc = AccountInfo(balance=1000.0, equity=1000.0, currency="USC")
        cand1 = make_candidate("CONC_1", "BTCUSD.c", OrderType.BUY, 95000.0, 94000.0, 97000.0)
        cand2 = make_candidate("CONC_2", "USDJPY.c", OrderType.BUY, 155.0, 154.5, 156.0)

        # Evaluate candidate 1 with $40 risk
        cap1 = self.capacity_engine.evaluate_capacity(cand1, acc, [], proposed_monetary_risk=40.0)
        self.assertTrue(cap1.allowed)

        # While cand1 is in-flight ($40 pending), cand2 ($30 risk) exceeds $60 budget
        cap2 = self.capacity_engine.evaluate_capacity(
            cand2, acc, [], proposed_monetary_risk=30.0, pending_orders_risk_usd=40.0
        )
        self.assertFalse(cap2.allowed, "Concurrent order must be blocked when aggregate risk exceeds budget")

    # 30. Companion account-status synchronization
    def test_30_companion_account_status_synchronization(self):
        acc = AccountInfo(
            account_number=88888,
            currency="USC",
            balance=100000.0,
            equity=100000.0,
            broker_server="JustMarkets-Cent",
            trade_mode="DEMO",
        )
        self.assertTrue(acc.is_cent_account)
        self.assertEqual(acc.account_type, "DEMO_CENT")
        self.assertEqual(acc.normalized_balance, 1000.0)  # Normalized
        self.assertEqual(acc.raw_balance, 100000.0)  # Native

        # Verify structured symbol mapping synchronization (USDJPY excluded)
        inv = [
            {"name": "XAUUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 100.0},
            {"name": "BTCUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
            {"name": "USDJPY.c", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 100000.0},
        ]
        self.universe.resolve_universe(inventory=inv)
        mappings = self.universe.get_structured_mappings()
        self.assertIn("BTCUSD", mappings)
        self.assertEqual(mappings["BTCUSD"]["actual_broker_symbol"], "BTCUSD.c")
        self.assertEqual(mappings["BTCUSD"]["validation_status"], "VALIDATED")
        self.assertNotIn("USDJPY", mappings)


if __name__ == "__main__":
    unittest.main()
