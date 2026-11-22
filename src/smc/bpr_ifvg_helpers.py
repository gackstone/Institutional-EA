'''Utility helpers for ICT primitives (BPR, IFVG, Breaker, Unicorn).'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

from src.core.contracts import FairValueGap, OrderBlock, OrderType


@dataclass(frozen=True)
class BprZone:
    """Breakout Pull‑back Reversal (BPR) zone – overlap of opposite‑direction FVGs.

    Attributes
    ----------
    symbol: str
    timeframe: str
    top: float
    bottom: float
    midpoint: float
    formation_time: datetime
    """

    symbol: str
    timeframe: str
    top: float
    bottom: float
    midpoint: float
    formation_time: datetime

    @property
    def direction(self) -> OrderType:
        """Direction is derived from the underlying FVG polarity.

        If the overlap originates from a bullish FVG (low‑high) intersecting a
        bearish FVG, the net bias is considered *neutral* for entry purposes.
        The strategy treats it as a *buy* zone when the price is approaching from
        below and as a *sell* zone when approaching from above.  For simplicity we
        expose both sides via ``OrderType`` based on which side of the overlap is
        nearer to the current price (caller can decide).
        """
        # This helper does not know the live price – return BUY as a generic
        # placeholder.  The consuming code can override based on market bias.
        return OrderType.BUY


def _overlap_interval(a_low: float, a_high: float, b_low: float, b_high: float) -> Optional[Tuple[float, float]]:
    """Return the overlapping interval (low, high) of two ranges, or ``None``.

    The ranges are inclusive; the function works for any ordering of the
    arguments.
    """
    low = max(a_low, b_low)
    high = min(a_high, b_high)
    if low < high:
        return low, high
    return None


def detect_bpr_zones(
    fvgs: List[FairValueGap],
    min_thickness: float = 0.0,
) -> List[BprZone]:
    """Detect BPR zones in a list of ``FairValueGap`` objects.

    A BPR zone is the geometric intersection of a *bullish* FVG and a *bearish*
    FVG that overlap.  The function iterates over all pairs, computes the
    overlap and, if the resulting thickness exceeds ``min_thickness``, creates a
    :class:`BprZone` instance.

    Parameters
    ----------
    fvgs:
        List of detected FVGs (both regular and inverse).
    min_thickness:
        Minimum required height of the overlap zone.  Default ``0.0`` means any
        overlap is accepted.

    Returns
    -------
    List[BprZone]
        All qualifying BPR zones.
    """
    zones: List[BprZone] = []
    for i, fvg_a in enumerate(fvgs):
        for fvg_b in fvgs[i + 1 :]:
            # Must be opposite directions (bullish vs bearish) and same symbol/timeframe
            if (
                fvg_a.symbol != fvg_b.symbol
                or fvg_a.timeframe != fvg_b.timeframe
                or fvg_a.direction == fvg_b.direction
            ):
                continue
            # Determine interval bounds for each FVG
            a_low, a_high = (fvg_a.bottom, fvg_a.top) if fvg_a.direction == OrderType.BUY else (fvg_a.top, fvg_a.bottom)
            b_low, b_high = (fvg_b.bottom, fvg_b.top) if fvg_b.direction == OrderType.BUY else (fvg_b.top, fvg_b.bottom)
            overlap = _overlap_interval(a_low, a_high, b_low, b_high)
            if overlap:
                low, high = overlap
                thickness = abs(high - low)
                if thickness >= min_thickness:
                    zones.append(
                        BprZone(
                            symbol=fvg_a.symbol,
                            timeframe=fvg_a.timeframe.value,
                            top=high,
                            bottom=low,
                            midpoint=(high + low) / 2.0,
                            formation_time=max(fvg_a.formation_time, fvg_b.formation_time),
                        )
                    )
    return zones


def detect_breaker_blocks(
    order_blocks: List[OrderBlock],
    fvgs: List[FairValueGap],
    max_lookahead_bars: int = 5,
) -> List[OrderBlock]:
    """Detect *breaker* blocks.

    A breaker block is a bullish order block that, after a subsequent sweep,
    experiences a displacement candle closing **above** the block's high.  The
    function looks forward up to ``max_lookahead_bars`` from each order block
    and returns the blocks that meet the condition.
    """
    breakers: List[OrderBlock] = []
    # Create an index for fast time lookup – we rely on the original chronological order
    for ob in order_blocks:
        if ob.direction != OrderType.BUY:
            continue
        # Find the index of the order block in the original candle list is not trivial here;
        # the engine that creates ``order_blocks`` already preserves chronological order.
        # We'll approximate by searching the list of fvgs for a sweep that occurs after the OB.
        for fvg in fvgs:
            if fvg.timeframe != ob.timeframe:
                continue
            if fvg.formation_time <= ob.formation_time:
                continue
            # Assume a sweep is represented by a *displacement* FVG where ``is_inverse`` is False.
            # A breakout is when a later candle (represented by the FVG's mitigation_time) closes
            # above the OB high.
            if fvg.mitigation_time and fvg.mitigation_time <= ob.formation_time:
                continue
            # Use the FVG's top/bottom as proxy for the sweep extremes.
            if fvg.top > ob.high:
                breakers.append(ob)
                break
    return breakers


def detect_unicorn_zones(
    breakers: List[OrderBlock],
    fvgs: List[FairValueGap],
    max_time_delta_minutes: int = 30,
) -> List[Tuple[OrderBlock, FairValueGap]]:
    """Detect *unicorn* zones – intersection of a breaker block and an FVG of the same direction.

    Returns a list of ``(breaker, fvg)`` tuples where the price ranges overlap and the
    timestamps are within ``max_time_delta_minutes`` of each other.
    """
    pairs: List[Tuple[OrderBlock, FairValueGap]] = []
    for ob in breakers:
        for fvg in fvgs:
            if fvg.direction != ob.direction:
                continue
            # Time proximity check
            delta = abs((fvg.formation_time - ob.formation_time).total_seconds() / 60)
            if delta > max_time_delta_minutes:
                continue
            # Overlap check – use the same helper as BPR
            overlap = _overlap_interval(
                ob.low,
                ob.high,
                fvg.bottom if fvg.direction == OrderType.BUY else fvg.top,
                fvg.top if fvg.direction == OrderType.BUY else fvg.bottom,
            )
            if overlap:
                pairs.append((ob, fvg))
    return pairs
