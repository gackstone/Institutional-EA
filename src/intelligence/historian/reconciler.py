"""
Position Lifecycle Reconciler for ATI.
Reconstructs completed trading positions from raw broker deals.
Correctly handles partial closes, multiple fills, commission, swap, and net financial performance.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.intelligence.contracts import BrokerDealRecord, CompletedPositionRecord
from src.intelligence.historian.normalization import AccountBrokerNormalizer

logger = logging.getLogger("ATI.Reconciler")


class PositionLifecycleReconciler:
    """
    Reconstructs complete position lifecycles from authoritative MT5 broker deals.
    Distinguishes active positions from completed positions.
    """

    def __init__(self, normalizer: Optional[AccountBrokerNormalizer] = None):
        self.normalizer = normalizer or AccountBrokerNormalizer()

    def reconcile_deals_into_positions(
        self,
        deals: List[BrokerDealRecord],
    ) -> Tuple[List[CompletedPositionRecord], Dict[int, List[BrokerDealRecord]]]:
        """
        Groups deals by position_id and evaluates whether positions are closed or still open.
        Returns (completed_positions, open_position_deals).
        """
        if not deals:
            return [], {}

        # Group deals by position_id
        deals_by_position: Dict[int, List[BrokerDealRecord]] = defaultdict(list)
        for deal in sorted(deals, key=lambda d: (d.timestamp, d.deal_ticket)):
            deals_by_position[deal.position_id].append(deal)

        completed_positions: List[CompletedPositionRecord] = []
        open_positions: Dict[int, List[BrokerDealRecord]] = {}

        for pos_id, pos_deals in deals_by_position.items():
            reconciled = self.reconcile_single_position(pos_id, pos_deals)
            if reconciled is not None:
                completed_positions.append(reconciled)
            else:
                open_positions[pos_id] = pos_deals

        return completed_positions, open_positions

    def reconcile_single_position(
        self,
        position_id: int,
        deals: List[BrokerDealRecord],
    ) -> Optional[CompletedPositionRecord]:
        """
        Evaluates a sequence of deals for a single position_id.
        If the remaining volume is zero (or near zero due to floating point), returns CompletedPositionRecord.
        Otherwise, returns None (position is still open).
        """
        if not deals:
            return None

        entry_deals: List[BrokerDealRecord] = []
        exit_deals: List[BrokerDealRecord] = []

        total_in_vol = 0.0
        total_out_vol = 0.0
        weighted_entry_cost = 0.0
        weighted_exit_cost = 0.0
        total_gross_profit = 0.0
        total_commission = 0.0
        total_swap = 0.0
        total_fee = 0.0

        canonical_symbol = ""
        broker_symbol = ""
        direction = "BUY"
        account_number = 0
        account_currency = "USD"
        denomination_factor = 1.0

        for deal in deals:
            # Set metadata from first available deal
            if not broker_symbol:
                broker_symbol = deal.symbol
                canonical_symbol = deal.canonical_symbol or self.normalizer.resolve_canonical_symbol(deal.symbol) or "UNKNOWN"
                account_number = deal.account_number
                account_currency = deal.account_currency
                denomination_factor = deal.denomination_factor

            # Accumulate financial costs
            total_commission += deal.commission
            total_swap += deal.swap
            total_profit = deal.profit
            total_gross_profit += total_profit
            total_fee += deal.fee

            entry_type = str(deal.entry_type).upper()
            deal_type = str(deal.deal_type).upper()

            if "INOUT" in entry_type:
                # Reversal or complex fill
                entry_deals.append(deal)
                exit_deals.append(deal)
            elif "IN" in entry_type:
                entry_deals.append(deal)
                total_in_vol += deal.volume
                weighted_entry_cost += deal.volume * deal.price
                if "BUY" in deal_type:
                    direction = "BUY"
                elif "SELL" in deal_type:
                    direction = "SELL"
            elif "OUT" in entry_type:
                exit_deals.append(deal)
                total_out_vol += deal.volume
                weighted_exit_cost += deal.volume * deal.price

        # Check if position is closed: out volume matches in volume (within 1e-5)
        is_closed = total_in_vol > 0 and abs(total_in_vol - total_out_vol) < 1e-4

        if not is_closed:
            return None  # Position still open

        # Position is closed
        open_time = entry_deals[0].timestamp if entry_deals else deals[0].timestamp
        close_time = exit_deals[-1].timestamp if exit_deals else deals[-1].timestamp
        open_price = (weighted_entry_cost / total_in_vol) if total_in_vol > 0 else deals[0].price
        close_price = (weighted_exit_cost / total_out_vol) if total_out_vol > 0 else deals[-1].price

        # Net profit = Gross profit + Commission + Swap - Fee
        realized_net_profit = total_gross_profit + total_commission + total_swap - total_fee

        # Extract exit reason from exit deal comments if available
        exit_reason = "MANUAL_OR_BROKER"
        if exit_deals:
            last_comment = exit_deals[-1].comment.strip().lower()
            if "sl" in last_comment or "stop loss" in last_comment:
                exit_reason = "STOP_LOSS"
            elif "tp" in last_comment or "take profit" in last_comment:
                exit_reason = "TAKE_PROFIT"
            elif "close" in last_comment:
                exit_reason = "SYSTEM_CLOSE"

        # Determine account type
        acc_type = "CENT" if denomination_factor > 1.0 else "STANDARD"

        return CompletedPositionRecord(
            position_id=position_id,
            canonical_symbol=canonical_symbol,
            broker_symbol=broker_symbol,
            direction=direction,
            open_time=open_time,
            close_time=close_time,
            open_price=round(open_price, 5),
            close_price=round(close_price, 5),
            volume=round(total_in_vol, 4),
            realized_gross_profit=round(total_gross_profit, 4),
            realized_net_profit=round(realized_net_profit, 4),
            commission=round(total_commission, 4),
            swap=round(total_swap, 4),
            exit_reason=exit_reason,
            account_number=account_number,
            account_currency=account_currency,
            account_type=acc_type,
            denomination_factor=denomination_factor,
            entry_deals=[d.deal_ticket for d in entry_deals],
            exit_deals=[d.deal_ticket for d in exit_deals],
            partial_closes_count=max(0, len(exit_deals) - 1),
            reconciled_at=datetime.now(timezone.utc),
        )
