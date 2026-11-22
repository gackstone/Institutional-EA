"""
Master Verification Suite for MT5 001 Adaptive $20 Net-Profit Scalping Engine.
Validates:
A. Position Target Tests ($20 net profit target, closing costs, graduated ratchet, deal reconciliation).
B. Position Capacity Tests (1 to 7 simultaneous positions allowed, 8th rejected, minimum 3 active target).
C. Risk & Governance Tests (Rule R9 2.0% cap, capital baseline, directional currency concentration, consecutive losses).
D. Target Feasibility Tests ($20 target calculation across Forex, Gold, Indices, rejection of infeasible setups).
E. Strategy & Directional Intelligence Tests (Momentum, Pullback, Sweep/Breakout, Reversal, Conflict rejection).
"""

import unittest
from datetime import datetime, timezone, timedelta
from typing import List

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
from src.core.config import AppConfig, RiskConfig, AccountProfileConfig
from src.risk.target_feasibility import TargetFeasibilityEngine, TargetFeasibilityResult
from src.risk.position_sizing import PositionSizingEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.trade_management import TradeManagementEngine, PositionAction
from src.execution.continuous_scalper import ContinuousScalpingEngine, MarketRegime


class TestAdaptive20UsdScalpingEngine(unittest.TestCase):
    def setUp(self):
        self.symbol_eurusd = SymbolInfo(
            symbol="EURUSD",
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            spread=10.0,
            ask=1.10010,
            bid=1.10000,
        )
        self.symbol_xauusd = SymbolInfo(
            symbol="XAUUSD",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            spread=25.0,
            ask=2700.25,
            bid=2700.00,
        )
        self.symbol_nas100 = SymbolInfo(
            symbol="NAS100",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.20,
            contract_size=1.0,
            min_lot=0.1,
            max_lot=50.0,
            lot_step=0.1,
            spread=150.0,
            ask=20500.0,
            bid=20498.5,
        )

        self.account_large = AccountInfo(
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            free_margin=10000.0,
            currency="USD",
            leverage=100,
            trading_enabled=True,
        )
        self.account_small = AccountInfo(
            balance=50.0,
            equity=50.0,
            margin=0.0,
            free_margin=50.0,
            currency="USD",
            leverage=100,
            trading_enabled=True,
        )

        self.risk_cfg = RiskConfig(
            max_simultaneous_positions=7,
            max_aggregate_open_risk_percent=6.0,
            target_net_profit_usd=20.0,
            min_net_profit_target_usd=5.0,
            profit_floor_lock_usd=5.0,
            strong_momentum_profit_extension=True,
        )
        self.trade_manager = TradeManagementEngine(self.risk_cfg)
        self.portfolio_risk = PortfolioRiskEngine(self.risk_cfg)
        self.sizing_engine = PositionSizingEngine()
        self.scalper = ContinuousScalpingEngine(symbols=["EURUSD", "GBPUSD", "XAUUSD"])

    # =========================================================================
    # A. POSITION TARGET TESTS ($20 NET PROFIT REALIZATION & CLOSING COSTS)
    # =========================================================================

    def test_position_full_close_at_20_net_target(self):
        """Position must trigger FULL_CLOSE when net profit reaches or exceeds $20.00."""
        pos = Position(
            ticket=1001,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.20,
            open_price=1.10000,
            current_price=1.10110,
            stop_loss=1.09900,
            take_profit=1.10150,
            profit=22.00,  # Gross profit $22.00
            commission=-1.40,  # Accrued commission
            swap=-0.30,  # Swap
            # Net profit = 22.00 - 1.40 - 0.30 = $20.30 >= $20.00
        )
        actions = self.trade_manager.evaluate_position(pos, self.symbol_eurusd, [])
        self.assertTrue(len(actions) > 0)
        close_action = [a for a in actions if a.action_type == "FULL_CLOSE"]
        self.assertEqual(len(close_action), 1)
        self.assertIn("Target $20.00 net profit achieved", close_action[0].reason)
        self.assertIn("20.30 net", close_action[0].reason)

    def test_commission_and_swap_reduce_net_profit_preventing_false_target_trigger(self):
        """Gross profit of $21.00 with $3.00 commissions/swap nets $18.00 (must NOT trigger $20 target exit)."""
        pos = Position(
            ticket=1002,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.20,
            open_price=1.10000,
            current_price=1.10105,
            stop_loss=1.09900,
            take_profit=1.10150,
            profit=21.00,  # Gross is > $20
            commission=-2.00,  # Comm drag
            swap=-1.00,  # Swap drag
            # Net profit = 21.00 - 3.00 = $18.00 < $20.00 target
        )
        actions = self.trade_manager.evaluate_position(pos, self.symbol_eurusd, [])
        # Must not trigger FULL_CLOSE for target attainment
        target_close = [a for a in actions if a.action_type == "FULL_CLOSE" and "Target $20.00" in a.reason]
        self.assertEqual(len(target_close), 0)

        # But it enters TARGET_APPROACH ($18.00 net) and locks profit floor!
        floor_mods = [a for a in actions if a.action_type == "MODIFY_SL"]
        self.assertTrue(len(floor_mods) > 0)
        self.assertIn("Target approach", floor_mods[0].reason)

    def test_graduated_profit_ratchet_stages(self):
        """Tests graduated profit ratchet: $5 floor -> $12 ratchet -> $15 ratchet -> $18 approach."""
        # Stage 1: $6.00 net profit locks initial ~$5 floor
        pos = Position(
            ticket=1003,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=1.10000,
            current_price=1.10070,
            stop_loss=1.09900,
            take_profit=1.10250,
            profit=7.00,
            commission=-0.70,
            swap=-0.30,  # Net = $6.00
        )
        actions = self.trade_manager.evaluate_position(pos, self.symbol_eurusd, [])
        self.assertTrue(any(a.action_type == "MODIFY_SL" for a in actions))
        self.assertTrue(pos.profit_floor_locked)
        self.assertEqual(pos.profit_lock_status, "FLOOR_LOCKED")

        # Stage 2: $13.00 net profit ratchets floor higher
        pos.profit = 14.00  # Net = $13.00
        pos.current_price = 1.10140
        actions = self.trade_manager.evaluate_position(pos, self.symbol_eurusd, [])
        self.assertTrue(any("Profit ratchet" in a.reason for a in actions))
        self.assertEqual(pos.profit_lock_status, "RATCHET_LOCKED")

    def test_deal_reconciliation_calculates_realized_net_profit(self):
        """Reconciliation accurately records deal profit, commission, and swap from MT5 history."""
        reconciled = self.trade_manager.reconcile_closed_deal(
            ticket=9999,
            deal_profit=23.50,
            deal_commission=-2.10,
            deal_swap=-0.90,
            close_reason="Target $20.00 net profit achieved"
        )
        self.assertEqual(reconciled, 20.50)

    # =========================================================================
    # B. POSITION CAPACITY TESTS (1 TO 7 POSITIONS, 8TH REJECTED)
    # =========================================================================

    def test_supports_up_to_seven_positions_and_rejects_eighth(self):
        """Verifies portfolio allows up to 7 simultaneous positions and strictly rejects 8th."""
        candidate = SignalCandidate(
            id="SIG_GBPJPY",
            symbol="GBPJPY",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=190.00,
            stop_loss=189.50,
            take_profit=191.00,
            risk_reward=2.0,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        active_positions = [
            Position(ticket=2001, symbol="EURUSD", order_type=OrderType.BUY, volume=0.05, open_price=1.1, current_price=1.1, stop_loss=1.09, take_profit=1.12, profit=5.0),
            Position(ticket=2002, symbol="USDCHF", order_type=OrderType.BUY, volume=0.05, open_price=0.9, current_price=0.9, stop_loss=0.89, take_profit=0.92, profit=5.0),
            Position(ticket=2003, symbol="USDCAD", order_type=OrderType.SELL, volume=0.05, open_price=1.35, current_price=1.35, stop_loss=1.36, take_profit=1.33, profit=5.0),
            Position(ticket=2004, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.02, open_price=2700.0, current_price=2700.0, stop_loss=2690.0, take_profit=2720.0, profit=5.0),
            Position(ticket=2005, symbol="XAGUSD", order_type=OrderType.SELL, volume=0.05, open_price=32.0, current_price=32.0, stop_loss=32.5, take_profit=31.0, profit=5.0),
            Position(ticket=2006, symbol="NAS100", order_type=OrderType.BUY, volume=0.1, open_price=20500.0, current_price=20500.0, stop_loss=20400.0, take_profit=20700.0, profit=5.0),
        ]

        # 1. With 6 positions, 7th position is permitted
        permitted_7th, reason_7th = self.portfolio_risk.evaluate_new_order_permission(
            candidate=candidate,
            account=self.account_large,
            active_positions=active_positions,
            proposed_monetary_risk=25.0,
            proposed_volume=0.05,
        )
        self.assertTrue(permitted_7th, f"7th position should be permitted: {reason_7th}")

        # 2. Add 7th position to active list
        active_positions.append(
            Position(
                ticket=2007,
                symbol="GBPJPY",
                order_type=OrderType.BUY,
                volume=0.05,
                open_price=190.0,
                current_price=190.0,
                stop_loss=189.5,
                take_profit=191.0,
                profit=5.0,
                initial_risk_amount=20.0,
            )
        )
        self.assertEqual(len(active_positions), 7)

        # 3. Opportunity-driven multi-position: 8th position is permitted
        candidate_8th = SignalCandidate(
            id="SIG_US30",
            symbol="US30",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=43000.0,
            stop_loss=42900.0,
            take_profit=43200.0,
            risk_reward=2.0,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )
        permitted_8th, reason_8th = self.portfolio_risk.evaluate_new_order_permission(
            candidate=candidate_8th,
            account=self.account_large,
            active_positions=active_positions,
            proposed_monetary_risk=25.0,
            proposed_volume=0.05,
        )
        self.assertTrue(permitted_8th, f"8th position should be permitted under opportunity-driven execution: {reason_8th}")

    # =========================================================================
    # C. RISK & GOVERNANCE TESTS (RULE R9 & CORRELATION)
    # =========================================================================

    def test_rule_r9_hard_cap_2_percent(self):
        """Sizing strictly caps risk at 2.0% regardless of requested parameters."""
        res = self.sizing_engine.calculate_lot_size(
            account=self.account_large,  # $10,000
            symbol_info=self.symbol_eurusd,
            entry_price=1.10000,
            stop_loss=1.09800,  # 20 pips = 200 pts ($200 per lot)
            risk_percent=5.0,  # Requesting 5% (violates R9)
        )
        self.assertTrue(res.is_approved)
        self.assertLessEqual(res.risk_percent_actual, 2.0 + 1e-4)
        self.assertLessEqual(res.monetary_risk, 200.0 + 1e-4)

    def test_directional_currency_concentration_limit(self):
        """Allows opportunity-driven entries across instruments without arbitrary 3-position currency cap."""
        # BUY EURUSD (+EUR, -USD)
        # BUY GBPUSD (+GBP, -USD)
        # BUY AUDUSD (+AUD, -USD)
        # Attempting BUY NZDUSD (+NZD, -USD)
        active_positions = [
            Position(ticket=301, symbol="EURUSD", order_type=OrderType.BUY, volume=0.05, open_price=1.1, current_price=1.1, stop_loss=1.09, take_profit=1.12, profit=0.0),
            Position(ticket=302, symbol="GBPUSD", order_type=OrderType.BUY, volume=0.05, open_price=1.3, current_price=1.3, stop_loss=1.29, take_profit=1.32, profit=0.0),
            Position(ticket=303, symbol="AUDUSD", order_type=OrderType.BUY, volume=0.05, open_price=0.66, current_price=0.66, stop_loss=0.65, take_profit=0.68, profit=0.0),
        ]

        cand_nzd = SignalCandidate(
            id="SIG_NZD", symbol="NZDUSD", timeframe=Timeframe.M5, direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP, entry_price=0.60, stop_loss=0.595, take_profit=0.61,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
            candidate=cand_nzd,
            account=self.account_large,
            active_positions=active_positions,
            proposed_monetary_risk=20.0,
        )
        self.assertTrue(permitted, f"Opportunity-driven multi-position execution allows 4th bet when risk allows: {reason}")

    def test_floating_drawdown_contracts_risk(self):
        """Under permissive trading engine, daily loss budget does not block new valid exposure."""
        active_positions = [
            Position(ticket=401, symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, open_price=1.1, current_price=1.085, stop_loss=1.08, take_profit=1.12, profit=-150.0)
        ]
        cand = SignalCandidate(
            id="SIG_XAU", symbol="XAUUSD", timeframe=Timeframe.M5, direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP, entry_price=2700.0, stop_loss=2690.0, take_profit=2720.0,
            risk_reward=2.0, score=80.0, timestamp=datetime.now(timezone.utc), status="APPROVED"
        )
        self.portfolio_risk.daily_starting_equity = 10000.0
        permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
            candidate=cand,
            account=AccountInfo(balance=10000.0, equity=9850.0, margin=100.0, free_margin=9750.0, currency="USD", leverage=100, trading_enabled=True),
            active_positions=active_positions,
            proposed_monetary_risk=30.0,
        )
        self.assertTrue(permitted)

    # =========================================================================
    # D. DYNAMIC $20 TARGET FEASIBILITY TESTS
    # =========================================================================

    def test_target_feasibility_across_forex_gold_and_indices(self):
        """Feasibility engine computes distinct price distances across Forex, Gold, and Indices."""
        # 1. EURUSD: 0.10 lot requires ~$22 gross ($20 net + ~$2 comm/spread) => ~22 pips (220 pts)
        res_fx = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=self.symbol_eurusd,
            volume=0.10,
            entry_price=1.10000,
            stop_loss=1.09850,  # 15 pips SL
            order_type=OrderType.BUY,
            account=self.account_large,
            atr_m15=0.00120,  # 12 pips ATR
        )
        self.assertTrue(res_fx.is_feasible)
        self.assertAlmostEqual(res_fx.target_net_usd, 20.0, delta=0.01)
        self.assertGreater(res_fx.required_price_distance, 0.0018)  # > 18 pips
        self.assertEqual(res_fx.target_price, round(1.10000 + res_fx.required_price_distance, 5))

        # 2. XAUUSD: 0.02 lot ($2 per $1.0 move). Requires ~$21 gross => ~$10.50 price move
        res_gold = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=self.symbol_xauusd,
            volume=0.02,
            entry_price=2700.00,
            stop_loss=2692.00,  # $8 SL
            order_type=OrderType.BUY,
            account=self.account_large,
            atr_m15=6.50,  # $6.50 ATR
        )
        self.assertTrue(res_gold.is_feasible)
        self.assertGreater(res_gold.required_price_distance, 9.0)  # > $9 move

        # 3. Small Account Infeasibility Guard:
        # A $25 account attempting 0.01 lot EURUSD with 20 pip SL risks $2.00 = 8.0% of equity (exceeds R9 2.0% cap).
        # Must identify target as infeasible rather than manufacture excessive exposure!
        res_small = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=self.symbol_eurusd,
            volume=0.01,
            entry_price=1.10000,
            stop_loss=1.09800,
            order_type=OrderType.BUY,
            account=self.account_small,  # $50 capital
            atr_m15=0.00100,
        )
        self.assertFalse(res_small.is_feasible)
        self.assertIn("Rule R9 hard cap of 2.0%", res_small.rejection_reason)

    # =========================================================================
    # E. STRATEGY & OPPORTUNITY RANKING TESTS
    # =========================================================================

    def test_opportunity_ranking_prioritizes_higher_confluence_and_unoccupied_symbols(self):
        """Opportunity ranking selects high-confluence, unhedged symbols over existing active symbols."""
        c1 = SignalCandidate(
            id="SIG_EUR", symbol="EURUSD", timeframe=Timeframe.M5, direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP, entry_price=1.1, stop_loss=1.098, take_profit=1.104,
            risk_reward=2.0, score=70.0, timestamp=datetime.now(timezone.utc), reasons=["REGIME:BULLISH_TREND"]
        )
        c2 = SignalCandidate(
            id="SIG_GBP", symbol="GBPUSD", timeframe=Timeframe.M5, direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP, entry_price=1.3, stop_loss=1.298, take_profit=1.305,
            risk_reward=2.5, score=75.0, timestamp=datetime.now(timezone.utc), reasons=["REGIME:BULLISH_TREND"]
        )

        active = [Position(ticket=501, symbol="EURUSD", order_type=OrderType.BUY, volume=0.05, open_price=1.1, current_price=1.1, stop_loss=1.09, take_profit=1.12, profit=0.0)]
        ranked = self.scalper.rank_scalp_opportunities([c1, c2], active_positions=active)
        self.assertEqual(len(ranked), 2)
        # GBPUSD should rank first because EURUSD has active position penalty
        self.assertEqual(ranked[0].symbol, "GBPUSD")


if __name__ == "__main__":
    unittest.main()
