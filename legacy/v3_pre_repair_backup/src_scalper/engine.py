"""
Master High-Speed Event-Driven Dual-Market Scalper Engine (GOLD + BTCUSD).
Implements the 10-Stage Low-Latency Execution Pipeline:
  MARKET DATA -> TICK VALIDATION -> MARKET REGIME DETECTION -> DIRECTIONAL SIGNAL ->
  ENTRY QUALITY SCORING -> ACCOUNT RISK APPROVAL -> ORDER EXECUTION ->
  BROKER CONFIRMATION -> BASKET MANAGEMENT -> EXIT AND RECONCILIATION
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

from src.scalper.basket import BasketPosition, GoldBasketManager, MultiBasketManager, ScalperBasket
from src.scalper.config import ScalperConfig
from src.scalper.direction import SymbolDirectionSelector
from src.scalper.entry_engine import MultiPositionEntryEngine
from src.scalper.executor import GoldOrderExecutor
from src.scalper.exit_engine import RapidExitEngine
from src.scalper.market_cache import IndicatorCache, TickCache
from src.scalper.notifier import ScalperNotificationManager
from src.scalper.reversal import DirectionReversalEngine
from src.scalper.risk import AccountRiskManager
from src.scalper.scheduler import MarketScheduler
from src.scalper.sizing import SymbolLotSizingEngine
from src.scalper.strategy_btc import BtcWeekendScalpingStrategy
from src.scalper.strategy_gold import GoldScalpingStrategy, StrategySignalEvaluation
from src.scalper.symbol_resolver import MultiSymbolResolver, ResolvedSymbolSpec
from src.scalper.telemetry import DuplicateOrderGuard, ExecutionLatencyTracker, OrderTelemetrySample

logger = logging.getLogger("DualMarketScalperEngine")


@dataclass
class EngineCycleStats:
    total_cycles: int = 0
    total_baskets_opened: int = 0
    total_baskets_closed: int = 0
    total_orders_submitted: int = 0
    total_orders_filled: int = 0
    total_orders_rejected: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    winning_trades: int = 0
    losing_trades: int = 0
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    net_profit_usd: float = 0.0
    max_floating_drawdown_pct: float = 0.0
    max_open_positions_seen: int = 0
    reversals_executed: int = 0
    duplicate_orders_prevented: int = 0
    start_time: float = field(default_factory=time.time)


class DualMarketScalperEngine:
    def __init__(self, config: Optional[ScalperConfig] = None, is_simulation: bool = False):
        self.config = config or ScalperConfig.load()
        self.is_simulation = is_simulation

        # 1. Market Scheduler
        self.scheduler = MarketScheduler(self.config.scheduler)

        # 2. Multi-Symbol Resolvers
        self.resolvers: Dict[str, MultiSymbolResolver] = {}
        for sym_k, sym_cfg in self.config.symbols.items():
            self.resolvers[sym_k.upper()] = MultiSymbolResolver(
                canonical=sym_cfg.canonical,
                aliases=sym_cfg.aliases,
                fallback=sym_cfg.canonical,
            )
        self.symbol_specs: Dict[str, ResolvedSymbolSpec] = {}

        # 3. Caches, Telemetry & Guards (Phase 2 & 11)
        self.tick_cache = TickCache(max_ticks=500)
        self.indicator_cache = IndicatorCache()
        self.latency_tracker = ExecutionLatencyTracker()
        self.duplicate_guard = DuplicateOrderGuard(dedup_window_ms=1000)

        # 4. Dedicated Strategy, Entry, Sizing, Basket, Exit, Reversal & Risk Engines
        self.gold_strategy = GoldScalpingStrategy(self.config.symbols.get("GOLD"))
        self.btc_strategy = BtcWeekendScalpingStrategy(self.config.symbols.get("BTCUSD"))
        self.entry_engine = MultiPositionEntryEngine()
        self.sizing = SymbolLotSizingEngine(self.config.lot_sizing)
        self.direction_selector = SymbolDirectionSelector(self.config.direction_selection)
        self.basket_manager = MultiBasketManager()
        self.exit_engine = RapidExitEngine()
        self.reversal_engine = DirectionReversalEngine()
        self.risk = AccountRiskManager(self.config)
        self.executor = GoldOrderExecutor(self.config.execution)
        self.notifier = ScalperNotificationManager()

        # Global & Per-symbol Statistics
        self.stats = EngineCycleStats()
        self.symbol_stats: Dict[str, EngineCycleStats] = {
            "GOLD": EngineCycleStats(),
            "BTCUSD": EngineCycleStats(),
        }

        self._is_running: bool = False
        self._cached_account: Dict[str, Any] = {
            "balance": 1000.0,
            "equity": 1000.0,
            "margin": 0.0,
            "free_margin": 1000.0,
            "margin_level": 1000.0,
            "trade_mode": "DEMO",
        }
        self._last_account_poll_ts: float = 0.0

    @property
    def symbol_spec(self) -> Optional[ResolvedSymbolSpec]:
        sched_k = self.scheduler.get_scheduled_symbol_key()
        return self.symbol_specs.get(sched_k) or self.symbol_specs.get("GOLD")

    @symbol_spec.setter
    def symbol_spec(self, val: ResolvedSymbolSpec) -> None:
        if val:
            k = "BTCUSD" if "BTC" in val.canonical.upper() else "GOLD"
            self.symbol_specs[k] = val

    def initialize(self) -> bool:
        logger.info(f"[ENGINE] Initializing {self.config.general.engine_name} v{self.config.general.version}...")

        ks = self.risk.check_kill_switch()
        if not ks.allowed:
            logger.critical(f"[ENGINE] Initialization halted: {ks.reason}")
            return False

        if not self.is_simulation:
            try:
                import MetaTrader5 as mt5

                if not mt5.initialize():
                    logger.error("[ENGINE] MetaTrader5 initialize() failed")
                    return False

                acc_info = mt5.account_info()
                if not acc_info:
                    logger.error("[ENGINE] Failed to retrieve account_info from MT5")
                    return False

                trade_mode = "DEMO" if int(getattr(acc_info, "trade_mode", 0)) == 0 else "REAL"
                mode_check = self.risk.check_demo_live_mode(trade_mode)
                if not mode_check.allowed:
                    logger.critical(f"[ENGINE] Safety mode check failed: {mode_check.reason}")
                    return False

                for sym_k, resolver in self.resolvers.items():
                    spec = resolver.resolve_with_mt5()
                    if spec:
                        self.symbol_specs[sym_k] = spec
                    else:
                        logger.warning(f"[ENGINE] Could not resolve {sym_k} on broker.")

                # Reconcile any pre-existing scalper positions on restart
                if self.config.execution.reconnect_reconciliation:
                    self.recover_open_positions_from_broker()

            except Exception as e:
                logger.error(f"[ENGINE] Exception during MT5 initialization: {e}")
                return False
        else:
            self.symbol_specs["GOLD"] = ResolvedSymbolSpec(
                symbol="XAUUSD",
                canonical="XAUUSD",
                digits=2,
                point=0.01,
                tick_size=0.01,
                tick_value=1.0,
                contract_size=100.0,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                filling_mode=2,
                bid=2650.00,
                ask=2650.30,
                spread_points=30.0,
                is_tradable=True,
            )
            self.symbol_specs["BTCUSD"] = ResolvedSymbolSpec(
                symbol="BTCUSD",
                canonical="BTCUSD",
                digits=2,
                point=0.01,
                tick_size=0.01,
                tick_value=1.0,
                contract_size=1.0,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                filling_mode=2,
                bid=67000.00,
                ask=67010.00,
                spread_points=1000.0,
                is_tradable=True,
            )

        self._is_running = True
        return True

    def recover_open_positions_from_broker(self, broker_positions: Optional[Sequence[Any]] = None) -> int:
        """
        Phase 2 & 13: Reconciles and adopts open scalper positions (magic 777001 / 777002)
        after a Python engine or MT5 terminal restart without duplicating orders or losing state.
        """
        pos_list = broker_positions
        if pos_list is None and not self.is_simulation:
            try:
                import MetaTrader5 as mt5

                pos_list = mt5.positions_get() or []
            except Exception:
                pos_list = []

        if not pos_list:
            return 0

        magic_to_key = {cfg.magic_number: k.upper() for k, cfg in self.config.symbols.items()}
        recovered = 0
        for p in pos_list:
            magic = int(getattr(p, "magic", 0))
            if magic not in magic_to_key:
                continue
            sym_k = magic_to_key[magic]
            sym_cfg = self.config.symbols[sym_k]
            ticket = int(getattr(p, "ticket", 0))
            symbol = str(getattr(p, "symbol", sym_cfg.canonical))
            p_type = int(getattr(p, "type", 0))
            direction = "BUY" if p_type == 0 else "SELL"
            vol = float(getattr(p, "volume", 0.01))
            open_px = float(getattr(p, "price_open", 0.0))
            curr_px = float(getattr(p, "price_current", open_px))
            profit = float(getattr(p, "profit", 0.0))
            sl = float(getattr(p, "sl", 0.0))
            tp = float(getattr(p, "tp", 0.0))

            basket = self.basket_manager.get_active_basket(sym_k)
            if basket is None:
                basket = self.basket_manager.start_new_basket(
                    symbol_key=sym_k,
                    symbol=symbol,
                    direction=direction,
                    target_size=sym_cfg.basket_size,
                    magic_number=magic,
                    basket_tp_usd=sym_cfg.basket_tp_usd,
                    tp_usd_per_min_lot=sym_cfg.tp_usd_per_min_lot,
                    max_hold_seconds=sym_cfg.max_hold_seconds,
                )
            if ticket not in basket.positions:
                basket.add_position(
                    BasketPosition(
                        ticket=ticket,
                        symbol=symbol,
                        direction=direction,
                        volume=vol,
                        open_price=open_px,
                        current_price=curr_px,
                        profit=profit,
                        stop_loss=sl,
                        take_profit=tp,
                        magic=magic,
                        symbol_key=sym_k,
                        entry_reason="RECOVERED_ON_RESTART",
                    )
                )
                recovered += 1
        return recovered

    def on_trade_transaction_event(self, event: Dict[str, Any]) -> None:
        """
        Phase 2 Requirement 2: Handles asynchronous OnTradeTransaction events from MQL5 EA
        to update position state incrementally without full-account polling.
        """
        ev_type = str(event.get("type", "")).upper()
        ticket = int(event.get("position", event.get("ticket", 0)))
        if ev_type in ("DEAL_CLOSE", "POSITION_CLOSED") and ticket > 0:
            pnl = float(event.get("profit", 0.0))
            self.basket_manager.on_position_closed(ticket, realized_pnl=pnl)
            self.risk.record_trade_outcome(pnl)

    def _get_account_snapshot(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not self.is_simulation:
            now_t = time.time()
            if force_refresh or (now_t - self._last_account_poll_ts >= 0.5):
                try:
                    import MetaTrader5 as mt5

                    info = mt5.account_info()
                    if info:
                        self._cached_account = {
                            "balance": float(info.balance),
                            "equity": float(info.equity),
                            "margin": float(info.margin),
                            "free_margin": float(info.margin_free),
                            "margin_level": float(info.margin_level),
                            "trade_mode": "DEMO" if int(getattr(info, "trade_mode", 0)) == 0 else "REAL",
                        }
                        self._last_account_poll_ts = now_t
                except Exception:
                    pass
        return dict(self._cached_account)

    def _sync_active_positions(self) -> None:
        if not self.is_simulation and self.basket_manager.get_all_active_baskets():
            try:
                import MetaTrader5 as mt5

                pos_list = mt5.positions_get() or []
                live_by_ticket = {p.ticket: p for p in pos_list}

                for basket in self.basket_manager.get_all_active_baskets():
                    tracked_tickets = list(basket.positions.keys())
                    for t in tracked_tickets:
                        if t in live_by_ticket:
                            lp = live_by_ticket[t]
                            basket.update_position(
                                ticket=t,
                                current_price=float(lp.price_current),
                                profit=float(lp.profit),
                                commission=float(getattr(lp, "commission", 0.0) or 0.0),
                                swap=float(getattr(lp, "swap", 0.0) or 0.0),
                            )
                        else:
                            basket.remove_position(t)
            except Exception as e:
                logger.debug(f"[ENGINE] Error synchronizing active positions: {e}")

    def run_single_tick_cycle(
        self,
        sim_ticks: Optional[List[Any]] = None,
        sim_candles: Optional[List[Any]] = None,
        strategy_bias: Optional[float] = None,
        current_dt: Optional[datetime] = None,
        simulated_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Executes the 10-Stage Low-Latency Pipeline without blocking sleeps.
        """
        self.stats.total_cycles += 1

        if simulated_prices and self.is_simulation:
            for sym_k, px in simulated_prices.items():
                sk = sym_k.upper()
                spec = self.symbol_specs.get(sk)
                if spec:
                    spec.bid = float(px)
                    spec.ask = round(float(px) + spec.spread_points * spec.point, 2)
                active_b = self.basket_manager.get_active_basket(sk)
                if active_b:
                    mult = 1.0 if "BTC" in sk else 100.0
                    for pos in active_b.positions.values():
                        sign = 1.0 if pos.direction == "BUY" else -1.0
                        pos.current_price = float(px)
                        pos.profit = round((float(px) - pos.open_price) * sign * pos.volume * mult, 2)
                        if pos.ticket in self.executor.simulated_positions:
                            self.executor.simulated_positions[pos.ticket]["profit"] = pos.profit
                            self.executor.simulated_positions[pos.ticket]["price_current"] = float(px)

        # 1. Kill Switch & Broker Connection Check
        ks = self.risk.check_kill_switch()
        if not ks.allowed:
            self.emergency_shutdown(reason=ks.reason)
            return

        conn = self.risk.check_broker_connection(is_connected=self.risk.broker_connected)
        if not conn.allowed:
            self.stats.rejection_reasons["BROKER_DISCONNECT"] = self.stats.rejection_reasons.get("BROKER_DISCONNECT", 0) + 1
            self.notifier.emit("BROKER_DISCONNECTION", instrument="ALL", reason=conn.reason)
            return

        # 2. Account, Daily Loss & Floating Drawdown Check
        acc = self._get_account_snapshot()
        bal = float(acc["balance"])
        eq = float(acc["equity"])

        if bal > 0 and eq < bal:
            cur_dd = ((bal - eq) / bal) * 100.0
            if cur_dd > self.stats.max_floating_drawdown_pct:
                self.stats.max_floating_drawdown_pct = round(cur_dd, 2)

        dd_check = self.risk.check_drawdown(bal, eq)
        if not dd_check.allowed:
            self.stats.rejection_reasons["DRAWDOWN_LIMIT"] = self.stats.rejection_reasons.get("DRAWDOWN_LIMIT", 0) + 1
            self.notifier.emit("RISK_LIMIT_REACHED", instrument="ALL", account_equity_usd=eq, reason=dd_check.reason)
            self.emergency_shutdown(reason=dd_check.reason)
            return

        floating_total = sum(b.net_floating_profit for b in self.basket_manager.get_all_active_baskets())
        daily_check = self.risk.check_daily_loss(bal, floating_pnl_usd=floating_total)
        if not daily_check.allowed:
            self.stats.rejection_reasons["DAILY_LOSS_LIMIT"] = self.stats.rejection_reasons.get("DAILY_LOSS_LIMIT", 0) + 1
            self.notifier.emit("RISK_LIMIT_REACHED", instrument="ALL", account_equity_usd=eq, reason=daily_check.reason)
            self.emergency_shutdown(reason=daily_check.reason)
            return

        streak_check = self.risk.check_consecutive_losses()
        if not streak_check.allowed:
            self.stats.rejection_reasons["LOSS_STREAK_COOLDOWN"] = self.stats.rejection_reasons.get("LOSS_STREAK_COOLDOWN", 0) + 1
            self.notifier.emit("TRADING_PAUSED", instrument="ALL", account_equity_usd=eq, reason=streak_check.reason)
            return

        # 3. Synchronize Active Positions & Upgrade Protective Stops (Break-Even & Trailing)
        self._sync_active_positions()

        total_open_pos = sum(b.position_count for b in self.basket_manager.get_all_active_baskets())
        if total_open_pos > self.stats.max_open_positions_seen:
            self.stats.max_open_positions_seen = total_open_pos

        for basket in self.basket_manager.get_all_active_baskets():
            sym_cfg = self.config.symbols.get(basket.symbol_key)
            spec = self.symbol_specs.get(basket.symbol_key)
            if sym_cfg and spec:
                stop_actions = self.exit_engine.evaluate_protective_stop_upgrades(basket, sym_cfg, point=spec.point)
                for act in stop_actions:
                    mod_res = self.executor.modify_position_sl(
                        ticket=act.ticket,
                        symbol=act.symbol,
                        new_sl=act.new_sl,
                        is_simulation=self.is_simulation,
                    )
                    if mod_res.is_success and act.ticket in basket.positions:
                        basket.positions[act.ticket].stop_loss = act.new_sl

        # 4. Evaluate Exits Across ALL Active Baskets (GOLD and BTCUSD)
        exit_triggers = self.basket_manager.evaluate_all_exits()
        for sym_k, tickets, reason in exit_triggers:
            self._close_basket_tickets(sym_k, tickets, reason, account_equity=eq)

        # 5. Market Scheduler Evaluation for NEW entries
        sched_key = self.scheduler.get_scheduled_symbol_key(current_dt)
        sched_spec = self.symbol_specs.get(sched_key)
        decision = self.scheduler.evaluate_market_status(sched_spec, current_dt)

        if decision.is_transition_bar:
            self.notifier.emit(
                "SCHEDULER_TRANSITION",
                instrument=sched_key,
                account_equity_usd=eq,
                reason=decision.reason,
            )

        if not decision.is_entry_permitted:
            self.latency_tracker.record_missed_opportunity(decision.reason)
            return

        # 6. Tick Validation & Indicator Cache Update
        if sched_spec and sim_ticks:
            last_t = sim_ticks[-1]
            t_bid = float(getattr(last_t, "bid", getattr(last_t, "price", sched_spec.bid)))
            t_ask = float(getattr(last_t, "ask", t_bid + sched_spec.spread_points * sched_spec.point))
            t_ts = float(getattr(last_t, "timestamp", getattr(last_t, "time", time.time())))
            t_val = self.tick_cache.push_tick(
                symbol=sched_spec.symbol,
                bid=t_bid,
                ask=t_ask,
                timestamp=t_ts,
                point=sched_spec.point,
                staleness_limit_ms=self.config.execution.tick_staleness_limit_ms,
            )
            if not t_val.is_valid:
                self.stats.rejection_reasons["STALE_OR_INVALID_TICK"] = self.stats.rejection_reasons.get("STALE_OR_INVALID_TICK", 0) + 1
                self.latency_tracker.record_missed_opportunity(t_val.reason)
                return
            if not t_val.is_new_tick:
                self.stats.duplicate_orders_prevented += 1
                self.latency_tracker.record_duplicate_prevented()
                return

        # 7. Check for Reversal if Active Basket Exists and Opposite Signal Arrives, or New Entry
        if self.basket_manager.has_active_basket(sched_key):
            if strategy_bias is not None and abs(strategy_bias) >= 0.75:
                active_b = self.basket_manager.get_active_basket(sched_key)
                opp_dir = "BUY" if strategy_bias > 0 else "SELL"
                if active_b and active_b.direction != opp_dir:
                    self._attempt_reversal(sched_key, acc, sim_ticks, sim_candles, strategy_bias)
            return

        if self.basket_manager.is_reentry_ready(sched_key):
            self._attempt_basket_entry(sched_key, acc, sim_ticks, sim_candles, strategy_bias)

    def _close_basket_tickets(
        self,
        sym_k: str,
        tickets: List[int],
        reason: str,
        account_equity: float = 1000.0,
    ) -> float:
        basket = self.basket_manager.get_active_basket(sym_k)
        if not basket:
            return 0.0
        is_buy = basket.direction == "BUY"
        spec = self.symbol_specs.get(sym_k)
        total_closed_pnl = 0.0

        for t in tickets:
            pos = basket.positions.get(t)
            vol = pos.volume if pos else 0.01
            close_res = self.executor.close_position(
                ticket=t,
                symbol=spec.symbol if spec else basket.symbol,
                volume=vol,
                is_buy=is_buy,
                spec=spec,
                is_simulation=self.is_simulation,
            )
            if close_res.is_success:
                pnl = pos.net_profit if pos else 0.0
                total_closed_pnl += pnl
                self.basket_manager.on_position_closed(t, realized_pnl=pnl, symbol_key=sym_k)
                self.risk.record_trade_outcome(pnl)
                sym_stat = self.symbol_stats.setdefault(sym_k, EngineCycleStats())
                if pnl >= 0:
                    self.stats.winning_trades += 1
                    self.stats.gross_profit_usd += pnl
                    sym_stat.winning_trades += 1
                    sym_stat.gross_profit_usd += pnl
                else:
                    self.stats.losing_trades += 1
                    self.stats.gross_loss_usd += abs(pnl)
                    sym_stat.losing_trades += 1
                    sym_stat.gross_loss_usd += abs(pnl)

                self.notifier.emit(
                    "POSITION_CLOSURE",
                    instrument=sym_k,
                    direction=basket.direction,
                    lot_size=vol,
                    basket_id=basket.basket_id,
                    open_positions_count=basket.position_count,
                    realized_pnl_usd=pnl,
                    account_equity_usd=account_equity,
                    reason=reason,
                    execution_latency_ms=close_res.fill_latency_ms,
                )

        if len(basket.positions) == 0:
            if sym_k in self.basket_manager.active_baskets:
                self.basket_manager.close_basket(sym_k, reason=reason)
            self.stats.total_baskets_closed += 1
            self.symbol_stats[sym_k].total_baskets_closed += 1
            self.stats.net_profit_usd = round(self.stats.gross_profit_usd - self.stats.gross_loss_usd, 2)
            self.symbol_stats[sym_k].net_profit_usd = round(
                self.symbol_stats[sym_k].gross_profit_usd - self.symbol_stats[sym_k].gross_loss_usd, 2
            )
            self.notifier.emit(
                "BASKET_COMPLETION",
                instrument=sym_k,
                direction=basket.direction,
                basket_id=basket.basket_id,
                open_positions_count=0,
                realized_pnl_usd=basket.realized_profit,
                account_equity_usd=account_equity,
                reason=reason,
            )
        return round(total_closed_pnl, 2)

    def _attempt_reversal(
        self,
        symbol_key: str,
        account: Dict[str, Any],
        ticks: Optional[List[Any]],
        candles: Optional[List[Any]],
        strategy_bias: Optional[float],
    ) -> bool:
        sym_k = symbol_key.upper()
        active_basket = self.basket_manager.get_active_basket(sym_k)
        sym_cfg = self.config.symbols.get(sym_k)
        spec = self.symbol_specs.get(sym_k)
        if not active_basket or not sym_cfg or not spec:
            return False

        snap = self.indicator_cache.get_or_update(
            symbol_key=sym_k,
            ticks=ticks or [],
            m1_bars=candles,
            point=spec.point,
            spread_points=spec.spread_points,
        )
        strategy = self.btc_strategy if sym_k == "BTCUSD" else self.gold_strategy
        sig = strategy.evaluate(snap, spec=spec, current_price=spec.bid, strategy_bias_override=strategy_bias)

        rev_eval = self.reversal_engine.evaluate_reversal(
            symbol_key=sym_k,
            active_basket=active_basket,
            opposite_signal=sig,
            instrument_config=sym_cfg,
            current_spread_points=spec.spread_points,
            estimated_slippage_points=0.0,
            risk_approved=True,
            tick_momentum=snap.tick_momentum,
        )
        if not rev_eval.approved:
            return False

        closed_tickets = list(active_basket.positions.keys())
        realized_pnl = self._close_basket_tickets(sym_k, closed_tickets, reason="REVERSAL_CLOSE", account_equity=account["equity"])
        if self.basket_manager.has_active_basket(sym_k):
            return False

        self._attempt_basket_entry(sym_k, account, ticks, candles, strategy_bias)
        new_basket = self.basket_manager.get_active_basket(sym_k)
        new_orders = (
            [{"ticket": p.ticket, "volume": p.volume, "price": p.open_price} for p in new_basket.positions.values()]
            if new_basket
            else []
        )
        self.reversal_engine.record_completed_reversal(
            symbol_key=sym_k,
            previous_direction=rev_eval.previous_direction,
            new_direction=rev_eval.new_direction,
            reason=rev_eval.reason,
            closed_positions=closed_tickets,
            realized_pnl_usd=realized_pnl,
            remaining_exposure_lots=new_basket.total_volume if new_basket else 0.0,
            new_order_details=new_orders,
        )
        self.stats.reversals_executed += 1
        self.notifier.emit(
            "REVERSAL",
            instrument=sym_k,
            direction=rev_eval.new_direction,
            basket_id=new_basket.basket_id if new_basket else "NONE",
            open_positions_count=new_basket.position_count if new_basket else 0,
            realized_pnl_usd=realized_pnl,
            account_equity_usd=account["equity"],
            reason=rev_eval.reason,
        )
        return True

    def _attempt_basket_entry(
        self,
        symbol_key: str,
        account: Dict[str, float],
        ticks: Optional[List[Any]],
        candles: Optional[List[Any]],
        strategy_bias: Optional[float],
    ) -> None:
        t_sig_start = time.perf_counter()
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        if not sym_cfg or not sym_cfg.enabled:
            return

        spec = self.symbol_specs.get(sym_k)
        if not spec or not spec.is_tradable:
            return

        # 1. Spread check
        spread_pts = spec.spread_points
        sp_check = self.risk.check_spread(sym_k, spread_pts)
        if not sp_check.allowed:
            self.stats.rejection_reasons["SPREAD_TOO_HIGH"] = self.stats.rejection_reasons.get("SPREAD_TOO_HIGH", 0) + 1
            return

        # 2. Cached Indicator & Strategy Signal Evaluation
        cached_ticks = ticks if ticks is not None else self.tick_cache.get_recent_ticks(spec.symbol, 25)
        snap = self.indicator_cache.get_or_update(
            symbol_key=sym_k,
            ticks=cached_ticks,
            m1_bars=candles,
            point=spec.point,
            spread_points=spread_pts,
        )

        dir_detail = self.direction_selector.select_direction(
            ticks=cached_ticks,
            m1_candles=candles,
            strategy_bias=strategy_bias,
            canonical=sym_cfg.canonical,
            instrument_config=sym_cfg,
        )
        direction = dir_detail.selected_direction

        strategy_engine = self.btc_strategy if sym_k == "BTCUSD" else self.gold_strategy
        sig_eval: StrategySignalEvaluation = strategy_engine.evaluate(
            snapshot=snap,
            spec=spec,
            current_price=spec.bid or (67000.0 if sym_k == "BTCUSD" else 2650.0),
            strategy_bias_override=strategy_bias,
            allow_fallback_in_sim=True,
        )
        sig_eval.direction = direction

        sig_latency_ms = round((time.perf_counter() - t_sig_start) * 1000.0, 3)
        self.latency_tracker.record_signal_latency(sig_latency_ms)

        if not sig_eval.is_valid:
            self.stats.rejection_reasons["SIGNAL_INVALID"] = self.stats.rejection_reasons.get("SIGNAL_INVALID", 0) + 1
            self.latency_tracker.record_missed_opportunity(sig_eval.rejection_reason)
            return

        # 3. Lot Sizing
        sizing_res = self.sizing.calculate_lot(account["balance"], spec=spec, instrument_config=sym_cfg)
        if not sizing_res.is_safe or sizing_res.lot <= 0:
            self.stats.rejection_reasons["SIZING_UNSAFE"] = self.stats.rejection_reasons.get("SIZING_UNSAFE", 0) + 1
            return

        # 4. Multi-Position Entry Plan
        entry_plan = self.entry_engine.plan_entries(
            symbol_key=sym_k,
            signal=sig_eval,
            instrument_config=sym_cfg,
            active_basket=self.basket_manager.get_active_basket(sym_k),
            tick_seq=snap.tick_seq,
        )
        if not entry_plan.allowed or not entry_plan.planned_entries:
            self.latency_tracker.record_missed_opportunity(entry_plan.rejection_reason)
            return

        basket_size = len(entry_plan.planned_entries)
        projected_lots = round(sizing_res.lot * basket_size, 4)
        current_open_pos = sum(b.position_count for b in self.basket_manager.get_all_active_baskets())
        current_total_lots = sum(b.total_volume for b in self.basket_manager.get_all_active_baskets())

        cap_check = self.risk.check_margin_and_capacity(
            account_balance=account["balance"],
            account_equity=account["equity"],
            account_margin=account["margin"],
            account_free_margin=account["free_margin"],
            current_open_positions=current_open_pos,
            current_total_lots=current_total_lots,
            proposed_lot=projected_lots,
        )
        if not cap_check.allowed:
            self.stats.rejection_reasons[cap_check.category] = self.stats.rejection_reasons.get(cap_check.category, 0) + 1
            return

        # 5. Start Basket & Submit Non-Blocking Orders with Idempotency Protection
        basket = self.basket_manager.start_new_basket(
            symbol_key=sym_k,
            symbol=spec.symbol,
            direction=direction,
            target_size=basket_size,
            magic_number=sym_cfg.magic_number,
            basket_tp_usd=sym_cfg.basket_tp_usd,
            tp_usd_per_min_lot=sym_cfg.tp_usd_per_min_lot,
            max_hold_seconds=sym_cfg.max_hold_seconds,
            profit_lock_trigger_usd=sym_cfg.profit_lock_trigger_usd,
            profit_lock_floor_usd=sym_cfg.profit_lock_floor_usd,
        )
        self.stats.total_baskets_opened += 1
        self.symbol_stats[sym_k].total_baskets_opened += 1

        pt = spec.point
        for idx, planned in enumerate(entry_plan.planned_entries):
            if self.config.execution.duplicate_order_protection:
                if not self.duplicate_guard.check_and_register(
                    entry_id=planned.entry_id,
                    symbol=spec.symbol,
                    direction=direction,
                    tick_seq=snap.tick_seq,
                    slot_index=idx,
                ):
                    self.stats.duplicate_orders_prevented += 1
                    self.latency_tracker.record_duplicate_prevented()
                    continue

            self.stats.total_orders_submitted += 1
            self.symbol_stats[sym_k].total_orders_submitted += 1

            curr_px = (spec.ask if direction == "BUY" else spec.bid) or (2650.00 if "XAU" in sym_cfg.canonical else 67000.00)
            protective_sl = self.risk.calculate_protective_sl(sym_k, direction, curr_px, pt)

            res = self.executor.submit_market_order(
                symbol=spec.symbol,
                direction=direction,
                volume=sizing_res.lot,
                stop_loss=protective_sl,
                take_profit=0.0,
                comment=f"{sym_cfg.comment_prefix}_{basket.basket_id[-4:]}_{idx+1}",
                magic=sym_cfg.magic_number,
                spec=spec,
                is_simulation=self.is_simulation,
            )

            self.latency_tracker.record_order_sample(
                OrderTelemetrySample(
                    entry_id=planned.entry_id,
                    symbol=spec.symbol,
                    direction=direction,
                    signal_latency_ms=sig_latency_ms,
                    submission_latency_ms=res.submission_latency_ms,
                    broker_ack_latency_ms=res.broker_ack_latency_ms,
                    fill_latency_ms=res.fill_latency_ms,
                    requested_price=res.requested_price,
                    fill_price=res.price,
                    slippage_points=res.slippage_points,
                    is_filled=res.is_success,
                    is_rejected=not res.is_success,
                    rejection_reason=res.error_message,
                )
            )

            if res.is_success:
                self.stats.total_orders_filled += 1
                self.symbol_stats[sym_k].total_orders_filled += 1
                bpos = BasketPosition(
                    ticket=res.ticket,
                    symbol=spec.symbol,
                    direction=direction,
                    volume=res.volume,
                    open_price=res.price,
                    current_price=res.price,
                    stop_loss=protective_sl,
                    magic=sym_cfg.magic_number,
                    symbol_key=sym_k,
                    entry_id=planned.entry_id,
                    entry_reason=planned.reason,
                    worst_case_risk_usd=sizing_res.worst_case_loss_usd,
                )
                basket.add_position(bpos)
            else:
                self.stats.total_orders_rejected += 1
                self.symbol_stats[sym_k].total_orders_rejected += 1
                rej_key = res.error_message or "ORDER_REJECTED"
                self.stats.rejection_reasons[rej_key] = self.stats.rejection_reasons.get(rej_key, 0) + 1

        if len(basket.positions) == 0:
            self.basket_manager.close_basket(sym_k, reason="ALL_ORDERS_FAILED")
        else:
            first_pos = next(iter(basket.positions.values()))
            self.notifier.emit(
                "NEW_BASKET",
                instrument=sym_k,
                direction=direction,
                entry_price=first_pos.open_price,
                lot_size=basket.total_volume,
                stop_loss=first_pos.stop_loss,
                basket_id=basket.basket_id,
                open_positions_count=basket.position_count,
                account_equity_usd=account["equity"],
                reason=sig_eval.rationale,
                execution_latency_ms=sig_latency_ms,
            )

    def emergency_shutdown(self, reason: str = "EMERGENCY_SHUTDOWN") -> None:
        logger.critical(f"[SHUTDOWN] Emergency liquidation triggered: {reason}")
        for sym_k, basket in list(self.basket_manager.active_baskets.items()):
            is_buy = basket.direction == "BUY"
            spec = self.symbol_specs.get(sym_k)
            for t, pos in list(basket.positions.items()):
                self.executor.close_position(
                    ticket=t,
                    symbol=spec.symbol if spec else basket.symbol,
                    volume=pos.volume,
                    is_buy=is_buy,
                    spec=spec,
                    is_simulation=self.is_simulation,
                )
                basket.remove_position(t)
            self.basket_manager.close_basket(sym_k, reason=reason)
        self.notifier.emit("EMERGENCY_SHUTDOWN", instrument="ALL", reason=reason)
        self._is_running = False

    def get_status_report(self) -> Dict[str, Any]:
        return {
            "total_cycles": self.stats.total_cycles,
            "total_baskets_opened": self.stats.total_baskets_opened,
            "total_baskets_closed": self.stats.total_baskets_closed,
            "total_orders_submitted": self.stats.total_orders_submitted,
            "total_orders_filled": self.stats.total_orders_filled,
            "total_orders_rejected": self.stats.total_orders_rejected,
            "reversals_executed": self.stats.reversals_executed,
            "duplicate_orders_prevented": self.stats.duplicate_orders_prevented,
            "net_profit_usd": round(self.stats.net_profit_usd, 2),
            "symbols": {
                k: {
                    "baskets_opened": v.total_baskets_opened,
                    "baskets_closed": v.total_baskets_closed,
                    "orders_filled": v.total_orders_filled,
                    "net_profit_usd": round(v.net_profit_usd, 2),
                }
                for k, v in self.symbol_stats.items()
            },
        }


class GoldScalperEngine(DualMarketScalperEngine):
    """
    Subclass preserving 100% backward compatibility for single-symbol GOLD callers and test suites.
    """

    def __init__(self, config: Optional[ScalperConfig] = None, is_simulation: bool = False):
        super().__init__(config=config, is_simulation=is_simulation)
        self.scheduler.config.weekday_symbol = "GOLD"
        self.scheduler.config.weekend_symbol = "GOLD"
        if "GOLD" in self.config.symbols:
            g = self.config.symbols["GOLD"]
            g.basket_size = self.config.basket.basket_size
            g.max_basket_size = self.config.basket.max_basket_size
            g.basket_tp_usd = self.config.basket_tp.basket_tp_usd
            g.tp_usd_per_min_lot = self.config.individual_tp.tp_usd_per_min_lot
            g.max_hold_seconds = self.config.holding_time.max_hold_seconds
        self.basket_manager = GoldBasketManager(
            basket_cfg=self.config.basket,
            ind_tp_cfg=self.config.individual_tp,
            basket_tp_cfg=self.config.basket_tp,
            holding_cfg=self.config.holding_time,
        )
