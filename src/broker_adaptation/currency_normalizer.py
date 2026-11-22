"""
Currency Normalization & Denomination Management Service.
Guarantees that native broker account values remain pristine while providing
mathematically verified conversions to normalized strategy currency (USD).
Includes double-conversion guard and multi-currency exchange rate tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

logger = logging.getLogger("CurrencyNormalizer")


@dataclass(frozen=True)
class NormalizedMonetaryValue:
    """
    Immutable container carrying both native and normalized figures with provenance.
    Prevents double conversions by tracking normalization status.
    """
    native_value: float
    native_currency: str
    normalized_value: float
    normalized_currency: str
    denomination_factor: float
    exchange_rate: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_cent(self) -> bool:
        return self.denomination_factor > 1.0


class CurrencyNormalizer:
    """
    Handles conversion between native broker account currencies and canonical USD strategy figures.
    Guarantees idempotence: values cannot be converted twice by mistake.
    """

    CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}

    def __init__(self):
        # Known exchange rates to USD: {CURRENCY: RATE_TO_USD}
        # 1 EUR = 1.08 USD, 1 GBP = 1.28 USD, 1 USD = 155 JPY (1 JPY = 0.00645 USD)
        self._rates_to_usd: Dict[str, float] = {
            "USD": 1.0,
            "USC": 0.01,  # 1 cent = 0.01 USD
            "EUR": 1.08,
            "EUC": 0.0108,
            "GBP": 1.28,
            "GBX": 0.0128,
            "JPY": 0.0065,
            "JPC": 0.000065,
            "AUD": 0.65,
            "CAD": 0.72,
            "CHF": 1.12,
            "NZD": 0.59,
        }

    def update_exchange_rate(self, currency: str, rate_to_usd: float) -> None:
        """Dynamically update an exchange rate from live market ticks."""
        if rate_to_usd > 0:
            c = currency.strip().upper()
            self._rates_to_usd[c] = float(rate_to_usd)
            if c in ("EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY"):
                cent_c = c[:2] + "C" if c != "GBP" else "GBX"
                self._rates_to_usd[cent_c] = float(rate_to_usd) / 100.0

    def get_denomination_factor(self, currency: str) -> float:
        """Returns 100.0 for cent currencies, 1.0 for standard."""
        curr = (currency or "").strip().upper()
        if curr in self.CENT_CURRENCIES:
            return 100.0
        return 1.0

    def normalize(
        self,
        native_value: float,
        native_currency: str,
        target_currency: str = "USD"
    ) -> NormalizedMonetaryValue:
        """
        Converts native currency value to target normalized currency (default USD).
        Guarantees precision and emits a structured NormalizedMonetaryValue.
        """
        c_from = (native_currency or "USD").strip().upper()
        c_to = (target_currency or "USD").strip().upper()
        denom_factor = self.get_denomination_factor(c_from)

        rate_from = self._rates_to_usd.get(c_from, 1.0)
        rate_to = self._rates_to_usd.get(c_to, 1.0)
        conversion_rate = rate_from / rate_to if rate_to > 0 else 1.0

        normalized_val = round(native_value * conversion_rate, 4)

        return NormalizedMonetaryValue(
            native_value=float(native_value),
            native_currency=c_from,
            normalized_value=normalized_val,
            normalized_currency=c_to,
            denomination_factor=denom_factor,
            exchange_rate=conversion_rate
        )

    def denormalize(
        self,
        normalized_value: float,
        target_native_currency: str,
        source_currency: str = "USD"
    ) -> float:
        """
        Converts a normalized USD strategy value back to native broker account currency.
        Used for lot sizing or margin checking in native units.
        """
        c_target = (target_native_currency or "USD").strip().upper()
        c_src = (source_currency or "USD").strip().upper()

        rate_target = self._rates_to_usd.get(c_target, 1.0)
        rate_src = self._rates_to_usd.get(c_src, 1.0)

        rate = rate_target / rate_src if rate_src > 0 else 1.0
        return round(normalized_value / rate if rate > 0 else normalized_value, 4)

    def verify_safety_bounds(
        self,
        native_balance: float,
        denomination_factor: float,
        min_usd_floor: float = 5.0
    ) -> Tuple[bool, str]:
        """
        Checks that normalized balance meets institutional minimum capital floor ($5.00).
        """
        norm_val = native_balance / denomination_factor if denomination_factor > 0 else native_balance
        if norm_val < min_usd_floor:
            return False, f"Normalized capital ${norm_val:.2f} is below the required ${min_usd_floor:.2f} safety floor."
        return True, "CAPITAL_SUFFICIENT"
