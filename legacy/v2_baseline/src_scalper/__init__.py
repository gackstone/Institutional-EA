"""
Dual-Market Scalper Engine package (GOLD + BTCUSD).
Provides high-frequency, multi-market calendar-routed execution on MetaTrader 5.
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
)
from src.scalper.symbol_resolver import (
    MultiSymbolResolver,
    GoldSymbolResolver,
    BtcSymbolResolver,
    ResolvedSymbolSpec,
)
from src.scalper.scheduler import (
    MarketScheduler,
    MarketScheduleDecision,
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
from src.scalper.risk import (
    AccountRiskManager,
    GoldRiskManager,
    RiskCheckVerdict,
)
from src.scalper.executor import (
    GoldOrderExecutor,
    OrderExecutionResult,
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
    "MultiSymbolResolver",
    "GoldSymbolResolver",
    "BtcSymbolResolver",
    "ResolvedSymbolSpec",
    "MarketScheduler",
    "MarketScheduleDecision",
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
    "AccountRiskManager",
    "GoldRiskManager",
    "RiskCheckVerdict",
    "GoldOrderExecutor",
    "OrderExecutionResult",
    "DualMarketScalperEngine",
    "GoldScalperEngine",
    "EngineCycleStats",
]
