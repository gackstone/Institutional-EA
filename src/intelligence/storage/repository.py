"""
Thread-safe SQLite repository for the MT5-001 Adaptive Trading Intelligence (ATI) Subsystem.
Provides atomic transactions, idempotency guarantees, and safe queries.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.intelligence.contracts import (
    BrokerDealRecord,
    CompletedPositionRecord,
    TradeAuditReport,
    MarketRegimeSnapshot,
    StrategyCandidateRecord,
    AuditClassification,
    CandidateStatus,
    MarketRegimeType,
    utc_now_iso,
)
from src.intelligence.storage.migrations import DEFAULT_ATI_DB_PATH, get_connection, init_ati_database


class ATIRepository:
    def __init__(self, db_path: str | Path = DEFAULT_ATI_DB_PATH):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self.schema_version = init_ati_database(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # --------------------------------------------------------------------------
    # Deal Management (Idempotent Ingestion)
    # --------------------------------------------------------------------------
    def insert_broker_deal(self, deal: BrokerDealRecord, raw_json: str = "{}") -> bool:
        """Inserts a broker deal idempotently. Returns True if inserted, False if duplicate."""
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO ati_broker_deals (
                            deal_ticket, order_ticket, position_id, symbol, canonical_symbol,
                            deal_type, entry_type, volume, price, commission, swap, profit,
                            fee, magic, comment, timestamp, account_number, account_currency,
                            denomination_factor, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            deal.deal_ticket,
                            deal.order_ticket,
                            deal.position_id,
                            deal.symbol,
                            deal.canonical_symbol,
                            deal.deal_type,
                            deal.entry_type,
                            deal.volume,
                            deal.price,
                            deal.commission,
                            deal.swap,
                            deal.profit,
                            deal.fee,
                            deal.magic,
                            deal.comment,
                            deal.timestamp.isoformat() if isinstance(deal.timestamp, datetime) else str(deal.timestamp),
                            deal.account_number,
                            deal.account_currency,
                            deal.denomination_factor,
                            raw_json,
                        ),
                    )
                    return cur.rowcount > 0
            finally:
                conn.close()

    def get_deals_for_position(self, position_id: int) -> List[BrokerDealRecord]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM ati_broker_deals WHERE position_id = ? ORDER BY timestamp ASC, deal_ticket ASC",
                    (position_id,),
                ).fetchall()
                deals = []
                for r in rows:
                    deals.append(
                        BrokerDealRecord(
                            deal_ticket=r["deal_ticket"],
                            order_ticket=r["order_ticket"],
                            position_id=r["position_id"],
                            symbol=r["symbol"],
                            canonical_symbol=r["canonical_symbol"],
                            deal_type=r["deal_type"],
                            entry_type=r["entry_type"],
                            volume=r["volume"],
                            price=r["price"],
                            commission=r["commission"],
                            swap=r["swap"],
                            profit=r["profit"],
                            fee=r["fee"],
                            magic=r["magic"],
                            comment=r["comment"],
                            timestamp=datetime.fromisoformat(r["timestamp"]),
                            account_number=r["account_number"],
                            account_currency=r["account_currency"],
                            denomination_factor=r["denomination_factor"],
                        )
                    )
                return deals
            finally:
                conn.close()

    def get_latest_deal_timestamp(self) -> Optional[datetime]:
        with self._lock:
            conn = self._conn()
            try:
                row = conn.execute("SELECT MAX(timestamp) AS max_t FROM ati_broker_deals").fetchone()
                if row and row["max_t"]:
                    return datetime.fromisoformat(row["max_t"])
                return None
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Completed Positions
    # --------------------------------------------------------------------------
    def upsert_completed_position(self, pos: CompletedPositionRecord) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO ati_completed_positions (
                            position_id, canonical_symbol, broker_symbol, direction,
                            open_time, close_time, open_price, close_price, volume,
                            initial_sl, initial_tp, realized_gross_profit, realized_net_profit,
                            commission, swap, slippage_pts, spread_pts, exit_reason,
                            strategy_id, strategy_version, signal_id, account_number,
                            account_currency, account_type, denomination_factor,
                            entry_deals_json, exit_deals_json, partial_closes_count,
                            features_snapshot_json, reconciled_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(position_id) DO UPDATE SET
                            close_time=excluded.close_time,
                            close_price=excluded.close_price,
                            volume=excluded.volume,
                            realized_gross_profit=excluded.realized_gross_profit,
                            realized_net_profit=excluded.realized_net_profit,
                            commission=excluded.commission,
                            swap=excluded.swap,
                            slippage_pts=excluded.slippage_pts,
                            spread_pts=excluded.spread_pts,
                            exit_reason=excluded.exit_reason,
                            entry_deals_json=excluded.entry_deals_json,
                            exit_deals_json=excluded.exit_deals_json,
                            partial_closes_count=excluded.partial_closes_count,
                            features_snapshot_json=excluded.features_snapshot_json,
                            reconciled_at=excluded.reconciled_at
                        """,
                        (
                            pos.position_id,
                            pos.canonical_symbol,
                            pos.broker_symbol,
                            pos.direction,
                            pos.open_time.isoformat() if isinstance(pos.open_time, datetime) else str(pos.open_time),
                            pos.close_time.isoformat() if isinstance(pos.close_time, datetime) else str(pos.close_time),
                            pos.open_price,
                            pos.close_price,
                            pos.volume,
                            pos.initial_sl,
                            pos.initial_tp,
                            pos.realized_gross_profit,
                            pos.realized_net_profit,
                            pos.commission,
                            pos.swap,
                            pos.slippage_pts,
                            pos.spread_pts,
                            pos.exit_reason,
                            pos.strategy_id,
                            pos.strategy_version,
                            pos.signal_id,
                            pos.account_number,
                            pos.account_currency,
                            pos.account_type,
                            pos.denomination_factor,
                            json.dumps(pos.entry_deals),
                            json.dumps(pos.exit_deals),
                            pos.partial_closes_count,
                            json.dumps(pos.features_snapshot),
                            pos.reconciled_at.isoformat() if isinstance(pos.reconciled_at, datetime) else str(pos.reconciled_at),
                        ),
                    )
            finally:
                conn.close()

    def get_completed_position(self, position_id: int) -> Optional[CompletedPositionRecord]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute("SELECT * FROM ati_completed_positions WHERE position_id = ?", (position_id,)).fetchone()
                if not r:
                    return None
                return CompletedPositionRecord(
                    position_id=r["position_id"],
                    canonical_symbol=r["canonical_symbol"],
                    broker_symbol=r["broker_symbol"],
                    direction=r["direction"],
                    open_time=datetime.fromisoformat(r["open_time"]),
                    close_time=datetime.fromisoformat(r["close_time"]),
                    open_price=r["open_price"],
                    close_price=r["close_price"],
                    volume=r["volume"],
                    initial_sl=r["initial_sl"],
                    initial_tp=r["initial_tp"],
                    realized_gross_profit=r["realized_gross_profit"],
                    realized_net_profit=r["realized_net_profit"],
                    commission=r["commission"],
                    swap=r["swap"],
                    slippage_pts=r["slippage_pts"],
                    spread_pts=r["spread_pts"],
                    exit_reason=r["exit_reason"],
                    strategy_id=r["strategy_id"],
                    strategy_version=r["strategy_version"],
                    signal_id=r["signal_id"],
                    account_number=r["account_number"],
                    account_currency=r["account_currency"],
                    account_type=r["account_type"],
                    denomination_factor=r["denomination_factor"],
                    entry_deals=json.loads(r["entry_deals_json"]),
                    exit_deals=json.loads(r["exit_deals_json"]),
                    partial_closes_count=r["partial_closes_count"],
                    features_snapshot=json.loads(r["features_snapshot_json"]),
                    reconciled_at=datetime.fromisoformat(r["reconciled_at"]),
                )
            finally:
                conn.close()

    def list_completed_positions(
        self,
        symbol: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[CompletedPositionRecord]:
        with self._lock:
            conn = self._conn()
            try:
                query = "SELECT * FROM ati_completed_positions"
                params: List[Any] = []
                if symbol:
                    query += " WHERE canonical_symbol = ?"
                    params.append(symbol)
                query += " ORDER BY close_time DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                rows = conn.execute(query, params).fetchall()
                positions = []
                for r in rows:
                    positions.append(
                        CompletedPositionRecord(
                            position_id=r["position_id"],
                            canonical_symbol=r["canonical_symbol"],
                            broker_symbol=r["broker_symbol"],
                            direction=r["direction"],
                            open_time=datetime.fromisoformat(r["open_time"]),
                            close_time=datetime.fromisoformat(r["close_time"]),
                            open_price=r["open_price"],
                            close_price=r["close_price"],
                            volume=r["volume"],
                            initial_sl=r["initial_sl"],
                            initial_tp=r["initial_tp"],
                            realized_gross_profit=r["realized_gross_profit"],
                            realized_net_profit=r["realized_net_profit"],
                            commission=r["commission"],
                            swap=r["swap"],
                            slippage_pts=r["slippage_pts"],
                            spread_pts=r["spread_pts"],
                            exit_reason=r["exit_reason"],
                            strategy_id=r["strategy_id"],
                            strategy_version=r["strategy_version"],
                            signal_id=r["signal_id"],
                            account_number=r["account_number"],
                            account_currency=r["account_currency"],
                            account_type=r["account_type"],
                            denomination_factor=r["denomination_factor"],
                            entry_deals=json.loads(r["entry_deals_json"]),
                            exit_deals=json.loads(r["exit_deals_json"]),
                            partial_closes_count=r["partial_closes_count"],
                            features_snapshot=json.loads(r["features_snapshot_json"]),
                            reconciled_at=datetime.fromisoformat(r["reconciled_at"]),
                        )
                    )
                return positions
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Audits
    # --------------------------------------------------------------------------
    def save_trade_audit(self, audit: TradeAuditReport) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO ati_trade_audits (
                            trade_id, audit_timestamp, audit_version, classification,
                            root_cause_confidence, entry_quality_score, exit_quality_score,
                            execution_quality_score, risk_quality_score,
                            detected_issues_json, supporting_evidence_json,
                            recommendations_json, suggested_experiments_json, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            audit.trade_id,
                            audit.audit_timestamp.isoformat() if isinstance(audit.audit_timestamp, datetime) else str(audit.audit_timestamp),
                            audit.audit_version,
                            audit.classification.value,
                            audit.root_cause_confidence,
                            audit.entry_quality_score,
                            audit.exit_quality_score,
                            audit.execution_quality_score,
                            audit.risk_quality_score,
                            json.dumps(audit.detected_issues),
                            json.dumps(audit.supporting_evidence),
                            json.dumps(audit.recommendations),
                            json.dumps(audit.suggested_experiments),
                            audit.status,
                        ),
                    )
            finally:
                conn.close()

    def get_trade_audit(self, trade_id: int) -> Optional[TradeAuditReport]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute("SELECT * FROM ati_trade_audits WHERE trade_id = ?", (trade_id,)).fetchone()
                if not r:
                    return None
                return TradeAuditReport(
                    trade_id=r["trade_id"],
                    audit_timestamp=datetime.fromisoformat(r["audit_timestamp"]),
                    audit_version=r["audit_version"],
                    classification=AuditClassification(r["classification"]),
                    root_cause_confidence=r["root_cause_confidence"],
                    entry_quality_score=r["entry_quality_score"],
                    exit_quality_score=r["exit_quality_score"],
                    execution_quality_score=r["execution_quality_score"],
                    risk_quality_score=r["risk_quality_score"],
                    detected_issues=json.loads(r["detected_issues_json"]),
                    supporting_evidence=json.loads(r["supporting_evidence_json"]),
                    recommendations=json.loads(r["recommendations_json"]),
                    suggested_experiments=json.loads(r["suggested_experiments_json"]),
                    status=r["status"],
                )
            finally:
                conn.close()

    def list_trade_audits(self, limit: int = 100) -> List[TradeAuditReport]:
        with self._lock:
            conn = self._conn()
            try:
                rows = conn.execute("SELECT * FROM ati_trade_audits ORDER BY trade_id DESC LIMIT ?", (limit,)).fetchall()
                audits = []
                for r in rows:
                    audits.append(
                        TradeAuditReport(
                            trade_id=r["trade_id"],
                            audit_timestamp=datetime.fromisoformat(r["audit_timestamp"]),
                            audit_version=r["audit_version"],
                            classification=AuditClassification(r["classification"]),
                            root_cause_confidence=r["root_cause_confidence"],
                            entry_quality_score=r["entry_quality_score"],
                            exit_quality_score=r["exit_quality_score"],
                            execution_quality_score=r["execution_quality_score"],
                            risk_quality_score=r["risk_quality_score"],
                            detected_issues=json.loads(r["detected_issues_json"]),
                            supporting_evidence=json.loads(r["supporting_evidence_json"]),
                            recommendations=json.loads(r["recommendations_json"]),
                            suggested_experiments=json.loads(r["suggested_experiments_json"]),
                            status=r["status"],
                        )
                    )
                return audits
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Market Regimes
    # --------------------------------------------------------------------------
    def record_market_regime(self, snapshot: MarketRegimeSnapshot) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO ati_market_regimes (
                            canonical_symbol, timestamp, regime, confidence,
                            adx_value, atr_value, trend_slope, volatility_ratio,
                            spread_pts, session_name, features_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.canonical_symbol,
                            snapshot.timestamp.isoformat() if isinstance(snapshot.timestamp, datetime) else str(snapshot.timestamp),
                            snapshot.regime.value,
                            snapshot.confidence,
                            snapshot.adx_value,
                            snapshot.atr_value,
                            snapshot.trend_slope,
                            snapshot.volatility_ratio,
                            snapshot.spread_pts,
                            snapshot.session_name,
                            json.dumps(snapshot.features),
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_latest_regime(self, canonical_symbol: str) -> Optional[MarketRegimeSnapshot]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute(
                    "SELECT * FROM ati_market_regimes WHERE canonical_symbol = ? ORDER BY timestamp DESC LIMIT 1",
                    (canonical_symbol,),
                ).fetchone()
                if not r:
                    return None
                return MarketRegimeSnapshot(
                    canonical_symbol=r["canonical_symbol"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    regime=MarketRegimeType(r["regime"]),
                    confidence=r["confidence"],
                    adx_value=r["adx_value"],
                    atr_value=r["atr_value"],
                    trend_slope=r["trend_slope"],
                    volatility_ratio=r["volatility_ratio"],
                    spread_pts=r["spread_pts"],
                    session_name=r["session_name"],
                    features=json.loads(r["features_json"]),
                )
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Strategy Candidates & Improvement Pipeline
    # --------------------------------------------------------------------------
    def save_candidate(self, cand: StrategyCandidateRecord) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO ati_strategy_candidates (
                            candidate_id, base_strategy, version, parameters_json,
                            target_symbols_json, target_regimes_json, creation_timestamp,
                            status, rationale, checksum, author, backtest_metrics_json,
                            walk_forward_metrics_json, out_of_sample_metrics_json,
                            shadow_test_metrics_json, promotion_notes, approved_by, approved_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cand.candidate_id,
                            cand.base_strategy,
                            cand.version,
                            json.dumps(cand.parameters),
                            json.dumps(cand.target_symbols),
                            json.dumps(cand.target_regimes),
                            cand.creation_timestamp.isoformat() if isinstance(cand.creation_timestamp, datetime) else str(cand.creation_timestamp),
                            cand.status.value,
                            cand.rationale,
                            cand.checksum,
                            cand.author,
                            json.dumps(cand.backtest_metrics),
                            json.dumps(cand.walk_forward_metrics),
                            json.dumps(cand.out_of_sample_metrics),
                            json.dumps(cand.shadow_test_metrics),
                            cand.promotion_notes,
                            cand.approved_by,
                            cand.approved_at.isoformat() if cand.approved_at else None,
                        ),
                    )
            finally:
                conn.close()

    def get_candidate(self, candidate_id: str) -> Optional[StrategyCandidateRecord]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute("SELECT * FROM ati_strategy_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
                if not r:
                    return None
                return StrategyCandidateRecord(
                    candidate_id=r["candidate_id"],
                    base_strategy=r["base_strategy"],
                    version=r["version"],
                    parameters=json.loads(r["parameters_json"]),
                    target_symbols=json.loads(r["target_symbols_json"]),
                    target_regimes=json.loads(r["target_regimes_json"]),
                    creation_timestamp=datetime.fromisoformat(r["creation_timestamp"]),
                    status=CandidateStatus(r["status"]),
                    rationale=r["rationale"],
                    checksum=r["checksum"],
                    author=r["author"],
                    backtest_metrics=json.loads(r["backtest_metrics_json"]),
                    walk_forward_metrics=json.loads(r["walk_forward_metrics_json"]),
                    out_of_sample_metrics=json.loads(r["out_of_sample_metrics_json"]),
                    shadow_test_metrics=json.loads(r["shadow_test_metrics_json"]),
                    promotion_notes=r["promotion_notes"],
                    approved_by=r["approved_by"],
                    approved_at=datetime.fromisoformat(r["approved_at"]) if r["approved_at"] else None,
                )
            finally:
                conn.close()

    def list_candidates(self, status: Optional[CandidateStatus] = None) -> List[StrategyCandidateRecord]:
        with self._lock:
            conn = self._conn()
            try:
                query = "SELECT * FROM ati_strategy_candidates"
                params: List[Any] = []
                if status:
                    query += " WHERE status = ?"
                    params.append(status.value)
                query += " ORDER BY creation_timestamp DESC"
                rows = conn.execute(query, params).fetchall()
                cands = []
                for r in rows:
                    cands.append(
                        StrategyCandidateRecord(
                            candidate_id=r["candidate_id"],
                            base_strategy=r["base_strategy"],
                            version=r["version"],
                            parameters=json.loads(r["parameters_json"]),
                            target_symbols=json.loads(r["target_symbols_json"]),
                            target_regimes=json.loads(r["target_regimes_json"]),
                            creation_timestamp=datetime.fromisoformat(r["creation_timestamp"]),
                            status=CandidateStatus(r["status"]),
                            rationale=r["rationale"],
                            checksum=r["checksum"],
                            author=r["author"],
                            backtest_metrics=json.loads(r["backtest_metrics_json"]),
                            walk_forward_metrics=json.loads(r["walk_forward_metrics_json"]),
                            out_of_sample_metrics=json.loads(r["out_of_sample_metrics_json"]),
                            shadow_test_metrics=json.loads(r["shadow_test_metrics_json"]),
                            promotion_notes=r["promotion_notes"],
                            approved_by=r["approved_by"],
                            approved_at=datetime.fromisoformat(r["approved_at"]) if r["approved_at"] else None,
                        )
                    )
                return cands
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Configurations & Rollback
    # --------------------------------------------------------------------------
    def save_active_config(self, version: int, config_json: str, checksum: str, promoted_by: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute("UPDATE ati_active_configurations SET is_active = 0")
                    cur = conn.execute(
                        """
                        INSERT INTO ati_active_configurations (version, config_json, checksum, promoted_by, promoted_at, is_active)
                        VALUES (?, ?, ?, ?, ?, 1)
                        """,
                        (version, config_json, checksum, promoted_by, utc_now_iso()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def record_rollback_snapshot(self, version: int, config_json: str, reason: str) -> int:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO ati_rollback_snapshots (version, config_json, reason, created_at) VALUES (?, ?, ?, ?)",
                        (version, config_json, reason, utc_now_iso()),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def get_latest_rollback_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute("SELECT * FROM ati_rollback_snapshots ORDER BY id DESC LIMIT 1").fetchone()
                return dict(r) if r else None
            finally:
                conn.close()

    # --------------------------------------------------------------------------
    # Reporting
    # --------------------------------------------------------------------------
    def save_report(self, report_id: str, report_type: str, period_start: str, period_end: str, report_json: str) -> None:
        with self._lock:
            conn = self._conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO ati_reports (report_id, report_type, period_start, period_end, report_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (report_id, report_type, period_start, period_end, report_json, utc_now_iso()),
                    )
            finally:
                conn.close()

    def get_latest_report(self, report_type: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._conn()
            try:
                r = conn.execute(
                    "SELECT * FROM ati_reports WHERE report_type = ? ORDER BY created_at DESC LIMIT 1",
                    (report_type,),
                ).fetchone()
                return dict(r) if r else None
            finally:
                conn.close()
