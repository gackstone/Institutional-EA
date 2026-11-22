"""
Manual Position Detector and Lifecycle Coordinator.
Discovers manual positions, manages adoption lifecycle, verifies policy guards,
and coordinates assessment and execution.
Tags: [SAFETY], [VIDEO/KNOWLEDGE], [DERIVED]
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.adapters.broker_interface import BrokerAdapter
from src.core.contracts import Candle, Position, SymbolInfo, Timeframe
from src.manual_mgmt.contracts import (
    AdoptionAssessment,
    ManagementMode,
    ManualMgmtConfig,
    ManualPositionRecord,
    PositionClass
)
from src.manual_mgmt.classifier import classify_position
from src.manual_mgmt.registry import ManualPositionRegistry
from src.manual_mgmt.assessor import ManualPositionAssessor
from src.manual_mgmt.policy import ManualMgmtPolicy
from src.manual_mgmt.executor import ManualMgmtExecutor

logger = logging.getLogger("ManualPositionDetector")


class ManualPositionDetector:
    def __init__(
        self,
        config: ManualMgmtConfig,
        broker: BrokerAdapter,
        registry: Optional[ManualPositionRegistry] = None,
        assessor: Optional[ManualPositionAssessor] = None,
        policy: Optional[ManualMgmtPolicy] = None,
        executor: Optional[ManualMgmtExecutor] = None,
        bot_magic: int = 100101
    ):
        self.config = config
        self.broker = broker
        self.bot_magic = bot_magic
        self.registry = registry or ManualPositionRegistry(lockout_minutes=config.user_override_lockout_minutes)
        self.assessor = assessor or ManualPositionAssessor(config=self.config)
        self.policy = policy or ManualMgmtPolicy(config=self.config)
        self.executor = executor or ManualMgmtExecutor(broker=self.broker, registry=self.registry)

    def get_summary(self) -> Dict[str, Any]:
        """Returns aggregated telemetry metrics for dashboard and monitoring [Section 12]."""
        records = self.registry.get_all_records()
        total_adopted = len(records)
        protected = sum(1 for r in records if r.current_sl > 0)
        awaiting_sl = sum(1 for r in records if r.current_sl <= 0)
        be_active = sum(1 for r in records if r.break_even_applied)
        trailing_active = sum(1 for r in records if r.trailing_applied)
        locked_out = sum(1 for r in records if r.is_locked_out())
        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode.value,
            "total_adopted": total_adopted,
            "protected_positions": protected,
            "awaiting_sl": awaiting_sl,
            "break_even_active": be_active,
            "trailing_active": trailing_active,
            "locked_out": locked_out,
            "allowed_symbols": self.config.allowed_symbols
        }

    def run_cycle(
        self,
        market_data_candles_m15: Optional[Dict[str, List[Candle]]] = None,
        market_data_candles_m5: Optional[Dict[str, List[Candle]]] = None,
        symbol_info_map: Optional[Dict[str, SymbolInfo]] = None,
        deals_history: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes one full manual trade management cycle.
        Returns a structured report of detected positions and actions taken.
        """
        report: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.config.mode.value,
            "detected_positions": {},
            "assessments": {},
            "executed_actions": [],
            "rejected_actions": []
        }

        # 1. Fetch current open positions and account status
        try:
            account_info = self.broker.get_account_info()
            all_positions = self.broker.get_positions()
        except Exception as e:
            logger.error(f"[DETECTOR_ERROR] Failed fetching broker data: {e}")
            return report

        current_tickets = {p.ticket for p in all_positions}

        # 2. Archive positions closed since last cycle
        for rec in self.registry.get_all_records():
            if rec.ticket not in current_tickets:
                self.registry.close_and_archive(rec.ticket, reason="Closed at broker")

        # 3. Classify and process each open position
        for pos in all_positions:
            ticket = int(pos.ticket)
            cls = classify_position(
                pos=pos,
                bot_magic=self.bot_magic,
                allowed_symbols=self.config.allowed_symbols,
                deals_history=deals_history
            )
            report["detected_positions"][ticket] = {
                "symbol": pos.symbol,
                "type": pos.order_type.value,
                "volume": pos.volume,
                "magic": pos.magic,
                "classification": cls.value
            }

            # Only MANUAL positions are processed by this coordinator [SAFETY]
            if cls != PositionClass.MANUAL:
                continue

            # Update or adopt position in registry
            record, user_override = self.registry.update_position_state(pos)
            if user_override:
                logger.warning(f"[OVERRIDE_ACTIVE] Ticket #{ticket} locked out until {record.lockout_until}")

            # Fetch candle data and symbol info
            sym = pos.symbol
            m15 = (market_data_candles_m15 or {}).get(sym) or []
            m5 = (market_data_candles_m5 or {}).get(sym) or []
            s_info = (symbol_info_map or {}).get(sym)

            # If candle bars are not supplied, attempt fetching via broker
            if not m15:
                try:
                    m15 = self.broker.get_rates(symbol=sym, timeframe="M15", count=100)
                except Exception:
                    m15 = []
            if not m5:
                try:
                    m5 = self.broker.get_rates(symbol=sym, timeframe="M5", count=100)
                except Exception:
                    m5 = []

            # 4. Assess position using strategy skills
            assessment = self.assessor.assess(
                pos=pos,
                record=record,
                candles_m15=m15,
                candles_m5=m5,
                symbol_info=s_info
            )
            report["assessments"][ticket] = {
                "action": assessment.action,
                "recommended_sl": assessment.recommended_sl,
                "recommended_tp": assessment.recommended_tp,
                "reason": assessment.reason,
                "skills_used": assessment.skills_used,
                "current_r": assessment.risk_r_current
            }

            if assessment.action == "NONE":
                continue

            # 5. Validate proposed action against policy guards [SAFETY]
            allowed, policy_reason = self.policy.validate_action(
                assessment=assessment,
                record=record,
                pos=pos,
                account_info=account_info,
                symbol_info=s_info
            )

            if not allowed:
                report["rejected_actions"].append({
                    "ticket": ticket,
                    "action": assessment.action,
                    "reason": policy_reason
                })
                logger.info(f"[ACTION_DECLINED] #{ticket} {assessment.action}: {policy_reason}")
                continue

            # 6. Execute validated action
            success, exec_msg = self.executor.execute_action(
                assessment=assessment,
                record=record,
                pos=pos,
                symbol_info=s_info
            )
            if success:
                report["executed_actions"].append({
                    "ticket": ticket,
                    "action": assessment.action,
                    "detail": exec_msg
                })
            else:
                report["rejected_actions"].append({
                    "ticket": ticket,
                    "action": assessment.action,
                    "reason": f"Execution failed: {exec_msg}"
                })

        return report
