# MT5 001 — Risk Management Scoring, Gap Analysis & Improvement Roadmap
**Forensic Technical Intelligence Audit**  
**Classification:** Quantitative Systems Assessment & Technical Maturity Audit  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Principal Quantitative Trading Systems Architect & Financial Systems Auditor  
**Date of Audit:** November 2026  

---

## 1. Quantitative Risk Management Scoring (0–10 Institutional Scale)

Each category is evaluated on a strict institutional benchmark (0 = Non-existent / Dangerous; 5 = Basic Retail; 8 = Institutional Grade; 10 = Tier-1 Hedge Fund Benchmark). A control receives a high score **only if it is genuinely implemented, wired into the execution path, and actively enforced**.

| # | Risk Management Domain | Score (0-10) | Forensic Evidence | Missing Controls / Vulnerabilities | Severity |
| :---: | :--- | :---: | :--- | :--- | :---: |
| **1** | **Account Protection** | **8.5 / 10** | Minimum-of-balance-and-equity baseline (`min(bal, eq)`), $5.00 operating capital floor, automatic Cent-account conversion, and hard tier limits. | Relies on periodic 5-cycle polling to sync balance; rapid market swings between syncs could execute on slightly stale balance. | Low |
| **2** | **Position Sizing** | **9.0 / 10** | Tick-value and contract-spec lot sizing (`position_sizing.py`), strict step quantization rounding down (`MathFloor`), dynamic small-account lot caps. Rule R9 hard 2.0% cap. | Micro-accounts (<$25) cannot trade wide stops without explicitly bypassing R9 rules, creating an all-or-nothing trade block. | Low |
| **3** | **Stop-Loss Enforcement** | **9.5 / 10** | Zero unprotected trades allowed (`SL <= 0` strictly rejected). Rule R9.3 anti-widening policy enforced across all order modification APIs. | Stop-loss is placed at the broker, but during extreme illiquidity or weekend gaps, slippage can exceed the specified SL price. | Medium |
| **4** | **Take-Profit Management** | **8.5 / 10** | Mandatory minimum R:R calculated on monetary net gain vs. net loss. Multi-stage $5+ net profit floor locking, break-even + buffer, partial 50% TP, and ATR trailing. | TP distance is fixed at order entry; dynamic target expansion on strong momentum is partially heuristic. | Low |
| **5** | **Daily Loss Protection** | **8.5 / 10** | Daily starting equity calibration, realized loss accumulator, and hard circuit breaker triggered at configured threshold (2%–4%). | Daily loss accumulator counts realized PnL from closed trades; floating open trade drawdown is handled by separate safety buffer. | Medium |
| **6** | **Drawdown Protection** | **8.0 / 10** | Multi-mode drawdown support (STATIC, TRAILING from peak equity, DAILY). 80% safety buffer halts new entries before hard limit is touched. | Peak equity is tracked in memory and persisted, but an ungraceful crash between deal updates could reset peak equity to current balance. | Medium |
| **7** | **Portfolio Exposure** | **7.5 / 10** | Maximum simultaneous position caps (3–5 positions) and aggregate open risk cap (1.5%–3.0% of equity). | Does not run real-time portfolio covariance matrix optimization or marginal VaR allocation before entry. | Medium |
| **8** | **Correlation Management** | **6.5 / 10** | Categorizes symbols into 5 coarse correlation groups (METALS, CRYPTO, EUR_GBP, USD_MAJORS, INDICES). Prohibits duplicate directional exposure in PROP mode. | Coarse static grouping; does not compute rolling statistical correlation matrices or dynamic PCA concentration. | Medium |
| **9** | **Execution Risk Control** | **8.5 / 10** | Live spread-to-SL ratio filter (35% cap), broker filling mode auto-detection (IOC/FOK/RETURN), 15-point slippage cap, 3-attempt retry loop, post-timeout reconciliation. | Network timeouts over localhost TCP are set to 2.0s, which can cause transient retries on busy CPUs. | Low |
| **10**| **Emergency Controls** | **9.0 / 10** | Telegram `/killswitch`, Companion UI Kill Switch, 30s EA heartbeat watchdog, MQL5 GlobalVariables state persistence, supervisor process watchdog. | Kill switch closes market positions and cancels pending orders, but does not revoke broker API credentials. | Low |
| **11**| **Market Condition Filtering**| **8.0 / 10** | Regime detection (EMA fan, ATR expansion ratio), Wilder RSI anti-chasing, tick-volume breakout validation. Setup Quality Gate G1-G8. | News filter is implemented but disabled by default in continuous scalping mode, leaving the bot exposed to high-impact economic spikes. | **HIGH** |
| **12**| **Strategy Validation** | **8.5 / 10** | Setup Quality Gate G1-G8, Bailey & Lopez de Prado Deflated Sharpe Ratio (DSR), CSCV Probability of Backtest Overfitting (PBO), 5,000 Monte Carlo sims. | In-sample to out-of-sample edge on legacy SMC was negative until Phase 4 ablation promoted specific gates. | Medium |
| **13**| **Trade Monitoring & Decay**| **8.5 / 10** | Real-time CUSUM sequential test on rolling R-multiples, alerting at 2.0$\sigma$, reducing risk at 2.5$\sigma$, and halting at 3.0$\sigma$. TCA execution latency audit. | CUSUM requires at least 15–20 closed trades to build statistical power, leaving early-sequence decay undetected. | Low |
| **14**| **Operational Reliability** | **8.5 / 10** | Windows Named Mutex, `SO_EXCLUSIVEADDRUSE` socket binding, single-instance file locks, rotating 5MB logs, clean SIGTERM shutdown handlers. | Desktop Companion (Electron) spawns Python scripts as child processes; if Electron is forcefully killed via Task Manager, orphaned children can linger. | Medium |
| **15**| **Recovery & Fault Tolerance**| **8.0 / 10** | Automatic recovery after 30-minute consecutive loss pause; supervisor auto-restarts crashed engines; MQL5 recovers position tags from GlobalVariables. | If MT5 terminal itself hangs without crashing, the supervisor's process check still sees `terminal64.exe` alive and will not force-restart it. | Medium |

