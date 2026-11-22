# MT5 001 — Complete Risk Management Forensic Audit
**Forensic Technical Intelligence Audit**  
**Classification:** Quantitative Risk & Execution Governance Audit  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Quantitative Risk Analyst & Financial Systems Auditor  
**Date of Audit:** November 2026  

---

## 1. Executive Summary: Risk Architecture & Philosophy

The **MT5 001** automated trading system implements a multi-tiered, defense-in-depth risk architecture. Risk is not governed by a single configuration parameter or cosmetic UI toggle; rather, it is enforced across **four distinct, non-bypassable barriers**:

1. **Native MQL5 Execution Gatekeeper** (`mql5/Experts/PythonBridgeEA.mq5`): Local pre-trade checks in native code prior to sending any order to the broker.
2. **Deterministic Position Sizing Engine** (`src/risk/position_sizing.py`): Enforces Rule R9 (hard-coded 2.0% risk cap), account capital tier limits, and tick-value quantization.
3. **Portfolio & Challenge Risk Supervisor** (`src/risk/portfolio_risk.py`): Real-time account equity tracking, trailing drawdown circuit breakers, and correlation constraints.
4. **Setup Quality Gate G8** (`src/smc/setup_quality_gate.py`): Pre-execution gate requiring structural stop loss and rejecting overexposure.

---

## 2. Account-Level Risk Management

### A. Risk Baseline Determination (Balance vs. Equity)
- **Primary Finding:** The system uses a **conservative hybrid baseline**:
  $$\text{Capital Base} = \min(\text{Account Balance}, \text{Account Equity})$$
  *(Verified in `PythonBridgeEA.mq5:2612`, `PythonBridgeEA.mq5:3901`, and `src/risk/position_sizing.py:103`).*
- **Audit Assessment:** This is an institutional best practice. By taking the minimum of balance and equity:
  - If the account has open floating profits, it **does not** pyramid risk on unrealized gains.
  - If the account has open floating losses (drawdown), it **immediately contracts** position sizes to reflect the reduced equity.

### B. Universal Account Tier Hierarchy & Capital Floors
The bot categorizes accounts into 6 distinct tiers via `AccountTierManager` (`config/account_tiers.json` and `src/risk/account_tier.py`):

| Account Tier | Balance Range (USD) | Target Risk % | Absolute Ceiling % | Max Open Positions | Max Total Risk % | Daily Loss Cap | Consecutive Loss Limit | Trading Allowed? |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BELOW_FLOOR** | `$0.00` to `< $5.00` | 0.0% | 0.0% | 0 | 0.0% | $0.00 | 1 | **NO (Hard Halt)** |
| **MICRO** | `$5.00` to `< $25.00` | 1.0% | 2.0% | 1 | 2.0% | $0.50 (2%) | 2 | **YES (With Flags)** |
| **MINI** | `$25.00` to `< $100.00`| 1.0% | 2.0% | 1 | 2.0% | $2.00 (2%) | 2 | **YES** |
| **SMALL** | `$100.00` to `< $500.00`| 1.0% | 2.0% | 2 | 3.0% | $15.00 (3%) | 3 | **YES** |
| **STANDARD** | `$500.00` to `< $5,000.00`| 1.0% | 2.0% | 3 | 3.0% | $100.00 (2.5%)| 3 | **YES** |
| **LARGE** | `$5,000.00`+ | 0.75% | 1.0% | 4 | 2.0% | $250.00 (2%) | 3 | **YES** |

- **Cent Account Detection:** Both Python and MQL5 detect USC, EUC, GBX, and JPC currencies, automatically dividing raw balance and equity by 100.0 to convert cent balances into USD equivalents (`PythonBridgeEA.mq5:3893-3900`).
- **Operating Floor Guard:** Any account with capital base `< $5.00` is assigned `BELOW_FLOOR` and trading is completely disabled (`position_sizing.py:133-157`).

---

## 3. Position Sizing & Lot Calculation Forensic Audit

### A. The Exact Lot-Sizing Formula
The bot sizes every order dynamically using tick-level contract specifications and structural stop loss distance:

$$\text{Risk Amount (\USD)} = \text{Capital Base} \times \left(\frac{\min(\text{Target Risk \%}, \text{Hard Ceiling \%})}{100}\right)$$

$$\text{Loss Per Lot (\USD)} = \left(\frac{\text{SL Distance (Price Points)} \times \text{Point Size}}{\text{Tick Size}}\right) \times \text{Tick Value}$$

