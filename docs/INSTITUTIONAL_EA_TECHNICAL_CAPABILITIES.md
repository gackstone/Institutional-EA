# MT5 001 — Technical Capabilities & Skills Inventory
**Forensic Technical Intelligence Audit**  
**Classification:** Quantitative Systems Capabilities & Audit Classification  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Senior Algorithmic Trading Engineer & Financial Systems Auditor  
**Date of Audit:** November 2026  

---

## 1. Capability Classification Standards

Every technical capability in the **MT5 001** codebase has been forensically examined and assigned one of seven strict institutional classifications based on source code presence, pipeline wiring, test coverage, and execution reality:

1. **FULLY IMPLEMENTED AND VERIFIED:** Code exists, is wired into the active production pipeline, and has verified test or live runtime coverage.
2. **IMPLEMENTED BUT NOT VERIFIED:** Code exists and is wired, but lacks sufficient unit/integration test coverage or empirical validation.
3. **PARTIALLY IMPLEMENTED:** Code is incomplete, handles only partial logic, or lacks critical branches.
4. **EXPERIMENTAL:** Code exists as a research or prototype module, not enabled in standard production configuration.
5. **CONFIGURED BUT DISABLED:** Feature flags or configuration entries exist and backend code exists, but setting is currently toggled OFF.
6. **REFERENCED BUT NOT IMPLEMENTED:** Mentions exist in comments, documentation, or string names, but no functional underlying implementation exists.
7. **NOT PRESENT:** Capability does not exist in the codebase.

---

## 2. Market Intelligence Capabilities

