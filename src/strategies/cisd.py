"""
Liquidity Sweep + CISD Strategy Module.
Detects a liquidity pool sweep (using LiquidityEngine) with close-back-inside
rejection (R4) and confirms with a CISD (Change in State of Delivery) body close
through the opening price of the manipulation leg.
"""

from __future__ import annotations

from typing import Optional, List

from src.strategies.base import SignalModule, StrategyContext, RawSignal
from src.core.contracts import OrderType, SetupType, Candle
from src.smc.liquidity import LiquidityEngine
from src.smc.market_structure import MarketStructureEngine


class CisdSignalModule(SignalModule):
    """Detects a liquidity sweep + close-back-inside followed by CISD confirmation (R4)."""

    def __init__(self, config):
        cfg = getattr(config.strategy, "cisd", {}) if hasattr(config, "strategy") else {}
        self.min_sweep_distance_atr: float = float(cfg.get("min_sweep_atr", 0.15))
        self.max_cisd_bars: int = int(cfg.get("max_cisd_bars", 3))
        self.min_rr: float = float(cfg.get("min_rr", 2.0))
        self.sweep_requires_close_back_inside: bool = bool(
            getattr(config.strategy, "sweep_requires_close_back_inside", True)
            if hasattr(config, "strategy") else True
        )
        self.liquidity_engine = LiquidityEngine(
            sweep_requires_close_back_inside=self.sweep_requires_close_back_inside
        )
        self.ms_engine = MarketStructureEngine()

    def generate_signal(self, ctx: StrategyContext) -> Optional[RawSignal]:
        if not ctx.m15_candles or len(ctx.m15_candles) < 15:
            return None
        candles = ctx.m15_candles
        # Use swing_lookback=2 on compact windows (<20 bars), else default 5
        lookback = 2 if len(candles) < 20 else 5
        pools = self.liquidity_engine.identify_liquidity_pools(
            symbol=ctx.symbol,
            timeframe=candles[0].timeframe if hasattr(candles[0], "timeframe") else None,
            candles=candles[:-1],
            swing_lookback=lookback,
        )
        if not pools:
            return None

        # Look for a recent sweep of any pool formed BEFORE the sweep candle
        last = candles[-1]
        # Approximate ATR using recent candles BEFORE the sweep candle so the sweep bar itself doesn't inflate ATR
        atr_window = candles[-15:-1] if len(candles) >= 2 else candles
        atr = max(sum(abs(c.high - c.low) for c in atr_window) / len(atr_window), 1e-5)
        for pool in reversed(pools):
            # Only consider candles strictly after the pool formed
            recent = [c for c in candles[-5:] if c.time > pool.formation_time]
            if not recent:
                continue
            swept, rejected, sweep_dist_pips = self.liquidity_engine.verify_sweep(pool, recent)
            if not swept:
                continue
            if self.sweep_requires_close_back_inside and not rejected:
                continue

            sweep_dist_price = sweep_dist_pips * self.liquidity_engine.pip_size
            if sweep_dist_price < self.min_sweep_distance_atr * atr:
                continue

            # Find index in `recent` where the sweep occurred
            sweep_idx = None
            sweep_candle: Optional[Candle] = None
            for i, c in enumerate(recent):
                if pool.level_type in ["BSL", "EQH"] and c.high > pool.price:
                    sweep_idx = i
                    sweep_candle = c
                    break
                if pool.level_type in ["SSL", "EQL"] and c.low < pool.price:
                    sweep_idx = i
                    sweep_candle = c
                    break
            if sweep_idx is None or sweep_candle is None:
                continue

            # R4: Sweeping BSL/EQH (highs) + closing back inside -> BEARISH reversal (SELL)
            #     Sweeping SSL/EQL (lows) + closing back inside -> BULLISH reversal (BUY)
            is_bearish_sweep = pool.level_type in ["BSL", "EQH"]
            direction = OrderType.SELL if is_bearish_sweep else OrderType.BUY

            # CISD confirmation: subsequent candle closes back inside and beyond the sweep candle's open
            cisd_ok = False
            if is_bearish_sweep and sweep_candle.close < pool.price and sweep_candle.is_bearish:
                cisd_ok = True
            elif (not is_bearish_sweep) and sweep_candle.close > pool.price and sweep_candle.is_bullish:
                cisd_ok = True
            else:
                for j in range(1, self.max_cisd_bars + 1):
                    if sweep_idx + j >= len(recent):
                        break
                    next_c = recent[sweep_idx + j]
                    if is_bearish_sweep and next_c.close < min(pool.price, sweep_candle.open):
                        cisd_ok = True
                        break
                    if (not is_bearish_sweep) and next_c.close > max(pool.price, sweep_candle.open):
                        cisd_ok = True
                        break
            if not cisd_ok:
                continue

            last = candles[-1]
            buffer = atr * 0.25
            if direction == OrderType.BUY:
                sweep_extreme = min(c.low for c in recent[sweep_idx:])
                sl = sweep_extreme - buffer
                sl_dist = max(last.close - sl, atr * 0.25)
                opposing = sorted(
                    [p.price for p in pools if p.level_type in ["BSL", "EQH"] and p.price > last.close]
                )
                valid_opp = [p for p in opposing if (p - last.close) / sl_dist >= self.min_rr - 1e-9]
                tp = valid_opp[0] if valid_opp else (opposing[-1] if opposing else (last.close + sl_dist * self.min_rr))
                rr = (tp - last.close) / sl_dist if sl_dist > 0 else 0.0
            else:
                sweep_extreme = max(c.high for c in recent[sweep_idx:])
                sl = sweep_extreme + buffer
                sl_dist = max(sl - last.close, atr * 0.25)
                opposing = sorted(
                    [p.price for p in pools if p.level_type in ["SSL", "EQL"] and p.price < last.close],
                    reverse=True,
                )
                valid_opp = [p for p in opposing if (last.close - p) / sl_dist >= self.min_rr - 1e-9]
                tp = valid_opp[0] if valid_opp else (opposing[-1] if opposing else (last.close - sl_dist * self.min_rr))
                rr = (last.close - tp) / sl_dist if sl_dist > 0 else 0.0

            if rr < self.min_rr:
                continue

            raw = RawSignal(
                symbol=ctx.symbol,
                direction=direction,
                entry_price=last.close,
                setup_type=SetupType.LIQUIDITY_SWEEP,
                score=80.0,
                rationale=f"R4 Liquidity sweep of {pool.level_type} @ {pool.price:.5f} with close-back-inside & CISD",
                timestamp=last.time,
                metadata={
                    "sweep_distance": sweep_dist_pips,
                    "swept_level": pool.price,
                    "swept_type": pool.level_type,
                    "close_back_inside": True,
                    "atr": atr,
                    "sl": sl,
                    "tp": tp,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "risk_reward_ratio": round(rr, 2),
                },
            )
            return raw
        return None
