"""
Account and Broker Normalization Engine for ATI.
Resolves broker aliases to approved canonical instruments (XAUUSD, BTCUSD, USDJPY),
enforces the non-negotiable 3-symbol whitelist, handles broker suffixes,
and normalizes cent/micro accounts to standard financial equivalents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple

logger = logging.getLogger("ATI.Normalization")

# Strictly authorized 2-symbol canonical universe (Gold and Bitcoin only)
APPROVED_CANONICAL_SYMBOLS: Tuple[str, ...] = ("XAUUSD", "BTCUSD")

# Common broker symbol suffixes and alias variations
CANONICAL_ALIASES: Dict[str, Set[str]] = {
    "XAUUSD": {
        "XAUUSD", "GOLD", "XAU",
        "XAUUSD.M", "XAUUSDM", "XAUUSD.MICRO",
        "GOLD.M", "GOLDM",
        "XAUUSD.C", "XAUUSDC", "GOLD.C", "GOLDC", "XAUUSD-CENT", "XAUUSD.CENT",
        "XAUUSD.PRO", "XAUUSD.RAW", "XAUUSD.ECN", "XAUUSD.STD",
    },
    "BTCUSD": {
        "BTCUSD", "BITCOIN", "BTC",
        "BTCUSD.M", "BTCUSDM", "BTCUSD.MICRO",
        "BTCUSD.C", "BTCUSDC", "BITCOIN.C", "BTCUSD-CENT", "BTCUSD.CENT",
        "BTCUSD.PRO", "BTCUSD.RAW", "BTCUSD.ECN", "BTCUSD.STD",
    },
}


@dataclass(frozen=True)
class NormalizedAccountContext:
    account_number: int
    account_currency: str
    account_type: str  # STANDARD, CENT, MICRO
    denomination_factor: float
    leverage: int
    trade_mode: str  # DEMO or REAL


class AccountBrokerNormalizer:
    """
    Normalizes broker symbols and financial metrics across account types.
    Strictly forbids expanding the canonical 3-symbol universe.
    """

    @classmethod
    def resolve_canonical_symbol(cls, broker_symbol: str) -> Optional[str]:
        """
        Maps a broker-specific symbol to its canonical approved name (XAUUSD, BTCUSD, USDJPY).
        Returns None if the symbol cannot be mapped to one of the 3 approved instruments.
        """
        if not broker_symbol:
            return None
        clean = broker_symbol.strip().upper()

        # Direct canonical match
        if clean in APPROVED_CANONICAL_SYMBOLS:
            return clean

        # Alias lookup
        for canon, aliases in CANONICAL_ALIASES.items():
            if clean in aliases:
                return canon

        # Dynamic suffix removal check (e.g. "XAUUSD.r", "BTCUSD_i", etc.)
        for canon in APPROVED_CANONICAL_SYMBOLS:
            if clean.startswith(canon):
                remainder = clean[len(canon):]
                # If remainder is a valid suffix separator like . or _ or - or single suffix letter
                if remainder.startswith((".", "_", "-", "+")) or len(remainder) <= 3:
                    return canon

        # For "GOLD" variations
        if clean.startswith("GOLD"):
            return "XAUUSD"

        # Not in approved universe
        logger.warning(f"[NORMALIZATION] Rejected symbol '{broker_symbol}': Outside approved 3-instrument universe.")
        return None

    @classmethod
    def is_symbol_approved(cls, broker_symbol: str) -> bool:
        return cls.resolve_canonical_symbol(broker_symbol) is not None

    @classmethod
    def detect_account_context(
        cls,
        account_number: int = 0,
        currency: str = "USD",
        company: str = "",
        server: str = "",
        trade_mode: str = "DEMO",
        leverage: int = 100,
    ) -> NormalizedAccountContext:
        """
        Detects cent, micro, or standard account properties from account currency and broker server.
        """
        curr = currency.upper().strip()
        comp = company.lower()
        srv = server.lower()

        # Check cent indicators
        is_cent = (
            curr in ("USDC", "EUROC", "GBPC", "CENT", "USCENT")
            or "cent" in comp
            or "cent" in srv
        )

        # Check micro indicators
        is_micro = "micro" in comp or "micro" in srv

        if is_cent:
            acc_type = "CENT"
            denom = 100.0
        elif is_micro:
            acc_type = "MICRO"
            denom = 1.0  # micro volume scaled, nominal currency usually 1.0
        else:
            acc_type = "STANDARD"
            denom = 1.0

        return NormalizedAccountContext(
            account_number=account_number,
            account_currency=curr,
            account_type=acc_type,
            denomination_factor=denom,
            leverage=leverage,
            trade_mode=trade_mode,
        )

    @classmethod
    def normalize_monetary_amount(cls, amount: float, denomination_factor: float) -> float:
        """Normalizes cent/standard nominal amounts to true USD equivalent."""
        factor = denomination_factor if denomination_factor > 0 else 1.0
        return round(amount / factor, 4)
