"""
Opt-in Read-Only Mobile Sync HTTP/SSE Server for Institutional EA Companion.

Security guarantees:
- OFF by default: never binds to a network interface until explicitly enabled
  by the desktop operator via localhost-only management endpoints.
- Strictly READ-ONLY: only GET data/stream endpoints plus POST /api/mobile/v1/pair
  (rate-limited) and POST /api/mobile/v1/unpair (self-revoke) exist. Every other
  write method/path is rejected with HTTP 403 READ_ONLY_ENFORCED.
- Per-device revocable tokens stored as SHA-256 hashes in SQLite (never plaintext),
  completely separate from the desktop LocalAuthManager session token.
- Never exposes MT5 credentials, API keys, Telegram tokens, or desktop session tokens.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import queue
import secrets
import socket
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from companion.service.market.drawings_engine import canonical_symbol

MOBILE_SYNC_SCHEMA_VERSION = "1.0.0"
APP_VERSION = "1.3.5"
DEFAULT_MOBILE_PORT = 8766
PAIRING_CODE_TTL_SEC = 300
PAIR_RATE_LIMIT_MAX_ATTEMPTS = 5
PAIR_RATE_LIMIT_WINDOW_SEC = 300
SUPPORTED_TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4"]
SUPPORTED_LAYERS = ["LIQ", "FVG_OB", "STRUCT", "SESS", "TRADES"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _mask_account_number(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text or text == "0":
        return "Not connected"
    if len(text) <= 4:
        return "***" + text[-2:]
    return f"{text[:2]}***{text[-3:]}"


def _discover_lan_ipv4_addresses() -> List[str]:
    """Returns non-loopback IPv4 addresses sorted with private RFC1918 LAN IPs first."""
    found: List[str] = []
    # Primary outbound interface probe (no packets sent on UDP connect)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("10.255.255.255", 1))
            primary = sock.getsockname()[0]
            if primary and not primary.startswith("127."):
                found.append(primary)
        finally:
            sock.close()
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except Exception:
        pass

    def _priority(ip: str) -> int:
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            parts = ip.split(".")
            if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return 2
        return 3

    found.sort(key=_priority)
    return found or ["127.0.0.1"]


def _parse_iso_ts(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


class MobileDeviceStore:
    """Thread-safe SQLite store for paired mobile devices (hashed tokens only)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mobile_paired_devices (
                        device_id TEXT PRIMARY KEY,
                        device_name TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        paired_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        revoked INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.commit()

    def create_device(self, device_name: str, platform: str) -> Tuple[Dict[str, Any], str]:
        device_id = f"mob_{uuid.uuid4().hex[:16]}"
        raw_token = f"iea_ro_{secrets.token_urlsafe(32)}"
        token_hash = _hash_token(raw_token)
        now = _utc_now_iso()
        clean_name = (device_name or "Android Device").strip()[:64] or "Android Device"
        clean_platform = (platform or "android").strip().lower()[:16]
        if clean_platform not in ("android", "ios", "web"):
            clean_platform = "android"

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO mobile_paired_devices
                        (device_id, device_name, platform, token_hash, paired_at, last_seen_at, revoked)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (device_id, clean_name, clean_platform, token_hash, now, now),
                )
                conn.commit()

        device = {
            "deviceId": device_id,
            "deviceName": clean_name,
            "platform": clean_platform,
            "pairedAt": now,
            "lastSeenAt": now,
            "revoked": False,
        }
        return device, raw_token

    def verify_token(self, raw_token: str) -> Optional[Dict[str, Any]]:
        if not raw_token or not raw_token.startswith("iea_ro_"):
            return None
        supplied_hash = _hash_token(raw_token)
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT device_id, device_name, platform, token_hash, paired_at, last_seen_at, revoked
                    FROM mobile_paired_devices
                    WHERE token_hash = ? AND revoked = 0
                    """,
                    (supplied_hash,),
                ).fetchone()
                if not row:
                    return None
                if not hmac.compare_digest(row["token_hash"], supplied_hash):
                    return None
                now = _utc_now_iso()
                conn.execute(
                    "UPDATE mobile_paired_devices SET last_seen_at = ? WHERE device_id = ?",
                    (now, row["device_id"]),
                )
                conn.commit()
                return {
                    "deviceId": row["device_id"],
                    "deviceName": row["device_name"],
                    "platform": row["platform"],
                    "pairedAt": row["paired_at"],
                    "lastSeenAt": now,
                }

    def list_devices(self) -> List[Dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT device_id, device_name, platform, paired_at, last_seen_at
                    FROM mobile_paired_devices
                    WHERE revoked = 0
                    ORDER BY paired_at DESC
                    """
                ).fetchall()
                return [
                    {
                        "deviceId": r["device_id"],
                        "deviceName": r["device_name"],
                        "platform": r["platform"],
                        "pairedAt": r["paired_at"],
                        "lastSeenAt": r["last_seen_at"],
                    }
                    for r in rows
                ]

    def revoke_device(self, device_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE mobile_paired_devices SET revoked = 1 WHERE device_id = ? AND revoked = 0",
                    (device_id,),
                )
                conn.commit()
                return cur.rowcount > 0

    def revoke_all(self) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE mobile_paired_devices SET revoked = 1 WHERE revoked = 0"
                )
                conn.commit()
                return cur.rowcount


