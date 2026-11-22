"""
Order Execution Manager and Reconciliation Engine.
Executes the mandatory Pre-Trade Checklist, validates broker responses,
monitors slippage, prevents duplicate orders, and handles simulation mode.
Enforces SMC Rulebook R9:
- Hard cap risk per trade at 2.0% regardless of config (default 1.0%).
- Reject any order without a stop loss (stop_loss <= 0).
- Reject any stop-loss modification that widens risk (moves SL further away).
"""

from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.contracts import (
    Candle, SignalCandidate, TradeOrder, Position, AccountInfo, SymbolInfo,
    OrderType, ExecutionMode, TradePlan, PlanAmendment, ProfitManagementMode, SetupType
)
from src.core.config import AppConfig
from src.risk.position_sizing import PositionSizingEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.replay_gate import MonteCarloReplayGate
from src.execution.bridge_client import BridgeClient
from src.execution.analytics.tca import TCAEngine
from src.execution.transaction_manager import TransactionManager, TransactionRecord

logger = logging.getLogger("OrderManager")


@dataclass
class PreTradeCheckResult:
    passed: bool
    rejection_reasons: List[str] = field(default_factory=list)
    calculated_volume: float = 0.0
    monetary_risk: float = 0.0
    trade_plan: Optional[TradePlan] = None


