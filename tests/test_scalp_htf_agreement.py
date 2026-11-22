"""
Unit tests for Simplified 2-Timeframe (1 Higher Timeframe + 1 Lower Timeframe) Alignment.
Tests:
- Bullish alignment (HTF=BULLISH, LTF=BULLISH) -> aligned
- Bearish alignment (HTF=BEARISH, LTF=BEARISH) -> aligned
- Opposing 3rd timeframe (e.g. H4=BEARISH when H1=BULLISH & M15=BULLISH) -> still aligned
- Conflicting HTF/LTF combinations (HTF!=LTF or HTF=RANGING) -> conflict
- Configurable htf_timeframe / ltf_timeframe override
"""

import unittest
from datetime import datetime, timezone
from src.core.contracts import TrendBias, Timeframe
from src.smc.mtf_analyzer import MultiTimeframeContext, TimeframeAnalysis
from src.smc.strategy_engine import SmcStrategyEngine


class TestScalpHTFAgreement(unittest.TestCase):
    def setUp(self):
        self.engine = SmcStrategyEngine(htf_timeframe="H1", ltf_timeframe="M15")
        self.now = datetime.now(timezone.utc)

    def _create_context(self, m15_bias: TrendBias, h1_bias: TrendBias, h4_bias: TrendBias) -> MultiTimeframeContext:
        def _make_tf(tf: Timeframe, bias: TrendBias):
            return TimeframeAnalysis(
                timeframe=tf,
                trend=bias,
                last_close=1.1000
            )

        return MultiTimeframeContext(
            symbol="EURUSD",
            timestamp=self.now,
            w1=_make_tf(Timeframe.W1, TrendBias.STRONG_BULLISH),
            d1=_make_tf(Timeframe.D1, TrendBias.STRONG_BULLISH),
            h4=_make_tf(Timeframe.H4, h4_bias),
            h1=_make_tf(Timeframe.H1, h1_bias),
            m15=_make_tf(Timeframe.M15, m15_bias),
            overall_bias=TrendBias.STRONG_BULLISH
        )

    def test_htf_ltf_agree_long(self):
        ctx = self._create_context(TrendBias.STRONG_BULLISH, TrendBias.STRONG_BULLISH, TrendBias.STRONG_BULLISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertTrue(agree)
        self.assertEqual(dirs["M15"], "BULLISH")
        self.assertEqual(dirs["H1"], "BULLISH")
        self.assertIn("aligned", msg.lower())

    def test_htf_ltf_agree_short(self):
        ctx = self._create_context(TrendBias.STRONG_BEARISH, TrendBias.STRONG_BEARISH, TrendBias.STRONG_BEARISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertTrue(agree)
        self.assertEqual(dirs["M15"], "BEARISH")
        self.assertEqual(dirs["H1"], "BEARISH")
        self.assertIn("aligned", msg.lower())

    def test_opposing_third_timeframe_does_not_block_long(self):
        # H1=BULLISH, M15=BULLISH, H4=BEARISH -> simplified 2-TF rule MUST allow
        ctx = self._create_context(TrendBias.STRONG_BULLISH, TrendBias.STRONG_BULLISH, TrendBias.STRONG_BEARISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertTrue(agree)
        self.assertEqual(dirs["H1"], "BULLISH")
        self.assertEqual(dirs["M15"], "BULLISH")

    def test_opposing_third_timeframe_does_not_block_short(self):
        # H1=BEARISH, M15=BEARISH, H4=BULLISH -> simplified 2-TF rule MUST allow
        ctx = self._create_context(TrendBias.STRONG_BEARISH, TrendBias.STRONG_BEARISH, TrendBias.STRONG_BULLISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertTrue(agree)
        self.assertEqual(dirs["H1"], "BEARISH")
        self.assertEqual(dirs["M15"], "BEARISH")

    def test_conflict_htf_bearish_ltf_bullish(self):
        ctx = self._create_context(TrendBias.STRONG_BULLISH, TrendBias.STRONG_BEARISH, TrendBias.STRONG_BULLISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertFalse(agree)
        self.assertIn("conflict", msg.lower())

    def test_conflict_htf_bullish_ltf_bearish(self):
        ctx = self._create_context(TrendBias.STRONG_BEARISH, TrendBias.STRONG_BULLISH, TrendBias.STRONG_BEARISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertFalse(agree)
        self.assertIn("conflict", msg.lower())

    def test_conflict_htf_ranging(self):
        ctx = self._create_context(TrendBias.STRONG_BULLISH, TrendBias.RANGING, TrendBias.STRONG_BULLISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx)
        self.assertFalse(agree)
        self.assertIn("conflict", msg.lower())

    def test_configurable_htf_override_h4_m15(self):
        ctx = self._create_context(TrendBias.STRONG_BULLISH, TrendBias.STRONG_BEARISH, TrendBias.STRONG_BULLISH)
        agree, msg, dirs = self.engine.check_scalp_htf_agreement(ctx, htf_timeframe="H4", ltf_timeframe="M15")
        self.assertTrue(agree)
        self.assertEqual(dirs, {"H4": "BULLISH", "M15": "BULLISH"})


if __name__ == "__main__":
    unittest.main()
