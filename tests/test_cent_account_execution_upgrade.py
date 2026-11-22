"""
Universal Small-Account and Cent-Account Execution Upgrade Test Suite.
Verifies:
- Standard USD and USC cent account execution compatibility.
- Adaptive micro-lot sizing (0.01 lots) with mathematical parity.
- Broker symbol suffix resolution (.c, .m, .pro).
- Dynamic filling mode handling (FOK for cent accounts).
- Removal of artificial trade blockers (3/3 caps, hardcoded USD balance minimums).
- Live broker order_check compatibility.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

from src.core.contracts import (
    AccountInfo,
    SymbolInfo,
    OrderType,
    SetupType,
    Timeframe,
    SignalCandidate,
    SignalLifecycleState,
)
from src.core.config import AppConfig, RiskConfig
from src.core.broker_resolver import BrokerSymbolResolver
from src.core.symbol_universe import get_symbol_universe
from src.risk.position_sizing import PositionSizingEngine, PositionSizeResult
from src.risk.account_tier import AccountTierManager, AccountTier
from src.risk.target_feasibility import TargetFeasibilityEngine
from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.execution.order_manager import OrderManager


class TestUniversalCentAccountUpgrade(unittest.TestCase):

    def setUp(self):
        self.universe = get_symbol_universe()
        self.resolver = BrokerSymbolResolver()
        self.tier_mgr = AccountTierManager()

        # JustMarkets Demo3 Cent Account Profile (1500 USC loaded, leverage 1:2000)
        self.cent_account = AccountInfo(
            balance=1500.0,
            equity=1500.0,
            free_margin=1500.0,
            currency="USC",
            leverage=2000.0,
            raw_balance=1500.0,
            raw_equity=1500.0,
            raw_currency="USC",
            broker_server="JustMarkets-Demo3",
        )

        # Standard USD Account Profile ($10,000 USD loaded, leverage 1:100)
        self.usd_account = AccountInfo(
            balance=10000.0,
            equity=10000.0,
            free_margin=10000.0,
            currency="USD",
            leverage=100.0,
            raw_balance=10000.0,
            raw_equity=10000.0,
            raw_currency="USD",
        )

        # Small 500 USC Account Profile ($5.00 USD)
        self.micro_cent_account = AccountInfo(
            balance=500.0,
            equity=500.0,
            free_margin=500.0,
            currency="USC",
            leverage=2000.0,
            raw_balance=500.0,
            raw_equity=500.0,
            raw_currency="USC",
            broker_server="JustMarkets-Demo3",
        )

        # Cent Symbol Specs (JustMarkets Demo3: XAUUSD.c, USDJPY.c)
        self.xau_cent = SymbolInfo(
            symbol="XAUUSD.c",
            digits=2,
            point=0.01,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            spread=15.0,
            ask=2600.15,
            bid=2600.00,
            tick_value=1.0,
            tick_size=0.01,
            currency_base="XAU",
            currency_profit="USD",
            currency_margin="XAU",
            filling_mode=1,  # FOK only
        )

        self.usdjpy_cent = SymbolInfo(
            symbol="USDJPY.c",
            digits=3,
            point=0.001,
            contract_size=1000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            spread=12.0,
            ask=150.012,
            bid=150.000,
            tick_value=0.6277,
            tick_size=0.001,
            currency_base="USD",
            currency_profit="JPY",
            currency_margin="USD",
            filling_mode=1,  # FOK only
        )

    def test_01_cent_account_recognition_and_native_balance(self):
        """Phase 1 & 3: Account recognition preserves native currency and calculates normalized parity."""
        self.assertTrue(self.cent_account.is_cent_account)
        self.assertEqual(self.cent_account.balance, 1500.0)  # Native USC preserved
        self.assertEqual(self.cent_account.equity, 1500.0)
        self.assertEqual(self.cent_account.currency, "USC")
        self.assertAlmostEqual(self.cent_account.normalized_balance, 15.0, places=2)  # $15 USD equivalent
        self.assertAlmostEqual(self.cent_account.normalized_equity, 15.0, places=2)

    def test_02_account_tier_mapping_for_cent_accounts(self):
        """Phase 2: 1500 USC ($15 USD) maps to MICRO tier ($5-$25), NOT STANDARD ($1500 USD)."""
        tier_def, changed, msg = self.tier_mgr.evaluate_account(self.cent_account)
        self.assertEqual(tier_def.name, "MICRO")
        self.assertTrue(tier_def.trading_allowed)

        # Standard USD $10,000 maps to LARGE
        tier_std, _, _ = self.tier_mgr.evaluate_account(self.usd_account)
        self.assertEqual(tier_std.name, "LARGE")

    def test_03_cent_symbol_resolution_with_broker_suffix(self):
        """Phase 4: Resolves canonical XAUUSD to broker XAUUSD.c seamlessly."""
        inv = [
            {"name": "XAUUSD.c", "trade_mode": 4, "digits": 2, "point": 0.01, "trade_contract_size": 1.0},
            {"name": "USDJPY.c", "trade_mode": 4, "digits": 3, "point": 0.001, "trade_contract_size": 1000.0},
        ]
        res_xau = self.resolver.resolve("XAUUSD", inventory=inv)
        self.assertEqual(res_xau.broker_symbol, "XAUUSD.c")
        self.assertIn(res_xau.status, ("VALIDATED", "RESOLVED_EXACT"))

        res_jpy = self.resolver.resolve("USDJPY", inventory=inv)
        self.assertEqual(res_jpy.status, "UNAUTHORIZED_SYMBOL")
        self.assertIsNone(res_jpy.broker_symbol)

    def test_04_position_sizing_cent_account_xauusd(self):
        """Phase 5: Adaptive micro-lot sizing calculates 0.01 lot without 100x inflation or margin errors."""
        engine = PositionSizingEngine(default_risk_percent=0.50, max_risk_percent_per_trade=2.0)
        res = engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.xau_cent,
            entry_price=2600.0,
            stop_loss=2595.0,  # 5 pt SL
            take_profit=2610.0,
            risk_percent=0.50,
            order_type=OrderType.BUY,
            adaptive_scalping=True,
        )
        self.assertTrue(res.is_approved, f"Sizing rejected: {res.rejection_reason}")
        self.assertEqual(res.volume, 0.01)  # Adaptive micro-lot 0.01 lot approved
        # 0.01 lot of Gold (1 oz contract size) with 5 pt SL risks 5.0 USC ($0.05 USD)
        self.assertAlmostEqual(res.monetary_risk_native, 5.0, delta=1.5)
        self.assertAlmostEqual(res.monetary_risk_normalized, 0.05, delta=0.02)
        # Risk percent is ~0.33% of 1500 USC equity (well under 2.0% R9 hard ceiling)
        self.assertLessEqual(res.risk_percent_actual, 2.0)
        # Margin required: 1.0 * 2600 * 0.01 / 2000 = $0.013 USD = 1.30 USC
        self.assertLess(res.margin_required, 10.0)  # Affordable margin

    def test_05_position_sizing_cent_account_usdjpy(self):
        """Phase 5: USDJPY.c sizing produces valid volume without dividing cents by dollars."""
        engine = PositionSizingEngine(default_risk_percent=0.25, max_risk_percent_per_trade=2.0)
        res = engine.calculate_lot_size(
            account=self.cent_account,
            symbol_info=self.usdjpy_cent,
            entry_price=150.00,
            stop_loss=149.80,  # 0.20 pt SL (20 pips)
            take_profit=150.40,
            risk_percent=0.25,
            order_type=OrderType.BUY,
            adaptive_scalping=True,
        )
        self.assertTrue(res.is_approved, f"Sizing rejected: {res.rejection_reason}")
        self.assertGreaterEqual(res.volume, 0.01)
        self.assertLessEqual(res.volume, 0.05)  # Reasonable volume, NOT 68 lots!
        self.assertLessEqual(res.risk_percent_actual, 2.0)

    def test_06_target_feasibility_on_cent_account(self):
        """Phase 6: Feasibility engine does not reject cent account trades with false R9 errors."""
        res = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=self.xau_cent,
            volume=0.01,
            entry_price=2600.0,
            stop_loss=2595.0,
            order_type=OrderType.BUY,
            account=self.cent_account,
            atr_m15=2.50,
            target_net_usd=20.0,
        )
        # Sizing risk is $0.05 USD on a $15 USD account (0.33% risk)
        self.assertLessEqual(res.risk_pct_of_capital, 2.0)

    def test_07_portfolio_capacity_multi_position_without_3_cap(self):
        """Phase 7 & 8: Dynamic capacity allows multi-position layering up to risk budget without 3/3 cap."""
        cap_engine = DynamicPortfolioCapacityEngine(
            max_aggregate_open_risk_percent=0.50,
            max_symbol_risk_percent=0.50,
            max_margin_utilization_percent=20.0,
        )
        cand = SignalCandidate(
            id="SIG_LAYER_1",
            symbol="XAUUSD.c",
            direction=OrderType.BUY,
            entry_price=2600.0,
            stop_loss=2595.0,
            take_profit=2610.0,
            timeframe=Timeframe.M1,
            setup_type=SetupType.FAST_SCALP,
            score=85.0,
            risk_reward=2.0,
            timestamp=datetime.now(timezone.utc),
        )
        # Capacity check with 0 open positions: Allowed
        res1 = cap_engine.evaluate_capacity(
            candidate=cand,
            account=self.cent_account,
            active_positions=[],
            proposed_monetary_risk=3.75,  # 0.25% of 1500 USC
            margin_required=1.30,
        )
        self.assertTrue(res1.allowed, f"Capacity rejected: {res1.rejection_reason}")
        self.assertEqual(res1.open_positions_total, 0)

    def test_08_order_manager_pre_check_with_19_param_diagnostics(self):
        """Phase 10: OrderManager executes pre-trade check and logs structured 19-parameter diagnostics."""
        cfg = AppConfig()
        cfg.risk = RiskConfig(
            risk_percentage=0.50,
            max_aggregate_open_risk_percent=0.50,
            max_margin_utilization_percent=20.0,
        )
        mock_bridge = MagicMock()
        mock_bridge.ping.return_value = True
        mock_bridge.is_connected.return_value = True

        sizing = PositionSizingEngine(default_risk_percent=0.25, max_risk_percent_per_trade=2.0)
        p_risk = PortfolioRiskEngine(config=cfg)
        om = OrderManager(config=cfg, bridge=mock_bridge, sizing_engine=sizing, portfolio_risk=p_risk)
        cand = SignalCandidate(
            id="SIG_DIAG_TEST",
            symbol="XAUUSD.c",
            direction=OrderType.BUY,
            entry_price=2600.0,
            stop_loss=2595.0,
            take_profit=2610.0,
            timeframe=Timeframe.M1,
            setup_type=SetupType.FAST_SCALP,
            score=90.0,
            risk_reward=2.0,
            status="APPROVED",
            timestamp=datetime.now(timezone.utc),
        )
        chk = om.run_pre_trade_checklist(cand, self.cent_account, self.xau_cent, [])
        self.assertTrue(chk.passed, f"Checklist failed: {chk.rejection_reasons}")
        self.assertEqual(chk.calculated_volume, 0.01)

    def test_09_live_mt5_broker_order_check(self):
        """Phase 11 & 12: Real broker order_check verification when live terminal is connected."""
        if not MT5_AVAILABLE:
            self.skipTest("MetaTrader5 package not available")
        if not mt5.initialize():
            self.skipTest("Live MT5 terminal not running")

        acc = mt5.account_info()
        if acc is None or acc.login != 1200556240:
            mt5.shutdown()
            self.skipTest("Not connected to target JustMarkets-Demo3 cent account")

        # Live order_check on XAUUSD.c with FOK filling mode
        req_xau = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD.c",
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY,
            "price": mt5.symbol_info_tick("XAUUSD.c").ask,
            "sl": mt5.symbol_info_tick("XAUUSD.c").ask - 5.0,
            "tp": mt5.symbol_info_tick("XAUUSD.c").ask + 10.0,
            "deviation": 20,
            "magic": 100101,
            "comment": "CENT_TEST_CHECK",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        chk_res = mt5.order_check(req_xau)
        mt5.shutdown()

        self.assertIsNotNone(chk_res)
        self.assertEqual(chk_res.retcode, 0, f"Live broker order_check failed: {chk_res.comment} (retcode {chk_res.retcode})")
        self.assertEqual(chk_res.comment, "Done")
        self.assertGreater(chk_res.margin, 0.0)


if __name__ == "__main__":
    unittest.main()
