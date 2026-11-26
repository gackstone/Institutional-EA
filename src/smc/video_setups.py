"""
Named Video-Derived Forex Setups (S1-S10) + Monotonic Confluence Scoring + Config Validator.

Implements:
  S1: Raid -> Shift -> FVG -> CE ("free ICT model", 4 steps)      [keepssy_fx 0007, 0008]
  S2: Silver Bullet (3 NY windows, first FVG after sweep, P10)    [keepssy_fx 0001, 0009]
  S3: NY Macro (09:50-10:10 & 10:50-11:10 NY, window expiry)      [keepssy_fx 0010]
  S4: London Judas Swing / Fake Breakout of Asian Range           [keepssy_fx 0011]
  S5: Asian-Range SD Projection Reversal (-2/-2.5 & +2/+2.5 SD)   [keepssy_fx 0013]
  S6: IFVG Reversal After Stop Hunt (5M FVG inverted -> retest)   [keepssy_fx 0005]
  S7: Stacked Breaker + IFVG Overlap                              [keepssy_fx 0004]
  S8: OTE Entry After Stop Hunt + BOS (0.705 / FVG in 0.62-0.79)  [keepssy_fx 0002, 0003, algovistra 0001]
  S9: Hidden Demand/Supply (HTF wick-to-wick gap -> LTF OB limit) [nexusquant_ai 0001]
  S10: Session-Level Sweep Reversals (Asia->LDN, LDN->NY, PD->Mid)[scriptedge 0001]

Epistemic note:
- All numeric thresholds are engineering starting defaults for replay calibration, not
  validated profitability claims.
- Gates (P2, P10, P11) apply strictly to each named setup's own detection; existing
  unfiltered execution pathways are untouched.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.contracts import (
    Candle,
    FairValueGap,
    LiquidityZone,
    OrderBlock,
    OrderType,
    SetupType,
    SignalCandidate,
    Timeframe,
)
from src.core.sessions import TradingSessionEngine
from src.smc.session_liquidity import SessionKeyLevels, SessionLiquidityEngine
from src.smc.video_primitives import (
    ConfirmedSweep,
    DrawOnLiquidity,
    MssDisplacementResult,
    StopClusterPool,
    ThreePointTurnResult,
    compute_atr,
    compute_bos_anchored_ote,
    detect_confirmed_sweep,
    detect_equal_clusters,
    detect_flipped_breakers,
    detect_fvgs_with_ce,
    detect_ifvg_candidates,
    detect_mss_with_displacement,
    evaluate_smt_divergence_video,
    evaluate_three_point_turn,
    find_swings,
    get_draw_on_liquidity,
    validate_draw_on_liquidity,
)
from src.strategy.inverse_coordination import InverseDirectionCoordinator

logger = logging.getLogger("VideoSetupEngine")

SETUP_IDS = (
    "S1_RAID_SHIFT_FVG_CE",
    "S2_SILVER_BULLET",
    "S3_NY_MACRO",
    "S4_LONDON_JUDAS_SWING",
    "S5_ASIAN_SD_REVERSAL",
    "S6_IFVG_STOP_HUNT",
    "S7_STACKED_BREAKER_IFVG",
    "S8_OTE_STOP_HUNT_BOS",
    "S9_HIDDEN_DEMAND_SUPPLY",
    "S10_SESSION_SWEEP_REVERSAL",
)

DEFAULT_VIDEO_SETUPS_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "execution_mode_for_new_setups": "DEMO_EXECUTE",  # SHADOW | DEMO_EXECUTE
    "reference_symbols": ["USDJPY", "XAGUSD", "DXY", "ETHUSD", "EURUSD"],
    "smt_pairs": {
        "XAUUSD": {"symbol": "USDJPY", "inverse": True, "fallback_reference": "XAGUSD"},
        "BTCUSD": {"symbol": "ETHUSD", "inverse": False, "fallback_reference": None},
    },
    "default_min_rr_demo": 2.0,
    "default_min_rr_prop": 2.5,
    "fvg_min_atr": 0.15,
    "eqh_tolerance_atr": 0.10,
    "min_pierce_atr": 0.05,
    "max_bars_to_reclaim": 3,
    "stop_buffer_atr": 0.05,
    "setups": {
        sid: {
            "enabled": True,
            "min_rr": 2.0,
            "allow_b_grade": False,
            "partial_pct": 0.50,
            "cancel_on_window_end": sid in ("S2_SILVER_BULLET", "S3_NY_MACRO"),
            "ote_entry_level": 0.705,
        }
        for sid in SETUP_IDS
    },
}


class VideoConfigValidationError(ValueError):
    """Raised when video_setups configuration contains invalid values (fail-closed)."""


def validate_video_setups_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed validator for the `video_setups` block in config/strategy_config.json."""
    if not isinstance(cfg, dict):
        raise VideoConfigValidationError("video_setups config must be a dict")

    mode = str(cfg.get("execution_mode_for_new_setups", "DEMO_EXECUTE")).upper()
    if mode not in ("SHADOW", "DEMO_EXECUTE"):
        raise VideoConfigValidationError(
            f"execution_mode_for_new_setups must be SHADOW or DEMO_EXECUTE, got '{mode}'"
        )

    for key in ("default_min_rr_demo", "default_min_rr_prop", "fvg_min_atr", "eqh_tolerance_atr", "min_pierce_atr", "stop_buffer_atr"):
        if key in cfg:
            val = float(cfg[key])
            if val < 0.0 or val > 20.0:
                raise VideoConfigValidationError(f"{key} out of valid range [0, 20]: {val}")

    setups = cfg.get("setups") or {}
    if not isinstance(setups, dict):
        raise VideoConfigValidationError("video_setups.setups must be a dict")
    for sid, scfg in setups.items():
        if not isinstance(scfg, dict):
            raise VideoConfigValidationError(f"Setup config for {sid} must be a dict")
        min_rr = float(scfg.get("min_rr", 2.0))
        if min_rr < 0.5 or min_rr > 20.0:
            raise VideoConfigValidationError(f"{sid}.min_rr out of range [0.5, 20]: {min_rr}")
        partial_pct = float(scfg.get("partial_pct", 0.50))
        if partial_pct < 0.0 or partial_pct > 1.0:
            raise VideoConfigValidationError(f"{sid}.partial_pct out of range [0, 1]: {partial_pct}")
        ote_lvl = float(scfg.get("ote_entry_level", 0.705))
        if ote_lvl < 0.5 or ote_lvl > 0.95:
            raise VideoConfigValidationError(f"{sid}.ote_entry_level out of range [0.5, 0.95]: {ote_lvl}")

    return cfg


