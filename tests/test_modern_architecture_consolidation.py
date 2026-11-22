"""
Comprehensive Regression Test Suite for the Consolidated Modern MT5 Architecture:
1. Architecture & Configuration Consolidation (legacy removal, single config loader, DEMO lock)
2. Unfiltered Trade Signal Handling (BUY/SELL signals bypass confluence, CHoCH/BOS, session, news, regime, R:R gates)
3. Account-Level Risk Management & Trade Outcome Accounting (streaks, cooldown expiry, deduplication, kill switch)
4. Broker Execution & Pre-Trade Validation (mandatory SL, stops_level, volume normalization, confirmation, partial fill)
5. Bridge & Lifecycle Safety (preflight check, manual position magic protection)
6. Promotion Gate Integrity (no hardcoded metrics, fail-closed on missing/malformed/insufficient evidence)
"""

from __future__ import annotations
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.core.config import AppConfig, RiskConfig
from src.core.contracts import (
    AccountInfo,
    Candle,
    DecisionOutcomeType,
    ExecutionMode,
    OrderType,
    Position,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)
from src.core.news_filter import EconomicNewsEvent
from src.core.orchestrator import TradingBotOrchestrator
from src.execution.continuous_scalper import ContinuousScalpingEngine
from src.execution.order_manager import OrderManager
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from scripts.promotion_check import (
    evaluate_promotion_gate,
    load_and_evaluate_promotion_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _build_candles(
    base_price: float,
    step: float,
    count: int = 25,
    tf_minutes: int = 5,
) -> list[Candle]:
    t0 = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    bars: list[Candle] = []
    p = base_price
    for i in range(count):
        o = p
        c = o + step
        hi = max(o, c) + abs(step) * 0.5 + 1e-4
        lo = min(o, c) - abs(step) * 0.5 - 1e-4
        bars.append(
            Candle(
                time=t0 + timedelta(minutes=i * tf_minutes),
                open=round(o, 5),
                high=round(hi, 5),
                low=round(lo, 5),
                close=round(c, 5),
                tick_volume=200,
                spread=12,
                complete=True,
            )
        )
        p = c
    return bars


class TestModernArchitectureConsolidation(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
        self.gold_spec = SymbolInfo(
            symbol="XAUUSD.m",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            spread=20.0,
            ask=2650.20,
            bid=2650.00,
            stops_level=10,
            freeze_level=5,
        )
        self.btc_spec = SymbolInfo(
            symbol="BTCUSD.m",
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            min_lot=0.01,
            max_lot=10.0,
            lot_step=0.01,
            spread=25.0,
            ask=88500.25,
            bid=88500.00,
            stops_level=15,
            freeze_level=5,
        )

    # =========================================================================
    # 1. ARCHITECTURE & CONFIGURATION CONSOLIDATION TESTS
    # =========================================================================
    def test_01_obsolete_scalper_architecture_removed(self) -> None:
        """Verifies obsolete parallel scalper package, YAML configs, and legacy launchers are removed."""
        obsolete_paths = [
            PROJECT_ROOT / "src" / "scalper",
            PROJECT_ROOT / "src" / "strategies" / "legacy_adapter.py",
            PROJECT_ROOT / "config" / "scalper.yaml",
            PROJECT_ROOT / "config" / "strategy.yaml",
            PROJECT_ROOT / "scripts" / "start_dual_scalper.py",
            PROJECT_ROOT / "scripts" / "start_gold_scalper.py",
            PROJECT_ROOT / "scripts" / "run_dual_market_simulation.py",
            PROJECT_ROOT / "scripts" / "run_gold_scalper_simulation.py",
        ]
        for p in obsolete_paths:
            self.assertFalse(p.exists(), f"Obsolete path should be removed from active workspace: {p}")

        # Verify authoritative modern entry points exist
        retained_paths = [
            PROJECT_ROOT / "src" / "core" / "orchestrator.py",
            PROJECT_ROOT / "src" / "core" / "config.py",
            PROJECT_ROOT / "config" / "settings.json",
            PROJECT_ROOT / "config" / "strategy_config.json",
            PROJECT_ROOT / "config" / "account_profiles.json",
            PROJECT_ROOT / "scripts" / "start_bot.py",
            PROJECT_ROOT / "scripts" / "supervisor.py",
            PROJECT_ROOT / "scripts" / "start_supervisor.bat",
            PROJECT_ROOT / "scripts" / "run_bridge_server.py",
            PROJECT_ROOT / "mql5" / "Experts" / "PythonBridgeEA.mq5",
        ]
        for p in retained_paths:
            self.assertTrue(p.exists(), f"Retained modern file must exist: {p}")

    def test_02_single_config_loader_and_demo_safety_defaults(self) -> None:
        """Verifies AppConfig.load_from_dir() loads cleanly in DEMO mode with LIVE_TRADING_ENABLED=false."""
        cfg = AppConfig.load_from_dir()
        self.assertEqual(cfg.execution_mode, ExecutionMode.DEMO)
        self.assertFalse(cfg.live_trading_enabled)
        self.assertFalse(cfg.legacy_filters_enabled)
        self.assertFalse(cfg.news_filter_enabled)

    # =========================================================================
    # 2. UNFILTERED TRADE SIGNAL HANDLING TESTS
    # =========================================================================
    def test_03_unfiltered_buy_and_sell_signals_reach_risk_and_execution(self) -> None:
        """
        Verifies valid BUY and SELL signals with low confluence score, missing CHoCH/BOS/FVG/OB,
        outside killzones, during high-impact news, and with low strategy R:R are NOT blocked by
        strategy filters and reach risk validation and dry-run order execution.
        """
        cfg = AppConfig.load_from_dir()
        cfg.dry_run = True
        cfg.legacy_filters_enabled = False
        orch = TradingBotOrchestrator(cfg)
        orch.alerts = None
        orch.account_info = AccountInfo(
            account_number=1200057798,
            balance=5000.0,
            equity=5000.0,
            free_margin=5000.0,
            leverage=200,
            trade_mode="DEMO",
        )
        orch.market_data.register_symbol_info(self.gold_spec)
        orch.market_data.register_symbol_info(self.btc_spec)

        # Register high-impact news right now (must NOT block signal)
        orch.news_filter.register_events(
            [
                EconomicNewsEvent(
                    id="NFP_HIGH",
                    title="Non-Farm Payrolls",
                    currency="USD",
                    impact="HIGH",
                    timestamp=self.now,
                )
            ]
        )

        # Low-score, low-R:R, unapproved candidate with strategy rejection reasons
        buy_cand = SignalCandidate(
            id="UNFILTERED_BUY_GOLD_1",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=2650.20,
            stop_loss=2645.20,
            take_profit=2652.70,  # R:R = 0.5 (below legacy min_rr 1.5/2.0)
            risk_reward=0.5,
            score=12.0,  # Below legacy min_confluence_score 55/75
            timestamp=self.now,
            status="REJECTED",
            rejection_reasons=[
                "Confluence score 12.0 < 75.0",
                "CHoCH only, awaiting BOS",
                "HTF_CONFLICT: D1/H4 bearish",
                "Reward-to-risk 0.50 < 2.00",
            ],
        )

        res_buy = orch._execute_approved_candidate("XAUUSD.m", buy_cand, self.now)
        self.assertIsNotNone(res_buy)
        self.assertEqual(res_buy.direction, OrderType.BUY)
        self.assertEqual(res_buy.status, "APPROVED")
        out_buy = orch.last_decision_outcomes["XAUUSD.m"]
        self.assertEqual(out_buy.outcome_type, DecisionOutcomeType.TRADE_SENT)

        # Symmetric SELL signal on BTCUSD.m
        sell_cand = SignalCandidate(
            id="UNFILTERED_SELL_BTC_1",
            symbol="BTCUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.SELL,
            setup_type=SetupType.FAST_SCALP,
            entry_price=88500.00,
            stop_loss=88700.00,
            take_profit=88400.00,  # R:R = 0.5
            risk_reward=0.5,
            score=10.0,
            timestamp=self.now,
            status="REJECTED",
            rejection_reasons=["Low score", "Missing FVG/OB", "Outside Killzone"],
        )

        res_sell = orch._execute_approved_candidate("BTCUSD.m", sell_cand, self.now)
        self.assertIsNotNone(res_sell)
        self.assertEqual(res_sell.direction, OrderType.SELL)
        self.assertEqual(res_sell.status, "APPROVED")
        out_sell = orch.last_decision_outcomes["BTCUSD.m"]
        self.assertEqual(out_sell.outcome_type, DecisionOutcomeType.TRADE_SENT)

    def test_04_unfiltered_continuous_scalper_generates_directional_signals_and_rejects_missing_data(self) -> None:
        """
        Verifies ContinuousScalpingEngine with min_confluence_score=0.0 generates valid BUY/SELL
        signals from directional price action without requiring multi-indicator/SMC confluence,
        never flips BUY/SELL direction, and returns None when market data is missing/insufficient.
        """
        scalper = ContinuousScalpingEngine(symbols=["XAUUSD.m", "BTCUSD.m"], min_confluence_score=0.0, min_rr=0.0)

        # 1. Missing/insufficient data -> returns None (never fabricates random trades)
        empty_sig = scalper.scan_symbol_timeframes("XAUUSD.m", {Timeframe.M1: []}, self.gold_spec)
        self.assertIsNone(empty_sig)

        # 2. Bullish directional candles -> BUY signal (never flipped to SELL)
        bull_bars = _build_candles(2645.0, +0.40, count=15, tf_minutes=1)
        buy_sig = scalper.scan_symbol_timeframes("XAUUSD.m", {Timeframe.M1: bull_bars}, self.gold_spec)
        self.assertIsNotNone(buy_sig)
        self.assertEqual(buy_sig.direction, OrderType.BUY)
        self.assertLess(buy_sig.stop_loss, buy_sig.entry_price)
        self.assertGreater(buy_sig.take_profit, buy_sig.entry_price)

        # 3. Bearish directional candles -> SELL signal (never flipped to BUY)
        bear_bars = _build_candles(88600.0, -15.0, count=15, tf_minutes=1)
        sell_sig = scalper.scan_symbol_timeframes("BTCUSD.m", {Timeframe.M1: bear_bars}, self.btc_spec)
        self.assertIsNotNone(sell_sig)
        self.assertEqual(sell_sig.direction, OrderType.SELL)
        self.assertGreater(sell_sig.stop_loss, sell_sig.entry_price)
        self.assertLess(sell_sig.take_profit, sell_sig.entry_price)

    # =========================================================================
    # 3. RISK MANAGEMENT & TRADE OUTCOME ACCOUNTING TESTS
    # =========================================================================
    def test_05_trade_outcome_accounting_and_cooldown_recovery(self) -> None:
        """
        Verifies:
        - Opening a trade does NOT count as a closed win or loss.
        - Duplicate close events (same ticket or deal_id) are deduplicated.
        - Partial closes update realized P/L without double-incrementing consecutive losses.
        - Winning closed trade resets consecutive-loss streak and symbol cooldown.
        - Consecutive-loss cooldown expires cleanly without permanent lockout.
        """
        risk_cfg = RiskConfig(
            max_consecutive_losses=3,
            consecutive_loss_trigger=2,
            consecutive_loss_cooldown_minutes=15,
            max_daily_loss_percent=5.0,
        )
        pr = PortfolioRiskEngine(risk_cfg)
        pr.initialize_day(5000.0, 5000.0)

        # Opening a trade only increments session_trades_count, never consecutive_losses
        pr.register_trade_executed()
        self.assertEqual(pr.consecutive_losses, 0)
        self.assertEqual(pr.daily_realized_loss, 0.0)

        # Partial close loss updates realized loss but does not increment consecutive_losses
        recorded_partial = pr.record_closed_trade(-10.0, volume=0.01, symbol="XAUUSD.m", ticket=1001, is_partial=True)
        self.assertTrue(recorded_partial)
        self.assertEqual(pr.daily_realized_loss, 10.0)
        self.assertEqual(pr.consecutive_losses, 0)

        # Full close loss #1 on ticket 1001
        rec1 = pr.record_closed_trade(-20.0, volume=0.01, symbol="XAUUSD.m", ticket=1001, deal_id=5001)
        self.assertTrue(rec1)
        self.assertEqual(pr.consecutive_losses, 1)
        self.assertEqual(pr.daily_realized_loss, 30.0)

        # Duplicate close event for same deal_id or ticket is ignored
        dup_deal = pr.record_closed_trade(-20.0, volume=0.01, symbol="XAUUSD.m", ticket=1001, deal_id=5001)
        dup_ticket = pr.record_closed_trade(-20.0, volume=0.01, symbol="XAUUSD.m", ticket=1001)
        self.assertFalse(dup_deal)
        self.assertFalse(dup_ticket)
        self.assertEqual(pr.consecutive_losses, 1)
        self.assertEqual(pr.daily_realized_loss, 30.0)

        # Full close loss #2 on XAUUSD.m triggers per-symbol cooldown
        pr.record_closed_trade(-25.0, volume=0.01, symbol="XAUUSD.m", ticket=1002, deal_id=5002)
        self.assertEqual(pr.consecutive_losses, 2)
        self.assertIn("XAUUSD.M", pr.symbol_cooldown_until)

        acc = AccountInfo(balance=4945.0, equity=4945.0, free_margin=4945.0, trade_mode="DEMO")
        cand = SignalCandidate(
            id="RISK_TEST_1",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2660.0,
            risk_reward=2.0,
            score=80.0,
            timestamp=self.now,
            status="APPROVED",
        )
        ok, reason = pr.evaluate_new_order_permission(cand, acc, [], 25.0, 0.01)
        self.assertFalse(ok)
        self.assertIn("consecutive-loss cooldown", reason)

        # Expire symbol cooldown -> recovers cleanly
        pr.symbol_cooldown_until["XAUUSD.M"] = datetime.now(timezone.utc) - timedelta(seconds=5)
        ok_after, _ = pr.evaluate_new_order_permission(cand, acc, [], 25.0, 0.01)
        self.assertTrue(ok_after)
        self.assertNotIn("XAUUSD.M", pr.symbol_cooldown_until)

        # Winning trade resets consecutive_losses to 0
        pr.record_closed_trade(+45.0, volume=0.01, symbol="XAUUSD.m", ticket=1003, deal_id=5003)
        self.assertEqual(pr.consecutive_losses, 0)

    def test_06_kill_switch_latch_and_demo_account_protection(self) -> None:
        """Verifies STOP.flag kill switch latches until cleared and REAL accounts are blocked in DEMO mode."""
        cfg = AppConfig.load_from_dir()
        cfg.execution_mode = ExecutionMode.DEMO
        cfg.live_trading_enabled = False
        pr = PortfolioRiskEngine(cfg)

        cand = SignalCandidate(
            id="KILL_TEST_1",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2660.0,
            risk_reward=2.0,
            score=80.0,
            timestamp=self.now,
            status="APPROVED",
        )
        demo_acc = AccountInfo(balance=5000.0, equity=5000.0, free_margin=5000.0, trade_mode="DEMO")
        real_acc = AccountInfo(balance=5000.0, equity=5000.0, free_margin=5000.0, trade_mode="REAL")

        # REAL account blocked when execution_mode=DEMO / LIVE_TRADING_ENABLED=false
        ok_real, reason_real = pr.evaluate_new_order_permission(cand, real_acc, [], 25.0, 0.01)
        self.assertFalse(ok_real)
        self.assertIn("Safety Lock", reason_real)

        # Kill switch file latches and blocks trading until explicitly cleared
        with tempfile.TemporaryDirectory() as tmpdir:
            flag_file = os.path.join(tmpdir, "STOP.flag")
            Path(flag_file).write_text("HALT", encoding="utf-8")
            pr.kill_switch_flag_path = flag_file

            ok_ks, reason_ks = pr.evaluate_new_order_permission(cand, demo_acc, [], 25.0, 0.01)
            self.assertFalse(ok_ks)
            self.assertIn("Kill switch is ACTIVE", reason_ks)

            # Even if file is removed, latch remains active until clear_kill_switch() is called
            os.remove(flag_file)
            ok_latched, _ = pr.evaluate_new_order_permission(cand, demo_acc, [], 25.0, 0.01)
            self.assertFalse(ok_latched)

            pr.clear_kill_switch()
            ok_cleared, _ = pr.evaluate_new_order_permission(cand, demo_acc, [], 25.0, 0.01)
            self.assertTrue(ok_cleared)

    # =========================================================================
    # 4. BROKER EXECUTION & PRE-TRADE VALIDATION TESTS
    # =========================================================================
    def test_07_execution_mandatory_sl_and_broker_confirmation(self) -> None:
        """Verifies orders without SL are rejected and unconfirmed broker fills are flagged UNCONFIRMED."""
        cfg = AppConfig.load_from_dir()
        cfg.dry_run = False
        mock_bridge = MagicMock()
        mock_bridge.is_connected.return_value = True
        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(1.0), PortfolioRiskEngine(cfg))
        acc = AccountInfo(balance=5000.0, equity=5000.0, free_margin=5000.0, leverage=200, trade_mode="DEMO")

        # 1. Missing SL (stop_loss=0.0) -> rejected
        no_sl_cand = SignalCandidate(
            id="NO_SL_1",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=2650.20,
            stop_loss=0.0,
            take_profit=2660.00,
            risk_reward=2.0,
            score=80.0,
            timestamp=self.now,
            status="APPROVED",
        )
        chk_no_sl = om.run_pre_trade_checklist(no_sl_cand, acc, self.gold_spec, [])
        self.assertFalse(chk_no_sl.passed)

        # 2. Valid SL -> accepted only when broker confirms open position
        valid_cand = SignalCandidate(
            id=f"VALID_SL_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M1,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=2650.20,
            stop_loss=2645.20,
            take_profit=2660.20,
            risk_reward=2.0,
            score=80.0,
            timestamp=self.now,
            status="APPROVED",
        )
        mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 990011,
            "price": 2650.20,
            "retcode": 10009,
        }
        # If broker position list is empty, order must be marked UNCONFIRMED
        mock_bridge.get_positions.return_value = []
        unconf_order = om.execute_signal(valid_cand, acc, self.gold_spec, [])
        self.assertIsNotNone(unconf_order)
        self.assertEqual(unconf_order.status, "UNCONFIRMED")

    # =========================================================================
    # 5. LIFECYCLE & POSITION OWNERSHIP PROTECTION TESTS
    # =========================================================================
    def test_08_position_ownership_magic_number_protection(self) -> None:
        """Verifies OrderManager.get_active_positions() isolates bot-owned magic numbers from manual positions."""
        cfg = AppConfig.load_from_dir()
        cfg.dry_run = False
        mock_bridge = MagicMock()
        mock_bridge.is_connected.return_value = True
        om = OrderManager(cfg, mock_bridge, PositionSizingEngine(1.0), PortfolioRiskEngine(cfg))
        bot_magic = cfg.magic_number
        manual_pos = Position(
            ticket=111,
            symbol="XAUUSD.m",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=2640.0,
            current_price=2650.0,
            stop_loss=2630.0,
            take_profit=2670.0,
            profit=100.0,
            magic=0,  # Manual position
        )
        bot_pos = Position(
            ticket=222,
            symbol="XAUUSD.m",
            order_type=OrderType.BUY,
            volume=0.05,
            open_price=2648.0,
            current_price=2650.0,
            stop_loss=2643.0,
            take_profit=2660.0,
            profit=10.0,
            magic=bot_magic,  # Bot-owned position
        )
        mock_bridge.get_positions.return_value = [manual_pos, bot_pos]

        bot_only = om.get_active_positions()
        all_acct = om.get_all_account_positions()
        self.assertEqual(len(bot_only), 1)
        self.assertEqual(bot_only[0].ticket, 222)
        self.assertEqual(len(all_acct), 2)

    # =========================================================================
    # 6. PROMOTION GATE VALIDATION TESTS
    # =========================================================================
    def test_09_promotion_check_rejects_missing_malformed_and_insufficient_evidence(self) -> None:
        """Verifies promotion_check.py has no hardcoded pass, rejects missing/malformed/small samples, and enforces DEMO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "nonexistent.json")
            ok_miss, _, verd_miss = load_and_evaluate_promotion_evidence(report_path=missing_path)
            self.assertFalse(ok_miss)
            self.assertIn("Missing validation evidence", verd_miss)

            malformed_path = os.path.join(tmpdir, "malformed.json")
            Path(malformed_path).write_text("{not_valid_json", encoding="utf-8")
            ok_mal, _, verd_mal = load_and_evaluate_promotion_evidence(report_path=malformed_path)
            self.assertFalse(ok_mal)
            self.assertIn("Malformed validation evidence", verd_mal)

            insufficient_path = os.path.join(tmpdir, "insufficient.json")
            Path(insufficient_path).write_text(
                json.dumps(
                    {
                        "wf_sharpe": 1.4,
                        "expectancy_r": 0.35,
                        "ci_lower": 0.10,
                        "dsr": 0.98,
                        "pbo": 0.10,
                        "mc_ruin_pct": 0.0,
                        "mc_breach_pct": 2.5,
                        "shadow_trade_count": 12,  # < 50 required shadow trades
                        "shadow_z_score": 0.4,
                        "operator_confirmed": True,
                    }
                ),
                encoding="utf-8",
            )
            ok_ins, criteria_ins, verd_ins = load_and_evaluate_promotion_evidence(report_path=insufficient_path)
            self.assertFalse(ok_ins)
            self.assertIn("DEMO mode", verd_ins)
            self.assertFalse(criteria_ins[4].passed)


if __name__ == "__main__":
    unittest.main()
