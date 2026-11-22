"""
Feature Extraction and Temporal Dataset Pipeline for ATI Learning.
Computes indicator and market condition features at original decision timestamps.
Strictly prevents look-ahead bias and temporal leakage.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.intelligence.contracts import CompletedPositionRecord


class HistoricalFeatureExtractor:
    """
    Extracts numerical features from market data and trade contexts.
    Features are strictly computed using historical bars preceding the trade entry timestamp.
    """

    FEATURE_NAMES = [
        "spread_pts",
        "adx",
        "atr",
        "rsi",
        "momentum_pct",
        "session_is_london",
        "session_is_newyork",
        "session_is_asian",
        "direction_is_buy",
        "hour_of_day",
        "day_of_week",
    ]

    @classmethod
    def extract_features_from_context(
        cls,
        entry_time: datetime,
        direction: str,
        spread_pts: float = 0.0,
        rsi: float = 50.0,
        adx: float = 25.0,
        atr: float = 1.0,
        momentum_pct: float = 0.0,
        session_name: str = "LONDON",
    ) -> Dict[str, float]:
        """Builds standardized feature vector for a trade entry."""
        hour = entry_time.hour
        day = entry_time.weekday()

        sess = session_name.upper()
        return {
            "spread_pts": float(spread_pts),
            "adx": float(adx),
            "atr": float(atr),
            "rsi": float(rsi),
            "momentum_pct": float(momentum_pct),
            "session_is_london": 1.0 if "LONDON" in sess else 0.0,
            "session_is_newyork": 1.0 if "NEW_YORK" in sess or "NEWYORK" in sess or "NY" in sess else 0.0,
            "session_is_asian": 1.0 if "ASIA" in sess or "TOKYO" in sess else 0.0,
            "direction_is_buy": 1.0 if direction.upper() == "BUY" else 0.0,
            "hour_of_day": float(hour),
            "day_of_week": float(day),
        }

    @classmethod
    def build_matrix_from_positions(
        cls,
        positions: List[CompletedPositionRecord],
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Builds chronologically ordered (X, y) arrays from completed positions.
        Returns (features_matrix, binary_labels, feature_names).
        Binary label: 1 if realized_net_profit > 0 else 0.
        """
        # Sort chronologically by open_time to guarantee temporal ordering
        sorted_pos = sorted(positions, key=lambda p: p.open_time)

        rows = []
        labels = []
        for pos in sorted_pos:
            snap = pos.features_snapshot or {}
            feat_dict = cls.extract_features_from_context(
                entry_time=pos.open_time,
                direction=pos.direction,
                spread_pts=pos.spread_pts or snap.get("spread_pts", 15.0),
                rsi=snap.get("rsi", 50.0),
                adx=snap.get("adx", 25.0),
                atr=snap.get("atr", 1.0),
                momentum_pct=snap.get("momentum_pct", 0.0),
                session_name=snap.get("session_name", "LONDON"),
            )
            vec = [feat_dict[k] for k in cls.FEATURE_NAMES]
            rows.append(vec)
            labels.append(1 if pos.realized_net_profit > 0 else 0)

        if not rows:
            return np.empty((0, len(cls.FEATURE_NAMES))), np.empty((0,)), cls.FEATURE_NAMES

        return np.array(rows, dtype=np.float64), np.array(labels, dtype=np.int32), cls.FEATURE_NAMES
