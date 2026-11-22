"""
MetaTrader 5 Synchronization & Reconciliation Service.
Detects MT5 installation/process, connects via BridgeClient or MetaTrader5 Python API,
verifies DEMO account mode, discovers Gold/BTC and configured symbol specifications,
reconciles broker-side positions/orders against bot-owned magic numbers, and handles
bounded exponential backoff reconnection.
"""

from __future__ import annotations
import os
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from companion.database.repository import CompanionRepository
from companion.service.events.event_bus import EventBus
from src.core.contracts import AccountInfo, Position, SymbolInfo
from src.execution.bridge_client import BridgeClient


COMMON_MT5_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\JustMarkets MT5 Terminal\terminal64.exe",
]


class MT5SyncService:
    def __init__(
        self,
        repo: CompanionRepository,
        events: EventBus,
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 5555,
        bot_magic: int = 100101,
        mt5_module: Any = None,
        bridge_client: Optional[BridgeClient] = None,
    ):
        self.repo = repo
        self.events = events
        self.bridge_host = bridge_host
        self.bridge_port = bridge_port
        self.bot_magic = int(bot_magic)
        self._mt5_override = mt5_module
        self.bridge = bridge_client or BridgeClient(host=bridge_host, port=bridge_port)

        self._lock = threading.RLock()
        self.connection_status: str = "DISCONNECTED"  # CONNECTED | DISCONNECTED | SYNCHRONIZING | ERROR
        self.last_sync_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.reconnect_attempts: int = 0
        self.max_backoff_sec: float = 30.0

        self.account: Dict[str, Any] = {
            "account_number": 0,
            "broker": "Not Connected",
            "currency": "USD",
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
            "margin_level": 0.0,
            "leverage": 100,
            "trade_mode": "UNKNOWN",
            "margin_mode_str": "HEDGING",
            "demo_verified": False,
            "netting_observe_only": False,
        }
        self.positions: List[Dict[str, Any]] = []
        self.pending_orders: List[Dict[str, Any]] = []
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.reconciliation_report: Dict[str, Any] = {
            "status": "NOT_SYNCED",
            "bot_owned_count": 0,
            "manual_count": 0,
            "other_ea_count": 0,
            "unexpected_tickets": [],
            "unprotected_bot_tickets": [],
            "timestamp": None,
        }
        self._previous_sl_tp: Dict[int, Tuple[float, float]] = {}

    def _get_mt5(self) -> Any:
        if self._mt5_override is not None:
            return self._mt5_override
        try:
            import MetaTrader5 as mt5
            return mt5
        except Exception:
            return None

    def detect_terminal(self) -> Dict[str, Any]:
        """Detects whether MetaTrader 5 is installed and whether terminal64.exe is running."""
        installed_paths = [p for p in COMMON_MT5_PATHS if Path(p).exists()]
        running = False
        if os.name == "nt":
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"],
                    text=True,
                    timeout=3,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                running = "terminal64.exe" in out.lower()
            except Exception:
                running = False
        return {
            "installed": len(installed_paths) > 0,
            "installed_paths": installed_paths,
            "running": running,
        }

    def connect(self) -> bool:
        """Connects via BridgeClient or direct MT5 API with bounded backoff tracking."""
        with self._lock:
            self.connection_status = "SYNCHRONIZING"
            try:
                if self.bridge.connect():
                    self.connection_status = "CONNECTED"
                    self.reconnect_attempts = 0
                    self.last_error = None
                    self.repo.record_connection_event("MT5_BRIDGE", "CONNECTED", f"Connected to {self.bridge_host}:{self.bridge_port}")
                    self.repo.resolve_component_errors("MT5SyncService", "MT5 Bridge connection restored")
                    self.events.log("MT5", "INFO", f"Connected to MT5 Bridge ({self.bridge_host}:{self.bridge_port})")
                    return True
            except Exception as exc:
                self.last_error = str(exc)

            # Fallback to direct MetaTrader5 API
            mt5 = self._get_mt5()
            if mt5 is not None:
                try:
                    if mt5.initialize():
                        self.connection_status = "CONNECTED"
                        self.reconnect_attempts = 0
                        self.last_error = None
                        self.repo.record_connection_event("MT5_DIRECT", "CONNECTED", "Connected via MetaTrader5 Python API")
                        self.repo.resolve_component_errors("MT5SyncService", "Direct MT5 terminal connection restored")
                        self.events.log("MT5", "INFO", "Connected to MT5 terminal via MetaTrader5 Python API")
                        return True
                except Exception as exc:
                    self.last_error = str(exc)

            self.reconnect_attempts += 1
            self.connection_status = "DISCONNECTED"
            err_msg = self.last_error or "Unable to connect to MT5 Bridge or MetaTrader 5 terminal."
            self.repo.record_connection_event("MT5", "DISCONNECTED", err_msg)
            self.repo.record_error(
                category="CONNECTION",
                severity="WARNING",
                component="MT5SyncService",
                message=err_msg,
                trading_affected=True,
                entries_blocked=True,
                recommended_recovery="Ensure MetaTrader 5 terminal is open and PythonBridgeEA is attached, or click Reconnect.",
                user_action_required=True,
            )
            self.events.log("MT5", "WARNING", f"MT5 connection failed (attempt {self.reconnect_attempts}): {err_msg}")
            return False

    def next_backoff_seconds(self) -> float:
        return min(self.max_backoff_sec, float(2 ** min(self.reconnect_attempts, 5)))

    def sync_all(self, target_symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Synchronizes account, symbols, positions, pending orders, and reconciliation state."""
        with self._lock:
            mt5 = self._get_mt5()
            acc_obj: Optional[AccountInfo] = None
            broker_name: str = "MetaTrader 5"
            raw_positions: List[Position] = []
            raw_orders: List[Dict[str, Any]] = []

            if self.bridge.is_connected():
                try:
                    acc_obj = self.bridge.get_account()
                    raw_positions = self.bridge.get_positions() or []
                    ord_res = self.bridge.send_request({"action": "ORDERS"})
                    if isinstance(ord_res, dict) and ord_res.get("status") == "SUCCESS":
                        raw_orders = list(ord_res.get("data", []))
                except Exception as exc:
                    self.last_error = str(exc)
                    self.connection_status = "DISCONNECTED"

            if acc_obj is None and mt5 is not None:
                try:
                    if mt5.initialize():
                        info = mt5.account_info()
                        if info is not None:
                            trade_mode = "DEMO" if int(getattr(info, "trade_mode", 0)) == 0 else "REAL"
                            margin_mode = int(getattr(info, "margin_mode", 2))
                            broker_name = str(getattr(info, "company", "MetaTrader 5"))
                            acc_obj = AccountInfo(
                                account_number=int(info.login),
                                balance=float(info.balance),
                                equity=float(info.equity),
                                margin=float(info.margin),
                                free_margin=float(info.margin_free),
                                margin_level=float(info.margin_level),
                                currency=str(info.currency),
                                leverage=int(info.leverage),
                                trade_mode=trade_mode,
                                margin_mode=margin_mode,
                                margin_mode_str="NETTING" if margin_mode == 1 else "HEDGING",
                            )
                            self.connection_status = "CONNECTED"
                        pos_list = mt5.positions_get() or []
                        for p in pos_list:
                            from src.core.contracts import OrderType
                            raw_positions.append(
                                Position(
                                    ticket=int(p.ticket),
                                    symbol=str(p.symbol),
                                    order_type=OrderType.BUY if int(p.type) == 0 else OrderType.SELL,
                                    volume=float(p.volume),
                                    open_price=float(p.price_open),
                                    current_price=float(p.price_current),
                                    stop_loss=float(p.sl),
                                    take_profit=float(p.tp),
                                    profit=float(p.profit),
                                    commission=float(getattr(p, "commission", 0.0)),
                                    swap=float(getattr(p, "swap", 0.0)),
                                    magic=int(getattr(p, "magic", 0)),
                                    comment=str(getattr(p, "comment", "")),
                                )
                            )
                        ord_list = mt5.orders_get() or []
                        for o in ord_list:
                            raw_orders.append(
                                {
                                    "ticket": int(o.ticket),
                                    "symbol": str(o.symbol),
                                    "type": int(o.type),
                                    "volume": float(o.volume_current),
                                    "price": float(o.price_open),
                                    "sl": float(o.sl),
                                    "tp": float(o.tp),
                                    "magic": int(getattr(o, "magic", 0)),
                                }
                            )
                except Exception as exc:
                    self.last_error = str(exc)
                    self.connection_status = "DISCONNECTED"

            if acc_obj is not None:
                demo_verified = str(acc_obj.trade_mode).upper() == "DEMO"
                netting_obs = str(getattr(acc_obj, "margin_mode_str", "HEDGING")).upper() == "NETTING"
                acc_bal = round(float(acc_obj.balance), 2)
                acc_eq = round(float(acc_obj.equity), 2)
                acc_credit = round(float(getattr(acc_obj, "credit", 0.0)), 2)
                acc_profit = round(float(getattr(acc_obj, "profit", 0.0)), 2)
                reconcil_diff = round(acc_eq - (acc_bal + acc_credit + acc_profit), 2)
                self.account = {
                    "account_number": acc_obj.account_number,
                    "broker": getattr(acc_obj, "broker", broker_name),
                    "currency": acc_obj.currency,
                    "balance": acc_bal,
                    "equity": acc_eq,
                    "credit": acc_credit,
                    "profit": acc_profit,
                    "equity_reconciliation_diff": reconcil_diff,
                    "margin": round(float(acc_obj.margin), 2),
                    "free_margin": round(float(acc_obj.free_margin), 2),
                    "margin_level": round(float(acc_obj.margin_level), 2),
                    "leverage": int(acc_obj.leverage),
                    "trade_mode": str(acc_obj.trade_mode).upper(),
                    "margin_mode_str": getattr(acc_obj, "margin_mode_str", "HEDGING"),
                    "demo_verified": demo_verified,
                    "netting_observe_only": netting_obs,
                }
                if not demo_verified:
                    self.repo.record_error(
                        category="RISK",
                        severity="CRITICAL",
                        component="MT5SyncService",
                        message=f"Connected account #{acc_obj.account_number} is {acc_obj.trade_mode}, not DEMO. Order submission locked.",
                        trading_affected=True,
                        entries_blocked=True,
                        recommended_recovery="Switch MT5 terminal to a verified DEMO account.",
                        user_action_required=True,
                    )

            # Symbol discovery & live quotes
            if mt5 is not None:
                self._discover_symbols(mt5, target_symbols or ["XAUUSD", "BTCUSD"])

            # Reconcile positions and classify ownership
            self._reconcile_positions(raw_positions)
            self.pending_orders = raw_orders
            self.last_sync_at = datetime.now(timezone.utc).isoformat()
            snapshot = self.get_snapshot()
            self.events.publish_event("mt5_sync", snapshot)
            return snapshot

    def _discover_symbols(self, mt5: Any, target_roots: List[str]) -> None:
        try:
            all_syms = mt5.symbols_get() or []
            for sym_obj in all_syms:
                name = str(getattr(sym_obj, "name", ""))
                upper = name.upper()
                if any(upper.startswith(r.upper().split(".")[0]) for r in target_roots):
                    tick = mt5.symbol_info_tick(name)
                    bid = float(getattr(tick, "bid", 0.0)) if tick else 0.0
                    ask = float(getattr(tick, "ask", 0.0)) if tick else 0.0
                    self.symbols[name] = {
                        "symbol": name,
                        "digits": int(getattr(sym_obj, "digits", 2)),
                        "point": float(getattr(sym_obj, "point", 0.01)),
                        "tick_size": float(getattr(sym_obj, "trade_tick_size", 0.01)),
                        "tick_value": float(getattr(sym_obj, "trade_tick_value", 1.0)),
                        "contract_size": float(getattr(sym_obj, "trade_contract_size", 1.0)),
                        "min_lot": float(getattr(sym_obj, "volume_min", 0.01)),
                        "max_lot": float(getattr(sym_obj, "volume_max", 50.0)),
                        "lot_step": float(getattr(sym_obj, "volume_step", 0.01)),
                        "stops_level": int(getattr(sym_obj, "trade_stops_level", 0)),
                        "spread": int(getattr(sym_obj, "spread", 0)),
                        "bid": bid,
                        "ask": ask,
                        "trade_mode": int(getattr(sym_obj, "trade_mode", 0)),
                    }
        except Exception:
            pass

    def _reconcile_positions(self, raw_positions: List[Position]) -> None:
        reconciled: List[Dict[str, Any]] = []
        bot_owned = 0
        manual = 0
        other_ea = 0
        unprotected_bot: List[int] = []

        for p in raw_positions:
            magic = int(getattr(p, "magic", 0))
            if magic == self.bot_magic:
                ownership = "BOT"
                bot_owned += 1
                if float(p.stop_loss) <= 0.0:
                    unprotected_bot.append(int(p.ticket))
            elif magic == 0:
                ownership = "MANUAL"
                manual += 1
            else:
                ownership = "OTHER_EA"
                other_ea += 1

            # Detect SL/TP changes
            prev = self._previous_sl_tp.get(int(p.ticket))
            cur = (float(p.stop_loss), float(p.take_profit))
            if prev is not None and prev != cur:
                self.events.log(
                    "RECONCILIATION",
                    "INFO",
                    f"SL/TP changed on #{p.ticket} ({p.symbol}): SL {prev[0]} -> {cur[0]}, TP {prev[1]} -> {cur[1]}",
                    instrument=p.symbol,
                    ticket=int(p.ticket),
                )
            self._previous_sl_tp[int(p.ticket)] = cur

            item = {
                "ticket": int(p.ticket),
                "symbol": p.symbol,
                "direction": p.order_type.value if hasattr(p.order_type, "value") else str(p.order_type),
                "volume": float(p.volume),
                "open_price": float(p.open_price),
                "current_price": float(p.current_price),
                "stop_loss": float(p.stop_loss),
                "take_profit": float(p.take_profit),
                "profit": round(float(p.profit), 2),
                "commission": round(float(getattr(p, "commission", 0.0)), 2),
                "swap": round(float(getattr(p, "swap", 0.0)), 2),
                "magic": magic,
                "ownership": ownership,
                "comment": str(getattr(p, "comment", "")),
            }
            reconciled.append(item)
            self.repo.upsert_trade_record(
                {
                    "ticket": item["ticket"],
                    "symbol": item["symbol"],
                    "direction": item["direction"],
                    "volume": item["volume"],
                    "entry_price": item["open_price"],
                    "stop_loss": item["stop_loss"],
                    "take_profit": item["take_profit"],
                    "profit": item["profit"],
                    "commission": item["commission"],
                    "swap": item["swap"],
                    "magic": magic,
                    "ownership": ownership,
                    "status": "OPEN",
                }
            )

        self.positions = reconciled
        self.reconciliation_report = {
            "status": "RECONCILED",
            "bot_owned_count": bot_owned,
            "manual_count": manual,
            "other_ea_count": other_ea,
            "unexpected_tickets": [r["ticket"] for r in reconciled if r["ownership"] in ("MANUAL", "OTHER_EA")],
            "unprotected_bot_tickets": unprotected_bot,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connection_status": self.connection_status,
                "last_sync_at": self.last_sync_at,
                "last_error": self.last_error,
                "reconnect_attempts": self.reconnect_attempts,
                "account": dict(self.account),
                "positions": list(self.positions),
                "pending_orders": list(self.pending_orders),
                "symbols": dict(self.symbols),
                "reconciliation": dict(self.reconciliation_report),
            }
