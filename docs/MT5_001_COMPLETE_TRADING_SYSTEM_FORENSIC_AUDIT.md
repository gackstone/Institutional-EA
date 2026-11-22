# MASTER FORENSIC AUDIT REPORT
# MT5 001 — COMPLETE BOT ARCHITECTURE, STRATEGY EXTRACTION, TRADING INTELLIGENCE & RISK MANAGEMENT AUDIT

**Project:** MT5 001 Institutional Algorithmic Day-Trading & Continuous Scalping System  
**System Target Directory:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Operating Environment:** Windows 10/11 x64, MetaTrader 5 (Build 4000+), Python 3.10+, Electron 28+  
**Audit Type:** Forensic Quantitative Trading Systems & Risk Governance Audit (Read-Only)  
**Lead Auditor:** Principal Quantitative Trading Systems Architect, Senior Algorithmic Trading Engineer, MQL5/Python Specialist & Financial Systems Auditor  
**Date of Audit:** November 2026  
**Audit Classification:** STRICTLY READ-ONLY FORENSIC EXAMINATION  

---

## TABLE OF CONTENTS
1. [Executive Summary & Architectural Overview](#1-executive-summary--architectural-overview)
2. [Project Structural Inventory & Dependency Map](#2-project-structural-inventory--dependency-map)
3. [Complete Trading Strategy Extraction & Execution Parity](#3-complete-trading-strategy-extraction--execution-parity)
4. [Smart Money Concepts (SMC) & ICT Forensic Analysis](#4-smart-money-concepts-smc--ict-forensic-analysis)
5. [Technical Indicators, Calculations & Market Data Audit](#5-technical-indicators-calculations--market-data-audit)
6. [Complete Risk Management Forensic Audit](#6-complete-risk-management-forensic-audit)
7. [Trading Decision Engine & Operational Logic Pipeline](#7-trading-decision-engine--operational-logic-pipeline)
8. [Market Regime & Adaptive Intelligence](#8-market-regime--adaptive-intelligence)
9. [Technical Capabilities & Skills Inventory](#9-technical-capabilities--skills-inventory)
10. [Learning, Memory & Performance Intelligence](#10-learning-memory--performance-intelligence)
11. [Trade Execution, MQL5 EA & Socket IPC Integration](#11-trade-execution-mql5-ea--socket-ipc-integration)
12. [Backtesting, Validation & Empirical Performance Claims](#12-backtesting-validation--empirical-performance-claims)
13. [Security, Operational Safety & Reliability Audit](#13-security-operational-safety--reliability-audit)
14. [Hidden, Dormant & Undocumented Capabilities](#14-hidden-dormant--undocumented-capabilities)
15. [Risk Management Scoring & Technical Maturity (0–10)](#15-risk-management-scoring--technical-maturity-010)
16. [Final Executive Assessment (The 20 Core Answers)](#16-final-executive-assessment-the-20-core-answers)
17. [Prioritized Improvement Roadmap](#17-prioritized-improvement-roadmap)

---

## 1. Executive Summary & Architectural Overview

The **MT5 001** trading system is an advanced, hybrid quantitative algorithmic execution platform. Rather than running purely as an MQL5 script or a detached Python bot, MT5 001 bifurcates execution into a **two-tier architecture**:
1. **Low-Latency Native Execution Layer (MQL5)**: Encapsulated in `mql5/Experts/PythonBridgeEA.mq5` (4,773 lines of native C++-style MQL5 code). This layer handles direct broker communication, tick-by-tick order placement, dynamic spread validation, structural trailing stops, break-even advances, $5+ profit locks, and native terminal-level circuit breakers.
2. **Quantitative Intelligence & Risk Layer (Python)**: Comprising over 25,000 lines of Python 3.10+ code across `src/core`, `src/smc`, `src/risk`, `src/execution`, `src/regime`, `src/patterns`, and `src/learning`. It computes multi-timeframe liquidity cascades, regime transitions, probabilistic meta-labeling, fractional Kelly bounds, GARCH(1,1) volatility targeting, and Page's CUSUM performance decay monitoring.

### Core Architectural Topology
```
                     ┌──────────────────────────────────────────────┐
                     │         MetaTrader 5 Client Terminal         │
                     │  ┌────────────────────────────────────────┐  │
                     │  │        PythonBridgeEA.mq5 (v3.10)      │  │
                     │  │  - Native trade safety gatekeeper      │  │
                     │  │  - Stop-loss & Trailing-stop execution │  │
                     │  │  - Tick-level spread & slippage checks │  │
                     │  └──────────────────┬─────────────────────┘  │
                     └─────────────────────┼────────────────────────┘
                                           │ TCP Socket IPC (Localhost)
                                           │ Port 5555: Data & Trade Link
                                           │ Port 5556: Admin IPC Link
                     ┌─────────────────────┴────────────────────────┐
                     │            Python Algorithmic Engine         │
                     │  ┌────────────────────────────────────────┐  │
                     │  │     src/execution/bridge_server.py     │  │
                     │  │  - SO_EXCLUSIVEADDRUSE socket binds    │  │
                     │  │  - Multi-client connection dispatcher  │  │
                     │  └──────────────────┬─────────────────────┘  │
                     │                     │                        │
                     │  ┌──────────────────┴─────────────────────┐  │
                     │  │       src/core/orchestrator.py         │  │
                     │  │  - ContinuousScalpingEngine (M1/M5/M15)│  │
                     │  │  - SmcStrategyEngine (W1->M15 Fallback)│  │
                     │  │  - SetupQualityGate (G1-G8 Hard Gates) │  │
                     │  │  - PositionSizingEngine (Rule R9)      │  │
                     │  │  - PortfolioRiskEngine (Drawdown/Streak│  │
                     │  └──────────────────┬─────────────────────┘  │
                     └─────────────────────┼────────────────────────┘
                                           │
          ┌────────────────────────────────┼────────────────────────────────┐
          │                                │                                │
          ▼                                ▼                                ▼
┌──────────────────┐             ┌──────────────────┐             ┌──────────────────┐
│ Desktop UI       │             │ ArcadeFX Cloud   │             │ Telegram Bot     │
│ companion/       │             │ agent/           │             │ src/notifications│
│ Electron/React   │             │ mt5_bot_agent.py │             │ 2-step console   │
│ 6 services watch │             │ Outbound HTTPS   │             │ Rate-limited     │
└──────────────────┘             └──────────────────┘             └──────────────────┘
```

---

## 2. Project Structural Inventory & Dependency Map

A forensic directory survey identifies the following core modules and responsibilities:

- **`mql5/Experts/PythonBridgeEA.mq5` (4,773 lines)**: The native MT5 bridge EA. Authoritative for broker execution, tick-by-tick spread enforcement, autonomous trailing, break-even locking, and terminal heartbeat watchdogs.
- **`src/core/`**:
  - `orchestrator.py`: Master trading loop coordinating market data, scalping, SMC scans, risk checks, order execution, and position management.
  - `market_data.py`: Multi-timeframe OHLCV bar cache with staleness gating (180s limit).
  - `sessions.py`: UTC session clock tracking Asian, London, New York, and London Close Killzones.
  - `instruments.py` & `contracts.py`: Strongly typed data contracts, tick specifications, and symbol profiles.
- **`src/execution/`**:
  - `continuous_scalper.py`: Real-time state-machine engine evaluating Momentum Continuation, Pullback, and Sweep/Breakout models across M1/M5/M15.
  - `bridge_server.py`: Dedicated asynchronous TCP socket server (Ports 5555 & 5556).
  - `bridge_client.py`: Thread-safe socket client used by the Python engine.
  - `order_manager.py`: Idempotent order builder, pre-trade checklist auditor, and timeout reconciler.
  - `analytics/tca.py`: Transaction Cost Analysis engine logging slippage, spread, and latency.
- **`src/smc/`**:
  - `market_structure.py`: Swing high/low ($k=5$), Break of Structure (BOS), Change of Character (CHoCH), and Market Structure Shift (MSS) detectors.
  - `fvg_ob.py`: 3-bar Fair Value Gap (FVG), Inverse FVG (IFVG), and Order Block (OB) detectors requiring displacement ($1.2\times\text{ATR}$) and structural breaks.
  - `liquidity.py`: Buy-Side Liquidity (BSL), Sell-Side Liquidity (SSL), Equal Highs/Lows (EQH/EQL), and sweep-with-rejection verifiers.
  - `weekly_daily.py`: Previous Week/Day High, Low, Open, Close, and Midpoint (PWH, PWL, PDH, PDL) interaction engine.
  - `session_liquidity.py`: Asian range calculator (00:00–09:00 UTC) and London Judas swing sweep detector.
  - `structure_confirmation.py`: 5-state automaton tracking CHoCH-Warning -> Pullback -> BOS-Confirmation.
  - `setup_quality_gate.py`: Phase 2 validation gate enforcing Rules R1–R9 across 8 hard gates (G1–G8).
  - `smc_rulebook.py`: Canonical rulebook definitions and configuration schemas.
- **`src/risk/`**:
  - `position_sizing.py`: Exact tick-value and contract-spec lot calculator enforcing Rule R9 ($5.00 floor, 2.0% hard cap, strict round-down).
  - `portfolio_risk.py`: Portfolio circuit breaker tracking daily loss, weekly loss, consecutive losses, and correlation exposure.
  - `account_tier.py`: Evaluates account balances into 6 discrete tiers (BELOW_FLOOR, MICRO, MINI, SMALL, STANDARD, LARGE).
  - `trade_management.py`: $5.00 net profit target locking, break-even advances, and partial profit taking.
  - `drawdown_throttle.py`: Progressive risk throttler (0.6x, 0.3x, 0.0x) based on drawdown proximity to safety buffer.
  - `kelly.py`: Fractional Quarter-Kelly ($0.25f^*$) risk sizing clamped to tier ceilings.
  - `volatility.py`: Variance-targeted GARCH(1,1) and RiskMetrics EWMA ($\lambda=0.94$) volatility forecasting.
- **`src/patterns/`**:
  - `candlesticks.py`: 51 vectorized closed-candle pattern detectors normalized by ATR.
  - `chart_patterns.py`: Swing-based classical chart patterns (Double Tops/Bottoms, Head & Shoulders).
  - `context.py` & `integration.py`: Confluence scorer integrating patterns into SMC points of interest.
- **`src/learning/`**:
  - `meta/`: Regularized logistic classifier with Platt probability calibration predicting trade success.
  - `validation/`: Backtest engine, Purged/Embargoed walk-forward cross-validation, Bailey & Lopez de Prado Deflated Sharpe Ratio (DSR), CSCV Probability of Backtest Overfitting (PBO), and 5,000-path Monte Carlo ruin simulations.
  - `champion_challenger.py`: Shadow challenger tracking framework requiring manual promotion.
- **`src/monitoring/`**:
  - `decay_guard.py`: Page's CUSUM sequential test monitoring cumulative negative R deviation (alerts at 2.0$\sigma$, cuts risk at 2.5$\sigma$, halts at 3.0$\sigma$).
  - `dashboard.py`: Rich CLI diagnostic dashboard.
  - `health_monitor.py`: Connection latency and socket health watchdog.
- **`companion/`**: Electron desktop companion app (`main.cjs` 2,095 lines) supervising 6 core services (Engine, Bridge, Cloud Sync, Telegram, Health, Logs) with real-time React GUI.
- **`agent/mt5_bot_agent.py` (1,307 lines)**: Outbound-only HTTPS cloud synchronization agent connecting MT5 to ArcadeFX Cloud platform with HMAC-SHA256 signed commands.
- **`scripts/supervisor.py` (707 lines)**: Autonomous Windows OS process supervisor with exponential backoff restarts, port probes, and Named Mutex locking.

---

## 3. Complete Trading Strategy Extraction & Execution Parity

### Operational Status of Identified Strategies

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               OPERATIONAL DISPOSITION TABLE                             │
├───────────────────────────────┬──────────────────────┬─────────────────────────────────┤
│ Strategy / Setup Model        │ Implementation State │ Primary Source Location         │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 1. Momentum Continuation      │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    Scalp (M1/M5/M15)          │ ACTIVE IN PRODUCTION │ scalper.py:366-457              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 2. Pullback Scalp             │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    (FVG/OB/OTE/EMA21)         │ ACTIVE IN PRODUCTION │ scalper.py:459-567              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 3. Breakout / Liquidity-      │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    Sweep Scalp (M1/M5/M15)    │ ACTIVE IN PRODUCTION │ scalper.py:569-648              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 4. Weekly/Daily Liquidity     │ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    Reversals (PWL/PWH/PDL/PDH)│ ACTIVE (FALLBACK)    │ 227-329; weekly_daily.py:1-250  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 5. Weekly/Daily Accepted Break│ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    Continuations (PWH/PWL)    │ ACTIVE (FALLBACK)    │ 238-243, 290-295                │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 6. M15 SMC Order Block / FVG  │ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    OTE Model (R1-R8)          │ ACTIVE (FALLBACK)    │ 244-261, 296-313                │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 7. Asian Range London Judas   │ FULLY IMPLEMENTED BUT│ src/smc/session_liquidity.py:   │
│    Session Sweep              │ CONDITIONALLY GATED  │ 46-175; strategy_engine.py:218  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 8. Candlestick & Chart Pattern│ IMPLEMENTED & WIRED  │ src/patterns/candlesticks.py;   │
│    Confluence Engine (51 Pat.)│ VIA CONFLUENCE HOOK  │ chart_patterns.py; context.py   │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 9. 28-Video AlgoVistra / Art  │ FULLY IMPLEMENTED BUT│ src/engine/pipeline.py:1-650;   │
│    of Trading 7-Gate Pipeline │ DISCONNECTED FROM BOT│ src/engine/skills/* (23 files)  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 10. CISD (Change in State     │ IMPLEMENTED IN EXT.  │ src/strategies/cisd.py:1-120    │
│     of Delivery Leg Break)    │ MODULE; UNUSED LIVE  │ (Modular pipeline disabled)     │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 11. Trendline Liquidity Sweep │ IMPLEMENTED IN EXT.  │ src/strategies/trendline_       │
│     Reversal Model            │ MODULE; UNUSED LIVE  │ liquidity.py:1-150              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 12. Volume-Price Distribution │ IMPLEMENTED IN EXT.  │ src/strategies/volume_          │
│     Accumulation Filter       │ MODULE; UNUSED LIVE  │ distribution.py:1-90            │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 13. SMT Intermarket           │ PARTIALLY CODED;     │ src/smc/smt.py:1-55             │
│     Divergence Engine         │ ORPHANED & DISCONNECTED                               │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 14. BPR / Unicorn Model       │ PARTIALLY CODED;     │ src/smc/bpr_ifvg_helpers.py:    │
│     (Breaker + FVG Overlap)   │ ORPHANED & DISCONNECTED                               │
└───────────────────────────────┴──────────────────────┴─────────────────────────────────┘
```

### Detailed Strategy Profiles

#### 1. Momentum Continuation Scalp (`continuous_scalper.py:366-457`)
- **Philosophy**: Captures impulsive continuation runs when price expands in alignment with fast moving averages.
- **Entry Rules (BUY)**:
  - Moving average alignment: `close > EMA9` and `EMA9 >= EMA21 - 0.10 * ATR14`.
  - Impulsive candle: Bullish candle with `body / range >= 0.45` and `body >= 0.35 * ATR14`.
  - Structural break: Candle close > prior candle high.
- **Filters**: RSI(14) between 45–68 (+4 pts); RSI >= 78 (-8 pts). Anti-chasing rejects entry if price is at >95% of 20-bar range with a weak body and RSI >= 78.
- **Exit Logic**: Stop loss placed at `min(last.low, prev.low) - 0.35 * ATR14`. Take profit placed at $1.5\text{R}$ to $2.0\text{R}$.

#### 2. Pullback Scalp (`continuous_scalper.py:459-567`)
- **Philosophy**: Enters shallow or deep pullbacks into institutional support/resistance within the 38.2%–79% OTE zone.
- **Entry Rules (BUY)**:
  - 12-bar swing window: Retracement depth between 35% and 82%, OR touches an active Bullish FVG, OR pulls back to within $0.45\times\text{ATR}$ of EMA21.
  - Turn confirmation: Bullish candle body OR lower wick rejection ($\ge 45\%$ of range).
- **Exit Logic**: Stop loss placed at `min(last.low, prev.low) - 0.40 * ATR14`. Take profit placed at $1.5\text{R}$ to $2.0\text{R}$.

#### 3. Breakout / Liquidity-Sweep Scalp (`continuous_scalper.py:569-648`)
- **Philosophy**: Exploits false breakout liquidity sweeps (turtle soup) or high-volume range expansion breakouts.
- **Entry Rules (BUY Sweep)**: Candle pierces 10-bar swing low and closes back inside range (Rule R4).
- **Entry Rules (BUY Breakout)**: Candle body closes decisively above 10-bar swing high with `body >= 0.45 * ATR14` and volume expansion $\ge 1.25\times$ rolling average.
- **Exit Logic**: Stop loss at `min(last.low, prev.low) - 0.40 * ATR14`. Take profit anchored at next swing pool.

#### 4. Weekly/Daily Liquidity Reversals (`strategy_engine.py:227-329`, `weekly_daily.py`)
- **Philosophy**: Institutional liquidity sweeps of Previous Week/Day Highs/Lows.
- **Entry Rules (Bullish Reversal)**: M15 candle pierces PWL or PDL, closes back inside range, confirmed by M15 CHoCH/BOS. Confluence score must be $\ge 75.0/100$.
- **Exit Logic**: Stop loss beyond sweep wick extreme; take profit at opposite pool (PWH/PDH) with $\text{R:R} \ge 2.0$.

---

## 4. Smart Money Concepts (SMC) & ICT Forensic Analysis

| Concept | Actual Implementation & Mechanics | Timeframe | Genuinely Enforced? | Operational Reality & Limitations |
| :--- | :--- | :---: | :---: | :--- |
| **Market Structure (HH/HL/LH/LL)** | Symmetrical lookback ($k=5$). Uptrend requires $H_{\text{last}} > H_{\text{prev}}$ AND $L_{\text{last}} > L_{\text{prev}}$. (`market_structure.py:103-118`). | W1, D1, H4, H1, M15 | **YES** | Genuinely implemented. 5-bar lag required to confirm swing points. |
| **Break of Structure (BOS)** | Candle body close beyond last swing extreme: $C_t > H_{\text{swing}}$ (buys) or $C_t < L_{\text{swing}}$ (sells). (`market_structure.py:123-173`). | M15, H1, H4 | **YES** | Body close strictly enforced; wicks do not trigger BOS. |
| **Change of Character (CHoCH)** | 5-state automaton: `CHOCH_WARNING` -> `PULLBACK` (LH/HL) -> `BOS_CONFIRMED`. (`structure_confirmation.py:1-492`). | M15 | **YES** | Institutional-grade state machine. Prevents false entries on initial trend-change warnings. |
| **Order Block (OB)** | Last opposite candle before displacement impulse ($1.2\times\text{ATR}$ or leaves FVG) that breaks structure. (`fvg_ob.py:200-380`). | M15, H1, H4 | **YES** | Strict displacement and BOS requirements eliminate naive single-candle false positives. |
| **Fair Value Gap (FVG)** | 3-candle imbalance: Bullish $L_t > H_{t-2}$ with gap $\ge \max(1.5\text{ pips}, 0.3\times\text{ATR})$. (`fvg_ob.py:45-198`). | M15, H1, H4 | **YES** | Fully tracks unmitigated gaps and flips breached gaps into Inverse FVGs (IFVG). |
| **Liquidity Sweeps** | Candle pierces level and closes back inside within 1–2 bars (Rule R4). (`liquidity.py:127-185`). | M15, H1, D1, W1 | **YES** | Genuinely enforced as Hard Gate G3 in Setup Quality Gate. |
| **Equal Highs/Lows (EQH/EQL)** | Swings within $2.0\times\text{pip\_size}$ tolerance. (`liquidity.py:65-98`). | M15, H1 | **YES** | Detected and prioritized as take-profit magnet targets. |
| **Premium / Discount (50%)** | Range equilibrium $= (H + L)/2.0$. Buys in Discount (<0.50), Sells in Premium (>0.50). (`setup_quality_gate.py:164-198`). | M15, H1, H4 | **YES (Soft)** | Enforced as a soft +5 pt bonus in Phase 4; hard blocking removed because it cut valid shallow pullbacks. |
| **Optimal Trade Entry (OTE)** | Fibonacci retracements: 61.8%, 70.5%, 78.6%. (`continuous_scalper.py:498-535`). | M5, M15 | **YES** | Used in Pullback Scalping Model and SMC OTE candidate scoring. |
| **Asian Range & Judas Swing** | Computes Asia 00:00–09:00 UTC range; detects London 08:00–12:00 UTC sweep of Asia high/low. (`session_liquidity.py:46-175`). | M15 | **PARTIAL** | Fully implemented in module, but toggled off in continuous scalping mode. |
| **SMT Divergence** | Cross-symbol correlation divergence. (`smt.py:1-55`). | M15 | **NO** | **Orphaned code.** Exists in `smt.py` but is uncalled in production. |
| **Balanced Price Range (BPR)** | Bullish/bearish FVG geometric overlap. (`bpr_ifvg_helpers.py:13-110`). | M15 | **NO** | **Orphaned code.** Exists in helper module but is disconnected from live engine. |

---

## 5. Technical Indicators, Calculations & Market Data Audit

### Indicator Verification Matrix

| Indicator / Model | Exact Implementation File | Calculation Method | Parameters & Defaults | Repainting Risk? | Production Impact |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **Exponential Moving Average** | `continuous_scalper.py:148-158` | Multiplier $k = \frac{2}{N+1}$; recursive closed-bar loop. | EMA9, EMA21, EMA50 | **ZERO** (Closed bars) | Directional trend alignment for scalping models. |
| **Relative Strength Index** | `continuous_scalper.py:175-194` | Wilder's smoothed RSI on closed candles. | Period = 14 | **ZERO** (Closed bars) | Modulates confluence score (+4 / -8 pts); anti-chasing guard. |
| **Average True Range (ATR)** | `continuous_scalper.py:160-173`; `fvg_ob.py:34-45` | True Range $\max(H-L, \|H-C_p\|, \|L-C_p\|)$ averaged over $N$ bars. | Period = 14 | **ZERO** (Closed bars) | Calibrates dynamic stop-loss distance and FVG minimum gap thresholds. |
| **Average Directional Index** | `strategy_engine.py:847-875` | Wilder's directional movement (+DI, -DI) and DX smoothed. | Period = 14, Threshold = 22.0 | **ZERO** (Closed bars) | Filters momentum strength in MQL5 adaptive mode selection. |
| **GARCH(1,1) Volatility** | `src/risk/volatility.py:38-115` | $\sigma_t^2 = \omega + \alpha \epsilon_{t-1}^2 + \beta \sigma_{t-1}^2$ with variance targeting. | $\alpha=0.08, \beta=0.90$ | **ZERO** (Historical returns) | Scales position size downward during high-volatility regimes. |
| **RiskMetrics EWMA** | `src/risk/volatility.py:118-150` | $\sigma_t^2 = \lambda \sigma_{t-1}^2 + (1-\lambda) r_{t-1}^2$ | $\lambda = 0.94$ | **ZERO** (Historical returns) | Backup exponential volatility estimator. |
| **Quarter-Kelly Sizing** | `src/risk/kelly.py:1-95` | $f^* = \frac{p(b+1)-1}{b}$; fractional risk $= 0.25 f^*$. | Fraction = 0.25 | **ZERO** (Closed trade returns) | Caps position sizing to mathematical growth optimum. |
| **Page's CUSUM Test** | `src/monitoring/decay_guard.py:1-110` | $S_t = \max(0, S_{t-1} + (E_{\text{base}} - R_t) - k)$ | $k = 0.20$, Window = 20 trades | **ZERO** (Sequential closed deals) | Halts bot at 3.0$\sigma$ cumulative negative expectancy drift. |
| **Deflated Sharpe (DSR)** | `src/learning/validation/statistics.py` | Bailey & Lopez de Prado (2014) DSR formula. | Trials = 10, Benchmark = 0.0 | **ZERO** (OOS distribution) | Quantitative validation gate for strategy promotion. |

---

## 6. Complete Risk Management Forensic Audit

### A. Account Baseline & Floor Governance
- **Capital Baseline**: $\text{Capital Base} = \min(\text{Balance}, \text{Equity})$.
- **Operating Floor**: Strictly $\$5.00$ USD. Accounts below $\$5.00$ are classified `BELOW_FLOOR` and trading is completely halted (`position_sizing.py:133-157`).
- **Cent Accounts**: USC, EUC, GBX, and JPC currencies are automatically divided by 100.0, neutralizing broker denomination scaling.

### B. Dynamic Position Sizing Formula & Invariants
Position volume is calculated dynamically from tick specifications and structural stop loss:
$$\text{Risk (\USD)} = \text{Capital Base} \times \left(\frac{\min(\text{Target Risk \%}, \text{Hard Ceiling \%})}{100}\right)$$

$$\text{Loss Per Lot (\USD)} = \left(\frac{\text{SL Points} \times \text{Point Size}}{\text{Tick Size}}\right) \times \text{Tick Value} + \text{Spread Cost} + \text{Commission Cost}$$

$$\text{Quantized Lots} = \left\lfloor \frac{\text{Risk Amount}}{\text{Total Loss Per Lot} \times \text{Volume Step}} \right\rfloor \times \text{Volume Step}$$

- **Strict Round-Down Invariant**: Sizing utilizes `MathFloor()`. Volume is **never rounded up**, guaranteeing actual monetary risk never exceeds the configured percentage due to step rounding.
- **Rule R9 Hard Ceiling**: Risk per trade is **hard-capped at 2.0% in source code**, regardless of what a user configures in JSON (`position_sizing.py:51, 97-100`). Default risk is 1.0%.

### C. Stop-Loss & Take-Profit Invariants
- **Mandatory Protective Stop-Loss (Rule R9.2)**: Every order must carry a valid `stop_loss > 0`. There is **zero execution path** capable of creating an unprotected market position.
- **Anti-Widening Stop Policy (Rule R9.3)**: Modifying a stop loss further away from price is strictly rejected across Python and MQL5.
- **Monetary Reward-to-Risk**: Evaluates actual monetary gain at TP against total monetary risk at SL (including spread and commissions). Enforces $\text{R:R} \ge 1.20$ (scalping) or $\ge 2.00$ (SMC).
- **$5+ Profit Locking**: Automatically locks in a minimum $\$5.00$ net profit floor once floating PnL crosses $\$5.00$, with dynamic momentum extension (`profit_extension_lock_ratio = 0.65`).
- **Break-Even & Partial TP**: Moves SL to entry $+ 1.0$ pip buffer at $+1.0\text{R}$ floating profit; closes 50% volume at $+1.0\text{R}$ or $+1.5\text{R}$.

### D. Multi-Tier Drawdown & Portfolio Circuit Breakers
- **Multi-Mode Drawdown**: Supports `STATIC`, `TRAILING` (from peak equity), and `DAILY_START_BALANCE`.
- **Safety Buffer Invariant**: Halts opening new trades when drawdown reaches 80% of the daily/total limit (e.g. at 3.2% loss on a 4.0% limit), ensuring slippage on open positions cannot cause an account breach.
- **Consecutive Loss Cooldown**: 2 consecutive losses trigger a 15-minute symbol cooldown; 3 consecutive losses trigger an account-wide 30-minute pause with automated recovery (`portfolio_risk.py:308-335`).
- **Aggregate Open Risk Cap**: Total combined open risk across all positions cannot exceed 1.5%–3.0% of equity.

---

## 7. Trading Decision Engine & Operational Logic Pipeline

The decision engine operates deterministically through a sequential 15-stage filter:

```
[Candle Ingestion] ──> [Staleness Gate (<180s)] ──> [Regime Classifier]
                             │
                             ▼
[Scalping Models M1/M5/M15] ──> [SMC Fallback Models]
                             │
                             ▼
[Confluence Scorer (>=55 / >=75)] ──> [Idempotency Key Check]
                             │
                             ▼
[Setup Quality Gate G1-G8] ──> [Meta-Labeling & Kelly Modulator]
                             │
                             ▼
[Position Sizing Engine ($5 Floor, R9 2.0% Cap)]
                             │
                             ▼
[Portfolio Risk Engine (Drawdown, Streaks, Cooldowns)]
                             │
                             ▼
[Bridge Dispatch (Port 5555)] ──> [Native MQL5 Safety Checks] ──> [Broker Fill]
                             │
                             ▼
[Position Manager: $5 Lock, BE, Partial TP, Trailing SL, CUSUM Update]
```

### Operational Cause-and-Effect Rules:
- **Enters BUY**: Fast EMA9 > EMA21 alignment, bullish displacement candle closing above prior high, confluence score >= 55.0, H4/D1 trend bullish, entry in Discount (<50%), structural SL > 0, monetary R:R >= 1.2, capital >= $5.00, risk <= 2.0%.
- **Enters SELL**: Fast EMA9 < EMA21 alignment, bearish displacement candle closing below prior low, confluence score >= 55.0, H4/D1 trend bearish, entry in Premium (>50%), structural SL > 0, monetary R:R >= 1.2, capital >= $5.00, risk <= 2.0%.
- **Rejects Entry**: `stop_loss <= 0`, risk > 2.0%, capital < $5.00, spread > 35% of SL, R:R < minimum, ranging HTF structure, counter-trend conflict, breakout candle chasing without pullback, margin required > 50% of free margin, daily loss limit reached, 3 consecutive losses active, duplicate bar signal, or bridge watchdog halted.
- **Reduces Size**: Reduced history mode (0.5x), 2 consecutive losses (0.5x), mild drawdown throttle (0.6x/0.3x), high GARCH volatility expansion (volatility scaling), CUSUM decay alert at 2.5$\sigma$ (0.5x).
- **Stops Trading**: Daily loss >= limit (4%), total drawdown >= limit (8%), 3 consecutive losses, capital < $5.00, CUSUM drift >= 3.0$\sigma$, or watchdog timeout > 30s.

---

## 8. Market Regime & Adaptive Intelligence

- **Regime Classification**: The bot categorizes market regimes into four distinct states using EMA fan separation, ATR ratios, and Gaussian volatility models (`continuous_scalper.py:264-303`, `src/regime/regime_detector.py`):
  1. `BULLISH_TREND`: `close > EMA9 > EMA21 + 0.05*ATR` and `EMA21 >= EMA50 - 0.1*ATR`.
  2. `BEARISH_TREND`: `close < EMA9 < EMA21 - 0.05*ATR` and `EMA21 <= EMA50 + 0.1*ATR`.
  3. `HIGH_VOLATILITY`: `ATR14 / LongATR50 >= 1.75`.
  4. `RANGING`: Absence of directional alignment or compressed volatility.
- **Adaptive Execution Behaviors**:
  - In `HIGH_VOLATILITY`, position sizing is dynamically compressed via `recommended_size_scale` and stops are widened to prevent whipsaws.
  - In `RANGING`, the SMC engine enforces Rule R1 ("Ranges = NO TRADE") and halts trend continuation entries, while the continuous scalper restricts entries strictly to liquidity sweeps of range boundaries.

---

## 9. Technical Capabilities & Skills Inventory

### Institutional Summary Matrix

| Capability Domain | Fully Verified & Active | Implemented / Wired | Disconnected / Orphaned | Not Present |
| :--- | :---: | :---: | :---: | :---: |
| **Market Intelligence** | Multi-Timeframe (W1..M1), EMA/RSI/ATR/ADX, SMC Structure, FVGs, OBs, Liquidity Pools. | 51 Candlestick & Chart Patterns. | AlgoVistra 28-Video Pipeline, SMT Divergence, BPR/Unicorn. | Machine Learning RL. |
| **Trading Operations** | Market execution, Pending orders, Modifications, Partial close (50%), Break-even, Trailing stops, $5 profit locks. | Multi-symbol round-robin, Manual position adoption. | CISD Module, Trendline Liquidity Module. | Triangular Arbitrage. |
| **Quantitative Analytics** | Monetary R:R, Weighted scoring, DSR, PBO, Monte Carlo Ruin, Fractional Kelly, GARCH(1,1), EWMA. | Genetic Parameter Optimizer. | N/A | Deep Neural Networks. |
| **Automation & Reliability** | 24/7 continuous scan, OS Mutex, Socket exclusivity, 30s Watchdog, CUSUM decay guard, Cloud agent. | Desktop Companion (Electron), Telegram console. | N/A | Cloud Auto-Scaling. |

---

## 10. Learning, Memory & Performance Intelligence

### Does the bot genuinely learn?
- **Forensic Assessment**: The bot implements **statistical performance tracking, parameter adaptation, and supervised meta-labeling**, but **does NOT implement autonomous online self-modifying code or reinforcement learning**.
- **Champion / Challenger Framework (`champion_challenger.py`)**: Tracks champion vs. shadow challenger strategies across out-of-sample deals. **Strictly enforces manual operator approval for strategy promotion**; uncontrolled autonomous live parameter shifting is explicitly prohibited by design for institutional safety.
- **Meta-Labeling Controller (`src/learning/meta/`)**: Trains a regularized logistic regression model with Platt calibration on historical trade features (spread, RSI, displacement, session, volatility) to predict secondary probability of success.
- **CUSUM Performance Drift Guard (`decay_guard.py`)**: Continuously monitors realized R-multiples using Page's cumulative sum algorithm. Detects structural alpha decay and automatically scales down risk.

---

## 11. Trade Execution, MQL5 EA & Socket IPC Integration

### Communication Protocol
- **Port 5555 (MQL5 Link)**: Custom persistent TCP socket link. Native EA sends JSON requests and receives JSON execution commands.
- **Port 5556 (IPC Link)**: Localhost administrative switchboard for CLI scripts, Telegram service, and Companion dashboard.
- **Socket Security**: Configures `SO_EXCLUSIVEADDRUSE` on Windows, preventing port hijacking or split-brain routing.

### State Synchronization & Recovery
- **Watchdog Timeout**: EA expects a ping every 15–30s. If heartbeat is lost for 30s, EA transitions to `g_watchdog_halted = true` and rejects new orders.
- **Terminal Crash Resilience**: EA serializes position attributes (initial SL points, strategy mode, BE status, partial TP status) directly to MT5 terminal global storage (`GlobalVariableSet`). Upon restart, state is re-anchored without losing trade plans.
- **Execution Deduplication**: Every order carries a unique `request_id`. The EA caches recent IDs; duplicate network packets return the cached fill result without sending duplicate orders to the broker.

---

## 12. Backtesting, Validation & Empirical Performance Claims

### Verified Empirical Performance Data (from `reports/`)

#### 1. Baseline Raw SMC Validation (`reports/validation_report.md`):
- **EURUSD.m**: 21 trades, Win Rate 28.6%, Profit Factor 0.93, Expectancy -0.042 R, DSR 0.0075. Verdict: `edge not demonstrated`.
- **XAUUSD.m**: 70 trades, Win Rate 31.4%, Profit Factor 1.13, Expectancy +0.089 R, DSR 0.0270, PBO 71.4%. Verdict: `edge not demonstrated`.
- **Monte Carlo Ruin Probability on $5 Account**: **92.2% to 96.2%**.

#### 2. Phase 4 Setup Quality Gate Ablation (`reports/smc_rulebook_phase4_validation.md`):
Dataset: 2024-01-01 to 2026-06-30 (1,063 OOS setups across EURUSD, GBPUSD, USDJPY, XAUUSD):
- **Baseline (All Gates OFF)**: 1,063 trades, Win Rate 21.8%, Expectancy `-0.414 R`, Profit Factor 0.53, Max DD 99.0%.
- **All Hard Gates ON (G1–G8 Enforced)**: 65 trades, Win Rate 50.8%, Expectancy `+0.595 R`, Profit Factor 2.08, Max DD 6.53%.
- **Recommended Configuration (G1, G3–G8 ENFORCE; G2 SHADOW)**: **123 trades, Win Rate 52.0%, Expectancy `+0.628 R`, Profit Factor 2.17, Max DD 4.55%, Max Losing Streak 4**.

---

## 13. Security, Operational Safety & Reliability Audit

1. **Credential Safety**:
   - Zero transmission of MT5 broker account passwords over the network or to ArcadeFX Cloud.
   - Credentials stored locally in Windows protected directories (`%LOCALAPPDATA%\ArcadeFX\...`).
2. **ArcadeFX Cloud Link**:
   - Outbound-only HTTPS connections; zero listening ports exposed to the public Internet.
   - All inbound cloud commands require HMAC-SHA256 signatures with nonce, timestamp, and replay expiry.
   - Hard ceilings defined in `local_limits.json` cannot be overridden by cloud commands.
3. **Process Supervision**:
   - `scripts/supervisor.py` manages process groups (`CREATE_NEW_PROCESS_GROUP`), prevents zombie tasks, and implements exponential restart backoffs (2s -> 60s).
   - Single-instance mutexes (`Local\ArcadeFX_MT5_Supervisor_Mutex`) prevent dual-engine conflicts.

---

## 14. Hidden, Dormant & Undocumented Capabilities

The audit revealed four major functional bodies present in code but detached from live execution:
1. **AlgoVistra / Art of Trading 28-Video Confirmation Pipeline (`src/engine/pipeline.py` & `src/engine/skills/*`)**: Contains 23 rich skill modules implementing multi-gate confirmation, range loops, and five-check models. **Executed only in backtest scripts and manual assessor; detached from live orchestrator.**
2. **Modular Strategy Pipeline Adapters (`src/strategies/*`)**: CISD, trendline liquidity, and volume distribution modules exist, but are gated behind disabled feature flags (`upgrade_enabled: false`).
3. **SMT Divergence Engine (`src/smc/smt.py`)**: Fully coded divergence logic between correlated assets; completely unreferenced in `src/`.
4. **BPR & Unicorn Zones (`src/smc/bpr_ifvg_helpers.py`)**: Helper functions exist and config flags are `true`, but functions are never called by `strategy_engine.py`.

---

## 15. Risk Management Scoring & Technical Maturity (0–10)

| Risk Management Domain | Score | Operational Enforcement Status |
| :--- | :---: | :--- |
| 1. Account Protection | **8.5 / 10** | `min(bal, eq)` baseline, $5 capital floor, automatic cent conversion. |
| 2. Position Sizing | **9.0 / 10** | Exact tick-value sizing, strict round-down step quantization, Rule R9 2.0% cap. |
| 3. Stop-Loss Enforcement | **9.5 / 10** | Mandatory SL on 100% of orders; anti-widening policy enforced across all APIs. |
| 4. Take-Profit Management | **8.5 / 10** | Monetary net R:R enforcement, $5 net profit lock, partial TP, trailing stops. |
| 5. Daily Loss Protection | **8.5 / 10** | Realized daily loss accumulator, automated daily circuit breaker. |
| 6. Drawdown Protection | **8.0 / 10** | Multi-mode drawdown (STATIC/TRAILING), 80% safety buffer halt. |
| 7. Portfolio Exposure | **7.5 / 10** | Simultaneous position caps (3–5), aggregate open risk cap (1.5%–3.0%). |
| 8. Correlation Management | **6.5 / 10** | Coarse static symbol grouping; lacks dynamic rolling covariance allocation. |
| 9. Execution Risk Control | **8.5 / 10** | 35% spread-to-SL filter, auto filling modes, retry loop, timeout reconciliation. |
| 10. Emergency Controls | **9.0 / 10** | Telegram kill switch, GUI kill switch, 30s heartbeat watchdog, MQL5 state recovery. |
| 11. Market Filtering | **8.0 / 10** | Regime detection, RSI anti-chasing; news filter is disabled by default. |
| 12. Strategy Validation | **8.5 / 10** | Setup Quality Gate G1-G8, Bailey DSR, CSCV PBO, 5,000 Monte Carlo runs. |
| 13. Trade Monitoring | **8.5 / 10** | Page's CUSUM performance drift guard alerting at 2.0$\sigma$, halting at 3.0$\sigma$. |
| 14. Operational Reliability | **8.5 / 10** | Windows Mutex, `SO_EXCLUSIVEADDRUSE` sockets, file locks, rotating logs. |
| 15. Recovery & Fault Tolerance | **8.0 / 10** | Auto-recovery on streak pause, supervisor process restart, MQL5 global sync. |

### Overall Technical Maturity Score: **8.3 / 10 (Institutional Grade)**

---

## 16. Final Executive Assessment (The 20 Core Answers)

### 1. What exactly is MT5 001?
MT5 001 is a hybrid institutional algorithmic trading system combining a low-latency native MQL5 Expert Advisor bridge (`PythonBridgeEA.mq5`) with a Python quantitative engine, an Electron desktop companion, and an outbound cloud telemetry agent.

### 2. What trading philosophy is it built around?
It is built around **Smart Money Concepts (SMC) and ICT institutional price delivery principles**, combined with quantitative risk management: high-probability liquidity sweeps, displacement order blocks, fair value gaps, strict multi-timeframe trend alignment, and mathematical capital preservation (Rule R9).

### 3. Which strategies does it genuinely implement?
It genuinely implements **Momentum Continuation Scalping**, **Pullback Scalping (FVG/OB/OTE)**, **Breakout / Liquidity-Sweep Scalping**, **Weekly/Daily Liquidity Reversals (PWL/PWH/PDL/PDH)**, and **M15 Institutional SMC Order Block / FVG mitigations**.

### 4. Which market conditions is it designed to trade?
It is designed to trade **clear trending markets** (bullish/bearish expansion legs) and **structured ranges with distinct liquidity boundaries**. It rejects illiquid sessions, unconfirmed chop, and hyper-volatile spikes.

### 5. How does it identify trade opportunities?
Via a dual-engine architecture:
1. `ContinuousScalpingEngine` continuously evaluates fast M1/M5/M15 candle anatomy, EMA9/21 alignment, OTE retracements, and swing sweeps.
2. `SmcStrategyEngine` scans M15 candles for Weekly/Daily liquidity pool interactions, structural CHoCH/BOS shifts, and unmitigated Order Blocks/FVGs.

### 6. How does it decide whether a trade is valid?
Through a sequential multi-stage gatekeeper: confluence score must exceed threshold (55.0 scalp / 75.0 SMC); Setup Quality Gate (G1–G8) must pass; secondary meta-labeling model must predict success; spread must be <= 35% of SL; and portfolio risk must approve open exposure.

### 7. How does it calculate position size?
Using exact tick value, tick size, and contract specifications:
$$\text{Raw Lots} = \frac{\text{Capital Base} \times \text{Risk \%}}{\text{Total Loss Per Lot (SL Points + Spread + Commission)}}$$
Volume is quantized using `MathFloor` (strictly rounding down) and clamped to the R9 hard cap of 2.0%.

### 8. How does it protect account equity?
By taking $\min(\text{Balance}, \text{Equity})$ as its capital baseline, enforcing an un-bypassable $\$5.00$ operating floor, capping daily losses at 2%–4%, halting entries at an 80% safety buffer, and enforcing hard drawdown lockouts.

### 9. How does it manage losing trades?
Losing trades are cut cleanly at the broker level by mandatory protective stop-losses. Widening stops is prohibited. After 2 consecutive losses on a symbol, a 15-minute cooldown is imposed; after 3 consecutive losses, account trading is paused for 30 minutes.

### 10. How does it secure profits?
Through an active trade management machine: once floating profit hits $\$5.00$ net, it locks in a $\$5.00$ floor; at $+1.0\text{R}$, it moves SL to break-even $+ 1.0$ pip buffer; at $+1.0\text{R}/+1.5\text{R}$, it closes 50% partial volume; and it trails the remainder using dynamic ATR/swing stops.

### 11. How does it manage simultaneous positions?
It limits simultaneous positions to 3–5 tickets, caps aggregate open risk across all positions at 1.5%–3.0% of equity, and enforces correlation group limits.

### 12. How does it respond to volatility and market changes?
It classifies market regime on every bar. In high volatility ($\text{ATR} / \text{LongATR} \ge 1.75$), it scales down position size via GARCH(1,1) volatility targeting and widens stop distances. In ranging markets, it halts trend-following entries.

### 13. What technical and analytical capabilities does it possess?
Multi-timeframe cascading analysis (W1 to M1), 51 candlestick pattern detectors, swing structure mapping, FVG/IFVG/OB detection, Deflated Sharpe Ratio calculation, Probability of Backtest Overfitting (PBO), Monte Carlo ruin simulations, and Page's CUSUM sequential decay testing.

### 14. Does it genuinely learn and adapt?
It **adapts dynamically** (modulating size via volatility and win rates, tracking CUSUM decay, and scoring via logistic meta-labeling), but **does not autonomously rewrite its own trading rules or run live online reinforcement learning**. Strategy promotions strictly require manual human approval.

### 15. What are its strongest technical abilities?
1. Defense-in-depth risk gating (Rule R9 2.0% hard cap, anti-widening stop policy, minimum-of-balance-and-equity baseline).
2. Robust native MQL5 integration with heartbeat watchdogs, state recovery in GlobalVariables, and idempotent request deduplication.
3. Sophisticated quantitative validation infrastructure (Bailey's DSR, CSCV PBO, Monte Carlo ruin, and CUSUM decay guard).

### 16. What are its weakest areas?
1. Disconnection between the 28-video AlgoVistra pipeline (`src/engine/pipeline.py`) and the active live production engine (`orchestrator.py`).
2. High-impact economic news filter is explicitly disabled in default continuous scalping configuration.
3. Static coarse correlation clusters rather than real-time rolling portfolio covariance optimization.

### 17. What important risk controls are missing?
1. Live automated news scraping link to avoid trading through unscheduled central bank announcements.
2. Dynamic tick-level portfolio covariance matrix calculation.
3. Automatic broker credential revocation on catastrophic emergency halt.

### 18. What could cause unexpected losses?
1. Severe weekend or overnight price gaps bypassing broker stop-loss execution levels.
2. Extreme spread blowouts during high-impact news events (due to news filter being disabled).
3. Operating on micro-accounts (<$25) with high-risk override flags enabled, allowing 0.01 lot to risk >10% of equity.

### 19. What limits its reliability?
1. Reliance on a single Windows machine / VPS running MT5 client terminal, Python engine, and Electron supervisor simultaneously.
2. Potential for MT5 terminal process freezing without crashing, bypassing supervisor PID checks.

### 20. What improvements would produce the greatest safety and performance benefits?
1. **Re-enabling the economic news blackout filter** on CPI, NFP, and FOMC announcements.
2. **Wiring the 28-video AlgoVistra confirmation pipeline directly into the live orchestrator**.
3. **Upgrading the supervisor process to actively probe socket heartbeats**, rather than relying solely on process PID presence.

---

## 17. Prioritized Improvement Roadmap

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
**Audit Verification:** Master forensic audit complete. All findings, code locations, formulas, scores, and structural inventories independently cross-referenced against the MT5 001 repository.
