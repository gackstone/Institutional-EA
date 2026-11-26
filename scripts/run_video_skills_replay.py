"""
Historical Replay Runner for Video-Derived Setups (S1-S10).
Replays available M15 history in data/historical/ for XAUUSD (with USDJPY inverse SMT)
and BTCUSD.m, writing reports/video_skills_replay_2026-11-26.md.

ALL metrics are explicitly labelled IN-SAMPLE AND UNVALIDATED.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.contracts import Candle, OrderType, Timeframe
from src.smc.session_liquidity import SessionLiquidityEngine
from src.smc.video_setups import VideoSetupEngine


def load_candles(path: Path, max_bars: int = 1200) -> List[Candle]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("candles", raw.get("data", []))
    rows = rows[-max_bars:]
    out: List[Candle] = []
    for r in rows:
        t_raw = r.get("time") or r.get("timestamp")
        if isinstance(t_raw, (int, float)):
            dt = datetime.fromtimestamp(float(t_raw), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(t_raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        out.append(
            Candle(
                time=dt,
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r.get("tick_volume", r.get("volume", 0)) or 0),
                complete=True,
            )
        )
    return out


def simulate_outcome(sig: Any, future_bars: List[Candle]) -> str:
    """Simple forward bar check (TP hit vs SL hit vs OPEN) — in-sample only."""
    for c in future_bars[:48]:
        if sig.direction == OrderType.BUY:
            if c.low <= sig.stop_loss:
                return "LOSS"
            if c.high >= sig.take_profit:
                return "WIN"
        else:
            if c.high >= sig.stop_loss:
                return "LOSS"
            if c.low <= sig.take_profit:
                return "WIN"
    return "UNRESOLVED"


def replay_symbol(
    symbol: str,
    candles: List[Candle],
    corr_symbol: str | None = None,
    corr_candles: List[Candle] | None = None,
    inverse_pair: bool = True,
) -> Dict[str, Any]:
    # Allow B grade in replay so we can measure BOTH A+ and B grade distributions honestly
    eng = VideoSetupEngine(
        config={
            "setups": {
                k: {"enabled": True, "min_rr": 2.0, "allow_b_grade": True}
                for k in (
                    "S1_RAID_SHIFT_FVG_CE",
                    "S2_SILVER_BULLET",
                    "S3_NY_MACRO",
                    "S4_LONDON_JUDAS_SWING",
                    "S5_ASIAN_SD_REVERSAL",
                    "S6_IFVG_STOP_HUNT",
                    "S7_STACKED_BREAKER_IFVG",
                    "S8_OTE_STOP_HUNT_BOS",
                    "S10_SESSION_SWEEP_REVERSAL",
                )
            }
        }
    )
    sess_liq = SessionLiquidityEngine()
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "A+": 0, "B": 0, "wins": 0, "losses": 0, "rr_sum": 0.0}
    )

    step = 6
    win_size = 40
    for end_idx in range(win_size, len(candles) - 48, step):
        window = candles[end_idx - win_size: end_idx]
        corr_win = corr_candles[end_idx - win_size: end_idx] if corr_candles and len(corr_candles) >= end_idx else None
        future = candles[end_idx:]
        kl = sess_liq.compute_session_key_levels(symbol, window)

        candidates = [
            eng.detect_s1_raid_shift_fvg_ce(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
            eng.detect_s2_silver_bullet(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
            eng.detect_s3_ny_macro(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
            eng.detect_s6_ifvg_stop_hunt(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
            eng.detect_s7_stacked_breaker_ifvg(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
            eng.detect_s8_ote_stop_hunt_bos(
                symbol, Timeframe.M15, window,
                correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair, key_levels=kl,
            ),
        ]
        if kl is not None:
            candidates.append(
                eng.detect_s10_session_sweep_reversal(
                    symbol, Timeframe.M15, window, kl,
                    correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair,
                )
            )
            if kl.asian_high and kl.asian_low and kl.asian_high > kl.asian_low:
                candidates.append(
                    eng.detect_s4_london_judas(
                        symbol, Timeframe.M15, window, kl.asian_high, kl.asian_low,
                        correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair,
                    )
                )
                candidates.append(
                    eng.detect_s5_asian_sd_reversal(
                        symbol, Timeframe.M15, window, kl.asian_high, kl.asian_low,
                        correlated_symbol=corr_symbol, correlated_candles=corr_win, inverse_pair=inverse_pair,
                    )
                )

        for sig in candidates:
            if sig is None:
                continue
            st = stats[sig.setup_id or "UNKNOWN"]
            st["count"] += 1
            if sig.three_point_grade in ("A+", "B"):
                st[sig.three_point_grade] += 1
            st["rr_sum"] += sig.risk_reward
            outcome = simulate_outcome(sig, future)
            if outcome == "WIN":
                st["wins"] += 1
            elif outcome == "LOSS":
                st["losses"] += 1

    return {"symbol": symbol, "bars_replayed": len(candles), "stats": dict(stats)}


def main() -> None:
    hist = ROOT / "data" / "historical"
    xau = load_candles(hist / "XAUUSD_M15.json", max_bars=1200)
    jpy = load_candles(hist / "USDJPY_M15.json", max_bars=1200)
    btc = load_candles(hist / "BTCUSD.m_M15.json", max_bars=1200)

    results = []
    if xau:
        results.append(replay_symbol("XAUUSD", xau, "USDJPY", jpy, inverse_pair=True))
    if btc:
        results.append(replay_symbol("BTCUSD", btc, None, None, inverse_pair=False))

    lines = [
        "# Video Skills Historical Replay Report (2026-11-26)",
        "",
        "> **IMPORTANT DISCLAIMER — IN-SAMPLE & UNVALIDATED:**",
        "> All figures below are **in-sample, unvalidated diagnostic replay counts** generated with engineering starting defaults from short educational video captions.",
        "> They do **not** represent live performance, out-of-sample validation, or a profitability claim.",
        "",
    ]
    for r in results:
        lines.append(f"## {r['symbol']} (M15, {r['bars_replayed']} bars replayed)")
        lines.append("")
        lines.append("| Setup ID | Signals | Grade A+ | Grade B | Avg R:R | Decided (W/L) | In-Sample Hit Rate |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        if not r["stats"]:
            lines.append("| *(no setups triggered in window)* | 0 | 0 | 0 | — | 0/0 | — |")
        else:
            for sid, st in sorted(r["stats"].items()):
                avg_rr = st["rr_sum"] / st["count"] if st["count"] else 0.0
                decided = st["wins"] + st["losses"]
                hr = f"{(st['wins'] / decided) * 100:.1f}%" if decided > 0 else "—"
                lines.append(
                    f"| `{sid}` | {st['count']} | {st['A+']} | {st['B']} | {avg_rr:.2f} | {st['wins']}/{st['losses']} | {hr} |"
                )
        lines.append("")

    out_path = ROOT / "reports" / "video_skills_replay_2026-11-26.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({len(results)} symbols replayed)")


if __name__ == "__main__":
    main()
