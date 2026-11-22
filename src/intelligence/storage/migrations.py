"""
Database migrations and schema definitions for the ATI Persistence Layer.
Ensures thread-safe, idempotent SQLite operations with foreign keys and WAL mode.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, List, Tuple

DEFAULT_ATI_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ati_intelligence.db"


def get_connection(db_path: str | Path = DEFAULT_ATI_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _migration_001_initial_ati(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- MT5 Broker Deals (Idempotent Deal Tracking)
        CREATE TABLE IF NOT EXISTS ati_broker_deals (
            deal_ticket INTEGER PRIMARY KEY,
            order_ticket INTEGER NOT NULL,
            position_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            canonical_symbol TEXT NOT NULL,
            deal_type TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            volume REAL NOT NULL,
            price REAL NOT NULL,
            commission REAL DEFAULT 0.0,
            swap REAL DEFAULT 0.0,
            profit REAL DEFAULT 0.0,
            fee REAL DEFAULT 0.0,
            magic INTEGER DEFAULT 0,
            comment TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            account_number INTEGER DEFAULT 0,
            account_currency TEXT DEFAULT 'USD',
            denomination_factor REAL DEFAULT 1.0,
            raw_json TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_ati_deals_pos ON ati_broker_deals (position_id);
        CREATE INDEX IF NOT EXISTS idx_ati_deals_sym ON ati_broker_deals (canonical_symbol);

        -- Reconciled Completed Positions (Authoritative Intelligence Records)
        CREATE TABLE IF NOT EXISTS ati_completed_positions (
            position_id INTEGER PRIMARY KEY,
            canonical_symbol TEXT NOT NULL,
            broker_symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            open_time TEXT NOT NULL,
            close_time TEXT NOT NULL,
            open_price REAL NOT NULL,
            close_price REAL NOT NULL,
            volume REAL NOT NULL,
            initial_sl REAL DEFAULT 0.0,
            initial_tp REAL DEFAULT 0.0,
            realized_gross_profit REAL DEFAULT 0.0,
            realized_net_profit REAL DEFAULT 0.0,
            commission REAL DEFAULT 0.0,
            swap REAL DEFAULT 0.0,
            slippage_pts REAL DEFAULT 0.0,
            spread_pts REAL DEFAULT 0.0,
            exit_reason TEXT DEFAULT 'UNKNOWN',
            strategy_id TEXT DEFAULT 'DEFAULT',
            strategy_version TEXT DEFAULT '1.0.0',
            signal_id TEXT DEFAULT '',
            account_number INTEGER DEFAULT 0,
            account_currency TEXT DEFAULT 'USD',
            account_type TEXT DEFAULT 'STANDARD',
            denomination_factor REAL DEFAULT 1.0,
            entry_deals_json TEXT DEFAULT '[]',
            exit_deals_json TEXT DEFAULT '[]',
            partial_closes_count INTEGER DEFAULT 0,
            features_snapshot_json TEXT DEFAULT '{}',
            reconciled_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ati_positions_sym ON ati_completed_positions (canonical_symbol);
        CREATE INDEX IF NOT EXISTS idx_ati_positions_close ON ati_completed_positions (close_time);

        -- Autonomous Trade Audits
        CREATE TABLE IF NOT EXISTS ati_trade_audits (
            trade_id INTEGER PRIMARY KEY,
            audit_timestamp TEXT NOT NULL,
            audit_version TEXT NOT NULL,
            classification TEXT NOT NULL,
            root_cause_confidence REAL DEFAULT 0.0,
            entry_quality_score REAL DEFAULT 0.0,
            exit_quality_score REAL DEFAULT 0.0,
            execution_quality_score REAL DEFAULT 0.0,
            risk_quality_score REAL DEFAULT 0.0,
            detected_issues_json TEXT DEFAULT '[]',
            supporting_evidence_json TEXT DEFAULT '{}',
            recommendations_json TEXT DEFAULT '[]',
            suggested_experiments_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'COMPLETED',
            FOREIGN KEY(trade_id) REFERENCES ati_completed_positions(position_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ati_audits_class ON ati_trade_audits (classification);

        -- Market Regime Observations
        CREATE TABLE IF NOT EXISTS ati_market_regimes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            regime TEXT NOT NULL,
            confidence REAL NOT NULL,
            adx_value REAL DEFAULT 0.0,
            atr_value REAL DEFAULT 0.0,
            trend_slope REAL DEFAULT 0.0,
            volatility_ratio REAL DEFAULT 1.0,
            spread_pts REAL DEFAULT 0.0,
            session_name TEXT DEFAULT 'UNKNOWN',
            features_json TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_ati_regimes_sym_time ON ati_market_regimes (canonical_symbol, timestamp);

        -- Strategy Candidates (Improvement Pipeline)
        CREATE TABLE IF NOT EXISTS ati_strategy_candidates (
            candidate_id TEXT PRIMARY KEY,
            base_strategy TEXT NOT NULL,
            version TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            target_symbols_json TEXT NOT NULL,
            target_regimes_json TEXT NOT NULL,
            creation_timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            rationale TEXT DEFAULT '',
            checksum TEXT DEFAULT '',
            author TEXT DEFAULT 'ATI_LABORATORY',
            backtest_metrics_json TEXT DEFAULT '{}',
            walk_forward_metrics_json TEXT DEFAULT '{}',
            out_of_sample_metrics_json TEXT DEFAULT '{}',
            shadow_test_metrics_json TEXT DEFAULT '{}',
            promotion_notes TEXT,
            approved_by TEXT,
            approved_at TEXT
        );

        -- Configuration Versioning & Rollback Snapshots
        CREATE TABLE IF NOT EXISTS ati_active_configurations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            checksum TEXT NOT NULL,
            promoted_by TEXT NOT NULL,
            promoted_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ati_rollback_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        -- Learning Engine Model Checkpoints
        CREATE TABLE IF NOT EXISTS ati_model_checkpoints (
            model_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            version TEXT NOT NULL,
            feature_names_json TEXT NOT NULL,
            model_bytes BLOB,
            metrics_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        -- Intelligence Reports (Daily & Weekly)
        CREATE TABLE IF NOT EXISTS ati_reports (
            report_id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ati_reports_type_time ON ati_reports (report_type, created_at);
        """
    )


MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "001_initial_ati_schema", _migration_001_initial_ati),
]


def init_ati_database(db_path: str | Path = DEFAULT_ATI_DB_PATH) -> int:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ati_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM ati_schema_migrations").fetchall()
        }
        current_version = max(applied) if applied else 0
        for version, name, fn in MIGRATIONS:
            if version not in applied:
                with conn:
                    fn(conn)
                    conn.execute(
                        "INSERT INTO ati_schema_migrations (version, name, applied_at) VALUES (?, ?, datetime('now'))",
                        (version, name),
                    )
                current_version = max(current_version, version)
        return current_version
    finally:
        conn.close()
