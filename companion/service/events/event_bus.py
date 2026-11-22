"""
Thread-safe real-time event bus and structured log buffer for the Companion Control Service.
"""

from __future__ import annotations
import queue
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from companion.service.security.auth import redact_secrets


@dataclass
class StructuredLogEntry:
    id: str
    timestamp: str
    severity: str
    component: str
    message: str
    instrument: str = ""
    ticket: int = 0
    correlation_id: str = ""


class EventBus:
    """Publishes real-time state, telemetry, and structured log events to SSE clients."""

    def __init__(self, max_logs: int = 1500):
        self._lock = threading.RLock()
        self._logs: Deque[StructuredLogEntry] = deque(maxlen=max_logs)
        self._subscribers: List[queue.Queue] = []
        self._counter = 0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        msg = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with self._lock:
            dead: List[queue.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(msg)
                    except Exception:
                        dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def log(
        self,
        component: str,
        severity: str,
        message: str,
        instrument: str = "",
        ticket: int = 0,
        correlation_id: str = "",
    ) -> StructuredLogEntry:
        with self._lock:
            self._counter += 1
            entry = StructuredLogEntry(
                id=f"LOG_{self._counter}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity=severity.upper(),
                component=component.upper(),
                message=redact_secrets(message),
                instrument=instrument,
                ticket=int(ticket or 0),
                correlation_id=correlation_id,
            )
            self._logs.append(entry)
        self.publish_event("log", asdict(entry))
        return entry

    def get_logs(
        self,
        limit: int = 200,
        severity: Optional[str] = None,
        instrument: Optional[str] = None,
        component: Optional[str] = None,
        ticket: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._logs)
        if severity:
            sev = severity.upper()
            items = [i for i in items if i.severity == sev]
        if instrument:
            inst = instrument.upper()
            items = [i for i in items if inst in i.instrument.upper()]
        if component:
            comp = component.upper()
            items = [i for i in items if comp in i.component.upper()]
        if ticket is not None and ticket > 0:
            items = [i for i in items if i.ticket == ticket]
        if correlation_id:
            items = [i for i in items if correlation_id in i.correlation_id]
        return [asdict(i) for i in items[-limit:]]

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()
