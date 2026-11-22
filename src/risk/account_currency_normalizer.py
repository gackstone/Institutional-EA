"""
Account Currency Normalizer & Monetary Conversion Engine.
Handles conversion between native broker account currency (including Cent denominations: USC, EUC, etc.)
and normalized internal accounting currency (USD).

Key Principles:
1. Never assume every account displaying 100,000 is a cent account.
2. Never assume every account using USD is a standard account.
3. Distinguish between Account Denomination, Reporting Currency, Broker Contract Specs, and User Risk Budget.
4. If an account is UNKNOWN, fail closed: do NOT divide by 100 without verified evidence.
5. Provide bidirectional conversion methods for native <-> normalized values.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from src.core.account_detector import AccountType, AccountDetectionResult

logger = logging.getLogger("AccountCurrencyNormalizer")


class SizingMode(str, Enum):
    RISK_PERCENT = "RISK_PERCENT"
    FIXED_LOT = "FIXED_LOT"
    FIXED_RISK = "FIXED_RISK"
    BROKER_MIN_VOLUME = "BROKER_MIN_VOLUME"


@dataclass(frozen=True)
class NormalizedMonetaryValue:
    native_value: float
    normalized_value: float
    native_currency: str
    normalized_currency: str = "USD"
    scale_factor: float = 1.0
    is_cent_account: bool = False

    def __str__(self) -> str:
        if self.is_cent_account:
            return f"{self.native_value:,.2f} {self.native_currency} (${self.normalized_value:,.2f} {self.normalized_currency})"
        return f"${self.normalized_value:,.2f} {self.normalized_currency}"


class AccountCurrencyNormalizer:
    """
    Normalizes account monetary balances, equity, risk budgets, and trade P&L.
    Preserves native values for MT5 execution while providing standardized USD values for risk.
    """

    def __init__(
        self,
        account_type: AccountType = AccountType.STANDARD,
        native_currency: str = "USD",
        denomination_factor: float = 1.0,
        manual_override_confirmed: bool = False,
    ):
        self.account_type = account_type
        self.native_currency = (native_currency or "USD").strip().upper()
        self.manual_override_confirmed = manual_override_confirmed

        # Only allow cent scaling if account is confirmed CENT or manual override confirmed
        if self.account_type.is_cent or (manual_override_confirmed and denomination_factor > 1.0):
            self.denomination_factor = denomination_factor if denomination_factor > 0 else 100.0
            self.is_cent = True
        else:
            self.denomination_factor = 1.0
            self.is_cent = False

    @classmethod
    def from_detection_result(cls, detection: AccountDetectionResult) -> AccountCurrencyNormalizer:
        """Constructs a normalizer instance from an AccountDetectionResult."""
        return cls(
            account_type=detection.account_type,
            native_currency=detection.account_currency,
            denomination_factor=detection.denomination_factor,
            manual_override_confirmed=detection.override_confirmed,
        )

    def to_normalized(self, native_amount: float) -> NormalizedMonetaryValue:
        """Converts native account currency to normalized USD."""
        norm_val = native_amount / self.denomination_factor
        return NormalizedMonetaryValue(
            native_value=native_amount,
            normalized_value=norm_val,
            native_currency=self.native_currency,
            normalized_currency="USD",
            scale_factor=self.denomination_factor,
            is_cent_account=self.is_cent,
        )

    def to_native(self, normalized_amount: float) -> NormalizedMonetaryValue:
        """Converts normalized USD to native account currency."""
        native_val = normalized_amount * self.denomination_factor
        return NormalizedMonetaryValue(
            native_value=native_val,
            normalized_value=normalized_amount,
            native_currency=self.native_currency,
            normalized_currency="USD",
            scale_factor=self.denomination_factor,
            is_cent_account=self.is_cent,
        )

    def calculate_risk_budget(
        self,
        equity: float,
        risk_percent: float = 1.0,
        fixed_monetary_risk: Optional[float] = None,
        sizing_mode: SizingMode = SizingMode.RISK_PERCENT,
    ) -> Tuple[NormalizedMonetaryValue, Optional[str]]:
        """
        Calculates intended monetary risk budget in both native and normalized denominations.
        Returns (NormalizedMonetaryValue, error_reason).
        """
        # Equity passed here might be native or normalized
        # If native equity is passed:
        norm_equity = equity if not self.is_cent else equity / self.denomination_factor

        if sizing_mode == SizingMode.FIXED_RISK and fixed_monetary_risk is not None:
            # Fixed monetary risk is specified in normalized USD
            norm_budget = fixed_monetary_risk
            native_budget = norm_budget * self.denomination_factor
        else:
            # Percentage of normalized equity
            clamped_pct = max(0.01, min(risk_percent, 2.0))  # Institutional R9 hard cap 2.0%
            norm_budget = norm_equity * (clamped_pct / 100.0)
            native_budget = norm_budget * self.denomination_factor

        if norm_budget <= 0.0:
            return (
                self.to_normalized(0.0),
                "Invalid risk budget: Calculated risk must be strictly greater than zero.",
            )

        val = NormalizedMonetaryValue(
            native_value=native_budget,
            normalized_value=norm_budget,
            native_currency=self.native_currency,
            normalized_currency="USD",
            scale_factor=self.denomination_factor,
            is_cent_account=self.is_cent,
        )
        return val, None

    def calculate_loss_per_lot(
        self,
        sl_distance_price: float,
        tick_size: float,
        tick_value: float,
    ) -> Tuple[float, float]:
        """
        Calculates loss per lot in native currency and normalized USD.
        In MT5 on a cent account, tick_value is already denominated in the account currency (cents).
        Returns (loss_per_lot_native, loss_per_lot_normalized).
        """
        if tick_size <= 0.0 or tick_value <= 0.0 or sl_distance_price <= 0.0:
            return 0.0, 0.0

        ticks = sl_distance_price / tick_size
        loss_native = ticks * tick_value
        loss_normalized = loss_native / self.denomination_factor
        return loss_native, loss_normalized
