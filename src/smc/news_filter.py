"""
SMC News Filter Engine.
Monitors high-impact macroeconomic event blackout windows (US CPI, NFP, FOMC, Rate Decisions).
Features:
- Configurable pre-event and post-event blackout windows (e.g. 15-30 min before/after).
- Graceful offline fallback: if calendar feeds are unreachable or unconfigured,
  falls back safely to standard volatility protections without crashing or freezing.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger("SmcNewsFilterEngine")


@dataclass
class EconomicEvent:
    event_id: str
    currency: str
    title: str
    event_time: datetime
    impact: str = "HIGH"


class NewsFilterEngine:
    def __init__(
        self,
        blackout_minutes_before: int = 15,
        blackout_minutes_after: int = 15,
        enabled: bool = False
    ):
        self.blackout_minutes_before = blackout_minutes_before
        self.blackout_minutes_after = blackout_minutes_after
        self.enabled = enabled
        self._events: List[EconomicEvent] = []

    def set_events(self, events: List[EconomicEvent]) -> None:
        self._events = list(events)
        logger.info(f"[SMC_NEWS_FILTER] Set {len(self._events)} events.")

    def add_event(self, event: EconomicEvent) -> None:
        self._events.append(event)

    def is_in_blackout(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        if not self.enabled or not self._events:
            return False, None

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        sym = symbol.upper()
        for ev in self._events:
            if ev.impact.upper() != "HIGH":
                continue
            curr = ev.currency.upper()
            if curr != "USD" and curr not in sym:
                continue

            ev_time = ev.event_time
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)

            w_start = ev_time - timedelta(minutes=self.blackout_minutes_before)
            w_end = ev_time + timedelta(minutes=self.blackout_minutes_after)

            if w_start <= now <= w_end:
                return True, f"High-Impact News: {ev.title} ({ev.currency}) at {ev_time.isoformat()}"

        return False, None
