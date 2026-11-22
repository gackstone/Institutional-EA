"""
Mandatory Multi-Symbol Safety and Account Protection Framework.
Enforces global account safety constraints across both GOLD and BTCUSD:
1. Hard account-wide position limit (MAX_OPEN_POSITIONS = 12 across all symbols)
2. Aggregate volume ceiling (MAX_TOTAL_LOTS = 1.00)
3. Minimum margin level (MIN_MARGIN_LEVEL = 300% & projected margin verification)
4. Multi-symbol equity drawdown stop (MAX_DD_PCT = 30%, closes positions across both symbols, pauses engine)
5. Symbol-specific spread protection (GOLD: 80 pts, BTCUSD: 3000 pts)
6. Symbol-specific protective stop-loss (GOLD: 300 pts, BTCUSD: 5000 pts)
7. Emergency kill switch (STOP.flag file, CLI, Telegram)
8. DEMO_MODE enforcement (default true, fails closed on real accounts)
"""

from __future__ import annotations
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import ScalperConfig, InstrumentScalperConfig

logger = logging.getLogger("AccountRiskManager")


@dataclass
class RiskCheckVerdict:
    allowed: bool
    reason: str = ""
    category: str = "PASS"


class AccountRiskManager:
    def __init__(self, config: ScalperConfig):
        self.config = config
        self.manual_kill_triggered: bool = False
        self.pause_until_timestamp: float = 0.0
        self.circuit_breaker_active: bool = False
        self.circuit_breaker_reason: str = ""

    @property
    def is_paused(self) -> bool:
        return time.time() < self.pause_until_timestamp

    def trigger_manual_kill(self, reason: str = "Operator invoked kill switch") -> None:
        self.manual_kill_triggered = True
        logger.critical(f"[KILL_SWITCH] Emergency kill switch manually activated: {reason}")

    def check_kill_switch(self) -> RiskCheckVerdict:
        """Verifies if STOP.flag or manual kill signal is active."""
        if self.manual_kill_triggered:
            return RiskCheckVerdict(
                allowed=False,
                reason="Emergency kill switch triggered by operator command",
                category="KILL_SWITCH",
            )

        flag_path = Path(self.config.kill_switch.flag_file_path)
        if flag_path.exists():
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Emergency kill switch flag file detected at '{flag_path.resolve()}'",
                category="KILL_SWITCH",
            )

        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_demo_live_mode(self, account_trade_mode: str) -> RiskCheckVerdict:
        """
        Validates account environment:
        - If DEMO_MODE=true, connected account must be DEMO.
        - Real/Live accounts are strictly blocked unless DEMO_MODE=false AND allow_real_trading=true.
        """
        is_demo_account = str(account_trade_mode).upper() in ("DEMO", "0")
        demo_configured = self.config.general.DEMO_MODE

        if demo_configured:
            if not is_demo_account:
                msg = f"LIVE ACCOUNT REJECTED: System configured in DEMO_MODE=true, but connected to LIVE/REAL account ({account_trade_mode})."
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(allowed=False, reason=msg, category="SAFETY_MODE")
            return RiskCheckVerdict(allowed=True, category="PASS")
        else:
            if not self.config.general.allow_real_trading:
                msg = "LIVE TRADING BLOCKED: DEMO_MODE is false but 'allow_real_trading' is not explicitly enabled in config/scalper.yaml."
                logger.critical(f"[SAFETY_MODE] {msg}")
                return RiskCheckVerdict(allowed=False, reason=msg, category="SAFETY_MODE")
            logger.warning("[SAFETY_MODE] CAUTION: Operating on LIVE account with DEMO_MODE=false.")
            return RiskCheckVerdict(allowed=True, category="PASS")

    def check_spread(self, symbol_key: str, current_spread_points: float) -> RiskCheckVerdict:
        """Verifies market spread does not exceed instrument-specific threshold."""
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        max_allowed = sym_cfg.spread_max_points if sym_cfg else 80.0
        if current_spread_points > max_allowed:
            msg = f"Spread protection triggered for {sym_k}: Current spread {current_spread_points:.1f} pts > Max allowed {max_allowed:.1f} pts"
            logger.warning(f"[SPREAD_PROTECTION] {msg}")
            return RiskCheckVerdict(allowed=False, reason=msg, category="SPREAD")
        return RiskCheckVerdict(allowed=True, category="PASS")

    def check_drawdown(self, balance: float, equity: float) -> RiskCheckVerdict:
        """
        Evaluates account-wide equity drawdown against balance across both instruments.
        If DD % >= MAX_DD_PCT: activates pause and requests emergency liquidation.
        """
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
        """
        Enforces:
        - Maximum open positions ceiling across account (default 12)
        - Maximum total lots ceiling across account (default 1.00)
        - Minimum margin level (300%) & projected margin verification
        - Free margin sufficiency
        """
        # 1. Total position count limit across all symbols
        max_pos = self.config.risk.max_open_positions
        if current_open_positions + 1 > max_pos:
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Account position limit reached: Current {current_open_positions} + 1 > Max {max_pos}",
                category="POSITION_LIMIT",
            )

        # 2. Total lot volume limit across all symbols
        max_lots = self.config.risk.max_total_lots
        projected_lots = round(current_total_lots + proposed_lot, 4)
        if projected_lots > max_lots + 1e-6:
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Account volume limit reached: Projected lots {projected_lots:.2f} > Max {max_lots:.2f}",
                category="VOLUME_LIMIT",
            )

        # 3. Projected Margin & Margin Level
        projected_new_margin = proposed_lot * margin_per_lot
        if projected_new_margin > account_free_margin:
            return RiskCheckVerdict(
                allowed=False,
                reason=f"Insufficient free margin: Required ${projected_new_margin:.2f} > Free ${account_free_margin:.2f}",
                category="MARGIN",
            )

        total_projected_margin = account_margin + projected_new_margin
        min_margin_lvl = self.config.risk.min_margin_level_pct
        if total_projected_margin > 0:
            projected_margin_lvl = (account_equity / total_projected_margin) * 100.0
            if projected_margin_lvl < min_margin_lvl:
                return RiskCheckVerdict(
                    allowed=False,
                    reason=f"Projected margin level {projected_margin_lvl:.1f}% < Minimum required {min_margin_lvl:.1f}%",
                    category="MARGIN",
                )

        return RiskCheckVerdict(allowed=True, category="PASS")

    def calculate_protective_sl(
        self,
        symbol_key: str,
        direction: str,
        entry_price: float,
        point: float,
    ) -> float:
        """Calculates exact protective stop loss price using symbol-specific sl_points."""
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