$$\text{Total Loss Per Lot} = \text{Loss Per Lot} + \text{Estimated Spread Drag} + \text{Commission Drag}$$
*(Where commission is modeled at $7.00 per standard roundturn lot).*

$$\text{Raw Lots} = \frac{\text{Risk Amount}}{\text{Total Loss Per Lot}}$$

$$\text{Quantized Volume} = \left\lfloor \frac{\text{Raw Lots}}{\text{Volume Step}} \right\rfloor \times \text{Volume Step}$$

$$\text{Final Volume} = \min(\text{Quantized Volume}, \text{Broker Max Lot}, \text{Profile Max Lot Cap})$$

- **Strict Round-Down Invariant:** Sizing uses `math.floor()` / `MathFloor()`. Volume is **never rounded up**, guaranteeing that actual monetary risk never exceeds the configured percentage due to step rounding (`PythonBridgeEA.mq5:3962`, `position_sizing.py:240`).
- **Dynamic Lot Cap for Small Accounts:** For accounts under $500.00, volume is dynamically capped at $\min(\text{Broker Max Lot}, \text{Min Lot} \times 3.0)$ (`PythonBridgeEA.mq5:3954`, `position_sizing.py:236`).

---

### B. Worked Mathematical Example

#### Hypothetical Account Parameters:
- **Account Balance:** \$2,500.00 USD
- **Account Equity:** \$2,400.00 USD
- **Instrument:** EURUSD
- **Entry Price (Ask):** 1.08500
- **Stop Loss Price:** 1.08300 (Structural SL distance = 0.00200 = 200 points / 20.0 pips)
- **Symbol Contract Specs:**
  - `Point Size`: 0.00001
  - `Tick Size`: 0.00001
  - `Tick Value`: \$1.00 USD per tick per standard lot
  - `Volume Step`: 0.01 lots
  - `Min Lot`: 0.01 lots
  - `Spread`: 1.2 pips (12 points)
- **Configured Target Risk:** 1.0% (Tier: STANDARD, Ceiling: 2.0%)

#### Step-by-Step Calculation:
1. **Capital Base Selection:**
   $$\text{Capital Base} = \min(2500.00, 2400.00) = \$2,400.00\text{ USD}$$
2. **Target Monetary Risk:**
   $$\text{Risk Amount} = \$2,400.00 \times \left(\frac{1.0}{100}\right) = \$24.00\text{ USD}$$
3. **Loss Per Lot Calculation:**
   $$\text{Ticks in SL} = \frac{0.00200}{0.00001} = 200\text{ ticks}$$
   $$\text{Base Loss Per Lot} = 200 \times \$1.00 = \$200.00\text{ USD}$$
   $$\text{Spread Cost Per Lot} = 12 \times \$1.00 = \$12.00\text{ USD}$$
   $$\text{Commission Cost Per Lot} = \$7.00\text{ USD}$$
   $$\text{Total Loss Per Lot} = 200.00 + 12.00 + 7.00 = \$219.00\text{ USD per lot}$$
4. **Raw Lot Calculation:**
   $$\text{Raw Lots} = \frac{\$24.00}{\$219.00} = 0.109589\text{ lots}$$
5. **Volume Quantization (Step = 0.01):**
   $$\text{Steps} = \lfloor 0.109589 / 0.01 \rfloor = \lfloor 10.9589 \rfloor = 10$$
   $$\text{Quantized Volume} = 10 \times 0.01 = \mathbf{0.10\text{ lots}}$$
6. **Real Risk Verification:**
   $$\text{Monetary Risk at SL} = 0.10 \times \$219.00 = \$21.90\text{ USD}$$
   $$\text{Actual Risk Percentage} = \left(\frac{\$21.90}{\$2,400.00}\right) \times 100 = \mathbf{0.9125\%}$$
   - Verified: $0.9125\% \le 1.0\%$ (Target) $< 2.0\%$ (R9 Hard Ceiling). **APPROVED.**

---

