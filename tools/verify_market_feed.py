"""
Read-Only Live MT5 Market Feed Verifier.
Connects to the running MetaTrader 5 DEMO terminal (never places or modifies orders),
validates canonical -> broker .m symbol mappings, and prints real-time quotes,
spreads (points), tick times/ages, tick volumes, digits, trade modes, and account balance/equity.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.market_feed import (
    SymbolMappingError,
    detect_broker_utc_offset_sec,
    fetch_live_quote,
    get_active_session_utc,
    load_broker_symbol_map,
    load_freshness_limits,
    validate_broker_symbols,
)


def main() -> int:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("ERROR: MetaTrader5 Python package is not installed.", file=sys.stderr)
        return 2

    if not mt5.initialize():
        print(f"ERROR: mt5.initialize() failed: {mt5.last_error()}", file=sys.stderr)
        return 1

    try:
        now_utc = datetime.now(timezone.utc)
        symbol_map = load_broker_symbol_map(PROJECT_ROOT / "config")
        limits = load_freshness_limits(PROJECT_ROOT / "config")
        max_age = limits["max_tick_age_seconds"]

        print("=" * 76)
        print("INSTITUTIONAL EA — LIVE MT5 MARKET FEED VERIFICATION (READ-ONLY)")
        print(f"UTC Now : {now_utc.isoformat()}")
        sched = get_active_session_utc(now_utc)
        print(f"Schedule: {sched['schedule_mode']} | Session: {sched['session']}")
        print("=" * 76)

        acct = mt5.account_info()
        if acct is None:
            print("ACCOUNT : UNAVAILABLE (no active MT5 account logged in)")
        else:
            mode = "DEMO" if int(getattr(acct, "trade_mode", 0)) == 0 else "REAL"
            floating = round(float(acct.equity) - float(acct.balance), 2)
            print(
                f"ACCOUNT : mode={mode} | broker={getattr(acct, 'company', 'MT5')} | "
                f"currency={acct.currency} | balance={acct.balance:.2f} | "
                f"equity={acct.equity:.2f} | floating={floating:+.2f} | "
                f"leverage=1:{acct.leverage}"
            )
            positions = mt5.positions_get() or []
            print(f"OPEN POS: {len(positions)} open position(s)")

        print("-" * 76)
        try:
            validate_broker_symbols(mt5, symbol_map)
            print(f"SYMBOL MAPPING: VALIDATED ({symbol_map})")
        except SymbolMappingError as exc:
            print(f"SYMBOL MAPPING WARNING: {exc}")

        broker_offset = detect_broker_utc_offset_sec(mt5, now_utc=now_utc)
        print(f"Broker Offset: UTC{broker_offset / 3600:+.1f}h ({broker_offset}s)")
        print("-" * 76)
        header = (
            f"{'CANONICAL':<9} {'BROKER':<10} {'BID':>11} {'ASK':>11} "
            f"{'SPR(pt)':>8} {'DIG':>3} {'VOL':>6} {'AGE(s)':>8} {'MODE':<10} {'STATUS'}"
        )
        print(header)
        print("-" * 76)

        quotes = []
        for canonical, broker_sym in symbol_map.items():
            q = fetch_live_quote(
                mt5=mt5,
                broker_symbol=broker_sym,
                canonical_symbol=canonical,
                max_age_sec=max_age,
                broker_utc_offset_sec=broker_offset,
                now_utc=now_utc,
            )
            if q is None:
                print(f"{canonical:<9} {broker_sym:<10} {'MISSING':>11}")
                continue
            quotes.append(q)
            dig = q["digits"]
            age_str = f"{q['tick_age_sec']:.1f}" if q["tick_age_sec"] is not None else "N/A"
            status_str = "MARKET_CLOSED" if q["market_closed"] else ("STALE" if q["stale"] else "LIVE")
            print(
                f"{canonical:<9} {q['symbol']:<10} {q['bid']:>11.{dig}f} {q['ask']:>11.{dig}f} "
                f"{q['spread_points']:>8d} {dig:>3d} {q['tick_volume']:>6d} {age_str:>8} "
                f"{q['trade_mode_label']:<10} {status_str} ({q['freshness_reason']})"
            )
            print(
                f"          last_tick_utc={q['tick_time_utc']} | point={q['point']} | "
                f"stops_lvl={q['stops_level']} | contract={q['contract_size']}"
            )

        print("=" * 76)
        if "--json" in sys.argv:
            print(json.dumps({"utc_now": now_utc.isoformat(), "quotes": quotes}, indent=2))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