| Capability | Classification | Forensic Evidence & Source Location | Implementation Details & Limitations |
| :--- | :--- | :--- | :--- |
| **Multi-Timeframe Analysis** | **FULLY IMPLEMENTED AND VERIFIED** | `src/smc/mtf_analyzer.py:1-250`; `orchestrator.py:617-640`; `tests/test_multi_timeframe.py` | Cascading analysis from W1 -> D1 -> H4 -> H1 -> M15. Computes trend bias, swing extremes, and reference levels across all timeframes. |
| **Technical Analysis Indicators** | **FULLY IMPLEMENTED AND VERIFIED** | `src/execution/continuous_scalper.py:148-194`; `src/core/volatility.py:1-120` | Vectorized EMA (EMA9, EMA21, EMA50), Wilder RSI(14), True Range ATR(14), and Wilder ADX(14). Zero repainting; strictly operates on closed bars. |
| **Price-Action Pattern Recognition** | **FULLY IMPLEMENTED AND VERIFIED** | `src/patterns/candlesticks.py:1-450`; `chart_patterns.py:1-350`; `tests/test_candlestick_patterns.py` | 51 closed-bar candlestick patterns (Doji, Engulfing, Morning/Evening Star, Pin Bar, etc.) and swing-based chart patterns (Double Tops/Bottoms, Head & Shoulders). ATR-normalized. |
| **SMC Structure Mapping (BOS/CHoCH)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/smc/market_structure.py:1-174`; `structure_confirmation.py:1-492`; `tests/test_market_structure.py` | Symmetrical swing lookback ($k=5$). Enforces candle body close for BOS and a 5-state automaton for CHoCH confirmation. |
| **Liquidity Mapping (BSL/SSL/EQH/EQL)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/smc/liquidity.py:1-185`; `tests/test_liquidity_engine.py` | Identifies resting stop liquidity pools and equal highs/lows within configurable pip tolerance. Detects pierce and close-back-inside sweeps. |
| **Order Block & FVG Detection** | **FULLY IMPLEMENTED AND VERIFIED** | `src/smc/fvg_ob.py:1-405`; `tests/test_smc_rulebook_golden.py` | Detects 3-bar FVGs (with IFVG inversion) and Order Blocks requiring displacement ($1.2 \times \text{ATR}$) and structural breaks (BOS). |
| **Market Regime Detection** | **FULLY IMPLEMENTED AND VERIFIED** | `src/regime/regime_detector.py:1-250`; `continuous_scalper.py:264-303`; `tests/test_regime_detection.py` | Multi-state classification: `BULLISH_TREND`, `BEARISH_TREND`, `RANGING`, `HIGH_VOLATILITY` based on EMA fan, ATR ratios, and Gaussian dispersion. |
| **Session & Killzone Awareness** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/sessions.py:1-150`; `config/sessions.json`; `tests/test_sessions_volatility.py` | UTC-aligned session clock tracking Asian, London, New York, and London Close Killzones. Computes session high/low liquidity levels. |
| **News Filtering & Blackout Guard** | **CONFIGURED BUT DISABLED** | `src/core/news_filter.py:1-120`; `config/strategy_config.json:12` | News engine with ForexFactory/economic calendar parser. Fully implemented, but explicitly disabled (`"news_filter_enabled": false`) in default scalping config. |
| **Economic Event Awareness** | **PARTIALLY IMPLEMENTED** | `src/core/news_filter.py:45-80` | Parses economic events if fed via JSON/CSV, but lacks live web-scraping socket link for automated real-time calendar updates. |
| **SMT Intermarket Divergence** | **EXPERIMENTAL** | `src/smc/smt.py:1-55` | Divergence logic between correlated assets exists in `smt.py`, but is orphaned and uncalled in the live execution pipeline. |
| **Balanced Price Range (BPR)** | **EXPERIMENTAL** | `src/smc/bpr_ifvg_helpers.py:13-110` | Geometric intersection of overlapping bullish and bearish FVGs exists, but is not connected to live signal generator. |

---

## 3. Trading Operations Capabilities

| Capability | Classification | Forensic Evidence & Source Location | Implementation Details & Limitations |
| :--- | :--- | :--- | :--- |
| **Market Order Execution** | **FULLY IMPLEMENTED AND VERIFIED** | `src/execution/order_manager.py:441-550`; `PythonBridgeEA.mq5:2725-2740` | Live market execution (`BUY`, `SELL`) via MT5 Bridge with filling mode negotiation (IOC, FOK, RETURN) and slippage deviation controls. |
| **Pending Order Execution** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:2741-2755`; `src/execution/analytics/limit_orders.py` | Supports `BUY_LIMIT`, `SELL_LIMIT`, `BUY_STOP`, `SELL_STOP` placement and cancellation tracking. |
| **Dynamic Position Modification** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:2883-2914`; `order_manager.py:validate_sl_modification` | Modifies SL and TP at broker level. Enforces anti-widening rule (Rule R9.3). |
| **Partial Profit Taking** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:2452`; `trade_management.py:120-165` | Native `PositionClosePartial` closes 50% of volume at specified R-multiples while maintaining remaining position open. |
| **Full Position Closure** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:2452`; `bridge_client.py:close_position` | Full market close via ticket selection with broker confirmation retcode auditing. |
| **Break-Even Protection** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:468`; `trade_management.py:65-95` | Automatically advances SL to entry price plus 1.0 pip buffer upon reaching target R-multiple. |
| **Dynamic Trailing Stops** | **FULLY IMPLEMENTED AND VERIFIED** | `PythonBridgeEA.mq5:469`; `trade_management.py:170-220` | ATR-based and swing-based trailing stops updating dynamically on incoming ticks. |
| **$5+ Net Profit Target Locking** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/orchestrator.py:911-960`; `config/risk_config.json:34-39` | Tracks net floating profit after fees and locks minimum $5.00 net floor upon reaching target. |
| **Multi-Position Management** | **FULLY IMPLEMENTED AND VERIFIED** | `src/execution/order_manager.py:get_active_positions`; `portfolio_risk.py` | Concurrently tracks up to 3–5 open positions, managing tickets independently. |
| **Multi-Symbol Scanning & Trading** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/orchestrator.py:165-175`; `continuous_scalper.py:98-115` | Multi-symbol round-robin loop scanning EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD.m concurrently. |
| **Discretionary Trade Adoption** | **FULLY IMPLEMENTED AND VERIFIED** | `src/manual_mgmt/*` (7 files); `tests/test_manual_management.py` | Discovers manual/phone trades, classifies them, and adopts them under OBSERVE or PROTECT management policies. |

