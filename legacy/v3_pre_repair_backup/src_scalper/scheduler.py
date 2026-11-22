"""
Phase 10: Market Scheduler and Trading Calendar for Dual-Market Scalping.
Routes trading execution based on trading calendar:
- MONDAY – FRIDAY: GOLD (XAUUSD) active for new entries
- SATURDAY – SUNDAY: BITCOIN (BTCUSD) active for new entries
- ALL DAYS: Continuous monitoring and lifecycle management of existing positions
Explicitly supports broker-time offset, daylight-saving adjustment, and symbol trading session verification.
Never force-closes or abandons existing baskets on schedule transitions.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore

from src.scalper.config import SchedulerConfig
from src.scalper.symbol_resolver import ResolvedSymbolSpec

logger = logging.getLogger("MarketScheduler")


@dataclass
class MarketScheduleDecision:
    scheduled_symbol: str               # "GOLD" or "BTCUSD"
    day_name: str                       # "MONDAY", ..., "SUNDAY"
    timestamp: datetime
    is_broker_tradable: bool = False
    is_entry_permitted: bool = False
    reason: str = ""
    is_transition_bar: bool = False
    broker_utc_offset_hours: int = 0
    is_dst_active: bool = False


class MarketScheduler:
    """
    Calendar-aware routing scheduler managing market transitions, broker-time offsets,
    daylight-saving differences, and broker trading session verification.
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or SchedulerConfig()
        self.last_active_symbol: Optional[str] = None

    def get_current_time(self, dt_override: Optional[datetime] = None) -> datetime:
        """Returns localized datetime according to configured timezone or broker UTC offset."""
        if dt_override is not None:
            base_dt = dt_override if dt_override.tzinfo is not None else dt_override.replace(tzinfo=timezone.utc)
        else:
            base_dt = datetime.now(timezone.utc)

        tz_str = self.config.timezone.upper()
        if tz_str not in ("UTC", "Z", ""):
            try:
                tz = zoneinfo.ZoneInfo(self.config.timezone)
                return base_dt.astimezone(tz)
            except Exception:
                pass

        if self.config.broker_utc_offset_hours != 0:
            broker_tz = timezone(timedelta(hours=self.config.broker_utc_offset_hours))
            return base_dt.astimezone(broker_tz)

        return base_dt

    def get_scheduled_symbol_key(self, current_dt: Optional[datetime] = None) -> str:
        """
        Determines scheduled symbol key based on calendar day:
        - Monday through Friday -> "GOLD"
        - Saturday through Sunday -> "BTCUSD"
        """
        dt = self.get_current_time(current_dt)
        day_name = dt.strftime("%A").upper()

        weekend_days = [d.upper() for d in self.config.weekend_days]
        if day_name in weekend_days:
            return self.config.weekend_symbol.upper()

        weekday_days = [d.upper() for d in self.config.weekday_days]
        if day_name in weekday_days:
            return self.config.weekday_symbol.upper()

        return self.config.weekday_symbol.upper()

    def evaluate_market_status(
        self,
        symbol_spec: Optional[ResolvedSymbolSpec],
        current_dt: Optional[datetime] = None,
    ) -> MarketScheduleDecision:
        """
        Evaluates calendar schedule AND broker trading status:
        1. Checks day of week in configured timezone / broker time.
        2. Validates broker trading permissions (trade_mode == 4) on the scheduled symbol.
        3. Confirms valid live quotes (bid > 0, ask > 0).
        4. Never substitutes GOLD when BTCUSD is unavailable on weekends.
        """
        dt = self.get_current_time(current_dt)
        day_name = dt.strftime("%A").upper()
        scheduled_key = self.get_scheduled_symbol_key(dt)
        dst_delta = dt.dst()
        is_dst = bool(dst_delta and dst_delta.total_seconds() != 0)

        is_transition = False
        if self.last_active_symbol is not None and self.last_active_symbol != scheduled_key:
            is_transition = True
            logger.info(
                f"[SCHEDULER] Market transition detected: '{self.last_active_symbol}' -> '{scheduled_key}' "
                f"at {dt.isoformat()} ({day_name}). Existing open positions remain actively managed."
            )
        self.last_active_symbol = scheduled_key

        if not self.config.enabled:
            return MarketScheduleDecision(
                scheduled_symbol=scheduled_key,
                day_name=day_name,
                timestamp=dt,
                is_broker_tradable=True,
                is_entry_permitted=True,
                reason="Scheduler disabled: routing unrestricted.",
                is_transition_bar=is_transition,
                broker_utc_offset_hours=self.config.broker_utc_offset_hours,
                is_dst_active=is_dst,
            )

        is_broker_tradable = False
        if symbol_spec is None:
            reason = f"Symbol specification for {scheduled_key} is unavailable."
        elif not symbol_spec.is_tradable or symbol_spec.trade_mode != 4:
            reason = f"Broker trade_mode ({symbol_spec.trade_mode}) indicates {symbol_spec.symbol} is closed or disabled for trading."
        elif symbol_spec.bid <= 0 or symbol_spec.ask <= 0:
            reason = f"No live price quotes streaming for {symbol_spec.symbol} (bid: {symbol_spec.bid}, ask: {symbol_spec.ask})."
        else:
            is_broker_tradable = True
            reason = f"Active schedule confirmed: {day_name} -> {scheduled_key} ({symbol_spec.symbol}) tradable."

        is_entry_permitted = is_broker_tradable if self.config.require_symbol_trading_availability else True

        return MarketScheduleDecision(
            scheduled_symbol=scheduled_key,
            day_name=day_name,
            timestamp=dt,
            is_broker_tradable=is_broker_tradable,
            is_entry_permitted=is_entry_permitted,
            reason=reason,
            is_transition_bar=is_transition,
            broker_utc_offset_hours=self.config.broker_utc_offset_hours,
            is_dst_active=is_dst,
        )
