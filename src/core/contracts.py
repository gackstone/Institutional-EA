"""
Strongly-typed data contracts for the Multi-Timeframe Algorithmic Trading Bot.
Provides immutable and validated models for market data, signals, orders, and risk.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

# Institutional logging severity levels: DEBUG, INFO, SUCCESS (25), WARNING, ERROR, CRITICAL
SUCCESS_LEVEL = 25
if not hasattr(logging, "SUCCESS"):
    logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
    setattr(logging, "SUCCESS", SUCCESS_LEVEL)
    def _logger_success(self, message, *args, **kwargs):
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, message, args, **kwargs)
    logging.Logger.success = _logger_success


class Timeframe(str, Enum):
    W1 = "W1"
    D1 = "D1"
    H4 = "H4"
    H1 = "H1"
    M30 = "M30"
    M15 = "M15"
    M5 = "M5"
    M1 = "M1"

    @property
    def minutes(self) -> int:
        mapping = {
            Timeframe.W1: 10080,
            Timeframe.D1: 1440,
            Timeframe.H4: 240,
            Timeframe.H1: 60,
            Timeframe.M30: 30,
            Timeframe.M15: 15,
            Timeframe.M5: 5,
            Timeframe.M1: 1,
        }
        return mapping[self]


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class TrendBias(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    RANGING = "RANGING"
    WEAK_BEARISH = "WEAK_BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"
    TRANSITIONAL = "TRANSITIONAL"


class MarketStructureType(str, Enum):
    BOS = "BOS"          # Break of Structure (trend continuation)
    CHOCH = "CHOCH"      # Change of Character (early trend reversal)
    MSS = "MSS"          # Market Structure Shift (displacement + confirmation)
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class SessionType(str, Enum):
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    NEW_YORK_PM = "NEW_YORK_PM"
    BEST_WINDOW = "BEST_WINDOW"
    ROLLOVER_BLACKOUT = "ROLLOVER_BLACKOUT"
    WEEKEND = "WEEKEND"
    HANDOVER_COOLDOWN = "HANDOVER_COOLDOWN"
    OFF_HOURS = "OFF_HOURS"


@dataclass(frozen=True)
class ActiveSessionInfo:
    primary_session: SessionType
    active_sessions: Tuple[SessionType, ...]
    is_best_window: bool
    time_in_session_minutes: float
    time_to_close_minutes: float
    is_handover_cooldown: bool
    is_rollover_blackout: bool
    is_weekend: bool
    is_monday_open_skip: bool
    is_friday_cutoff: bool
    is_cash_open_blackout: bool
    active_profile: str
    broker_offset_verified: bool
    can_trade: bool
    rejection_reason: Optional[str] = None


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    SIMULATION = "SIMULATION"
    DEMO = "DEMO"
    REAL = "REAL"
    PROP = "PROP"
    RETAIL = "RETAIL"


class AccountProfile(str, Enum):
    DEMO = "DEMO"
    LIVE = "LIVE"
    PROP = "PROP"
    RETAIL = "RETAIL"


class AccountTier(str, Enum):
    BELOW_FLOOR = "BELOW_FLOOR"
    MICRO = "MICRO"
    MINI = "MINI"
    SMALL = "SMALL"
    STANDARD = "STANDARD"
    LARGE = "LARGE"


class AffordabilityStatus(str, Enum):
    TRADABLE = "TRADABLE"
    MARGINAL = "MARGINAL"
    BLOCKED = "BLOCKED"


class DrawdownType(str, Enum):
    STATIC = "STATIC"
    TRAILING = "TRAILING"
    DAILY_START_EQUITY = "DAILY_START_EQUITY"
    DAILY_START_BALANCE = "DAILY_START_BALANCE"


class ProfitManagementMode(str, Enum):
    QUICK_SCALP = "QUICK_SCALP"
    PROFIT_RUNNING = "PROFIT_RUNNING"

    @property
    def canonical_mode(self) -> str:
        return "SCALP" if self == ProfitManagementMode.QUICK_SCALP else "HOLD"


class ExecutionModePolicy(str, Enum):
    ADAPTIVE = "ADAPTIVE"
    HOLD_ONLY = "HOLD_ONLY"
    SCALP_ONLY = "SCALP_ONLY"


class SignalLifecycleState(str, Enum):
    DETECTED = "DETECTED"
    GENERATED = "GENERATED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    WAITING_FOR_EXECUTION = "WAITING_FOR_EXECUTION"
    RISK_SIZED = "RISK_SIZED"
    ORDER_PREPARED = "ORDER_PREPARED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    EXECUTED = "EXECUTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    PENDING_ORDER = "PENDING_ORDER"
    BROKER_REJECTED = "BROKER_REJECTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    INVALID_MARKET_PRICE = "INVALID_MARKET_PRICE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    APPROVED = "APPROVED"
    SCALP_SELECTED = "SCALP_SELECTED"
    HOLD_SELECTED = "HOLD_SELECTED"
    EXECUTING = "EXECUTING"
    EXECUTION_RETRY = "EXECUTION_RETRY"
    OPEN = "OPEN"
    MANAGING = "MANAGING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    RETRY_PENDING = "RETRY_PENDING"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class PositionManagementState(str, Enum):
    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN_UNPROTECTED = "OPEN_UNPROTECTED"
    PROTECTED = "PROTECTED"
    PROFIT_MONITORING = "PROFIT_MONITORING"
    PROFIT_20_REACHED = "PROFIT_20_REACHED"
    SCALP_CLOSE_PENDING = "SCALP_CLOSE_PENDING"
    PROFIT_LOCK_PENDING = "PROFIT_LOCK_PENDING"
    PROFIT_LOCK_CONFIRMED = "PROFIT_LOCK_CONFIRMED"
    PROFIT_RUNNING = "PROFIT_RUNNING"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED_CONFIRMED = "CLOSED_CONFIRMED"
    PNL_RECONCILED = "PNL_RECONCILED"
    SLOT_RELEASED = "SLOT_RELEASED"


class SetupType(str, Enum):
    WEEKLY_REVERSAL = "WEEKLY_REVERSAL"
    WEEKLY_CONTINUATION = "WEEKLY_CONTINUATION"
    DAILY_REVERSAL = "DAILY_REVERSAL"
    DAILY_CONTINUATION = "DAILY_CONTINUATION"
    M15_SMC_OTE = "M15_SMC_OTE"
    SESSION_SWEEP = "SESSION_SWEEP"
    PATTERN_CONFLUENCE = "PATTERN_CONFLUENCE"
    FAST_SCALP = "FAST_SCALP"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    TRENDLINE_LIQUIDITY = "TRENDLINE_LIQUIDITY"
    SMC_MODEL_1_SWEEP = "SMC_MODEL_1_SWEEP"
    SMC_MODEL_2_BOS_FVG = "SMC_MODEL_2_BOS_FVG"
    SMC_MODEL_3_OB_RETEST = "SMC_MODEL_3_OB_RETEST"
    SMC_MODEL_4_CHOCH = "SMC_MODEL_4_CHOCH"


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int = 0
    complete: bool = True
    session_name: Optional[str] = None

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['time'] = self.time.isoformat()
        return d


@dataclass
class SymbolInfo:
    symbol: str
    digits: int = 5
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0
    contract_size: float = 100000.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    margin_required: float = 0.0
    spread: float = 1.2
    ask: float = 0.0
    bid: float = 0.0
    stops_level: int = 0
    freeze_level: int = 0
    filling_mode: str = "FOK"
    last_tick_time: Optional[datetime] = None
    currency_base: str = "USD"
    currency_profit: str = "USD"
    currency_margin: str = "USD"

    def round_price(self, price: float) -> float:
        return round(price, self.digits)

    def normalize_volume(self, volume: float) -> float:
        step = self.lot_step
        rounded = round(volume / step) * step
        # Always clamp within min and max
        if rounded < self.min_lot:
            return 0.0
        return min(round(rounded, 2), self.max_lot)

    def normalize_volume_down(self, volume: float) -> float:
        """Strictly rounds DOWN to the nearest lot_step without inflating risk."""
        import math
        step = self.lot_step if self.lot_step > 0 else 0.01
        floored = math.floor((volume + 1e-9) / step) * step
        if floored < self.min_lot - 1e-9:
            return 0.0
        return min(round(floored, 2), self.max_lot)


@dataclass
class AccountInfo:
    account_number: int = 0
    balance: float = 10000.0
    equity: float = 10000.0
    margin: float = 0.0
    free_margin: float = 10000.0
    margin_level: float = 0.0
    credit: float = 0.0
    profit: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    trade_mode: str = "DEMO"  # DEMO, REAL, CONTEST
    profile: str = "DEMO"     # DEMO, LIVE, PROP
    trading_enabled: bool = False
    peak_equity: float = 0.0
    initial_balance: float = 0.0
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    remaining_daily_loss: float = 500.0
    remaining_drawdown: float = 1000.0
    profit_target_pct: float = 10.0
    trading_days: int = 0
    # Tier and Cent Account support
    tier: str = "STANDARD"
    is_cent_account: bool = False
    raw_currency: str = "USD"
    raw_balance: float = 10000.0
    raw_equity: float = 10000.0
    margin_mode: int = 0
    margin_mode_str: str = "HEDGING"
    last_sync_time: Optional[datetime] = None
    account_type: str = "STANDARD"
    denomination_factor: float = 1.0
    broker_server: str = ""
    company: str = ""

    def __post_init__(self):
        if self.margin_mode == 1 or self.margin_mode_str == "NETTING":
            self.margin_mode = 1
            self.margin_mode_str = "NETTING"
        else:
            self.margin_mode = 2
            self.margin_mode_str = "HEDGING"

        # Auto-detect CENT and MICRO accounts: USC, EUC, GBX, etc.
        cent_currencies = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}
        curr_upper = (self.currency or "").strip().upper()
        raw_curr_upper = (self.raw_currency or "").strip().upper()
        server_lower = (self.broker_server or "").strip().lower()
        comp_lower = (self.company or "").strip().lower()

        if curr_upper in cent_currencies or raw_curr_upper in cent_currencies or "cent" in server_lower or "cent" in comp_lower:
            self.is_cent_account = True
            self.denomination_factor = 100.0
            self.account_type = "DEMO_CENT" if (self.trade_mode == "DEMO" or "demo" in server_lower) else "CENT"
            self.raw_currency = self.currency
            self.raw_balance = self.balance
            self.raw_equity = self.equity
        elif "micro" in server_lower or "micro" in comp_lower or (curr_upper == "USD" and 0.0 < self.balance < 100.0):
            self.is_cent_account = False
            self.denomination_factor = 1.0
            self.account_type = "DEMO_MICRO" if (self.trade_mode == "DEMO" or "demo" in server_lower) else "MICRO"
            self.raw_currency = self.currency
            self.raw_balance = self.balance
            self.raw_equity = self.equity
        elif curr_upper in {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"} and "cent" not in server_lower:
            self.is_cent_account = False
            self.denomination_factor = 1.0
            self.account_type = "DEMO_STANDARD" if (self.trade_mode == "DEMO" or "demo" in server_lower) else "STANDARD"
            self.raw_currency = self.currency
            self.raw_balance = self.balance
            self.raw_equity = self.equity
        else:
            self.is_cent_account = False
            self.denomination_factor = 1.0
            self.account_type = "UNKNOWN"
            self.raw_currency = self.currency
            self.raw_balance = self.balance
            self.raw_equity = self.equity

        if self.profile == "DEMO" and not self.trading_enabled:
            self.trading_enabled = True
        if self.initial_balance <= 0.0:
            self.initial_balance = self.balance
        if self.peak_equity <= 0.0:
            self.peak_equity = max(self.balance, self.equity)

    @property
    def normalized_balance(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.balance / denom, 2)

    @property
    def normalized_equity(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.equity / denom, 2)

    @property
    def normalized_free_margin(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.free_margin / denom, 2)


@dataclass
class WeeklyDailyLevels:
    symbol: str
    # Weekly levels
    pwh: float
    pwl: float
    pwo: float
    pwc: float
    pwm: float
    cwo: float
    cwh: float
    cwl: float
    # Daily levels
    pdh: float
    pdl: float
    pdo: float
    pdc: float
    pdm: float
    cdo: float
    cdh: float
    cdl: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "PWH": self.pwh,
            "PWL": self.pwl,
            "PWO": self.pwo,
            "PWC": self.pwc,
            "PWM": self.pwm,
            "CWO": self.cwo,
            "CWH": self.cwh,
            "CWL": self.cwl,
            "PDH": self.pdh,
            "PDL": self.pdl,
            "PDO": self.pdo,
            "PDC": self.pdc,
            "PDM": self.pdm,
            "CDO": self.cdo,
            "CDH": self.cdh,
            "CDL": self.cdl,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class LiquidityZone:
    id: str
    symbol: str
    timeframe: Timeframe
    level_type: str  # BSL (Buy-Side Liquidity), SSL (Sell-Side Liquidity), EQH, EQL
    price: float
    high: float
    low: float
    formation_time: datetime
    swept: bool = False
    sweep_time: Optional[datetime] = None
    rejection_confirmed: bool = False


@dataclass
class FairValueGap:
    id: str
    symbol: str
    timeframe: Timeframe
    direction: OrderType  # BUY for bullish FVG, SELL for bearish FVG
    top: float
    bottom: float
    midpoint: float
    formation_time: datetime
    mitigated: bool = False
    mitigation_time: Optional[datetime] = None
    is_inverse: bool = False

    @property
    def size(self) -> float:
        return abs(self.top - self.bottom)


@dataclass
class OrderBlock:
    id: str
    symbol: str
    timeframe: Timeframe
    direction: OrderType  # BUY = Bullish OB (down-candle before up displacement), SELL = Bearish OB
    high: float
    low: float
    open_price: float
    close_price: float
    formation_time: datetime
    mitigated: bool = False
    is_breaker: bool = False
    strength_score: float = 1.0


@dataclass
class MarketStructureEvent:
    id: str
    symbol: str
    timeframe: Timeframe
    event_type: MarketStructureType
    direction: OrderType  # BUY for bullish break/shift, SELL for bearish
    price: float
    timestamp: datetime
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    confirmed_by_close: bool = True
    displacement_ratio: float = 1.0


@dataclass
class SignalCandidate:
    id: str
    symbol: str
    timeframe: Timeframe
    direction: OrderType
    setup_type: SetupType
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    score: float
    timestamp: datetime
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXPIRED, EXECUTED
    reasons: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    fvg: Optional[FairValueGap] = None
    ob: Optional[OrderBlock] = None
    related_level: Optional[str] = None  # e.g. "PDL_SWEEP", "PWH_BREAKOUT"
    trade_plan: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_name: Optional[str] = None
    profit_mode: ProfitManagementMode = ProfitManagementMode.QUICK_SCALP
    lifecycle_state: SignalLifecycleState = SignalLifecycleState.DETECTED
    execution_mode_selected: Optional[str] = None  # "SCALP" or "HOLD"


@dataclass
class TradeOrder:
    symbol: str
    order_type: OrderType
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    magic: int = 100101
    comment: str = "MT5_SMC_BOT"
    ticket: Optional[int] = None
    status: str = "CREATED"  # CREATED, SENT, FILLED, REJECTED, CANCELLED
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None


@dataclass
class Position:
    ticket: int
    symbol: str
    order_type: OrderType
    volume: float
    open_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    profit: float
    swap: float = 0.0
    commission: float = 0.0
    magic: int = 100101
    comment: str = ""
    identifier: int = 0
    open_time: Optional[datetime] = None
    initial_risk_amount: float = 0.0
    initial_sl_distance: float = 0.0
    break_even_activated: bool = False
    partial_taken: bool = False
    profit_floor_locked: bool = False
    peak_net_profit: float = 0.0
    estimated_closing_costs: float = 0.0
    target_profit: float = 20.0
    profit_lock_status: str = "NONE"  # "NONE", "BE_LOCKED", "FLOOR_LOCKED", "RATCHET_LOCKED", "TARGET_APPROACH"
    strategy_attribution: str = ""
    validity_state: str = "ACTIVE"   # "ACTIVE", "INVALIDATED", "CLOSING", "CLOSED"
    realized_net_profit: Optional[float] = None
    profit_mode: ProfitManagementMode = ProfitManagementMode.QUICK_SCALP
    management_state: PositionManagementState = PositionManagementState.PROTECTED
    profit_lock_sl_price: float = 0.0
    locked_net_profit_usd: float = 0.0
    highest_locked_profit: float = 0.0
    profit_protection_active: bool = False
    features_snapshot: Dict[str, Any] = field(default_factory=dict)
    # Cent account and broker tracking
    canonical_symbol: str = ""
    account_type: str = "STANDARD"
    broker_identity: str = ""
    denomination_factor: float = 1.0
    reserved_portfolio_risk: float = 0.0

    @property
    def actual_broker_symbol(self) -> str:
        return self.symbol

    @property
    def native_profit(self) -> float:
        return self.profit

    @property
    def normalized_profit(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.profit / denom, 2)

    @property
    def native_commission(self) -> float:
        return self.commission

    @property
    def normalized_commission(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.commission / denom, 2)

    @property
    def native_swap(self) -> float:
        return self.swap

    @property
    def normalized_swap(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.swap / denom, 2)

    @property
    def normalized_net_profit(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.net_profit / denom, 2)

    @property
    def direction(self) -> OrderType:
        return self.order_type

    @property
    def entry_price(self) -> float:
        return self.open_price

    @property
    def current_sl(self) -> float:
        return self.stop_loss

    @property
    def initial_sl(self) -> float:
        if self.initial_sl_distance > 0:
            if self.order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP):
                return self.open_price - self.initial_sl_distance
            else:
                return self.open_price + self.initial_sl_distance
        return self.stop_loss

    @property
    def entry_timestamp(self) -> Optional[datetime]:
        return self.open_time

    @property
    def accrued_commission(self) -> float:
        return self.commission

    @property
    def current_floating_net_profit(self) -> float:
        return self.net_profit

    @property
    def net_profit(self) -> float:
        """Net floating profit in account currency including commission and swap."""
        return round(float(self.profit) + float(self.commission) + float(self.swap), 2)

    @property
    def management_mode(self) -> str:
        """Canonical position management mode: 'SCALP' or 'HOLD'."""
        if self.profit_mode == ProfitManagementMode.PROFIT_RUNNING:
            return "HOLD"
        return "SCALP"
class DecisionOutcomeType(str, Enum):
    TRADE_SENT = "TRADE SENT"
    TRADE_SKIPPED = "TRADE SKIPPED"
    NO_SETUP = "NO SETUP"


@dataclass
class DecisionOutcome:
    symbol: str
    bar_time: datetime
    outcome_type: DecisionOutcomeType
    details: str
    reason_code: Optional[str] = None
    real_numbers: Dict[str, Any] = field(default_factory=dict)
    ticket: Optional[int] = None
    volume: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_dollars: Optional[float] = None
    risk_percent: Optional[float] = None
    direction: Optional[str] = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def format_line(self) -> str:
        if self.outcome_type == DecisionOutcomeType.TRADE_SENT:
            d_str = self.direction.value if hasattr(self.direction, "value") else str(self.direction)
            t_str = str(self.ticket) if self.ticket is not None else "0"
            vol = self.volume if self.volume is not None else 0.0
            ep = self.entry_price if self.entry_price is not None else 0.0
            sl = self.stop_loss if self.stop_loss is not None else 0.0
            tp = self.take_profit if self.take_profit is not None else 0.0
            rd = self.risk_dollars if self.risk_dollars is not None else 0.0
            rp = self.risk_percent if self.risk_percent is not None else 0.0
            return (
                f"TRADE SENT: {self.symbol}, {d_str}, {vol:.2f}, "
                f"{ep:.5f}, {sl:.5f}, {tp:.5f}, "
                f"${rd:.2f} ({rp:.2f}% of balance), ticket #{t_str}"
            )
        elif self.outcome_type == DecisionOutcomeType.TRADE_SKIPPED:
            code = self.reason_code or "SKIPPED"
            return f"TRADE SKIPPED: {code} | {self.details}"
        else:
            return f"NO SETUP: {self.details}"


@dataclass(frozen=True)
class PlanAmendment:
    amendment_type: str  # "BREAK_EVEN", "TRAILING_STOP", "PARTIAL_TP"
    old_sl: float
    new_sl: float
    timestamp: datetime
    reason: str
    old_tp: Optional[float] = None
    new_tp: Optional[float] = None
    partial_volume: Optional[float] = None


@dataclass(frozen=True)
class TradePlan:
    plan_id: str
    symbol: str
    direction: OrderType
    entry_price: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_percent: float
    reward_to_risk: float
    structure_state: str
    timestamp: datetime
    amendments: Tuple[PlanAmendment, ...] = field(default_factory=tuple)
    pattern_name: Optional[str] = None
    pattern_family: Optional[str] = None
    pattern_score: float = 0.0
    session_name: Optional[str] = None

    def with_amendment(self, amendment: PlanAmendment) -> TradePlan:
        """Returns a new immutable TradePlan instance containing the amendment."""
        return TradePlan(
            plan_id=self.plan_id,
            symbol=self.symbol,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss=amendment.new_sl if amendment.new_sl > 0 else self.stop_loss,
            take_profit=amendment.new_tp if (amendment.new_tp is not None and amendment.new_tp > 0) else self.take_profit,
            lots=self.lots if amendment.partial_volume is None else max(0.0, round(self.lots - amendment.partial_volume, 2)),
            risk_percent=self.risk_percent,
            reward_to_risk=self.reward_to_risk,
            structure_state=self.structure_state,
            timestamp=self.timestamp,
            amendments=self.amendments + (amendment,),
            pattern_name=self.pattern_name,
            pattern_family=self.pattern_family,
            pattern_score=self.pattern_score,
            session_name=self.session_name
        )

    def format_log(self) -> str:
        d_str = self.direction.value if hasattr(self.direction, "value") else str(self.direction)
        ts_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"[LOCKED_TRADE_PLAN] PlanID={self.plan_id} | Symbol={self.symbol} | "
            f"Direction={d_str} | Entry={self.entry_price:.5f} | SL={self.stop_loss:.5f} | "
            f"TP={self.take_profit:.5f} | Lots={self.lots:.2f} | Risk={self.risk_percent:.2f}% | "
            f"R:R=1:{self.reward_to_risk:.2f} | Structure={self.structure_state} | Timestamp={ts_str}"
        )

    def format_signal_text(self) -> str:
        d_str = self.direction.value if hasattr(self.direction, "value") else str(self.direction)
        return (
            f"📋 <b>LOCKED TRADE PLAN</b>\n"
            f"• <b>Plan ID:</b> <code>{self.plan_id}</code>\n"
            f"• <b>Symbol:</b> <code>{self.symbol}</code>\n"
            f"• <b>Direction:</b> <code>{d_str}</code>\n"
            f"• <b>Entry:</b> <code>{self.entry_price:.5f}</code>\n"
            f"• <b>Stop Loss:</b> <code>{self.stop_loss:.5f}</code>\n"
            f"• <b>Take Profit:</b> <code>{self.take_profit:.5f}</code>\n"
            f"• <b>Volume:</b> <code>{self.lots:.2f} lots</code>\n"
            f"• <b>Risk %:</b> <code>{self.risk_percent:.2f}%</code>\n"
            f"• <b>Reward/Risk:</b> <code>1:{self.reward_to_risk:.2f}</code>\n"
            f"• <b>Structure:</b> <code>{self.structure_state}</code>\n"
            f"• <b>Locked at:</b> <code>{self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>"
        )


class ExecutionFillingMode(str, Enum):
    FOK = "FOK"
    IOC = "IOC"
    RETURN = "RETURN"


@dataclass
class ExecutionLatencyRecord:
    client_order_id: str
    symbol: str
    direction: str
    bar_received_ns: int = 0
    analysis_done_ns: int = 0
    checklist_passed_ns: int = 0
    order_sent_ns: int = 0
    fill_confirmed_ns: int = 0
    requote_count: int = 0
    requested_price: float = 0.0
    fill_price: float = 0.0
    slippage_points: float = 0.0
    spread_at_entry_points: float = 0.0
    filling_mode: str = "FOK"
    status: str = "PENDING"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def analysis_ms(self) -> float:
        if self.bar_received_ns > 0 and self.analysis_done_ns >= self.bar_received_ns:
            return round((self.analysis_done_ns - self.bar_received_ns) / 1_000_000.0, 3)
        return 0.0

    @property
    def checklist_ms(self) -> float:
        if self.analysis_done_ns > 0 and self.checklist_passed_ns >= self.analysis_done_ns:
            return round((self.checklist_passed_ns - self.analysis_done_ns) / 1_000_000.0, 3)
        return 0.0

    @property
    def dispatch_ms(self) -> float:
        if self.order_sent_ns > 0 and self.fill_confirmed_ns >= self.order_sent_ns:
            return round((self.fill_confirmed_ns - self.order_sent_ns) / 1_000_000.0, 3)
        return 0.0

    @property
    def total_ms(self) -> float:
        if self.bar_received_ns > 0 and self.fill_confirmed_ns >= self.bar_received_ns:
            return round((self.fill_confirmed_ns - self.bar_received_ns) / 1_000_000.0, 3)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "analysis_ms": self.analysis_ms,
            "checklist_ms": self.checklist_ms,
            "dispatch_ms": self.dispatch_ms,
            "total_ms": self.total_ms,
            "requote_count": self.requote_count,
            "requested_price": self.requested_price,
            "fill_price": self.fill_price,
            "slippage_points": self.slippage_points,
            "spread_at_entry_points": self.spread_at_entry_points,
            "filling_mode": self.filling_mode,
            "status": self.status,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class DataHealthStatus:
    symbol: str
    broker_symbol: str
    timeframe: Timeframe
    requested_count: int = 0
    received_count: int = 0
    required_minimum: int = 20
    latest_completed_bar_time: Optional[datetime] = None
    forming_bar_time: Optional[datetime] = None
    freshness_seconds: float = 0.0
    missing_gaps_count: int = 0
    duplicate_bars_removed: int = 0
    invalid_bars_removed: int = 0
    connection_status: str = "CONNECTED"
    source: str = "NONE"
    last_sync_time: Optional[datetime] = None
    retry_count: int = 0
    is_stale: bool = False
    is_healthy: bool = False
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "timeframe": self.timeframe.value if hasattr(self.timeframe, "value") else str(self.timeframe),
            "requested_count": self.requested_count,
            "received_count": self.received_count,
            "required_minimum": self.required_minimum,
            "latest_completed_bar_time": self.latest_completed_bar_time.isoformat() if self.latest_completed_bar_time else None,
            "forming_bar_time": self.forming_bar_time.isoformat() if self.forming_bar_time else None,
            "freshness_seconds": round(self.freshness_seconds, 1),
            "missing_gaps_count": self.missing_gaps_count,
            "duplicate_bars_removed": self.duplicate_bars_removed,
            "invalid_bars_removed": self.invalid_bars_removed,
            "connection_status": self.connection_status,
            "source": self.source,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "retry_count": self.retry_count,
            "is_stale": self.is_stale,
            "is_healthy": self.is_healthy,
            "failure_reason": self.failure_reason,
        }


def calculate_risk_reward(
    entry: float,
    stop_loss: float,
    take_profit: float,
    order_type: Optional[OrderType] = None
) -> float:
    """
    Authoritative single Risk-to-Reward calculation utility.
    Validates non-zero prices, positive stop distances, and correct trade directionality.
    Returns mathematically exact rounded ratio: abs(TP - entry) / abs(entry - SL).
    """
    if entry <= 0.0 or stop_loss <= 0.0 or take_profit <= 0.0:
        return 0.0
    sl_dist = abs(entry - stop_loss)
    tp_dist = abs(take_profit - entry)
    if sl_dist <= 1e-7:
        return 0.0

    # Directional sanity check
    if order_type is not None:
        is_buy = order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        is_sell = order_type in (OrderType.SELL, OrderType.SELL_LIMIT, OrderType.SELL_STOP)
        if is_buy and (stop_loss >= entry or take_profit <= entry):
            return 0.0
        if is_sell and (stop_loss <= entry or take_profit >= entry):
            return 0.0

    return round(tp_dist / sl_dist, 4)


