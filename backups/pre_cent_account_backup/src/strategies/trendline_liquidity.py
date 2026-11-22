"""
Trendline-as-Liquidity Strategy Module.
Implements a SignalModule that builds trendlines from confirmed swing highs (resistance)
and swing lows (support) and treats the trendline as a resting liquidity barrier (R4).
When price sweeps beyond the trendline and closes back inside the range, a valid
reversal entry is generated.
"""

from __future__ import annotations

from typing import Optional, List

from src.strategies.base import SignalModule, StrategyContext, RawSignal
from src.core.contracts import OrderType, SetupType, Candle
from src.smc.market_structure import MarketStructureEngine
from src.smc.liquidity import LiquidityEngine
from src.core.config import AppConfig


class Trendline:
    """Represents a trendline in price-time space anchored on swing highs or swing lows."""

    def __init__(self, p1: Candle, p2: Candle, is_resistance: bool = False):
        self.x1 = p1.time.timestamp()
        self.y1 = p1.high if is_resistance else p1.low
        self.x2 = p2.time.timestamp()
        self.y2 = p2.high if is_resistance else p2.low
        self.is_resistance = is_resistance
        if self.x2 == self.x1:
            self.slope = 0.0
        else:
            self.slope = (self.y2 - self.y1) / (self.x2 - self.x1)
        self.intercept = self.y1 - self.slope * self.x1

    def price_at(self, ts: float) -> float:
        return self.slope * ts + self.intercept

    def distance_to(self, ts: float, price: float) -> float:
        """Signed distance (price - trendline). Positive => above trendline."""
        return price - self.price_at(ts)


class TrendlineLiquiditySignalModule(SignalModule):
    """Generates a signal when price sweeps a swing trendline and closes back inside (R4)."""

    def __init__(self, config: AppConfig):
        self.cfg = config
        tl_cfg = getattr(self.cfg.strategy, "trendline_liquidity", {}) if hasattr(self.cfg, "strategy") else {}
        self.swing_lookback: int = int(tl_cfg.get("swing_lookback", 5))
        self.min_touches: int = int(tl_cfg.get("min_touches", 2))
        self.band_atr_multiplier: float = float(tl_cfg.get("band_atr_multiplier", 0.5))
        self.min_rr: float = float(tl_cfg.get("min_rr", 2.0))
        self.decay_pct: float = float(tl_cfg.get("decay_pct", 0.15))
        self.ms_engine = MarketStructureEngine(swing_lookback=self.swing_lookback)
        self.liq_engine = LiquidityEngine()

    def _build_trendlines(self, candles: List[Candle]) -> List[Trendline]:
        swing_highs, swing_lows = self.ms_engine.find_swing_points(candles)
        trendlines: List[Trendline] = []

        # Resistance trendlines connecting swing highs
        for i in range(len(swing_highs) - 1):
            idx1, c1 = swing_highs[i]
            idx2, c2 = swing_highs[i + 1]
            if idx2 - idx1 >= self.min_touches:
                trendlines.append(Trendline(c1, c2, is_resistance=True))

        # Support trendlines connecting swing lows
        for i in range(len(swing_lows) - 1):
            idx1, c1 = swing_lows[i]
            idx2, c2 = swing_lows[i + 1]
            if idx2 - idx1 >= self.min_touches:
                trendlines.append(Trendline(c1, c2, is_resistance=False))

        return trendlines

    def generate_signal(self, ctx: StrategyContext) -> Optional[RawSignal]:
        if not ctx.m15_candles or len(ctx.m15_candles) < 2 * self.swing_lookback + 3:
            return None
        candles = ctx.m15_candles
        trendlines = self._build_trendlines(candles[:-1])
        if not trendlines:
            return None

        last_candle = candles[-1]
        ts = last_candle.time.timestamp()
        atr = max(sum(abs(c.high - c.low) for c in candles[-14:]) / 14.0, 1e-5)

        for tl in reversed(trendlines):
            tl_price = tl.price_at(ts)

            # Support trendline sweep: wick pierces below trendline, body closes back above trendline (R4)
            if not tl.is_resistance:
                swept_support = (last_candle.low < tl_price) and (last_candle.close > tl_price)
                if swept_support:
                    direction = OrderType.BUY
                    entry = last_candle.close
                    sl = min(last_candle.low - atr * 0.25, entry - atr)
                    sl_dist = max(entry - sl, atr * 0.5)
                    tp = entry + sl_dist * self.min_rr
                    raw = RawSignal(
                        symbol=ctx.symbol,
                        direction=direction,
                        entry_price=entry,
                        setup_type=SetupType.TRENDLINE_LIQUIDITY,
                        score=75.0,
                        rationale=f"Support trendline liquidity sweep & close back inside @ {tl_price:.5f}",
                        timestamp=last_candle.time,
                        metadata={
                            "trendline_slope": tl.slope,
                            "trendline_intercept": tl.intercept,
                            "trendline_price": tl_price,
                            "close_back_inside": True,
                            "sl": sl,
                            "tp": tp,
                            "stop_loss": sl,
                            "take_profit": tp,
                            "risk_reward_ratio": self.min_rr,
                            "atr": atr,
                        },
                    )
                    return raw

            # Resistance trendline sweep: wick pierces above trendline, body closes back below trendline (R4)
            else:
                swept_resistance = (last_candle.high > tl_price) and (last_candle.close < tl_price)
                if swept_resistance:
                    direction = OrderType.SELL
                    entry = last_candle.close
                    sl = max(last_candle.high + atr * 0.25, entry + atr)
                    sl_dist = max(sl - entry, atr * 0.5)
                    tp = entry - sl_dist * self.min_rr
                    raw = RawSignal(
                        symbol=ctx.symbol,
                        direction=direction,
                        entry_price=entry,
                        setup_type=SetupType.TRENDLINE_LIQUIDITY,
                        score=75.0,
                        rationale=f"Resistance trendline liquidity sweep & close back inside @ {tl_price:.5f}",
                        timestamp=last_candle.time,
                        metadata={
                            "trendline_slope": tl.slope,
                            "trendline_intercept": tl.intercept,
                            "trendline_price": tl_price,
                            "close_back_inside": True,
                            "sl": sl,
                            "tp": tp,
                            "stop_loss": sl,
                            "take_profit": tp,
                            "risk_reward_ratio": self.min_rr,
                            "atr": atr,
                        },
                    )
                    return raw

        return None