### C. The Micro-Account Dilemma ($5 - $25 Accounts)
On a $10 account with EURUSD and a 20-pip SL, 0.01 lot risks:
$$0.01 \times \$219.00 = \$2.19\text{ USD} \implies \frac{\$2.19}{\$10.00} = \mathbf{21.9\%\text{ risk}}$$
- **Forensic Finding:** A 21.9% risk violates Rule R9 (2.0% hard cap).
- **How the bot handles this:**
  - By default, `InpMicroAccountMinLotAllowed = false`. The trade is **strictly rejected** with reason:
    `"Min lot 0.01 risks $2.19 (21.90% of capital $10.00), exceeding target risk 1.00% (Ceiling: 2.00%). Min balance needed: $219.00."` (`position_sizing.py:280-309`).
  - Only if the operator explicitly enables BOTH `micro_account_min_lot_allowed: true` AND `acknowledged_high_risk_microaccount: true` AND risk is within `InpAbsoluteRiskCeiling` (5.0%) will an exception be considered. Otherwise, accounts under ~$100–$200 are mathematically blocked from trading wide-stop currency setups, protecting the user from inadvertent over-leverage.

---

## 4. Stop-Loss & Trade Protection Audit

### A. Mandatory Protective Stop-Loss (Rule R9.2)
- **Zero Unprotected Positions:** Every single order path (`OrderManager.execute_signal`, `PythonBridgeEA.mq5:TRADE`, `SetupQualityGate:G8`, `PortfolioRiskEngine:1c`) enforces:
  $$\text{If } \text{Stop Loss} \le 0.0 \implies \mathbf{REJECT\ ORDER}$$
- There is **no execution path** in the codebase capable of creating a naked/unprotected position.

### B. Anti-Widening Stop Policy (Rule R9.3)
- Stop loss modifications are audited by `OrderManager.validate_sl_modification()`:
  - For BUY positions: `new_sl < current_sl` is **strictly rejected**.
  - For SELL positions: `new_sl > current_sl` is **strictly rejected**.
  - Removing a stop loss (`new_sl <= 0`) is **strictly rejected**.
  - *Slogan enforced in code:* "Never move a stop loss further away from price; never widen risk."

### C. Stop Distance Constraints
- **Broker Freeze & Stop Level Gate:** Stop distances must exceed `stops_level * 2.5` to avoid broker rejection (`continuous_scalper.py:676-683`).
- **Dynamic Spread Filter:** If current broker spread exceeds 35% of the stop loss distance, trade entry is skipped (`continuous_scalper.py:679`, `PythonBridgeEA.mq5:2571-2580`).

---

## 5. Take-Profit & Reward Management

### A. Expected Reward vs. Monetary Risk (R:R Calculation)
- The bot does **not** rely on naive pip distance comparisons. It computes actual monetary reward against actual monetary loss:
  $$\text{Reward-to-Risk (R:R)} = \frac{\text{Net Monetary Gain at TP (\USD)}}{\text{Total Monetary Loss at SL (\USD)}}$$
  *(Verified in `position_sizing.py:348`, `PythonBridgeEA.mq5:2589-2593`).*
- All trading modes require minimum R:R >= 1.20 (scalping) or >= 2.00 (SMC).

### B. Active Profit Locking Subsystem ($5+ Floor & Trailing)
Implemented in `src/risk/trade_management.py` and `src/core/orchestrator.py:manage_active_positions`:
1. **$5.00 Net Profit Target Lock (`enable_profit_management_5usd: true`)**:
   - When a position's net unrealized profit (after swap and commissions) reaches or exceeds \$5.00 USD, the bot immediately moves the stop loss to lock in a minimum \$5.00 net floor profit.
2. **Strong Momentum Profit Extension**:
   - If price exhibits accelerating momentum (ADX > 30 and ATR expansion), instead of closing immediately at \$5.00, it activates an aggressive trailing lock (`profit_extension_lock_ratio = 0.65`), locking in 65% of peak floating profit while letting the remainder run.
3. **Break-Even Protection**:
   - Moves stop loss to entry price + buffer (1.0 pip / 20 points) once profit reaches +1.0R (or +0.5R in fast scalp mode).
4. **Partial Profit Taking**:
   - Closes 50% (`partial_tp_ratio = 0.50`) of volume at +1.0R / +1.5R, leaving the remaining half risk-free with stop loss at break-even.

---

## 6. Daily, Weekly & Portfolio Risk Controls

