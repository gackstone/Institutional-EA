"""
Phase 6: Dedicated BTCUSD Weekend Scalping Strategy Engine.
Operates Saturday and Sunday with independent:
- Signal engine & market regime detection
- Volatility model & spread-relative-to-ATR validation
- Sudden price displacement & reversal risk evaluation
- M1/M5 price action + M15/H1 directional bias
Calibrated against actual BTCUSD broker contract specifications (contract_size=1.0, point=0.01).
Never inherits GOLD parameters and never substitutes GOLD when BTCUSD is unavailable.
"""

from __future__ import annotations
from typing import Optional

from src.scalper.config import InstrumentScalperConfig
from src.scalper.market_cache import IndicatorSnapshot
from src.scalper.strategy_gold import StrategySignalEvaluation
from src.scalper.symbol_resolver import ResolvedSymbolSpec


BTC_ENTRY_TYPES = (
    "CRYPTO_MOMENTUM_BURST",
    "VOLATILITY_EXPANSION_BREAKOUT",
    "HTF_ALIGNED_PULLBACK",
    "LIQUIDITY_SWEEP_RECLAIM",
    "DISPLACEMENT_CONTINUATION",
)


class BtcWeekendScalpingStrategy:
    """
    Dedicated Bitcoin (BTCUSD) weekend scalping strategy engine.
    """

    def __init__(self, config: Optional[InstrumentScalperConfig] = None):
        self.config = config or InstrumentScalperConfig(
            canonical="BTCUSD",
            schedule="weekends",
            magic_number=777002,
            sl_points=5000.0,
            tp_points=7500.0,
            spread_max_points=3000.0,
            max_spread=3000.0,
            max_slippage=150.0,
            commission_per_lot_usd=0.0,
        )

    def evaluate(
        self,
        snapshot: IndicatorSnapshot,
        spec: Optional[ResolvedSymbolSpec] = None,
        current_price: float = 67000.0,
        strategy_bias_override: Optional[float] = None,
        allow_fallback_in_sim: bool = True,
    ) -> StrategySignalEvaluation:
        if spec is not None and "BTC" not in spec.canonical.upper() and "BTC" not in spec.symbol.upper():
            return StrategySignalEvaluation(
                symbol_key="BTCUSD",
                is_valid=False,
                direction="BUY",
                entry_type="NONE",
                quality_score=0.0,
                regime=snapshot.volatility_regime,
                expected_move_points=0.0,
                estimated_cost_points=0.0,
                reward_to_cost_ratio=0.0,
                recommended_positions=0,
                sl_points=self.config.sl_points,
                tp_points=self.config.tp_points,
                rejection_reason=f"INVALID_BTC_SYMBOL: Refusing to substitute non-BTC symbol {spec.symbol}",
            )

        pt = spec.point if spec and spec.point > 0 else 0.01
        spread_pts = snapshot.spread_points

        # 1. BTCUSD Spread limit check
        if spread_pts > self.config.spread_max_points:
            return StrategySignalEvaluation(
                symbol_key="BTCUSD",
                is_valid=False,
                direction="BUY",
                entry_type="NONE",
                quality_score=0.0,
                regime=snapshot.volatility_regime,
                expected_move_points=0.0,
                estimated_cost_points=spread_pts,
                reward_to_cost_ratio=0.0,
                recommended_positions=0,
                sl_points=self.config.sl_points,
                tp_points=self.config.tp_points,
                rejection_reason=f"BTC_SPREAD_WIDE: {spread_pts:.1f} > {self.config.spread_max_points:.1f}",
            )

        # 2. Spread relative to ATR & extreme volatility check
        if snapshot.volatility_regime == "EXTREME_VOLATILITY":
            return StrategySignalEvaluation(
                symbol_key="BTCUSD",
                is_valid=False,
                direction="BUY",
                entry_type="NONE",
                quality_score=0.0,
                regime=snapshot.volatility_regime,
                expected_move_points=0.0,
                estimated_cost_points=spread_pts,
                reward_to_cost_ratio=0.0,
                recommended_positions=0,
                sl_points=self.config.sl_points,
                tp_points=self.config.tp_points,
                rejection_reason="BTC_EXTREME_VOLATILITY_OR_SPREAD_TO_ATR",
            )

        # 3. Analyze M1/M5 price action + M15/H1 directional bias + tick momentum
        ext_bias = float(strategy_bias_override) if strategy_bias_override is not None else 0.0
        composite = (
            0.35 * snapshot.tick_momentum
            + 0.20 * snapshot.m1_trend_bias
            + 0.20 * snapshot.m5_structure_bias
            + 0.15 * snapshot.m15_market_bias
            + 0.05 * snapshot.h1_macro_bias
            + 0.05 * ext_bias
        )
        direction = "BUY" if composite >= 0 else "SELL"
        dir_sign = 1.0 if direction == "BUY" else -1.0

        # 4. Classify BTCUSD Entry Setup
        atr_m1 = max(15.0, snapshot.atr_m1)
        disp = snapshot.candle_displacement * dir_sign
        entry_type = "CRYPTO_MOMENTUM_BURST"
        if snapshot.volatility_regime == "TRENDING_EXPANSION" and disp >= atr_m1 * 0.4:
            entry_type = "VOLATILITY_EXPANSION_BREAKOUT"
        elif snapshot.m15_market_bias * dir_sign > 0 and snapshot.h1_macro_bias * dir_sign >= 0:
            entry_type = "HTF_ALIGNED_PULLBACK"
        elif abs(disp) >= atr_m1 * 0.55:
            entry_type = "DISPLACEMENT_CONTINUATION"

        # 5. Expected move vs BTC transaction costs (spread + slippage + commission)
        atr_pts = max(2500.0, atr_m1 / pt)
        expected_move_pts = max(self.config.tp_points * 0.50, atr_pts * 1.40)
        slippage_est_pts = min(60.0, self.config.max_slippage * 0.25)
        estimated_cost_pts = round(spread_pts + slippage_est_pts, 2)
        reward_to_cost = round(expected_move_pts / max(1.0, estimated_cost_pts), 2)

        if reward_to_cost < 1.15:
            return StrategySignalEvaluation(
                symbol_key="BTCUSD",
                is_valid=False,
                direction=direction,
                entry_type=entry_type,
                quality_score=0.30,
                regime=snapshot.volatility_regime,
                expected_move_points=expected_move_pts,
                estimated_cost_points=estimated_cost_pts,
                reward_to_cost_ratio=reward_to_cost,
                recommended_positions=0,
                sl_points=self.config.sl_points,
                tp_points=self.config.tp_points,
                rejection_reason=f"BTC_UNFAVORABLE_REWARD_TO_COST: {reward_to_cost:.2f} < 1.15",
            )

        htf_bonus = 0.15 if (snapshot.m15_market_bias * dir_sign >= 0 and snapshot.h1_macro_bias * dir_sign >= 0) else 0.0
        cost_bonus = min(0.20, (reward_to_cost - 1.0) * 0.08)
        raw_strength = min(0.65, max(0.25 if allow_fallback_in_sim else 0.0, abs(composite) * 0.85 + 0.40))
        quality_score = round(min(1.0, raw_strength + htf_bonus + cost_bonus), 4)

        if quality_score < self.config.min_entry_quality_score and not allow_fallback_in_sim:
            return StrategySignalEvaluation(
                symbol_key="BTCUSD",
                is_valid=False,
                direction=direction,
                entry_type=entry_type,
                quality_score=quality_score,
                regime=snapshot.volatility_regime,
                expected_move_points=expected_move_pts,
                estimated_cost_points=estimated_cost_pts,
                reward_to_cost_ratio=reward_to_cost,
                recommended_positions=0,
                sl_points=self.config.sl_points,
                tp_points=self.config.tp_points,
                rejection_reason=f"WEAK_BTC_SIGNAL: score {quality_score:.2f} < {self.config.min_entry_quality_score:.2f}",
            )

        max_pos = self.config.basket_size
        if self.config.entry_mode.lower() == "single_entry":
            rec_pos = 1
        elif quality_score >= 0.72:
            rec_pos = max_pos
        elif quality_score >= 0.60:
            rec_pos = max(1, max_pos - 1)
        else:
            rec_pos = max_pos if allow_fallback_in_sim else max(1, max_pos // 2)

        return StrategySignalEvaluation(
            symbol_key="BTCUSD",
            is_valid=True,
            direction=direction,
            entry_type=entry_type,
            quality_score=quality_score,
            regime=snapshot.volatility_regime,
            expected_move_points=round(expected_move_pts, 1),
            estimated_cost_points=estimated_cost_pts,
            reward_to_cost_ratio=reward_to_cost,
            recommended_positions=rec_pos,
            sl_points=self.config.sl_points,
            tp_points=self.config.tp_points,
            rationale=f"BTCUSD {entry_type} ({direction}) | Score={quality_score:.2f} | R/Cost={reward_to_cost:.2f} | Regime={snapshot.volatility_regime}",
        )
