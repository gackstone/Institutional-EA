# Manual Position Adoption & Professional Trade Management Runbook

> **Version:** 1.0.0  
> **Classification Tagging:** `[SAFETY]` (Non-negotiable invariants), `[VIDEO/KNOWLEDGE]` (Transferred SMC strategy skills), `[ASSUMPTION]` (Engineering parameters requiring paper testing).  
> **Disclaimer:** Software engineering guide for algorithmic trading tools. Illustrative and educational purposes only. Not financial advice.

---

## 1. Overview & Operational Philosophy

The **Manual Position Management Subsystem** empowers traders to open discretionary trades directly on their desktop, mobile, or WebTrader MetaTrader 5 terminal while delegating ongoing lifecycle risk management to the bot's transferred algorithmic strategy engine.

### Core Tenets
1. **Safety Beats Completeness:** If any condition is ambiguous, the bot defaults to read-only observation (`OBSERVE`).
2. **User Supremacy:** The user is always the ultimate authority. If the user edits an adopted trade's Stop Loss or Take Profit in MT5, the bot immediately cedes control and locks itself out for 30 minutes.
3. **Tighten-Only Stop Policy (R9.3):** The bot is mathematically prevented from widening a stop loss or removing a stop loss. It can only reduce risk.
4. **No Pyramiding on Losers:** Adding to positions (in `FULL` mode) is strictly forbidden unless the initial trade is in profit and its stop loss is already secured at break-even or better.

---

## 2. Operational Modes

The system operates under four distinct modes configured via `config/manual_management.yaml`:

```
 [ OBSERVE ]  --->  [ PROTECT ]  --->  [ ASSIST ]  --->  [ FULL ]
  Read-only          Naked SL           PROTECT +         ASSIST +
  Telemetry &        Placement &        Structural        Winning
  Recommendations    Break-Even         Trailing Stops    Scale-Ins
```

| Mode | Allowed Actions | Broker Writes Permitted? | Intended Use Case |
| :--- | :--- | :---: | :--- |
| **`OBSERVE`** *(Default)* | Analysis, recommendation logging, alerts | **NO** (Zero orders/writes) | Paper testing, monitoring, and audit verification. |
| **`PROTECT`** | `SET_SL` (naked positions), `BREAK_EVEN` | **YES** (Tighten SL only) | Disaster protection: sets stop on naked manual trades and secures Break-Even at +1.0R. |
| **`ASSIST`** | `SET_SL`, `BREAK_EVEN`, `TRAIL_SL` | **YES** (Tighten SL only) | Professional swing & trend following: trails confirmed structure pivots at +1.5R. |
| **`FULL`** | `SET_SL`, `BREAK_EVEN`, `TRAIL_SL`, `ADD_ON` | **YES** (SL & continuation orders) | Autonomous scaling: adds to winning positions once risk is banked at Break-Even. |

---

## 3. Position Classification Hierarchy

Every open MT5 position is evaluated against the following deterministic priority chain:

1. **`BOT_OWN`**: `pos.magic == config.magic_number` (default `100101`). Managed exclusively by the bot's autonomous scalper/swing pipelines.
2. **`EXCLUDED`**:
   - Ticket comment contains `#bot:off`, `#ignore`, or `#manual:off`.
   - Symbol is not listed in `config.allowed_symbols` (when list is non-empty).
3. **`OTHER_EA`**: `pos.magic != 0` and `pos.magic != config.magic_number`, or opening deal reason was `DEAL_REASON_EXPERT`. Strictly untouched.
4. **`MANUAL`**: `pos.magic == 0` and opening deal reason is `CLIENT` (desktop), `MOBILE` (iOS/Android), or `WEB`. Adopted and managed according to configured mode.
5. **`UNKNOWN`**: Fallback for unclassified tickets. Treated as read-only.

---

## 4. Safety Controls & Invariants `[SAFETY]`

### A. Real Account Protection
By default, the engine refuses all broker modifications if connected to a **REAL** account (`account_info().trade_mode == REAL` or 2). To enable management on real funds, you must explicitly configure:
```yaml
allow_real_account_management: true
```
If this flag is `false`, the bot automatically downgrades to `OBSERVE` mode and emits a security log.

### B. Netting Account Isolation
In Netting accounts (`margin_mode == 1`), brokers maintain only one volume-weighted position per symbol. Any new manual order modifies the bot's tickets. The subsystem automatically detects Netting accounts and forces `OBSERVE` mode to prevent position contamination.

### C. 30-Minute User Override Lockout
If the trader drags an SL or TP in MT5:
1. The registry compares broker SL against `record.last_bot_sl_update`.
2. A user modification triggers `record.user_override_detected = True`.
3. The bot sets `lockout_until = now + 30 minutes` and logs `[USER_OVERRIDE]`.
4. The bot will reject all automated modifications for that ticket until the timer expires.

### D. Emergency Kill Switch (`state/PAUSE`)
To immediately halt all automated order modifications across manual positions:
- Create an empty file named `state/PAUSE`, or
- Set `pause_all: true` in `config/manual_management.yaml`.

---

## 5. Configuration Reference (`config/manual_management.yaml`)

```yaml
# Operational mode: OBSERVE, PROTECT, ASSIST, FULL
mode: "OBSERVE"

# Real account barrier (safety lock)
allow_real_account_management: false

# Detection poll interval in seconds
poll_interval_seconds: 2.0

# User override freeze timer (minutes)
user_override_lockout_minutes: 30

# Allowed symbols (empty list = allow all)
allowed_symbols:
  - "EURUSD"
  - "GBPUSD"
  - "USDJPY"
  - "XAUUSD"

# Risk & Lifecycle Parameters
break_even_activation_r: 1.0       # [VIDEO 12] Advance SL to BE at +1.0R
break_even_buffer_points: 10.0      # Buffer to cover spread + commissions
trailing_stop_activation_r: 1.5   # [VIDEO 15] Begin trailing at +1.5R
max_addons_per_position: 1         # Max continuation scale-ins
min_addon_rr_in_profit: 1.0        # Profit required before add-on permitted

# Emergency kill switch
pause_all: false
```

---

## 6. Verification & Replay Harness

The repository includes a dedicated replay simulator to verify position adoption, Break-Even, trailing stops, and user overrides before deploying live:

```powershell
# 1. Test naked position adoption and Break-Even in PROTECT mode:
python scripts/run_manual_replay.py --mode PROTECT --entry 1.1000 --sl 0.0 --steps 12 --override-step -1

# 2. Test structural trailing stop advancement in ASSIST mode:
python scripts/run_manual_replay.py --mode ASSIST --entry 1.1000 --sl 0.0 --steps 12 --override-step -1

# 3. Test user override detection and lockout:
python scripts/run_manual_replay.py --mode PROTECT --entry 1.1000 --sl 1.0950 --steps 12 --override-step 7
```

---

## 7. State & Audit Files

- **`state/manual_positions.json`:** Active adopted positions state (atomic JSON writes).
- **`state/manual_positions_history.json`:** Permanent archive of closed manual positions.
- **`logs/manual_management_audit.log`:** Structured JSON-lines audit log tracking every adoption, SL update, and override event.

---

## 8. Unit Test Suite

Execute the dedicated 13-scenario unit test suite:
```powershell
$env:PYTHONPATH="."
python -m unittest -v tests/test_manual_management.py
```
All 13 tests verify classification, naked adoption, tighten-only enforcement, user override lockouts, real account barriers, netting account isolation, and add-on invariants.
