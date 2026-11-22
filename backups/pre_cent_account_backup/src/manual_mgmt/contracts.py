"""
Contracts, Enums, and Models for Manual Position Adoption and Trade Management.
Tags: [SAFETY], [VIDEO/KNOWLEDGE], [ASSUMPTION]
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any

from src.core.contracts import OrderType


class PositionClass(str, Enum):
    BOT_OWN = "BOT_OWN"
    MANUAL = "MANUAL"
    OTHER_EA = "OTHER_EA"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class ManagementMode(str, Enum):
    OBSERVE = "OBSERVE"   # [SAFETY] Read-only: audit, monitor, recommend; zero orders
    PROTECT = "PROTECT"   # Adopt naked positions, set structure SL/TP, break-even at +1.0R
    ASSIST = "ASSIST"     # PROTECT + structure trailing stop + momentum alerts
    FULL = "FULL"         # ASSIST + strict winning scale-ins + take-profit / strategy exits


@dataclass
class ManualMgmtConfig:
    enabled: bool = False                        # [SAFETY] Opt-in initially; must be explicitly enabled
    mode: ManagementMode = ManagementMode.OBSERVE
    allow_real_account_management: bool = False  # [SAFETY] Hard lock against real accounts
    poll_interval_seconds: float = 2.0           # [ASSUMPTION] Polling cadence
    user_override_lockout_minutes: int = 30      # [SAFETY] 30m lockout on user edit
    allowed_symbols: List[str] = field(default_factory=list)

    # Protective Stop Loss & Take Profit
    auto_sl_enabled: bool = True
    auto_tp_enabled: bool = True
    tp_target_r: float = 2.0                     # Risk-to-reward ratio for calculated Take Profit
    preserve_user_sl_tp: bool = True             # Preserve user-defined SL/TP by default

    # Break-Even Protection
    break_even_enabled: bool = True
    break_even_activation_r: float = 1.0         # [VIDEO 12] Break-even after confirmed +1.0R
    break_even_buffer_points: float = 10.0       # Spread + commission buffer

    # Trailing Stop Loss
    trailing_stop_enabled: bool = True
    trailing_stop_activation_r: float = 1.5      # [ASSUMPTION] Trail after +1.5R
    trailing_method: str = "STRUCTURE"           # "STRUCTURE", "ATR", "FIXED"
    trailing_atr_multiplier: float = 1.5
    trailing_fixed_points: float = 200.0

    # Automatic Strategy-Based Exit
    auto_exit_enabled: bool = True               # Close position when strategy exit / invalidation occurs

    # Risk & Exposure Controls
    adopt_existing_on_startup: bool = True
    max_manual_positions: int = 5
    max_risk_per_trade_percent: float = 2.0
    max_daily_loss_percent: float = 5.0
    max_addons_per_position: int = 1             # [SAFETY] Maximum 1 pyramid scale-in
    min_addon_rr_in_profit: float = 1.0          # [SAFETY] Position must be >= +1.0R and at BE
    pause_all: bool = False                      # Emergency kill switch flag
    notify_telegram: bool = True                 # Push alerts via Telegram

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ManualMgmtConfig:
        mode_val = data.get("mode", "OBSERVE")
        if isinstance(mode_val, str):
            try:
                mode_val = ManagementMode(mode_val.upper())
            except ValueError:
                mode_val = ManagementMode.OBSERVE

        return cls(
            enabled=bool(data.get("enabled", False)),
            mode=mode_val,
            allow_real_account_management=bool(data.get("allow_real_account_management", False)),
            poll_interval_seconds=float(data.get("poll_interval_seconds", 2.0)),
            user_override_lockout_minutes=int(data.get("user_override_lockout_minutes", 30)),
            allowed_symbols=list(data.get("allowed_symbols", [])),
            auto_sl_enabled=bool(data.get("auto_sl_enabled", True)),
            auto_tp_enabled=bool(data.get("auto_tp_enabled", True)),
            tp_target_r=float(data.get("tp_target_r", 2.0)),
            preserve_user_sl_tp=bool(data.get("preserve_user_sl_tp", True)),
            break_even_enabled=bool(data.get("break_even_enabled", True)),
            break_even_activation_r=float(data.get("break_even_activation_r", 1.0)),
            break_even_buffer_points=float(data.get("break_even_buffer_points", 10.0)),
            trailing_stop_enabled=bool(data.get("trailing_stop_enabled", True)),
            trailing_stop_activation_r=float(data.get("trailing_stop_activation_r", 1.5)),
            trailing_method=str(data.get("trailing_method", "STRUCTURE")).upper(),
            trailing_atr_multiplier=float(data.get("trailing_atr_multiplier", 1.5)),
            trailing_fixed_points=float(data.get("trailing_fixed_points", 200.0)),
            auto_exit_enabled=bool(data.get("auto_exit_enabled", True)),
            adopt_existing_on_startup=bool(data.get("adopt_existing_on_startup", True)),
            max_manual_positions=int(data.get("max_manual_positions", 5)),
            max_risk_per_trade_percent=float(data.get("max_risk_per_trade_percent", 2.0)),
            max_daily_loss_percent=float(data.get("max_daily_loss_percent", 5.0)),
            max_addons_per_position=int(data.get("max_addons_per_position", 1)),
            min_addon_rr_in_profit=float(data.get("min_addon_rr_in_profit", 1.0)),
            pause_all=bool(data.get("pause_all", False)),
            notify_telegram=bool(data.get("notify_telegram", True))
        )


@dataclass
class ManualPositionRecord:
    ticket: int
    symbol: str
    direction: OrderType
    volume: float
    open_price: float
    initial_sl: float
    current_sl: float
    initial_tp: float
    current_tp: float
    adoption_time: str
    assigned_mode: str
    initial_volume: float = 0.0
    last_bot_sl_update: Optional[float] = None
    last_bot_tp_update: Optional[float] = None
    last_bot_update_time: Optional[str] = None
    user_override_detected: bool = False
    lockout_until: Optional[str] = None
    break_even_applied: bool = False
    trailing_applied: bool = False
    last_action: Optional[str] = None
    add_ons_count: int = 0
    notes: List[str] = field(default_factory=list)

    def is_locked_out(self, now: Optional[datetime] = None) -> bool:
        """Returns True if the ticket is currently locked out due to a user override [SAFETY]."""
        if not self.lockout_until:
            return False
        current_dt = now or datetime.now(timezone.utc)
        try:
            lockout_dt = datetime.fromisoformat(self.lockout_until)
            return current_dt < lockout_dt
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.direction.value if isinstance(self.direction, OrderType) else str(self.direction)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ManualPositionRecord:
        dir_val = data.get("direction", "BUY")
        ot = OrderType.BUY if str(dir_val).upper() == "BUY" else OrderType.SELL
        vol = float(data.get("volume", 0.0))
        init_vol = float(data.get("initial_volume", 0.0)) or vol
        return cls(
            ticket=int(data.get("ticket", 0)),
            symbol=str(data.get("symbol", "")),
            direction=ot,
            volume=vol,
            open_price=float(data.get("open_price", 0.0)),
            initial_sl=float(data.get("initial_sl", 0.0)),
            current_sl=float(data.get("current_sl", 0.0)),
            initial_tp=float(data.get("initial_tp", 0.0)),
            current_tp=float(data.get("current_tp", 0.0)),
            adoption_time=str(data.get("adoption_time", "")),
            assigned_mode=str(data.get("assigned_mode", "OBSERVE")),
            initial_volume=init_vol,
            last_bot_sl_update=data.get("last_bot_sl_update"),
            last_bot_tp_update=data.get("last_bot_tp_update"),
            last_bot_update_time=data.get("last_bot_update_time"),
            user_override_detected=bool(data.get("user_override_detected", False)),
            lockout_until=data.get("lockout_until"),
            break_even_applied=bool(data.get("break_even_applied", False)),
            trailing_applied=bool(data.get("trailing_applied", False)),
            last_action=data.get("last_action"),
            add_ons_count=int(data.get("add_ons_count", 0)),
            notes=list(data.get("notes", []))
        )


@dataclass
class AdoptionAssessment:
    ticket: int
    symbol: str
    direction: OrderType
    classification: PositionClass
    action: str  # "NONE", "SET_SL", "SET_TP", "BREAK_EVEN", "TRAIL_SL", "CLOSE", "ADD_ON", "ALERT"
    recommended_sl: Optional[float] = None
    recommended_tp: Optional[float] = None
    add_on_volume: Optional[float] = None
    close_volume: Optional[float] = None
    reason: str = ""
    skills_used: List[str] = field(default_factory=list)
    risk_r_current: float = 0.0
    invalidation_level: Optional[float] = None
