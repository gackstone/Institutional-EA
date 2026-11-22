"""
Centralized Configuration Loader and Validator for Dual-Market Scalper Engine.
Supports multi-symbol scheduling: Weekdays (GOLD) + Weekends (BTCUSD),
with independent symbol parameters and global account-level risk controls.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


@dataclass
class GeneralConfig:
    engine_name: str = "DualMarketScalperEngine"
    version: str = "2.0.0"
    magic_number: int = 777001
    comment_prefix: str = "DMS"
    DEMO_MODE: bool = True
    allow_real_trading: bool = False
    require_live_confirmation: bool = True
    LEGACY_FILTERS_ENABLED: bool = False
    EXECUTION_INTERVAL_MS: int = 250
    tick_timeout_seconds: float = 5.0
    candle_context_timeframe: str = "M1"


@dataclass
class SchedulerConfig:
    enabled: bool = True
    timezone: str = "UTC"
    weekday_symbol: str = "GOLD"
    weekend_symbol: str = "BTCUSD"
    weekday_days: List[str] = field(default_factory=lambda: [
        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"
    ])
    weekend_days: List[str] = field(default_factory=lambda: [
        "SATURDAY", "SUNDAY"
    ])
    manage_existing_positions: bool = True
    require_symbol_trading_availability: bool = True


@dataclass
class InstrumentScalperConfig:
    enabled: bool = True
    canonical: str = "XAUUSD"
    magic_number: int = 777001
    comment_prefix: str = "GS_GOLD"
    aliases: List[str] = field(default_factory=list)
    basket_size: int = 4
    max_basket_size: int = 10
    order_spacing_ms: int = 150
    burst_timeout_seconds: float = 3.0
    lot_step_balance: float = 50.0
    min_lot: float = 0.01
    max_lot: float = 0.50
    micro_account_min_lot: float = 0.01
    tp_usd_per_min_lot: float = 0.50
    basket_tp_usd: float = 2.00
    min_basket_tp_usd: float = 1.00
    max_hold_seconds: int = 180
    breakeven_urgency_seconds: int = 120
    sl_points: float = 300.0
    spread_max_points: float = 80.0
    fallback_lookback_ticks: int = 20
    fallback_m1_candles: int = 5
    fallback_momentum_period: int = 10


@dataclass
class RiskConfig:
    max_open_positions: int = 12
    max_total_lots: float = 1.00
    min_margin_level_pct: float = 300.0
    max_margin_usage_pct: float = 50.0
    max_dd_pct: float = 30.0
    pause_minutes: int = 60
    max_daily_loss_enabled: bool = False
    max_daily_loss_usd: float = 50.0
    daily_profit_target_enabled: bool = False
    daily_profit_target_usd: float = 100.0
    accounting_includes_floating: bool = True


@dataclass
class KillSwitchConfig:
    enabled: bool = True
    flag_file_path: str = "STOP.flag"
    cli_command_enabled: bool = True
    telegram_command_enabled: bool = True
    on_trigger_action: str = "CLOSE_ALL_AND_HALT"


@dataclass
class ExecutionConfig:
    order_type: str = "MARKET"
    preferred_filling_mode: str = "AUTO"
    slippage_points: int = 25
    max_retries: int = 3
    retry_delay_ms: int = 100
    rate_limit_per_second: int = 5


@dataclass
class LoggingConfig:
    log_level: str = "INFO"
    log_file: str = "logs/dual_market_scalper.log"
    log_basket_events: bool = True
    log_tick_frequency_sec: int = 10


# Backward-compatibility adapter dataclasses
@dataclass
class SymbolConfig:
    target_canonical: str = "XAUUSD"
    aliases: List[str] = field(default_factory=list)
    auto_detect_broker_symbol: bool = True
    fallback_symbol: str = "XAUUSD"


@dataclass
class BasketConfig:
    basket_size: int = 4
    max_basket_size: int = 10
    order_spacing_ms: int = 150
    burst_timeout_seconds: float = 3.0


@dataclass
class LotSizingConfig:
    formula: str = "floor(balance / LOT_STEP_BALANCE) * 0.01"
    lot_step_balance: float = 50.0
    micro_account_min_lot: float = 0.01
    min_lot_override: float = 0.01
    max_lot_override: float = 0.50
    clamp_to_broker_step: bool = True


@dataclass
class IndividualTPConfig:
    enabled: bool = True
    tp_usd_per_min_lot: float = 0.50
    account_for_costs: bool = True


@dataclass
class BasketTPConfig:
    enabled: bool = True
    basket_tp_usd: float = 2.00
    min_basket_tp_usd: float = 1.00
    account_for_costs: bool = True


@dataclass
class HoldingTimeConfig:
    max_hold_seconds: int = 180
    breakeven_urgency_seconds: int = 120
    allow_controlled_loss_exit: bool = True


@dataclass
class ProtectiveSLConfig:
    sl_points: float = 300.0
    enforce_immediate_placement: bool = True
    post_modify_retry_count: int = 3
    fail_closed_on_unprotected: bool = True


@dataclass
class SpreadProtectionConfig:
    spread_max_points: float = 80.0
    action: str = "SKIP_ENTRY"


@dataclass
class PositionLimitsConfig:
    max_open_positions: int = 12


@dataclass
class VolumeLimitsConfig:
    max_total_lots: float = 1.00


@dataclass
class MarginProtectionConfig:
    min_margin_level_pct: float = 300.0
    max_margin_usage_pct: float = 50.0
    check_projected_margin: bool = True


@dataclass
class EquityProtectionConfig:
    max_dd_pct: float = 30.0
    action_on_breach: str = "CLOSE_ALL_AND_PAUSE"
    pause_minutes: int = 60


@dataclass
class DailyLimitsConfig:
    max_daily_loss_enabled: bool = False
    max_daily_loss_usd: float = 50.0
    daily_profit_target_enabled: bool = False
    daily_profit_target_usd: float = 100.0
    accounting_includes_floating: bool = True


@dataclass
class LegacyFiltersConfig:
    LEGACY_FILTERS_ENABLED: bool = False
    bypass_session_filters: bool = True
    bypass_news_filters: bool = True
    bypass_htf_agreement: bool = True
    bypass_candle_close_confirmation: bool = True
    bypass_quality_gate: bool = True
    bypass_anti_chase: bool = True
    bypass_strict_rr_gate: bool = True
    bypass_cooldown_periods: bool = True
    bypass_single_position_limit: bool = True


@dataclass
class DirectionFallbackConfig:
    lookback_ticks: int = 20
    m1_candle_lookback: int = 5
    momentum_period: int = 10
    default_on_flat: str = "BUY"


@dataclass
class DirectionSelectionConfig:
    use_strategy_scoring: bool = True
    scoring_weight_smc: float = 0.35
    scoring_weight_momentum: float = 0.40
    scoring_weight_patterns: float = 0.25
    min_bias_threshold: float = 0.05
    fallback: DirectionFallbackConfig = field(default_factory=DirectionFallbackConfig)


@dataclass
class ExecutionLoopConfig:
    interval_ms: int = 250
    tick_timeout_seconds: float = 5.0
    candle_context_timeframe: str = "M1"


@dataclass
class SafetyModeConfig:
    DEMO_MODE: bool = True
    allow_real_trading: bool = False
    require_live_confirmation: bool = True


@dataclass
class ScalperConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    symbols: Dict[str, InstrumentScalperConfig] = field(default_factory=dict)
    risk: RiskConfig = field(default_factory=RiskConfig)
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Backward-compatibility section proxies
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    basket: BasketConfig = field(default_factory=BasketConfig)
    lot_sizing: LotSizingConfig = field(default_factory=LotSizingConfig)
    individual_tp: IndividualTPConfig = field(default_factory=IndividualTPConfig)
    basket_tp: BasketTPConfig = field(default_factory=BasketTPConfig)
    holding_time: HoldingTimeConfig = field(default_factory=HoldingTimeConfig)
    protective_sl: ProtectiveSLConfig = field(default_factory=ProtectiveSLConfig)
    position_limits: PositionLimitsConfig = field(default_factory=PositionLimitsConfig)
    volume_limits: VolumeLimitsConfig = field(default_factory=VolumeLimitsConfig)
    margin_protection: MarginProtectionConfig = field(default_factory=MarginProtectionConfig)
    equity_protection: EquityProtectionConfig = field(default_factory=EquityProtectionConfig)
    daily_limits: DailyLimitsConfig = field(default_factory=DailyLimitsConfig)
    spread_protection: SpreadProtectionConfig = field(default_factory=SpreadProtectionConfig)
    legacy_filters: LegacyFiltersConfig = field(default_factory=LegacyFiltersConfig)
    direction_selection: DirectionSelectionConfig = field(default_factory=DirectionSelectionConfig)
    execution_loop: ExecutionLoopConfig = field(default_factory=ExecutionLoopConfig)
    safety_mode: SafetyModeConfig = field(default_factory=SafetyModeConfig)

    @classmethod
    def load(cls, config_path: str | Path = "config/scalper.yaml") -> ScalperConfig:
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        def _sub(section_cls, key):
            data = raw.get(key, {})
            if not isinstance(data, dict):
                return section_cls()
            fields = section_cls.__dataclass_fields__
            filtered = {k: v for k, v in data.items() if k in fields}
            return section_cls(**filtered)

        gen_cfg = _sub(GeneralConfig, "general")
        sched_cfg = _sub(SchedulerConfig, "scheduler")
        risk_cfg = _sub(RiskConfig, "risk")
        kill_cfg = _sub(KillSwitchConfig, "kill_switch")
        exec_cfg = _sub(ExecutionConfig, "execution")
        log_cfg = _sub(LoggingConfig, "logging")

        # Parse symbol profiles
        raw_symbols = raw.get("symbols", {})
        symbols_map: Dict[str, InstrumentScalperConfig] = {}
        for sym_key, sym_val in raw_symbols.items():
            if isinstance(sym_val, dict):
                flds = InstrumentScalperConfig.__dataclass_fields__
                filtered = {k: v for k, v in sym_val.items() if k in flds}
                symbols_map[sym_key.upper()] = InstrumentScalperConfig(**filtered)

        # Ensure default GOLD and BTCUSD profiles if missing
        if "GOLD" not in symbols_map:
            symbols_map["GOLD"] = InstrumentScalperConfig(
                canonical="XAUUSD",
                magic_number=777001,
                comment_prefix="GS_GOLD",
                aliases=["XAUUSD", "XAUUSDm", "XAUUSD.m", "XAUUSD.a", "GOLD"],
                sl_points=300.0,
                spread_max_points=80.0,
            )
        if "BTCUSD" not in symbols_map:
            symbols_map["BTCUSD"] = InstrumentScalperConfig(
                canonical="BTCUSD",
                magic_number=777002,
                comment_prefix="BS_BTC",
                aliases=["BTCUSD", "BTCUSDm", "BTCUSD.m", "BTCUSD.a", "BTCUSD#"],
                sl_points=5000.0,
                spread_max_points=3000.0,
            )

        # Build primary config instance
        cfg = cls(
            general=gen_cfg,
            scheduler=sched_cfg,
            symbols=symbols_map,
            risk=risk_cfg,
            kill_switch=kill_cfg,
            execution=exec_cfg,
            logging=log_cfg,
        )

        # Wire backward-compatibility adapters from GOLD profile
        gold = symbols_map["GOLD"]
        cfg.symbol = SymbolConfig(
            target_canonical=gold.canonical,
            aliases=gold.aliases,
            fallback_symbol=gold.canonical,
        )
        cfg.basket = BasketConfig(
            basket_size=gold.basket_size,
            max_basket_size=gold.max_basket_size,
            order_spacing_ms=gold.order_spacing_ms,
            burst_timeout_seconds=gold.burst_timeout_seconds,
        )
        cfg.lot_sizing = LotSizingConfig(
            lot_step_balance=gold.lot_step_balance,
            min_lot_override=gold.min_lot,
            max_lot_override=gold.max_lot,
            micro_account_min_lot=gold.micro_account_min_lot,
        )
        cfg.individual_tp = IndividualTPConfig(
            enabled=True,
            tp_usd_per_min_lot=gold.tp_usd_per_min_lot,
        )
        cfg.basket_tp = BasketTPConfig(
            enabled=True,
            basket_tp_usd=gold.basket_tp_usd,
            min_basket_tp_usd=gold.min_basket_tp_usd,
        )
        cfg.holding_time = HoldingTimeConfig(
            max_hold_seconds=gold.max_hold_seconds,
            breakeven_urgency_seconds=gold.breakeven_urgency_seconds,
        )
        cfg.protective_sl = ProtectiveSLConfig(
            sl_points=gold.sl_points,
        )
        cfg.spread_protection = SpreadProtectionConfig(
            spread_max_points=gold.spread_max_points,
        )
        cfg.position_limits = PositionLimitsConfig(
            max_open_positions=risk_cfg.max_open_positions,
        )
        cfg.volume_limits = VolumeLimitsConfig(
            max_total_lots=risk_cfg.max_total_lots,
        )
        cfg.margin_protection = MarginProtectionConfig(
            min_margin_level_pct=risk_cfg.min_margin_level_pct,
            max_margin_usage_pct=risk_cfg.max_margin_usage_pct,
        )
        cfg.equity_protection = EquityProtectionConfig(
            max_dd_pct=risk_cfg.max_dd_pct,
            pause_minutes=risk_cfg.pause_minutes,
        )
        cfg.daily_limits = DailyLimitsConfig(
            max_daily_loss_enabled=risk_cfg.max_daily_loss_enabled,
            max_daily_loss_usd=risk_cfg.max_daily_loss_usd,
            daily_profit_target_enabled=risk_cfg.daily_profit_target_enabled,
            daily_profit_target_usd=risk_cfg.daily_profit_target_usd,
        )
        cfg.legacy_filters = LegacyFiltersConfig(
            LEGACY_FILTERS_ENABLED=gen_cfg.LEGACY_FILTERS_ENABLED,
        )
        cfg.execution_loop = ExecutionLoopConfig(
            interval_ms=gen_cfg.EXECUTION_INTERVAL_MS,
            tick_timeout_seconds=gen_cfg.tick_timeout_seconds,
            candle_context_timeframe=gen_cfg.candle_context_timeframe,
        )
        cfg.safety_mode = SafetyModeConfig(
            DEMO_MODE=gen_cfg.DEMO_MODE,
            allow_real_trading=gen_cfg.allow_real_trading,
            require_live_confirmation=gen_cfg.require_live_confirmation,
        )
        cfg.direction_selection = DirectionSelectionConfig(
            fallback=DirectionFallbackConfig(
                lookback_ticks=gold.fallback_lookback_ticks,
                m1_candle_lookback=gold.fallback_m1_candles,
                momentum_period=gold.fallback_momentum_period,
            )
        )

        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Enforces critical invariants and safety boundaries across all profiles."""
        if self.risk.max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1, got {self.risk.max_open_positions}")
        if self.risk.max_total_lots <= 0:
            raise ValueError(f"max_total_lots must be > 0, got {self.risk.max_total_lots}")
        if not (0 < self.risk.max_dd_pct < 100.0):
            raise ValueError(f"max_dd_pct must be between 0 and 100%, got {self.risk.max_dd_pct}")
        if self.risk.min_margin_level_pct < 100.0:
            raise ValueError(f"min_margin_level_pct must be >= 100%, got {self.risk.min_margin_level_pct}")

        for name, sym_cfg in self.symbols.items():
            if sym_cfg.basket_size < 1:
                raise ValueError(f"basket_size for {name} must be >= 1, got {sym_cfg.basket_size}")
            if sym_cfg.basket_size > sym_cfg.max_basket_size:
                raise ValueError(
                    f"basket_size ({sym_cfg.basket_size}) for {name} cannot exceed max_basket_size ({sym_cfg.max_basket_size})"
                )
            if sym_cfg.sl_points <= 0:
                raise ValueError(f"sl_points for {name} must be > 0, got {sym_cfg.sl_points}")
            if sym_cfg.spread_max_points <= 0:
                raise ValueError(f"spread_max_points for {name} must be > 0, got {sym_cfg.spread_max_points}")
            if sym_cfg.lot_step_balance <= 0:
                raise ValueError(f"lot_step_balance for {name} must be > 0, got {sym_cfg.lot_step_balance}")