def compute_stop_with_buffer(
    direction: OrderType,
    extreme_price: float,
    spread_price: float,
    atr: float,
    stop_buffer_atr: float = 0.05,
) -> float:
    """Stop = beyond sweep/raid extreme + buffer max(2 * spread, 0.05 * ATR)."""
    buf = max(2.0 * max(0.0, spread_price), stop_buffer_atr * max(atr, 1e-9))
    if direction == OrderType.BUY:
        return round(extreme_price - buf, 5)
    return round(extreme_price + buf, 5)


def score_video_setup(
    context: str,
    three_point_grade: str,
    sweep_kind: str,
    approach_score: float,
    has_breaker_ifvg_overlap: bool,
    in_sd_zone: bool,
    pd_mid_target: bool,
    rr: float,
) -> Tuple[float, Dict[str, float]]:
    """
    Monotonic, explainable confluence scoring for video-derived setups.
    Returns (total_score_0_100, feature_contributions_dict).
    """
    breakdown: Dict[str, float] = {
        "time_window": 18.0 if context in ("SILVER_BULLET", "NY_MACRO", "NY_KILLZONE", "JUDAS") else (10.0 if context != "NONE" else 4.0),
        "three_point_grade": 30.0 if three_point_grade == "A+" else (15.0 if three_point_grade == "B" else 0.0),
        "sweep_kind": 15.0 if sweep_kind == "SWEEP" else 5.0,
        "approach_score": round(min(10.0, max(0.0, approach_score / 10.0)), 2),
        "breaker_ifvg_overlap": 12.0 if has_breaker_ifvg_overlap else 0.0,
        "sd_zone_flag": 6.0 if in_sd_zone else 0.0,
        "pd_mid_confluence": 4.0 if pd_mid_target else 0.0,
        "rr_quality": round(min(5.0, max(0.0, (rr - 1.5) * 2.5)), 2),
    }
    total = round(min(100.0, sum(breakdown.values())), 2)
    return total, breakdown


