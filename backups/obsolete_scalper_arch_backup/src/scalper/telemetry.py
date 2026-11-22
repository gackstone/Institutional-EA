"""
Phase 2: Execution Latency Measurement & Duplicate-Order Prevention Guard.
Measures actual broker and infrastructure performance:
- Signal calculation latency (ms)
- Order submission latency (ms)
- Broker acknowledgement latency (ms)
- Fill latency (ms)
- Slippage (points & USD)
- Rejection rate (%)
- Missed opportunities
- Duplicate-order prevention count
"""

from __future__ import annotations
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Set


@dataclass
class OrderTelemetrySample:
    entry_id: str
    symbol: str
    direction: str
    signal_latency_ms: float = 0.0
    submission_latency_ms: float = 0.0
    broker_ack_latency_ms: float = 0.0
    fill_latency_ms: float = 0.0
    requested_price: float = 0.0
    fill_price: float = 0.0
    slippage_points: float = 0.0
    slippage_usd: float = 0.0
    is_filled: bool = False
    is_rejected: bool = False
    rejection_reason: str = ""
    timestamp: float = field(default_factory=time.time)


class DuplicateOrderGuard:
    """
    Prevents duplicate orders caused by repeated ticks, reconnects, or delayed acknowledgements.
    Tracks both:
    - Idempotency entry tokens (`entry_id`)
    - Fingerprint keys `(symbol, direction, tick_seq, slot_idx)` within a configurable time window
    """

    def __init__(self, dedup_window_ms: int = 1000):
        self.dedup_window_ms = dedup_window_ms
        self._seen_entry_ids: Set[str] = set()
        self._recent_fingerprints: Dict[str, float] = {}
        self.duplicates_blocked: int = 0

    def check_and_register(
        self,
        entry_id: str,
        symbol: str,
        direction: str,
        tick_seq: int = 0,
        slot_index: int = 0,
        now_override: Optional[float] = None,
    ) -> bool:
        """
        Returns True if the order is unique and permitted; False if it is a duplicate.
        """
        now_ts = now_override if now_override is not None else time.time()

        if entry_id and entry_id in self._seen_entry_ids:
            self.duplicates_blocked += 1
            return False

        # Prune expired fingerprints
        cutoff = now_ts - (self.dedup_window_ms / 1000.0)
        if len(self._recent_fingerprints) > 200:
            self._recent_fingerprints = {
                k: ts for k, ts in self._recent_fingerprints.items() if ts >= cutoff
            }

        if tick_seq > 0:
            fp = f"{symbol.upper()}:{direction.upper()}:SEQ{tick_seq}:SLOT{slot_index}"
            if fp in self._recent_fingerprints and self._recent_fingerprints[fp] >= cutoff:
                self.duplicates_blocked += 1
                return False
            self._recent_fingerprints[fp] = now_ts

        if entry_id:
            self._seen_entry_ids.add(entry_id)
        return True


class ExecutionLatencyTracker:
    """
    Records high-resolution latency and slippage metrics across the 10-stage execution pipeline.
    """

    def __init__(self):
        self.samples: List[OrderTelemetrySample] = []
        self.signal_latencies_ms: List[float] = []
        self.missed_opportunities: Dict[str, int] = {}
        self.duplicate_orders_prevented: int = 0

    def record_signal_latency(self, latency_ms: float) -> None:
        self.signal_latencies_ms.append(round(max(0.0, latency_ms), 4))

    def record_missed_opportunity(self, reason: str) -> None:
        self.missed_opportunities[reason] = self.missed_opportunities.get(reason, 0) + 1

    def record_duplicate_prevented(self) -> None:
        self.duplicate_orders_prevented += 1

    def record_order_sample(self, sample: OrderTelemetrySample) -> None:
        self.samples.append(sample)

    def summary(self) -> Dict[str, Any]:
        filled = [s for s in self.samples if s.is_filled]
        rejected = [s for s in self.samples if s.is_rejected]
        total = len(self.samples)

        def _avg(vals: List[float]) -> float:
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        def _max(vals: List[float]) -> float:
            return round(max(vals), 3) if vals else 0.0

        sig_lats = self.signal_latencies_ms or [s.signal_latency_ms for s in self.samples if s.signal_latency_ms > 0]
        sub_lats = [s.submission_latency_ms for s in self.samples if s.submission_latency_ms >= 0]
        ack_lats = [s.broker_ack_latency_ms for s in self.samples if s.broker_ack_latency_ms >= 0]
        fill_lats = [s.fill_latency_ms for s in filled]
        slip_pts = [s.slippage_points for s in filled]
        slip_usd = [s.slippage_usd for s in filled]

        rej_rate = round((len(rejected) / total * 100.0), 2) if total > 0 else 0.0

        return {
            "total_orders_evaluated": total,
            "filled_orders": len(filled),
            "rejected_orders": len(rejected),
            "rejection_rate_pct": rej_rate,
            "signal_calculation_latency_ms": {
                "avg": _avg(sig_lats),
                "max": _max(sig_lats),
                "samples": len(sig_lats),
            },
            "order_submission_latency_ms": {
                "avg": _avg(sub_lats),
                "max": _max(sub_lats),
            },
            "broker_acknowledgement_latency_ms": {
                "avg": _avg(ack_lats),
                "max": _max(ack_lats),
            },
            "fill_latency_ms": {
                "avg": _avg(fill_lats),
                "max": _max(fill_lats),
            },
            "slippage": {
                "avg_points": _avg(slip_pts),
                "max_points": _max(slip_pts),
                "total_slippage_usd": round(sum(slip_usd), 2),
            },
            "missed_opportunities_total": sum(self.missed_opportunities.values()),
            "missed_opportunities_by_reason": dict(self.missed_opportunities),
            "duplicate_orders_prevented": self.duplicate_orders_prevented,
        }
