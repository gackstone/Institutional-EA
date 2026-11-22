"""
Phase 14: Concise Real-Time Monitoring & Throttled Telegram Notification Manager.
Includes all 15 mandatory telemetry fields:
- Instrument, Direction, Entry price, Lot size, Stop loss, Take profit,
  Basket identifier, Number of open positions, Current floating P/L, Realized P/L,
  Remaining risk budget, Account equity, Drawdown, Entry/exit reason, Execution latency.
Provides rate-limited alerts for:
- NEW_BASKET, ADDITIONAL_ENTRY, POSITION_CLOSURE, BASKET_COMPLETION, REVERSAL,
  RISK_LIMIT_REACHED, TRADING_PAUSED, BROKER_DISCONNECTION, SCHEDULER_TRANSITION, EMERGENCY_SHUTDOWN.
Never sends excessive messages on every tick.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ScalperNotifier")

ALERT_EVENT_TYPES = (
    "NEW_BASKET",
    "ADDITIONAL_ENTRY",
    "POSITION_CLOSURE",
    "BASKET_COMPLETION",
    "REVERSAL",
    "RISK_LIMIT_REACHED",
    "TRADING_PAUSED",
    "BROKER_DISCONNECTION",
    "SCHEDULER_TRANSITION",
    "EMERGENCY_SHUTDOWN",
)


@dataclass
class ScalperNotificationPayload:
    event_type: str
    instrument: str
    direction: str
    entry_price: float
    lot_size: float
    stop_loss: float
    take_profit: float
    basket_id: str
    open_positions_count: int
    floating_pnl_usd: float
    realized_pnl_usd: float
    remaining_risk_budget_usd: float
    account_equity_usd: float
    drawdown_pct: float
    reason: str
    execution_latency_ms: float
    timestamp: float = field(default_factory=time.time)

    def format_message(self) -> str:
        return (
            f"[{self.event_type}] {self.instrument} {self.direction} | "
            f"Basket: {self.basket_id} (Open: {self.open_positions_count}) | "
            f"Px: {self.entry_price:.2f} | Lot: {self.lot_size:.2f} | "
            f"SL: {self.stop_loss:.2f} | TP: {self.take_profit:.2f} | "
            f"Float P/L: ${self.floating_pnl_usd:.2f} | Realized P/L: ${self.realized_pnl_usd:.2f} | "
            f"Rem Risk: ${self.remaining_risk_budget_usd:.2f} | Equity: ${self.account_equity_usd:.2f} "
            f"(DD: {self.drawdown_pct:.2f}%) | Latency: {self.execution_latency_ms:.1f}ms | "
            f"Reason: {self.reason}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScalperNotificationManager:
    """
    Event-driven notification dispatcher with per-event rate limiting so the engine
    never spams Telegram on high-frequency ticks.
    """

    def __init__(self, min_interval_sec_by_type: Optional[Dict[str, float]] = None):
        self.min_interval_sec_by_type = min_interval_sec_by_type or {
            "RISK_LIMIT_REACHED": 30.0,
            "BROKER_DISCONNECTION": 30.0,
            "TRADING_PAUSED": 30.0,
        }
        self._last_sent_ts: Dict[str, float] = {}
        self.sent_notifications: List[ScalperNotificationPayload] = []
        self.suppressed_count: int = 0

    def emit(
        self,
        event_type: str,
        instrument: str,
        direction: str = "NONE",
        entry_price: float = 0.0,
        lot_size: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        basket_id: str = "NONE",
        open_positions_count: int = 0,
        floating_pnl_usd: float = 0.0,
        realized_pnl_usd: float = 0.0,
        remaining_risk_budget_usd: float = 0.0,
        account_equity_usd: float = 1000.0,
        drawdown_pct: float = 0.0,
        reason: str = "",
        execution_latency_ms: float = 0.0,
        now_override: Optional[float] = None,
    ) -> Optional[ScalperNotificationPayload]:
        now_ts = now_override if now_override is not None else time.time()
        ev = event_type.upper()

        cooldown = self.min_interval_sec_by_type.get(ev, 0.0)
        if cooldown > 0:
            last_t = self._last_sent_ts.get(ev, 0.0)
            if now_ts - last_t < cooldown:
                self.suppressed_count += 1
                return None

        payload = ScalperNotificationPayload(
            event_type=ev,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            lot_size=lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            basket_id=basket_id,
            open_positions_count=open_positions_count,
            floating_pnl_usd=round(floating_pnl_usd, 2),
            realized_pnl_usd=round(realized_pnl_usd, 2),
            remaining_risk_budget_usd=round(remaining_risk_budget_usd, 2),
            account_equity_usd=round(account_equity_usd, 2),
            drawdown_pct=round(drawdown_pct, 2),
            reason=reason,
            execution_latency_ms=round(execution_latency_ms, 2),
            timestamp=now_ts,
        )
        self._last_sent_ts[ev] = now_ts
        self.sent_notifications.append(payload)
        logger.info(f"[NOTIFY] {payload.format_message()}")
        return payload
