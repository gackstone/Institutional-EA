"""
Automatic MT5 Account-Type Detection & Broker Compatibility Module.
Inspects connected MetaTrader 5 account and terminal information, consults the
configurable broker compatibility registry, and classifies the account into:
- STANDARD
- CENT
- DEMO_STANDARD
- DEMO_CENT
- OTHER
- UNKNOWN

Safety Rules:
- Never assume an account displaying 100,000 is a cent account.
- Never assume an account using USD is a standard account without verification.
- Never automatically reinterpret an account balance by dividing by 100 without verified evidence.
- If classification confidence is insufficient, mark UNKNOWN and fail closed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AccountDetector")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "broker_registry.json"


class AccountType(str, Enum):
    STANDARD = "STANDARD"
    CENT = "CENT"
    DEMO_STANDARD = "DEMO_STANDARD"
    DEMO_CENT = "DEMO_CENT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"

    @property
    def is_cent(self) -> bool:
        return self in (AccountType.CENT, AccountType.DEMO_CENT)

    @property
    def is_demo(self) -> bool:
        return self in (AccountType.DEMO_STANDARD, AccountType.DEMO_CENT)


@dataclass
class AccountDetectionResult:
    account_login: int = 0
    broker_server: str = ""
    account_company: str = ""
    account_currency: str = "USD"
    account_balance: float = 0.0
    account_equity: float = 0.0
    free_margin: float = 0.0
    margin: float = 0.0
    leverage: int = 100
    trade_mode: str = "DEMO"  # DEMO, REAL, CONTEST
    trade_allowed: bool = False
    trade_expert: bool = False
    terminal_connected: bool = False
    terminal_trade_allowed: bool = False
    account_type: AccountType = AccountType.UNKNOWN
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW
    denomination_factor: float = 1.0  # 100.0 for cent accounts (1 USD = 100 cents), 1.0 for standard
    normalized_balance: float = 0.0
    normalized_equity: float = 0.0
    evidence: List[str] = field(default_factory=list)
    manual_override: Optional[str] = None
    override_confirmed: bool = False
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class AccountDetector:
    """
    Inspects live or provided MT5 account and terminal data to reliably classify
    the account type and verify currency denomination.
    """

    DEFAULT_CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}
    DEFAULT_STANDARD_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or CONFIG_PATH
        self.known_cent_currencies = set(self.DEFAULT_CENT_CURRENCIES)
        self.broker_registry: Dict[str, Any] = {}
        self.load_registry()

    def load_registry(self) -> None:
        if self.registry_path and os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    currencies = data.get("known_cent_currencies", [])
                    if currencies:
                        self.known_cent_currencies.update(c.upper() for c in currencies)
                    self.broker_registry = data.get("brokers", {})
                logger.info(f"[AccountDetector] Loaded broker registry with {len(self.broker_registry)} brokers.")
            except Exception as e:
                logger.warning(f"[AccountDetector] Failed to load broker registry from {self.registry_path}: {e}")

    def detect(
        self,
        account_info: Any = None,
        terminal_info: Any = None,
        manual_override: Optional[str] = None,
        override_confirmed: bool = False,
    ) -> AccountDetectionResult:
        """
        Analyzes account information and terminal state.
        If account_info is None, attempts to import MetaTrader5 and query directly.
        """
        raw_meta: Dict[str, Any] = {}
        evidence: List[str] = []

        if account_info is None:
            try:
                import MetaTrader5 as mt5
                if mt5.initialize():
                    account_info = mt5.account_info()
                    terminal_info = mt5.terminal_info()
            except Exception as e:
                logger.debug(f"[AccountDetector] Direct MT5 query failed: {e}")

        # Extract attributes from MT5 object, dataclass, or dictionary
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
        server = str(_get(account_info, "server", "") or "")
        company = str(_get(account_info, "company", "") or "")
        currency = str(_get(account_info, "currency", "USD") or "USD").strip().upper()
        balance = float(_get(account_info, "balance", 0.0) or 0.0)
        equity = float(_get(account_info, "equity", balance) or 0.0)
        margin = float(_get(account_info, "margin", 0.0) or 0.0)
        free_margin = float(_get(account_info, "margin_free", _get(account_info, "free_margin", equity)) or 0.0)
        leverage = int(_get(account_info, "leverage", 100) or 100)

        trade_allowed = bool(_get(account_info, "trade_allowed", False))
        trade_expert = bool(_get(account_info, "trade_expert", False))

        raw_trade_mode = _get(account_info, "trade_mode", 0)
        if isinstance(raw_trade_mode, int):
            trade_mode = "REAL" if raw_trade_mode == 2 else ("CONTEST" if raw_trade_mode == 1 else "DEMO")
        else:
            trade_mode = str(raw_trade_mode).upper()
        is_demo = (trade_mode == "DEMO" or "demo" in server.lower())

        term_conn = bool(_get(terminal_info, "connected", True if login > 0 else False))
        term_trade = bool(_get(terminal_info, "trade_allowed", False))

        raw_meta = {
            "login": login,
            "server": server,
            "company": company,
            "currency": currency,
            "balance": balance,
            "equity": equity,
            "leverage": leverage,
            "trade_mode": trade_mode,
            "trade_allowed": trade_allowed,
            "trade_expert": trade_expert,
            "terminal_connected": term_conn,
            "terminal_trade_allowed": term_trade,
        }

        # Check manual override first
        if manual_override and override_confirmed:
            norm_ov = manual_override.strip().upper()
            if norm_ov in ("CENT", "DEMO_CENT"):
                chosen_type = AccountType.DEMO_CENT if is_demo else AccountType.CENT
                denom = 100.0
                evidence.append(f"Manual user override confirmed: {norm_ov}")
                return AccountDetectionResult(
                    account_login=login,
                    broker_server=server,
                    account_company=company,
                    account_currency=currency,
                    account_balance=balance,
                    account_equity=equity,
                    free_margin=free_margin,
                    margin=margin,
                    leverage=leverage,
                    trade_mode=trade_mode,
                    trade_allowed=trade_allowed,
                    trade_expert=trade_expert,
                    terminal_connected=term_conn,
                    terminal_trade_allowed=term_trade,
                    account_type=chosen_type,
                    confidence="HIGH",
                    denomination_factor=denom,
                    normalized_balance=balance / denom,
                    normalized_equity=equity / denom,
                    evidence=evidence,
                    manual_override=manual_override,
                    override_confirmed=True,
                    raw_metadata=raw_meta,
                )
            elif norm_ov in ("STANDARD", "DEMO_STANDARD"):
                chosen_type = AccountType.DEMO_STANDARD if is_demo else AccountType.STANDARD
                evidence.append(f"Manual user override confirmed: {norm_ov}")
                return AccountDetectionResult(
                    account_login=login,
                    broker_server=server,
                    account_company=company,
                    account_currency=currency,
                    account_balance=balance,
                    account_equity=equity,
                    free_margin=free_margin,
                    margin=margin,
                    leverage=leverage,
                    trade_mode=trade_mode,
                    trade_allowed=trade_allowed,
                    trade_expert=trade_expert,
                    terminal_connected=term_conn,
                    terminal_trade_allowed=term_trade,
                    account_type=chosen_type,
                    confidence="HIGH",
                    denomination_factor=1.0,
                    normalized_balance=balance,
                    normalized_equity=equity,
                    evidence=evidence,
                    manual_override=manual_override,
                    override_confirmed=True,
                    raw_metadata=raw_meta,
                )

        # Automatic detection logic
        # Rule 1: Check currency against known cent currencies
        is_cent_currency = currency in self.known_cent_currencies
        if is_cent_currency:
            evidence.append(f"Currency '{currency}' matches known cent currencies list.")

        # Rule 2: Check broker registry entries for company and server matches
        matched_broker_config = None
        for b_name, b_cfg in self.broker_registry.items():
            comp_patterns = b_cfg.get("company_patterns", [])
            cent_servers = b_cfg.get("cent_servers", [])
            cent_currencies = [c.upper() for c in b_cfg.get("cent_currencies", [])]

            comp_match = any(p.lower() in company.lower() for p in comp_patterns) if company else False
            serv_match = any(s.lower() in server.lower() for s in cent_servers) if server else False
            curr_match = currency in cent_currencies

            if serv_match or (comp_match and curr_match):
                matched_broker_config = b_cfg
                evidence.append(f"Broker registry matched '{b_name}' rule (server_match={serv_match}, comp_match={comp_match}, curr_match={curr_match}).")
                break

        # Rule 3: Check server naming pattern for explicit "cent" keywords
        server_has_cent = "cent" in server.lower()
        if server_has_cent:
            evidence.append(f"Server name '{server}' contains explicit 'cent' identifier.")

        # Rule 4: Synthesize account type with strict safety guards
        account_type = AccountType.UNKNOWN
        confidence = "LOW"
        denomination_factor = 1.0

        if is_cent_currency:
            # Confirmed cent currency (USC, EUC, etc.)
            account_type = AccountType.DEMO_CENT if is_demo else AccountType.CENT
            confidence = "HIGH"
            denomination_factor = 100.0
            evidence.append("Account classified as CENT based on verified cent currency denomination.")
        elif matched_broker_config and (server_has_cent or currency in matched_broker_config.get("cent_currencies", [])):
            account_type = AccountType.DEMO_CENT if is_demo else AccountType.CENT
            confidence = "HIGH"
            denomination_factor = float(matched_broker_config.get("denomination_factor", 100.0))
            evidence.append("Account classified as CENT based on broker registry server and currency alignment.")
        elif server_has_cent and currency in self.DEFAULT_STANDARD_CURRENCIES:
            # Ambiguity: Server says cent, but currency says standard USD.
            # Require explicit confirmation before dividing by 100!
            account_type = AccountType.UNKNOWN
            confidence = "LOW"
            denomination_factor = 1.0
            evidence.append(
                f"AMBIGUOUS_DENOMINATION: Server name '{server}' contains 'cent', but currency is '{currency}'. "
                "Marked UNKNOWN to prevent accidental 100x balance interpretation."
            )
        elif currency in self.DEFAULT_STANDARD_CURRENCIES and not server_has_cent:
            account_type = AccountType.DEMO_STANDARD if is_demo else AccountType.STANDARD
            confidence = "HIGH"
            denomination_factor = 1.0
            evidence.append(f"Account classified as STANDARD based on verified conventional currency '{currency}'.")
        else:
            # Unknown denomination: fail closed!
            account_type = AccountType.UNKNOWN
            confidence = "LOW"
            denomination_factor = 1.0
            evidence.append(f"Unknown or unverified currency denomination '{currency}'. Classification failed closed.")

        norm_balance = balance / denomination_factor
        norm_equity = equity / denomination_factor

        return AccountDetectionResult(
            account_login=login,
            broker_server=server,
            account_company=company,
            account_currency=currency,
            account_balance=balance,
            account_equity=equity,
            free_margin=free_margin,
            margin=margin,
            leverage=leverage,
            trade_mode=trade_mode,
            trade_allowed=trade_allowed,
            trade_expert=trade_expert,
            terminal_connected=term_conn,
            terminal_trade_allowed=term_trade,
            account_type=account_type,
            confidence=confidence,
            denomination_factor=denomination_factor,
            normalized_balance=norm_balance,
            normalized_equity=norm_equity,
            evidence=evidence,
            manual_override=manual_override,
            override_confirmed=override_confirmed,
            raw_metadata=raw_meta,
        )
