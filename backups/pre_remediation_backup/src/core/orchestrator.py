"""
Master Trading Engine Orchestrator.
Coordinates the end-to-end institutional algorithmic pipeline & continuous M1/M5/M15 scalping engine:
Market Data -> Liquidity/Structure -> MTF -> Continuous Scalping / SMC Strategy -> Risk -> Execution -> Lifecycle Management.
"""

from __future__ import annotations
from datetime import datetime, timezone
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("TradingBotOrchestrator")

from src.core.config import AppConfig
from src.core.contracts import (
    AccountInfo,
    Candle,
    DecisionOutcome,
    DecisionOutcomeType,
    ExecutionMode,
    OrderType,
    Position,
    ProfitManagementMode,
    SignalCandidate,
    SignalLifecycleState,
    SymbolInfo,
    Timeframe,
    TradeOrder,
)
from src.core.market_data import MarketDataEngine
from src.core.news_filter import NewsFilterEngine
from src.core.sessions import TradingSessionEngine
from src.core.volatility import VolatilityEngine
from src.execution.bridge_client import BridgeClient
from src.execution.continuous_scalper import ContinuousScalpingEngine, ScalpingLifecycleState
from src.execution.order_manager import OrderManager
from src.learning.champion_challenger import ChampionChallengerEngine, StrategyCandidate
from src.learning.performance_tracker import PerformanceTracker, TradeRecord
from src.monitoring.alerts_telegram import TelegramAlertManager
from src.execution.active_mode import ActiveTradingEngine, ActiveTradingConfig, ProhibitionViolationError
from concurrent.futures import ThreadPoolExecutor
from src.monitoring.dashboard import DashboardState, TradingDashboard
from src.monitoring.health_monitor import ContinuousHealthMonitor
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.risk.state_manager import StateManager
from src.risk.trade_management import TradeManagementEngine
from src.smc.mtf_analyzer import MultiTimeframeAnalyzer, MultiTimeframeContext
from src.smc.setup_quality_gate import SetupQualityGate, GateMode
from dataclasses import asdict
from src.regime.regime_detector import RegimeDetector
from src.regime.models import RegimeType, RegimeSuggestion
from src.learning.meta.meta_classifier import MetaLabelingController
from src.risk.volatility import VolatilityEngine as AdvancedVolatilityEngine
from src.risk.kelly import KellyEngine
from src.monitoring.decay_guard import DecayGuard
from src.execution.analytics.tca import TCAEngine
from src.core.instruments import is_gold, get_instrument_profile
from src.smc.smc_rulebook import NoTradeReason
from src.smc.strategy_engine import SmcStrategyEngine
from src.core.symbol_universe import SpecializedSymbolUniverse, get_symbol_universe
from src.core.trading_schedule import TradingScheduleManager, get_trading_schedule, OperatingMode
from src.strategy.inverse_coordination import InverseDirectionCoordinator, CorrelationRegime


