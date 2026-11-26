"""
Dynamic Trade and Position Management Engine.
Manages open positions during their lifecycle supporting Dual-Mode Intelligent Profit Management:
- MODE A: QUICK_SCALP (Rapid $20 net profit target full closure & slot recycling)
- MODE B: PROFIT_RUNNING ($20 minimum profit protection & progressive trend trailing to $35, $60+)

Key Capabilities:
- Deterministic 12-stage position management state machine
- Account-currency-aware Net Floating Profit calculation (gross + commission + swap + exit costs)
- Exact monetary Stop-Loss calculation guaranteeing at least $20.00 net profit protection
- Progressive profit ratchets ($35, $60, $80+) and structural/ATR trailing
- Adaptive Exit Intelligence on structural reversal or momentum stall
- Broker stop-distance compliance (stops_level / freeze_level) and Rule R9.3 preservation
- Robust state persistence to disk (surviving restarts and disconnects)
- Dual-mode institutional performance metrics tracking
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import RiskConfig
from src.core.contracts import (
    Candle,
    OrderType,
    PlanAmendment,
    Position,
    PositionManagementState,
    ProfitManagementMode,
    SymbolInfo,
)
from src.risk.mode_selector import ModeSelectionEngine

logger = logging.getLogger("TradeManagement")


@dataclass
class PositionAction:
    ticket: int
    symbol: str
    action_type: str  # "MODIFY_SL", "PARTIAL_CLOSE", "FULL_CLOSE"
    new_sl: Optional[float] = None
    close_volume: Optional[float] = None
    reason: str = ""
    amendment: Optional[PlanAmendment] = None


@dataclass
class BasketAction:
    action_type: str  # "CLOSE_BASKET", "TRAILING_BASKET_EXIT"
    symbol: str
    direction: OrderType
    tickets: List[int]
    positions: List[Position]
    gross_profit_usd: float
    commission_usd: float
    swap_usd: float
    estimated_exit_costs_usd: float
    basket_net_profit_usd: float
    reason: str


@dataclass
class ModePerformanceStats:
    mode: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    net_realized_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_commission: float = 0.0
    total_swap: float = 0.0
    total_holding_duration_seconds: float = 0.0
    trades_reaching_20: int = 0
    trades_protecting_20_successfully: int = 0
    total_profit_beyond_20: float = 0.0
    total_profit_surrendered_after_20: float = 0.0
    stop_modification_attempts: int = 0
    stop_modification_successes: int = 0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0

    @property
    def win_rate(self) -> float:
        return round((self.winning_trades / self.total_trades) * 100.0, 2) if self.total_trades > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        if abs(self.gross_loss) > 1e-6:
            return round(self.gross_profit / abs(self.gross_loss), 2)
        return round(self.gross_profit, 2) if self.gross_profit > 0 else 1.0

    @property
    def average_win(self) -> float:
        return round(self.gross_profit / self.winning_trades, 2) if self.winning_trades > 0 else 0.0

    @property
    def average_loss(self) -> float:
        return round(self.gross_loss / self.losing_trades, 2) if self.losing_trades > 0 else 0.0

    @property
    def average_holding_duration_minutes(self) -> float:
        if self.total_trades > 0:
            return round((self.total_holding_duration_seconds / self.total_trades) / 60.0, 1)
        return 0.0

    @property
    def pct_reaching_20(self) -> float:
        return round((self.trades_reaching_20 / self.total_trades) * 100.0, 1) if self.total_trades > 0 else 0.0

    @property
    def pct_protecting_20(self) -> float:
        return round((self.trades_protecting_20_successfully / self.trades_reaching_20) * 100.0, 1) if self.trades_reaching_20 > 0 else 0.0

    @property
    def avg_profit_beyond_20(self) -> float:
        return round(self.total_profit_beyond_20 / self.trades_reaching_20, 2) if self.trades_reaching_20 > 0 else 0.0

    @property
    def stop_modification_success_rate(self) -> float:
        if self.stop_modification_attempts > 0:
            return round((self.stop_modification_successes / self.stop_modification_attempts) * 100.0, 1)
        return 100.0

    @property
    def expectancy(self) -> float:
        return round(self.net_realized_pnl / self.total_trades, 2) if self.total_trades > 0 else 0.0


class DualModePerformanceTracker:
    def __init__(self):
        self.stats: Dict[str, ModePerformanceStats] = {
            "QUICK_SCALP": ModePerformanceStats(mode="QUICK_SCALP"),
            "PROFIT_RUNNING": ModePerformanceStats(mode="PROFIT_RUNNING"),
        }

    def record_reach_20(self, mode: str) -> None:
        m_key = "PROFIT_RUNNING" if "RUN" in str(mode).upper() else "QUICK_SCALP"
        self.stats[m_key].trades_reaching_20 += 1

    def record_protect_20_success(self, mode: str) -> None:
        m_key = "PROFIT_RUNNING" if "RUN" in str(mode).upper() else "QUICK_SCALP"
        self.stats[m_key].trades_protecting_20_successfully += 1

    def record_stop_mod_attempt(self, mode: str, success: bool) -> None:
        m_key = "PROFIT_RUNNING" if "RUN" in str(mode).upper() else "QUICK_SCALP"
        self.stats[m_key].stop_modification_attempts += 1
        if success:
            self.stats[m_key].stop_modification_successes += 1

    def record_closed_trade(
        self,
        mode: str,
        pnl: float,
        gross: float,
        commission: float,
        swap: float,
        holding_seconds: float,
        reached_20: bool,
        protected_20: bool,
        profit_beyond_20: float = 0.0,
        surrendered_after_20: float = 0.0,
    ) -> None:
        m_key = "PROFIT_RUNNING" if "RUN" in str(mode).upper() else "QUICK_SCALP"
        s = self.stats[m_key]
        s.total_trades += 1
        s.net_realized_pnl += pnl
        s.total_commission += abs(commission)
        s.total_swap += swap
        s.total_holding_duration_seconds += holding_seconds

        if pnl > 0.01:
            s.winning_trades += 1
            s.gross_profit += pnl
        elif pnl < -0.01:
            s.losing_trades += 1
            s.gross_loss += abs(pnl)
        else:
            s.breakeven_trades += 1

        if reached_20 and s.trades_reaching_20 < s.total_trades:
            s.trades_reaching_20 += 1
        if protected_20 and s.trades_protecting_20_successfully < s.total_trades:
            s.trades_protecting_20_successfully += 1

        s.total_profit_beyond_20 += max(0.0, profit_beyond_20)
        s.total_profit_surrendered_after_20 += max(0.0, surrendered_after_20)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "QUICK_SCALP": self.stats["QUICK_SCALP"],
            "PROFIT_RUNNING": self.stats["PROFIT_RUNNING"],
        }


class BasketProfitManager:
    """
    Evaluates real-time combined net profit across open position baskets.
    Calculates:
      Basket Net Profit = Combined Floating Profit + Swap + Commission - Estimated Exit Costs.
    Triggers rapid basket closure when configured basket profit target (or trailing profit protection floor)
    is satisfied across multi-position scalping layers.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self._peak_basket_profits: Dict[str, float] = {}
        self._basket_closure_requested: Dict[str, bool] = {}

    def get_peak_profit(self, symbol_or_key: str) -> float:
        return self._peak_basket_profits.get(symbol_or_key, 0.0)

    def reset_basket_state(self, symbol_or_key: str) -> None:
        self._peak_basket_profits.pop(symbol_or_key, None)
        self._basket_closure_requested.pop(symbol_or_key, None)

    def evaluate_baskets(
        self,
        active_positions: List[Position],
        symbol_info_map: Dict[str, SymbolInfo],
        target_basket_net_profit_usd: Optional[float] = None,
        basket_trailing_enabled: Optional[bool] = None,
        basket_trailing_floor_usd: Optional[float] = None,
    ) -> List[BasketAction]:
        actions: List[BasketAction] = []
        if not active_positions:
            self._peak_basket_profits.clear()
            self._basket_closure_requested.clear()
            return actions

        target_target = float(
            target_basket_net_profit_usd
            if target_basket_net_profit_usd is not None
            else getattr(self.config, "basket_profit_target_usd", 20.0)
        )
        trailing_on = bool(
            basket_trailing_enabled
            if basket_trailing_enabled is not None
            else getattr(self.config, "basket_trailing_enabled", True)
        )
        trailing_floor = float(
            basket_trailing_floor_usd
            if basket_trailing_floor_usd is not None
            else getattr(self.config, "basket_trailing_floor_usd", 10.0)
        )

        # Group positions by symbol and direction
        baskets: Dict[str, List[Position]] = {}
        for pos in active_positions:
            key = f"{pos.symbol}_{pos.order_type.value}"
            baskets.setdefault(key, []).append(pos)

        # Clear inactive keys
        active_keys = set(baskets.keys())
        for old_k in list(self._peak_basket_profits.keys()):
            if old_k not in active_keys:
                self.reset_basket_state(old_k)

        for key, basket in baskets.items():
            first_pos = basket[0]
            sym = first_pos.symbol
            direction = first_pos.order_type
            sym_info = symbol_info_map.get(sym) or SymbolInfo(symbol=sym)

            gross_profit = sum(float(p.profit) for p in basket)
            commission = sum(float(getattr(p, "commission", 0.0) or 0.0) for p in basket)
            swap = sum(float(getattr(p, "swap", 0.0) or 0.0) for p in basket)
            exit_costs = sum(TradeManagementEngine.estimate_closing_costs(p, sym_info) for p in basket)
            basket_net = round(gross_profit + commission + swap - exit_costs, 2)

            peak_net = max(self._peak_basket_profits.get(key, 0.0), basket_net)
            self._peak_basket_profits[key] = peak_net

            logger.debug(
                f"[BASKET] {key}: count={len(basket)}, gross=${gross_profit:.2f}, comm=${commission:.2f}, "
                f"swap=${swap:.2f}, costs=${exit_costs:.2f} => Net=${basket_net:.2f} (Peak=${peak_net:.2f}, Target=${target_target:.2f})"
            )

            if self._basket_closure_requested.get(key, False):
                continue

            # 1. Full Target Achievement
            if basket_net >= target_target:
                self._basket_closure_requested[key] = True
                action = BasketAction(
                    action_type="CLOSE_BASKET",
                    symbol=sym,
                    direction=direction,
                    tickets=[p.ticket for p in basket],
                    positions=list(basket),
                    gross_profit_usd=gross_profit,
                    commission_usd=commission,
                    swap_usd=swap,
                    estimated_exit_costs_usd=exit_costs,
                    basket_net_profit_usd=basket_net,
                    reason=(
                        f"[SCALPING][INFO] Basket profit target reached: ${basket_net:.2f} >= ${target_target:.2f} "
                        f"across {len(basket)} positions on {sym}"
                    ),
                )
                logger.info(
                    f"[SCALPING][SUCCESS] Basket closure triggered for {key}: ${basket_net:.2f} net >= ${target_target:.2f} "
                    f"target across {len(basket)} positions (Tickets: {[p.ticket for p in basket]})"
                )
                actions.append(action)
                continue

            # 2. Dynamic Trailing Basket Profit Protection
            if trailing_on and peak_net >= trailing_floor:
                trail_threshold = max(trailing_floor * 0.65, peak_net * 0.72)
                if basket_net <= trail_threshold and basket_net > 0.0:
                    self._basket_closure_requested[key] = True
                    action = BasketAction(
                        action_type="TRAILING_BASKET_EXIT",
                        symbol=sym,
                        direction=direction,
                        tickets=[p.ticket for p in basket],
                        positions=list(basket),
                        gross_profit_usd=gross_profit,
                        commission_usd=commission,
                        swap_usd=swap,
                        estimated_exit_costs_usd=exit_costs,
                        basket_net_profit_usd=basket_net,
                        reason=(
                            f"[SCALPING][INFO] Basket trailing profit floor triggered: secured ${basket_net:.2f} net "
                            f"(peak was ${peak_net:.2f}) across {len(basket)} positions on {sym}"
                        ),
                    )
                    logger.info(
                        f"[SCALPING][SUCCESS] Basket trailing floor exit for {key}: banking ${basket_net:.2f} net "
                        f"(peak was ${peak_net:.2f}) across {len(basket)} positions"
                    )
                    actions.append(action)

        return actions


