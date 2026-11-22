"""
High-Speed Dual-Market Scalper Engine Package (GOLD Weekdays + BTCUSD Weekends).
Exports all configuration, resolution, scheduling, caching, telemetry, strategy,
entry, sizing, basket, exit, reversal, risk, notification, and execution classes.
"""

from src.scalper.config import (
    ScalperConfig,
    GeneralConfig,
    SchedulerConfig,
    InstrumentScalperConfig,
    RiskConfig,
    KillSwitchConfig,
    ExecutionConfig,
    LoggingConfig,
    RISK_PROFILE_PCT_MAP,
)
from src.scalper.symbol_resolver import (
    MultiSymbolResolver,
    GoldSymbolResolver,
    BtcSymbolResolver,
    ResolvedSymbolSpec,
)
from src.scalper.scheduler import MarketScheduler, MarketScheduleDecision
from src.scalper.market_cache import (
    TickCache,
    CachedTick,
    TickValidationResult,
    IndicatorCache,
    IndicatorSnapshot,
)
from src.scalper.telemetry import (
    ExecutionLatencyTracker,
    OrderTelemetrySample,
    DuplicateOrderGuard,
)
from src.scalper.strategy_gold import (
    GoldScalpingStrategy,
    StrategySignalEvaluation,
    GOLD_ENTRY_TYPES,
)
from src.scalper.strategy_btc import BtcWeekendScalpingStrategy, BTC_ENTRY_TYPES
from src.scalper.entry_engine import (
    MultiPositionEntryEngine,
    EntryMode,
    PlannedOrderEntry,
    EntryPlanDecision,
)
from src.scalper.sizing import (
    SymbolLotSizingEngine,
    GoldLotSizingEngine,
    SizingCalculationResult,
)
from src.scalper.direction import (
    SymbolDirectionSelector,
    GoldDirectionSelector,
    DirectionScoreDetail,
)
from src.scalper.basket import (
    MultiBasketManager,
    GoldBasketManager,
    ScalperBasket,
    GoldBasket,
    BasketPosition,
    BasketState,
)
from src.scalper.exit_engine import RapidExitEngine, StopModificationAction
from src.scalper.reversal import (
    DirectionReversalEngine,
    ReversalRecord,
    ReversalEvaluation,
)
from src.scalper.risk import (
    AccountRiskManager,
    GoldRiskManager,
    RiskCheckVerdict,
    RiskTriggerEvent,
)
from src.scalper.executor import GoldOrderExecutor, OrderExecutionResult
from src.scalper.notifier import (
    ScalperNotificationManager,
    ScalperNotificationPayload,
    ALERT_EVENT_TYPES,
)
from src.scalper.engine import (
    DualMarketScalperEngine,
    GoldScalperEngine,
    EngineCycleStats,
)

__all__ = [
    "ScalperConfig",
    "GeneralConfig",
    "SchedulerConfig",
    "InstrumentScalperConfig",
    "RiskConfig",
    "KillSwitchConfig",
    "ExecutionConfig",
    "LoggingConfig",
    "RISK_PROFILE_PCT_MAP",
    "MultiSymbolResolver",
    "GoldSymbolResolver",
    "BtcSymbolResolver",
    "ResolvedSymbolSpec",
    "MarketScheduler",
    "MarketScheduleDecision",
    "TickCache",
    "CachedTick",
    "TickValidationResult",
    "IndicatorCache",
    "IndicatorSnapshot",
    "ExecutionLatencyTracker",
    "OrderTelemetrySample",
    "DuplicateOrderGuard",
    "GoldScalpingStrategy",
    "BtcWeekendScalpingStrategy",
    "StrategySignalEvaluation",
    "GOLD_ENTRY_TYPES",
    "BTC_ENTRY_TYPES",
    "MultiPositionEntryEngine",
    "EntryMode",
    "PlannedOrderEntry",
    "EntryPlanDecision",
    "SymbolLotSizingEngine",
    "GoldLotSizingEngine",
    "SizingCalculationResult",
    "SymbolDirectionSelector",
    "GoldDirectionSelector",
    "DirectionScoreDetail",
    "MultiBasketManager",
    "GoldBasketManager",
    "ScalperBasket",
    "GoldBasket",
    "BasketPosition",
    "BasketState",
    "RapidExitEngine",
    "StopModificationAction",
    "DirectionReversalEngine",
    "ReversalRecord",
    "ReversalEvaluation",
    "AccountRiskManager",
    "GoldRiskManager",
    "RiskCheckVerdict",
    "RiskTriggerEvent",
    "GoldOrderExecutor",
    "OrderExecutionResult",
    "ScalperNotificationManager",
    "ScalperNotificationPayload",
    "ALERT_EVENT_TYPES",
    "DualMarketScalperEngine",
    "GoldScalperEngine",
    "EngineCycleStats",
]
