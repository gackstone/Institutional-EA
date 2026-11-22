"""
Portfolio Risk and Circuit Breaker Engine.
Enforces aggregate portfolio safety constraints, tracking daily/weekly losses,
consecutive losses, correlated currency exposure, and maximum simultaneous positions.
Triggers institutional circuit breakers upon limit breach.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Optional, Set, Any

from src.core.contracts import Position, AccountInfo, SignalCandidate, OrderType, AccountProfile, DrawdownType
from src.core.config import RiskConfig, AccountProfileConfig, PropFirmRulesConfig, get_default_account_profiles


@dataclass
class RiskBreachEvent:
    event_type: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = "CRITICAL"


class PortfolioRiskEngine:
    def __init__(
        self,
        config: Optional[Any] = None,
        profile_config: Optional[AccountProfileConfig] = None
    ):
        if hasattr(config, 'risk'):
            self.config = config.risk
            self.app_config = config
            self.profile = profile_config or config.account_profiles.get(config.account_profile, get_default_account_profiles()["DEMO"])
        else:
            self.config = config or RiskConfig()
            self.app_config = None
            self.profile = profile_config or get_default_account_profiles()["DEMO"]

        self.circuit_breaker_active = False
        self.circuit_breaker_reason: Optional[str] = None
        self.buffer_halted = False
        self.hard_locked = False
        self.risk_events: List[RiskBreachEvent] = []

        # Tracking metrics
        self.current_day: date = datetime.now(timezone.utc).date()
        self.initial_balance: float = 0.0
        self.peak_equity: float = 0.0
        self.daily_starting_equity: float = 0.0
        self.daily_starting_balance: float = 0.0
        self.daily_realized_loss: float = 0.0
        self.weekly_starting_equity: float = 0.0
        self.weekly_realized_loss: float = 0.0
        self.consecutive_losses: int = 0
        self.session_trades_count: int = 0
        self.last_deal_profit: float = 0.0
        self.last_deal_volume: float = 0.0
        self.symbol_consecutive_losses: Dict[str, int] = {}
        self.symbol_cooldown_until: Dict[str, datetime] = {}
        self.trading_days_count: int = 0
        self.last_known_balance: float = 0.0

    @property
    def is_safety_buffer_active(self) -> bool:
        return self.buffer_halted

    def initialize_day(self, equity: float, balance: Optional[float] = None) -> None:
        """Called at start of day/session or first tick to calibrate baseline."""
        today = datetime.now(timezone.utc).date()
        if today != self.current_day or self.daily_starting_equity <= 0:
            self.current_day = today
            self.daily_starting_equity = equity
            self.daily_starting_balance = balance if balance is not None and balance > 0 else equity
            self.daily_realized_loss = 0.0
            self.session_trades_count = 0
            if self.weekly_starting_equity <= 0 or today.weekday() == 0:  # Monday
                self.weekly_starting_equity = equity
                self.weekly_realized_loss = 0.0

    def update_equity(self, equity: Any, balance: Optional[float] = None) -> Tuple[float, float]:
        """
        Updates equity tracking, peak equity, and calculates real-time daily loss % and drawdown %.
        Accepts either (equity: float, balance: float) or (account: AccountInfo).
        Returns: (daily_loss_pct, total_drawdown_pct)
        """
        acc = None
        if hasattr(equity, 'equity') and hasattr(equity, 'balance'):
            acc = equity
            eq_val = float(acc.equity)
            bal_val = float(acc.balance)
            if getattr(acc, 'initial_balance', 0.0) > 0:
                self.initial_balance = acc.initial_balance
            if getattr(acc, 'peak_equity', 0.0) > 0 and self.peak_equity < acc.peak_equity:
                self.peak_equity = acc.peak_equity
        else:
            eq_val = float(equity)
            bal_val = float(balance) if balance is not None else eq_val

        if self.initial_balance <= 0:
            self.initial_balance = bal_val
        if self.daily_starting_equity <= 0:
            self.daily_starting_equity = eq_val
        if self.daily_starting_balance <= 0:
            self.daily_starting_balance = bal_val

        # Detect deposit or withdrawal adjustments without closed trade PnL
        if self.last_known_balance > 0 and abs(bal_val - self.last_known_balance) > 0.001:
            delta = bal_val - self.last_known_balance
            if abs(delta - self.last_deal_profit) > 0.01:
                self.initial_balance = max(bal_val, self.initial_balance + delta)
                self.daily_starting_balance = max(bal_val, self.daily_starting_balance + delta)
                self.daily_starting_equity = max(eq_val, self.daily_starting_equity + delta)
                if delta > 0:
                    self.peak_equity += delta
                else:
                    self.peak_equity = max(bal_val, self.peak_equity + delta)
        self.last_known_balance = bal_val
        if self.daily_starting_equity <= 0:
            self.daily_starting_equity = eq_val
        if self.daily_starting_balance <= 0:
            self.daily_starting_balance = bal_val
        if self.initial_balance <= 0:
            self.initial_balance = bal_val

        if eq_val > self.peak_equity:
            self.peak_equity = eq_val

        # 1. Daily Loss %
        day_ref = (
            self.daily_starting_balance
            if self.profile.drawdown_type == DrawdownType.DAILY_START_BALANCE
            else self.daily_starting_equity
        )
        daily_loss_money = max(0.0, day_ref - eq_val)
        daily_loss_pct = (daily_loss_money / day_ref * 100.0) if day_ref > 0 else 0.0

        # 2. Total Drawdown %
        if self.profile.drawdown_type == DrawdownType.STATIC:
            ref = self.initial_balance
            dd_money = max(0.0, ref - eq_val)
            dd_pct = (dd_money / ref * 100.0) if ref > 0 else 0.0
        elif self.profile.drawdown_type == DrawdownType.TRAILING:
            ref = self.peak_equity
            dd_money = max(0.0, ref - eq_val)
            dd_pct = (dd_money / ref * 100.0) if ref > 0 else 0.0
        else:
            dd_pct = daily_loss_pct

        # Check safety buffer and hard limit
        daily_limit = self.profile.max_daily_loss_percent
        dd_limit = self.profile.max_total_drawdown_percent
        buffer_ratio = self.profile.safety_buffer_percent / 100.0

        if daily_loss_pct >= daily_limit * 0.95 or dd_pct >= dd_limit * 0.95:
            self.hard_locked = True
            self._trigger_circuit_breaker(
                f"Hard drawdown limit breached! Daily: {daily_loss_pct:.2f}% (limit {daily_limit}%), DD: {dd_pct:.2f}% (limit {dd_limit}%)"
            )
        elif daily_loss_pct >= daily_limit * buffer_ratio or dd_pct >= dd_limit * buffer_ratio:
            self.buffer_halted = True
        else:
            self.buffer_halted = False

        if acc is not None:
            acc.daily_loss_pct = daily_loss_pct
            acc.drawdown_pct = dd_pct
            acc.peak_equity = self.peak_equity
            acc.initial_balance = self.initial_balance

        return daily_loss_pct, dd_pct

    def reset_state(self, current_balance: float) -> None:
        """
        Sets challenge baseline, day-start balance, and peak equity to current balance,
        and clears daily counters.
        """
        self.initial_balance = current_balance
        self.peak_equity = current_balance
        self.daily_starting_balance = current_balance
        self.daily_starting_equity = current_balance
        self.last_known_balance = current_balance
        self.daily_realized_loss = 0.0
        self.weekly_realized_loss = 0.0
        self.consecutive_losses = 0
        self.symbol_consecutive_losses.clear()
        self.symbol_cooldown_until.clear()
        self.session_trades_count = 0
        self.trading_days_count = 0
        self.last_deal_profit = 0.0
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = None
        self.buffer_halted = False
        self.hard_locked = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_balance": self.initial_balance,
            "peak_equity": self.peak_equity,
            "daily_starting_balance": self.daily_starting_balance,
            "daily_starting_equity": self.daily_starting_equity,
            "daily_realized_loss": self.daily_realized_loss,
            "consecutive_losses": self.consecutive_losses,
            "session_trades_count": self.session_trades_count,
            "trading_days_count": self.trading_days_count,
            "current_day": self.current_day.isoformat(),
            "last_known_balance": self.last_known_balance
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        if not data:
            return
        if "initial_balance" in data and float(data["initial_balance"]) > 0:
            self.initial_balance = float(data["initial_balance"])
        if "peak_equity" in data and float(data["peak_equity"]) > 0:
            self.peak_equity = float(data["peak_equity"])
        if "daily_starting_balance" in data and float(data["daily_starting_balance"]) > 0:
            self.daily_starting_balance = float(data["daily_starting_balance"])
        if "daily_starting_equity" in data and float(data["daily_starting_equity"]) > 0:
            self.daily_starting_equity = float(data["daily_starting_equity"])
        if "daily_realized_loss" in data:
            self.daily_realized_loss = float(data["daily_realized_loss"])
        if "consecutive_losses" in data:
            self.consecutive_losses = int(data["consecutive_losses"])
        if "session_trades_count" in data:
            self.session_trades_count = int(data["session_trades_count"])
        if "trading_days_count" in data:
            self.trading_days_count = int(data["trading_days_count"])
        if "last_known_balance" in data and float(data["last_known_balance"]) > 0:
            self.last_known_balance = float(data["last_known_balance"])
        if "current_day" in data:
            try:
                from datetime import date
                self.current_day = date.fromisoformat(data["current_day"])
            except Exception:
                pass

    def record_closed_trade(self, profit: float, volume: float = 0.01, symbol: Optional[str] = None) -> None:
        """Updates realized losses, win/loss streaks and per-symbol cooldowns."""
        self.last_deal_profit = profit
        self.last_deal_volume = volume
        sym_key = str(symbol).upper() if symbol else None
        if profit < 0:
            self.daily_realized_loss += abs(profit)
            self.weekly_realized_loss += abs(profit)
            self.consecutive_losses += 1

            if sym_key:
                self.symbol_consecutive_losses[sym_key] = self.symbol_consecutive_losses.get(sym_key, 0) + 1
                trigger = int(getattr(self.config, "consecutive_loss_trigger", 2))
                if self.symbol_consecutive_losses[sym_key] >= trigger:
                    cooldown_min = int(getattr(self.config, "consecutive_loss_cooldown_minutes", 15))
                    self.symbol_cooldown_until[sym_key] = (
                        datetime.now(timezone.utc) + timedelta(minutes=cooldown_min)
                    )

            if self.consecutive_losses >= self.config.max_consecutive_losses:
                self._trigger_circuit_breaker(
                    f"Max consecutive losses reached: {self.consecutive_losses} in a row."
                )

            if self.daily_starting_equity > 0:
                daily_pct = (self.daily_realized_loss / self.daily_starting_equity) * 100.0
                if daily_pct >= self.config.max_daily_loss_percent:
                    self._trigger_circuit_breaker(
                        f"Daily loss limit breached: {daily_pct:.2f}% >= {self.config.max_daily_loss_percent:.2f}%"
                    )

            if self.weekly_starting_equity > 0:
                weekly_pct = (self.weekly_realized_loss / self.weekly_starting_equity) * 100.0
                if weekly_pct >= self.config.max_weekly_loss_percent:
                    self._trigger_circuit_breaker(
                        f"Weekly loss limit breached: {weekly_pct:.2f}% >= {self.config.max_weekly_loss_percent:.2f}%"
                    )
        else:
            self.consecutive_losses = 0
            if sym_key:
                self.symbol_consecutive_losses.pop(sym_key, None)
                self.symbol_cooldown_until.pop(sym_key, None)

    def record_trade_result(self, profit: float, volume: float = 0.01, symbol: Optional[str] = None) -> None:
        """Backward-compatible alias used by the orchestrator when a trade closes."""
        self.record_closed_trade(profit=profit, volume=volume, symbol=symbol)

    @property
    def effective_risk_multiplier(self) -> float:
        """Temporary risk reduction while a consecutive-loss streak is active."""
        trigger = int(getattr(self.config, "consecutive_loss_trigger", 2))
        if self.consecutive_losses >= trigger:
            return float(getattr(self.config, "consecutive_loss_risk_reduction", 0.5))
        return 1.0

    @staticmethod
    def _correlation_group(symbol: str) -> Optional[str]:
        """Maps broker symbols to coarse correlation groups (USD / metals / crypto / FX)."""
        s = str(symbol).upper()
        root = s
        for sfx in (".M", ".STD", ".PRO", ".ECN", "_ECN", ".RAW", ".A", ".R", ".C", ".I", "M", "+", "#"):
            if root.endswith(sfx) and len(root) > len(sfx):
                root = root[:-len(sfx)]
                break
        if root.startswith("XAU") or root.startswith("GOLD") or "XAG" in root:
            return "METALS"
        if "BTC" in root or "ETH" in root or "XRP" in root:
            return "CRYPTO"
        if root.startswith("EUR") or root.startswith("GBP") or root.startswith("AUD") or root.startswith("NZD"):
            return "EUR_GBP_BLOC"
        if root in ("USDJPY", "USDCHF", "USDCAD"):
            return "USD_MAJORS"
        if any(idx in root for idx in ("NAS100", "US30", "US500", "SPX", "USTEC", "DJ30", "GER40", "DAX", "NDX")):
            return "INDICES"
        return None

    @staticmethod
    def _get_symbol_currency_bias(symbol: str, order_type: OrderType) -> Dict[str, int]:
        """
        Determines the directional currency delta (+1 for long, -1 for short)
        for a given symbol and order type.
        """
        s = str(symbol).upper()
        root = s
        for sfx in (".M", ".STD", ".PRO", ".ECN", "_ECN", ".RAW", ".A", ".R", ".C", ".I", "M", "+", "#"):
            if root.endswith(sfx) and len(root) > len(sfx):
                root = root[:-len(sfx)]
                break

        is_buy = order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        bias: Dict[str, int] = {}

        if root.startswith("XAU") or root.startswith("GOLD"):
            bias["METALS"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif root.startswith("XAG") or root.startswith("SILVER"):
            bias["METALS"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif any(idx in root for idx in ("NAS100", "US30", "US500", "SPX", "USTEC", "DJ30", "NDX")):
            bias["INDICES"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif any(idx in root for idx in ("GER40", "DAX")):
            bias["INDICES"] = 1 if is_buy else -1
            bias["EUR"] = -1 if is_buy else 1
        elif "BTC" in root or "ETH" in root:
            bias["CRYPTO"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif len(root) >= 6:
            base = root[:3]
            quote = root[3:6]
            bias[base] = 1 if is_buy else -1
            bias[quote] = -1 if is_buy else 1

        return bias

    def _auto_recover_consecutive_loss_breaker(self) -> None:
        """Consecutive-loss breakers pause trading temporarily instead of locking forever."""
        if not self.circuit_breaker_active:
            return
        reason = self.circuit_breaker_reason or ""
        if not reason.startswith("Max consecutive losses"):
            return
        cooldown_min = int(getattr(self.config, "consecutive_loss_cooldown_minutes", 15))
        # Find the most recent streak event; pause is measured from it.
        streak_time = None
        for ev in reversed(self.risk_events):
            if ev.event_type == "CIRCUIT_BREAKER_TRIGGERED" and ev.message.startswith("Max consecutive losses"):
                streak_time = ev.timestamp
                break
        if streak_time is None:
            return
        if datetime.now(timezone.utc) >= streak_time + timedelta(minutes=cooldown_min):
            self.circuit_breaker_active = False
            self.circuit_breaker_reason = None
            self.consecutive_losses = 0
            self.risk_events.append(
                RiskBreachEvent(
                    event_type="AUTO_RECOVERY",
                    message=f"Consecutive-loss pause elapsed after {cooldown_min} minutes; trading resumed.",
                    severity="INFO",
                )
            )

    def evaluate_new_order_permission(
        self,
        candidate: SignalCandidate,
        account: AccountInfo,
        active_positions: List[Position],
        proposed_monetary_risk: float,
        proposed_volume: float = 0.01
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates whether a new order is permitted against all portfolio-level constraints
        and institutional prop firm rules.
        Returns: (is_permitted, rejection_reason)
        """
        self.initialize_day(account.equity)
        self.update_equity(account)

        # Consecutive-loss pause is temporary; auto-recover once the cooldown elapses.
        self._auto_recover_consecutive_loss_breaker()

        # Check symbol-specific consecutive loss cooldown
        sym_key = str(candidate.symbol).upper()
        cooldown_until = self.symbol_cooldown_until.get(sym_key)
        now_utc = datetime.now(timezone.utc)
        if cooldown_until and now_utc < cooldown_until:
            rem_sec = int((cooldown_until - now_utc).total_seconds())
            consec = self.symbol_consecutive_losses.get(sym_key, 2)
            return False, f"Symbol {candidate.symbol} in consecutive-loss cooldown ({consec} losses) for {rem_sec}s."


        # 0. Check Live/Prop Trading Enabled Gating
        if self.profile.profile_name in [AccountProfile.LIVE, AccountProfile.PROP]:
            account_enabled = getattr(account, "trading_enabled", False)
            config_enabled = getattr(self.app_config, "trading_enabled", True) if self.app_config else True
            if not (account_enabled and config_enabled):
                return False, f"Trading is disabled for {self.profile.profile_name.value if hasattr(self.profile.profile_name, 'value') else self.profile.profile_name} profile. Enable via input or /enable."

        # 1. Check Circuit Breaker & Hard Lock
        if self.hard_locked or self.circuit_breaker_active:
            return False, f"Portfolio Circuit Breaker is ACTIVE: {self.circuit_breaker_reason}"

        # 1b. Check Safety Buffer (stop opening trades at buffer level)
        if self.buffer_halted:
            return False, f"Trading paused: Safety buffer reached ({self.profile.safety_buffer_percent:.0f}% of limit)."

        # 1c. Retail Protective Stop Loss
        if getattr(self.profile.rules, 'require_sl', True):
            if candidate.stop_loss <= 0.0:
                return False, 'Risk Rule: Stop Loss is strictly required on every trade.'

        # 1d. Retail Mode: Martingale / lot escalation restriction
        if getattr(self.profile.rules, 'no_martingale', False) and self.last_deal_profit < 0.0:
            if self.last_deal_volume > 0.0 and proposed_volume > (self.last_deal_volume * 1.5):
                return False, (
                    f'Martingale detected: lot escalation after a loss '
                    f'(proposed {proposed_volume:.2f} > 1.5x previous lot {self.last_deal_volume:.2f}).'
                )

        # 1e. Retail Mode: Grid / Averaging Down toggle
        if getattr(self.profile.rules, 'no_grid_averaging', False):
            for p in active_positions:
                if p.symbol == candidate.symbol and p.order_type == candidate.direction:
                    if p.profit < 0.0:
                        return False, f'Risk Rule: Grid/Averaging down prohibited while position #{p.ticket} is in drawdown (${p.profit:.2f}).'

        # 1f. Retail Mode: Hedging toggle (permitted in retail)
        if getattr(self.profile.rules, 'no_hedging', False):
            for p in active_positions:
                if p.symbol == candidate.symbol and p.order_type != candidate.direction:
                    return False, f'Risk Rule: Hedging prohibited (opposite position #{p.ticket} active on {p.symbol}).'

        # 1g. Retail Mode: Weekend Holding toggle
        if getattr(self.profile.rules, 'no_weekend_holding', False):
            now_utc = datetime.now(timezone.utc)
            fri_hr = getattr(self.profile.rules, 'weekend_close_hour_friday', 22)
            if now_utc.weekday() == 4 and now_utc.hour >= fri_hr:
                return False, f'Risk Rule: Weekend holding prohibited after {fri_hr:02d}:00 Friday.'

        # 1h. Hard Lot Cap
        if proposed_volume > self.profile.rules.max_lot_cap:
            return False, f"Volume {proposed_volume:.2f} exceeds profile hard lot cap {self.profile.rules.max_lot_cap:.2f}."

        # 2. Maximum Simultaneous Positions (Max 7 Absolute Ceiling)
        hard_max_pos = 7
        configured_max = min(hard_max_pos, getattr(self.config, 'max_simultaneous_positions', hard_max_pos))
        profile_max = min(hard_max_pos, getattr(self.profile, 'max_open_positions', hard_max_pos))
        max_pos = min(hard_max_pos, configured_max, profile_max)

        if len(active_positions) >= hard_max_pos:
            return False, f"Maximum simultaneous portfolio ceiling reached ({len(active_positions)}/7 positions open)."
        if len(active_positions) >= max_pos:
            return False, f"Maximum simultaneous positions reached ({len(active_positions)}/{max_pos})."

        # 2b. Margin Level and Free Margin Verification
        if getattr(account, "margin", 0.0) > 0 and getattr(account, "equity", 0.0) > 0:
            margin_level = (account.equity / account.margin) * 100.0
            if margin_level < 150.0:
                return False, f"Margin level critical ({margin_level:.1f}% < 150.0% min requirement)."

        # 2c. Aggregate Unrealized Floating Loss Guard
        unrealized_pnl = sum(float(getattr(p, "profit", 0.0) or 0.0) for p in active_positions)
        if self.daily_starting_equity > 0:
            max_daily_money = self.daily_starting_equity * (self.config.max_daily_loss_percent / 100.0)
            if unrealized_pnl < -(0.65 * max_daily_money):
                return False, (
                    f"Aggregate floating drawdown (${unrealized_pnl:.2f}) exceeds 65% of daily loss budget "
                    f"(${max_daily_money:.2f}). Pausing additional exposure."
                )

        # 2c-2. Maximum Aggregate Open Risk Guard
        max_agg_risk_pct = float(getattr(self.config, "max_aggregate_risk_percent", 8.0))
        active_monetary_risk = sum(float(getattr(p, "initial_risk_amount", 0.0) or 0.0) for p in active_positions)
        total_risk_proposed = active_monetary_risk + proposed_monetary_risk
        if getattr(account, "equity", 0.0) > 0:
            agg_risk_pct = (total_risk_proposed / account.equity) * 100.0
            if agg_risk_pct > max_agg_risk_pct:
                return False, f"Aggregate open risk ({agg_risk_pct:.2f}%) exceeds maximum limit ({max_agg_risk_pct:.2f}%)."

        # 2d. Directional Currency Concentration Guard (Max 3 directional bets on any single currency across different instruments)
        currency_exposure: Dict[str, int] = {}
        for p in active_positions:
            p_bias = self._get_symbol_currency_bias(p.symbol, p.order_type)
            for curr, delta in p_bias.items():
                currency_exposure[curr] = currency_exposure.get(curr, 0) + delta

        cand_root = candidate.symbol.split('.')[0].upper()
        other_sym_positions = [
            p for p in active_positions 
            if p.symbol.split('.')[0].upper() != cand_root
        ]

        cand_bias = self._get_symbol_currency_bias(candidate.symbol, candidate.direction)
        for curr, delta in cand_bias.items():
            new_exp = currency_exposure.get(curr, 0) + delta
            other_exp = 0
            for p in other_sym_positions:
                p_bias = self._get_symbol_currency_bias(p.symbol, p.order_type)
                other_exp += p_bias.get(curr, 0)

            # Limit cross-instrument concentration, allowing same-symbol scaling within portfolio limits
            if abs(new_exp) > 3 and abs(other_exp) >= 2:
                direction_str = "LONG" if new_exp > 0 else "SHORT"
                return False, (
                    f"Directional concentration limit exceeded for currency '{curr}': "
                    f"would result in {abs(new_exp)} simultaneous {direction_str} positions (max 3 allowed)."
                )

        # 3. Maximum Daily Loss Limit
        if self.daily_starting_equity > 0:
            daily_loss_pct = (self.daily_realized_loss / self.daily_starting_equity) * 100.0
            if daily_loss_pct >= self.config.max_daily_loss_percent:
                self._trigger_circuit_breaker(
                    f"Daily loss limit breached: {daily_loss_pct:.2f}% >= {self.config.max_daily_loss_percent:.2f}%"
                )
                return False, f"Daily loss limit breached ({daily_loss_pct:.2f}%)."

        # 4. Maximum Weekly Loss Limit
        if self.weekly_starting_equity > 0:
            weekly_loss_pct = (self.weekly_realized_loss / self.weekly_starting_equity) * 100.0
            if weekly_loss_pct >= self.config.max_weekly_loss_percent:
                self._trigger_circuit_breaker(
                    f"Weekly loss limit breached: {weekly_loss_pct:.2f}% >= {self.config.max_weekly_loss_percent:.2f}%"
                )
                return False, f"Weekly loss limit breached ({weekly_loss_pct:.2f}%)."

        # 5. Maximum Aggregate Open Risk
        current_open_risk = sum(p.initial_risk_amount for p in active_positions)
        total_open_risk_with_new = current_open_risk + proposed_monetary_risk
        max_allowed_open_risk = account.equity * (self.config.max_aggregate_open_risk_percent / 100.0)

        if total_open_risk_with_new > max_allowed_open_risk:
            return False, (
                f"Aggregate open risk would exceed limit: ${total_open_risk_with_new:.2f} > "
                f"${max_allowed_open_risk:.2f} ({self.config.max_aggregate_open_risk_percent}% of equity)."
            )

        # 6. Per-symbol and correlated exposure protection
        same_symbol_positions = [p for p in active_positions if p.symbol == candidate.symbol]
        max_per_symbol = int(getattr(self.config, 'max_positions_per_symbol', 0))
        if max_per_symbol <= 0:
            # 0 means "use the profile limit" rather than accidentally blocking at 1.
            max_per_symbol = max(1, int(getattr(self.profile, 'max_open_positions', 1)))
        if len(same_symbol_positions) >= max_per_symbol:
            return False, f"Maximum simultaneous positions for {candidate.symbol} reached ({len(same_symbol_positions)}/{max_per_symbol})."
        if len(same_symbol_positions) > 0:
            for p in same_symbol_positions:
                if p.order_type != candidate.direction:
                    return False, f"Conflicting open position exists on {candidate.symbol} in opposite direction."

        max_correlated = int(getattr(self.config, 'max_correlated_positions', 2))
        cand_group = self._correlation_group(candidate.symbol)
        if cand_group and max_correlated > 0:
            # Same-symbol stacking is governed by max_positions_per_symbol above.
            correlated = [
                p for p in active_positions
                if p.symbol != candidate.symbol and self._correlation_group(p.symbol) == cand_group
            ]
            if len(correlated) >= max_correlated:
                return False, (
                    f"Correlation exposure limit reached: {len(correlated)}/{max_correlated} "
                    f"positions already open in group '{cand_group}'."
                )

        # 7. Max trades per session
        if self.session_trades_count >= self.config.max_trades_per_session:
            return False, f"Session trade quota reached ({self.session_trades_count}/{self.config.max_trades_per_session})."

        return True, None

    def register_trade_executed(self) -> None:
        self.session_trades_count += 1

    def _trigger_circuit_breaker(self, reason: str) -> None:
        self.circuit_breaker_active = True
        self.circuit_breaker_reason = reason
        self.risk_events.append(
            RiskBreachEvent(event_type="CIRCUIT_BREAKER_TRIGGERED", message=reason)
        )

    def manual_reset_circuit_breaker(self, admin_token: str) -> bool:
        """Requires explicit admin authorization to resume after safety halt."""
        if admin_token == "AUTHORIZE_SYSTEM_RESET":
            self.circuit_breaker_active = False
            self.circuit_breaker_reason = None
            self.consecutive_losses = 0
            self.risk_events.append(
                RiskBreachEvent(event_type="MANUAL_RESET", message="Circuit breaker cleared by admin.", severity="INFO")
            )
            return True
        return False
