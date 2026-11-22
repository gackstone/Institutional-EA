"""
Account Classification & Anomaly Detection Service.
Classifies MT5 accounts into STANDARD, CENT, MICRO, DEMO, and REAL categories,
determines denomination factors, and detects account synchronization anomalies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AccountClassifier")


class AccountCategory(str, Enum):
    STANDARD = "STANDARD"
    CENT = "CENT"
    MICRO = "MICRO"
    PROP = "PROP"
    UNKNOWN = "UNKNOWN"

    @property
    def is_cent(self) -> bool:
        return self == AccountCategory.CENT

    @property
    def is_micro(self) -> bool:
        return self in (AccountCategory.MICRO, AccountCategory.CENT)


class TradeMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"
    CONTEST = "CONTEST"
    UNKNOWN = "UNKNOWN"


@dataclass
class AccountProfile:
    login: int = 0
    server: str = ""
    company: str = ""
    currency: str = "USD"
    category: AccountCategory = AccountCategory.STANDARD
    trade_mode: TradeMode = TradeMode.DEMO
    denomination_factor: float = 1.0  # 100.0 for USC/EUC/GBX, 1.0 for standard
    currency_digits: int = 2
    leverage: int = 100
    native_balance: float = 0.0
    native_equity: float = 0.0
    native_free_margin: float = 0.0
    native_margin: float = 0.0
    normalized_balance: float = 0.0
    normalized_equity: float = 0.0
    normalized_free_margin: float = 0.0
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    evidence: List[str] = field(default_factory=list)
    anomalies: List[str] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_cent(self) -> bool:
        return self.category.is_cent

    @property
    def session_key(self) -> str:
        return f"{self.server}:{self.login}"


class AccountClassifier:
    """
    Intelligently inspects MT5 account and terminal data to classify the account profile,
    detect cent vs standard vs micro environments, and guard against denomination mismatch.
    """

    KNOWN_CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}
    KNOWN_STANDARD_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}

    def __init__(self):
        pass

    def classify(
        self,
        account_info: Any,
        terminal_info: Any = None,
        symbols_sample: Optional[List[str]] = None
    ) -> AccountProfile:
        """
        Classifies an MT5 account based on account_info, terminal_info, and symbol naming samples.
        """
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        login = int(_get(account_info, "login", 0) or 0)
        server = str(_get(account_info, "server", "") or "").strip()
        company = str(_get(account_info, "company", "") or "").strip()
        currency = str(_get(account_info, "currency", "USD") or "USD").strip().upper()
        raw_trade_mode = _get(account_info, "trade_mode", 0)
        leverage = int(_get(account_info, "leverage", 100) or 100)
        balance = float(_get(account_info, "balance", 0.0) or 0.0)
        equity = float(_get(account_info, "equity", balance) or balance)
        margin = float(_get(account_info, "margin", 0.0) or 0.0)
        free_margin = float(_get(account_info, "margin_free", _get(account_info, "free_margin", balance)) or balance)

        evidence: List[str] = []
        anomalies: List[str] = []

        # Trade mode classification
        if raw_trade_mode == 0 or "demo" in server.lower():
            t_mode = TradeMode.DEMO
        elif raw_trade_mode == 2:
            t_mode = TradeMode.CONTEST
        else:
            t_mode = TradeMode.REAL

        # Category and Denomination Factor
        category = AccountCategory.UNKNOWN
        denom_factor = 1.0
        confidence = "LOW"

        # Signal 1: Account Currency Code
        if currency in self.KNOWN_CENT_CURRENCIES:
            category = AccountCategory.CENT
            denom_factor = 100.0
            evidence.append(f"Currency code '{currency}' is a known cent currency")
            confidence = "HIGH"

        # Signal 2: Server or Account Name keywords
        server_lower = server.lower()
        company_lower = company.lower()
        if "cent" in server_lower or "cent" in company_lower:
            evidence.append(f"Server or company contains 'cent' keyword: {server} / {company}")
            if category != AccountCategory.CENT:
                category = AccountCategory.CENT
                denom_factor = 100.0
                confidence = "HIGH"

        # Signal 3: Symbols inventory sample (e.g., .c suffix for Cent)
        if symbols_sample:
            cent_symbols = [s for s in symbols_sample if s.upper().endswith(".C") or s.upper().endswith("-CENT")]
            if len(cent_symbols) >= 2:
                evidence.append(f"Found cent symbol suffixes in inventory: {cent_symbols[:3]}")
                if category == AccountCategory.UNKNOWN:
                    category = AccountCategory.CENT
                    denom_factor = 100.0
                    confidence = "MEDIUM"

        # Signal 4: Micro account keywords
        if "micro" in server_lower or "micro" in company_lower:
            evidence.append(f"Server contains 'micro' keyword: {server}")
            if category == AccountCategory.UNKNOWN:
                category = AccountCategory.MICRO
                denom_factor = 1.0
                confidence = "MEDIUM"

        # Signal 5: Standard currencies
        if category == AccountCategory.UNKNOWN and currency in self.KNOWN_STANDARD_CURRENCIES:
            category = AccountCategory.STANDARD
            denom_factor = 1.0
            evidence.append(f"Currency code '{currency}' is a standard fiat currency")
            confidence = "HIGH"

        # Denomination Anomaly Detection:
        # Detect historical bug where free margin was divided by 100 while balance was left in native cents
        # (e.g. balance 1499.40 USC, free_margin 14.99 USC with 0 open positions)
        if margin == 0.0 and balance > 0.0 and free_margin > 0.0:
            ratio = balance / free_margin
            if 95.0 <= ratio <= 105.0:
                anomaly_msg = (
                    f"CRITICAL_DENOMINATION_MISMATCH: Native balance ({balance:.2f}) is ~100x free margin ({free_margin:.2f}) "
                    f"with 0 margin used. Likely unhealed double-scaling in free_margin feed."
                )
                anomalies.append(anomaly_msg)
                logger.warning(f"[AccountClassifier] {anomaly_msg}")
                # Auto-heal free_margin for consistent representation
                free_margin = balance

        norm_balance = round(balance / denom_factor, 2)
        norm_equity = round(equity / denom_factor, 2)
        norm_free_margin = round(free_margin / denom_factor, 2)

        return AccountProfile(
            login=login,
            server=server,
            company=company,
            currency=currency,
            category=category,
            trade_mode=t_mode,
            denomination_factor=denom_factor,
            currency_digits=2,
            leverage=leverage,
            native_balance=balance,
            native_equity=equity,
            native_free_margin=free_margin,
            native_margin=margin,
            normalized_balance=norm_balance,
            normalized_equity=norm_equity,
            normalized_free_margin=norm_free_margin,
            confidence=confidence,
            evidence=evidence,
            anomalies=anomalies,
            raw_metadata={
                "raw_trade_mode": raw_trade_mode,
                "server": server,
                "company": company,
            }
        )
