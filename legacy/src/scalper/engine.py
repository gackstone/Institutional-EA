"""
Master GOLD Scalper Engine.
Coordinates the high-frequency event loop (200-500ms):
Analyze -> Select Direction -> Open Basket -> Monitor Profit -> Close Basket -> Re-enter.
Integrates symbol resolution, dynamic lot sizing, directional scoring, basket management,
and mandatory safety/circuit-breaker protections.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import ScalperConfig
from src.scalper.symbol_resolver import GoldSymbolResolver, ResolvedSymbolSpec
from src.scalper.sizing import GoldLotSizingEngine, SizingCalculationResult
from src.scalper.direction import GoldDirectionSelector, DirectionScoreDetail
from src.scalper.basket import GoldBasketManager, GoldBasket, BasketPosition, BasketState
from src.scalper.risk import GoldRiskManager, RiskCheckVerdict
from src.scalper.executor import GoldOrderExecutor, OrderExecutionResult

logger = logging.getLogger("GoldScalperEngine")


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


class GoldScalperEngine:
    def __init__(self, config: Optional[ScalperConfig] = None, is_simulation: bool = False):
        self.config = config or ScalperConfig.load()
        self.is_simulation = is_simulation

        # Initialize subcomponents
        self.resolver = GoldSymbolResolver(
            aliases=self.config.symbol.aliases,
            fallback=self.config.symbol.fallback_symbol,
        )
        self.symbol_spec: Optional[ResolvedSymbolSpec] = None

        self.sizing = GoldLotSizingEngine(self.config.lot_sizing)
        self.direction_selector = GoldDirectionSelector(self.config.direction_selection)
        self.basket_manager = GoldBasketManager(
            basket_cfg=self.config.basket,
            ind_tp_cfg=self.config.individual_tp,
            basket_tp_cfg=self.config.basket_tp,
            holding_cfg=self.config.holding_time,
        )
        self.risk = GoldRiskManager(self.config)
        self.executor = GoldOrderExecutor(self.config.execution)

        self.stats = EngineCycleStats()
        self._is_running: bool = False
        self._last_tick_time: float = 0.0

    def initialize(self) -> bool:
        """Initializes terminal connection and resolves GOLD symbol."""
        logger.info(f"[ENGINE] Initializing {self.config.general.engine_name} v{self.config.general.version}...")

        # 1. Kill-switch check
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

                # Resolve Gold Symbol
                self.symbol_spec = self.resolver.resolve_with_mt5()
                if not self.symbol_spec or not self.symbol_spec.is_tradable:
                    logger.error("[ENGINE] Could not resolve a valid tradable Gold symbol.")
                    return False

            except Exception as e:
                logger.error(f"[ENGINE] Exception during initialization: {e}")
                return False
        else:
            # Simulation environment defaults
            self.symbol_spec = ResolvedSymbolSpec(
                symbol="XAUUSD",
                digits=2,
                point=0.01,
                tick_size=0.01,
                tick_value=1.0,
                min_lot=0.01,
                max_lot=100.0,
                lot_step=0.01,
                filling_mode=2,
                bid=2650.00,
                ask=2650.30,
                spread_points=30.0,
                is_tradable=True,
            )
            logger.info("[ENGINE] Initialized in SIMULATION mode.")

        self._is_running = True
        return True

    def _get_account_snapshot(self) -> Dict[str, float]:
        """Retrieves real-time account balances and margins."""
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
        """Synchronizes active basket positions with MT5 terminal."""
        if not self.basket_manager.has_active_basket():
            return
        basket = self.basket_manager.active_basket
        if not basket:
            return

        if not self.is_simulation:
            try:
                import MetaTrader5 as mt5
                pos_list = mt5.positions_get(symbol=self.symbol_spec.symbol) or []
                live_tickets = {p.ticket: p for p in pos_list if p.magic == self.config.general.magic_number}

                # Update existing positions
                tracked_tickets = list(basket.positions.keys())
                for t in tracked_tickets:
                    if t in live_tickets:
                        lp = live_tickets[t]
                        basket.update_position(
                            ticket=t,
                            current_price=float(lp.price_current),
                            profit=float(lp.profit),
                            commission=float(getattr(lp, "commission", 0.0) or 0.0),
                            swap=float(getattr(lp, "swap", 0.0) or 0.0),
                        )
                    else:
                        # Position closed externally or via broker SL/TP
                        basket.remove_position(t)
                        self.stats.winning_trades += 1  # Reconciled in basket
            except Exception as e:
                logger.debug(f"[ENGINE] Error synchronizing active positions: {e}")

    def run_single_tick_cycle(
        self,
        sim_ticks: Optional[List[Any]] = None,
        sim_candles: Optional[List[Any]] = None,
        strategy_bias: Optional[float] = None,
    ) -> None:
        """
        Executes a single cycle of the 200-500ms loop:
        1. Safety & Kill Switch Checks
        2. Account & Position Sync
        3. Basket Exit Evaluation
        4. Immediate Re-entry / Basket Generation
        """
        self.stats.total_cycles += 1

        # 1. Kill Switch & Risk Checks
        ks = self.risk.check_kill_switch()
        if not ks.allowed:
            logger.critical(f"[ENGINE] Halting cycle: {ks.reason}")
            self.emergency_shutdown(reason=ks.reason)
            return

        # 2. Account & Quote Snapshot
        acc = self._get_account_snapshot()
        bal = acc["balance"]
        eq = acc["equity"]

        # Track Drawdown
        if bal > 0 and eq < bal:
            cur_dd = ((bal - eq) / bal) * 100.0
            if cur_dd > self.stats.max_floating_drawdown_pct:
                self.stats.max_floating_drawdown_pct = round(cur_dd, 2)

        dd_check = self.risk.check_drawdown(bal, eq)
        if not dd_check.allowed:
            self.stats.rejection_reasons["DRAWDOWN_LIMIT"] = self.stats.rejection_reasons.get("DRAWDOWN_LIMIT", 0) + 1
            self.emergency_shutdown(reason=dd_check.reason)
            return

        # 3. Synchronize Active Basket Positions
        self._sync_active_positions()

        # Update peak position count stat
        cur_pos_count = self.basket_manager.active_basket.position_count if self.basket_manager.active_basket else 0
        if cur_pos_count > self.stats.max_open_positions_seen:
            self.stats.max_open_positions_seen = cur_pos_count

        # 4. Basket Exit Evaluation
        if self.basket_manager.has_active_basket():
            tickets_to_close, exit_reason = self.basket_manager.evaluate_exits()
            if tickets_to_close:
                basket = self.basket_manager.active_basket
                is_buy = basket.direction == "BUY"
                for t in tickets_to_close:
                    pos = basket.positions.get(t)
                    vol = pos.volume if pos else self.config.lot_sizing.micro_account_min_lot
                    close_res = self.executor.close_position(
                        ticket=t,
                        symbol=self.symbol_spec.symbol,
                        volume=vol,
                        is_buy=is_buy,
                        spec=self.symbol_spec,
                        is_simulation=self.is_simulation,
                    )
                    if close_res.is_success:
                        self.basket_manager.on_position_closed(t, realized_pnl=pos.net_profit if pos else 0.0)
                        if pos and pos.net_profit >= 0:
                            self.stats.winning_trades += 1
                            self.stats.gross_profit_usd += pos.net_profit
                        elif pos:
                            self.stats.losing_trades += 1
                            self.stats.gross_loss_usd += abs(pos.net_profit)

                if len(basket.positions) == 0:
                    self.basket_manager.close_active_basket(reason=exit_reason or "EXIT_TRIGGERED")
                    self.stats.total_baskets_closed += 1
                    self.stats.net_profit_usd = round(self.stats.gross_profit_usd - self.stats.gross_loss_usd, 2)

        # 5. Immediate Basket Entry Evaluation
        # If no active basket exists and we are ready for re-entry:
        if not self.basket_manager.has_active_basket() and self.basket_manager.ready_for_reentry:
            self._attempt_basket_entry(acc, sim_ticks, sim_candles, strategy_bias)

    def _attempt_basket_entry(
        self,
        account: Dict[str, float],
        ticks: Optional[List[Any]],
        candles: Optional[List[Any]],
        strategy_bias: Optional[float]
    ) -> None:
        """Evaluates entry conditions, selects direction, sizes lot, and fires basket burst."""
        # Check spread
        spread_pts = self.symbol_spec.spread_points if self.symbol_spec else 30.0
        sp_check = self.risk.check_spread(spread_pts)
        if not sp_check.allowed:
            self.stats.rejection_reasons["SPREAD_TOO_HIGH"] = self.stats.rejection_reasons.get("SPREAD_TOO_HIGH", 0) + 1
            return

        # Calculate lot size
        sizing_res = self.sizing.calculate_lot(account["balance"], self.symbol_spec)
        if not sizing_res.is_safe or sizing_res.lot <= 0:
            self.stats.rejection_reasons["SIZING_UNSAFE"] = self.stats.rejection_reasons.get("SIZING_UNSAFE", 0) + 1
            return

        # Check margin and capacity limits for the whole basket
        basket_size = self.config.basket.basket_size
        projected_basket_lots = round(sizing_res.lot * basket_size, 4)
        cap_check = self.risk.check_margin_and_capacity(
            account_balance=account["balance"],
            account_equity=account["equity"],
            account_margin=account["margin"],
            account_free_margin=account["free_margin"],
            current_open_positions=0,
            current_total_lots=0.0,
            proposed_lot=projected_basket_lots,
        )
        if not cap_check.allowed:
            self.stats.rejection_reasons[cap_check.category] = self.stats.rejection_reasons.get(cap_check.category, 0) + 1
            return

        # Select direction (Always returns BUY or SELL)
        dir_detail = self.direction_selector.select_direction(
            ticks=ticks,
            m1_candles=candles,
            strategy_bias=strategy_bias,
        )
        direction = dir_detail.selected_direction

        # Start Basket
        basket = self.basket_manager.start_new_basket(direction=direction, target_size=basket_size)
        self.stats.total_baskets_opened += 1
        logger.info(
            f"[ENGINE] Initiating basket {basket.basket_id} | {direction} | Size: {basket_size} | "
            f"Lot per pos: {sizing_res.lot} | Source: {dir_detail.decision_source} (Bias: {dir_detail.composite_bias})"
        )

        # Submit Basket Orders rapidly within 1-2 seconds
        spacing_sec = max(0.01, self.config.basket.order_spacing_ms / 1000.0)
        sym = self.symbol_spec.symbol
        pt = self.symbol_spec.point

        for i in range(basket_size):
            self.stats.total_orders_submitted += 1

            # Estimate protective SL based on current quote
            curr_px = (self.symbol_spec.ask if direction == "BUY" else self.symbol_spec.bid) or 2650.00
            protective_sl = self.risk.calculate_protective_sl(direction, curr_px, pt)

            res = self.executor.submit_market_order(
                symbol=sym,
                direction=direction,
                volume=sizing_res.lot,
                stop_loss=protective_sl,
                take_profit=0.0,  # Managed by individual/basket TP engine
                comment=f"GS_{basket.basket_id[-4:]}_{i+1}",
                magic=self.config.general.magic_number,
                spec=self.symbol_spec,
                is_simulation=self.is_simulation,
            )

            if res.is_success:
                self.stats.total_orders_filled += 1
                bpos = BasketPosition(
                    ticket=res.ticket,
                    symbol=sym,
                    direction=direction,
                    volume=res.volume,
                    open_price=res.price,
                    current_price=res.price,
                    stop_loss=protective_sl,
                )
                basket.add_position(bpos)
            else:
                self.stats.total_orders_rejected += 1
                rej_key = res.error_message or "ORDER_REJECTED"
                self.stats.rejection_reasons[rej_key] = self.stats.rejection_reasons.get(rej_key, 0) + 1
                logger.warning(f"[ENGINE] Basket order {i+1}/{basket_size} failed: {res.error_message}")

            if i < basket_size - 1:
                time.sleep(spacing_sec)

        # If all orders in basket failed, close basket and re-prime
        if len(basket.positions) == 0:
            logger.error(f"[ENGINE] All orders for basket {basket.basket_id} failed. Closing basket and repriming.")
            self.basket_manager.close_active_basket(reason="ALL_ORDERS_FAILED")

    def emergency_shutdown(self, reason: str = "EMERGENCY_SHUTDOWN") -> None:
        """Immediately closes all positions owned by scalper and halts engine."""
        logger.critical(f"[SHUTDOWN] Emergency liquidation triggered: {reason}")
        if self.basket_manager.has_active_basket():
            basket = self.basket_manager.active_basket
            is_buy = basket.direction == "BUY"
            for t, pos in list(basket.positions.items()):
                self.executor.close_position(
                    ticket=t,
                    symbol=self.symbol_spec.symbol,
                    volume=pos.volume,
                    is_buy=is_buy,
                    spec=self.symbol_spec,
                    is_simulation=self.is_simulation,
                )
                basket.remove_position(t)
            self.basket_manager.close_active_basket(reason=reason)
        self._is_running = False
