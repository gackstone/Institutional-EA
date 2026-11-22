# Institutional EA Adaptive Trading Intelligence (ATI) — Architecture & Operating Manual

## 1. System Overview

The **Adaptive Trading Intelligence (ATI)** subsystem transforms Institutional EA into a self-auditing, continuously learning, and experimentally self-improving algorithmic trading platform. 

ATI operates as a non-invasive, consultative intelligence layer alongside the active trading engine.

```
+--------------------------------------------------------------------------------------------------+
|                                    Institutional EA ENGINE / ORCHESTRATOR                                |
|                                                                                                  |
|   +--------------------+     +---------------------+     +-----------------------------------+   |
|   |   Live MT5 / EA    | <-> | TradingBot          | <-> | Risk & Order Execution Engine     |   |
|   |   Terminal         |     | Orchestrator        |     | (Mandatory SL, Lot Sizing, R9)    |   |
|   +--------------------+     +---------------------+     +-----------------------------------+   |
+-----------------------------------------|--------------------------------------------------------+
                                          | Non-blocking Context & Sync
                                          v
+--------------------------------------------------------------------------------------------------+
|                            ADAPTIVE TRADING INTELLIGENCE (src/intelligence)                      |
|                                                                                                  |
|   +--------------------+     +--------------------+     +------------------------------------+   |
|   | MT5 Trade Historian| --> | Autonomous Auditor | --> | AI Pattern Recognition & Learning  |   |
|   | (Idempotent Deals) |     | (Forensic Quality) |     | (Chronological Calibrated Models)  |   |
|   +--------------------+     +--------------------+     +------------------------------------+   |
|             |                          |                                  |                      |
|             v                          v                                  v                      |
|   +--------------------+     +--------------------+     +------------------------------------+   |
|   | Adaptive Market    |     | Strategy Lab &     |     | Controlled Self-Improvement        |   |
|   | Regime Profiler    |     | Counterfactuals    |     | Controller & Rollback Snapshots    |   |
|   +--------------------+     +--------------------+     +------------------------------------+   |
|                                        |                                                         |
|                                        v                                                         |
|                       +-----------------------------------+                                      |
|                       | SQLite Persistence (WAL Mode)     |                                      |
|                       | data/ati_intelligence.db          |                                      |
|                       +-----------------------------------+                                      |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Core Subsystem Modules

### 2.1 Intelligent Trade Historian (`src/intelligence/historian/`)
- **Authoritative Source**: Pulls directly from MT5 executed deals (`history_deals_get`).
- **Idempotency**: Broker deal tickets are stored with unique primary keys in SQLite (`ati_broker_deals`). Duplicate deals are ignored (`INSERT OR IGNORE`).
- **Position Lifecycle Reconciler**: Pairs `ENTRY_IN` and `ENTRY_OUT` deals by `position_id`. Accurately handles partial closes and calculates weighted entry/exit prices, gross profit, commissions, swaps, fees, and true net profit.
- **Account Normalization**: Identifies cent accounts (USDC, 100x factor), micro accounts, and standard accounts. Converts all financial metrics to normalized USD amounts.
- **Symbol Whitelist Hard Enforcement**: Exclusively permits `XAUUSD`, `BTCUSD`, and `USDJPY` (plus broker suffixes like `.c`, `.m`, `.raw`). Rejects all unapproved symbols.

### 2.2 Autonomous Trade Auditor (`src/intelligence/auditor/`)
- Investigates every closed position across 4 forensic dimensions:
  1. **Entry Quality**: Spread at entry, momentum (ADX), volatility (ATR), regime alignment.
  2. **Exit Quality**: Stop loss behavior, take profit attainment, trailing stops, early termination.
  3. **Execution Quality**: Slippage, cost drag (commission + swap vs gross profit), partial fills.
  4. **Risk Quality**: Stop loss presence (enforces R9 mandatory non-zero SL), sizing.
- Classifies trade outcomes into structured categories:
  - `NORMAL_STATISTICAL_LOSS`: Normal trade within strategy risk boundaries.
  - `STRATEGY_FAILURE`: Systematic breakdown under unfavorable market conditions.
  - `ENTRY_TIMING_FAILURE`: Poor entry momentum or late execution.
  - `EXIT_OPTIMIZATION_OPPORTUNITY`: Premature profit closure or trailing stop giveback.
  - `EXECUTION_FAILURE`: Severe broker slippage or latency.
  - `SPREAD_OR_COST_ISSUE`: Excessive commission or wide spread drag.
  - `RISK_POLICY_VIOLATION`: Position opened without mandatory initial stop loss.
  - `MARKET_REGIME_MISMATCH`: Strategy triggered in unsuited market state.

### 2.3 AI Pattern Recognition & Learning (`src/intelligence/learning/`)
- **Temporal Datasets**: Sorts trades strictly chronologically. Prevents lookahead bias and future-to-past data leakage.
- **Feature Extraction**: Indicator values at original decision timestamp (RSI, ADX, ATR, spread, session, direction, hour, day).
- **Calibrated Classifier**: Pure NumPy calibrated logistic classification with L2 regularization and Brier score calibration tracking.
- **Observation Mode Safeguard**: Safely operates in observation-only mode if sample volume is under 15 trades.

### 2.4 Adaptive Market Regime Intelligence (`src/intelligence/regime/`)
- Classifies market into objective states: `STRONG_BULLISH`, `STRONG_BEARISH`, `SIDEWAYS_CONSOLIDATION`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `UNSTABLE_SPREAD`.
- Segments win rates and net profits by regime to identify strategy strengths and weaknesses.

### 2.5 Strategy Optimization Laboratory (`src/intelligence/laboratory/`)
- **Historical Backtesting**: Models candidate parameter filters with simulated transaction costs, commission, and slippage.
- **Walk-Forward Validation**: In-sample training (70%) and out-of-sample validation (30%).
- **Counterfactual Trade Analysis**: Simulates "what if" scenarios (e.g. tighter spread filter, profit floor lock) while strictly distinguishing actual from simulated results.

### 2.6 Controlled Self-Improvement Controller (`src/intelligence/improvement/`)
- **Promotion Lifecycle**:
  `OBSERVE -> AUDIT -> IDENTIFY -> CANDIDATE -> BACKTEST -> WALK-FORWARD -> OUT-OF-SAMPLE -> SHADOW TEST -> APPROVAL -> CONTROLLED DEPLOYMENT -> MONITOR -> ROLLBACK`.
- **Parameter Allowlist**: Allows adaptation only for explicitly allowlisted, bounded parameters (`max_spread_pts`, `min_confluence_score`, `min_risk_reward_ratio`, etc.).
- **Forbidden Parameters**: Prohibits touching risk limits, stop loss requirements, live trading locks, or approved symbols.
- **Instant Rollback**: Automatically creates snapshots before any configuration deployment; can revert in one command.

### 2.7 AI Performance Monitoring & Reporting (`src/intelligence/monitoring/`)
- **Drift Monitor**: Flags consecutive loss clusters (>= 5 losses) and win rate degradation (> 25% drop). Triggers model recalibration fallback.
- **Automated Reporter**: Generates Daily and Weekly intelligence reports in JSON and Markdown, clearly categorizing `ACTUAL_RESULTS`, `SIMULATED_RESULTS`, `MODEL_PREDICTIONS`, and `AI_RECOMMENDATIONS`.

---

## 3. Configuration & Operating Modes

Located in `config/ati_config.json`:

```json
{
  "ati": {
    "enabled": true,
    "mode": "OBSERVATION",
    "auto_training": true,
    "auto_experimentation": true,
    "auto_promotion": false,
    "autonomous_code_changes": false,
    "shadow_testing": true,
    "trade_auditing": true,
    "pattern_discovery": true,
    "market_regime_detection": true,
    "execution_analysis": true,
    "counterfactual_analysis": true,
    "model_monitoring": true,
    "rollback_enabled": true,
    "approved_symbols": ["XAUUSD", "BTCUSD", "USDJPY"]
  }
}
```

### Supported Operating Modes:
1. `OBSERVATION` (Default): Collects deals, reconciles positions, conducts trade audits, logs findings.
2. `LEARNING`: Trains pattern models in background without affecting live decision logic.
3. `EXPERIMENTATION`: Runs laboratory backtests and walk-forward evaluations.
4. `SHADOW`: Evaluates candidate configurations in parallel without submitting candidate orders.
5. `APPROVAL`: Holds validated improvements awaiting operator signature.
6. `CONTROLLED_ADAPTATION`: Deploys explicitly approved allowlisted parameters.
7. `DISABLED`: Disables ATI completely.

---

## 4. Companion Control Service API Endpoints

The Local Control Service (`companion/service/api/server.py`) exposes authenticated endpoints on `http://127.0.0.1:8765`:

- `GET /api/ati/status` — Operating status, win rate, net profit, drift status.
- `GET /api/ati/audits` — List of forensic trade audits with issues and recommendations.
- `GET /api/ati/candidates` — Registered strategy improvement candidates and validation metrics.
- `GET /api/ati/execution` — Execution quality metrics (average slippage, cost drag ratio, rejections).
- `GET /api/ati/reports/daily` — Latest daily intelligence report.
- `GET /api/ati/reports/weekly` — Latest weekly intelligence report.
- `POST /api/ati/sync` — Triggers immediate incremental MT5 history synchronization.
- `POST /api/ati/audit-all` — Triggers audit of all unaudited positions.
- `POST /api/ati/train` — Triggers temporal model training.
- `POST /api/ati/approve` — Applies authorized operator approval to a candidate (`{"candidate_id": "...", "operator": "..."}`).
- `POST /api/ati/rollback` — Instantly rolls back active configuration (`{"reason": "..."}`).
