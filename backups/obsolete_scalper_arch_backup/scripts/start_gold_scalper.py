"""
Main Entry Point: Dedicated High-Frequency GOLD Scalper Engine.
Executes the continuous tick-by-tick scalping cycle on XAUUSD:
Analyze -> Select Direction -> Open Basket -> Monitor Profit -> Close Basket -> Re-enter.
"""

from __future__ import annotations
import argparse
import os
from pathlib import Path
import signal
import sys
import time

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.app_paths import SingleInstanceLock
from src.scalper.config import ScalperConfig
from src.scalper.engine import GoldScalperEngine


def _handle_term(signum, frame):
    raise KeyboardInterrupt


try:
    signal.signal(signal.SIGTERM, _handle_term)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_term)
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser(description="Dedicated High-Frequency GOLD (XAUUSD) Scalping Engine")
    parser.add_argument("--config", type=str, default="config/scalper.yaml", help="Path to scalper YAML configuration")
    parser.add_argument("--simulation", action="store_true", help="Run in simulation mode without sending live MT5 orders")
    parser.add_argument("--max-cycles", type=int, default=0, help="Maximum tick cycles to execute (0 = continuous)")
    parser.add_argument("--interval-ms", type=int, default=0, help="Override execution loop interval in milliseconds")
    parser.add_argument(
        "--liquidate-on-exit",
        action="store_true",
        help="Force liquidation of open scalper positions on Ctrl+C or max-cycles exit (default: preserve open positions)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("  GOLD SCALPER ENGINE — DEDICATED HIGH-FREQUENCY MT5 SYSTEM")
    print("=" * 80)

    # 1. Acquire Single Instance Lock
    lock = SingleInstanceLock("mt5_gold_scalper_engine")
    if not lock.acquire():
        print("[SINGLE_INSTANCE] Another Gold Scalper Engine is already running. Exiting cleanly.")
        return 0

    engine = None
    exit_code = 0
    try:
        cfg = ScalperConfig.load(args.config)
        if args.interval_ms > 0:
            cfg.execution_loop.interval_ms = args.interval_ms

        for warn_msg in getattr(cfg, "config_warnings", []):
            print(f"[CONFIG_WARNING] {warn_msg}")

        print(f"[CONFIG] Engine: {cfg.general.engine_name} v{cfg.general.version}")
        print(f"[CONFIG] Target Symbol: {cfg.symbol.target_canonical} (Auto-resolve: {cfg.symbol.auto_detect_broker_symbol})")
        print(f"[CONFIG] Basket Size: {cfg.basket.basket_size} positions | Aggregate TP: ${cfg.basket_tp.basket_tp_usd:.2f}")
        print(f"[CONFIG] Individual TP: ${cfg.individual_tp.tp_usd_per_min_lot:.2f} per 0.01 lot | Max Hold: {cfg.holding_time.max_hold_seconds}s")
        print(f"[CONFIG] Execution Interval: {cfg.execution_loop.interval_ms}ms | DEMO_MODE: {cfg.safety_mode.DEMO_MODE}")
        print(f"[CONFIG] Protective SL: {cfg.protective_sl.sl_points} points | Max Positions: {cfg.position_limits.max_open_positions}")

        engine = GoldScalperEngine(config=cfg, is_simulation=args.simulation)
        if not engine.initialize():
            print("[FATAL] Engine initialization failed. Halting.")
            engine.shutdown(reason="INIT_FAILED", liquidate_positions=False)
            return 1

        print(f"\n[ACTIVE] Starting continuous tick execution loop on {engine.symbol_spec.symbol} (Press Ctrl+C to stop)...")
        cycle_interval_sec = max(0.05, cfg.execution_loop.interval_ms / 1000.0)

        cycles = 0
        while engine._is_running:
            cycles += 1
            start_t = time.time()

            engine.run_single_tick_cycle()

            if cycles % 20 == 0:
                stats = engine.stats
                print(
                    f"[STATUS] Cycle {cycles} | Baskets Opened/Closed: {stats.total_baskets_opened}/{stats.total_baskets_closed} | "
                    f"Fills: {stats.total_orders_filled} | Net P/L: ${stats.net_profit_usd:.2f} | Max DD: {stats.max_floating_drawdown_pct}%"
                )

            if args.max_cycles > 0 and cycles >= args.max_cycles:
                print(f"[COMPLETE] Finished scheduled {cycles} cycles.")
                engine.shutdown(reason="MAX_CYCLES_COMPLETED", liquidate_positions=args.liquidate_on_exit)
                break

            elapsed = time.time() - start_t
            sleep_for = max(0.01, cycle_interval_sec - elapsed)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Operator interrupted execution (Ctrl+C). Stopping cleanly...")
        if engine is not None:
            engine.shutdown(reason="OPERATOR_INTERRUPT", liquidate_positions=args.liquidate_on_exit)
    except Exception as exc:
        print(f"\n[ERROR] Unhandled exception in gold scalper loop: {exc}")
        exit_code = 1
        if engine is not None:
            engine.shutdown(reason=f"UNHANDLED_EXCEPTION:{type(exc).__name__}", liquidate_positions=False)
        raise
    finally:
        if engine is not None:
            engine.shutdown(reason="FINALLY_CLEANUP", liquidate_positions=False)
        lock.release()
        print("[SHUTDOWN] Single instance lock released. Engine terminated.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
