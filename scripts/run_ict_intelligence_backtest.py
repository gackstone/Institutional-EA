"""
Chronological Out-of-Sample Walk-Forward Backtest & Shadow-Mode Validation
for ICT/SMC Market Intelligence (Videos 0010–0019).

Compares:
  A. Existing Baseline (`VideoSetupEngine`)
  B. New `ICTIntelligenceEngine` in SHADOW mode (diagnostics, rejection rates, lifecycle)
  C. Integrated ICT Intelligence (approved confirmed/high-quality candidates)

Includes spread, commission, and slippage costs, chronological 60% IS / 40% OOS split,
Deflated Sharpe Ratio (DSR) from `src/learning/validation/statistics.py`, and breakdowns by
setup model, trading session, and volatility regime.

Writes: `reports/ict_intelligence_validation_2026-11-26.md`
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.contracts import Candle, OrderType, Timeframe
from src.learning.validation.statistics import deflated_sharpe_ratio
from src.smc.ict_intelligence import (
    ICTIntelligenceEngine,
    ICTModelPerformanceTracker,
    SetupLifecycleStage,
)
from src.smc.video_primitives import compute_atr
from src.smc.video_setups import VideoSetupEngine


def _load_candles(path: Path, limit: int = 1500) -> List[Candle]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("candles") or raw.get("data") or []
    out: List[Candle] = []
    for row in raw[-limit:]:
        ts_val = row.get("time") or row.get("timestamp")
        if isinstance(ts_val, (int, float)):
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        out.append(
            Candle(
                time=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                tick_volume=int(row.get("tick_volume", row.get("volume", 100))),
                complete=True,
            )
        )
    return out


def _session_tag(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 7:
        return "ASIA"
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 17:
        return "NEW_YORK"
    return "OFF_HOURS"


def _vol_regime(candles: List[Candle]) -> str:
    if len(candles) < 30:
        return "NORMAL"
    cur_atr = compute_atr(candles[-15:], 14)
    base_atr = compute_atr(candles[-60:], 30)
    ratio = cur_atr / max(base_atr, 1e-9)
    if ratio > 1.35:
        return "HIGH_VOL"
    if ratio < 0.70:
        return "LOW_VOL"
    return "NORMAL"


def _simulate_outcome_r(
    direction: OrderType,
    entry: float,
    sl: float,
    tp: float,
    future_bars: List[Candle],
    cost_price: float,
    horizon: int = 48,
) -> Optional[float]:
    risk = abs(entry - sl)
    if risk <= 1e-9:
        return None
    cost_r = cost_price / risk
    is_buy = direction == OrderType.BUY
    filled = False
    for bar in future_bars[:horizon]:
        if not filled:
            if bar.low <= entry <= bar.high:
                filled = True
            else:
                continue
        if is_buy:
            if bar.low <= sl:
                return round(-1.0 - cost_r, 4)
            if bar.high >= tp:
                return round((abs(tp - entry) / risk) - cost_r, 4)
        else:
            if bar.high >= sl:
                return round(-1.0 - cost_r, 4)
            if bar.low <= tp:
                return round((abs(entry - tp) / risk) - cost_r, 4)
    return None


def _summarize_r(pnls: List[float], n_trials: int = 8) -> Dict[str, Any]:
    if not pnls:
        return {
            "trades": 0, "win_rate": 0.0, "pf": 0.0, "exp_r": 0.0,
            "max_dd_r": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0, "dsr": 0.0,
        }
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = (gw / gl) if gl > 1e-9 else gw
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in pnls:
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    arr = np.array(pnls, dtype=float)
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = (float(np.mean(arr)) / std) if std > 1e-9 else 0.0
    dsr = deflated_sharpe_ratio(sharpe, arr, n_trials=n_trials) if len(arr) >= 5 else 0.0
    return {
        "trades": len(pnls),
        "win_rate": round(len(wins) / len(pnls) * 100.0, 1),
        "pf": round(pf, 2),
        "exp_r": round(float(np.mean(arr)), 3),
        "max_dd_r": round(max_dd, 2),
        "avg_win_r": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_r": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "dsr": round(float(dsr), 3),
    }


def run_symbol_validation(
    symbol: str,
    m15_path: Path,
    d1_path: Path,
    spread_price: float,
    commission_slippage_price: float,
    pip_size: float,
) -> Dict[str, Any]:
    candles = _load_candles(m15_path, limit=1400)
    daily = _load_candles(d1_path, limit=200)
    if len(candles) < 200:
        return {"symbol": symbol, "error": "Insufficient data"}

    split_idx = int(len(candles) * 0.60)  # Chronological 60% IS / 40% OOS
    total_cost = spread_price + commission_slippage_price

    base_eng = VideoSetupEngine({
        "setups": {
            "S1_RAID_SHIFT_FVG_CE": {"enabled": True, "min_rr": 1.8, "allow_b_grade": True},
            "S6_IFVG_STOP_HUNT": {"enabled": True, "min_rr": 1.8, "allow_b_grade": True},
            "S8_OTE_STOP_HUNT_BOS": {"enabled": True, "min_rr": 1.8, "allow_b_grade": True},
        }
    })
    ict_eng = ICTIntelligenceEngine({"mode": "SHADOW", "min_rr": 1.8})
    tracker_oos = ICTModelPerformanceTracker()

    base_oos_r: List[float] = []
    ict_is_r: List[float] = []
    ict_oos_r: List[float] = []
    shadow_total = 0
    shadow_rejected = 0
    shadow_approved = 0
    rejection_counts: Dict[str, int] = {}

    for i in range(80, len(candles) - 50, 3):
        win = candles[i - 80: i + 1]
        fut = candles[i + 1: i + 50]
        cur_dt = win[-1].time
        d_hist = [d for d in daily if d.time <= cur_dt]
        is_oos = i >= split_idx
        sess = _session_tag(cur_dt)
        reg = _vol_regime(win)

        # A. Baseline existing engine (OOS only for fair comparison)
        if is_oos:
            b_sig = (
                base_eng.detect_s1_raid_shift_fvg_ce(symbol, Timeframe.M15, win, pip_size=pip_size)
                or base_eng.detect_s6_ifvg_stop_hunt(symbol, Timeframe.M15, win, pip_size=pip_size)
                or base_eng.detect_s8_ote_stop_hunt_bos(symbol, Timeframe.M15, win, pip_size=pip_size)
            )
            if b_sig is not None:
                r_out = _simulate_outcome_r(b_sig.direction, b_sig.entry_price, b_sig.stop_loss, b_sig.take_profit, fut, total_cost)
                if r_out is not None:
                    base_oos_r.append(r_out)

        # B/C. New ICT Intelligence Engine (SHADOW mode)
        evs = ict_eng.evaluate_market(
            symbol, Timeframe.M15, win,
            daily_candles=d_hist, spread_price=spread_price,
            volatility_regime=reg, pip_size=pip_size,
        )
        for ev in evs:
            shadow_total += 1
            if ev.decision == "REJECTED":
                shadow_rejected += 1
                for rc in ev.rejection_codes:
                    rejection_counts[rc] = rejection_counts.get(rc, 0) + 1
            elif ev.lifecycle_stage in (SetupLifecycleStage.CONFIRMED, SetupLifecycleStage.HIGH_QUALITY):
                shadow_approved += 1
                r_out = _simulate_outcome_r(ev.direction, ev.entry_price, ev.stop_loss, ev.take_profit, fut, total_cost)
                if r_out is not None:
                    if is_oos:
                        ict_oos_r.append(r_out)
                        tracker_oos.record_outcome(ev.model_name, r_out, session=sess, volatility_regime=reg)
                    else:
                        ict_is_r.append(r_out)

    return {
        "symbol": symbol,
        "bars": len(candles),
        "oos_bars": len(candles) - split_idx,
        "baseline_oos": _summarize_r(base_oos_r),
        "ict_is": _summarize_r(ict_is_r),
        "ict_oos": _summarize_r(ict_oos_r),
        "shadow_total": shadow_total,
        "shadow_approved": shadow_approved,
        "shadow_rejected": shadow_rejected,
        "rejection_rate_pct": round((shadow_rejected / max(shadow_total, 1)) * 100.0, 1),
        "rejection_counts": rejection_counts,
        "by_model": tracker_oos.summary_by_model(),
        "by_session": tracker_oos.summary_by_session(),
        "by_regime": tracker_oos.summary_by_regime(),
    }


def main() -> None:
    data_dir = ROOT / "data" / "historical"
    results = [
        run_symbol_validation(
            "XAUUSD",
            data_dir / "XAUUSD_M15.json",
            data_dir / "XAUUSD_D1.json",
            spread_price=0.25,
            commission_slippage_price=0.15,
            pip_size=0.01,
        ),
        run_symbol_validation(
            "BTCUSD",
            data_dir / "BTCUSD.m_M15.json",
            data_dir / "BTCUSD.m_D1.json",
            spread_price=15.0,
            commission_slippage_price=10.0,
            pip_size=1.0,
        ),
    ]

    lines = [
        "# ICT/SMC Market Intelligence Walk-Forward Validation Report (2026-11-26)",
        "",
        "> **EMPIRICAL DISCLAIMER:** Chronological 60% In-Sample / 40% Out-of-Sample evaluation with spread, commission, and slippage deductions. New ICT intelligence remains deployed in **`SHADOW` mode** by default (`allow_live_orders: false`). Do not promote any model to `DEMO_EXECUTE` unless out-of-sample expectancy and Deflated Sharpe Ratio (DSR) meet promotion gates.",
        "",
    ]

    for res in results:
        if "error" in res:
            lines.append(f"## {res['symbol']} — {res['error']}\n")
            continue
        b = res["baseline_oos"]
        i_is = res["ict_is"]
        i_oos = res["ict_oos"]
        lines.extend([
            f"## {res['symbol']} (M15, {res['bars']} bars total / {res['oos_bars']} OOS bars)",
            "",
            "### A / B / C Strategy Comparison (Net of Spread, Commission & Slippage)",
            "",
            "| Cohort | Trades | Win Rate | Profit Factor | Expectancy (R) | Max DD (R) | Avg Win (R) | Avg Loss (R) | DSR |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| A. Existing Baseline (OOS) | {b['trades']} | {b['win_rate']}% | {b['pf']} | {b['exp_r']} | {b['max_dd_r']} | {b['avg_win_r']} | {b['avg_loss_r']} | {b['dsr']} |",
            f"| B/C. ICT Intelligence (IS) | {i_is['trades']} | {i_is['win_rate']}% | {i_is['pf']} | {i_is['exp_r']} | {i_is['max_dd_r']} | {i_is['avg_win_r']} | {i_is['avg_loss_r']} | {i_is['dsr']} |",
            f"| B/C. ICT Intelligence (OOS) | {i_oos['trades']} | {i_oos['win_rate']}% | {i_oos['pf']} | {i_oos['exp_r']} | {i_oos['max_dd_r']} | {i_oos['avg_win_r']} | {i_oos['avg_loss_r']} | {i_oos['dsr']} |",
            "",
            f"- **Shadow Mode Diagnostics**: `{res['shadow_total']}` evaluated | `{res['shadow_approved']}` confirmed/high-quality | `{res['shadow_rejected']}` rejected (`{res['rejection_rate_pct']}%` rejection rate)",
            f"- **Top Rejection Reasons**: `{res['rejection_counts']}`",
            "",
            "### OOS Performance by Setup Model",
            "",
            "| Model | Trades | Win Rate | Profit Factor | Expectancy (R) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        for m, st in res["by_model"].items():
            lines.append(f"| `{m}` | {st['trades']} | {st['win_rate']*100:.1f}% | {st['profit_factor']} | {st['expectancy_r']} |")
        lines.extend([
            "",
            "### OOS Performance by Session & Volatility Regime",
            f"- **Sessions**: `{res['by_session']}`",
            f"- **Volatility Regimes**: `{res['by_regime']}`",
            "",
        ])

    out_path = ROOT / "reports" / "ict_intelligence_validation_2026-11-26.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
