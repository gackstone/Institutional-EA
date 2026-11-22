# ARCHITECTURE_BEFORE: Institutional MT5 Algorithmic Day-Trading System

## 1. System Overview & Entry Points

The repository represents an institutional MetaTrader 5 (MT5) multi-timeframe algorithmic trading platform designed for day trading and swing-scalping across multiple asset classes (FX, Precious Metals, Crypto, Indices). The system combines an MQL5 Expert Advisor (`PythonBridgeEA.mq5`) with a multi-layered Python trading engine (`src/`), a persistent TCP communication bridge (`src/execution/bridge_server.py`), and a secure cloud companion agent (`agent/mt5_bot_agent.py`).

### Key Application Entry Points
1. **Trading Engine CLI Launcher (`scripts/start_bot.py`)**:
   - Primary console entry point. Initializes single-instance lock (`mt5_trading_engine`).
   - Loads application configuration via `AppConfig.load_from_dir()`.
   - Bootstraps `TradingBotOrchestrator`, connects to MT5 Bridge (or falls back to direct `MetaTrader5` Python API), performs multi-timeframe candle warmup (W1 down to M1), and enters the continuous scanning loop.
2. **Batch Launcher (`start_mt5_bot.bat`)**:
   - Executes pre-flight diagnostics (`scripts/selfcheck.py`) and launches the cloud bot agent or trading engine.
3. **Cloud Agent Entry Point (`agent/mt5_bot_agent.py`)**:
   - Outbound-only orchestration agent running next to MT5. Enforces local limits (`local_limits.json`), communicates with cloud management via HMAC-SHA256 signed requests, and streams telemetry/heartbeats.
4. **Persistent Bridge Server (`scripts/run_bridge_server.py`, `src/execution/bridge_server.py`)**:
   - Multi-connection TCP socket daemon listening on `127.0.0.1:5555` (for MQL5 EAs) and `127.0.0.1:5556` (for IPC client requests).
5. **MQL5 Expert Advisor (`mql5/Experts/PythonBridgeEA.mq5`)**:
   - Attached to charts inside MetaTrader 5. Manages socket client communication, order dispatching, local stop-loss/take-profit modifications, and emergency safeguards.

---

## 2. Python-to-MT5 Execution Flow

The communication and execution pipeline operates across three primary layers:

```
[ Market Data & Scanners ]
            │
            ▼
[ TradingBotOrchestrator ]
            │
            ▼
[ Setup Quality & Checklist Gates ]
            │
            ▼
   [ OrderManager ]
            │
    ┌───────┴───────────────────────┐
    ▼                               ▼
[ LiveMT5Broker Adapter ]    [ BridgeClient ]
    │ (BrokerFactory)               │ (JSON via TCP)
    └───────────────┬───────────────┘
                    ▼
     [ Persistent BridgeServer (5555/5556) ]
                    │
                    ▼ (Native Socket)
      [ PythonBridgeEA.mq5 in MT5 Terminal ]
                    │
                    ▼ (MQL5 OrderSend)
             [ Broker Trade Server ]
```

### Direct MT5 API Fallback
When the TCP socket bridge is unavailable or not running, the system leverages `MetaTrader5` direct Python bindings in `scripts/start_bot.py` (`_sync_account_from_mt5_direct`) and `src/core/market_data.py`, retrieving live quotes, ticks, and candle history directly from the terminal terminal context.

---

## 3. Strategy, Signal, and Analytical Modules

The intelligence stack is extensive and modular:
1. **Smart Money Concepts (SMC/ICT) Engine (`src/smc/`)**:
   - `market_structure.py`: Identifies Swing Highs/Lows, Break of Structure (BOS), and Change of Character (CHoCH).
   - `fvg_ob.py`: Detects Fair Value Gaps (FVG) and Order Blocks (OB).
   - `liquidity.py` & `session_liquidity.py`: Maps Buy-Side (BSL) and Sell-Side (SSL) liquidity pools, Equal Highs/Lows (EQH/EQL), Previous Day High/Low (PDH/PDL), Previous Week High/Low (PWH/PWL).
   - `mtf_analyzer.py`: Multi-timeframe context aggregator across W1, D1, H4, H1, M15.
   - `strategy_engine.py` (`SmcStrategyEngine`): Generates `SignalCandidate` setups combining sweeps, MSS, and FVG/OB entries.
2. **Modular Microstructure Skills (`src/engine/skills/`)**:
   - 28 granular strategy skills including `candle_anatomy.py`, `breakout_trap_classifier.py`, `five_check_model.py`, `sweep_fvg_entry.py`, `range_location_filter.py`, and `inducement_ob_entry.py`.
3. **Continuous Multi-Timeframe Scalper (`src/execution/continuous_scalper.py`)**:
   - Implements stateful per-symbol lifecycle (MARKET_DATA -> ANALYSIS -> SIGNAL_GENERATION -> RISK_VALIDATION -> ORDER_EXECUTION -> POSITION_MANAGEMENT -> PROFIT_LOCKING -> RESCAN).
   - Evaluates three entry models: Momentum Continuation Scalp, Pullback Scalp, and Liquidity-Sweep Reversal.
