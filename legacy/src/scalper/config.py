"""
Centralized Configuration Loader and Validator for GOLD Scalper Engine.
Parses config/scalper.yaml and enforces safe, validated defaults.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


@dataclass
class GeneralConfig:
    engine_name: str = "GoldScalperEngine"
    version: str = "1.0.0"
    magic_number: int = 777001
    comment_prefix: str = "GS_GOLD"


@dataclass
class SymbolConfig:
    target_canonical: str = "XAUUSD"
    aliases: List[str] = field(default_factory=lambda: [
        "XAUUSD", "XAUUSDm", "XAUUSD.m", "XAUUSD.a", "XAUUSD.pro", "XAUUSD.raw",
        "XAUUSD.std", "GOLD", "GOLD.m", "GOLDm", "XAU/USD"
    ])
    auto_detect_broker_symbol: bool = True
    fallback_symbol: str = "XAUUSD"


@dataclass
class ExecutionLoopConfig:
    interval_ms: int = 250
    tick_timeout_seconds: float = 5.0
    candle_context_timeframe: str = "M1"


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
class SpreadProtectionConfig:
    spread_max_points: float = 80.0
    action: str = "SKIP_ENTRY"


@dataclass
class ExecutionConfig:
    order_type: str = "MARKET"
    preferred_filling_mode: str = "AUTO"
    slippage_points: int = 25
    max_retries: int = 3
    retry_delay_ms: int = 100
    rate_limit_per_second: int = 5


@dataclass
class KillSwitchConfig:
    enabled: bool = True
    flag_file_path: str = "STOP.flag"
    cli_command_enabled: bool = True
    telegram_command_enabled: bool = True
    on_trigger_action: str = "CLOSE_ALL_AND_HALT"


@dataclass
class SafetyModeConfig:
    DEMO_MODE: bool = True
    allow_real_trading: bool = False
    require_live_confirmation: bool = True


@dataclass
class LoggingConfig:
    log_level: str = "INFO"
    log_file: str = "logs/gold_scalper.log"
    log_basket_events: bool = True
    log_tick_frequency_sec: int = 10


@dataclass
class ScalperConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    execution_loop: ExecutionLoopConfig = field(default_factory=ExecutionLoopConfig)
    direction_selection: DirectionSelectionConfig = field(default_factory=DirectionSelectionConfig)
    legacy_filters: LegacyFiltersConfig = field(default_factory=LegacyFiltersConfig)
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
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
    safety_mode: SafetyModeConfig = field(default_factory=SafetyModeConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

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

        cfg = cls(
            general=_sub(GeneralConfig, "general"),
            symbol=_sub(SymbolConfig, "symbol"),
            execution_loop=_sub(ExecutionLoopConfig, "execution_loop"),
            legacy_filters=_sub(LegacyFiltersConfig, "legacy_filters"),
            basket=_sub(BasketConfig, "basket"),
            lot_sizing=_sub(LotSizingConfig, "lot_sizing"),
            individual_tp=_sub(IndividualTPConfig, "individual_tp"),
            basket_tp=_sub(BasketTPConfig, "basket_tp"),
            holding_time=_sub(HoldingTimeConfig, "holding_time"),
            protective_sl=_sub(ProtectiveSLConfig, "protective_sl"),
            position_limits=_sub(PositionLimitsConfig, "position_limits"),
            volume_limits=_sub(VolumeLimitsConfig, "volume_limits"),
            margin_protection=_sub(MarginProtectionConfig, "margin_protection"),
            equity_protection=_sub(EquityProtectionConfig, "equity_protection"),
            daily_limits=_sub(DailyLimitsConfig, "daily_limits"),
            spread_protection=_sub(SpreadProtectionConfig, "spread_protection"),
            execution=_sub(ExecutionConfig, "execution"),
            kill_switch=_sub(KillSwitchConfig, "kill_switch"),
            safety_mode=_sub(SafetyModeConfig, "safety_mode"),
            logging=_sub(LoggingConfig, "logging"),
        )

        # Handle nested direction_selection.fallback
        dir_data = raw.get("direction_selection", {})
        if isinstance(dir_data, dict):
            fallback_data = dir_data.get("fallback", {})
            fb_fields = DirectionFallbackConfig.__dataclass_fields__
            fb_filtered = {k: v for k, v in fallback_data.items() if k in fb_fields}
            fallback_cfg = DirectionFallbackConfig(**fb_filtered)

            dir_fields = DirectionSelectionConfig.__dataclass_fields__
            dir_filtered = {k: v for k, v in dir_data.items() if k in dir_fields and k != "fallback"}
            cfg.direction_selection = DirectionSelectionConfig(fallback=fallback_cfg, **dir_filtered)

        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Enforces critical invariants and fail-safe boundaries."""
        if self.basket.basket_size < 1:
            raise ValueError(f"basket_size must be >= 1, got {self.basket.basket_size}")
        if self.basket.basket_size > self.basket.max_basket_size:
            raise ValueError(
                f"basket_size ({self.basket.basket_size}) cannot exceed max_basket_size ({self.basket.max_basket_size})"
            )
        if self.position_limits.max_open_positions < self.basket.basket_size:
            raise ValueError(
                f"max_open_positions ({self.position_limits.max_open_positions}) must be >= basket_size ({self.basket.basket_size})"
            )
        if self.lot_sizing.lot_step_balance <= 0:
            raise ValueError(f"lot_step_balance must be positive, got {self.lot_sizing.lot_step_balance}")
        if self.margin_protection.min_margin_level_pct < 100.0:
            raise ValueError(
                f"min_margin_level_pct must be >= 100%, got {self.margin_protection.min_margin_level_pct}"
            )
        if not (0 < self.equity_protection.max_dd_pct < 100.0):
            raise ValueError(
                f"max_dd_pct must be between 0 and 100%, got {self.equity_protection.max_dd_pct}"
            )
        if self.protective_sl.sl_points <= 0:
            raise ValueError(f"sl_points must be positive, got {self.protective_sl.sl_points}")
        if self.execution_loop.interval_ms < 50:
            raise ValueError(f"interval_ms must be >= 50ms, got {self.execution_loop.interval_ms}")
        if self.spread_protection.spread_max_points <= 0:
            raise ValueError(f"spread_max_points must be > 0, got {self.spread_protection.spread_max_points}")
