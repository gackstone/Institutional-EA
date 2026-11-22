"""
Centralized Account Normalization & Adaptive Configuration Engine.
Authoritative source for account categorization (STANDARD, MICRO, CENT),
single-point monetary normalization to calculation currency (USD),
and proportional derivation of account-adaptive risk and profit thresholds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AccountNormalization")


class AccountType(str, Enum):
    STANDARD_USD = "STANDARD_USD"
    MICRO_USD = "MICRO_USD"
    CENT_USC = "CENT_USC"
    STANDARD_OTHER = "STANDARD_OTHER"
    UNKNOWN = "UNKNOWN"

    @property
    def is_cent(self) -> bool:
        return self == AccountType.CENT_USC

    @property
    def is_micro(self) -> bool:
        return self == AccountType.MICRO_USD

    @property
    def is_standard(self) -> bool:
        return self in (AccountType.STANDARD_USD, AccountType.STANDARD_OTHER)


@dataclass(frozen=True)
class NormalizedAccountSnapshot:
    """
    Immutable representation of an active MT5 account holding both pristine native
    figures and single-conversion normalized USD calculation figures.
    """
    login: int
    masked_login: str
    server: str
    company: str
    account_type: AccountType
    currency: str                       # Native currency (e.g. USC, USD, EUR)
    calculation_currency: str = "USD"   # Calculation currency
    denomination_factor: float = 1.0    # 100.0 for cent accounts, 1.0 for standard/micro
    leverage: int = 100
    trade_mode: str = "DEMO"            # DEMO, REAL, CONTEST
    margin_mode: int = 2                # 1 = Netting, 2 = Hedging
    margin_mode_str: str = "HEDGING"
    
    # Native MT5 values (Pristine, broker reported)
    native_balance: float = 0.0
    native_equity: float = 0.0
    native_free_margin: float = 0.0
    native_margin: float = 0.0
    margin_level: float = 0.0
    
    # Normalized USD-equivalent calculation values (Single conversion)
    normalized_balance: float = 0.0
    normalized_equity: float = 0.0
    normalized_free_margin: float = 0.0
    normalized_margin: float = 0.0
    
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_verified: bool = True
    verification_status: str = "VERIFIED"


@dataclass(frozen=True)
class AdaptiveMonetaryThresholds:
    """
    Account-proportionate monetary thresholds derived from normalized equity.
    Preserves existing reference values for Standard USD accounts, and dynamically scales
    for Micro USD and Cent USC accounts without changing percentage limits.
    """
    # Reference baseline equity ($10,000 USD)
    reference_equity: float
    current_equity: float
    equity_scale_ratio: float
    
    # Profit targets
    target_net_profit_usd: float        # Normalized target in calculation currency
    target_net_profit_native: float     # Target in native account currency
    min_profit_filter_native: float     # Transaction cost + minimum net hurdle in native units
    
    # Monetary risk budgets
    risk_percentage: float              # Percentage (e.g. 1.0% or 0.25%)
    max_permitted_risk_usd: float       # Normalized risk budget
    max_permitted_risk_native: float    # Native risk budget
    
    # Portfolio exposure budgets
    max_aggregate_risk_pct: float
    max_portfolio_monetary_risk_native: float
    
    # Daily loss bounds
    daily_loss_limit_pct: float
    daily_loss_limit_native: float


class AccountNormalizationEngine:
    """
    Central authoritative engine for MT5 account detection, currency normalization,
    and adaptive threshold configuration.
    """

    KNOWN_CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}
    KNOWN_STANDARD_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}
    REFERENCE_STANDARD_EQUITY = 10000.0  # Standard reference capital base for scaling

    def __init__(self):
        # Fallback static exchange rates to USD; live rates updated dynamically
        self._rates_to_usd: Dict[str, float] = {
            "USD": 1.0,
            "USC": 0.01,
            "EUR": 1.08,
            "EUC": 0.0108,
            "GBP": 1.28,
            "GBX": 0.0128,
            "JPY": 0.0065,
            "AUD": 0.65,
            "CAD": 0.72,
            "CHF": 1.12,
            "NZD": 0.59,
        }

    @staticmethod
    def mask_login(login: Any) -> str:
        s = str(login or "").strip()
        if len(s) <= 4:
            return "***" + s
        return "***" + s[-4:]

    def detect_account_type(
        self,
        currency: str,
        balance: float,
        server: str = "",
        company: str = "",
        symbol_sample: Optional[List[str]] = None
    ) -> Tuple[AccountType, float, bool, str]:
        """
        Determines the account type and denomination factor using multi-signal classification.
        Returns: (AccountType, denomination_factor, is_verified, status_code)
        """
        curr = (currency or "").strip().upper()
        srv = (server or "").strip().lower()
        comp = (company or "").strip().lower()

        # Signal 1: Native cent currencies
        if curr in self.KNOWN_CENT_CURRENCIES:
            return AccountType.CENT_USC, 100.0, True, "VERIFIED"

        # Signal 2: Server or company names explicitly designating Cent accounts
        if "cent" in srv or "cent" in comp:
            return AccountType.CENT_USC, 100.0, True, "VERIFIED"

        # Signal 3: Symbol naming inspection (.c or c suffix on major FX/Gold)
        if symbol_sample:
            cent_symbols = [s for s in symbol_sample if s.endswith(".c") or (s.endswith("c") and len(s) == 7)]
            micro_symbols = [s for s in symbol_sample if "micro" in s.lower() or s.endswith(".m") or (s.endswith("m") and len(s) == 7)]
            if len(cent_symbols) >= 2:
                return AccountType.CENT_USC, 100.0, True, "VERIFIED"
            if len(micro_symbols) >= 2:
                return AccountType.MICRO_USD, 1.0, True, "VERIFIED"

        # Signal 4: Micro accounts (USD currency, micro in server or symbols)
        if "micro" in srv or "micro" in comp:
            return AccountType.MICRO_USD, 1.0, True, "VERIFIED"

        # Signal 5: Standard USD
        if curr == "USD":
            # If balance is small (< $100) on standard symbols, it functions as a micro-capitalized standard account
            if 0.0 < balance < 100.0:
                return AccountType.MICRO_USD, 1.0, True, "VERIFIED"
            return AccountType.STANDARD_USD, 1.0, True, "VERIFIED"

        # Signal 6: Standard other currency (EUR, GBP, JPY, etc.)
        if curr in self.KNOWN_STANDARD_CURRENCIES:
            return AccountType.STANDARD_OTHER, 1.0, True, "VERIFIED"

        # Unverified currency
        return AccountType.UNKNOWN, 1.0, False, "ACCOUNT_CURRENCY_UNVERIFIED"

    def normalize_account_snapshot(
        self,
        account_raw: Any,
        terminal_raw: Any = None,
        symbols_sample: Optional[List[str]] = None
    ) -> NormalizedAccountSnapshot:
        """
        Builds a NormalizedAccountSnapshot from MT5 account_info and terminal_info.
        Ensures strict single conversion and preserves native figures.
        """
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        login = int(_get(account_raw, "login", 0) or 0)
        server = str(_get(account_raw, "server", "") or "").strip()
        company = str(_get(account_raw, "company", "") or "").strip()
        currency = str(_get(account_raw, "currency", "USD") or "USD").strip().upper()
        leverage = int(_get(account_raw, "leverage", 100) or 100)
        
        native_balance = float(_get(account_raw, "balance", 0.0) or 0.0)
        native_equity = float(_get(account_raw, "equity", native_balance) or native_balance)
        native_free_margin = float(_get(account_raw, "margin_free", _get(account_raw, "free_margin", native_equity)) or native_equity)
        native_margin = float(_get(account_raw, "margin", 0.0) or 0.0)
        margin_level = float(_get(account_raw, "margin_level", 0.0) or 0.0)

        trade_mode_int = int(_get(account_raw, "trade_mode", 0) or 0)
        trade_mode = "DEMO" if trade_mode_int == 0 else "REAL"
        margin_mode_int = int(_get(account_raw, "margin_mode", 2) or 2)
        margin_mode_str = "NETTING" if margin_mode_int == 1 else "HEDGING"

        # Classification
        acct_type, denom_factor, is_verified, status_code = self.detect_account_type(
            currency=currency,
            balance=native_balance,
            server=server,
            company=company,
            symbol_sample=symbols_sample
        )

        # Single conversion to calculation currency (USD)
        rate_to_usd = self._rates_to_usd.get(currency, 1.0)
        if acct_type.is_cent:
            norm_balance = round(native_balance / denom_factor, 2)
            norm_equity = round(native_equity / denom_factor, 2)
            norm_free_margin = round(native_free_margin / denom_factor, 2)
            norm_margin = round(native_margin / denom_factor, 2)
        else:
            norm_balance = round(native_balance * rate_to_usd, 2)
            norm_equity = round(native_equity * rate_to_usd, 2)
            norm_free_margin = round(native_free_margin * rate_to_usd, 2)
            norm_margin = round(native_margin * rate_to_usd, 2)

        return NormalizedAccountSnapshot(
            login=login,
            masked_login=self.mask_login(login),
            server=server,
            company=company,
            account_type=acct_type,
            currency=currency,
            calculation_currency="USD",
            denomination_factor=denom_factor,
            leverage=leverage,
            trade_mode=trade_mode,
            margin_mode=margin_mode_int,
            margin_mode_str=margin_mode_str,
            native_balance=native_balance,
            native_equity=native_equity,
            native_free_margin=native_free_margin,
            native_margin=native_margin,
            margin_level=margin_level,
            normalized_balance=norm_balance,
            normalized_equity=norm_equity,
            normalized_free_margin=norm_free_margin,
            normalized_margin=norm_margin,
            is_verified=is_verified,
            verification_status=status_code,
        )

    def resolve_adaptive_thresholds(
        self,
        snapshot: NormalizedAccountSnapshot,
        configured_risk_pct: float = 0.25,
        reference_target_usd: float = 20.0,
        max_aggregate_risk_pct: float = 0.50,
        daily_loss_pct: float = 1.0,
    ) -> AdaptiveMonetaryThresholds:
        """
        Derives account-proportionate monetary thresholds from normalized equity.
        Maintains reference standard values for $10k accounts, scales smoothly for micro/cent accounts.
        """
        norm_equity = snapshot.normalized_equity if snapshot.normalized_equity > 0 else snapshot.normalized_balance
        ref_equity = self.REFERENCE_STANDARD_EQUITY

        # For Standard USD accounts >= $5,000, keep full configured reference targets
        if snapshot.account_type == AccountType.STANDARD_USD and norm_equity >= 5000.0:
            scale_ratio = 1.0
            target_usd = reference_target_usd
        else:
            # Scale proportionally with a floor and sensible single-scalp cap (max 2% gain per scalp)
            scale_ratio = max(0.001, norm_equity / ref_equity)
            target_usd = reference_target_usd * scale_ratio
            # Small account guard: Single scalp target should never require > 5% account gain
            if norm_equity > 0 and target_usd > norm_equity * 0.05:
                target_usd = max(0.05, round(norm_equity * 0.02, 2))
            target_usd = max(0.05, round(target_usd, 2))

        # Convert target to native units
        if snapshot.account_type.is_cent:
            target_native = round(target_usd * snapshot.denomination_factor, 2)
        else:
            rate = self._rates_to_usd.get(snapshot.currency, 1.0)
            target_native = round(target_usd / rate, 2) if rate > 0 else target_usd

        # Risk budget calculations
        # R_max = Normalized_equity * (Risk% / 100)
        risk_pct = min(2.0, max(0.01, configured_risk_pct))
        max_risk_usd = round(norm_equity * (risk_pct / 100.0), 4)
        
        if snapshot.account_type.is_cent:
            max_risk_native = round(snapshot.native_equity * (risk_pct / 100.0), 2)
        else:
            max_risk_native = max_risk_usd

        # Portfolio aggregate risk budget
        max_portfolio_risk_native = round(snapshot.native_equity * (max_aggregate_risk_pct / 100.0), 2)
        daily_loss_native = round(snapshot.native_equity * (daily_loss_pct / 100.0), 2)

        return AdaptiveMonetaryThresholds(
            reference_equity=ref_equity,
            current_equity=norm_equity,
            equity_scale_ratio=scale_ratio,
            target_net_profit_usd=target_usd,
            target_net_profit_native=target_native,
            min_profit_filter_native=round(target_native * 0.5, 2),
            risk_percentage=risk_pct,
            max_permitted_risk_usd=max_risk_usd,
            max_permitted_risk_native=max_risk_native,
            max_aggregate_risk_pct=max_aggregate_risk_pct,
            max_portfolio_monetary_risk_native=max_portfolio_risk_native,
            daily_loss_limit_pct=daily_loss_pct,
            daily_loss_limit_native=daily_loss_native,
        )
