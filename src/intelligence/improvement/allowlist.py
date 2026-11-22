"""
Allowlist and Parameter Safety Validator for ATI Self-Improvement.
Enforces that only non-safety-critical, bounded trading parameters may be candidate targets.
Strictly blocks modification of risk limits, stop losses, whitelist symbols, and live trading locks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

# Strictly authorized adaptive parameters and their immutable valid ranges
ALLOWLISTED_PARAMETER_BOUNDS: Dict[str, Tuple[float, float]] = {
    "max_spread_pts": (10.0, 50.0),
    "min_confluence_score": (50.0, 95.0),
    "min_risk_reward_ratio": (1.0, 5.0),
    "adx_entry_threshold": (12.0, 40.0),
    "fast_exit_profit_floor_usd": (1.0, 20.0),
    "trailing_activation_profit_usd": (2.0, 30.0),
    "swing_lookback_bars": (3.0, 15.0),
}

# Forbidden keys that must NEVER be altered by any autonomous adaptation
FORBIDDEN_PARAMETER_KEYS: Set[str] = {
    "symbols",
    "approved_symbols",
    "whitelist",
    "account_number",
    "risk_percentage",
    "max_account_risk",
    "max_drawdown_percent",
    "emergency_stop",
    "mandatory_sl",
    "demo_mode",
    "live_trading_enabled",
    "password",
    "api_key",
    "token",
}


class ParameterAllowlistValidator:
    """Validates proposed candidate parameters against hard safety boundaries."""

    @classmethod
    def validate_candidate_parameters(cls, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates candidate dictionary against allowlist and forbidden keys.
        Returns (is_valid, error_reason).
        """
        if not params:
            return False, "Candidate parameters dictionary is empty."

        for key, value in params.items():
            k_lower = key.lower()

            # 1. Check for any forbidden security/risk key
            for forbidden in FORBIDDEN_PARAMETER_KEYS:
                if forbidden in k_lower:
                    return False, f"CRITICAL SAFETY VIOLATION: Parameter '{key}' matches forbidden safety key '{forbidden}'."

            # 2. Check if key is explicitly in the allowlist
            if key not in ALLOWLISTED_PARAMETER_BOUNDS:
                return False, f"Parameter '{key}' is not in the explicit ATI adaptation allowlist."

            # 3. Check parameter type and bounds
            if not isinstance(value, (int, float)):
                return False, f"Parameter '{key}' value must be numeric, got {type(value).__name__}."

            min_b, max_b = ALLOWLISTED_PARAMETER_BOUNDS[key]
            if value < min_b or value > max_b:
                return False, f"Parameter '{key}' value {value} is outside allowed safe bounds [{min_b}, {max_b}]."

        return True, "Valid"

    @classmethod
    def compute_config_checksum(cls, config_dict: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 checksum of configuration payload."""
        payload = json.dumps(config_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
