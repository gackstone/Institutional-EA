"""
AlgoVistra Quantitative Engine Types and Pure Function Contracts.
Defines SkillResult, Context, and unified DataFrame/Candle adapters.
Every rule and output is tagged [VIDEO n], [DERIVED], or [ASSUMPTION].
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

from src.core.contracts import Candle, OrderType, Timeframe


@dataclass
class SkillResult:
    """
    Standard return contract for all AlgoVistra skills:
    evaluate(df: DataFrame, ctx: Context) -> SkillResult(status, level_prices, reasons, confidence)
    """
    status: str  # "PASS", "FAIL", "TRIGGERED", "HOLD", "PENDING", "TRAP", "DECAYING", "NO_TRADE"
    level_prices: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    confidence: float = 1.0
    tag: str = "[VIDEO]"  # [VIDEO n], [DERIVED], [ASSUMPTION]
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    passed: Optional[bool] = None

    def __post_init__(self):
        if self.passed is None:
            self.passed = self.status in (
                "PASS", "TRIGGERED", "BREAKOUT_CONFIRMED", "HELD",
                "CONFIRMED", "ACTIVE", "QUALIFIED_OB", "SWEEP_CONFIRMED",
                "ACTIVE_GAP", "ANALYZED", "BULL", "BEAR"
            )
        if not self.tags and self.tag:
            self.tags = [self.tag]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
            "level_prices": dict(self.level_prices),
            "reasons": list(self.reasons),
            "confidence": round(self.confidence, 3),
            "tag": self.tag,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class Context:
    """
    Shared evaluation context across pipeline gates.
    """
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    current_price: float = 0.0
    atr: float = 0.0010
    pip_size: float = 0.0001
    trend: str = "RANGE/TRANSITION"  # "BULL", "BEAR", "RANGE/TRANSITION" [VIDEO 4]
    protected_low: Optional[float] = None  # [VIDEO 3]
    protected_high: Optional[float] = None # [VIDEO 3]
    protected_swing_low: Optional[float] = None
    protected_swing_high: Optional[float] = None
    bos_level: Optional[float] = None
    bos_time: Optional[datetime] = None
    active_leg: Optional[Tuple[float, float]] = None # (protected_low, high) or (protected_high, low) [VIDEO 2]
    equilibrium: Optional[float] = None # 50% equilibrium level [VIDEO 2]
    liquidity_pools: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.protected_swing_low is None and self.protected_low is not None:
            self.protected_swing_low = self.protected_low
        elif self.protected_low is None and self.protected_swing_low is not None:
            self.protected_low = self.protected_swing_low

        if self.protected_swing_high is None and self.protected_high is not None:
            self.protected_swing_high = self.protected_high
        elif self.protected_high is None and self.protected_swing_high is not None:
            self.protected_high = self.protected_swing_high


def normalize_to_candles(data: Any) -> List[Candle]:
    """
    Converts pandas.DataFrame, List[Candle], or List[dict] into List[Candle].
    [GROUND RULE 4]: Ensures all candles returned are completed/closed bars only.
    """
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], Candle):
            # Already Candle objects: filter complete closed candles
            return [c for c in data if getattr(c, "complete", True)]
        elif isinstance(data[0], dict):
            candles = []
            for d in data:
                t = d.get("time")
                if isinstance(t, str):
                    dt = datetime.fromisoformat(t)
                elif isinstance(t, (int, float)):
                    dt = datetime.fromtimestamp(t, tz=timezone.utc)
                elif isinstance(t, datetime):
                    dt = t
                else:
                    dt = datetime.now(timezone.utc)
                candles.append(
                    Candle(
                        time=dt,
                        open=float(d.get("open", 0.0)),
                        high=float(d.get("high", 0.0)),
                        low=float(d.get("low", 0.0)),
                        close=float(d.get("close", 0.0)),
                        tick_volume=int(d.get("tick_volume", 0)),
                        spread=int(d.get("spread", 0)),
                        complete=bool(d.get("complete", True)),
                    )
                )
            return [c for c in candles if c.complete]

    # Handle pandas DataFrame
    if HAS_PANDAS and isinstance(data, pd.DataFrame):
        candles = []
        for idx, row in data.iterrows():
            t = row.get("time", idx)
            if isinstance(t, str):
                dt = datetime.fromisoformat(t)
            elif isinstance(t, (int, float)):
                dt = datetime.fromtimestamp(t, tz=timezone.utc)
            elif isinstance(t, datetime):
                dt = t
            elif hasattr(t, "to_pydatetime"):
                dt = t.to_pydatetime()
            else:
                dt = datetime.now(timezone.utc)

            is_complete = bool(row.get("complete", True))
            candles.append(
                Candle(
                    time=dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    tick_volume=int(row.get("tick_volume", 0)),
                    spread=int(row.get("spread", 0)),
                    complete=is_complete,
                )
            )
        return [c for c in candles if c.complete]

    return []