### Overall Technical Maturity Score: **8.3 / 10 (Institutional Grade)**

---

## 2. Forensic Gap Analysis: Disconnected & Incomplete Modules

### Gap 1: Disconnection of the 28-Video AlgoVistra Engine
- **Finding:** The repository contains a massive, 23-module strategy pipeline (`src/engine/pipeline.py` and `src/engine/skills/*`) implementing advanced concepts from the AlgoVistra and Art of Trading curricula (e.g. `protected_swing_marker`, `range_liquidity_loop`, `ifvg_inversion`, `inducement_ob_entry`, `five_check_model`).
- **Operational Reality:** This pipeline is **not wired into the live production trading orchestrator** (`src/core/orchestrator.py`). It is only executed in backtest scripts and manual trade assessor tools.
- **Risk:** An operator reading the codebase or documentation might falsely assume these 23 institutional models govern live trade execution, when live trading actually runs the fast `ContinuousScalpingEngine` and legacy `SmcStrategyEngine`.

### Gap 2: News Blackout Filter Disabled in Continuous Scalping
- **Finding:** `src/core/news_filter.py` contains a working economic news filter. However, in `config/strategy_config.json:12` and `mql5/Experts/PythonBridgeEA.mq5:132`, the news filter is explicitly hard-toggled to `OFF`:
  `"news_filter_enabled": false`, `"InpNewsFilterEnabled = false"`.
- **Operational Reality:** The bot operates continuously straight through high-impact FOMC, NFP, and CPI releases.
- **Risk:** High-impact economic news causes extreme slippage, massive spread widening (which triggers the 35% spread rejection, but only after entry if a trade is already open), and severe whipsaws that can blow through stop losses.

### Gap 3: Orphaned SMT & BPR Helper Primitives
- **Finding:** `src/smc/smt.py` (SMT Divergence Engine) and `src/smc/bpr_ifvg_helpers.py` (Balanced Price Range & Unicorn zones) exist in the source tree. `config/strategy_config.json` contains flags (`enable_smt_mss_ifvg: true`, `enable_unicorn: true`).
- **Operational Reality:** Neither `smt.py` nor the BPR helper functions are imported or called in `orchestrator.py` or `strategy_engine.py`.
- **Risk:** Misleading configuration flags that create false confidence in intermarket divergence protection that does not actually execute.

