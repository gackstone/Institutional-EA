"""
Same-Symbol Directional Exposure and Hedging Intelligence Manager.
Audits and governs concurrent positions on the same instrument:
- Inspects active symbol positions, directions, lots, entry prices, stops, and strategy attribution.
- Distinguishes:
  1. CONFLICTING_SIGNAL: Same strategy whipsawing into opposite direction without thesis closure.
  2. LEGITIMATE_HEDGE: Distinct strategy/timeframe hedging or independent counter-trend scalp.
  3. INDEPENDENT_SETUP: Multi-timeframe or distinct model entries with separate risk budgets.
- Calculates and restricts Gross Volume, Net Volume, and Cumulative Symbol Monetary Risk.
- Prevents uncontrolled accumulation of opposing positions while allowing verified independent trades.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import OrderType, Position, SignalCandidate, SymbolInfo, AccountInfo

logger = logging.getLogger("DirectionalExposureManager")


class ExposureDisposition(str, Enum):
    ALLOW_INDEPENDENT = "ALLOW_INDEPENDENT"
    ALLOW_HEDGE = "ALLOW_HEDGE"
    ALLOW_SAME_DIRECTION = "ALLOW_SAME_DIRECTION"
    REJECT_CONFLICTING_SIGNAL = "REJECT_CONFLICTING_SIGNAL"
    REJECT_EXCESSIVE_SYMBOL_EXPOSURE = "REJECT_EXCESSIVE_SYMBOL_EXPOSURE"
    REJECT_EXCESSIVE_SYMBOL_RISK = "REJECT_EXCESSIVE_SYMBOL_RISK"
    REJECT_POSITION_COUNT_LIMIT = "REJECT_POSITION_COUNT_LIMIT"


@dataclass
class DirectionalExposureDecision:
    allowed: bool
    disposition: ExposureDisposition
    reason: str
    existing_buy_lots: float
    existing_sell_lots: float
    projected_net_lots: float
    projected_gross_lots: float
    symbol_positions_count: int
    total_monetary_risk: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "existing_buy_lots": round(self.existing_buy_lots, 4),
            "existing_sell_lots": round(self.existing_sell_lots, 4),
            "projected_net_lots": round(self.projected_net_lots, 4),
            "projected_gross_lots": round(self.projected_gross_lots, 4),
            "symbol_positions_count": self.symbol_positions_count,
            "total_monetary_risk": round(self.total_monetary_risk, 2),
        }


class SameSymbolExposureManager:
    """
    Evaluates new trade candidates against existing positions on the same instrument.
    Enforces risk budgets, margin feasibility, and strategy isolation.
    """

    def __init__(
        self,
        max_positions_per_symbol: int = 0,  # 0 = dynamic risk-budget driven (no fixed position cap)
        max_gross_lots_per_symbol: float = 2.0,
        max_symbol_risk_pct: float = 4.0,
        allow_cross_strategy_hedging: bool = True,
    ):
        self.max_positions_per_symbol = max_positions_per_symbol
        self.max_gross_lots_per_symbol = max_gross_lots_per_symbol
        self.max_symbol_risk_pct = max_symbol_risk_pct
        self.allow_cross_strategy_hedging = allow_cross_strategy_hedging

    def evaluate_new_signal(
        self,
        candidate: SignalCandidate,
        symbol_info: SymbolInfo,
        account: AccountInfo,
        active_positions: List[Position],
        proposed_volume: float,
        proposed_monetary_risk: float,
        bot_magic_number: int = 100101,
    ) -> DirectionalExposureDecision:
        """
        Evaluates whether a new BUY or SELL signal on `candidate.symbol` can proceed.
        """
        symbol = candidate.symbol
        is_cand_buy = candidate.direction in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)

        # 1. Filter existing positions on this symbol
        sym_positions = [
            p for p in active_positions
            if p.symbol == symbol or p.symbol.split(".")[0] == symbol.split(".")[0]
        ]

        buy_positions = [p for p in sym_positions if p.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)]
        sell_positions = [p for p in sym_positions if p.order_type in (OrderType.SELL, OrderType.SELL_LIMIT, OrderType.SELL_STOP)]

        existing_buy_lots = sum(p.volume for p in buy_positions)
        existing_sell_lots = sum(p.volume for p in sell_positions)
        count_existing = len(sym_positions)

        # Projected exposure
        cand_lots = proposed_volume
        projected_buy_lots = existing_buy_lots + (cand_lots if is_cand_buy else 0.0)
        projected_sell_lots = existing_sell_lots + (0.0 if is_cand_buy else cand_lots)
        projected_gross = projected_buy_lots + projected_sell_lots
        projected_net = projected_buy_lots - projected_sell_lots

        # Calculate current cumulative monetary risk on this symbol
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0

        current_sym_risk = 0.0
        for p in sym_positions:
            init_risk = float(getattr(p, "initial_risk_amount", 0.0) or 0.0)
            if init_risk > 0.01:
                current_sym_risk += init_risk
            elif p.stop_loss > 0:
                dist = abs(p.open_price - p.stop_loss)
                current_sym_risk += (dist / tick_size) * tick_value * float(p.volume)
            else:
                # Unprotected estimate
                current_sym_risk += (50 * point / tick_size) * tick_value * float(p.volume)

        projected_total_sym_risk = current_sym_risk + proposed_monetary_risk
        capital_base = max(account.balance, account.equity, 100.0)
        projected_sym_risk_pct = (projected_total_sym_risk / capital_base) * 100.0

        # No existing positions -> trivially allowed
        if count_existing == 0:
            return DirectionalExposureDecision(
                allowed=True,
                disposition=ExposureDisposition.ALLOW_INDEPENDENT,
                reason="No existing positions on symbol; initial directional exposure approved.",
                existing_buy_lots=0.0,
                existing_sell_lots=0.0,
                projected_net_lots=projected_net,
                projected_gross_lots=projected_gross,
                symbol_positions_count=0,
                total_monetary_risk=projected_total_sym_risk,
            )

        # 2. Opportunity-driven multi-position support (Arbitrary position-count limits disabled)
        logger.info(
            f"[POSITION_MANAGER] Multiple concurrent positions are supported on {symbol}. "
            f"Existing positions: {count_existing}. Validating volume and monetary risk."
        )

        # 3. Maximum gross volume per symbol
        if projected_gross > self.max_gross_lots_per_symbol:
            reason = (
                f"Projected gross volume {projected_gross:.2f} lots on {symbol} "
                f"exceeds symbol maximum gross limit {self.max_gross_lots_per_symbol:.2f} lots."
            )
            return DirectionalExposureDecision(
                allowed=False,
                disposition=ExposureDisposition.REJECT_EXCESSIVE_SYMBOL_EXPOSURE,
                reason=reason,
                existing_buy_lots=existing_buy_lots,
                existing_sell_lots=existing_sell_lots,
                projected_net_lots=projected_net,
                projected_gross_lots=projected_gross,
                symbol_positions_count=count_existing,
                total_monetary_risk=projected_total_sym_risk,
            )

        # 4. Maximum cumulative monetary risk on symbol
        if projected_sym_risk_pct > self.max_symbol_risk_pct:
            reason = (
                f"Cumulative monetary risk on {symbol} ({projected_sym_risk_pct:.2f}%, ${projected_total_sym_risk:.2f}) "
                f"exceeds maximum symbol risk budget {self.max_symbol_risk_pct:.2f}% (${capital_base * self.max_symbol_risk_pct / 100.0:.2f})."
            )
            return DirectionalExposureDecision(
                allowed=False,
                disposition=ExposureDisposition.REJECT_EXCESSIVE_SYMBOL_RISK,
                reason=reason,
                existing_buy_lots=existing_buy_lots,
                existing_sell_lots=existing_sell_lots,
                projected_net_lots=projected_net,
                projected_gross_lots=projected_gross,
                symbol_positions_count=count_existing,
                total_monetary_risk=projected_total_sym_risk,
            )

        # 5. Directional Analysis: Same direction vs Opposite direction
        opposing_positions = sell_positions if is_cand_buy else buy_positions
        same_positions = buy_positions if is_cand_buy else sell_positions

        cand_strategy = str(getattr(candidate, "setup_type", "") or getattr(candidate, "id", "")).upper()

        if opposing_positions:
            # OPPOSITE DIRECTION CASE (Potential Hedge or Conflicting Signal)
            # Check if this comes from the EXACT same strategy on the same timeframe/model
            # (which represents a conflicting contradictory signal)
            for opp_p in opposing_positions:
                opp_comment = str(getattr(opp_p, "comment", "")).upper()
                opp_magic = getattr(opp_p, "magic", 0)

                # Same strategy signature on both sides without previous trade thesis closure -> Conflicting whipsaw!
                if opp_comment and cand_strategy and (
                    cand_strategy in opp_comment or opp_comment in cand_strategy
                ) and opp_magic == bot_magic_number:
                    reason = (
                        f"Conflicting duplicate opposite signal on {symbol}: Strategy '{cand_strategy}' already has "
                        f"active position #{opp_p.ticket} ({opp_p.order_type.value}) in opposite direction."
                    )
                    return DirectionalExposureDecision(
                        allowed=False,
                        disposition=ExposureDisposition.REJECT_CONFLICTING_SIGNAL,
                        reason=reason,
                        existing_buy_lots=existing_buy_lots,
                        existing_sell_lots=existing_sell_lots,
                        projected_net_lots=projected_net,
                        projected_gross_lots=projected_gross,
                        symbol_positions_count=count_existing,
                        total_monetary_risk=projected_total_sym_risk,
                    )

            # Different strategy or multi-timeframe hedge:
            if not self.allow_cross_strategy_hedging:
                return DirectionalExposureDecision(
                    allowed=False,
                    disposition=ExposureDisposition.REJECT_CONFLICTING_SIGNAL,
                    reason=f"Opposite-direction positions on {symbol} disabled by policy.",
                    existing_buy_lots=existing_buy_lots,
                    existing_sell_lots=existing_sell_lots,
                    projected_net_lots=projected_net,
                    projected_gross_lots=projected_gross,
                    symbol_positions_count=count_existing,
                    total_monetary_risk=projected_total_sym_risk,
                )

            # Legitimate independent cross-strategy hedge approved
            reason = (
                f"Legitimate cross-strategy hedge approved on {symbol}: {candidate.direction.value} {cand_lots:.2f} lots "
                f"(Strategy: {cand_strategy}) complements active opposite #{opposing_positions[0].ticket} "
                f"(Strategy: {getattr(opposing_positions[0], 'comment', 'EXISTING')}). "
                f"Net exposure reduced to {abs(projected_net):.2f} lots, total risk: ${projected_total_sym_risk:.2f}."
            )
            return DirectionalExposureDecision(
                allowed=True,
                disposition=ExposureDisposition.ALLOW_HEDGE,
                reason=reason,
                existing_buy_lots=existing_buy_lots,
                existing_sell_lots=existing_sell_lots,
                projected_net_lots=projected_net,
                projected_gross_lots=projected_gross,
                symbol_positions_count=count_existing,
                total_monetary_risk=projected_total_sym_risk,
            )

        # SAME DIRECTION CASE (Multiple independent entries, e.g. M1 scalp + M15 SMC)
        reason = (
            f"Independent concurrent {candidate.direction.value} entry approved on {symbol}: "
            f"Gross: {projected_gross:.2f} lots, Net: {projected_net:.2f} lots, Total symbol risk: ${projected_total_sym_risk:.2f}."
        )
        return DirectionalExposureDecision(
            allowed=True,
            disposition=ExposureDisposition.ALLOW_SAME_DIRECTION,
            reason=reason,
            existing_buy_lots=existing_buy_lots,
            existing_sell_lots=existing_sell_lots,
            projected_net_lots=projected_net,
            projected_gross_lots=projected_gross,
            symbol_positions_count=count_existing,
            total_monetary_risk=projected_total_sym_risk,
        )