class OrderManager:
    def __init__(
        self,
        config: AppConfig,
        bridge: BridgeClient,
        sizing_engine: PositionSizingEngine,
        portfolio_risk: PortfolioRiskEngine,
        transaction_manager: Optional[TransactionManager] = None
    ):
        self.config = config
        self.bridge = bridge
        self.sizing = sizing_engine
        self.portfolio_risk = portfolio_risk
        self.tca = TCAEngine(enabled=True)
        self.transaction_manager = transaction_manager or TransactionManager(
            ledger_file=getattr(config, "transaction_ledger_file", "data/order_transactions.json")
        )
        self.simulated_positions: List[Position] = []
        self._sim_ticket_counter = 500000
        self._executed_signal_ids: Set[str] = set()
        self._active_trade_plans: Dict[int, TradePlan] = {}
        self._signal_trade_plans: Dict[str, TradePlan] = {}
        self.replay_gate = MonteCarloReplayGate(enabled=getattr(self.config.risk, "enable_replay_gate", False))
        self.telegram_cmd_handler: Optional[Any] = None
        self.shadow_journal: Optional[Any] = None
        self.session_engine = None
        self.affinity_engine = None
        self.session_risk = None
        self.fast_risk_guard = None
        self.fast_watchdog = None
        self.fast_exit_manager = None
        try:
            from src.core.sessions import TradingSessionEngine
            from src.core.session_affinity import SessionAffinityEngine
            from src.risk.session_risk import SessionRiskEngine
            self.session_engine = TradingSessionEngine(self.config.session)
            self.affinity_engine = SessionAffinityEngine()
            self.session_risk = SessionRiskEngine()
        except Exception:
            pass
        try:
            from src.risk.fast_risk_guard import FastRiskGuardEngine
            from src.execution.watchdog import FastWatchdog
            from src.execution.fast_exit_manager import FastTickExitManager
            self.fast_risk_guard = FastRiskGuardEngine()
            self.fast_watchdog = FastWatchdog()
            self.fast_exit_manager = FastTickExitManager()
        except Exception:
            pass

    @staticmethod
    def validate_sl_modification(
        direction: OrderType,
        current_sl: float,
        new_sl: float
    ) -> Tuple[bool, str]:
        """
        Rule R9.3: NEVER move a stop further away (widen risk).
        Moving to breakeven / trailing in the profitable direction remains allowed.
        """
        if new_sl <= 0:
            return False, "R9.2/R9.3 violation: Cannot remove stop loss (new_sl <= 0)."
        if current_sl <= 0:
            return True, "Setting initial stop loss."

        is_buy = direction in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        if is_buy:
            if new_sl < current_sl - 1e-9:
                return (
                    False,
                    f"R9.3 violation: Refusing to widen BUY stop loss from {current_sl:.5f} to {new_sl:.5f}.",
                )
        else:
            if new_sl > current_sl + 1e-9:
                return (
                    False,
                    f"R9.3 violation: Refusing to widen SELL stop loss from {current_sl:.5f} to {new_sl:.5f}.",
                )
        return True, "SL modification tightens or preserves risk."

    def run_pre_trade_checklist(
        self,
        candidate: SignalCandidate,
        account: AccountInfo,
        symbol_info: SymbolInfo,
        active_positions: List[Position],
        recent_candles: Optional[List[Candle]] = None
    ) -> PreTradeCheckResult:
        """
        Executes strict Pre-Trade Validation Checklist including R9 Risk Rules.
        """
        rejections: List[str] = []

        # 0. Strict Three-Symbol Universe & Schedule Pre-Checks
        if getattr(self.config, "strict_three_symbol_universe", False):
            from src.core.symbol_universe import get_symbol_universe
            universe = get_symbol_universe()
            is_approved, canonical = universe.validate_or_reject(candidate.symbol)
            if not is_approved:
                rejections.append(
                    f"Pre-check failed (Universe Restriction): Symbol {candidate.symbol} is outside the approved 3-instrument universe [XAUUSD, BTCUSD, USDJPY]."
                )
            else:
                from src.core.trading_schedule import get_trading_schedule
                schedule = get_trading_schedule(getattr(self.config, "weekday_btc_fallback_enabled", False))
                check_dt = candidate.timestamp if candidate.timestamp else datetime.now(timezone.utc)
                eligible, sched_reason = schedule.is_instrument_eligible_for_new_entry(candidate.symbol, check_dt)
                if not eligible:
                    rejections.append(f"Pre-check failed (Schedule Mode): {sched_reason}")

        # 1. Is MT5 connection healthy? (In live/demo mode)
        if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL]:
            if not self.bridge.ping():
                rejections.append("Pre-check failed: MT5 bridge connection unhealthy or unreachable.")
            elif hasattr(self.bridge, "check_symbol_session"):
                try:
                    sess_res = self.bridge.check_symbol_session(candidate.symbol)
                    if isinstance(sess_res, dict) and sess_res.get("status") == "SUCCESS" and sess_res.get("market_open") is False:
                        rejections.append(
                            f"Pre-check failed (Market Closed): {sess_res.get('reason', 'Outside broker trading session')} [retcode 10018]"
                        )
                except Exception as sess_exc:
                    logger.debug(f"[ORDER_MANAGER] Symbol session check skipped for {candidate.symbol}: {sess_exc}")

        # 2. Is signal approved and valid?
        if candidate.status != "APPROVED":
            rejections.append(f"Pre-check failed: Signal candidate is {candidate.status}.")

        # 3. Is stop loss & direction valid? (R9.2: Always use a stop loss)
        if candidate.stop_loss <= 0:
            rejections.append("Pre-check failed (R9.2): Stop loss is required (stop_loss <= 0).")

        sl_distance = abs(candidate.entry_price - candidate.stop_loss)
        if sl_distance <= 0:
            rejections.append("Pre-check failed: Stop loss distance is zero or negative.")

        # 3b. Broker stops_level and freeze_level validation
        stops_pts = max(int(getattr(symbol_info, "stops_level", 0)), int(getattr(symbol_info, "freeze_level", 0)))
        pt_spec = float(symbol_info.point) if getattr(symbol_info, "point", 0) > 0 else 0.00001
        if stops_pts > 0 and pt_spec > 0:
            min_stop_distance = stops_pts * pt_spec
            if sl_distance < min_stop_distance - 1e-9:
                rejections.append(
                    f"Pre-check failed: Stop loss distance ({sl_distance:.5f}) is closer than broker stops_level ({min_stop_distance:.5f})."
                )

        if candidate.direction in [OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP]:
            if candidate.stop_loss > 0 and candidate.stop_loss >= candidate.entry_price:
                rejections.append(f"Pre-check failed: Invalid stops on BUY - SL ({candidate.stop_loss}) must be below entry ({candidate.entry_price}).")
            if candidate.take_profit > 0 and candidate.take_profit <= candidate.entry_price:
                rejections.append(f"Pre-check failed: Invalid stops on BUY - TP ({candidate.take_profit}) must be above entry ({candidate.entry_price}).")
        elif candidate.direction in [OrderType.SELL, OrderType.SELL_LIMIT, OrderType.SELL_STOP]:
            if candidate.stop_loss > 0 and candidate.stop_loss <= candidate.entry_price:
                rejections.append(f"Pre-check failed: Invalid stops on SELL - SL ({candidate.stop_loss}) must be above entry ({candidate.entry_price}).")
            if candidate.take_profit > 0 and candidate.take_profit >= candidate.entry_price:
                rejections.append(f"Pre-check failed: Invalid stops on SELL - TP ({candidate.take_profit}) must be below entry ({candidate.entry_price}).")

        # 4. Spread friction recording (Telemetric cost measurement, non-blocking)
        spread_pts = float(symbol_info.spread)
        pt = float(symbol_info.point) if symbol_info.point > 0 else 0.01
        sl_dist_pts = sl_distance / pt if pt > 0 else sl_distance
        is_scalp_signal = str(getattr(candidate, "id", "")).startswith("SCALP_")
        if self.config.execution_mode not in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION):
            if symbol_info.ask <= 0 or symbol_info.bid <= 0 or symbol_info.ask < symbol_info.bid:
                rejections.append(
                    f"MARKET_DATA_UNAVAILABLE: Invalid bid/ask quote for {symbol_info.symbol} "
                    f"(bid={symbol_info.bid}, ask={symbol_info.ask})."
                )

        if not hasattr(candidate, "metadata") or not isinstance(candidate.metadata, dict):
            candidate.metadata = {}
        candidate.metadata["spread_pts"] = spread_pts
        spread_pct_sl = (spread_pts / sl_dist_pts * 100.0) if sl_dist_pts > 0 else 0.0
        candidate.metadata["spread_pct_sl"] = round(spread_pct_sl, 2)
        logger.info(f"[INFO] [SPREAD_ENGINE] Strategy-level spread rejection is disabled. Spread retained for diagnostics: {spread_pts:.1f} pts ({spread_pct_sl:.1f}% of SL).")

        # 5. Position sizing and volume verification (R9.1: hard cap 2.0% risk per trade)
        requested_risk_pct = min(2.0, float(getattr(self.config.risk, "risk_percentage", 1.0)))
        if float(getattr(self.config.risk, "risk_percentage", 1.0)) > 2.0:
            rejections.append(
                f"Pre-check failed (R9.1): Configured risk_percentage ({self.config.risk.risk_percentage:.2f}%) exceeds 2.0% hard cap."
            )

        kelly_pct = getattr(candidate, "metadata", {}).get("kelly_risk_pct") if hasattr(candidate, "metadata") else None
        vol_scale = None
        if hasattr(candidate, "metadata") and isinstance(candidate.metadata, dict):
            vf = candidate.metadata.get("volatility_forecast")
            if isinstance(vf, dict):
                vol_scale = vf.get("recommended_size_scale")

        atr_m15 = 0.0
        if recent_candles and len(recent_candles) >= 15:
            from src.core.volatility import VolatilityEngine
            vol_eng = VolatilityEngine(atr_period=14)
            atr_m15 = vol_eng.calculate_atr(recent_candles)
        elif hasattr(self, "market_data") and self.market_data:
            try:
                m15_candles = self.market_data.get_candles(candidate.symbol, Timeframe.M15)
                if m15_candles and len(m15_candles) >= 15:
                    from src.core.volatility import VolatilityEngine
                    vol_eng = VolatilityEngine(atr_period=14)
                    atr_m15 = vol_eng.calculate_atr(m15_candles)
            except Exception:
                pass

        if atr_m15 <= 0.0 and hasattr(candidate, "metadata") and isinstance(candidate.metadata, dict):
            atr_m15 = float(candidate.metadata.get("atr_m15") or candidate.metadata.get("atr") or 0.0)

        if atr_m15 <= 0.0:
            atr_m15 = max(sl_distance * 0.8, 10.0 * pt)

        min_rr_allowed = float(getattr(self.config.risk, "scalping_min_risk_reward_ratio", 1.2)) if is_scalp_signal else float(getattr(self.config.risk, "min_risk_reward_ratio", 1.5))
        if getattr(candidate, "risk_reward", 0.0) > 0:
            min_rr_allowed = min(min_rr_allowed, float(candidate.risk_reward))

        size_result = self.sizing.calculate_lot_size(
            account=account,
            symbol_info=symbol_info,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            order_type=candidate.direction,
            risk_percent=requested_risk_pct,
            sizing_reference=self.config.risk.sizing_reference,
            adaptive_scalping=is_scalp_signal and (getattr(self.config, "risk_profile", "") == "ADAPTIVE_SCALPING"),
            min_rr_override=min_rr_allowed,
            kelly_risk_pct=kelly_pct,
            volatility_scale=vol_scale,
            atr_m15=atr_m15,
            target_net_usd=float(getattr(self.config.risk, "target_net_profit_usd", 20.0)),
        )
        if size_result.reward_to_risk > 0:
            candidate.risk_reward = size_result.reward_to_risk
        if size_result.target_price_20usd and (candidate.take_profit is None or candidate.take_profit <= 0):
            candidate.take_profit = size_result.target_price_20usd

        # Intelligent Dual-Mode Classification (QUICK_SCALP vs PROFIT_RUNNING)
        try:
            from src.risk.mode_selector import ModeSelectionEngine
            sel_mode, mode_rat, _ = ModeSelectionEngine.classify_trade_opportunity(
                candidate=candidate,
                symbol_info=symbol_info,
                recent_candles=recent_candles,
                min_rr_for_hold=float(getattr(self.config.risk, "min_risk_reward_ratio", 2.0)),
                min_score_for_hold=float(getattr(self.config.strategy, "min_confluence_score", 75.0)),
                execution_mode_policy=str(getattr(self.config.strategy, "execution_mode_policy", "ADAPTIVE")),
            )
            candidate.profit_mode = sel_mode
            if hasattr(candidate, "execution_mode_selected"):
                candidate.execution_mode_selected = sel_mode.canonical_mode
            if not hasattr(candidate, "metadata") or not isinstance(candidate.metadata, dict):
                candidate.metadata = {}
            candidate.metadata["profit_mode"] = sel_mode.value
            candidate.metadata["management_mode"] = sel_mode.canonical_mode
            candidate.metadata["mode_rationale"] = mode_rat
        except Exception as e:
            logger.debug(f"Mode selection classification fallback: {e}")

        if not size_result.is_approved:
            rejections.append(f"Pre-check failed (Sizing): {size_result.rejection_reason}")
        elif size_result.risk_percent_actual > 2.0 + 1e-4:
            rejections.append(
                f"Pre-check failed (R9.1): Actual trade risk ({size_result.risk_percent_actual:.2f}%) exceeds 2.0% hard cap."
            )
        elif size_result.feasibility and not size_result.feasibility.is_feasible:
            feas_rej = size_result.feasibility.rejection_reason or ""
            # Only enforce target feasibility as a pre-check rejection if it specifically violates R9 risk limits
            if "Rule R9" in feas_rej and "hard cap" in feas_rej:
                rejections.append(f"Pre-check failed (Target Feasibility): {feas_rej}")

        # 6. Portfolio Capacity & Aggregate Risk Controls (Replacing Portfolio Risk Veto)
        # Margin level verification (>= 150.0%)
        if getattr(account, "margin", 0.0) > 0 and getattr(account, "equity", 0.0) > 0:
            margin_level = (account.equity / account.margin) * 100.0
            if margin_level < 150.0:
                logger.warning(f"[WARNING] [MARGIN_MANAGER] Order cannot proceed because available margin is insufficient ({margin_level:.1f}% < 150.0%).")
                rejections.append(f"Pre-check failed: Margin level critical ({margin_level:.1f}% < 150.0% min requirement).")

        # Arbitrary position-count limits disabled: opportunity-driven multi-position execution
        logger.info(
            f"[POSITION_MANAGER] Arbitrary position-count restrictions are disabled. "
            f"Active positions: {len(active_positions)}. Multiple concurrent positions are supported."
        )

        # Maximum aggregate open risk cap (8.0% hard ceiling)
        max_agg_risk_pct = float(getattr(self.config.risk, "max_aggregate_risk_percent", 8.0))
        active_monetary_risk = sum(float(getattr(p, "initial_risk_amount", 0.0) or 0.0) for p in active_positions)
        total_risk_proposed = active_monetary_risk + size_result.monetary_risk
        if getattr(account, "equity", 0.0) > 0:
            agg_risk_pct = (total_risk_proposed / account.equity) * 100.0
            if agg_risk_pct > max_agg_risk_pct:
                rejections.append(f"Pre-check failed: Aggregate open risk ({agg_risk_pct:.2f}%) exceeds maximum limit ({max_agg_risk_pct:.2f}%).")

        # Telemetry recording of portfolio risk evaluation (non-blocking for independent setups)
        try:
            allowed, risk_reason = self.portfolio_risk.evaluate_new_order_permission(
                candidate=candidate,
                account=account,
                active_positions=active_positions,
                proposed_monetary_risk=size_result.monetary_risk,
                proposed_volume=size_result.volume
            )
            candidate.metadata["portfolio_risk_eval"] = {"allowed": allowed, "reason": risk_reason}
        except Exception as e:
            logger.debug(f"Portfolio risk telemetry error: {e}")

        # 7. Duplicate order / signal prevention
        if candidate.id in self._executed_signal_ids:
            rejections.append(f"Pre-check failed: Signal ID {candidate.id} was already executed.")

        # 8. Duplicate conflicting position check
        for p in active_positions:
            if p.symbol == candidate.symbol and p.order_type != candidate.direction:
                rejections.append(f"Pre-check failed: Conflicting active position on {candidate.symbol}.")

        # 9. Is setup still available? Entry Quality Guard [Configurable]
        legacy_filters_enabled = getattr(self.config, "legacy_filters_enabled", False)
        anti_chase_enabled = getattr(self.config.risk, "anti_chasing_filter_enabled", False)
        strict_rr_enabled = getattr(self.config.risk, "strict_entry_quality_enabled", False)
        if legacy_filters_enabled and (anti_chase_enabled or strict_rr_enabled) and self.config.execution_mode not in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION):
            live_fill_price = symbol_info.ask if candidate.direction == OrderType.BUY else symbol_info.bid
            is_price_in_sync = (
                candidate.entry_price <= 0
                or abs(live_fill_price - candidate.entry_price) / max(candidate.entry_price, 1e-5) < 0.05
            )
            if live_fill_price > 0 and candidate.stop_loss > 0 and candidate.take_profit > 0 and is_price_in_sync:
                live_risk = abs(live_fill_price - candidate.stop_loss)
                if anti_chase_enabled:
                    trigger_ref = candidate.entry_price or live_fill_price
                    drift = abs(live_fill_price - trigger_ref)
                    max_drift = live_risk * 1.0  # [ASSUMPTION: 1.0 x planned risk]
                    if drift > max_drift:
                        rejections.append(
                            f"Pre-check failed (Anti-Chasing V14): Price drifted {drift:.5f} > max extension {max_drift:.5f} from trigger. Don't chase [VIDEO 14]."
                        )
        elif legacy_filters_enabled and self.config.execution_mode not in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION):
            deviation = abs(symbol_info.ask - candidate.entry_price) if candidate.direction == OrderType.BUY else abs(symbol_info.bid - candidate.entry_price)
            max_dev = max(5.0 * symbol_info.point * 10, sl_distance * 0.35) if is_scalp_signal else (5.0 * symbol_info.point * 10)
            if deviation > max_dev and symbol_info.ask > 0 and (abs(symbol_info.ask - candidate.entry_price) / max(candidate.entry_price, 1e-5) < 0.05):
                rejections.append(f"Pre-check failed: Price drifted {deviation/symbol_info.point:.1f} points away from entry.")

        # 10. Margin sufficiency
        if size_result.margin_required > account.free_margin:
            rejections.append("Pre-check failed: Free margin insufficient.")

        # 11. Structure Confirmation (BOS after CHoCH)
        allow_choch_only = getattr(self.config.strategy, "allow_choch_only_entries", True)
        if legacy_filters_enabled and not allow_choch_only and hasattr(candidate, "rejection_reasons"):
            for r in candidate.rejection_reasons:
                if "CHoCH only" in r or "trapped" in r or "awaiting BOS" in r:
                    rejections.append(f"Pre-check failed (Structure): Structure confirmed (BOS after CHoCH) check failed: {r}")

        # 12. Replay Gate passed
        if legacy_filters_enabled and self.replay_gate and self.replay_gate.enabled and recent_candles:
            temp_plan = TradePlan(
                plan_id=f"PLAN_{candidate.id}",
                symbol=candidate.symbol,
                direction=candidate.direction,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                lots=size_result.volume,
                risk_percent=size_result.risk_percent_actual,
                reward_to_risk=candidate.risk_reward,
                structure_state="BOS_CONFIRMED",
                timestamp=datetime.now(timezone.utc)
            )
            replay_res = self.replay_gate.evaluate_plan(
                plan=temp_plan,
                recent_candles=recent_candles,
                spread_pts=float(symbol_info.spread),
                point=float(symbol_info.point) if symbol_info.point > 0 else 0.00001
            )
            if not replay_res.passed:
                rejections.append(f"Pre-check failed (Replay Gate): {replay_res.rejection_reason}")

        # 13-16. Session-Aware Pre-Trade Checklist Items
        session_enabled = False
        sess_info = None
        if self.session_engine and hasattr(self.session_engine, "_raw_cfg"):
            session_enabled = bool(self.session_engine._raw_cfg.get("enabled", True))

        if legacy_filters_enabled and session_enabled and self.session_engine and self.affinity_engine and self.session_risk:
            from src.core.contracts import SessionType
            broker_offset_ok = getattr(self.bridge, "broker_utc_offset", 0) != 0 or not self.session_engine.require_verified_offset
            if self.config.execution_mode in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION):
                broker_offset_ok = True

            sess_dt = candidate.timestamp if candidate.timestamp else datetime.now(timezone.utc)
            sess_info = self.session_engine.get_session_info(
                current_dt=sess_dt,
                broker_offset_verified=broker_offset_ok
            )

            # Checklist Item #13: Session active (Weekend check - Crypto trades 24/7)
            is_crypto = any(c in candidate.symbol.upper() for c in ("BTC", "ETH", "CRYPTO"))
            if sess_info.primary_session == SessionType.WEEKEND and not is_crypto:
                if getattr(self.config.risk, "no_weekend_holding", True):
                    rejections.append(f"Pre-check failed (Session active): Weekend market closure active ({sess_info.primary_session.value})")

            # Checklist Item #14: Symbol allowed for session (Affinity check - Configurable)
            enforce_affinity = getattr(self.config.strategy, "enforce_session_affinity", False)
            if enforce_affinity:
                allowed_aff, aff_weight, aff_reason = self.affinity_engine.is_symbol_allowed(
                    session=sess_info.primary_session,
                    raw_symbol=candidate.symbol,
                    dt_utc=sess_dt
                )
                if not allowed_aff:
                    rejections.append(f"Pre-check failed (Symbol allowed for session): {aff_reason}")

            # Checklist Item #15: Not in handover/rollover/blackout (Configurable)
            enforce_handover = getattr(self.config.strategy, "enforce_handover_cooldown", False)
            if sess_info.is_rollover_blackout:
                rejections.append("Pre-check failed (Not in handover/rollover/blackout): Daily swap rollover blackout active")
            elif enforce_handover and sess_info.is_handover_cooldown:
                rejections.append(f"Pre-check failed (Not in handover/rollover/blackout): {sess_info.rejection_reason}")

            # Checklist Item #16: Session trade and loss caps OK
            allowed_risk, s_mult, s_reason = self.session_risk.evaluate_session_risk_permission(
                candidate=candidate,
                active_session=sess_info.primary_session,
                account=account,
                active_positions=active_positions
            )
            if not allowed_risk:
                rejections.append(f"Pre-check failed (Session trade and loss caps OK): {s_reason}")

        # 17-19. Fast Mode Speed & Reliability Guardrails (when Fast Mode is enabled or FAST_SCALP setup)
        fast_enabled = bool(self.fast_risk_guard and self.fast_risk_guard._cfg.get("enabled", False))
        if legacy_filters_enabled and (fast_enabled or getattr(candidate, "setup_type", None) == SetupType.FAST_SCALP):
            if self.fast_watchdog:
                wd_ok, wd_reason = self.fast_watchdog.can_open_new_trade(
                    symbol_info=symbol_info,
                    now_utc=candidate.timestamp
                )
                if not wd_ok:
                    rejections.append(f"Pre-check failed (Fast Watchdog): {wd_reason}")
            if self.fast_risk_guard:
                fg_ok, fg_reason = self.fast_risk_guard.validate_trade_candidate(
                    candidate=candidate,
                    account=account,
                    symbol_info=symbol_info,
                    active_positions=active_positions,
                    proposed_volume=size_result.volume,
                    proposed_monetary_risk=size_result.monetary_risk
                )
                if not fg_ok:
                    rejections.append(f"Pre-check failed (Fast Risk Guard): {fg_reason}")

        passed = len(rejections) == 0

        structure_state_str = "BOS_CONFIRMED"
        if hasattr(candidate, "rejection_reasons"):
            for r in candidate.rejection_reasons:
                if "CHoCH" in r or "trapped" in r:
                    structure_state_str = "CHOCH_WARNING"
        if hasattr(candidate, "reasons"):
            for r in candidate.reasons:
                if "BOS" in r:
                    structure_state_str = "BOS_CONFIRMED"

        plan = TradePlan(
            plan_id=f"PLAN_{candidate.id}",
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            lots=size_result.volume if passed else 0.0,
            risk_percent=size_result.risk_percent_actual if passed else 0.0,
            reward_to_risk=candidate.risk_reward,
            structure_state=structure_state_str,
            timestamp=datetime.now(timezone.utc),
            session_name=sess_info.primary_session.value if sess_info else None
        )
        if sess_info:
            candidate.session_name = sess_info.primary_session.value
        candidate.trade_plan = plan
        self._signal_trade_plans[candidate.id] = plan

        # 13. Human Confirmed Gate (LIVE/PROP only when confirm_mode enabled; DEMO auto-executes)
        if passed and self.config.execution_mode in (ExecutionMode.REAL, ExecutionMode.PROP):
            if hasattr(self, "telegram_cmd_handler") and self.telegram_cmd_handler and getattr(self.telegram_cmd_handler, "confirm_mode", False):
                confirmed = self.telegram_cmd_handler.request_trade_confirmation(plan, timeout_sec=120)
                if not confirmed:
                    rejections.append("Pre-check failed (Human Confirm): Trade plan confirmation timed out or cancelled by operator.")
                    passed = False

        if hasattr(self, "shadow_journal") and self.shadow_journal:
            decision_label = "TAKEN" if passed else "REJECTED_CHECKLIST"
            for r in rejections:
                if "Structure" in r:
                    decision_label = "REJECTED_BOS"
                    break
                elif "Replay Gate" in r:
                    decision_label = "REJECTED_REPLAY"
                    break
            self.shadow_journal.record_setup(
                setup_id=candidate.id,
                symbol=candidate.symbol,
                direction=candidate.direction,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                reward_to_risk=candidate.risk_reward,
                decision=decision_label,
                rejection_reasons=rejections
            )
        if passed:
            logging.getLogger("OrderManager").info(plan.format_log())
        return PreTradeCheckResult(
            passed=passed,
            rejection_reasons=rejections,
            calculated_volume=size_result.volume if passed else 0.0,
            monetary_risk=size_result.monetary_risk if passed else 0.0,
            trade_plan=plan
        )

    def execute_signal(
        self,
        candidate: SignalCandidate,
        account: AccountInfo,
        symbol_info: SymbolInfo,
        active_positions: List[Position],
        recent_candles: Optional[List[Candle]] = None,
        prevalidated: Optional[PreTradeCheckResult] = None,
    ) -> Optional[TradeOrder]:
        """
        Executes pre-trade validation, then submits order to MT5 Bridge
        or simulates order execution in SIMULATION mode.

        When `prevalidated` is supplied the orchestrator's already-executed
        checklist is reused instead of running the full checklist twice.
        """
        if candidate.stop_loss <= 0:
            candidate.status = "REJECTED"
            candidate.rejection_reasons.append("R9.2 violation: Cannot execute order without a stop loss (stop_loss <= 0).")
            return None

        # Check duplicate execution
        if candidate.id in self._executed_signal_ids or self.transaction_manager.is_signal_executed_or_in_flight(candidate.id):
            logger.warning(f"[ORDER_MANAGER] Signal {candidate.id} already executed or in-flight. Skipping duplicate.")
            candidate.status = "REJECTED"
            candidate.rejection_reasons.append("Duplicate signal execution prevented")
            return None

        check = prevalidated or self.run_pre_trade_checklist(
            candidate, account, symbol_info, active_positions, recent_candles=recent_candles
        )
        if not check.passed:
            candidate.status = "REJECTED"
            candidate.rejection_reasons.extend(check.rejection_reasons)
            return None

        # Mode: SIMULATION or BACKTEST
        if self.config.execution_mode in [ExecutionMode.SIMULATION, ExecutionMode.BACKTEST]:
            self._sim_ticket_counter += 1
            sim_ticket = self._sim_ticket_counter
            req_id = f"REQ_SIM_{candidate.symbol}_{int(datetime.now(timezone.utc).timestamp()*1000)}_{uuid.uuid4().hex[:6].upper()}"

            self.transaction_manager.record_submission(
                signal_id=candidate.id,
                symbol=candidate.symbol,
                direction=candidate.direction.value,
                volume=check.calculated_volume,
                price=candidate.entry_price,
                sl=candidate.stop_loss,
                tp=candidate.take_profit,
                request_id=req_id,
            )
            self.transaction_manager.record_acceptance(
                request_id=req_id,
                order_ticket=sim_ticket,
                comment="SIMULATED",
            )
            self.transaction_manager.record_fill(
                request_id=req_id,
                position_ticket=sim_ticket,
                fill_price=candidate.entry_price,
                filled_volume=check.calculated_volume,
                sl=candidate.stop_loss,
                tp=candidate.take_profit,
            )

            order = TradeOrder(
                ticket=sim_ticket,
                symbol=candidate.symbol,
                order_type=candidate.direction,
                volume=check.calculated_volume,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                magic=self.config.magic_number,
                comment=f"SIM_{candidate.setup_type.value}",
                status="FILLED",
                executed_at=datetime.now(timezone.utc)
            )

            # Register simulated position
            new_pos = Position(
                ticket=sim_ticket,
                symbol=candidate.symbol,
                order_type=candidate.direction,
                volume=check.calculated_volume,
                open_price=candidate.entry_price,
                current_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                profit=0.0,
                magic=self.config.magic_number,
                comment=order.comment,
                open_time=datetime.now(timezone.utc),
                initial_risk_amount=check.monetary_risk,
                initial_sl_distance=abs(candidate.entry_price - candidate.stop_loss),
                profit_mode=getattr(candidate, "profit_mode", ProfitManagementMode.QUICK_SCALP)
            )
            self.simulated_positions.append(new_pos)
            if check.trade_plan:
                self._active_trade_plans[sim_ticket] = check.trade_plan
            self._executed_signal_ids.add(candidate.id)
            self.portfolio_risk.register_trade_executed()
            candidate.status = "EXECUTED"
            if hasattr(candidate, "lifecycle_state"):
                from src.core.contracts import SignalLifecycleState
                candidate.lifecycle_state = SignalLifecycleState.FILLED
            return order

        # Calculate accurate monetary risk percent for MT5 Bridge (R9.1 hard cap 2.0%)
        bal = account.balance if account.balance > 0 else 10000.0
        risk_pct = round((check.monetary_risk / bal) * 100.0, 2) if check.monetary_risk > 0 else float(self.config.risk.max_risk_per_trade_percent)
        risk_pct = min(2.0, risk_pct)

        # Mode: DEMO or REAL Live Execution via MT5 Bridge
        req_id = f"REQ_{candidate.symbol}_{int(datetime.now(timezone.utc).timestamp()*1000)}_{uuid.uuid4().hex[:6].upper()}"
        self.transaction_manager.record_submission(
            signal_id=candidate.id,
            symbol=candidate.symbol,
            direction=candidate.direction.value,
            volume=check.calculated_volume,
            price=candidate.entry_price,
            sl=candidate.stop_loss,
            tp=candidate.take_profit,
            request_id=req_id,
        )

        # Snapshot existing tickets prior to order transmission
        pre_existing_tickets = set()
        pre_existing_order_tickets = set()
        try:
            for p in self.bridge.get_positions():
                pre_existing_tickets.add(int(p.ticket))
        except Exception as e:
            logger.debug(f"[ORDER_MANAGER] Could not snapshot positions: {e}")

        try:
            pre_ord_res = self.bridge.send_request({"action": "ORDERS"})
            if pre_ord_res.get("status") == "SUCCESS" and "data" in pre_ord_res:
                pre_existing_order_tickets = {int(o.get("ticket", 0)) for o in pre_ord_res["data"]}
        except Exception as e:
            logger.debug(f"[ORDER_MANAGER] Could not snapshot orders: {e}")

        exec_mode_str = (
            "HOLD"
            if getattr(candidate, "profit_mode", ProfitManagementMode.QUICK_SCALP) == ProfitManagementMode.PROFIT_RUNNING
            else "SCALP"
        )
        if hasattr(candidate, "lifecycle_state"):
            from src.core.contracts import SignalLifecycleState
            candidate.lifecycle_state = SignalLifecycleState.SUBMITTED

        # Order submission with controlled retry on recoverable broker conditions
        max_retries = 2
        attempt = 0
        confirmed_ticket = 0
        retcode_val = 0
        retcode_ok = False
        res = {}

        while attempt <= max_retries:
            res = self.bridge.execute_trade(
                symbol=candidate.symbol,
                order_type=candidate.direction,
                volume=check.calculated_volume,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                price=candidate.entry_price,
                risk_percent=risk_pct,
                mode=exec_mode_str,
                magic=self.config.magic_number,
                comment=f"{exec_mode_str}_{candidate.setup_type.value}",
                request_id=req_id,
                deviation=int(getattr(self.config.risk, "max_slippage_points", 15))
            )
            res = res if isinstance(res, dict) else {}

            # Handle IPC Timeout with immediate reconciliation recovery
            if res.get("status") == "ERROR" and ("timed out" in str(res.get("message", "")).lower() or "timeout" in str(res.get("message", "")).lower()):
                logger.warning(f"[ORDER_MANAGER] Execution timed out awaiting response for {candidate.symbol} ({req_id}). Checking MT5 positions/orders...")
                try:
                    open_positions = self.bridge.get_positions()
                    for pos in open_positions:
                        if (
                            pos.ticket not in pre_existing_tickets
                            and pos.symbol == candidate.symbol
                            and pos.order_type == candidate.direction
                            and abs(pos.volume - check.calculated_volume) < 1e-4
                            and (pos.magic == self.config.magic_number or "SMC" in pos.comment or "SCALP" in pos.comment)
                        ):
                            logger.info(f"[ORDER_MANAGER] Reconciled timed-out order #{pos.ticket} as successfully FILLED in MT5!")
                            res = {"status": "SUCCESS", "ticket": pos.ticket, "price": pos.open_price, "retcode": 10009}
                            break
                except Exception as e:
                    logger.error(f"[ORDER_MANAGER] Error during timed-out order reconciliation: {e}")

            retcode = res.get("retcode")
            retcode_val = int(retcode) if retcode is not None else 0
            retcode_ok = retcode is None or retcode_val in (10008, 10009, 10010)
            try:
                confirmed_ticket = int(res.get("ticket", 0) or 0)
            except (TypeError, ValueError):
                confirmed_ticket = 0

            # If order accepted/filled, exit retry loop
            if res.get("status") == "SUCCESS" and retcode_ok and confirmed_ticket > 0:
                break

            # Recoverable broker error handling (Requote 10004, Price changed 10020, No quote 10021, Request timeout 10012)
            is_recoverable = retcode_val in (10004, 10020, 10021, 10012) or ("timeout" in str(res.get("message", "")).lower())
            if is_recoverable and attempt < max_retries:
                attempt += 1
                logger.warning(
                    f"[ORDER_MANAGER] Recoverable broker issue on {candidate.symbol} (retcode={retcode_val}, "
                    f"msg={res.get('message')}). Retrying attempt {attempt}/{max_retries}..."
                )
                # 1. Confirm whether previous request was accepted before submitting retry (prevents duplicates)
                try:
                    open_positions = self.bridge.get_positions()
                    reconciled = False
                    for pos in open_positions:
                        if (
                            pos.ticket not in pre_existing_tickets
                            and pos.symbol == candidate.symbol
                            and pos.order_type == candidate.direction
                            and abs(pos.volume - check.calculated_volume) < 1e-4
                        ):
                            logger.info(f"[ORDER_MANAGER] Pre-retry check found position #{pos.ticket} already accepted. Skipping duplicate submission.")
                            confirmed_ticket = pos.ticket
                            res = {"status": "SUCCESS", "ticket": pos.ticket, "price": pos.open_price, "retcode": 10009}
                            retcode_ok = True
                            reconciled = True
                            break
                    if reconciled:
                        break
                except Exception:
                    pass

                # 2. Refresh market quote and parameters if valid
                try:
                    sym_info = self.bridge.get_symbol_info(candidate.symbol)
                    if sym_info and sym_info.ask > 0 and sym_info.bid > 0:
                        new_p = sym_info.ask if candidate.direction == OrderType.BUY else sym_info.bid
                        if abs(new_p - candidate.entry_price) / max(candidate.entry_price, 1e-5) < 0.005:
                            candidate.entry_price = new_p
                except Exception:
                    pass
                time.sleep(0.2 * attempt)
            else:
                break

        if res.get("status") != "SUCCESS" or not retcode_ok or confirmed_ticket <= 0:
            is_market_closed = (res.get("status") == "MARKET_CLOSED" or retcode_val == 10018)
            from src.core.contracts import SignalLifecycleState
            if is_market_closed:
                candidate.lifecycle_state = SignalLifecycleState.RETRY_PENDING
            elif "timeout" in str(res.get("message", "")).lower():
                candidate.lifecycle_state = SignalLifecycleState.CONNECTION_FAILED
            else:
                candidate.lifecycle_state = SignalLifecycleState.BROKER_REJECTED
            candidate.status = "REJECTED"
            err_msg = str(res.get("message") or f"MT5 did not confirm execution (ticket={confirmed_ticket}, retcode={retcode_val})")
            logger.warning(f"[WARNING] [EXECUTION_ENGINE] Broker rejected order: {err_msg}")
            candidate.rejection_reasons.append(err_msg)
            self.transaction_manager.record_rejection(
                request_id=req_id,
                error_message=err_msg,
                retcode=retcode_val,
            )
            return TradeOrder(
                symbol=candidate.symbol,
                order_type=candidate.direction,
                volume=check.calculated_volume,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                magic=self.config.magic_number,
                status="REJECTED",
                error=err_msg
            )

        # Order was accepted by MT5 (retcode 10008, 10009, or 10010)
        logger.info(f"[SUCCESS] [EXECUTION_ENGINE] {candidate.symbol} {candidate.direction.value} order accepted by broker.")
        order_ticket = confirmed_ticket
        if hasattr(candidate, "lifecycle_state"):
            from src.core.contracts import SignalLifecycleState
            candidate.lifecycle_state = SignalLifecycleState.ACCEPTED
        self.transaction_manager.record_acceptance(
            request_id=req_id,
            order_ticket=order_ticket,
            comment=f"Accepted by MT5 retcode={retcode_val}",
        )

        # Phase 2: Broker-Side Position Verification
        # Never report an executed trade solely on order submission response; poll MT5 positions.
        verified_position: Optional[Position] = None
        max_verification_attempts = 8
        verification_poll_interval = 0.25

        for attempt in range(max_verification_attempts):
            time.sleep(verification_poll_interval)
            try:
                positions = self.bridge.get_positions()
                for pos in positions:
                    is_exact_ticket = (order_ticket > 0 and pos.ticket == order_ticket)
                    is_exact_identifier = (order_ticket > 0 and getattr(pos, "identifier", 0) == order_ticket)
                    is_new_matching_position = (
                        pos.ticket not in pre_existing_tickets
                        and pos.symbol == candidate.symbol
                        and pos.order_type == candidate.direction
                        and (pos.magic == self.config.magic_number or "SMC" in pos.comment or "SCALP" in pos.comment)
                    )
                    if is_exact_ticket or is_exact_identifier or is_new_matching_position:
                        verified_position = pos
                        break
            except Exception as e:
                logger.warning(f"[ORDER_MANAGER] Polling positions failed on attempt {attempt+1}: {e}")
            if verified_position is not None:
                break

        if verified_position is None:
            # Check pending orders
            is_pending = False
            try:
                orders_res = self.bridge.send_request({"action": "ORDERS"})
                if orders_res.get("status") == "SUCCESS" and "data" in orders_res:
                    for ord_item in orders_res["data"]:
                        tkt = int(ord_item.get("ticket", 0))
                        if tkt == order_ticket or (
                            tkt not in pre_existing_order_tickets
                            and ord_item.get("symbol") == candidate.symbol
                            and int(ord_item.get("magic", 0)) == self.config.magic_number
                        ):
                            is_pending = True
                            order_ticket = tkt
                            break
            except Exception as e:
                logger.warning(f"[ORDER_MANAGER] Polling pending orders failed: {e}")

            if is_pending:
                logger.info(f"[ORDER_MANAGER] Order #{order_ticket} verified as active pending order in MT5.")
                if hasattr(candidate, "lifecycle_state"):
                    from src.core.contracts import SignalLifecycleState
                    candidate.lifecycle_state = SignalLifecycleState.PENDING_ORDER
                return TradeOrder(
                    ticket=order_ticket,
                    symbol=candidate.symbol,
                    order_type=candidate.direction,
                    volume=check.calculated_volume,
                    entry_price=candidate.entry_price,
                    stop_loss=candidate.stop_loss,
                    take_profit=candidate.take_profit,
                    magic=self.config.magic_number,
                    status="ACCEPTED",
                )

            # Not found in positions or pending orders -> EXECUTION UNCONFIRMED
            unconfirmed_reason = f"Order #{order_ticket} accepted (retcode {retcode_val}) but no broker position or pending order verified after {max_verification_attempts} attempts."
            logger.error(f"[ORDER_MANAGER] {unconfirmed_reason}")
            self.transaction_manager.record_unconfirmed(
                request_id=req_id,
                reason=unconfirmed_reason,
            )
            candidate.status = "UNCONFIRMED"
            candidate.rejection_reasons.append(unconfirmed_reason)
            return TradeOrder(
                ticket=order_ticket,
                symbol=candidate.symbol,
                order_type=candidate.direction,
                volume=check.calculated_volume,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                magic=self.config.magic_number,
                status="UNCONFIRMED",
                error=unconfirmed_reason,
            )

        # Position verified at broker
        actual_ticket = verified_position.ticket
        logger.info(f"[SUCCESS] [POSITION_MANAGER] Position confirmed and registered successfully: #{actual_ticket} on {candidate.symbol}")
        actual_fill_price = float(verified_position.open_price)
        actual_volume = float(verified_position.volume)
        actual_sl = float(verified_position.stop_loss)
        actual_tp = float(verified_position.take_profit)

        # Enforce protective Stop Loss
        if actual_sl <= 0.0:
            logger.warning(f"[ORDER_MANAGER] Position #{actual_ticket} missing Stop Loss at broker (sl={actual_sl}). Applying immediate protective SL/TP...")
            mod_res = self.bridge.modify_order(
                ticket=actual_ticket,
                sl=candidate.stop_loss,
                tp=candidate.take_profit,
            )
            if mod_res.get("status") != "SUCCESS":
                time.sleep(0.2)
                mod_res = self.bridge.modify_order(
                    ticket=actual_ticket,
                    sl=candidate.stop_loss,
                    tp=candidate.take_profit,
                )
            if mod_res.get("status") == "SUCCESS":
                actual_sl = candidate.stop_loss
                if actual_tp <= 0.0:
                    actual_tp = candidate.take_profit
                logger.info(f"[ORDER_MANAGER] Successfully attached protective SL/TP to #{actual_ticket} via post-fill modification.")
            else:
                logger.critical(f"[ORDER_MANAGER] FAILED to establish stop loss protection for #{actual_ticket}! Closing unprotected position...")
                self.bridge.close_position(actual_ticket)
                candidate.status = "REJECTED"
                err_msg = f"Position #{actual_ticket} closed immediately: failed to establish mandatory stop loss protection."
                candidate.rejection_reasons.append(err_msg)
                self.transaction_manager.record_rejection(req_id, err_msg, retcode=10016)
                return TradeOrder(
                    ticket=actual_ticket,
                    symbol=candidate.symbol,
                    order_type=candidate.direction,
                    volume=actual_volume,
                    entry_price=actual_fill_price,
                    stop_loss=0.0,
                    take_profit=0.0,
                    magic=self.config.magic_number,
                    status="REJECTED",
                    error=err_msg,
                )

        # Determine if partial fill
        is_partial = actual_volume < (check.calculated_volume - 1e-4)
        if is_partial:
            remaining_vol = round(check.calculated_volume - actual_volume, 2)
            self.transaction_manager.record_partial_fill(
                request_id=req_id,
                position_ticket=actual_ticket,
                fill_price=actual_fill_price,
                filled_volume=actual_volume,
                remaining_volume=remaining_vol,
                sl=actual_sl,
                tp=actual_tp,
            )
            order_status = "PARTIALLY_FILLED"
        else:
            self.transaction_manager.record_fill(
                request_id=req_id,
                position_ticket=actual_ticket,
                fill_price=actual_fill_price,
                filled_volume=actual_volume,
                sl=actual_sl,
                tp=actual_tp,
            )
            order_status = "FILLED"

        if check.trade_plan and actual_ticket > 0:
            self._active_trade_plans[actual_ticket] = check.trade_plan

        # Recalculate actual R:R from broker fill price & stops
        if actual_fill_price > 0 and actual_sl > 0 and actual_tp > 0:
            actual_risk = abs(actual_fill_price - actual_sl)
            actual_reward = abs(actual_tp - actual_fill_price)
            actual_rr = (actual_reward / actual_risk) if actual_risk > 0 else 0.0
            if not isinstance(getattr(candidate, "metadata", None), dict):
                candidate.metadata = {}
            candidate.metadata["actual_fill_price"] = actual_fill_price
            candidate.metadata["actual_volume"] = actual_volume
            candidate.metadata["actual_rr"] = round(actual_rr, 4)
        if hasattr(candidate, "lifecycle_state"):
            from src.core.contracts import SignalLifecycleState
            candidate.lifecycle_state = SignalLifecycleState.PARTIAL_FILL if is_partial else SignalLifecycleState.FILLED

        if hasattr(self, "tca") and self.tca:
            try:
                spread_pts = float(symbol_info.spread) if symbol_info else 10.0
                pt = float(symbol_info.point) if symbol_info and symbol_info.point > 0 else 0.00001
                tv = float(symbol_info.tick_value) if symbol_info and symbol_info.tick_value > 0 else 1.0
                self.tca.record_execution(
                    request_id=req_id,
                    symbol=candidate.symbol,
                    order_type=candidate.direction.value,
                    volume=actual_volume,
                    intended_price=candidate.entry_price,
                    filled_price=actual_fill_price,
                    spread_at_signal_pts=spread_pts,
                    spread_at_fill_pts=spread_pts,
                    latency_ms=float(res.get("latency_ms", 15.0)),
                    retcode=retcode_val or 10009,
                    point=pt,
                    tick_value=tv,
                )
            except Exception as tca_err:
                logger.debug(f"TCA audit logging non-blocking exception: {tca_err}")

        order = TradeOrder(
            ticket=actual_ticket,
            symbol=candidate.symbol,
            order_type=candidate.direction,
            volume=actual_volume,
            entry_price=actual_fill_price,
            stop_loss=actual_sl,
            take_profit=actual_tp,
            magic=self.config.magic_number,
            status=order_status,
            executed_at=datetime.now(timezone.utc),
        )
        self._executed_signal_ids.add(candidate.id)
        self.portfolio_risk.register_trade_executed()
        candidate.status = "EXECUTED"
        return order

    def get_active_positions(self, own_only: bool = True) -> List[Position]:
        """Returns active positions depending on operating mode.
        [SAFETY] By default (own_only=True), filters positions to return only those
        belonging to this bot (pos.magic == config.magic_number).
        """
        if getattr(self.config, "dry_run", False) or self.config.execution_mode in [ExecutionMode.SIMULATION, ExecutionMode.BACKTEST]:
            positions = list(self.simulated_positions)
        else:
            positions = self.bridge.get_positions()
            try:
                self.transaction_manager.reconcile_with_broker_positions(positions)
            except Exception as rec_err:
                logger.debug(f"Transaction reconciliation non-blocking error: {rec_err}")

        if own_only:
            return [p for p in positions if getattr(p, "magic", 0) == self.config.magic_number]
        return positions

    def get_all_account_positions(self) -> List[Position]:
        """Returns all positions on the MT5 account regardless of magic number."""
        return self.get_active_positions(own_only=False)

    def get_trade_plan(self, key: Any) -> Optional[TradePlan]:
        if isinstance(key, int):
            return self._active_trade_plans.get(key)
        return self._signal_trade_plans.get(str(key))

    def apply_plan_amendment(self, ticket: int, amendment: PlanAmendment) -> Optional[TradePlan]:
        current_plan = self._active_trade_plans.get(ticket)
        if not current_plan:
            logger.warning(f"[PLAN_AMENDMENT] No active plan found for ticket #{ticket}")
            return None

        # Rule R9.3: NEVER move a stop further away (widen risk)
        valid_sl, sl_reason = self.validate_sl_modification(
            direction=current_plan.direction,
            current_sl=current_plan.stop_loss,
            new_sl=amendment.new_sl
        )
        if not valid_sl:
            logger.error(f"[R9.3_REJECTED] Ticket #{ticket}: {sl_reason}")
            return None

        new_plan = current_plan.with_amendment(amendment)
        self._active_trade_plans[ticket] = new_plan
        logger.info(
            f"[PLAN_AMENDMENT] Ticket #{ticket}: {amendment.amendment_type} | "
            f"SL amended from {amendment.old_sl:.5f} to {amendment.new_sl:.5f} | "
            f"Reason: {amendment.reason}"
        )
        return new_plan
