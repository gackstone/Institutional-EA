"""
Unit tests for live market feed utilities (src/data/market_feed.py).
Uses clearly-labeled test fixtures only (no real account numbers or reference screenshot prices).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.data.market_feed import (
    SymbolMappingError,
    TRADE_MODE_CLOSEONLY,
    TRADE_MODE_DISABLED,
    TRADE_MODE_FULL,
    compute_spread_points,
    convert_broker_time_to_utc,
    convert_utc_to_broker_time,
    evaluate_freshness,
    fetch_live_quote,
    fetch_ohlc_candles,
    get_active_session_utc,
    resolve_broker_symbol,
    round_price_for_symbol,
    round_volume_for_symbol,
    validate_broker_symbols,
)


class _FixtureMT5:
    """Clearly-labeled in-memory MT5 test fixture for deterministic unit testing."""

    TIMEFRAME_M5 = 5

    def __init__(self, symbols_list, ticks_by_sym, rates_by_sym=None):
        self._symbols = {s.name: s for s in symbols_list}
        self._ticks = ticks_by_sym
        self._rates = rates_by_sym or {}

    def symbols_get(self):
        return list(self._symbols.values())

    def symbol_select(self, name, enable):
        return name in self._symbols

    def symbol_info(self, name):
        return self._symbols.get(name)

    def symbol_info_tick(self, name):
        return self._ticks.get(name)

    def copy_rates_from_pos(self, name, tf, start, count):
        return self._rates.get(name, [])[:count]


def test_symbol_mapping_resolution_and_validation():
    sym_map = {"XAUUSD": "XAUUSD.m", "USDJPY": "USDJPY.m", "BTCUSD": "BTCUSD.m"}
    assert resolve_broker_symbol("XAUUSD", sym_map) == "XAUUSD.m"
    assert resolve_broker_symbol("usdjpy", sym_map) == "USDJPY.m"
    assert resolve_broker_symbol("BTCUSD.m", sym_map) == "BTCUSD.m"

    with pytest.raises(SymbolMappingError):
        resolve_broker_symbol("EURUSD", sym_map)

    fixture_ok = _FixtureMT5(
        symbols_list=[
            SimpleNamespace(name="XAUUSD.m"),
            SimpleNamespace(name="USDJPY.m"),
            SimpleNamespace(name="BTCUSD.m"),
        ],
        ticks_by_sym={},
    )
    assert validate_broker_symbols(fixture_ok, sym_map) == sym_map

    fixture_missing = _FixtureMT5(
        symbols_list=[SimpleNamespace(name="XAUUSD.m")],
        ticks_by_sym={},
    )
    with pytest.raises(SymbolMappingError):
        validate_broker_symbols(fixture_missing, sym_map)


def test_spread_math_and_per_symbol_rounding():
    # Gold (2 digits, point 0.01)
    assert compute_spread_points(3400.10, 3400.35, 0.01) == 25
    assert round_price_for_symbol(3400.126, 2) == 3400.13

    # USDJPY (3 digits, point 0.001)
    assert compute_spread_points(150.100, 150.116, 0.001) == 16
    assert round_price_for_symbol(150.1167, 3) == 150.117

    # BTCUSD (2 digits, point 0.01)
    assert compute_spread_points(60000.00, 60015.50, 0.01) == 1550

    # Invalid / inverted spread guard
    assert compute_spread_points(100.0, 99.0, 0.01) == 0
    assert compute_spread_points(0.0, 100.0, 0.01) == 0

    # Lot size rounding & clamping
    assert round_volume_for_symbol(0.127, 0.01, 50.0, 0.01) == 0.12
    assert round_volume_for_symbol(0.002, 0.01, 50.0, 0.01) == 0.01
    assert round_volume_for_symbol(75.0, 0.01, 50.0, 0.01) == 50.0


def test_freshness_and_market_closed_guards():
    now = datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc)

    # Fresh tick (5s old, trade_mode FULL)
    res_live = evaluate_freshness(now - timedelta(seconds=5), now, max_age_sec=30, trade_mode=TRADE_MODE_FULL)
    assert not res_live.is_stale
    assert not res_live.is_market_closed
    assert not res_live.entries_blocked

    # Stale tick (45s old > 30s limit)
    res_stale = evaluate_freshness(now - timedelta(seconds=45), now, max_age_sec=30, trade_mode=TRADE_MODE_FULL)
    assert res_stale.is_stale
    assert not res_stale.is_market_closed
    assert res_stale.entries_blocked

    # Market closed via trade_mode=DISABLED or CLOSEONLY
    res_closed_mode = evaluate_freshness(now - timedelta(seconds=2), now, max_age_sec=30, trade_mode=TRADE_MODE_DISABLED)
    assert res_closed_mode.is_market_closed
    assert res_closed_mode.entries_blocked

    res_closeonly = evaluate_freshness(now - timedelta(seconds=2), now, max_age_sec=30, trade_mode=TRADE_MODE_CLOSEONLY)
    assert res_closeonly.is_market_closed
    assert res_closeonly.entries_blocked

    # Market closed via old weekend tick (>600s old)
    res_weekend = evaluate_freshness(now - timedelta(hours=12), now, max_age_sec=30, trade_mode=TRADE_MODE_FULL)
    assert res_weekend.is_market_closed
    assert res_weekend.entries_blocked

    # Frozen tick timestamp (not advancing)
    frozen_t = now - timedelta(seconds=20)
    res_frozen = evaluate_freshness(
        frozen_t, now, max_age_sec=30, trade_mode=TRADE_MODE_FULL, prev_tick_time_utc=frozen_t, stale_check_cycles=6
    )
    assert res_frozen.is_stale
    assert res_frozen.entries_blocked


def test_broker_to_utc_time_conversion_and_sessions():
    # Broker server UTC+3 (10800s ahead of UTC)
    utc_ref = datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc)
    broker_ts = int(utc_ref.timestamp()) + 10800
    converted = convert_broker_time_to_utc(broker_ts, broker_utc_offset_sec=10800)
    assert converted == utc_ref

    broker_dt = convert_utc_to_broker_time(utc_ref, broker_utc_offset_sec=10800)
    assert broker_dt.hour == 17

    # Weekday London/NY overlap (Wed 14:00 UTC)
    sess_overlap = get_active_session_utc(utc_ref)
    assert sess_overlap["schedule_mode"] == "WEEKDAY_GOLD_MODE"
    assert sess_overlap["session"] == "LDN_NY_OVERLAP"
    assert sess_overlap["fx_market_open"] is True

    # Weekend Saturday 12:00 UTC -> WEEKEND_BTC_MODE
    sat_utc = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
    sess_wknd = get_active_session_utc(sat_utc)
    assert sess_wknd["schedule_mode"] == "WEEKEND_BTC_MODE"
    assert sess_wknd["fx_market_open"] is False
    assert sess_wknd["btc_market_open"] is True


def test_fetch_live_quote_and_candles_from_fixture():
    now = datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc)
    tick_ts = int((now - timedelta(seconds=3)).timestamp())
    sym_fixture = SimpleNamespace(
        name="USDJPY.m",
        digits=3,
        point=0.001,
        trade_tick_size=0.001,
        trade_tick_value=0.65,
        trade_contract_size=100000.0,
        volume_min=0.01,
        volume_max=50.0,
        volume_step=0.01,
        trade_stops_level=5,
        trade_mode=TRADE_MODE_FULL,
    )
    tick_fixture = SimpleNamespace(bid=150.200, ask=150.214, time=tick_ts, volume=12)
    bar_fixture = [
        {"time": tick_ts - 300, "open": 150.100, "high": 150.250, "low": 150.050, "close": 150.200, "tick_volume": 85}
    ]
    mt5_fix = _FixtureMT5([sym_fixture], {"USDJPY.m": tick_fixture}, {"USDJPY.m": bar_fixture})

    quote = fetch_live_quote(mt5_fix, "USDJPY.m", "USDJPY", max_age_sec=30, now_utc=now)
    assert quote is not None
    assert quote["spread_points"] == 14
    assert quote["stale"] is False
    assert quote["source"] == "MT5"

    candles = fetch_ohlc_candles(mt5_fix, "USDJPY.m", "M5", count=10)
    assert len(candles) == 1
    assert candles[0]["close"] == 150.200
    assert candles[0]["volume"] == 85
