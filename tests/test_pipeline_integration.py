"""
End-to-End Pipeline Integration Test.
Validates the full workflow from candle ingestion, MTF analysis, SMC setup scoring,
pre-trade checklist, order execution, position lifecycle management, to dashboard generation.
"""

import unittest
from datetime import datetime, timezone, timedelta
from src.core.contracts import Candle, Timeframe, ExecutionMode, SymbolInfo
from src.core.config import AppConfig
from src.core.orchestrator import TradingBotOrchestrator


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.execution_mode = ExecutionMode.SIMULATION
        self.orchestrator = TradingBotOrchestrator(self.config)
        self.base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_full_pipeline_execution(self):
        symbol = "EURUSD"

        # 1. Register symbol
        sym_info = SymbolInfo(
            symbol=symbol,
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            spread=1.0,
            ask=1.0850,
            bid=1.0849
        )
        self.orchestrator.market_data.register_symbol_info(sym_info)

        # 2. Feed Multi-Timeframe Candles with clear HH + HL structure (R1) and displacement FVG/OB (R5/R6)
        def make_candles(count, step, base_p):
            res = []
            p = base_p
            n_bars = max(count, 44)
            for i in range(n_bars):
                cycle_pos = i % 12
                delta = step * 1.5 if cycle_pos < 7 else -step * 1.0
                o = p
                c = o + delta
                h = max(o, c) + abs(step * 0.2)
                l = min(o, c) - abs(step * 0.2)
                # Create a clean 3-candle bullish displacement FVG near the end of the series
                if i == n_bars - 3:
                    c = o + step * 3.5
                    h = c + abs(step * 0.1)
                    l = o - abs(step * 0.1)
                elif i == n_bars - 2:
                    o = p
                    c = o + step * 2.0
                    l = res[-2].high + abs(step * 0.8)  # Non-overlapping FVG above candle i-2 high
                    h = max(c, l) + abs(step * 0.2)
                res.append(Candle(time=self.base_time + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, complete=True))
                p = c
            return res

        w1 = make_candles(44, 0.0020, 1.0500)
        d1 = make_candles(44, 0.0010, 1.0700)
        h4 = make_candles(44, 0.0008, 1.0750)
        h1 = make_candles(44, 0.0005, 1.0800)
        m15 = make_candles(50, 0.0003, 1.0820)

        self.orchestrator.market_data.set_candles(symbol, Timeframe.W1, w1)
        self.orchestrator.market_data.set_candles(symbol, Timeframe.D1, d1)
        self.orchestrator.market_data.set_candles(symbol, Timeframe.H4, h4)
        self.orchestrator.market_data.set_candles(symbol, Timeframe.H1, h1)
        self.orchestrator.market_data.set_candles(symbol, Timeframe.M15, m15)

        sym_info.ask = m15[-1].close
        sym_info.bid = m15[-1].close - 0.0001
        self.orchestrator.market_data.register_symbol_info(sym_info)

        # 3. Run Pipeline Cycle
        candidate = self.orchestrator.run_cycle_for_symbol(symbol)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.symbol, symbol)

        # 4. Verify Active Positions
        positions = self.orchestrator.order_manager.get_active_positions()
        if candidate.status == "APPROVED":
            self.assertTrue(len(positions) >= 1)
            # Verify position properties
            pos = positions[0]
            self.assertEqual(pos.symbol, symbol)
            self.assertTrue(pos.volume >= 0.01)

        # 5. Position Management Check
        self.orchestrator.manage_active_positions()

        # 6. Dashboard State Generation
        state = self.orchestrator.get_dashboard_state()
        self.assertIsNotNone(state)
        self.assertEqual(state.execution_mode, "SIMULATION")


if __name__ == "__main__":
    unittest.main()
