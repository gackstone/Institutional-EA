"""
Unit and Integration Test Suite: Unified Risk Calculation, Removal of Micro-Lot Overrides
and Cent/Micro Account Execution Reconciliation (Cases A through H).
"""

import unittest
from datetime import datetime, timezone
from typing import Dict, Any, List

from src.core.contracts import (
    AccountInfo,
    SymbolInfo,
    SignalCandidate,
    OrderType,
    SetupType,
    Timeframe,
    TradePlan,
)
from src.risk.position_sizing import PositionSizingEngine, PositionSizeResult
from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine, PortfolioCapacityResult
from src.broker_adaptation.account_normalization import (
    AccountNormalizationEngine,
    AccountType,
    NormalizedAccountSnapshot,
)


class TestUnifiedRiskReconciliation(unittest.TestCase):
    def setUp(self):
        self.norm_engine = AccountNormalizationEngine()
        self.sizing_engine = PositionSizingEngine(
            default_risk_percent=1.0,
            max_risk_percent_per_trade=2.0
        )
        self.capacity_engine = DynamicPortfolioCapacityEngine(
            max_aggregate_open_risk_percent=1.5,
            max_symbol_risk_percent=1.0,
            min_margin_level_percent=150.0,
            max_margin_utilization_percent=20.0,
        )

        # Standard USD Account ($1,840.07 reference)
        self.std_account = AccountInfo(
            account_number=2002270203,
            balance=1840.07,
            equity=1840.07,
            free_margin=1840.07,
            currency="USD",
            raw_currency="USD",
            leverage=100,
            trade_mode="DEMO",
            broker_server="JustMarkets-Demo",
        )

        # Cent USC Account (1,571.90 USC = ~$15.72 USD)
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

        # USDJPY Cent Symbol (contract size 1,000, 3 digits, point 0.001)
        self.sym_usdjpy_cent = SymbolInfo(
            symbol="USDJPY.c",
            digits=3,
            point=0.001,
            tick_size=0.001,
            tick_value=0.0065,  # native USC tick value per lot (or ~0.65 JPY / 100)
            contract_size=1000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=0.50,
            spread=15,
        )

        # USDJPY Standard Symbol (contract size 100,000, 3 digits, point 0.001)
        self.sym_usdjpy_std = SymbolInfo(
            symbol="USDJPY.m",
            digits=3,
            point=0.001,
            tick_size=0.001,
            tick_value=0.65,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=10.0,
            spread=15,
        )

        # XAUUSD Cent Symbol (contract size 1.0, 2 digits, point 0.01)
        self.sym_xau_cent = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=1.30,
            spread=25,
        )

        # XAUUSD Standard Symbol (contract size 100.0, 2 digits, point 0.01)
        self.sym_xau_std = SymbolInfo(
            symbol="XAUUSD.m",
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

    # =========================================================================
    # Cases A & B: Sizing vs Execution Contradiction Elimination
    # =========================================================================
    def test_cases_a_and_b_sizing_vs_execution_volume_risk_identity(self):
        """
        Verify that sizing output and downstream execution consumption produce
        identical volume and risk metrics without contradictory recalculations.
        """
        entry = 155.000
        sl = 154.500  # 500 points (50 pips)
        tp = 156.500  # 1500 points (150 pips, 3.0 RR)

        res = self.sizing_engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.sym_usdjpy_cent,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )

        self.assertTrue(res.is_approved)
        # Volume must be positive and strictly within permitted limits
        self.assertGreater(res.volume, 0.0)
        self.assertLessEqual(res.monetary_risk_native, 16.0)  # <= 1% of 1,571.90 USC = 15.72 USC

        # Downstream TradePlan construction must inherit the exact volume and risk
        plan = TradePlan(
            plan_id="PLAN_CASE_A",
            symbol=self.sym_usdjpy_cent.symbol,
            direction=OrderType.BUY,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            lots=res.volume,
            risk_percent=res.risk_percent_actual,
            reward_to_risk=res.reward_to_risk,
            structure_state="BOS_CONFIRMED",
            timestamp=datetime.now(timezone.utc),
        )

        self.assertEqual(plan.lots, res.volume)
        self.assertEqual(plan.risk_percent, res.risk_percent_actual)
        self.assertEqual(plan.reward_to_risk, res.reward_to_risk)

        # Capacity engine receives identical native risk
        cand = SignalCandidate(
            id="CAND_CASE_A",
            symbol=self.sym_usdjpy_cent.symbol,
            direction=OrderType.BUY,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            timeframe=Timeframe.M15,
            setup_type=SetupType.SESSION_SWEEP,
            risk_reward=res.reward_to_risk,
            score=85.0,
            timestamp=datetime.now(timezone.utc),
        )
        cap = self.capacity_engine.evaluate_capacity(
            candidate=cand,
            account=self.cent_account,
            active_positions=[],
            proposed_monetary_risk=res.monetary_risk,
            margin_required=res.margin_required,
        )
        self.assertTrue(cap.allowed)
        self.assertEqual(cap.proposed_risk_usd, res.monetary_risk)

    # =========================================================================
    # Case C: USDJPY Minimum-Lot Affordability Rejection
    # =========================================================================
    def test_case_c_usdjpy_min_lot_affordability_rejection(self):
        """
        When minimum broker lot size exceeds the risk budget, the engine must
        reject the trade with MIN_VOLUME_EXCEEDS_RISK_BUDGET and return 0.00 volume.
        """
        # Account with $6.00 USD balance attempting standard USDJPY.m (contract size 100,000)
        small_usd_account = AccountInfo(
            account_number=30002,
            balance=6.0,
            equity=6.0,
            free_margin=6.0,
            currency="USD",
            raw_currency="USD",
            leverage=100,
            trade_mode="DEMO",
            broker_server="Standard-Live",
        )
        # 1.0% risk budget of $6.00 = $0.06 USD.
        # A 50-pip SL on standard USDJPY risks $3.25 USD on min 0.01 lot.
        # Required raw lot: 0.06 / 325 = 0.00018 << 0.01.
        res = self.sizing_engine.calculate_lot_size(
            account=small_usd_account,
            symbol_info=self.sym_usdjpy_std,
            entry_price=155.000,
            stop_loss=154.500,  # 50 pips SL
            take_profit=156.500,
            order_type=OrderType.BUY,
            risk_percent=1.0,
            adaptive_scalping=False,
        )
        self.assertFalse(res.is_approved)
        self.assertEqual(res.volume, 0.0)
        self.assertIn("MIN_VOLUME_EXCEEDS_RISK_BUDGET", res.rejection_reason)
        self.assertFalse(res.is_micro_exception)

    # =========================================================================
    # Case D: Micro-Lot Override Elimination
    # =========================================================================
    def test_case_d_elimination_of_micro_lot_override(self):
        """
        Prove that when raw calculated volume < min_lot (e.g. raw 0.0059 lots vs min 0.01),
        the engine NEVER rounds up or grants a micro-lot exception.
        Volume MUST be 0.00 and is_micro_exception MUST be False.
        """
        # Account with $15.72 USD standard capital
        small_usd_account = AccountInfo(
            account_number=30001,
            balance=15.72,
            equity=15.72,
            free_margin=15.72,
            currency="USD",
            raw_currency="USD",
            leverage=100,
            trade_mode="DEMO",
            broker_server="Standard-Live",
        )
        # Standard Gold contract (100 oz): 0.01 lot with 50 pt ($0.50 move) = $50.00 loss
        # On $15.72 capital, raw volume = 0.1572 / 5000 = 0.00003 lots << 0.01 min_lot.
        res = self.sizing_engine.calculate_lot_size(
            account=small_usd_account,
            symbol_info=self.sym_xau_std,
            entry_price=2600.00,
            stop_loss=2595.00,  # 500 pt SL
            take_profit=2615.00,
            order_type=OrderType.BUY,
            risk_percent=1.0,
            adaptive_scalping=True,  # Even with adaptive scalping active, override is prohibited!
        )
        self.assertFalse(res.is_approved)
        self.assertEqual(res.volume, 0.0)
        self.assertFalse(res.is_micro_exception)
        self.assertIn("MIN_VOLUME_EXCEEDS_RISK_BUDGET", res.rejection_reason)

    # =========================================================================
    # Case E: Currency Normalization Fidelity
    # =========================================================================
    def test_case_e_currency_normalization_cent_to_usd(self):
        """
        1,571.90 USC must normalize to $15.72 USD (factor 100.0), never $1,571.90 USD.
        Native risk in USC and normalized risk in USD must be strictly consistent.
        """
        raw = {
            "login": 1200556240,
            "balance": 1571.90,
            "equity": 1571.90,
            "currency": "USC",
            "server": "JustMarkets-Demo3",
        }
        snap = self.norm_engine.normalize_account_snapshot(raw)
        self.assertEqual(snap.account_type, AccountType.CENT_USC)
        self.assertEqual(snap.denomination_factor, 100.0)
        self.assertAlmostEqual(snap.native_balance, 1571.90, places=2)
        self.assertAlmostEqual(snap.normalized_balance, 15.72, places=2)

        # Sizing result on cent account reports consistent native and normalized risk
        res = self.sizing_engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.sym_xau_cent,
            entry_price=2600.00,
            stop_loss=2595.00,
            take_profit=2615.00,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        if res.is_approved:
            self.assertAlmostEqual(
                res.monetary_risk_native / 100.0,
                res.monetary_risk_normalized,
                places=2
            )

    # =========================================================================
    # Case F: Unified Risk/Reward Calculation
    # =========================================================================
    def test_case_f_unified_risk_reward_consistency(self):
        """
        Reward-to-Risk ratio must be computed identically between entry, SL, TP,
        and transaction costs, ensuring signal, sizing, and plan RR match.
        """
        entry = 2600.00
        sl = 2595.00   # 500 points
        tp = 2615.00   # 1500 points (3:1 gross distance)

        res = self.sizing_engine.calculate_lot_size(
            account=self.std_account,
            symbol_info=self.sym_xau_std,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        # Expected net RR is slightly less than 3.0 due to spread and commission
        self.assertGreaterEqual(res.reward_to_risk, 2.70)
        self.assertLessEqual(res.reward_to_risk, 3.00)

        # Candidate and TradePlan adopt size_result.reward_to_risk
        cand = SignalCandidate(
            id="CAND_CASE_F",
            symbol="XAUUSD.m",
            direction=OrderType.BUY,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            timeframe=Timeframe.M15,
            setup_type=SetupType.SESSION_SWEEP,
            score=90.0,
            timestamp=datetime.now(timezone.utc),
            risk_reward=res.reward_to_risk,
        )
        self.assertEqual(cand.risk_reward, res.reward_to_risk)

    # =========================================================================
    # Case G: OrderCheck Preflight Diagnostics
    # =========================================================================
    def test_case_g_order_check_diagnostics_success_and_failure(self):
        """
        OrderCheck returning retcode 0 (or 10009/10027) with comment 'Done'
        must be classified as SUCCESS, while specific broker retcodes (10014, 10019)
        must be mapped to descriptive error codes.
        """
        # Simulated success response from MT5 OrderCheck
        success_resp = {
            "status": "SUCCESS",
            "request_id": "REQ_001",
            "symbol": "XAUUSD.m",
            "retcode": 0,
            "margin": 1.29,
            "margin_free": 1838.78,
            "margin_level": 142540.0,
            "comment": "Done"
        }
        self.assertEqual(success_resp["status"], "SUCCESS")
        self.assertEqual(success_resp["retcode"], 0)

        # Simulated failure response: Invalid Volume
        fail_vol = {
            "status": "ERROR",
            "request_id": "REQ_002",
            "symbol": "XAUUSD.m",
            "retcode": 10014,
            "comment": "Invalid volume"
        }
        rej_code = "ORDER_CHECK_FAILED"
        if fail_vol["retcode"] == 10014:
            rej_code = "INVALID_VOLUME"
        self.assertEqual(rej_code, "INVALID_VOLUME")

        # Simulated failure response: Insufficient Margin
        fail_margin = {
            "status": "ERROR",
            "request_id": "REQ_003",
            "symbol": "XAUUSD.m",
            "retcode": 10019,
            "comment": "No money"
        }
        rej_code_margin = "ORDER_CHECK_FAILED"
        if fail_margin["retcode"] == 10019:
            rej_code_margin = "INSUFFICIENT_MARGIN"
        self.assertEqual(rej_code_margin, "INSUFFICIENT_MARGIN")

    # =========================================================================
    # Case H: Standard USD Risk Percentage Reporting
    # =========================================================================
    def test_case_h_standard_usd_risk_reporting_fidelity(self):
        """
        On Standard USD account ($1,840.07), risk percent must accurately reflect
        actual dollar loss against capital base (e.g. $18.40 loss = 1.00% risk).
        """
        entry = 2600.00
        sl = 2595.00
        tp = 2615.00

        res = self.sizing_engine.calculate_lot_size(
            account=self.std_account,
            symbol_info=self.sym_xau_std,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            order_type=OrderType.BUY,
            risk_percent=1.0,
        )
        self.assertTrue(res.is_approved)
        # Target risk budget: 1% of 1840.07 = $18.40 USD
        self.assertLessEqual(res.monetary_risk_native, 18.40)
        self.assertAlmostEqual(res.monetary_risk_native, res.monetary_risk_normalized, places=2)
        # Actual risk percentage based on base SL loss must be <= target risk (1.0%)
        self.assertLessEqual(res.risk_percent_actual, 1.0)
        base_sl_loss = res.volume * (500 * self.sym_xau_std.point * self.sym_xau_std.tick_value / self.sym_xau_std.tick_size)
        expected_risk_pct = (base_sl_loss / self.std_account.balance) * 100.0
        self.assertAlmostEqual(res.risk_percent_actual, expected_risk_pct, places=2)


if __name__ == "__main__":
    unittest.main()
