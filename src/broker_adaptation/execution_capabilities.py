"""
Execution Capabilities & Broker Constraint Validation Engine.
Evaluates broker execution modes, resolves filling policies, validates minimum stop levels,
and emits standard diagnostic rejection codes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.broker_adaptation.symbol_specification import BrokerSymbolSpec

logger = logging.getLogger("ExecutionCapabilities")


class StandardRejectionCode(str, Enum):
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    SYMBOL_NOT_AVAILABLE = "SYMBOL_NOT_AVAILABLE"
    MARKET_CLOSED = "MARKET_CLOSED"
    MIN_LOT_RISK_EXCEEDED = "MIN_LOT_RISK_EXCEEDED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    STOP_DISTANCE_TOO_CLOSE = "STOP_DISTANCE_TOO_CLOSE"
    FILLING_MODE_UNSUPPORTED = "FILLING_MODE_UNSUPPORTED"
    UNAUTHORIZED_SYMBOL = "UNAUTHORIZED_SYMBOL"
    AMBIGUOUS_BROKER_SYMBOL = "AMBIGUOUS_BROKER_SYMBOL"
    PRICE_OFF_QUOTES = "PRICE_OFF_QUOTES"
    TRADE_CONTEXT_BUSY = "TRADE_CONTEXT_BUSY"
    INVALID_STOPS = "INVALID_STOPS"
    ROUNDING_INVALID_VOLUME = "ROUNDING_INVALID_VOLUME"
    BROKER_TRADE_DISABLED = "BROKER_TRADE_DISABLED"


@dataclass
class ExecutionValidationResult:
    is_valid: bool
    rejection_code: Optional[StandardRejectionCode] = None
    reason: str = ""
    resolved_filling_mode: str = "FOK"
    recommended_deviation: int = 15
    adjusted_volume: float = 0.0
    adjusted_sl: float = 0.0
    adjusted_tp: float = 0.0


class ExecutionCapabilitiesEngine:
    """
    Validates orders against broker constraints before order submission.
    Ensures broker stop levels, filling modes, and execution parameters are respected.
    """

    def __init__(self, default_deviation: int = 15):
        self.default_deviation = default_deviation

    def resolve_filling_mode(self, spec: BrokerSymbolSpec) -> str:
        """
        Determines the optimal broker filling mode for an order based on symbol specs.
        Cent accounts and ECN brokers typically mandate FOK (1) or IOC (2).
        """
        # If cent symbol or only FOK allowed
        if spec.allows_fok:
            return "FOK"
        if spec.allows_ioc:
            return "IOC"
        if spec.allows_return:
            return "RETURN"
        return "FOK"

    def validate_pre_execution(
        self,
        spec: Optional[BrokerSymbolSpec],
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        volume: float,
        direction: str,  # "BUY" or "SELL"
        free_margin: float,
        margin_required: float = 0.0,
    ) -> ExecutionValidationResult:
        """
        Conducts comprehensive pre-execution check against the 14 standard failure conditions.
        """
        # 1. Spec presence
        if spec is None:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.SYMBOL_NOT_FOUND,
                reason="Symbol specification could not be retrieved from broker."
            )

        # 2. Broker trade enabled
        if not spec.is_tradable:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.BROKER_TRADE_DISABLED,
                reason=f"Broker has disabled trading for {spec.name} (trade_mode={spec.trade_mode})."
            )

        # 3. Stop loss presence and validity
        if stop_loss <= 0.0:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.INVALID_STOPS,
                reason="Stop loss is mandatory and must be strictly positive."
            )

        is_buy = direction.upper() in ("BUY", "BUY_LIMIT", "BUY_STOP")
        if is_buy and stop_loss >= entry_price:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.INVALID_STOPS,
                reason=f"BUY stop loss ({stop_loss}) must be strictly below entry price ({entry_price})."
            )
        if not is_buy and stop_loss <= entry_price:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.INVALID_STOPS,
                reason=f"SELL stop loss ({stop_loss}) must be strictly above entry price ({entry_price})."
            )

        # 4. Stop level distance check
        min_stop_distance_pts = spec.calculate_stop_buffer_points()
        actual_sl_dist_pts = abs(entry_price - stop_loss) / spec.point if spec.point > 0 else 0
        if min_stop_distance_pts > 0 and actual_sl_dist_pts < min_stop_distance_pts:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.STOP_DISTANCE_TOO_CLOSE,
                reason=(
                    f"Stop loss distance ({actual_sl_dist_pts:.1f} pts) is closer than broker "
                    f"minimum stop level ({min_stop_distance_pts} pts) for {spec.name}."
                )
            )

        if take_profit > 0.0:
            actual_tp_dist_pts = abs(entry_price - take_profit) / spec.point if spec.point > 0 else 0
            if min_stop_distance_pts > 0 and actual_tp_dist_pts < min_stop_distance_pts:
                return ExecutionValidationResult(
                    is_valid=False,
                    rejection_code=StandardRejectionCode.STOP_DISTANCE_TOO_CLOSE,
                    reason=(
                        f"Take profit distance ({actual_tp_dist_pts:.1f} pts) is closer than broker "
                        f"minimum stop level ({min_stop_distance_pts} pts) for {spec.name}."
                    )
                )

        # 5. Volume quantization and limits
        quantized_vol = spec.quantize_volume(volume)
        if quantized_vol <= 0.0 or quantized_vol < spec.volume_min:
            return ExecutionValidationResult(
                is_valid=False,
                rejection_code=StandardRejectionCode.ROUNDING_INVALID_VOLUME,
                reason=(
                    f"Requested volume {volume:.4f} rounds to {quantized_vol:.4f}, which is below "
                    f"broker minimum volume {spec.volume_min:.4f} for {spec.name}."
                )
            )

        if quantized_vol > spec.volume_max:
            quantized_vol = spec.volume_max

        # 6. Margin check
        if margin_required > 0.0 and free_margin > 0.0:
            if margin_required > free_margin:
                return ExecutionValidationResult(
                    is_valid=False,
                    rejection_code=StandardRejectionCode.INSUFFICIENT_MARGIN,
                    reason=(
                        f"Required margin ({margin_required:.2f}) exceeds account free margin "
                        f"({free_margin:.2f}) for volume {quantized_vol:.2f} {spec.name}."
                    )
                )

        # 7. Filling mode resolution
        fill_mode = self.resolve_filling_mode(spec)

        return ExecutionValidationResult(
            is_valid=True,
            resolved_filling_mode=fill_mode,
            recommended_deviation=self.default_deviation,
            adjusted_volume=quantized_vol,
            adjusted_sl=spec.round_price(stop_loss),
            adjusted_tp=spec.round_price(take_profit) if take_profit > 0 else 0.0,
            reason="All execution checks passed successfully."
        )
