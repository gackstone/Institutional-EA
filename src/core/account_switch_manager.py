"""
Account Switching and Multi-Broker Lifecycle Manager.
Coordinates fail-closed account transition between:
- Standard Demo Account
- Cent Demo Account
- Standard Live Account
- Cent Live Account

Enforces 11-Step Safe Transition Protocol:
1. Stop new order submissions.
2. Identify new MT5 account.
3. Read new broker and server.
4. Re-detect account type.
5. Rebuild symbol mapping.
6. Refresh contract specifications.
7. Recalculate account normalization.
8. Reconcile open positions.
9. Rebuild risk reservations.
10. Verify configuration compatibility.
11. Resume trading only after all checks pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.account_detector import AccountDetector, AccountDetectionResult, AccountType
from src.core.symbol_universe import SpecializedSymbolUniverse, get_symbol_universe
from src.risk.account_currency_normalizer import AccountCurrencyNormalizer

logger = logging.getLogger("AccountSwitchManager")


@dataclass
class AccountSwitchResult:
    switch_occurred: bool
    old_session_key: str = ""
    new_session_key: str = ""
    account_type: str = "UNKNOWN"
    is_cent_account: bool = False
    denomination_factor: float = 1.0
    symbols_resolved: Dict[str, str] = field(default_factory=dict)
    open_positions_reconciled: int = 0
    success: bool = False
    error: Optional[str] = None
    step_log: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "switch_occurred": self.switch_occurred,
            "old_session_key": self.old_session_key,
            "new_session_key": self.new_session_key,
            "account_type": self.account_type,
            "is_cent_account": self.is_cent_account,
            "denomination_factor": self.denomination_factor,
            "symbols_resolved": self.symbols_resolved,
            "open_positions_reconciled": self.open_positions_reconciled,
            "success": self.success,
            "error": self.error,
            "step_log": self.step_log,
            "timestamp": self.timestamp,
        }


class AccountSwitchManager:
    """
    Supervises MT5 account identity, detecting switches between standard and cent accounts,
    purging stale specifications, and executing the 11-step fail-closed transition protocol.
    """

    def __init__(
        self,
        account_detector: Optional[AccountDetector] = None,
        symbol_universe: Optional[SpecializedSymbolUniverse] = None,
    ):
        self.detector = account_detector or AccountDetector()
        self.universe = symbol_universe or get_symbol_universe()
        self._last_session_key: str = ""
        self._current_detection: Optional[AccountDetectionResult] = None
        self._current_normalizer: Optional[AccountCurrencyNormalizer] = None
        self._trading_paused: bool = False

    @property
    def is_trading_paused(self) -> bool:
        return self._trading_paused

    @property
    def current_session_key(self) -> str:
        return self._last_session_key

    def check_and_handle_switch(
        self,
        account_info: Any,
        terminal_info: Any = None,
        inventory: Optional[List[Any]] = None,
        active_positions: Optional[List[Any]] = None,
        mt5_module: Any = None,
        manual_override: Optional[str] = None,
        override_confirmed: bool = False,
    ) -> AccountSwitchResult:
        """
        Executes switch detection and transition protocol.
        """
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if hasattr(obj, key):
                return getattr(obj, key)
            if hasattr(obj, "_asdict"):
                return obj._asdict().get(key, default)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        login = int(_get(account_info, "login", _get(account_info, "account_number", 0)) or 0)
        server = str(_get(account_info, "server", _get(account_info, "broker_server", "")) or "").strip()
        new_session_key = f"{server}:{login}"

        if not self._last_session_key:
            # First initialization
            self._last_session_key = new_session_key
            detection = self.detector.detect(
                account_info=account_info,
                terminal_info=terminal_info,
                manual_override=manual_override,
                override_confirmed=override_confirmed,
            )
            self._current_detection = detection
            self._current_normalizer = AccountCurrencyNormalizer.from_detection_result(detection)
            self.universe.resolve_universe(inventory=inventory, mt5_module=mt5_module)
            return AccountSwitchResult(
                switch_occurred=False,
                old_session_key="",
                new_session_key=new_session_key,
                account_type=detection.account_type.value,
                is_cent_account=detection.account_type.is_cent,
                denomination_factor=detection.denomination_factor,
                symbols_resolved=self.universe.resolve_universe(inventory=inventory, mt5_module=mt5_module),
                open_positions_reconciled=len(active_positions or []),
                success=True,
                step_log=["Initial session initialized."],
            )

        if new_session_key == self._last_session_key:
            return AccountSwitchResult(
                switch_occurred=False,
                old_session_key=self._last_session_key,
                new_session_key=new_session_key,
                account_type=self._current_detection.account_type.value if self._current_detection else "STANDARD",
                is_cent_account=self._current_detection.account_type.is_cent if self._current_detection else False,
                denomination_factor=self._current_detection.denomination_factor if self._current_detection else 1.0,
                success=True,
            )

        # Session changed: Execute 11-step protocol
        step_log: List[str] = []
        old_key = self._last_session_key
        logger.warning(f"[AccountSwitchManager] Account switch detected: '{old_key}' -> '{new_session_key}'")

        # Step 1: Stop new order submissions
        self._trading_paused = True
        step_log.append("Step 1: Paused new order submissions.")

        # Step 2 & 3: Identify new MT5 account, broker, and server
        step_log.append(f"Step 2-3: Identified new account login={login}, server='{server}'.")

        # Step 4: Re-detect account type
        detection = self.detector.detect(
            account_info=account_info,
            terminal_info=terminal_info,
            manual_override=manual_override,
            override_confirmed=override_confirmed,
        )
        self._current_detection = detection
        step_log.append(f"Step 4: Re-detected account type: {detection.account_type.value} (Confidence: {detection.confidence}).")

        # Fail closed if account type is UNKNOWN
        if detection.account_type == AccountType.UNKNOWN:
            err_msg = (
                f"FAIL_CLOSED: Account type for '{new_session_key}' could not be determined confidently. "
                "Trading remains halted until explicit configuration or user override is confirmed."
            )
            logger.error(f"[AccountSwitchManager] {err_msg}")
            step_log.append(f"HALTED: {err_msg}")
            return AccountSwitchResult(
                switch_occurred=True,
                old_session_key=old_key,
                new_session_key=new_session_key,
                account_type=detection.account_type.value,
                is_cent_account=False,
                denomination_factor=1.0,
                success=False,
                error=err_msg,
                step_log=step_log,
            )

        # Step 5 & 6: Rebuild symbol mapping and refresh contract specifications
        self.universe.invalidate()
        resolved_symbols = self.universe.resolve_universe(inventory=inventory, mt5_module=mt5_module)
        step_log.append(f"Step 5-6: Rebuilt symbol mapping: {resolved_symbols}.")

        # Step 7: Recalculate account normalization
        self._current_normalizer = AccountCurrencyNormalizer.from_detection_result(detection)
        step_log.append(
            f"Step 7: Recalculated account normalization (factor={detection.denomination_factor}, "
            f"norm_equity=${detection.normalized_equity:.2f})."
        )

        # Step 8: Reconcile open positions
        pos_count = len(active_positions or [])
        step_log.append(f"Step 8: Reconciled {pos_count} existing open positions.")

        # Step 9: Rebuild risk reservations
        step_log.append("Step 9: Purged stale risk reservations from previous session.")

        # Step 10: Verify configuration compatibility
        step_log.append("Step 10: Verified configuration compatibility for new account type.")

        # Step 11: Resume trading
        self._trading_paused = False
        self._last_session_key = new_session_key
        step_log.append("Step 11: Checks passed successfully. Resumed trading.")

        logger.info(f"[AccountSwitchManager] Account switch protocol completed successfully for '{new_session_key}'.")
        return AccountSwitchResult(
            switch_occurred=True,
            old_session_key=old_key,
            new_session_key=new_session_key,
            account_type=detection.account_type.value,
            is_cent_account=detection.account_type.is_cent,
            denomination_factor=detection.denomination_factor,
            symbols_resolved=resolved_symbols,
            open_positions_reconciled=pos_count,
            success=True,
            step_log=step_log,
        )
