'''Speed engine – impulse vs pull‑back velocity analysis and market‑state classification.

The engine consumes the list of ``Leg`` objects produced by ``leg_engine`` and
identifies impulse‑leg / pull‑back‑leg pairs.  It computes the velocity‑ratio
(VR = pullback_velocity / impulse_velocity) and, together with overlap and
efficiency metrics, classifies the market state for a given symbol/timeframe.
All thresholds are configurable via ``config/speed_config.json``.
'''\n\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom enum import Enum\nfrom typing import List, Tuple, Dict\n\nfrom src.smc.leg_engine import Leg
import numpy as np
from src.core.contracts import OrderType\n\n\nclass MarketSpeedState(str, Enum):\n    UPTREND_HEALTHY = "UPTREND_HEALTHY"\n    UPTREND_WEAKENING = "UPTREND_WEAKENING"\n    DOWNTREND_HEALTHY = "DOWNTREND_HEALTHY"\n    DOWNTREND_WEAKENING = "DOWNTREND_WEAKENING"\n    TRANSITION = "TRANSITION"\n    RANGE_CHOP = "RANGE_CHOP"\n\n\n@dataclass(frozen=True)\nclass SpeedPair:\n    impulse: Leg\n    pullback: Leg\n    vr: float  # pullback velocity / impulse velocity\n    overlap_compare: Tuple[float, float]  # (impulse_overlap, pullback_overlap)\n    efficiency_compare: Tuple[float, float]  # (impulse_er, pullback_er)\n\n\n@dataclass(frozen=True)\nclass SpeedStateResult:\n    state: MarketSpeedState\n    fast_side: int  # -1 for down, +1 for up, 0 for none\n    confidence: float  # 0‑1 confidence based on metric distance from thresholds\n    bias: float  # fast‑side bias in [-1, +1] (same as fast_side but smoothed)\n    recent_pair: SpeedPair | None\n    htf_agreement: Dict[str, bool]  # e.g. {"M1": True, "M5": False}\n\n\nclass SpeedEngine:\n    def __init__(self, config: dict):\n        self.cfg = config\n        # thresholds – defaults are marked as UNCALIBRATED in the config file\n        self.vr_healthy = self.cfg.get("vr_healthy", 0.5)\n        self.vr_warning = self.cfg.get("vr_warning", 0.8)\n        self.vr_flip = self.cfg.get("vr_flip", 1.0)\n        self.min_overlap = self.cfg.get("min_overlap", 0.2)\n        self.min_efficiency = self.cfg.get("min_efficiency", 0.3)\n        self.dwell_bars = self.cfg.get("dwell_bars", 5)\n        self.state_history: List[Tuple[int, MarketSpeedState]] = []  # (bar_index, state)\n\n    def _pair_legs(self, legs: List[Leg]) -> List[SpeedPair]:\n        """Match each impulse leg with the following pull‑back leg.
\n        An impulse leg is defined as having velocity > ``vr_healthy`` * median
        velocity of all legs and low overlap.  The next leg is treated as the
        pull‑back.  If the next leg does not exist the pair is discarded.
        """\n        pairs: List[SpeedPair] = []\n        if not legs:
            return pairs\n        median_vel = float(np.median([l.velocity_atr for l in legs]))
        for i in range(len(legs) - 1):
            imp = legs[i]
            # Heuristic for impulse: high velocity, low overlap, good efficiency
            if (imp.velocity_atr > median_vel and imp.overlap_ratio < self.min_overlap and imp.kaufman_er > self.min_efficiency):\n                pull = legs[i + 1]\n                # Avoid division by zero – if impulse velocity is zero, skip
                if imp.velocity_atr == 0:
                    continue\n                vr = pull.velocity_atr / imp.velocity_atr
                pair = SpeedPair(
                    impulse=imp,
                    pullback=pull,
                    vr=vr,
                    overlap_compare=(imp.overlap_ratio, pull.overlap_ratio),
                    efficiency_compare=(imp.kaufman_er, pull.kaufman_er),
                )
                pairs.append(pair)\n        return pairs\n\n    def _classify_state(self, recent_pair: SpeedPair | None, bar_index: int) -> SpeedStateResult:\n        """Determine the market speed state from the most recent pair.
\n        Hysteresis is applied via ``self.dwell_bars`` – a state persists for at
        least that many bars unless a clear flip condition is met.
        """\n        if recent_pair is None:
            # No impulse‑pullback pattern – fallback to RANGE_CHOP
            return SpeedStateResult(
                state=MarketSpeedState.RANGE_CHOP,
                fast_side=0,
                confidence=0.0,
                bias=0.0,
                recent_pair=None,
                htf_agreement={},
            )
        vr = recent_pair.vr
        # Determine fast side based on impulse direction
        fast_side = 1 if recent_pair.impulse.direction == OrderType.BUY else -1
        # Confidence scaling – linear interpolation between thresholds
        if vr <= self.vr_healthy:
            confidence = 1.0 - (vr / self.vr_healthy) * 0.5  # high confidence healthy
        elif vr >= self.vr_warning:
            confidence = 0.5 - ((vr - self.vr_warning) / (self.vr_flip - self.vr_warning)) * 0.5
        else:
            confidence = 0.5  # middle ground
        # State decision
        if vr <= self.vr_healthy:
            state = MarketSpeedState.UPTREND_HEALTHY if fast_side > 0 else MarketSpeedState.DOWNTREND_HEALTHY
        elif vr >= self.vr_warning and vr < self.vr_flip:
            state = MarketSpeedState.UPTREND_WEAKENING if fast_side > 0 else MarketSpeedState.DOWNTREND_WEAKENING
        elif vr >= self.vr_flip:
            state = MarketSpeedState.TRANSITION
        else:
            state = MarketSpeedState.RANGE_CHOP
        # Apply dwell‑time hysteresis – keep previous state if not enough bars have passed
        if self.state_history:
            last_bar, last_state = self.state_history[-1]
            if bar_index - last_bar < self.dwell_bars and last_state != MarketSpeedState.TRANSITION:
                state = last_state
        # Record history
        self.state_history.append((bar_index, state))
        # Bias is fast_side scaled by confidence
        bias = fast_side * confidence
        # Placeholder for HTF agreement – empty for now (filled by caller)
        return SpeedStateResult(
            state=state,
            fast_side=fast_side,
            confidence=confidence,
            bias=bias,
            recent_pair=recent_pair,
            htf_agreement={},
        )\n\n    def evaluate(self, legs: List[Leg], current_bar_index: int) -> SpeedStateResult:\n        """Public entry point – returns the market speed state for the latest bar.
\n        ``current_bar_index`` is the index of the most recent closed candle in the
        full candle list (used for hysteresis).  The function pairs the legs, picks
        the most recent valid pair, and classifies the state.
        """\n        pairs = self._pair_legs(legs)
        recent_pair = pairs[-1] if pairs else None
        return self._classify_state(recent_pair, current_bar_index)\n\n# Helper to load config JSON – placed here to avoid circular imports\ndef load_speed_config(path: str = "config/speed_config.json") -> dict:\n    import json, os\n    if os.path.exists(path):\n        with open(path, "r", encoding="utf-8") as f:\n            return json.load(f)
    return {}\n