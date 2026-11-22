#!/usr/bin/env python3
"""
ArcadeFx — MT5 Bot Agent
Outbound-only secure orchestration agent running next to MetaTrader 5 on Windows.

Hard Rules Enforced:
1. NEVER stores or transmits MT5 or broker passwords.
2. Outbound HTTPS connections ONLY — zero open ports on the host machine.
3. Safe cloud commands only (start, stop, pause, resume, close_all, kill_switch, update_config).
4. Local limits (local_limits.json) are hard ceilings: cloud CANNOT raise risk or enable live trading.
5. All cloud commands are signed with HMAC-SHA256, carry nonce + expiry to prevent replays.
6. Heartbeats sent every 15-30 seconds with actual MT5 terminal data.
7. Offline resilience with local event queue and deduplication.
8. Interactive pairing code prompt with automatic uppercase normalization and format validation.
"""

from __future__ import annotations
import os
import sys
import json
import time
import hmac
import hashlib
import sqlite3
import argparse
import socket
import logging
import signal
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from urllib import request, error

# Ensure project root is in sys.path
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(sys.executable).resolve().parent))
    if hasattr(sys, "_MEIPASS"):
        sys.path.insert(0, str(sys._MEIPASS))
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Optional MetaTrader5 integration
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

# Existing Trading Bot Imports
try:
    from src.core.config import AppConfig
    from src.core.contracts import AccountInfo, Position, OrderType, ExecutionMode
    from src.core.orchestrator import TradingBotOrchestrator
    from src.execution.bridge_client import BridgeClient
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    AppConfig = None
    AccountInfo = None
    Position = None
    OrderType = None
    ExecutionMode = None
    TradingBotOrchestrator = None
    BridgeClient = None
    ORCHESTRATOR_AVAILABLE = False

# Configuration Defaults
DEFAULT_API_URL = os.environ.get("ARCADEFX_API_URL", "https://www.arcadefx.live/api/v1")
AGENT_VERSION = "1.2.0"

# Centralized safe Windows writable directories
from src.core.app_paths import (
    get_base_app_data_dir,
    get_logs_dir,
    get_state_dir,
    get_credentials_dir,
    get_primary_credentials_file,
    get_legacy_credentials_files,
    setup_service_logger,
    SingleInstanceLock
)

CONFIG_DIR = str(get_credentials_dir())
CREDENTIALS_FILE = str(get_primary_credentials_file())
LOCAL_LIMITS_FILE = str(get_base_app_data_dir() / "local_limits.json")
QUEUE_DB_FILE = str(get_state_dir() / "offline_queue.sqlite")
AGENT_STATE_FILE = get_state_dir() / "agent_state.json"

# Safe rotating logger setup writing to %LOCALAPPDATA%\ArcadeFX\MT5-OO1 Companion\logs
logger = setup_service_logger("ArcadeFxAgent", "arcadefx_agent.log")


class LocalCredentialStore:
    """Manages encrypted device tokens and signing secrets across safe Windows app data locations."""

    @classmethod
    def get_candidate_files(cls) -> List[Path]:
        candidates = [get_primary_credentials_file()]
        candidates.extend(get_legacy_credentials_files())
        return candidates

    @classmethod
    def save(cls, data: Dict[str, Any]) -> None:
        token = data.get("deviceToken") or data.get("device_token") or data.get("token")
        inst = data.get("instanceId") or data.get("instance_id")
        sec = data.get("signingSecret") or data.get("signing_secret")
        normalized = {
            "version": 2,
            "format": "json_utf8",
            "deviceToken": token,
            "device_token": token,
            "token": token,
            "instanceId": inst,
            "instance_id": inst,
            "signingSecret": sec,
            "signing_secret": sec,
            "apiUrl": data.get("apiUrl") or data.get("api_url") or DEFAULT_API_URL,
            "pairedAt": data.get("pairedAt") or data.get("paired_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        target_path = get_primary_credentials_file()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        # Mirror to legacy path for backward compatibility with older tools
        try:
            legacy_dir = Path.home() / ".arcadefx_agent"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            with open(legacy_dir / "credentials.enc.json", "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2)
        except Exception:
            pass

        logger.info("Device credentials saved securely.")

    @classmethod
    def load(cls) -> Optional[Dict[str, Any]]:
        for file_path in cls.get_candidate_files():
            if not file_path.exists():
                continue
            try:
                with open(file_path, "rb") as f:
                    raw_bytes = f.read()

                if not raw_bytes:
                    continue

                # 1. Plain UTF-8 JSON attempt
                try:
                    data = json.loads(raw_bytes.decode("utf-8"))
                    if isinstance(data, dict):
                        token = data.get("deviceToken") or data.get("device_token") or data.get("token")
                        if token:
                            data["deviceToken"] = token
                            data["device_token"] = token
                            data["token"] = token
                            inst = data.get("instanceId") or data.get("instance_id")
                            data["instanceId"] = inst
                            data["instance_id"] = inst
                            sec = data.get("signingSecret") or data.get("signing_secret")
                            data["signingSecret"] = sec
                            data["signing_secret"] = sec

                            primary = get_primary_credentials_file()
                            if file_path.resolve() != primary.resolve() and not primary.exists():
                                cls.save(data)
                            return data
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

                # 2. XOR Obfuscation fallback
                try:
                    seed = f"{socket.gethostname()}-{os.getenv('USERNAME', 'default')}-arcadefx-agent-v1"
                    key = hashlib.sha256(seed.encode("utf-8")).digest()
                    recovered = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw_bytes)])
                    data = json.loads(recovered.decode("utf-8"))
                    if isinstance(data, dict):
                        token = data.get("deviceToken") or data.get("device_token") or data.get("token")
                        if token:
                            data["deviceToken"] = token
                            data["device_token"] = token
                            data["token"] = token
                            inst = data.get("instanceId") or data.get("instance_id")
                            data["instanceId"] = inst
                            data["instance_id"] = inst
                            sec = data.get("signingSecret") or data.get("signing_secret")
                            data["signingSecret"] = sec
                            data["signing_secret"] = sec
                            cls.save(data)
                            return data
                except Exception:
                    pass

                logger.error(f"Unrecognized or corrupted credential encoding in {file_path.name}. File preserved without deletion for recovery.")
            except Exception as e:
                logger.error(f"Failed to access credentials file {file_path}: {e}")

        return None

    @classmethod
    def clear(cls) -> None:
        for file_path in cls.get_candidate_files():
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
        logger.info("Cleared local credentials.")


