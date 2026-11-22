"""
Broker Symbol Specification Extractor & Validator.
Parses raw MT5 symbol structures or dictionaries into a comprehensive,
fully validated BrokerSymbolSpec object with volume and price quantization utilities.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SymbolSpecification")


@dataclass
class BrokerSymbolSpec:
    name: str
    canonical_name: str
    currency_base: str = "USD"
    currency_profit: str = "USD"
    currency_margin: str = "USD"
    digits: int = 5
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0
    contract_size: float = 100000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    volume_limit: float = 0.0
    trade_mode: int = 4  # 0=DISABLED, 1=LONG_ONLY, 2=SHORT_ONLY, 3=CLOSE_ONLY, 4=FULL
    execution_mode: int = 2  # 0=REQUEST, 1=INSTANT, 2=MARKET, 3=EXCHANGE
    filling_mode: int = 1  # 1=FOK, 2=IOC, 4=RETURN
    stops_level: int = 0  # points
    freeze_level: int = 0  # points
    margin_initial: float = 0.0
    margin_maintenance: float = 0.0
    spread: int = 0
    bid: float = 0.0
    ask: float = 0.0
    path: str = ""
    description: str = ""
    supported_filling_modes: List[str] = field(default_factory=list)
    discovery_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_tradable(self) -> bool:
        """Determines if the symbol is tradable for both BUY and SELL."""
        return self.trade_mode == 4

    @property
    def allows_fok(self) -> bool:
        return "FOK" in self.supported_filling_modes or (self.filling_mode & 1) != 0

    @property
    def allows_ioc(self) -> bool:
        return "IOC" in self.supported_filling_modes or (self.filling_mode & 2) != 0

    @property
    def allows_return(self) -> bool:
        return "RETURN" in self.supported_filling_modes or (self.filling_mode & 4) != 0

    def round_price(self, price: float) -> float:
        """Rounds price strictly to symbol digits."""
        return round(price, self.digits)

    def quantize_volume(self, volume: float) -> float:
        """
        Quantizes volume strictly DOWN to volume_step to prevent inflating risk.
        Clamps between volume_min and volume_max.
        Returns 0.0 if volume is below volume_min.
        """
        step = self.volume_step if self.volume_step > 0 else 0.01
        floored = math.floor((volume + 1e-9) / step) * step
        if floored < self.volume_min - 1e-9:
            return 0.0
        return min(round(floored, 4), self.volume_max)

    def calculate_stop_buffer_points(self) -> int:
        """
        Returns minimum distance points required from current price for SL/TP,
        incorporating stops_level plus a safety spread buffer.
        """
        base_stops = max(0, self.stops_level)
        spread_pts = max(0, self.spread)
        return max(base_stops, spread_pts // 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "canonical_name": self.canonical_name,
            "currency_base": self.currency_base,
            "currency_profit": self.currency_profit,
            "currency_margin": self.currency_margin,
            "digits": self.digits,
            "point": self.point,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "contract_size": self.contract_size,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "trade_mode": self.trade_mode,
            "execution_mode": self.execution_mode,
            "filling_mode": self.filling_mode,
            "stops_level": self.stops_level,
            "freeze_level": self.freeze_level,
            "supported_filling_modes": self.supported_filling_modes,
            "is_tradable": self.is_tradable,
            "discovery_timestamp": self.discovery_timestamp,
        }


def extract_symbol_spec(raw_obj: Any, canonical_name: str) -> BrokerSymbolSpec:
    """
    Extracts a BrokerSymbolSpec from an MT5 SymbolInfo object, a dictionary, or a mock object.
    """
    def _val(attr: str, default: Any) -> Any:
        if hasattr(raw_obj, attr):
            v = getattr(raw_obj, attr)
            if v is not None:
                return v
        if isinstance(raw_obj, dict) and attr in raw_obj:
            v = raw_obj[attr]
            if v is not None:
                return v
        return default

    name = str(_val("name", _val("symbol", canonical_name))).strip() or canonical_name
    digits = int(_val("digits", 5))
    point = float(_val("point", 10 ** -digits))
    tick_size = float(_val("trade_tick_size", _val("tick_size", point)))
    tick_value = float(_val("trade_tick_value", _val("tick_value", 1.0)))
    contract_size = float(_val("trade_contract_size", _val("contract_size", 100000.0)))
    volume_min = float(_val("volume_min", 0.01))
    volume_max = float(_val("volume_max", 100.0))
    volume_step = float(_val("volume_step", 0.01))
    volume_limit = float(_val("volume_limit", 0.0))
    trade_mode = int(_val("trade_mode", 4))
    execution_mode = int(_val("execution_mode", 2))
    filling_mode = int(_val("filling_mode", 1))
    stops_level = int(_val("trade_stops_level", _val("stops_level", 0)))
    freeze_level = int(_val("trade_freeze_level", _val("freeze_level", 0)))
    currency_base = str(_val("currency_base", "USD"))
    currency_profit = str(_val("currency_profit", "USD"))
    currency_margin = str(_val("currency_margin", "USD"))
    spread = int(_val("spread", 0))
    bid = float(_val("bid", 0.0))
    ask = float(_val("ask", 0.0))
    path = str(_val("path", ""))
    description = str(_val("description", ""))

    supported_filling_modes: List[str] = []
    # In MT5: 1=FOK (SYMBOL_FILLING_FOK), 2=IOC (SYMBOL_FILLING_IOC)
    if (filling_mode & 1) != 0 or filling_mode == 0:
        supported_filling_modes.append("FOK")
    if (filling_mode & 2) != 0:
        supported_filling_modes.append("IOC")
    if (filling_mode & 4) != 0:
        supported_filling_modes.append("RETURN")
    if not supported_filling_modes:
        supported_filling_modes.append("FOK")

    return BrokerSymbolSpec(
        name=name,
        canonical_name=canonical_name,
        currency_base=currency_base,
        currency_profit=currency_profit,
        currency_margin=currency_margin,
        digits=digits,
        point=point,
        tick_size=tick_size,
        tick_value=tick_value,
        contract_size=contract_size,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        volume_limit=volume_limit,
        trade_mode=trade_mode,
        execution_mode=execution_mode,
        filling_mode=filling_mode,
        stops_level=stops_level,
        freeze_level=freeze_level,
        spread=spread,
        bid=bid,
        ask=ask,
        path=path,
        description=description,
        supported_filling_modes=supported_filling_modes,
    )
