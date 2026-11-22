"""
Dedicated XAUUSD and USDJPY Inverse Directional Coordination Engine.
Governs the coordinated trading relationship:
- XAUUSD BUY  -> USDJPY preferred direction: SELL
- XAUUSD SELL -> USDJPY preferred direction: BUY

Features:
1. Rolling Pearson correlation analysis between XAUUSD and USDJPY returns.
2. Market regime classification (INVERSE_STRONG, INVERSE_MODERATE, UNCORRELATED, POSITIVE_BREAKDOWN).
3. Weakened correlation detection: avoids forcing inverse bias when market correlation breaks down.
4. Independent confirmation requirement: USDJPY ALWAYS requires its own technical setup.
5. Non-blocking invariant: A valid XAUUSD trade is NEVER blocked if USDJPY fails to confirm.
6. Shared directional state persistence and stale-signal invalidation.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, NamedTuple

from src.core.contracts import Candle, OrderType, SignalCandidate, TrendBias

logger = logging.getLogger("InverseCoordinator")


class CorrelationRegime(str, Enum):
    INVERSE_STRONG = "INVERSE_STRONG"          # r < -0.50 (Reliable inverse relationship)
    INVERSE_MODERATE = "INVERSE_MODERATE"      # -0.50 <= r < -0.20 (Standard inverse relationship)
    UNCORRELATED = "UNCORRELATED"              # -0.20 <= r <= 0.20 (Independent price action)
    POSITIVE_BREAKDOWN = "POSITIVE_BREAKDOWN"  # r > 0.20 (Relationship broken down / co-moving)


class CoordinationEvaluationResult(NamedTuple):
    is_approved: bool
    rationale: str
    score_adjustment: float
    regime: CorrelationRegime = CorrelationRegime.INVERSE_MODERATE
    correlation: float = -0.50

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_approved": self.is_approved,
            "rationale": self.rationale,
            "score_adjustment": self.score_adjustment,
            "regime": getattr(self.regime, "value", str(self.regime)),
            "correlation": self.correlation,
        }


@dataclass
class InverseCoordinationState:
    xauusd_bias: str = "NEUTRAL"                           # BULLISH, BEARISH, NEUTRAL
    xauusd_last_signal_direction: Optional[OrderType] = None
    xauusd_last_signal_time: Optional[datetime] = None
    usdjpy_preferred_direction: Optional[OrderType] = None  # SELL if XAUUSD BUY, BUY if XAUUSD SELL
    correlation_value: float = -0.55                       # Rolling correlation coefficient
    correlation_regime: CorrelationRegime = CorrelationRegime.INVERSE_MODERATE
    is_inverse_valid: bool = True                          # True when regime is INVERSE_STRONG or INVERSE_MODERATE
    signal_validity_duration_minutes: int = 120            # Invalidate directional signals older than 2 hours
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_coordinated_positions: Dict[str, List[int]] = field(default_factory=lambda: {"XAUUSD": [], "USDJPY": []})

    def is_signal_fresh(self, current_time: Optional[datetime] = None) -> bool:
        if not self.xauusd_last_signal_time:
            return False
        now = current_time or datetime.now(timezone.utc)
        return (now - self.xauusd_last_signal_time) < timedelta(minutes=self.signal_validity_duration_minutes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xauusd_bias": self.xauusd_bias,
            "xauusd_last_signal_direction": self.xauusd_last_signal_direction.value if self.xauusd_last_signal_direction else None,
            "xauusd_last_signal_time": self.xauusd_last_signal_time.isoformat() if self.xauusd_last_signal_time else None,
            "usdjpy_preferred_direction": self.usdjpy_preferred_direction.value if self.usdjpy_preferred_direction else None,
            "correlation_value": round(self.correlation_value, 4),
            "correlation_regime": self.correlation_regime.value,
            "is_inverse_valid": self.is_inverse_valid,
            "is_signal_fresh": self.is_signal_fresh(),
            "last_updated": self.last_updated.isoformat(),
            "active_coordinated_positions": dict(self.active_coordinated_positions),
        }


class InverseDirectionCoordinator:
    """
    Coordinates directional preferences between Gold (XAUUSD) and US Dollar / Yen (USDJPY).
    Ensures both instruments trade with confluences while maintaining strictly independent risk controls.
    """

    def __init__(
        self,
        lookback_bars: int = 30,
        strong_inverse_threshold: float = -0.50,
        moderate_inverse_threshold: float = -0.20,
        positive_breakdown_threshold: float = 0.20,
        signal_validity_minutes: int = 120,
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.lookback_bars = lookback_bars
        self.strong_inverse_threshold = strong_inverse_threshold
        self.moderate_inverse_threshold = moderate_inverse_threshold
        self.positive_breakdown_threshold = positive_breakdown_threshold
        self.signal_validity_minutes = signal_validity_minutes
        self.state = InverseCoordinationState(
            signal_validity_duration_minutes=signal_validity_minutes
        )

    @property
    def preferred_usdjpy_direction(self) -> Optional[OrderType]:
        return self.state.usdjpy_preferred_direction

    @property
    def xauusd_bias(self) -> Optional[OrderType]:
        return self.state.xauusd_last_signal_direction

    @property
    def current_correlation(self) -> float:
        return self.state.correlation_value

    @current_correlation.setter
    def current_correlation(self, val: float) -> None:
        self.state.correlation_value = val

    @property
    def regime(self) -> CorrelationRegime:
        return self.state.correlation_regime

    @regime.setter
    def regime(self, r: CorrelationRegime) -> None:
        self.state.correlation_regime = r

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "xauusd_direction": self.state.xauusd_bias,
            "usdjpy_preferred_direction": self.state.usdjpy_preferred_direction.value if self.state.usdjpy_preferred_direction else "NONE",
            "correlation_regime": self.state.correlation_regime.value,
            "current_correlation": self.state.correlation_value,
            "is_inverse_valid": self.state.is_inverse_valid,
        }

    def calculate_correlation(
        self,
        xau_candles: List[Candle],
        usdjpy_candles: List[Candle],
        lookback: Optional[int] = None
    ) -> float:
        return self.compute_rolling_correlation(xau_candles, usdjpy_candles, lookback)

    def compute_rolling_correlation(
        self,
        xau_candles: List[Candle],
        usdjpy_candles: List[Candle],
        lookback: Optional[int] = None
    ) -> float:
        """
        Calculates Pearson correlation of price returns between XAUUSD and USDJPY.
        """
        lb = lookback or self.lookback_bars
        if not xau_candles or not usdjpy_candles or len(xau_candles) < lb or len(usdjpy_candles) < lb:
            return self.state.correlation_value

        # Align lengths
        n = min(len(xau_candles), len(usdjpy_candles), lb + 1)
        x_closes = [c.close for c in xau_candles[-n:]]
        y_closes = [c.close for c in usdjpy_candles[-n:]]

        # Calculate percentage returns
        x_returns = [(x_closes[i] - x_closes[i - 1]) / x_closes[i - 1] for i in range(1, len(x_closes)) if x_closes[i - 1] > 0]
        y_returns = [(y_closes[i] - y_closes[i - 1]) / y_closes[i - 1] for i in range(1, len(y_closes)) if y_closes[i - 1] > 0]

        m = min(len(x_returns), len(y_returns))
        if m < 5:
            return self.state.correlation_value

        x_ret = x_returns[-m:]
        y_ret = y_returns[-m:]

        mean_x = sum(x_ret) / m
        mean_y = sum(y_ret) / m

        cov = sum((x_ret[i] - mean_x) * (y_ret[i] - mean_y) for i in range(m))
        var_x = sum((x_ret[i] - mean_x) ** 2 for i in range(m))
        var_y = sum((y_ret[i] - mean_y) ** 2 for i in range(m))

        if var_x <= 1e-12 or var_y <= 1e-12:
            corr = 0.0
        else:
            corr = cov / math.sqrt(var_x * var_y)
            corr = max(-1.0, min(1.0, corr))

        # Classify regime
        if corr < self.strong_inverse_threshold:
            regime = CorrelationRegime.INVERSE_STRONG
            is_valid = True
        elif corr < self.moderate_inverse_threshold:
            regime = CorrelationRegime.INVERSE_MODERATE
            is_valid = True
        elif corr > self.positive_breakdown_threshold:
            regime = CorrelationRegime.POSITIVE_BREAKDOWN
            is_valid = False
        else:
            regime = CorrelationRegime.UNCORRELATED
            is_valid = False

        self.state.correlation_value = round(corr, 4)
        self.state.correlation_regime = regime
        self.state.is_inverse_valid = is_valid
        self.state.last_updated = datetime.now(timezone.utc)

        if is_valid:
            logger.info(
                f"[CORRELATION_ENGINE] XAUUSD/USDJPY inverse relationship validated "
                f"(r={corr:.2f}, regime={regime.value})."
            )
        else:
            logger.warning(
                f"[WARNING] [CORRELATION_ENGINE] Inverse relationship weakened (r={corr:.2f}, regime={regime.value}). "
                f"USDJPY directional coordination temporarily suspended."
            )

        return corr

    def update_xauusd_signal(self, candidate: SignalCandidate) -> None:
        """
        Called when XAUUSD establishes a validated trading signal or bias:
        - XAUUSD BUY  -> sets XAUUSD bias to BULLISH and USDJPY preferred direction to SELL
        - XAUUSD SELL -> sets XAUUSD bias to BEARISH and USDJPY preferred direction to BUY
        """
        now = getattr(candidate, "timestamp", None) or datetime.now(timezone.utc)
        if candidate.direction in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP):
            self.state.xauusd_bias = "BULLISH"
            self.state.xauusd_last_signal_direction = OrderType.BUY
            self.state.usdjpy_preferred_direction = OrderType.SELL
            logger.info("[INFO] [DIRECTIONAL_ENGINE] XAUUSD BUY bias detected. USDJPY preferred direction set to SELL.")
        elif candidate.direction in (OrderType.SELL, OrderType.SELL_LIMIT, OrderType.SELL_STOP):
            self.state.xauusd_bias = "BEARISH"
            self.state.xauusd_last_signal_direction = OrderType.SELL
            self.state.usdjpy_preferred_direction = OrderType.BUY
            logger.info("[INFO] [DIRECTIONAL_ENGINE] XAUUSD SELL bias detected. USDJPY preferred direction set to BUY.")

        self.state.xauusd_last_signal_time = now
        self.state.last_updated = datetime.now(timezone.utc)

    def evaluate_usdjpy_candidate(
        self,
        candidate: Optional[SignalCandidate],
        current_time: Optional[datetime] = None
    ) -> CoordinationEvaluationResult:
        """
        Evaluates a USDJPY setup against the current inverse coordination state.
        Under the two-instrument universe directive, USDJPY is universally excluded
        from new automated entries.
        """
        logger.warning("INSTRUMENT_BLOCKED: USDJPY | REASON: NOT_IN_ALLOWED_TRADING_UNIVERSE")
        return CoordinationEvaluationResult(
            is_approved=False,
            rationale="INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted.",
            score_adjustment=0.0,
            regime=self.state.correlation_regime,
            correlation=self.state.correlation_value,
        )

    def record_active_position(self, symbol: str, ticket: int) -> None:
        canon = "XAUUSD" if "XAU" in symbol.upper() or "GOLD" in symbol.upper() else ("USDJPY" if "JPY" in symbol.upper() else "OTHER")
        if canon in self.state.active_coordinated_positions:
            if ticket not in self.state.active_coordinated_positions[canon]:
                self.state.active_coordinated_positions[canon].append(ticket)

    def remove_position(self, ticket: int) -> None:
        for canon, tickets in self.state.active_coordinated_positions.items():
            if ticket in tickets:
                tickets.remove(ticket)


# Global singleton coordinator
_INVERSE_COORDINATOR = InverseDirectionCoordinator()


def get_inverse_coordinator() -> InverseDirectionCoordinator:
    global _INVERSE_COORDINATOR
    return _INVERSE_COORDINATOR