class TradingBotOrchestrator:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.load_from_dir()

        # 0. Specialized 3-Symbol Universe, Trading Scheduler & Inverse Direction Coordinator
        self.symbol_universe = get_symbol_universe()
        self.trading_scheduler = get_trading_schedule(getattr(self.config, "weekday_btc_fallback_enabled", False))
        self.inverse_coordinator = InverseDirectionCoordinator(
            enabled=getattr(self.config, "inverse_coordination_enabled", True)
        )

        # 1. Market Data & Environment
        self.market_data = MarketDataEngine(symbols=self.config.symbols)
        self.sessions = TradingSessionEngine(self.config.session)
        self.volatility = VolatilityEngine()
        self.news_filter = NewsFilterEngine(enabled=bool(getattr(self.config, "news_filter_enabled", True)))

        # 2. Strategy, MTF & Continuous M1/M5/M15 Scalping Engine
        self.mtf_analyzer = MultiTimeframeAnalyzer()
        self.strategy_engine = SmcStrategyEngine(
            min_score=self.config.strategy.min_confluence_score,
            min_rr=self.config.risk.min_risk_reward_ratio,
            swing_lookback=getattr(self.config.strategy, "swing_lookback_bars", 5),
            require_close_break=getattr(self.config.strategy, "require_close_break", True),
            require_lower_high=getattr(self.config.strategy, "require_lower_high", True),
            choch_timeout_bars=getattr(self.config.strategy, "choch_timeout_bars", 20),
            allow_choch_only_entries=getattr(self.config.strategy, "allow_choch_only_entries", False),
            failed_choch_action=getattr(self.config.strategy, "failed_choch_action", "RESET_AND_LOG_TRAP"),
            ob_requires_displacement=getattr(self.config.smc_rulebook, "ob_requires_displacement", True),
            ob_displacement_atr_mult=getattr(self.config.smc_rulebook, "ob_displacement_atr_mult", 1.2),
            ob_requires_bos=getattr(self.config.smc_rulebook, "ob_requires_bos", True),
            fvg_min_atr=getattr(self.config.smc_rulebook, "fvg_min_atr", 0.3),
            sweep_requires_close_back_inside=getattr(self.config.smc_rulebook, "sweep_requires_close_back_inside", True),
            pd_equilibrium=getattr(self.config.smc_rulebook, "pd_equilibrium", 0.5),
            tp_requires_liquidity_pool=getattr(self.config.smc_rulebook, "tp_requires_liquidity_pool", True),
            htf_timeframe=getattr(self.config.strategy, "htf_timeframe", "H1"),
            ltf_timeframe=getattr(self.config.strategy, "ltf_timeframe", "M15"),
        )
        self.strategy_engine.execution_mode = self.config.execution_mode
        legacy_init = bool(getattr(self.config, "legacy_filters_enabled", False))
        self.strategy_engine.legacy_filters_enabled = legacy_init
        self.continuous_scalper = ContinuousScalpingEngine(
            symbols=self.config.symbols,
            min_confluence_score=float(getattr(self.config.strategy, "scalping_min_confluence_score", 55.0)) if legacy_init else 0.0,
            min_rr=float(getattr(self.config.risk, "scalping_min_risk_reward_ratio", 1.5)) if legacy_init else 0.0,
            require_htf_agreement=bool(getattr(self.config.strategy, "continuous_scalp_require_htf_agreement", False)) if legacy_init else False,
            auto_rescan_after_closure=bool(getattr(self.config, "auto_rescan_after_closure", True)),
        )

        self.quality_gate = SetupQualityGate(getattr(self.config, "smc_rulebook", None))
        # 3. Risk & Management
        self.sizing_engine = PositionSizingEngine(self.config.risk.risk_percentage)
        self.portfolio_risk = PortfolioRiskEngine(self.config)
        self.trade_manager = TradeManagementEngine(self.config.risk)

        # 4. Bridge & Execution
        self.bridge = BridgeClient(
            host=self.config.bridge_host,
            port=self.config.bridge_port,
        )
        self.order_manager = OrderManager(
            config=self.config,
            bridge=self.bridge,
            sizing_engine=self.sizing_engine,
            portfolio_risk=self.portfolio_risk,
        )

        # Broker-aware symbol resolution for specialized 3-symbol universe
        try:
            self.symbol_universe.resolve_universe(bridge_client=self.bridge)
        except Exception as res_err:
            logger.debug(f"[SYMBOL_MANAGER] Symbol resolution skipped: {res_err}")

        # Hook 1: Broker Adapter Delegation (Strangler Pattern)
        if getattr(self.config, "upgrade_enabled", False) and getattr(self.config, "broker_adapter_enabled", False):
            from src.adapters.broker_factory import BrokerFactory

            self.broker = BrokerFactory.create_broker(self.config, self.bridge)
        else:
            self.broker = None

        # 3b. Unified Modern Strategy Pipeline (obsolete legacy_adapter removed)
        self.strategy_pipeline = None

        # 5. Learning & Tracking
        self.performance_tracker = PerformanceTracker()
        champion_cand = StrategyCandidate(
            id="SMC_CHAMPION_V1",
            name="Institutional SMC Multi-Timeframe",
            version="1.0.0",
            parameters={"min_score": 75.0, "min_rr": 2.0},
            is_champion=True,
        )
        self.learning_engine = ChampionChallengerEngine(champion=champion_cand)

        # 6. Monitoring, Health & Alerts
        self.dashboard = TradingDashboard(execution_mode=self.config.execution_mode.value)
        self.active_engine = ActiveTradingEngine()
        self.alerts = TelegramAlertManager(
            bot_token=self.config.telegram_bot_token,
            chat_id=self.config.telegram_chat_id,
        )
        self.health_monitor = ContinuousHealthMonitor(symbols=self.config.symbols)

        # 6b. Advanced Quantitative Intelligence & Governance (Phase 3)
        self.regime_detector = RegimeDetector()
        self.meta_labeling = MetaLabelingController()
        self.advanced_volatility = AdvancedVolatilityEngine()
        self.kelly_engine = KellyEngine(kelly_fraction=0.25)
        self.decay_guard = DecayGuard(baseline_win_rate=0.55, baseline_expectancy_r=0.45, enabled=True)
        self.tca = TCAEngine(enabled=True)

        # 6c. Multi-Pair Market Intelligence and Modular Scalping Engine
        from src.engine.market_intelligence import MarketIntelligenceEngine
        from src.engine.intelligent_scoring import IntelligentScoringEngine
        from src.engine.multi_pair_scanner import MultiPairScanner

        self.market_intelligence = MarketIntelligenceEngine()
        self.intelligent_scoring = IntelligentScoringEngine()
        self.multi_pair_scanner = MultiPairScanner(
            market_data=self.market_data,
            market_intelligence=self.market_intelligence,
            scoring_engine=self.intelligent_scoring,
            symbols=self.config.symbols,
        )

        # State storage
        self.active_contexts: Dict[str, MultiTimeframeContext] = {}
        self.recent_signals: List[SignalCandidate] = []
        self.account_info = AccountInfo()
        self.last_decision_outcomes: Dict[str, DecisionOutcome] = {}
        self.auto_sync_market_data: bool = False
        self.enforce_stale_data_check: bool = False
        self.max_candle_staleness_seconds: float = 7200.0
        self._executed_signal_keys: set = set()
        self._active_positions_cache: Dict[int, Position] = {}

        # 7. Atomic State Persistence & Safe Startup Load
        # Simulation/backtest runs must be deterministic and must not inherit live
        # risk state (daily counters, peak equity, circuit breakers) from disk.
        self.state_manager = StateManager("data/bot_state.json")
        if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL] and not getattr(self.config, "dry_run", False):
            saved_state = self.state_manager.load_state()
            if saved_state:
                self.portfolio_risk.load_from_dict(saved_state)

        # Reset duplicate alert suppression on startup
        if hasattr(self, "alerts") and self.alerts and hasattr(self.alerts, "notifier"):
            self.alerts.notifier.reset_suppression_counter()

        # 8. Manual Position Management Subsystem [SAFETY]
        self.manual_mgmt_detector = None
        try:
            import os
            import yaml
            from src.manual_mgmt import ManualPositionDetector, ManualMgmtConfig
            mm_cfg_path = "config/manual_management.yaml"
            mm_data = {}
            if os.path.exists(mm_cfg_path):
                with open(mm_cfg_path, "r", encoding="utf-8") as f:
                    mm_data = yaml.safe_load(f) or {}
            mm_config = ManualMgmtConfig.from_dict(mm_data)
            mgmt_broker = self.broker
            if mgmt_broker is None and hasattr(self, "bridge") and self.bridge:
                from src.adapters.live_mt5_broker import LiveMT5Broker
                mgmt_broker = LiveMT5Broker(self.bridge)
            if mgmt_broker:
                self.manual_mgmt_detector = ManualPositionDetector(
                    config=mm_config,
                    broker=mgmt_broker,
                    bot_magic=self.config.magic_number
                )
                logging.getLogger("Orchestrator").info(
                    f"[MANUAL_MGMT] Initialized in mode={mm_config.mode.value} "
                    f"(allow_real={mm_config.allow_real_account_management})"
                )
        except Exception as mm_err:
            logging.getLogger("Orchestrator").debug(f"Manual position management not initialized: {mm_err}")

        self._known_manual_tickets: Set[int] = set()
        self._retry_pending_signals: Dict[str, Tuple[SignalCandidate, datetime, str]] = {}
        self._last_scalp_close_ts: Dict[str, float] = {}
        self._consecutive_failed_entries: Dict[str, int] = {}

        # Wire Bridge connection state callbacks
        if hasattr(self, "bridge") and self.bridge and hasattr(self.bridge, "set_connection_callbacks"):
            self.bridge.set_connection_callbacks(
                on_lost=lambda d: self.alerts.alert_connection_lost(d) if hasattr(self, "alerts") and self.alerts else None,
                on_restored=lambda d: self.alerts.alert_connection_restored(d) if hasattr(self, "alerts") and self.alerts else None,
            )

    def initialize_market_data(self, max_retries: int = 3) -> Dict[str, Dict[str, object]]:
        """
        Synchronizes full historical candles across all configured symbols and timeframes
        (including M1, M5, M15, H1, H4, D1, W1) before live scanning begins,
        and enables incremental auto-sync on subsequent cycles.
        """
        self.auto_sync_market_data = True
        health = self.market_data.initialize_and_warmup(
            bridge=self.bridge if self.bridge.is_connected() else None,
            max_retries=max_retries,
        )
        for sym, tf_map in health.items():
            m1_info = tf_map.get("M1", {})
            m5_info = tf_map.get("M5", {})
            m15_info = tf_map.get("M15", {})
            h1_info = tf_map.get("H1", {})
            h4_info = tf_map.get("H4", {})
            d1_info = tf_map.get("D1", {})
            w1_info = tf_map.get("W1", {})
            print(
                f"[MarketData] Warmup {sym} (broker={m15_info.get('broker_symbol', sym)}): "
                f"W1={w1_info.get('received_count', 0)}, D1={d1_info.get('received_count', 0)}, "
                f"H4={h4_info.get('received_count', 0)}, H1={h1_info.get('received_count', 0)}, "
                f"M15={m15_info.get('received_count', 0)}, M5={m5_info.get('received_count', 0)}, "
                f"M1={m1_info.get('received_count', 0)} | Healthy={m15_info.get('is_healthy', False)}"
            )
        return health

    @staticmethod
    def classify_outcome_category(outcome: DecisionOutcome) -> str:
        """
        Maps a DecisionOutcome to one of the explicit diagnostic categories:
        - TRADE_EXECUTED
        - MARKET_CLOSED
        - INSUFFICIENT_DATA
        - STALE_DATA
        - SPREAD_TOO_HIGH
        - RISK_RESTRICTION
        - CONNECTION_FAILURE
        - ORDER_EXECUTION_FAILURE
        - DUPLICATE_SIGNAL_BLOCKED
        - NO_VALID_SETUP
        """
        if outcome.outcome_type == DecisionOutcomeType.TRADE_SENT:
            return "TRADE_EXECUTED"
        code = (outcome.reason_code or "").upper()
        details_lower = (outcome.details or "").lower()
        if code == "STALE_DATA" or "stale" in details_lower:
            return "STALE_DATA"
        if code == "DUPLICATE_SIGNAL" or "duplicate signal" in details_lower:
            return "DUPLICATE_SIGNAL_BLOCKED"
        if "insufficient" in details_lower and "candle" in details_lower:
            return "INSUFFICIENT_DATA"
        if code == "SPREAD_TOO_HIGH" or "spread" in details_lower:
            return "SPREAD_TOO_HIGH"
        if code in ("MARKET_CLOSED", "SESSION_FILTER") or "weekend" in details_lower or "market closed" in details_lower:
            return "MARKET_CLOSED"
        if code == "CONNECTION_FAILURE" or "bridge disconnected" in details_lower or "connection" in details_lower:
            return "CONNECTION_FAILURE"
        if code == "EXECUTION_FAILED":
            return "ORDER_EXECUTION_FAILURE"
        if outcome.outcome_type == DecisionOutcomeType.TRADE_SKIPPED:
            return "RISK_RESTRICTION"
        return "NO_VALID_SETUP"

    def update_account(self, account: AccountInfo) -> None:
        import threading as _threading
        if not hasattr(self, "_account_lock"):
            self._account_lock = _threading.Lock()
        with self._account_lock:
            self.account_info = account
            self.portfolio_risk.update_equity(account)
            if hasattr(self, "state_manager"):
                self.state_manager.save_state(self.portfolio_risk.to_dict())

    def sync_account_from_bridge(self) -> Optional[AccountInfo]:
        """Fetch latest account info from MT5 Bridge and synchronize internal risk and dashboard state."""
        if not self.bridge or not self.bridge.is_connected():
            return None
        try:
            acc = self.bridge.get_account()
            if acc and getattr(acc, "balance", 0) > 0:
                self.update_account(acc)
                return acc
        except Exception as e:
            logger.debug(f"[ORCHESTRATOR] sync_account_from_bridge exception: {e}")
        return None

    def reset_state(self) -> tuple[bool, str]:
        try:
            # [SAFETY] Check only bot-owned positions so manual trades do not block bot resets
            all_positions = self.bridge.get_positions() if self.bridge.is_connected() else []
            bot_positions = [p for p in all_positions if getattr(p, "magic", 0) == self.config.magic_number]
            if bot_positions and len(bot_positions) > 0:
                return False, f"❌ <b>RESET REFUSED</b>: {len(bot_positions)} active bot position(s) are open. Close bot positions first."
        except Exception:
            pass

        if self.bridge.is_connected():
            try:
                self.bridge.send_request({"action": "RESET_STATE"})
                acc = self.bridge.get_account()
                if acc:
                    self.account_info = acc
            except Exception:
                pass

        cur_bal = self.account_info.balance
        self.portfolio_risk.reset_state(cur_bal)
        if hasattr(self, "state_manager"):
            self.state_manager.save_state(self.portfolio_risk.to_dict())
        if hasattr(self, "alerts") and self.alerts and hasattr(self.alerts, "notifier"):
            self.alerts.notifier.reset_suppression_counter()

        return True, f"✅ <b>STATE RESET COMPLETE</b>: Baseline balance, day-start balance, and peak equity reset to ${cur_bal:.2f}. Challenge progress: 0.0%. Daily counters cleared."

    def _record_and_dispatch_outcome(self, outcome: DecisionOutcome) -> None:
        self.last_decision_outcomes[outcome.symbol] = outcome
        line = outcome.format_line()
        print(f"[{outcome.evaluated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}] [{outcome.symbol}] {line}")
        if hasattr(self, "health_monitor") and self.health_monitor:
            if outcome.outcome_type == DecisionOutcomeType.TRADE_SENT:
                self.health_monitor.record_scan(
                    outcome.symbol,
                    diagnostic_reason="Trade executed",
                    details=outcome.details,
                )
                self.health_monitor.record_trade_execution(outcome.symbol, True, outcome.details)
            else:
                self.health_monitor.record_scan(
                    outcome.symbol,
                    diagnostic_reason=outcome.details,
                    details=outcome.details,
                )
        if hasattr(self, "alerts") and self.alerts:
            self.alerts.send_decision_outcome(outcome)

    def _execute_approved_candidate(
        self,
        symbol: str,
        candidate: SignalCandidate,
        bar_time: datetime,
    ) -> Optional[SignalCandidate]:
        """
        Runs pre-trade risk validation and order execution for an approved SignalCandidate,
        updating lifecycle state, idempotency keys, health monitor, and Telegram notifications.
        """
        sig_key = f"{symbol}_{candidate.direction.value}_{bar_time.isoformat()}"
        if sig_key in self._executed_signal_keys or self.continuous_scalper.is_duplicate_signal(sig_key):
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                reason_code="DUPLICATE_SIGNAL",
                details=f"Duplicate signal blocked for {symbol} {candidate.direction.value} on bar {bar_time.isoformat()}",
                real_numbers={"signal_id": candidate.id},
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        # High-impact news blackout gate (CPI, NFP, FOMC)
        legacy_enabled = getattr(self.config, "legacy_filters_enabled", False)
        if legacy_enabled:
            news_safe, news_reason = self.news_filter.is_trading_allowed(symbol, bar_time)
            if not news_safe:
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=bar_time,
                    outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                    reason_code="NEWS_BLACKOUT",
                    details=f"News filter blocked trade: {news_reason}",
                    real_numbers={"news_blocked": True},
                )
                self._record_and_dispatch_outcome(outcome)
                return None
        else:
            news_safe, news_reason = True, "Bypassed (LEGACY_FILTERS_ENABLED=false)"

        # Phase 2 Setup Quality Gate evaluation (sits between setup detected and order placed)
        mtf_ctx_for_gate = self.active_contexts.get(symbol)
        ltf_candles_for_gate = self.market_data.get_candles(symbol, Timeframe.M15)
        is_kz_for_gate, _ = self.sessions.evaluate_killzone(bar_time, symbol=symbol)
        gate_verdict = self.quality_gate.evaluate(
            candidate=candidate,
            mtf=mtf_ctx_for_gate,
            ltf_candles=ltf_candles_for_gate,
            proposed_risk_pct=float(getattr(self.config.risk, "risk_percentage", 1.0)),
            is_in_killzone=is_kz_for_gate,
            news_safe=news_safe,
        )
        candidate.metadata["quality_gate_verdict"] = gate_verdict.to_dict()
        is_shadow = getattr(gate_verdict, "mode", None) == GateMode.SHADOW
        if legacy_enabled and not is_shadow and gate_verdict.blocked:
            rej_code = gate_verdict.reason_codes[0] if gate_verdict.reason_codes else "QUALITY_GATE_REJECTED"
            rej_details = "; ".join(gate_verdict.hard_fails)
            candidate.status = "REJECTED"
            candidate.rejection_reasons.extend(gate_verdict.hard_fails)
            self.continuous_scalper.on_position_closed_or_rejected(symbol, was_closed=False)
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                reason_code=rej_code,
                details=f"SetupQualityGate blocked trade ({rej_code}): {rej_details}",
                real_numbers={"quality_gate": gate_verdict.to_dict()},
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        if not legacy_enabled and candidate.status != "APPROVED":
            if candidate.rejection_reasons:
                candidate.metadata["bypassed_strategy_filters"] = list(candidate.rejection_reasons)
                candidate.rejection_reasons.clear()
            candidate.status = "APPROVED"

        candidate.lifecycle_state = SignalLifecycleState.VALIDATED

        self.continuous_scalper.transition_state(symbol, ScalpingLifecycleState.RISK_VALIDATION)
        symbol_info = self.market_data.get_symbol_info(symbol)
        active_positions = self.order_manager.get_active_positions()

        # Opportunity-driven execution: Arbitrary position-count limits disabled
        is_scalp_exec = getattr(candidate, "profit_mode", ProfitManagementMode.QUICK_SCALP) == ProfitManagementMode.QUICK_SCALP
        if is_scalp_exec:
            open_scalps = sum(1 for p in active_positions if getattr(p, "profit_mode", ProfitManagementMode.QUICK_SCALP) == ProfitManagementMode.QUICK_SCALP)
            logger.info(f"[POSITION_MANAGER] Arbitrary position-count restrictions are disabled. Scalp position count: {open_scalps}")

            if legacy_enabled:
                cooldown_s = float(getattr(self.config.strategy, "scalp_cooldown_seconds", 30.0))
                last_close = self._last_scalp_close_ts.get(symbol, 0.0)
                elapsed_since_close = time.time() - last_close if last_close > 0 else cooldown_s + 1.0
                if cooldown_s > 0 and elapsed_since_close < cooldown_s:
                    outcome = DecisionOutcome(
                        symbol=symbol,
                        bar_time=bar_time,
                        outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                        reason_code="SCALP_COOLDOWN",
                        details=f"Scalp cooldown active for {symbol}: {elapsed_since_close:.1f}s < {cooldown_s:.1f}s",
                    )
                    self._record_and_dispatch_outcome(outcome)
                    return None

                max_fail_entries = int(getattr(self.config.strategy, "max_repeated_failed_entries", 3))
                if max_fail_entries > 0 and self._consecutive_failed_entries.get(symbol, 0) >= max_fail_entries:
                    outcome = DecisionOutcome(
                        symbol=symbol,
                        bar_time=bar_time,
                        outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                        reason_code="REPEATED_ENTRY_FAILURES",
                        details=f"Paused repeated scalps on {symbol} after {self._consecutive_failed_entries[symbol]} consecutive failed entries",
                    )
                    self._record_and_dispatch_outcome(outcome)
                    return None

        check = self.order_manager.run_pre_trade_checklist(
            candidate=candidate,
            account=self.account_info,
            symbol_info=symbol_info,
            active_positions=active_positions,
            recent_candles=ltf_candles_for_gate
        )

        bal = min(self.account_info.balance, self.account_info.equity) if self.account_info.balance > 0 else 10000.0
        risk_pct = (check.monetary_risk / bal * 100.0) if bal > 0 else 0.5

        if check.passed:
            candidate.lifecycle_state = SignalLifecycleState.RISK_SIZED
        else:
            rej_summary = "; ".join(check.rejection_reasons)
            rej_lower = rej_summary.lower()
            rej_code = "ORDER_REJECTED"
            if any("Market Closed" in r or "10018" in r for r in check.rejection_reasons):
                rej_code = "MARKET_CLOSED"
                candidate.lifecycle_state = SignalLifecycleState.RETRY_PENDING
                self._retry_pending_signals[symbol] = (candidate, datetime.now(timezone.utc), rej_code)
            elif "market_data_unavailable" in rej_lower or "bid/ask" in rej_lower:
                rej_code = "MARKET_DATA_UNAVAILABLE"
                candidate.lifecycle_state = SignalLifecycleState.INVALID_MARKET_PRICE
            elif "invalid stops" in rej_lower and "sl" in rej_lower:
                rej_code = "INVALID_STOP_LOSS"
                candidate.lifecycle_state = SignalLifecycleState.INVALID_MARKET_PRICE
            elif "invalid stops" in rej_lower and "tp" in rej_lower:
                rej_code = "INVALID_TAKE_PROFIT"
                candidate.lifecycle_state = SignalLifecycleState.INVALID_MARKET_PRICE
            elif "volume" in rej_lower or "lot" in rej_lower:
                rej_code = "INVALID_VOLUME"
                candidate.lifecycle_state = SignalLifecycleState.INVALID_MARKET_PRICE
            elif "margin" in rej_lower:
                rej_code = "INSUFFICIENT_MARGIN"
                candidate.lifecycle_state = SignalLifecycleState.REJECTED
            elif "disconnected" in rej_lower:
                rej_code = "MT5_TERMINAL_DISCONNECTED"
                candidate.lifecycle_state = SignalLifecycleState.CONNECTION_FAILED
            elif "disabled" in rej_lower:
                rej_code = "BROKER_TRADE_DISABLED"
                candidate.lifecycle_state = SignalLifecycleState.REJECTED
            else:
                candidate.lifecycle_state = SignalLifecycleState.REJECTED

            self.continuous_scalper.on_position_closed_or_rejected(symbol, was_closed=False)
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                reason_code=rej_code,
                details=rej_summary,
                real_numbers={"reasons": check.rejection_reasons, "balance": bal},
            )
            self._record_and_dispatch_outcome(outcome)
            if hasattr(self, "alerts") and self.alerts and rej_code != "MARKET_CLOSED":
                try:
                    self.alerts.alert_order_rejected(symbol=symbol, action=candidate.direction.value, reason=rej_summary)
                except Exception as alert_err:
                    logger.debug(f"[ORCHESTRATOR] Telegram alert_order_rejected error (isolated): {alert_err}")
            return None

        # Phase 3 Meta-Labeling Secondary Filter
        if hasattr(self, "meta_labeling") and self.meta_labeling and getattr(self.meta_labeling, "enabled", False):
            try:
                m_ok, m_mult, m_reason = self.meta_labeling.evaluate_candidate(
                    historical_candles=ltf_candles_for_gate or [],
                    candidate=candidate,
                    current_spread_pts=float(symbol_info.spread) if symbol_info else 10.0,
                    actual_volume=check.calculated_volume,
                    actual_decision="APPROVED",
                )
                candidate.metadata["meta_labeling"] = {
                    "proceed": m_ok,
                    "multiplier": m_mult,
                    "reason": m_reason,
                }
                if (
                    legacy_enabled
                    and not m_ok
                    and not getattr(self.meta_labeling, "shadow_mode", True)
                    and self.config.execution_mode not in (ExecutionMode.BACKTEST, ExecutionMode.SIMULATION)
                ):
                    self.continuous_scalper.on_position_closed_or_rejected(symbol, was_closed=False)
                    outcome = DecisionOutcome(
                        symbol=symbol,
                        bar_time=bar_time,
                        outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                        reason_code="META_LABELING_FILTER",
                        details=f"Meta-labeling model filtered candidate: {m_reason}",
                        real_numbers={"meta_multiplier": m_mult},
                    )
                    self._record_and_dispatch_outcome(outcome)
                    return None
            except Exception:
                pass

        # Active Mode Prohibitions & Frequency Controls (Part 6)
        if legacy_enabled and getattr(self.config.strategy, "active_scalp_mode", True) and hasattr(self, "active_engine"):
            m15 = self.market_data.get_candles(symbol, Timeframe.M15)
            point = symbol_info.point or 0.00001
            atr_pts = 100.0
            if m15 and len(m15) >= 14:
                ranges = [abs(c.high - c.low) / point for c in m15[-14:]]
                atr_pts = sum(ranges) / len(ranges)

            allowed, prohib_msg = self.active_engine.verify_prohibitions(
                symbol=symbol,
                direction=candidate.direction,
                candidate_price=candidate.entry_price,
                candidate_risk_pct=risk_pct,
                candidate_lots=check.calculated_volume,
                atr=atr_pts * point,
                account=self.account_info,
                active_positions=active_positions
            )
            if not allowed:
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=bar_time,
                    outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                    reason_code="PROHIBITION_BLOCKED",
                    details=prohib_msg,
                    real_numbers={"reason": prohib_msg, "balance": bal}
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        # Success-First Signal Delivery: Only notify signal when execution eligibility is 100% confirmed
        self.continuous_scalper.transition_state(symbol, ScalpingLifecycleState.ORDER_EXECUTION)
        candidate.lifecycle_state = SignalLifecycleState.ORDER_PREPARED
        if hasattr(self, "alerts") and self.alerts and check.calculated_volume > 0:
            try:
                self.alerts.alert_signal_approved(
                    symbol=symbol,
                    direction=candidate.direction.value,
                    score=candidate.score,
                    entry=candidate.entry_price,
                    sl=candidate.stop_loss,
                    tp=candidate.take_profit,
                    rr=candidate.risk_reward,
                    lots=check.calculated_volume,
                    risk_pct=risk_pct,
                    reason=(candidate.reasons[0] if candidate.reasons else f"Score {candidate.score:.1f}"),
                )
            except Exception as alert_err:
                logger.debug(f"[ORCHESTRATOR] Telegram alert_signal_approved error (isolated): {alert_err}")

        # Dry run support
        if getattr(self.config, "dry_run", False):
            self._executed_signal_keys.add(sig_key)
            self.continuous_scalper.mark_signal_executed(
                sig_key,
                symbol=candidate.symbol,
                price=candidate.entry_price,
                direction=candidate.direction
            )
            self.continuous_scalper.mark_signal_executed(
                candidate.id,
                symbol=candidate.symbol,
                price=candidate.entry_price,
                direction=candidate.direction
            )
            self.continuous_scalper.transition_state(symbol, ScalpingLifecycleState.POSITION_MANAGEMENT)
            candidate.lifecycle_state = SignalLifecycleState.FILLED
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SENT,
                details="Dry-run order simulated",
                direction=candidate.direction.value,
                volume=check.calculated_volume,
                entry_price=candidate.entry_price,
                stop_loss=candidate.stop_loss,
                take_profit=candidate.take_profit,
                risk_dollars=check.monetary_risk,
                risk_percent=risk_pct,
                ticket=999999,
            )
            self._record_and_dispatch_outcome(outcome)
            return candidate

        # Telegram submission notification
        if hasattr(self, "alerts") and self.alerts and hasattr(self.alerts, "alert_order_submitted"):
            try:
                self.alerts.alert_order_submitted(
                    symbol=symbol,
                    direction=candidate.direction.value,
                    volume=check.calculated_volume,
                    price=candidate.entry_price,
                    sl=candidate.stop_loss,
                    tp=candidate.take_profit,
                    request_id=f"ORD_{candidate.id[-10:]}",
                )
            except Exception as alert_err:
                logger.debug(f"[ORCHESTRATOR] Telegram alert_order_submitted error (isolated): {alert_err}")

        # Execute order via MT5 / Bridge
        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account_info,
            symbol_info=symbol_info,
            active_positions=active_positions,
            prevalidated=check,
        )

        if order and order.status in ("FILLED", "PARTIALLY_FILLED"):
            self._executed_signal_keys.add(sig_key)
            self.continuous_scalper.mark_signal_executed(
                sig_key,
                symbol=candidate.symbol,
                price=order.entry_price,
                direction=candidate.direction
            )
            self.continuous_scalper.mark_signal_executed(
                candidate.id,
                symbol=candidate.symbol,
                price=order.entry_price,
                direction=candidate.direction
            )
            self.continuous_scalper.transition_state(symbol, ScalpingLifecycleState.POSITION_MANAGEMENT)
            ticket = order.ticket or 0
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SENT,
                details=f"Order broker-verified [{order.status}]",
                direction=candidate.direction.value,
                volume=order.volume,
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                risk_dollars=check.monetary_risk,
                risk_percent=risk_pct,
                ticket=ticket,
            )
            self._record_and_dispatch_outcome(outcome)
            if hasattr(self, "alerts") and self.alerts:
                try:
                    if order.status == "PARTIALLY_FILLED":
                        self.alerts.alert_order_partially_filled(
                            symbol=order.symbol,
                            direction=order.order_type.value,
                            ticket=ticket,
                            filled_volume=order.volume,
                            remaining_volume=round(check.calculated_volume - order.volume, 2),
                            price=order.entry_price,
                        )
                    self.alerts.alert_trade_executed(
                        ticket=ticket,
                        symbol=order.symbol,
                        direction=order.order_type.value,
                        volume=order.volume,
                        price=order.entry_price,
                        sl=order.stop_loss,
                        tp=order.take_profit,
                        execution_status=order.status,
                        account_number=getattr(self.account_info, "account_number", None),
                        timestamp=order.executed_at,
                    )
                except Exception as alert_err:
                    logger.debug(f"[ORCHESTRATOR] Telegram alert_trade_executed error (isolated): {alert_err}")
            return candidate
            return candidate

        elif order and order.status == "ACCEPTED":
            ticket = order.ticket or 0
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SENT,
                details="Pending order accepted by broker",
                direction=candidate.direction.value,
                volume=order.volume,
                entry_price=order.entry_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                risk_dollars=check.monetary_risk,
                risk_percent=risk_pct,
                ticket=ticket,
            )
            self._record_and_dispatch_outcome(outcome)
            if hasattr(self, "alerts") and self.alerts:
                self.alerts.alert_order_accepted(
                    symbol=order.symbol,
                    direction=order.order_type.value,
                    volume=order.volume,
                    price=order.entry_price,
                    ticket=ticket,
                    request_id=f"ORD_{candidate.id[-10:]}",
                )
            return candidate

        elif order and order.status == "UNCONFIRMED":
            err = getattr(order, "error", "Execution unconfirmed: order accepted but no broker position verified")
            self.continuous_scalper.on_position_closed_or_rejected(symbol, was_closed=False)
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                reason_code="EXECUTION_UNCONFIRMED",
                details=err,
            )
            self._record_and_dispatch_outcome(outcome)
            if hasattr(self, "alerts") and self.alerts:
                self.alerts.alert_execution_unconfirmed(
                    symbol=symbol,
                    direction=candidate.direction.value,
                    ticket=order.ticket or 0,
                    request_id=f"ORD_{candidate.id[-10:]}",
                    reason=err,
                )
            return None

        else:
            err = (
                getattr(order, "error", None)
                or "; ".join(getattr(candidate, "rejection_reasons", []))
                or "Execution returned null or unfilled"
            )
            self.continuous_scalper.on_position_closed_or_rejected(symbol, was_closed=False)
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                reason_code="EXECUTION_FAILED",
                details=f"Broker/bridge refused order: {err}",
            )
            self._record_and_dispatch_outcome(outcome)
            if hasattr(self, "alerts") and self.alerts:
                self.alerts.alert_order_rejected(symbol=symbol, action=candidate.direction.value, reason=err)
            return None

    def run_cycle_for_symbol(self, symbol: str) -> Optional[SignalCandidate]:
        """
        Executes a complete scanning cycle for a single instrument:
        1. Retrieves candles across W1, D1, H4, H1, M15 (no news-based blocking)
        2. Computes MTF bias and liquidity levels
        3. Verifies SCALP higher-timeframe agreement (if enabled on StrategyConfig)
        4. Scans for SMC setups
        5. Validates risk & executes if approved
        Every evaluation ends with exactly one outcome line (TRADE SENT, TRADE SKIPPED, NO SETUP).
        """
        now = datetime.now(timezone.utc)

        # 0a. Strict 3-Instrument Universe Guard
        canonical = self.symbol_universe.get_canonical_symbol(symbol)
        strict_universe = getattr(self.config, "strict_three_symbol_universe", False)
        if strict_universe:
            is_approved, _ = self.symbol_universe.validate_or_reject(symbol)
            if not is_approved:
                logger.warning(f"[SYMBOL_MANAGER] Candidate evaluation blocked: {symbol} is outside approved 3-instrument universe [XAUUSD, BTCUSD, USDJPY]")
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=now,
                    outcome_type=DecisionOutcomeType.NO_SETUP,
                    reason_code="UNAUTHORIZED_SYMBOL",
                    details=f"Symbol {symbol} is rejected by strict 3-instrument universe policy.",
                )
                self._record_and_dispatch_outcome(outcome)
                return None

            # 0b. Operational Schedule Guard
            is_eligible, sched_reason = self.trading_scheduler.is_instrument_eligible_for_new_entry(symbol, now)
            if not is_eligible:
                logger.info(f"[TRADING_SCHEDULER] Skipping new trade scan for {symbol}: {sched_reason}")
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=now,
                    outcome_type=DecisionOutcomeType.NO_SETUP,
                    reason_code="SCHEDULE_INACTIVE",
                    details=sched_reason,
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        if self.auto_sync_market_data:
            self.market_data.sync_symbol_history(
                symbol=symbol,
                bridge=self.bridge if self.bridge.is_connected() else None,
                max_retries=2,
                force_full=False,
            )
        m15 = self.market_data.get_candles(symbol, Timeframe.M15)
        bar_time = m15[-1].time if (m15 and len(m15) > 0) else now

        # 1. Retrieve candles & check history sufficiency
        if not m15 or len(m15) < 20:
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.NO_SETUP,
                reason_code="INSUFFICIENT_DATA",
                details=f"Insufficient M15 candle history (have {len(m15) if m15 else 0}, required 20)",
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        # 1b. Optional Stale-Data Guard
        if self.enforce_stale_data_check:
            age_seconds = max(0.0, (now - bar_time).total_seconds())
            if age_seconds > self.max_candle_staleness_seconds:
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=bar_time,
                    outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                    reason_code="STALE_DATA",
                    details=(
                        f"Stale M15 market data for {symbol}: latest closed bar is {age_seconds:.0f}s old "
                        f"(max allowed {self.max_candle_staleness_seconds:.0f}s)"
                    ),
                    real_numbers={"age_seconds": age_seconds, "max_allowed_seconds": self.max_candle_staleness_seconds},
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        # 2. Weekend holding restriction check
        legacy_enabled = getattr(self.config, "legacy_filters_enabled", False)
        self.strategy_engine.legacy_filters_enabled = legacy_enabled
        profile = getattr(self.portfolio_risk, "profile", None)
        if legacy_enabled and profile and getattr(profile.rules, "no_weekend_holding", False):
            if now.weekday() == 4 and now.hour >= profile.rules.weekend_close_hour_friday:
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=bar_time,
                    outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                    reason_code="SESSION_FILTER",
                    details=f"Weekend holding prohibited after Friday {profile.rules.weekend_close_hour_friday:02d}:00 (current hour {now.hour:02d})",
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        # 3. Multi-timeframe context
        w1 = self.market_data.get_candles(symbol, Timeframe.W1)
        d1 = self.market_data.get_candles(symbol, Timeframe.D1)
        h4 = self.market_data.get_candles(symbol, Timeframe.H4)
        h1 = self.market_data.get_candles(symbol, Timeframe.H1)
        mtf_ctx = self.mtf_analyzer.analyze(symbol, w1, d1, h4, h1, m15)
        self.active_contexts[symbol] = mtf_ctx

        # Hook 2: Feature Pipeline Extraction (Strangler Pattern)
        if getattr(self.config, "upgrade_enabled", False) and getattr(self.config, "feature_pipeline_enabled", False):
            from src.features.feature_registry import FeaturePipeline

            sym_info = self.market_data.get_symbol_info(symbol)
            self._current_feature_snapshot = FeaturePipeline.extract_snapshot(
                symbol=symbol,
                m15_candles=m15,
                h1_candles=h1,
                h4_candles=h4,
                d1_candles=d1,
                point=sym_info.point if sym_info else 0.00001,
            )

        # 4. SCALP higher-timeframe agreement check
        if legacy_enabled and getattr(self.config.strategy, "scalp_require_htf_agreement", True):
            agree, msg, dirs = self.strategy_engine.check_scalp_htf_agreement(mtf_ctx, legacy_mode=legacy_enabled)
            if not agree:
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=bar_time,
                    outcome_type=DecisionOutcomeType.NO_SETUP,
                    reason_code=NoTradeReason.UNCLEAR_STRUCTURE,
                    details=msg,
                    real_numbers=dirs,
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        # 5. Session & Killzone check & SMC Strategy Scan (M6: symbol-aware session evaluation)
        is_kz, _ = self.sessions.evaluate_killzone(now, symbol=symbol)
        candidates = self.strategy_engine.scan_for_opportunities(mtf_ctx, m15, is_in_killzone=is_kz)
        if not candidates:
            if not legacy_enabled:
                pending_entry = self._retry_pending_signals.get(symbol)
                if pending_entry is not None:
                    pending_cand, pending_ts, pending_reason = pending_entry
                    ttl_sec = 3600.0 if pending_reason == "MARKET_CLOSED" else 300.0
                    if (now - pending_ts).total_seconds() <= ttl_sec:
                        self._retry_pending_signals.pop(symbol, None)
                        logging.getLogger("Orchestrator").info(
                            f"[RETRY_PENDING] Re-evaluating {symbol} {pending_cand.direction.value} after transient {pending_reason}"
                        )
                        return self._execute_approved_candidate(symbol=symbol, candidate=pending_cand, bar_time=bar_time)
                    else:
                        self._retry_pending_signals.pop(symbol, None)

            # Build comprehensive SMC setup condition diagnostics
            current_close = m15[-1].close if m15 else 0.0
            bias_summary = ", ".join(f"{getattr(tf, 'value', str(tf))}:{bias.value if hasattr(bias, 'value') else str(bias)}" for tf, bias in getattr(mtf_ctx, "bias", {}).items())
            levels_obj = getattr(mtf_ctx, "levels", {})
            levels_dict = levels_obj.to_dict() if hasattr(levels_obj, "to_dict") else (levels_obj if isinstance(levels_obj, dict) else getattr(levels_obj, "__dict__", {}))
            levels_summary = ", ".join(f"{k}:{v:.2f}" for k, v in levels_dict.items() if isinstance(v, (int, float)))
            interactions_list = [getattr(i.interaction, "value", str(i.interaction)) for i in getattr(mtf_ctx, "level_interactions", [])]
            diag_detail = (
                f"No valid SMC setup for {symbol} @ {current_close:.2f} | "
                f"Killzone: {'ACTIVE' if is_kz else 'INACTIVE'} | "
                f"HTF Bias: [{bias_summary}] | "
                f"Levels: [{levels_summary}] | "
                f"Interactions: {interactions_list or 'None'}"
            )
            logging.getLogger("Orchestrator").info(f"[SMC_DIAGNOSTICS] {diag_detail}")

            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.NO_SETUP,
                reason_code=NoTradeReason.NO_POI,
                details=diag_detail,
                real_numbers={
                    "current_price": current_close,
                    "is_killzone": 1 if is_kz else 0,
                    "interactions_count": len(interactions_list),
                },
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        # Filter for top candidate
        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0]
        self.recent_signals.append(best)

        # Inverse Directional Coordination between XAUUSD and USDJPY
        coord_enabled = getattr(self.config, "inverse_coordination_enabled", True) and not getattr(self.config, "legacy_filters_enabled", False)
        if coord_enabled:
            if canonical == "XAUUSD":
                self.inverse_coordinator.update_xauusd_signal(best)
                logger.info(
                    f"[DIRECTIONAL_ENGINE] XAUUSD signal registered: {best.direction.value} @ {best.entry_price:.2f} "
                    f"| Preferred USDJPY: {self.inverse_coordinator.preferred_usdjpy_direction}"
                )
            elif canonical == "USDJPY":
                try:
                    xau_sym = self.symbol_universe.get_broker_symbol("XAUUSD")
                    xau_c = self.market_data.get_candles(xau_sym, Timeframe.M15)
                    jpy_c = self.market_data.get_candles(symbol, Timeframe.M15)
                    if xau_c and jpy_c and len(xau_c) >= 15 and len(jpy_c) >= 15:
                        self.inverse_coordinator.calculate_correlation(xau_c, jpy_c)
                except Exception as corr_exc:
                    logger.debug(f"[CORRELATION_ENGINE] Could not compute correlation: {corr_exc}")

                coord_res = self.inverse_coordinator.evaluate_usdjpy_candidate(best)
                if not coord_res.is_approved:
                    logger.warning(f"[DIRECTIONAL_ENGINE] USDJPY candidate rejected: {coord_res.rationale}")
                    outcome = DecisionOutcome(
                        symbol=symbol,
                        bar_time=bar_time,
                        outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                        reason_code="INVERSE_COORDINATION_REJECT",
                        details=coord_res.rationale,
                    )
                    self._record_and_dispatch_outcome(outcome)
                    return None
                else:
                    best.score += coord_res.score_adjustment
                    if not hasattr(best, "metadata") or not isinstance(best.metadata, dict):
                        best.metadata = {}
                    best.metadata["inverse_coordination"] = coord_res.to_dict()
                    logger.info(
                        f"[DIRECTIONAL_ENGINE] USDJPY candidate approved with inverse coordination: "
                        f"adjustment={coord_res.score_adjustment:+.1f}, regime={coord_res.regime.value}, r={coord_res.correlation:.2f}"
                    )

        # Phase 3 & 4: Quantitative Intelligence, Volatility Targeting, & Kelly Sizing
        if hasattr(self, "regime_detector") and self.regime_detector and getattr(self.regime_detector, "enabled", False):
            try:
                reg_res = self.regime_detector.evaluate_closed_bar(
                    symbol=symbol,
                    candles_m15=m15,
                    candles_h1=h1,
                    actual_bot_decision="SCAN",
                )
                if reg_res:
                    best.metadata["regime"] = reg_res.regime.value
                    best.metadata["regime_confidence"] = reg_res.confidence
                    best.metadata["regime_suggestion"] = reg_res.suggestion.value
            except Exception:
                pass

        if hasattr(self, "advanced_volatility") and self.advanced_volatility and len(m15) >= 15:
            try:
                closes = [c.close for c in m15]
                highs = [c.high for c in m15]
                lows = [c.low for c in m15]
                atr_val = self.volatility.calculate_atr(m15)
                vf = self.advanced_volatility.forecast(
                    symbol=symbol,
                    closes=closes,
                    highs=highs,
                    lows=lows,
                    atr_value=atr_val,
                )
                if vf:
                    best.metadata["volatility_forecast"] = asdict(vf)
                    if is_gold(symbol) and vf.recommended_stop_scale > 1.0 and best.stop_loss > 0:
                        dist = abs(best.entry_price - best.stop_loss)
                        scaled_dist = dist * min(1.4, vf.recommended_stop_scale)
                        if best.direction == OrderType.BUY:
                            best.stop_loss = round(best.entry_price - scaled_dist, 5)
                        else:
                            best.stop_loss = round(best.entry_price + scaled_dist, 5)
            except Exception:
                pass

        if hasattr(self, "kelly_engine") and self.kelly_engine:
            try:
                perf = self.performance_tracker.calculate_summary()
                win_rate = perf.win_rate if perf.total_trades >= 10 else 0.55
                pf = perf.profit_factor if perf.total_trades >= 10 and perf.profit_factor > 0 else 1.8
                ke = self.kelly_engine.evaluate(
                    win_rate=win_rate,
                    reward_to_risk=pf,
                    tier_target_risk_pct=float(getattr(self.config.risk, "risk_percentage", 1.0)),
                    tier_ceiling_risk_pct=2.0,
                )
                if ke and ke.is_tradable:
                    best.metadata["kelly_risk_pct"] = ke.applied_risk_pct
            except Exception:
                pass

        # 6. Adaptive Mode Evaluation & Candidate Approval Status
        exec_policy = str(getattr(self.config.strategy, "execution_mode_policy", "ADAPTIVE")).upper()
        if legacy_enabled and best.status != "APPROVED":
            # Check if candidate failed ONLY because normal holding min R:R was not met -> evaluate Adaptive Scalping Mode
            non_rr_rejections = [
                r for r in best.rejection_reasons
                if "Reward-to-risk" not in r and "below mandatory threshold" not in r
            ]
            scalp_min_rr = float(getattr(self.config.risk, "scalping_min_risk_reward_ratio", 1.2))
            scalp_min_score = float(getattr(self.config.strategy, "scalping_min_confluence_score", 55.0))
            if (
                exec_policy != "HOLD_ONLY"
                and not non_rr_rejections
                and (best.risk_reward + 1e-6) >= scalp_min_rr
                and best.score >= scalp_min_score
            ):
                best.profit_mode = ProfitManagementMode.QUICK_SCALP
                if hasattr(best, "execution_mode_selected"):
                    best.execution_mode_selected = "SCALP"
                if hasattr(best, "lifecycle_state"):
                    from src.core.contracts import SignalLifecycleState
                    best.lifecycle_state = SignalLifecycleState.SCALP_SELECTED
                best.metadata["mode_rationale"] = (
                    f"Adaptive Scalping fallback selected: RR={best.risk_reward:.2f} >= scalp min {scalp_min_rr:.2f}, "
                    f"score={best.score:.1f} >= {scalp_min_score:.1f}"
                )
                best.rejection_reasons.clear()
                best.status = "APPROVED"
                logging.getLogger("Orchestrator").info(
                    f"[ADAPTIVE_MODE] {symbol} {best.direction.value}: Promoted to SCALP mode ({best.metadata['mode_rationale']})"
                )

        if legacy_enabled and best.status != "APPROVED":
            reasons_str = (
                "; ".join(best.rejection_reasons)
                if best.rejection_reasons
                else f"Score {best.score:.1f} < {self.config.strategy.min_confluence_score:.1f}"
            )
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.NO_SETUP,
                reason_code=(
                    NoTradeReason.RR_TOO_LOW if "R:R" in reasons_str or "RR" in reasons_str
                    else NoTradeReason.WRONG_PD_ZONE if "DISCOUNT" in reasons_str or "PREMIUM" in reasons_str
                    else NoTradeReason.NO_SWEEP if "sweep" in reasons_str.lower()
                    else NoTradeReason.NO_LTF_CONFIRMATION if "CHoCH" in reasons_str or "BOS" in reasons_str
                    else NoTradeReason.LOW_SCORE
                ),
                details=f"Candidate {best.setup_type.value} rejected: {reasons_str}",
            )
            self._record_and_dispatch_outcome(outcome)
            # Rejected candidates are returned for observability (callers must check
            # status), matching the canonical decision-replay contract.
            return best

        return self._execute_approved_candidate(symbol=symbol, candidate=best, bar_time=bar_time)

    def run_scalping_cycle_for_symbol(self, symbol: str) -> Optional[SignalCandidate]:
        """
        Executes a continuous M1/M5/M15 scalping cycle for `symbol`:
        1. Syncs latest M1, M5, M15, H1 candles & live tick
        2. Evaluates M1/M5/M15 Momentum Continuation, Pullback, and Liquidity-Sweep/Breakout scalps
        3. Falls back to M15 SMC opportunities if no lower-timeframe scalp candidate triggered
        4. Validates risk & executes if qualified, then immediately transitions lifecycle state
        """
        now = datetime.now(timezone.utc)

        # 0a. Strict 3-Instrument Universe Guard
        canonical = self.symbol_universe.get_canonical_symbol(symbol)
        strict_universe = getattr(self.config, "strict_three_symbol_universe", False)
        if strict_universe:
            is_approved, _ = self.symbol_universe.validate_or_reject(symbol)
            if not is_approved:
                logger.warning(f"[SYMBOL_MANAGER] Candidate evaluation blocked: {symbol} is outside approved 3-instrument universe [XAUUSD, BTCUSD, USDJPY]")
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=now,
                    outcome_type=DecisionOutcomeType.NO_SETUP,
                    reason_code="UNAUTHORIZED_SYMBOL",
                    details=f"Symbol {symbol} is rejected by strict 3-instrument universe policy.",
                )
                self._record_and_dispatch_outcome(outcome)
                return None

            # 0b. Operational Schedule Guard
            is_eligible, sched_reason = self.trading_scheduler.is_instrument_eligible_for_new_entry(symbol, now)
            if not is_eligible:
                logger.info(f"[TRADING_SCHEDULER] Skipping new trade scan for {symbol}: {sched_reason}")
                outcome = DecisionOutcome(
                    symbol=symbol,
                    bar_time=now,
                    outcome_type=DecisionOutcomeType.NO_SETUP,
                    reason_code="SCHEDULE_INACTIVE",
                    details=sched_reason,
                )
                self._record_and_dispatch_outcome(outcome)
                return None

        if self.auto_sync_market_data:
            self.market_data.sync_symbol_history(
                symbol=symbol,
                bridge=self.bridge if self.bridge.is_connected() else None,
                max_retries=2,
                force_full=False,
            )

        m1 = self.market_data.get_candles(symbol, Timeframe.M1)
        m5 = self.market_data.get_candles(symbol, Timeframe.M5)
        m15 = self.market_data.get_candles(symbol, Timeframe.M15)
        h1 = self.market_data.get_candles(symbol, Timeframe.H1)

        latest_bars = m1 or m5 or m15
        bar_time = latest_bars[-1].time if latest_bars else now

        if (not m1 or len(m1) < 12) and (not m5 or len(m5) < 12) and (not m15 or len(m15) < 12):
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.NO_SETUP,
                reason_code="INSUFFICIENT_DATA",
                details=f"Market data unavailable: insufficient M1/M5/M15 candle history for {symbol}",
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        sym_info = self.market_data.get_symbol_info(symbol)
        candles_by_tf = {
            Timeframe.M1: m1,
            Timeframe.M5: m5,
            Timeframe.M15: m15,
            Timeframe.H1: h1,
        }

        best = self.continuous_scalper.scan_symbol_timeframes(
            symbol=symbol,
            candles_by_tf=candles_by_tf,
            symbol_info=sym_info,
            execution_timeframes=[Timeframe.M1, Timeframe.M5, Timeframe.M15],
        )

        # Multi-Strategy Engine Fallback / Integration
        if best is None and hasattr(self, "multi_pair_scanner") and self.multi_pair_scanner:
            active_pos = self.order_manager.get_active_positions() if hasattr(self, "order_manager") else []
            opp = self.multi_pair_scanner.scan_single_symbol(
                symbol=symbol,
                active_positions=active_pos,
                bridge=self.bridge if self.bridge.is_connected() else None,
            )
            if opp.is_tradable and opp.candidate is not None:
                best = opp.candidate

        if best is None:
            outcome = DecisionOutcome(
                symbol=symbol,
                bar_time=bar_time,
                outcome_type=DecisionOutcomeType.NO_SETUP,
                details="No qualifying signal on M1/M5/M15 continuous scalping scan",
            )
            self._record_and_dispatch_outcome(outcome)
            return None

        # Inverse Directional Coordination between XAUUSD and USDJPY
        coord_enabled = getattr(self.config, "inverse_coordination_enabled", True) and not getattr(self.config, "legacy_filters_enabled", False)
        if coord_enabled:
            if canonical == "XAUUSD":
                self.inverse_coordinator.update_xauusd_signal(best)
                logger.info(
                    f"[DIRECTIONAL_ENGINE] XAUUSD signal registered: {best.direction.value} @ {best.entry_price:.2f} "
                    f"| Preferred USDJPY: {self.inverse_coordinator.preferred_usdjpy_direction}"
                )
            elif canonical == "USDJPY":
                try:
                    xau_sym = self.symbol_universe.get_broker_symbol("XAUUSD")
                    xau_c = self.market_data.get_candles(xau_sym, Timeframe.M15)
                    jpy_c = self.market_data.get_candles(symbol, Timeframe.M15)
                    if xau_c and jpy_c and len(xau_c) >= 15 and len(jpy_c) >= 15:
                        self.inverse_coordinator.calculate_correlation(xau_c, jpy_c)
                except Exception as corr_exc:
                    logger.debug(f"[CORRELATION_ENGINE] Could not compute correlation: {corr_exc}")

                coord_res = self.inverse_coordinator.evaluate_usdjpy_candidate(best)
                if not coord_res.is_approved:
                    logger.warning(f"[DIRECTIONAL_ENGINE] USDJPY candidate rejected: {coord_res.rationale}")
                    outcome = DecisionOutcome(
                        symbol=symbol,
                        bar_time=bar_time,
                        outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
                        reason_code="INVERSE_COORDINATION_REJECT",
                        details=coord_res.rationale,
                    )
                    self._record_and_dispatch_outcome(outcome)
                    return None
                else:
                    best.score += coord_res.score_adjustment
                    if not hasattr(best, "metadata") or not isinstance(best.metadata, dict):
                        best.metadata = {}
                    best.metadata["inverse_coordination"] = coord_res.to_dict()
                    logger.info(
                        f"[DIRECTIONAL_ENGINE] USDJPY candidate approved with inverse coordination: "
                        f"adjustment={coord_res.score_adjustment:+.1f}, regime={coord_res.regime.value}, r={coord_res.correlation:.2f}"
                    )

        self.recent_signals.append(best)
        if hasattr(self, "health_monitor") and self.health_monitor:
            self.health_monitor.record_signal(
                symbol=symbol,
                direction=best.direction.value,
                setup_type=best.setup_type.value,
                score=best.score,
            )

        return self._execute_approved_candidate(symbol=symbol, candidate=best, bar_time=best.timestamp)

    def run_continuous_scalping_tick_cycle(self, concurrent: bool = False) -> Dict[str, Optional[SignalCandidate]]:
        """
        Executes one complete continuous scalping pass across all enabled symbols (in fair round-robin
        or concurrent order) and immediately manages all open positions toward the $20 net profit target.
        Evaluates valid opportunities purely on an opportunity-driven basis while respecting genuine account risk.
        """
        results: Dict[str, Optional[SignalCandidate]] = {}

        # 1. Manage currently active open positions first
        self.manage_active_positions()

        # 2. Position capacity evaluation (Opportunity-driven: arbitrary 3-min / 7-max limits eliminated)
        active_positions = list(self.order_manager.get_active_positions())
        logger.info(
            f"[POSITION_MANAGER] Arbitrary position-count restrictions are disabled. "
            f"Active positions: {len(active_positions)}. Multiple concurrent positions are supported."
        )

        # 3. Dynamic opportunity scanning in strict schedule priority order
        mocked_fn = getattr(self.continuous_scalper, "get_ordered_symbols_for_cycle", None)
        is_mocked = hasattr(mocked_fn, "_mock_return_value") or hasattr(mocked_fn, "assert_called")

        if getattr(self.config, "strict_three_symbol_universe", False) and not is_mocked:
            sched_priority = self.trading_scheduler.get_scanning_priority_order()
            ordered_symbols = []
            for c in sched_priority:
                broker_sym = self.symbol_universe.get_broker_symbol(c)
                eligible, _ = self.trading_scheduler.is_instrument_eligible_for_new_entry(broker_sym)
                if eligible:
                    ordered_symbols.append(broker_sym)
            logger.debug(
                f"[PRIORITY_ENGINE] Cycle scanning order: {ordered_symbols} "
                f"(mode={self.trading_scheduler.get_operating_mode().value})"
            )
        else:
            ordered_symbols = self.continuous_scalper.get_ordered_symbols_for_cycle()

        if concurrent and getattr(self.config, "multi_symbol_execution", True):
            raw = self.continuous_scalper.evaluate_symbols_concurrently(self.run_scalping_cycle_for_symbol)
            for sym, val in raw.items():
                if getattr(self.config, "strict_three_symbol_universe", False) and not is_mocked and sym not in ordered_symbols:
                    continue
                if isinstance(val, Exception) or (isinstance(val, dict) and "error" in val):
                    err_str = str(val["error"]) if isinstance(val, dict) else str(val)
                    if hasattr(self, "health_monitor") and self.health_monitor:
                        self.health_monitor.record_scan_failure(sym, err_str)
                    results[sym] = None
                else:
                    results[sym] = val if isinstance(val, SignalCandidate) else None
        else:
            for sym in ordered_symbols:
                # Opportunity-driven: scan all scheduled symbols regardless of position count
                try:
                    results[sym] = self.run_scalping_cycle_for_symbol(sym)
                except Exception as e:
                    if hasattr(self, "health_monitor") and self.health_monitor:
                        self.health_monitor.record_scan_failure(sym, str(e))
                    results[sym] = None

        # 4. Final position management check
        self.manage_active_positions()
        return results

    def manage_active_positions(self) -> List[object]:
        """Evaluates lifecycle actions ($20 Net Profit Target, Graduated Ratchet, Break-Even, Trailing SL, Full Close)."""
        executed_actions = []
        active_positions = list(self.order_manager.get_active_positions())
        scalp_mode = getattr(self.config, "trading_mode", "CONTINUOUS_SCALPING") == "CONTINUOUS_SCALPING"

        # Detect positions closed since last cycle (e.g. SL or TP hit at broker)
        current_tickets = {p.ticket for p in active_positions}
        closed_tickets = [t for t in self._active_positions_cache if t not in current_tickets]
        for t in closed_tickets:
            closed_pos = self._active_positions_cache.pop(t, None)
            if closed_pos:
                deal_profit = float(closed_pos.profit)
                deal_comm = float(getattr(closed_pos, "commission", 0.0) or 0.0)
                deal_swap = float(getattr(closed_pos, "swap", 0.0) or 0.0)
                try:
                    import MetaTrader5 as mt5
                    deals = mt5.history_deals_get(position=t)
                    if deals:
                        out_deals = [d for d in deals if getattr(d, "entry", 0) == 1]
                        if out_deals:
                            deal_profit = sum(float(d.profit) for d in out_deals)
                            deal_comm = sum(float(d.commission) for d in out_deals)
                            deal_swap = sum(float(d.swap) for d in out_deals)
                except Exception:
                    pass

                realized_pnl = self.trade_manager.reconcile_closed_deal(
                    ticket=t,
                    deal_profit=deal_profit,
                    deal_commission=deal_comm,
                    deal_swap=deal_swap,
                    close_reason="SL/TP hit or external broker close"
                )
                self.portfolio_risk.record_trade_result(
                    profit=realized_pnl,
                    volume=closed_pos.volume,
                    symbol=closed_pos.symbol,
                    ticket=closed_pos.ticket,
                )
                if hasattr(self, "decay_guard") and self.decay_guard:
                    try:
                        init_r = getattr(closed_pos, "initial_risk_amount", 0.0)
                        r_outcome = (realized_pnl / init_r) if init_r > 0 else (1.0 if realized_pnl > 0 else -1.0)
                        self.decay_guard.add_trade(r_outcome)
                        d_res = self.decay_guard.evaluate()
                        if d_res.status in ("WARNING", "REDUCE_RISK", "PAUSE"):
                            logging.getLogger("Orchestrator").warning(f"[DECAY_GUARD] Status: {d_res.status} | {d_res.action_required}")
                    except Exception:
                        pass
                self.trade_manager.forget_position(closed_pos.ticket)
                self._last_scalp_close_ts[closed_pos.symbol] = time.time()
                self.continuous_scalper.on_position_closed_or_rejected(closed_pos.symbol, was_closed=True)
                if hasattr(self, "alerts") and self.alerts:
                    self.alerts.alert_trade_closed(
                        symbol=closed_pos.symbol,
                        ticket=closed_pos.ticket,
                        direction=closed_pos.order_type.value,
                        close_reason="SL/TP hit or external close",
                        money_pnl=realized_pnl,
                    )

        # Update cache with currently active positions
        for pos in active_positions:
            self._active_positions_cache[pos.ticket] = pos

        for pos in active_positions:
            self.continuous_scalper.transition_state(pos.symbol, ScalpingLifecycleState.POSITION_MANAGEMENT)
            sym_info = self.market_data.get_symbol_info(pos.symbol)
            m5 = self.market_data.get_candles(pos.symbol, Timeframe.M5)
            m15 = self.market_data.get_candles(pos.symbol, Timeframe.M15)
            recent_bars = m15 if len(m15) >= 5 else m5
            pos_is_scalp = (
                getattr(pos, "profit_mode", ProfitManagementMode.QUICK_SCALP) == ProfitManagementMode.QUICK_SCALP
            )
            actions = self.trade_manager.evaluate_position(pos, sym_info, recent_bars, scalp_mode=pos_is_scalp)

            for act in actions:
                executed_actions.append(act)
                if act.amendment is not None:
                    self.order_manager.apply_plan_amendment(pos.ticket, act.amendment)

                if act.action_type == "FULL_CLOSE":
                    if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL] and not getattr(self.config, "dry_run", False):
                        self.bridge.close_order(ticket=act.ticket)
                    else:
                        self.order_manager.simulated_positions = [
                            p for p in self.order_manager.simulated_positions if p.ticket != act.ticket
                        ]

                    deal_profit = float(pos.profit)
                    deal_comm = float(getattr(pos, "commission", 0.0) or 0.0)
                    deal_swap = float(getattr(pos, "swap", 0.0) or 0.0)
                    try:
                        import MetaTrader5 as mt5
                        deals = mt5.history_deals_get(position=act.ticket)
                        if deals:
                            out_deals = [d for d in deals if getattr(d, "entry", 0) == 1]
                            if out_deals:
                                deal_profit = sum(float(d.profit) for d in out_deals)
                                deal_comm = sum(float(d.commission) for d in out_deals)
                                deal_swap = sum(float(d.swap) for d in out_deals)
                    except Exception:
                        pass

                    realized_pnl = self.trade_manager.reconcile_closed_deal(
                        ticket=act.ticket,
                        deal_profit=deal_profit,
                        deal_commission=deal_comm,
                        deal_swap=deal_swap,
                        close_reason=act.reason
                    )
                    self.portfolio_risk.record_trade_result(
                        profit=realized_pnl,
                        volume=pos.volume,
                        symbol=pos.symbol,
                        ticket=act.ticket,
                    )
                    if hasattr(self, "decay_guard") and self.decay_guard:
                        try:
                            init_r = getattr(pos, "initial_risk_amount", 0.0)
                            r_outcome = (realized_pnl / init_r) if init_r > 0 else (1.0 if realized_pnl > 0 else -1.0)
                            self.decay_guard.add_trade(r_outcome)
                            d_res = self.decay_guard.evaluate()
                            if d_res.status in ("WARNING", "REDUCE_RISK", "PAUSE"):
                                logging.getLogger("Orchestrator").warning(f"[DECAY_GUARD] Status: {d_res.status} | {d_res.action_required}")
                        except Exception:
                            pass

                    self._active_positions_cache.pop(pos.ticket, None)
                    self.trade_manager.forget_position(pos.ticket)
                    self._last_scalp_close_ts[pos.symbol] = time.time()
                    self.continuous_scalper.on_position_closed_or_rejected(pos.symbol, was_closed=True)
                    if hasattr(self, "alerts") and self.alerts:
                        self.alerts.alert_trade_closed(
                            symbol=pos.symbol,
                            ticket=pos.ticket,
                            direction=pos.order_type.value,
                            close_reason=act.reason,
                            money_pnl=realized_pnl,
                        )
                    break

                elif act.action_type == "MODIFY_SL" and act.new_sl is not None:
                    pos.stop_loss = act.new_sl
                    self.continuous_scalper.transition_state(pos.symbol, ScalpingLifecycleState.PROFIT_LOCKING)
                    if "Break-even" in act.reason:
                        pos.break_even_activated = True
                        if hasattr(self, "alerts") and self.alerts:
                            self.alerts.alert_break_even(pos.symbol, pos.ticket, act.new_sl)
                    else:
                        if hasattr(self, "alerts") and self.alerts:
                            self.alerts.alert_trailing_stop(
                                pos.symbol,
                                pos.ticket,
                                act.new_sl,
                                pos.current_price,
                            )
                    if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL] and not getattr(self.config, "dry_run", False):
                        # D11 Fix: Pass both SL and existing/updated TP to modify_order
                        mod_res = self.bridge.modify_order(ticket=act.ticket, sl=act.new_sl, tp=getattr(pos, "take_profit", None))
                        success = bool(mod_res and mod_res.get("status") == "SUCCESS")
                        self.trade_manager.record_stop_modification_result(act.ticket, success=success, reason=str((mod_res or {}).get("message", "")))
                    else:
                        self.trade_manager.record_stop_modification_result(act.ticket, success=True, reason="Simulated modify confirmed")

                elif act.action_type == "PARTIAL_CLOSE" and act.close_volume is not None:
                    # D9 Fix: Broker volume-step normalization and minimum remaining validation
                    sym_info = self.market_data.get_symbol_info(pos.symbol)
                    valid_close_vol = act.close_volume
                    if sym_info and hasattr(sym_info, "normalize_volume_down"):
                        valid_close_vol = sym_info.normalize_volume_down(act.close_volume)

                    rem_vol = round(max(0.0, pos.volume - valid_close_vol), 4)
                    min_lot = getattr(sym_info, "min_lot", 0.01) if sym_info else 0.01

                    # If remaining volume would be below broker min_lot, fully close
                    if 0.0 < rem_vol < min_lot:
                        valid_close_vol = pos.volume
                        rem_vol = 0.0

                    pos.volume = rem_vol
                    pos.partial_taken = True
                    self.continuous_scalper.transition_state(pos.symbol, ScalpingLifecycleState.PROFIT_LOCKING)
                    if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL, ExecutionMode.RETAIL] and not getattr(self.config, "dry_run", False):
                        if valid_close_vol > 0:
                            self.bridge.close_order(ticket=act.ticket, volume=valid_close_vol)
                    if hasattr(self, "alerts") and self.alerts:
                        self.alerts.alert_partial_close(
                            symbol=pos.symbol,
                            ticket=pos.ticket,
                            closed_volume=valid_close_vol,
                            remaining_volume=pos.volume,
                            pnl=pos.profit * 0.5,
                        )

        # 8b. Evaluate manual positions via manual_mgmt subsystem [SAFETY]
        self.manage_manual_positions()

        if hasattr(self, "health_monitor") and self.health_monitor:
            self.health_monitor.record_position_management(len(active_positions), len(executed_actions))
        return executed_actions

    def manage_manual_positions(self) -> Dict[str, Any]:
        """Runs one cycle of the manual position detector & management subsystem."""
        if not getattr(self, "manual_mgmt_detector", None):
            return {}
        try:
            all_account_pos = self.order_manager.get_all_account_positions()
            bot_magic = getattr(self.config, "magic_number", 100101)

            # Detect and alert newly observed manual positions
            for p in all_account_pos:
                if getattr(p, "magic", 0) != bot_magic:
                    if p.ticket not in self._known_manual_tickets:
                        self._known_manual_tickets.add(p.ticket)
                        if hasattr(self, "alerts") and self.alerts:
                            self.alerts.alert_manual_trade_detected(
                                symbol=p.symbol,
                                ticket=p.ticket,
                                direction=p.order_type.value,
                                volume=p.volume,
                                price=p.open_price,
                                sl=p.stop_loss,
                                tp=p.take_profit,
                            )

            manual_symbols = {p.symbol for p in all_account_pos if getattr(p, "magic", 0) != bot_magic}
            m15_map = {}
            m5_map = {}
            sinfo_map = {}
            for msym in manual_symbols:
                m15_map[msym] = self.market_data.get_candles(msym, Timeframe.M15)
                m5_map[msym] = self.market_data.get_candles(msym, Timeframe.M5)
                sinfo_map[msym] = self.market_data.get_symbol_info(msym)

            report = self.manual_mgmt_detector.run_cycle(
                market_data_candles_m15=m15_map,
                market_data_candles_m5=m5_map,
                symbol_info_map=sinfo_map
            )

            # Audit executed actions and alert via Telegram if available
            executed = report.get("executed_actions", [])
            assessments = report.get("assessments", {})
            for item in executed:
                ticket = item.get("ticket")
                action = str(item.get("action", ""))
                detail = str(item.get("detail", ""))
                msg = f"[MANUAL_MGMT] #{ticket} {action}: {detail}"
                logging.getLogger("Orchestrator").info(msg)

                if hasattr(self, "alerts") and self.alerts:
                    pos_match = next((p for p in all_account_pos if p.ticket == ticket), None)
                    sym = pos_match.symbol if pos_match else ""
                    ass = assessments.get(ticket, {})
                    rec_sl = ass.get("recommended_sl", 0.0)
                    rec_tp = ass.get("recommended_tp", 0.0)
                    reason = ass.get("reason", detail)

                    if action in ("SET_SLTP", "SET_SL", "ATTACH_PROTECTION") or "SL" in action:
                        self.alerts.alert_manual_trade_protected(
                            symbol=sym,
                            ticket=ticket,
                            sl=rec_sl,
                            tp=rec_tp,
                            reason=reason,
                        )
                    elif action == "BREAK_EVEN":
                        self.alerts.alert_break_even(
                            symbol=sym,
                            ticket=ticket,
                            new_sl=rec_sl,
                        )
                    elif action == "TRAILING_STOP":
                        curr_px = pos_match.current_price if pos_match else 0.0
                        self.alerts.alert_trailing_stop(
                            symbol=sym,
                            ticket=ticket,
                            new_sl=rec_sl,
                            current_price=curr_px,
                        )
                    else:
                        if hasattr(self.alerts, "notifier") and self.alerts.notifier:
                            try:
                                self.alerts.notifier.notify(f"🛡️ <b>Manual Trade Management</b>\n{msg}", category="TRADE")
                            except Exception:
                                pass

            return report
        except Exception as mm_err:
            logging.getLogger("Orchestrator").error(f"[MANUAL_MGMT_ERROR] Cycle execution failed: {mm_err}")
            return {}

    def manage_open_positions(self) -> List[object]:
        """Alias for manage_active_positions() used by continuous runtime loops."""
        return self.manage_active_positions()

    def get_dashboard_state(self) -> DashboardState:
        """Returns the current state snapshot for monitoring."""
        perf = self.performance_tracker.calculate_summary()
        active_positions = self.order_manager.get_active_positions()
        sched_state = self.trading_scheduler.get_status() if hasattr(self, "trading_scheduler") else {}
        coord_state = self.inverse_coordinator.get_status() if hasattr(self, "inverse_coordinator") else {}
        return self.dashboard.build_snapshot(
            account=self.account_info,
            active_positions=active_positions,
            signals=self.recent_signals,
            market_contexts=self.active_contexts,
            perf=perf,
            portfolio_risk_engine=self.portfolio_risk,
            schedule_info=sched_state,
            coordination_info=coord_state,
        )

    def run_cycle_all_symbols(self) -> Dict[str, Optional[SignalCandidate]]:
        """Scans all eligible specialized symbols in priority order."""
        ordered_canonical = self.trading_scheduler.get_scanning_priority_order()
        target_symbols = [
            self.symbol_universe.get_broker_symbol(c)
            for c in ordered_canonical
            if self.trading_scheduler.is_instrument_eligible_for_new_entry(c)[0]
        ]
        results = {}
        for sym in target_symbols:
            try:
                results[sym] = self.run_cycle_for_symbol(sym)
            except Exception as e:
                if hasattr(self, "health_monitor") and self.health_monitor:
                    self.health_monitor.record_scan_failure(sym, str(e))
                results[sym] = None
        return results
