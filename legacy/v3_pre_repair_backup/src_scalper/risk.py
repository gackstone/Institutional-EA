"""
Phase 9: Shared Account Equity & Risk Protection Controller Across GOLD and BTCUSD.
Enforces:
1. Maximum account-wide open risk (max_open_risk_pct)
2. Maximum daily realized and floating loss (max_daily_loss_pct / max_daily_loss_usd)
3. Maximum equity drawdown (max_dd_pct)
4. Maximum open positions (max_open_positions = 12)
5. Maximum aggregate volume (max_total_lots = 1.00)
6. Maximum margin utilization (max_margin_utilization_pct = 50%) & Minimum margin level (300%)
7. Maximum spread (instrument-calibrated)
8. Maximum slippage (instrument-calibrated)
9. Maximum consecutive losses & loss-streak cooldown
10. Emergency kill switch (STOP.flag, CLI, Telegram)
11. Broker disconnection protection
12. DEMO_MODE enforcement (default true, fails closed on real accounts)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from src.scalper.config import ScalperConfig

logger = logging.getLogger("AccountRiskManager")


@dataclass
class RiskCheckVerdict:
    allowed: bool
    reason: str = ""
    category: str = "PASS"


@dataclass
class RiskTriggerEvent:
    category: str
    reason: str
    emergency_policy: str
    timestamp: float = field(default_factory=time.time)


class AccountRiskManager:
    def __init__(self, config: ScalperConfig):
        self.config = config
        self.manual_kill_triggered: bool = False
        self.pause_until_timestamp: float = 0.0
        self.circuit_breaker_active: bool = False
        self.circuit_breaker_reason: str = ""
        self.consecutive_losses: int = 0
        self.realized_daily_pnl_usd: float = 0.0
        self.broker_connected: bool = True
        self.last_broker_heartbeat: float = field(default_factory=time.time) if False else time.time()
        self.trigger_events: List[RiskTriggerEvent] = []

    @property
    def is_paused(self) -> bool:
        return time.time() < self.pause_until_timestamp

    def _record_trigger(self, category: str, reason: str, policy: str = "BLOCK_NEW_ENTRIES") -> None:
        self.trigger_events.append(
            RiskTriggerEvent(category=category, reason=reason, emergency_policy=policy)
        )

    def trigger_manual_kill(self, reason: str = "Operator invoked kill switch") -> None:
        self.manual_kill_triggered = True
        self._record_trigger("KILL_SWITCH", reason, "CLOSE_ALL_AND_HALT")
        logger.critical(f"[KILL_SWITCH] Emergency kill switch manually activated: {reason}")

    def check_kill_switch(self) -> RiskCheckVerdict:
        if self.manual_kill_triggered:
            return RiskCheckVerdict(
                allowed=False,
                reason="Emergency kill switch triggered by operator command",
                category="KILL_SWITCH",
            )

        flag_path = Path(self.config.kill_switch.flag_file_path)
        if flag_path.exists():
            reason = f"Emergency kill switch flag file detected at '{flag_path.resolve()}'"
            self._record_trigger("KILL_SWITCH", reason, "CLOSE_ALL_AND_HALT")
            return RiskCheckVerdict(allowed=False, reason=reason, category="KILL_SWITCH")

        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_demo_live_mode(self, account_trade_mode: str) -> RiskCheckVerdict:
        is_demo_account = str(account_trade_mode).upper() in ("DEMO", "0")
        demo_configured = self.config.general.DEMO_MODE

        if demo_configured:
            if not is_demo_account:
                msg = f"LIVE ACCOUNT REJECTED: System configured in DEMO_MODE=true, but connected to LIVE/REAL account ({account_trade_mode})."
                self._record_trigger("SAFETY_MODE", msg, "HALT")
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(allowed=False, reason=msg, category="SAFETY_MODE")
            return RiskCheckVerdict(allowed=True, category="PASS")
        else:
            if not self.config.general.allow_real_trading:
                msg = "LIVE TRADING BLOCKED: DEMO_MODE is false but 'allow_real_trading' is not explicitly enabled in config/scalper.yaml."
                self._record_trigger("SAFETY_MODE", msg, "HALT")
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(allowed=False, reason=msg, category="SAFETY_MODE")
            return RiskCheckVerdict(allowed=True, category="PASS")

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
            self._record_trigger("BROKER_DISCONNECT", msg, "HOLD_WITH_BROKER_SL")
            return RiskCheckVerdict(allowed=False, reason=msg, category="BROKER_DISCONNECT")

        if last_heartbeat_ts is not None:
            age = now_ts - last_heartbeat_ts
            timeout = self.config.risk.broker_disconnect_timeout_sec
            if timeout > 0 and age > timeout:
                msg = f"Broker heartbeat stale ({age:.1f}s > {timeout:.1f}s limit)"
                self._record_trigger("BROKER_DISCONNECT", msg, "HOLD_WITH_BROKER_SL")
                return RiskCheckVerdict(allowed=False, reason=msg, category="BROKER_DISCONNECT")

        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_spread(self, symbol_key: str, current_spread_points: float) -> RiskCheckVerdict:
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        max_allowed = sym_cfg.spread_max_points if sym_cfg else 80.0
        if current_spread_points > max_allowed:
            msg = f"Spread protection triggered for {sym_k}: Current spread {current_spread_points:.1f} pts > Max allowed {max_allowed:.1f} pts"
            self._record_trigger("SPREAD", msg, "SKIP_ENTRY")
            return RiskCheckVerdict(allowed=False, reason=msg, category="SPREAD")
        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_slippage(self, symbol_key: str, slippage_points: float) -> RiskCheckVerdict:
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        max_slip = sym_cfg.max_slippage if sym_cfg else float(self.config.execution.slippage_points)
        if slippage_points > max_slip:
            msg = f"Slippage protection triggered for {sym_k}: Slippage {slippage_points:.1f} pts > Max allowed {max_slip:.1f} pts"
            self._record_trigger("SLIPPAGE", msg, "SKIP_ENTRY")
            return RiskCheckVerdict(allowed=False, reason=msg, category="SLIPPAGE")
        return RiskCheckVerdict(allowed=True, category="PASS")

    def record_trade_outcome(self, pnl_usd: float, now_override: Optional[float] = None) -> None:
        now_ts = now_override if now_override is not None else time.time()
        self.realized_daily_pnl_usd = round(self.realized_daily_pnl_usd + pnl_usd, 4)
        if pnl_usd < 0:
            self.consecutive_losses += 1
            max_losses = self.config.risk.max_consecutive_losses
            if max_losses > 0 and self.consecutive_losses >= max_losses:
                cooldown = self.config.risk.loss_streak_cooldown_seconds
                self.pause_until_timestamp = max(self.pause_until_timestamp, now_ts + cooldown)
                reason = f"Consecutive loss limit reached ({self.consecutive_losses} >= {max_losses}): cooldown for {cooldown}s"
                self._record_trigger("LOSS_STREAK_COOLDOWN", reason, "PAUSE_NEW_ENTRIES")
        elif pnl_usd > 0:
            self.consecutive_losses = 0

    def check_consecutive_losses(self, now_override: Optional[float] = None) -> RiskCheckVerdict:
        now_ts = now_override if now_override is not None else time.time()
        max_losses = self.config.risk.max_consecutive_losses
        if max_losses > 0 and self.consecutive_losses >= max_losses and now_ts < self.pause_until_timestamp:
            rem = int(self.pause_until_timestamp - now_ts)
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Loss-streak cooldown active ({self.consecutive_losses} consecutive losses, {rem}s remaining)",
                category="LOSS_STREAK_COOLDOWN",
            )
        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_daily_loss(
        self,
        day_start_balance: float,
        realized_daily_pnl_usd: Optional[float] = None,
        floating_pnl_usd: float = 0.0,
    ) -> RiskCheckVerdict:
        if not (self.config.risk.daily_loss_enabled or self.config.risk.max_daily_loss_enabled):
            return RiskCheckVerdict(allowed=True, category="PASS")

        realized = realized_daily_pnl_usd if realized_daily_pnl_usd is not None else self.realized_daily_pnl_usd
        net_daily_pnl = realized + (floating_pnl_usd if self.config.risk.accounting_includes_floating else 0.0)
        if net_daily_pnl >= 0:
            return RiskCheckVerdict(allowed=True, category="PASS")

        daily_loss_abs = abs(net_daily_pnl)
        max_usd = self.config.risk.max_daily_loss_usd
        max_pct = self.config.risk.max_daily_loss_pct
        pct_limit_usd = (day_start_balance * (max_pct / 100.0)) if day_start_balance > 0 and max_pct > 0 else float("inf")
        effective_limit_usd = min(max_usd if max_usd > 0 else float("inf"), pct_limit_usd)

        if daily_loss_abs >= effective_limit_usd:
            reason = f"Max daily loss breached: -${daily_loss_abs:.2f} exceeds limit -${effective_limit_usd:.2f}"
            self._record_trigger("DAILY_LOSS", reason, "CLOSE_ALL_AND_PAUSE")
            return RiskCheckVerdict(allowed=False, reason=reason, category="DAILY_LOSS")

        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_open_risk(
        self,
        account_equity: float,
        current_open_risk_usd: float,
        proposed_additional_risk_usd: float = 0.0,
    ) -> RiskCheckVerdict:
        if account_equity <= 0:
            return RiskCheckVerdict(allowed=False, reason="Invalid account equity", category="OPEN_RISK")
        max_pct = self.config.risk.max_open_risk_pct
        max_risk_usd = account_equity * (max_pct / 100.0)
        projected = current_open_risk_usd + max(0.0, proposed_additional_risk_usd)
        if projected > max_risk_usd + 1e-6:
            reason = f"Account-wide open risk cap exceeded: Projected ${projected:.2f} > Max ${max_risk_usd:.2f} ({max_pct:.2f}%)"
            self._record_trigger("OPEN_RISK", reason, "BLOCK_NEW_ENTRIES")
            return RiskCheckVerdict(allowed=False, reason=reason, category="OPEN_RISK")
        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_drawdown(self, balance: float, equity: float) -> RiskCheckVerdict:
        if self.is_paused:
            remaining_sec = int(self.pause_until_timestamp - time.time())
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Trading suspended due to active risk pause ({remaining_sec}s remaining)",
                category="DRAWDOWN",
            )

        if balance <= 0:
            return RiskCheckVerdict(allowed=False, reason=f"Invalid balance: ${balance:.2f}", category="DRAWDOWN")

        if equity < balance:
            dd_pct = ((balance - equity) / balance) * 100.0
            max_dd = self.config.risk.max_dd_pct
            if dd_pct >= max_dd:
                self.circuit_breaker_active = True
                self.circuit_breaker_reason = f"Max drawdown breached: {dd_pct:.2f}% >= {max_dd:.1f}% limit"
                pause_secs = self.config.risk.pause_minutes * 60
                self.pause_until_timestamp = time.time() + pause_secs
                self._record_trigger("DRAWDOWN", self.circuit_breaker_reason, "LIQUIDATE_ALL_AND_PAUSE")
                logger.critical(
                    f"[CIRCUIT_BREAKER] {self.circuit_breaker_reason}. Activating {self.config.risk.pause_minutes}m pause across all instruments."
                )
                return RiskCheckVerdict(allowed=False, reason=self.circuit_breaker_reason, category="DRAWDOWN")

        return RiskCheckVerdict(allowed=True, category="PASS")

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
        max_pos = self.config.risk.max_open_positions
        if current_open_positions + 1 > max_pos:
            reason = f"Account position limit reached: Current {current_open_positions} + 1 > Max {max_pos}"
            self._record_trigger("POSITION_LIMIT", reason, "BLOCK_NEW_ENTRIES")
            return RiskCheckVerdict(allowed=False, reason=reason, category="POSITION_LIMIT")

        max_lots = self.config.risk.max_total_lots
        projected_lots = round(current_total_lots + proposed_lot, 4)
        if projected_lots > max_lots + 1e-6:
            reason = f"Account volume limit reached: Projected lots {projected_lots:.2f} > Max {max_lots:.2f}"
            self._record_trigger("VOLUME_LIMIT", reason, "BLOCK_NEW_ENTRIES")
            return RiskCheckVerdict(allowed=False, reason=reason, category="VOLUME_LIMIT")

        projected_new_margin = proposed_lot * margin_per_lot
        if projected_new_margin > account_free_margin:
            reason = f"Insufficient free margin: Required ${projected_new_margin:.2f} > Free ${account_free_margin:.2f}"
            self._record_trigger("MARGIN", reason, "BLOCK_NEW_ENTRIES")
            return RiskCheckVerdict(allowed=False, reason=reason, category="MARGIN")

        total_projected_margin = account_margin + projected_new_margin
        if account_equity > 0 and total_projected_margin > 0:
            margin_util_pct = (total_projected_margin / account_equity) * 100.0
            max_util_pct = self.config.risk.max_margin_usage_pct
            if max_util_pct > 0 and margin_util_pct > max_util_pct:
                reason = f"Margin utilization {margin_util_pct:.1f}% > Maximum allowed {max_util_pct:.1f}%"
                self._record_trigger("MARGIN", reason, "BLOCK_NEW_ENTRIES")
                return RiskCheckVerdict(allowed=False, reason=reason, category="MARGIN")

        min_margin_lvl = self.config.risk.min_margin_level_pct
        if total_projected_margin > 0:
            projected_margin_lvl = (account_equity / total_projected_margin) * 100.0
            if projected_margin_lvl < min_margin_lvl:
                reason = f"Projected margin level {projected_margin_lvl:.1f}% < Minimum required {min_margin_lvl:.1f}%"
                self._record_trigger("MARGIN", reason, "BLOCK_NEW_ENTRIES")
                return RiskCheckVerdict(allowed=False, reason=reason, category="MARGIN")

        return RiskCheckVerdict(allowed=True, category="PASS")

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