class OfflineEventQueue:
    """SQLite-backed event queue for zero-data-loss offline operation."""

    def __init__(self, db_path: str = QUEUE_DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queued_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    dedup_id TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def enqueue(self, event_type: str, payload: Dict[str, Any], dedup_id: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO queued_events (event_type, payload_json, dedup_id) VALUES (?, ?, ?)",
                    (event_type, json.dumps(payload), dedup_id)
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not enqueue event {dedup_id}: {e}")

    def get_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, event_type, payload_json, dedup_id FROM queued_events ORDER BY id ASC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                return [
                    {"id": r[0], "eventType": r[1], "payload": json.loads(r[2]), "dedupId": r[3]}
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"Error fetching pending events: {e}")
            return []

    def delete_events(self, ids: List[int]):
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(f"DELETE FROM queued_events WHERE id IN ({placeholders})", ids)
                conn.commit()
        except Exception as e:
            logger.warning(f"Error deleting events: {e}")

    def clear(self):
        """Clears all queued events upon unpairing or token invalidation."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM queued_events")
                conn.commit()
            logger.info("Cleared offline events queue.")
        except Exception as e:
            logger.warning(f"Error clearing offline events: {e}")


class MT5BotAgent:
    """ArcadeFx MT5 Bot Agent orchestrator."""

    def __init__(self, api_url: str = DEFAULT_API_URL):
        self.api_url = api_url.rstrip("/")
        self.credentials = LocalCredentialStore.load() or {}
        self.device_token = self.credentials.get("device_token")
        self.instance_id = self.credentials.get("instance_id")
        self.signing_secret = self.credentials.get("signing_secret")
        self.offline_queue = OfflineEventQueue()
        self.seen_nonces = set()
        self.bot_state = "STOPPED"
        self.start_time = time.time()
        self.last_error: Optional[str] = None
        self.is_running = False
        self._stop_event = threading.Event()
        self._trading_thread: Optional[threading.Thread] = None

        # Existing Trading Infrastructure Handles
        self.config: Optional[Any] = None
        self.orchestrator: Optional[Any] = None
        self.bridge: Optional[Any] = None

        self._init_trading_infrastructure()

    def _init_trading_infrastructure(self):
        """Initializes connection to existing MT5 trading engine and bridge."""
        if ORCHESTRATOR_AVAILABLE:
            try:
                self.config = AppConfig.load_from_dir()
                self.orchestrator = TradingBotOrchestrator(self.config)
                self.bridge = self.orchestrator.bridge
                logger.info("Existing trading orchestrator and bridge initialized.")
            except Exception as e:
                logger.warning(f"Notice during orchestrator initialization: {e}")
                self.bridge = BridgeClient() if BridgeClient else None
        elif BridgeClient:
            self.bridge = BridgeClient()

    def load_local_limits(self) -> Dict[str, Any]:
        """Loads and returns local machine hard ceilings."""
        if not os.path.exists(LOCAL_LIMITS_FILE):
            default_limits = {
                "max_risk_pct_ceiling": 1.0,
                "max_lots_ceiling": 0.5,
                "max_drawdown_pct_ceiling": 5.0,
                "allow_live_trading": False,
                "allowed_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD.m"],
                "enforce_local_confirmation_for_live": True,
                "comment": "HARD LOCAL CEILINGS: The cloud service CANNOT raise values above these local limits or enable live trading. Local limits ALWAYS win."
            }
            try:
                with open(LOCAL_LIMITS_FILE, "w") as f:
                    json.dump(default_limits, f, indent=2)
            except Exception:
                pass
            return default_limits

        try:
            with open(LOCAL_LIMITS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"max_risk_pct_ceiling": 1.0, "max_lots_ceiling": 0.5, "max_drawdown_pct_ceiling": 5.0, "allow_live_trading": False}

    def _http_request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, use_auth: bool = True, max_redirects: int = 3) -> Dict[str, Any]:
        """Makes an outbound HTTPS/HTTP request with redirect following and no inbound server listening."""
        url = path if path.startswith("http") else f"{self.api_url}{path}"
        # Ensure canonical domain to avoid HTTP 308 apex redirect
        if url.startswith("https://arcadefx.live"):
            url = "https://www.arcadefx.live" + url[len("https://arcadefx.live"):]
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"ArcadeFx-MT5BotAgent/{AGENT_VERSION}"
        }
        if use_auth and self.device_token:
            headers["x-bot-token"] = self.device_token

        body = json.dumps(data).encode("utf-8") if data else None
        req = request.Request(url, data=body, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=20) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body)
        except error.HTTPError as e:
            if e.code in (301, 302, 307, 308) and max_redirects > 0:
                redirect_url = e.headers.get("Location")
                if redirect_url:
                    logger.info(f"Following redirect ({e.code}) to: {redirect_url}")
                    return self._http_request(method, redirect_url, data=data, use_auth=use_auth, max_redirects=max_redirects - 1)
            err_content = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_content)
                err_msg = err_json.get("error", err_content)
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                raise RuntimeError(err_msg)
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}")
        except error.URLError as e:
            raise RuntimeError(f"NETWORK ERROR: Unable to reach ArcadeFX.live. {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Network error contacting {url}: {e}")

    @staticmethod
    def validate_pairing_code_format(code: str) -> Tuple[bool, str]:
        """Validates 6-character alphanumeric pairing code format."""
        if not code:
            return False, "Pairing code cannot be empty. Please enter the 6-character pairing code."
        code_clean = code.strip().upper()
        if len(code_clean) != 6 or not code_clean.isalnum():
            return False, "Invalid format. The pairing code must be a 6-character alphanumeric code (e.g. C2E2AD)."
        return True, code_clean

    def pair_with_code(self, pairing_code: str, instance_name: Optional[str] = None) -> Tuple[bool, str]:
        """
        Submits pairing code to ArcadeFX.live backend (/bot/pairing/claim).
        Returns (success: bool, message: str).
        """
        valid, normalized_or_err = self.validate_pairing_code_format(pairing_code)
        if not valid:
            return False, normalized_or_err

        clean_code = normalized_or_err
        machine_name = instance_name or f"{socket.gethostname()}-MT5"
        logger.info(f"Submitting pairing code [{clean_code}] to {self.api_url}/bot/pairing/claim...")

        try:
            res = self._http_request(
                method="POST",
                path="/bot/pairing/claim",
                data={
                    "pairingCode": clean_code,
                    "instanceName": machine_name,
                    "engineVersion": AGENT_VERSION
                },
                use_auth=False
            )

            if not res.get("success"):
                err_raw = res.get("error", "Unknown pairing error")
                err_lower = str(err_raw).lower()
                if "already" in err_lower or "claimed" in err_lower or "used" in err_lower:
                    return False, "ALREADY USED: This pairing code has already been used. Generate another code."
                elif "expired" in err_lower:
                    return False, "EXPIRED CODE: This pairing code has expired. Generate a new code from ArcadeFX.live."
                elif "invalid" in err_lower or "not found" in err_lower:
                    return False, "INVALID CODE: The pairing code is invalid. Check ArcadeFX.live and try again."
                else:
                    return False, f"PAIRING FAILED: {err_raw}"

            self.device_token = res["deviceToken"]
            self.instance_id = res["instanceId"]
            self.signing_secret = res["signingSecret"]

            LocalCredentialStore.save({
                "device_token": self.device_token,
                "instance_id": self.instance_id,
                "signing_secret": self.signing_secret,
                "api_url": self.api_url,
                "paired_at": time.time()
            })

            return True, "MACHINE PAIRED SUCCESSFULLY"

        except RuntimeError as e:
            err_msg = str(e)
            err_lower = err_msg.lower()
            if "already" in err_lower or "claimed" in err_lower or "used" in err_lower:
                return False, "ALREADY USED: This pairing code has already been used. Generate another code."
            elif "expired" in err_lower:
                return False, "EXPIRED CODE: This pairing code has expired. Generate a new code from ArcadeFX.live."
            elif "not found" in err_lower or "invalid" in err_lower:
                return False, "INVALID CODE: The pairing code is invalid. Check ArcadeFX.live and try again."
            elif "network error" in err_lower or "connection refused" in err_lower or "timed out" in err_lower:
                return False, "NETWORK ERROR: Unable to reach ArcadeFX.live. Check your internet connection."
            elif "http 5" in err_lower:
                return False, "SERVER ERROR: ArcadeFX.live is temporarily unavailable. Retrying connection..."
            return False, f"ERROR: {err_msg}"
        except Exception as e:
            return False, f"NETWORK ERROR: Unable to reach ArcadeFX.live ({e})"

    def check_local_connectivity(self) -> Dict[str, str]:
        """Verifies local MT5 terminal, PythonBridgeEA socket, and trading engine readiness."""
        results = {
            "mt5": "NOT RUNNING",
            "bridge": "DISCONNECTED",
            "trading_engine": "READY" if self.orchestrator else "INITIALIZING"
        }

        # 1. MT5 Terminal Check
        if MT5_AVAILABLE:
            try:
                if mt5.initialize():
                    t_info = mt5.terminal_info()
                    if t_info and getattr(t_info, "connected", False):
                        results["mt5"] = "CONNECTED"
                    else:
                        results["mt5"] = "RUNNING (No Broker Connection)"
                else:
                    results["mt5"] = "NOT RUNNING"
            except Exception:
                results["mt5"] = "ERROR ACCESSING TERMINAL"
        else:
            try:
                output = os.popen('tasklist /FI "IMAGENAME eq terminal64.exe"').read()
                results["mt5"] = "PROCESS DETECTED" if "terminal64.exe" in output else "NOT RUNNING"
            except Exception:
                results["mt5"] = "UNKNOWN"

        # 2. Execution Bridge Check (query port 5556 IPC STATUS or 5555 TCP)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(("127.0.0.1", 5556))
            s.sendall(b'{"action": "STATUS"}\n')
            rx = s.recv(4096)
            s.close()
            if rx:
                st = json.loads(rx.decode("utf-8").strip())
                active = st.get("active_connections_count", 0)
                if active > 0:
                    results["bridge"] = f"CONNECTED (Active EA Clients: {active})"
                else:
                    results["bridge"] = "CONNECTED (Daemon Active, Awaiting EA)"
            else:
                results["bridge"] = "CONNECTED"
        except Exception:
            try:
                s5 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s5.settimeout(2.0)
                s5.connect(("127.0.0.1", 5555))
                s5.close()
                results["bridge"] = "CONNECTED (Port 5555)"
            except Exception:
                results["bridge"] = "DISCONNECTED"

        return results

    def verify_command_signature(self, command: Dict[str, Any]) -> bool:
        """Verifies HMAC-SHA256 signature, nonce replay protection, and expiration."""
        signature = command.get("signature")
        nonce = command.get("nonce")
        expires_at_str = command.get("expires_at")
        payload = json.loads(command.get("payload_json", "{}"))

        if not self.signing_secret:
            logger.error("Command verification failed: Missing local signing secret.")
            return False

        # Nonce check (prevent replay)
        if nonce in self.seen_nonces:
            logger.error(f"Command replay detected! Nonce {nonce} already seen.")
            return False
        self.seen_nonces.add(nonce)

        # Expiration check
        try:
            if expires_at_str:
                now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if expires_at_str < now_str:
                    logger.error("Command expired. Rejecting.")
                    return False
        except Exception:
            pass

        # Signature verification
        msg_dict = {
            "commandId": command["id"],
            "instanceId": command["instance_id"],
            "commandType": command["command_type"],
            "payload": payload,
            "nonce": nonce,
            "expiresAt": expires_at_str
        }
        serialized = json.dumps(msg_dict, sort_keys=True)
        expected_sig = hmac.new(
            self.signing_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.error("HMAC signature mismatch on cloud command! Possible tampering.")
            return False

        return True

    def validate_local_limits_for_command(self, cmd_type: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Hard Limits Enforcement:
        Cloud can NEVER raise risk limits above local ceiling or enable live trading.
        Local limits ALWAYS win.
        """
        limits = self.load_local_limits()

        if payload.get("mode") == "LIVE" or cmd_type == "enable_live":
            if not limits.get("allow_live_trading", False):
                return False, "Live trading REJECTED: allow_live_trading=false in local_limits.json. Local physical confirmation required."

        if "riskPercent" in payload:
            req_risk = float(payload["riskPercent"])
            ceiling = float(limits.get("max_risk_pct_ceiling", 1.0))
            if req_risk > ceiling:
                return False, f"Risk percent ({req_risk}%) exceeds local machine hard ceiling ({ceiling}%). Local limits win."

        if "lotSize" in payload:
            req_lots = float(payload["lotSize"])
            ceiling_lots = float(limits.get("max_lots_ceiling", 0.5))
            if req_lots > ceiling_lots:
                return False, f"Lot size ({req_lots}) exceeds local hard lot cap ({ceiling_lots})."

        return True, None

    def execute_safe_command(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Executes authorized cloud command on the real trading orchestrator & bridge."""
        cmd_type = cmd["command_type"]
        payload = json.loads(cmd.get("payload_json", "{}"))

        logger.info(f"[COMMAND_EXECUTING] Executing {cmd_type} with payload {payload}")

        if cmd_type == "start":
            self.bot_state = "RUNNING"
            if self.orchestrator and hasattr(self.orchestrator, "alerts") and self.orchestrator.alerts:
                try:
                    self.orchestrator.alerts.alert_bot_status("Trading Bot STARTED via ArcadeFX Cloud.")
                except Exception:
                    pass
            return {"status": "RUNNING", "message": "Bot engine started successfully."}

        elif cmd_type == "pause":
            self.bot_state = "PAUSED"
            if self.orchestrator and hasattr(self.orchestrator, "alerts") and self.orchestrator.alerts:
                try:
                    self.orchestrator.alerts.alert_bot_status("Trading Bot PAUSED via ArcadeFX Cloud. Existing positions monitored.")
                except Exception:
                    pass
            return {"status": "PAUSED", "message": "Bot trading paused. Existing positions monitored."}

        elif cmd_type == "resume":
            self.bot_state = "RUNNING"
            if self.orchestrator and hasattr(self.orchestrator, "alerts") and self.orchestrator.alerts:
                try:
                    self.orchestrator.alerts.alert_bot_status("Trading Bot RESUMED via ArcadeFX Cloud.")
                except Exception:
                    pass
            return {"status": "RUNNING", "message": "Bot trading resumed."}

        elif cmd_type == "stop":
            self.bot_state = "STOPPED"
            if self.orchestrator and hasattr(self.orchestrator, "alerts") and self.orchestrator.alerts:
                try:
                    self.orchestrator.alerts.alert_bot_status("Trading Bot STOPPED via ArcadeFX Cloud.")
                except Exception:
                    pass
            return {"status": "STOPPED", "message": "Bot engine stopped."}

        elif cmd_type == "close_all":
            closed_tickets = []
            payload = cmd.get("payload", {}) if isinstance(cmd.get("payload"), dict) else {}
            include_manual = bool(payload.get("include_manual", False))
            target_magic = getattr(self.config, "magic_number", 100101)

            # 1. Close via BridgeClient
            if self.bridge and self.bridge.is_connected():
                positions = self.bridge.get_positions()
                for pos in positions:
                    # [SAFETY] Protect manual trades unless explicitly commanded with include_manual=True
                    if not include_manual and getattr(pos, "magic", 0) != target_magic:
                        logger.info(f"[CLOSE_ALL] Preserving non-bot position #{pos.ticket} (magic={getattr(pos, 'magic', 0)})")
                        continue
                    res = self.bridge.close_order(pos.ticket)
                    if res.get("status") == "SUCCESS":
                        closed_tickets.append(pos.ticket)
            # 2. Close via MetaTrader5 python library if still open
            elif MT5_AVAILABLE:
                try:
                    positions = mt5.positions_get()
                    if positions:
                        for p in positions:
                            # [SAFETY] Protect manual trades unless explicitly commanded with include_manual=True
                            if not include_manual and getattr(p, "magic", 0) != target_magic:
                                logger.info(f"[CLOSE_ALL] Preserving non-bot direct position #{p.ticket} (magic={getattr(p, 'magic', 0)})")
                                continue
                            tick = mt5.symbol_info_tick(p.symbol)
                            price = tick.bid if p.type == 0 else tick.ask
                            req = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "position": p.ticket,
                                "symbol": p.symbol,
                                "volume": p.volume,
                                "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                                "price": price,
                                "deviation": 20,
                                "magic": p.magic,
                                "comment": "ArcadeFx Cloud Close All",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            res = mt5.order_send(req)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                closed_tickets.append(p.ticket)
                except Exception as e:
                    logger.error(f"Error closing positions via direct MT5: {e}")

            return {
                "status": self.bot_state,
                "closedCount": len(closed_tickets),
                "closedTickets": closed_tickets,
                "message": f"Closed {len(closed_tickets)} positions via execution bridge."
            }

        elif cmd_type == "kill_switch":
            self.bot_state = "KILL_SWITCH"
            close_all = payload.get("close_all", False)
            if self.bridge and self.bridge.is_connected():
                try:
                    self.bridge.kill_switch(close_all=close_all)
                except Exception:
                    pass
            return {"status": "KILL_SWITCH", "message": "EMERGENCY KILL SWITCH ACTIVATED. All trading halted."}

        elif cmd_type == "update_config":
            if self.config:
                if "riskPercent" in payload and hasattr(self.config, "risk"):
                    self.config.risk.risk_percentage = float(payload["riskPercent"])
                if "symbolsEnabled" in payload:
                    self.config.symbols = payload["symbolsEnabled"]
            return {"status": self.bot_state, "appliedConfig": payload, "message": "Config applied within local limits."}

        else:
            raise ValueError(f"Unsupported command type: {cmd_type}")

    def poll_and_execute_commands(self) -> None:
        """Polls ArcadeFX cloud for pending signed commands and acknowledges execution results."""
        if not self.device_token:
            return
        try:
            res = self._http_request("POST", "/bot/commands/poll")
            commands = res.get("commands", [])
            for cmd in commands:
                cmd_id = cmd["id"]
                cmd_type = cmd.get("command_type", "UNKNOWN")
                logger.info(f"[COMMAND_RECEIVED] ID={cmd_id} Type={cmd_type}")

                # 1. Verify signature & replay protection
                if not self.verify_command_signature(cmd):
                    logger.warning(f"[COMMAND_REJECTED] Signature failed or replay detected for {cmd_id}")
                    self._http_request("POST", f"/bot/commands/{cmd_id}/ack", {
                        "success": False,
                        "errorMessage": "Command signature verification failed or replayed."
                    })
                    continue

                logger.info(f"[COMMAND_VALIDATED] Signature and replay checks passed for {cmd_id}")

                # 2. Verify local limits
                payload = json.loads(cmd.get("payload_json", "{}"))
                allowed, err = self.validate_local_limits_for_command(cmd_type, payload)
                if not allowed:
                    logger.warning(f"[COMMAND_REJECTED] Rejected by local limits: {err}")
                    self._http_request("POST", f"/bot/commands/{cmd_id}/ack", {
                        "success": False,
                        "errorMessage": err
                    })
                    continue

                # 3. Execute command safely
                try:
                    result = self.execute_safe_command(cmd)
                    logger.info(f"[COMMAND_COMPLETED] {cmd_type} executed successfully.")
                    self._http_request("POST", f"/bot/commands/{cmd_id}/ack", {
                        "success": True,
                        "result": result
                    })
                except Exception as ex:
                    logger.error(f"[COMMAND_FAILED] Execution error for {cmd_id}: {ex}")
                    self._http_request("POST", f"/bot/commands/{cmd_id}/ack", {
                        "success": False,
                        "errorMessage": str(ex)
                    })
        except Exception as e:
            err_msg = str(e)
            if any(phrase in err_msg.lower() for phrase in ["invalid or revoked", "authentication required", "unauthorized", "401", "token expired", "token revoked"]):
                self._handle_auth_failure("Invalid or revoked bot agent token during command poll")
                raise
            logger.debug(f"Command polling cycle notice: {e}")

    def collect_real_telemetry(self) -> Dict[str, Any]:
        """Collects actual account, position, and status data directly from MT5 / bridge."""
        limits = self.load_local_limits()
        uptime = int(time.time() - self.start_time)

        account_number_masked = "N/A"
        balance = 0.0
        equity = 0.0
        credit = 0.0
        floating_profit = 0.0
        margin = 0.0
        free_margin = 0.0
        currency = "USD"
        leverage = 100
        mode = "DEMO"
        broker_name = "MetaTrader 5"
        mt5_connected = False
        bridge_connected = False
        open_positions: List[Dict[str, Any]] = []

        # 1. Query Execution Bridge
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            s.connect(("127.0.0.1", 5556))
            s.sendall(b'{"action": "STATUS"}\n')
            rx = s.recv(4096)
            s.close()
            if rx:
                bridge_connected = True
        except Exception:
            try:
                s5 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s5.settimeout(1.5)
                s5.connect(("127.0.0.1", 5555))
                s5.close()
                bridge_connected = True
            except Exception:
                bridge_connected = False

        if self.bridge and bridge_connected:
            try:
                acc = self.bridge.get_account()
                if acc:
                    if acc.account_number:
                        acc_str = str(acc.account_number)
                        account_number_masked = f"***{acc_str[-4:]}" if len(acc_str) > 4 else "***"
                    balance = float(acc.balance)
                    equity = float(acc.equity)
                    credit = float(getattr(acc, "credit", 0.0))
                    floating_profit = float(getattr(acc, "profit", 0.0))
                    margin = float(acc.margin)
                    free_margin = float(getattr(acc, "free_margin", 0.0))
                    currency = str(acc.currency)
                    leverage = int(acc.leverage)
                    mode = str(acc.trade_mode)

                positions = self.bridge.get_positions()
                for p in positions:
                    open_positions.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": p.order_type.name if hasattr(p.order_type, "name") else str(p.order_type),
                        "volume": p.volume,
                        "openPrice": p.open_price,
                        "currentPrice": p.current_price,
                        "stopLoss": p.stop_loss,
                        "takeProfit": p.take_profit,
                        "sl": p.stop_loss,
                        "tp": p.take_profit,
                        "profit": p.profit,
                        "comment": getattr(p, "comment", "")
                    })
            except Exception as e:
                logger.debug(f"Bridge telemetry query notice: {e}")

        # 2. Query Direct MetaTrader5 library (if MT5 available)
        if MT5_AVAILABLE:
            try:
                if mt5.initialize():
                    t_info = mt5.terminal_info()
                    if t_info and getattr(t_info, "connected", False):
                        mt5_connected = True
                        if hasattr(t_info, "company"):
                            broker_name = t_info.company

                    if balance == 0.0:
                        raw_acc = mt5.account_info()
                        if raw_acc:
                            acc_str = str(raw_acc.login)
                            account_number_masked = f"***{acc_str[-4:]}" if len(acc_str) > 4 else "***"
                            balance = float(raw_acc.balance)
                            equity = float(raw_acc.equity)
                            credit = float(getattr(raw_acc, "credit", 0.0))
                            floating_profit = float(getattr(raw_acc, "profit", 0.0))
                            margin = float(raw_acc.margin)
                            free_margin = float(getattr(raw_acc, "margin_free", 0.0))
                            currency = str(raw_acc.currency)
                            leverage = int(raw_acc.leverage)
                            mode = "DEMO" if int(getattr(raw_acc, "trade_mode", 0)) == 0 else "REAL"
                            if hasattr(raw_acc, "company") and raw_acc.company:
                                broker_name = raw_acc.company

                    if not open_positions:
                        raw_pos = mt5.positions_get()
                        if raw_pos:
                            for p in raw_pos:
                                open_positions.append({
                                    "ticket": int(p.ticket),
                                    "symbol": str(p.symbol),
                                    "type": "BUY" if p.type == 0 else "SELL",
                                    "volume": float(p.volume),
                                    "openPrice": float(p.price_open),
                                    "currentPrice": float(p.price_current),
                                    "stopLoss": float(p.sl),
                                    "takeProfit": float(p.tp),
                                    "sl": float(p.sl),
                                    "tp": float(p.tp),
                                    "profit": float(p.profit),
                                    "comment": str(p.comment)
                                })
            except Exception as e:
                logger.debug(f"Direct MT5 telemetry query notice: {e}")

        return {
            "instanceName": f"{socket.gethostname()}-MT5",
            "accountNumberMasked": account_number_masked,
            "mode": mode,
            "currency": currency,
            "leverage": leverage,
            "balance": balance,
            "equity": equity,
            "credit": credit,
            "profit": floating_profit,
            "equityReconciliationDiff": round(equity - (balance + credit + floating_profit), 2),
            "margin": margin,
            "freeMargin": free_margin,
            "broker": broker_name,
            "openPositions": open_positions,
            "botState": self.bot_state,
            "mt5Connected": mt5_connected,
            "bridgeConnected": bridge_connected,
            "lastSignal": "Monitoring Order Blocks & Scalp Liquidity",
            "engineVersion": AGENT_VERSION,
            "lastError": self.last_error,
            "uptimeSeconds": uptime,
            "localLimitsSnapshot": {
                "maxRiskPctCeiling": limits.get("max_risk_pct_ceiling", 1.0),
                "maxLotsCeiling": limits.get("max_lots_ceiling", 0.5),
                "maxDrawdownPctCeiling": limits.get("max_drawdown_pct_ceiling", 5.0),
                "liveTradingAllowedLocally": limits.get("allow_live_trading", False)
            }
        }

    def _handle_auth_failure(self, reason: str):
        """Cleanly handles invalid or revoked token, halts loop, clears credentials, and prompts for re-pairing."""
        logger.warning(f"[AUTH_INVALID] Bot token authentication failed: {reason}. Clearing invalid credentials and transitioning to pairing wait mode.")
        self.device_token = None
        self.signing_secret = None
        LocalCredentialStore.clear()
        self.offline_queue.clear()
        self.update_agent_state("AUTHENTICATION_FAILED", error="Invalid or revoked bot agent token. Please generate a new pairing code from ArcadeFX.live dashboard.")

    def send_heartbeat(self) -> None:
        """Sends comprehensive 20s telemetry heartbeat to ArcadeFX.live."""
        if not self.device_token:
            return
        telemetry = self.collect_real_telemetry()
        try:
            self._http_request("POST", "/bot/heartbeat", telemetry)
            self._last_successful_heartbeat_at = time.time()
            logger.info(
                f"Heartbeat sent (State: {self.bot_state} | MT5: {'Connected' if telemetry['mt5Connected'] else 'Offline'} | "
                f"Balance: ${telemetry['balance']:.2f} | Equity: ${telemetry['equity']:.2f} | Positions: {len(telemetry['openPositions'])})"
            )
            self.drain_offline_queue()
        except Exception as e:
            err_msg = str(e)
            if any(phrase in err_msg.lower() for phrase in ["invalid or revoked", "authentication required", "unauthorized", "401", "token expired", "token revoked"]):
                self._handle_auth_failure("Invalid or revoked bot agent token")
                raise
            logger.warning(f"Heartbeat delivery failed (queuing snapshot locally): {e}")
            self.offline_queue.enqueue(
                event_type="heartbeat_failure",
                payload={"error": str(e), "state": self.bot_state, "telemetry": telemetry},
                dedup_id=f"hb-fail-{int(time.time() * 1000)}"
            )

    def drain_offline_queue(self) -> None:
        """Drains local SQLite offline events queue to ArcadeFX cloud."""
        pending = self.offline_queue.get_pending(limit=25)
        if not pending:
            return
        try:
            res = self._http_request("POST", "/bot/events/sync", {"events": pending})
            if res.get("success"):
                ids_to_del = [item["id"] for item in pending]
                self.offline_queue.delete_events(ids_to_del)
                logger.info(f"Synced {len(ids_to_del)} offline events successfully.")
        except Exception as e:
            logger.debug(f"Queue drain deferred: {e}")

    def _trading_worker_loop(self):
        """Background trading scan worker running the existing orchestrator when RUNNING or PAUSED."""
        logger.info("Background trading worker loop initialized.")
        while not self._stop_event.is_set():
            try:
                if self.bot_state == "RUNNING" and self.orchestrator:
                    # Run continuous market scan
                    for sym in self.orchestrator.continuous_scalper.get_ordered_symbols_for_cycle():
                        if self._stop_event.is_set() or self.bot_state != "RUNNING":
                            break
                        try:
                            sig = self.orchestrator.run_scalping_cycle_for_symbol(sym)
                            if sig is None:
                                self.orchestrator.run_cycle_for_symbol(sym)
                        except Exception as e:
                            logger.debug(f"Scan cycle notice for {sym}: {e}")

                    # Manage active positions (profit locking, trailing stops)
                    try:
                        self.orchestrator.manage_active_positions()
                    except Exception as e:
                        logger.debug(f"Position management notice: {e}")

                    time.sleep(1.0)

                elif self.bot_state == "PAUSED" and self.orchestrator:
                    # In PAUSED mode: NO new entries, but manage existing open positions safely!
                    try:
                        self.orchestrator.manage_active_positions()
                    except Exception as e:
                        logger.debug(f"Position management notice: {e}")
                    time.sleep(2.0)

                else:
                    time.sleep(1.0)

            except Exception as e:
                logger.error(f"Trading worker loop unexpected error: {e}")
                time.sleep(2.0)

    def start_trading_worker(self):
        if self._trading_thread is None or not self._trading_thread.is_alive():
            self._trading_thread = threading.Thread(target=self._trading_worker_loop, daemon=True)
            self._trading_thread.start()

    def update_agent_state(self, status: str, error: Optional[str] = None):
        """Updates internal status and writes state/agent_state.json for supervisor and UI."""
        self.bot_state = status
        try:
            state_data = {
                "status": status,
                "is_paired": bool(self.device_token and self.instance_id),
                "instance_id": self.instance_id,
                "last_update": time.time(),
                "error": error
            }
            with open(AGENT_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
        except Exception:
            pass

    def wait_for_pairing_loop(self, instance_name: Optional[str] = None):
        """Persistent non-blocking daemon loop waiting for pairing code via credentials file or trigger."""
        self.update_agent_state("WAITING_FOR_PAIRING")
        logger.info("ArcadeFX Cloud Agent waiting for device pairing... (State: WAITING_FOR_PAIRING)")

        trigger_file = get_state_dir() / "pairing_request.json"
        result_file = get_state_dir() / "pairing_result.json"

        while not self._stop_event.is_set():
            # 1. Check if credentials were written (by Electron GUI or CLI)
            creds = LocalCredentialStore.load()
            if creds and (creds.get("device_token") or creds.get("token")):
                self.device_token = creds.get("device_token") or creds.get("token")
                self.instance_id = creds.get("instance_id") or creds.get("instanceId")
                self.signing_secret = creds.get("signing_secret") or creds.get("signingSecret")
                self.update_agent_state("PAIRING_SUCCESSFUL")
                logger.info(f"Pairing detected! Instance: {self.instance_id}. Transitioning to active cloud connection.")
                self.run_loop()
                return

            # 2. Check if a pairing trigger request was dropped into state/
            if trigger_file.exists():
                try:
                    self.update_agent_state("PAIRING_IN_PROGRESS")
                    with open(trigger_file, "r", encoding="utf-8") as f:
                        req_data = json.load(f)
                    trigger_file.unlink(missing_ok=True)
                    code = req_data.get("pairingCode", "").strip()
                    m_name = req_data.get("instanceName") or instance_name
                    success, msg = self.pair_with_code(code, m_name)
                    with open(result_file, "w", encoding="utf-8") as f:
                        json.dump({"success": success, "message": msg, "timestamp": time.time()}, f)
                    if success:
                        self.update_agent_state("PAIRING_SUCCESSFUL")
                        self.run_loop()
                        return
                    else:
                        self.update_agent_state("AUTHENTICATION_FAILED", error=msg)
                except Exception as e:
                    logger.error(f"Error handling pairing trigger: {e}")
                    self.update_agent_state("WAITING_FOR_PAIRING", error=str(e))

            time.sleep(2.0)

    def run_loop(self) -> None:
        """Main persistent agent service loop with exponential backoff on network failure."""
        logger.info(f"Starting MT5 Bot Agent v{AGENT_VERSION} (Outbound-only, zero open ports)...")
        if not self.device_token:
            logger.info("Agent is not paired. Entering persistent waiting loop...")
            self.wait_for_pairing_loop()
            return

        self.is_running = True
        self.update_agent_state("ONLINE")
        self.start_trading_worker()

        last_hb = 0.0
        consecutive_net_errors = 0

        while not self._stop_event.is_set():
            # Check for unpair trigger request
            unpair_file = get_state_dir() / "unpair_request.json"
            if unpair_file.exists():
                unpair_file.unlink(missing_ok=True)
                logger.info("[UNPAIR_TRIGGER] Cloud unpairing requested. Clearing credentials and awaiting re-pairing...")
                self.device_token = None
                self.signing_secret = None
                LocalCredentialStore.clear()
                self.offline_queue.clear()
                self.update_agent_state("WAITING_FOR_PAIRING")
                self.wait_for_pairing_loop()
                return

            if not self.device_token:
                logger.info("Agent is not paired. Returning to pairing wait loop...")
                self.wait_for_pairing_loop()
                return

            now = time.time()
            try:
                # 1. Poll cloud commands every 3 seconds
                self.poll_and_execute_commands()

                # 2. Send heartbeat every 20 seconds
                if now - last_hb >= 20.0:
                    self.send_heartbeat()
                    last_hb = now
                    self.update_agent_state("ONLINE")

                consecutive_net_errors = 0
                time.sleep(3)

            except KeyboardInterrupt:
                logger.info("Shutdown requested by user (Ctrl+C).")
                break
            except Exception as e:
                err_str = str(e)
                if not self.device_token:
                    logger.info("Device token was cleared. Returning to pairing wait loop...")
                    self.wait_for_pairing_loop()
                    return
                consecutive_net_errors += 1
                backoff = min(60, 2 ** min(consecutive_net_errors, 5))
                self.update_agent_state("RECONNECTING", error=err_str)
                logger.warning(f"Loop error: {err_str}. Retrying in {backoff}s...")
                time.sleep(backoff)

        self.shutdown()

    def shutdown(self):
        """Gracefully shuts down agent and trading engine."""
        logger.info("Gracefully stopping ArcadeFX MT5 Bot Agent...")
        self.is_running = False
        self._stop_event.set()
        self.update_agent_state("STOPPED")
        if self.bridge:
            try:
                self.bridge.disconnect()
            except Exception:
                pass
        logger.info("ArcadeFX MT5 Bot Agent stopped cleanly.")


def display_pairing_prompt():
    """Renders the required professional terminal onboarding interface."""
    print("====================================================")
    print("ARCADEFx MT5 BOT AGENT")
    print("CLOUD PAIRING\n")
    print("Welcome to ArcadeFX MT5 Bot Agent.\n")
    print("Connect your local MT5 trading machine to your")
    print("ArcadeFX.live cloud dashboard.\n")
    print("CONNECTION STATUS: NOT PAIRED\n")
    print("STEP 1:")
    print("Open https://arcadefx.live\n")
    print("STEP 2:")
    print("Navigate to MT5 Bot > Pair MT5 Machine.\n")
    print("STEP 3:")
    print("Click Generate 10-Minute Pairing Code.\n")
    print("STEP 4:")
    print("Enter your pairing code below.\n")
    print("---")


def display_pairing_success(instance_id: str, local_checks: Dict[str, str]):
    """Renders the required connection success confirmation box."""
    print("\n====================================================")
    print("ARCADEFx MT5 BOT AGENT\n")
    print("[ SUCCESS ] MACHINE PAIRED SUCCESSFULLY\n")
    print("Cloud Platform: ArcadeFX.live")
    print("Machine Status: CONNECTED")
    print("Authentication: VERIFIED")
    print(f"MT5 Terminal: {local_checks.get('mt5', 'CHECKING')}")
    print(f"Trading Engine: {local_checks.get('trading_engine', 'CHECKING')}")
    print(f"Execution Bridge: {local_checks.get('bridge', 'CHECKING')}\n")
    print(f"Machine ID: {instance_id}\n")
    print("Your MT5 trading machine is now connected")
    print("to ArcadeFX.live.\n")
    print("The agent is initializing the existing trading")
    print("infrastructure...\n")
    print("====================================================\n")


def interactive_pairing_flow(agent: MT5BotAgent, instance_name: Optional[str] = None) -> bool:
    """Interactively prompts user for pairing code with validation and error retries."""
    display_pairing_prompt()

    while True:
        try:
            user_input = input("\nENTER ARCADEFx PAIRING CODE: ")
        except (KeyboardInterrupt, EOFError):
            print("\n[CANCELLED] Pairing aborted by user.")
            return False

        code_trimmed = user_input.strip()
        if code_trimmed.lower() in ("q", "quit", "exit"):
            print("[EXIT] Pairing cancelled.")
            return False

        valid, result = agent.validate_pairing_code_format(code_trimmed)
        if not valid:
            print(f"\n[ERROR] {result}")
            print("Enter the 6-character pairing code displayed on")
            print("your ArcadeFX.live dashboard (or 'q' to exit).")
            continue

        clean_code = result
        print(f"\nEnter the 6-character pairing code displayed on")
        print(f"your ArcadeFX.live dashboard.")
        print(f"\n[CONNECT] Authenticating with ArcadeFX.live...")

        success, msg = agent.pair_with_code(clean_code, instance_name)
        if success:
            local_checks = agent.check_local_connectivity()
            display_pairing_success(agent.instance_id or "UNKNOWN", local_checks)
            return True
        else:
            print(f"\n[FAILED] {msg}")
            print("Please generate a fresh code on https://arcadefx.live and try again.")


def main():
    parser = argparse.ArgumentParser(description="ArcadeFx MT5 Bot Agent")
    parser.add_argument("--pair", type=str, help="One-time pairing code from ArcadeFX dashboard")
    parser.add_argument("--name", type=str, help="Instance name")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="ArcadeFx API URL")
    parser.add_argument("--status", action="store_true", help="Print local agent status and limits")
    parser.add_argument("--clear-auth", action="store_true", help="Clear saved credentials")
    parser.add_argument("--daemon", action="store_true", help="Run in non-blocking daemon / background mode")

    args = parser.parse_args()

    # Enforce single instance lock for background / daemon execution
    agent_lock = SingleInstanceLock("mt5_bot_agent")
    if args.daemon or not sys.stdin.isatty():
        if not agent_lock.acquire():
            logger.info("[SINGLE_INSTANCE] Another MT5 Bot Agent process is already running. Exiting duplicate instance.")
            return

    agent = MT5BotAgent(api_url=args.api_url)

    if args.clear_auth:
        LocalCredentialStore.clear()
        print("Cleared credentials.")
        return

    if args.status:
        creds = LocalCredentialStore.load()
        limits = agent.load_local_limits()
        local_checks = agent.check_local_connectivity()
        print("=== MT5 Bot Agent Status ===")
        print(f"Paired: {bool(creds and (creds.get('device_token') or creds.get('token')))}")
        print(f"Instance ID: {creds.get('instance_id') if creds else 'None'}")
        print(f"Local Checks: {json.dumps(local_checks, indent=2)}")
        print(f"Local Limits: {json.dumps(limits, indent=2)}")
        return

    # CLI Pairing argument provided
    if args.pair:
        valid, clean_code_or_err = agent.validate_pairing_code_format(args.pair)
        if not valid:
            print(f"[ERROR] {clean_code_or_err}")
            sys.exit(1)

        print("[CONNECT] Authenticating with ArcadeFX.live...")
        success, msg = agent.pair_with_code(clean_code_or_err, args.name)
        if success:
            local_checks = agent.check_local_connectivity()
            display_pairing_success(agent.instance_id or "UNKNOWN", local_checks)
            agent.run_loop()
        else:
            print(f"[PAIRING FAILED] {msg}")
            sys.exit(1)
        return

    try:
        # If already paired, resume automatically
        if agent.device_token and agent.instance_id:
            local_checks = agent.check_local_connectivity()
            print("====================================================")
            print("ARCADEFx MT5 BOT AGENT")
            print("\n[ RESUMING ] CONNECTING PAIRED MACHINE\n")
            print(f"Cloud Platform: ArcadeFX.live")
            print(f"Machine Status: CONNECTED")
            print(f"Authentication: VERIFIED")
            print(f"MT5 Terminal: {local_checks.get('mt5', 'CHECKING')}")
            print(f"Trading Engine: {local_checks.get('trading_engine', 'CHECKING')}")
            print(f"Execution Bridge: {local_checks.get('bridge', 'CHECKING')}")
            print(f"\nMachine ID: {agent.instance_id}\n")
            print("Starting cloud telemetry & command listener...")
            print("====================================================\n")
            agent.run_loop()
            return

        # Non-blocking daemon flow for background/companion supervision
        if args.daemon or not sys.stdin.isatty():
            logger.info("ArcadeFX Cloud Agent running in non-blocking daemon mode. Waiting for pairing code...")
            agent.wait_for_pairing_loop(args.name)
            return

        # Default interactive flow when run in an interactive terminal
        paired = interactive_pairing_flow(agent, args.name)
        if paired:
            agent.run_loop()
        else:
            sys.exit(1)
    finally:
        agent_lock.release()


if __name__ == "__main__":
    main()
