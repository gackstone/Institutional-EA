"""
Trading Calendar and Schedule Engine for MT5 001.
Governs operating modes:
- WEEKDAY_GOLD_MODE (Monday to Friday):
    1. XAUUSD — Primary trading instrument (highest scanning and analysis priority).
    2. USDJPY — Secondary instrument with inverse directional coordination.
    3. BTCUSD — Disabled during normal weekdays unless explicitly enabled as fallback.
- WEEKEND_BTC_MODE (Saturday and Sunday):
    1. BTCUSD — Primary and exclusively permitted new-entry trading instrument.
    2. XAUUSD — Inactive for new entries (existing positions continue to be managed).
    3. USDJPY — Inactive for new entries (existing positions continue to be managed).

Uses broker server time / configured timezone as reference for calendar day transitions.
Preserves existing position management across all schedule transitions without force-closing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, time
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from src.core.symbol_universe import SpecializedSymbolUniverse, get_symbol_universe

logger = logging.getLogger("TradingScheduler")


class OperatingMode(str, Enum):
    WEEKDAY_GOLD_MODE = "WEEKDAY_GOLD_MODE"
    WEEKEND_BTC_MODE = "WEEKEND_BTC_MODE"


class InstrumentTradingStatus(str, Enum):
    PRIMARY = "PRIMARY"
    INVERSE_COORDINATION = "INVERSE_COORDINATION"
    FALLBACK = "FALLBACK"
    INACTIVE = "INACTIVE"


@dataclass
class ScheduleStatusSnapshot:
    operating_mode: OperatingMode
    current_day: str
    current_time_utc: str
    broker_server_time: Optional[str]
    instrument_statuses: Dict[str, str]
    scanning_order: List[str]
    weekday_btc_fallback_enabled: bool


class TradingScheduleManager:
    """
    Manages weekday vs weekend trading schedules, instrument priorities,
    and eligibility for new orders.
    """

    def __init__(
        self,
        symbol_universe: Optional[SpecializedSymbolUniverse] = None,
        weekday_btc_fallback_enabled: bool = True,
        weekend_start_friday_hour_utc: int = 22,
        weekend_end_sunday_hour_utc: int = 22,
    ):
        self.universe = symbol_universe or get_symbol_universe()
        self.weekday_btc_fallback_enabled = weekday_btc_fallback_enabled
        self.weekend_start_friday_hour_utc = weekend_start_friday_hour_utc
        self.weekend_end_sunday_hour_utc = weekend_end_sunday_hour_utc
        self._current_mode: OperatingMode = OperatingMode.WEEKDAY_GOLD_MODE
        self._last_logged_day: Optional[int] = None
        self._last_logged_mode: Optional[OperatingMode] = None

    def get_current_operating_mode(self, current_dt: Optional[datetime] = None) -> OperatingMode:
        """
        Calculates the active operating mode based on current timestamp.
        Monday 00:00 UTC through Friday 22:00 UTC -> WEEKDAY_GOLD_MODE
        Friday 22:00 UTC through Sunday 22:00 UTC -> WEEKEND_BTC_MODE
        """
        now = current_dt or datetime.now(timezone.utc)
        weekday = now.weekday()  # Monday = 0, Sunday = 6
        hour = now.hour

        # Check for Friday post-close weekend transition
        if weekday == 4 and hour >= self.weekend_start_friday_hour_utc:
            mode = OperatingMode.WEEKEND_BTC_MODE
        # Saturday is weekend
        elif weekday == 5:
            mode = OperatingMode.WEEKEND_BTC_MODE
        # Sunday before market open is weekend
        elif weekday == 6 and hour < self.weekend_end_sunday_hour_utc:
            mode = OperatingMode.WEEKEND_BTC_MODE
        # All other times are weekday
        else:
            mode = OperatingMode.WEEKDAY_GOLD_MODE

        self._check_and_log_mode_transition(now, mode)
        self._current_mode = mode
        return mode

    def _check_and_log_mode_transition(self, now: datetime, mode: OperatingMode) -> None:
        weekday = now.weekday()
        day_name = now.strftime("%A")

        if self._last_logged_mode != mode or self._last_logged_day != weekday:
            if mode == OperatingMode.WEEKDAY_GOLD_MODE:
                logger.info(f"[TRADING_SCHEDULER] {day_name} detected. Activating WEEKDAY_GOLD_MODE.")
                logger.info("[SUCCESS] [PRIORITY_ENGINE] XAUUSD assigned primary weekday scanning priority.")
                if not self.weekday_btc_fallback_enabled:
                    logger.info("[INFO] [PRIORITY_ENGINE] BTCUSD set to INACTIVE for weekday operation.")
            else:
                logger.info(f"[TRADING_SCHEDULER] {day_name} detected. Activating WEEKEND_BTC_MODE.")
                logger.info("[SUCCESS] [SYMBOL_MANAGER] BTCUSD activated as weekend trading instrument.")
                logger.info("[INFO] [SYMBOL_MANAGER] XAUUSD trading paused for weekend mode.")

            self._last_logged_mode = mode
            self._last_logged_day = weekday

    def is_instrument_eligible_for_new_entry(
        self,
        symbol: str,
        current_dt: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Strict gate checking whether a symbol can receive NEW order submissions
        under current schedule rules.
        Existing open positions are NEVER blocked from position management by this check.
        """
        # 1. Universe authorization check
        valid_symbol, reject_reason = self.universe.validate_or_reject(symbol)
        if not valid_symbol:
            return False, reject_reason or f"Unauthorized symbol '{symbol}'"

        canon = self.universe.get_canonical_symbol(symbol)
        if canon == "USDJPY" or self.universe.normalize_root(symbol) == "USDJPY":
            return False, "INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted."

        mode = self.get_current_operating_mode(current_dt)

        # 2. Weekday Mode rules
        if mode == OperatingMode.WEEKDAY_GOLD_MODE:
            if canon == "XAUUSD":
                return True, "WEEKDAY_PRIMARY: XAUUSD eligible for primary execution."
            elif canon == "BTCUSD":
                if self.weekday_btc_fallback_enabled:
                    return True, "WEEKDAY_FALLBACK: BTCUSD eligible as configured fallback instrument."
                return False, "WEEKDAY_INACTIVE: BTCUSD is inactive during standard weekday Gold mode."

        # 3. Weekend Mode rules
        elif mode == OperatingMode.WEEKEND_BTC_MODE:
            if canon == "BTCUSD":
                return True, "WEEKEND_PRIMARY: BTCUSD eligible for primary weekend execution."
            elif canon == "XAUUSD":
                return False, "WEEKEND_INACTIVE: XAUUSD trading is disabled during weekend mode."

        return False, f"SCHEDULE_INACTIVE: Symbol '{symbol}' not eligible under mode {mode.value}"

    def get_scanning_priority_order(self, current_dt: Optional[datetime] = None) -> List[str]:
        """
        Returns resolved broker symbols in the exact priority order for scanning:
        - Weekday: [XAUUSD_broker] (plus BTCUSD_broker if fallback enabled)
        - Weekend: [BTCUSD_broker]
        """
        mode = self.get_current_operating_mode(current_dt)
        xau_broker = self.universe.get_broker_symbol("XAUUSD")
        btc_broker = self.universe.get_broker_symbol("BTCUSD")

        if mode == OperatingMode.WEEKDAY_GOLD_MODE:
            order = [xau_broker]
            if self.weekday_btc_fallback_enabled:
                order.append(btc_broker)
            return order
        else:
            return [btc_broker]

    def get_instrument_status(
        self,
        symbol: str,
        current_dt: Optional[datetime] = None
    ) -> InstrumentTradingStatus:
        """Returns the high-level trading status for UI/dashboard reporting."""
        canon = self.universe.get_canonical_symbol(symbol)
        mode = self.get_current_operating_mode(current_dt)

        if mode == OperatingMode.WEEKDAY_GOLD_MODE:
            if canon == "XAUUSD":
                return InstrumentTradingStatus.PRIMARY
            elif canon == "BTCUSD":
                return InstrumentTradingStatus.FALLBACK if self.weekday_btc_fallback_enabled else InstrumentTradingStatus.INACTIVE
        else:
            if canon == "BTCUSD":
                return InstrumentTradingStatus.PRIMARY
            else:
                return InstrumentTradingStatus.INACTIVE

        return InstrumentTradingStatus.INACTIVE

    def get_operating_mode(self, current_dt: Optional[datetime] = None) -> OperatingMode:
        """Alias for get_current_operating_mode."""
        return self.get_current_operating_mode(current_dt)

    def get_status(self, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Dictionary snapshot of schedule status."""
        snap = self.get_status_snapshot(current_dt)
        return {
            "mode": snap.operating_mode.value,
            "weekday_name": snap.current_day,
            "priority_order": snap.scanning_order,
            "instrument_statuses": snap.instrument_statuses,
            "weekday_btc_fallback_enabled": snap.weekday_btc_fallback_enabled,
        }

    def get_status_snapshot(
        self,
        current_dt: Optional[datetime] = None,
        broker_server_time_str: Optional[str] = None
    ) -> ScheduleStatusSnapshot:
        now = current_dt or datetime.now(timezone.utc)
        mode = self.get_current_operating_mode(now)
        statuses = {
            "XAUUSD": self.get_instrument_status("XAUUSD", now).value,
            "USDJPY": self.get_instrument_status("USDJPY", now).value,
            "BTCUSD": self.get_instrument_status("BTCUSD", now).value,
        }
        return ScheduleStatusSnapshot(
            operating_mode=mode,
            current_day=now.strftime("%A"),
            current_time_utc=now.isoformat(),
            broker_server_time=broker_server_time_str,
            instrument_statuses=statuses,
            scanning_order=self.get_scanning_priority_order(now),
            weekday_btc_fallback_enabled=self.weekday_btc_fallback_enabled,
        )


_default_schedule_instance: Optional[TradingScheduleManager] = None


def get_trading_schedule(weekday_btc_fallback: bool = True) -> TradingScheduleManager:
    global _default_schedule_instance
    if _default_schedule_instance is None:
        _default_schedule_instance = TradingScheduleManager(weekday_btc_fallback_enabled=weekday_btc_fallback)
    else:
        _default_schedule_instance.weekday_btc_fallback_enabled = weekday_btc_fallback
    return _default_schedule_instance
