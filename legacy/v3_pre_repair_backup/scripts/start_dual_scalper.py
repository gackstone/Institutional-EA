"""
Main Entry Point: Dual-Market Calendar-Aware Scalper Engine (GOLD + BTCUSD).
Routes trading automatically based on the configured calendar:
- MONDAY – FRIDAY: GOLD (XAUUSD) active for new entries
- SATURDAY – SUNDAY: BITCOIN (BTCUSD) active for new entries
- ALL DAYS: Continuous monitoring and lifecycle management of existing positions across transitions
"""

from __future__ import annotations
import argparse
from pathlib import Path
import signal
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.app_paths import SingleInstanceLock
from src.scalper.config import ScalperConfig
from src.scalper.engine import DualMarketScalperEngine


def _handle_term(signum, frame):
    raise KeyboardInterrupt


try:
    signal.signal(signal.SIGTERM, _handle_term)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_term)
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser(description="Dual-Market Calendar-Aware Scalping Engine (GOLD + BTCUSD)")
    parser.add_argument("--config", type=str, default="config/scalper.yaml", help="Path to scalper YAML configuration")
    parser.add_argument("--simulation", action="store_true", help="Run in simulation mode without sending live MT5 orders")
    parser.add_argument("--max-cycles", type=int, default=0, help="Maximum tick cycles to execute (0 = continuous)")
    parser.add_argument("--interval-ms", type=int, default=0, help="Override execution loop interval in milliseconds")
    args = parser.parse_args()

    print("=" * 80)
    print("  DUAL-MARKET SCALPER ENGINE — XAUUSD (WEEKDAYS) + BTCUSD (WEEKENDS)")
    print("=" * 80)

    lock = SingleInstanceLock("mt5_dual_market_scalper_engine")
    if not lock.acquire():
        print("[SINGLE_INSTANCE] Another Dual-Market Scalper Engine is already running. Exiting cleanly.")
        return 0

    try:
        cfg = ScalperConfig.load(args.config)
        if args.interval_ms > 0:
            cfg.general.EXECUTION_INTERVAL_MS = args.interval_ms
            cfg.execution_loop.interval_ms = args.interval_ms

        print(f"[CONFIG] Engine: {cfg.general.engine_name} v{cfg.general.version}")
        print(f"[CONFIG] Schedule: Weekdays -> {cfg.scheduler.weekday_symbol} | Weekends -> {cfg.scheduler.weekend_symbol} ({cfg.scheduler.timezone})")
        for sym_k, sym_cfg in cfg.symbols.items():
            print(
                f"[CONFIG] {sym_k:6s} | Canonical: {sym_cfg.canonical:6s} | Magic: {sym_cfg.magic_number} | "
                f"Basket: {sym_cfg.basket_size} pos | Basket TP: ${sym_cfg.basket_tp_usd:.2f} | "
                f"SL: {sym_cfg.sl_points} pts | Max Spread: {sym_cfg.spread_max_points} pts"
            )
        print(
            f"[CONFIG] Global Risk | Max Positions: {cfg.risk.max_open_positions} | Max Lots: {cfg.risk.max_total_lots} | "
            f"Max DD: {cfg.risk.max_dd_pct}% | Min Margin Level: {cfg.risk.min_margin_level_pct}% | DEMO_MODE: {cfg.general.DEMO_MODE}"
        )

        engine = DualMarketScalperEngine(config=cfg, is_simulation=args.simulation)
        if not engine.initialize():
            print("[FATAL] Engine initialization failed. Halting.")
            return 1

        active_key = engine.scheduler.get_scheduled_symbol_key()
        print(f"\n[ACTIVE] Starting dual-market loop (Current Scheduled Market: {active_key}) — Press Ctrl+C to stop...")
        cycle_interval_sec = max(0.05, cfg.general.EXECUTION_INTERVAL_MS / 1000.0)

        cycles = 0
        while engine._is_running:
            cycles += 1
            start_t = time.time()

            engine.run_single_tick_cycle()

            if cycles % 20 == 0:
                stats = engine.stats
                g_stats = engine.symbol_stats["GOLD"]
                b_stats = engine.symbol_stats["BTCUSD"]
                sched = engine.scheduler.get_scheduled_symbol_key()
                print(
                    f"[STATUS] Cycle {cycles} ({sched}) | Total Baskets: {stats.total_baskets_opened}/{stats.total_baskets_closed} "
                    f"(GOLD: {g_stats.total_baskets_opened}/{g_stats.total_baskets_closed}, BTC: {b_stats.total_baskets_opened}/{b_stats.total_baskets_closed}) | "
                    f"Net P/L: ${stats.net_profit_usd:.2f} | Max DD: {stats.max_floating_drawdown_pct}%"
                )

            if args.max_cycles > 0 and cycles >= args.max_cycles:
                print(f"[COMPLETE] Finished scheduled {cycles} cycles.")
                break

            elapsed = time.time() - start_t
            sleep_for = max(0.01, cycle_interval_sec - elapsed)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Operator interrupted execution (Ctrl+C). Stopping cleanly...")
        if "engine" in locals():
            engine.emergency_shutdown("OPERATOR_INTERRUPT")
    finally:
        lock.release()
        print("[SHUTDOWN] Single instance lock released. Engine terminated.")


if __name__ == "__main__":
    main()
