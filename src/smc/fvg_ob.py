"""
Fair Value Gap (FVG) and Order Block (OB) Engine.
Identifies institutional imbalances (FVG, IFVG), Order Blocks,
Breaker Blocks, and computes Premium/Discount/OTE zones (R5, R6, R7).
"""

from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime

from src.core.contracts import (
    Candle, Timeframe, OrderType, FairValueGap, OrderBlock
)


class FvgObEngine:
    def __init__(
        self,
        min_fvg_pips: float = 1.0,
        pip_size: float = 0.0001,
        fvg_min_atr: float = 0.3,
        fvg_requires_impulse: bool = False,
        ob_requires_displacement: bool = True,
        ob_displacement_atr_mult: float = 1.2,
        ob_requires_bos: bool = True,
        pd_equilibrium: float = 0.5,
    ):
        self.min_fvg_pips = min_fvg_pips
        self.pip_size = pip_size
        self.fvg_min_atr = fvg_min_atr
        self.fvg_requires_impulse = fvg_requires_impulse
        self.ob_requires_displacement = ob_requires_displacement
        self.ob_displacement_atr_mult = ob_displacement_atr_mult
        self.ob_requires_bos = ob_requires_bos
        self.pd_equilibrium = pd_equilibrium

    @staticmethod
    def compute_atr(candles: List[Candle], period: int = 14) -> float:
        """Computes True Range average over up to `period` closed bars."""
        if not candles:
            return 0.0
        if len(candles) == 1:
            return max(candles[0].range, 1e-9)
        window = candles[-min(len(candles), period + 1):]
        trs: List[float] = []
        for idx in range(1, len(window)):
            cur = window[idx]
            prev = window[idx - 1]
            tr = max(
                cur.high - cur.low,
                abs(cur.high - prev.close),
                abs(cur.low - prev.close),
            )
            trs.append(tr)
        return (sum(trs) / len(trs)) if trs else max(candles[-1].range, 1e-9)

    def detect_fvgs(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle]
    ) -> List[FairValueGap]:
        """
        Detects 3-candle Fair Value Gaps and tracks both regular FVGs and IFVGs (Inverse FVGs) (R6).
        Bullish FVG: Candle[i-2].high < Candle[i].low
        Bearish FVG: Candle[i-2].low > Candle[i].high
        Enforces minimum gap size (`max(min_fvg_pips * pip_size, fvg_min_atr * local_atr)`).
        """
        fvgs: List[FairValueGap] = []
        n = len(candles)
        if n < 3:
            return fvgs

        static_min_gap = self.min_fvg_pips * self.pip_size

        for i in range(2, n):
            c1 = candles[i - 2]
            c2 = candles[i - 1]  # The displacement candle
            c3 = candles[i]

            # Causal local ATR up to bar i
            local_atr = self.compute_atr(candles[max(0, i - 14): i + 1])
            atr_min_gap = (self.fvg_min_atr * local_atr) if self.fvg_min_atr > 0 else 0.0
            min_gap = max(static_min_gap, atr_min_gap)

            # Optional R6 impulse check on c2
            if self.fvg_requires_impulse:
                if c2.range <= 0 or (c2.body / c2.range) < 0.50:
                    continue

            # Bullish FVG (c3.low > c1.high)
            if c3.low > c1.high and (c3.low - c1.high) >= min_gap:
                bottom = c1.high
                top = c3.low
                mid = (top + bottom) / 2.0
                fvg_id = f"{symbol}_{timeframe}_{c2.time.isoformat()}_BULL_FVG"

                # Check mitigation in subsequent candles
                mitigated = False
                mitigation_time = None
                invalidated_as_ifvg = False
                ifvg_candidate = False
                for future in candles[i + 1:]:
                    if future.low <= bottom:
                        mitigated = True
                        mitigation_time = future.time
                        if future.close < bottom:
                            ifvg_candidate = True
                    if ifvg_candidate and future.close > top:
                        invalidated_as_ifvg = True

                fvgs.append(
                    FairValueGap(
                        id=fvg_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=OrderType.BUY,
                        top=top,
                        bottom=bottom,
                        midpoint=mid,
                        formation_time=c2.time,
                        mitigated=mitigated,
                        mitigation_time=mitigation_time,
                        is_inverse=False
                    )
                )

                if ifvg_candidate and not invalidated_as_ifvg and mitigation_time:
                    fvgs.append(
                        FairValueGap(
                            id=f"{symbol}_{timeframe}_{c2.time.isoformat()}_BEAR_IFVG",
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=OrderType.SELL,
                            top=top,
                            bottom=bottom,
                            midpoint=mid,
                            formation_time=mitigation_time,
                            mitigated=False,
                            mitigation_time=None,
                            is_inverse=True
                        )
                    )

            # Bearish FVG (c1.low > c3.high)
            elif c1.low > c3.high and (c1.low - c3.high) >= min_gap:
                top = c1.low
                bottom = c3.high
                mid = (top + bottom) / 2.0
                fvg_id = f"{symbol}_{timeframe}_{c2.time.isoformat()}_BEAR_FVG"

                mitigated = False
                mitigation_time = None
                invalidated_as_ifvg = False
                ifvg_candidate = False
                for future in candles[i + 1:]:
                    if future.high >= top:
                        mitigated = True
                        mitigation_time = future.time
                        if future.close > top:
                            ifvg_candidate = True
                    if ifvg_candidate and future.close < bottom:
                        invalidated_as_ifvg = True

                fvgs.append(
                    FairValueGap(
                        id=fvg_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=OrderType.SELL,
                        top=top,
                        bottom=bottom,
                        midpoint=mid,
                        formation_time=c2.time,
                        mitigated=mitigated,
                        mitigation_time=mitigation_time,
                        is_inverse=False
                    )
                )

                if ifvg_candidate and not invalidated_as_ifvg and mitigation_time:
                    fvgs.append(
                        FairValueGap(
                            id=f"{symbol}_{timeframe}_{c2.time.isoformat()}_BULL_IFVG",
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=OrderType.BUY,
                            top=top,
                            bottom=bottom,
                            midpoint=mid,
                            formation_time=mitigation_time,
                            mitigated=False,
                            mitigation_time=None,
                            is_inverse=True
                        )
                    )

        return fvgs

    def detect_order_blocks(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: List[Candle]
    ) -> List[OrderBlock]:
        """
        Detects Order Blocks per Rule R5:
        - Bullish OB: The last bearish candle preceding a strong bullish impulse that breaks structure.
        - Bearish OB: The last bullish candle preceding a strong bearish impulse that breaks structure.
        When `ob_requires_displacement=True`, requires impulse body >= `ob_displacement_atr_mult * ATR`
        or an FVG left on the impulse leg (`c_disp2.low > c_ob.high` / `c_disp2.high < c_ob.low`).
        When `ob_requires_bos=True`, requires the impulse leg (`c_disp`..`c_disp3`) to body-close
        beyond the prior local swing high/low.
        """
        order_blocks: List[OrderBlock] = []
        n = len(candles)
        if n < 4:
            return order_blocks

        for i in range(1, n - 2):
            c_ob = candles[i]
            c_disp = candles[i + 1]
            c_disp2 = candles[i + 2]
            c_disp3 = candles[i + 3] if (i + 3) < n else c_disp2

            local_atr = self.compute_atr(candles[max(0, i - 14): i + 1])

            # Prior swing reference window (up to 10 bars before c_ob)
            prior_slice = candles[max(0, i - 10): i]
            prior_swing_high = max((c.high for c in prior_slice), default=c_ob.high)
            prior_swing_low = min((c.low for c in prior_slice), default=c_ob.low)

            # Bullish Order Block candidate:
            if c_ob.is_bearish and c_disp.is_bullish:
                disp_range = max(c_disp2.close, c_disp3.close) - c_ob.high
                if disp_range > 0 and c_disp.close > c_ob.high:
                    # R5.1: Displacement check (impulse body >= 1.2 * ATR OR FVG created)
                    leaves_fvg = c_disp2.low > c_ob.high
                    max_impulse_body = max(c_disp.body, c_disp2.body if c_disp2.is_bullish else 0.0)
                    has_displacement = (
                        (local_atr > 0 and max_impulse_body >= self.ob_displacement_atr_mult * local_atr)
                        or leaves_fvg
                    )
                    if self.ob_requires_displacement and not has_displacement:
                        continue

                    # R5.2: Structural break check (impulse leg body closes above prior swing high)
                    impulse_max_close = max(c_disp.close, c_disp2.close, c_disp3.close)
                    breaks_structure = impulse_max_close > prior_swing_high
                    if self.ob_requires_bos and not breaks_structure:
                        continue

                    mitigated = False
                    for future in candles[i + 2:]:
                        if future.low <= c_ob.low:
                            mitigated = True
                            break

                    ob_body = max(c_ob.body, self.pip_size * 0.1)
                    disp_expansion = max(0.0, c_disp.body / ob_body)
                    score_disp = min(0.40, disp_expansion * 0.15)
                    disp_body_ratio = (c_disp.body / c_disp.range) if c_disp.range > 0 else 0.5
                    score_body = min(0.30, disp_body_ratio * 0.30)
                    score_vol = 0.10
                    if getattr(c_disp, "tick_volume", 0) > 0 and getattr(c_ob, "tick_volume", 0) > 0:
                        vol_ratio = c_disp.tick_volume / max(c_ob.tick_volume, 1)
                        score_vol = min(0.20, vol_ratio * 0.10)
                    score_fresh = 0.10 if not mitigated else 0.0
                    bonus = 0.10 if (leaves_fvg and breaks_structure) else 0.0
                    strength = round(min(1.0, max(0.20, score_disp + score_body + score_vol + score_fresh + bonus)), 2)

                    order_blocks.append(
                        OrderBlock(
                            id=f"{symbol}_{timeframe}_{c_ob.time.isoformat()}_BULL_OB",
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=OrderType.BUY,
                            high=c_ob.high,
                            low=c_ob.low,
                            open_price=c_ob.open,
                            close_price=c_ob.close,
                            formation_time=c_ob.time,
                            mitigated=mitigated,
                            is_breaker=False,
                            strength_score=strength
                        )
                    )

            # Bearish Order Block candidate:
            elif c_ob.is_bullish and c_disp.is_bearish:
                disp_range = c_ob.low - min(c_disp2.close, c_disp3.close)
                if disp_range > 0 and c_disp.close < c_ob.low:
                    # R5.1: Displacement check (impulse body >= 1.2 * ATR OR FVG created)
                    leaves_fvg = c_disp2.high < c_ob.low
                    max_impulse_body = max(c_disp.body, c_disp2.body if c_disp2.is_bearish else 0.0)
                    has_displacement = (
                        (local_atr > 0 and max_impulse_body >= self.ob_displacement_atr_mult * local_atr)
                        or leaves_fvg
                    )
                    if self.ob_requires_displacement and not has_displacement:
                        continue

                    # R5.2: Structural break check (impulse leg body closes below prior swing low)
                    impulse_min_close = min(c_disp.close, c_disp2.close, c_disp3.close)
                    breaks_structure = impulse_min_close < prior_swing_low
                    if self.ob_requires_bos and not breaks_structure:
                        continue

                    mitigated = False
                    for future in candles[i + 2:]:
                        if future.high >= c_ob.high:
                            mitigated = True
                            break

                    ob_body = max(c_ob.body, self.pip_size * 0.1)
                    disp_expansion = max(0.0, c_disp.body / ob_body)
                    score_disp = min(0.40, disp_expansion * 0.15)
                    disp_body_ratio = (c_disp.body / c_disp.range) if c_disp.range > 0 else 0.5
                    score_body = min(0.30, disp_body_ratio * 0.30)
                    score_vol = 0.10
                    if getattr(c_disp, "tick_volume", 0) > 0 and getattr(c_ob, "tick_volume", 0) > 0:
                        vol_ratio = c_disp.tick_volume / max(c_ob.tick_volume, 1)
                        score_vol = min(0.20, vol_ratio * 0.10)
                    score_fresh = 0.10 if not mitigated else 0.0
                    bonus = 0.10 if (leaves_fvg and breaks_structure) else 0.0
                    strength = round(min(1.0, max(0.20, score_disp + score_body + score_vol + score_fresh + bonus)), 2)

                    order_blocks.append(
                        OrderBlock(
                            id=f"{symbol}_{timeframe}_{c_ob.time.isoformat()}_BEAR_OB",
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=OrderType.SELL,
                            high=c_ob.high,
                            low=c_ob.low,
                            open_price=c_ob.open,
                            close_price=c_ob.close,
                            formation_time=c_ob.time,
                            mitigated=mitigated,
                            is_breaker=False,
                            strength_score=strength
                        )
                    )

        return order_blocks

    @staticmethod
    def has_ob_fvg_confluence(
        ob: Optional[OrderBlock],
        fvg: Optional[FairValueGap],
        tolerance: float = 0.0005
    ) -> bool:
        """
        Checks whether an OrderBlock and FairValueGap belong to the same directional leg
        and spatially overlap or touch within `tolerance` (R6: OB + FVG = confluence).
        """
        if ob is None or fvg is None:
            return False
        if ob.direction != fvg.direction:
            return False
        overlap_low = max(ob.low, fvg.bottom) - tolerance
        overlap_high = min(ob.high, fvg.top) + tolerance
        return overlap_high >= overlap_low

    @staticmethod
    def calculate_premium_discount(
        range_high: float,
        range_low: float,
        current_price: float,
        pd_equilibrium: float = 0.5
    ) -> Dict[str, Any]:
        """
        Calculates Premium/Discount zones (R7) and Optimal Trade Entry (OTE) levels.
        Fib levels: `pd_equilibrium` (default 0.50 Equilibrium), 0.62 (OTE min), 0.705 (OTE sweet spot), 0.79 (OTE max).
        """
        total_range = range_high - range_low
        if total_range <= 0:
            return {
                "equilibrium": current_price,
                "pd_ratio": 0.5,
                "is_discount": False,
                "is_premium": False,
                "ote_62": current_price,
                "ote_705": current_price,
                "ote_79": current_price
            }

        eq = range_low + pd_equilibrium * total_range
        pd_ratio = (current_price - range_low) / total_range
        is_discount = current_price < eq
        is_premium = current_price > eq

        fib_62 = range_high - 0.62 * total_range
        fib_705 = range_high - 0.705 * total_range
        fib_79 = range_high - 0.79 * total_range

        return {
            "equilibrium": round(eq, 5),
            "pd_ratio": round(pd_ratio, 4),
            "is_discount": is_discount,
            "is_premium": is_premium,
            "ote_62": round(fib_62, 5),
            "ote_705": round(fib_705, 5),
            "ote_79": round(fib_79, 5)
        }
