"""
MT5 Historical Deal and Order Collector for ATI.
Retrieves executed deals from MetaTrader 5 API or BridgeClient,
enforces idempotent ingestion into the ATI repository, and coordinates reconciliation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.intelligence.contracts import BrokerDealRecord, CompletedPositionRecord
from src.intelligence.historian.normalization import AccountBrokerNormalizer
from src.intelligence.historian.reconciler import PositionLifecycleReconciler
from src.intelligence.storage.repository import ATIRepository

logger = logging.getLogger("ATI.Collector")


class MT5TradeHistorian:
    """
    Authoritative ingestion and reconciliation subsystem for executed broker trades.
    Retrieves deals incrementally, prevents duplicate processing, and updates position history.
    """

    def __init__(
        self,
        repo: ATIRepository,
        normalizer: Optional[AccountBrokerNormalizer] = None,
        reconciler: Optional[PositionLifecycleReconciler] = None,
        mt5_module: Any = None,
    ):
        self.repo = repo
        self.normalizer = normalizer or AccountBrokerNormalizer()
        self.reconciler = reconciler or PositionLifecycleReconciler(self.normalizer)
        self._mt5_override = mt5_module

    def _get_mt5(self) -> Any:
        if self._mt5_override is not None:
            return self._mt5_override
        try:
            import MetaTrader5 as mt5
            return mt5
        except Exception:
            return None

    def sync_history(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Pulls history deals from MT5, stores new deals idempotently,
        and triggers position reconciliation for affected positions.
        """
        mt5 = self._get_mt5()
        if mt5 is None:
            return {"status": "UNAVAILABLE", "error": "MetaTrader 5 module unavailable"}

        try:
            if not mt5.initialize():
                return {"status": "DISCONNECTED", "error": "Failed to initialize MT5"}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)}

        now = datetime.now(timezone.utc)
        if to_date is None:
            to_date = now + timedelta(days=1)
        if from_date is None:
            # Query repository for latest deal timestamp, otherwise backfill last 30 days
            last_ts = self.repo.get_latest_deal_timestamp()
            if last_ts is not None:
                from_date = last_ts - timedelta(hours=2)  # Overlap window for delayed broker settlements
            else:
                from_date = now - timedelta(days=30)

        # Get account metadata
        acc_info = mt5.account_info()
        acc_num = int(getattr(acc_info, "login", 0)) if acc_info else 0
        currency = str(getattr(acc_info, "currency", "USD")) if acc_info else "USD"
        company = str(getattr(acc_info, "company", "")) if acc_info else ""
        server = str(getattr(acc_info, "server", "")) if acc_info else ""
        trade_mode = "DEMO" if int(getattr(acc_info, "trade_mode", 0)) == 0 else "REAL"
        leverage = int(getattr(acc_info, "leverage", 100)) if acc_info else 100

        acc_context = self.normalizer.detect_account_context(
            account_number=acc_num,
            currency=currency,
            company=company,
            server=server,
            trade_mode=trade_mode,
            leverage=leverage,
        )

        try:
            raw_deals = mt5.history_deals_get(from_date, to_date)
        except Exception as fetch_err:
            return {"status": "FETCH_ERROR", "error": str(fetch_err)}

        if raw_deals is None:
            err = mt5.last_error()
            return {"status": "EMPTY", "deals_count": 0, "last_error": err}

        new_deals_count = 0
        affected_positions: set[int] = set()

        for d in raw_deals:
            deal_ticket = int(getattr(d, "ticket", 0))
            pos_id = int(getattr(d, "position_id", 0))
            if pos_id == 0:
                pos_id = deal_ticket  # Fallback for balance or standalone transactions

            symbol = str(getattr(d, "symbol", "") or "")
            # Verify symbol against canonical 3-symbol universe
            canon_sym = self.normalizer.resolve_canonical_symbol(symbol)
            if not canon_sym:
                # Deal is for symbol outside the 3 approved instruments; skip according to whitelist rules
                continue

            # Deal type
            dtype_val = int(getattr(d, "type", 0))
            deal_type = "DEAL_TYPE_BUY" if dtype_val == 0 else ("DEAL_TYPE_SELL" if dtype_val == 1 else "DEAL_TYPE_OTHER")

            # Entry type
            etype_val = int(getattr(d, "entry", 0))
            if etype_val == 0:
                entry_type = "ENTRY_IN"
            elif etype_val == 1:
                entry_type = "ENTRY_OUT"
            elif etype_val == 2:
                entry_type = "ENTRY_INOUT"
            elif etype_val == 3:
                entry_type = "ENTRY_OUT_BY"
            else:
                entry_type = "ENTRY_UNKNOWN"

            deal_time = datetime.fromtimestamp(float(getattr(d, "time", 0)), tz=timezone.utc)

            deal_record = BrokerDealRecord(
                deal_ticket=deal_ticket,
                order_ticket=int(getattr(d, "order", 0)),
                position_id=pos_id,
                symbol=symbol,
                canonical_symbol=canon_sym,
                deal_type=deal_type,
                entry_type=entry_type,
                volume=float(getattr(d, "volume", 0.0)),
                price=float(getattr(d, "price", 0.0)),
                commission=float(getattr(d, "commission", 0.0)),
                swap=float(getattr(d, "swap", 0.0)),
                profit=float(getattr(d, "profit", 0.0)),
                fee=float(getattr(d, "fee", 0.0)),
                magic=int(getattr(d, "magic", 0)),
                comment=str(getattr(d, "comment", "") or ""),
                timestamp=deal_time,
                account_number=acc_context.account_number,
                account_currency=acc_context.account_currency,
                denomination_factor=acc_context.denomination_factor,
            )

            # Idempotent insert
            if self.repo.insert_broker_deal(deal_record):
                new_deals_count += 1
                affected_positions.add(pos_id)

        # Reconcile affected positions
        completed_count = 0
        for pos_id in affected_positions:
            pos_deals = self.repo.get_deals_for_position(pos_id)
            reconciled = self.reconciler.reconcile_single_position(pos_id, pos_deals)
            if reconciled is not None:
                self.repo.upsert_completed_position(reconciled)
                completed_count += 1

        return {
            "status": "SUCCESS",
            "total_broker_deals": len(raw_deals),
            "new_deals_ingested": new_deals_count,
            "affected_positions": len(affected_positions),
            "completed_positions_reconciled": completed_count,
        }