---

## 4. Quantitative & Statistical Capabilities

| Capability | Classification | Forensic Evidence & Source Location | Implementation Details & Limitations |
| :--- | :--- | :--- | :--- |
| **Monetary Risk/Reward (R:R)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/risk/position_sizing.py:341-373`; `PythonBridgeEA.mq5:2589-2605` | Computes exact monetary gain at TP vs. monetary loss at SL taking into account spread and commissions. |
| **Weighted Confluence Scoring** | **FULLY IMPLEMENTED AND VERIFIED** | `src/smc/strategy_engine.py:658-805`; `config/strategy_config.json:94-106` | Evaluates signals on a 0–100 scale across 8 weighted technical factors. Rejection threshold >= 75.0 (SMC) or >= 55.0 (scalping). |
| **Deflated Sharpe Ratio (DSR)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/validation/statistics.py:55-110`; `reports/validation_report.md` | Bailey & Lopez de Prado (2014) DSR formula correcting Sharpe for skewness, kurtosis, and multi-trial selection bias. |
| **Probability of Backtest Overfitting** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/validation/statistics.py:112-160` | Combinatorially Symmetric Cross-Validation (CSCV) estimating the probability that an in-sample strategy overfits. |
| **Monte Carlo Ruin Risk Simulation** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/validation/monte_carlo.py:1-120`; `tests/test_validation_suite.py` | 5,000-iteration block bootstrap evaluating ruin probabilities across $5, $25, $100, and $500 starting balances. |
| **Fractional Kelly Sizing** | **FULLY IMPLEMENTED AND VERIFIED** | `src/risk/kelly.py:1-95`; `tests/test_risk_management.py` | Quarter-Kelly ($0.25f^*$) sizing. Clamped to account tier ceilings; strictly non-positive expectancy forces Kelly to 0.0. |
| **GARCH(1,1) Volatility Modeling** | **FULLY IMPLEMENTED AND VERIFIED** | `src/risk/volatility.py:38-115`; `tests/test_volatility_risk.py` | Variance-targeting GARCH(1,1) forward conditional volatility forecasting. Modulates stop scaling and sizing. |
| **EWMA (RiskMetrics) Modeling** | **FULLY IMPLEMENTED AND VERIFIED** | `src/risk/volatility.py:118-150` | RiskMetrics exponential volatility estimator with decay factor $\lambda = 0.94$. |
| **Transaction Cost Analysis (TCA)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/execution/analytics/tca.py:1-180`; `reports/raw/tca_records.jsonl` | Measures execution slippage, spread cost at fill, latency delay, and post-trade markouts. |
| **Purged & Embargoed Walk-Forward** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/validation/walk_forward.py:1-150` | Walk-forward cross-validation with purging and embargoing to eliminate serial correlation lookahead bias. |

---

## 5. Automation, Learning & System Intelligence

