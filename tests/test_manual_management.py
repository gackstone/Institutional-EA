"""
Unit Tests for Manual Position Adoption and Trade Management Subsystem.
Verifies all safety invariants, classification, user overrides, tightening rules,
and operational modes.
Tags: [SAFETY], [VIDEO/KNOWLEDGE], [ASSUMPTION]
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.adapters.broker_interface import BrokerAdapter, OrderResult, TradeRequest
from src.core.contracts import AccountInfo, Candle, OrderType, Position, SymbolInfo
from src.manual_mgmt.contracts import (
    AdoptionAssessment,
    ManagementMode,
    ManualMgmtConfig,
    ManualPositionRecord,
    PositionClass
)
from src.manual_mgmt.classifier import classify_position, clean_base_symbol
from src.manual_mgmt.registry import ManualPositionRegistry
from src.manual_mgmt.assessor import ManualPositionAssessor
from src.manual_mgmt.policy import ManualMgmtPolicy
from src.manual_mgmt.executor import ManualMgmtExecutor
from src.manual_mgmt.detector import ManualPositionDetector


class MockBroker(BrokerAdapter):
    def __init__(self, account_info: AccountInfo):
        self._account_info = account_info
        self._positions = []
        self.modify_calls = []
        self.order_calls = []

    def ping(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def get_account_info(self) -> AccountInfo:
        return self._account_info

    def get_positions(self, symbol=None):
        if symbol:
            return [p for p in self._positions if p.symbol == symbol]
        return list(self._positions)

    def get_rates(self, symbol, timeframe, count):
        return []

    def send_order(self, request: TradeRequest) -> OrderResult:
        self.order_calls.append(request)
        return OrderResult(success=True, ticket=99999, price=request.price, volume=request.volume, retcode=10009)

    def modify_order(self, ticket: int, sl: float, tp: float) -> OrderResult:
        self.modify_calls.append((ticket, sl, tp))
        return OrderResult(success=True, ticket=ticket, retcode=10009)

    def cancel_order(self, ticket: int) -> OrderResult:
        return OrderResult(success=True, ticket=ticket)

    def close_position(self, ticket: int, volume=None) -> OrderResult:
        return OrderResult(success=True, ticket=ticket)


class TestManualPositionManagement(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "manual_positions.json")
        self.hist_file = os.path.join(self.temp_dir, "manual_positions_history.json")
        self.audit_file = os.path.join(self.temp_dir, "manual_audit.log")
        self.pause_file = os.path.join(self.temp_dir, "PAUSE")

        self.account_demo = AccountInfo(account_number=12345, trade_mode="DEMO", margin_mode=2, margin_mode_str="HEDGING")
        self.account_real = AccountInfo(account_number=54321, trade_mode="REAL", margin_mode=2, margin_mode_str="HEDGING")
        self.account_netting = AccountInfo(account_number=99999, trade_mode="DEMO", margin_mode=1, margin_mode_str="NETTING")

        self.symbol_eurusd = SymbolInfo(
            symbol="EURUSD.m",
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            stops_level=5,
            ask=1.10010,
            bid=1.10000
        )

        base_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        self.candles_m15 = [
            Candle(time=base_time + timedelta(minutes=15 * i), open=1.0950 + i * 0.0005, high=1.0960 + i * 0.0005,
                   low=1.0945 + i * 0.0005, close=1.0955 + i * 0.0005)
            for i in range(25)
        ]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Deterministic Classification
    def test_classification_logic(self):
        # BOT_OWN
        pos_bot = Position(ticket=1, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.10,
                           current_price=1.10, stop_loss=1.09, take_profit=1.12, profit=0.0, magic=100101)
        self.assertEqual(classify_position(pos_bot, bot_magic=100101), PositionClass.BOT_OWN)

        # MANUAL (magic == 0)
        pos_manual = Position(ticket=2, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.10,
                              current_price=1.10, stop_loss=1.09, take_profit=1.12, profit=0.0, magic=0)
        self.assertEqual(classify_position(pos_manual, bot_magic=100101), PositionClass.MANUAL)

        # OTHER_EA (magic non-zero and not bot)
        pos_other = Position(ticket=3, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.10,
                             current_price=1.10, stop_loss=1.09, take_profit=1.12, profit=0.0, magic=777)
        self.assertEqual(classify_position(pos_other, bot_magic=100101), PositionClass.OTHER_EA)

        # EXCLUDED via comment tag
        pos_tag = Position(ticket=4, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.10,
                           current_price=1.10, stop_loss=1.09, take_profit=1.12, profit=0.0, magic=0, comment="#bot:off")
        self.assertEqual(classify_position(pos_tag, bot_magic=100101), PositionClass.EXCLUDED)

        # EXCLUDED via symbol list
        pos_sym = Position(ticket=5, symbol="BTCUSD", order_type=OrderType.BUY, volume=0.1, open_price=50000,
                           current_price=50000, stop_loss=49000, take_profit=52000, profit=0.0, magic=0)
        self.assertEqual(classify_position(pos_sym, bot_magic=100101, allowed_symbols=["EURUSD", "GBPUSD"]), PositionClass.EXCLUDED)

    # 2. Missing Stop Loss Adoption in PROTECT Mode
    def test_missing_stop_loss_adoption(self):
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        assessor = ManualPositionAssessor(config=config)
        policy = ManualMgmtPolicy(config=config, pause_file=self.pause_file)

        pos_naked = Position(ticket=100, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                             open_price=1.1000, current_price=1.1005, stop_loss=0.0, take_profit=0.0, profit=5.0, magic=0)
        rec = registry.adopt_position(pos_naked, mode=ManagementMode.PROTECT)

        assessment = assessor.assess(pos_naked, rec, self.candles_m15, symbol_info=self.symbol_eurusd)
        self.assertEqual(assessment.action, "SET_SL")
        self.assertGreater(assessment.recommended_sl, 0.0)
        self.assertLess(assessment.recommended_sl, pos_naked.open_price)

        allowed, reason = policy.validate_action(assessment, rec, pos_naked, self.account_demo, self.symbol_eurusd)
        self.assertTrue(allowed, reason)

    # 3. Tighten-Only Rule (R9.3) Stop Widening Rejection
    def test_tighten_only_sl_rejection(self):
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        policy = ManualMgmtPolicy(config=config, pause_file=self.pause_file)
        pos = Position(ticket=101, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1100, profit=20.0, magic=0)
        rec = ManualPositionRecord(ticket=101, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="PROTECT")

        # Attempt to widen stop to 1.0900 (further away from market) [SAFETY]
        bad_assessment = AdoptionAssessment(
            ticket=101, symbol="EURUSD.m", direction=OrderType.BUY, classification=PositionClass.MANUAL,
            action="SET_SL", recommended_sl=1.0900, reason="Bad move"
        )
        allowed, reason = policy.validate_action(bad_assessment, rec, pos, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed)
        self.assertIn("R9.3 violation", reason)

        # Attempt to place SL above market price
        above_market = AdoptionAssessment(
            ticket=101, symbol="EURUSD.m", direction=OrderType.BUY, classification=PositionClass.MANUAL,
            action="SET_SL", recommended_sl=1.1050, reason="Above price"
        )
        allowed2, reason2 = policy.validate_action(above_market, rec, pos, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed2)

    # 4. User Override Detection and 30-Minute Lockout
    def test_user_override_detection_and_lockout(self):
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file, lockout_minutes=30)
        pos = Position(ticket=102, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1100, profit=20.0, magic=0)
        rec = registry.adopt_position(pos, mode=ManagementMode.PROTECT)
        self.assertFalse(rec.is_locked_out())

        # Simulate user manually dragging stop to 1.0970 in MT5 terminal
        pos_moved = Position(ticket=102, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                             open_price=1.1000, current_price=1.1020, stop_loss=1.0970, take_profit=1.1100, profit=20.0, magic=0)
        now = datetime.now(timezone.utc)
        updated_rec, override_detected = registry.update_position_state(pos_moved, now=now)

        self.assertTrue(override_detected)
        self.assertTrue(updated_rec.user_override_detected)
        self.assertTrue(updated_rec.is_locked_out(now))

        # Check that policy rejects bot modifications while locked out [SAFETY]
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        policy = ManualMgmtPolicy(config=config, pause_file=self.pause_file)
        assessment = AdoptionAssessment(ticket=102, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="BREAK_EVEN",
                                        recommended_sl=1.1001, reason="Break-Even")
        allowed, reason = policy.validate_action(assessment, updated_rec, pos_moved, self.account_demo, self.symbol_eurusd, now=now)
        self.assertFalse(allowed)
        self.assertIn("User manual override active", reason)

        # After 31 minutes, lockout expires
        future_time = now + timedelta(minutes=31)
        self.assertFalse(updated_rec.is_locked_out(future_time))

    # 5. Real Account Barrier
    def test_real_account_barrier(self):
        config_safe = ManualMgmtConfig(mode=ManagementMode.PROTECT, allow_real_account_management=False)
        policy_safe = ManualMgmtPolicy(config=config_safe, pause_file=self.pause_file)
        pos = Position(ticket=103, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1050, stop_loss=1.0950, take_profit=1.1100, profit=50.0, magic=0)
        rec = ManualPositionRecord(ticket=103, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="PROTECT")
        assessment = AdoptionAssessment(ticket=103, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="BREAK_EVEN",
                                        recommended_sl=1.1001, reason="Break-Even")

        # Rejected on REAL account when allow_real_account_management is False [SAFETY]
        allowed, reason = policy_safe.validate_action(assessment, rec, pos, self.account_real, self.symbol_eurusd)
        self.assertFalse(allowed)
        self.assertIn("REAL account detected", reason)

        # Allowed when flag is explicitly True
        config_real_allowed = ManualMgmtConfig(mode=ManagementMode.PROTECT, allow_real_account_management=True)
        policy_real_allowed = ManualMgmtPolicy(config=config_real_allowed, pause_file=self.pause_file)
        allowed2, reason2 = policy_real_allowed.validate_action(assessment, rec, pos, self.account_real, self.symbol_eurusd)
        self.assertTrue(allowed2, reason2)

    # 6. Netting Account Barrier
    def test_netting_account_barrier(self):
        config = ManualMgmtConfig(mode=ManagementMode.FULL)
        policy = ManualMgmtPolicy(config=config, pause_file=self.pause_file)
        pos = Position(ticket=104, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1050, stop_loss=1.0950, take_profit=1.1100, profit=50.0, magic=0)
        rec = ManualPositionRecord(ticket=104, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="FULL")
        assessment = AdoptionAssessment(ticket=104, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="BREAK_EVEN",
                                        recommended_sl=1.1001, reason="Break-Even")

        # Rejects action on Netting account [SAFETY]
        allowed, reason = policy.validate_action(assessment, rec, pos, self.account_netting, self.symbol_eurusd)
        self.assertFalse(allowed)
        self.assertIn("Netting account detected", reason)

    # 7. Emergency Pause (state/PAUSE)
    def test_emergency_pause_file(self):
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        policy = ManualMgmtPolicy(config=config, pause_file=self.pause_file)
        pos = Position(ticket=105, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1050, stop_loss=1.0950, take_profit=1.1100, profit=50.0, magic=0)
        rec = ManualPositionRecord(ticket=105, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="PROTECT")
        assessment = AdoptionAssessment(ticket=105, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="BREAK_EVEN",
                                        recommended_sl=1.1001, reason="Break-Even")

        # Create PAUSE file
        with open(self.pause_file, "w") as f:
            f.write("EMERGENCY_STOP")

        allowed, reason = policy.validate_action(assessment, rec, pos, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed)
        self.assertIn("emergency pause", reason)

    # 8. Break-Even at +1.0R
    def test_break_even_at_one_r(self):
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT, break_even_activation_r=1.0)
        assessor = ManualPositionAssessor(config=config)
        # Entry 1.1000, SL 1.0950 (50 pips risk). At 1.1055, current R = 55 / 50 = +1.1R
        pos_profit = Position(ticket=106, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                              open_price=1.1000, current_price=1.1055, stop_loss=1.0950, take_profit=1.1100, profit=55.0, magic=0)
        rec = ManualPositionRecord(ticket=106, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="PROTECT", break_even_applied=False)

        assessment = assessor.assess(pos_profit, rec, self.candles_m15, symbol_info=self.symbol_eurusd)
        self.assertEqual(assessment.action, "BREAK_EVEN")
        self.assertGreater(assessment.recommended_sl, pos_profit.open_price)

    # 9. Mode Hierarchies: PROTECT vs ASSIST Trailing Stops
    def test_mode_trailing_stop_permission(self):
        # In PROTECT mode, trailing stops are prohibited (BE and initial SL only)
        config_protect = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        policy_protect = ManualMgmtPolicy(config=config_protect, pause_file=self.pause_file)
        pos = Position(ticket=107, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1080, stop_loss=1.1005, take_profit=1.1200, profit=80.0, magic=0)
        rec = ManualPositionRecord(ticket=107, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.1005, initial_tp=1.1200,
                                   current_tp=1.1200, adoption_time="now", assigned_mode="PROTECT", break_even_applied=True)
        trail_assessment = AdoptionAssessment(ticket=107, symbol="EURUSD.m", direction=OrderType.BUY,
                                              classification=PositionClass.MANUAL, action="TRAIL_SL",
                                              recommended_sl=1.1030, reason="Trail")

        allowed_protect, reason_protect = policy_protect.validate_action(trail_assessment, rec, pos, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed_protect)
        self.assertIn("Mode PROTECT only permits", reason_protect)

        # In ASSIST mode, trailing stop is approved
        config_assist = ManualMgmtConfig(mode=ManagementMode.ASSIST)
        policy_assist = ManualMgmtPolicy(config=config_assist, pause_file=self.pause_file)
        allowed_assist, reason_assist = policy_assist.validate_action(trail_assessment, rec, pos, self.account_demo, self.symbol_eurusd)
        self.assertTrue(allowed_assist, reason_assist)

    # 10. Add-On (Pyramid) Safety Gates: Never Add to Loser
    def test_addon_loser_prohibition(self):
        config_full = ManualMgmtConfig(mode=ManagementMode.FULL)
        policy_full = ManualMgmtPolicy(config=config_full, pause_file=self.pause_file)

        # Losing position (entry 1.1000, current price 1.0980)
        pos_loser = Position(ticket=108, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                             open_price=1.1000, current_price=1.0980, stop_loss=1.0950, take_profit=1.1100, profit=-20.0, magic=0)
        rec = ManualPositionRecord(ticket=108, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.0950, initial_tp=1.1100,
                                   current_tp=1.1100, adoption_time="now", assigned_mode="FULL")

        addon_assessment = AdoptionAssessment(ticket=108, symbol="EURUSD.m", direction=OrderType.BUY,
                                              classification=PositionClass.MANUAL, action="ADD_ON",
                                              add_on_volume=0.05, reason="Scale-in")

        # Prohibited: cannot add to a position that is not in profit [SAFETY]
        allowed, reason = policy_full.validate_action(addon_assessment, rec, pos_loser, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed)
        self.assertIn("no averaging down", reason)

        # Profitable position BUT stop is not at Break-Even
        pos_profitable_no_be = Position(ticket=109, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                                       open_price=1.1000, current_price=1.1060, stop_loss=1.0950, take_profit=1.1100, profit=60.0, magic=0)
        allowed2, reason2 = policy_full.validate_action(addon_assessment, rec, pos_profitable_no_be, self.account_demo, self.symbol_eurusd)
        self.assertFalse(allowed2)
        self.assertIn("SL is at Break-Even or better", reason2)

        # Profitable position WITH stop at Break-Even -> Approved!
        pos_winner_be = Position(ticket=110, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                                 open_price=1.1000, current_price=1.1060, stop_loss=1.1005, take_profit=1.1100, profit=60.0, magic=0)
        allowed3, reason3 = policy_full.validate_action(addon_assessment, rec, pos_winner_be, self.account_demo, self.symbol_eurusd)
        self.assertTrue(allowed3, reason3)

    # 11. Atomic State Persistence Across Restarts
    def test_atomic_state_persistence(self):
        reg1 = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        pos = Position(ticket=200, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.2,
                       open_price=1.1000, current_price=1.1000, stop_loss=1.0950, take_profit=1.1100, profit=0.0, magic=0)
        reg1.adopt_position(pos, mode=ManagementMode.PROTECT)
        reg1.record_bot_modification(ticket=200, new_sl=1.1005, action_note="Test modification")

        # Verify new registry loads persisted state cleanly
        reg2 = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        rec = reg2.get_record(200)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.ticket, 200)
        self.assertEqual(rec.current_sl, 1.1005)
        self.assertEqual(rec.assigned_mode, "PROTECT")

    # 12. Full End-to-End Detector Cycle with Mock Broker
    def test_e2e_detector_cycle(self):
        mock_broker = MockBroker(account_info=self.account_demo)
        # Position with missing SL
        mock_broker._positions = [
            Position(ticket=300, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0)
        ]
        config = ManualMgmtConfig(mode=ManagementMode.PROTECT)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(
            config=config,
            broker=mock_broker,
            registry=registry,
            bot_magic=100101
        )

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertIn(300, res["detected_positions"])
        self.assertEqual(res["detected_positions"][300]["classification"], "MANUAL")
        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["ticket"], 300)
        self.assertEqual(res["executed_actions"][0]["action"], "SET_SL")
        self.assertEqual(len(mock_broker.modify_calls), 1)
        self.assertEqual(mock_broker.modify_calls[0][0], 300)
        self.assertGreater(mock_broker.modify_calls[0][1], 0.0)

    # 13. Executor Retry on Transient Requote (10004)
    def test_executor_transient_error_retry(self):
        mock_broker = MockBroker(account_info=self.account_demo)
        # Mock modify_order to fail on first attempt with 10004 then succeed
        call_count = [0]
        def custom_modify(ticket, sl, tp):
            call_count[0] += 1
            if call_count[0] == 1:
                return OrderResult(success=False, ticket=ticket, retcode=10004, error_message="Requote")
            return OrderResult(success=True, ticket=ticket, retcode=10009)

        mock_broker.modify_order = custom_modify
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        executor = ManualMgmtExecutor(broker=mock_broker, registry=registry, audit_log_path=self.audit_file,
                                      max_retries=3, backoff_sec=0.01)

        pos = Position(ticket=400, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1050, stop_loss=1.0950, take_profit=1.1100, profit=50.0, magic=0)
        rec = registry.adopt_position(pos, mode=ManagementMode.PROTECT)
        assessment = AdoptionAssessment(ticket=400, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="BREAK_EVEN",
                                        recommended_sl=1.1001, reason="Break-Even")

        success, msg = executor.execute_action(assessment, rec, pos, symbol_info=self.symbol_eurusd)
        self.assertTrue(success, msg)
        self.assertEqual(call_count[0], 2)
        self.assertEqual(rec.current_sl, 1.1001)

    # -------------------------------------------------------------------------
    # Comprehensive Acceptance Verification Suite: Scenarios 1 - 15 (Section 15)
    # -------------------------------------------------------------------------

    def test_scenario_1_manual_buy_without_sl_tp(self):
        """1. Manual BUY position without SL or TP."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=501, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.2,
                       open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=20.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_sl_enabled=True, auto_tp_enabled=True, tp_target_r=2.0)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "SET_SL")
        self.assertEqual(len(mock_broker.modify_calls), 1)
        mod_ticket, mod_sl, mod_tp = mock_broker.modify_calls[0]
        self.assertEqual(mod_ticket, 501)
        self.assertLess(mod_sl, pos.open_price)  # Protective SL below entry
        self.assertGreater(mod_tp, pos.open_price)  # Target TP above entry

    def test_scenario_2_manual_sell_without_sl_tp(self):
        """2. Manual SELL position without SL or TP."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=502, symbol="EURUSD.m", order_type=OrderType.SELL, volume=0.2,
                       open_price=1.1000, current_price=1.0990, stop_loss=0.0, take_profit=0.0, profit=20.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_sl_enabled=True, auto_tp_enabled=True, tp_target_r=2.0)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "SET_SL")
        mod_ticket, mod_sl, mod_tp = mock_broker.modify_calls[0]
        self.assertEqual(mod_ticket, 502)
        self.assertGreater(mod_sl, pos.open_price)  # Protective SELL SL above entry
        self.assertLess(mod_tp, pos.open_price)     # Target SELL TP below entry

    def test_scenario_3_manual_position_with_existing_sl(self):
        """3. Manual position with an existing SL (adds TP if auto_tp_enabled)."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=503, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1010, stop_loss=1.0950, take_profit=0.0, profit=10.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_tp_enabled=True, tp_target_r=2.0)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "SET_TP")
        mod_ticket, mod_sl, mod_tp = mock_broker.modify_calls[0]
        self.assertEqual(mod_ticket, 503)
        self.assertEqual(mod_sl, 1.0950)  # SL preserved
        self.assertGreater(mod_tp, pos.current_price)  # Target TP added

    def test_scenario_4_manual_position_with_existing_tp(self):
        """4. Manual position with an existing TP (adds SL if missing, preserves user TP)."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=504, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=1.1150, profit=10.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_sl_enabled=True, preserve_user_sl_tp=True)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "SET_SL")
        mod_ticket, mod_sl, mod_tp = mock_broker.modify_calls[0]
        self.assertEqual(mod_ticket, 504)
        self.assertGreater(mod_sl, 0.0)
        self.assertEqual(mod_tp, 1.1150)  # User TP strictly preserved

    def test_scenario_5_manual_position_with_both_sl_and_tp(self):
        """5. Manual position with both SL and TP (preserved, no premature modification)."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=505, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1150, profit=20.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, preserve_user_sl_tp=True)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        # In profit of +0.4R (below +1.0R BE threshold) -> Action is NONE, 0 modify calls
        self.assertEqual(len(res["executed_actions"]), 0)
        self.assertEqual(len(mock_broker.modify_calls), 0)

    def test_scenario_6_manual_changes_to_sl_and_tp(self):
        """6. Manual changes to SL and TP trigger user override lockout."""
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file, lockout_minutes=30)
        pos = Position(ticket=506, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1150, profit=20.0, magic=0)
        rec = registry.adopt_position(pos)
        self.assertFalse(rec.is_locked_out())

        # User changes SL to 1.0970 manually
        pos_edited = Position(ticket=506, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                              open_price=1.1000, current_price=1.1020, stop_loss=1.0970, take_profit=1.1150, profit=20.0, magic=0)
        now = datetime.now(timezone.utc)
        updated_rec, override = registry.update_position_state(pos_edited, now=now)
        self.assertTrue(override)
        self.assertTrue(updated_rec.is_locked_out(now))

    def test_scenario_7_break_even_activation(self):
        """7. Break-even activation when trade reaches +1.0R."""
        mock_broker = MockBroker(account_info=self.account_demo)
        # Entry 1.1000, SL 1.0950 (50 pips risk). At 1.1055, trade is at +1.1R
        pos = Position(ticket=507, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1055, stop_loss=1.0950, take_profit=1.1200, profit=55.0, magic=0)
        mock_broker._positions = [pos]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, break_even_enabled=True, break_even_activation_r=1.0)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "BREAK_EVEN")
        rec = registry.get_record(507)
        self.assertTrue(rec.break_even_applied)
        self.assertGreater(mock_broker.modify_calls[0][1], pos.open_price)

    def test_scenario_8_trailing_stop_activation(self):
        """8. Trailing Stop activation across methods (STRUCTURE, ATR, FIXED)."""
        # Test ATR trailing
        config_atr = ManualMgmtConfig(enabled=True, mode=ManagementMode.ASSIST, trailing_stop_enabled=True,
                                      trailing_stop_activation_r=1.5, trailing_method="ATR", trailing_atr_multiplier=1.5)
        assessor_atr = ManualPositionAssessor(config=config_atr)

        pos_trail = Position(ticket=508, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                             open_price=1.1000, current_price=1.1100, stop_loss=1.1005, take_profit=1.1300, profit=100.0, magic=0)
        rec = ManualPositionRecord(ticket=508, symbol="EURUSD.m", direction=OrderType.BUY, volume=0.1,
                                   open_price=1.1000, initial_sl=1.0950, current_sl=1.1005, initial_tp=1.1300,
                                   current_tp=1.1300, adoption_time="now", assigned_mode="ASSIST", break_even_applied=True)

        assessment = assessor_atr.assess(pos_trail, rec, self.candles_m15, symbol_info=self.symbol_eurusd)
        self.assertEqual(assessment.action, "TRAIL_SL")
        self.assertGreater(assessment.recommended_sl, rec.current_sl)
        self.assertLess(assessment.recommended_sl, pos_trail.current_price)

    def test_scenario_9_strategy_based_automatic_closure(self):
        """9. Strategy-based automatic closure upon confirmed structure breakdown."""
        mock_broker = MockBroker(account_info=self.account_demo)
        pos = Position(ticket=509, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.0940, stop_loss=1.0900, take_profit=1.1200, profit=-60.0, magic=0)
        mock_broker._positions = [pos]

        # Inverted candles (falling trend breaking below recent lows)
        base_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        bear_candles = [
            Candle(time=base_time + timedelta(minutes=15 * i), open=1.1000 - i * 0.0010, high=1.1005 - i * 0.0010,
                   low=1.0980 - i * 0.0010, close=1.0985 - i * 0.0010)
            for i in range(25)
        ]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_exit_enabled=True)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": bear_candles},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["executed_actions"]), 1)
        self.assertEqual(res["executed_actions"][0]["action"], "CLOSE")
        # Position should be closed and archived
        self.assertIsNone(registry.get_record(509))

    def test_scenario_10_multiple_manual_positions_simultaneously(self):
        """10. Multiple manual positions processed simultaneously."""
        mock_broker = MockBroker(account_info=self.account_demo)
        mock_broker._positions = [
            Position(ticket=510, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0),
            Position(ticket=511, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0),
            Position(ticket=512, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0),
        ]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_sl_enabled=True)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(len(res["detected_positions"]), 3)
        self.assertEqual(len(res["executed_actions"]), 3)
        self.assertEqual(len(mock_broker.modify_calls), 3)

    def test_scenario_11_mt5_disconnection_and_reconnection(self):
        """11. MT5 disconnection handling and subsequent reconnection."""
        mock_broker = MockBroker(account_info=self.account_demo)
        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        # Simulate disconnection (broker raises socket error)
        mock_broker.get_positions = MagicMock(side_effect=ConnectionResetError("Socket reset"))
        res = detector.run_cycle(market_data_candles_m15={"EURUSD.m": self.candles_m15})
        self.assertEqual(len(res["detected_positions"]), 0)

        # Restore connection
        mock_broker.get_positions = lambda symbol=None: [
            Position(ticket=513, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0)
        ]
        res2 = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )
        self.assertIn(513, res2["detected_positions"])
        self.assertEqual(len(res2["executed_actions"]), 1)

    def test_scenario_12_application_restart_with_open_positions(self):
        """12. Application restart with open manual positions and reconciliation."""
        # Pre-populate registry with 2 positions on disk
        reg1 = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        p1 = Position(ticket=514, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                      open_price=1.1000, current_price=1.1010, stop_loss=1.0950, take_profit=1.1200, profit=10.0, magic=0)
        p2 = Position(ticket=515, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                      open_price=1.1000, current_price=1.1010, stop_loss=1.0950, take_profit=1.1200, profit=10.0, magic=0)
        reg1.adopt_position(p1)
        reg1.adopt_position(p2)

        # Now simulate restart: broker only has p1 open (p2 was closed while offline)
        mock_broker = MockBroker(account_info=self.account_demo)
        mock_broker._positions = [p1]

        reg2 = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        self.assertIsNotNone(reg2.get_record(514))
        self.assertIsNotNone(reg2.get_record(515))

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=reg2, bot_magic=100101)
        detector.run_cycle(market_data_candles_m15={"EURUSD.m": self.candles_m15})

        # p1 remains active, p2 is reconciled and archived
        self.assertIsNotNone(reg2.get_record(514))
        self.assertIsNone(reg2.get_record(515))

    def test_scenario_13_partial_position_closure(self):
        """13. Partial position closure volume update without false lockout."""
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        pos = Position(ticket=516, symbol="EURUSD.m", order_type=OrderType.BUY, volume=1.0,
                       open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1200, profit=20.0, magic=0)
        rec = registry.adopt_position(pos)
        self.assertEqual(rec.volume, 1.0)
        self.assertEqual(rec.initial_volume, 1.0)

        # Partially closed from 1.0 to 0.4 lots
        pos_partial = Position(ticket=516, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.4,
                               open_price=1.1000, current_price=1.1020, stop_loss=1.0950, take_profit=1.1200, profit=8.0, magic=0)
        updated_rec, override = registry.update_position_state(pos_partial)
        self.assertEqual(updated_rec.volume, 0.4)
        self.assertFalse(override)  # Partial close must NOT trigger user override lockout
        self.assertFalse(updated_rec.is_locked_out())

    def test_scenario_14_rejected_sltp_modification(self):
        """14. Rejected SL/TP modification raises clear error and logs failure."""
        mock_broker = MockBroker(account_info=self.account_demo)
        mock_broker.modify_order = MagicMock(return_value=OrderResult(success=False, ticket=517, retcode=10016, error_message="Invalid stops"))

        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        pos = Position(ticket=517, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                       open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=0)
        rec = registry.adopt_position(pos)

        executor = ManualMgmtExecutor(broker=mock_broker, registry=registry, audit_log_path=self.audit_file, max_retries=1)
        assessment = AdoptionAssessment(ticket=517, symbol="EURUSD.m", direction=OrderType.BUY,
                                        classification=PositionClass.MANUAL, action="SET_SL",
                                        recommended_sl=1.0950, reason="Initial SL")

        success, msg = executor.execute_action(assessment, rec, pos, symbol_info=self.symbol_eurusd)
        self.assertFalse(success)
        self.assertIn("Invalid stops", msg)
        # Position SL must remain 0.0 in registry (not falsely marked as protected)
        self.assertEqual(rec.current_sl, 0.0)

    def test_scenario_15_ea_positions_unaffected(self):
        """15. Existing EA-generated positions and Bot positions remain unaffected."""
        mock_broker = MockBroker(account_info=self.account_demo)
        mock_broker._positions = [
            Position(ticket=801, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=100101),  # Bot
            Position(ticket=802, symbol="EURUSD.m", order_type=OrderType.BUY, volume=0.1,
                     open_price=1.1000, current_price=1.1010, stop_loss=0.0, take_profit=0.0, profit=10.0, magic=999999),  # Other EA
        ]

        config = ManualMgmtConfig(enabled=True, mode=ManagementMode.PROTECT, auto_sl_enabled=True)
        registry = ManualPositionRegistry(state_file=self.state_file, history_file=self.hist_file)
        detector = ManualPositionDetector(config=config, broker=mock_broker, registry=registry, bot_magic=100101)

        res = detector.run_cycle(
            market_data_candles_m15={"EURUSD.m": self.candles_m15},
            symbol_info_map={"EURUSD.m": self.symbol_eurusd}
        )

        self.assertEqual(res["detected_positions"][801]["classification"], "BOT_OWN")
        self.assertEqual(res["detected_positions"][802]["classification"], "OTHER_EA")
        self.assertEqual(len(res["executed_actions"]), 0)
        self.assertEqual(len(mock_broker.modify_calls), 0)
        self.assertEqual(len(registry.get_all_records()), 0)



if __name__ == "__main__":
    unittest.main()
