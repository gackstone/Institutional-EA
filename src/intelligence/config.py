"""
Configuration loader, schema validator, and safety limits for Adaptive Trading Intelligence (ATI).
Ensures non-negotiable safety invariant enforcement (approved 3-symbol universe, risk immutability,
no code generation, live trading lock).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.intelligence.contracts import ATIOperatingMode

# Strict 2-symbol canonical whitelist (Gold and Bitcoin only)
CANONICAL_SYMBOLS = ("XAUUSD", "BTCUSD")


@dataclass
class ATISafetyConfig:
    allow_live_trading_activation: bool = False
    allow_risk_limit_changes: bool = False
    allow_symbol_universe_changes: bool = False
    allow_execution_permission_changes: bool = False
    require_candidate_validation: bool = True
    require_approval_for_promotion: bool = True


@dataclass
class ATIConfig:
    enabled: bool = True
    mode: ATIOperatingMode = ATIOperatingMode.OBSERVATION
    auto_training: bool = True
    auto_experimentation: bool = True
    auto_promotion: bool = False  # NEVER auto-promote by default
    autonomous_code_changes: bool = False  # STRICTLY FALSE
    shadow_testing: bool = True
    trade_auditing: bool = True
    pattern_discovery: bool = True
    market_regime_detection: bool = True
    execution_analysis: bool = True
    counterfactual_analysis: bool = True
    model_monitoring: bool = True
    rollback_enabled: bool = True
    approved_symbols: List[str] = field(default_factory=lambda: list(CANONICAL_SYMBOLS))
    safety: ATISafetyConfig = field(default_factory=ATISafetyConfig)
    database_path: Optional[str] = None
    min_audit_samples: int = 5
    min_backtest_trades: int = 20

    def validate(self) -> None:
        """Enforces hard security and safety bounds."""
        # 1. Symbol whitelist safety
        for sym in self.approved_symbols:
            if sym.upper() not in CANONICAL_SYMBOLS:
                raise ValueError(
                    f"ATI Safety Violation: Symbol '{sym}' is outside the authorized universe {CANONICAL_SYMBOLS}."
                )

        # 2. Safety rules invariant enforcement
        if self.safety.allow_live_trading_activation:
            raise ValueError("ATI Safety Violation: allow_live_trading_activation must never be enabled.")

        if self.safety.allow_symbol_universe_changes:
            raise ValueError("ATI Safety Violation: allow_symbol_universe_changes must never be enabled.")

        if self.safety.allow_risk_limit_changes:
            raise ValueError("ATI Safety Violation: allow_risk_limit_changes must never be enabled.")

        if self.autonomous_code_changes:
            raise ValueError("ATI Safety Violation: autonomous_code_changes is strictly prohibited.")

        # 3. Operating mode safety
        if isinstance(self.mode, str):
            try:
                self.mode = ATIOperatingMode(self.mode.upper())
            except ValueError:
                self.mode = ATIOperatingMode.OBSERVATION

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ATIConfig:
        raw = dict(data)
        mode_val = raw.get("mode", ATIOperatingMode.OBSERVATION.value)
        if isinstance(mode_val, str):
            try:
                mode_enum = ATIOperatingMode(mode_val.upper())
            except ValueError:
                mode_enum = ATIOperatingMode.OBSERVATION
        else:
            mode_enum = mode_val

        safety_dict = raw.get("safety", {})
        safety_cfg = ATISafetyConfig(**safety_dict) if isinstance(safety_dict, dict) else ATISafetyConfig()

        cfg = cls(
            enabled=bool(raw.get("enabled", True)),
            mode=mode_enum,
            auto_training=bool(raw.get("auto_training", True)),
            auto_experimentation=bool(raw.get("auto_experimentation", True)),
            auto_promotion=bool(raw.get("auto_promotion", False)),
            autonomous_code_changes=False,  # strictly forced to False
            shadow_testing=bool(raw.get("shadow_testing", True)),
            trade_auditing=bool(raw.get("trade_auditing", True)),
            pattern_discovery=bool(raw.get("pattern_discovery", True)),
            market_regime_detection=bool(raw.get("market_regime_detection", True)),
            execution_analysis=bool(raw.get("execution_analysis", True)),
            counterfactual_analysis=bool(raw.get("counterfactual_analysis", True)),
            model_monitoring=bool(raw.get("model_monitoring", True)),
            rollback_enabled=bool(raw.get("rollback_enabled", True)),
            approved_symbols=list(raw.get("approved_symbols", CANONICAL_SYMBOLS)),
            safety=safety_cfg,
            database_path=raw.get("database_path"),
            min_audit_samples=int(raw.get("min_audit_samples", 5)),
            min_backtest_trades=int(raw.get("min_backtest_trades", 20)),
        )
        cfg.validate()
        return cfg

    @classmethod
    def load_from_file(cls, path: str | Path) -> ATIConfig:
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            ati_data = data.get("ati", data)
            return cls.from_dict(ati_data)
