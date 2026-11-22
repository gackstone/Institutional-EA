"""
Dedicated Gold Scalper Engine: High-Frequency MT5 XAUUSD Scalping System.
Tick-responsive, multi-position layering, basket net profit realization,
and automated rescan loop.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import signal
import sys
import time

# Clean shutdown handler
def _handle_term(signum, frame):
    raise KeyboardInterrupt

try:
    signal.signal(signal.SIGTERM, _handle_term)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_term)
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("GoldScalper")

from src.core.config import AppConfig
from src.core.contracts import AccountInfo, ExecutionMode
from src.core.orchestrator import TradingBotOrchestrator
from src.core.app_paths import (
    SingleInstanceLock,
    clear_engine_heartbeat,
    get_state_dir,
    write_engine_heartbeat,
)


def _sync_account_from_mt5_direct(orchestrator: TradingBotOrchestrator) -> bool:
    """Synchronizes live account details directly via MetaTrader5 Python API."""
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            return False
        info = mt5.account_info()
        if info is None:
            return False
        trade_mode = "DEMO" if int(getattr(info, "trade_mode", 0)) == 0 else "REAL"
        profile_name = "RETAIL" if getattr(orchestrator.config, "execution_mode", None) == ExecutionMode.RETAIL else ("DEMO" if trade_mode == "DEMO" else "LIVE")
        acc = AccountInfo(
            account_number=int(info.login),
            balance=float(info.balance),
            raw_balance=float(info.balance),
            equity=float(info.equity),
            raw_equity=float(info.equity),
            margin=float(info.margin),
            free_margin=float(info.margin_free),
            margin_level=float(info.margin_level),
            currency=str(info.currency),
            raw_currency=str(info.currency),
            leverage=int(info.leverage),
            trade_mode=trade_mode,
            profile=profile_name,
            trading_enabled=True,
            broker_server=str(getattr(info, "server", "") or ""),
            company=str(getattr(info, "company", "") or ""),
            margin_mode=int(getattr(info, "margin_mode", 2)),
            margin_mode_str="NETTING" if int(getattr(info, "margin_mode", 2)) == 1 else "HEDGING",
        )
        orchestrator.update_account(acc)
        masked_login = f"***{str(acc.account_number)[-4:]}" if acc.account_number else "N/A"
        print(
            f"[ACCOUNT_MODE] Direct MT5 Synchronized: {acc.trade_mode} [{acc.margin_mode_str}] | "
            f"Account: {masked_login} | Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f}"
        )
        return True
    except Exception as e:
        logger.debug(f"Direct MT5 sync error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Dedicated Gold Scalper Engine — High-Frequency MT5 XAUUSD Scalping System")
    parser.add_argument("--dry-run", action="store_true", help="Run in safe dry-run mode without sending live orders")
    parser.add_argument("--max-cycles", type=int, default=0, help="Maximum scan cycles to run (0 = continuous)")
    parser.add_argument("--interval", type=float, default=0.25, help="Sleep interval in seconds between cycles")
    parser.add_argument("--basket-target", type=float, default=20.0, help="Basket net profit target in USD")
    parser.add_argument("--individual-target", type=float, default=10.0, help="Individual position net profit target in USD")
    args, _ = parser.parse_known_args()

    print("=" * 80)
    print("  DEDICATED GOLD SCALPER ENGINE — HIGH-FREQUENCY MT5 XAUUSD SCALPING SYSTEM")
    print("=" * 80)

    engine_lock = SingleInstanceLock("gold_scalper_engine")
    if not engine_lock.acquire():
        print("[SINGLE_INSTANCE] Another Gold Scalper Engine instance is already running. Exiting cleanly.")
        return 0

    state_dir = get_state_dir()
    engine_stop_flag = state_dir / "engine_stop.flag"
    try:
        engine_stop_flag.unlink(missing_ok=True)
    except Exception:
        pass

    started_ts = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()
    write_engine_heartbeat({
        "pid": os.getpid(),
        "status": "INITIALIZING",
        "system": "GOLD_SCALPER",
        "started_at": started_iso,
        "timestamp": started_iso,
        "epoch": started_ts,
        "uptime_seconds": 0.0,
        "cycles": 0,
        "account_number": 0,
        "bridge_connected": False,
    })

    config = AppConfig.load_from_dir()
    config.symbols = ["XAUUSD"]
    config.trading_mode = "CONTINUOUS_SCALPING"
    config.risk.basket_profit_target_usd = args.basket_target
    config.risk.individual_profit_target_usd = args.individual_target
    config.risk.tick_driven_execution = True
    config.risk.multi_position_execution = True
    config.risk.dynamic_position_layering = True

    if args.dry_run or "--dry-run" in sys.argv:
        config.dry_run = True
        print("[MODE] DRY-RUN MODE ENABLED: Simulating execution without broker orders.")

    print(
        f"Gold Scalper Active | Symbols: {', '.join(config.symbols)} | "
        f"Basket Target: ${config.risk.basket_profit_target_usd:.2f} | "
        f"Individual Target: ${config.risk.individual_profit_target_usd:.2f} | "
        f"Tick-Driven: ON | Multi-Position Layering: ON"
    )

    orchestrator = TradingBotOrchestrator(config)

    # In DEMO/REAL/RETAIL mode, connect to Bridge or direct MT5
    if config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL]:
        if orchestrator.bridge.connect():
            print("Connected to MT5 Bridge successfully.")
            acc = orchestrator.bridge.get_account()
            if acc:
                orchestrator.update_account(acc)
        else:
            print("[BRIDGE] Bridge not reachable; falling back to direct MT5 API...")
            _sync_account_from_mt5_direct(orchestrator)

    print("\n[WARMUP] Synchronizing Gold candle history...")
    orchestrator.initialize_market_data(max_retries=3)

    print("\nStarting high-frequency Gold tick & scalp loop (Press Ctrl+C to stop)...")
    try:
        cycles = 0
        while True:
            if engine_stop_flag.exists():
                print("\n[Shutdown] Graceful stop flag detected. Stopping cleanly...")
                break

            cycles += 1
            cycle_start = time.time()

            # Account sync every 10 cycles
            if cycles % 10 == 1 and config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL]:
                orchestrator.sync_account_from_bridge()

            # Manage active positions & baskets first
            orchestrator.manage_active_positions()

            # Execute tick-responsive scalping cycle for Gold
            broker_sym = orchestrator.symbol_universe.get_broker_symbol("XAUUSD")
            try:
                sig = orchestrator.run_scalping_cycle_for_symbol(broker_sym)
                if sig is not None:
                    logger.info(f"[SCALPING][INFO] Candidate processed on cycle #{cycles}: {sig.id}")
            except Exception as e:
                logger.debug(f"[ERROR] Isolated exception during Gold scan: {e}")

            # Re-evaluate open positions and baskets immediately
            orchestrator.manage_active_positions()

            if cycles % 20 == 0:
                cur_acc = getattr(orchestrator, "account_info", None)
                bal = getattr(cur_acc, "balance", 0.0) if cur_acc else 0.0
                eq = getattr(cur_acc, "equity", 0.0) if cur_acc else 0.0
                open_pos = orchestrator.order_manager.get_active_positions()
                print(f"[STATUS] Cycle #{cycles} | Open Gold Positions: {len(open_pos)} | Balance: ${bal:.2f} | Equity: ${eq:.2f}")

            if args.max_cycles > 0 and cycles >= args.max_cycles:
                print(f"\n[COMPLETE] Reached scheduled limit of {cycles} cycles.")
                break

            elapsed = time.time() - cycle_start
            sleep_time = max(0.01, float(args.interval) - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[Shutdown] Stopping Gold Scalper safely...")
    finally:
        try:
            engine_stop_flag.unlink(missing_ok=True)
        except Exception:
            pass
        clear_engine_heartbeat()
        engine_lock.release()
        orchestrator.bridge.disconnect()
        print("[Shutdown] Gold Scalper stopped cleanly.")


if __name__ == "__main__":
    main()