4. **Pattern & Regime Recognition**:
   - `src/patterns/candlesticks.py` & `chart_patterns.py`: Classical price action patterns.
   - `src/regime/regime_detector.py`: Machine-learning and statistical regime identification (BULLISH_TREND, BEARISH_TREND, RANGING, HIGH_VOLATILITY).
   - `src/learning/meta/meta_classifier.py`: Meta-labeling secondary filter predicting probability of trade success.

---

## 4. Legacy Entry Filters & Gating Mechanisms

The existing architecture is characterized by multi-tier defensive entry gates that frequently block trades from executing:

1. **Session & Killzone Gating (`src/core/sessions.py`, `src/core/session_affinity.py`)**:
   - Blocks setups outside active Killzones (London Open, New York Open, Asian).
   - Enforces weekend shutdown, session handover cooldowns, and swap rollover blackout windows.
2. **Economic News Filter (`src/core/news_filter.py`, `src/smc/news_filter.py`)**:
   - Restricts trading before and after high-impact economic news releases (CPI, NFP, FOMC).
3. **Higher-Timeframe Alignment (`src/smc/strategy_engine.py`, `check_scalp_htf_agreement`)**:
   - Requires lower-timeframe scalp direction to match H1/H4 macro trend bias.
4. **Setup Quality Gate (`src/smc/setup_quality_gate.py`)**:
   - Evaluates strict rulebook criteria: minimum confluence score (typically 55-75), discount/premium location requirement, order block displacement multiplier, and liquidity target requirements.
5. **Closed-Candle Confirmation Requirement**:
   - System evaluates signals strictly on closed bars (`closed_candles_only: true`, M15 or M5), requiring completed candles rather than reacting to live ticks.
6. **Pre-Trade Checklist Gates (`src/execution/order_manager.py`)**:
   - Anti-chasing price drift filters (`drift > max_drift`).
   - Strict Reward-to-Risk minimums (`live_rr < min_allowed_rr`, requiring 1:1.5 or 1:2.0).
   - Structure confirmation (requiring BOS confirmation after CHoCH before permitting entry).
   - Monte Carlo replay gate (`src/risk/replay_gate.py`).
7. **Active Mode Frequency Controls (`src/execution/active_mode.py`)**:
   - Enforces post-trade cooldown timers and maximum trade frequency limits per hour/session.
8. **Single-Position-Per-Symbol Restrictions**:
   - Rejects additional orders if an active position exists on the symbol or if a signal has already been executed on the same bar.

---

## 5. Risk Management and Capital Safety Controls

The system includes institutional safety controls:
1. **Position Sizing Engine (`src/risk/position_sizing.py`)**:
   - Computes lots based on account equity, currency conversion, contract point value, and stop-loss distance.
   - Enforces Rule R9 (hard-cap risk at 2.0% per trade; default 1.0%).
   - Normalizes volume to broker `min_lot`, `max_lot`, and `lot_step`.
2. **Portfolio Risk & Circuit Breaker Engine (`src/risk/portfolio_risk.py`)**:
   - Tracks daily starting equity/balance, peak equity, and daily/weekly realized losses.
   - Triggers circuit breakers on daily loss breach (default 2% - 4%) or maximum total drawdown (default 8% - 10%).
   - Halts new order initiation when safety buffers are reached.
3. **Fast Risk Guard (`src/risk/fast_risk_guard.py`)**:
   - Inspects margin sufficiency, maximum simultaneous positions, and spread thresholds.
4. **Trade Lifecycle Management (`src/risk/trade_management.py`, `src/execution/fast_exit_manager.py`)**:
   - Evaluates break-even triggers, progressive trailing stops, partial take profits, and monetary profit protection ($5 / $20 target thresholds).
5. **Protective Stop-Loss Mandatory Rule**:
   - Strict rejection of any order missing a stop loss (`stop_loss <= 0`) and refusal to widen stop losses (Rule R9.3).

---

## 6. Manual Position Management Subsystem

Located in `src/manual_mgmt/` and integrated into `TradingBotOrchestrator.manage_manual_positions()`:
- Automatically detects manually opened positions on the account (positions whose magic number differs from the bot's magic number).
- Classifies positions (`MANUAL_STANDALONE`, `ORPHAN_BOT_DISCONNECTED`, `HYBRID_MANUAL_ADOPTED`).
- Adopts manual positions according to configured policies (`config/manual_management.yaml`), providing break-even, trailing stop, and exit protection without interfering with bot operations.

---

## 7. Configuration and Testing Infrastructure

- **Configuration Files (`config/`)**:
  - `settings.json`: General execution mode (DEMO/REAL), symbol list, and timeframe settings.
  - `strategy.yaml` & `strategy_config.json`: Strategy parameters, swing lookback, confluence thresholds.
  - `risk_config.json` & `risk_fit.json`: Risk percentages, drawdowns, break-even settings.
  - `instruments.json`: Canonical instrument profiles and broker symbol alias definitions.
- **Testing Architecture (`tests/`)**:
  - Over 60 comprehensive test files covering unit, integration, simulation, and regression test suites executed via `pytest`.
