"""
Phase 9 & Master Repair: Shared Account Equity & Risk Protection Controller Across GOLD and BTCUSD.
Enforces:
1. Canonical `account_risk` configuration with legacy adapter synchronization.
2. Explicit, distinguishable risk actions:
   - PASS
   - BLOCK_NEW_ENTRIES
   - PAUSE_NEW_ENTRIES
   - MANAGE_EXISTING_POSITIONS
   - CLOSE_ALL_AND_PAUSE
   - LIQUIDATE_ALL_AND_PAUSE
   - CLOSE_ALL_AND_HALT
3. Separated pause lifecycles (loss-streak cooldown vs drawdown circuit breaker vs daily loss pause):
   - A consecutive-loss cooldown blocks new entries (`PAUSE_NEW_ENTRIES`), preserves its `LOSS_STREAK_COOLDOWN`
     category, continues managing existing positions, and NEVER triggers emergency liquidation or masquerades as `DRAWDOWN`.
4. Deduplicated `RiskTriggerEvent` tracking (updates `occurrence_count` and `last_seen_timestamp` instead of
   appending duplicate events on every engine tick).
5. Fail-safe, latched `STOP.flag` kill switch requiring explicit operator recovery.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from src.scalper.config import ScalperConfig

logger = logging.getLogger("AccountRiskManager")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class RiskAction:
    PASS = "PASS"
    BLOCK_NEW_ENTRIES = "BLOCK_NEW_ENTRIES"
    PAUSE_NEW_ENTRIES = "PAUSE_NEW_ENTRIES"
    MANAGE_EXISTING_POSITIONS = "MANAGE_EXISTING_POSITIONS"
    CLOSE_ALL_AND_PAUSE = "CLOSE_ALL_AND_PAUSE"
    LIQUIDATE_ALL_AND_PAUSE = "LIQUIDATE_ALL_AND_PAUSE"
    CLOSE_ALL_AND_HALT = "CLOSE_ALL_AND_HALT"


@dataclass
class RiskCheckVerdict:
    allowed: bool
    reason: str = ""
    category: str = "PASS"
    action: str = RiskAction.PASS


@dataclass
class RiskTriggerEvent:
    category: str
    reason: str
    emergency_policy: str
    timestamp: float = field(default_factory=time.time)
    last_seen_timestamp: float = field(default_factory=time.time)
    occurrence_count: int = 1


class AccountRiskManager:
    def __init__(self, config: ScalperConfig):
        self.config = config
        self.manual_kill_triggered: bool = False
        self.kill_switch_latched: bool = False
        self.kill_switch_reason: str = ""

        # Separate pause timers by category so loss-streak cooldown never masquerades as drawdown
        self.loss_streak_pause_until: float = 0.0
        self.drawdown_pause_until: float = 0.0
        self.daily_loss_pause_until: float = 0.0
        self.pause_until_timestamp: float = 0.0
        self.active_pause_category: str = ""
        self.active_pause_reason: str = ""

        self.circuit_breaker_active: bool = False
        self.circuit_breaker_reason: str = ""
        self._drawdown_liquidation_dispatched: bool = False
        self._daily_loss_close_dispatched: bool = False

        self.consecutive_losses: int = 0
        self.realized_daily_pnl_usd: float = 0.0
        self.broker_connected: bool = True
        self.last_broker_heartbeat: float = time.time()
        self.trigger_events: List[RiskTriggerEvent] = []
        self._active_triggers: Dict[str, RiskTriggerEvent] = {}

    @property
    def is_paused(self) -> bool:
        now_ts = time.time()
        return (
            now_ts < self.pause_until_timestamp
            or now_ts < self.loss_streak_pause_until
            or now_ts < self.drawdown_pause_until
            or now_ts < self.daily_loss_pause_until
        )

    def _record_trigger(self, category: str, reason: str, policy: str = RiskAction.BLOCK_NEW_ENTRIES) -> None:
        """
        Records a risk trigger event while deduplicating persistent consecutive triggers of the same category.
        """
        now_ts = time.time()
        active = self._active_triggers.get(category)
        if active is not None and active.emergency_policy == policy:
            active.occurrence_count += 1
            active.last_seen_timestamp = now_ts
            active.reason = reason
            return

        ev = RiskTriggerEvent(
            category=category,
            reason=reason,
            emergency_policy=policy,
            timestamp=now_ts,
            last_seen_timestamp=now_ts,
            occurrence_count=1,
        )
        self.trigger_events.append(ev)
        self._active_triggers[category] = ev

    def _clear_trigger(self, category: str) -> None:
        self._active_triggers.pop(category, None)

    def resolve_kill_switch_path(self) -> Optional[Path]:
        if not self.config or not getattr(self.config, "kill_switch", None):
            return None
        raw_path = str(getattr(self.config.kill_switch, "flag_file_path", "") or "").strip()
        if not raw_path:
            return None
        p = Path(raw_path)
        if p.is_absolute():
            return p
        # Check working directory first, then project root for predictable resolution
        cwd_p = Path.cwd() / p
        if cwd_p.exists():
            return cwd_p.resolve()
        root_p = PROJECT_ROOT / p
        return root_p.resolve()

    def trigger_manual_kill(self, reason: str = "Operator invoked kill switch") -> None:
        self.manual_kill_triggered = True
        self.kill_switch_latched = True
        self.kill_switch_reason = reason
        self._record_trigger("KILL_SWITCH", reason, RiskAction.CLOSE_ALL_AND_HALT)
        logger.critical(f"[KILL_SWITCH] Emergency kill switch manually activated: {reason}")

    @property
    def kill_switch_triggered(self) -> bool:
        return self.kill_switch_latched or self.manual_kill_triggered

    def reset_daily_baseline(self, balance: float) -> None:
        self.daily_starting_balance = float(balance)
        self.realized_daily_pnl_usd = 0.0
        self.daily_loss_pause_until = 0.0

    def acknowledge_and_reset_kill_switch(self, operator_confirmed: bool = True) -> bool:
        """
        Explicit operator recovery procedure:
        1. Requires `operator_confirmed=True`.
        2. Verifies `STOP.flag` file is no longer present on disk.
        3. Clears latched kill switch state.
        """
        if not operator_confirmed:
            return False
        flag_path = self.resolve_kill_switch_path()
        if flag_path is not None and flag_path.exists():
            logger.warning(f"[KILL_SWITCH] Cannot reset kill switch while flag file still exists at '{flag_path}'")
            return False
        self.manual_kill_triggered = False
        self.kill_switch_latched = False
        self.kill_switch_reason = ""
        self._clear_trigger("KILL_SWITCH")
        logger.info("[KILL_SWITCH] Operator confirmed safe reset of kill switch.")
        return True

    def check_kill_switch(self) -> RiskCheckVerdict:
        # Fail-safe: missing or disabled kill_switch configuration blocks trading
        if not self.config or not getattr(self.config, "kill_switch", None) or not self.config.kill_switch.enabled:
            reason = "Kill switch safety configuration is missing or disabled (fail-safe halt)"
            self._record_trigger("KILL_SWITCH", reason, RiskAction.CLOSE_ALL_AND_HALT)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="KILL_SWITCH",
                action=RiskAction.CLOSE_ALL_AND_HALT,
            )

        flag_path = self.resolve_kill_switch_path()
        if flag_path is None:
            reason = "Kill switch flag_file_path is empty or invalid (fail-safe halt)"
            self._record_trigger("KILL_SWITCH", reason, RiskAction.CLOSE_ALL_AND_HALT)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="KILL_SWITCH",
                action=RiskAction.CLOSE_ALL_AND_HALT,
            )

        if self.manual_kill_triggered:
            reason = self.kill_switch_reason or "Emergency kill switch triggered by operator command"
            self._record_trigger("KILL_SWITCH", reason, RiskAction.CLOSE_ALL_AND_HALT)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="KILL_SWITCH",
                action=RiskAction.CLOSE_ALL_AND_HALT,
            )

        if flag_path.exists():
            reason = f"Emergency kill switch flag file detected at '{flag_path}'"
            self.kill_switch_latched = True
            self.kill_switch_reason = reason
            action = str(getattr(self.config.kill_switch, "on_trigger_action", RiskAction.CLOSE_ALL_AND_HALT))
            self._record_trigger("KILL_SWITCH", reason, action)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="KILL_SWITCH",
                action=action,
            )

        if self.kill_switch_latched:
            reason = f"Kill switch remains latched ({self.kill_switch_reason}); explicit operator reset required"
            self._record_trigger("KILL_SWITCH", reason, RiskAction.CLOSE_ALL_AND_HALT)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="KILL_SWITCH",
                action=RiskAction.CLOSE_ALL_AND_HALT,
            )

        self._clear_trigger("KILL_SWITCH")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_demo_live_mode(self, account_trade_mode: str) -> RiskCheckVerdict:
        if not self.config or not getattr(self.config, "general", None):
            msg = "Missing general safety configuration (fail-safe block)"
            self._record_trigger("SAFETY_MODE", msg, RiskAction.CLOSE_ALL_AND_HALT)
            return RiskCheckVerdict(allowed=False, reason=msg, category="SAFETY_MODE", action=RiskAction.CLOSE_ALL_AND_HALT)

        is_demo_account = str(account_trade_mode).upper() in ("DEMO", "0", "ACCOUNT_TRADE_MODE_DEMO")
        demo_configured = bool(self.config.general.DEMO_MODE and self.config.safety_mode.DEMO_MODE)

        if demo_configured:
            if not is_demo_account:
                msg = (
                    f"LIVE ACCOUNT REJECTED: System configured in DEMO_MODE=true, "
                    f"but connected to LIVE/REAL account ({account_trade_mode})."
                )
                self._record_trigger("SAFETY_MODE", msg, RiskAction.CLOSE_ALL_AND_HALT)
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(
                    allowed=False,
                    reason=msg,
                    category="SAFETY_MODE",
                    action=RiskAction.CLOSE_ALL_AND_HALT,
                )
            self._clear_trigger("SAFETY_MODE")
            return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)
        else:
            if not (self.config.general.allow_real_trading and self.config.safety_mode.allow_real_trading):
                msg = "LIVE TRADING BLOCKED: DEMO_MODE is false but 'allow_real_trading' is not explicitly enabled."
                self._record_trigger("SAFETY_MODE", msg, RiskAction.CLOSE_ALL_AND_HALT)
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(
                    allowed=False,
                    reason=msg,
                    category="SAFETY_MODE",
                    action=RiskAction.CLOSE_ALL_AND_HALT,
                )
            self._clear_trigger("SAFETY_MODE")
            return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_broker_connection(
        self,
        is_connected: bool = True,
        last_heartbeat_ts: Optional[float] = None,
        now_override: Optional[float] = None,
    ) -> RiskCheckVerdict:
        now_ts = now_override if now_override is not None else time.time()
        self.broker_connected = is_connected
        if not is_connected:
            msg = "Broker terminal disconnected: blocking new entries and preserving broker-side SL protection."
            self._record_trigger("BROKER_DISCONNECT", msg, RiskAction.MANAGE_EXISTING_POSITIONS)
            return RiskCheckVerdict(
                allowed=False,
                reason=msg,
                category="BROKER_DISCONNECT",
                action=RiskAction.MANAGE_EXISTING_POSITIONS,
            )

        if last_heartbeat_ts is not None:
            age = now_ts - last_heartbeat_ts
            timeout = self.config.risk.broker_disconnect_timeout_sec
            if timeout > 0 and age > timeout:
                msg = f"Broker heartbeat stale ({age:.1f}s > {timeout:.1f}s limit)"
                self._record_trigger("BROKER_DISCONNECT", msg, RiskAction.MANAGE_EXISTING_POSITIONS)
                return RiskCheckVerdict(
                    allowed=False,
                    reason=msg,
                    category="BROKER_DISCONNECT",
                    action=RiskAction.MANAGE_EXISTING_POSITIONS,
                )

        self._clear_trigger("BROKER_DISCONNECT")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_spread(self, symbol_key: str, current_spread_points: float) -> RiskCheckVerdict:
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        if sym_k == "GOLD" and self.config.spread_protection.spread_max_points != 80.0:
            max_allowed = self.config.spread_protection.spread_max_points
        else:
            max_allowed = sym_cfg.spread_max_points if sym_cfg else self.config.spread_protection.spread_max_points
        if current_spread_points > max_allowed:
            msg = (
                f"Spread protection triggered for {sym_k}: "
                f"Current spread {current_spread_points:.1f} pts > Max allowed {max_allowed:.1f} pts"
            )
            self._record_trigger("SPREAD", msg, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(allowed=False, reason=msg, category="SPREAD", action=RiskAction.BLOCK_NEW_ENTRIES)
        self._clear_trigger("SPREAD")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_slippage(self, symbol_key: str, slippage_points: float) -> RiskCheckVerdict:
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        max_slip = sym_cfg.max_slippage if sym_cfg else float(self.config.execution.slippage_points)
        if slippage_points > max_slip:
            msg = (
                f"Slippage protection triggered for {sym_k}: "
                f"Slippage {slippage_points:.1f} pts > Max allowed {max_slip:.1f} pts"
            )
            self._record_trigger("SLIPPAGE", msg, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(allowed=False, reason=msg, category="SLIPPAGE", action=RiskAction.BLOCK_NEW_ENTRIES)
        self._clear_trigger("SLIPPAGE")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def record_trade_outcome(self, pnl_usd: float, now_override: Optional[float] = None) -> None:
        now_ts = now_override if now_override is not None else time.time()
        self.realized_daily_pnl_usd = round(self.realized_daily_pnl_usd + pnl_usd, 4)
        if pnl_usd < 0:
            self.consecutive_losses += 1
            max_losses = self.config.risk.max_consecutive_losses
            if max_losses > 0 and self.consecutive_losses >= max_losses:
                cooldown = self.config.risk.loss_streak_cooldown_seconds
                self.loss_streak_pause_until = max(self.loss_streak_pause_until, now_ts + cooldown)
                self.pause_until_timestamp = max(self.pause_until_timestamp, self.loss_streak_pause_until)
                self.active_pause_category = "LOSS_STREAK_COOLDOWN"
                reason = f"Consecutive loss limit reached ({self.consecutive_losses} >= {max_losses}): cooldown for {cooldown}s"
                self.active_pause_reason = reason
                self._record_trigger("LOSS_STREAK_COOLDOWN", reason, RiskAction.PAUSE_NEW_ENTRIES)
        elif pnl_usd > 0:
            self.consecutive_losses = 0
            self.loss_streak_pause_until = 0.0
            if self.active_pause_category == "LOSS_STREAK_COOLDOWN":
                self.active_pause_category = ""
                self.active_pause_reason = ""
            self._clear_trigger("LOSS_STREAK_COOLDOWN")

    def check_consecutive_losses(self, now_override: Optional[float] = None) -> RiskCheckVerdict:
        now_ts = now_override if now_override is not None else time.time()
        max_losses = self.config.risk.max_consecutive_losses
        if max_losses > 0 and self.consecutive_losses >= max_losses and now_ts < self.loss_streak_pause_until:
            rem = int(self.loss_streak_pause_until - now_ts)
            reason = f"Loss-streak cooldown active ({self.consecutive_losses} consecutive losses, {rem}s remaining)"
            self._record_trigger("LOSS_STREAK_COOLDOWN", reason, RiskAction.PAUSE_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="LOSS_STREAK_COOLDOWN",
                action=RiskAction.PAUSE_NEW_ENTRIES,
            )
        self._clear_trigger("LOSS_STREAK_COOLDOWN")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_daily_loss(
        self,
        day_start_balance: float,
        realized_daily_pnl_usd: Optional[float] = None,
        floating_pnl_usd: float = 0.0,
        now_override: Optional[float] = None,
    ) -> RiskCheckVerdict:
        now_ts = now_override if now_override is not None else time.time()
        daily_en = bool(
            self.config.risk.daily_loss_enabled
            or self.config.risk.max_daily_loss_enabled
            or self.config.daily_limits.max_daily_loss_enabled
        )
        if not daily_en:
            return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

        if (
            getattr(self, "daily_starting_balance", 0.0) > 0
            and realized_daily_pnl_usd is not None
            and realized_daily_pnl_usd > 0
            and self.realized_daily_pnl_usd < 0
        ):
            # Caller passed (current_balance, current_equity) after reset_daily_baseline()
            day_start_balance = float(self.daily_starting_balance)
            realized = self.realized_daily_pnl_usd
        else:
            realized = realized_daily_pnl_usd if realized_daily_pnl_usd is not None else self.realized_daily_pnl_usd
        net_daily_pnl = realized + (floating_pnl_usd if self.config.risk.accounting_includes_floating else 0.0)
        if net_daily_pnl >= 0:
            self._daily_loss_close_dispatched = False
            self._clear_trigger("DAILY_LOSS")
            return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

        daily_loss_abs = abs(net_daily_pnl)
        max_usd = (
            self.config.daily_limits.max_daily_loss_usd
            if self.config.daily_limits.max_daily_loss_usd != 50.0
            else self.config.risk.max_daily_loss_usd
        )
        max_pct = self.config.risk.max_daily_loss_pct
        pct_limit_usd = (day_start_balance * (max_pct / 100.0)) if day_start_balance > 0 and max_pct > 0 else float("inf")
        effective_limit_usd = min(max_usd if max_usd > 0 else float("inf"), pct_limit_usd)

        if daily_loss_abs >= effective_limit_usd:
            reason = f"Max daily loss breached: -${daily_loss_abs:.2f} exceeds limit -${effective_limit_usd:.2f}"
            pause_secs = self.config.risk.pause_minutes * 60
            self.daily_loss_pause_until = max(self.daily_loss_pause_until, now_ts + pause_secs)
            self.pause_until_timestamp = max(self.pause_until_timestamp, self.daily_loss_pause_until)
            self.active_pause_category = "DAILY_LOSS"
            self.active_pause_reason = reason
            policy = getattr(self.config.risk, "daily_loss_action", RiskAction.CLOSE_ALL_AND_PAUSE)
            if not self._daily_loss_close_dispatched:
                self._daily_loss_close_dispatched = True
                action = policy
            else:
                action = RiskAction.PAUSE_NEW_ENTRIES
            self._record_trigger("DAILY_LOSS", reason, policy)
            return RiskCheckVerdict(allowed=False, reason=reason, category="DAILY_LOSS", action=action)

        self._clear_trigger("DAILY_LOSS")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_open_risk(
        self,
        account_equity: float,
        current_open_risk_usd: float,
        proposed_additional_risk_usd: float = 0.0,
    ) -> RiskCheckVerdict:
        if account_equity <= 0:
            return RiskCheckVerdict(
                allowed=False,
                reason="Invalid account equity",
                category="OPEN_RISK",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )
        max_pct = self.config.risk.max_open_risk_pct
        max_risk_usd = account_equity * (max_pct / 100.0)
        projected = current_open_risk_usd + max(0.0, proposed_additional_risk_usd)
        if projected > max_risk_usd + 1e-6:
            reason = f"Account-wide open risk cap exceeded: Projected ${projected:.2f} > Max ${max_risk_usd:.2f} ({max_pct:.2f}%)"
            self._record_trigger("OPEN_RISK", reason, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="OPEN_RISK",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )
        self._clear_trigger("OPEN_RISK")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_drawdown(self, balance: float, equity: float, now_override: Optional[float] = None) -> RiskCheckVerdict:
        now_ts = now_override if now_override is not None else time.time()

        if balance <= 0:
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Invalid balance: ${balance:.2f}",
                category="DRAWDOWN",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )

        max_dd = (
            self.config.equity_protection.max_dd_pct
            if self.config.equity_protection.max_dd_pct != 30.0
            else self.config.risk.max_dd_pct
        )
        pause_mins = (
            self.config.equity_protection.pause_minutes
            if self.config.equity_protection.pause_minutes != 60
            else self.config.risk.pause_minutes
        )

        if equity < balance:
            dd_pct = ((balance - equity) / balance) * 100.0
            if dd_pct >= max_dd:
                self.circuit_breaker_active = True
                self.circuit_breaker_reason = f"Max drawdown breached: {dd_pct:.2f}% >= {max_dd:.1f}% limit"
                pause_secs = pause_mins * 60
                self.drawdown_pause_until = max(self.drawdown_pause_until, now_ts + pause_secs)
                self.pause_until_timestamp = max(self.pause_until_timestamp, self.drawdown_pause_until)
                self.active_pause_category = "DRAWDOWN"
                self.active_pause_reason = self.circuit_breaker_reason
                policy = getattr(self.config.risk, "drawdown_action", RiskAction.LIQUIDATE_ALL_AND_PAUSE)
                if not self._drawdown_liquidation_dispatched:
                    self._drawdown_liquidation_dispatched = True
                    action = policy
                    logger.critical(
                        f"[CIRCUIT_BREAKER] {self.circuit_breaker_reason}. Activating {pause_mins}m pause across all instruments."
                    )
                else:
                    action = RiskAction.PAUSE_NEW_ENTRIES
                self._record_trigger("DRAWDOWN", self.circuit_breaker_reason, policy)
                return RiskCheckVerdict(
                    allowed=False,
                    reason=self.circuit_breaker_reason,
                    category="DRAWDOWN",
                    action=action,
                )

        # If a genuine drawdown pause is still cooling down (even after equity recovered post-close),
        # block new entries with PAUSE_NEW_ENTRIES rather than re-liquidating.
        if now_ts < self.drawdown_pause_until:
            rem = int(self.drawdown_pause_until - now_ts)
            reason = f"Drawdown circuit-breaker cooldown active ({rem}s remaining)"
            self._record_trigger("DRAWDOWN", reason, RiskAction.PAUSE_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="DRAWDOWN",
                action=RiskAction.PAUSE_NEW_ENTRIES,
            )

        self._drawdown_liquidation_dispatched = False
        self._clear_trigger("DRAWDOWN")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def check_margin_and_capacity(
        self,
        account_balance: float,
        account_equity: float,
        account_margin: float,
        account_free_margin: float,
        current_open_positions: int,
        current_total_lots: float,
        proposed_lot: float,
        margin_per_lot: float = 20.0,
    ) -> RiskCheckVerdict:
        max_pos = (
            self.config.position_limits.max_open_positions
            if self.config.position_limits.max_open_positions != 12
            else self.config.risk.max_open_positions
        )
        if current_open_positions + 1 > max_pos:
            reason = f"Account position limit reached: Current {current_open_positions} + 1 > Max {max_pos}"
            self._record_trigger("POSITION_LIMIT", reason, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="POSITION_LIMIT",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )
        self._clear_trigger("POSITION_LIMIT")

        max_lots = (
            self.config.volume_limits.max_total_lots
            if self.config.volume_limits.max_total_lots != 1.00
            else self.config.risk.max_total_lots
        )
        projected_lots = round(current_total_lots + proposed_lot, 4)
        if projected_lots > max_lots + 1e-6:
            reason = f"Account volume limit reached: Projected lots {projected_lots:.2f} > Max {max_lots:.2f}"
            self._record_trigger("VOLUME_LIMIT", reason, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="VOLUME_LIMIT",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )
        self._clear_trigger("VOLUME_LIMIT")

        projected_new_margin = proposed_lot * margin_per_lot
        if projected_new_margin > account_free_margin:
            reason = f"Insufficient free margin: Required ${projected_new_margin:.2f} > Free ${account_free_margin:.2f}"
            self._record_trigger("MARGIN", reason, RiskAction.BLOCK_NEW_ENTRIES)
            return RiskCheckVerdict(
                allowed=False,
                reason=reason,
                category="MARGIN",
                action=RiskAction.BLOCK_NEW_ENTRIES,
            )

        total_projected_margin = account_margin + projected_new_margin
        if account_equity > 0 and total_projected_margin > 0:
            margin_util_pct = (total_projected_margin / account_equity) * 100.0
            max_util_pct = (
                self.config.margin_protection.max_margin_usage_pct
                if self.config.margin_protection.max_margin_usage_pct != 50.0
                else self.config.risk.max_margin_usage_pct
            )
            if max_util_pct > 0 and margin_util_pct > max_util_pct:
                reason = f"Margin utilization {margin_util_pct:.1f}% > Maximum allowed {max_util_pct:.1f}%"
                self._record_trigger("MARGIN", reason, RiskAction.BLOCK_NEW_ENTRIES)
                return RiskCheckVerdict(
                    allowed=False,
                    reason=reason,
                    category="MARGIN",
                    action=RiskAction.BLOCK_NEW_ENTRIES,
                )

        min_margin_lvl = (
            self.config.margin_protection.min_margin_level_pct
            if self.config.margin_protection.min_margin_level_pct != 300.0
            else self.config.risk.min_margin_level_pct
        )
        if total_projected_margin > 0:
            projected_margin_lvl = (account_equity / total_projected_margin) * 100.0
            if projected_margin_lvl < min_margin_lvl:
                reason = f"Projected margin level {projected_margin_lvl:.1f}% < Minimum required {min_margin_lvl:.1f}%"
                self._record_trigger("MARGIN", reason, RiskAction.BLOCK_NEW_ENTRIES)
                return RiskCheckVerdict(
                    allowed=False,
                    reason=reason,
                    category="MARGIN",
                    action=RiskAction.BLOCK_NEW_ENTRIES,
                )

        self._clear_trigger("MARGIN")
        return RiskCheckVerdict(allowed=True, category="PASS", action=RiskAction.PASS)

    def calculate_protective_sl(
        self,
        symbol_key: str,
        direction: str,
        entry_price: float,
        point: float,
    ) -> float:
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        pts = sym_cfg.sl_points if sym_cfg else 300.0
        pt_val = point if point > 0 else 0.01
        sl_distance = pts * pt_val
        if direction.upper() in ("BUY", "ORDER_TYPE_BUY", "0"):
            return round(entry_price - sl_distance, 3)
        else:
            return round(entry_price + sl_distance, 3)


# Backward-compatible Gold risk manager alias
class GoldRiskManager(AccountRiskManager):
    def check_spread(self, current_spread_points: float, symbol_key: str = "GOLD") -> RiskCheckVerdict:
        return super().check_spread(symbol_key, current_spread_points)

    def calculate_protective_sl(self, direction: str, entry_price: float, point: float, symbol_key: str = "GOLD") -> float:
        return super().calculate_protective_sl(symbol_key, direction, entry_price, point)
