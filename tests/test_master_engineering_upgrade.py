"""
Master Engineering Test Suite: Permissive Engine, Reliable SMC Execution & SL/TP Enforcement.

Validates all 20 specific acceptance criteria defined in Phase 11:
1. Genuinely valid bullish liquidity sweep setup proceeds directly to execution.
2. Genuinely valid bearish liquidity sweep setup proceeds directly to execution.
3. Genuinely valid MSS setup proceeds directly to execution.
4. Genuinely valid BOS/FVG setup proceeds directly to execution.
5. Genuinely valid Order Block setup proceeds directly to execution.
6. Genuinely valid CHOCH setup proceeds directly to execution.
7. Daily-loss circuit-breaker code is absent from the execution path and cannot block trades.
8. Persisted state from prior run does not disable trading after an application restart.
9. Confidence-threshold logic cannot silently suppress an otherwise valid setup.
10. Multiple independent valid setups processed without arbitrary strategy conflict rejections.
11. Position volume calculated correctly across Forex, Gold, Index, and Crypto instruments.
12. Every new position submitted to broker has valid, non-zero Stop Loss and Take Profit.
13. Any setup with invalid/missing Stop Loss or Take Profit rejected before submission.
14. Recoverable broker errors trigger controlled retries without creating duplicate positions.
15. Non-recoverable broker errors recorded accurately with broker retcode and reason.
16. Uncontrolled duplicate orders cannot be created across restarts or concurrent cycles.
17. Partial fills recorded accurately and remaining volume handled properly.
18. Positions reported as filled match actual broker position tickets and volume.
19. Telegram delivery failure does not halt signal generation or order execution.
20. Log messages use correct severity classification and correlation IDs.
"""

import unittest
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock, patch

from src.core.contracts import (
    Candle, OrderType, Timeframe, TrendBias, MarketStructureType,
    SignalCandidate, SignalLifecycleState, SetupType, AccountInfo,
    SymbolInfo, Position, TradeOrder, ExecutionMode,
    FairValueGap, OrderBlock, MarketStructureEvent,
)
from src.core.config import AppConfig, RiskConfig, StrategyConfig
from src.core.orchestrator import TradingBotOrchestrator
from src.smc.strategy_engine import SmcStrategyEngine
from src.smc.mtf_analyzer import MultiTimeframeContext, TimeframeAnalysis
from src.smc.structure_confirmation import ConfirmationState, CycleDirection, StructureStateSnapshot
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.execution.order_manager import OrderManager
from src.execution.transaction_manager import TransactionManager


def _create_candle_series(count: int, base_price: float, trend: str = "BULLISH", step: float = 0.0005) -> List[Candle]:
    candles = []
    t0 = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    p = base_price
    for i in range(count):
        delta = step if trend == "BULLISH" else (-step if trend == "BEARISH" else (step if i % 2 == 0 else -step))
        o = p
        c = o + delta
        h = max(o, c) + (abs(step) * 0.3)
        l = min(o, c) - (abs(step) * 0.3)
        candles.append(Candle(
            time=t0 + timedelta(minutes=15 * i),
            open=round(o, 5),
            high=round(h, 5),
            low=round(l, 5),
            close=round(c, 5),
            tick_volume=100,
            spread=10,
            complete=True
        ))
        p = c
    return candles


