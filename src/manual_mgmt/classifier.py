"""
Deterministic Position Classifier.
Classifies open MT5 positions into BOT_OWN, MANUAL, OTHER_EA, EXCLUDED, or UNKNOWN.
Tags: [SAFETY], [DERIVED]
"""

from __future__ import annotations
import logging
import re
from typing import Any, List, Optional, Sequence

from src.core.contracts import Position
from src.manual_mgmt.contracts import PositionClass

logger = logging.getLogger("ManualMgmtClassifier")

# MT5 Deal Reason Constants (MetaTrader 5 API)
DEAL_REASON_CLIENT = 0
DEAL_REASON_MOBILE = 1
DEAL_REASON_WEB = 2
DEAL_REASON_EXPERT = 3
DEAL_REASON_SL = 4
DEAL_REASON_TP = 5


def clean_base_symbol(symbol: str) -> str:
    """Strips broker suffixes/prefixes (e.g. 'EURUSD.m' -> 'EURUSD', 'BTCUSD_i' -> 'BTCUSD')."""
    match = re.match(r"^([A-Za-z0-9]+)", symbol)
    return match.group(1).upper() if match else symbol.upper()


def classify_position(
    pos: Position,
    bot_magic: int = 100101,
    allowed_symbols: Optional[Sequence[str]] = None,
    deals_history: Optional[List[Any]] = None
) -> PositionClass:
    """
    Deterministically classifies a position. First match wins. [SAFETY]
    1. BOT_OWN: pos.magic == bot_magic
    2. EXCLUDED: comment has #bot:off or symbol not in allowed_symbols
    3. OTHER_EA: pos.magic != 0 and pos.magic != bot_magic
    4. MANUAL: pos.magic == 0 (with optional verification via opening deal reason)
    5. UNKNOWN: fallback if ticket data corrupted
    """
    try:
        magic = int(getattr(pos, "magic", 0) or 0)
        comment = str(getattr(pos, "comment", "") or "").lower()
        symbol = str(getattr(pos, "symbol", "") or "")

        # 1. BOT_OWN
        if magic == bot_magic:
            return PositionClass.BOT_OWN

        # 2. EXCLUDED: explicit opt-out tag in comment
        if "#bot:off" in comment or "#ignore" in comment or "#manual:off" in comment:
            return PositionClass.EXCLUDED

        # 2a. Explicit opt-in override in comment
        if "#manual:on" in comment or "#bot:manage" in comment:
            return PositionClass.MANUAL

        # 2b. EXCLUDED: symbol not in allowed list (if configured)
        if allowed_symbols:
            base_sym = clean_base_symbol(symbol)
            allowed_bases = {clean_base_symbol(s) for s in allowed_symbols}
            if symbol not in allowed_symbols and base_sym not in allowed_bases:
                return PositionClass.EXCLUDED

        # 3. OTHER_EA: distinct non-zero magic number
        if magic != 0:
            return PositionClass.OTHER_EA

        # 4. Examine opening deal reason if deal history provided
        if deals_history:
            ticket = int(pos.ticket)
            opening_deals = [
                d for d in deals_history
                if getattr(d, "position_id", getattr(d, "position", 0)) == ticket
                and getattr(d, "entry", 0) == 0  # In-deal
            ]
            if opening_deals:
                reason = getattr(opening_deals[0], "reason", -1)
                if reason == DEAL_REASON_EXPERT:
                    return PositionClass.OTHER_EA
                if reason in (DEAL_REASON_CLIENT, DEAL_REASON_MOBILE, DEAL_REASON_WEB):
                    return PositionClass.MANUAL

        # 4b. Standard MANUAL (magic == 0)
        if magic == 0:
            return PositionClass.MANUAL

        return PositionClass.UNKNOWN
    except Exception as e:
        logger.error(f"[CLASSIFICATION_ERROR] Failed to classify ticket #{getattr(pos, 'ticket', 0)}: {e}")
        return PositionClass.UNKNOWN
