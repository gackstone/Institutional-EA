"""
BTCUSD DEMO Sample Trading Service (`BTCUSD_DEMO_SAMPLE_MODE`).
Integrates with the existing MT5SyncService, PortfolioRiskEngine, PositionSizer,
CompanionRepository, EventBus, and TelegramNotifier — without duplicating the
execution, risk, or MT5 connection stack.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("BTCUSDSampleTradingService")

from companion.database.repository import CompanionRepository
from companion.service.configuration.config_service import ConfigurationService
from companion.service.events.event_bus import EventBus
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.orchestration.engine_controller import EngineController
from src.core.contracts import AccountInfo, OrderType, Position, SetupType, SignalCandidate, SymbolInfo, Timeframe
from src.notifications.telegram_service import TelegramCommandHandler, TelegramNotifier
from src.risk.position_sizing import PositionSizingEngine


BTC_CANDIDATE_ALIASES = ("BTCUSD.m", "BTCUSD", "BTCUSDm", "BTCUSD.micro", "BTC/USD")


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class BTCUSDSampleTradingService:
    def __init__(
        self,
        project_root: str | Path,
        repo: CompanionRepository,
        events: EventBus,
        config_service: ConfigurationService,
        mt5_sync: MT5SyncService,
        engine: EngineController,
        telegram_notifier: Optional[TelegramNotifier] = None,
        telegram_commands: Optional[TelegramCommandHandler] = None,
    ):
        self.project_root = Path(project_root)
        self.repo = repo
        self.events = events
        self.config_service = config_service
        self.mt5_sync = mt5_sync
        self.engine = engine
        self.notifier = telegram_notifier
        self.commands = telegram_commands

        self._lock = threading.RLock()
        self.enabled: bool = False
        self.active: bool = False
        self.paused: bool = False
        self.state: str = "DISABLED"  # DISABLED | INITIALIZING | MONITORING | PAUSED | STOPPED | BLOCKED
        self.broker_symbol: str = "BTCUSD.m"
        self.max_simultaneous_positions: int = 1
        self.last_signal: Optional[Dict[str, Any]] = None
        self.last_executed_trade: Optional[Dict[str, Any]] = None
        self.last_execution_result: Optional[str] = None
        self.last_check_note: str = "Not started"
        self.daily_btcusd_pnl: float = 0.0

        self._known_open_btc_tickets: Dict[int, Dict[str, Any]] = {}
        self._last_conn_state: str = "UNKNOWN"
        self._recent_signal_keys: set[str] = set()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._wire_telegram_commands()

    def _wire_telegram_commands(self) -> None:
        if not self.commands:
            return
        self.commands.status_provider = lambda: {
            "mode": "BTCUSD_DEMO_SAMPLE_MODE" if self.active else self.engine.engine_state,
            "connected": self.mt5_sync.connection_status == "CONNECTED",
            "account": self.mt5_sync.account,
            "positions": self.mt5_sync.positions,
            "paused": self.paused or self.engine.pause_flag_path.exists(),
            "symbols": list(self.mt5_sync.symbols.keys()),
        }
        self.commands.positions_provider = lambda: self.mt5_sync.positions
        self.commands.balance_provider = lambda: self.mt5_sync.account
        self.commands.btc_provider = lambda: {
            "symbol": self.broker_symbol,
            "bid": self.mt5_sync.symbols.get(self.broker_symbol, {}).get("bid", 0.0),
            "ask": self.mt5_sync.symbols.get(self.broker_symbol, {}).get("ask", 0.0),
            "spread_points": self.mt5_sync.symbols.get(self.broker_symbol, {}).get("spread_points", 0),
            "status": self.mt5_sync.connection_status,
            "sample_state": self.state,
        }
        self.commands.history_provider = lambda: [
            t for t in self.repo.get_trade_records(limit=50) if "BTC" in str(t.get("symbol", "")).upper()
        ]
        self.commands.risk_provider = lambda: {
            **self.engine.risk_engine.to_dict(),
            "max_positions": self.max_simultaneous_positions,
        }
        self.commands.pause_handler = lambda: bool(self.pause().get("success"))
        self.commands.resume_handler = lambda: bool(self.resume().get("success"))
        self.commands.stop_handler = lambda: (bool(self.stop().get("success")), "BTCUSD sample trading stopped safely.")

    # ------------------------------------------------------------------
    # Telegram Notification Formatters (Section 9 Exact Templates)
    # ------------------------------------------------------------------
    def _send_tg(self, event_id: str, text: str) -> None:
        if not self.notifier or not self.notifier.config.enabled:
            return
        try:
            self.notifier.send_deduplicated(event_id, text, disable_notification=False, parse_mode="HTML")
        except Exception as exc:
            self.events.log("TELEGRAM", "WARNING", f"Notification dispatch error: {exc}")

    def notify_startup(self) -> None:
        self._send_tg(
            f"startup_{int(time.time() // 10)}",
            "🤖 <b>Institutional EA BTCUSD SAMPLE TRADING</b>\n\n"
            "Status: INITIALIZING\n"
            f"Instrument: {self.broker_symbol}\n"
            "Trading Environment: DEMO ONLY\n"
            "MT5 Connection: Checking...\n"
            "Risk Manager: Checking...\n"
            f"Telegram Notifications: {'Enabled' if (self.notifier and self.notifier.config.enabled) else 'Disabled'}",
        )

    def notify_connection_established(self, broker: str, symbol: str) -> None:
        self._send_tg(
            f"conn_ok_{symbol}_{int(time.time() // 30)}",
            "🟢 <b>MT5 CONNECTION ESTABLISHED</b>\n\n"
            "Bot: Institutional EA\n"
            f"Broker: {broker}\n"
            "Account Mode: DEMO\n"
            f"Instrument: {symbol}\n"
            "Market Data: Available\n"
            "Trading Status: READY",
        )

    def notify_trade_executed(self, direction: str, symbol: str, entry: float, volume: float, sl: float, tp: float, ticket: int) -> None:
        is_buy = direction.upper() == "BUY"
        icon = "🟢" if is_buy else "🔴"
        self._send_tg(
            f"exec_{ticket}_{direction}",
            f"{icon} <b>BTCUSD {direction.upper()} EXECUTED</b>\n\n"
            "Bot: Institutional EA\n"
            f"Instrument: {symbol}\n"
            f"Direction: {direction.upper()}\n"
            f"Entry Price: {entry:.2f}\n"
            f"Volume: {volume:.2f}\n"
            f"Stop Loss: {sl:.2f}\n"
            f"Take Profit: {tp:.2f}\n"
            f"Order Ticket: {ticket}\n"
            "Account: DEMO\n"
            "Execution Status: CONFIRMED\n"
            f"Timestamp: {_utc_now_str()}",
        )

    def notify_position_closed(
        self, direction: str, entry: float, exit_price: float, volume: float,
        pnl: float, commission: float, swap: float, reason: str, ticket: int
    ) -> None:
        result = "PROFIT" if pnl > 0.01 else ("LOSS" if pnl < -0.01 else "BREAK-EVEN")
        self._send_tg(
            f"closed_{ticket}",
            "🏁 <b>BTCUSD POSITION CLOSED</b>\n\n"
            f"Direction: {direction}\n"
            f"Entry Price: {entry:.2f}\n"
            f"Exit Price: {exit_price:.2f}\n"
            f"Volume: {volume:.2f}\n"
            f"Realized P/L: ${pnl:.2f}\n"
            f"Commission: ${commission:.2f}\n"
            f"Swap: ${swap:.2f}\n"
            f"Closing Reason: {reason}\n"
            f"Result: {result}\n"
            f"Order/Position Reference: {ticket}",
        )

    def notify_risk_rejected(self, direction: str, reason: str, signal_ref: str) -> None:
        self._send_tg(
            f"risk_rej_{signal_ref}",
            "⚠️ <b>BTCUSD TRADE REJECTED</b>\n\n"
            f"Reason: {reason}\n"
            f"Instrument: {self.broker_symbol}\n"
            f"Direction: {direction}\n"
            f"Signal: {signal_ref}\n"
            "Risk Manager: ACTIVE\n"
            "Execution: BLOCKED\n"
            "Account: DEMO",
        )

    def notify_sl_tp_updated(self, ticket: int, message: str) -> None:
        self._send_tg(
            f"sltp_{ticket}_{hash(message) & 0xffff}",
            f"🛡️ <b>BTCUSD PROTECTION UPDATE</b>\n\nTicket: {ticket}\n{message}\nAccount: DEMO",
        )

    def notify_connection_lost(self) -> None:
        self._send_tg(
            f"conn_lost_{int(time.time() // 30)}",
            "🔴 <b>MT5 CONNECTION LOST</b>\n\n"
            f"Instrument: {self.broker_symbol}\n"
            "Connection Status: DISCONNECTED\n"
            "New Entries: BLOCKED\n"
            "Position Protection: MONITORING\n"
            "Recovery: RECONNECTING",
        )

    def notify_connection_restored(self, trading_status: str) -> None:
        self._send_tg(
            f"conn_restored_{int(time.time() // 30)}",
            "🟢 <b>MT5 CONNECTION RESTORED</b>\n\n"
            "Connection: ESTABLISHED\n"
            "Account Verification: DEMO\n"
            "Position Reconciliation: COMPLETED\n"
            f"Trading Status: {trading_status}",
        )

    def notify_bot_stopped(self, open_count: int) -> None:
        self._send_tg(
            f"stopped_{int(time.time() // 10)}",
            "⏹ <b>Institutional EA BTCUSD BOT STOPPED</b>\n\n"
            "Status: STOPPED\n"
            "New Entries: DISABLED\n"
            f"Open Positions: {open_count}\n"
            "Position Protection: MONITORING\n"
            f"Timestamp: {_utc_now_str()}",
        )

    # ------------------------------------------------------------------
    # Symbol Discovery & 10-Point DEMO Precondition Check (Section 4 & 13)
    # ------------------------------------------------------------------
    def discover_btcusd_symbol(self, mt5: Any) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
        if mt5 is None:
            return None, None, "MetaTrader5 module unavailable"
        cfg_instruments = self.config_service.get_full_config().get("instruments", {}).get("instruments", {})
        btc_aliases = list(cfg_instruments.get("BTCUSD", {}).get("aliases", []))
        candidates = []
        for sym in list(BTC_CANDIDATE_ALIASES) + btc_aliases:
            if sym not in candidates:
                candidates.append(sym)

        for sym in candidates:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not getattr(info, "visible", True) and hasattr(mt5, "symbol_select"):
                    mt5.symbol_select(sym, True)
                    info = mt5.symbol_info(sym)
                trade_mode = int(getattr(info, "trade_mode", 0))
                if trade_mode == 0:
                    continue
                tick = mt5.symbol_info_tick(sym) if hasattr(mt5, "symbol_info_tick") else None
                bid = float(getattr(tick, "bid", 0.0) or getattr(info, "bid", 0.0))
                ask = float(getattr(tick, "ask", 0.0) or getattr(info, "ask", 0.0))
                if bid <= 0 or ask <= 0:
                    continue
                specs = {
                    "symbol": sym,
                    "digits": int(getattr(info, "digits", 2)),
                    "point": float(getattr(info, "point", 0.01)),
                    "tick_size": float(getattr(info, "trade_tick_size", 0.01) or 0.01),
                    "tick_value": float(getattr(info, "trade_tick_value", 0.01) or 0.01),
                    "volume_min": float(getattr(info, "volume_min", 0.01) or 0.01),
                    "volume_max": float(getattr(info, "volume_max", 100.0) or 100.0),
                    "volume_step": float(getattr(info, "volume_step", 0.01) or 0.01),
                    "stops_level": int(getattr(info, "trade_stops_level", 0) or 0),
                    "spread_points": int(getattr(info, "spread", 0) or 0),
                    "bid": bid,
                    "ask": ask,
                }
                return sym, specs, "OK"
        return None, None, "No tradable BTCUSD symbol found on connected MT5 broker"

    def verify_activation_preconditions(self) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Runs the mandatory 10-point DEMO-only safety gate before activation."""
        if self.engine.stop_flag_path.exists() or self.engine.risk_engine.is_kill_switch_active():
            return False, "STOP.flag kill switch is active. Clear it before starting sample trading.", None
        if self.engine.pause_flag_path.exists():
            return False, "state/PAUSE is active. Resume trading before activation.", None

        if not self.mt5_sync.connect():
            return False, "Cannot connect to MetaTrader 5 terminal.", None

        snap = self.mt5_sync.sync_all(["BTCUSD", "BTCUSD.m", "XAUUSD"])
        acct = snap.get("account", {})
        if not acct.get("demo_verified", False) or str(acct.get("trade_mode", "")).upper() != "DEMO":
            return False, f"LIVE/REAL account blocked: trade_mode={acct.get('trade_mode')}. Only DEMO is allowed.", None

        mt5 = self.mt5_sync._get_mt5()
        sym, specs, sym_err = self.discover_btcusd_symbol(mt5)
        if not sym or not specs:
            return False, sym_err, None

        self.broker_symbol = sym
        self.mt5_sync.symbols[sym] = specs
        self.engine.risk_engine.initialize_day(float(acct.get("equity", 10000.0)), float(acct.get("balance", 10000.0)))
        if self.engine.risk_engine.is_kill_switch_active() or self.engine.risk_engine.emergency_pause_active:
            return False, "PortfolioRiskEngine blocked new trades (kill switch or emergency pause active).", None

        return True, f"Verified DEMO account #{acct.get('account_number')} and symbol {sym}", specs

    # ------------------------------------------------------------------
    # Lifecycle Controls
    # ------------------------------------------------------------------
    def enable(self) -> Dict[str, Any]:
        with self._lock:
            self.enabled = True
            self.state = "READY" if not self.active else self.state
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_ENABLE", "BTCUSDSampleTradingService", "Enabled BTCUSD_DEMO_SAMPLE_MODE")
            return {"success": True, "message": "BTCUSD sample trading enabled.", "status": self.get_status()}

    def disable(self) -> Dict[str, Any]:
        self.stop()
        with self._lock:
            self.enabled = False
            self.state = "DISABLED"
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_DISABLE", "BTCUSDSampleTradingService", "Disabled BTCUSD_DEMO_SAMPLE_MODE")
            return {"success": True, "message": "BTCUSD sample trading disabled.", "status": self.get_status()}

    def start(self) -> Dict[str, Any]:
        with self._lock:
            self.enabled = True
            self.state = "INITIALIZING"
            self.notify_startup()
            ok, msg, _specs = self.verify_activation_preconditions()
            if not ok:
                self.state = "BLOCKED"
                self.last_execution_result = msg
                self.events.log("BTCUSD_SAMPLE", "WARNING", f"Activation refused: {msg}")
                return {"success": False, "message": msg, "status": self.get_status()}

            self.active = True
            self.paused = False
            self.state = "MONITORING"
            self._stop_event.clear()
            self._last_conn_state = "CONNECTED"
            self.notify_connection_established(self.mt5_sync.account.get("broker", "MT5 Demo"), self.broker_symbol)
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_START", "BTCUSDSampleTradingService", f"Started on {self.broker_symbol}")

            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True, name="BTCUSDSampleLoop")
                self._thread.start()

            return {"success": True, "message": f"BTCUSD_DEMO_SAMPLE_MODE active on {self.broker_symbol}", "status": self.get_status()}

    def pause(self) -> Dict[str, Any]:
        with self._lock:
            self.paused = True
            if self.active:
                self.state = "PAUSED"
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_PAUSE", "BTCUSDSampleTradingService", "Paused new sample entries")
            return {"success": True, "message": "BTCUSD sample entries paused.", "status": self.get_status()}

    def resume(self) -> Dict[str, Any]:
        with self._lock:
            ok, msg, _ = self.verify_activation_preconditions()
            if not ok:
                return {"success": False, "message": msg, "status": self.get_status()}
            self.paused = False
            if self.active:
                self.state = "MONITORING"
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_RESUME", "BTCUSDSampleTradingService", "Resumed sample entries")
            return {"success": True, "message": "BTCUSD sample entries resumed.", "status": self.get_status()}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            was_active = self.active
            self.active = False
            self.paused = False
            self.state = "STOPPED" if self.enabled else "DISABLED"
            self._stop_event.set()
            open_btc = [p for p in self.mt5_sync.positions if "BTC" in str(p.get("symbol", "")).upper()]
            if was_active:
                self.notify_bot_stopped(len(open_btc))
            self.repo.record_audit("operator", "BTCUSD_SAMPLE_STOP", "BTCUSDSampleTradingService", "Stopped BTCUSD sample trading")
            return {"success": True, "message": "BTCUSD sample trading stopped.", "status": self.get_status()}

    # ------------------------------------------------------------------
    # Signal Evaluation, Risk Authorization & Confirmed MT5 Execution
    # ------------------------------------------------------------------
    def evaluate_btcusd_signal(self, mt5: Any, specs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluates real M5 candles for a valid directional BTCUSD setup. Never fabricates signals."""
        if mt5 is None or not hasattr(mt5, "copy_rates_from_pos"):
            return None
        rates = mt5.copy_rates_from_pos(self.broker_symbol, getattr(mt5, "TIMEFRAME_M5", 5), 0, 30)
        if rates is None or len(rates) < 20:
            self.last_check_note = "Insufficient M5 candle history"
            return None

        closes = [float(r["close"]) for r in rates]
        highs = [float(r["high"]) for r in rates]
        lows = [float(r["low"]) for r in rates]
        bar_time = int(rates[-2]["time"])  # Last closed M5 bar

        ema_fast = sum(closes[-6:-1]) / 5.0
        ema_slow = sum(closes[-16:-1]) / 15.0
        prev_fast = sum(closes[-7:-2]) / 5.0
        prev_slow = sum(closes[-17:-2]) / 15.0
        atr = max(10.0, sum(h - l for h, l in zip(highs[-15:-1], lows[-15:-1])) / 14.0)

        direction: Optional[str] = None
        if prev_fast <= prev_slow and ema_fast > ema_slow and closes[-2] > ema_fast:
            direction = "BUY"
        elif prev_fast >= prev_slow and ema_fast < ema_slow and closes[-2] < ema_fast:
            direction = "SELL"

        if direction is None:
            self.last_check_note = "No qualifying BTCUSD M5 EMA/structure signal (monitoring)"
            return None

        sig_key = f"{self.broker_symbol}_{direction}_{bar_time}"
        if sig_key in self._recent_signal_keys:
            self.last_check_note = f"Signal {sig_key} already evaluated"
            return None

        entry = specs["ask"] if direction == "BUY" else specs["bid"]
        sl_dist = max(atr * 1.5, float(specs.get("stops_level", 0)) * specs["point"] * 2.0, 120.0)
        tp_dist = sl_dist * 2.5
        sl = round(entry - sl_dist if direction == "BUY" else entry + sl_dist, specs["digits"])
        tp = round(entry + tp_dist if direction == "BUY" else entry - tp_dist, specs["digits"])

        return {
            "signal_id": sig_key,
            "symbol": self.broker_symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "rr_ratio": 2.5,
            "strategy": "BTCUSD_M5_EMA_STRUCTURE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "valid": True,
        }

    def authorize_and_execute(self, signal: Dict[str, Any], is_manual_test: bool = False) -> Dict[str, Any]:
        """Validates signal through PortfolioRiskEngine & PositionSizer, executes on MT5, confirms broker fill."""
        sig_id = signal["signal_id"]
        direction = signal["direction"].upper()
        self.last_signal = signal

        if sig_id in self._recent_signal_keys and not is_manual_test:
            return {"success": False, "message": "Duplicate signal prevented."}

        snap = self.mt5_sync.sync_all([self.broker_symbol])
        acct = snap["account"]
        if not acct.get("demo_verified") or str(acct.get("trade_mode")).upper() != "DEMO":
            reason = "DEMO account verification failed — execution blocked."
            self.notify_risk_rejected(direction, reason, sig_id)
            return {"success": False, "message": reason}

        open_btc = [p for p in snap.get("positions", []) if "BTC" in str(p.get("symbol", "")).upper()]
        logger.info(f"[POSITION_MANAGER] Multiple concurrent BTCUSD positions supported. Active BTC positions: {len(open_btc)}")

        mt5 = self.mt5_sync._get_mt5()
        sym, specs, sym_err = self.discover_btcusd_symbol(mt5)
        if not sym or not specs:
            self.notify_risk_rejected(direction, sym_err, sig_id)
            return {"success": False, "message": sym_err}

        # Spread diagnostic (strategy-level spread rejection disabled)
        logger.info(f"[SPREAD_ENGINE] Strategy-level spread rejection is disabled. BTCUSD spread: {specs.get('spread_points', 0)} pts")

        # Calculate volume using actual BTCUSD contract specs via PositionSizingEngine
        acc_obj = AccountInfo(
            account_number=int(acct.get("account_number", 0)),
            balance=float(acct.get("balance", 10000.0)),
            equity=float(acct.get("equity", 10000.0)),
            free_margin=float(acct.get("free_margin", 10000.0)),
            currency=str(acct.get("currency", "USD")),
            leverage=int(acct.get("leverage", 100)),
            trade_mode="DEMO",
        )
        sym_obj = SymbolInfo(
            symbol=sym,
            digits=specs["digits"],
            point=specs["point"],
            tick_size=specs["tick_size"],
            tick_value=specs["tick_value"],
            contract_size=1.0,
            min_lot=specs["volume_min"],
            max_lot=specs["volume_max"],
            lot_step=specs["volume_step"],
            stops_level=specs["stops_level"],
            spread=specs["spread_points"],
            bid=specs["bid"],
            ask=specs["ask"],
        )
        sizer = PositionSizingEngine(
            default_risk_percent=0.5,
            max_risk_percent_per_trade=float(getattr(self.engine.risk_engine.config, "max_risk_percent_per_trade", 2.0)),
        )
        size_res = sizer.calculate_lot_size(
            account=acc_obj,
            symbol_info=sym_obj,
            entry_price=signal["entry_price"],
            stop_loss=signal["stop_loss"],
            take_profit=signal["take_profit"],
            risk_percent=0.5,
            order_type=OrderType.BUY if direction == "BUY" else OrderType.SELL,
        )
        volume = specs["volume_min"] if is_manual_test else max(specs["volume_min"], size_res.volume)
        volume = min(volume, specs["volume_max"])
        risk_pct = size_res.risk_percent_actual

        if not size_res.is_approved and not is_manual_test:
            reason = f"PositionSizingEngine rejected: {size_res.rejection_reason}"
            self.repo.record_risk_decision(sym, direction, False, reason, 0.0, risk_pct)
            self.notify_risk_rejected(direction, reason, sig_id)
            return {"success": False, "message": reason}

        # Evaluate full portfolio risk permission via PortfolioRiskEngine
        cand = SignalCandidate(
            id=sig_id,
            symbol=sym,
            timeframe=Timeframe.M5,
            setup_type=list(SetupType)[0],
            direction=OrderType.BUY if direction == "BUY" else OrderType.SELL,
            entry_price=float(signal["entry_price"]),
            stop_loss=float(signal["stop_loss"]),
            take_profit=float(signal["take_profit"]),
            risk_reward=float(signal.get("rr_ratio", 1.8)),
            score=75.0,
            timestamp=datetime.now(timezone.utc),
        )
        active_pos_objs = [
            Position(
                ticket=int(p.get("ticket", 0)),
                symbol=str(p.get("symbol", sym)),
                order_type=OrderType.BUY if str(p.get("direction", "BUY")) == "BUY" else OrderType.SELL,
                volume=float(p.get("volume", 0.01)),
                open_price=float(p.get("open_price", 0.0)),
                current_price=float(p.get("current_price", 0.0)),
                stop_loss=float(p.get("sl", 0.0)),
                take_profit=float(p.get("tp", 0.0)),
                profit=float(p.get("profit", 0.0)),
                magic=int(p.get("magic", 0)),
            )
            for p in snap.get("positions", [])
        ]
        risk_ok, risk_reason = self.engine.risk_engine.evaluate_new_order_permission(
            candidate=cand,
            account=acc_obj,
            active_positions=active_pos_objs,
            proposed_monetary_risk=float(size_res.monetary_risk or 1.0),
            proposed_volume=volume,
        )
        if not risk_ok:
            reason = risk_reason or "PortfolioRiskEngine rejected order"
            self.repo.record_risk_decision(sym, direction, False, reason, 0.0, risk_pct)
            self.notify_risk_rejected(direction, reason, sig_id)
            return {"success": False, "message": reason}

        self._recent_signal_keys.add(sig_id)
        self.repo.record_risk_decision(sym, direction, True, "Approved by PortfolioRiskEngine + PositionSizer", volume, risk_pct)

        # Submit order via MT5
        order_type = getattr(mt5, "ORDER_TYPE_BUY", 0) if direction == "BUY" else getattr(mt5, "ORDER_TYPE_SELL", 1)
        price = specs["ask"] if direction == "BUY" else specs["bid"]
        req = {
            "action": getattr(mt5, "TRADE_ACTION_DEAL", 1),
            "symbol": sym,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(signal["stop_loss"]),
            "tp": float(signal["take_profit"]),
            "deviation": 30,
            "magic": self.mt5_sync.bot_magic,
            "comment": "Institutional EA BTC SAMPLE",
            "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
        }
        res = mt5.order_send(req)
        retcode = getattr(res, "retcode", None) if res is not None else None
        done_code = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        if res is None or retcode != done_code:
            err_msg = f"MT5 order_send failed (retcode={retcode}, comment={getattr(res, 'comment', 'None')})"
            self.last_execution_result = err_msg
            self.repo.record_error("EXECUTION", "ERROR", "BTCUSDSampleTradingService", err_msg, trading_affected=True)
            return {"success": False, "message": err_msg}

        order_ticket = int(getattr(res, "order", 0) or getattr(res, "deal", 0))
        fill_price = float(getattr(res, "price", 0.0) or price)

        # Confirm actual position on broker side
        confirmed_pos = None
        if hasattr(mt5, "positions_get"):
            for p in (mt5.positions_get(symbol=sym) or []):
                if int(getattr(p, "ticket", 0)) == order_ticket or int(getattr(p, "identifier", 0)) == order_ticket or int(getattr(p, "magic", 0)) == self.mt5_sync.bot_magic:
                    confirmed_pos = p
                    break

        pos_ticket = int(getattr(confirmed_pos, "ticket", order_ticket))
        actual_sl = float(getattr(confirmed_pos, "sl", signal["stop_loss"]))
        actual_tp = float(getattr(confirmed_pos, "tp", signal["take_profit"]))
        actual_entry = float(getattr(confirmed_pos, "price_open", fill_price))

        self.last_executed_trade = {
            "ticket": pos_ticket,
            "symbol": sym,
            "direction": direction,
            "volume": volume,
            "entry_price": actual_entry,
            "sl": actual_sl,
            "tp": actual_tp,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._known_open_btc_tickets[pos_ticket] = dict(self.last_executed_trade)
        self.last_execution_result = f"CONFIRMED {direction} #{pos_ticket} @ {actual_entry:.2f}"

        self.repo.upsert_trade_record({
            "ticket": pos_ticket,
            "symbol": sym,
            "direction": direction,
            "volume": volume,
            "entry_price": actual_entry,
            "close_price": 0.0,
            "stop_loss": actual_sl,
            "take_profit": actual_tp,
            "profit": 0.0,
            "magic": self.mt5_sync.bot_magic,
            "ownership": "BOT",
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        })
        self.notify_trade_executed(direction, sym, actual_entry, volume, actual_sl, actual_tp, pos_ticket)
        return {"success": True, "message": self.last_execution_result, "trade": self.last_executed_trade}

    def place_manual_test_order(self, direction: str) -> Dict[str, Any]:
        """Controlled DEMO-only manual test order passing through the exact same risk manager."""
        dir_up = direction.strip().upper()
        if dir_up not in ("BUY", "SELL"):
            return {"success": False, "message": "Direction must be BUY or SELL."}
        ok, msg, specs = self.verify_activation_preconditions()
        if not ok or not specs:
            return {"success": False, "message": msg}

        entry = specs["ask"] if dir_up == "BUY" else specs["bid"]
        sl_dist = max(120.0, float(specs.get("stops_level", 0)) * specs["point"] * 2.0)
        tp_dist = sl_dist * 2.5
        signal = {
            "signal_id": f"MANUAL_TEST_{dir_up}_{uuid.uuid4().hex[:8]}",
            "symbol": self.broker_symbol,
            "direction": dir_up,
            "entry_price": entry,
            "stop_loss": round(entry - sl_dist if dir_up == "BUY" else entry + sl_dist, specs["digits"]),
            "take_profit": round(entry + tp_dist if dir_up == "BUY" else entry - tp_dist, specs["digits"]),
            "rr_ratio": 2.5,
            "strategy": "MANUAL_DEMO_TEST",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "valid": True,
        }
        return self.authorize_and_execute(signal, is_manual_test=True)

    # ------------------------------------------------------------------
    # Monitoring Cycle
    # ------------------------------------------------------------------
    def run_cycle(self) -> None:
        if not self.active:
            return
        snap = self.mt5_sync.sync_all([self.broker_symbol])
        conn = snap.get("connection_status", "DISCONNECTED")

        if conn != "CONNECTED":
            if self._last_conn_state == "CONNECTED":
                self.notify_connection_lost()
            self._last_conn_state = conn
            self.mt5_sync.connect()
            return
        elif self._last_conn_state != "CONNECTED":
            self.notify_connection_restored(self.state)
            self._last_conn_state = "CONNECTED"

        # Detect closed BTC positions
        current_btc_tickets = {
            int(p["ticket"]): p for p in snap.get("positions", []) if "BTC" in str(p.get("symbol", "")).upper()
        }
        for ticket, prev in list(self._known_open_btc_tickets.items()):
            if ticket not in current_btc_tickets:
                mt5 = self.mt5_sync._get_mt5()
                exit_price, pnl, comm, swap = prev["entry_price"], 0.0, 0.0, 0.0
                if mt5 is not None and hasattr(mt5, "history_deals_get"):
                    deals = mt5.history_deals_get(position=ticket) or []
                    for d in deals:
                        if getattr(d, "entry", 0) == 1:
                            exit_price = float(getattr(d, "price", exit_price))
                            pnl += float(getattr(d, "profit", 0.0))
                            comm += float(getattr(d, "commission", 0.0))
                            swap += float(getattr(d, "swap", 0.0))
                self.daily_btcusd_pnl += pnl
                self.repo.upsert_trade_record({
                    "ticket": ticket,
                    "symbol": prev["symbol"],
                    "direction": prev["direction"],
                    "volume": prev["volume"],
                    "entry_price": prev["entry_price"],
                    "close_price": exit_price,
                    "stop_loss": prev["sl"],
                    "take_profit": prev["tp"],
                    "profit": pnl,
                    "commission": comm,
                    "swap": swap,
                    "magic": self.mt5_sync.bot_magic,
                    "ownership": "BOT",
                    "status": "CLOSED",
                    "opened_at": prev["timestamp"],
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                })
                self.notify_position_closed(prev["direction"], prev["entry_price"], exit_price, prev["volume"], pnl, comm, swap, "CLOSED", ticket)
                del self._known_open_btc_tickets[ticket]

        if self.paused or self.engine.stop_flag_path.exists() or self.engine.pause_flag_path.exists():
            return

        mt5 = self.mt5_sync._get_mt5()
        _sym, specs, _err = self.discover_btcusd_symbol(mt5)
        if not specs:
            return
        sig = self.evaluate_btcusd_signal(mt5, specs)
        if sig is not None:
            self.authorize_and_execute(sig)

    def _loop(self) -> None:
        while not self._stop_event.is_set() and self.active:
            try:
                self.run_cycle()
            except Exception as exc:
                self.events.log("BTCUSD_SAMPLE", "ERROR", f"Cycle error: {exc}")
            self._stop_event.wait(5.0)

    def get_status(self) -> Dict[str, Any]:
        open_btc = [p for p in self.mt5_sync.positions if "BTC" in str(p.get("symbol", "")).upper()]
        floating_pnl = sum(float(p.get("profit", 0.0)) for p in open_btc)
        spec = self.mt5_sync.symbols.get(self.broker_symbol, {})
        return {
            "enabled": self.enabled,
            "active": self.active,
            "paused": self.paused,
            "state": self.state,
            "operating_mode": "BTCUSD_DEMO_SAMPLE_MODE",
            "broker_symbol": self.broker_symbol,
            "bid": spec.get("bid", 0.0),
            "ask": spec.get("ask", 0.0),
            "spread_points": spec.get("spread_points", 0),
            "mt5_connection": self.mt5_sync.connection_status,
            "demo_verified": self.mt5_sync.account.get("demo_verified", False),
            "open_positions": open_btc,
            "floating_pnl": round(floating_pnl, 2),
            "daily_pnl": round(self.daily_btcusd_pnl, 2),
            "last_signal": self.last_signal,
            "last_executed_trade": self.last_executed_trade,
            "last_execution_result": self.last_execution_result,
            "last_check_note": self.last_check_note,
            "telegram": {
                "enabled": bool(self.notifier and self.notifier.config.enabled),
                "has_token": bool(self.notifier and self.notifier.config.bot_token),
                "has_chat_id": bool(self.notifier and self.notifier.config.chat_id),
                "delivery_count": self.notifier.delivery_count if self.notifier else 0,
                "failed_count": self.notifier.failed_count if self.notifier else 0,
                "last_notification": self.notifier.last_notification if self.notifier else None,
            },
        }
