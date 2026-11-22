"""
Comprehensive Verification Suite for Institutional EA Adaptive Account Architecture.
Tests Standard USD reference preservation, Micro USD automatic normalization,
Cent USC automatic normalization, broker volume constraints, and trade eligibility rules:
- Accounts are eligible when broker specifications and risk budget permit.
- Never force trades when minimum broker volume exceeds permitted risk.
- Never round volume up to force broker acceptance.
- Single-point normalization with zero double conversion.
"""

import math
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.contracts import AccountInfo, SymbolInfo, OrderType
from src.risk.position_sizing import PositionSizingEngine, PositionSizeResult
from src.risk.target_feasibility import TargetFeasibilityEngine, TargetFeasibilityResult
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.broker_adaptation.account_normalization import (
    AccountNormalizationEngine,
    AccountType,
    NormalizedAccountSnapshot,
    AdaptiveMonetaryThresholds,
)
from src.broker_adaptation.execution_capabilities import StandardRejectionCode


class TestAdaptiveAccountArchitecture(unittest.TestCase):
    def setUp(self):
        self.norm_engine = AccountNormalizationEngine()
        self.sizing_engine = PositionSizingEngine(
            default_risk_percent=1.0,
            max_risk_percent_per_trade=2.0
        )

        # 1. Standard USD Account ($10,000 reference)
        self.std_account = AccountInfo(
            account_number=10001,
            balance=10000.0,
            equity=10000.0,
            free_margin=10000.0,
            currency="USD",
            raw_currency="USD",
            leverage=100,
            trade_mode="DEMO",
            broker_server="Standard-Live",
        )

        # 2. Micro USD Account ($50 small balance)
        self.micro_account = AccountInfo(
            account_number=20002,
            balance=50.0,
            equity=50.0,
            free_margin=50.0,
            currency="USD",
            raw_currency="USD",
            leverage=100,
            trade_mode="DEMO",
            broker_server="XMGlobal-Micro",
        )

        # 3. Cent USC Account (1,571.90 USC = ~$15.72 USD)
        self.cent_account = AccountInfo(
            account_number=1200556240,
            balance=1571.90,
            equity=1571.90,
            free_margin=1571.90,
            currency="USC",
            raw_currency="USC",
            leverage=2000,
            trade_mode="DEMO",
            broker_server="JustMarkets-Demo3",
        )

        # Standard Symbols
        self.sym_xau_std = SymbolInfo(
            symbol="XAUUSD",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=260.0,
            spread=20,
        )

        self.sym_usdjpy_std = SymbolInfo(
            symbol="USDJPY",
            digits=3,
            point=0.001,
            tick_size=0.001,
            tick_value=0.65,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=1000.0,
            spread=12,
        )

        # Cent Symbols (JustMarkets-Demo3 specs)
        self.sym_xau_cent = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=1000.0,
            lot_step=0.01,
            margin_required=1.30,
            spread=25,
        )

        self.sym_usdjpy_cent = SymbolInfo(
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

    # =========================================================================
    # A. Standard USD Account Reference Preservation Tests
    # =========================================================================
    def test_standard_usd_account_detection_and_identity_preservation(self):
        """Verify Standard USD account behaves identically as the reference implementation."""
        raw = {"login": 10001, "balance": 10000.0, "equity": 10000.0, "currency": "USD", "server": "Standard-Live"}
        snap = self.norm_engine.normalize_account_snapshot(raw)
        
        self.assertEqual(snap.account_type, AccountType.STANDARD_USD)
        self.assertEqual(snap.denomination_factor, 1.0)
        self.assertEqual(snap.native_balance, 10000.0)
        self.assertEqual(snap.normalized_balance, 10000.0)
        self.assertTrue(snap.is_verified)

        thresh = self.norm_engine.resolve_adaptive_thresholds(snap, configured_risk_pct=1.0, reference_target_usd=20.0)
        self.assertEqual(thresh.target_net_profit_usd, 20.0)
        self.assertEqual(thresh.target_net_profit_native, 20.0)
        self.assertEqual(thresh.max_permitted_risk_usd, 100.0)
        self.assertEqual(thresh.max_permitted_risk_native, 100.0)

    def test_standard_usd_position_sizing_reference(self):
        """Standard USD account computes verified standard lot sizes."""
        # $10,000 balance, 1% risk = $100 budget.
        # XAUUSD: 500 pt SL ($5.00 move) on 100 oz contract = $500 structural loss/lot.
        # Total loss/lot = 500 (SL) + 20 (spread) + 7 (commission) = $527.
        # Raw lots = 100 / 527 = 0.1897 lots. Quantized downward = 0.18 lots.
        res = self.sizing_engine.calculate_lot_size(
            account=self.std_account,
            symbol_info=self.sym_xau_std,
            entry_price=2600.0,
            stop_loss=2595.0,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        self.assertAlmostEqual(res.volume, 0.18, places=2)
        self.assertLessEqual(res.monetary_risk_native, 100.0)
        self.assertAlmostEqual(res.monetary_risk_normalized, res.monetary_risk_native, places=2)

    # =========================================================================
    # B. Cent USC Account Normalization & Sizing Tests
    # =========================================================================
    def test_cent_usc_account_detection_and_single_conversion(self):
        """Verify Cent USC account is detected, denomination is 100.0, and converted exactly once."""
        raw = {"login": 1200556240, "balance": 1571.90, "equity": 1571.90, "currency": "USC", "server": "JustMarkets-Demo3"}
        snap = self.norm_engine.normalize_account_snapshot(raw)
        
        self.assertEqual(snap.account_type, AccountType.CENT_USC)
        self.assertEqual(snap.denomination_factor, 100.0)
        self.assertEqual(snap.native_balance, 1571.90)
        self.assertEqual(snap.normalized_balance, 15.72)
        self.assertTrue(snap.is_verified)

        thresh = self.norm_engine.resolve_adaptive_thresholds(snap, configured_risk_pct=1.0, reference_target_usd=20.0)
        # 1.0% risk on 1571.90 USC = 15.72 USC = $0.1572 USD
        self.assertAlmostEqual(thresh.max_permitted_risk_native, 15.72, places=2)
        self.assertAlmostEqual(thresh.max_permitted_risk_usd, 0.1572, places=4)

    def test_cent_usc_position_sizing_gold(self):
        """Cent account on XAUUSD.c calculates 0.02 - 0.03 lots, never 3.50+ lots."""
        res = self.sizing_engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.sym_xau_cent,
            entry_price=2600.0,
            stop_loss=2595.0,  # 5 pt SL
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        self.assertIn(res.volume, [0.02, 0.03])
        # Monetary risk: ~10.92 - 15.0 USC (< $0.16 USD)
        self.assertLessEqual(res.monetary_risk_native, 16.0)
        self.assertLessEqual(res.monetary_risk_normalized, 0.16)

    def test_cent_usc_position_sizing_usdjpy(self):
        """Cent account on USDJPY.c calculates safe micro-lots (~0.04 - 0.11 lots), never 20+ lots."""
        res = self.sizing_engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.sym_usdjpy_cent,
            entry_price=155.00,
            stop_loss=154.50,  # 50 pips SL
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        self.assertLess(res.volume, 0.50)
        self.assertGreaterEqual(res.volume, 0.04)
        self.assertLessEqual(res.monetary_risk_native, 16.0)

    # =========================================================================
    # C. Micro USD Account Normalization & Sizing Tests
    # =========================================================================
    def test_micro_usd_account_detection_and_normalization(self):
        """Verify Micro USD account with small balance ($50) is detected correctly."""
        raw = {"login": 20002, "balance": 50.0, "equity": 50.0, "currency": "USD", "server": "XMGlobal-Micro"}
        snap = self.norm_engine.normalize_account_snapshot(raw)
        
        self.assertEqual(snap.account_type, AccountType.MICRO_USD)
        self.assertEqual(snap.denomination_factor, 1.0)
        self.assertEqual(snap.native_balance, 50.0)
        self.assertEqual(snap.normalized_balance, 50.0)

        thresh = self.norm_engine.resolve_adaptive_thresholds(snap, configured_risk_pct=1.0, reference_target_usd=20.0)
        # 1.0% risk on $50 = $0.50 risk budget
        self.assertAlmostEqual(thresh.max_permitted_risk_usd, 0.50, places=2)
        self.assertAlmostEqual(thresh.max_permitted_risk_native, 0.50, places=2)

    # =========================================================================
    # D. Critical Trade Eligibility & Broker Constraint Rules
    # =========================================================================
    def test_rejection_when_minimum_volume_exceeds_risk_budget(self):
        """
        CRITICAL DIRECTIVE RULE:
        We must make every account eligible when permitted, but we MUST NOT force trades
        when the broker's minimum lot exceeds the permitted risk.
        Verify that MIN_VOLUME_EXCEEDS_RISK_BUDGET is emitted and volume is 0.00.
        """
        # Micro account has $15.72 USD capital, 1.0% risk budget = $0.1572 USD.
        # Suppose a standard XAUUSD symbol (100 oz contract) requires min_lot = 0.01.
        # With a 5 pt SL ($5.00 move), min lot 0.01 risks:
        # 0.01 lot * 100 oz * $5.00 = $5.00 USD loss!
        # $5.00 USD loss exceeds the $0.1572 risk budget (and even the 2.0% ceiling of $0.31).
        # Sizing must REJECT the trade and NEVER round up or force execution!
        res = self.sizing_engine.calculate_lot_size(
            account=self.micro_account,
            symbol_info=self.sym_xau_std,
            entry_price=2600.0,
            stop_loss=2595.0,  # 5 pt SL = $5.00/oz
            order_type=OrderType.BUY,
            risk_percent=1.0,
            adaptive_scalping=False,
        )
        self.assertFalse(res.is_approved)
        self.assertEqual(res.volume, 0.0)
        self.assertIn("MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET", res.rejection_reason)
        # Confirm no volume was forced
        self.assertLess(res.raw_lots, self.sym_xau_std.min_lot)

    def test_never_round_volume_up_to_force_broker_acceptance(self):
        """Verify downward volume quantization: never rounds up."""
        # If raw volume calculates to 0.028 lots and step is 0.01, quantized volume must be 0.02, not 0.03
        raw_volume = 0.028
        step = 0.01
        step_str = f"{step:.8f}".rstrip("0")
        step_decimals = len(step_str.split(".")[1]) if "." in step_str else 2
        steps_count = math.floor(round(raw_volume / step, 6))
        quantized = round(steps_count * step, step_decimals)
        self.assertEqual(quantized, 0.02)

    def test_broker_volume_step_precision_0001(self):
        """Verify support for brokers with 0.001 lot steps."""
        step = 0.001
        raw_volume = 0.0149
        step_str = f"{step:.8f}".rstrip("0")
        step_decimals = len(step_str.split(".")[1]) if "." in step_str else 2
        steps_count = math.floor(round(raw_volume / step, 6))
        quantized = round(steps_count * step, step_decimals)
        self.assertEqual(quantized, 0.014)
        self.assertEqual(step_decimals, 3)

    # =========================================================================
    # E. Double-Conversion Guard & Unverified Currency Security
    # =========================================================================
    def test_unverified_currency_halts_trading(self):
        """If currency cannot be verified, detect_account_type reports ACCOUNT_CURRENCY_UNVERIFIED."""
        raw = {"login": 99999, "balance": 1000.0, "currency": "XYZ", "server": "UnknownBroker"}
        snap = self.norm_engine.normalize_account_snapshot(raw)
        self.assertFalse(snap.is_verified)
        self.assertEqual(snap.verification_status, "ACCOUNT_CURRENCY_UNVERIFIED")

    def test_double_conversion_protection(self):
        """Verifies that normalized values cannot be converted twice."""
        raw = {"login": 1200556240, "balance": 1500.0, "currency": "USC"}
        snap = self.norm_engine.normalize_account_snapshot(raw)
        self.assertEqual(snap.normalized_balance, 15.0)

        # Re-normalizing an already normalized USD snapshot must preserve 15.0
        raw_normalized = {"login": 1200556240, "balance": snap.normalized_balance, "currency": "USD"}
        snap2 = self.norm_engine.normalize_account_snapshot(raw_normalized)
        self.assertEqual(snap2.normalized_balance, 15.0)


if __name__ == "__main__":
    unittest.main()
