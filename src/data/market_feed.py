"""
Live MetaTrader 5 Market Data Feed, Symbol Mapping, Freshness/Market-Closed Guards,
and Broker-to-UTC Time Conversion.

REAL DATA ONLY: No hardcoded prices, spreads, volumes, or account figures exist here.
All live quotes, spreads, OHLC bars, and contract specs come directly from MT5.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_BROKER_SYMBOL_MAP: Dict[str, str] = {
    "XAUUSD": "XAUUSD.m",
    "USDJPY": "USDJPY.m",
    "BTCUSD": "BTCUSD.m",
}

DEFAULT_MAX_TICK_AGE_SECONDS: float = 30.0

# MT5 SYMBOL_TRADE_MODE constants
TRADE_MODE_DISABLED = 0
TRADE_MODE_LONGONLY = 1
TRADE_MODE_SHORTONLY = 2
TRADE_MODE_CLOSEONLY = 3
TRADE_MODE_FULL = 4

TRADE_MODE_LABELS: Dict[int, str] = {
    TRADE_MODE_DISABLED: "DISABLED",
    TRADE_MODE_LONGONLY: "LONGONLY",
    TRADE_MODE_SHORTONLY: "SHORTONLY",
    TRADE_MODE_CLOSEONLY: "CLOSEONLY",
    TRADE_MODE_FULL: "FULL",
}

TIMEFRAME_MINUTES: Dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


class SymbolMappingError(RuntimeError):
    """Raised when a configured canonical symbol cannot be resolved or selected in MT5."""


@dataclass
class FreshnessResult:
    is_stale: bool
    is_market_closed: bool
    entries_blocked: bool
    tick_age_sec: Optional[float]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_broker_symbol_map(config_dir: str | Path = "config") -> Dict[str, str]:
    """Loads canonical -> broker symbol mapping from config/instruments.json."""
    inst_path = Path(config_dir) / "instruments.json"
    if inst_path.exists():
        try:
            data = json.loads(inst_path.read_text(encoding="utf-8"))
            mapping = data.get("broker_symbol_map")
            if isinstance(mapping, dict) and mapping:
                return {str(k).upper(): str(v) for k, v in mapping.items()}
        except Exception:
            pass
    return dict(DEFAULT_BROKER_SYMBOL_MAP)


def load_freshness_limits(config_dir: str | Path = "config") -> Dict[str, float]:
    inst_path = Path(config_dir) / "instruments.json"
    if inst_path.exists():
        try:
            data = json.loads(inst_path.read_text(encoding="utf-8"))
            fg = data.get("freshness_guard", {})
            return {
                "max_tick_age_seconds": float(fg.get("max_tick_age_seconds", DEFAULT_MAX_TICK_AGE_SECONDS)),
                "stale_ui_warning_seconds": float(fg.get("stale_ui_warning_seconds", 15.0)),
            }
        except Exception:
            pass
    return {
        "max_tick_age_seconds": DEFAULT_MAX_TICK_AGE_SECONDS,
        "stale_ui_warning_seconds": 15.0,
    }


def resolve_broker_symbol(canonical: str, symbol_map: Dict[str, str]) -> str:
    """Resolves a canonical or broker symbol to the configured broker symbol. Raises if unmapped."""
    raw = str(canonical).strip()
    upper = raw.upper()
    if upper in symbol_map:
        return symbol_map[upper]
    # Check if already a mapped broker symbol
    for mapped in symbol_map.values():
        if mapped.upper() == upper:
            return mapped
    raise SymbolMappingError(
        f"Unmapped symbol '{canonical}'. Configured canonical symbols: {sorted(symbol_map.keys())}"
    )


def validate_broker_symbols(mt5: Any, symbol_map: Dict[str, str]) -> Dict[str, str]:
    """
    Validates at startup that every mapped broker symbol exists in MT5 (symbols_get)
    and can be selected in Market Watch (symbol_select). Fails loudly if missing.
    """
    if mt5 is None:
        raise SymbolMappingError("MetaTrader5 module is unavailable; cannot validate broker symbols.")

    available = mt5.symbols_get() or []
    available_names = {str(getattr(s, "name", "")): s for s in available}
    missing: List[str] = []
    unselectable: List[str] = []

    for canonical, broker_sym in symbol_map.items():
        if broker_sym not in available_names:
            missing.append(f"{canonical}->{broker_sym}")
            continue
        select_fn = getattr(mt5, "symbol_select", None)
        if callable(select_fn) and not select_fn(broker_sym, True):
            unselectable.append(f"{canonical}->{broker_sym}")

    if missing or unselectable:
        parts = []
        if missing:
            parts.append(f"missing from MT5: {', '.join(missing)}")
        if unselectable:
            parts.append(f"symbol_select failed: {', '.join(unselectable)}")
        raise SymbolMappingError("Broker symbol validation failed — " + "; ".join(parts))

    return dict(symbol_map)


def compute_spread_points(bid: float, ask: float, point: float) -> int:
    """Computes live spread in broker points from (ask - bid) / point."""
    if point <= 0 or bid <= 0 or ask <= 0 or ask < bid:
        return 0
    return int(round((ask - bid) / point))


def round_price_for_symbol(price: float, digits: int) -> float:
    """Rounds a price strictly to the broker symbol's decimal digits."""
    return round(float(price), max(0, int(digits)))


