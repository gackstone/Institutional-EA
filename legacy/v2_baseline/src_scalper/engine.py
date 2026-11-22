"""
Master Dual-Market Scalper Engine (GOLD + BTCUSD).
Coordinates the high-frequency event loop (200-500ms):
- Weekdays: GOLD (XAUUSD) active for entries
- Weekends: BTCUSD active for entries
- All days: Continuous monitoring and exit management of existing positions across transitions
- Account-wide safety guards: 30% drawdown stop, 300% margin level, 12 positions ceiling, kill switch
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import ScalperConfig, InstrumentScalperConfig
from src.scalper.symbol_resolver import MultiSymbolResolver, GoldSymbolResolver, BtcSymbolResolver, ResolvedSymbolSpec
from src.scalper.scheduler import MarketScheduler, MarketScheduleDecision
from src.scalper.sizing import SymbolLotSizingEngine, SizingCalculationResult
from src.scalper.direction import SymbolDirectionSelector, DirectionScoreDetail
from src.scalper.basket import MultiBasketManager, GoldBasketManager, ScalperBasket, BasketPosition, BasketState
from src.scalper.risk import AccountRiskManager, GoldRiskManager, RiskCheckVerdict
from src.scalper.executor import GoldOrderExecutor, OrderExecutionResult

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

        # 3. Engines
        self.sizing = SymbolLotSizingEngine(self.config.lot_sizing)
        self.direction_selector = SymbolDirectionSelector(self.config.direction_selection)
        self.basket_manager = MultiBasketManager()
        self.risk = AccountRiskManager(self.config)
        self.executor = GoldOrderExecutor(self.config.execution)

        # Global & Per-symbol Statistics
        self.stats = EngineCycleStats()
        self.symbol_stats: Dict[str, EngineCycleStats] = {
            "GOLD": EngineCycleStats(),
            "BTCUSD": EngineCycleStats(),
        }

        self._is_running: bool = False

    @property
    def symbol_spec(self) -> Optional[ResolvedSymbolSpec]:
        """Backward-compatibility property returning active or primary (GOLD) spec."""
        sched_k = self.scheduler.get_scheduled_symbol_key()
        return self.symbol_specs.get(sched_k) or self.symbol_specs.get("GOLD")

    @symbol_spec.setter
    def symbol_spec(self, val: ResolvedSymbolSpec) -> None:
        if val:
            k = "BTCUSD" if "BTC" in val.canonical.upper() else "GOLD"
            self.symbol_specs[k] = val

    def initialize(self) -> bool:
        """Initializes MT5 terminal, resolves both instruments, and validates safety."""
        logger.info(f"[ENGINE] Initializing {self.config.general.engine_name} v{self.config.general.version}...")

        # 1. Kill switch check
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

                logger.info(
                    f"[ENGINE] Connected to MT5 | Account: {acc_info.login} ({trade_mode}) | "
                    f"Balance: ${acc_info.balance:.2f} | Equity: ${acc_info.equity:.2f}"
                )

                # Resolve all configured symbols (GOLD and BTCUSD)
                for sym_k, resolver in self.resolvers.items():
                    spec = resolver.resolve_with_mt5()
                    if spec:
                        self.symbol_specs[sym_k] = spec
                        logger.info(
                            f"[ENGINE] Resolved {sym_k} -> {spec.symbol} (Tradable: {spec.is_tradable}, Digits: {spec.digits}, Spread: {spec.spread_points} pts)"
                        )
                    else:
                        logger.warning(f"[ENGINE] Could not resolve {sym_k} on broker.")

            except Exception as e:
                logger.error(f"[ENGINE] Exception during MT5 initialization: {e}")
                return False
        else:
            # Simulation environment specs
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
            logger.info("[ENGINE] Initialized DualMarketScalperEngine in SIMULATION mode.")

        self._is_running = True
        return True

    def _get_account_snapshot(self) -> Dict[str, float]:
        """Retrieves real-time account balances and margin state."""
        if not self.is_simulation:
            try:
                import MetaTrader5 as mt5
                info = mt5.account_info()
                if info:
                    return {
                        "balance": float(info.balance),
                        "equity": float(info.equity),
                        "margin": float(info.margin),
                        "free_margin": float(info.margin_free),
                        "margin_level": float(info.margin_level),
                        "trade_mode": "DEMO" if int(getattr(info, "trade_mode", 0)) == 0 else "REAL",
                    }
            except Exception:
                pass
        return {
            "balance": 1000.0,
            "equity": 1000.0,
            "margin": 0.0,
            "free_margin": 1000.0,
            "margin_level": 1000.0,
            "trade_mode": "DEMO",
        }

    def _sync_active_positions(self) -> None:
        """Synchronizes active positions across ALL instruments from MT5."""
        if not self.is_simulation:
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
    ) -> None:
        """
        Executes a single cycle of the 200-500ms loop:
        1. Safety & Kill Switch Checks
        2. Account & Floating Drawdown Snapshot across both symbols
        3. Synchronizes active positions for all open baskets
        4. Evaluates exits on ALL open baskets (managing outgoing positions across schedule transitions)
        5. Schedules and routes NEW basket entry to active instrument (GOLD on weekdays, BTCUSD on weekends)
        """
        self.stats.total_cycles += 1

        # 1. Kill Switch Check
        ks = self.risk.check_kill_switch()
        if not ks.allowed:
            logger.critical(f"[ENGINE] Halting cycle: {ks.reason}")
            self.emergency_shutdown(reason=ks.reason)
            return

        # 2. Account & Floating Drawdown Check
        acc = self._get_account_snapshot()
        bal = acc["balance"]
        eq = acc["equity"]

        if bal > 0 and eq < bal:
            cur_dd = ((bal - eq) / bal) * 100.0
            if cur_dd > self.stats.max_floating_drawdown_pct:
                self.stats.max_floating_drawdown_pct = round(cur_dd, 2)

        dd_check = self.risk.check_drawdown(bal, eq)
        if not dd_check.allowed:
            self.stats.rejection_reasons["DRAWDOWN_LIMIT"] = self.stats.rejection_reasons.get("DRAWDOWN_LIMIT", 0) + 1
            self.emergency_shutdown(reason=dd_check.reason)
            return

        # 3. Synchronize Active Positions
        self._sync_active_positions()

        # Update peak open positions stat across all instruments
        total_open_pos = sum(b.position_count for b in self.basket_manager.get_all_active_baskets())
        if total_open_pos > self.stats.max_open_positions_seen:
            self.stats.max_open_positions_seen = total_open_pos

        # 4. Evaluate Exits Across ALL Active Baskets (GOLD and BTCUSD)
        # This guarantees existing positions are managed to completion even across transitions!
        exit_triggers = self.basket_manager.evaluate_all_exits()
        for sym_k, tickets, reason in exit_triggers:
            basket = self.basket_manager.get_active_basket(sym_k)
            if not basket:
                continue
            is_buy = basket.direction == "BUY"
            spec = self.symbol_specs.get(sym_k)
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
                    self.basket_manager.on_position_closed(t, realized_pnl=pos.net_profit if pos else 0.0, symbol_key=sym_k)
                    pnl = pos.net_profit if pos else 0.0
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

            if len(basket.positions) == 0:
                self.basket_manager.close_basket(sym_k, reason=reason)
                self.stats.total_baskets_closed += 1
                self.symbol_stats[sym_k].total_baskets_closed += 1
                self.stats.net_profit_usd = round(self.stats.gross_profit_usd - self.stats.gross_loss_usd, 2)
                self.symbol_stats[sym_k].net_profit_usd = round(
                    self.symbol_stats[sym_k].gross_profit_usd - self.symbol_stats[sym_k].gross_loss_usd, 2
                )

        # 5. Market Scheduler Evaluation for NEW entries
        sched_key = self.scheduler.get_scheduled_symbol_key(current_dt)
        sched_spec = self.symbol_specs.get(sched_key)
        decision = self.scheduler.evaluate_market_status(sched_spec, current_dt)

        if not decision.is_entry_permitted:
            # Market closed on broker or symbol not tradable -> skip new entries
            logger.debug(f"[ENGINE] Entry skipped for {sched_key}: {decision.reason}")
            return

        # Check if active basket already exists for scheduled symbol
        if not self.basket_manager.has_active_basket(sched_key) and self.basket_manager.is_reentry_ready(sched_key):
            self._attempt_basket_entry(sched_key, acc, sim_ticks, sim_candles, strategy_bias)

    def _attempt_basket_entry(
        self,
        symbol_key: str,
        account: Dict[str, float],
        ticks: Optional[List[Any]],
        candles: Optional[List[Any]],
        strategy_bias: Optional[float],
    ) -> None:
        """Dispatches a new basket on the active instrument."""
        sym_k = symbol_key.upper()
        sym_cfg = self.config.symbols.get(sym_k)
        if not sym_cfg or not sym_cfg.enabled:
            return

        spec = self.symbol_specs.get(sym_k)
        if not spec or not spec.is_tradable:
            return

        # Check instrument-specific spread
        spread_pts = spec.spread_points
        sp_check = self.risk.check_spread(sym_k, spread_pts)
        if not sp_check.allowed:
            self.stats.rejection_reasons["SPREAD_TOO_HIGH"] = self.stats.rejection_reasons.get("SPREAD_TOO_HIGH", 0) + 1
            return

        # Dynamic lot sizing tailored to instrument
        sizing_res = self.sizing.calculate_lot(account["balance"], spec=spec, instrument_config=sym_cfg)
        if not sizing_res.is_safe or sizing_res.lot <= 0:
            self.stats.rejection_reasons["SIZING_UNSAFE"] = self.stats.rejection_reasons.get("SIZING_UNSAFE", 0) + 1
            return

        # Check global account-wide capacity
        basket_size = sym_cfg.basket_size
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

        # Select direction (infallible BUY or SELL)
        dir_detail = self.direction_selector.select_direction(
            ticks=ticks,
            m1_candles=candles,
            strategy_bias=strategy_bias,
            canonical=sym_cfg.canonical,
            instrument_config=sym_cfg,
        )
        direction = dir_detail.selected_direction

        # Start Basket
        basket = self.basket_manager.start_new_basket(
            symbol_key=sym_k,
            symbol=spec.symbol,
            direction=direction,
            target_size=basket_size,
            magic_number=sym_cfg.magic_number,
            basket_tp_usd=sym_cfg.basket_tp_usd,
            tp_usd_per_min_lot=sym_cfg.tp_usd_per_min_lot,
            max_hold_seconds=sym_cfg.max_hold_seconds,
        )
        self.stats.total_baskets_opened += 1
        self.symbol_stats[sym_k].total_baskets_opened += 1
        logger.info(
            f"[ENGINE] Initiating {sym_k} basket {basket.basket_id} on {spec.symbol} | Direction: {direction} | "
            f"Size: {basket_size} | Lot/pos: {sizing_res.lot} | Magic: {sym_cfg.magic_number}"
        )

        spacing_sec = max(0.01, sym_cfg.order_spacing_ms / 1000.0)
        pt = spec.point

        for i in range(basket_size):
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
                comment=f"{sym_cfg.comment_prefix}_{basket.basket_id[-4:]}_{i+1}",
                magic=sym_cfg.magic_number,
                spec=spec,
                is_simulation=self.is_simulation,
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
                )
                basket.add_position(bpos)
            else:
                self.stats.total_orders_rejected += 1
                self.symbol_stats[sym_k].total_orders_rejected += 1
                rej_key = res.error_message or "ORDER_REJECTED"
                self.stats.rejection_reasons[rej_key] = self.stats.rejection_reasons.get(rej_key, 0) + 1
                logger.warning(f"[ENGINE] {sym_k} order {i+1}/{basket_size} failed: {res.error_message}")

            if i < basket_size - 1:
                time.sleep(spacing_sec)

        if len(basket.positions) == 0:
            logger.error(f"[ENGINE] All orders for {sym_k} basket {basket.basket_id} failed. Closing basket and repriming.")
            self.basket_manager.close_basket(sym_k, reason="ALL_ORDERS_FAILED")

    def emergency_shutdown(self, reason: str = "EMERGENCY_SHUTDOWN") -> None:
        """Immediately closes all positions owned by scalper across BOTH instruments."""
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
        self._is_running = False


# Backward-compatible GoldScalperEngine class
class GoldScalperEngine(DualMarketScalperEngine):
    """
    Subclass preserving 100% backward compatibility for single-symbol GOLD callers and test suites.
    """

    def __init__(self, config: Optional[ScalperConfig] = None, is_simulation: bool = False):
        super().__init__(config=config, is_simulation=is_simulation)
        # Single-symbol GOLD engine always routes to GOLD regardless of day-of-week
        self.scheduler.config.weekday_symbol = "GOLD"
        self.scheduler.config.weekend_symbol = "GOLD"
        # Sync legacy config proxies into symbols["GOLD"]
        if "GOLD" in self.config.symbols:
            g = self.config.symbols["GOLD"]
            g.basket_size = self.config.basket.basket_size
            g.max_basket_size = self.config.basket.max_basket_size
            g.basket_tp_usd = self.config.basket_tp.basket_tp_usd
            g.tp_usd_per_min_lot = self.config.individual_tp.tp_usd_per_min_lot
            g.max_hold_seconds = self.config.holding_time.max_hold_seconds
        # Use GoldBasketManager for direct legacy access to .active_basket and .closed_baskets
        self.basket_manager = GoldBasketManager(
            basket_cfg=self.config.basket,
            ind_tp_cfg=self.config.individual_tp,
            basket_tp_cfg=self.config.basket_tp,
            holding_cfg=self.config.holding_time,
        )
