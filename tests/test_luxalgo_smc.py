"""Unit tests for LuxAlgo Smart Money Concepts Python port (CC BY-NC-SA 4.0 © LuxAlgo)."""

import math
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.service.market.luxalgo_smc import (
    BEARISH,
    BULLISH,
    MAX_OBJECTS_PER_KIND,
    SmcConfig,
    detect_luxalgo_smc,
)


def _generate_realistic_candles(count: int = 400, step_sec: int = 3600, base: float = 154.0):
    """Deterministic multi-wave OHLC series producing swings, BOS/CHoCH, OBs, FVGs, and EQH/EQL."""
    start_ts = 1760000000
    candles = []
    price = base
    for i in range(count):
        # Macro wave (period ~120) + micro wave (period ~16) + occasional displacement
        macro = math.sin(i / 22.0) * 1.4
        micro = math.sin(i / 3.2) * 0.35
        trend = (i / float(count)) * 1.2
        target = base + trend + macro + micro
        o = price
        c = target
        # Inject occasional strong displacement for FVG formation
        if i % 37 == 15:
            c = o + 0.95
        elif i % 37 == 31:
            c = o - 0.90
        # Inject equal highs around i=60 and i=70
        h = max(o, c) + 0.14
        l = min(o, c) - 0.14
        if i in (60, 72):
            h = base + 3.20
            c = max(c, base + 3.05)
        if i in (110, 122):
            l = base - 2.40
            c = min(c, base - 2.25)
        candles.append(
            {
                "time": start_ts + i * step_sec,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
            }
        )
        price = c
    return candles


class TestLuxAlgoSmc(unittest.TestCase):
    def test_full_detection_produces_all_smc_structures_with_irl_erl_tags(self):
        candles = _generate_realistic_candles(450)
        res = detect_luxalgo_smc(candles, SmcConfig())

        # Internal & swing structure breaks
        self.assertGreater(len(res.internal_structures), 0)
        self.assertGreater(len(res.swing_structures), 0)
        for ev in res.internal_structures:
            self.assertIn(ev["tag"], ("BOS", "CHoCH"))
            self.assertEqual(ev["tier"], "INTERNAL")
            self.assertEqual(ev["irl_erl"], "IRL")
            self.assertLess(ev["start_time"], ev["end_time"])
        for ev in res.swing_structures:
            self.assertIn(ev["tag"], ("BOS", "CHoCH"))
            self.assertEqual(ev["tier"], "SWING")
            self.assertEqual(ev["irl_erl"], "ERL")
            self.assertLess(ev["start_time"], ev["end_time"])

        # Order blocks capped to default N=5
        self.assertLessEqual(len(res.internal_order_blocks), 5)
        self.assertLessEqual(len(res.swing_order_blocks), 5)
        for ob in res.internal_order_blocks:
            self.assertEqual(ob["tier"], "INTERNAL")
            self.assertEqual(ob["irl_erl"], "IRL")
            self.assertGreater(ob["top"], ob["bottom"])
        for ob in res.swing_order_blocks:
            self.assertEqual(ob["tier"], "SWING")
            self.assertEqual(ob["irl_erl"], "ERL")
            self.assertGreater(ob["top"], ob["bottom"])

        # Strong/Weak High & Low + Premium/Equilibrium/Discount exact formulas
        self.assertEqual(len(res.strong_weak_levels), 2)
        high_lvl = next(x for x in res.strong_weak_levels if x["kind"] == "HIGH")
        low_lvl = next(x for x in res.strong_weak_levels if x["kind"] == "LOW")
        self.assertGreater(high_lvl["price"], low_lvl["price"])
        self.assertIn(high_lvl["label"], ("Strong High", "Weak High"))
        self.assertIn(low_lvl["label"], ("Strong Low", "Weak Low"))
        self.assertEqual(high_lvl["irl_erl"], "ERL")
        self.assertEqual(low_lvl["irl_erl"], "ERL")

        self.assertEqual(len(res.premium_discount_zones), 3)
        prem = next(z for z in res.premium_discount_zones if z["kind"] == "PREMIUM")
        eq = next(z for z in res.premium_discount_zones if z["kind"] == "EQUILIBRIUM")
        disc = next(z for z in res.premium_discount_zones if z["kind"] == "DISCOUNT")
        top = high_lvl["price"]
        bot = low_lvl["price"]
        self.assertAlmostEqual(prem["top"], top, places=4)
        self.assertAlmostEqual(prem["bottom"], 0.95 * top + 0.05 * bot, places=4)
        self.assertAlmostEqual(eq["top"], 0.525 * top + 0.475 * bot, places=4)
        self.assertAlmostEqual(eq["bottom"], 0.525 * bot + 0.475 * top, places=4)
        self.assertAlmostEqual(disc["top"], 0.95 * bot + 0.05 * top, places=4)
        self.assertAlmostEqual(disc["bottom"], bot, places=4)
        self.assertEqual(eq["irl_erl"], "IRL")

        # Swing points
        self.assertGreater(len(res.swing_points), 0)
        for sp in res.swing_points:
            self.assertIn(sp["tag"], ("HH", "HL", "LH", "LL"))
            self.assertEqual(sp["irl_erl"], "ERL")

        # Candle trends length matches input
        self.assertEqual(len(res.candle_trends), len(candles))

    def test_present_mode_keeps_only_most_recent_structure(self):
        candles = _generate_realistic_candles(450)
        hist = detect_luxalgo_smc(candles, SmcConfig(mode="Historical"))
        pres = detect_luxalgo_smc(candles, SmcConfig(mode="Present"))
        self.assertGreater(len(hist.internal_structures), 1)
        self.assertLessEqual(len(pres.internal_structures), 1)
        self.assertLessEqual(len(pres.swing_structures), 1)
        self.assertLessEqual(len(pres.equal_highs_lows), 1)
        if hist.internal_structures and pres.internal_structures:
            self.assertEqual(pres.internal_structures[0], hist.internal_structures[-1])

    def test_confluence_filter_and_ob_options(self):
        candles = _generate_realistic_candles(350)
        no_filter = detect_luxalgo_smc(candles, SmcConfig(internal_confluence_filter=False))
        with_filter = detect_luxalgo_smc(candles, SmcConfig(internal_confluence_filter=True))
        self.assertLessEqual(len(with_filter.internal_structures), len(no_filter.internal_structures))

        cmr = detect_luxalgo_smc(
            candles,
            SmcConfig(ob_filter="Cumulative Mean Range", ob_mitigation="Close", internal_ob_count=10),
        )
        self.assertLessEqual(len(cmr.internal_order_blocks), 10)

    def test_performance_and_object_caps_on_5000_candles(self):
        candles = _generate_realistic_candles(5000, step_sec=300)
        t0 = time.perf_counter()
        res = detect_luxalgo_smc(candles, SmcConfig())
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 2.0, f"5000-candle SMC detection took {elapsed:.2f}s")
        self.assertLessEqual(len(res.internal_structures), MAX_OBJECTS_PER_KIND)
        self.assertLessEqual(len(res.swing_structures), MAX_OBJECTS_PER_KIND)
        self.assertLessEqual(len(res.equal_highs_lows), MAX_OBJECTS_PER_KIND)
        self.assertLessEqual(len(res.fair_value_gaps), MAX_OBJECTS_PER_KIND)
        self.assertLessEqual(len(res.swing_points), MAX_OBJECTS_PER_KIND)


if __name__ == "__main__":
    unittest.main()