### Gap 4: Empirical Backtest Edge Deficit on Raw SMC
- **Finding:** As documented in `reports/validation_report.md`, raw SMC without Setup Quality Gate enforcement showed **negative out-of-sample expectancy** on major pairs:
  - EURUSD.m: -0.042 R (Win rate 28.6%, Profit Factor 0.93).
  - XAUUSD.m: +0.089 R (Win rate 31.4%, Profit Factor 1.13, PBO 71.4%).
  - Monte Carlo ruin probability on a $5 starting account was **92% - 96%**.
- **Operational Reality:** Only when the Phase 4 Setup Quality Gate was enforced (`reports/smc_rulebook_phase4_validation.md`) did OOS expectancy rise to `+0.628 R` with a Profit Factor of `2.17`.
- **Risk:** If an operator disables the Setup Quality Gate (`gate_mode: OFF`), the bot immediately reverts to negative expected value.

---

## 3. Potential Failure Scenarios & Stress Points

1. **Weekend & Holiday Gap Risk**:
   - *Scenario:* A position is held over the weekend despite Friday close settings, or an unexpected geopolitical event occurs over Sunday market open.
   - *Impact:* Price opens 100 pips beyond the Stop Loss. The broker fills at the opening market price, causing realized loss to substantially exceed the 2.0% risk cap.
2. **Terminal Freezing Without Process Termination**:
   - *Scenario:* MetaTrader 5 UI freezes due to a corrupt chart history file or memory leak, but `terminal64.exe` remains listed in Task Manager.
   - *Impact:* `scripts/supervisor.py` sees the process alive, but socket heartbeats fail. The native EA's internal watchdog halts execution after 30s, leaving open positions unmanaged by Python.
3. **Execution Latency Spikes on Micro VPS**:
   - *Scenario:* Running MT5, Python engine, Electron companion, and Postgres/SQLite on a low-spec single-core VPS.
   - *Impact:* CPU spikes cause TCP socket timeouts (>2.0s). Order Manager initiates recovery queries, delaying fills and causing slippage.

---

## 4. Prioritized Engineering Improvement Roadmap

```
┌────────────────────────────────────────────────────────────────────────┐
│                      ENGINEERING ROADMAP PHASES                        │
├───────────────┬───────────────────────────────────┬────────────────────┤
│ Priority      │ Recommended Architecture Upgrade  │ Expected Impact    │
├───────────────┼───────────────────────────────────┼────────────────────┤
│ **PHASE 1**   │ Re-enable Live Economic News      │ Eliminates spread  │
│ (Immediate)   │ Filter on High-Impact Releases    │ blowouts during    │
│               │ (CPI, NFP, FOMC Blackout Windows) │ NFP/FOMC events.   │
├───────────────┼───────────────────────────────────┼────────────────────┤
│ **PHASE 2**   │ Wire AlgoVistra 28-Video Pipeline │ Unlocks advanced   │
│ (High)        │ Directly into Orchestrator        │ institutional entry│
│               │ (Replace legacy fallback engine)  │ models live.       │
├───────────────┼───────────────────────────────────┼────────────────────┤
│ **PHASE 3**   │ Dynamic Rolling Correlation       │ Prevents clustered │
│ (Medium)      │ Matrix & Portfolio Covariance     │ drawdowns across   │
│               │ (Replace static symbol groups)    │ correlated majors. │
├───────────────┼───────────────────────────────────┼────────────────────┤
│ **PHASE 4**   │ Active Health Socket Ping in      │ Eliminates frozen  │
│ (Medium)      │ Supervisor (Not just PID check)   │ terminal unmanaged │
│               │                                   │ zombie states.     │
├───────────────┼───────────────────────────────────┼────────────────────┤
│ **PHASE 5**   │ Connect SMT Divergence Engine     │ Filters false      │
│ (Low/Research)│ to Live Multi-Symbol Stream       │ breakout traps via │
│               │ (EURUSD vs GBPUSD / DXY)          │ correlated assets. │
└───────────────┴───────────────────────────────────┴────────────────────┘
```

---
**Audit Verification:** All scores, failure modes, and technical gaps forensicly derived from codebase execution analysis.
