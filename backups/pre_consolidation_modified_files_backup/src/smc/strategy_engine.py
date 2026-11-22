"""
ICT and Smart Money Concepts Strategy Engine.
Combines Weekly/Daily Liquidity models, Multi-Timeframe Bias,
Market Structure Shifts, FVG/OB entries, and Confluence Scoring (>= 75/100).
Aligned with Canonical SMC Rulebook (R1-R9).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from src.core.contracts import (
    Candle, Timeframe, OrderType, TrendBias, SetupType, SignalCandidate,
    FairValueGap, OrderBlock, MarketStructureType, WeeklyDailyLevels, ExecutionMode
)
from src.smc.mtf_analyzer import MultiTimeframeContext
from src.smc.market_structure import MarketStructureEngine
from src.smc.fvg_ob import FvgObEngine
from src.smc.weekly_daily import InteractionType
from src.smc.structure_confirmation import StructureStateMachine, ConfirmationState, CycleDirection, StructureStateSnapshot
from src.core.instruments import get_registry


def _get_instrument_min_score(symbol: str, default_min_score: float) -> float:
    """Fetch instrument-specific min_confidence from InstrumentRegistry,
    falling back to default_min_score if not found or <= 0."""
    try:
        registry = get_registry()
        profile = registry.get(symbol)
        if profile and profile.min_confidence > 0:
            return float(profile.min_confidence)
    except Exception:
        pass
    return default_min_score


def _get_instrument_pip_size(symbol: str, default_pip_size: float) -> float:
    """Fetch instrument-specific pip_size from InstrumentRegistry."""
    try:
        registry = get_registry()
        profile = registry.get(symbol)
        if profile and profile.pip_size > 0:
            return float(profile.pip_size)
    except Exception:
        pass
    return default_pip_size


class SmcStrategyEngine:
    def __init__(
        self,
        min_score: float = 75.0,
        min_rr: float = 2.0,
        pip_size: float = 0.0001,
        swing_lookback: int = 5,
        require_close_break: bool = True,
        require_lower_high: bool = True,
        choch_timeout_bars: int = 20,
        allow_choch_only_entries: bool = False,
        choch_requires_confirmation: bool = True,
        failed_choch_action: str = "RESET_AND_LOG_TRAP",
        tp_requires_liquidity_pool: bool = True,
        fvg_min_atr: float = 0.3,
        ob_requires_displacement: bool = True,
        ob_displacement_atr_mult: float = 1.2,
        ob_requires_bos: bool = True,
        pd_equilibrium: float = 0.5,
        sweep_requires_close_back_inside: bool = True,
    ):
        self.sweep_requires_close_back_inside = sweep_requires_close_back_inside
        self.min_score = min_score
        self.min_rr = min_rr
        self.pip_size = pip_size
        self.choch_requires_confirmation = choch_requires_confirmation
        self.allow_choch_only_entries = allow_choch_only_entries and (not choch_requires_confirmation)
        self.tp_requires_liquidity_pool = tp_requires_liquidity_pool
        self.fvg_min_atr = fvg_min_atr
        self.ob_requires_displacement = ob_requires_displacement
        self.ob_displacement_atr_mult = ob_displacement_atr_mult
        self.ob_requires_bos = ob_requires_bos
        self.pd_equilibrium = pd_equilibrium

        self.struct_engine = MarketStructureEngine(
            swing_lookback=swing_lookback,
            bos_body_close_required=require_close_break,
        )
        self.fvg_engine = FvgObEngine(
            min_fvg_pips=1.5,
            pip_size=pip_size,
            fvg_min_atr=fvg_min_atr,
            ob_requires_displacement=ob_requires_displacement,
            ob_displacement_atr_mult=ob_displacement_atr_mult,
            ob_requires_bos=ob_requires_bos,
            pd_equilibrium=pd_equilibrium,
        )
        self._fvg_engine_cache: Dict[str, FvgObEngine] = {}
        self.pattern_adapter = None
        self.session_liq_engine = None
        self.session_liq_enabled = False
        self.execution_mode: Optional[ExecutionMode] = None
        try:
            import json, os
            cfg_p = "config/sessions.json"
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    s_cfg = json.load(f)
                    self.session_liq_enabled = bool(s_cfg.get("session_liquidity_enabled", True))
            from src.smc.session_liquidity import SessionLiquidityEngine
            self.session_liq_engine = SessionLiquidityEngine(pip_multiplier=1.0 / pip_size if pip_size > 0 else 10000.0)
        except Exception:
            pass
        self.struct_confirmation = StructureStateMachine(
            swing_lookback=swing_lookback,
            require_close_break=require_close_break,
            require_lower_high=require_lower_high,
            choch_timeout_bars=choch_timeout_bars,
            allow_choch_only_entries=self.allow_choch_only_entries,
            choch_requires_confirmation=choch_requires_confirmation,
            failed_choch_action=failed_choch_action
        )

    def _get_fvg_engine(self, symbol: str) -> FvgObEngine:
        """Return cached per-symbol FvgObEngine with accurate instrument pip_size and rulebook params."""
        if symbol not in self._fvg_engine_cache:
            ps = _get_instrument_pip_size(symbol, self.pip_size)
            self._fvg_engine_cache[symbol] = FvgObEngine(
                min_fvg_pips=1.5,
                pip_size=ps,
                fvg_min_atr=self.fvg_min_atr,
                ob_requires_displacement=self.ob_requires_displacement,
                ob_displacement_atr_mult=self.ob_displacement_atr_mult,
                ob_requires_bos=self.ob_requires_bos,
                pd_equilibrium=self.pd_equilibrium,
            )
        return self._fvg_engine_cache[symbol]

    def check_scalp_htf_agreement(
        self,
        mtf_ctx: MultiTimeframeContext,
        weighted: bool = False
    ) -> Tuple[bool, str, Dict[str, str]]:
        """
        Evaluates whether M15, H1, and H4 directions agree for SCALP mode (R1).
        When weighted=False (default): enforces classic strict agreement across M15, H1, H4.
        When weighted=True: H4 is the primary anchor (45%), H1 (35%), M15 (20%) so M15/H1
        cannot override an opposing H4 trend.
        Returns: (agree: bool, log_message: str, directions: Dict[str, str])
        """
        def _bias_to_dir(bias: TrendBias) -> str:
            if bias in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]:
                return "BULLISH"
            elif bias in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH]:
                return "BEARISH"
            return "RANGING"

        m15_dir = _bias_to_dir(mtf_ctx.m15.trend)
        h1_dir = _bias_to_dir(mtf_ctx.h1.trend)
        h4_dir = _bias_to_dir(mtf_ctx.h4.trend)

        directions = {"M15": m15_dir, "H1": h1_dir, "H4": h4_dir}

        if not weighted:
            if m15_dir != "RANGING" and m15_dir == h1_dir == h4_dir:
                return True, f"SCALP HTF agreement: All timeframes {m15_dir}", directions
            else:
                return False, f"SCALP HTF conflict (M15={m15_dir}, H1={h1_dir}, H4={h4_dir})", directions

        # R1: H4 is the primary HTF structure anchor (45%), H1 (35%), M15 (20%)
        weights = {"H4": 0.45, "H1": 0.35, "M15": 0.20}
        bull_score = sum(weights[k] for k, v in directions.items() if v == "BULLISH")
        bear_score = sum(weights[k] for k, v in directions.items() if v == "BEARISH")

        if bull_score >= 0.60 and h4_dir != "BEARISH":
            return True, f"SCALP HTF weighted agreement: BULLISH ({bull_score:.0%})", directions
        elif bear_score >= 0.60 and h4_dir != "BULLISH":
            return True, f"SCALP HTF weighted agreement: BEARISH ({bear_score:.0%})", directions
        else:
            return False, f"SCALP HTF conflict (M15={m15_dir}, H1={h1_dir}, H4={h4_dir})", directions

    def scan_for_opportunities(
        self,
        mtf_ctx: MultiTimeframeContext,
        m15_candles: List[Candle],
        is_in_killzone: bool = False
    ) -> List[SignalCandidate]:
        """
        Scans M15 market data within the multi-timeframe context to identify,
        score, and validate institutional SMC trade setups.
        """
        candidates: List[SignalCandidate] = []
        if len(m15_candles) < 20:
            return candidates

        symbol = mtf_ctx.symbol
        last_candle = m15_candles[-1]
        current_price = last_candle.close

        # Update CHoCH-Warning -> BOS-Confirmation State Machine
        struct_state = self.struct_confirmation.update(symbol, Timeframe.M15, m15_candles)

        # Detect M15 structure, FVGs and OBs
        _, m15_events = self.struct_engine.analyze_structure(symbol, Timeframe.M15, m15_candles)
        sym_fvg_engine = self._get_fvg_engine(symbol)
        m15_fvgs = sym_fvg_engine.detect_fvgs(symbol, Timeframe.M15, m15_candles)
        m15_obs = sym_fvg_engine.detect_order_blocks(symbol, Timeframe.M15, m15_candles)

        active_bullish_fvgs = [f for f in m15_fvgs if not f.mitigated and f.direction == OrderType.BUY]
        active_bearish_fvgs = [f for f in m15_fvgs if not f.mitigated and f.direction == OrderType.SELL]
        active_bullish_obs = [o for o in m15_obs if not o.mitigated and o.direction == OrderType.BUY]
        active_bearish_obs = [o for o in m15_obs if not o.mitigated and o.direction == OrderType.SELL]

        # Check for Weekly/Daily interactions
        interaction_types = [res.interaction for res in mtf_ctx.level_interactions]

        # Compute Asia range & check for London Judas sweeps (only when sessions enabled)
        asia_sweep = None
        if self.session_liq_engine and self.session_liq_enabled:
            asia_range = self.session_liq_engine.calculate_asia_range(symbol, m15_candles)
            if asia_range:
                asia_sweep = self.session_liq_engine.detect_london_asia_sweep(symbol, m15_candles, asia_range, pip_size=self.pip_size)

        # Check for recent M15 Swing / Equal-High / Equal-Low liquidity sweep with rejection
        m15_ssl_sweep, m15_bsl_sweep = self._detect_recent_swing_sweep(m15_candles)

        # ------------------------------------------------------------------
        # Setup 1: BULLISH OPPORTUNITIES (Reversals & Continuations)
        # ------------------------------------------------------------------
        bullish_setup_type: Optional[SetupType] = None
        related_level = None

        if InteractionType.PWL_SWEEP in interaction_types:
            bullish_setup_type = SetupType.WEEKLY_REVERSAL
            related_level = "PWL_SWEEP"
        elif InteractionType.PDL_SWEEP in interaction_types:
            bullish_setup_type = SetupType.DAILY_REVERSAL
            related_level = "PDL_SWEEP"
        elif InteractionType.PWH_ACCEPTED_BREAK in interaction_types:
            bullish_setup_type = SetupType.WEEKLY_CONTINUATION
            related_level = "PWH_ACCEPTED_BREAK"
        elif InteractionType.PDH_ACCEPTED_BREAK in interaction_types:
            bullish_setup_type = SetupType.DAILY_CONTINUATION
            related_level = "PDH_ACCEPTED_BREAK"
        elif mtf_ctx.h4.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]:
            bullish_setup_type = SetupType.M15_SMC_OTE
            related_level = "H4_TREND_ALIGNMENT"
        elif asia_sweep and asia_sweep.direction_bias == OrderType.BUY:
            bullish_setup_type = SetupType.SESSION_SWEEP
            related_level = "ASIA_LOW_SWEEP"
        elif m15_ssl_sweep and any(e.direction == OrderType.BUY for e in m15_events):
            bullish_setup_type = SetupType.DAILY_REVERSAL
            related_level = "M15_SSL_SWEEP"
        elif (
            mtf_ctx.h4.trend != TrendBias.RANGING
            and mtf_ctx.h1.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]
            and (active_bullish_fvgs or active_bullish_obs)
            and any(e.direction == OrderType.BUY for e in m15_events)
        ):
            bullish_setup_type = SetupType.M15_SMC_OTE
            related_level = "H1_M15_CONTINUATION"

        if bullish_setup_type is not None:
            candidate = self._evaluate_bullish_candidate(
                symbol=symbol,
                setup_type=bullish_setup_type,
                related_level=related_level,
                mtf_ctx=mtf_ctx,
                m15_candles=m15_candles,
                m15_events=m15_events,
                active_fvgs=active_bullish_fvgs,
                active_obs=active_bullish_obs,
                is_in_killzone=is_in_killzone,
                struct_state=struct_state
            )
            if candidate:
                candidates.append(candidate)

        # ------------------------------------------------------------------
        # Setup 2: BEARISH OPPORTUNITIES (Reversals & Continuations)
        # ------------------------------------------------------------------
        bearish_setup_type: Optional[SetupType] = None
        bear_related_level = None

        if InteractionType.PWH_SWEEP in interaction_types:
            bearish_setup_type = SetupType.WEEKLY_REVERSAL
            bear_related_level = "PWH_SWEEP"
        elif InteractionType.PDH_SWEEP in interaction_types:
            bearish_setup_type = SetupType.DAILY_REVERSAL
            bear_related_level = "PDH_SWEEP"
        elif InteractionType.PWL_ACCEPTED_BREAK in interaction_types:
            bearish_setup_type = SetupType.WEEKLY_CONTINUATION
            bear_related_level = "PWL_ACCEPTED_BREAK"
        elif InteractionType.PDL_ACCEPTED_BREAK in interaction_types:
            bearish_setup_type = SetupType.DAILY_CONTINUATION
            bear_related_level = "PDL_ACCEPTED_BREAK"
        elif mtf_ctx.h4.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH]:
            bearish_setup_type = SetupType.M15_SMC_OTE
            bear_related_level = "H4_TREND_ALIGNMENT"
        elif asia_sweep and asia_sweep.direction_bias == OrderType.SELL:
            bearish_setup_type = SetupType.SESSION_SWEEP
            bear_related_level = "ASIA_HIGH_SWEEP"
        elif m15_bsl_sweep and any(e.direction == OrderType.SELL for e in m15_events):
            bearish_setup_type = SetupType.DAILY_REVERSAL
            bear_related_level = "M15_BSL_SWEEP"
        elif (
            mtf_ctx.h4.trend != TrendBias.RANGING
            and mtf_ctx.h1.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH]
            and (active_bearish_fvgs or active_bearish_obs)
            and any(e.direction == OrderType.SELL for e in m15_events)
        ):
            bearish_setup_type = SetupType.M15_SMC_OTE
            bear_related_level = "H1_M15_CONTINUATION"

        if bearish_setup_type is not None:
            candidate = self._evaluate_bearish_candidate(
                symbol=symbol,
                setup_type=bearish_setup_type,
                related_level=bear_related_level,
                mtf_ctx=mtf_ctx,
                m15_candles=m15_candles,
                m15_events=m15_events,
                active_fvgs=active_bearish_fvgs,
                active_obs=active_bearish_obs,
                is_in_killzone=is_in_killzone,
                struct_state=struct_state
            )
            if candidate:
                candidates.append(candidate)

        # Modular Pattern Confluence Hook
        pat_cands = self._evaluate_patterns_hook(
            symbol=symbol,
            mtf_ctx=mtf_ctx,
            m15_candles=m15_candles,
            active_obs=active_bullish_obs + active_bearish_obs,
            active_fvgs=active_bullish_fvgs + active_bearish_fvgs,
            struct_state=struct_state,
            is_in_killzone=is_in_killzone
        )
        if pat_cands:
            candidates.extend(pat_cands)

        return candidates

    def _evaluate_patterns_hook(
        self,
        symbol: str,
        mtf_ctx: MultiTimeframeContext,
        m15_candles: List[Candle],
        active_obs: List[OrderBlock],
        active_fvgs: List[FairValueGap],
        struct_state: Optional[StructureStateSnapshot],
        is_in_killzone: bool
    ) -> List[SignalCandidate]:
        if getattr(self, "execution_mode", None) in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION):
            return []
        if self.pattern_adapter is None:
            try:
                from src.patterns.integration import PatternIntegrationAdapter
                self.pattern_adapter = PatternIntegrationAdapter()
            except Exception:
                return []
        if not self.pattern_adapter.is_enabled:
            return []

        htf_bias = (
            'BULLISH' if mtf_ctx.h4.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]
            else 'BEARISH' if mtf_ctx.h4.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH]
            else 'RANGING'
        )
        liq_levels = {}
        if mtf_ctx.levels:
            liq_levels = {
                'pwh': mtf_ctx.levels.pwh,
                'pwl': mtf_ctx.levels.pwl,
                'pdh': mtf_ctx.levels.pdh,
                'pdl': mtf_ctx.levels.pdl
            }
        return self.pattern_adapter.evaluate_symbol_patterns(
            symbol=symbol,
            m15_candles=m15_candles,
            mtf_bias=htf_bias,
            active_obs=active_obs,
            active_fvgs=active_fvgs,
            liquidity_levels=liq_levels,
            struct_state=struct_state,
            is_in_killzone=is_in_killzone,
            news_safe=True,
            min_rr=self.min_rr
        )

    @staticmethod
    def _select_best_bullish_target(
        entry_price: float,
        sl_distance: float,
        min_rr: float,
        mtf_ctx: MultiTimeframeContext,
        swing_highs: List[Tuple[int, Candle]],
        tp_requires_liquidity_pool: bool = True,
    ) -> Tuple[float, bool]:
        """
        Selects the next logical Buy-Side Liquidity pool (PDH, PWH, M15/H1/H4 swing high) (R4, R8).
        Returns (target_price, anchored_to_liquidity_pool).
        """
        pool_candidates: List[float] = []
        if mtf_ctx.levels:
            if mtf_ctx.levels.pdh > entry_price:
                pool_candidates.append(mtf_ctx.levels.pdh)
            if mtf_ctx.levels.pwh > entry_price:
                pool_candidates.append(mtf_ctx.levels.pwh)
        for tf_obj in (mtf_ctx.m15, mtf_ctx.h1, mtf_ctx.h4, mtf_ctx.d1):
            sh_val = getattr(tf_obj, "swing_high", None)
            if sh_val and sh_val > entry_price:
                pool_candidates.append(float(sh_val))
        for _, c in swing_highs:
            if c.high > entry_price:
                pool_candidates.append(c.high)

        pool_candidates = sorted(set(pool_candidates))
        # Prefer the nearest liquidity pool that satisfies min_rr
        valid_pools = [p for p in pool_candidates if (p - entry_price) / sl_distance >= min_rr - 1e-9]
        if valid_pools:
            return valid_pools[0], True
        # If liquidity pools exist above entry_price but none reaches min_rr:
        if pool_candidates:
            if tp_requires_liquidity_pool:
                # Return the furthest known structural pool so true structural RR is evaluated honestly
                return pool_candidates[-1], True
            return entry_price + (min_rr * sl_distance), False
        # Fallback if no structural pool metadata was populated at all
        if tp_requires_liquidity_pool:
            return entry_price + (min_rr * sl_distance), False
        return entry_price + (min_rr * sl_distance), False

    @staticmethod
    def _select_best_bearish_target(
        entry_price: float,
        sl_distance: float,
        min_rr: float,
        mtf_ctx: MultiTimeframeContext,
        swing_lows: List[Tuple[int, Candle]],
        tp_requires_liquidity_pool: bool = True,
    ) -> Tuple[float, bool]:
        """
        Selects the next logical Sell-Side Liquidity pool (PDL, PWL, M15/H1/H4 swing low) (R4, R8).
        Returns (target_price, anchored_to_liquidity_pool).
        """
        pool_candidates: List[float] = []
        if mtf_ctx.levels:
            if 0 < mtf_ctx.levels.pdl < entry_price:
                pool_candidates.append(mtf_ctx.levels.pdl)
            if 0 < mtf_ctx.levels.pwl < entry_price:
                pool_candidates.append(mtf_ctx.levels.pwl)
        for tf_obj in (mtf_ctx.m15, mtf_ctx.h1, mtf_ctx.h4, mtf_ctx.d1):
            sl_val = getattr(tf_obj, "swing_low", None)
            if sl_val and 0 < sl_val < entry_price:
                pool_candidates.append(float(sl_val))
        for _, c in swing_lows:
            if 0 < c.low < entry_price:
                pool_candidates.append(c.low)

        pool_candidates = sorted(set(pool_candidates), reverse=True)
        valid_pools = [p for p in pool_candidates if (entry_price - p) / sl_distance >= min_rr - 1e-9]
        if valid_pools:
            return valid_pools[0], True
        if pool_candidates:
            if tp_requires_liquidity_pool:
                return pool_candidates[-1], True
            return entry_price - (min_rr * sl_distance), False
        if tp_requires_liquidity_pool:
            return entry_price - (min_rr * sl_distance), False
        return entry_price - (min_rr * sl_distance), False

    def _evaluate_bullish_candidate(
        self,
        symbol: str,
        setup_type: SetupType,
        related_level: str,
        mtf_ctx: MultiTimeframeContext,
        m15_candles: List[Candle],
        m15_events: List,
        active_fvgs: List[FairValueGap],
        active_obs: List[OrderBlock],
        is_in_killzone: bool,
        struct_state: Optional[StructureStateSnapshot] = None
    ) -> Optional[SignalCandidate]:
        current_candle = m15_candles[-1]
        entry_price = current_candle.close

        sh, sl = self.struct_engine.find_swing_points(m15_candles)
        recent_swing_low = sl[-1][1].low if sl else min(c.low for c in m15_candles[-10:])
        sl_buffer = 2.0 * _get_instrument_pip_size(symbol, self.pip_size)
        stop_loss = recent_swing_low - sl_buffer

        best_ob = active_obs[-1] if active_obs else None
        best_fvg = active_fvgs[-1] if active_fvgs else None
        if best_ob and best_ob.low < stop_loss:
            stop_loss = best_ob.low - sl_buffer

        if struct_state and struct_state.state == ConfirmationState.BOS_CONFIRMED and struct_state.direction == CycleDirection.BULLISH:
            if 0 < struct_state.stop_loss_reference < entry_price:
                stop_loss = min(stop_loss, struct_state.stop_loss_reference - sl_buffer)

        sl_distance = entry_price - stop_loss
        if sl_distance <= 0:
            return None

        target_price, _ = self._select_best_bullish_target(
            entry_price=entry_price,
            sl_distance=sl_distance,
            min_rr=self.min_rr,
            mtf_ctx=mtf_ctx,
            swing_highs=sh,
            tp_requires_liquidity_pool=self.tp_requires_liquidity_pool,
        )
        rr = (target_price - entry_price) / sl_distance

        # Structure Confirmation Gating (R3)
        rejection_reasons_init: List[str] = []
        if struct_state and not self.allow_choch_only_entries:
            if struct_state.direction == CycleDirection.BULLISH:
                if struct_state.state == ConfirmationState.CHOCH_WARNING:
                    rejection_reasons_init.append("CHoCH only, awaiting BOS")
                elif struct_state.state == ConfirmationState.PULLBACK:
                    rejection_reasons_init.append("CHoCH pullback in progress, awaiting BOS")
                elif struct_state.state == ConfirmationState.FAILED_TRAP:
                    rejection_reasons_init.append("CHoCH failed - trapped")

        score, reasons, rejection_reasons = self._score_setup(
            direction=OrderType.BUY,
            setup_type=setup_type,
            mtf_ctx=mtf_ctx,
            m15_events=m15_events,
            best_fvg=best_fvg,
            best_ob=best_ob,
            is_in_killzone=is_in_killzone,
            rr=rr,
            struct_state=struct_state,
            entry_price=entry_price,
        )
        rejection_reasons.extend(rejection_reasons_init)

        effective_min_score = _get_instrument_min_score(symbol, self.min_score)
        status = "APPROVED" if score >= effective_min_score and rr >= self.min_rr - 1e-9 and not rejection_reasons else "REJECTED"

        return SignalCandidate(
            id=f"{symbol}_BUY_{current_candle.time.isoformat()}",
            symbol=symbol,
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=setup_type,
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(target_price, 5),
            risk_reward=round(rr, 2),
            score=round(score, 1),
            timestamp=current_candle.time,
            status=status,
            reasons=reasons,
            rejection_reasons=rejection_reasons,
            fvg=best_fvg,
            ob=best_ob,
            related_level=related_level
        )

    def _evaluate_bearish_candidate(
        self,
        symbol: str,
        setup_type: SetupType,
        related_level: str,
        mtf_ctx: MultiTimeframeContext,
        m15_candles: List[Candle],
        m15_events: List,
        active_fvgs: List[FairValueGap],
        active_obs: List[OrderBlock],
        is_in_killzone: bool,
        struct_state: Optional[StructureStateSnapshot] = None
    ) -> Optional[SignalCandidate]:
        current_candle = m15_candles[-1]
        entry_price = current_candle.close

        sh, sl = self.struct_engine.find_swing_points(m15_candles)
        recent_swing_high = sh[-1][1].high if sh else max(c.high for c in m15_candles[-10:])
        sl_buffer = 2.0 * _get_instrument_pip_size(symbol, self.pip_size)
        stop_loss = recent_swing_high + sl_buffer

        best_ob = active_obs[-1] if active_obs else None
        best_fvg = active_fvgs[-1] if active_fvgs else None
        if best_ob and best_ob.high > stop_loss:
            stop_loss = best_ob.high + sl_buffer

        if struct_state and struct_state.state == ConfirmationState.BOS_CONFIRMED and struct_state.direction == CycleDirection.BEARISH:
            if struct_state.stop_loss_reference > entry_price:
                stop_loss = max(stop_loss, struct_state.stop_loss_reference + sl_buffer)

        sl_distance = stop_loss - entry_price
        if sl_distance <= 0:
            return None

        target_price, _ = self._select_best_bearish_target(
            entry_price=entry_price,
            sl_distance=sl_distance,
            min_rr=self.min_rr,
            mtf_ctx=mtf_ctx,
            swing_lows=sl,
            tp_requires_liquidity_pool=self.tp_requires_liquidity_pool,
        )
        rr = (entry_price - target_price) / sl_distance

        # Structure Confirmation Gating (R3)
        rejection_reasons_init: List[str] = []
        if struct_state and not self.allow_choch_only_entries:
            if struct_state.direction == CycleDirection.BEARISH:
                if struct_state.state == ConfirmationState.CHOCH_WARNING:
                    rejection_reasons_init.append("CHoCH only, awaiting BOS")
                elif struct_state.state == ConfirmationState.PULLBACK:
                    rejection_reasons_init.append("CHoCH pullback in progress, awaiting BOS")
                elif struct_state.state == ConfirmationState.FAILED_TRAP:
                    rejection_reasons_init.append("CHoCH failed - trapped")

        score, reasons, rejection_reasons = self._score_setup(
            direction=OrderType.SELL,
            setup_type=setup_type,
            mtf_ctx=mtf_ctx,
            m15_events=m15_events,
            best_fvg=best_fvg,
            best_ob=best_ob,
            is_in_killzone=is_in_killzone,
            rr=rr,
            struct_state=struct_state,
            entry_price=entry_price,
        )
        rejection_reasons.extend(rejection_reasons_init)

        effective_min_score = _get_instrument_min_score(symbol, self.min_score)
        status = "APPROVED" if score >= effective_min_score and rr >= self.min_rr - 1e-9 and not rejection_reasons else "REJECTED"

        return SignalCandidate(
            id=f"{symbol}_SELL_{current_candle.time.isoformat()}",
            symbol=symbol,
            timeframe=Timeframe.M15,
            direction=OrderType.SELL,
            setup_type=setup_type,
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(target_price, 5),
            risk_reward=round(rr, 2),
            score=round(score, 1),
            timestamp=current_candle.time,
            status=status,
            reasons=reasons,
            rejection_reasons=rejection_reasons,
            fvg=best_fvg,
            ob=best_ob,
            related_level=related_level
        )

    def _score_setup(
        self,
        direction: OrderType,
        setup_type: SetupType,
        mtf_ctx: MultiTimeframeContext,
        m15_events: List,
        best_fvg: Optional[FairValueGap],
        best_ob: Optional[OrderBlock],
        is_in_killzone: bool,
        rr: float,
        struct_state: Optional[StructureStateSnapshot] = None,
        entry_price: float = 0.0,
    ) -> Tuple[float, List[str], List[str]]:
        """
        Calculates confluence score (0-100) and checks hard disqualifiers (R1-R8).
        """
        score = 0.0
        reasons: List[str] = []
        rejection_reasons: List[str] = []

        is_bullish = direction == OrderType.BUY

        # 1. Weekly Alignment (15 pts)
        w1_aligned = (is_bullish and mtf_ctx.w1.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]) or \
                     (not is_bullish and mtf_ctx.w1.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
        if w1_aligned:
            score += 15
            reasons.append("W1 trend aligned (+15)")
        elif setup_type in [SetupType.WEEKLY_REVERSAL, SetupType.DAILY_REVERSAL]:
            score += 10
            reasons.append("Reversal at key liquidity boundary (+10)")

        # 2. Daily Alignment (15 pts)
        d1_aligned = (is_bullish and mtf_ctx.d1.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]) or \
                     (not is_bullish and mtf_ctx.d1.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
        if d1_aligned:
            score += 15
            reasons.append("D1 directional bias aligned (+15)")

        # 3. H4 Primary Trend (15 pts)
        h4_aligned = (is_bullish and mtf_ctx.h4.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]) or \
                     (not is_bullish and mtf_ctx.h4.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
        if h4_aligned:
            score += 15
            reasons.append("H4 primary trend aligned (+15)")

        # 4. H1 Confluence (10 pts)
        h1_aligned = (is_bullish and mtf_ctx.h1.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH]) or \
                     (not is_bullish and mtf_ctx.h1.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
        if h1_aligned:
            score += 10
            reasons.append("H1 confluence aligned (+10)")

        # 5. M15 Structure Confirmation (BOS / MSS by candle body close) (15 pts) (R2, R3)
        bos_or_mss = any(
            e.direction == direction and e.event_type in [MarketStructureType.BOS, MarketStructureType.MSS]
            for e in m15_events
        )
        choch_only = any(
            e.direction == direction and e.event_type == MarketStructureType.CHOCH
            for e in m15_events
        )
        state_bos_confirmed = (
            struct_state is not None
            and struct_state.state == ConfirmationState.BOS_CONFIRMED
            and (
                (is_bullish and struct_state.direction == CycleDirection.BULLISH)
                or (not is_bullish and struct_state.direction == CycleDirection.BEARISH)
            )
        )
        if bos_or_mss or state_bos_confirmed:
            score += 15
            reasons.append("M15 BOS/MSS confirmed by candle body close (+15)")
        elif choch_only and self.allow_choch_only_entries:
            score += 10
            reasons.append("M15 CHoCH warning present (+10)")
        else:
            reasons.append("M15 structure unconfirmed (0)")

        # 6. Liquidity Sweep Interaction (10 pts) (R4)
        has_sweep = any("SWEEP" in res.interaction.value for res in mtf_ctx.level_interactions)
        if has_sweep or setup_type in [SetupType.WEEKLY_REVERSAL, SetupType.DAILY_REVERSAL, SetupType.SESSION_SWEEP]:
            score += 10
            reasons.append("Liquidity sweep confirmed with rejection (+10)")

        # 7. FVG Quality (10 pts) & OB Quality (up to 7 pts) + OB+FVG Confluence Bonus (R5, R6)
        if best_fvg:
            score += 10
            fvg_label = "IFVG (Inverse FVG)" if getattr(best_fvg, "is_inverse", False) else "FVG"
            reasons.append(f"Valid M15 {fvg_label} imbalance present ({best_fvg.id}) (+10)")

        if best_ob:
            ob_base = 3.0
            ob_bonus = min(4.0, round(getattr(best_ob, "strength_score", 1.0) * 4.0, 1))
            ob_pts = ob_base + ob_bonus
            score += ob_pts
            reasons.append(f"Order Block ({best_ob.id}) strength={getattr(best_ob, 'strength_score', 1.0):.2f} (+{ob_pts:.1f})")

        # R6: OB + FVG spatial confluence bonus (+5 pts)
        if FvgObEngine.has_ob_fvg_confluence(best_ob, best_fvg, tolerance=5.0 * self.pip_size):
            score += 5.0
            reasons.append("OB + FVG spatial confluence (+5)")

        # 8. Premium / Discount Zone Alignment (R7) (+5 pts)
        in_correct_pd_zone = (
            (is_bullish and (mtf_ctx.m15.is_discount or mtf_ctx.h1.is_discount or mtf_ctx.h4.is_discount))
            or (not is_bullish and (mtf_ctx.m15.is_premium or mtf_ctx.h1.is_premium or mtf_ctx.h4.is_premium))
        )
        if in_correct_pd_zone:
            score += 5.0
            zone_name = "Discount (<50%)" if is_bullish else "Premium (>50%)"
            reasons.append(f"Entry aligned with {zone_name} equilibrium zone (+5)")

        # 9. Session / Killzone (5 pts)
        if is_in_killzone:
            score += 5
            reasons.append("Formed within London or New York Kill Zone (+5)")

        # 10. Higher-Timeframe Conflict Check (protect against trading into opposing H4+D1 trend)
        h4_opposes = (
            (is_bullish and mtf_ctx.h4.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
            or (not is_bullish and mtf_ctx.h4.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH])
        )
        d1_opposes = (
            (is_bullish and mtf_ctx.d1.trend in [TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH])
            or (not is_bullish and mtf_ctx.d1.trend in [TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH])
        )
        if setup_type not in [SetupType.WEEKLY_REVERSAL, SetupType.DAILY_REVERSAL] and h4_opposes and d1_opposes:
            rejection_reasons.append(
                f"HTF_CONFLICT: Higher-timeframe bias (D1={mtf_ctx.d1.trend.value}, H4={mtf_ctx.h4.trend.value}) opposes {direction.value} setup"
            )

        # Alignment Score contribution (up to 5 pts)
        alignment_score = getattr(mtf_ctx, "alignment_score", 0.0)
        if alignment_score >= 80.0:
            score += 5
            reasons.append(f"High MTF alignment score ({alignment_score:.1f}%) (+5)")
        elif alignment_score >= 60.0:
            score += 2
            reasons.append(f"Moderate MTF alignment score ({alignment_score:.1f}%) (+2)")

        # Mandatory Hard Filters
        if rr < self.min_rr - 1e-9:
            rejection_reasons.append(f"Reward-to-risk {rr:.2f} is below mandatory threshold {self.min_rr:.2f}")

        effective_min_score = _get_instrument_min_score(getattr(mtf_ctx, "symbol", "UNKNOWN"), self.min_score)
        if score < effective_min_score:
            rejection_reasons.append(f"Confluence score {score:.1f} is below minimum {effective_min_score:.1f}")

        return min(100.0, score), reasons, rejection_reasons

    def _detect_recent_swing_sweep(self, candles: List[Candle]) -> Tuple[bool, bool]:
        """
        Detects whether recent closed candles swept prior M15 swing low (SSL sweep -> bullish)
        or prior M15 swing high (BSL sweep -> bearish) and rejected back inside range (R4).
        Returns (ssl_swept_bullish, bsl_swept_bearish).
        """
        if len(candles) < 15:
            return False, False
        prior = candles[:-3]
        recent = candles[-3:]
        prior_low = min(c.low for c in prior[-20:])
        prior_high = max(c.high for c in prior[-20:])
        ssl_sweep = any(c.low < prior_low and c.close > prior_low for c in recent) or (
            min(c.low for c in recent) < prior_low and recent[-1].close > prior_low
        )
        bsl_sweep = any(c.high > prior_high and c.close < prior_high for c in recent) or (
            max(c.high for c in recent) > prior_high and recent[-1].close < prior_high
        )
        return ssl_sweep, bsl_sweep

    @staticmethod
    def calculate_atr(candles: List[Candle], period: int = 14) -> float:
        """Calculates Average True Range (ATR) on closed candles."""
        if not candles:
            return 0.0
        if len(candles) < 2:
            return candles[-1].range
        trs: List[float] = []
        for i in range(1, len(candles)):
            h = candles[i].high
            l = candles[i].low
            pc = candles[i - 1].close
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window) if window else 0.0

    @staticmethod
    def calculate_adx(candles: List[Candle], period: int = 14) -> float:
        """Calculates Average Directional Index (ADX) on closed candles."""
        if len(candles) < period + 2:
            return 20.0
        plus_dm_list: List[float] = []
        minus_dm_list: List[float] = []
        tr_list: List[float] = []
        for i in range(1, len(candles)):
            up_move = candles[i].high - candles[i - 1].high
            down_move = candles[i - 1].low - candles[i].low
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low - candles[i - 1].close),
            )
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            tr_list.append(tr)
        dx_values: List[float] = []
        start_idx = max(0, len(tr_list) - period * 2)
        for j in range(start_idx + period, len(tr_list) + 1):
            tr_sum = sum(tr_list[j - period : j])
            if tr_sum <= 1e-12:
                continue
            p_di = 100.0 * sum(plus_dm_list[j - period : j]) / tr_sum
            m_di = 100.0 * sum(minus_dm_list[j - period : j]) / tr_sum
            denom = p_di + m_di
            if denom > 1e-12:
                dx_values.append(100.0 * abs(p_di - m_di) / denom)
        return sum(dx_values[-period:]) / len(dx_values[-period:]) if dx_values else 20.0
