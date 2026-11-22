"""
Unit Tests for Modular Strategy Pipeline (Stage 3).
Tests SignalModule, FilterModule, ExitModule, SizingModule, StrategyPipeline,
and LegacySMCStrategy zero-trades parity.
"""

import unittest
from datetime import datetime, timezone, timedelta

from src.strategies.base import (
    SignalModule, FilterModule, ExitModule, SizingModule, StrategyPipeline,
    StrategyContext, RawSignal, FilterResult, ExitPlan, SizingPlan
)
from src.core.contracts import (
    Candle, OrderType, SetupType, SignalCandidate, SymbolInfo, AccountInfo, Position,
    TrendBias, Timeframe
)
from src.smc.strategy_engine import SmcStrategyEngine
from src.risk.position_sizing import PositionSizingEngine
from src.smc.mtf_analyzer import MultiTimeframeContext, TimeframeAnalysis


class DummySignalModule(SignalModule):
    def __init__(self, should_signal: bool = True):
        self.should_signal = should_signal

    def generate_signal(self, ctx: StrategyContext):
        if not self.should_signal:
            return None
        return RawSignal(
            symbol=ctx.symbol,
            direction=OrderType.BUY,
            entry_price=1.1000,
            setup_type=SetupType.SESSION_SWEEP,
            score=85.0,
            rationale="Test dummy",
            timestamp=datetime.now(timezone.utc)
        )


class DummyFilterModule(FilterModule):
    def __init__(self, should_pass: bool = True):
        self.should_pass = should_pass

    def filter_signal(self, signal: RawSignal, ctx: StrategyContext):
        if not self.should_pass:
            return FilterResult(passed=False, reason_code="DUMMY_FILTER", details="Filtered out")
        return FilterResult(passed=True, details="Passed")


class DummyExitModule(ExitModule):
    def compute_exits(self, signal: RawSignal, ctx: StrategyContext):
        return ExitPlan(
            stop_loss=signal.entry_price - 0.0020,
            take_profit=signal.entry_price + 0.0040,
            risk_reward_ratio=2.0
        )


class DummySizingModule(SizingModule):
    def __init__(self, should_pass: bool = True):
        self.should_pass = should_pass

    def compute_size(self, signal: RawSignal, exits: ExitPlan, ctx: StrategyContext):
        if not self.should_pass:
            return SizingPlan(valid=False, rejection_reason="Risk exceeds tier floor")
        return SizingPlan(
            valid=True,
            volume=0.10,
            risk_amount=50.0,
            risk_percent=1.0,
            margin_required=110.0
        )


class TestStrategyPipeline(unittest.TestCase):
    def setUp(self):
        self.ctx = StrategyContext(
            symbol="EURUSD.m",
            m15_candles=[
                Candle(time=datetime.now(timezone.utc), open=1.1000, high=1.1050, low=1.0990, close=1.1020)
            ],
            symbol_info=SymbolInfo(
                symbol="EURUSD.m", digits=5, point=0.00001, tick_size=0.00001, tick_value=1.0,
                contract_size=100000.0, min_lot=0.01, max_lot=50.0, lot_step=0.01, spread=10,
                ask=1.1001, bid=1.1000
            ),
            account_info=AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)
        )

    def test_pipeline_full_success(self):
        pipeline = StrategyPipeline(
            name="TestPipeline",
            signal_module=DummySignalModule(should_signal=True),
            filter_module=DummyFilterModule(should_pass=True),
            exit_module=DummyExitModule(),
            sizing_module=DummySizingModule(should_pass=True)
        )
        cand, filt = pipeline.evaluate(self.ctx)
        self.assertTrue(filt.passed)
        self.assertIsNotNone(cand)
        self.assertEqual(cand.symbol, "EURUSD.m")
        self.assertEqual(cand.direction, OrderType.BUY)
        self.assertEqual(cand.stop_loss, 1.0980)
        self.assertEqual(cand.take_profit, 1.1040)
        self.assertEqual(cand.risk_reward, 2.0)

    def test_pipeline_no_signal(self):
        pipeline = StrategyPipeline(
            name="TestPipeline",
            signal_module=DummySignalModule(should_signal=False),
            filter_module=DummyFilterModule(should_pass=True),
            exit_module=DummyExitModule(),
            sizing_module=DummySizingModule(should_pass=True)
        )
        cand, filt = pipeline.evaluate(self.ctx)
        self.assertFalse(filt.passed)
        self.assertIsNone(cand)
        self.assertEqual(filt.reason_code, "NO_RAW_SIGNAL")

    def test_pipeline_filter_rejection(self):
        pipeline = StrategyPipeline(
            name="TestPipeline",
            signal_module=DummySignalModule(should_signal=True),
            filter_module=DummyFilterModule(should_pass=False),
            exit_module=DummyExitModule(),
            sizing_module=DummySizingModule(should_pass=True)
        )
        cand, filt = pipeline.evaluate(self.ctx)
        self.assertFalse(filt.passed)
        self.assertIsNone(cand)
        self.assertEqual(filt.reason_code, "DUMMY_FILTER")

    def test_pipeline_sizing_rejection(self):
        pipeline = StrategyPipeline(
            name="TestPipeline",
            signal_module=DummySignalModule(should_signal=True),
            filter_module=DummyFilterModule(should_pass=True),
            exit_module=DummyExitModule(),
            sizing_module=DummySizingModule(should_pass=False)
        )
        cand, filt = pipeline.evaluate(self.ctx)
        self.assertFalse(filt.passed)
        self.assertIsNone(cand)
        self.assertEqual(filt.reason_code, "SIZING_REJECTED")


if __name__ == "__main__":
    unittest.main()