def round_volume_for_symbol(
    volume: float,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> float:
    """Rounds and clamps a lot size to the broker symbol's min/max/step specification."""
    if volume_step <= 0:
        volume_step = 0.01
    clamped = max(volume_min, min(volume_max, float(volume)))
    steps = math.floor((clamped - volume_min) / volume_step + 1e-9)
    rounded = volume_min + steps * volume_step
    # Determine precision from volume_step
    step_str = f"{volume_step:.8f}".rstrip("0")
    decimals = len(step_str.split(".")[1]) if "." in step_str else 0
    return round(max(volume_min, min(volume_max, rounded)), decimals)


def detect_broker_utc_offset_sec(
    mt5: Any,
    probe_symbols: Tuple[str, ...] = ("BTCUSD.m", "BTCUSD", "XAUUSD.m", "USDJPY.m"),
    now_utc: Optional[datetime] = None,
) -> int:
    """
    Infers the broker MT5 server UTC offset (rounded to the nearest 30-minute boundary)
    by comparing a live tick's broker timestamp against current UTC time.
    """
    if mt5 is None:
        return 0
    now_ts = (now_utc or datetime.now(timezone.utc)).timestamp()
    for sym in probe_symbols:
        try:
            tick = mt5.symbol_info_tick(sym)
            t_raw = int(getattr(tick, "time", 0)) if tick else 0
            if t_raw > 0:
                diff = t_raw - now_ts
                # Only trust live ticks within +/- 14 hours of UTC
                if abs(diff) <= 14 * 3600:
                    return int(round(diff / 1800.0) * 1800)
        except Exception:
            continue
    return 0


def convert_broker_time_to_utc(
    broker_timestamp_sec: float,
    broker_utc_offset_sec: int = 0,
) -> datetime:
    """Explicitly converts a broker server unix timestamp to timezone-aware UTC datetime."""
    utc_ts = float(broker_timestamp_sec) - float(broker_utc_offset_sec)
    return datetime.fromtimestamp(utc_ts, tz=timezone.utc)


def convert_utc_to_broker_time(
    utc_dt: datetime,
    broker_utc_offset_sec: int = 0,
) -> datetime:
    """Explicitly converts a UTC datetime to broker server time."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    else:
        utc_dt = utc_dt.astimezone(timezone.utc)
    broker_tz = timezone(timedelta(seconds=int(broker_utc_offset_sec)))
    return utc_dt.astimezone(broker_tz)


def get_active_session_utc(utc_dt: datetime) -> Dict[str, Any]:
    """
    Computes trading session & weekend/weekday schedule strictly from UTC datetime.
    Forex/Gold closed from Fri 21:00 UTC to Sun 22:00 UTC; BTC trades 24/7.
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    else:
        utc_dt = utc_dt.astimezone(timezone.utc)

    wd = utc_dt.weekday()  # Mon=0 .. Sun=6
    hour = utc_dt.hour
    is_fx_weekend = (wd == 4 and hour >= 21) or (wd == 5) or (wd == 6 and hour < 22)

    if is_fx_weekend:
        return {
            "schedule_mode": "WEEKEND_BTC_MODE",
            "session": "WEEKEND_CRYPTO_24_7",
            "fx_market_open": False,
            "btc_market_open": True,
            "utc_iso": utc_dt.isoformat(),
        }

    if 0 <= hour < 7:
        sess = "ASIAN"
    elif 7 <= hour < 13:
        sess = "LONDON"
    elif 13 <= hour < 16:
        sess = "LDN_NY_OVERLAP"
    elif 16 <= hour < 21:
        sess = "NEW_YORK"
    else:
        sess = "ROLLOVER"

    return {
        "schedule_mode": "WEEKDAY_GOLD_MODE",
        "session": sess,
        "fx_market_open": True,
        "btc_market_open": True,
        "utc_iso": utc_dt.isoformat(),
    }


def evaluate_freshness(
    tick_time_utc: Optional[datetime],
    now_utc: datetime,
    max_age_sec: float = DEFAULT_MAX_TICK_AGE_SECONDS,
    trade_mode: int = TRADE_MODE_FULL,
    prev_tick_time_utc: Optional[datetime] = None,
    stale_check_cycles: int = 0,
) -> FreshnessResult:
    """
    Evaluates live tick freshness and market-closed guards.
    Blocks entries when:
      1. trade_mode is DISABLED (0) or CLOSEONLY (3) -> Market closed
      2. tick_time_utc is missing or age > max_age_sec -> Stale / Market closed
      3. tick time has not advanced across repeated checks while age > max_age_sec
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    if trade_mode in (TRADE_MODE_DISABLED, TRADE_MODE_CLOSEONLY):
        age = max(0.0, (now_utc - tick_time_utc).total_seconds()) if tick_time_utc else None
        return FreshnessResult(
            is_stale=True,
            is_market_closed=True,
            entries_blocked=True,
            tick_age_sec=round(age, 1) if age is not None else None,
            reason=f"Market closed (trade_mode={TRADE_MODE_LABELS.get(trade_mode, str(trade_mode))})",
        )

    if tick_time_utc is None:
        return FreshnessResult(
            is_stale=True,
            is_market_closed=False,
            entries_blocked=True,
            tick_age_sec=None,
            reason="No tick received from MT5",
        )

    if tick_time_utc.tzinfo is None:
        tick_time_utc = tick_time_utc.replace(tzinfo=timezone.utc)

    age_sec = max(0.0, (now_utc - tick_time_utc).total_seconds())

    # If tick is older than 10 minutes on an FX/metals symbol, treat as market closed
    if age_sec > 600.0:
        return FreshnessResult(
            is_stale=True,
            is_market_closed=True,
            entries_blocked=True,
            tick_age_sec=round(age_sec, 1),
            reason=f"Market closed (last tick {int(age_sec)}s ago)",
        )

    if age_sec > max_age_sec:
        return FreshnessResult(
            is_stale=True,
            is_market_closed=False,
            entries_blocked=True,
            tick_age_sec=round(age_sec, 1),
            reason=f"Stale tick ({age_sec:.1f}s > {max_age_sec:.0f}s limit)",
        )

    if (
        prev_tick_time_utc is not None
        and tick_time_utc == prev_tick_time_utc
        and stale_check_cycles >= 5
        and age_sec >= max_age_sec * 0.5
    ):
        return FreshnessResult(
            is_stale=True,
            is_market_closed=False,
            entries_blocked=True,
            tick_age_sec=round(age_sec, 1),
            reason="Tick timestamp not advancing",
        )

    return FreshnessResult(
        is_stale=False,
        is_market_closed=False,
        entries_blocked=False,
        tick_age_sec=round(age_sec, 1),
        reason="LIVE",
    )


def fetch_live_quote(
    mt5: Any,
    broker_symbol: str,
    canonical_symbol: str,
    max_age_sec: float = DEFAULT_MAX_TICK_AGE_SECONDS,
    broker_utc_offset_sec: int = 0,
    now_utc: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Pulls live tick + contract specifications directly from MT5 for one broker symbol."""
    if mt5 is None:
        return None
    now = now_utc or datetime.now(timezone.utc)
    sym_info = mt5.symbol_info(broker_symbol)
    if sym_info is None:
        return None
    tick = mt5.symbol_info_tick(broker_symbol)
    digits = int(getattr(sym_info, "digits", 2))
    point = float(getattr(sym_info, "point", 0.01))
    trade_mode = int(getattr(sym_info, "trade_mode", TRADE_MODE_FULL))

    bid = round_price_for_symbol(float(getattr(tick, "bid", 0.0)), digits) if tick else 0.0
    ask = round_price_for_symbol(float(getattr(tick, "ask", 0.0)), digits) if tick else 0.0
    tick_ts = int(getattr(tick, "time", 0)) if tick else 0
    tick_vol = int(getattr(tick, "volume", 0)) if tick else 0
    tick_time_utc = (
        convert_broker_time_to_utc(tick_ts, broker_utc_offset_sec) if tick_ts > 0 else None
    )

    spread_points = compute_spread_points(bid, ask, point)
    freshness = evaluate_freshness(
        tick_time_utc=tick_time_utc,
        now_utc=now,
        max_age_sec=max_age_sec,
        trade_mode=trade_mode,
    )

    return {
        "canonical": canonical_symbol,
        "symbol": broker_symbol,
        "bid": bid,
        "ask": ask,
        "spread_points": spread_points,
        "digits": digits,
        "point": point,
        "tick_size": float(getattr(sym_info, "trade_tick_size", point)),
        "tick_value": float(getattr(sym_info, "trade_tick_value", 0.0)),
        "contract_size": float(getattr(sym_info, "trade_contract_size", 0.0)),
        "volume_min": float(getattr(sym_info, "volume_min", 0.01)),
        "volume_max": float(getattr(sym_info, "volume_max", 0.0)),
        "volume_step": float(getattr(sym_info, "volume_step", 0.01)),
        "stops_level": int(getattr(sym_info, "trade_stops_level", 0)),
        "trade_mode": trade_mode,
        "trade_mode_label": TRADE_MODE_LABELS.get(trade_mode, str(trade_mode)),
        "tick_volume": tick_vol,
        "tick_time_utc": tick_time_utc.isoformat() if tick_time_utc else None,
        "tick_age_sec": freshness.tick_age_sec,
        "stale": freshness.is_stale,
        "market_closed": freshness.is_market_closed,
        "entries_blocked": freshness.entries_blocked,
        "freshness_reason": freshness.reason,
        "source": "MT5",
    }


def _resolve_mt5_timeframe(mt5: Any, tf: str) -> Optional[int]:
    tf_upper = str(tf).upper().strip()
    attr = f"TIMEFRAME_{tf_upper}"
    val = getattr(mt5, attr, None)
    if val is not None:
        return int(val)
    return None


def fetch_ohlc_candles(
    mt5: Any,
    broker_symbol: str,
    timeframe: str = "M5",
    count: int = 120,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
    broker_utc_offset_sec: int = 0,
) -> List[Dict[str, Any]]:
    """Fetches real OHLCV candles directly from MT5 via copy_rates_from_pos or copy_rates_range."""
    if mt5 is None:
        return []
    mt5_tf = _resolve_mt5_timeframe(mt5, timeframe)
    if mt5_tf is None:
        return []

    rates = None
    try:
        if start_utc is not None and end_utc is not None:
            fn_range = getattr(mt5, "copy_rates_range", None)
            if callable(fn_range):
                s_naive = convert_utc_to_broker_time(start_utc, broker_utc_offset_sec).replace(tzinfo=None)
                e_naive = convert_utc_to_broker_time(end_utc, broker_utc_offset_sec).replace(tzinfo=None)
                rates = fn_range(broker_symbol, mt5_tf, s_naive, e_naive)
        else:
            fn_pos = getattr(mt5, "copy_rates_from_pos", None)
            if callable(fn_pos):
                rates = fn_pos(broker_symbol, mt5_tf, 0, max(1, min(1000, int(count))))
    except Exception:
        return []

    if rates is None or len(rates) == 0:
        return []

    candles: List[Dict[str, Any]] = []
    for bar in rates:
        # Works for both numpy structured records and dicts
        if isinstance(bar, dict):
            t_raw = int(bar["time"])
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            v = int(bar.get("tick_volume", bar.get("volume", 0)))
        else:
            t_raw = int(bar["time"])
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            v = int(bar["tick_volume"]) if "tick_volume" in bar.dtype.names else 0
        t_utc = int(t_raw - broker_utc_offset_sec)
        candles.append({
            "time": t_utc,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
    return candles