class VideoSetupEngine:
    """
    Unified detector for S1-S10 video-derived setups.
    Does not alter or filter any existing strategy engine entries.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        session_engine: Optional[TradingSessionEngine] = None,
        session_liq_engine: Optional[SessionLiquidityEngine] = None,
        coordinator: Optional[InverseDirectionCoordinator] = None,
    ):
        merged = dict(DEFAULT_VIDEO_SETUPS_CONFIG)
        if config:
            merged.update(config)
            if "setups" in config and isinstance(config["setups"], dict):
                merged_setups = dict(DEFAULT_VIDEO_SETUPS_CONFIG["setups"])
                for k, v in config["setups"].items():
                    merged_setups[k] = {**merged_setups.get(k, {}), **v}
                merged["setups"] = merged_setups
        self.cfg = validate_video_setups_config(merged)
        self.session_engine = session_engine or TradingSessionEngine()
        self.session_liq_engine = session_liq_engine or SessionLiquidityEngine()
        self.coordinator = coordinator or InverseDirectionCoordinator()
        self.skipped_events: List[Dict[str, Any]] = []

    def _setup_cfg(self, setup_id: str) -> Dict[str, Any]:
        return self.cfg["setups"].get(setup_id, {})

    def _record_skip(self, setup_id: str, symbol: str, reason: str) -> None:
        self.skipped_events.append({
            "tier": 3,
            "setup_id": setup_id,
            "symbol": symbol,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.skipped_events) > 200:
            self.skipped_events = self.skipped_events[-200:]

    def _build_signal(
        self,
        *,
        setup_id: str,
        symbol: str,
        timeframe: Timeframe,
        direction: OrderType,
        entry_price: float,
        stop_loss: float,
        draw: Optional[DrawOnLiquidity],
        timestamp: datetime,
        context: str,
        sweep_kind: str,
        turn: ThreePointTurnResult,
        entry_model: str,
        invalidation_price: float,
        provenance: List[str],
        fvg: Optional[FairValueGap] = None,
        ob: Optional[OrderBlock] = None,
        has_overlap: bool = False,
        in_sd_zone: bool = False,
        pd_mid_target: bool = False,
        approach_score: float = 50.0,
        account_profile: str = "DEMO",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[SignalCandidate]:
        scfg = self._setup_cfg(setup_id)
        if not scfg.get("enabled", True):
            return None

        min_rr = float(
            self.cfg.get("default_min_rr_prop", 2.5)
            if account_profile.upper() == "PROP"
            else scfg.get("min_rr", self.cfg.get("default_min_rr_demo", 2.0))
        )

        # P10: "No draw, no trade"
        ok_draw, rr, draw_reason = validate_draw_on_liquidity(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            draw=draw,
            min_rr=min_rr,
        )
        if not ok_draw or draw is None:
            self._record_skip(setup_id, symbol, draw_reason)
            return None

        # P11 grade gate (A+ required by default; B allowed only if allow_b_grade=True)
        allow_b = bool(scfg.get("allow_b_grade", False))
        if turn.grade == "INVALID" or (turn.grade == "B" and not allow_b):
            self._record_skip(setup_id, symbol, f"GRADE_{turn.grade}: {turn.reason}")
            return None

        score, breakdown = score_video_setup(
            context=context,
            three_point_grade=turn.grade,
            sweep_kind=sweep_kind,
            approach_score=approach_score,
            has_breaker_ifvg_overlap=has_overlap,
            in_sd_zone=in_sd_zone,
            pd_mid_target=pd_mid_target,
            rr=rr,
        )

        # Execution routing: DEMO_EXECUTE for A+, SHADOW for lower grades or when SHADOW configured
        cfg_mode = str(self.cfg.get("execution_mode_for_new_setups", "DEMO_EXECUTE")).upper()
        exec_policy = "DEMO_EXECUTE" if (cfg_mode == "DEMO_EXECUTE" and turn.grade == "A+") else "SHADOW"

        meta = {
            "execution_policy": exec_policy,
            "partial_pct": float(scfg.get("partial_pct", 0.50)),
            "cancel_on_window_end": bool(scfg.get("cancel_on_window_end", False)),
            "smt_source": turn.smt_source,
            "correlation_regime": turn.correlation_regime,
            **(extra_meta or {}),
        }

        return SignalCandidate(
            id=f"{setup_id}_{symbol}_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            setup_type=SetupType.SMC_MODEL_1_SWEEP,
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(draw.price, 5),
            risk_reward=rr,
            score=score,
            timestamp=timestamp,
            status="APPROVED" if exec_policy == "DEMO_EXECUTE" else "SHADOW",
            reasons=[
                f"{setup_id} ({context}) grade={turn.grade} entry={entry_model} RR={rr:.2f}",
                f"Draw={draw.pool_type}@{draw.price:.5f}",
            ],
            fvg=fvg,
            ob=ob,
            related_level=draw.pool_type,
            metadata=meta,
            session_name=context,
            setup_id=setup_id,
            context=context,
            sweep_kind=sweep_kind,
            smt_status=turn.smt_status,
            three_point_grade=turn.grade,
            draw_on_liquidity={"price": draw.price, "type": draw.pool_type, "pool_id": draw.pool_id},
            entry_model=entry_model,
            invalidation_price=round(invalidation_price, 5),
            provenance=list(provenance),
            confluence_breakdown=breakdown,
        )

    def _eval_smt(
        self,
        symbol: str,
        candles: Sequence[Candle],
        direction: OrderType,
        sweep_index: int,
        correlated_symbol: Optional[str],
        correlated_candles: Optional[Sequence[Candle]],
        inverse_pair: bool = True,
    ) -> Tuple[str, str, str]:
        return evaluate_smt_divergence_video(
            primary_symbol=symbol,
            primary_candles=candles,
            direction=direction,
            sweep_index=sweep_index,
            correlated_symbol=correlated_symbol,
            correlated_candles=correlated_candles,
            inverse_pair=inverse_pair,
            coordinator=self.coordinator,
        )

    # ------------------------------------------------------------------------
    # S1: Raid -> Shift -> FVG -> CE (core 4-step engine)
    # ------------------------------------------------------------------------
    def detect_s1_raid_shift_fvg_ce(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        direction: Optional[OrderType] = None,
        *,
        context: str = "NONE",
        setup_id: str = "S1_RAID_SHIFT_FVG_CE",
        provenance: Optional[List[str]] = None,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[SignalCandidate]:
        if len(candles) < 10:
            return None
        pools = detect_equal_clusters(
            symbol, timeframe, candles,
            atr_tolerance_mult=float(self.cfg.get("eqh_tolerance_atr", 0.10)),
        )
        key_zones = key_levels.to_liquidity_zones(pip_size=pip_size) if key_levels else []
        atr = compute_atr(candles, 14)

        dirs = [direction] if direction is not None else [OrderType.BUY, OrderType.SELL]
        for d in dirs:
            target_types = ("EQL", "SSL") if d == OrderType.BUY else ("EQH", "BSL")
            candidate_pools = [p for p in pools if p.level_type in target_types]
            for pool in candidate_pools:
                sweep = detect_confirmed_sweep(
                    candles,
                    level_price=pool.price,
                    level_type=pool.level_type,
                    start_index=pool.formation_index + 1,
                    min_pierce_atr=float(self.cfg.get("min_pierce_atr", 0.05)),
                    max_bars_to_reclaim=int(self.cfg.get("max_bars_to_reclaim", 3)),
                )
                if not sweep:
                    continue
                mss = detect_mss_with_displacement(
                    symbol, timeframe, candles,
                    after_index=sweep.reclaim_index,
                    direction=d,
                    fvg_min_atr=float(self.cfg.get("fvg_min_atr", 0.15)),
                    pip_size=pip_size,
                )
                if not mss:
                    continue

                smt_status, smt_src, regime = self._eval_smt(
                    symbol, candles, d, sweep.pierce_index,
                    correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
                )
                turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
                sl = compute_stop_with_buffer(
                    d, sweep.sweep_extreme, spread_price, atr,
                    stop_buffer_atr=float(self.cfg.get("stop_buffer_atr", 0.05)),
                )
                draw = get_draw_on_liquidity(d, mss.ce_price, pools, key_zones)
                sig = self._build_signal(
                    setup_id=setup_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=d,
                    entry_price=mss.ce_price,
                    stop_loss=sl,
                    draw=draw,
                    timestamp=candles[-1].time,
                    context=context,
                    sweep_kind=sweep.classification.kind,
                    turn=turn,
                    entry_model="CE",
                    invalidation_price=sweep.sweep_extreme,
                    provenance=provenance or ["keepssy_fx-20261126-0007", "keepssy_fx-20261126-0008"],
                    fvg=mss.fvg,
                    approach_score=sweep.classification.score,
                    account_profile=account_profile,
                    extra_meta=extra_meta,
                )
                if sig:
                    return sig
        return None

    # ------------------------------------------------------------------------
    # S2: Silver Bullet (3 NY windows)
    # ------------------------------------------------------------------------
    def detect_s2_silver_bullet(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        *,
        broker_utc_offset_sec: int = 0,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if not candles:
            return None
        win = self.session_engine.get_active_ict_windows(
            candles[-1].time, broker_utc_offset_sec=broker_utc_offset_sec
        )
        if not win["is_silver_bullet"]:
            return None
        sb_name = next((w for w in win["active_windows"] if w.startswith("silver_bullet_")), "silver_bullet_ny_am")
        end_utc = win["window_ends_utc"].get(sb_name)
        return self.detect_s1_raid_shift_fvg_ce(
            symbol, timeframe, candles,
            context="SILVER_BULLET",
            setup_id="S2_SILVER_BULLET",
            provenance=["keepssy_fx-20261126-0001", "keepssy_fx-20261126-0009"],
            correlated_symbol=correlated_symbol,
            correlated_candles=correlated_candles,
            inverse_pair=inverse_pair,
            key_levels=key_levels,
            spread_price=spread_price,
            pip_size=pip_size,
            account_profile=account_profile,
            extra_meta={
                "window_name": sb_name,
                "window_end_utc": end_utc.isoformat() if end_utc else None,
            },
        )

    # ------------------------------------------------------------------------
    # S3: NY Macro (09:50-10:10 & 10:50-11:10 NY)
    # ------------------------------------------------------------------------
    def detect_s3_ny_macro(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        *,
        broker_utc_offset_sec: int = 0,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if not candles:
            return None
        win = self.session_engine.get_active_ict_windows(
            candles[-1].time, broker_utc_offset_sec=broker_utc_offset_sec
        )
        if not win["is_ny_macro"]:
            return None
        m_name = next((w for w in win["active_windows"] if w.startswith("ny_macro_")), "ny_macro_1")
        end_utc = win["window_ends_utc"].get(m_name)
        return self.detect_s1_raid_shift_fvg_ce(
            symbol, timeframe, candles,
            context="NY_MACRO",
            setup_id="S3_NY_MACRO",
            provenance=["keepssy_fx-20261126-0010"],
            correlated_symbol=correlated_symbol,
            correlated_candles=correlated_candles,
            inverse_pair=inverse_pair,
            key_levels=key_levels,
            spread_price=spread_price,
            pip_size=pip_size,
            account_profile=account_profile,
            extra_meta={
                "window_name": m_name,
                "window_end_utc": end_utc.isoformat() if end_utc else None,
            },
        )

    # ------------------------------------------------------------------------
    # S4: London Judas Swing / Fake Breakout of Asian Range
    # ------------------------------------------------------------------------
    def detect_s4_london_judas(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        asian_high: float,
        asian_low: float,
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if len(candles) < 8 or asian_high <= asian_low:
            return None
        atr = compute_atr(candles, 14)

        for lvl_type, lvl_px, opp_px, opp_type, d in [
            ("ASIA_HIGH", asian_high, asian_low, "ASIA_LOW_SSL", OrderType.SELL),
            ("ASIA_LOW", asian_low, asian_high, "ASIA_HIGH_BSL", OrderType.BUY),
        ]:
            sweep = detect_confirmed_sweep(
                candles, level_price=lvl_px, level_type=lvl_type,
                min_pierce_atr=float(self.cfg.get("min_pierce_atr", 0.05)),
                max_bars_to_reclaim=int(self.cfg.get("max_bars_to_reclaim", 3)),
            )
            if not sweep:
                continue
            mss = detect_mss_with_displacement(
                symbol, timeframe, candles, after_index=sweep.reclaim_index, direction=d,
                fvg_min_atr=float(self.cfg.get("fvg_min_atr", 0.15)), pip_size=pip_size,
            )
            if not mss:
                continue
            smt_status, smt_src, regime = self._eval_smt(
                symbol, candles, d, sweep.pierce_index,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sl = compute_stop_with_buffer(d, sweep.sweep_extreme, spread_price, atr)
            draw = DrawOnLiquidity(
                price=opp_px, pool_type=opp_type, pool_id=f"{symbol}_{opp_type}",
                distance=abs(opp_px - mss.ce_price),
            )
            sig = self._build_signal(
                setup_id="S4_LONDON_JUDAS_SWING",
                symbol=symbol,
                timeframe=timeframe,
                direction=d,
                entry_price=mss.ce_price,
                stop_loss=sl,
                draw=draw,
                timestamp=candles[-1].time,
                context="JUDAS",
                sweep_kind=sweep.classification.kind,
                turn=turn,
                entry_model="CE",
                invalidation_price=sweep.sweep_extreme,
                provenance=["keepssy_fx-20261126-0011"],
                fvg=mss.fvg,
                approach_score=sweep.classification.score,
                account_profile=account_profile,
            )
            if sig:
                return sig
        return None

    # ------------------------------------------------------------------------
    # S5: Asian-Range SD Projection Reversal (-2/-2.5 SD & +2/+2.5 SD)
    # ------------------------------------------------------------------------
    def detect_s5_asian_sd_reversal(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        asian_high: float,
        asian_low: float,
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        rng = asian_high - asian_low
        if len(candles) < 8 or rng <= 0:
            return None
        atr = compute_atr(candles, 14)

        # Downside projections (-1, -2, -2.5 SD) -> Bullish reversal back to Asian Low
        neg_2 = asian_low - 2.0 * rng
        neg_25 = asian_low - 2.5 * rng
        # Upside projections (+1, +2, +2.5 SD) -> Bearish reversal back to Asian High
        pos_2 = asian_high + 2.0 * rng
        pos_25 = asian_high + 2.5 * rng

        for d, zone_edge, zone_far, tp1, tp_label in [
            (OrderType.BUY, neg_2, neg_25, asian_low, "ASIA_LOW_TP1"),
            (OrderType.SELL, pos_2, pos_25, asian_high, "ASIA_HIGH_TP1"),
        ]:
            # Find candle that entered the +-2.0 to +-2.5 SD run-out zone
            touch_idx: Optional[int] = None
            extreme_px: float = 0.0
            for i, c in enumerate(candles):
                if d == OrderType.BUY and neg_25 <= c.low <= neg_2:
                    if touch_idx is None or c.low < extreme_px:
                        touch_idx = i
                        extreme_px = c.low
                elif d == OrderType.SELL and pos_2 <= c.high <= pos_25:
                    if touch_idx is None or c.high > extreme_px:
                        touch_idx = i
                        extreme_px = c.high
            if touch_idx is None or touch_idx >= len(candles) - 2:
                continue

            mss = detect_mss_with_displacement(
                symbol, timeframe, candles, after_index=touch_idx, direction=d,
                fvg_min_atr=float(self.cfg.get("fvg_min_atr", 0.15)), pip_size=pip_size,
            )
            if not mss:
                continue
            # Require FVG above -2 SD projection (for longs) or below +2 SD (for shorts)
            if d == OrderType.BUY and mss.fvg.bottom < neg_25:
                continue
            if d == OrderType.SELL and mss.fvg.top > pos_25:
                continue

            smt_status, smt_src, regime = self._eval_smt(
                symbol, candles, d, touch_idx,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sl = compute_stop_with_buffer(d, extreme_px, spread_price, atr)
            draw = DrawOnLiquidity(
                price=tp1, pool_type=tp_label, pool_id=f"{symbol}_{tp_label}",
                distance=abs(tp1 - mss.ce_price),
            )
            sig = self._build_signal(
                setup_id="S5_ASIAN_SD_REVERSAL",
                symbol=symbol,
                timeframe=timeframe,
                direction=d,
                entry_price=mss.ce_price,
                stop_loss=sl,
                draw=draw,
                timestamp=candles[-1].time,
                context="ASIAN_SD",
                sweep_kind="SWEEP",
                turn=turn,
                entry_model="CE",
                invalidation_price=extreme_px,
                provenance=["keepssy_fx-20261126-0013"],
                fvg=mss.fvg,
                in_sd_zone=True,
                account_profile=account_profile,
                extra_meta={
                    "runner_enabled": True,
                    "sd_projections": {
                        "-1": round(asian_low - rng, 5),
                        "-2": round(neg_2, 5),
                        "-2.5": round(neg_25, 5),
                        "+1": round(asian_high + rng, 5),
                        "+2": round(pos_2, 5),
                        "+2.5": round(pos_25, 5),
                    },
                },
            )
            if sig:
                return sig
        return None

    # ------------------------------------------------------------------------
    # S6: IFVG Reversal After Stop Hunt
    # ------------------------------------------------------------------------
    def detect_s6_ifvg_stop_hunt(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if len(candles) < 8:
            return None
        pools = detect_equal_clusters(symbol, timeframe, candles)
        key_zones = key_levels.to_liquidity_zones(pip_size=pip_size) if key_levels else []
        atr = compute_atr(candles, 14)

        for d in (OrderType.BUY, OrderType.SELL):
            target_types = ("EQL", "SSL") if d == OrderType.BUY else ("EQH", "BSL")
            for pool in [p for p in pools if p.level_type in target_types]:
                sweep = detect_confirmed_sweep(
                    candles, pool.price, pool.level_type, start_index=pool.formation_index + 1,
                )
                if not sweep:
                    continue
                ifvgs = detect_ifvg_candidates(
                    symbol, timeframe, candles, direction=d, stop_hunt_index=sweep.pierce_index,
                    fvg_min_atr=float(self.cfg.get("fvg_min_atr", 0.15)), pip_size=pip_size,
                )
                if not ifvgs:
                    continue
                best_ifvg = ifvgs[0]
                smt_status, smt_src, regime = self._eval_smt(
                    symbol, candles, d, sweep.pierce_index,
                    correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
                )
                turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
                sl = compute_stop_with_buffer(d, sweep.sweep_extreme, spread_price, atr)
                draw = get_draw_on_liquidity(d, best_ifvg.ifvg.midpoint, pools, key_zones)
                inv_px = best_ifvg.ifvg.bottom if d == OrderType.BUY else best_ifvg.ifvg.top
                sig = self._build_signal(
                    setup_id="S6_IFVG_STOP_HUNT",
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=d,
                    entry_price=best_ifvg.ifvg.midpoint,
                    stop_loss=sl,
                    draw=draw,
                    timestamp=candles[-1].time,
                    context="NONE",
                    sweep_kind=sweep.classification.kind,
                    turn=turn,
                    entry_model="IFVG_RETEST",
                    invalidation_price=inv_px,
                    provenance=["keepssy_fx-20261126-0005"],
                    fvg=best_ifvg.ifvg,
                    approach_score=sweep.classification.score,
                    account_profile=account_profile,
                    extra_meta={
                        "is_first_before_stop_hunt": best_ifvg.is_first_before_stop_hunt,
                        "retested": best_ifvg.retested,
                    },
                )
                if sig:
                    return sig
        return None

    # ------------------------------------------------------------------------
    # S7: Stacked Breaker + IFVG Overlap
    # ------------------------------------------------------------------------
    def detect_s7_stacked_breaker_ifvg(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if len(candles) < 8:
            return None
        pools = detect_equal_clusters(symbol, timeframe, candles)
        key_zones = key_levels.to_liquidity_zones(pip_size=pip_size) if key_levels else []
        atr = compute_atr(candles, 14)

        for d in (OrderType.SELL, OrderType.BUY):
            breakers = detect_flipped_breakers(symbol, timeframe, candles, direction=d, pip_size=pip_size)
            ifvgs = detect_ifvg_candidates(symbol, timeframe, candles, direction=d, pip_size=pip_size)
            if not breakers or not ifvgs:
                continue

            # Find overlapping breaker + IFVG pair
            overlap_pair: Optional[Tuple[OrderBlock, FairValueGap, float, float]] = None
            for br in breakers:
                for iv in ifvgs:
                    ov_low = max(br.low, iv.ifvg.bottom)
                    ov_high = min(br.high, iv.ifvg.top)
                    if ov_low <= ov_high:
                        overlap_pair = (br, iv.ifvg, ov_low, ov_high)
                        break
                if overlap_pair:
                    break
            if not overlap_pair:
                continue

            br, iv_fvg, ov_low, ov_high = overlap_pair
            entry_px = (ov_low + ov_high) / 2.0
            raid_extreme = max(c.high for c in candles) if d == OrderType.SELL else min(c.low for c in candles)
            raid_idx = (
                max(range(len(candles)), key=lambda i: candles[i].high)
                if d == OrderType.SELL
                else min(range(len(candles)), key=lambda i: candles[i].low)
            )
            smt_status, smt_src, regime = self._eval_smt(
                symbol, candles, d, raid_idx,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sl = compute_stop_with_buffer(d, raid_extreme, spread_price, atr)
            draw = get_draw_on_liquidity(d, entry_px, pools, key_zones)
            inv_px = br.high if d == OrderType.SELL else br.low
            sig = self._build_signal(
                setup_id="S7_STACKED_BREAKER_IFVG",
                symbol=symbol,
                timeframe=timeframe,
                direction=d,
                entry_price=entry_px,
                stop_loss=sl,
                draw=draw,
                timestamp=candles[-1].time,
                context="NONE",
                sweep_kind="SWEEP",
                turn=turn,
                entry_model="BREAKER_OVERLAP",
                invalidation_price=inv_px,
                provenance=["keepssy_fx-20261126-0004"],
                fvg=iv_fvg,
                ob=br,
                has_overlap=True,
                account_profile=account_profile,
                extra_meta={"overlap_zone": [round(ov_low, 5), round(ov_high, 5)]},
            )
            if sig:
                return sig
        return None

    # ------------------------------------------------------------------------
    # S8: OTE Entry After Stop Hunt + BOS (0.705 or FVG inside 0.62-0.79)
    # ------------------------------------------------------------------------
    def detect_s8_ote_stop_hunt_bos(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        key_levels: Optional[SessionKeyLevels] = None,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        if len(candles) < 10:
            return None
        pools = detect_equal_clusters(symbol, timeframe, candles)
        key_zones = key_levels.to_liquidity_zones(pip_size=pip_size) if key_levels else []
        atr = compute_atr(candles, 14)
        scfg = self._setup_cfg("S8_OTE_STOP_HUNT_BOS")
        entry_lvl = float(scfg.get("ote_entry_level", 0.705))

        for d in (OrderType.BUY, OrderType.SELL):
            ote = compute_bos_anchored_ote(
                symbol, timeframe, candles, direction=d, entry_level=entry_lvl, pip_size=pip_size
            )
            if not ote:
                continue
            entry_px = ote.overlapping_fvg.midpoint if ote.overlapping_fvg else ote.ote_sweet_spot
            sl = compute_stop_with_buffer(d, ote.anchor_origin, spread_price, atr)
            draw = get_draw_on_liquidity(d, entry_px, pools, key_zones)
            if draw is None:
                # Target opposing extreme of the BOS leg if untapped
                draw = DrawOnLiquidity(
                    price=ote.anchor_extreme,
                    pool_type="BSL" if d == OrderType.BUY else "SSL",
                    pool_id=f"{symbol}_OTE_TARGET",
                    distance=abs(ote.anchor_extreme - entry_px),
                )
            smt_status, smt_src, regime = self._eval_smt(
                symbol, candles, d, ote.origin_index,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sig = self._build_signal(
                setup_id="S8_OTE_STOP_HUNT_BOS",
                symbol=symbol,
                timeframe=timeframe,
                direction=d,
                entry_price=entry_px,
                stop_loss=sl,
                draw=draw,
                timestamp=candles[-1].time,
                context="NONE",
                sweep_kind="SWEEP",
                turn=turn,
                entry_model="OTE",
                invalidation_price=ote.anchor_origin,
                provenance=[
                    "keepssy_fx-20261126-0002",
                    "keepssy_fx-20261126-0003",
                    "algovistra-20261125-0001",
                ],
                fvg=ote.overlapping_fvg,
                account_profile=account_profile,
                extra_meta={
                    "fib_levels": ote.levels,
                    "ote_zone": [ote.ote_low, ote.ote_high],
                    "tap_and_close_triggered": ote.tap_and_close_triggered,
                },
            )
            if sig:
                return sig
        return None

    # ------------------------------------------------------------------------
    # S9: Hidden Demand/Supply (HTF wick-to-wick gap behind BOS -> LTF OB)
    # ------------------------------------------------------------------------
    def detect_s9_hidden_demand_supply(
        self,
        symbol: str,
        htf_candles: Sequence[Candle],
        ltf_candles: Sequence[Candle],
        *,
        htf_timeframe: Timeframe = Timeframe.H1,
        ltf_timeframe: Timeframe = Timeframe.M5,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        """
        S9 [VIDEO: nexusquant_ai-20261125-0001]:
        Finds an HTF BOS impulse containing two same-direction candles whose wicks do NOT
        overlap (hidden wick-to-wick gap), then refines on LTF to the last opposing candle
        inside that zone for a limit entry.
        """
        if len(htf_candles) < 6 or len(ltf_candles) < 5:
            return None
        atr_ltf = compute_atr(ltf_candles, 14)

        for d in (OrderType.BUY, OrderType.SELL):
            # Look for HTF BOS + wick-to-wick gap between candle i-1 and i+1
            zone_bounds: Optional[Tuple[float, float, datetime, float]] = None
            for i in range(2, len(htf_candles) - 1):
                c_prev = htf_candles[i - 1]
                c_imp = htf_candles[i]
                c_next = htf_candles[i + 1]
                prior_high = max(c.high for c in htf_candles[:i])
                prior_low = min(c.low for c in htf_candles[:i])

                if d == OrderType.BUY and c_imp.is_bullish and c_next.is_bullish:
                    if max(c_imp.close, c_next.close) > prior_high and c_next.low > c_prev.high:
                        target_px = max(c.high for c in htf_candles[i:])
                        zone_bounds = (c_prev.high, c_next.low, c_imp.time, target_px)
                elif d == OrderType.SELL and c_imp.is_bearish and c_next.is_bearish:
                    if min(c_imp.close, c_next.close) < prior_low and c_next.high < c_prev.low:
                        target_px = min(c.low for c in htf_candles[i:])
                        zone_bounds = (c_next.high, c_prev.low, c_imp.time, target_px)

            if not zone_bounds:
                continue

            z_low, z_high, _z_time, target_px = zone_bounds
            # Refine on LTF: find last opposing candle inside [z_low, z_high]
            ltf_ob: Optional[Candle] = None
            for lc in reversed(ltf_candles):
                in_zone = lc.low <= z_high and lc.high >= z_low
                if not in_zone:
                    continue
                if d == OrderType.BUY and lc.is_bearish:
                    ltf_ob = lc
                    break
                if d == OrderType.SELL and lc.is_bullish:
                    ltf_ob = lc
                    break

            entry_px = (
                (ltf_ob.high if d == OrderType.BUY else ltf_ob.low)
                if ltf_ob is not None
                else (z_low + z_high) / 2.0
            )
            sl_base = z_low if d == OrderType.BUY else z_high
            sl = compute_stop_with_buffer(d, sl_base, spread_price, atr_ltf)
            draw = DrawOnLiquidity(
                price=target_px,
                pool_type="BSL" if d == OrderType.BUY else "SSL",
                pool_id=f"{symbol}_S9_BSL_SSL",
                distance=abs(target_px - entry_px),
            )
            smt_status, smt_src, regime = self._eval_smt(
                symbol, ltf_candles, d, len(ltf_candles) - 1,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sig = self._build_signal(
                setup_id="S9_HIDDEN_DEMAND_SUPPLY",
                symbol=symbol,
                timeframe=ltf_timeframe,
                direction=d,
                entry_price=entry_px,
                stop_loss=sl,
                draw=draw,
                timestamp=ltf_candles[-1].time,
                context="NONE",
                sweep_kind="SWEEP",
                turn=turn,
                entry_model="LTF_OB_LIMIT",
                invalidation_price=sl_base,
                provenance=["nexusquant_ai-20261125-0001"],
                account_profile=account_profile,
                extra_meta={
                    "htf_timeframe": htf_timeframe.value,
                    "hidden_zone": [round(z_low, 5), round(z_high, 5)],
                    "ltf_ob_refined": ltf_ob is not None,
                },
            )
            if sig:
                return sig
        return None

    # ------------------------------------------------------------------------
    # S10: Session-Level Sweep Reversals (Asia->LDN, LDN->NY, PDL/PDH->PD Mid)
    # ------------------------------------------------------------------------
    def detect_s10_session_sweep_reversal(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
        key_levels: SessionKeyLevels,
        *,
        correlated_symbol: Optional[str] = None,
        correlated_candles: Optional[Sequence[Candle]] = None,
        inverse_pair: bool = True,
        spread_price: float = 0.0,
        pip_size: float = 0.01,
        account_profile: str = "DEMO",
    ) -> Optional[SignalCandidate]:
        """
        S10 [VIDEO: scriptedge_-20261114-0001]:
        1. London sweeps Asia Low/High -> reversal
        2. NY sweeps London High/Low -> reversal
        3. PDL/PDH swept -> return to Previous-Day Midpoint (PD Mid as TP1)
        Always enters via S1 mechanics (MSS + FVG + CE), NEVER on the sweep alone.
        """
        if len(candles) < 8 or key_levels is None:
            return None
        atr = compute_atr(candles, 14)

        level_cases: List[Tuple[str, Optional[float], Optional[float], str, OrderType, bool]] = [
            ("PDL", key_levels.pdl, key_levels.pd_mid, "PD_MID", OrderType.BUY, True),
            ("PDH", key_levels.pdh, key_levels.pd_mid, "PD_MID", OrderType.SELL, True),
            ("ASIA_LOW", key_levels.asian_low, key_levels.asian_high, "ASIA_HIGH_BSL", OrderType.BUY, False),
            ("ASIA_HIGH", key_levels.asian_high, key_levels.asian_low, "ASIA_LOW_SSL", OrderType.SELL, False),
            ("LONDON_HIGH", key_levels.london_high, key_levels.london_low, "LONDON_LOW_SSL", OrderType.SELL, False),
            ("LONDON_LOW", key_levels.london_low, key_levels.london_high, "LONDON_HIGH_BSL", OrderType.BUY, False),
        ]

        for lvl_name, lvl_px, target_px, target_type, d, is_pd_mid in level_cases:
            if lvl_px is None or target_px is None:
                continue
            sweep = detect_confirmed_sweep(
                candles, level_price=lvl_px, level_type=lvl_name,
                min_pierce_atr=float(self.cfg.get("min_pierce_atr", 0.05)),
                max_bars_to_reclaim=int(self.cfg.get("max_bars_to_reclaim", 3)),
            )
            if not sweep:
                continue
            mss = detect_mss_with_displacement(
                symbol, timeframe, candles, after_index=sweep.reclaim_index, direction=d,
                fvg_min_atr=float(self.cfg.get("fvg_min_atr", 0.15)), pip_size=pip_size,
            )
            if not mss:
                continue
            smt_status, smt_src, regime = self._eval_smt(
                symbol, candles, d, sweep.pierce_index,
                correlated_symbol, correlated_candles, inverse_pair=inverse_pair,
            )
            turn = evaluate_three_point_turn(True, True, smt_status, smt_src, regime)
            sl = compute_stop_with_buffer(d, sweep.sweep_extreme, spread_price, atr)
            draw = DrawOnLiquidity(
                price=target_px,
                pool_type=target_type,
                pool_id=f"{symbol}_{target_type}",
                distance=abs(target_px - mss.ce_price),
            )
            sig = self._build_signal(
                setup_id="S10_SESSION_SWEEP_REVERSAL",
                symbol=symbol,
                timeframe=timeframe,
                direction=d,
                entry_price=mss.ce_price,
                stop_loss=sl,
                draw=draw,
                timestamp=candles[-1].time,
                context="SESSION_SWEEP",
                sweep_kind=sweep.classification.kind,
                turn=turn,
                entry_model="CE",
                invalidation_price=sweep.sweep_extreme,
                provenance=["scriptedge_-20261114-0001"],
                fvg=mss.fvg,
                pd_mid_target=is_pd_mid,
                approach_score=sweep.classification.score,
                account_profile=account_profile,
                extra_meta={"swept_session_level": lvl_name},
            )
            if sig:
                return sig
        return None
