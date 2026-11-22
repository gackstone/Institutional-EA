"""
Intelligent Signal Scoring Engine.
Synthesizes individual strategy signals, market regime, higher-timeframe trend context,
and momentum into independent, weighted BUY and SELL confidence scores.
Enforces decision thresholds, minimum directional advantage, and transparent diagnostics.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import Candle, OrderType, Timeframe, TrendBias
from src.engine.market_intelligence import (
    MarketIntelligenceEngine,
    MarketSnapshot,
    DetailedMarketRegime,
)
from src.strategies.scalping_strategies import (
    BaseScalpingStrategy,
    StrategySignal,
    EmaTrendScalpingStrategy,
    RsiMomentumScalpingStrategy,
    MacdMomentumScalpingStrategy,
    BollingerBandScalpingStrategy,
    AtrVolatilityScalpingStrategy,
    PriceActionCandleStrategy,
    DirectionalEfficiencyStrategy,
)

logger = logging.getLogger("IntelligentScoring")


@dataclass
class ScoringWeightsConfig:
    # Baseline Research Weights (Sum = 100.0%)
    htf_trend_weight: float = 0.20          # Higher-timeframe trend (M15/H1)
    ema_weight: float = 0.15                # EMA directional alignment
    rsi_weight: float = 0.10                # RSI momentum
    macd_weight: float = 0.10               # MACD momentum
    price_action_weight: float = 0.15       # Price action & candle anatomy
    atr_volatility_weight: float = 0.10     # ATR & volatility context
    directional_efficiency_weight: float = 0.10 # Directional efficiency
    short_term_momentum_weight: float = 0.10    # Short-term M1 momentum
    bollinger_bands_weight: float = 0.05    # Bollinger Band interaction

    # Thresholds
    decision_threshold: float = 55.0        # Minimum score to trigger a trade (55-65)
    min_directional_advantage: float = 8.0  # Buy vs Sell score advantage required


@dataclass
class ScoredDecisionResult:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    direction: Optional[OrderType]
    buy_score: float
    sell_score: float
    net_advantage: float
    decision_threshold: float
    min_advantage_threshold: float
    is_qualified: bool
    rejection_reason: Optional[str]
    regime: DetailedMarketRegime
    strategy_signals: Dict[str, StrategySignal] = field(default_factory=dict)
    recommended_entry_price: float = 0.0
    recommended_sl: float = 0.0
    recommended_tp: float = 0.0
    recommended_rr: float = 0.0
    sl_distance: float = 0.0
    tp_distance: float = 0.0
    applied_weights: Dict[str, float] = field(default_factory=dict)
    diagnostics_log: str = ""


class IntelligentScoringEngine:
    """
    Unified BUY/SELL signal-scoring engine.
    Combines independent strategy modules, regime adaptations, and multi-timeframe context
    to make transparent, robust trading decisions without over-filtering.
    """

    def __init__(
        self,
        weights_config: Optional[ScoringWeightsConfig] = None,
        strategies: Optional[List[BaseScalpingStrategy]] = None,
    ):
        self.config = weights_config or ScoringWeightsConfig()

        # Initialize default 7 strategies if none provided
        if strategies is not None:
            self.strategies: List[BaseScalpingStrategy] = list(strategies)
        else:
            self.strategies = [
                EmaTrendScalpingStrategy(weight=self.config.ema_weight),
                RsiMomentumScalpingStrategy(weight=self.config.rsi_weight),
                MacdMomentumScalpingStrategy(weight=self.config.macd_weight),
                BollingerBandScalpingStrategy(weight=self.config.bollinger_bands_weight),
                AtrVolatilityScalpingStrategy(weight=self.config.atr_volatility_weight),
                PriceActionCandleStrategy(weight=self.config.price_action_weight),
                DirectionalEfficiencyStrategy(weight=self.config.directional_efficiency_weight),
            ]

    def _get_regime_adapted_weights(self, regime: DetailedMarketRegime) -> Dict[str, float]:
        """
        Dynamically modulates strategy weights based on detected market regime.
        - Trending: boosts EMA, MACD, and Directional Efficiency.
        - Ranging: boosts Bollinger Bands and RSI mean-reversion, lowers EMA.
        - Breakout: boosts Price Action and short-term momentum.
        - High Volatility: boosts ATR Volatility and Price Action.
        """
        w = {
            "HTF_TREND": self.config.htf_trend_weight,
            "EMA_TREND": self.config.ema_weight,
            "RSI_MOMENTUM": self.config.rsi_weight,
            "MACD_MOMENTUM": self.config.macd_weight,
            "PRICE_ACTION": self.config.price_action_weight,
            "ATR_VOLATILITY": self.config.atr_volatility_weight,
            "DIRECTIONAL_EFFICIENCY": self.config.directional_efficiency_weight,
            "SHORT_TERM_MOMENTUM": self.config.short_term_momentum_weight,
            "BOLLINGER_BANDS": self.config.bollinger_bands_weight,
        }

        if regime in (DetailedMarketRegime.TRENDING_BULLISH, DetailedMarketRegime.TRENDING_BEARISH):
            w["EMA_TREND"] *= 1.30
            w["MACD_MOMENTUM"] *= 1.25
            w["DIRECTIONAL_EFFICIENCY"] *= 1.30
            w["HTF_TREND"] *= 1.20
            w["BOLLINGER_BANDS"] *= 0.70
        elif regime == DetailedMarketRegime.RANGING:
            w["BOLLINGER_BANDS"] *= 1.60
            w["RSI_MOMENTUM"] *= 1.40
            w["EMA_TREND"] *= 0.65
            w["DIRECTIONAL_EFFICIENCY"] *= 0.70
            w["HTF_TREND"] *= 0.80
        elif regime == DetailedMarketRegime.BREAKOUT:
            w["PRICE_ACTION"] *= 1.40
            w["SHORT_TERM_MOMENTUM"] *= 1.35
            w["ATR_VOLATILITY"] *= 1.25
            w["BOLLINGER_BANDS"] *= 1.20
        elif regime == DetailedMarketRegime.HIGH_VOLATILITY:
            w["ATR_VOLATILITY"] *= 1.50
            w["PRICE_ACTION"] *= 1.25
            w["HTF_TREND"] *= 1.10
        elif regime == DetailedMarketRegime.REVERSAL:
            w["PRICE_ACTION"] *= 1.45
            w["RSI_MOMENTUM"] *= 1.30
            w["EMA_TREND"] *= 0.80

        # Normalize total sum of weights to 1.0
        total = sum(w.values())
        if total > 0:
            for k in w:
                w[k] = w[k] / total
        return w

    def _evaluate_htf_trend_contribution(
        self,
        m15_snapshot: Optional[MarketSnapshot],
        h1_snapshot: Optional[MarketSnapshot],
    ) -> Tuple[float, float, str]:
        """
        Computes (htf_buy_points, htf_sell_points, description) for HTF trend context.
        Scale: 0.0 to 100.0.
        """
        if not m15_snapshot and not h1_snapshot:
            return 50.0, 50.0, "No HTF snapshot available (Neutral 50/50)"

        buy_pts = 0.0
        sell_pts = 0.0
        notes = []

        for tf_name, snap in [("M15", m15_snapshot), ("H1", h1_snapshot)]:
            if snap is None:
                continue
            if snap.direction == TrendBias.STRONG_BULLISH:
                buy_pts += 50.0
                notes.append(f"{tf_name}=StrongBull")
            elif snap.direction == TrendBias.WEAK_BULLISH:
                buy_pts += 35.0
                sell_pts += 10.0
                notes.append(f"{tf_name}=WeakBull")
            elif snap.direction == TrendBias.STRONG_BEARISH:
                sell_pts += 50.0
                notes.append(f"{tf_name}=StrongBear")
            elif snap.direction == TrendBias.WEAK_BEARISH:
                sell_pts += 35.0
                buy_pts += 10.0
                notes.append(f"{tf_name}=WeakBear")
            else:
                buy_pts += 25.0
                sell_pts += 25.0
                notes.append(f"{tf_name}=Ranging")

        return min(100.0, buy_pts), min(100.0, sell_pts), "; ".join(notes)

    def _evaluate_short_term_momentum_contribution(
        self,
        snapshot: MarketSnapshot,
    ) -> Tuple[float, float]:
        """
        Computes (momentum_buy_pts, momentum_sell_pts) from M1 momentum score [-100, 100].
        Scale: 0.0 to 100.0.
        """
        mom = snapshot.momentum_score  # [-100.0, 100.0]
        if mom > 0:
            buy_pts = 50.0 + (mom * 0.5)
            sell_pts = max(0.0, 50.0 - (mom * 0.5))
        else:
            sell_pts = 50.0 + (abs(mom) * 0.5)
            buy_pts = max(0.0, 50.0 - (abs(mom) * 0.5))
        return min(100.0, buy_pts), min(100.0, sell_pts)

    def evaluate_symbol(
        self,
        symbol: str,
        m1_candles: List[Candle],
        m1_snapshot: MarketSnapshot,
        m15_snapshot: Optional[MarketSnapshot] = None,
        h1_snapshot: Optional[MarketSnapshot] = None,
        current_spread_pts: float = 1.0,
        point_size: float = 0.00001,
        timeframe: Timeframe = Timeframe.M1,
    ) -> ScoredDecisionResult:
        """
        Evaluates a symbol, running all strategies and generating composite BUY/SELL scores.
        """
        now = datetime.now(timezone.utc)
        applied_weights = self._get_regime_adapted_weights(m1_snapshot.regime)

        # 1. Evaluate Individual Strategies
        strategy_signals: Dict[str, StrategySignal] = {}
        for strategy in self.strategies:
            if not strategy.enabled:
                continue
            sig = strategy.evaluate(symbol, m1_candles, m1_snapshot, timeframe=timeframe)
            strategy_signals[sig.strategy_name] = sig

        # 2. HTF Trend Component (20% default)
        htf_buy, htf_sell, htf_desc = self._evaluate_htf_trend_contribution(m15_snapshot, h1_snapshot)

        # 3. Short-Term Momentum Component (10% default)
        mom_buy, mom_sell = self._evaluate_short_term_momentum_contribution(m1_snapshot)

        # 4. Aggregate Composite BUY and SELL Scores
        weighted_buy = 0.0
        weighted_sell = 0.0

        weighted_buy += htf_buy * applied_weights.get("HTF_TREND", 0.20)
        weighted_sell += htf_sell * applied_weights.get("HTF_TREND", 0.20)

        weighted_buy += mom_buy * applied_weights.get("SHORT_TERM_MOMENTUM", 0.10)
        weighted_sell += mom_sell * applied_weights.get("SHORT_TERM_MOMENTUM", 0.10)

        for strat_name, sig in strategy_signals.items():
            w = applied_weights.get(strat_name, 0.10)
            weighted_buy += sig.buy_strength * w
            weighted_sell += sig.sell_strength * w

        # Market quality penalty (non-blocking score adjustment rather than automatic suppression)
        if m1_snapshot.spread_atr_ratio > 0.50:
            penalty = min(12.0, (m1_snapshot.spread_atr_ratio - 0.50) * 15.0)
            weighted_buy = max(0.0, weighted_buy - penalty)
            weighted_sell = max(0.0, weighted_sell - penalty)

        buy_score = round(min(100.0, max(0.0, weighted_buy)), 1)
        sell_score = round(min(100.0, max(0.0, weighted_sell)), 1)
        net_advantage = round(abs(buy_score - sell_score), 1)

        # 5. Check Qualification and Direction
        direction: Optional[OrderType] = None
        is_qualified = False
        rejection_reasons: List[str] = []

        # Hard gating safety checks (Reserved ONLY for genuine data integrity failures)
        if not m1_snapshot.data_quality_healthy:
            rejection_reasons.append("Data quality degraded or insufficient history")
        else:
            # Weighted scoring check
            thresh = self.config.decision_threshold
            min_adv = self.config.min_directional_advantage

            if buy_score >= thresh and (buy_score - sell_score) >= min_adv:
                direction = OrderType.BUY
                is_qualified = True
            elif sell_score >= thresh and (sell_score - buy_score) >= min_adv:
                direction = OrderType.SELL
                is_qualified = True
            else:
                if max(buy_score, sell_score) < thresh:
                    rejection_reasons.append(
                        f"Score below threshold ({max(buy_score, sell_score):.1f} < {thresh:.1f})"
                    )
                if net_advantage < min_adv:
                    rejection_reasons.append(
                        f"Insufficient directional advantage ({net_advantage:.1f} < {min_adv:.1f})"
                    )

        # 6. Suggested SL, TP, and R:R
        last_close = m1_candles[-1].close if m1_candles else 0.0
        atr = max(m1_snapshot.current_atr, 1e-6)

        # Consensus SL/TP from strategies
        sl_distances = [
            s.suggested_sl_distance for s in strategy_signals.values() if s.suggested_sl_distance > 0
        ]
        tp_distances = [
            s.suggested_tp_distance for s in strategy_signals.values() if s.suggested_tp_distance > 0
        ]
        avg_sl_dist = sum(sl_distances) / len(sl_distances) if sl_distances else 1.2 * atr
        avg_tp_dist = sum(tp_distances) / len(tp_distances) if tp_distances else 1.8 * atr

        entry_price = last_close
        if direction == OrderType.BUY:
            sl_price = round(entry_price - avg_sl_dist, 5)
            tp_price = round(entry_price + avg_tp_dist, 5)
        elif direction == OrderType.SELL:
            sl_price = round(entry_price + avg_sl_dist, 5)
            tp_price = round(entry_price - avg_tp_dist, 5)
        else:
            sl_price = 0.0
            tp_price = 0.0

        rr_ratio = round(avg_tp_dist / avg_sl_dist, 2) if avg_sl_dist > 0 else 0.0

        # Construct Diagnostic Log line
        strat_summary = ", ".join(
            f"{name}(B:{sig.buy_strength:.0f}/S:{sig.sell_strength:.0f})"
            for name, sig in strategy_signals.items()
        )
        diag = (
            f"[{symbol} {timeframe.value}] Scores: BUY={buy_score:.1f}, SELL={sell_score:.1f}, "
            f"NetAdv={net_advantage:.1f} | Regime={m1_snapshot.regime.value} | HTF=[{htf_desc}] | "
            f"Strategies: {strat_summary}"
        )
        if not is_qualified:
            diag += f" | REJECTED: {'; '.join(rejection_reasons)}"
        else:
            diag += f" | APPROVED: {direction.value if direction else 'NONE'} @ {entry_price:.5f} SL={sl_price:.5f} TP={tp_price:.5f} (RR={rr_ratio})"

        return ScoredDecisionResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now,
            direction=direction,
            buy_score=buy_score,
            sell_score=sell_score,
            net_advantage=net_advantage,
            decision_threshold=self.config.decision_threshold,
            min_advantage_threshold=self.config.min_directional_advantage,
            is_qualified=is_qualified,
            rejection_reason="; ".join(rejection_reasons) if rejection_reasons else None,
            regime=m1_snapshot.regime,
            strategy_signals=strategy_signals,
            recommended_entry_price=entry_price,
            recommended_sl=sl_price,
            recommended_tp=tp_price,
            recommended_rr=rr_ratio,
            sl_distance=avg_sl_dist,
            tp_distance=avg_tp_dist,
            applied_weights=applied_weights,
            diagnostics_log=diag,
        )
