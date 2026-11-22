"""
SQLite schema and forward-only migrations for the Institutional EA Companion Control Centre.
The broker (MetaTrader 5) remains authoritative for live account and execution truth;
this database records configuration history, audit trails, errors, operations, and
reconciled trade/risk records.
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Callable, List, Tuple


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "companion_control.db"


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _migration_001_initial(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            change_summary TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'operator',
            requires_restart INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket INTEGER NOT NULL,
            correlation_id TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            volume REAL NOT NULL,
            entry_price REAL NOT NULL,
            close_price REAL DEFAULT 0.0,
            stop_loss REAL DEFAULT 0.0,
            take_profit REAL DEFAULT 0.0,
            profit REAL DEFAULT 0.0,
            commission REAL DEFAULT 0.0,
            swap REAL DEFAULT 0.0,
            magic INTEGER DEFAULT 0,
            ownership TEXT NOT NULL DEFAULT 'UNKNOWN',
            status TEXT NOT NULL DEFAULT 'OPEN',
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            UNIQUE(ticket, status)
        );

        CREATE TABLE IF NOT EXISTS order_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            ticket INTEGER DEFAULT 0,
            symbol TEXT NOT NULL,
            order_type TEXT NOT NULL,
            volume REAL NOT NULL,
            price REAL DEFAULT 0.0,
            stop_loss REAL DEFAULT 0.0,
            take_profit REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            retcode INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execution_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            symbol TEXT,
            ticket INTEGER DEFAULT 0,
            correlation_id TEXT,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS risk_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            approved INTEGER NOT NULL,
            reason TEXT NOT NULL,
            risk_percent REAL DEFAULT 0.0,
            proposed_volume REAL DEFAULT 0.0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS error_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            component TEXT NOT NULL,
            message TEXT NOT NULL,
            trading_affected INTEGER NOT NULL DEFAULT 0,
            entries_blocked INTEGER NOT NULL DEFAULT 0,
            recommended_recovery TEXT NOT NULL,
            user_action_required INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            resolution_note TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS operation_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            operation_name TEXT NOT NULL,
            args_json TEXT NOT NULL,
            status TEXT NOT NULL,
            exit_code INTEGER,
            stdout TEXT DEFAULT '',
            stderr TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_ms INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS connection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            component TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "001_initial_companion_schema", _migration_001_initial),
]


def init_database(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Applies pending SQLite migrations and returns the current schema version."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        current_version = max(applied) if applied else 0
        for version, name, fn in MIGRATIONS:
            if version not in applied:
                with conn:
                    fn(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, datetime('now'))",
                        (version, name),
                    )
                current_version = max(current_version, version)
        return current_version
    finally:
        conn.close()