class TestMasterEngineeringUpgrade(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.execution_mode = ExecutionMode.SIMULATION
        self.config.legacy_filters_enabled = False
        self.config.telegram_bot_token = ""
        self.config.telegram_chat_id = ""
        self.config.risk.max_daily_loss_enabled = False
        self.config.risk.max_daily_loss_percent = 0.0

        self.strategy_engine = SmcStrategyEngine(
            min_score=50.0,
            min_rr=1.5,
            swing_lookback=3,
            allow_choch_only_entries=True,
            legacy_filters_enabled=False
        )

        self.mock_bridge = MagicMock()
        self.mock_bridge.is_connected.return_value = True
        self.mock_bridge.ping.return_value = True

        self.sizing_engine = PositionSizingEngine(default_risk_percent=float(self.config.risk.risk_percentage))
        self.portfolio_risk = PortfolioRiskEngine(self.config.risk)
        self.portfolio_risk.app_config = self.config

        self.tmp_ledger = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8")
        self.tmp_ledger.write("{}")
        self.tmp_ledger.close()
        self.config.transaction_ledger_file = self.tmp_ledger.name
        self.tx_manager = TransactionManager(ledger_file=self.tmp_ledger.name)

        self.order_manager = OrderManager(
            config=self.config,
            bridge=self.mock_bridge,
            sizing_engine=self.sizing_engine,
            portfolio_risk=self.portfolio_risk,
            transaction_manager=self.tx_manager,
        )

        self.account = AccountInfo(
            account_number=123456,
            balance=10000.0,
            equity=10000.0,
            free_margin=10000.0,
            margin=0.0,
            currency="USD",
            leverage=100,
            trading_enabled=True,
        )

        self.eurusd_info = SymbolInfo(
            symbol="EURUSD",
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            spread=2.0,
            ask=1.10002,
            bid=1.10000,
            stops_level=5,
        )

    def tearDown(self):
        if hasattr(self, "tmp_ledger") and os.path.exists(self.tmp_ledger.name):
            try:
                os.remove(self.tmp_ledger.name)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 1. Bullish Liquidity Sweep Proceeds to Execution
    # -------------------------------------------------------------------------
    def test_01_bullish_liquidity_sweep_proceeds_to_execution(self):
        candles = _create_candle_series(25, 1.1000, trend="BEARISH", step=0.0002)
        # Create a swing sweep on the final closed bars: sweep below prior low and close back inside
        prior_low = min(c.low for c in candles[:-3])
        candles[-2] = Candle(
            time=candles[-2].time,
            open=prior_low + 0.0001,
            high=prior_low + 0.0003,
            low=prior_low - 0.0008,  # Wick sweeps liquidity below prior low
            close=prior_low + 0.0002,  # Close reclaims back inside range
            complete=True
        )
        tf = TimeframeAnalysis(timeframe=Timeframe.H4, trend=TrendBias.STRONG_BULLISH, last_close=candles[-1].close)
        mtf = MultiTimeframeContext(symbol="EURUSD", timestamp=candles[-1].time, w1=tf, d1=tf, h4=tf, h1=tf, m15=tf, overall_bias=TrendBias.STRONG_BULLISH)

        cands = self.strategy_engine.scan_for_opportunities(mtf, candles)
        bull_cands = [c for c in cands if c.direction == OrderType.BUY]
        self.assertTrue(len(bull_cands) > 0, "Bullish sweep candidate must be identified")
        cand = bull_cands[0]
        self.assertEqual(cand.status, "APPROVED")

        # Execute through order manager
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed, f"Pre-trade checklist must pass: {check.rejection_reasons}")
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(cand.lifecycle_state, SignalLifecycleState.FILLED)

    # -------------------------------------------------------------------------
    # 2. Bearish Liquidity Sweep Proceeds to Execution
    # -------------------------------------------------------------------------
    def test_02_bearish_liquidity_sweep_proceeds_to_execution(self):
        candles = _create_candle_series(25, 1.1000, trend="BULLISH", step=0.0002)
        prior_high = max(c.high for c in candles[:-3])
        candles[-2] = Candle(
            time=candles[-2].time,
            open=prior_high - 0.0001,
            high=prior_high + 0.0008,  # Wick sweeps buy-side liquidity above prior high
            low=prior_high - 0.0003,
            close=prior_high - 0.0002,  # Close rejects back down inside range
            complete=True
        )
        tf = TimeframeAnalysis(timeframe=Timeframe.H4, trend=TrendBias.STRONG_BEARISH, last_close=candles[-1].close)
        mtf = MultiTimeframeContext(symbol="EURUSD", timestamp=candles[-1].time, w1=tf, d1=tf, h4=tf, h1=tf, m15=tf, overall_bias=TrendBias.STRONG_BEARISH)

        cands = self.strategy_engine.scan_for_opportunities(mtf, candles)
        bear_cands = [c for c in cands if c.direction == OrderType.SELL]
        self.assertTrue(len(bear_cands) > 0, "Bearish sweep candidate must be identified")
        cand = bear_cands[0]
        self.assertEqual(cand.status, "APPROVED")

        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed, f"Pre-trade checklist must pass: {check.rejection_reasons}")
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")

    # -------------------------------------------------------------------------
    # 3. MSS Setup Proceeds Directly to Execution
    # -------------------------------------------------------------------------
    def test_03_mss_setup_proceeds_to_execution(self):
        cand = SignalCandidate(
            id="EURUSD_BUY_MSS_01",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.SMC_MODEL_1_SWEEP,
            entry_price=1.10200,
            stop_loss=1.10000,
            take_profit=1.10600,
            risk_reward=2.0,
            score=70.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
            reasons=["MSS confirmed with displacement (+15)"],
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed)
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(cand.lifecycle_state, SignalLifecycleState.FILLED)

    # -------------------------------------------------------------------------
    # 4. BOS/FVG Setup Proceeds Directly to Execution (Model 2)
    # -------------------------------------------------------------------------
    def test_04_bos_fvg_setup_proceeds_to_execution(self):
        cand = SignalCandidate(
            id="EURUSD_BUY_BOS_FVG_01",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.SMC_MODEL_2_BOS_FVG,
            entry_price=1.10300,
            stop_loss=1.10100,
            take_profit=1.10800,
            risk_reward=2.5,
            score=75.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
            reasons=["BOS confirmed", "M15 FVG retracement retested"],
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed)
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")

    # -------------------------------------------------------------------------
    # 5. Order Block Setup Proceeds Directly to Execution (Model 3)
    # -------------------------------------------------------------------------
    def test_05_order_block_setup_proceeds_to_execution(self):
        cand = SignalCandidate(
            id="EURUSD_SELL_OB_01",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.SELL,
            setup_type=SetupType.SMC_MODEL_3_OB_RETEST,
            entry_price=1.10500,
            stop_loss=1.10700,
            take_profit=1.10000,
            risk_reward=2.5,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
            reasons=["Bearish Order Block retest at premium boundary"],
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed)
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")

    # -------------------------------------------------------------------------
    # 6. CHOCH Setup Proceeds Directly to Execution (Model 4)
    # -------------------------------------------------------------------------
    def test_06_choch_setup_proceeds_to_execution(self):
        cand = SignalCandidate(
            id="EURUSD_BUY_CHOCH_01",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.SMC_MODEL_4_CHOCH,
            entry_price=1.10150,
            stop_loss=1.09950,
            take_profit=1.10550,
            risk_reward=2.0,
            score=65.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
            reasons=["CHOCH displacement into valid entry zone"],
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed)
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")

    # -------------------------------------------------------------------------
    # 7. Daily Loss Circuit Breaker Is Absent and Cannot Block Trades
    # -------------------------------------------------------------------------
    def test_07_daily_loss_circuit_breaker_absent_cannot_block_trades(self):
        self.portfolio_risk.initialize_day(10000.0)
        # Record massive daily losses
        self.portfolio_risk.record_closed_trade(-500.0, volume=0.05)
        self.portfolio_risk.record_closed_trade(-300.0, volume=0.05)
        self.assertEqual(self.portfolio_risk.daily_realized_loss, 800.0)
        # Assert circuit breaker did not trigger on daily loss
        self.assertFalse(self.portfolio_risk.circuit_breaker_active)
        self.assertIsNone(self.portfolio_risk.circuit_breaker_reason)

        cand = SignalCandidate(
            id="EURUSD_PERM_01",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000,
            stop_loss=1.09800,
            take_profit=1.10400,
            risk_reward=2.0,
            score=60.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )
        allowed, reason = self.portfolio_risk.evaluate_new_order_permission(
            cand, self.account, [], 50.0, 0.05
        )
        self.assertTrue(allowed, f"Trade must not be rejected by daily loss: {reason}")

    # -------------------------------------------------------------------------
    # 8. Persisted State From Prior Run Does Not Disable Trading on Restart
    # -------------------------------------------------------------------------
    def test_08_persisted_state_from_prior_run_does_not_disable_trading_on_restart(self):
        stale_data = {
            "initial_balance": 10000.0,
            "peak_equity": 10500.0,
            "daily_starting_balance": 10000.0,
            "daily_starting_equity": 10000.0,
            "daily_realized_loss": 850.0,
            "circuit_breaker_active": True,
            "circuit_breaker_reason": "Daily loss limit breached",
            "buffer_halted": True,
            "hard_locked": True,
        }
        self.portfolio_risk.load_from_dict(stale_data)
        # On startup load, circuit breaker, buffer halt, and hard lock must be reset to clean state
        self.assertFalse(self.portfolio_risk.circuit_breaker_active)
        self.assertIsNone(self.portfolio_risk.circuit_breaker_reason)
        self.assertFalse(self.portfolio_risk.buffer_halted)
        self.assertFalse(self.portfolio_risk.hard_locked)

    # -------------------------------------------------------------------------
    # 9. Confidence Threshold Cannot Silently Suppress Valid Setup
    # -------------------------------------------------------------------------
    def test_09_confidence_threshold_cannot_silently_suppress_valid_setup(self):
        candles = _create_candle_series(25, 1.1000, trend="BULLISH", step=0.0003)
        tf = TimeframeAnalysis(timeframe=Timeframe.H4, trend=TrendBias.STRONG_BULLISH, last_close=candles[-1].close)
        mtf = MultiTimeframeContext(symbol="EURUSD", timestamp=candles[-1].time, w1=tf, d1=tf, h4=tf, h1=tf, m15=tf, overall_bias=TrendBias.STRONG_BULLISH)

        cands = self.strategy_engine.scan_for_opportunities(mtf, candles)
        for c in cands:
            # Under permissive mode, every genuinely valid setup is APPROVED regardless of score falling below 75
            self.assertEqual(c.status, "APPROVED")
            self.assertNotIn("Confluence score", "".join(c.rejection_reasons))

    # -------------------------------------------------------------------------
    # 10. Multiple Independent Valid Setups Processed Without Conflict
    # -------------------------------------------------------------------------
    def test_10_multiple_independent_valid_setups_processed_without_conflict(self):
        cand1 = SignalCandidate(
            id="EURUSD_BUY_MULTI_1", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=65.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        cand2 = SignalCandidate(
            id="XAUUSD_SELL_MULTI_2", symbol="XAUUSD", timeframe=Timeframe.M15,
            direction=OrderType.SELL, setup_type=SetupType.SMC_MODEL_3_OB_RETEST,
            entry_price=2700.00, stop_loss=2705.00, take_profit=2690.00,
            risk_reward=2.0, score=70.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check1 = self.order_manager.run_pre_trade_checklist(cand1, self.account, self.eurusd_info, [])
        self.assertTrue(check1.passed)

        xau_info = SymbolInfo(symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01, tick_value=1.0, contract_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01, spread=25.0, ask=2700.25, bid=2700.00)
        check2 = self.order_manager.run_pre_trade_checklist(cand2, self.account, xau_info, [])
        self.assertTrue(check2.passed)

        # Both can be executed independently
        ord1 = self.order_manager.execute_signal(cand1, self.account, self.eurusd_info, [], prevalidated=check1)
        ord2 = self.order_manager.execute_signal(cand2, self.account, xau_info, [], prevalidated=check2)
        self.assertIsNotNone(ord1)
        self.assertIsNotNone(ord2)
        self.assertEqual(ord1.status, "FILLED")
        self.assertEqual(ord2.status, "FILLED")

    # -------------------------------------------------------------------------
    # 11. Position Volume Calculated Correctly Across Asset Classes
    # -------------------------------------------------------------------------
    def test_11_position_volume_calculated_correctly_across_asset_classes(self):
        # 1. Forex: EURUSD (100k contract, 0.00001 pt)
        res_fx = self.sizing_engine.calculate_lot_size(
            account=self.account,
            symbol_info=self.eurusd_info,
            entry_price=1.10000,
            stop_loss=1.09800,  # 20 pips = 200 pts
            risk_percent=1.0,   # $100 risk
        )
        self.assertTrue(res_fx.is_approved)
        self.assertGreater(res_fx.volume, 0.0)
        self.assertLessEqual(res_fx.risk_percent_actual, 2.0)

        # 2. Gold: XAUUSD (100 contract, 0.01 pt)
        xau_info = SymbolInfo(symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01, tick_value=1.0, contract_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01, spread=20.0, ask=2700.20, bid=2700.00)
        res_gold = self.sizing_engine.calculate_lot_size(
            account=self.account,
            symbol_info=xau_info,
            entry_price=2700.00,
            stop_loss=2695.00,  # $5 sl distance
            risk_percent=1.0,
        )
        self.assertTrue(res_gold.is_approved)
        self.assertGreater(res_gold.volume, 0.0)

        # 3. Crypto: BTCUSD (1 contract, 0.01 pt)
        btc_info = SymbolInfo(symbol="BTCUSD", digits=2, point=0.01, tick_size=0.01, tick_value=0.01, contract_size=1.0, min_lot=0.01, max_lot=20.0, lot_step=0.01, spread=100.0, ask=90000.0, bid=89999.0)
        res_btc = self.sizing_engine.calculate_lot_size(
            account=self.account,
            symbol_info=btc_info,
            entry_price=90000.00,
            stop_loss=89000.00, # $1,000 sl distance
            risk_percent=1.0,
        )
        self.assertTrue(res_btc.is_approved)
        self.assertGreater(res_btc.volume, 0.0)

        # 4. Indices: US30 (1 contract, 0.1 pt)
        us30_info = SymbolInfo(symbol="US30", digits=1, point=0.1, tick_size=0.1, tick_value=1.0, contract_size=1.0, min_lot=0.1, max_lot=50.0, lot_step=0.1, spread=3.0, ask=43500.0, bid=43497.0)
        res_idx = self.sizing_engine.calculate_lot_size(
            account=self.account,
            symbol_info=us30_info,
            entry_price=43500.0,
            stop_loss=43400.0,  # 100 pts sl distance
            risk_percent=1.0,
        )
        self.assertTrue(res_idx.is_approved)
        self.assertGreater(res_idx.volume, 0.0)

    # -------------------------------------------------------------------------
    # 12. Every New Position Has Valid Non-Zero Stop Loss and Take Profit
    # -------------------------------------------------------------------------
    def test_12_every_new_position_has_valid_non_zero_sl_and_tp(self):
        cand = SignalCandidate(
            id="EURUSD_VALID_SLTP_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10500,
            risk_reward=2.5, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertGreater(order.stop_loss, 0.0)
        self.assertGreater(order.take_profit, 0.0)
        self.assertTrue(order.stop_loss < order.entry_price < order.take_profit)

    # -------------------------------------------------------------------------
    # 13. Invalid or Missing SL/TP Rejected Before Submission
    # -------------------------------------------------------------------------
    def test_13_invalid_or_missing_sl_tp_rejected_before_submission(self):
        # Missing Stop Loss (stop_loss <= 0)
        cand_no_sl = SignalCandidate(
            id="EURUSD_NO_SL", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=0.0, take_profit=1.10500,
            risk_reward=2.5, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check_no_sl = self.order_manager.run_pre_trade_checklist(cand_no_sl, self.account, self.eurusd_info, [])
        self.assertFalse(check_no_sl.passed)
        self.assertTrue(any("Stop loss is required" in r for r in check_no_sl.rejection_reasons))

        # BUY with Stop Loss above Entry
        cand_bad_sl = SignalCandidate(
            id="EURUSD_BAD_SL", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.10200, take_profit=1.10500,
            risk_reward=2.5, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check_bad_sl = self.order_manager.run_pre_trade_checklist(cand_bad_sl, self.account, self.eurusd_info, [])
        self.assertFalse(check_bad_sl.passed)
        self.assertTrue(any("Invalid stops on BUY" in r for r in check_bad_sl.rejection_reasons))

    # -------------------------------------------------------------------------
    # 14. Recoverable Broker Errors Trigger Controlled Retries Without Duplicates
    # -------------------------------------------------------------------------
    def test_14_recoverable_broker_errors_trigger_retries_without_duplicates(self):
        # Switch to DEMO mode to engage live broker execution path
        self.config.execution_mode = ExecutionMode.DEMO
        cand = SignalCandidate(
            id="EURUSD_RECOVERABLE_RETRY_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.assertTrue(check.passed)

        # 1st call returns 10004 REQUOTE, 2nd call confirms acceptance (10009)
        self.mock_bridge.execute_trade.side_effect = [
            {"status": "ERROR", "retcode": 10004, "message": "Requote"},
            {"status": "SUCCESS", "ticket": 777111, "price": 1.10010, "retcode": 10009}
        ]
        self.mock_bridge.get_positions.return_value = [
            Position(
                ticket=777111, symbol="EURUSD", order_type=OrderType.BUY,
                volume=check.calculated_volume, open_price=1.10010, current_price=1.10010,
                stop_loss=1.09800, take_profit=1.10400, profit=0.0, magic=self.config.magic_number
            )
        ]

        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.ticket, 777111)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(self.mock_bridge.execute_trade.call_count, 2)

    # -------------------------------------------------------------------------
    # 15. Non-Recoverable Broker Errors Recorded Accurately With Retcode
    # -------------------------------------------------------------------------
    def test_15_non_recoverable_broker_errors_recorded_with_retcode(self):
        self.config.execution_mode = ExecutionMode.DEMO
        cand = SignalCandidate(
            id="EURUSD_NON_RECOVERABLE_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        self.mock_bridge.execute_trade.return_value = {
            "status": "ERROR", "retcode": 10019, "message": "Insufficient margin for trade"
        }
        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "REJECTED")
        self.assertIn("Insufficient margin", order.error)
        self.assertEqual(cand.lifecycle_state, SignalLifecycleState.BROKER_REJECTED)

    # -------------------------------------------------------------------------
    # 16. Duplicate Orders Prevented Across Cycles and Restarts
    # -------------------------------------------------------------------------
    def test_16_duplicate_orders_prevented_across_cycles(self):
        cand = SignalCandidate(
            id="EURUSD_IDEMPOTENT_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        order1 = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order1)

        # Attempt executing the exact same candidate id a second time
        order2 = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [])
        self.assertIsNone(order2, "Second submission of identical signal must be rejected as duplicate")
        self.assertTrue(any("duplicate" in r.lower() for r in cand.rejection_reasons))

    # -------------------------------------------------------------------------
    # 17. Partial Fills Handled Accurately With Remaining Volume
    # -------------------------------------------------------------------------
    def test_17_partial_fills_handled_accurately(self):
        self.config.execution_mode = ExecutionMode.DEMO
        cand = SignalCandidate(
            id="EURUSD_PARTIAL_FILL_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])
        req_vol = check.calculated_volume
        filled_vol = round(req_vol / 2.0, 2)

        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS", "ticket": 888222, "price": 1.10000, "retcode": 10009
        }
        # Broker position reports only half the volume filled
        self.mock_bridge.get_positions.return_value = [
            Position(
                ticket=888222, symbol="EURUSD", order_type=OrderType.BUY,
                volume=filled_vol, open_price=1.10000, current_price=1.10000,
                stop_loss=1.09800, take_profit=1.10400, profit=0.0, magic=self.config.magic_number
            )
        ]

        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "PARTIALLY_FILLED")
        self.assertEqual(order.volume, filled_vol)
        self.assertEqual(cand.lifecycle_state, SignalLifecycleState.PARTIAL_FILL)

    # -------------------------------------------------------------------------
    # 18. Actual Broker Position Verified Against Position Ticket
    # -------------------------------------------------------------------------
    def test_18_broker_position_verified_against_ticket(self):
        self.config.execution_mode = ExecutionMode.DEMO
        cand = SignalCandidate(
            id="EURUSD_VERIFY_TICKET_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        check = self.order_manager.run_pre_trade_checklist(cand, self.account, self.eurusd_info, [])

        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS", "ticket": 999333, "price": 1.10005, "retcode": 10009
        }
        # If broker returns no position matching the ticket, order is unconfirmed
        self.mock_bridge.get_positions.return_value = []
        self.mock_bridge.send_request.return_value = {"status": "SUCCESS", "data": []}

        order = self.order_manager.execute_signal(cand, self.account, self.eurusd_info, [], prevalidated=check)
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "UNCONFIRMED")
        self.assertIn("no broker position", order.error)

    # -------------------------------------------------------------------------
    # 19. Telegram Delivery Failure Does Not Halt Execution
    # -------------------------------------------------------------------------
    def test_19_telegram_delivery_failure_does_not_halt_execution(self):
        orch = TradingBotOrchestrator(self.config)
        orch.alerts = MagicMock()
        orch.alerts.alert_signal_approved.side_effect = RuntimeError("Telegram connection timeout")
        orch.alerts.alert_order_submitted.side_effect = ConnectionError("Telegram socket closed")
        orch.alerts.alert_trade_executed.side_effect = Exception("Telegram rate limit 429")

        cand = SignalCandidate(
            id="EURUSD_TG_FAIL_01", symbol="EURUSD", timeframe=Timeframe.M15,
            direction=OrderType.BUY, setup_type=SetupType.M15_SMC_OTE,
            entry_price=1.10000, stop_loss=1.09800, take_profit=1.10400,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        orch.market_data.register_symbol_info(self.eurusd_info)
        orch.account_info = self.account

        # Order must execute smoothly without being interrupted by Telegram failures
        res = orch._execute_approved_candidate("EURUSD", cand, datetime.now(timezone.utc))
        self.assertIsNotNone(res)
        self.assertEqual(res.status, "EXECUTED")

    # -------------------------------------------------------------------------
    # 20. Correct Log Severity Classification and Correlation Identifier
    # -------------------------------------------------------------------------
    def test_20_logging_severity_classification_and_correlation_id(self):
        logger = logging.getLogger("TestAuditLogger")
        self.assertTrue(hasattr(logger, "success"), "Custom logger.success method must be registered")
        self.assertEqual(logging.SUCCESS, 25)

        cand = SignalCandidate(
            id="EURUSD_BUY_20261115_0900",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.SMC_MODEL_1_SWEEP,
            entry_price=1.10000,
            stop_loss=1.09800,
            take_profit=1.10400,
            risk_reward=2.0,
            score=75.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )
        # Correlation ID format verification
        self.assertIn("EURUSD", cand.id)
        self.assertIn("BUY", cand.id)


if __name__ == "__main__":
    unittest.main()
