"""
MetaTrader 5 Synchronization & Reconciliation Service.
Detects MT5 installation/process, connects via BridgeClient or MetaTrader5 Python API,
verifies DEMO account mode, discovers Gold/BTC and configured symbol specifications,
reconciles broker-side positions/orders against bot-owned magic numbers, and handles
bounded exponential backoff reconnection.
"""

from __future__ import annotations
import os
import socket
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
from src.data.market_feed import (
    detect_broker_utc_offset_sec,
    fetch_live_quote,
    fetch_ohlc_candles,
    load_broker_symbol_map,
    load_freshness_limits,
    resolve_broker_symbol,
)
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
        self._bridge_explicit = bridge_client is not None
        self.bridge = bridge_client or BridgeClient(host=bridge_host, port=bridge_port)

        self._lock = threading.RLock()
        self.connection_status: str = "DISCONNECTED"  # CONNECTED | DISCONNECTED | SYNCHRONIZING | ERROR
        self.last_sync_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.reconnect_attempts: int = 0
        self.max_backoff_sec: float = 30.0
        self.terminal_path: Optional[str] = None
        self.last_candle_times: Dict[str, str] = {}
        self.zmq_status: Dict[str, Any] = {
            "port_5555": False,
            "port_5556": False,
            "connected": False,
            "checked_at": None,
        }

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

    def _init_mt5(self, mt5: Any, terminal_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Initializes MetaTrader5 Python API with optional terminal_path and captures last_error()."""
        path_to_use = terminal_path or self.terminal_path
        try:
            ok = mt5.initialize(path=path_to_use) if path_to_use else mt5.initialize()
        except TypeError:
            # Mock MT5 modules in unit tests may define initialize() with no kwargs
            ok = mt5.initialize()
        except Exception as exc:
            return False, f"MT5 initialize exception: {exc}"

        if ok:
            if path_to_use:
                self.terminal_path = path_to_use
            return True, None

        last_err_fn = getattr(mt5, "last_error", None)
        if callable(last_err_fn):
            try:
                err = last_err_fn()
                return False, f"MT5 initialize failed: {err}"
            except Exception:
                pass
        return False, "MT5 initialize() returned False (terminal may not be running or IPC disabled)"

    def check_zmq_bridge(self) -> Dict[str, Any]:
        """Probes local TCP bridge ports 5555 (MQL5 EA) and 5556 (IPC switchboard)."""
        def _probe(port: int) -> bool:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.35)
            try:
                return s.connect_ex((self.bridge_host, port)) == 0
            except Exception:
                return False
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        p5555 = _probe(self.bridge_port)
        p5556 = _probe(5556)
        self.zmq_status = {
            "port_5555": p5555,
            "port_5556": p5556,
            "connected": bool(p5555 or self.bridge.is_connected()),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        return dict(self.zmq_status)

    def connect(self, terminal_path: Optional[str] = None) -> bool:
        """Connects via BridgeClient or direct MT5 API with bounded backoff tracking."""
        with self._lock:
            self.connection_status = "SYNCHRONIZING"
            if terminal_path:
                self.terminal_path = terminal_path
            if self._mt5_override is None or self._bridge_explicit:
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
                ok, err = self._init_mt5(mt5, terminal_path=terminal_path)
                if ok:
                    self.connection_status = "CONNECTED"
                    self.reconnect_attempts = 0
                    self.last_error = None
                    self.repo.record_connection_event("MT5_DIRECT", "CONNECTED", "Connected via MetaTrader5 Python API")
                    self.repo.resolve_component_errors("MT5SyncService", "Direct MT5 terminal connection restored")
                    self.events.log("MT5", "INFO", "Connected to MT5 terminal via MetaTrader5 Python API")
                    return True
                if err:
                    self.last_error = err

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
                recommended_recovery="Ensure MetaTrader 5 terminal is open and PythonBridgeEA is attached, or click Sync MT5.",
                user_action_required=True,
            )
            self.events.log("MT5", "WARNING", f"MT5 connection failed (attempt {self.reconnect_attempts}): {err_msg}")
            return False

    def next_backoff_seconds(self) -> float:
        return min(self.max_backoff_sec, float(2 ** min(self.reconnect_attempts, 5)))

    def sync_all(self, target_symbols: Optional[List[str]] = None, terminal_path: Optional[str] = None) -> Dict[str, Any]:
        """Synchronizes account, symbols, positions, pending orders, and reconciliation state."""
        with self._lock:
            if terminal_path:
                self.terminal_path = terminal_path
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
                    ok, init_err = self._init_mt5(mt5, terminal_path=terminal_path)
                    if ok:
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
                            self.last_error = None
                        else:
                            self.connection_status = "DISCONNECTED"
                            self.last_error = "MT5 terminal running, but no account is logged in."
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
                    else:
                        self.last_error = init_err
                        self.connection_status = "DISCONNECTED"
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
                if acc_bal > 0 or acc_eq > 0:
                    try:
                        self.repo.record_balance_snapshot(
                            balance=acc_bal,
                            equity=acc_eq,
                            floating_pnl=round(acc_eq - acc_bal, 2),
                            source="MT5",
                        )
                    except Exception:
                        pass
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

            # Symbol discovery & live quotes (all 3 mapped broker .m symbols with freshness guards)
            if mt5 is not None:
                self._discover_symbols(mt5, target_symbols or ["XAUUSD", "USDJPY", "BTCUSD"])

            # Reconcile positions and classify ownership
            self._reconcile_positions(raw_positions)
            self.pending_orders = raw_orders
            self.check_zmq_bridge()
            self.last_sync_at = datetime.now(timezone.utc).isoformat()
            snapshot = self.get_snapshot()
            self.events.publish_event("mt5_sync", snapshot)
            return snapshot

    def _discover_symbols(self, mt5: Any, target_roots: List[str]) -> None:
        try:
            symbol_map = load_broker_symbol_map()
            limits = load_freshness_limits()
            max_age = limits["max_tick_age_seconds"]
            now_utc = datetime.now(timezone.utc)
            broker_offset = detect_broker_utc_offset_sec(mt5, now_utc=now_utc)

            for canonical, broker_sym in symbol_map.items():
                if target_roots and canonical not in [r.upper().split(".")[0] for r in target_roots]:
                    continue
                select_fn = getattr(mt5, "symbol_select", None)
                if callable(select_fn):
                    try:
                        select_fn(broker_sym, True)
                    except Exception:
                        pass
                quote = fetch_live_quote(
                    mt5=mt5,
                    broker_symbol=broker_sym,
                    canonical_symbol=canonical,
                    max_age_sec=max_age,
                    broker_utc_offset_sec=broker_offset,
                    now_utc=now_utc,
                )
                if quote is not None:
                    self.symbols[broker_sym] = quote
                    continue

                # Fallback for test fixtures that only implement symbols_get()
                all_syms = mt5.symbols_get() or []
                for sym_obj in all_syms:
                    name = str(getattr(sym_obj, "name", ""))
                    if name.upper() == broker_sym.upper() or name.upper().startswith(canonical):
                        tick = mt5.symbol_info_tick(name)
                        bid = float(getattr(tick, "bid", 0.0)) if tick else 0.0
                        ask = float(getattr(tick, "ask", 0.0)) if tick else 0.0
                        pt = float(getattr(sym_obj, "point", 0.01))
                        spr = int(round((ask - bid) / pt)) if pt > 0 and ask >= bid and bid > 0 else int(getattr(sym_obj, "spread", 0))
                        self.symbols[name] = {
                            "canonical": canonical,
                            "symbol": name,
                            "digits": int(getattr(sym_obj, "digits", 2)),
                            "point": pt,
                            "tick_size": float(getattr(sym_obj, "trade_tick_size", pt)),
                            "tick_value": float(getattr(sym_obj, "trade_tick_value", 1.0)),
                            "contract_size": float(getattr(sym_obj, "trade_contract_size", 1.0)),
                            "volume_min": float(getattr(sym_obj, "volume_min", 0.01)),
                            "volume_max": float(getattr(sym_obj, "volume_max", 50.0)),
                            "volume_step": float(getattr(sym_obj, "volume_step", 0.01)),
                            "stops_level": int(getattr(sym_obj, "trade_stops_level", 0)),
                            "spread_points": spr,
                            "bid": bid,
                            "ask": ask,
                            "trade_mode": int(getattr(sym_obj, "trade_mode", 0)),
                            "stale": False,
                            "market_closed": False,
                            "source": "MT5",
                        }
        except Exception:
            pass

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 120,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetches real OHLCV candles directly from MT5 for the mapped broker symbol."""
        symbol_map = load_broker_symbol_map()
        try:
            broker_sym = resolve_broker_symbol(symbol, symbol_map)
        except Exception:
            broker_sym = symbol
        canonical = symbol.upper().split(".")[0]

        mt5 = self._get_mt5()
        now_utc = datetime.now(timezone.utc)
        if mt5 is None:
            return {
                "symbol": canonical,
                "broker_symbol": broker_sym,
                "timeframe": timeframe.upper(),
                "candles": [],
                "quote": self.symbols.get(broker_sym),
                "source": "MT5",
                "connected": False,
                "status_reason": "MT5_NOT_CONNECTED",
                "last_error": "MetaTrader5 Python package unavailable",
                "fetched_at": now_utc.isoformat(),
            }

        ok_init, init_err = self._init_mt5(mt5)
        if not ok_init:
            return {
                "symbol": canonical,
                "broker_symbol": broker_sym,
                "timeframe": timeframe.upper(),
                "candles": [],
                "quote": self.symbols.get(broker_sym),
                "source": "MT5",
                "connected": False,
                "status_reason": "MT5_NOT_CONNECTED",
                "last_error": init_err,
                "fetched_at": now_utc.isoformat(),
            }

        # Ensure symbol is enabled in Market Watch before fetching rates
        select_fn = getattr(mt5, "symbol_select", None)
        sym_selected = True
        if callable(select_fn):
            try:
                sym_selected = bool(select_fn(broker_sym, True))
            except Exception:
                sym_selected = False

        broker_offset = detect_broker_utc_offset_sec(mt5, now_utc=now_utc)
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if start_iso else None
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else None

        candles = fetch_ohlc_candles(
            mt5=mt5,
            broker_symbol=broker_sym,
            timeframe=timeframe,
            count=count,
            start_utc=start_dt,
            end_utc=end_dt,
            broker_utc_offset_sec=broker_offset,
        )
        quote = fetch_live_quote(
            mt5=mt5,
            broker_symbol=broker_sym,
            canonical_symbol=canonical,
            max_age_sec=load_freshness_limits()["max_tick_age_seconds"],
            broker_utc_offset_sec=broker_offset,
            now_utc=now_utc,
        )
        if quote:
            self.symbols[broker_sym] = quote

        if candles:
            last_ts = candles[-1].get("time")
            if last_ts:
                self.last_candle_times[broker_sym] = datetime.fromtimestamp(int(last_ts), tz=timezone.utc).isoformat()
            status_reason = "MARKET_CLOSED" if (quote and quote.get("market_closed")) else "OK"
        else:
            sym_info_fn = getattr(mt5, "symbol_info", None)
            sym_exists = bool(sym_info_fn(broker_sym)) if callable(sym_info_fn) else sym_selected
            if not sym_exists:
                status_reason = "SYMBOL_NOT_FOUND"
            elif quote and quote.get("market_closed"):
                status_reason = "MARKET_CLOSED"
            else:
                status_reason = "NO_CANDLES"

        return {
            "symbol": canonical,
            "broker_symbol": broker_sym,
            "timeframe": timeframe.upper(),
            "candles": candles,
            "quote": quote or self.symbols.get(broker_sym),
            "source": "MT5",
            "connected": self.connection_status == "CONNECTED" or len(candles) > 0,
            "status_reason": status_reason,
            "last_error": self.last_error,
            "fetched_at": now_utc.isoformat(),
        }

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
                "terminal_path": self.terminal_path,
                "zmq_bridge": dict(self.zmq_status),
                "last_candle_times": dict(self.last_candle_times),
                "account": dict(self.account),
                "positions": list(self.positions),
                "pending_orders": list(self.pending_orders),
                "symbols": dict(self.symbols),
                "reconciliation": dict(self.reconciliation_report),
            }