### A. Multi-Tier Drawdown Protection

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DRAWDOWN CONTROL LADDER                         │
├───────────────────────┬──────────────┬─────────────────────────────────┤
│ Drawdown Level        │ Multiplier   │ Operational Action              │
├───────────────────────┼──────────────┼─────────────────────────────────┤
│ Normal (0% to Buffer) │ 1.0x         │ Normal operations               │
├───────────────────────┼──────────────┼─────────────────────────────────┤
│ Mild Throttle (60%)   │ 0.6x         │ Reduce position risk by 40%     │
├───────────────────────┼──────────────┼─────────────────────────────────┤
│ Heavy Throttle (75%)  │ 0.3x         │ Reduce position risk by 70%     │
├───────────────────────┼──────────────┼─────────────────────────────────┤
│ Safety Buffer (80%)   │ 0.0x         │ PAUSE: Block new trade entries  │
├───────────────────────┼──────────────┼─────────────────────────────────┤
│ Hard Limit (95%-100%) │ Circuit Break│ HARD LOCK: Halt bot, alert op   │
└───────────────────────┴──────────────┴─────────────────────────────────┘
```

- **Drawdown Types Supported:**
  - `STATIC`: Calculated from initial account balance.
  - `TRAILING`: Calculated from peak high-watermark equity.
  - `DAILY_START_BALANCE` / `DAILY_START_EQUITY`: Calculated from day-start baseline.
- **Safety Buffer Invariant:** Halts opening new trades when drawdown reaches 80% of the limit (e.g. at 3.2% loss on a 4.0% daily limit), ensuring slippage on open positions cannot cause an account breach.

### B. Streak & Cooldown Limits
- **Max Consecutive Losses:** Hard cap of 3 consecutive losses (`max_consecutive_losses: 3`).
- **Consecutive Loss Cooldown:** After 2 losses on a single symbol, enforces an automated 15-minute symbol cooldown (`symbol_cooldown_until`).
- **Global Circuit Breaker Recovery:** Consecutive-loss breaker pauses trading for 30 minutes, then auto-recovers safely without requiring manual intervention (`portfolio_risk.py:308-335`).

### C. Correlation & Portfolio Concentration Risk
- **Aggregate Open Risk Cap:** Total combined open risk across all positions cannot exceed 1.5% - 3.0% of equity (`max_aggregate_open_risk_percent`).
- **Correlation Clusters:** Categorizes symbols into 5 correlation groups (`METALS`, `CRYPTO`, `EUR_GBP_BLOC`, `USD_MAJORS`, `INDICES`).
- **Hedging & Directional Exposure:** In `RETAIL` mode, simultaneous hedging is allowed. In `PROP` mode, opposite hedging and duplicate directional exposure are prohibited.

---

## 7. Execution Risk & Broker Constraints

- **Spread Guard:** Dynamically samples live Ask-Bid spread. Rejects entries if spread exceeds configured pip ceiling or 35% of SL distance.
- **Broker Filling Mode Adaptation:** Dynamically interrogates symbol capabilities (`SYMBOL_FILLING_MODE`), auto-selecting `IOC`, `FOK`, or `RETURN` (`PythonBridgeEA.mq5:3996-4015`).
- **Slippage Control:** Enforces maximum deviation in points (`InpMaxDeviation` / `max_slippage_points = 15`).
- **Execution Retry Loop:** Implements 3-attempt transient retry loop with 150ms backoff for transient broker retcodes (10004 REQUOTE, 10021 PRICE_CHANGED, 10031 TIMEOUT).
- **Post-Fill Reconciliation:** If an order execution times out over TCP, `OrderManager` queries MT5 position and order books to verify if the ticket was filled before reporting an error, preventing duplicate order placement.

---

## 8. Emergency Risk Management & Fail-Safe Systems

1. **Software Kill Switch (`KILL_SWITCH` action)**:
   - Activated via Telegram (`/killswitch`), Desktop Companion GUI, or Cloud Agent.
   - Immediately closes all open market positions, cancels all pending orders, and sets `g_risk_halted = true` in MQL5.
2. **Watchdog Heartbeat Monitor**:
   - `PythonBridgeEA.mq5` expects a heartbeat ping from the Python engine every 15–30 seconds.
   - If no heartbeat is received for 30 seconds (`InpWatchdogTimeoutSec`), the EA transitions to `g_watchdog_halted = true` and rejects all incoming trade orders.
3. **Supervisor Process Watchdog**:
   - `scripts/supervisor.py` monitors child process PIDs and TCP port health. If the trading engine or bridge crashes, restarts it with exponential backoff (2s -> 60s).
4. **Terminal Crash & Restart Recovery**:
   - Native EA persists position state (initial SL points, strategy mode, BE status, partial TP status) in MT5 terminal `GlobalVariableSet` (`SMC_INITSL_<ticket>`, `SMC_MODE_<ticket>`).
   - If the MT5 terminal or Python process restarts, all positions are re-synchronized with their preserved state.

---
**Audit Verification:** All risk formulas, circuit breakers, and lot sizing logic forensicly verified against repository implementation.
