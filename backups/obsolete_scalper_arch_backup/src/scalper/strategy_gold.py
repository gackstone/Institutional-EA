"""
Phase 5: Dedicated Short-Term GOLD (XAUUSD) Weekday Scalping Strategy Engine.
Analyzes:
- M1 price action, M5 directional structure, M15 market bias
- Spread and volatility, tick momentum, short-term tick activity
- Candle displacement, recent swing highs/lows, support & resistance
- Breakout and rejection behavior, ATR and volatility regime
Classifies 5 explicit entry types:
1. MOMENTUM_CONTINUATION
2. CONFIRMED_BREAKOUT
3. PULLBACK_CONTINUATION
4. LIQUIDITY_SWEEP_CONFIRMED
5. SIGNIFICANT_LEVEL_REJECTION
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from src.scalper.config import InstrumentScalperConfig
from src.scalper.market_cache import IndicatorSnapshot
from src.scalper.symbol_resolver import ResolvedSymbolSpec


GOLD_ENTRY_TYPES = (
    "MOMENTUM_CONTINUATION",
    "CONFIRMED_BREAKOUT",
    "PULLBACK_CONTINUATION",
    "LIQUIDITY_SWEEP_CONFIRMED",
    "SIGNIFICANT_LEVEL_REJECTION",
)


@dataclass
class StrategySignalEvaluation:
    symbol_key: str
    is_valid: bool
    direction: str                  # "BUY" or "SELL"
    entry_type: str                 # One of GOLD_ENTRY_TYPES or "NONE"
    quality_score: float            # [0.0, 1.0]
    regime: str
    expected_move_points: float
    estimated_cost_points: float
    reward_to_cost_ratio: float
    recommended_positions: int
    sl_points: float
    tp_points: float
    rejection_reason: str = ""
    rationale: str = ""


class GoldScalpingStrategy:
    """
    Dedicated XAUUSD weekday strategy engine using separate GOLD parameters.
    Never inherits BTCUSD spread, volatility, or stop-loss parameters.
    """

    def __init__(self, config: Optional[InstrumentScalperConfig] = None):
        self.config = config or InstrumentScalperConfig(
            canonical="XAUUSD",
            magic_number=777001,
            sl_points=300.0,
            tp_points=450.0,
            spread_max_points=80.0,
            max_spread=80.0,
            max_slippage=25.0,
        )

    def evaluate(
        self,
        snapshot: IndicatorSnapshot,
        spec: Optional[ResolvedSymbolSpec] = None,
        current_price: float = 2650.0,
        strategy_bias_override: Optional[float] = None,
        allow_fallback_in_sim: bool = True,
    ) -> StrategySignalEvaluation:
        pt = spec.point if spec and spec.point > 0 else 0.01
        spread_pts = snapshot.spread_points

        # 1. Spread check against GOLD max_spread
        if spread_pts > self.config.spread_max_points:
            return StrategySignalEvaluation(
                symbol_key="GOLD",
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
                rejection_reason=f"GOLD_SPREAD_WIDE: {spread_pts:.1f} > {self.config.spread_max_points:.1f}",
            )

        # 2. Abnormal volatility regime check
        if snapshot.volatility_regime == "EXTREME_VOLATILITY":
            return StrategySignalEvaluation(
                symbol_key="GOLD",
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
                rejection_reason="GOLD_EXTREME_VOLATILITY_REGIME",
            )

        # 3. Directional composite from M1 price action, M5 structure, M15 market bias, and tick momentum
        ext_bias = float(strategy_bias_override) if strategy_bias_override is not None else 0.0
        composite = (
            0.35 * snapshot.tick_momentum
            + 0.25 * snapshot.m1_trend_bias
            + 0.20 * snapshot.m5_structure_bias
            + 0.10 * snapshot.m15_market_bias
            + 0.10 * ext_bias
        )
        direction = "BUY" if composite >= 0 else "SELL"
        dir_sign = 1.0 if direction == "BUY" else -1.0

        # 4. Classify GOLD Entry Type
        disp = snapshot.candle_displacement * dir_sign
        atr_m1 = max(0.20, snapshot.atr_m1)
        entry_type = "MOMENTUM_CONTINUATION"

        if snapshot.swing_high_m1 > 0 and snapshot.swing_low_m1 > 0:
            if direction == "BUY" and current_price >= snapshot.swing_high_m1 and disp >= atr_m1 * 0.35:
                entry_type = "CONFIRMED_BREAKOUT"
            elif direction == "SELL" and current_price <= snapshot.swing_low_m1 and disp >= atr_m1 * 0.35:
                entry_type = "CONFIRMED_BREAKOUT"
            elif direction == "BUY" and current_price <= snapshot.support_level + atr_m1 * 0.25 and snapshot.tick_momentum > 0.15:
                entry_type = "LIQUIDITY_SWEEP_CONFIRMED"
            elif direction == "SELL" and current_price >= snapshot.resistance_level - atr_m1 * 0.25 and snapshot.tick_momentum < -0.15:
                entry_type = "LIQUIDITY_SWEEP_CONFIRMED"
            elif (direction == "BUY" and snapshot.rsi_m1 < 42.0 and snapshot.m5_structure_bias > 0) or (
                direction == "SELL" and snapshot.rsi_m1 > 58.0 and snapshot.m5_structure_bias < 0
            ):
                entry_type = "PULLBACK_CONTINUATION"
            elif abs(disp) >= atr_m1 * 0.50 and snapshot.m15_market_bias * dir_sign < 0:
                entry_type = "SIGNIFICANT_LEVEL_REJECTION"

        # 5. Expected move vs transaction costs (spread + commission + expected slippage)
        atr_pts = max(80.0, atr_m1 / pt)
        expected_move_pts = max(self.config.tp_points * 0.45, atr_pts * 1.35)
        comm_pts = (self.config.commission_per_lot_usd * 0.01) / max(1e-6, pt)
        slippage_est_pts = min(10.0, self.config.max_slippage * 0.25)
        estimated_cost_pts = round(spread_pts + comm_pts + slippage_est_pts, 2)
        reward_to_cost = round(expected_move_pts / max(1.0, estimated_cost_pts), 2)

        if reward_to_cost < 1.25:
            return StrategySignalEvaluation(
                symbol_key="GOLD",
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
                rejection_reason=f"UNFAVORABLE_REWARD_TO_COST: {reward_to_cost:.2f} < 1.25",
            )

        # 6. Entry quality score [0.0, 1.0]
        alignment_bonus = 0.15 if (snapshot.m5_structure_bias * dir_sign >= 0 and snapshot.m15_market_bias * dir_sign >= 0) else 0.0
        cost_bonus = min(0.20, (reward_to_cost - 1.0) * 0.06)
        raw_strength = min(0.65, max(0.22 if allow_fallback_in_sim else 0.0, abs(composite) * 0.85 + 0.38))
        quality_score = round(min(1.0, raw_strength + alignment_bonus + cost_bonus), 4)

        if quality_score < self.config.min_entry_quality_score and not allow_fallback_in_sim:
            return StrategySignalEvaluation(
                symbol_key="GOLD",
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
                rejection_reason=f"WEAK_GOLD_SIGNAL: score {quality_score:.2f} < {self.config.min_entry_quality_score:.2f}",
            )

        # Scale recommended positions by signal quality up to configured basket_size
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
            symbol_key="GOLD",
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
            rationale=f"GOLD {entry_type} ({direction}) | Score={quality_score:.2f} | R/Cost={reward_to_cost:.2f} | Regime={snapshot.volatility_regime}",
        )
