"""
Centralized Notification Policy and Smart Deduplication Manager.
Enforces the Institutional EA Success-First Alert System:
- Suppresses repetitive rejected-trade alerts (ORDER REJECTED, SETUP SKIPPED, PRE-CHECK FAILED)
- Emits confirmed execution, closure, and validated signal alerts
- Guarantees immediate delivery of critical risk, connectivity, and circuit-breaker alerts
- Manages persistent state transitions and one-time recovery notifications
"""

from __future__ import annotations
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("NotificationPolicy")


DEFAULT_POLICY: Dict[str, Any] = {
    "trade_signals_enabled": True,
    "execution_success_enabled": True,
    "trade_closure_enabled": True,
    "profit_alerts_enabled": True,
    "critical_alerts_enabled": True,
    "recovery_alerts_enabled": True,
    "rejected_trade_alerts_enabled": False,
    "routine_status_alerts_enabled": False,
    "daily_summary_enabled": True,
    "notification_deduplication_enabled": True,
}


class NotificationPolicy:
    """Centralized policy and deduplication controller."""

    def __init__(
        self,
        config_path: str = "config/telegram_notifications.json",
        state_path: str = "data/notification_state.json",
    ):
        self.config_path = config_path
        self.state_path = state_path
        self._lock = threading.Lock()
        self._cfg: Dict[str, Any] = dict(DEFAULT_POLICY)
        self.load_config()

        # Active state deduplication mapping: key -> {"active": bool, "since": float, "last_summary": str}
        self._active_states: Dict[str, Dict[str, Any]] = {}
        self._load_state()

    def load_config(self) -> None:
        """Loads configuration from JSON file or initializes default."""
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        self._cfg.update(loaded)
                except Exception as e:
                    logger.warning(f"[NotificationPolicy] Failed to load config from {self.config_path}: {e}")
            else:
                self._save_config_unlocked()

    def _save_config_unlocked(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, indent=2)
        except Exception as e:
            logger.error(f"[NotificationPolicy] Could not save config: {e}")

    def _load_state(self) -> None:
        """Loads persistent deduplication state from disk."""
        with self._lock:
            if os.path.exists(self.state_path):
                try:
                    with open(self.state_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self._active_states = data
                except Exception as e:
                    logger.warning(f"[NotificationPolicy] Failed to load state from {self.state_path}: {e}")
                    self._active_states = {}

    def _save_state_unlocked(self) -> None:
        """Persists deduplication state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
            temp_path = f"{self.state_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._active_states, f, indent=2)
            if os.path.exists(self.state_path):
                os.replace(temp_path, self.state_path)
            else:
                os.rename(temp_path, self.state_path)
        except Exception as e:
            logger.error(f"[NotificationPolicy] Could not persist state: {e}")

    # -------------------------------------------------------------------------
    # Policy Checks
    # -------------------------------------------------------------------------
    def is_trade_signals_enabled(self) -> bool:
        return bool(self._cfg.get("trade_signals_enabled", True))

    def is_execution_success_enabled(self) -> bool:
        return bool(self._cfg.get("execution_success_enabled", True))

    def is_trade_closure_enabled(self) -> bool:
        return bool(self._cfg.get("trade_closure_enabled", True))

    def is_profit_alerts_enabled(self) -> bool:
        return bool(self._cfg.get("profit_alerts_enabled", True))

    def is_critical_alerts_enabled(self) -> bool:
        # Critical alerts must always remain enabled
        return bool(self._cfg.get("critical_alerts_enabled", True))

    def is_recovery_alerts_enabled(self) -> bool:
        return bool(self._cfg.get("recovery_alerts_enabled", True))

    def is_rejected_trade_alerts_enabled(self) -> bool:
        # Default False: Suppress all rejected setups and failed checks from Telegram
        return bool(self._cfg.get("rejected_trade_alerts_enabled", False))

    def is_routine_status_alerts_enabled(self) -> bool:
        # Default False: Suppress routine scanning, heartbeat, warmup updates
        return bool(self._cfg.get("routine_status_alerts_enabled", False))

    def is_daily_summary_enabled(self) -> bool:
        return bool(self._cfg.get("daily_summary_enabled", True))

    def is_deduplication_enabled(self) -> bool:
        return bool(self._cfg.get("notification_deduplication_enabled", True))

    # -------------------------------------------------------------------------
    # State Deduplication & Recovery Gate
    # -------------------------------------------------------------------------
    def transition_state(self, key: str, active: bool, summary: str = "") -> Tuple[bool, bool]:
        """
        Transitions a state condition (e.g. BRIDGE_OFFLINE, CIRCUIT_BREAKER_ACTIVE).
        Returns: (state_changed: bool, is_now_active: bool)
        """
        with self._lock:
            existing = self._active_states.get(key)
            was_active = existing.get("active", False) if existing else False

            if active == was_active:
                return False, active

            self._active_states[key] = {
                "active": active,
                "timestamp": time.time(),
                "summary": summary,
            }
            self._save_state_unlocked()
            return True, active

    def is_state_active(self, key: str) -> bool:
        with self._lock:
            rec = self._active_states.get(key)
            return bool(rec and rec.get("active", False))

    def get_active_states_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._active_states.values() if v.get("active", False))

    # -------------------------------------------------------------------------
    # Settings Display Card
    # -------------------------------------------------------------------------
    def format_settings_card(self) -> str:
        """Returns clean HTML dashboard summary of notification policy preferences."""
        def _badge(val: bool) -> str:
            return "ENABLED 🟢" if val else "DISABLED ⚪"

        active_count = self.get_active_states_count()
        lines = [
            "🔔 <b>TELEGRAM NOTIFICATION SETTINGS</b>\n",
            f"• <b>Trade Signals:</b> <code>{_badge(self.is_trade_signals_enabled())}</code>",
            f"• <b>Trade Executions:</b> <code>{_badge(self.is_execution_success_enabled())}</code>",
            f"• <b>Trade Closures:</b> <code>{_badge(self.is_trade_closure_enabled())}</code>",
            f"• <b>Profit Milestones:</b> <code>{_badge(self.is_profit_alerts_enabled())}</code>",
            f"• <b>Critical Risk Alerts:</b> <code>{_badge(self.is_critical_alerts_enabled())}</code>",
            f"• <b>Recovery Notifications:</b> <code>{_badge(self.is_recovery_alerts_enabled())}</code>",
            f"• <b>Rejected Trade Alerts:</b> <code>{_badge(self.is_rejected_trade_alerts_enabled())}</code>",
            f"• <b>Routine Status Alerts:</b> <code>{_badge(self.is_routine_status_alerts_enabled())}</code>",
            f"• <b>Daily Summary:</b> <code>{_badge(self.is_daily_summary_enabled())}</code>",
            f"• <b>Smart Deduplication:</b> <code>{_badge(self.is_deduplication_enabled())}</code>",
            f"\n🛡️ <b>Active State Incidents:</b> <code>{active_count}</code>",
            "<i>Use config/telegram_notifications.json to modify delivery preferences.</i>",
        ]
        return "\n".join(lines)


# Global default instance
_policy_instance: Optional[NotificationPolicy] = None


def get_notification_policy() -> NotificationPolicy:
    global _policy_instance
    if _policy_instance is None:
        _policy_instance = NotificationPolicy()
    return _policy_instance
