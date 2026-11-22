"""
Persistent Transaction and Order Reconciliation Manager.
Maintains an authoritative, crash-resilient ledger of all order requests,
broker-side confirmations, deal tickets, fill prices, and execution states.
Prevents duplicate order submissions across application restarts, network timeouts,
bridge reconnects, and repeated strategy signals.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import logging
import os
import tempfile
import threading
from typing import Dict, List, Optional, Any

from src.core.contracts import Position, OrderType

logger = logging.getLogger("TransactionManager")


@dataclass
class TransactionRecord:
    signal_id: str
    request_id: str
    broker_order_ticket: int = 0
    deal_ticket: int = 0
    position_ticket: int = 0
    symbol: str = ""
    direction: str = ""
    requested_volume: float = 0.0
    executed_volume: float = 0.0
    requested_entry: float = 0.0
    actual_fill_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    execution_status: str = "SUBMITTED"  # SUBMITTED, ACCEPTED, FILLED, PARTIALLY_FILLED, REJECTED, UNCONFIRMED, CLOSED
    timestamp: str = ""
    error_message: Optional[str] = None
    retcode: Optional[int] = None
    reconciled_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TransactionRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TransactionManager:
    """
    Authoritative local persistence ledger for trading transactions and order lifecycle.
    Guarantees idempotency and two-phase broker reconciliation.
    """

    def __init__(self, ledger_file: str = "data/order_transactions.json"):
        self.ledger_file = os.path.abspath(ledger_file)
        self._lock = threading.RLock()
        self._transactions: Dict[str, TransactionRecord] = {}  # key: request_id
        self._signal_to_request: Dict[str, str] = {}           # key: signal_id -> request_id
        self._position_to_request: Dict[int, str] = {}         # key: position_ticket -> request_id
        self._order_ticket_to_request: Dict[int, str] = {}     # key: order_ticket -> request_id
        os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)
        self._load_ledger()

    def _load_ledger(self) -> None:
        with self._lock:
            if not os.path.exists(self.ledger_file):
                return
            try:
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    raw_txs = data.get("transactions", {})
                    for req_id, tx_dict in raw_txs.items():
                        try:
                            rec = TransactionRecord.from_dict(tx_dict)
                            self._transactions[req_id] = rec
                            if rec.signal_id:
                                self._signal_to_request[rec.signal_id] = req_id
                            if rec.position_ticket > 0:
                                self._position_to_request[rec.position_ticket] = req_id
                            if rec.broker_order_ticket > 0:
                                self._order_ticket_to_request[rec.broker_order_ticket] = req_id
                        except Exception as e:
                            logger.warning(f"Error parsing transaction record {req_id}: {e}")
                logger.info(f"[TransactionManager] Loaded {len(self._transactions)} transaction records from {self.ledger_file}")
            except Exception as e:
                logger.error(f"[TransactionManager] Failed to read ledger file {self.ledger_file}: {e}")

    def _save_ledger(self) -> bool:
        with self._lock:
            dir_name = os.path.dirname(self.ledger_file)
            payload = {
                "version": "1.0.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "transactions": {k: v.to_dict() for k, v in self._transactions.items()}
            }
            try:
                with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                    temp_name = tf.name
                    json.dump(payload, tf, indent=2)
                    tf.flush()
                    os.fsync(tf.fileno())
                os.replace(temp_name, self.ledger_file)
                return True
            except Exception as e:
                logger.error(f"[TransactionManager] Failed to atomically persist ledger: {e}")
                if "temp_name" in locals() and os.path.exists(temp_name):
                    try:
                        os.remove(temp_name)
                    except Exception:
                        pass
                return False

    def is_signal_executed_or_in_flight(self, signal_id: str) -> bool:
        """Checks if a signal ID is currently in-flight (SUBMITTED, ACCEPTED) or unconfirmed."""
        with self._lock:
            if not signal_id:
                return False
            req_id = self._signal_to_request.get(signal_id)
            if not req_id:
                return False
            tx = self._transactions.get(req_id)
            if not tx:
                return False
            if tx.execution_status in ("CLOSED", "REJECTED"):
                return False
            return tx.execution_status in ("SUBMITTED", "ACCEPTED", "UNCONFIRMED")

    def is_request_active(self, request_id: str) -> bool:
        """Returns True if request is currently pending confirmation or filled."""
        with self._lock:
            tx = self._transactions.get(request_id)
            if not tx:
                return False
            return tx.execution_status in ("SUBMITTED", "ACCEPTED", "FILLED", "PARTIALLY_FILLED")

    def record_submission(
        self,
        signal_id: str = "",
        symbol: str = "",
        direction: str = "",
        volume: float = 0.0,
        price: float = 0.0,
        sl: float = 0.0,
        tp: float = 0.0,
        request_id: str = "",
        **kwargs
    ) -> TransactionRecord:
        """Records initial order submission to MT5."""
        req_id = request_id or kwargs.get("req_id") or f"REQ_{int(datetime.now(timezone.utc).timestamp()*1000)}"
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            tx = TransactionRecord(
                signal_id=signal_id,
                request_id=req_id,
                symbol=symbol,
                direction=direction,
                requested_volume=volume,
                requested_entry=price,
                stop_loss=sl,
                take_profit=tp,
                execution_status="SUBMITTED",
                timestamp=now_iso,
            )
            self._transactions[req_id] = tx
            if signal_id:
                self._signal_to_request[signal_id] = req_id
            self._save_ledger()
            return tx

    def record_acceptance(
        self,
        request_id: str,
        broker_order_ticket: int = 0,
        order_ticket: int = 0,
        retcode: int = 10009,
        comment: str = "",
        **kwargs
    ) -> Optional[TransactionRecord]:
        """Records MT5 broker acceptance of order request (retcode 10008/10009)."""
        ticket = broker_order_ticket or order_ticket
        with self._lock:
            tx = self._transactions.get(request_id)
            if not tx:
                return None
            tx.broker_order_ticket = ticket
            tx.retcode = retcode
            tx.execution_status = "ACCEPTED"
            tx.reconciled_at = datetime.now(timezone.utc).isoformat()
            if comment:
                tx.error_message = comment
            if ticket > 0:
                self._order_ticket_to_request[ticket] = request_id
            self._save_ledger()
            return tx

    def record_fill(
        self,
        request_id: str,
        position_ticket: int = 0,
        deal_ticket: int = 0,
        fill_price: float = 0.0,
        executed_volume: float = 0.0,
        actual_sl: float = 0.0,
        actual_tp: float = 0.0,
        is_partial: bool = False,
        **kwargs
    ) -> Optional[TransactionRecord]:
        """Records verified broker execution with confirmed position and deal tickets."""
        vol = executed_volume or kwargs.get("filled_volume", 0.0)
        s_loss = actual_sl if actual_sl > 0 else kwargs.get("sl", 0.0)
        t_profit = actual_tp if actual_tp > 0 else kwargs.get("tp", 0.0)
        px = fill_price or kwargs.get("price", 0.0)
        p_ticket = position_ticket or kwargs.get("ticket", 0)
        d_ticket = deal_ticket or kwargs.get("deal", 0)

        with self._lock:
            tx = self._transactions.get(request_id)
            if not tx:
                return None
            tx.position_ticket = p_ticket
            tx.deal_ticket = d_ticket
            tx.actual_fill_price = px
            tx.executed_volume = vol
            tx.stop_loss = s_loss
            tx.take_profit = t_profit
            tx.execution_status = "PARTIALLY_FILLED" if is_partial else "FILLED"
            tx.reconciled_at = datetime.now(timezone.utc).isoformat()
            if p_ticket > 0:
                self._position_to_request[p_ticket] = request_id
            self._save_ledger()
            return tx

    def record_partial_fill(
        self,
        request_id: str,
        position_ticket: int = 0,
        fill_price: float = 0.0,
        executed_volume: float = 0.0,
        remaining_volume: float = 0.0,
        deal_ticket: int = 0,
        actual_sl: float = 0.0,
        actual_tp: float = 0.0,
        sl: float = 0.0,
        tp: float = 0.0,
        **kwargs
    ) -> Optional[TransactionRecord]:
        """Records partial broker execution."""
        vol = executed_volume or kwargs.get("filled_volume", 0.0)
        s_loss = actual_sl or sl or kwargs.get("stop_loss", 0.0)
        t_profit = actual_tp or tp or kwargs.get("take_profit", 0.0)
        return self.record_fill(
            request_id=request_id,
            position_ticket=position_ticket,
            deal_ticket=deal_ticket,
            fill_price=fill_price,
            executed_volume=vol,
            actual_sl=s_loss,
            actual_tp=t_profit,
            is_partial=True,
            **kwargs
        )

    def record_rejection(
        self,
        request_id: str,
        error_message: str = "",
        retcode: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Optional[TransactionRecord]:
        """Records explicit broker or bridge rejection."""
        err_msg = error_message or reason or "Unknown rejection"
        with self._lock:
            tx = self._transactions.get(request_id)
            if not tx:
                return None
            tx.execution_status = "REJECTED"
            tx.error_message = err_msg
            if retcode is not None:
                tx.retcode = retcode
            tx.reconciled_at = datetime.now(timezone.utc).isoformat()
            self._save_ledger()
            return tx

    def record_unconfirmed(
        self,
        request_id: str,
        reason: str
    ) -> Optional[TransactionRecord]:
        """Records order accepted by MT5 but lacking deal/position confirmation."""
        with self._lock:
            tx = self._transactions.get(request_id)
            if not tx:
                return None
            tx.execution_status = "UNCONFIRMED"
            tx.error_message = reason
            tx.reconciled_at = datetime.now(timezone.utc).isoformat()
            self._save_ledger()
            return tx

    def record_close(
        self,
        position_ticket: int,
        exit_price: float = 0.0,
        profit: float = 0.0,
        close_reason: str = ""
    ) -> Optional[TransactionRecord]:
        """Marks position closed in transaction ledger."""
        with self._lock:
            req_id = self._position_to_request.get(position_ticket)
            if not req_id:
                return None
            tx = self._transactions.get(req_id)
            if not tx:
                return None
            tx.execution_status = "CLOSED"
            tx.reconciled_at = datetime.now(timezone.utc).isoformat()
            tx.error_message = f"Closed: {close_reason} (P/L: ${profit:.2f} @ {exit_price})"
            self._save_ledger()
            return tx

    def get_transaction(self, request_id: str) -> Optional[TransactionRecord]:
        with self._lock:
            return self._transactions.get(request_id)

    def get_transaction_by_signal_id(self, signal_id: str) -> Optional[TransactionRecord]:
        """Looks up transaction record by signal ID."""
        with self._lock:
            req_id = self._signal_to_request.get(signal_id)
            if req_id:
                return self._transactions.get(req_id)
            for tx in self._transactions.values():
                if tx.signal_id == signal_id:
                    return tx
            return None

    def get_open_transactions(self) -> List[TransactionRecord]:
        with self._lock:
            return [tx for tx in self._transactions.values() if tx.execution_status in ("FILLED", "PARTIALLY_FILLED", "UNCONFIRMED")]

    def reconcile_with_broker_positions(self, broker_positions: List[Position]) -> Dict[str, Any]:
        """
        Reconciles ledger against active MT5 broker positions.
        Identifies positions closed externally and confirms live active positions.
        """
        with self._lock:
            live_tickets = {p.ticket: p for p in broker_positions}
            reconciled_count = 0
            closed_count = 0

            for req_id, tx in self._transactions.items():
                if tx.execution_status in ("FILLED", "PARTIALLY_FILLED"):
                    if tx.position_ticket > 0 and tx.position_ticket not in live_tickets:
                        tx.execution_status = "CLOSED"
                        tx.reconciled_at = datetime.now(timezone.utc).isoformat()
                        tx.error_message = "Closed at broker (detected via position reconciliation)"
                        closed_count += 1
                    elif tx.position_ticket in live_tickets:
                        bp = live_tickets[tx.position_ticket]
                        tx.stop_loss = bp.stop_loss
                        tx.take_profit = bp.take_profit
                        tx.executed_volume = bp.volume
                        reconciled_count += 1

            if closed_count > 0 or reconciled_count > 0:
                self._save_ledger()

            return {
                "active_broker_positions": len(broker_positions),
                "reconciled_active_transactions": reconciled_count,
                "marked_closed_transactions": closed_count
            }

    def get_all_transactions(self) -> List[TransactionRecord]:
        with self._lock:
            return list(self._transactions.values())

    def clear(self) -> None:
        """Clears all records in ledger and persists empty state (useful for test resets)."""
        with self._lock:
            self._transactions.clear()
            self._save_ledger()
