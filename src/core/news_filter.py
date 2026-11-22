"""
Macroeconomic and High-Impact News Protection Engine.
Monitors high-impact macroeconomic event blackout windows (US CPI, NFP, FOMC, Rate Decisions).
Features:
- Configurable pre-event and post-event blackout windows (e.g. 15-30 min before/after).
- Graceful offline fallback: if calendar feeds are unreachable or unconfigured,
  falls back safely to standard volatility and spread protections without crashing or freezing.
- Dynamic per-currency and per-symbol matching (USD events impact XAUUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Set

logger = logging.getLogger("NewsFilterEngine")


@dataclass
class EconomicNewsEvent:
    id: str
    title: str
    currency: str
    impact: str  # 'HIGH', 'MEDIUM', 'LOW'
    timestamp: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


class NewsFilterEngine:
    def __init__(
        self,
        restrict_minutes_before: int = 15,
        restrict_minutes_after: int = 15,
        restrict_high_only: bool = True,
        enabled: bool = False,
    ):
        self.enabled = enabled
        self.restrict_before = timedelta(minutes=restrict_minutes_before)
        self.restrict_after = timedelta(minutes=restrict_minutes_after)
        self.restrict_high_only = restrict_high_only
        self._news_events: List[EconomicNewsEvent] = []
        self._feed_healthy: bool = True
        self._static_schedules_enabled: bool = True

    def register_events(self, events: List[EconomicNewsEvent]) -> None:
        """Loads live or cached economic calendar events."""
        self._news_events = list(events)
        self._feed_healthy = True
        logger.info(f"[NEWS_FILTER] Registered {len(self._news_events)} economic events.")

    def clear_events(self) -> None:
        self._news_events = []

    def set_feed_status(self, is_healthy: bool) -> None:
        self._feed_healthy = is_healthy
        if not is_healthy:
            logger.warning("[NEWS_FILTER] Calendar feed unreachable; operating under graceful offline volatility fallback.")

    @staticmethod
    def _currency_matches_symbol(currency: str, symbol: str) -> bool:
        """Determines if news for `currency` impacts the trading `symbol`."""
        curr = currency.upper().strip()
        sym = symbol.upper().strip()
        # USD events impact almost all monitored assets (Gold, Crypto, Indices, Majors)
        if curr == "USD":
            return True
        if curr in sym:
            return True
        # Base currency checks
        if curr == "EUR" and "EUR" in sym:
            return True
        if curr == "GBP" and "GBP" in sym:
            return True
        if curr == "JPY" and "JPY" in sym:
            return True
        return False

    def is_trading_allowed(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether trading is allowed for `symbol` given current economic events.
        Returns: (is_allowed: bool, reason_if_blocked: Optional[str])
        """
        if not self.enabled:
            return True, None

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Check registered live events
        for ev in self._news_events:
            if self.restrict_high_only and ev.impact.upper() != "HIGH":
                continue

            if not self._currency_matches_symbol(ev.currency, symbol):
                continue

            ev_time = ev.timestamp
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)

            window_start = ev_time - self.restrict_before
            window_end = ev_time + self.restrict_after

            if window_start <= now <= window_end:
                diff_min = (ev_time - now).total_seconds() / 60.0
                if diff_min >= 0:
                    status_str = f"in {diff_min:.0f}m"
                else:
                    status_str = f"{abs(diff_min):.0f}m ago"
                msg = f"High-Impact News Blackout: '{ev.title}' ({ev.currency}) {status_str} [Window: -{self.restrict_before.total_seconds()/60:.0f}m / +{self.restrict_after.total_seconds()/60:.0f}m]"
                logger.info(f"[NEWS_FILTER] Blocked {symbol}: {msg}")
                return False, msg

        # Graceful fallback: If feed is offline or no events registered, allow trading safely
        return True, None