class TradeManagementEngine:
    def __init__(self, config: Optional[RiskConfig] = None, persistence_path: Optional[str] = None):
        self.config = config or RiskConfig()
        self._persistence_file = Path(persistence_path) if persistence_path else None
        self._position_states: Dict[int, Dict[str, Any]] = {}
        self.performance_tracker = DualModePerformanceTracker()
        self.basket_manager = BasketProfitManager(config=self.config)
        if self._persistence_file:
            self._load_states_from_disk()

    def evaluate_baskets(
        self,
        active_positions: List[Position],
        symbol_info_map: Dict[str, SymbolInfo],
        target_basket_net_profit_usd: Optional[float] = None,
        basket_trailing_enabled: Optional[bool] = None,
        basket_trailing_floor_usd: Optional[float] = None,
    ) -> List[BasketAction]:
        return self.basket_manager.evaluate_baskets(
            active_positions=active_positions,
            symbol_info_map=symbol_info_map,
            target_basket_net_profit_usd=target_basket_net_profit_usd,
            basket_trailing_enabled=basket_trailing_enabled,
            basket_trailing_floor_usd=basket_trailing_floor_usd,
        )

    # =========================================================================
    # STATE MACHINE & PERSISTENCE
    # =========================================================================

    def transition_state(self, ticket: int, new_state: PositionManagementState, reason: str = "") -> None:
        """
        Executes a deterministic state transition in the 12-stage lifecycle.
        Logs the transition and persists updated state to disk.
        """
        ticket = int(ticket)
        state = self._position_states.get(ticket)
        if state is not None:
            old_state = state.get("management_state", "UNKNOWN")
            target_str = new_state.value if hasattr(new_state, "value") else str(new_state)
            state["management_state"] = target_str
            state["last_state_transition"] = datetime.now(timezone.utc).isoformat()
            state["last_transition_reason"] = reason
            logger.info(f"[STATE_MACHINE] Ticket #{ticket} transitioned {old_state} -> {target_str} | {reason}")
            self._save_states_to_disk()

    def _restore_state(self, position: Position) -> Dict[str, Any]:
        """
        Retrieves or initializes independent lifecycle telemetry for a position.
        Ensures selected mode and management state are tracked per ticket.
        """
        ticket = int(position.ticket)

        # Determine mode from position attribute, comment, or default
        if getattr(self.config, "enable_partial_at_1r", False) or getattr(self.config, "enable_swing_trailing", False):
            assigned_mode_str = "CLASSIC"
        else:
            assigned_mode = getattr(position, "profit_mode", None)
            if hasattr(assigned_mode, "value"):
                assigned_mode_str = assigned_mode.value
            elif assigned_mode:
                assigned_mode_str = str(assigned_mode)
            else:
                comm = str(getattr(position, "comment", "")).upper()
                if comm.startswith("SCALP") or "FAST" in comm:
                    assigned_mode_str = "QUICK_SCALP"
                elif "RUN" in comm or "SMC" in comm:
                    assigned_mode_str = "PROFIT_RUNNING"
                else:
                    assigned_mode_str = "QUICK_SCALP"

        state = self._position_states.setdefault(
            ticket,
            {
                "ticket": ticket,
                "symbol": position.symbol,
                "direction": position.order_type.value,
                "entry_price": position.open_price,
                "initial_sl": getattr(position, "initial_sl", position.stop_loss),
                "current_sl": position.stop_loss,
                "volume": position.volume,
                "initial_monetary_risk": float(getattr(position, "initial_risk_amount", 0.0) or 0.0),
                "current_floating_net_profit": 0.0,
                "accrued_commission": float(getattr(position, "commission", 0.0) or 0.0),
                "swap": float(getattr(position, "swap", 0.0) or 0.0),
                "estimated_closing_costs": 0.0,
                "target_profit": float(getattr(self.config, "target_net_profit_usd", 20.0)),
                "profit_lock_status": "NONE",
                "strategy_attribution": str(getattr(position, "comment", "")),
                "entry_timestamp": getattr(position, "open_time", None).isoformat() if getattr(position, "open_time", None) else None,
                "validity_state": "ACTIVE",
                "peak_net_profit": 0.0,
                "break_even_activated": False,
                "partial_taken": False,
                "profit_floor_locked": False,
                "realized_net_profit": None,
                # Dual-mode fields
                "profit_mode": assigned_mode_str,
                "management_state": PositionManagementState.PROTECTED.value if position.stop_loss > 0 else PositionManagementState.OPEN_UNPROTECTED.value,
                "profit_lock_sl_price": 0.0,
                "locked_net_profit_usd": 0.0,
                "highest_locked_profit": 0.0,
                "profit_protection_active": False,
                "reached_20_timestamp": None,
                "protected_20_timestamp": None,
                "close_requested": False,
            },
        )

        position.peak_net_profit = max(
            float(getattr(position, "peak_net_profit", 0.0) or 0.0),
            float(state.get("peak_net_profit", 0.0) or 0.0),
        )
        if state.get("break_even_activated"):
            position.break_even_activated = True
        if state.get("partial_taken"):
            position.partial_taken = True
        if state.get("profit_floor_locked"):
            position.profit_floor_locked = True

        position.profit_lock_status = state.get("profit_lock_status", "NONE")
        position.target_profit = float(state.get("target_profit", 20.0))
        position.validity_state = state.get("validity_state", "ACTIVE")

        # Sync dual-mode contracts
        mode_val = state.get("profit_mode", "QUICK_SCALP")
        position.profit_mode = ProfitManagementMode(mode_val) if hasattr(ProfitManagementMode, mode_val) else ProfitManagementMode.QUICK_SCALP
        state_val = state.get("management_state", "PROTECTED")
        position.management_state = PositionManagementState(state_val) if hasattr(PositionManagementState, state_val) else PositionManagementState.PROTECTED
        position.locked_net_profit_usd = float(state.get("locked_net_profit_usd", 0.0))
        position.profit_protection_active = bool(state.get("profit_protection_active", False))
        position.highest_locked_profit = float(state.get("highest_locked_profit", 0.0))
        position.profit_lock_sl_price = float(state.get("profit_lock_sl_price", 0.0))

        return state

    def _persist_state(self, position: Position, state: Dict[str, Any]) -> None:
        state["peak_net_profit"] = max(
            float(state.get("peak_net_profit", 0.0) or 0.0),
            float(getattr(position, "peak_net_profit", 0.0) or 0.0),
        )
        state["break_even_activated"] = bool(state.get("break_even_activated")) or bool(
            getattr(position, "break_even_activated", False)
        )
        state["partial_taken"] = bool(state.get("partial_taken")) or bool(
            getattr(position, "partial_taken", False)
        )
        state["profit_floor_locked"] = bool(state.get("profit_floor_locked")) or bool(
            getattr(position, "profit_floor_locked", False)
        )
        state["current_sl"] = float(position.stop_loss)
        state["volume"] = float(position.volume)
        state["profit_lock_status"] = getattr(position, "profit_lock_status", "NONE")
        state["current_floating_net_profit"] = getattr(position, "net_profit", 0.0)
        state["accrued_commission"] = float(getattr(position, "commission", 0.0) or 0.0)
        state["swap"] = float(getattr(position, "swap", 0.0) or 0.0)
        state["estimated_closing_costs"] = float(getattr(position, "estimated_closing_costs", 0.0) or 0.0)
        state["validity_state"] = getattr(position, "validity_state", "ACTIVE")
        state["locked_net_profit_usd"] = float(getattr(position, "locked_net_profit_usd", 0.0))
        state["highest_locked_profit"] = float(getattr(position, "highest_locked_profit", 0.0))
        state["profit_protection_active"] = bool(getattr(position, "profit_protection_active", False))
        self._save_states_to_disk()

    def _save_states_to_disk(self) -> None:
        if not self._persistence_file:
            return
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            serializable = {}
            for t, s in self._position_states.items():
                s_copy = dict(s)
                for k, v in s_copy.items():
                    if isinstance(v, datetime):
                        s_copy[k] = v.isoformat()
                serializable[str(t)] = s_copy
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist position lifecycle states: {e}")

    def _load_states_from_disk(self) -> None:
        if not self._persistence_file:
            return
        try:
            if self._persistence_file.exists():
                with open(self._persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            try:
                                ticket = int(k)
                                self._position_states[ticket] = v
                            except Exception:
                                pass
        except Exception as e:
            logger.warning(f"Failed to load position lifecycle states: {e}")

    def get_position_state(self, ticket: int) -> Optional[Dict[str, Any]]:
        return self._position_states.get(int(ticket))

    def get_all_position_states(self) -> Dict[int, Dict[str, Any]]:
        return dict(self._position_states)

    def record_stop_modification_result(self, ticket: int, success: bool, reason: str = "") -> None:
        """
        Handles broker acknowledgement or rejection of a Stop-Loss modification request.
        Updates state machine and modification success statistics.
        """
        ticket = int(ticket)
        state = self._position_states.get(ticket)
        mode = state.get("profit_mode", "QUICK_SCALP") if state else "QUICK_SCALP"
        self.performance_tracker.record_stop_mod_attempt(mode=mode, success=success)

        if state is not None:
            if success:
                if state.get("management_state") == PositionManagementState.PROFIT_LOCK_PENDING.value:
                    self.transition_state(ticket, PositionManagementState.PROFIT_LOCK_CONFIRMED, "Broker confirmed SL lock")
                    self.transition_state(ticket, PositionManagementState.PROFIT_RUNNING, "Running with active profit protection")
                    state["profit_protection_active"] = True
                    if not state.get("protected_20_timestamp"):
                        state["protected_20_timestamp"] = datetime.now(timezone.utc).isoformat()
                        self.performance_tracker.record_protect_20_success(mode)
            else:
                logger.warning(f"[STOP_MOD] Modification rejected for Ticket #{ticket}: {reason}. Keeping position protected.")
                state["profit_protection_active"] = False

    def reconcile_closed_deal(
        self,
        ticket: int,
        deal_profit: float,
        deal_commission: float = 0.0,
        deal_swap: float = 0.0,
        close_reason: str = ""
    ) -> float:
        """
        Reconciles actual MT5 deal history after closure, calculating true realized net profit:
        realized_net = DEAL_PROFIT + DEAL_COMMISSION + DEAL_SWAP.
        Transitions state: CLOSED_CONFIRMED -> PNL_RECONCILED -> SLOT_RELEASED.
        """
        ticket = int(ticket)
        realized_net = round(deal_profit + deal_commission + deal_swap, 2)
        state = self._position_states.get(ticket)
        if state is not None:
            mode = state.get("profit_mode", "QUICK_SCALP")
            peak_net = float(state.get("peak_net_profit", 0.0) or 0.0)
            reached_20 = bool(state.get("reached_20_timestamp")) or peak_net >= 20.0
            profit_beyond_20 = max(0.0, realized_net - 20.0) if realized_net >= 20.0 else 0.0
            surrendered_after_20 = max(0.0, peak_net - realized_net) if reached_20 and peak_net > realized_net else 0.0

            duration_sec = 0.0
            entry_ts_str = state.get("entry_timestamp")
            if entry_ts_str:
                try:
                    entry_dt = datetime.fromisoformat(entry_ts_str) if isinstance(entry_ts_str, str) else entry_ts_str
                    duration_sec = (datetime.now(timezone.utc) - entry_dt).total_seconds()
                except Exception:
                    pass

            # Record in dual-mode analytics tracker
            self.performance_tracker.record_closed_trade(
                mode=mode,
                pnl=realized_net,
                gross=deal_profit,
                commission=deal_commission,
                swap=deal_swap,
                holding_seconds=duration_sec,
                reached_20=reached_20,
                protected_20=realized_net >= 19.50 and reached_20,
                profit_beyond_20=profit_beyond_20,
                surrendered_after_20=surrendered_after_20,
            )

            state["realized_net_profit"] = realized_net
            state["validity_state"] = "CLOSED"
            state["close_reason"] = close_reason
            state["closed_at"] = datetime.now(timezone.utc).isoformat()
            self.transition_state(ticket, PositionManagementState.CLOSED_CONFIRMED, close_reason)
            self.transition_state(ticket, PositionManagementState.PNL_RECONCILED, f"Realized net ${realized_net:.2f}")
            self.transition_state(ticket, PositionManagementState.SLOT_RELEASED, "Position capacity released")
            self._save_states_to_disk()

            logger.info(
                f"[RECONCILIATION] Position #{ticket} [{mode}] on {state.get('symbol')} closed: "
                f"Gross: ${deal_profit:.2f}, Comm: ${deal_commission:.2f}, Swap: ${deal_swap:.2f} => "
                f"NET REALIZED: ${realized_net:.2f} (Target: ${state.get('target_profit', 20.0):.2f}) | {close_reason}"
            )
        return realized_net

    def forget_position(self, ticket: int) -> None:
        """Drops lifecycle state when a position is fully closed, reconciled, and slot released."""
        self._position_states.pop(int(ticket), None)
        self._save_states_to_disk()

    # =========================================================================
    # TRANSACTION COST & NET PROFIT CALCULATIONS
    # =========================================================================

    @staticmethod
    def estimate_closing_costs(position: Position, symbol_info: SymbolInfo) -> float:
        """
        Estimates closing transaction costs (expected exit commission and spread drag).
        """
        vol = float(position.volume)
        accrued_comm = abs(float(getattr(position, "commission", 0.0) or 0.0))
        exit_comm = accrued_comm if accrued_comm > 0.01 else round(3.50 * vol, 2)

        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0
        spread_pts = float(getattr(symbol_info, "spread", 10.0))
        half_spread_usd = 0.5 * (spread_pts * point / tick_size) * tick_value * vol

        return round(exit_comm + half_spread_usd, 2)

    def calculate_estimated_realized_net_profit(
        self,
        position: Position,
        symbol_info: SymbolInfo
    ) -> Tuple[float, float, float]:
        """
        Returns: (net_floating_profit, estimated_closing_costs, estimated_realized_profit)
        """
        net_floating = self.calculate_net_profit(position, symbol_info)
        closing_costs = self.estimate_closing_costs(position, symbol_info)
        net_realized_est = round(net_floating - closing_costs, 2)
        return net_floating, closing_costs, net_realized_est

    @staticmethod
    def calculate_net_profit(position: Position, symbol_info: SymbolInfo) -> float:
        """
        Computes net floating profit in account currency:
        net_profit = gross_profit + commission + swap.
        """
        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        price_diff = (
            (position.current_price - position.open_price)
            if is_buy
            else (position.open_price - position.current_price)
        )
        gross_profit = float(position.profit)
        if abs(gross_profit) < 1e-9 and abs(price_diff) > 1e-9:
            tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else (symbol_info.point or 0.00001)
            tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0
            gross_profit = (price_diff / tick_size) * tick_value * float(position.volume)

        commission = float(getattr(position, "commission", 0.0))
        swap = float(getattr(position, "swap", 0.0))
        return round(gross_profit + commission + swap, 2)

    @staticmethod
    def calculate_atr(candles: List[Candle], period: int = 14) -> float:
        """Calculates Average True Range from completed candles."""
        if not candles:
            return 0.0
        completed = [c for c in candles if getattr(c, "complete", True)]
        if len(completed) < 2:
            completed = list(candles)
        if len(completed) < 2:
            return completed[-1].range if completed else 0.0
        trs: List[float] = []
        window = completed[-(period + 1):]
        for i in range(1, len(window)):
            c = window[i]
            p = window[i - 1]
            tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _assess_momentum_and_structure(
        position: Position,
        recent_candles: List[Candle],
        net_profit: float,
    ) -> Tuple[bool, bool, bool, str]:
        """
        Evaluates recent completed candles to determine:
        (is_strong_momentum, is_weakening_momentum, is_structural_reversal, details)
        """
        if not recent_candles or len(recent_candles) < 3:
            return True, False, False, "Insufficient bars for momentum check; defaulting to hold"

        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        completed = [c for c in recent_candles if getattr(c, "complete", True)]
        if len(completed) < 3:
            completed = list(recent_candles)

        last = completed[-1]
        prev = completed[-2]

        # 1. Structural Reversal Check (requires >= 5 bars)
        if len(completed) >= 5:
            prior_window = completed[-5:-1]
            prior_swing_low = min(c.low for c in prior_window)
            prior_swing_high = max(c.high for c in prior_window)
            last_range = max(last.range, 1e-9)
            body_ratio = last.body / last_range
            if is_buy and last.is_bearish and last.close < prior_swing_low and body_ratio >= 0.45:
                return (
                    False,
                    True,
                    True,
                    f"Bearish structural break below prior swing low {prior_swing_low:.5f} (close={last.close:.5f})",
                )
            if (not is_buy) and last.is_bullish and last.close > prior_swing_high and body_ratio >= 0.45:
                return (
                    False,
                    True,
                    True,
                    f"Bullish structural break above prior swing high {prior_swing_high:.5f} (close={last.close:.5f})",
                )

        # 2. Weakening Momentum / Exhaustion
        last_range = max(last.range, 1e-9)
        if is_buy:
            two_counter_bars = last.is_bearish and prev.is_bearish
            exhaustion_wick = (last.upper_wick / last_range >= 0.55) and (last.close <= last.open)
        else:
            two_counter_bars = last.is_bullish and prev.is_bullish
            exhaustion_wick = (last.lower_wick / last_range >= 0.55) and (last.close >= last.open)

        peak_net = float(getattr(position, "peak_net_profit", 0.0))
        profit_giveback = peak_net >= 6.5 and net_profit <= peak_net * 0.72

        if two_counter_bars or exhaustion_wick or profit_giveback:
            reason_parts = []
            if two_counter_bars:
                reason_parts.append("2 consecutive counter-direction closed bars")
            if exhaustion_wick:
                reason_parts.append("exhaustion rejection wick >= 55% of bar range")
            if profit_giveback:
                reason_parts.append(f"profit retraced from peak ${peak_net:.2f} to ${net_profit:.2f}")
            return False, True, False, ", ".join(reason_parts)

        return True, False, False, "Momentum & market structure remain aligned with position"

    def compute_cost_aware_break_even_sl(
        self,
        position: Position,
        symbol_info: SymbolInfo,
    ) -> Optional[float]:
        """
        Calculates break-even Stop-Loss price including spread, commission, swap,
        and configured break_even_buffer_pips so a break-even exit never results in a net loss.
        """
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        pip_size = point * 10
        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0
        usd_per_price_unit = (tick_value / tick_size) * max(float(position.volume), 0.01)

        buffer_dist = float(getattr(self.config, "break_even_buffer_pips", 2.0)) * pip_size
        costs_usd = -(float(getattr(position, "commission", 0.0)) + float(getattr(position, "swap", 0.0)))
        cost_price_offset = (max(0.0, costs_usd) / usd_per_price_unit) if usd_per_price_unit > 1e-9 else 0.0
        spread_offset = float(getattr(symbol_info, "spread", 0.0)) * point * 0.5
        total_offset = max(buffer_dist, cost_price_offset + spread_offset + (0.5 * pip_size))

        min_stop_pts = max(int(getattr(symbol_info, "stops_level", 0)), int(getattr(symbol_info, "freeze_level", 0)), 2)
        min_stop_dist = min_stop_pts * point

        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        if is_buy:
            candidate_sl = symbol_info.round_price(position.open_price + total_offset)
            if candidate_sl > position.stop_loss and candidate_sl <= (position.current_price - min_stop_dist):
                return candidate_sl
            fallback_sl = symbol_info.round_price(position.open_price + buffer_dist)
            if fallback_sl > position.stop_loss and fallback_sl < position.current_price:
                return fallback_sl
        else:
            candidate_sl = symbol_info.round_price(position.open_price - total_offset)
            if (position.stop_loss <= 0 or candidate_sl < position.stop_loss) and candidate_sl >= (position.current_price + min_stop_dist):
                return candidate_sl
            fallback_sl = symbol_info.round_price(position.open_price - buffer_dist)
            if (position.stop_loss <= 0 or fallback_sl < position.stop_loss) and fallback_sl > position.current_price:
                return fallback_sl
        return None

    def compute_atr_trailing_sl(
        self,
        position: Position,
        symbol_info: SymbolInfo,
        recent_candles: List[Candle],
    ) -> Optional[float]:
        """
        Calculates ATR volatility-adaptive trailing stop that locks in profit as price moves favorably.
        """
        atr = self.calculate_atr(recent_candles, period=14)
        if atr <= 0:
            return None
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        mult = float(getattr(self.config, "trailing_stop_atr_multiplier", 1.2))
        trail_dist = max(atr * mult, max(int(getattr(symbol_info, "stops_level", 0)), 3) * point * 2.0)

        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        if is_buy:
            candidate_sl = symbol_info.round_price(position.current_price - trail_dist)
            if candidate_sl > position.open_price and candidate_sl > position.stop_loss and candidate_sl < position.current_price:
                return candidate_sl
        else:
            candidate_sl = symbol_info.round_price(position.current_price + trail_dist)
            if (
                candidate_sl < position.open_price
                and (position.stop_loss <= 0 or candidate_sl < position.stop_loss)
                and candidate_sl > position.current_price
            ):
                return candidate_sl
        return None

    def _compute_structural_trailing_sl(
        self,
        position: Position,
        symbol_info: SymbolInfo,
        recent_candles: List[Candle],
    ) -> Optional[float]:
        """
        Calculates trailing stop behind the most recently confirmed protected swing level.
        """
        if not recent_candles or len(recent_candles) < 4:
            return None
        completed = [c for c in recent_candles if getattr(c, "complete", True)]
        if len(completed) < 4:
            return None

        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        pip_size = point * 10
        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        window = completed[-4:-1]

        if is_buy:
            recent_low = min(c.low for c in window)
            candidate_sl = symbol_info.round_price(recent_low - (1.5 * pip_size))
            if candidate_sl > position.stop_loss and candidate_sl < position.current_price:
                return candidate_sl
        else:
            recent_high = max(c.high for c in window)
            candidate_sl = symbol_info.round_price(recent_high + (1.5 * pip_size))
            if (position.stop_loss <= 0 or candidate_sl < position.stop_loss) and candidate_sl > position.current_price:
                return candidate_sl
        return None

    def _compute_profit_lock_sl(
        self,
        position: Position,
        symbol_info: SymbolInfo,
        target_locked_net_usd: float,
        slippage_buffer_usd: float = 1.0,
    ) -> Optional[float]:
        """
        Calculates the exact Stop Loss price that locks `target_locked_net_usd` in net profit
        (after accrued commission, estimated closing commission, swap, and slippage buffer),
        while strictly respecting broker stops_level and freeze_level restrictions.
        """
        if position.volume <= 0:
            return None
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0
        usd_per_price_unit = (tick_value / tick_size) * float(position.volume)
        if usd_per_price_unit <= 1e-9:
            return None

        # Accrued commission (opening)
        accrued_comm = abs(float(getattr(position, "commission", 0.0) or 0.0))
        # Exit commission ($3.50/lot or symmetrical to opening if target >= 15)
        exit_comm = accrued_comm if (accrued_comm > 0.01 and target_locked_net_usd >= 15.0) else 0.0
        # Swap debit
        swap_val = float(getattr(position, "swap", 0.0) or 0.0)
        swap_debit = abs(swap_val) if swap_val < 0 else 0.0
        eff_buffer = slippage_buffer_usd if target_locked_net_usd >= 18.0 else 0.0

        total_costs_usd = accrued_comm + exit_comm + swap_debit + eff_buffer
        required_gross_usd = target_locked_net_usd + total_costs_usd
        price_offset = required_gross_usd / usd_per_price_unit

        min_stop_pts = max(int(getattr(symbol_info, "stops_level", 0)), int(getattr(symbol_info, "freeze_level", 0)), 2)
        min_stop_dist = min_stop_pts * point

        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        if is_buy:
            desired_sl = symbol_info.round_price(position.open_price + price_offset)
            max_allowed_sl = position.current_price - min_stop_dist
            if desired_sl <= max_allowed_sl:
                candidate_sl = desired_sl
            else:
                candidate_sl = symbol_info.round_price(max_allowed_sl)

            if candidate_sl > position.open_price and candidate_sl > position.stop_loss and candidate_sl < position.current_price:
                actual_locked_gross = (candidate_sl - position.open_price) * usd_per_price_unit
                actual_locked_net = actual_locked_gross - (accrued_comm + exit_comm + swap_debit)
                if actual_locked_net >= (target_locked_net_usd - 0.50):
                    return candidate_sl
        else:
            desired_sl = symbol_info.round_price(position.open_price - price_offset)
            min_allowed_sl = position.current_price + min_stop_dist
            if desired_sl >= min_allowed_sl:
                candidate_sl = desired_sl
            else:
                candidate_sl = symbol_info.round_price(min_allowed_sl)

            if (
                candidate_sl < position.open_price
                and (position.stop_loss <= 0 or candidate_sl < position.stop_loss)
                and candidate_sl > position.current_price
            ):
                actual_locked_gross = (position.open_price - candidate_sl) * usd_per_price_unit
                actual_locked_net = actual_locked_gross - (accrued_comm + exit_comm + swap_debit)
                if actual_locked_net >= (target_locked_net_usd - 0.50):
                    return candidate_sl
        return None

    # =========================================================================
    # DUAL-MODE EVALUATION ENGINE
    # =========================================================================

    def evaluate_position(
        self,
        position: Position,
        symbol_info: SymbolInfo,
        recent_candles: List[Candle],
        scalp_mode: bool = False,
    ) -> List[PositionAction]:
        """
        Evaluates active position under the Intelligent Dual-Mode architecture:
        - MODE A (QUICK_SCALP): Fast $20 net closure & slot recycling
        - MODE B (PROFIT_RUNNING): $20 minimum profit protection & progressive trend trailing ($35, $60+)
        - Preserves Rule R9 (mandatory stop loss, never loosen established stop loss)
        """
        actions: List[PositionAction] = []
        state = self._restore_state(position)
        is_buy = position.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        pip_size = point * 10
        is_scalp_pos = scalp_mode or str(getattr(position, "comment", "")).upper().startswith("SCALP")

        # Initial risk distance (R distance)
        r_dist = position.initial_sl_distance
        if r_dist <= 0:
            r_dist = abs(position.open_price - position.stop_loss)
        if r_dist <= 0:
            r_dist = 10 * pip_size

        # Current price move & R-multiple
        if is_buy:
            profit_dist = position.current_price - position.open_price
        else:
            profit_dist = position.open_price - position.current_price
        current_r = profit_dist / r_dist if r_dist > 0 else 0.0

        # Calculate exact monetary net profits
        net_profit, closing_costs, est_net_exit = self.calculate_estimated_realized_net_profit(position, symbol_info)
        position.estimated_closing_costs = closing_costs

        if net_profit > position.peak_net_profit:
            position.peak_net_profit = net_profit
            state["peak_net_profit"] = net_profit

        # 0A. Time-Stop Policy
        if getattr(self.config, "enable_time_stop", False):
            max_bars = int(getattr(self.config, "time_stop_max_bars", 32))
            if len(recent_candles) >= max_bars:
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=f"Time stop triggered after {len(recent_candles)} bars (limit: {max_bars})",
                )
                logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                actions.append(act)
                return actions

        # 0B. Session-End Flatten
        if getattr(self.config, "enable_session_end_flatten", False) and recent_candles:
            last_time = recent_candles[-1].time
            is_session_end = (last_time.hour >= 21)
            if is_session_end:
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=f"End-of-session flatten triggered at {last_time.strftime('%H:%M UTC')}",
                )
                logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                actions.append(act)
                return actions

        # Momentum & Structure assessment
        is_strong_mom, is_weak_mom, is_struct_rev, mom_details = self._assess_momentum_and_structure(
            position=position,
            recent_candles=recent_candles,
            net_profit=net_profit,
        )

        target_net_target = float(getattr(self.config, "target_net_profit_usd", 20.0))
        if is_scalp_pos:
            effective_scalp_target = float(getattr(self.config, "individual_profit_target_usd", target_net_target))
        else:
            effective_scalp_target = target_net_target
        enable_rev_exit = bool(getattr(self.config, "enable_structural_reversal_exit", True))
        dynamic_tp = bool(getattr(self.config, "dynamic_take_profit", True))

        # Check Mode: QUICK_SCALP vs PROFIT_RUNNING
        raw_mode = state.get("profit_mode", "QUICK_SCALP")
        profit_mode = raw_mode.value if hasattr(raw_mode, "value") else str(raw_mode)

        # =========================================================================
        # MODE A: QUICK SCALPING (INDIVIDUAL PROFIT REALIZATION)
        # =========================================================================
        if profit_mode == "QUICK_SCALP":
            # At verified net profit >= target (or est net exit >= target), initiate rapid full close
            if net_profit >= effective_scalp_target or (net_profit >= (effective_scalp_target - 0.20) and est_net_exit >= (effective_scalp_target - 0.50)):
                if state.get("management_state") == PositionManagementState.SCALP_CLOSE_PENDING.value or state.get("close_requested"):
                    return actions

                self.transition_state(position.ticket, PositionManagementState.SCALP_CLOSE_PENDING, f"Target ${effective_scalp_target:.2f} achieved")
                state["close_requested"] = True
                position.validity_state = "CLOSING"
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=(
                        f"[SCALPING][INFO] Individual profit target reached: Target ${effective_scalp_target:.2f} net profit achieved "
                        f"(QUICK_SCALP full closure: ${net_profit:.2f} net >= ${effective_scalp_target:.2f}, "
                        f"est realized ${est_net_exit:.2f}) on {position.symbol} #{position.ticket}"
                    ),
                )
                logger.info(f"[SCALPING][SUCCESS] Individual position closure triggered #{act.ticket} on {act.symbol}: {act.reason}")
                actions.append(act)
                self._persist_state(position, state)
                return actions

            # Early Exit: Confirmed structural reversal against open position while in positive profit
            if enable_rev_exit and is_struct_rev and (net_profit > 0.0 or (is_scalp_pos and current_r >= -0.35)):
                position.validity_state = "INVALIDATED"
                self.transition_state(position.ticket, PositionManagementState.EXIT_PENDING, f"Structural reversal: {mom_details}")
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=f"Structural reversal exit (${net_profit:.2f} net): {mom_details}",
                )
                logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                actions.append(act)
                self._persist_state(position, state)
                return actions

            # Dynamic Take-Profit in Scalping Mode on momentum stall in profit
            if is_scalp_pos and dynamic_tp and is_weak_mom and current_r >= 1.2 and net_profit > 0.0:
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=f"Dynamic Take-Profit triggered at +{current_r:.2f}R (${net_profit:.2f} net) on momentum stall ({mom_details})",
                )
                logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                actions.append(act)
                self._persist_state(position, state)
                return actions

        # =========================================================================
        # MODE B: PROFIT-RUNNING WITH $20 MINIMUM PROFIT PROTECTION
        # =========================================================================
        elif profit_mode == "PROFIT_RUNNING":
            # ADAPTIVE EXIT: Structural reversal while in profit takes top priority
            if enable_rev_exit and is_struct_rev and net_profit > 0.0:
                position.validity_state = "INVALIDATED"
                self.transition_state(position.ticket, PositionManagementState.EXIT_PENDING, f"Structural reversal: {mom_details}")
                act = PositionAction(
                    ticket=position.ticket,
                    symbol=position.symbol,
                    action_type="FULL_CLOSE",
                    reason=f"Adaptive Exit (PROFIT_RUNNING Structural Reversal banking ${net_profit:.2f} net): {mom_details}",
                )
                logger.info(f"[ADAPTIVE_EXIT] Triggered FULL_CLOSE #{act.ticket} on {act.symbol}: {act.reason}")
                actions.append(act)
                self._persist_state(position, state)
                return actions

            if net_profit >= target_net_target:
                # Mark reached 20 in state
                if not state.get("reached_20_timestamp"):
                    state["reached_20_timestamp"] = datetime.now(timezone.utc).isoformat()
                    self.performance_tracker.record_reach_20(profit_mode)
                    self.transition_state(position.ticket, PositionManagementState.PROFIT_20_REACHED, "Reached $20 net floating profit")

                # Check if $20 profit protection stop is already installed
                point = symbol_info.point if symbol_info.point > 0 else 0.00001
                tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
                tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0
                usd_per_unit = (tick_value / tick_size) * float(position.volume)

                is_protection_installed = bool(state.get("profit_protection_active", False)) or bool(getattr(position, "profit_protection_active", False))
                if not is_protection_installed and is_buy and position.stop_loss > position.open_price:
                    locked_gross = (position.stop_loss - position.open_price) * usd_per_unit
                    costs = abs(float(getattr(position, "commission", 0.0) or 0.0)) * 2 + abs(float(getattr(position, "swap", 0.0) or 0.0))
                    if (locked_gross - costs) >= 19.50:
                        is_protection_installed = True
                elif not is_protection_installed and not is_buy and 0 < position.stop_loss < position.open_price:
                    locked_gross = (position.open_price - position.stop_loss) * usd_per_unit
                    costs = abs(float(getattr(position, "commission", 0.0) or 0.0)) * 2 + abs(float(getattr(position, "swap", 0.0) or 0.0))
                    if (locked_gross - costs) >= 19.50:
                        is_protection_installed = True

                if not is_protection_installed:
                    # Activate $20 Minimum Profit Protection
                    lock_sl = self._compute_profit_lock_sl(position, symbol_info, target_locked_net_usd=target_net_target)
                    if lock_sl is not None:
                        self.transition_state(position.ticket, PositionManagementState.PROFIT_LOCK_PENDING, f"Installing $20 profit protection SL at {lock_sl}")
                        state["profit_lock_sl_price"] = lock_sl
                        state["locked_net_profit_usd"] = target_net_target
                        state["profit_lock_status"] = "PROFIT_20_LOCKED"
                        position.profit_lock_status = "PROFIT_20_LOCKED"
                        position.locked_net_profit_usd = target_net_target
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=lock_sl,
                                reason=f"PROFIT_RUNNING: $20.00 minimum profit protection activated (locking >= $20 net at SL {lock_sl})",
                                amendment=PlanAmendment(
                                    amendment_type="PROFIT_FLOOR_LOCK",
                                    old_sl=position.stop_loss,
                                    new_sl=lock_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"PROFIT_RUNNING: $20.00 profit protection at SL {lock_sl}",
                                ),
                            )
                        )
                        self._persist_state(position, state)
                        return actions
                else:
                    # Protection confirmed: position is in PROFIT_RUNNING mode!
                    if state.get("management_state") != PositionManagementState.PROFIT_RUNNING.value:
                        self.transition_state(position.ticket, PositionManagementState.PROFIT_RUNNING, "$20 protection confirmed, running position")
                    position.profit_protection_active = True

                    # 1. Progressive Profit Ratchets ($35, $60, $80+)
                    progressive_target = 0.0
                    if net_profit >= 80.0:
                        progressive_target = 65.0
                    elif net_profit >= 60.0:
                        progressive_target = 45.0
                    elif net_profit >= 35.0:
                        progressive_target = 25.0

                    higher_cand_sl = None
                    if progressive_target > state.get("highest_locked_profit", 0.0):
                        higher_cand_sl = self._compute_profit_lock_sl(position, symbol_info, target_locked_net_usd=progressive_target)

                    # 2. Structural Trailing SL
                    struct_cand_sl = self._compute_structural_trailing_sl(position, symbol_info, recent_candles)

                    # 3. ATR Volatility Trailing SL
                    atr_cand_sl = self.compute_atr_trailing_sl(position, symbol_info, recent_candles)

                    # Select best valid SL strictly improving upon current stop loss (R9.3)
                    candidate_stops = [s for s in (higher_cand_sl, struct_cand_sl, atr_cand_sl) if s is not None]
                    best_sl = None
                    if is_buy:
                        valid_stops = [s for s in candidate_stops if s > position.stop_loss and s < position.current_price]
                        if valid_stops:
                            best_sl = max(valid_stops)
                    else:
                        valid_stops = [s for s in candidate_stops if (position.stop_loss <= 0 or s < position.stop_loss) and s > position.current_price]
                        if valid_stops:
                            best_sl = min(valid_stops)

                    if best_sl is not None:
                        new_locked_usd = progressive_target if higher_cand_sl == best_sl else state.get("locked_net_profit_usd", 20.0)
                        state["highest_locked_profit"] = max(state.get("highest_locked_profit", 0.0), new_locked_usd)
                        state["locked_net_profit_usd"] = max(state.get("locked_net_profit_usd", 0.0), new_locked_usd)
                        position.locked_net_profit_usd = state["locked_net_profit_usd"]
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=best_sl,
                                reason=f"PROFIT_RUNNING progressive trail: ratcheted SL to {best_sl} (floating ${net_profit:.2f} net)",
                                amendment=PlanAmendment(
                                    amendment_type="TRAILING_STOP",
                                    old_sl=position.stop_loss,
                                    new_sl=best_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"PROFIT_RUNNING progressive trail to SL {best_sl}",
                                ),
                            )
                        )



        # =========================================================================
        # INTERMEDIATE PROFIT FLOOR & GRADUATED RATCHET ($5.00 to $19.99 net)
        # =========================================================================
        min_net_target = min(5.0, float(getattr(self.config, "min_net_profit_target_usd", 5.0)))
        floor_lock_usd = min(5.0, float(getattr(self.config, "profit_floor_lock_usd", 5.0)))
        enable_5usd = bool(getattr(self.config, "enable_profit_management_5usd", True))
        allow_extension = bool(getattr(self.config, "strong_momentum_profit_extension", True))
        ext_lock_ratio = float(getattr(self.config, "profit_extension_lock_ratio", 0.65))

        if net_profit < target_net_target:
            if net_profit >= 18.0:
                position.profit_lock_status = "TARGET_APPROACH"
                state["profit_lock_status"] = "TARGET_APPROACH"
                if is_weak_mom:
                    act = PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="FULL_CLOSE",
                        reason=f"Target approach exit: banked ${net_profit:.2f} net on momentum exhaustion ({mom_details})",
                    )
                    logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                    actions.append(act)
                    self._persist_state(position, state)
                    return actions
                else:
                    lock_sl = self._compute_profit_lock_sl(position, symbol_info, 15.0)
                    if lock_sl is not None:
                        position.profit_floor_locked = True
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=lock_sl,
                                reason=f"Target approach: locked ~$15.00 net floor at SL {lock_sl} (${net_profit:.2f} net)",
                                amendment=PlanAmendment(
                                    amendment_type="PROFIT_FLOOR_LOCK",
                                    old_sl=position.stop_loss,
                                    new_sl=lock_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"Target approach: locked ~$15.00 net floor at SL {lock_sl}",
                                ),
                            )
                        )
            elif net_profit >= 12.0:
                position.profit_lock_status = "RATCHET_LOCKED"
                state["profit_lock_status"] = "RATCHET_LOCKED"
                if is_weak_mom:
                    act = PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="FULL_CLOSE",
                        reason=f"Profit ratchet exit: banked ${net_profit:.2f} net on weakening momentum ({mom_details})",
                    )
                    logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                    actions.append(act)
                    self._persist_state(position, state)
                    return actions
                else:
                    target_lock_usd = 11.0 if net_profit >= 15.0 else 8.0
                    lock_sl = self._compute_profit_lock_sl(position, symbol_info, target_lock_usd)
                    if lock_sl is not None:
                        position.profit_floor_locked = True
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=lock_sl,
                                reason=f"Profit ratchet active (${net_profit:.2f} net): locked ~${target_lock_usd:.2f} net floor at SL {lock_sl}",
                                amendment=PlanAmendment(
                                    amendment_type="PROFIT_FLOOR_LOCK",
                                    old_sl=position.stop_loss,
                                    new_sl=lock_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"Ratchet: locked ~${target_lock_usd:.2f} net floor at SL {lock_sl}",
                                ),
                            )
                        )
            elif enable_5usd and net_profit >= min_net_target:
                position.profit_lock_status = "FLOOR_LOCKED"
                state["profit_lock_status"] = "FLOOR_LOCKED"
                if is_weak_mom or not allow_extension:
                    act = PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="FULL_CLOSE",
                        reason=(
                            f"Net profit target >= ${min_net_target:.2f} secured (${net_profit:.2f} net) "
                            f"on weakening momentum ({mom_details})"
                        ),
                    )
                    logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")
                    actions.append(act)
                    self._persist_state(position, state)
                    return actions
                elif is_strong_mom:
                    if net_profit >= 8.0:
                        target_lock_usd = max(floor_lock_usd, round(net_profit * ext_lock_ratio, 2))
                    else:
                        target_lock_usd = min(floor_lock_usd, round(net_profit * 0.85, 2))

                    lock_sl = self._compute_profit_lock_sl(position, symbol_info, target_lock_usd)
                    if lock_sl is not None:
                        position.profit_floor_locked = True
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=lock_sl,
                                reason=(
                                    f"Profit extension active (${net_profit:.2f} net, strong momentum toward $20): "
                                    f"locked ~${target_lock_usd:.2f} net profit floor at SL {lock_sl}"
                                ),
                                amendment=PlanAmendment(
                                    amendment_type="PROFIT_FLOOR_LOCK",
                                    old_sl=position.stop_loss,
                                    new_sl=lock_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"Locked ~${target_lock_usd:.2f} net profit floor at SL {lock_sl} (net=${net_profit:.2f})",
                                ),
                            )
                        )

        # =========================================================================
        # COMMON STOP MANAGEMENT (Break-even & Structural Trailing)
        # =========================================================================
        be_mode = getattr(self.config, "be_move_mode", "structure_only")

        # Mode A: Structure-Only trailing [VIDEO 12]
        if not actions and be_mode == "structure_only" and len(recent_candles) >= 5:
            completed = [c for c in recent_candles if getattr(c, "complete", True)]
            if len(completed) >= 5:
                window = completed[-5:-1]
                if is_buy:
                    struct_swing_low = min(c.low for c in window)
                    cand_sl = symbol_info.round_price(struct_swing_low - (2 * pip_size))
                    if struct_swing_low > position.open_price and cand_sl > position.stop_loss and cand_sl < position.current_price:
                        state["break_even_activated"] = True
                        position.break_even_activated = True
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=cand_sl,
                                reason=f"Break-even (Structural SL Trail): New protected low {struct_swing_low:.5f} formed above entry [VIDEO 12]",
                                amendment=PlanAmendment(
                                    amendment_type="BREAK_EVEN",
                                    old_sl=position.stop_loss,
                                    new_sl=cand_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"Structural SL Trail: New protected low {struct_swing_low:.5f} [VIDEO 12]",
                                ),
                            )
                        )
                else:
                    struct_swing_high = max(c.high for c in window)
                    cand_sl = symbol_info.round_price(struct_swing_high + (2 * pip_size))
                    if struct_swing_high < position.open_price and (position.stop_loss <= 0 or cand_sl < position.stop_loss) and cand_sl > position.current_price:
                        state["break_even_activated"] = True
                        position.break_even_activated = True
                        actions.append(
                            PositionAction(
                                ticket=position.ticket,
                                symbol=position.symbol,
                                action_type="MODIFY_SL",
                                new_sl=cand_sl,
                                reason=f"Break-even (Structural SL Trail): New protected high {struct_swing_high:.5f} formed below entry [VIDEO 12]",
                                amendment=PlanAmendment(
                                    amendment_type="BREAK_EVEN",
                                    old_sl=position.stop_loss,
                                    new_sl=cand_sl,
                                    timestamp=datetime.now(timezone.utc),
                                    reason=f"Structural SL Trail: New protected high {struct_swing_high:.5f} [VIDEO 12]",
                                ),
                            )
                        )

        # Mode B: Optional fixed-R break-even
        elif not actions and getattr(self.config, "enable_break_even", False) and be_mode == "fixed_r" and not position.break_even_activated:
            be_threshold_r = (
                float(getattr(self.config, "scalp_break_even_at_r", 0.5))
                if is_scalp_pos
                else float(getattr(self.config, "break_even_at_r", 1.0))
            )
            if current_r >= be_threshold_r:
                if is_scalp_pos:
                    new_sl = self.compute_cost_aware_break_even_sl(position, symbol_info)
                else:
                    buffer_dist = self.config.break_even_buffer_pips * pip_size
                    if is_buy:
                        cand_sl = symbol_info.round_price(position.open_price + buffer_dist)
                        new_sl = cand_sl if cand_sl > position.stop_loss else None
                    else:
                        cand_sl = symbol_info.round_price(position.open_price - buffer_dist)
                        new_sl = cand_sl if cand_sl < position.stop_loss else None

                if new_sl is not None:
                    state["break_even_activated"] = True
                    position.break_even_activated = True
                    actions.append(
                        PositionAction(
                            ticket=position.ticket,
                            symbol=position.symbol,
                            action_type="MODIFY_SL",
                            new_sl=new_sl,
                            reason=f"Fixed-R Break-even activated at +{current_r:.2f}R (SL -> {new_sl}) [ASSUMPTION]",
                            amendment=PlanAmendment(
                                amendment_type="BREAK_EVEN",
                                old_sl=position.stop_loss,
                                new_sl=new_sl,
                                timestamp=datetime.now(timezone.utc),
                                reason=f"Fixed-R Break-even activated at +{current_r:.2f}R [ASSUMPTION]",
                            ),
                        )
                    )

        # Partial Take-Profit at 1.0R with Break-Even
        if getattr(self.config, "enable_partial_at_1r", False) and not position.partial_taken and current_r >= 1.0:
            raw_partial_vol = position.volume * 0.5
            partial_vol = symbol_info.normalize_volume(raw_partial_vol)
            if partial_vol >= symbol_info.min_lot and partial_vol < position.volume:
                state["partial_taken"] = True
                position.partial_taken = True
                actions.append(
                    PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="PARTIAL_CLOSE",
                        close_volume=partial_vol,
                        reason=f"Partial TP at 1.0R triggered (+{current_r:.2f}R, close {partial_vol} lots)",
                        amendment=PlanAmendment(
                            amendment_type="PARTIAL_TP",
                            old_sl=position.stop_loss,
                            new_sl=position.stop_loss,
                            partial_volume=partial_vol,
                            timestamp=datetime.now(timezone.utc),
                            reason=f"Partial TP at 1.0R (+{current_r:.2f}R)",
                        ),
                    )
                )

        # Standard Partial Profit-Taking
        if self.config.enable_partial_tp and not position.partial_taken:
            partial_threshold_r = (
                float(getattr(self.config, "scalp_partial_tp_at_r", 1.0))
                if is_scalp_pos
                else float(self.config.partial_tp_at_r)
            )
            if current_r >= partial_threshold_r:
                raw_partial_vol = position.volume * self.config.partial_tp_ratio
                partial_vol = symbol_info.normalize_volume(raw_partial_vol)
                if partial_vol >= symbol_info.min_lot and partial_vol < position.volume:
                    state["partial_taken"] = True
                    position.partial_taken = True
                    actions.append(
                        PositionAction(
                            ticket=position.ticket,
                            symbol=position.symbol,
                            action_type="PARTIAL_CLOSE",
                            close_volume=partial_vol,
                            reason=f"Partial TP triggered at +{current_r:.2f}R (close {partial_vol} lots)",
                            amendment=PlanAmendment(
                                amendment_type="PARTIAL_TP",
                                old_sl=position.stop_loss,
                                new_sl=position.stop_loss,
                                partial_volume=partial_vol,
                                timestamp=datetime.now(timezone.utc),
                                reason=f"Partial TP triggered at +{current_r:.2f}R",
                            ),
                        )
                    )

        # Structural & ATR Trailing Stop
        if self.config.trailing_stop_enabled and current_r > 1.5 and len(recent_candles) >= 3:
            recent_c = recent_candles[-2]
            if is_buy and recent_c.low > position.stop_loss:
                new_trail_sl = symbol_info.round_price(recent_c.low - (2 * pip_size))
                if new_trail_sl > position.stop_loss and new_trail_sl < position.current_price:
                    actions.append(
                        PositionAction(
                            ticket=position.ticket,
                            symbol=position.symbol,
                            action_type="MODIFY_SL",
                            new_sl=new_trail_sl,
                            reason=f"Structural trailing stop advanced to {new_trail_sl}",
                            amendment=PlanAmendment(
                                amendment_type="TRAILING_STOP",
                                old_sl=position.stop_loss,
                                new_sl=new_trail_sl,
                                timestamp=datetime.now(timezone.utc),
                                reason=f"Structural trailing stop advanced to {new_trail_sl}",
                            ),
                        )
                    )
            elif not is_buy and recent_c.high < position.stop_loss:
                new_trail_sl = symbol_info.round_price(recent_c.high + (2 * pip_size))
                if new_trail_sl < position.stop_loss and new_trail_sl > position.current_price:
                    actions.append(
                        PositionAction(
                            ticket=position.ticket,
                            symbol=position.symbol,
                            action_type="MODIFY_SL",
                            new_sl=new_trail_sl,
                            reason=f"Structural trailing stop advanced to {new_trail_sl}",
                            amendment=PlanAmendment(
                                amendment_type="TRAILING_STOP",
                                old_sl=position.stop_loss,
                                new_sl=new_trail_sl,
                                timestamp=datetime.now(timezone.utc),
                                reason=f"Structural trailing stop advanced to {new_trail_sl}",
                            ),
                        )
                    )
        elif self.config.trailing_stop_enabled and is_scalp_pos and current_r >= 0.85 and len(recent_candles) >= 3:
            atr_sl = self.compute_atr_trailing_sl(position, symbol_info, recent_candles)
            if atr_sl is not None:
                actions.append(
                    PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="MODIFY_SL",
                        new_sl=atr_sl,
                        reason=f"ATR volatility-adaptive trailing stop advanced to {atr_sl} (+{current_r:.2f}R)",
                        amendment=PlanAmendment(
                            amendment_type="TRAILING_STOP",
                            old_sl=position.stop_loss,
                            new_sl=atr_sl,
                            timestamp=datetime.now(timezone.utc),
                            reason=f"ATR volatility-adaptive trailing stop advanced to {atr_sl}",
                        ),
                    )
                )

        # 4. Structure-Based Trailing Stop (trail beyond latest confirmed swing)
        if getattr(self.config, "enable_swing_trailing", False) and len(recent_candles) >= 7:
            k = 3
            n = len(recent_candles)
            if is_buy:
                for idx in range(n - 2, k - 1, -1):
                    c = recent_candles[idx]
                    if all(c.low <= recent_candles[j].low for j in range(idx - k, idx)) and all(
                        c.low <= recent_candles[j].low for j in range(idx + 1, min(n, idx + k + 1))
                    ):
                        trail_sl = symbol_info.round_price(c.low - (2 * pip_size))
                        if trail_sl > position.stop_loss and trail_sl < position.current_price:
                            actions.append(
                                PositionAction(
                                    ticket=position.ticket,
                                    symbol=position.symbol,
                                    action_type="MODIFY_SL",
                                    new_sl=trail_sl,
                                    reason=f"Structure-based swing trailing stop advanced to {trail_sl} (beyond swing low {c.low:.5f})",
                                    amendment=PlanAmendment(
                                        amendment_type="TRAILING_STOP",
                                        old_sl=position.stop_loss,
                                        new_sl=trail_sl,
                                        timestamp=datetime.now(timezone.utc),
                                        reason=f"Swing trailing SL advanced to {trail_sl}",
                                    ),
                                )
                            )
                        break
            else:
                for idx in range(n - 2, k - 1, -1):
                    c = recent_candles[idx]
                    if all(c.high >= recent_candles[j].high for j in range(idx - k, idx)) and all(
                        c.high >= recent_candles[j].high for j in range(idx + 1, min(n, idx + k + 1))
                    ):
                        trail_sl = symbol_info.round_price(c.high + (2 * pip_size))
                        if trail_sl < position.stop_loss and trail_sl > position.current_price:
                            actions.append(
                                PositionAction(
                                    ticket=position.ticket,
                                    symbol=position.symbol,
                                    action_type="MODIFY_SL",
                                    new_sl=trail_sl,
                                    reason=f"Structure-based swing trailing stop advanced to {trail_sl} (beyond swing high {c.high:.5f})",
                                    amendment=PlanAmendment(
                                        amendment_type="TRAILING_STOP",
                                        old_sl=position.stop_loss,
                                        new_sl=trail_sl,
                                        timestamp=datetime.now(timezone.utc),
                                        reason=f"Swing trailing SL advanced to {trail_sl}",
                                    ),
                                )
                            )
                        break

        # Log all generated position management actions at TRADE level
        for act in actions:
            logger.info(f"[TRADE] Position Action #{act.ticket} on {act.symbol}: {act.action_type} | {act.reason}")

        self._persist_state(position, state)
        return actions

    # ========================================================================
    # VIDEO-DERIVED TRADE MANAGEMENT HELPERS (STRICTLY TIGHTEN-ONLY R9.3)
    # ========================================================================

    @staticmethod
    def is_tighter_stop(direction: OrderType, current_sl: float, candidate_sl: float) -> bool:
        """Rule R9.3 guard: returns True ONLY if candidate_sl strictly tightens current_sl."""
        if candidate_sl <= 0.0:
            return False
        if current_sl <= 0.0:
            return True
        if direction == OrderType.BUY:
            return candidate_sl > current_sl
        return candidate_sl < current_sl

    def evaluate_video_runner_management(
        self,
        position: Position,
        current_price: float,
        first_target_price: float,
        partial_pct: float = 0.50,
        cost_buffer: float = 0.0,
        trailing_stop_candidate: Optional[float] = None,
        symbol_info: Optional[SymbolInfo] = None,
    ) -> List[PositionAction]:
        """
        Runner / 'let it ride' management [VIDEO: keepssy_fx-20261126-0001, 0013]:
        1. At first target (e.g. Asian low / PD mid), take partial (default 50%) and move SL to
           break-even + cost buffer (strictly tighten-only R9.3).
        2. After partial is taken, trail remainder toward next untapped pool using structural SL
           (strictly tighten-only R9.3; never widens or removes a stop).
        """
        actions: List[PositionAction] = []
        is_buy = position.order_type == OrderType.BUY
        hit_tp1 = (current_price >= first_target_price) if is_buy else (current_price <= first_target_price)

        if hit_tp1 and not position.partial_taken:
            raw_close = position.volume * max(0.0, min(1.0, partial_pct))
            close_vol = (
                symbol_info.normalize_volume_down(raw_close)
                if symbol_info
                else round(raw_close, 2)
            )
            if close_vol > 0 and close_vol < position.volume:
                actions.append(
                    PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="PARTIAL_CLOSE",
                        close_volume=close_vol,
                        reason=f"Runner TP1 reached ({first_target_price:.5f}); banking {partial_pct*100:.0f}% partial",
                    )
                )

            be_sl = (position.open_price + abs(cost_buffer)) if is_buy else (position.open_price - abs(cost_buffer))
            if symbol_info:
                be_sl = symbol_info.round_price(be_sl)
            be_valid_side = (be_sl < current_price) if is_buy else (be_sl > current_price)
            if be_valid_side and self.is_tighter_stop(position.order_type, position.stop_loss, be_sl):
                actions.append(
                    PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="MODIFY_SL",
                        new_sl=be_sl,
                        reason=f"Runner TP1 break-even + cost buffer locked at {be_sl:.5f} (R9.3 tighten-only)",
                    )
                )

        if position.partial_taken and trailing_stop_candidate is not None:
            cand = symbol_info.round_price(trailing_stop_candidate) if symbol_info else trailing_stop_candidate
            side_ok = (cand < current_price) if is_buy else (cand > current_price)
            if side_ok and self.is_tighter_stop(position.order_type, position.stop_loss, cand):
                actions.append(
                    PositionAction(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        action_type="MODIFY_SL",
                        new_sl=cand,
                        reason=f"Runner structural trail tightened to {cand:.5f} (R9.3)",
                    )
                )

        return actions

    @staticmethod
    def evaluate_invalidation_exit(
        position: Position,
        last_closed_candle: Candle,
        invalidation_price: Optional[float],
    ) -> Optional[PositionAction]:
        """
        Early invalidation exit: closes position if a closed candle closes back beyond
        the setup's invalidation price (e.g. IFVG closed through again or breaker reclaimed).
        """
        if invalidation_price is None or invalidation_price <= 0:
            return None
        is_buy = position.order_type == OrderType.BUY
        invalidated = (
            (is_buy and last_closed_candle.close < invalidation_price)
            or (not is_buy and last_closed_candle.close > invalidation_price)
        )
        if not invalidated:
            return None
        return PositionAction(
            ticket=position.ticket,
            symbol=position.symbol,
            action_type="FULL_CLOSE",
            reason=(
                f"Setup invalidation close: bar closed at {last_closed_candle.close:.5f} "
                f"beyond invalidation {invalidation_price:.5f}"
            ),
        )

    @staticmethod
    def should_cancel_window_expired_order(
        window_name: Optional[str],
        order_placed_dt: datetime,
        current_dt: datetime,
        session_engine: Any,
        cancel_on_window_end: bool = True,
        broker_utc_offset_sec: int = 0,
    ) -> bool:
        """Cancels unfilled S2 Silver Bullet / S3 NY Macro limit orders once their NY window closes."""
        if not cancel_on_window_end or not window_name:
            return False
        return bool(
            session_engine.is_window_expired(
                window_name=window_name,
                order_placed_dt=order_placed_dt,
                current_dt=current_dt,
                broker_utc_offset_sec=broker_utc_offset_sec,
            )
        )
