"""
Adaptive Market Regime Detection and Profiling for ATI.
Classifies live and historical market conditions into measurable states:
STRONG_BULLISH, STRONG_BEARISH, SIDEWAYS_CONSOLIDATION, HIGH_VOLATILITY, LOW_VOLATILITY, UNSTABLE_SPREAD.
Segments strategy performance across regimes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from src.intelligence.contracts import (
    CompletedPositionRecord,
    MarketRegimeSnapshot,
    MarketRegimeType,
    utc_now,
)
from src.intelligence.storage.repository import ATIRepository

logger = logging.getLogger("ATI.Regime")


class MarketRegimeDetector:
    """
    Classifies market regimes using objective statistical measures:
    trend slope, ADX strength, ATR volatility ratio, and spread stability.
    """

    def __init__(self, repo: Optional[ATIRepository] = None):
        self.repo = repo

    def detect_regime(
        self,
        canonical_symbol: str,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        spread_pts: float = 15.0,
        session_name: str = "LONDON",
        timestamp: Optional[datetime] = None,
    ) -> MarketRegimeSnapshot:
        """Computes objective regime classification from candle arrays."""
        ts = timestamp or utc_now()
        n = len(closes)

        if n < 14:
            snap = MarketRegimeSnapshot(
                canonical_symbol=canonical_symbol,
                timestamp=ts,
                regime=MarketRegimeType.UNKNOWN,
                confidence=0.3,
                session_name=session_name,
            )
            if self.repo:
                self.repo.record_market_regime(snap)
            return snap

        # 1. Spread Check
        if spread_pts > 45.0:
            snap = MarketRegimeSnapshot(
                canonical_symbol=canonical_symbol,
                timestamp=ts,
                regime=MarketRegimeType.UNSTABLE_SPREAD,
                confidence=0.90,
                spread_pts=spread_pts,
                session_name=session_name,
            )
            if self.repo:
                self.repo.record_market_regime(snap)
            return snap

        # 2. Volatility (ATR)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        atr_14 = float(np.mean(tr[-14:]))
        atr_baseline = float(np.mean(tr)) if len(tr) >= 30 else atr_14
        vol_ratio = (atr_14 / atr_baseline) if atr_baseline > 0 else 1.0

        # 3. Trend Slope & Linear Regression
        x = np.arange(min(20, n))
        y = closes[-len(x):]
        slope, _ = np.polyfit(x, y, 1)
        pct_slope = (slope / closes[-1]) * 100.0

        # 4. ADX Approximation (Directional Movement)
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        sum_tr = np.sum(tr[-14:]) + 1e-6
        plus_di = 100.0 * (np.sum(plus_dm[-14:]) / sum_tr)
        minus_di = 100.0 * (np.sum(minus_dm[-14:]) / sum_tr)
        dx = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-6)
        adx = float(dx)

        # Classification logic
        if vol_ratio > 1.8:
            regime = MarketRegimeType.HIGH_VOLATILITY
            conf = min(0.95, 0.5 + (vol_ratio - 1.0) * 0.25)
        elif vol_ratio < 0.6:
            regime = MarketRegimeType.LOW_VOLATILITY
            conf = 0.85
        elif adx > 25.0 and pct_slope > 0.05:
            regime = MarketRegimeType.STRONG_BULLISH
            conf = min(0.95, 0.6 + (adx / 100.0))
        elif adx > 25.0 and pct_slope < -0.05:
            regime = MarketRegimeType.STRONG_BEARISH
            conf = min(0.95, 0.6 + (adx / 100.0))
        else:
            regime = MarketRegimeType.SIDEWAYS_CONSOLIDATION
            conf = 0.75

        snapshot = MarketRegimeSnapshot(
            canonical_symbol=canonical_symbol,
            timestamp=ts,
            regime=regime,
            confidence=round(conf, 2),
            adx_value=round(adx, 2),
            atr_value=round(atr_14, 5),
            trend_slope=round(pct_slope, 4),
            volatility_ratio=round(vol_ratio, 2),
            spread_pts=round(spread_pts, 1),
            session_name=session_name,
            features={"pct_slope": pct_slope, "plus_di": plus_di, "minus_di": minus_di},
        )

        if self.repo:
            self.repo.record_market_regime(snapshot)

        return snapshot

    @classmethod
    def segment_performance_by_regime(
        cls,
        positions: List[CompletedPositionRecord],
    ) -> Dict[str, Dict[str, Any]]:
        """Calculates win rate, net profit, and trade count partitioned by market regime."""
        regime_stats: Dict[str, Dict[str, Any]] = {}

        for pos in positions:
            r = pos.features_snapshot.get("regime", "UNKNOWN")
            if r not in regime_stats:
                regime_stats[r] = {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "net_profit": 0.0,
                    "win_rate_pct": 0.0,
                }
            s = regime_stats[r]
            s["total_trades"] += 1
            if pos.realized_net_profit > 0:
                s["wins"] += 1
            else:
                s["losses"] += 1
            s["net_profit"] = round(s["net_profit"] + pos.normalized_net_profit, 2)

        for r, s in regime_stats.items():
            tot = s["total_trades"]
            s["win_rate_pct"] = round((s["wins"] / tot * 100.0) if tot > 0 else 0.0, 1)

        return regime_stats
