"""Tests for read-only Engine Drawings Observer (Safety Rule 5 & Schema Parity)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.service.market.drawings_engine import (
    compute_drawings_from_candles,
    should_include_for_timeframe,
    validate_drawing_item,
)
from src.core.contracts import Candle, Timeframe
from src.smc.fvg_ob import FvgObEngine
from src.smc.market_structure import MarketStructureEngine


def _make_candles_series(count: int, step_sec: int, base: float = 2650.0, amp: float = 12.0):
    end = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)  # Wednesday
    start = end - timedelta(seconds=step_sec * count)
    rows = []
    price = base
    for i in range(count):
        t = int((start + timedelta(seconds=i * step_sec)).timestamp())
        # Create clear impulse + swing structure so FVG/OB/BOS/EQH all form naturally
        phase = i % 24
        if phase < 6:
            delta = amp * 0.35
        elif phase < 12:
            delta = -amp * 0.25
        elif phase == 12:
            delta = amp * 1.4  # strong displacement -> FVG + BOS + OB
        elif phase < 18:
            delta = amp * 0.15
        else:
            delta = -amp * 0.45
        o = price
        c = price + delta
        h = max(o, c) + amp * 0.15
        l = min(o, c) - amp * 0.15
        rows.append({"time": t, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2), "volume": 120})
        price = c
    return rows


class TestChartDrawingsEngine(unittest.TestCase):
    def test_compute_drawings_produces_all_layers_and_valid_schema(self):
        candles_by_tf = {
            "W1": _make_candles_series(6, 7 * 86400, base=2600.0, amp=40.0),
            "D1": _make_candles_series(10, 86400, base=2620.0, amp=20.0),
            "H1": _make_candles_series(80, 3600, base=2640.0, amp=8.0),
            "M15": _make_candles_series(120, 900, base=2645.0, amp=5.0),
            "M5": _make_candles_series(160, 300, base=2650.0, amp=3.5),
        }
        latest_t = candles_by_tf["M5"][-1]["time"]
        positions = [
            {
                "ticket": 8801,
                "symbol": "XAUUSD.m",
                "direction": "BUY",
                "volume": 0.05,
                "open_price": 2652.0,
                "current_price": 2660.0,
                "sl": 2653.0,
                "initial_stop_loss": 2642.0,
                "tp": 2675.0,
                "profit": 40.0,
                "ownership": "BOT",
                "open_timestamp": latest_t - 1800,
            },
            # Different symbol must be filtered out
            {
                "ticket": 8802,
                "symbol": "BTCUSD.m",
                "direction": "SELL",
                "volume": 0.01,
                "open_price": 92000.0,
                "current_price": 91800.0,
                "sl": 93000.0,
                "tp": 90000.0,
                "profit": 20.0,
                "ownership": "BOT",
                "open_timestamp": latest_t - 900,
            },
        ]
        pending_signals = [
            {
                "id": "sig-101",
                "symbol": "XAUUSD.m",
                "timeframe": "M5",
                "direction": "SELL",
                "entry_price": 2670.0,
                "stop_loss": 2680.0,
                "take_profit": 2645.0,
                "risk_reward": 2.5,
                "status": "PENDING",
                "timestamp": latest_t - 600,
            }
        ]
        closed_trades = [
            {
                "ticket": 8790,
                "symbol": "XAUUSD.m",
                "direction": "BUY",
                "volume": 0.03,
                "entry_price": 2635.0,
                "exit_price": 2655.0,
                "stop_loss": 2625.0,
                "take_profit": 2655.0,
                "realized_pnl": 60.0,
                "status": "CLOSED",
                "opened_at": datetime.fromtimestamp(latest_t - 14400, tz=timezone.utc).isoformat(),
                "closed_at": datetime.fromtimestamp(latest_t - 7200, tz=timezone.utc).isoformat(),
            }
        ]

        feed = compute_drawings_from_candles(
            symbol="XAUUSD",
            chart_tf="M5",
            candles_by_tf=candles_by_tf,
            positions=positions,
            pending_signals=pending_signals,
            closed_trades=closed_trades,
            config_dir=ROOT / "config",
            broker_symbol="XAUUSD.m",
        )

        self.assertEqual(feed["schema_version"], "1.0")
        self.assertEqual(feed["symbol"], "XAUUSD")
        self.assertEqual(feed["dropped_count"], 0)
        self.assertGreater(feed["counts"]["liquidity"], 0)
        self.assertGreater(feed["counts"]["sessions"], 0)
        self.assertGreater(feed["counts"]["fvgOb"], 0)
        self.assertGreater(feed["counts"]["structure"], 0)
        self.assertEqual(feed["counts"]["trades"], 3)  # 1 open + 1 pending + 1 closed (BTC excluded)

        for d in feed["drawings"]:
            self.assertTrue(validate_drawing_item(d, "XAUUSD"))
            self.assertEqual(d["symbol"], "XAUUSD")

    def test_read_only_observer_does_not_alter_engine_decisions(self):
        """Safety Rule 5 proof: engine outputs are identical before and after observer runs."""
        raw_m15 = _make_candles_series(100, 900, base=2650.0, amp=5.0)
        candles_obj = [
            Candle(
                time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                tick_volume=r["volume"],
                complete=True,
            )
            for r in raw_m15
        ]

        fvg_eng = FvgObEngine(min_fvg_pips=1.5, pip_size=0.1, fvg_min_atr=0.3)
        ms_eng = MarketStructureEngine(swing_lookback=5)

        before_fvgs = [(f.top, f.bottom, f.mitigated) for f in fvg_eng.detect_fvgs("XAUUSD", Timeframe.M15, candles_obj)]
        before_trend, before_ev = ms_eng.analyze_structure("XAUUSD", Timeframe.M15, candles_obj)
        before_events = [(e.event_type, e.price, e.timestamp) for e in before_ev]

        # Run read-only observer
        _ = compute_drawings_from_candles(
            symbol="XAUUSD",
            chart_tf="M15",
            candles_by_tf={"M15": raw_m15},
            config_dir=ROOT / "config",
        )

        after_fvgs = [(f.top, f.bottom, f.mitigated) for f in fvg_eng.detect_fvgs("XAUUSD", Timeframe.M15, candles_obj)]
        after_trend, after_ev = ms_eng.analyze_structure("XAUUSD", Timeframe.M15, candles_obj)
        after_events = [(e.event_type, e.price, e.timestamp) for e in after_ev]

        self.assertEqual(before_fvgs, after_fvgs)
        self.assertEqual(before_trend, after_trend)
        self.assertEqual(before_events, after_events)

    def test_timeframe_filter_rules(self):
        self.assertTrue(should_include_for_timeframe("D1", "M5", "LIQ"))
        self.assertFalse(should_include_for_timeframe("M5", "H1", "FVG"))
        self.assertTrue(should_include_for_timeframe("M5", "H4", "TRADE"))


if __name__ == "__main__":
    unittest.main()
