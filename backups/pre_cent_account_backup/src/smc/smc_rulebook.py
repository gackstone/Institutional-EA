"""
Canonical SMC Rulebook (Single Source of Truth).

Encodes the 9-rule SMC hypothesis framework (R1-R9) and configurable default
parameters used across structure detectors, POI (OB/FVG) detectors, liquidity
sweep validators, setup quality gates, and risk-rule enforcement.

Epistemic note: Every rule and parameter below is a testable price-action
hypothesis with a default value, evaluated empirically out-of-sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Any


class GateMode(str, Enum):
    """Execution mode for the Setup Quality Gate and individual hard gates."""
    OFF = "OFF"
    SHADOW = "SHADOW"
    ENFORCE = "ENFORCE"


@dataclass(frozen=True)
class SmcRuleDefinition:
    """Metadata describing a canonical rule in the SMC Rulebook."""
    rule_id: str
    title: str
    hypothesis: str
    default_parameters: Dict[str, Any]


# ---------------------------------------------------------------------------
# Canonical Rule Definitions (R1 - R9)
# ---------------------------------------------------------------------------

SMC_RULE_DEFINITIONS: Dict[str, SmcRuleDefinition] = {
    "R1": SmcRuleDefinition(
        rule_id="R1",
        title="Market Structure",
        hypothesis=(
            "Uptrend = higher highs (HH) + higher lows (HL); downtrend = lower highs (LH) + lower lows (LL). "
            "Ranges or unclear structure = NO TRADE ('no clear trend, wait'). "
            "Read primary directional structure on HTF (H4/D1); M1-type small timeframes are noise and may not define trend."
        ),
        default_parameters={
            "htf_structure_timeframes": ["H4", "D1"],
            "require_both_hh_hl_for_trend": True,
            "ranging_structure_no_trade": True,
        },
    ),
    "R2": SmcRuleDefinition(
        rule_id="R2",
        title="Break of Structure (BOS)",
        hypothesis=(
            "A candle BODY CLOSE beyond the last swing point (above last swing high in an uptrend, "
            "below last swing low in a downtrend) confirms the trend remains active. "
            "A wick through the level is NOT a BOS (it is a potential sweep). "
            "Do not chase the breakout candle; wait for a pullback."
        ),
        default_parameters={
            "bos_body_close_required": True,
            "reject_breakout_candle_chase": True,
        },
    ),
    "R3": SmcRuleDefinition(
        rule_id="R3",
        title="Change of Character (CHoCH)",
        hypothesis=(
            "The FIRST candle body close against the prevailing trend (e.g., in a downtrend, a close above "
            "the last lower high). One CHoCH is an early warning, NOT a confirmed reversal. "
            "Wait for confirmation (a pullback that holds, followed by a BOS in the new direction)."
        ),
        default_parameters={
            "choch_requires_confirmation": True,
            "allow_choch_only_entries": False,
        },
    ),
    "R4": SmcRuleDefinition(
        rule_id="R4",
        title="Liquidity & Sweeps",
        hypothesis=(
            "Resting stops cluster at equal highs/equal lows (EQH/EQL), beyond obvious swing points, "
            "trendlines, and session/daily highs and lows. A liquidity sweep occurs when price pierces the "
            "level and quickly CLOSES BACK INSIDE the range. Take-profit targets are anchored at the next liquidity pool."
        ),
        default_parameters={
            "sweep_requires_close_back_inside": True,
            "tp_requires_liquidity_pool": True,
        },
    ),
    "R5": SmcRuleDefinition(
        rule_id="R5",
        title="Order Block (OB)",
        hypothesis=(
            "The last opposite-colored candle before a strong displacement impulse that BREAKS structure (BOS/MSS). "
            "Not every opposite candle is an OB: require displacement (body >= 1.2 * ATR or leaving an FVG) "
            "and a structural break."
        ),
        default_parameters={
            "ob_requires_displacement": True,
            "ob_displacement_atr_mult": 1.2,
            "ob_requires_bos": True,
        },
    ),
    "R6": SmcRuleDefinition(
        rule_id="R6",
        title="Fair Value Gap (FVG)",
        hypothesis=(
            "Three-candle imbalance where candle 1's high and candle 3's low do not overlap (bullish; mirror for bearish). "
            "Only meaningful gaps count: impulsive middle candle in the trend direction, gap size >= fvg_min_atr * ATR, "
            "with a confluence bonus when overlapping or adjacent to a valid Order Block."
        ),
        default_parameters={
            "fvg_min_atr": 0.3,
            "fvg_requires_impulse": True,
            "ob_fvg_confluence_bonus_pts": 10.0,
        },
    ),
    "R7": SmcRuleDefinition(
        rule_id="R7",
        title="Premium / Discount Equilibrium",
        hypothesis=(
            "Across the active swing range (swing low to swing high), 50% (0.50) is equilibrium. "
            "Above 50% = premium (expensive); below 50% = discount (cheap). "
            "In an uptrend look for buys in discount (< 0.50); in a downtrend look for sells in premium (> 0.50)."
        ),
        default_parameters={
            "pd_equilibrium": 0.5,
        },
    ),
    "R8": SmcRuleDefinition(
        rule_id="R8",
        title="Complete 6-Step Entry Model",
        hypothesis=(
            "1. HTF (H4/D1) clear trend + BOS in trade direction. "
            "2. Pullback into discount (longs) / premium (shorts) beyond 50% equilibrium. "
            "3. Liquidity sweep with close-back-inside in that zone. "
            "4. Mark valid OB / FVG point of interest (POI) inside the zone. "
            "5. On LTF (e.g. M15) wait for CHoCH + confirming BOS inside the zone. "
            "6. Enter on pullback into the LTF OB/FVG; SL beyond sweep extreme; TP at next liquidity pool with RR >= min_rr."
        ),
        default_parameters={
            "min_rr": 2.0,
            "require_poi_touch_on_pullback": True,
        },
    ),
    "R9": SmcRuleDefinition(
        rule_id="R9",
        title="Risk & Trade Hygiene",
        hypothesis=(
            "Risk 1-2% per trade (default 1.0%, hard code cap 2.0%). Always use a stop loss. "
            "NEVER move a stop loss further away from price (never widen risk). "
            "Log 'no-trade' decisions explicitly with structured reason codes ('No setup is also a decision')."
        ),
        default_parameters={
            "default_risk_pct": 1.0,
            "max_risk_pct": 2.0,
            "require_stop_loss": True,
            "forbid_sl_widening": True,
        },
    ),
}


@dataclass
class SmcRulebookConfig:
    """
    Canonical runtime configuration for SMC Rulebook detectors, Setup Quality Gate (G1-G8),
    and Risk-Rule Enforcement (R9). All thresholds live here and can be loaded from
    config/strategy_config.json without magic numbers in detector code.
    """
    # R1: Market Structure
    require_both_hh_hl_for_trend: bool = True
    ranging_structure_no_trade: bool = True
    htf_timeframes: List[str] = field(default_factory=lambda: ["H4", "D1"])

    # R2: Break of Structure
    bos_body_close_required: bool = True
    reject_breakout_candle_chase: bool = True

    # R3: Change of Character
    choch_requires_confirmation: bool = True
    allow_choch_only_entries: bool = False

    # R4: Liquidity Sweep
    sweep_requires_close_back_inside: bool = True
    tp_requires_liquidity_pool: bool = True

    # R5: Order Block
    ob_requires_displacement: bool = True
    ob_displacement_atr_mult: float = 1.2
    ob_requires_bos: bool = True

    # R6: Fair Value Gap
    fvg_min_atr: float = 0.3
    fvg_requires_impulse: bool = True
    fvg_impulse_body_atr_mult: float = 0.7
    ob_fvg_confluence_bonus_pts: float = 10.0

    # R7: Premium / Discount
    pd_equilibrium: float = 0.5

    # R8: Entry Model & Targets
    min_rr: float = 2.0
    require_poi_touch_on_pullback: bool = True

    # R9: Risk Rules
    default_risk_pct: float = 1.0
    max_risk_pct: float = 2.0
    require_stop_loss: bool = True
    forbid_sl_widening: bool = True

    # Phase 2 Setup Quality Gate Modes & Per-Gate Toggles
    # Default mode is SHADOW per Phase 2 specification; Phase 4 ablation promotes proven gates to ENFORCE.
    gate_mode: GateMode = GateMode.SHADOW
    g1_structure_enabled: bool = True
    g2_zone_enabled: bool = True
    g3_sweep_enabled: bool = True
    g4_poi_quality_enabled: bool = True
    g5_ltf_confirm_enabled: bool = True
    g6_htf_alignment_enabled: bool = True
    g7_stops_targets_enabled: bool = True
    g8_risk_enabled: bool = True

    def __post_init__(self) -> None:
        # Enforce R9 hard cap of 2.0% regardless of external configuration input
        if self.max_risk_pct > 2.0:
            self.max_risk_pct = 2.0
        if self.default_risk_pct > self.max_risk_pct:
            self.default_risk_pct = self.max_risk_pct
        if isinstance(self.gate_mode, str):
            self.gate_mode = GateMode(self.gate_mode.upper())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SmcRulebookConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "gate_mode" in filtered and isinstance(filtered["gate_mode"], str):
            filtered["gate_mode"] = GateMode(filtered["gate_mode"].upper())
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["gate_mode"] = self.gate_mode.value
        return d


# Canonical No-Trade / Gate Rejection Reason Codes (R9.4)
class NoTradeReason:
    UNCLEAR_STRUCTURE = "G1_UNCLEAR_OR_RANGING_STRUCTURE"
    NO_HTF_BOS = "G1_NO_HTF_BOS_IN_TREND_DIRECTION"
    WRONG_PD_ZONE = "G2_WRONG_PREMIUM_DISCOUNT_ZONE"
    NO_SWEEP = "G3_NO_LIQUIDITY_SWEEP_WITH_CLOSE_BACK_INSIDE"
    WEAK_OR_MISSING_POI = "G4_MISSING_DISPLACEMENT_OB_OR_MIN_ATR_FVG"
    NO_LTF_CONFIRMATION = "G5_NO_CONFIRMED_LTF_CHOCH_BOS_OR_BREAKOUT_CHASE"
    HTF_COUNTERTREND = "G6_AGAINST_HTF_TREND_ALIGNMENT"
    INVALID_SL_EXTREME = "G7_SL_NOT_BEYOND_SWEEP_OR_POI_EXTREME"
    NO_LIQUIDITY_TP = "G7_TP_NOT_AT_STRUCTURAL_LIQUIDITY_POOL"
    RR_TOO_LOW = "G7_RR_BELOW_MIN_RR"
    MISSING_STOP_LOSS = "G8_MISSING_STOP_LOSS"
    RISK_ABOVE_CAP = "G8_RISK_PCT_EXCEEDS_2PCT_HARD_CAP"
    SL_WIDENING_REJECTED = "R9_SL_WIDENING_MODIFICATION_REJECTED"
    NO_POI = WEAK_OR_MISSING_POI
    LOW_SCORE = "NO_TRADE_LOW_CONFLUENCE_SCORE"
    SL_NOT_BEYOND_SWEEP = INVALID_SL_EXTREME
    RISK_EXCEEDED = RISK_ABOVE_CAP
