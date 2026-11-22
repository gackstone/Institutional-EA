"""
Manual Position Management Safety Policy Engine.
Enforces non-negotiable safety rules:
- Emergency PAUSE gate (state/PAUSE)
- Real account protection (allow_real_account_management)
- Netting account isolation (forced OBSERVE)
- User override lockout enforcement
- Tighten-only stop loss validation (R9.3)
- Strictly no averaging down / no pyramids on losing positions
Tags: [SAFETY], [ART-12], [DERIVED]
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from src.core.contracts import AccountInfo, OrderType, Position, SymbolInfo
from src.manual_mgmt.contracts import (
    AdoptionAssessment,
    ManualMgmtConfig,
    ManualPositionRecord,
    ManagementMode,
    PositionClass
)

logger = logging.getLogger("ManualMgmtPolicy")


class ManualMgmtPolicy:
    def __init__(self, config: ManualMgmtConfig, pause_file: str = "state/PAUSE"):
        self.config = config
        self.pause_file = pause_file

    def is_paused(self) -> bool:
        """Checks if emergency pause flag or file is active [SAFETY]."""
        return self.config.pause_all or os.path.exists(self.pause_file)

    def is_real_account(self, account_info: AccountInfo) -> bool:
        """Determines if the connected MT5 account is a REAL trading account."""
        mode_str = str(getattr(account_info, "trade_mode", "DEMO")).upper()
        prof_str = str(getattr(account_info, "profile", "DEMO")).upper()
        return mode_str in ("REAL", "LIVE", "2") or prof_str in ("REAL", "LIVE")

    def is_netting_account(self, account_info: AccountInfo) -> bool:
        """Determines if the account operates in Netting mode."""
        margin_mode = getattr(account_info, "margin_mode", 0)
        mode_str = str(getattr(account_info, "margin_mode_str", "HEDGING")).upper()
        return margin_mode == 1 or mode_str == "NETTING"

    def validate_action(
        self,
        assessment: AdoptionAssessment,
        record: ManualPositionRecord,
        pos: Position,
        account_info: AccountInfo,
        symbol_info: Optional[SymbolInfo] = None,
        now: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Validates whether an action proposed by the assessor is permitted to execute.
        Returns (is_allowed, reason).
        """
        action = assessment.action
        current_time = now or datetime.now(timezone.utc)

        # 0. NONE action requires no validation
        if action == "NONE":
            return False, "No action requested."

        # 1. Emergency Pause Guard [SAFETY]
        if self.is_paused():
            return False, f"Blocked by emergency pause (pause_file={self.pause_file} or config.pause_all=True) [SAFETY]."

        # 2. Real Account Barrier [SAFETY]
        if self.is_real_account(account_info) and not self.config.allow_real_account_management:
            return False, "Blocked: REAL account detected and allow_real_account_management is False. Forced OBSERVE [SAFETY]."

        # 3. Netting Account Barrier [SAFETY]
        if self.is_netting_account(account_info):
            return False, "Blocked: Netting account detected (margin_mode=1). Forced OBSERVE to prevent position blending [SAFETY]."

        # 4. User Override Lockout Guard [SAFETY]
        if record.is_locked_out(current_time):
            return False, f"Blocked: User manual override active. Bot locked out until {record.lockout_until} [SAFETY]."

        # 5. Operational Mode Check
        active_mode = self.config.mode
        if active_mode == ManagementMode.OBSERVE:
            return False, f"Blocked: Active mode is OBSERVE. Broker writes prohibited [SAFETY]."

        allowed_protect_actions = ("SET_SL", "SET_TP", "BREAK_EVEN", "CLOSE")
        if active_mode == ManagementMode.PROTECT and action not in allowed_protect_actions:
            return False, f"Blocked: Mode PROTECT only permits initial SL/TP, Break-Even, and Strategy Exit; '{action}' rejected."

        allowed_assist_actions = ("SET_SL", "SET_TP", "BREAK_EVEN", "TRAIL_SL", "CLOSE")
        if active_mode == ManagementMode.ASSIST and action not in allowed_assist_actions:
            return False, f"Blocked: Mode ASSIST does not permit '{action}'."

        # 5b. Close Action Guard
        if action == "CLOSE":
            if not self.config.auto_exit_enabled:
                return False, "Blocked: auto_exit_enabled is False. Strategy-based closure prohibited."
            return True, "Close action approved by policy."

        # 5c. Take Profit Modification Guard
        if action == "SET_TP":
            if not self.config.auto_tp_enabled:
                return False, "Blocked: auto_tp_enabled is False. Take Profit modification prohibited."
            current_tp = float(pos.take_profit)
            if self.config.preserve_user_sl_tp and current_tp > 0.0:
                return False, "Blocked: preserve_user_sl_tp is True and user-defined TP already exists."

            new_tp = assessment.recommended_tp
            if new_tp is None or new_tp <= 0.0:
                return False, "Invalid Take Profit: new_tp <= 0.0."

            current_px = float(pos.current_price)
            is_buy = pos.order_type == OrderType.BUY
            if is_buy and new_tp <= current_px:
                return False, f"Invalid BUY TP: new_tp ({new_tp:.5f}) <= current_price ({current_px:.5f})."
            if not is_buy and new_tp >= current_px:
                return False, f"Invalid SELL TP: new_tp ({new_tp:.5f}) >= current_price ({current_px:.5f})."

            if symbol_info:
                stops_dist = symbol_info.stops_level * symbol_info.point
                if stops_dist > 0:
                    dist_to_px = abs(current_px - new_tp)
                    if dist_to_px < stops_dist:
                        return False, f"TP too close to market: {dist_to_px:.5f} < broker stops_level ({stops_dist:.5f})."

            return True, "Take Profit modification approved by policy."

        # 6. Stop Loss Modification Tighten-Only Rule (R9.3) [SAFETY]
        if action in ("SET_SL", "BREAK_EVEN", "TRAIL_SL"):
            new_sl = assessment.recommended_sl
            if new_sl is None or new_sl <= 0.0:
                return False, "R9.2/R9.3 violation: Cannot set or move SL to <= 0.0 [SAFETY]."

            current_sl = float(pos.stop_loss)
            current_px = float(pos.current_price)
            is_buy = pos.order_type == OrderType.BUY

            # Validate price bounds
            if is_buy and new_sl >= current_px:
                return False, f"Invalid BUY SL: new_sl ({new_sl:.5f}) >= current_price ({current_px:.5f})."
            if not is_buy and new_sl <= current_px:
                return False, f"Invalid SELL SL: new_sl ({new_sl:.5f}) <= current_price ({current_px:.5f})."

            # Check stops level proximity if symbol info available
            if symbol_info:
                stops_dist = symbol_info.stops_level * symbol_info.point
                if stops_dist > 0:
                    dist_to_px = abs(current_px - new_sl)
                    if dist_to_px < stops_dist:
                        return False, f"SL too close to market: {dist_to_px:.5f} < broker stops_level ({stops_dist:.5f})."

            # If an existing SL is present, it MUST strictly tighten (reduce risk)
            if current_sl > 0.0:
                if is_buy and new_sl <= current_sl:
                    return False, f"R9.3 violation: New BUY SL ({new_sl:.5f}) is <= current SL ({current_sl:.5f}) (widens risk) [SAFETY]."
                if not is_buy and new_sl >= current_sl:
                    return False, f"R9.3 violation: New SELL SL ({new_sl:.5f}) is >= current SL ({current_sl:.5f}) (widens risk) [SAFETY]."

        # 7. Add-On (Pyramid) Safety Invariants [SAFETY]
        if action == "ADD_ON":
            if active_mode != ManagementMode.FULL:
                return False, "Add-ons permitted in FULL mode only."

            # Max add-on count check
            if record.add_ons_count >= self.config.max_addons_per_position:
                return False, f"Maximum add-ons ({self.config.max_addons_per_position}) already reached."

            # Never average down / never add to losing position
            is_buy = pos.order_type == OrderType.BUY
            current_px = float(pos.current_price)
            open_px = float(pos.open_price)
            is_profitable = (current_px > open_px) if is_buy else (current_px < open_px)
            if not is_profitable:
                return False, "Prohibited: Cannot add to a position that is not in profit (no averaging down) [SAFETY]."

            # Stop MUST already be secured at break-even or better
            current_sl = float(pos.stop_loss)
            if is_buy and current_sl < open_px:
                return False, "Prohibited: Cannot add on until original position SL is at Break-Even or better [SAFETY]."
            if not is_buy and (current_sl <= 0 or current_sl > open_px):
                return False, "Prohibited: Cannot add on until original position SL is at Break-Even or better [SAFETY]."

            # Sizing check
            addon_vol = assessment.add_on_volume or 0.0
            if addon_vol <= 0.0:
                return False, "Invalid add-on volume <= 0.0."

        return True, "Action approved by policy."
