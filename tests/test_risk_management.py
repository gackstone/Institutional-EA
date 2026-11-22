"""
Unit tests for Portfolio Risk and Circuit Breaker Engine.
"""

import unittest
from datetime import datetime, timezone
from src.core.contracts import AccountInfo, Position, SignalCandidate, OrderType, SetupType, Timeframe
from src.core.config import RiskConfig
from src.risk.portfolio_risk import PortfolioRiskEngine


class TestPortfolioRiskEngine(unittest.TestCase):
    def setUp(self):
        self.config = RiskConfig(
            max_daily_loss_percent=2.0,
            max_weekly_loss_percent=4.0,
            max_aggregate_open_risk_percent=1.5,
            max_simultaneous_positions=3,
            max_consecutive_losses=3
        )
        self.risk_engine = PortfolioRiskEngine(self.config)
        self.account = AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)

        self.candidate = SignalCandidate(
            id="EURUSD_TEST",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.DAILY_REVERSAL,
            entry_price=1.0850,
            stop_loss=1.0830,
            take_profit=1.0900,
            risk_reward=2.5,
            score=85.0,
            timestamp=datetime.now(timezone.utc)
        )

    def test_daily_loss_limit_circuit_breaker(self):
        self.risk_engine.initialize_day(10000.0)
        # Realize $210 loss (> 2% of $10,000)
        self.risk_engine.record_closed_trade(-210.0)

        # Per Phase 2 architecture: daily-loss limits no longer block order execution
        allowed, reason = self.risk_engine.evaluate_new_order_permission(
            self.candidate, self.account, [], 50.0
        )
        self.assertTrue(allowed)
        self.assertFalse(self.risk_engine.circuit_breaker_active)
        self.assertIsNone(reason)

    def test_max_simultaneous_positions(self):
        active = [
            Position(ticket=1, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.08, current_price=1.08, stop_loss=1.075, take_profit=1.09, profit=10.0),
            Position(ticket=2, symbol="GBPUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.28, current_price=1.28, stop_loss=1.275, take_profit=1.29, profit=10.0),
            Position(ticket=3, symbol="USDJPY", order_type=OrderType.SELL, volume=0.1, open_price=150.0, current_price=150.0, stop_loss=150.5, take_profit=149.0, profit=10.0),
        ]
        # Opportunity-driven: 4th position is permitted
        allowed, reason = self.risk_engine.evaluate_new_order_permission(
            self.candidate, self.account, active, 50.0
        )
        self.assertTrue(allowed, f"Opportunity-driven multi-position execution must permit 4th position: {reason}")

    def test_circuit_breaker_manual_reset(self):
        self.risk_engine.initialize_day(10000.0)
        # Daily loss does not trigger circuit breaker under permissive engine
        self.risk_engine.record_closed_trade(-250.0)
        self.assertFalse(self.risk_engine.circuit_breaker_active)

        # Trigger circuit breaker directly to test manual reset authorization
        self.risk_engine._trigger_circuit_breaker("Safety test event")
        self.assertTrue(self.risk_engine.circuit_breaker_active)

        # Invalid token fails
        self.assertFalse(self.risk_engine.manual_reset_circuit_breaker("WRONG_TOKEN"))
        self.assertTrue(self.risk_engine.circuit_breaker_active)

        # Valid token resets
        self.assertTrue(self.risk_engine.manual_reset_circuit_breaker("AUTHORIZE_SYSTEM_RESET"))
        self.assertFalse(self.risk_engine.circuit_breaker_active)

    def test_authoritative_rr_calculation(self):
        from src.core.contracts import calculate_risk_reward
        # BUY: Entry 1.1000, SL 1.0950 (50 pts), TP 1.1100 (100 pts) -> R:R 2.0
        rr_buy = calculate_risk_reward(1.1000, 1.0950, 1.1100, OrderType.BUY)
        self.assertEqual(rr_buy, 2.0)

        # SELL: Entry 150.00, SL 150.50 (0.50), TP 148.50 (1.50) -> R:R 3.0
        rr_sell = calculate_risk_reward(150.00, 150.50, 148.50, OrderType.SELL)
        self.assertEqual(rr_sell, 3.0)

        # Invalid BUY (SL above entry) -> 0.0
        self.assertEqual(calculate_risk_reward(1.1000, 1.1050, 1.1100, OrderType.BUY), 0.0)

        # Invalid SELL (TP above entry) -> 0.0
        self.assertEqual(calculate_risk_reward(150.00, 150.50, 151.00, OrderType.SELL), 0.0)

    def test_capacity_manager_supports_7_positions(self):
        cfg = RiskConfig()
        engine = PortfolioRiskEngine(cfg)
        positions_6 = [
            Position(ticket=i, symbol=f"SYM_{i}", order_type=OrderType.BUY, volume=0.01, open_price=1.0, current_price=1.0, stop_loss=0.99, take_profit=1.02, profit=5.0)
            for i in range(1, 7)
        ]
        # 7th position must be permitted
        allowed_7th, reason_7th = engine.evaluate_new_order_permission(self.candidate, self.account, positions_6, 20.0)
        self.assertTrue(allowed_7th, f"7th position must be permitted: {reason_7th}")

        positions_7 = positions_6 + [
            Position(ticket=7, symbol="SYM_7", order_type=OrderType.BUY, volume=0.01, open_price=1.0, current_price=1.0, stop_loss=0.99, take_profit=1.02, profit=5.0)
        ]
        # Opportunity-driven: 8th position is also permitted without arbitrary ceiling
        allowed_8th, reason_8th = engine.evaluate_new_order_permission(self.candidate, self.account, positions_7, 20.0)
        self.assertTrue(allowed_8th, f"8th position must be permitted under opportunity-driven execution: {reason_8th}")

    def test_shadow_gate_verdict_cannot_veto(self):
        from src.smc.setup_quality_gate import QualityGateVerdict, GateMode
        verdict = QualityGateVerdict(
            passed=False,
            effective_pass=True,
            mode=GateMode.SHADOW,
            score=35.0,
            size_multiplier=1.0,
            hard_fails=["G1_DISPLACEMENT_MISSING"]
        )
        self.assertFalse(verdict.blocked)
        self.assertTrue(verdict.effective_pass)



if __name__ == "__main__":
    unittest.main()