| Capability | Classification | Forensic Evidence & Source Location | Implementation Details & Limitations |
| :--- | :--- | :--- | :--- |
| **Autonomous Signal Generation** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/orchestrator.py:141-175`; `start_bot.py:141-193` | 24/7 autonomous loop scanning data, generating signals, sizing lots, and executing trades without human intervention. |
| **Adaptive Stop Sizing (ATR)** | **FULLY IMPLEMENTED AND VERIFIED** | `src/execution/continuous_scalper.py:676-715` | Dynamically adapts stop distances based on ATR and instrument profiles, avoiding fixed-pip rigidity. |
| **Machine Learning Meta-Labeling** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/meta/meta_classifier.py:1-120`; `model.py:1-140` | Pure NumPy regularized logistic regression with Platt calibration. Predicts secondary trade success probability. |
| **Champion / Challenger Framework** | **FULLY IMPLEMENTED AND VERIFIED** | `src/learning/champion_challenger.py:1-120`; `tests/test_champion_challenger.py` | Evaluates challenger strategies in shadow mode. Strictly requires manual approval for live promotion. |
| **Genetic Parameter Optimization** | **IMPLEMENTED BUT NOT VERIFIED** | `src/learning/genetic_optimizer.py:1-110` | Evolutionary algorithm for parameter optimization. Present in codebase, but not executed in standard live runs. |
| **CUSUM Strategy Decay Guard** | **FULLY IMPLEMENTED AND VERIFIED** | `src/monitoring/decay_guard.py:1-110`; `tests/test_monitoring_decay.py` | Page's CUSUM sequential test monitoring cumulative negative R deviation. Alerts at 2.0$\sigma$, cuts risk at 2.5$\sigma$, halts at 3.0$\sigma$. |
| **LLM-Assisted Trade Review** | **EXPERIMENTAL** | `src/monitoring/llm_reviewer.py:1-99` | Generates prompt templates for OpenAI/Gemini weekly reviews. Requires external API key; purely advisory. |
| **Reinforcement Learning** | **NOT PRESENT** | N/A | No reinforcement learning (RL) agents, Q-learning, or policy gradient models exist in the codebase. |

---

## 6. Infrastructure, Integration & Operational Safety

| Capability | Classification | Forensic Evidence & Source Location | Implementation Details & Limitations |
| :--- | :--- | :--- | :--- |
| **MT5 Terminal IPC Bridge** | **FULLY IMPLEMENTED AND VERIFIED** | `mql5/Experts/PythonBridgeEA.mq5`; `bridge_server.py:1-250` | Multi-connection TCP socket server on port 5555/5556. Handles heartbeats, data rates, orders, and position sync. |
| **Direct MetaTrader5 API Fallback** | **FULLY IMPLEMENTED AND VERIFIED** | `scripts/start_bot.py:42-78`; `src/adapters/live_mt5_broker.py` | Automatically synchronizes accounts and historical rates directly via MetaTrader5 Python API if TCP bridge is down. |
| **Single-Instance OS Guard** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/app_paths.py:SingleInstanceLock`; `supervisor.py:MUTEX_NAME` | Win32 Named Mutex and file lock preventing duplicate instances of bridge server, engine, or supervisor. |
| **Heartbeat Watchdog System** | **FULLY IMPLEMENTED AND VERIFIED** | `mql5/Experts/PythonBridgeEA.mq5:492`; `src/monitoring/health_monitor.py` | 30-second heartbeat ping. Native EA halts execution immediately if Python bridge connection is lost. |
| **Desktop Companion UI** | **FULLY IMPLEMENTED AND VERIFIED** | `companion/electron/main.cjs:1-2095`; `companion/src/*` | Electron desktop app supervising 6 core services (Engine, Bridge, Cloud Sync, Telegram, Health, Logs) with real-time React UI. |
| **Institutional EA Cloud Telemetry Link** | **FULLY IMPLEMENTED AND VERIFIED** | `agent/mt5_bot_agent.py:1-1307`; `local_limits.json` | Outbound-only HTTPS/WSS telemetry agent. HMAC-SHA256 signed cloud commands; local limits act as an un-bypassable ceiling. |
| **Telegram Control & Alerts** | **FULLY IMPLEMENTED AND VERIFIED** | `src/notifications/telegram_service.py:1-350`; `router.py:1-120` | Asynchronous rate-limited Telegram dispatcher with interactive two-step command console (`/status`, `/pause`, `/killswitch`). |
| **Encrypted Credential Storage** | **FULLY IMPLEMENTED AND VERIFIED** | `src/core/app_paths.py:get_primary_credentials_file`; `mt5_bot_agent.py:95` | Secure local credential storage in `%LOCALAPPDATA%\Institutional EA\...`. Zero transmission of MT5 broker passwords to cloud. |

---
**Audit Verification:** Every classification substantiated with exact file locations, code paths, and architectural boundaries.
