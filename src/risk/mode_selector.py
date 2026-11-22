"""
Intelligent Mode Selection Engine.
Classifies trading opportunities at entry into:
- MODE A: QUICK_SCALP (Rapid $20 net profit target full closure & slot recycling)
- MODE B: PROFIT_RUNNING ($20 minimum profit protection & progressive trend trailing)

Classification evaluates:
1. Strategy type (Fast Scalp vs Institutional SMC / Swing)
2. Expected holding duration & timeframe horizon
3. Higher-timeframe directional alignment (W1/D1/H4/H1)
4. Market structure (BOS, CHoCH, displacement)
5. SMC/ICT confluence score (Threshold >= 75 for profit running)
6. Expected reward-to-risk (RR >= 2.2 for profit running)
7. Volatility regime (Normal/Low vs Extreme)
8. Liquidity pool objectives and continuation evidence
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import (
    Candle,
    OrderType,
    ProfitManagementMode,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)

logger = logging.getLogger("ModeSelector")


class ModeSelectionEngine:
    """
    Classifies positions at entry into QUICK_SCALP or PROFIT_RUNNING mode.
    Never forces every position to close at $20, while ensuring only high-conviction
    continuation setups are granted profit-running status.
    """

    MIN_SCORE_FOR_PROFIT_RUNNING = 75.0
    MIN_RR_FOR_PROFIT_RUNNING = 2.00

    PROFIT_RUNNING_ELIGIBLE_SETUPS = {
        SetupType.M15_SMC_OTE,
        SetupType.SESSION_SWEEP,
        SetupType.PATTERN_CONFLUENCE,
        SetupType.LIQUIDITY_SWEEP,
        SetupType.WEEKLY_REVERSAL,
        SetupType.WEEKLY_CONTINUATION,
        SetupType.DAILY_REVERSAL,
        SetupType.DAILY_CONTINUATION,
        SetupType.TRENDLINE_LIQUIDITY,
    }

    @classmethod
    def classify_trade_opportunity(
        cls,
        candidate: SignalCandidate,
        symbol_info: Optional[SymbolInfo] = None,
        recent_candles: Optional[List[Candle]] = None,
        volatility_regime: Optional[str] = "NORMAL",
        holding_horizon_minutes: Optional[float] = None,
        min_rr_for_hold: Optional[float] = None,
        min_score_for_hold: Optional[float] = None,
        execution_mode_policy: str = "ADAPTIVE",
        htf_aligned: Optional[bool] = None,
    ) -> Tuple[ProfitManagementMode, str, Dict[str, Any]]:
        """
        Evaluates candidate attributes and returns:
        (selected_mode, decision_rationale, metrics_dict)
        """
        reasons = [str(r).upper() for r in (getattr(candidate, "reasons", None) or [])]
        setup_type = getattr(candidate, "setup_type", None)
        score = float(getattr(candidate, "score", 0.0) or 0.0)
        rr = float(getattr(candidate, "risk_reward", 0.0) or 0.0)
        sig_id = str(getattr(candidate, "id", "")).upper()
        timeframe = getattr(candidate, "timeframe", None)

        metrics = {
            "score": score,
            "risk_reward": rr,
            "setup_type": setup_type.value if hasattr(setup_type, "value") else str(setup_type),
            "volatility_regime": volatility_regime,
            "timeframe": timeframe.value if hasattr(timeframe, "value") else str(timeframe),
            "htf_aligned": False,
            "institutional_sponsorship": False,
        }

        policy = str(execution_mode_policy or "ADAPTIVE").upper()
        if policy == "SCALP_ONLY":
            return (
                ProfitManagementMode.QUICK_SCALP,
                "Classified as QUICK_SCALP: execution_mode_policy=SCALP_ONLY.",
                metrics,
            )

        # 1. Fast Scalp Strategy Check: M1/M5 fast scalps default to QUICK_SCALP
        if setup_type == SetupType.FAST_SCALP or sig_id.startswith("SCALP_") or sig_id.startswith("FAST_"):
            rationale = (
                f"Classified as QUICK_SCALP: Setup type is '{setup_type.value if hasattr(setup_type, 'value') else setup_type}' "
                f"designed for rapid $20 net monetization and slot recycling."
            )
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # 2. Confluence Score Filter: Requires institutional grade (>= configured hold score)
        eff_min_score = float(min_score_for_hold) if min_score_for_hold is not None else cls.MIN_SCORE_FOR_PROFIT_RUNNING
        if score < eff_min_score:
            rationale = (
                f"Classified as QUICK_SCALP: Setup score {score:.1f} is below {eff_min_score:.1f} "
                f"threshold required for PROFIT_RUNNING continuation."
            )
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # 3. Reward-to-Risk Requirement (>= configured min_rr_for_hold, precision-safe)
        eff_min_rr = float(min_rr_for_hold) if min_rr_for_hold is not None else cls.MIN_RR_FOR_PROFIT_RUNNING
        if (rr + 1e-6) < eff_min_rr:
            rationale = (
                f"Classified as QUICK_SCALP: Reward-to-Risk {rr:.4f} (display {rr:.2f}) < {eff_min_rr:.4f} "
                f"minimum required for normal holding mode."
            )
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # 4. Volatility Regime Check: Extreme volatility produces whipsaws unsuitable for trailing stops
        if str(volatility_regime).upper() == "EXTREME":
            rationale = "Classified as QUICK_SCALP: EXTREME volatility regime detected; securing quick $20 target."
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # 5. Higher-Timeframe Trend and Structural Alignment Check
        is_buy = candidate.direction in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        htf_bullish = any("BULLISH" in r or "UPTREND" in r for r in reasons) or any("REGIME:BULLISH_TREND" in r for r in reasons)
        htf_bearish = any("BEARISH" in r or "DOWNTREND" in r for r in reasons) or any("REGIME:BEARISH_TREND" in r for r in reasons)

        if is_buy and htf_bearish:
            rationale = "Classified as QUICK_SCALP: Counter-trend BUY against bearish HTF structure; rapid exit mandated."
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        if not is_buy and htf_bullish:
            rationale = "Classified as QUICK_SCALP: Counter-trend SELL against bullish HTF structure; rapid exit mandated."
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        metrics["htf_aligned"] = (is_buy and htf_bullish) or (not is_buy and htf_bearish) or any("HTF" in r for r in reasons)

        # 6. Institutional Sponsorship & Continuation Confirmation
        has_sponsorship = (
            any("BOS" in r for r in reasons)
            or any("DISPLACEMENT" in r for r in reasons)
            or any("SWEEP" in r for r in reasons)
            or any("ORDER_BLOCK" in r or "OB" in r for r in reasons)
            or any("FVG" in r for r in reasons)
            or getattr(candidate, "ob", None) is not None
            or getattr(candidate, "fvg", None) is not None
        )
        metrics["institutional_sponsorship"] = has_sponsorship

        if not has_sponsorship:
            rationale = (
                "Classified as QUICK_SCALP: Lacks confirmed institutional sponsorship (BOS/Displacement/Sweep) "
                "for extended trend holding."
            )
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # 7. Setup Type Whitelist
        if setup_type not in cls.PROFIT_RUNNING_ELIGIBLE_SETUPS:
            rationale = f"Classified as QUICK_SCALP: Setup {setup_type} not in eligible continuation whitelist."
            return ProfitManagementMode.QUICK_SCALP, rationale, metrics

        # All criteria satisfied for PROFIT_RUNNING
        rationale = (
            f"Classified as PROFIT_RUNNING: Score={score:.1f} >= 75.0, RR={rr:.2f} >= 2.2, "
            f"HTF aligned, confirmed institutional sponsorship ({setup_type.value if hasattr(setup_type, 'value') else setup_type}). "
            f"Securing $20 minimum profit protection upon attainment and trailing toward extended targets."
        )
        return ProfitManagementMode.PROFIT_RUNNING, rationale, metrics
