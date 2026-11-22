"""
Unit tests for Multi-Timeframe Analysis Engine.
"""

import unittest
from datetime import datetime, timezone, timedelta
from src.core.contracts import Candle, Timeframe, TrendBias
from src.smc.mtf_analyzer import MultiTimeframeAnalyzer


def build_trending_candles(start: float, step: float, count: int, base_time: datetime) -> list:
    """Builds a trending candle sequence with Higher Highs (HH) and Higher Lows (HL) swing pivots (R1, lookback=5)."""
    candles = []
    p = start
    n_bars = max(count, 42)
    for i in range(n_bars):
        # 12-bar wave cycle: 7 bars up, 5 bars pullback (smaller magnitude so each wave forms HH and HL with lookback=5)
        cycle_pos = i % 12
        delta = step * 1.5 if cycle_pos < 7 else -step * 1.0
        o = p
        c = o + delta
        h = max(o, c) + abs(step * 0.2)
        l = min(o, c) - abs(step * 0.2)
        candles.append(
            Candle(
                time=base_time + timedelta(minutes=15 * i),
                open=o, high=h, low=l, close=c, complete=True
            )
        )
        p = c
    return candles


class TestMultiTimeframeAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = MultiTimeframeAnalyzer()
        self.base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_strong_bullish_alignment(self):
        # Create consistently higher high/higher low sequences
        w1 = build_trending_candles(1.0500, 0.0050, 42, self.base_time)
        d1 = build_trending_candles(1.0600, 0.0030, 42, self.base_time)
        h4 = build_trending_candles(1.0700, 0.0020, 42, self.base_time)
        h1 = build_trending_candles(1.0750, 0.0010, 42, self.base_time)
        m15 = build_trending_candles(1.0800, 0.0005, 42, self.base_time)

        ctx = self.analyzer.analyze("EURUSD", w1, d1, h4, h1, m15)
        self.assertIsNotNone(ctx)
        self.assertIn(ctx.overall_bias, [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH])
        self.assertTrue(ctx.alignment_score >= 50.0)


if __name__ == "__main__":
    unittest.main()
