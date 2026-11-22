"""
Authoritative Configuration Service for the Institutional EA Companion & Trading Engine.
Validates all configuration updates, enforces DEMO-only safety locks, tracks
versioned configuration history in SQLite, supports preview/rollback/export/import,
and identifies settings requiring an engine restart.
"""

from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from companion.database.repository import CompanionRepository
from src.core.config import AppConfig


ALLOWED_OPERATING_MODES = (
    "OBSERVE",
    "DRY_RUN",
    "DEMO_SCALPING",
    "DEMO_FAST",
    "DEMO_MANUAL_ASSIST",
    "BTCUSD_DEMO_SAMPLE_MODE",
)

RESTART_REQUIRED_KEYS = {
    "bridge_host",
    "bridge_port",
    "bridge_sub_port",
    "magic_number",
    "symbols",
    "EXECUTION_TIMEFRAMES",
    "CONTEXT_TIMEFRAMES",
    "TRADING_MODE",
}


class ConfigurationValidationError(ValueError):
    """Raised when a proposed configuration update fails safety or schema validation."""


class ConfigurationService:
    def __init__(self, config_dir: str | Path, repo: CompanionRepository):
        self.config_dir = Path(config_dir)
        self.repo = repo
        self.settings_path = self.config_dir / "settings.json"
        self.risk_path = self.config_dir / "risk_config.json"
        self.strategy_path = self.config_dir / "strategy_config.json"
        self.instruments_path = self.config_dir / "instruments.json"

        # Seed initial version if none recorded yet
        if not self.repo.get_config_versions(limit=1):
            self.repo.save_config_version(
                self.get_full_config(),
                change_summary="Initial baseline configuration snapshot",
                author="system",
                requires_restart=False,
            )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_full_config(self) -> Dict[str, Any]:
        settings = self._read_json(self.settings_path)
        risk = self._read_json(self.risk_path)
        strategy = self._read_json(self.strategy_path)
        instruments = self._read_json(self.instruments_path)
        operating_mode = settings.get("operating_mode", "DRY_RUN" if settings.get("dry_run") else "DEMO_SCALPING")
        return {
            "operating_mode": operating_mode,
            "settings": settings,
            "risk": risk,
            "strategy": strategy,
            "instruments": instruments,
            "live_trading_locked": True,
        }

    def validate_bundle(self, bundle: Dict[str, Any]) -> List[str]:
        """Validates a configuration bundle and returns a list of validation errors (empty if valid)."""
        errors: List[str] = []
        settings = bundle.get("settings", {})
        risk = bundle.get("risk", {})
        op_mode = bundle.get("operating_mode") or settings.get("operating_mode", "DEMO_SCALPING")

        if op_mode not in ALLOWED_OPERATING_MODES:
            errors.append(f"Invalid operating_mode '{op_mode}'. Must be one of {ALLOWED_OPERATING_MODES}.")

        if settings.get("LIVE_TRADING_ENABLED") is True:
            errors.append("LIVE_TRADING_ENABLED must remain false. Live trading is strictly locked.")

        exec_mode = str(settings.get("execution_mode", "DEMO")).upper()
        if exec_mode in ("REAL", "LIVE"):
            errors.append(f"execution_mode '{exec_mode}' is prohibited. Only DEMO mode is permitted.")

        risk_pct = float(risk.get("risk_percentage", 1.0))
        if not (0.05 <= risk_pct <= 2.0):
            errors.append(f"risk_percentage ({risk_pct}) must be between 0.05% and 2.00%.")

        # Note: Daily-loss limits are disabled per architecture directive
        max_daily = float(risk.get("max_daily_loss_percent", 0.0))
        if max_daily > 0 and not (0.5 <= max_daily <= 20.0):
            errors.append(f"max_daily_loss_percent ({max_daily}) must be between 0.5% and 20.0%.")

        max_agg = float(risk.get("max_aggregate_open_risk_percent", 6.0))
        if not (0.5 <= max_agg <= 25.0):
            errors.append(f"max_aggregate_open_risk_percent ({max_agg}) must be between 0.5% and 25.0%.")

        max_sym_risk = float(risk.get("max_symbol_risk_percent", 4.0))
        if not (0.5 <= max_sym_risk <= 15.0):
            errors.append(f"max_symbol_risk_percent ({max_sym_risk}) must be between 0.5% and 15.0%.")

        max_margin_util = float(risk.get("max_margin_utilization_percent", 80.0))
        if not (10.0 <= max_margin_util <= 95.0):
            errors.append(f"max_margin_utilization_percent ({max_margin_util}) must be between 10.0% and 95.0%.")

        bridge_port = int(settings.get("bridge_port", 5555))
        if not (1024 <= bridge_port <= 65535):
            errors.append(f"bridge_port ({bridge_port}) must be between 1024 and 65535.")

        if "symbols" in settings and isinstance(settings["symbols"], list):
            from src.core.symbol_universe import get_symbol_universe
            universe = get_symbol_universe()
            invalid_syms = [s for s in settings["symbols"] if not universe.is_approved(str(s))]
            if invalid_syms:
                errors.append(
                    f"Unauthorized symbols {invalid_syms}. Only XAUUSD and BTCUSD are permitted."
                )

        return errors

    def preview_changes(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Computes proposed diff, validation errors, and whether an engine restart is required."""
        current = self.get_full_config()
        proposed = copy.deepcopy(current)

        for section in ("settings", "risk", "strategy", "instruments"):
            if section in patch and isinstance(patch[section], dict):
                if section == "instruments" and "instruments" in patch["instruments"]:
                    proposed["instruments"] = copy.deepcopy(patch["instruments"])
                else:
                    proposed[section].update(patch[section])

        if "operating_mode" in patch:
            proposed["operating_mode"] = patch["operating_mode"]
            proposed["settings"]["operating_mode"] = patch["operating_mode"]
            proposed["settings"]["dry_run"] = patch["operating_mode"] == "DRY_RUN"

        # Enforce DEMO lock on proposed state before validation if omitted
        proposed["settings"].setdefault("execution_mode", "DEMO")
        proposed["settings"].setdefault("LIVE_TRADING_ENABLED", False)

        errors = self.validate_bundle(proposed)
        changed_keys: List[str] = []
        requires_restart = False

        for sec in ("settings", "risk", "strategy"):
            cur_sec = current.get(sec, {})
            new_sec = proposed.get(sec, {})
            for k in set(cur_sec.keys()) | set(new_sec.keys()):
                if cur_sec.get(k) != new_sec.get(k):
                    changed_keys.append(f"{sec}.{k}")
                    if k in RESTART_REQUIRED_KEYS:
                        requires_restart = True

        if current.get("operating_mode") != proposed.get("operating_mode"):
            changed_keys.append("operating_mode")

        if current.get("instruments") != proposed.get("instruments"):
            changed_keys.append("instruments")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "changed_keys": sorted(changed_keys),
            "requires_restart": requires_restart,
            "proposed": proposed,
        }

    def apply_update(
        self,
        patch: Dict[str, Any],
        change_summary: str = "Configuration update via Companion Control Centre",
        author: str = "operator",
    ) -> Dict[str, Any]:
        """Validates and atomically commits configuration changes with version tracking."""
        preview = self.preview_changes(patch)
        if not preview["valid"]:
            raise ConfigurationValidationError("; ".join(preview["errors"]))

        proposed = preview["proposed"]
        if "risk" in proposed:
            proposed["risk"]["max_daily_loss_enabled"] = False
            proposed["risk"]["max_daily_loss_percent"] = 0.0
        if "settings" in proposed and "MAX_DAILY_LOSS_ENABLED" in proposed["settings"]:
            proposed["settings"]["MAX_DAILY_LOSS_ENABLED"] = False
        self._write_json(self.settings_path, proposed["settings"])
        self._write_json(self.risk_path, proposed["risk"])
        self._write_json(self.strategy_path, proposed["strategy"])
        self._write_json(self.instruments_path, proposed["instruments"])

        # Verify AppConfig loads cleanly after write
        AppConfig.load_from_dir(str(self.config_dir))

        ver = self.repo.save_config_version(
            proposed,
            change_summary=change_summary,
            author=author,
            requires_restart=preview["requires_restart"],
        )
        self.repo.record_audit(
            actor=author,
            action="CONFIG_UPDATE",
            component="ConfigurationService",
            details=f"v{ver}: {change_summary} | keys={preview['changed_keys']}",
        )
        return {
            "version": ver,
            "changed_keys": preview["changed_keys"],
            "requires_restart": preview["requires_restart"],
            "config": proposed,
        }

    def rollback_to_version(self, version: int, author: str = "operator") -> Dict[str, Any]:
        """Restores a previously recorded configuration version."""
        bundle = self.repo.get_config_version_data(version)
        if not bundle:
            raise ConfigurationValidationError(f"Configuration version {version} not found.")
        return self.apply_update(
            bundle,
            change_summary=f"Rollback to configuration v{version}",
            author=author,
        )

    def get_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self.repo.get_config_versions(limit=limit)
