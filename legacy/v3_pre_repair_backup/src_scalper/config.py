"""
Centralized Configuration Loader and Validator for High-Speed Dual-Market Scalper Engine (v3.0.0).
Supports Phase 15 sections (gold, btc, account_risk, execution) alongside backward-compatible
multi-symbol (symbols.GOLD, symbols.BTCUSD, risk, scheduler) and v1 single-symbol adapters.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


RISK_PROFILE_PCT_MAP: Dict[str, float] = {
    "CONSERVATIVE": 0.10,
    "STANDARD": 0.25,
    "AGGRESSIVE_DEMO": 0.50,
}


@dataclass
class GeneralConfig:
    engine_name: str = "DualMarketScalperEngine"
    version: str = "3.0.0"
    magic_number: int = 777001
    comment_prefix: str = "DMS"
    DEMO_MODE: bool = True
    allow_real_trading: bool = False
    require_live_confirmation: bool = True
    LEGACY_FILTERS_ENABLED: bool = False
    EXECUTION_INTERVAL_MS: int = 200
    tick_timeout_seconds: float = 5.0
    candle_context_timeframe: str = "M1"


@dataclass
class SchedulerConfig:
    enabled: bool = True
    timezone: str = "UTC"
    broker_utc_offset_hours: int = 0
    dst_auto_adjust: bool = True
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
    schedule: str = "weekdays"
    execution_mode: str = "DEMO"
    canonical: str = "XAUUSD"
    magic_number: int = 777001
    comment_prefix: str = "GS_GOLD"
    aliases: List[str] = field(default_factory=list)
    entry_mode: str = "controlled_multi_entry"  # single_entry, controlled_multi_entry, pyramid_entry, re_entry, reversal
    risk_profile: str = "STANDARD"              # CONSERVATIVE (0.10%), STANDARD (0.25%), AGGRESSIVE_DEMO (0.50%)
    max_positions: int = 4
    basket_size: int = 4
    max_basket_size: int = 10
    max_basket_risk_pct: float = 0.25
    max_spread: float = 80.0
    max_slippage: float = 25.0
    order_spacing_ms: int = 0
    burst_timeout_seconds: float = 2.0
    lot_step_balance: float = 50.0
    min_lot: float = 0.01
    max_lot: float = 0.50
    micro_account_min_lot: float = 0.01
    tp_usd_per_min_lot: float = 0.50
    basket_tp_usd: float = 2.00
    min_basket_tp_usd: float = 1.00
    max_hold_seconds: int = 180
    breakeven_urgency_seconds: int = 120
    breakeven_trigger_r: float = 1.0
    breakeven_buffer_points: float = 15.0
    trailing_stop_enabled: bool = True
    trailing_start_r: float = 1.2
    trailing_distance_points: float = 120.0
    trailing_step_points: float = 25.0
    profit_lock_trigger_usd: float = 1.50
    profit_lock_floor_usd: float = 0.90
    sl_points: float = 300.0
    tp_points: float = 450.0
    spread_max_points: float = 80.0
    cooldown_seconds: float = 2.0
    reversal_cooldown_seconds: float = 10.0
    min_entry_quality_score: float = 0.55
    commission_per_lot_usd: float = 7.0
    fallback_lookback_ticks: int = 20
    fallback_m1_candles: int = 5
    fallback_momentum_period: int = 10


@dataclass
class RiskConfig:
    daily_loss_enabled: bool = False
    max_daily_loss_enabled: bool = False
    max_daily_loss_pct: float = 5.0
    max_daily_loss_usd: float = 50.0
    max_drawdown_pct: float = 30.0
    max_dd_pct: float = 30.0
    max_open_risk_pct: float = 2.0
    max_margin_utilization_pct: float = 50.0
    max_margin_usage_pct: float = 50.0
    min_margin_level_pct: float = 300.0
    max_open_positions: int = 12
    max_total_lots: float = 1.00
    max_consecutive_losses: int = 4
    loss_streak_cooldown_seconds: int = 300
    pause_minutes: int = 60
    emergency_stop_enabled: bool = True
    broker_disconnect_timeout_sec: float = 15.0
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
    event_driven: bool = True
    duplicate_order_protection: bool = True
    broker_confirmation_required: bool = True
    tick_staleness_limit_ms: int = 5000
    max_execution_latency_ms: int = 1500
    reconnect_reconciliation: bool = True
    order_type: str = "MARKET"
    preferred_filling_mode: str = "AUTO"
    slippage_points: int = 25
    max_retries: int = 2
    retry_delay_ms: int = 20
    rate_limit_per_second: int = 10


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
    order_spacing_ms: int = 0
    burst_timeout_seconds: float = 2.0


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
    scope: str = "ACCOUNT_WIDE"


@dataclass
class VolumeLimitsConfig:
    max_total_lots: float = 1.00
    max_lot_per_order: float = 0.50


@dataclass
class MarginProtectionConfig:
    min_margin_level_pct: float = 300.0
    max_margin_usage_pct: float = 50.0
    verify_projected_margin: bool = True


@dataclass
class EquityProtectionConfig:
    max_dd_pct: float = 30.0
    pause_minutes: int = 60
    close_all_on_breach: bool = True


@dataclass
class DailyLimitsConfig:
    max_daily_loss_enabled: bool = False
    max_daily_loss_usd: float = 50.0
    daily_profit_target_enabled: bool = False
    daily_profit_target_usd: float = 100.0
    accounting_includes_floating: bool = True


@dataclass
class DirectionFallbackConfig:
    lookback_ticks: int = 20
    m1_candle_lookback: int = 5
    momentum_period: int = 10
    default_on_flat: str = "BUY"


@dataclass
class DirectionSelectionConfig:
    preserve_strategy_intelligence: bool = True
    scoring_weight_smc: float = 0.35
    scoring_weight_momentum: float = 0.40
    scoring_weight_patterns: float = 0.25
    min_bias_threshold: float = 0.10
    fallback: DirectionFallbackConfig = field(default_factory=DirectionFallbackConfig)


@dataclass
class LegacyFiltersConfig:
    LEGACY_FILTERS_ENABLED: bool = False


@dataclass
class ExecutionLoopConfig:
    interval_ms: int = 200
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

    # Backward-compatible single-symbol fields
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    basket: BasketConfig = field(default_factory=BasketConfig)
    lot_sizing: LotSizingConfig = field(default_factory=LotSizingConfig)
    individual_tp: IndividualTPConfig = field(default_factory=IndividualTPConfig)
    basket_tp: BasketTPConfig = field(default_factory=BasketTPConfig)
    holding_time: HoldingTimeConfig = field(default_factory=HoldingTimeConfig)
    protective_sl: ProtectiveSLConfig = field(default_factory=ProtectiveSLConfig)
    spread_protection: SpreadProtectionConfig = field(default_factory=SpreadProtectionConfig)
    position_limits: PositionLimitsConfig = field(default_factory=PositionLimitsConfig)
    volume_limits: VolumeLimitsConfig = field(default_factory=VolumeLimitsConfig)
    margin_protection: MarginProtectionConfig = field(default_factory=MarginProtectionConfig)
    equity_protection: EquityProtectionConfig = field(default_factory=EquityProtectionConfig)
    daily_limits: DailyLimitsConfig = field(default_factory=DailyLimitsConfig)
    direction_selection: DirectionSelectionConfig = field(default_factory=DirectionSelectionConfig)
    legacy_filters: LegacyFiltersConfig = field(default_factory=LegacyFiltersConfig)
    execution_loop: ExecutionLoopConfig = field(default_factory=ExecutionLoopConfig)
    safety_mode: SafetyModeConfig = field(default_factory=SafetyModeConfig)

    def __post_init__(self) -> None:
        if not self.symbols:
            self.symbols = {
                "GOLD": InstrumentScalperConfig(
                    canonical="XAUUSD",
                    schedule="weekdays",
                    magic_number=777001,
                    comment_prefix="GS_GOLD",
                    aliases=["XAUUSD", "XAUUSD.m", "XAUUSDm", "XAUUSD.a", "GOLD", "GOLD.m"],
                    sl_points=300.0,
                    tp_points=450.0,
                    spread_max_points=80.0,
                    max_spread=80.0,
                    max_slippage=25.0,
                ),
                "BTCUSD": InstrumentScalperConfig(
                    canonical="BTCUSD",
                    schedule="weekends",
                    magic_number=777002,
                    comment_prefix="GS_BTC",
                    aliases=["BTCUSD", "BTCUSD.m", "BTCUSDm", "BTCUSD.a", "BTCUSD#", "BTCUSD.", "BTCUSDpro", "BITCOIN"],
                    sl_points=5000.0,
                    tp_points=7500.0,
                    spread_max_points=3000.0,
                    max_spread=3000.0,
                    max_slippage=150.0,
                    breakeven_buffer_points=200.0,
                    trailing_distance_points=2000.0,
                    trailing_step_points=300.0,
                    commission_per_lot_usd=0.0,
                ),
            }

    @property
    def gold(self) -> InstrumentScalperConfig:
        return self.symbols["GOLD"]

    @property
    def btc(self) -> InstrumentScalperConfig:
        return self.symbols["BTCUSD"]

    @property
    def account_risk(self) -> RiskConfig:
        return self.risk

    def get_symbol_config(self, symbol_key: str) -> InstrumentScalperConfig:
        key = symbol_key.upper()
        if key in ("BTC", "BTCUSD", "BITCOIN"):
            key = "BTCUSD"
        elif key in ("GOLD", "XAUUSD", "XAU"):
            key = "GOLD"
        if key in self.symbols:
            return self.symbols[key]
        return self.symbols["GOLD"]

    @classmethod
    def _parse_instrument_cfg(cls, raw_sym: Dict[str, Any], default_canonical: str, default_magic: int) -> InstrumentScalperConfig:
        is_btc = "BTC" in default_canonical.upper()
        max_pos = int(raw_sym.get("basket_size", raw_sym.get("max_positions", 4)))
        max_sp = float(raw_sym.get("spread_max_points", raw_sym.get("max_spread", 3000.0 if is_btc else 80.0)))
        risk_prof = str(raw_sym.get("risk_profile", "STANDARD")).upper()
        default_risk_pct = RISK_PROFILE_PCT_MAP.get(risk_prof, 0.25)
        return InstrumentScalperConfig(
            enabled=bool(raw_sym.get("enabled", True)),
            schedule=str(raw_sym.get("schedule", "weekends" if is_btc else "weekdays")),
            execution_mode=str(raw_sym.get("execution_mode", "DEMO")),
            canonical=str(raw_sym.get("canonical", default_canonical)),
            magic_number=int(raw_sym.get("magic_number", default_magic)),
            comment_prefix=str(raw_sym.get("comment_prefix", f"GS_{'BTC' if is_btc else 'GOLD'}")),
            aliases=list(raw_sym.get("aliases", [default_canonical])),
            entry_mode=str(raw_sym.get("entry_mode", "controlled_multi_entry")),
            risk_profile=risk_prof,
            max_positions=int(raw_sym.get("max_positions", max_pos)),
            basket_size=max_pos,
            max_basket_size=int(raw_sym.get("max_basket_size", 10)),
            max_basket_risk_pct=float(raw_sym.get("max_basket_risk_pct", default_risk_pct)),
            max_spread=max_sp,
            max_slippage=float(raw_sym.get("max_slippage", 150.0 if is_btc else 25.0)),
            order_spacing_ms=int(raw_sym.get("order_spacing_ms", 0)),
            burst_timeout_seconds=float(raw_sym.get("burst_timeout_seconds", 2.0)),
            lot_step_balance=float(raw_sym.get("lot_step_balance", 50.0)),
            min_lot=float(raw_sym.get("min_lot", 0.01)),
            max_lot=float(raw_sym.get("max_lot", 0.50)),
            micro_account_min_lot=float(raw_sym.get("micro_account_min_lot", 0.01)),
            tp_usd_per_min_lot=float(raw_sym.get("tp_usd_per_min_lot", 0.50)),
            basket_tp_usd=float(raw_sym.get("basket_tp_usd", 2.00)),
            min_basket_tp_usd=float(raw_sym.get("min_basket_tp_usd", 1.00)),
            max_hold_seconds=int(raw_sym.get("max_hold_seconds", 180)),
            breakeven_urgency_seconds=int(raw_sym.get("breakeven_urgency_seconds", 120)),
            breakeven_trigger_r=float(raw_sym.get("breakeven_trigger_r", 1.0)),
            breakeven_buffer_points=float(raw_sym.get("breakeven_buffer_points", 200.0 if is_btc else 15.0)),
            trailing_stop_enabled=bool(raw_sym.get("trailing_stop_enabled", True)),
            trailing_start_r=float(raw_sym.get("trailing_start_r", 1.2)),
            trailing_distance_points=float(raw_sym.get("trailing_distance_points", 2000.0 if is_btc else 120.0)),
            trailing_step_points=float(raw_sym.get("trailing_step_points", 300.0 if is_btc else 25.0)),
            profit_lock_trigger_usd=float(raw_sym.get("profit_lock_trigger_usd", 1.50)),
            profit_lock_floor_usd=float(raw_sym.get("profit_lock_floor_usd", 0.90)),
            sl_points=float(raw_sym.get("sl_points", 5000.0 if is_btc else 300.0)),
            tp_points=float(raw_sym.get("tp_points", 7500.0 if is_btc else 450.0)),
            spread_max_points=max_sp,
            cooldown_seconds=float(raw_sym.get("cooldown_seconds", 3.0 if is_btc else 2.0)),
            reversal_cooldown_seconds=float(raw_sym.get("reversal_cooldown_seconds", 15.0 if is_btc else 10.0)),
            min_entry_quality_score=float(raw_sym.get("min_entry_quality_score", 0.58 if is_btc else 0.55)),
            commission_per_lot_usd=float(raw_sym.get("commission_per_lot_usd", 0.0 if is_btc else 7.0)),
            fallback_lookback_ticks=int(raw_sym.get("fallback_lookback_ticks", 20)),
            fallback_m1_candles=int(raw_sym.get("fallback_m1_candles", 5)),
            fallback_momentum_period=int(raw_sym.get("fallback_momentum_period", 10)),
        )

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "ScalperConfig":
        if path is None:
            root = Path(__file__).resolve().parent.parent.parent
            path = root / "config" / "scalper.yaml"
        else:
            path = Path(path)

        if not path.exists():
            cfg = cls()
            cfg.validate()
            return cfg

        with open(path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        gen_raw = raw.get("general", {})
        sched_raw = raw.get("scheduler", {})
        syms_raw = raw.get("symbols", {})
        gold_raw = raw.get("gold", {})
        btc_raw = raw.get("btc", {})
        acct_risk_raw = raw.get("account_risk", {})
        risk_raw = raw.get("risk", {})
        ks_raw = raw.get("kill_switch", {})
        exec_raw = raw.get("execution", {})
        log_raw = raw.get("logging", {})

        gen_cfg = GeneralConfig(
            engine_name=str(gen_raw.get("engine_name", "DualMarketScalperEngine")),
            version=str(gen_raw.get("version", "3.0.0")),
            magic_number=int(gen_raw.get("magic_number", 777001)),
            comment_prefix=str(gen_raw.get("comment_prefix", "DMS")),
            DEMO_MODE=bool(gen_raw.get("DEMO_MODE", True)),
            allow_real_trading=bool(gen_raw.get("allow_real_trading", False)),
            require_live_confirmation=bool(gen_raw.get("require_live_confirmation", True)),
            LEGACY_FILTERS_ENABLED=bool(gen_raw.get("LEGACY_FILTERS_ENABLED", False)),
            EXECUTION_INTERVAL_MS=int(gen_raw.get("EXECUTION_INTERVAL_MS", 200)),
            tick_timeout_seconds=float(gen_raw.get("tick_timeout_seconds", 5.0)),
            candle_context_timeframe=str(gen_raw.get("candle_context_timeframe", "M1")),
        )

        sched_cfg = SchedulerConfig(
            enabled=bool(sched_raw.get("enabled", True)),
            timezone=str(sched_raw.get("timezone", "UTC")),
            broker_utc_offset_hours=int(sched_raw.get("broker_utc_offset_hours", 0)),
            dst_auto_adjust=bool(sched_raw.get("dst_auto_adjust", True)),
            weekday_symbol=str(sched_raw.get("weekday_symbol", "GOLD")),
            weekend_symbol=str(sched_raw.get("weekend_symbol", "BTCUSD")),
            weekday_days=list(sched_raw.get("weekday_days", ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"])),
            weekend_days=list(sched_raw.get("weekend_days", ["SATURDAY", "SUNDAY"])),
            manage_existing_positions=bool(sched_raw.get("manage_existing_positions", True)),
            require_symbol_trading_availability=bool(sched_raw.get("require_symbol_trading_availability", True)),
        )

        symbols_dict: Dict[str, InstrumentScalperConfig] = {}
        merged_gold = {**syms_raw.get("GOLD", {}), **gold_raw}
        merged_btc = {**syms_raw.get("BTCUSD", {}), **btc_raw}
        if merged_gold:
            symbols_dict["GOLD"] = cls._parse_instrument_cfg(merged_gold, "XAUUSD", 777001)
        if merged_btc:
            symbols_dict["BTCUSD"] = cls._parse_instrument_cfg(merged_btc, "BTCUSD", 777002)

        merged_risk = {**acct_risk_raw, **risk_raw}
        max_dd = float(merged_risk.get("max_dd_pct", merged_risk.get("max_drawdown_pct", 30.0)))
        max_margin_u = float(merged_risk.get("max_margin_usage_pct", merged_risk.get("max_margin_utilization_pct", 50.0)))
        daily_en = bool(merged_risk.get("max_daily_loss_enabled", merged_risk.get("daily_loss_enabled", False)))

        risk_cfg = RiskConfig(
            daily_loss_enabled=daily_en,
            max_daily_loss_enabled=daily_en,
            max_daily_loss_pct=float(merged_risk.get("max_daily_loss_pct", 5.0)),
            max_daily_loss_usd=float(merged_risk.get("max_daily_loss_usd", 50.0)),
            max_drawdown_pct=max_dd,
            max_dd_pct=max_dd,
            max_open_risk_pct=float(merged_risk.get("max_open_risk_pct", 2.0)),
            max_margin_utilization_pct=max_margin_u,
            max_margin_usage_pct=max_margin_u,
            min_margin_level_pct=float(merged_risk.get("min_margin_level_pct", 300.0)),
            max_open_positions=int(merged_risk.get("max_open_positions", 12)),
            max_total_lots=float(merged_risk.get("max_total_lots", 1.00)),
            max_consecutive_losses=int(merged_risk.get("max_consecutive_losses", 4)),
            loss_streak_cooldown_seconds=int(merged_risk.get("loss_streak_cooldown_seconds", 300)),
            pause_minutes=int(merged_risk.get("pause_minutes", 60)),
            emergency_stop_enabled=bool(merged_risk.get("emergency_stop_enabled", True)),
            broker_disconnect_timeout_sec=float(merged_risk.get("broker_disconnect_timeout_sec", 15.0)),
            daily_profit_target_enabled=bool(merged_risk.get("daily_profit_target_enabled", False)),
            daily_profit_target_usd=float(merged_risk.get("daily_profit_target_usd", 100.0)),
            accounting_includes_floating=bool(merged_risk.get("accounting_includes_floating", True)),
        )

        ks_cfg = KillSwitchConfig(
            enabled=bool(ks_raw.get("enabled", True)),
            flag_file_path=str(ks_raw.get("flag_file_path", "STOP.flag")),
            cli_command_enabled=bool(ks_raw.get("cli_command_enabled", True)),
            telegram_command_enabled=bool(ks_raw.get("telegram_command_enabled", True)),
            on_trigger_action=str(ks_raw.get("on_trigger_action", "CLOSE_ALL_AND_HALT")),
        )

        exec_cfg = ExecutionConfig(
            event_driven=bool(exec_raw.get("event_driven", True)),
            duplicate_order_protection=bool(exec_raw.get("duplicate_order_protection", True)),
            broker_confirmation_required=bool(exec_raw.get("broker_confirmation_required", True)),
            tick_staleness_limit_ms=int(exec_raw.get("tick_staleness_limit_ms", 5000)),
            max_execution_latency_ms=int(exec_raw.get("max_execution_latency_ms", 1500)),
            reconnect_reconciliation=bool(exec_raw.get("reconnect_reconciliation", True)),
            order_type=str(exec_raw.get("order_type", "MARKET")),
            preferred_filling_mode=str(exec_raw.get("preferred_filling_mode", "AUTO")),
            slippage_points=int(exec_raw.get("slippage_points", 25)),
            max_retries=int(exec_raw.get("max_retries", 2)),
            retry_delay_ms=int(exec_raw.get("retry_delay_ms", 20)),
            rate_limit_per_second=int(exec_raw.get("rate_limit_per_second", 10)),
        )

        log_cfg = LoggingConfig(
            log_level=str(log_raw.get("log_level", "INFO")),
            log_file=str(log_raw.get("log_file", "logs/dual_market_scalper.log")),
            log_basket_events=bool(log_raw.get("log_basket_events", True)),
            log_tick_frequency_sec=int(log_raw.get("log_tick_frequency_sec", 10)),
        )

        cfg = cls(
            general=gen_cfg,
            scheduler=sched_cfg,
            symbols=symbols_dict,
            risk=risk_cfg,
            kill_switch=ks_cfg,
            execution=exec_cfg,
            logging=log_cfg,
        )

        gold = cfg.get_symbol_config("GOLD")
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
