"""
Thread-safe SQLite repository for Institutional EA Companion Control Centre persistence.
"""

from __future__ import annotations
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from companion.database.migrations import DEFAULT_DB_PATH, get_connection, init_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CompanionRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self.schema_version = init_database(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def health_check(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
                return {
                    "healthy": True,
                    "db_path": str(self.db_path),
                    "schema_version": int(row["v"] or 0) if row else 0,
                }
            except Exception as exc:
                return {"healthy": False, "db_path": str(self.db_path), "error": str(exc)}
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Audit & Connection History
    # ------------------------------------------------------------------
    def record_audit(self, actor: str, action: str, component: str, details: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO audit_logs (actor, action, component, details, created_at) VALUES (?, ?, ?, ?, ?)",
                        (actor, action, component, details, _utc_now()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def record_connection_event(self, target: str, status: str, details: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO connection_history (target, status, details, created_at) VALUES (?, ?, ?, ?)",
                        (target, status, details, _utc_now()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_connection_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM connection_history ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Error Centre (never silently cleared; preserved with RESOLVED history)
    # ------------------------------------------------------------------
    def record_error(
        self,
        category: str,
        severity: str,
        component: str,
        message: str,
        trading_affected: bool = False,
        entries_blocked: bool = False,
        recommended_recovery: str = "Inspect logs and verify component health.",
        user_action_required: bool = False,
    ) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO error_events (
                            category, severity, component, message, trading_affected,
                            entries_blocked, recommended_recovery, user_action_required,
                            status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                        """,
                        (
                            category.upper(),
                            severity.upper(),
                            component,
                            message,
                            1 if trading_affected else 0,
                            1 if entries_blocked else 0,
                            recommended_recovery,
                            1 if user_action_required else 0,
                            _utc_now(),
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def resolve_error(self, error_id: int, resolution_note: str = "Resolved after verified recovery") -> bool:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        UPDATE error_events
                        SET status = 'RESOLVED', resolution_note = ?, resolved_at = ?
                        WHERE id = ? AND status = 'ACTIVE'
                        """,
                        (resolution_note, _utc_now(), error_id),
                    )
                    return cur.rowcount > 0
            finally:
                conn.close()

    def resolve_component_errors(self, component: str, resolution_note: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        UPDATE error_events
                        SET status = 'RESOLVED', resolution_note = ?, resolved_at = ?
                        WHERE component = ? AND status = 'ACTIVE'
                        """,
                        (resolution_note, _utc_now(), component),
                    )
                    return int(cur.rowcount)
            finally:
                conn.close()

    def get_errors(self, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM error_events WHERE status = ? ORDER BY id DESC LIMIT ?",
                        (status.upper(), limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM error_events ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Configuration Versioning
    # ------------------------------------------------------------------
    def save_config_version(
        self,
        config_dict: Dict[str, Any],
        change_summary: str,
        author: str = "operator",
        requires_restart: bool = False,
    ) -> int:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute("SELECT COALESCE(MAX(version), 0) AS max_v FROM config_versions").fetchone()
                next_ver = int(row["max_v"]) + 1 if row else 1
                with conn:
                    conn.execute(
                        """
                        INSERT INTO config_versions (version, config_json, change_summary, author, requires_restart, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            next_ver,
                            json.dumps(config_dict, indent=2),
                            change_summary,
                            author,
                            1 if requires_restart else 0,
                            _utc_now(),
                        ),
                    )
                return next_ver
            finally:
                conn.close()

    def get_config_versions(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT id, version, change_summary, author, requires_restart, created_at FROM config_versions ORDER BY version DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_config_version_data(self, version: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT config_json FROM config_versions WHERE version = ?", (version,)
                ).fetchone()
                if not row:
                    return None
                return json.loads(row["config_json"])
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Operations Audit
    # ------------------------------------------------------------------
    def create_operation_audit(self, operation_id: str, operation_name: str, args: Dict[str, Any]) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO operation_audits (operation_id, operation_name, args_json, status, started_at)
                        VALUES (?, ?, ?, 'RUNNING', ?)
                        """,
                        (operation_id, operation_name, json.dumps(args), _utc_now()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def finish_operation_audit(
        self,
        audit_id: int,
        status: str,
        exit_code: Optional[int],
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE operation_audits
                        SET status = ?, exit_code = ?, stdout = ?, stderr = ?, completed_at = ?, duration_ms = ?
                        WHERE id = ?
                        """,
                        (status, exit_code, stdout, stderr, _utc_now(), duration_ms, audit_id),
                    )
            finally:
                conn.close()

    def get_operation_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM operation_audits ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Risk Decisions & Trade Records
    # ------------------------------------------------------------------
    def record_risk_decision(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        approved: bool,
        reason: str,
        risk_percent: float = 0.0,
        proposed_volume: float = 0.0,
    ) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO risk_decisions (
                            signal_id, symbol, direction, approved, reason, risk_percent, proposed_volume, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            signal_id,
                            symbol,
                            direction,
                            1 if approved else 0,
                            reason,
                            float(risk_percent),
                            float(proposed_volume),
                            _utc_now(),
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_risk_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM risk_decisions ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def upsert_trade_record(self, trade: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO trade_records (
                            ticket, correlation_id, symbol, direction, volume, entry_price, close_price,
                            stop_loss, take_profit, profit, commission, swap, magic, ownership, status,
                            opened_at, closed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticket, status) DO UPDATE SET
                            close_price = excluded.close_price,
                            stop_loss = excluded.stop_loss,
                            take_profit = excluded.take_profit,
                            profit = excluded.profit,
                            commission = excluded.commission,
                            swap = excluded.swap,
                            closed_at = excluded.closed_at
                        """,
                        (
                            int(trade.get("ticket", 0)),
                            trade.get("correlation_id", ""),
                            str(trade.get("symbol", "")),
                            str(trade.get("direction", "BUY")),
                            float(trade.get("volume", 0.0)),
                            float(trade.get("entry_price", 0.0)),
                            float(trade.get("close_price", 0.0)),
                            float(trade.get("stop_loss", 0.0)),
                            float(trade.get("take_profit", 0.0)),
                            float(trade.get("profit", 0.0)),
                            float(trade.get("commission", 0.0)),
                            float(trade.get("swap", 0.0)),
                            int(trade.get("magic", 0)),
                            str(trade.get("ownership", "UNKNOWN")),
                            str(trade.get("status", "OPEN")),
                            str(trade.get("opened_at") or _utc_now()),
                            trade.get("closed_at"),
                        ),
                    )
            finally:
                conn.close()

    def get_trade_records(self, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM trade_records WHERE status = ? ORDER BY id DESC LIMIT ?",
                        (status.upper(), limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM trade_records ORDER BY id DESC LIMIT ?", (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def cleanup_stale_open_trade_records(self, active_open_tickets: List[int]) -> int:
        """Removes stale status='OPEN' rows whose tickets are no longer open in MT5."""
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    if not active_open_tickets:
                        cur = conn.execute("DELETE FROM trade_records WHERE status = 'OPEN'")
                    else:
                        placeholders = ",".join("?" for _ in active_open_tickets)
                        cur = conn.execute(
                            f"DELETE FROM trade_records WHERE status = 'OPEN' AND ticket NOT IN ({placeholders})",
                            tuple(int(t) for t in active_open_tickets),
                        )
                    return int(cur.rowcount)
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Real Balance Snapshots, Screenshots, Signals & Alerts (Migration 002)
    # ------------------------------------------------------------------
    def record_balance_snapshot(self, balance: float, equity: float, floating_pnl: float = 0.0, source: str = "MT5") -> None:
        with self._lock:
            conn = self._conn()
            try:
                last = conn.execute(
                    "SELECT balance, equity, created_at FROM balance_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if last and abs(float(last["balance"]) - balance) < 1e-4 and abs(float(last["equity"]) - equity) < 1e-4:
                    return
                with conn:
                    conn.execute(
                        "INSERT INTO balance_snapshots (balance, equity, floating_pnl, source, created_at) VALUES (?, ?, ?, ?, ?)",
                        (round(float(balance), 2), round(float(equity), 2), round(float(floating_pnl), 2), source, _utc_now()),
                    )
            finally:
                conn.close()

    def get_balance_snapshots(self, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM balance_snapshots ORDER BY id ASC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def record_trade_screenshot(self, ticket: int, symbol: str, stage: str, filename: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT OR REPLACE INTO trade_screenshots (ticket, symbol, stage, filename, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (int(ticket), str(symbol), str(stage).upper(), str(filename), _utc_now()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_trade_screenshots(self, ticket: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                if ticket is not None:
                    rows = conn.execute(
                        "SELECT * FROM trade_screenshots WHERE ticket = ? ORDER BY id ASC LIMIT ?",
                        (int(ticket), limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM trade_screenshots ORDER BY id DESC LIMIT ?", (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_execution_events_for_ticket(self, ticket: int) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM execution_events WHERE ticket = ? ORDER BY id ASC",
                    (int(ticket),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def record_signal(self, sig: Dict[str, Any]) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO signal_records (
                            signal_id, symbol, direction, score, entry_price, stop_loss,
                            take_profit, rr, status, rejection_reason, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(sig.get("signal_id", "")),
                            str(sig.get("symbol", "")),
                            str(sig.get("direction", "")),
                            float(sig.get("score", 0.0)),
                            float(sig.get("entry_price", 0.0)),
                            float(sig.get("stop_loss", 0.0)),
                            float(sig.get("take_profit", 0.0)),
                            float(sig.get("rr", 0.0)),
                            str(sig.get("status", "WATCHING")).upper(),
                            str(sig.get("rejection_reason", "")),
                            str(sig.get("created_at") or _utc_now()),
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_signals(self, limit: int = 150) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM signal_records ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def record_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        symbol: str = "",
        telegram_status: str = "SKIPPED",
        dedup_key: str = "",
    ) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO alert_events (
                            alert_type, severity, symbol, message, telegram_status, dedup_key, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(alert_type).lower(),
                            str(severity).upper(),
                            str(symbol),
                            str(message),
                            str(telegram_status).upper(),
                            str(dedup_key),
                            _utc_now(),
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_alerts(self, limit: int = 150) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM alert_events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_alert_settings(self) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "enabled_types": {
                "signal": True,
                "trade_open": True,
                "trade_close": True,
                "be_moved": True,
                "sl_tp_hit": True,
                "daily_loss_warn": True,
                "bridge_down": True,
                "heartbeat_lost": True,
                "stale_data": True,
            },
            "telegram_enabled": True,
            "quiet_hours_enabled": False,
            "quiet_start_utc": "22:00",
            "quiet_end_utc": "06:00",
            "rate_limit_per_min": 6,
            "dedup_window_sec": 120,
        }
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT value_json FROM alert_settings WHERE key = 'alert_prefs'"
                ).fetchone()
                if row:
                    saved = json.loads(row["value_json"])
                    if isinstance(saved, dict):
                        merged = {**defaults, **saved}
                        if isinstance(saved.get("enabled_types"), dict):
                            merged["enabled_types"] = {**defaults["enabled_types"], **saved["enabled_types"]}
                        return merged
                return defaults
            finally:
                conn.close()

    def save_alert_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_alert_settings()
        updated = {**current, **settings}
        if isinstance(settings.get("enabled_types"), dict):
            updated["enabled_types"] = {**current["enabled_types"], **settings["enabled_types"]}
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO alert_settings (key, value_json, updated_at)
                        VALUES ('alert_prefs', ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                        """,
                        (json.dumps(updated), _utc_now()),
                    )
                return updated
            finally:
                conn.close()
