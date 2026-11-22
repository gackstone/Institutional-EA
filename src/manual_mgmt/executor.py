"""
Manual Position Management Safe Order Executor.
Executes approved trade actions with retries, retcode handling, idempotency,
and immediate registry updates to prevent false user-override flags.
Tags: [SAFETY], [DERIVED]
"""

from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from src.adapters.broker_interface import BrokerAdapter, OrderResult, TradeRequest
from src.core.contracts import Position, OrderType, SymbolInfo
from src.manual_mgmt.contracts import (
    AdoptionAssessment,
    ManualPositionRecord,
    ManagementMode
)
from src.manual_mgmt.registry import ManualPositionRegistry

logger = logging.getLogger("ManualMgmtExecutor")

# Transient broker retcodes eligible for retry
RETRYABLE_RETCODES = {
    10004,  # TRADE_RETCODE_REQUOTE
    10006,  # TRADE_RETCODE_REJECT
    10018,  # TRADE_RETCODE_MARKET_CLOSED (brief off-quote)
    10020,  # TRADE_RETCODE_PRICE_CHANGED
    10021,  # TRADE_RETCODE_PRICE_OFF
}


class ManualMgmtExecutor:
    def __init__(
        self,
        broker: BrokerAdapter,
        registry: ManualPositionRegistry,
        audit_log_path: str = "logs/manual_management_audit.log",
        max_retries: int = 3,
        backoff_sec: float = 0.5
    ):
        self.broker = broker
        self.registry = registry
        self.audit_log_path = audit_log_path
        self.max_retries = max_retries
        self.backoff_sec = backoff_sec
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_log_path)), exist_ok=True)

    def _log_audit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Appends a structured JSON audit line."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **data
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"[AUDIT_LOG_ERROR] Could not write audit log: {e}")

    def execute_action(
        self,
        assessment: AdoptionAssessment,
        record: ManualPositionRecord,
        pos: Position,
        symbol_info: Optional[SymbolInfo] = None
    ) -> Tuple[bool, str]:
        """
        Executes an approved action (SET_SL, BREAK_EVEN, TRAIL_SL, ADD_ON).
        Updates the registry on success and logs the outcome.
        """
        action = assessment.action
        ticket = int(assessment.ticket)

        if action in ("SET_SL", "BREAK_EVEN", "TRAIL_SL"):
            target_sl = assessment.recommended_sl
            if target_sl is None or target_sl <= 0:
                return False, f"Target SL invalid ({target_sl})"

            # If recommended_tp is provided and position currently lacks TP, set both in one call
            tp = float(assessment.recommended_tp) if (assessment.recommended_tp and float(pos.take_profit) <= 0.0) else float(pos.take_profit)
            attempt = 0
            last_err = ""

            while attempt < self.max_retries:
                attempt += 1
                res: OrderResult = self.broker.modify_order(
                    ticket=ticket,
                    sl=float(target_sl),
                    tp=tp
                )

                if res.success or res.retcode == 10009:  # TRADE_RETCODE_DONE
                    self.registry.record_bot_modification(
                        ticket=ticket,
                        new_sl=target_sl,
                        new_tp=tp if tp > 0 else None,
                        action_note=f"{action} executed at {target_sl:.5f} ({assessment.reason})"
                    )
                    if action == "BREAK_EVEN":
                        record.break_even_applied = True
                    elif action == "TRAIL_SL":
                        record.trailing_applied = True
                    record.last_action = action
                    self.registry.save_state()

                    self._log_audit("ORDER_MODIFIED", {
                        "ticket": ticket,
                        "action": action,
                        "new_sl": target_sl,
                        "new_tp": tp,
                        "old_sl": pos.stop_loss,
                        "old_tp": pos.take_profit,
                        "reason": assessment.reason,
                        "retcode": res.retcode
                    })
                    logger.info(f"[EXECUTED] #{ticket} {action}: SL moved from {pos.stop_loss:.5f} to {target_sl:.5f} (TP={tp:.5f})")
                    return True, f"SL updated to {target_sl:.5f}"

                last_err = res.error_message or f"Retcode {res.retcode}"
                if res.retcode in RETRYABLE_RETCODES and attempt < self.max_retries:
                    time.sleep(self.backoff_sec * attempt)
                    continue
                else:
                    break

            self._log_audit("MODIFY_FAILED", {
                "ticket": ticket,
                "action": action,
                "attempted_sl": target_sl,
                "error": last_err
            })
            logger.error(f"[EXECUTION_FAILED] #{ticket} {action} failed: {last_err}")
            return False, last_err

        elif action == "SET_TP":
            target_tp = assessment.recommended_tp
            if target_tp is None or target_tp <= 0:
                return False, f"Target TP invalid ({target_tp})"

            cur_sl = float(pos.stop_loss)
            attempt = 0
            last_err = ""

            while attempt < self.max_retries:
                attempt += 1
                res: OrderResult = self.broker.modify_order(
                    ticket=ticket,
                    sl=cur_sl,
                    tp=float(target_tp)
                )

                if res.success or res.retcode == 10009:  # TRADE_RETCODE_DONE
                    self.registry.record_bot_modification(
                        ticket=ticket,
                        new_tp=target_tp,
                        action_note=f"SET_TP executed at {target_tp:.5f} ({assessment.reason})"
                    )
                    record.last_action = action
                    self.registry.save_state()

                    self._log_audit("ORDER_MODIFIED", {
                        "ticket": ticket,
                        "action": action,
                        "new_tp": target_tp,
                        "old_tp": pos.take_profit,
                        "reason": assessment.reason,
                        "retcode": res.retcode
                    })
                    logger.info(f"[EXECUTED] #{ticket} SET_TP: TP set to {target_tp:.5f}")
                    return True, f"TP updated to {target_tp:.5f}"

                last_err = res.error_message or f"Retcode {res.retcode}"
                if res.retcode in RETRYABLE_RETCODES and attempt < self.max_retries:
                    time.sleep(self.backoff_sec * attempt)
                    continue
                else:
                    break

            self._log_audit("MODIFY_FAILED", {
                "ticket": ticket,
                "action": action,
                "attempted_tp": target_tp,
                "error": last_err
            })
            logger.error(f"[EXECUTION_FAILED] #{ticket} SET_TP failed: {last_err}")
            return False, last_err

        elif action == "CLOSE":
            close_vol = assessment.close_volume or float(pos.volume)
            attempt = 0
            last_err = ""

            while attempt < self.max_retries:
                attempt += 1
                res: OrderResult = self.broker.close_position(ticket=ticket, volume=close_vol)
                if res.success or res.retcode == 10009:
                    self.registry.close_and_archive(ticket=ticket, reason=assessment.reason)
                    self._log_audit("POSITION_CLOSED", {
                        "ticket": ticket,
                        "volume": close_vol,
                        "reason": assessment.reason,
                        "retcode": res.retcode
                    })
                    logger.info(f"[CLOSED] #{ticket} closed ({close_vol}L): {assessment.reason}")
                    return True, f"Position #{ticket} closed safely: {assessment.reason}"

                last_err = res.error_message or f"Retcode {res.retcode}"
                if res.retcode in RETRYABLE_RETCODES and attempt < self.max_retries:
                    time.sleep(self.backoff_sec * attempt)
                    continue
                else:
                    break

            self._log_audit("CLOSE_FAILED", {
                "ticket": ticket,
                "volume": close_vol,
                "error": last_err
            })
            logger.error(f"[CLOSE_FAILED] Failed to close #{ticket}: {last_err}")
            return False, last_err

        elif action == "ADD_ON":
            addon_lots = assessment.add_on_volume or 0.0
            if addon_lots <= 0:
                return False, f"Invalid add-on volume {addon_lots}"

            # Prepare trade request for continuation scale-in
            action_type = "BUY" if pos.order_type == OrderType.BUY else "SELL"
            # Sizing and risk: use original trade's current SL as the stop
            cur_sl = float(pos.stop_loss)
            cur_tp = float(pos.take_profit)

            trade_req = TradeRequest(
                symbol=pos.symbol,
                action=action_type,
                volume=addon_lots,
                price=float(pos.current_price),
                sl=cur_sl,
                tp=cur_tp,
                magic=pos.magic,  # Maintain manual/bot association
                comment=f"Bot_AddOn_#{ticket}"
            )

            res = self.broker.send_order(trade_req)
            if res.success:
                self.registry.record_add_on(
                    ticket=ticket,
                    add_on_lots=addon_lots,
                    note=f"Add-on executed via ticket #{res.ticket}"
                )
                self._log_audit("ADD_ON_EXECUTED", {
                    "parent_ticket": ticket,
                    "new_ticket": res.ticket,
                    "volume": addon_lots,
                    "price": res.price,
                    "reason": assessment.reason
                })
                logger.info(f"[ADD_ON_SUCCESS] Added {addon_lots}L to #{ticket} (New Ticket #{res.ticket})")
                return True, f"Add-on executed (Ticket #{res.ticket})"
            else:
                self._log_audit("ADD_ON_FAILED", {
                    "parent_ticket": ticket,
                    "volume": addon_lots,
                    "error": res.error_message
                })
                logger.error(f"[ADD_ON_FAILED] Failed adding to #{ticket}: {res.error_message}")
                return False, res.error_message

        return False, f"Unsupported action: {action}"