class MobileSyncManager:
    """
    Controls the opt-in LAN read-only mobile sync HTTP/SSE server, pairing codes,
    rate limiting, and device token revocation.
    """

    def __init__(
        self,
        ctx: Any,
        db_path: Optional[Path] = None,
        port: int = DEFAULT_MOBILE_PORT,
        bind_host: str = "0.0.0.0",
    ):
        self.ctx = ctx
        self.port = int(port)
        self.bind_host = bind_host
        self.store = MobileDeviceStore(
            db_path or (Path(ctx.data_dir) / "data" / "mobile_sync.db")
        )
        self._lock = threading.RLock()
        self._enabled = False
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._active_code: Optional[str] = None
        self._code_expires_at: float = 0.0
        self._pair_failures: Dict[str, List[float]] = {}
        self._companion_name = socket.gethostname() or "Institutional-EA-PC"

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            hosts = _discover_lan_ipv4_addresses()
            now = time.time()
            code_valid = bool(self._active_code and now < self._code_expires_at)
            qr_payload = None
            if self._enabled and code_valid:
                qr_payload = {
                    "v": 1,
                    "host": hosts[0],
                    "hosts": hosts,
                    "port": self.port,
                    "code": self._active_code,
                    "expiresAt": int(self._code_expires_at),
                    "companionName": self._companion_name,
                }
            return {
                "enabled": self._enabled,
                "port": self.port,
                "hosts": hosts,
                "primaryHost": hosts[0],
                "companionName": self._companion_name,
                "schemaVersion": MOBILE_SYNC_SCHEMA_VERSION,
                "readOnlyEnforced": True,
                "pairingCode": self._active_code if code_valid else None,
                "pairingCodeExpiresAt": int(self._code_expires_at) if code_valid else None,
                "qrPayload": qr_payload,
                "devices": self.store.list_devices(),
            }

    def generate_pairing_code(self, ttl_sec: int = PAIRING_CODE_TTL_SEC) -> Dict[str, Any]:
        with self._lock:
            self._active_code = f"{secrets.randbelow(1_000_000):06d}"
            self._code_expires_at = time.time() + max(30, int(ttl_sec))
            return self.get_status()

    def enable(self, port: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            if self._enabled and self._server is not None:
                if not self._active_code or time.time() >= self._code_expires_at:
                    self.generate_pairing_code()
                return self.get_status()

            if port is not None:
                self.port = int(port)

            handler = self._build_handler()
            server = ThreadingHTTPServer((self.bind_host, self.port), handler)
            self.port = int(server.server_address[1])
            self._server = server
            self._enabled = True
            self._thread = threading.Thread(
                target=server.serve_forever,
                name="mobile-sync-http",
                daemon=True,
            )
            self._thread.start()
            self.generate_pairing_code()
            if getattr(self.ctx, "events", None):
                self.ctx.events.log(
                    "MOBILE_SYNC",
                    "INFO",
                    f"Opt-in read-only Mobile Sync enabled on port {self.port}",
                )
            return self.get_status()

    def disable(self) -> Dict[str, Any]:
        with self._lock:
            srv = self._server
            self._server = None
            self._enabled = False
            self._active_code = None
            self._code_expires_at = 0.0
        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
        if getattr(self.ctx, "events", None):
            self.ctx.events.log("MOBILE_SYNC", "INFO", "Mobile Sync disabled and LAN listener stopped")
        return self.get_status()

    def revoke_device(self, device_id: str) -> Dict[str, Any]:
        revoked = self.store.revoke_device(device_id)
        if revoked and getattr(self.ctx, "events", None):
            self.ctx.events.publish_event("mobile_device_revoked", {"deviceId": device_id})
            self.ctx.events.log("MOBILE_SYNC", "INFO", f"Revoked mobile device {device_id}")
        return {"revoked": revoked, "status": self.get_status()}

    def revoke_all_devices(self) -> Dict[str, Any]:
        count = self.store.revoke_all()
        if count > 0 and getattr(self.ctx, "events", None):
            self.ctx.events.publish_event("mobile_device_revoked", {"all": True})
            self.ctx.events.log("MOBILE_SYNC", "INFO", f"Revoked all {count} mobile devices")
        return {"revokedCount": count, "status": self.get_status()}

    def _check_rate_limit(self, client_ip: str) -> bool:
        now = time.time()
        with self._lock:
            attempts = [
                ts for ts in self._pair_failures.get(client_ip, [])
                if now - ts < PAIR_RATE_LIMIT_WINDOW_SEC
            ]
            self._pair_failures[client_ip] = attempts
            return len(attempts) < PAIR_RATE_LIMIT_MAX_ATTEMPTS

    def _record_pair_failure(self, client_ip: str) -> None:
        now = time.time()
        with self._lock:
            attempts = [
                ts for ts in self._pair_failures.get(client_ip, [])
                if now - ts < PAIR_RATE_LIMIT_WINDOW_SEC
            ]
            attempts.append(now)
            self._pair_failures[client_ip] = attempts

    def _claim_pairing_code(
        self, client_ip: str, code: str, device_name: str, platform: str
    ) -> Tuple[int, Dict[str, Any]]:
        if not self._check_rate_limit(client_ip):
            return 429, {
                "error": "RATE_LIMITED",
                "message": "Too many pairing attempts. Wait 5 minutes and try again.",
            }

        clean_code = str(code or "").strip()
        with self._lock:
            now = time.time()
            expected = self._active_code
            expires = self._code_expires_at
            if not expected or now >= expires or not hmac.compare_digest(clean_code, expected):
                self._record_pair_failure(client_ip)
                return 401, {
                    "error": "INVALID_OR_EXPIRED_CODE",
                    "message": "Pairing code is invalid or expired. Generate a new code on your PC.",
                }
            # Rotate/invalidate single-use code on successful claim
            self._active_code = None
            self._code_expires_at = 0.0

        device, raw_token = self.store.create_device(device_name=device_name, platform=platform)
        if getattr(self.ctx, "events", None):
            self.ctx.events.log(
                "MOBILE_SYNC",
                "INFO",
                f"Paired read-only mobile device '{device['deviceName']}' ({device['deviceId']})",
            )
        return 200, {
            "deviceId": device["deviceId"],
            "deviceToken": raw_token,
            "companionName": self._companion_name,
            "schemaVersion": MOBILE_SYNC_SCHEMA_VERSION,
            "readOnly": True,
            "pairedAt": device["pairedAt"],
        }

    # --- Read-only payload builders (single source of truth from companion) ---

    def build_status_payload(self) -> Dict[str, Any]:
        eng = self.ctx.engine.get_status()
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        raw_state = str(eng.get("engine_state") or eng.get("state") or "STOPPED").upper()
        if raw_state not in ("RUNNING", "PAUSED", "STOPPED", "STARTING", "ERROR", "EMERGENCY_STOP"):
            raw_state = "UNKNOWN"
        mt5_status = str(snap.get("connection_status") or "DISCONNECTED").upper()
        if mt5_status not in ("CONNECTED", "DISCONNECTED", "SYNCHRONIZING", "ERROR"):
            mt5_status = "DISCONNECTED"
        return {
            "schemaVersion": MOBILE_SYNC_SCHEMA_VERSION,
            "appVersion": APP_VERSION,
            "botState": raw_state,
            "mt5Connected": mt5_status == "CONNECTED",
            "mt5Status": mt5_status,
            "demoMode": bool(acc.get("demo_verified", False)),
            "broker": str(acc.get("broker") or "Not Connected"),
            "accountMasked": _mask_account_number(acc.get("account_number")),
            "lastHeartbeat": snap.get("last_sync_at") or eng.get("last_heartbeat"),
            "serverTime": _utc_now_iso(),
            "readOnlyEnforced": True,
        }

    def build_account_payload(self) -> Dict[str, Any]:
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        positions = snap.get("positions") or []
        balance = float(acc.get("balance", 0.0) or 0.0)
        equity = float(acc.get("equity", 0.0) or 0.0)
        floating = round(equity - balance, 2) if (balance or equity) else round(
            sum(float(p.get("profit", 0.0) or 0.0) for p in positions), 2
        )
        return {
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "margin": round(float(acc.get("margin", 0.0) or 0.0), 2),
            "freeMargin": round(float(acc.get("free_margin", 0.0) or 0.0), 2),
            "marginLevel": round(float(acc.get("margin_level", 0.0) or 0.0), 2),
            "floatingPnl": floating,
            "currency": str(acc.get("currency") or "USD"),
            "leverage": int(acc.get("leverage", 0) or 0),
            "tradeMode": str(acc.get("trade_mode") or "UNKNOWN"),
            "broker": str(acc.get("broker") or "Not Connected"),
            "accountMasked": _mask_account_number(acc.get("account_number")),
            "openPositionsCount": len(positions),
            "updatedAt": snap.get("last_sync_at"),
        }

    def build_stats_payload(self) -> Dict[str, Any]:
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        currency = str(acc.get("currency") or "USD")
        trades = self.ctx.repo.get_trade_records(limit=2000) or []
        closed = [t for t in trades if str(t.get("status", "")).upper() != "OPEN"]
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        total_profit = 0.0
        today_pnl = 0.0
        wins = 0
        losses = 0
        trades_today = 0

        for t in closed:
            pnl = float(t.get("pnl", t.get("profit", 0.0)) or 0.0)
            total_profit += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            ts_str = str(t.get("closed_at") or t.get("opened_at") or "")
            if ts_str.startswith(today_prefix):
                today_pnl += pnl
                trades_today += 1

        deals_count = len(closed)
        decided = wins + losses
        win_rate = round((wins / decided) * 100.0, 2) if decided > 0 else 0.0
        return {
            "todayPnl": round(today_pnl, 2),
            "totalProfit": round(total_profit, 2),
            "winRate": win_rate,
            "dealsCount": deals_count,
            "tradesToday": trades_today,
            "winsCount": wins,
            "lossesCount": losses,
            "currency": currency,
            "computedAt": _utc_now_iso(),
        }

    def build_positions_payload(self) -> Dict[str, Any]:
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        syms = snap.get("symbols") or {}
        out: List[Dict[str, Any]] = []
        for p in snap.get("positions") or []:
            sym = str(p.get("symbol") or "")
            canon = canonical_symbol(sym)
            spec = syms.get(sym) or syms.get(canon) or {}
            digits = int(spec.get("digits", 2 if "XAU" in canon or "BTC" in canon else 3 if "JPY" in canon else 5))
            raw_type = str(p.get("direction") or p.get("type") or "BUY").upper()
            pos_type = "SELL" if "SELL" in raw_type or raw_type == "1" else "BUY"
            sl_val = p.get("sl")
            tp_val = p.get("tp")
            open_ts = _parse_iso_ts(p.get("open_time") or p.get("opened_at") or p.get("time")) or 0
            ownership = str(p.get("ownership") or "BOT_OWN").upper()
            if ownership not in ("BOT_OWN", "MANUAL", "OTHER_EA"):
                ownership = "BOT_OWN"
            out.append({
                "ticket": int(p.get("ticket", 0) or 0),
                "symbol": sym or canon,
                "canonicalSymbol": canon or sym,
                "type": pos_type,
                "volume": float(p.get("volume", 0.0) or 0.0),
                "openPrice": float(p.get("open_price", p.get("price_open", 0.0)) or 0.0),
                "currentPrice": float(p.get("current_price", p.get("price_current", 0.0)) or 0.0),
                "sl": float(sl_val) if sl_val is not None and float(sl_val) > 0 else None,
                "tp": float(tp_val) if tp_val is not None and float(tp_val) > 0 else None,
                "profit": round(float(p.get("profit", 0.0) or 0.0), 2),
                "swap": round(float(p.get("swap", 0.0) or 0.0), 2),
                "openTime": int(open_ts),
                "digits": digits,
                "ownership": ownership,
                "comment": str(p.get("comment") or ""),
            })
        return {
            "positions": out,
            "currency": str(acc.get("currency") or "USD"),
            "updatedAt": snap.get("last_sync_at"),
        }

    def build_trades_payload(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        syms = snap.get("symbols") or {}
        page = max(1, int(query.get("page", ["1"])[0] or "1"))
        limit = max(1, min(100, int(query.get("limit", ["25"])[0] or "25")))
        symbol_filter = (query.get("symbol", [""])[0] or "").strip().upper()
        outcome_filter = (query.get("outcome", ["ALL"])[0] or "ALL").strip().upper()
        from_iso = query.get("from", [None])[0]
        to_iso = query.get("to", [None])[0]
        sort_by = (query.get("sort", ["time_desc"])[0] or "time_desc").strip().lower()
        search_q = (query.get("q", [""])[0] or "").strip().lower()

        from_ts = _parse_iso_ts(from_iso)
        to_ts = _parse_iso_ts(to_iso)

        raw_trades = self.ctx.repo.get_trade_records(limit=2000) or []
        normalized: List[Dict[str, Any]] = []
        for t in raw_trades:
            sym = str(t.get("symbol") or "")
            canon = canonical_symbol(sym)
            if symbol_filter and symbol_filter != "ALL" and canon != canonical_symbol(symbol_filter):
                continue
            pnl = round(float(t.get("pnl", t.get("profit", 0.0)) or 0.0), 2)
            if outcome_filter == "WIN" and pnl <= 0:
                continue
            if outcome_filter == "LOSS" and pnl >= 0:
                continue

            opened_at = t.get("opened_at")
            closed_at = t.get("closed_at")
            ref_ts = _parse_iso_ts(closed_at or opened_at)
            if from_ts is not None and (ref_ts is None or ref_ts < from_ts):
                continue
            if to_ts is not None and (ref_ts is None or ref_ts > to_ts):
                continue

            raw_dir = str(t.get("direction") or t.get("side") or "BUY").upper()
            direction = "SELL" if "SELL" in raw_dir else "BUY"
            strategy_tag = str(t.get("strategy_tag") or t.get("comment") or "")
            ticket = int(t.get("ticket", 0) or 0)

            if search_q:
                haystack = f"{ticket} {sym} {canon} {direction} {strategy_tag}".lower()
                if search_q not in haystack:
                    continue

            open_ts = _parse_iso_ts(opened_at)
            close_ts = _parse_iso_ts(closed_at)
            duration_sec = (
                max(0, int(close_ts - open_ts))
                if (open_ts is not None and close_ts is not None)
                else None
            )
            spec = syms.get(sym) or syms.get(canon) or {}
            digits = int(spec.get("digits", 2 if "XAU" in canon or "BTC" in canon else 3 if "JPY" in canon else 5))

            entry_p = t.get("entry_price", t.get("open_price"))
            exit_p = t.get("exit_price", t.get("close_price"))
            sl_p = t.get("sl")
            tp_p = t.get("tp")

            normalized.append({
                "ticket": ticket,
                "symbol": sym or canon,
                "canonicalSymbol": canon or sym,
                "direction": direction,
                "volume": float(t.get("volume", 0.0) or 0.0),
                "entryPrice": float(entry_p) if entry_p is not None else None,
                "exitPrice": float(exit_p) if exit_p is not None else None,
                "sl": float(sl_p) if sl_p is not None and float(sl_p) > 0 else None,
                "tp": float(tp_p) if tp_p is not None and float(tp_p) > 0 else None,
                "pnl": pnl,
                "openedAt": str(opened_at) if opened_at else None,
                "closedAt": str(closed_at) if closed_at else None,
                "durationSec": duration_sec,
                "status": str(t.get("status") or "CLOSED").upper(),
                "strategyTag": strategy_tag,
                "digits": digits,
                "_sort_ts": ref_ts or 0.0,
            })

        if sort_by == "time_asc":
            normalized.sort(key=lambda x: x["_sort_ts"])
        elif sort_by == "pnl_desc":
            normalized.sort(key=lambda x: x["pnl"], reverse=True)
        elif sort_by == "pnl_asc":
            normalized.sort(key=lambda x: x["pnl"])
        else:
            normalized.sort(key=lambda x: x["_sort_ts"], reverse=True)

        total = len(normalized)
        wins = sum(1 for x in normalized if x["pnl"] > 0)
        losses = sum(1 for x in normalized if x["pnl"] < 0)
        decided = wins + losses
        net_pnl = round(sum(x["pnl"] for x in normalized), 2)
        win_rate = round((wins / decided) * 100.0, 2) if decided > 0 else 0.0

        start = (page - 1) * limit
        end = start + limit
        page_items = []
        for item in normalized[start:end]:
            clean = {k: v for k, v in item.items() if k != "_sort_ts"}
            page_items.append(clean)

        return {
            "page": page,
            "limit": limit,
            "total": total,
            "hasMore": end < total,
            "currency": str(acc.get("currency") or "USD"),
            "summary": {
                "count": total,
                "netPnl": net_pnl,
                "winRate": win_rate,
                "wins": wins,
                "losses": losses,
            },
            "items": page_items,
        }

    def build_symbols_payload(self) -> Dict[str, Any]:
        snap = self.ctx.mt5_sync.get_snapshot()
        syms = snap.get("symbols") or {}
        seen = set()
        out: List[Dict[str, Any]] = []
        for broker_sym, spec in syms.items():
            canon = canonical_symbol(broker_sym)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            bid = spec.get("bid")
            ask = spec.get("ask")
            point = float(spec.get("point", 0.01) or 0.01)
            digits = int(spec.get("digits", 2) or 2)
            spread_pts = spec.get("spread_points")
            if spread_pts is None and bid is not None and ask is not None and point > 0:
                spread_pts = round((float(ask) - float(bid)) / point, 1)
            out.append({
                "symbol": canon,
                "brokerSymbol": str(broker_sym),
                "digits": digits,
                "point": point,
                "bid": float(bid) if bid is not None else None,
                "ask": float(ask) if ask is not None else None,
                "spreadPoints": float(spread_pts) if spread_pts is not None else None,
            })
        return {
            "symbols": out,
            "timeframes": list(SUPPORTED_TIMEFRAMES),
            "layers": list(SUPPORTED_LAYERS),
        }

    def build_candles_payload(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        sym = query.get("symbol", [""])[0].strip()
        if not sym:
            syms_payload = self.build_symbols_payload()
            sym = syms_payload["symbols"][0]["symbol"] if syms_payload["symbols"] else "XAUUSD"
        tf = query.get("tf", ["M5"])[0].strip().upper()
        if tf not in SUPPORTED_TIMEFRAMES:
            tf = "M5"
        limit = max(10, min(500, int(query.get("limit", query.get("count", ["160"]))[0] or "160")))
        from_iso = query.get("from", [None])[0]
        to_iso = query.get("to", [None])[0]

        res = self.ctx.mt5_sync.get_candles(sym, tf, limit, from_iso, to_iso) or {}
        candles_out = []
        for c in res.get("candles") or []:
            t_val = _parse_iso_ts(c.get("time"))
            if t_val is None:
                continue
            candles_out.append({
                "time": int(t_val),
                "open": float(c.get("open", 0.0)),
                "high": float(c.get("high", 0.0)),
                "low": float(c.get("low", 0.0)),
                "close": float(c.get("close", 0.0)),
                "volume": float(c.get("volume", c.get("tick_volume", 0)) or 0),
            })
        canon = canonical_symbol(sym)
        return {
            "symbol": canon or sym,
            "brokerSymbol": str(res.get("broker_symbol") or res.get("symbol") or sym),
            "timeframe": tf,
            "digits": int(res.get("digits", 2) or 2),
            "point": float(res.get("point", 0.01) or 0.01),
            "bid": float(res["bid"]) if res.get("bid") is not None else None,
            "ask": float(res["ask"]) if res.get("ask") is not None else None,
            "spreadPoints": float(res["spread_points"]) if res.get("spread_points") is not None else None,
            "candles": candles_out,
            "stale": bool(res.get("stale", False)),
            "marketClosed": bool(res.get("market_closed", False)),
            "tickTimeUtc": res.get("tick_time_utc"),
            "source": str(res.get("source") or "MT5"),
        }

    def build_drawings_payload(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        sym = query.get("symbol", [""])[0].strip()
        if not sym:
            syms_payload = self.build_symbols_payload()
            sym = syms_payload["symbols"][0]["symbol"] if syms_payload["symbols"] else "XAUUSD"
        tf = query.get("tf", ["M5"])[0].strip().upper()
        if tf not in SUPPORTED_TIMEFRAMES:
            tf = "M5"
        count = max(20, min(500, int(query.get("count", ["160"])[0] or "160")))
        return self.ctx.chart_drawings.get_drawings(sym, tf, count)

    def build_equity_payload(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        rng = (query.get("range", ["1W"])[0] or "1W").strip().upper()
        if rng not in ("1D", "1W", "1M", "ALL"):
            rng = "1W"
        snap = self.ctx.mt5_sync.get_snapshot()
        acc = snap.get("account") or {}
        currency = str(acc.get("currency") or "USD")
        now_ts = time.time()
        cutoff = {
            "1D": now_ts - 86400,
            "1W": now_ts - 7 * 86400,
            "1M": now_ts - 30 * 86400,
            "ALL": 0.0,
        }[rng]

        snapshots = self.ctx.repo.get_balance_snapshots(limit=500) or []
        points: List[Dict[str, Any]] = []
        base_balance: Optional[float] = None
        for row in snapshots:
            ts = _parse_iso_ts(row.get("timestamp") or row.get("created_at"))
            if ts is None or ts < cutoff:
                continue
            bal = float(row.get("balance", 0.0) or 0.0)
            eq = float(row.get("equity", bal) or bal)
            if base_balance is None:
                base_balance = bal
            points.append({
                "time": int(ts),
                "balance": round(bal, 2),
                "equity": round(eq, 2),
                "pnl": round(eq - base_balance, 2),
            })
        points.sort(key=lambda x: x["time"])
        return {
            "range": rng,
            "currency": currency,
            "points": points,
        }

    def build_activity_payload(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        limit = max(1, min(100, int(query.get("limit", ["40"])[0] or "40")))
        events_out: List[Dict[str, Any]] = []
        try:
            alerts = self.ctx.repo.get_alerts(limit=limit) or []
            for a in alerts:
                events_out.append({
                    "id": f"alert_{a.get('id', '')}",
                    "timestamp": str(a.get("created_at") or a.get("timestamp") or _utc_now_iso()),
                    "type": str(a.get("alert_type") or "ALERT").upper(),
                    "severity": str(a.get("severity") or "INFO").upper(),
                    "symbol": a.get("symbol") or None,
                    "message": str(a.get("message") or ""),
                    "ticket": int(a["ticket"]) if a.get("ticket") else None,
                })
        except Exception:
            pass

        try:
            logs = self.ctx.events.get_logs(limit=limit) or []
            for idx, entry in enumerate(logs):
                comp = str(entry.get("component") or entry.get("service") or "BOT").upper()
                if comp in ("CONTROL_SERVICE", "HTTP"):
                    continue
                events_out.append({
                    "id": f"log_{entry.get('id', idx)}",
                    "timestamp": str(entry.get("timestamp") or _utc_now_iso()),
                    "type": comp,
                    "severity": str(entry.get("severity") or entry.get("level") or "INFO").upper(),
                    "symbol": entry.get("instrument") or entry.get("symbol") or None,
                    "message": str(entry.get("message") or ""),
                    "ticket": int(entry["ticket"]) if entry.get("ticket") else None,
                })
        except Exception:
            pass

        events_out.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"events": events_out[:limit]}

    def build_full_snapshot_event(self) -> Dict[str, Any]:
        return {
            "type": "snapshot",
            "timestamp": _utc_now_iso(),
            "payload": {
                "status": self.build_status_payload(),
                "account": self.build_account_payload(),
                "stats": self.build_stats_payload(),
                "positions": self.build_positions_payload()["positions"],
                "symbols": self.build_symbols_payload(),
            },
        }

    # --- HTTP Request Handler (Strictly Read-Only) ---

    def _build_handler(self):
        manager = self

        class MobileReadOnlyHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(self, status_code: int, data: Any) -> None:
                raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
                accept_enc = (self.headers.get("Accept-Encoding") or "").lower()
                use_gzip = "gzip" in accept_enc and len(raw) > 512
                body = gzip.compress(raw) if use_gzip else raw
                try:
                    self.send_response(status_code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    if use_gzip:
                        self.send_header("Content-Encoding", "gzip")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Read-Only-Mode", "enforced")
                    self.end_headers()
                    self.wfile.write(body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass

            def _read_json_body(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 16_384:
                    return {}
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw) if raw.strip() else {}

            def _extract_token(self, query: Dict[str, List[str]]) -> str:
                auth_header = self.headers.get("Authorization") or ""
                if auth_header.lower().startswith("bearer "):
                    return auth_header[7:].strip()
                hdr = self.headers.get("X-Mobile-Token") or ""
                if hdr:
                    return hdr.strip()
                return (query.get("token", [""])[0] or "").strip()

            def _authenticate(self, query: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
                tok = self._extract_token(query)
                if not tok:
                    return None
                return manager.store.verify_token(tok)

            def _reject_mutation(self) -> None:
                self._send_json(
                    403,
                    {
                        "error": "READ_ONLY_ENFORCED",
                        "message": "Mobile sync is strictly read-only. Mutation methods are forbidden.",
                    },
                )

            def do_PUT(self) -> None:
                self._reject_mutation()

            def do_PATCH(self) -> None:
                self._reject_mutation()

            def do_DELETE(self) -> None:
                self._reject_mutation()

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/api/mobile/v1/pair":
                    try:
                        body = self._read_json_body()
                    except Exception:
                        self._send_json(400, {"error": "INVALID_JSON"})
                        return
                    client_ip = self.client_address[0] if self.client_address else "unknown"
                    code_status, payload = manager._claim_pairing_code(
                        client_ip=client_ip,
                        code=str(body.get("code", "")),
                        device_name=str(body.get("deviceName", "Android Device")),
                        platform=str(body.get("platform", "android")),
                    )
                    self._send_json(code_status, payload)
                    return

                if path == "/api/mobile/v1/unpair":
                    device = self._authenticate(query)
                    if not device:
                        self._send_json(401, {"error": "UNAUTHORIZED"})
                        return
                    manager.revoke_device(device["deviceId"])
                    self._send_json(200, {"unpaired": True, "deviceId": device["deviceId"]})
                    return

                # Every other POST path (including /api/engine/*, /api/trades/*, /api/config/*)
                # is strictly forbidden.
                self._reject_mutation()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/api/mobile/v1/health":
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "schemaVersion": MOBILE_SYNC_SCHEMA_VERSION,
                            "readOnlyEnforced": True,
                        },
                    )
                    return

                device = self._authenticate(query)
                if not device:
                    self._send_json(401, {"error": "UNAUTHORIZED", "message": "Invalid or revoked device token"})
                    return

                if path == "/api/mobile/v1/status":
                    self._send_json(200, manager.build_status_payload())
                elif path == "/api/mobile/v1/account":
                    self._send_json(200, manager.build_account_payload())
                elif path == "/api/mobile/v1/stats":
                    self._send_json(200, manager.build_stats_payload())
                elif path == "/api/mobile/v1/positions":
                    self._send_json(200, manager.build_positions_payload())
                elif path == "/api/mobile/v1/trades":
                    self._send_json(200, manager.build_trades_payload(query))
                elif path == "/api/mobile/v1/candles":
                    self._send_json(200, manager.build_candles_payload(query))
                elif path == "/api/mobile/v1/drawings":
                    self._send_json(200, manager.build_drawings_payload(query))
                elif path == "/api/mobile/v1/symbols":
                    self._send_json(200, manager.build_symbols_payload())
                elif path == "/api/mobile/v1/equity":
                    self._send_json(200, manager.build_equity_payload(query))
                elif path == "/api/mobile/v1/activity":
                    self._send_json(200, manager.build_activity_payload(query))
                elif path == "/api/mobile/v1/events":
                    self._stream_sse(device["deviceId"])
                else:
                    self._send_json(404, {"error": "NOT_FOUND", "path": path})

            def _stream_sse(self, device_id: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Read-Only-Mode", "enforced")
                self.end_headers()
                sub = manager.ctx.events.subscribe()
                try:
                    init_ev = manager.build_full_snapshot_event()
                    self.wfile.write(f"data: {json.dumps(init_ev)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                    while manager.enabled:
                        try:
                            ev = sub.get(timeout=15.0)
                            ev_type = str(ev.get("type") or "")
                            if ev_type == "mobile_device_revoked":
                                p = ev.get("payload") or {}
                                if p.get("all") or p.get("deviceId") == device_id:
                                    rev_msg = {
                                        "type": "revoked",
                                        "timestamp": _utc_now_iso(),
                                        "payload": {"deviceId": device_id},
                                    }
                                    self.wfile.write(f"data: {json.dumps(rev_msg)}\n\n".encode("utf-8"))
                                    self.wfile.flush()
                                    break
                                continue

                            # Map companion EventBus events to mobile v1 SSE events
                            if ev_type in ("mt5_snapshot", "engine_state", "snapshot"):
                                out_ev = manager.build_full_snapshot_event()
                            elif ev_type in ("log", "alert", "trade_event"):
                                out_ev = {
                                    "type": "activity",
                                    "timestamp": _utc_now_iso(),
                                    "payload": ev.get("payload"),
                                }
                            else:
                                out_ev = {
                                    "type": "status",
                                    "timestamp": _utc_now_iso(),
                                    "payload": manager.build_status_payload(),
                                }
                            self.wfile.write(f"data: {json.dumps(out_ev)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except queue.Empty:
                            ping_ev = {
                                "type": "ping",
                                "timestamp": _utc_now_iso(),
                                "payload": {"serverTime": _utc_now_iso()},
                            }
                            self.wfile.write(f"data: {json.dumps(ping_ev)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                except Exception:
                    pass
                finally:
                    manager.ctx.events.unsubscribe(sub)

        return MobileReadOnlyHandler
