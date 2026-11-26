"""
Read-only Engine Drawings Observer for the Companion Chart.

Safety Rule 5 compliance:
- Purely additive and read-only: invokes the existing engine analyzers
  (WeeklyDailyEngine, SessionLiquidityEngine, LiquidityEngine, FvgObEngine,
  MarketStructureEngine, TradingSessionEngine) using the exact configuration
  in config/strategy_config.json and config/sessions.json.
- Never mutates trading strategy state, risk state, or order-decision logic.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import Candle, Timeframe
from src.smc.weekly_daily import WeeklyDailyEngine
from companion.service.market.luxalgo_smc import SmcConfig, detect_luxalgo_smc

SCHEMA_VERSION = "1.0"

TF_RANK: Dict[str, int] = {
    "M1": 1,
    "M5": 2,
    "M15": 3,
    "M30": 4,
    "H1": 5,
    "H4": 6,
    "D1": 7,
    "W1": 8,
    "MN1": 9,
}

TF_ENUM_MAP: Dict[str, Timeframe] = {
    "M1": Timeframe.M1,
    "M5": Timeframe.M5,
    "M15": Timeframe.M15,
    "M30": Timeframe.M30,
    "H1": Timeframe.H1,
    "H4": Timeframe.H4,
    "D1": Timeframe.D1,
    "W1": Timeframe.W1,
}

# Caps per layer (max 500 per Pine spec to guarantee smooth 60fps canvas rendering)
LAYER_CAPS = {
    "LIQ": 120,
    "SESS": 32,
    "FVG": 100,
    "OB": 40,
    "STRUCT": 200,
    "TRADE": 30,
}


def canonical_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    for suffix in (".M", "M", "_SB", ".RAW", ".ECN", ".PRO", ".STD"):
        if raw.endswith(suffix) and len(raw) > len(suffix) + 3:
            # Keep standard 6-char symbols intact (e.g., XAUUSD.m -> XAUUSD)
            if suffix == "M" and "." not in raw:
                continue
            raw = raw[: -len(suffix)]
            break
    return raw.split(".")[0]


def pip_params_for_symbol(symbol: str) -> Tuple[float, float]:
    """Returns (pip_size, pip_multiplier) matching Institutional EA symbol specs."""
    sym = canonical_symbol(symbol)
    if "XAU" in sym or "GOLD" in sym:
        return 0.1, 10.0
    if "BTC" in sym:
        return 1.0, 1.0
    if "JPY" in sym:
        return 0.01, 100.0
    return 0.0001, 10000.0


def _to_unix_sec(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value <= 0:
            return None
        return int(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        try:
            dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return None
    return None


def _is_finite_pos(v: Any) -> bool:
    try:
        f = float(v)
        return math.isfinite(f) and f > 0.0
    except Exception:
        return False


def _dicts_to_candles(rows: List[Dict[str, Any]]) -> List[Candle]:
    out: List[Candle] = []
    for r in rows or []:
        t = _to_unix_sec(r.get("time"))
        if t is None:
            continue
        try:
            o = float(r["open"])
            h = float(r["high"])
            l = float(r["low"])
            c = float(r["close"])
            if not all(math.isfinite(x) for x in (o, h, l, c)):
                continue
            out.append(
                Candle(
                    time=datetime.fromtimestamp(t, tz=timezone.utc),
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    tick_volume=int(r.get("volume", r.get("tick_volume", 0)) or 0),
                    complete=True,
                )
            )
        except Exception:
            continue
    out.sort(key=lambda x: x.time)
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _direction_str(d: Any) -> str:
    val = getattr(d, "value", d)
    s = str(val or "NEUTRAL").upper()
    if s in ("BUY", "BULL", "BULLISH", "LONG"):
        return "BULLISH"
    if s in ("SELL", "BEAR", "BEARISH", "SHORT"):
        return "BEARISH"
    return "NEUTRAL"


def should_include_for_timeframe(drawing_tf: str, chart_tf: str, drawing_type: str) -> bool:
    """
    Timeframe visibility policy:
    - TRADE and SESS apply across all intraday timeframes (M1..H4).
    - Higher-timeframe drawings (drawing_tf >= chart_tf) are shown on lower timeframes.
    - Lower-timeframe drawings (drawing_tf < chart_tf) are NOT shown on higher timeframes.
    """
    if drawing_type in ("TRADE", "SESS"):
        return True
    d_rank = TF_RANK.get(str(drawing_tf).upper(), 0)
    c_rank = TF_RANK.get(str(chart_tf).upper(), 0)
    if d_rank == 0 or c_rank == 0:
        return True
    return d_rank >= c_rank


def _parse_hhmm(hhmm: str) -> Tuple[int, int]:
    parts = str(hhmm or "00:00").split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _build_session_drawings(
    symbol: str,
    chart_tf: str,
    visible_candles: List[Candle],
    sessions_cfg: Dict[str, Any],
    broker_offset_hours: int = 0,
) -> List[Dict[str, Any]]:
    if not visible_candles or TF_RANK.get(chart_tf.upper(), 0) > TF_RANK["H4"]:
        return []

    profile_name = str(sessions_cfg.get("active_profile", "ist_reference"))
    profiles = sessions_cfg.get("profiles", {})
    prof = profiles.get(profile_name) or profiles.get("ist_reference") or {}

    # Exact windows from config/sessions.json
    if profile_name == "market_local_dst":
        windows = [
            ("ASIA", "Asia", prof.get("asia", {}).get("fallback_utc_start", "00:00"), prof.get("asia", {}).get("fallback_utc_end", "09:00")),
            ("LONDON", "London", prof.get("london", {}).get("fallback_utc_start", "07:00"), prof.get("london", {}).get("fallback_utc_end", "15:30")),
            ("NY", "New York", prof.get("new_york", {}).get("fallback_utc_start", "12:00"), prof.get("new_york", {}).get("fallback_utc_end", "21:00")),
            ("OVERLAP", "LDN/NY Overlap", "12:00", "15:30"),
        ]
    else:
        windows = [
            ("ASIA", "Asia", prof.get("asia", {}).get("start_utc", "00:00"), prof.get("asia", {}).get("end_utc", "09:00")),
            ("LONDON", "London", prof.get("london", {}).get("start_utc", "06:00"), prof.get("london", {}).get("end_utc", "12:00")),
            ("OVERLAP", "LDN/NY Overlap", prof.get("london_ny_overlap", {}).get("start_utc", "12:30"), prof.get("london_ny_overlap", {}).get("end_utc", "16:00")),
            ("NY", "New York", prof.get("new_york", {}).get("start_utc", "12:30"), prof.get("new_york", {}).get("end_utc", "17:30")),
        ]

    offset_sec = int(broker_offset_hours) * 3600
    min_ts = int(visible_candles[0].time.timestamp())
    max_ts = int(visible_candles[-1].time.timestamp())

    # Collect unique UTC dates covered by visible candles (with 1-day padding)
    start_day = datetime.fromtimestamp(min_ts - offset_sec, tz=timezone.utc).date() - timedelta(days=1)
    end_day = datetime.fromtimestamp(max_ts - offset_sec, tz=timezone.utc).date() + timedelta(days=1)

    items: List[Dict[str, Any]] = []
    cur_day = start_day
    is_btc = "BTC" in canonical_symbol(symbol)
    while cur_day <= end_day:
        # Skip Saturday/Sunday for non-crypto symbols (no FX/Gold session boxes on weekend gap)
        if is_btc or cur_day.weekday() < 5:
            for subtype, label, start_hm, end_hm in windows:
                sh, sm = _parse_hhmm(start_hm)
                eh, em = _parse_hhmm(end_hm)
                s_dt = datetime(cur_day.year, cur_day.month, cur_day.day, sh, sm, tzinfo=timezone.utc)
                e_dt = datetime(cur_day.year, cur_day.month, cur_day.day, eh, em, tzinfo=timezone.utc)
                if e_dt <= s_dt:
                    e_dt += timedelta(days=1)
                s_ts = int(s_dt.timestamp()) + offset_sec
                e_ts = int(e_dt.timestamp()) + offset_sec
                if e_ts < min_ts or s_ts > max_ts:
                    continue
                # Compute actual high/low of candles inside this session window if available
                in_win = [c for c in visible_candles if s_ts <= int(c.time.timestamp()) <= e_ts]
                sess_high = max((c.high for c in in_win), default=None)
                sess_low = min((c.low for c in in_win), default=None)
                items.append(
                    {
                        "id": f"sess:{symbol}:{subtype}:{cur_day.isoformat()}",
                        "type": "SESS",
                        "subtype": subtype,
                        "symbol": symbol,
                        "timeframe": chart_tf,
                        "start_time": s_ts,
                        "end_time": e_ts,
                        "price_levels": {
                            "high": sess_high,
                            "low": sess_low,
                        },
                        "direction": "NEUTRAL",
                        "status": "ACTIVE" if s_ts <= max_ts <= e_ts else "EXPIRED",
                        "source": "TradingSessionEngine",
                        "meta": {
                            "label": label,
                            "profile": profile_name,
                            "utc_window": f"{start_hm}-{end_hm} UTC",
                            "broker_utc_offset_hours": broker_offset_hours,
                        },
                    }
                )
        cur_day += timedelta(days=1)

    return items[-LAYER_CAPS["SESS"] :]


def validate_drawing_item(item: Dict[str, Any], expected_symbol: str) -> bool:
    """Validates schema invariants before emitting a drawing to the chart."""
    if not isinstance(item, dict):
        return False
    if not item.get("id") or not item.get("type") or not item.get("source"):
        return False
    if canonical_symbol(item.get("symbol", "")) != canonical_symbol(expected_symbol):
        return False
    dtype = item.get("type")
    if dtype not in ("LIQ", "SESS", "FVG", "OB", "STRUCT", "TRADE"):
        return False
    if _to_unix_sec(item.get("start_time")) is None:
        return False
    end_t = item.get("end_time")
    if end_t is not None and _to_unix_sec(end_t) is None:
        return False

    pl = item.get("price_levels")
    if not isinstance(pl, dict):
        return False

    if dtype in ("LIQ", "STRUCT"):
        return _is_finite_pos(pl.get("price"))
    if dtype in ("FVG", "OB"):
        return _is_finite_pos(pl.get("top")) and _is_finite_pos(pl.get("bottom")) and float(pl["top"]) > float(pl["bottom"])
    if dtype == "TRADE":
        return _is_finite_pos(pl.get("entry"))
    return True


def compute_drawings_from_candles(
    symbol: str,
    chart_tf: str,
    candles_by_tf: Dict[str, List[Dict[str, Any]]],
    positions: Optional[List[Dict[str, Any]]] = None,
    pending_signals: Optional[List[Dict[str, Any]]] = None,
    closed_trades: Optional[List[Dict[str, Any]]] = None,
    config_dir: Optional[Path] = None,
    broker_utc_offset_hours: Optional[int] = None,
    broker_symbol: Optional[str] = None,
    smc_config: Optional[SmcConfig] = None,
) -> Dict[str, Any]:
    """
    Pure, deterministic read-only computation of all chart drawings for (symbol, chart_tf).
    Uses LuxAlgo Smart Money Concepts (CC BY-NC-SA 4.0) detection for SMC layers,
    WeeklyDailyEngine / MN1 for MTF Highs & Lows, sessions.json for SESS, and MT5/repo for TRADES.
    Never modifies any trading engine state.
    """
    canon = canonical_symbol(symbol)
    tf_upper = str(chart_tf or "M5").upper()
    _pip_size, pip_mult = pip_params_for_symbol(canon)

    cfg_root = Path(config_dir) if config_dir else Path("config")
    sessions_cfg = _load_json(cfg_root / "sessions.json")

    if broker_utc_offset_hours is None:
        broker_utc_offset_hours = int(sessions_cfg.get("broker_utc_offset_hours", 0))

    # Convert raw candle dicts to engine Candle objects
    converted: Dict[str, List[Candle]] = {
        k.upper(): _dicts_to_candles(v) for k, v in (candles_by_tf or {}).items()
    }
    chart_candles = converted.get(tf_upper, [])
    d1_candles = converted.get("D1", [])
    w1_candles = converted.get("W1", [])
    mn1_candles = converted.get("MN1", [])

    raw_items: List[Dict[str, Any]] = []
    min_chart_ts = int(chart_candles[0].time.timestamp()) if chart_candles else 0
    max_chart_ts = int(chart_candles[-1].time.timestamp()) if chart_candles else 0

    # ------------------------------------------------------------------
    # 1. LIQ (MTF Highs & Lows): Daily (PDH/PDL), Weekly (PWH/PWL), Monthly (PMH/PML)
    # ------------------------------------------------------------------
    if len(d1_candles) >= 2:
        try:
            prev_d = d1_candles[-2]
            prev_d_ts = int(prev_d.time.timestamp())
            for code, price, direction in (
                ("PDH", prev_d.high, "BEARISH"),
                ("PDL", prev_d.low, "BULLISH"),
            ):
                if _is_finite_pos(price):
                    raw_items.append(
                        {
                            "id": f"liq:{canon}:D1:{code}:{prev_d_ts}",
                            "type": "LIQ",
                            "subtype": code,
                            "symbol": canon,
                            "broker_symbol": broker_symbol,
                            "timeframe": "D1",
                            "start_time": prev_d_ts,
                            "end_time": None,
                            "price_levels": {"price": round(float(price), 5)},
                            "direction": direction,
                            "status": "ACTIVE",
                            "source": "LuxAlgoSMC_MTF",
                            "meta": {
                                "label": code,
                                "mtf_period": "D",
                                "irl_erl": "ERL",
                                "smc": True,
                            },
                        }
                    )
        except Exception:
            pass

    if len(w1_candles) >= 2:
        try:
            prev_w = w1_candles[-2]
            prev_w_ts = int(prev_w.time.timestamp())
            for code, price, direction in (
                ("PWH", prev_w.high, "BEARISH"),
                ("PWL", prev_w.low, "BULLISH"),
            ):
                if _is_finite_pos(price):
                    raw_items.append(
                        {
                            "id": f"liq:{canon}:W1:{code}:{prev_w_ts}",
                            "type": "LIQ",
                            "subtype": code,
                            "symbol": canon,
                            "broker_symbol": broker_symbol,
                            "timeframe": "W1",
                            "start_time": prev_w_ts,
                            "end_time": None,
                            "price_levels": {"price": round(float(price), 5)},
                            "direction": direction,
                            "status": "ACTIVE",
                            "source": "LuxAlgoSMC_MTF",
                            "meta": {
                                "label": code,
                                "mtf_period": "W",
                                "irl_erl": "ERL",
                                "smc": True,
                            },
                        }
                    )
        except Exception:
            pass

    if len(mn1_candles) >= 2:
        try:
            prev_m = mn1_candles[-2]
            prev_m_ts = int(prev_m.time.timestamp())
            for code, price, direction in (
                ("PMH", prev_m.high, "BEARISH"),
                ("PML", prev_m.low, "BULLISH"),
            ):
                if _is_finite_pos(price):
                    raw_items.append(
                        {
                            "id": f"liq:{canon}:MN1:{code}:{prev_m_ts}",
                            "type": "LIQ",
                            "subtype": code,
                            "symbol": canon,
                            "broker_symbol": broker_symbol,
                            "timeframe": "MN1",
                            "start_time": prev_m_ts,
                            "end_time": None,
                            "price_levels": {"price": round(float(price), 5)},
                            "direction": direction,
                            "status": "ACTIVE",
                            "source": "LuxAlgoSMC_MTF",
                            "meta": {
                                "label": code,
                                "mtf_period": "M",
                                "irl_erl": "ERL",
                                "smc": True,
                            },
                        }
                    )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 2. LuxAlgo Smart Money Concepts (Structure, OBs, FVGs, EQH/EQL, Strong/Weak H/L, P/D)
    # ------------------------------------------------------------------
    raw_chart_rows = [
        {
            "time": int(c.time.timestamp()),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
        }
        for c in chart_candles
    ]
    smc = detect_luxalgo_smc(raw_chart_rows, config=smc_config)

    # 2a. Internal & Swing Structure (BOS / CHoCH)
    for ev in smc.internal_structures + smc.swing_structures:
        tier = ev["tier"]
        tag = ev["tag"]
        raw_items.append(
            {
                "id": f"struct:{canon}:{tf_upper}:{tier}:{tag}:{ev['start_time']}:{ev['end_time']}",
                "type": "STRUCT",
                "subtype": tag.upper(),
                "symbol": canon,
                "broker_symbol": broker_symbol,
                "timeframe": tf_upper,
                "start_time": ev["start_time"],
                "end_time": ev["end_time"],
                "price_levels": {"price": ev["price"]},
                "direction": ev["direction"],
                "status": "ACTIVE",
                "source": "LuxAlgoSMC",
                "meta": {
                    "label": tag,
                    "tier": tier,
                    "irl_erl": ev["irl_erl"],
                    "smc": True,
                },
            }
        )

    # 2b. Internal & Swing Order Blocks
    for ob in smc.internal_order_blocks + smc.swing_order_blocks:
        tier = ob["tier"]
        raw_items.append(
            {
                "id": f"ob:{canon}:{tf_upper}:{tier}:{ob['start_time']}:{ob['bottom']}",
                "type": "OB",
                "subtype": f"{tier}_OB",
                "symbol": canon,
                "broker_symbol": broker_symbol,
                "timeframe": tf_upper,
                "start_time": ob["start_time"],
                "end_time": None,
                "price_levels": {
                    "top": ob["top"],
                    "bottom": ob["bottom"],
                    "midpoint": ob["midpoint"],
                },
                "direction": ob["direction"],
                "status": "ACTIVE",
                "source": "LuxAlgoSMC",
                "meta": {
                    "label": "OB",
                    "tier": tier,
                    "irl_erl": ob["irl_erl"],
                    "smc": True,
                },
            }
        )

    # 2c. Fair Value Gaps
    for fvg in smc.fair_value_gaps:
        raw_items.append(
            {
                "id": f"fvg:{canon}:{tf_upper}:FVG:{fvg['start_time']}:{fvg['bottom']}",
                "type": "FVG",
                "subtype": "FVG",
                "symbol": canon,
                "broker_symbol": broker_symbol,
                "timeframe": tf_upper,
                "start_time": fvg["start_time"],
                "end_time": None,
                "price_levels": {
                    "top": fvg["top"],
                    "bottom": fvg["bottom"],
                    "midpoint": fvg["midpoint"],
                },
                "direction": fvg["direction"],
                "status": "ACTIVE",
                "source": "LuxAlgoSMC",
                "meta": {
                    "label": "FVG",
                    "extend_bars": fvg["extend_bars"],
                    "irl_erl": fvg["irl_erl"],
                    "smc": True,
                },
            }
        )

    # 2d. EQH / EQL
    for eq in smc.equal_highs_lows:
        raw_items.append(
            {
                "id": f"liq:{canon}:{tf_upper}:{eq['tag']}:{eq['start_time']}:{eq['end_time']}",
                "type": "LIQ",
                "subtype": eq["tag"],
                "symbol": canon,
                "broker_symbol": broker_symbol,
                "timeframe": tf_upper,
                "start_time": eq["start_time"],
                "end_time": eq["end_time"],
                "price_levels": {
                    "price": eq["price"],
                    "high": eq["start_price"],
                    "low": eq["end_price"],
                },
                "direction": eq["direction"],
                "status": "ACTIVE",
                "source": "LuxAlgoSMC",
                "meta": {
                    "label": eq["tag"],
                    "irl_erl": eq["irl_erl"],
                    "smc": True,
                },
            }
        )

    # 2e. Strong / Weak High & Low
    for sw in smc.strong_weak_levels:
        subtype = f"STRONG_WEAK_{sw['kind']}"
        raw_items.append(
            {
                "id": f"liq:{canon}:{tf_upper}:{subtype}:{sw['start_time']}",
                "type": "LIQ",
                "subtype": subtype,
                "symbol": canon,
                "broker_symbol": broker_symbol,
                "timeframe": tf_upper,
                "start_time": sw["start_time"],
                "end_time": None,
                "price_levels": {"price": sw["price"]},
                "direction": sw["direction"],
                "status": "ACTIVE",
                "source": "LuxAlgoSMC",
                "meta": {
                    "label": sw["label"],
                    "is_strong": sw["is_strong"],
                    "irl_erl": sw["irl_erl"],
                    "smc": True,
                },
            }
        )

    # ------------------------------------------------------------------
    # 4. SESS: Sessions & Killzones from config/sessions.json
    # ------------------------------------------------------------------
    raw_items.extend(
        _build_session_drawings(
            symbol=canon,
            chart_tf=tf_upper,
            visible_candles=chart_candles,
            sessions_cfg=sessions_cfg,
            broker_offset_hours=broker_utc_offset_hours,
        )
    )

    # ------------------------------------------------------------------
    # 5. TRADES: Open MT5 positions, Pending Signals, Closed Trade History
    # ------------------------------------------------------------------
    for pos in positions or []:
        if canonical_symbol(pos.get("symbol", "")) != canon:
            continue
        entry = float(pos.get("open_price") or pos.get("entry_price") or 0.0)
        sl = float(pos.get("sl") or pos.get("stop_loss") or 0.0)
        init_sl = float(pos.get("initial_stop_loss") or sl)
        tp = float(pos.get("tp") or pos.get("take_profit") or 0.0)
        cur_px = float(pos.get("current_price") or entry)
        open_ts = (
            _to_unix_sec(pos.get("open_timestamp"))
            or _to_unix_sec(pos.get("open_time"))
            or max_chart_ts
            or int(datetime.now(timezone.utc).timestamp())
        )
        direction = _direction_str(pos.get("direction", "BUY"))
        risk = abs(entry - sl) if sl > 0 else 0.0
        reward = abs(tp - entry) if tp > 0 else 0.0
        rr = round(reward / risk, 2) if risk > 0 and reward > 0 else 0.0
        tp1 = (
            round(entry + (risk if direction == "BULLISH" else -risk), 5)
            if risk > 0 and reward > risk * 1.25
            else 0.0
        )
        ticket = int(pos.get("ticket", 0) or 0)
        raw_items.append(
            {
                "id": f"trade:open:{canon}:{ticket}",
                "type": "TRADE",
                "subtype": "OPEN",
                "symbol": canon,
                "broker_symbol": str(pos.get("symbol") or broker_symbol or canon),
                "timeframe": tf_upper,
                "start_time": open_ts,
                "end_time": None,
                "price_levels": {
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "initial_sl": round(init_sl, 5),
                    "tp": round(tp, 5),
                    "tp1": tp1,
                    "current": round(cur_px, 5),
                    "pnl": round(float(pos.get("profit", 0.0) or 0.0), 2),
                    "rr": rr,
                    "volume": float(pos.get("volume", 0.0) or 0.0),
                    "ticket": ticket,
                    "ownership": str(pos.get("ownership", "BOT")),
                },
                "direction": direction,
                "status": "OPEN",
                "source": "MT5SyncService",
                "meta": {
                    "comment": str(pos.get("comment", "")),
                    "sl_moved": bool(init_sl > 0 and sl > 0 and abs(init_sl - sl) > 1e-6),
                },
            }
        )

    for sig in pending_signals or []:
        if canonical_symbol(sig.get("symbol", "")) != canon:
            continue
        sig_status = str(sig.get("status", "PENDING")).upper()
        if sig_status not in ("PENDING", "ACTIVE", "DETECTED", "APPROVED"):
            continue
        entry = float(sig.get("entry_price") or sig.get("entry") or 0.0)
        sl = float(sig.get("stop_loss") or sig.get("sl") or 0.0)
        tp = float(sig.get("take_profit") or sig.get("tp") or 0.0)
        ts = _to_unix_sec(sig.get("timestamp") or sig.get("created_at")) or max_chart_ts
        if not _is_finite_pos(entry) or ts is None:
            continue
        sig_id = str(sig.get("id") or sig.get("signal_id") or ts)
        raw_items.append(
            {
                "id": f"trade:pending:{canon}:{sig_id}",
                "type": "TRADE",
                "subtype": "PENDING",
                "symbol": canon,
                "broker_symbol": str(sig.get("symbol") or broker_symbol or canon),
                "timeframe": str(sig.get("timeframe") or tf_upper).upper(),
                "start_time": ts,
                "end_time": None,
                "price_levels": {
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "initial_sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "rr": round(float(sig.get("risk_reward", 0.0) or 0.0), 2),
                },
                "direction": _direction_str(sig.get("direction", "BUY")),
                "status": "PENDING",
                "source": "CompanionRepository",
                "meta": {
                    "setup_type": str(sig.get("setup_type", "")),
                    "score": float(sig.get("score", 0.0) or 0.0),
                },
            }
        )

    for tr in closed_trades or []:
        if canonical_symbol(tr.get("symbol", "")) != canon:
            continue
        if str(tr.get("status", "")).upper() != "CLOSED":
            continue
        entry = float(tr.get("entry_price") or tr.get("open_price") or 0.0)
        exit_px = float(tr.get("exit_price") or tr.get("close_price") or 0.0)
        sl = float(tr.get("stop_loss") or tr.get("sl") or 0.0)
        tp = float(tr.get("take_profit") or tr.get("tp") or 0.0)
        open_ts = _to_unix_sec(tr.get("opened_at") or tr.get("open_time"))
        close_ts = _to_unix_sec(tr.get("closed_at") or tr.get("close_time"))
        if not _is_finite_pos(entry) or open_ts is None:
            continue
        # Only show closed trades overlapping the loaded candle history (when candles exist)
        if min_chart_ts > 0 and close_ts is not None and close_ts < min_chart_ts:
            continue
        ticket = int(tr.get("ticket", 0) or 0)
        raw_items.append(
            {
                "id": f"trade:closed:{canon}:{ticket}:{open_ts}",
                "type": "TRADE",
                "subtype": "CLOSED",
                "symbol": canon,
                "broker_symbol": str(tr.get("symbol") or broker_symbol or canon),
                "timeframe": tf_upper,
                "start_time": open_ts,
                "end_time": close_ts or open_ts,
                "price_levels": {
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "initial_sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "exit": round(exit_px, 5) if exit_px > 0 else round(entry, 5),
                    "pnl": round(float(tr.get("realized_pnl") or tr.get("profit") or 0.0), 2),
                    "volume": float(tr.get("volume", 0.0) or 0.0),
                    "ticket": ticket,
                    "ownership": str(tr.get("ownership", "BOT")),
                },
                "direction": _direction_str(tr.get("direction", "BUY")),
                "status": "CLOSED",
                "source": "CompanionRepository",
                "meta": {"comment": str(tr.get("comment", ""))},
            }
        )

    # ------------------------------------------------------------------
    # 6. Validate, deduplicate by ID, apply timeframe filter, and cap per layer
    # ------------------------------------------------------------------
    seen_ids = set()
    valid_by_type: Dict[str, List[Dict[str, Any]]] = {k: [] for k in LAYER_CAPS}
    dropped_count = 0

    for item in raw_items:
        if not validate_drawing_item(item, canon):
            dropped_count += 1
            continue
        if not should_include_for_timeframe(item["timeframe"], tf_upper, item["type"]):
            continue
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        valid_by_type[item["type"]].append(item)

    final_drawings: List[Dict[str, Any]] = []
    for dtype, items in valid_by_type.items():
        cap = LAYER_CAPS[dtype]
        # Prefer active/open items and most recent start_time
        items.sort(
            key=lambda x: (
                0 if x.get("status") in ("OPEN", "ACTIVE", "PENDING") else 1,
                -(_to_unix_sec(x.get("start_time")) or 0),
            )
        )
        final_drawings.extend(items[:cap])

    liq_count = len([d for d in final_drawings if d["type"] == "LIQ"])
    fvg_count = len([d for d in final_drawings if d["type"] == "FVG"])
    ob_count = len([d for d in final_drawings if d["type"] == "OB"])
    fvg_ob_count = fvg_count + ob_count
    struct_count = len([d for d in final_drawings if d["type"] == "STRUCT"])
    sess_count = len([d for d in final_drawings if d["type"] == "SESS"])
    trades_count = len([d for d in final_drawings if d["type"] == "TRADE"])

    counts = {
        "liquidity": liq_count,
        "fvgOb": fvg_ob_count,
        "structure": struct_count,
        "sessions": sess_count,
        "trades": trades_count,
        "LIQ": liq_count,
        "FVG": fvg_count,
        "OB": ob_count,
        "FVG_OB": fvg_ob_count,
        "STRUCT": struct_count,
        "SESS": sess_count,
        "TRADE": trades_count,
        "TRADES": trades_count,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": canon,
        "broker_symbol": broker_symbol or canon,
        "timeframe": tf_upper,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "broker_utc_offset_hours": broker_utc_offset_hours,
        "dropped_count": dropped_count,
        "counts": counts,
        "drawings": final_drawings,
        "items": final_drawings,
        "smc": {
            "swing_trend": smc.swing_trend,
            "internal_trend": smc.internal_trend,
            "swing_points": smc.swing_points,
            "premium_discount_zones": smc.premium_discount_zones,
            "strong_weak_levels": smc.strong_weak_levels,
        },
    }


class ChartDrawingsService:
    """Fetches candles/positions/history from Control Service and computes read-only engine drawings."""

    def __init__(self, project_root: Path, mt5_sync: Any, repo: Any):
        self.project_root = Path(project_root)
        self.mt5_sync = mt5_sync
        self.repo = repo

    def get_drawings(self, symbol: str, timeframe: str = "M5", count: int = 160) -> Dict[str, Any]:
        tf_upper = str(timeframe or "M5").upper()
        canon = canonical_symbol(symbol)

        candles_by_tf: Dict[str, List[Dict[str, Any]]] = {}
        primary = self.mt5_sync.get_candles(symbol=canon, timeframe=tf_upper, count=max(160, int(count)))
        broker_symbol = primary.get("broker_symbol") or canon
        candles_by_tf[tf_upper] = primary.get("candles") or []

        # Fetch HTF candles (D1, W1, MN1) for MTF Highs & Lows only when primary is connected
        if candles_by_tf[tf_upper]:
            htf_requests = [("D1", 10), ("W1", 6), ("MN1", 4)]
            for htf, hcount in htf_requests:
                if htf not in candles_by_tf:
                    try:
                        res = self.mt5_sync.get_candles(symbol=canon, timeframe=htf, count=hcount)
                        if res.get("candles"):
                            candles_by_tf[htf] = res["candles"]
                    except Exception:
                        pass

        snap = self.mt5_sync.get_snapshot()
        positions = snap.get("positions") or []

        try:
            pending_signals = self.repo.get_signals(limit=50) if hasattr(self.repo, "get_signals") else []
        except Exception:
            pending_signals = []

        try:
            if hasattr(self.repo, "get_trade_records"):
                closed_trades = self.repo.get_trade_records(limit=150)
            elif hasattr(self.repo, "get_trade_history"):
                closed_trades = self.repo.get_trade_history(limit=150)
            else:
                closed_trades = []
        except Exception:
            closed_trades = []

        return compute_drawings_from_candles(
            symbol=canon,
            chart_tf=tf_upper,
            candles_by_tf=candles_by_tf,
            positions=positions,
            pending_signals=pending_signals,
            closed_trades=closed_trades,
            config_dir=self.project_root / "config",
            broker_symbol=broker_symbol,
        )
