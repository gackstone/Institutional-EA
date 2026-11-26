# Changelog

All notable changes to the Institutional Multi-Timeframe Algorithmic Trading Bot (`Institutional EA`) are documented in this file.

## [3.14.0] - 2026-11-26

### Added - Advanced ICT/SMC Market Intelligence Upgrade (Videos 0010–0019)
- **Audit, Specification & Rollback Runbook (`docs/ICT_INTELLIGENCE_AUDIT_AND_SPEC.md`, `docs/STRATEGY.md`)**:
  - Audited existing SMC/learning modules and specified Modules A–H, anti-double-counting scoring, Shadow Mode deployment, promotion gates, and instant rollback procedure.
- **ICT Market Intelligence Engine (`src/smc/ict_intelligence.py`, `config/strategy_config.json`)**:
  - **Module A**: 60-day highs/lows (`D60_HIGH`/`D60_LOW`), 3–4 month `QuarterlyContext`, and enriched `EnrichedLiquidityLevel` metadata.
  - **Module B & C**: 4-way closed-candle sweep classifier (`CONFIRMED_SWEEP`, `POTENTIAL_SWEEP`, `GENUINE_BREAKOUT`, `UNCONFIRMED_RAID`) and structure transition classifier separating body-close `MSS`/`BOS` from `WICK_ONLY_PENETRATION` and `TEMPORARY_PULLBACK`.
  - **Module D**: 7-factor `DisplacementAssessment` rejecting weak candles without imbalance.
  - **Module E**: Distinct lifecycles for `OrderBlock`, `BreakerBlock` (0019), `MitigationBlock` (0018), `PropulsionBlock` (0016, 50% mean threshold), `RejectionBlock` (0017), and `FailedSetupTransition` tracking.
  - **Module F, G & H**: True ICT `UnicornSetup` (0011), displacement-gated `OTESetup` (0014), and liquidity-first take-profit selection with `-2.0` Fibonacci extension projections (0012, 0013).
  - **Shadow Mode, Explainable Scoring & Per-Model Tracker**: Defaults to `mode: "SHADOW"`, `allow_live_orders: false`, `never_scale_lot_by_score: true`, with 5 lifecycle stages, 11 explicit `RejectionCode`s, duplicate-signal prevention, and `ICTModelPerformanceTracker`.
- **Automated Tests & Walk-Forward Validation (`tests/test_ict_intelligence_0010_0019.py`, `scripts/run_ict_intelligence_backtest.py`, `reports/ict_intelligence_validation_2026-11-26.md`)**:
  - Added comprehensive unit, anti-look-ahead, anti-repainting, precision, shadow-mode, and fail-closed safety tests plus chronological 60/40 IS/OOS walk-forward comparison with spread, commission, slippage, and Deflated Sharpe Ratio (DSR).

## [3.13.0] - 2026-11-26

### Added - Video-derived updates (2026-11)
- **Audit & Provenance (`docs/VIDEO_SKILLS_AUDIT.md`, `knowledge/exports/video_skills_2026-11.json`, `knowledge/forex_kb.json`)**:
  - Audited all 16 forex-video strategies against the existing engine (`a` already exists / `b` partial / `c` missing) and exported machine-readable primitives (`P1–P11`), named setups (`S1–S10`), 4 documented failure modes, provenance tags, and explicit educational/calibration disclaimers.
  - Documented source limitations: `keepssy_fx-20261126-0012` was missing from the source set; the 3rd HTF-bias confluence slot in `P2` (`chart__tactix-20261113-0001`) is explicitly flagged as configurable and *not from the video*.
- **NY `zoneinfo` Windows & Session Key Levels (`config/sessions.json`, `src/core/sessions.py`, `src/smc/session_liquidity.py`)**:
  - Added editable `ict_ny_windows` evaluated strictly in `America/New_York` (`zoneinfo`) for DST correctness: `silver_bullet_london` (`03:00–04:00`), `silver_bullet_ny_am` (`10:00–11:00`), `silver_bullet_ny_pm` (`14:00–15:00`), `ny_killzone` (`07:00–10:00`), `ny_macro_1` (`09:50–10:10`), and `ny_macro_2` (`10:50–11:10`), plus `broker_time_to_utc()`, `to_ny_time()`, `get_active_ict_windows()`, and `is_window_expired()`.
  - Added `SessionKeyLevels` (`Asian H/L/Mid`, `London H/L`, `PDH/PDL/PD Mid`, `NY Morning H/L`) and `compute_session_key_levels()`.
- **Core Video Primitives `P1–P11` & Data-Only Reference Symbols (`src/smc/video_primitives.py`, `src/core/symbol_universe.py`)**:
  - Implemented `P1` equal-cluster liquidity (`0.10 * ATR(14)`), `P2` sweep-vs-breakout classifier (candle formation + approach overlap/body/slope + optional HTF slot), `P3` confirmed sweep (`min_pierce_atr=0.05`, `max_bars_to_reclaim=3`), `P4` MSS with displacement + FVG, `P5` FVG with Consequent Encroachment (CE), `P6` IFVG close-through inversion + "first FVG before stop hunt" priority, `P7` bidirectional flipped breaker blocks, `P8` BOS-anchored Fibonacci OTE (`0.62–0.79`, sweet spot `0.705`, rejecting minor pullbacks), `P9–P10` draw-on-liquidity target & "no draw, no trade" gate, and `P11` SMT divergence + 3-point turn grading (`A+` / `B` / `INVALID`) wired into the existing XAUUSD/USDJPY inverse coordination engine.
  - Added `DATA_ONLY_REFERENCE_SYMBOLS` (`USDJPY`, `XAGUSD`, `DXY`, `USDX`, `ETHUSD`, `EURUSD`) for SMT reference only; `APPROVED_CANONICAL_SYMBOLS` (`XAUUSD`, `BTCUSD`) remains strictly enforced for order execution.
- **Named Setups `S1–S10` & Monotonic Scoring (`src/smc/video_setups.py`, `src/core/contracts.py`, `config/strategy_config.json`)**:
  - Extended `SignalCandidate` with backward-compatible optional fields (`setup_id`, `context`, `sweep_kind`, `smt_status`, `three_point_grade`, `draw_on_liquidity`, `entry_model`, `invalidation_price`, `provenance`, `confluence_breakdown`).
  - Implemented `VideoSetupEngine` covering `S1`–`S10` (`S1_RAID_SHIFT_FVG_CE`, `S2_SILVER_BULLET`, `S3_NY_MACRO`, `S4_LONDON_JUDAS_SWING`, `S5_ASIAN_SD_REVERSAL`, `S6_IFVG_STOP_HUNT`, `S7_STACKED_BREAKER_IFVG`, `S8_OTE_STOP_HUNT_BOS`, `S9_HIDDEN_DEMAND_SUPPLY`, `S10_SESSION_SWEEP_REVERSAL`), fail-closed config validation (`validate_video_setups_config`), and monotonic confluence scoring without adding global filters that veto existing entries.
- **Tighten-Only Trade Management, Manual Adoption, Telegram & Companion (`src/risk/trade_management.py`, `src/manual_mgmt/assessor.py`, `src/notifications/`, `companion/src/components/screens/SignalsAlertsScreens.tsx`)**:
  - Added strictly tighten-only (R9.3) runner management (`evaluate_video_runner_management`: partial TP1 + BE+cost buffer + structural trail), `evaluate_invalidation_exit()`, and `should_cancel_window_expired_order()`.
  - Updated `ManualPositionAssessor` to prefer nearby confirmed sweep extremes for naked-position SL and P9 draw-on-liquidity for suggested TP while preserving User Supremacy and R9.3.
  - Added single `<b>Model:</b>` line to existing Telegram `TradeSetupEvent` template and surfaced `setup_id`, `three_point_grade`, and `provenance` in the Companion Signals table.
- **Tests & Historical Replay (`tests/test_video_skills_2026_11.py`, `scripts/run_video_skills_replay.py`, `reports/video_skills_replay_2026-11-26.md`)**:
  - Added unit, DST/timezone, mirror (long/short), negative, config-validation, and safety tests proving reference symbols cannot be traded and stops can never be widened.
  - Added historical replay script generating an in-sample, unvalidated calibration report across local XAUUSD/USDJPY/BTCUSD M15 candles.

## [3.12.0] - 2026-11-26

### Added - Public Website, Authentication, $50/mo Binance USDT Subscription, Admin Console & Supabase Integration
- **Shared Cloud & Payment Contract (`packages/cloud-contract/`)**:
  - Centralized `INSTITUTIONAL_EA_PRO_PLAN` ($50 USD / month), `BINANCE_USDT_TRC20_CONFIG` (`TPP26iUrsJmstHVGh38rHYBipo6drZvj9D`, TRON TRC20, supplied Binance QR asset), UTC entitlement evaluation, 72-hour offline grace window policy, TXID validation, and strong password validation.
- **Public Website, Pricing, Auth, Checkout & Admin Portal (`apps/web/`)**:
  - Institutional dark landing page with responsive navigation, Hero, verified Platform Overview, Architecture separation diagram, Windows Companion Downloads, Documentation, Terms of Service, Privacy Policy, Risk Disclosure, and Contact pages.
  - Dedicated `/pricing` page (`Institutional EA Pro` — `$50 USD / month`) and `/account/subscription` portal with Binance USDT (TRC20) QR code, Copy Address, network/NFT warnings, TXID & receipt submission form, transaction history, and device management.
  - Full `/auth/*` flows (`sign-in`, `sign-up`, `forgot-password`, `verify-email`, `callback`) including validated loopback desktop sign-in handoff for the Windows Companion App.
  - Modular `/admin` dashboard gated by server-verified `role === 'admin'` for payment approval/rejection, subscription management, device revocation, and audit log review.
- **Supabase Backend Migrations, RLS & Edge Functions (`supabase/`)**:
  - Added `20261126000001_initial_cloud_schema.sql` and `20261126000002_rls_and_storage.sql` covering `profiles`, `plans`, `subscriptions`, `payments`, `devices`, `audit_logs`, and private `payment-proofs` storage with strict Row Level Security, anti-role-escalation triggers, duplicate TXID prevention, and server-side 3-device limits.
  - Added server-side Deno Edge Functions: `admin-review-payment`, `admin-manage-subscription`, and `device-heartbeat`.
- **Windows Companion Cloud Integration (`companion/`)**:
  - Added `companion/electron/cloudAuthManager.cjs` with Electron `safeStorage` (Windows DPAPI) encrypted credential & entitlement caching, privacy-conscious SHA-256 device fingerprinting, and system-browser loopback auth.
  - Added `AccountSubscriptionScreen.tsx` integrated cleanly alongside all existing Companion screens while preserving strict trading safety isolation (subscription state never closes MT5 positions or blocks local emergency controls).
- **Documentation & Tests**:
  - Updated `.env.example`, authored `docs/SUPABASE_AND_SUBSCRIPTION_DEPLOYMENT.md`, and added unit/security tests in `packages/cloud-contract/tests/cloudContract.test.ts` and `companion/src/utils/__tests__/cloudAuthAndSecurity.test.ts`.

## [3.11.0] - 2026-11-22

### Added - Companion App Institutional Trading-Terminal Dashboard Redesign (`companion/`)
- **Left Navigation Shell (`companion/src/App.tsx`)**:
  - Added collapsible dark trading-terminal sidebar grouping all 16 companion screens into **Monitor** (`Dashboard`, `Market Watch`, `Signals Pipeline`, `Positions & Orders`, `Trade History`, `Analytics`), **Control** (`Engine Control`, `Risk Manager`, `Instruments`, `Configuration`, `MT5 Terminal`, `Operations`), and **Diagnose** (`Error Centre`, `Event Logs`, `System Health`, `Settings`).
  - Integrated SSE streaming (`/api/events`) with automatic polling fallback and stale/disconnected state banners.
- **Redesigned Dashboard Screen (`companion/src/components/screens/CoreTradingScreens.tsx`)**:
  - **Top Status Bar**: Displays MT5 connection with masked account (`****0001`), prominent `DEMO · LIVE_TRADING_ENABLED=false` locked safety badge, active schedule mode badge (`WEEKDAY_GOLD_MODE` / `WEEKEND_BTC_MODE`), active session + live 1-second UTC clock, ZMQ bridge ports (`5555/5556`), Telegram readiness button, and `Pause`, `Stop`, and `Close All` controls with two-step confirmation.
  - **6-Card KPI Row**: Displays Balance/Equity, Today P&L (`$` + `+R`), Daily Loss Used vs Limit, Total Drawdown vs Cap, Open Exposure (`Bot` / `Manual` / `Pending`), and Next Schedule Switch countdown.
  - **Live Institutional Chart (`companion/src/components/LiveTradingChart.tsx`)**: Built on `lightweight-charts` with symbol selector (`XAUUSD`, `USDJPY`, `BTCUSD`), timeframe selector (`M1`, `M5`, `M15`, `H1`, `H4`), shaded Risk/Reward zones, Entry line (`BUY`/`SELL`, lots, setup score), active SL (red), ghosted initial SL when tightened, `TP1`/`TP2` (green with R-multiples), live price tag with floating R, lifecycle event annotations (`BE+ Lock`, `Partial 50% @ TP1`), toggleable SMC overlays (`Liquidity PDL/PWH`, `FVG/OB`, `Structure MSS/CHoCH`, `Sessions`, `Trade Labels`), collision-aware label placement, and full-height responsive sizing.
  - **Right Column & Analytical Panels**: Engine Control & Supervisor card (`OBSERVE`, `DRY_RUN`, `DEMO_SCALPING`, `DEMO_FAST`, `DEMO_MANUAL_ASSIST`), Open Positions & Orders card with tighten-only SL enforcement (and disabled `Widen/Remove SL`), Live Trade Timeline, Risk Manager (`DEMO` / `PROP` / `LIVE` profile limits), Gold–USDJPY Inverse Coordination, Schedule & Instruments matrix, System Health & Drift Guards (`EA Heartbeat`, `Queue Depth`, `CUSUM/PSI`, `TCA`, `Error Centre count`), Manual Position Adoption, and Recent Trades table.
- **Pure Chart Math & Unit Tests (`companion/src/utils/tradeChartMath.ts`, `companion/src/utils/__tests__/tradeChartMath.test.ts`)**:
  - Added pure unit-tested utilities for R-multiple math, risk/reward zone geometry, tighten-only SL validation, collision-aware vertical label layout (`resolveLabelCollisions`), account masking, and schedule/session countdown calculation.

## [3.10.0] - 2026-11-10

### Added - Manual Position Adoption & Professional Trade Management (`src/manual_mgmt/`)
- **Isolation Guards & Accidental Closure Prevention `[SAFETY]`**:
  - Remediated universal position ingestion hazard in `src/execution/order_manager.py:get_active_positions(own_only=True)`: defaults to filtering strictly for bot-owned positions (`magic == config.magic_number`).
  - Added `[SAFETY]` guard to `agent/mt5_bot_agent.py:close_all`: manual trades are strictly preserved unless explicitly commanded with `include_manual=True`.
  - Added isolation guard to `src/core/orchestrator.py:reset_state()`: manual swing trades no longer block bot intraday resets.
  - Isolated orchestrator lifecycle management so only bot-owned positions trigger risk metrics updates, decay guard transitions, and scalper state shifts.
- **Deterministic Classification Hierarchy (`src/manual_mgmt/classifier.py`)**:
  - Deterministically classifies every MT5 position into `BOT_OWN`, `MANUAL`, `OTHER_EA`, `EXCLUDED`, or `UNKNOWN`.
  - Distinguishes manual discretionary trades (`pos.magic == 0` and opening deal reason in `CLIENT/MOBILE/WEB`) from external EAs (`pos.magic != 0` or `DEAL_REASON_EXPERT`).
  - Supports comment opt-out tags (`#bot:off`, `#ignore`) and symbol filtering.
- **Atomic State Persistence & User Supremacy (`src/manual_mgmt/registry.py`)**:
  - Thread-safe registry (`threading.RLock`) managing active adopted positions with atomic JSON file persistence (`state/manual_positions.json`).
  - **User Supremacy Invariant `[SAFETY]`**: Automatically detects when user manually modifies SL/TP directly in MT5, immediately ceding control and enforcing a 30-minute lockout timer (`lockout_until`).
- **Strategy Skills Assessor (`src/manual_mgmt/assessor.py`)**:
  - Evaluates manual positions using transferred 28-video strategy skills (`protected_swing_marker`, `swing_hierarchy`, `structure_momentum_monitor`, `trend_by_structure`, `five_check_model`, `stop_management_policy`).
  - Adopts naked positions (missing SL) and computes structure-based invalidation SL levels.
  - Calculates cost-covering Break-Even at `+1.0R` (`[VIDEO 12]`) and trailing stops behind confirmed swing pivots at `+1.5R` (`[VIDEO 15]`).
  - Detects winning continuation scale-in opportunities (`FULL` mode only).
- **Safety Policy Engine (`src/manual_mgmt/policy.py`)**:
  - **Real Account Barrier**: Hard-locked against real accounts unless `allow_real_account_management: true` is explicitly configured.
  - **Netting Account Isolation**: Automatically detects Netting accounts (`margin_mode == 1`) and forces `OBSERVE` mode.
  - **Tighten-Only Stop Policy**: Enforces Rulebook R9.3: mathematically prohibits moving a stop loss further away (widening risk) or removing a stop loss.
  - **Prohibits Averaging Down**: Strictly prohibits adding to losing positions or positions without SL secured at Break-Even.
  - Emergency Kill Switch integration (`state/PAUSE` and `config.pause_all`).
- **Safe Execution & Retries (`src/manual_mgmt/executor.py`)**:
  - Idempotent broker modifications with exponential backoff for transient retcodes (`10004`, `10018`, `10020`).
  - Updates registry immediately upon modification to eliminate false user-override flags.
  - Structured JSON audit logging to `logs/manual_management_audit.log`.
- **Replay Harness, Runbook & Verification**:
  - Created interactive CLI simulator `scripts/run_manual_replay.py` with support for `OBSERVE`, `PROTECT`, `ASSIST`, `FULL`, and user intervention testing.
  - Authored comprehensive operations runbook in `docs/manual_management_runbook.md`.
  - Added 13 unit tests in `tests/test_manual_management.py` (100% passing).


### Added - Institutional EA Cloud Pairing Code Authentication & Remote Control Engine
- **Interactive Pairing Flow (`agent/mt5_bot_agent.py`)**:
  - Implemented interactive terminal onboarding interface with step-by-step guidance to connect local MT5 to `https://Institutional EA Cloud`.
  - Automatic uppercase normalization, accidental whitespace trimming, and strict 6-character alphanumeric validation.
  - Interactive retry loop with clear diagnostic messaging (`INVALID CODE`, `EXPIRED CODE`, `ALREADY USED`, `NETWORK ERROR`, `SERVER ERROR`).
  - Supports non-interactive CLI pairing flag `python agent/mt5_bot_agent.py --pair <CODE>`.
- **Cloud API Integration (`/api/v1/bot`)**:
  - Direct integration with existing Institutional EA endpoints: `POST /bot/pairing/claim`, `POST /bot/heartbeat`, `POST /bot/commands/poll`, `POST /bot/commands/:id/ack`, `POST /bot/events/sync`.
  - Outbound-only HTTPS architecture; zero open inbound listening ports on the host machine.
  - Machine-bound credential store (`~/.institutional_ea_agent/credentials.enc.json`) and SQLite-backed offline event queue.
- **Real MT5 Status & Telemetry Synchronization**:
  - Heartbeat telemetry synchronizes live MT5 terminal connectivity, active bridge status, broker name, masked login (`***57798`), real account balance, equity, leverage, open positions, and local limits snapshot.
- **Signed Cloud Controls & Local Hard Ceilings (`agent/local_limits.json`)**:
  - Remote execution of `start`, `pause`, `resume`, `stop`, `close_all`, and `kill_switch`.
  - Enforces HMAC-SHA256 signature verification, replay protection with unique nonces, and 5-minute expiration checks.
  - Enforces local machine hard ceilings: cloud commands cannot increase risk percentage above local limit or force live trading without local physical confirmation.
- **Windows VPS Launchers & Diagnostics**:
  - Created `start_mt5_agent.bat` and `start_mt5_bot.bat` for Windows VPS operations.
  - Integrated Institutional EA agent pairing check into `scripts/selfcheck.py`.


## [3.8.0] - 2026-11-08

### Added - Canonical SMC Rulebook Alignment (`R1–R9`), SetupQualityGate (`G1–G8`), & Out-of-Sample Ablation
- **Canonical SMC Rulebook (`src/smc/smc_rulebook.py`, `docs/SMC_RULEBOOK.md`, `config/strategy_config.json`)**: Aligned `R1–R9` across all SMC/ICT detectors (`market_structure.py`, `structure_confirmation.py`, `liquidity.py`, `fvg_ob.py`, `mtf_analyzer.py`, `strategy_engine.py`, `cisd.py`, `trendline_liquidity.py`).
- **SetupQualityGate (`src/smc/setup_quality_gate.py`, `src/core/orchestrator.py`)**: Evaluates candidate setups across Hard Gates `G1–G8` and Soft Factors (`OFF`/`SHADOW`/`ENFORCE`), validated via 2.5-year out-of-sample ablation (`reports/smc_rulebook_phase4_validation.md`, `+1.031R` expectancy, `3.74` PF).
- **R9 Risk-Rule Enforcement**: Hard-capped risk per trade at `2.0%` (`1.0%` default), mandatory SL check (`stop_loss > 0`), and 3-layer never-widen-SL guard across `OrderManager`, `BridgeClient`, and `PythonBridgeEA.mq5`.
- **CI/CD & Repository Consolidation (`.github/workflows/ci.yml`, `scripts/verify_deep.py`)**: Consolidated all 6 branches into `main`, updated Golden Master canonical baseline (`8,640` decisions), and verified `294/294` passing tests.

## [3.7.0] - 2026-11-03

### Added - Structured Telegram Notification Layer & Live Trade Threading (`config/notifications.json`, `docs/NOTIFICATIONS.md`)
- **28 Typed Notification Events & Centralized HTML Templates (`src/notifications/events.py`, `src/notifications/templates/default_templates.py`)**:
  - Replaced raw-log Telegram dumps with 28 structured `@dataclass` payloads rendered by `TemplateRenderer` into clean 3–8 line HTML cards (`<code>` values, symbol-digit prices, thousands-separated money, signed `R` multiples, percentages, UTC + configurable local timezone footer `UTC+3`, HTML escaping, and safe 4,096-character splitting).
  - Plain-English MT5 retcode mapper (`map_retcode_to_plain_english`), account number masking (`****0001`), and automatic secret/token redaction (`sanitize_sensitive_text`).
- **3-Tier Noise Policy & State-Transition Alerting (`src/notifications/router.py`)**:
  - `LOUD` (sound on), `SILENT` (`disable_notification=True`), and `ON_DEMAND` (logged to disk for `/logs [N]` and `/last [N]`; never pushed by default).
  - Removed per-bar `"NO SETUP"` and 5/15-minute heartbeat spam; replaced with a single Pinned Status Card edited in place (`update_pinned_status_card`), optional periodic `HealthOK` ("running smoothly") check, and optional hourly Market-Watch digest (`/marketwatch on|off`).
  - State-transition alerting (`OK -> WARNING -> CRITICAL -> RECOVERED`) with cooldowns (`600s`), repeat merging (`"occurred N times in 10 min"`), escalation, and quiet hours (`/quiet <hours>`).
- **Live Trade Card Editing & Reply Threading (`src/notifications/router.py`, `src/notifications/telegram_transport.py`)**:
  - Posts `TRADE SETUP`, edits the card in-place to append a live timeline (`Opened -> Break-Even -> Partial TP -> Closed`), threads replies via `reply_to_message_id`, sends a separate `LOUD` message on close, and automatically falls back to a new card if `editMessageText` fails or the card was deleted.
- **Operator Commands, Inline Buttons & Noise-Source Fixes (`src/notifications/telegram_service.py`, `src/execution/bridge_server.py`)**:
  - Inline keyboard buttons (`Pause`, `Resume`, `Status`, `Positions`, `Close All` two-step confirmation) and commands `/status`, `/positions`, `/today`, `/week`, `/health`, `/marketwatch`, `/quiet`, `/logs`, `/preview_alerts` (sends all 28 sample cards labelled `🧪 [SAMPLE]`), all gated by strict `TELEGRAM_CHAT_ID` verification.
  - Fixed `"Insufficient M15 candle history (have 0, required 20)"` spam by deduplicating into a single warm-up progress card and one ready card when synchronized.
  - Fixed `/positions -> Provider unavailable` by wiring `positions_provider`, `balance_provider`, `pause_handler`, `resume_handler`, `closeall_handler`, and `killswitch_handler` in `PersistentBridgeServer.start()` and adding automatic retry + friendly fallback in `_handle_positions`.
  - Moved `Suppressed Alert Duplicates` counter out of `/status` into `/health`.

## [3.6.0] - 2026-11-03

### Added - Fast Mode Low-Latency Scalping Execution Layer (`config/fast_mode.json`)
- **Low-Latency Execution Path (`src/execution/persistent_socket.py`, `src/execution/async_queue.py`, `mql5/Experts/PythonBridgeEA.mq5`)**:
  - Stage-by-stage nanosecond latency tracking (`bar_received_ns -> analysis_done_ns -> checklist_passed_ns -> order_sent_ns -> fill_confirmed_ns`), requote count, slippage, and spread at entry per trade.
  - `NonBlockingExecutionQueue`: Queues Telegram dispatches, journaling, and chart drawing off the critical order path (`< 5µs` enqueue overhead).
  - `PersistentBridgeSocket` (`TCP_NODELAY`) and `LowLatencyOrderDispatcher`: Auto-detects/falls back across filling modes (`FOK`, `IOC`, `RETURN`), validates `stops_level` and `freeze_level`, enforces mandatory server-side SL/TP on every order, handles requotes/off-quotes with bounded retries that re-validate quote and spread before each retry, and uses deterministic `client_order_id` (`CID_<SYM>_<DIR>_<HASH>`) for 100% idempotency.
- **Scalp Entry Engine (`src/execution/fast_mode_engine.py`)**:
  - `PrecomputedSymbolState` cache refreshed on bar close so an entry trigger only executes light checks.
  - Evaluates closed candles on `M1`/`M5` aligned with `M15`/`H1` HTF bias and active session affinity.
  - Triggers on confirmed `BOS_CONFIRMED` after `CHoCH`, FVG/OB mitigation, or displacement + rejection candle/chart pattern.
  - Enforces spread $\le 10\%$ of SL distance, ATR floor/ceiling bounds, $\ge 2.0\text{R}$ target, post-trade cooldown (`120s`), and hourly rate cap (`3` trades/symbol/hour).
- **Fast Tick Exit Manager (`src/execution/fast_exit_manager.py`)**:
  - Tick-level evaluation: Break-even at `+0.5R` above spread+buffer, `50%` partial TP at `+1.0R` + confirmed swing/ATR trailing, time stop, momentum-failure exit on closed-bar breakdown, spread-spike SL freeze protection, session-end/rollover/news flatten, and MFE/MAE excursion tracking.
- **Speed Risk Guardrails (`src/risk/fast_risk_guard.py`)**:
  - Strict downward lot rounding (`normalize_volume_down`).
  - `ForceMinLotRiskFloor` and small-account minimum balance calculation + `DECISION` message (`"<SYMBOL> skipped: min lot (0.01) risks X% > Y% cap; needs about $Z balance or a cent/micro account"`).
  - Margin level guardrails: projected margin floor $\ge 300\%$ required for entry; critical margin floor $\le 150\%$ triggers immediate flatten + pause.
  - Combined open-risk cap, anti-stacking, anti-grid (no averaging down), anti-martingale (no lot increase after loss), consecutive-loss circuit breaker (`2` losses), and equity-velocity kill switch ($> 2.5\%$ floating loss in `60s`).
- **Always-On Watchdog & Remote Telegram Controls (`src/execution/watchdog.py`, `src/notifications/telegram_service.py`)**:
  - Heartbeat monitor, auto-reconnect with full state reconciliation against MT5 open positions, stale-tick guard (`5s`), clock drift check (`10s`), weekend guard, and graceful shutdown cancelling orphaned pending orders.
  - Telegram commands: `/fastmode on|off`, `/pause`, `/resume`, `/flatten` (strict `chat_id` verification), `/fastquality`, and `/margin`.
- **Walk-Forward Evaluation & Soak Test (`scripts/evaluate_fast_mode.py`, `scripts/soak_test_fast_mode.py`, `reports/fast_mode_performance.json`)**:
  - Walk-forward evaluation with realistic spread, commission, slippage, and `25ms` latency confirms Fast Mode improves net expectancy from `+0.144R` to `+0.358R` (`+0.214R` gain), increases Profit Factor from `1.37` to `6.21`, and reduces Max Drawdown from `12.06R` to `1.61R`.

## [3.5.0] - 2026-11-03

### Added - Professional Session-Aware Trading Architecture & Affinity Matrix
- **Dual Session Engine (`src/core/sessions.py`, `config/sessions.json`)**:
  - `ist_reference` profile: Static UTC schedule based on IST (UTC+5:30) reference windows: Asia (00:00–09:00 UTC), London (06:00–12:00 UTC), New York (12:30–17:30 UTC), and Best Window (12:30–17:30 UTC).
  - `market_local_dst` profile: Dynamic local market hours using deterministic rules and `zoneinfo` (`Europe/London`, `America/New_York`) with automatic DST adaptation.
  - Overlap detection (London / NY Overlap) and fail-safe broker UTC offset gating.
  - Transition buffers: Monday open skip (30m), Friday cutoff (20:00 UTC), handover cooldown (15m), and daily swap rollover blackout (21:55–22:15 UTC).
  - Backward compatibility: Preserves exact legacy method signatures (`get_current_session`, `evaluate_killzone`, `calculate_session_levels`).
- **Session × Symbol Affinity Matrix (`src/core/session_affinity.py`, `config/session_affinity.json`)**:
  - Canonical asset resolution stripping broker suffixes (`.m`, `m`, `_i`, `_raw`, `GOLD`, `USTEC`, `DJ30`).
  - Gating modes: `scored` (continuous confluence multiplier with minimum weight floor 0.20) vs `strict` (binary gate requiring weight $\ge 0.80$).
  - US Cash Open blackout window for equity indices (`NAS100`, `US30`): 14:00 – 15:00 UTC (14:30 UTC Cash Open $\pm$ 30 minutes).
- **Session Liquidity Engine (`src/smc/session_liquidity.py`, `src/smc/strategy_engine.py`)**:
  - Daily Asian range computation (Asia High, Low, Midpoint, Range pips).
  - Asia High/Low registered as institutional BSL/SSL liquidity pools.
  - London Judas Swing detection: Sweeps of Asian range extremes followed by candle close rejections inside the range (`SetupType.SESSION_SWEEP`).
- **Session Risk Controls & Correlation Guard (`src/risk/session_risk.py`, `src/execution/order_manager.py`)**:
  - Session budgets: Max 2 trades per session, max 2 consecutive losses circuit breaker, and 1.0% balance session loss cap.
  - Risk scaling multipliers: 0.50x risk in Asia, 1.00x in London/NY (only tightens risk, never loosens global limits).
  - Cross-pair correlation guard blocking concurrent same-direction exposure (e.g. `EURUSD` + `GBPUSD`).
  - Pre-trade checklist items #13–#16 seamlessly added to the 16-point execution checklist.
- **Interactive Telegram Controls (`src/notifications/telegram_service.py`)**:
  - `/session`: Displays current session status, time in session, time to close, and active window.
  - `/sessionstats`: Displays performance statistics broken down by session and affinity mode.
  - `/sessionmode strict|scored`: Dynamic switching between strict gating and scored confluence weighting.
  - `/sessionprofile ist_reference|market_local_dst`: Profile switching between IST reference and market local DST.
- **Empirical Walk-Forward Evaluation (`scripts/evaluate_sessions.py`)**:
  - Walk-forward multi-regime simulation comparing Baseline vs Scored vs Strict modes with transaction costs.
  - Demonstrates a **35.1% reduction in drawdown** under Scored Mode and a **58.2% reduction in drawdown** under Strict Mode.
  - Output metrics exported to `reports/session_performance.json` and fed to `ChampionChallengerEngine`.
- **Verification & Test Coverage**:
  - 185 automated tests passing (`Ran 185 tests in 105s. OK`).
  - Golden Master 8,640 decisions 100% bit-for-bit identical with session layer disabled by default (`"enabled": false`).
  - Deep verification 12/12 suites passing (100%).
  - MetaEditor compilation: 0 errors, 0 warnings.
  - Secret scan: 0 secrets found.

## [3.4.0] - 2026-11-03

### Added - Institutional Pattern Recognition & Multi-Factor Confluence Layer
- **Pluggable Pattern Engine (`src/patterns/`)**:
  - `PatternResult`, `ScoredPattern`, `PatternRegistry` supporting `CANDLE`, `CHART`, and `HARMONIC` families.
  - **51 Candlestick Detectors (`src/patterns/candlesticks.py`)**: Vectorized numpy array detectors with ATR-normalized ratios, prior trend slope evaluation, and Forex gap-equivalent handling ($\ge 0.30 \times \text{ATR}$). Includes all 19 reference chart patterns (with "Bullish Harboring" properly implemented as Bullish Harami Cross) plus 32 additional detectors.
  - **16 Chart Patterns & 4 Harmonics (`src/patterns/chart_patterns.py`)**: Head & Shoulders (and Inverse), Double/Triple Tops & Bottoms, Ascending/Descending/Symmetrical Triangles, Wedges, Flags, Pennants, Rectangles, Channels, Cup & Handle, Rounding Bottom, Broadening, Diamond, Island Reversal, and Gartley, Bat, Butterfly, Crab harmonics. Strictly requires candle-close breakout confirmation (wicks ignored) with measured-move target projection.
- **Context Scorer & Confluence Rubric (`src/patterns/context.py`)**:
  - 0–100 composite confluence score evaluated across Order Block/FVG location (30%), HTF trend alignment (25%), BOS structure confirmation (20%), confirmation candle close (10%), volume expansion (10%), and session/news regime (5%).
  - Automatic opposing signal conflict cancellation (score = 0, no trade) and same-direction overlap de-duplication with stack synergy bonus.
  - Gated trade execution: requires score $\ge 65.0$ and $\text{R:R} \ge 2.0$.
- **Strategy Engine Integration (`src/patterns/integration.py`, `src/smc/strategy_engine.py`)**:
  - Clean modular hook delivering `PATTERN_CONFLUENCE` setups to the execution pipeline. Default `enabled: false` in `config/patterns_config.json` guaranteeing 100% bit-for-bit backward compatibility.
- **Empirical Evidence & Evaluation Script (`scripts/evaluate_patterns.py`)**:
  - Multi-regime walk-forward splits reporting sample size, win rate, expectancy, profit factor, and max drawdown with transaction costs.
  - Exported to `reports/pattern_performance.json` with empirical classifications (`ENABLE`, `DISABLE_OR_TUNE`, `INSUFFICIENT_SAMPLE`).
- **Telegram Controls (`src/notifications/telegram_service.py`)**:
  - `/patterns on|off` toggles global pattern layer.
  - `/pattern <name> on|off` enables/disables specific detectors.
  - `/patternstats` displays top-performing patterns with statistical edge.
- **Verification & Test Coverage**:
  - 164 automated tests passing (`Ran 164 tests in 89s. OK`).
  - Golden Master 8,640 decisions 100% bit-for-bit identical.
  - Deep verification 12/12 suites passing (100%).
  - MetaEditor: 0 errors, 0 warnings.
  - Secret scan: 0 secrets found.

## [3.3.0] - 2026-11-03

### Added - 6-Phase Advanced Quantitative Execution Subsystems
- **Phase 1: CHoCH-Warning -> BOS-Confirmation State Machine (`src/smc/structure_confirmation.py`)**:
  - Deterministic closed-candle state machine (`IDLE -> CHOCH_WARNING -> PULLBACK -> BOS_CONFIRMED -> FAILED_TRAP`).
  - Gated entries behind BOS confirmation; anchored SL behind confirmed LH/HL.
- **Phase 2: Locked Immutable Trade Plan (`src/core/contracts.py`, `src/execution/order_manager.py`)**:
  - Immutable `TradePlan` dataclass binding entry, SL, TP, lots, risk %, R:R, and structural state.
  - Plan lifecycle shifts (break-even, trailing, partials) logged as explicit immutable `PlanAmendment` records.
- **Phase 3: Monte Carlo "Time Machine" Replay Gate (`src/risk/replay_gate.py`)**:
  - Vectorized block-bootstrap simulation over 10,000 M15 price paths (<2s runtime, deterministic trade seed).
  - Pre-trade gating on $P(\text{target}) > P(\text{stop}) + \text{edge}$ and minimum expected R.
  - Monte Carlo trade-result sequence drawdown estimation in `scripts/run_backtest.py`.
- **Phase 4: Human Confirm Gate & Paper Shadow Journal (`src/monitoring/shadow_journal.py`, `src/notifications/telegram_service.py`)**:
  - Interactive operator confirmation (120s timeout) for LIVE/PROP modes with `/confirm_mode on|off`.
  - DEMO mode auto-executes; unauthorized chats rejected.
  - Forward tracking of taken and rejected setups; `/shadow_report` command.
- **Phase 5: Multi-Symbol Opportunity Scanner & News Blackout (`src/smc/symbol_scanner.py`, `src/smc/news_filter.py`)**:
  - 5-factor scoring model ranking symbols on M15 close: Structure, HTF alignment, Spread/ATR, Session liquidity, News proximity.
  - High-impact macroeconomic calendar blackout window (15m before/after).
- **Phase 6: Exit Machine (`src/risk/trade_management.py`, `config/risk_config.json`)**:
  - Configurable optional exit rules (default OFF): Time Stop (X bars), End-of-Session Flatten, 1.0R Partial + BE, Structure-Based Swing Trailing.
  - All exit actions logged at `[TRADE]` level.
- **Verification & Test Coverage**:
  - 152 automated tests passing (`Ran 152 tests in 78s. OK`).
  - Golden Master 8,640 decisions 100% bit-for-bit identical.
  - Deep verification 12/12 suites passing (100%).
  - MetaEditor: 0 errors, 0 warnings.
  - Secret scan: 0 secrets found.

## [3.2.0] - 2026-11-03

### Added - CHoCH-Warning -> BOS-Confirmation State Machine & Structure Lifecycle
- **Market Structure Confirmation Module (`src/smc/structure_confirmation.py`)**:
  - Deterministic state machine tracking `IDLE -> CHOCH_WARNING -> PULLBACK -> BOS_CONFIRMED -> FAILED_TRAP`.
  - **CHoCH = Warning Only**: Candle close confirmation required (`require_close_break: true`); wick breaks strictly ignored. CHoCH alone cannot trigger trades.
  - **Pullback & Retracement Validation**: Requires confirmed Lower High (bearish) or Higher Low (bullish) relative to pre-CHoCH extreme before BOS eligibility.
  - **BOS Confirmation**: Unlocks trade entry only after candle close breaks the post-CHoCH impulse extreme.
  - **Trap Invalidation**: Closes beyond pre-CHoCH extreme are classified as `FAILED_TRAP`, reset prior trend, and recorded.
  - **Configurable Timeouts**: Warnings expire back to `IDLE` after `choch_timeout_bars` (default 20).
- **Strategy Engine Gating (`src/smc/strategy_engine.py`)**:
  - Gated candidate execution when `allow_choch_only_entries: false`.
  - Rejections logged at `DECISION` level with clear diagnostics (`"CHoCH only, awaiting BOS"`, `"CHoCH failed - trapped"`).
  - Stop loss anchored to the confirmed Lower High (shorts) or Higher Low (longs) for structural invalidation protection.
- **Pre-Trade Checklist Item #11 (`src/execution/order_manager.py`)**:
  - Validates "Structure confirmed (BOS after CHoCH)" before sending order requests.
- **Telegram Multi-Tier Notifications (`src/notifications/telegram_service.py`)**:
  - CHoCH detected $\rightarrow$ `DECISION`/`INFO` (silent digest queue).
  - BOS confirmed + valid setup $\rightarrow$ `SIGNAL` (immediate loud alert).
  - Failed CHoCH / Trap $\rightarrow$ `DECISION` (silent digest queue).
- **MQL5 EA Chart Visuals (`mql5/Experts/PythonBridgeEA.mq5`)**:
  - Optional inputs to draw CHoCH (dashed line + label) and BOS (solid line + label) on MT5 charts, with failed CHoCH lines rendered in gray (`clrDarkGray`).
  - Native MetaEditor compilation verified: 0 errors, 0 warnings.
- **Automated Test Coverage (`tests/test_structure_confirmation.py`)**:
  - Full synthetic test suite covering bearish/bullish confirmation sequences, trap invalidations, wick-only rejections, and timeout expirations.

## [3.1.0] - 2026-11-03

### Added - Quant Best-Practice Upgrade (Stages 1-3)
- **Broker Adapter Layer (`src/adapters/`)**:
  - `BrokerAdapter` abstract interface with `LiveMT5Broker` and `SimBroker`.
  - High-fidelity simulation mechanics: half-spread + volatility slippage, institutional commissions, margin verification, and SL/TP boundary triggers.
- **Data & Feature Pipeline (`src/features/`)**:
  - Zero-lookahead feature extraction: ATR(14), EMA(20, 50, 200), RSI(14), ADX(14), Bollinger Bands, fractal swings, and MTF alignment.
- **Modular Strategy Plug-in Architecture (`src/strategies/`)**:
  - `SignalModule`, `FilterModule`, `ExitModule`, and `SizingModule` composable pipeline with `LegacySMCStrategy` adapter.

## [3.0.0] - 2026-11-02

### Added - Modern Quantitative Upgrade & Account Adaptation Suite
- **Stage 0 & 0A: Baseline Data & Account-Size Adaptation ($5 Minimum Floor)**:
  - Account tiers in `config/account_tiers.json`: `BELOW_FLOOR` (<$5), `MICRO` ($5-$25), `MINI` ($25-$100), `SMALL` ($100-$500), `STANDARD` ($500-$5,000), `LARGE` (>$5,000) with 5% boundary hysteresis.
  - Universal Cent Account detection (USC, EUC, GBX) with transparent 100:1 unit conversion and dual-unit logging.
  - Single shared mathematical position sizing algorithm strictly enforcing downward volume step rounding, `OrderCalcProfit` dollar verification, and operator micro-account high risk gating.
  - Symbol Affordability Scanner (`src/risk/affordability.py`) classifying pairs into `TRADABLE`, `MARGINAL`, and `BLOCKED` with automated ranking by transaction drag.
  - Multi-timeframe historical candle loader (`src/data/historical_loader.py`) with automatic broker UTC offset detection and local caching outside git.
  - Real broker cost profiler (`src/data/cost_model.py`) reporting hourly spread distributions, tick values, and swap rates.
  - Property-based tests verifying zero ceiling breaches across random balances, prices, and stop distances.
  - Live demo execution verification on MT5 demo account (#1200057798) placing and closing 0.01 lot EURUSD with verified risk metrics.

- **Stage 1: Quantitative Validation Suite (`src/learning/validation/`)**:
  - Purged and embargoed walk-forward engine eliminating serial correlation and lookahead contamination.
  - Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio (DSR) and Combinatorial Symmetric Cross-Validation (CSCV) Probability of Backtest Overfitting (PBO).
  - 5,000-resample Monte Carlo permutation engine estimating ending equity distributions and ruin/breach probabilities for Demo (10%), Live (6%), and Prop (4%) drawdown limits.
  - Friction stress-testing matrix evaluating performance at 1.0x, 1.5x, and 2.0x transaction drag.

- **Stage 2: Dynamic Regime Detection (`src/regime/`)**:
  - Feature extraction engine: realized volatility, ATR percentiles, ADX, MTF trend slope, session codes, and spread ratios.
  - Gaussian volatility state classifier mapping conditions into SCALP, HOLD, and NO_TRADE.
  - Feature flag `regime_detection` with non-intrusive shadow mode logging and OOS expectancy tracking.

- **Stage 3: Meta-Labeling Engine (`src/learning/meta/`)**:
  - Triple-barrier labeling algorithm (take profit, stop loss, and vertical bar expiration barriers) computing exact return in R.
  - Strictly causal point-in-time feature extractor with runtime timestamp assertions preventing future lookahead.
  - Platt-calibrated regularized classifier with Brier score tracking and SHA-256 model weight registry.
  - Risk scaling invariant: can only downscale risk (<= 1.0x) or skip; never upscales risk.

- **Stage 4: Volatility and Risk Modeling (`src/risk/`)**:
  - GARCH(1,1) conditional variance forecasting, RiskMetrics EWMA ($\lambda=0.94$), HAR-RV, and ATR fallback.
  - Fractional Kelly criterion engine capping allocation strictly by tier target risk, with mathematical zero floor on non-positive expectancy.
  - Multi-tier drawdown throttle (100% -> 70% -> 40% -> 0% pause at 80% buffer utilization) and 99% CVaR tail risk alerting.
  - Portfolio exposure engine: strictly max 1 open position on MICRO/MINI tiers, net currency exposure caps, cross-pair rolling correlation gating (>0.70), and PCA concentration ratio.

- **Stage 5: Execution Quality and Analytics (TCA) (`src/execution/analytics/`)**:
  - Per-order TCA auditing: intended vs filled price, slippage points and USD, latency, retcodes, and transaction drag.
  - Time-of-day spread filter blocking rollover hours (21:00-23:00 UTC) and spreads exceeding 2.0x hourly median.
  - Passive limit order engine with expiration.
  - Idempotent request manager with SHA-256 request IDs preventing duplicate orders on network retries.
  - Automated weekly execution cost reporting for Telegram and Markdown artifacts.

- **Stage 6: Monitoring and Decay Detection (`src/monitoring/`)**:
  - CUSUM strategy decay guard with 3-tier sigma alerts: Warning (2.0s), Reduced Risk (2.5s), Pause (3.0s, requiring operator `/run`).
  - Feature drift detection using Population Stability Index (PSI) and Kolmogorov-Smirnov 2-sample tests over rolling 100 bars.

## [1.4.0] - 2026-11-22

### Added
- **Live MT5 Market Data Feed (`src/data/market_feed.py`)**: Real-time `symbol_info_tick`, `(ask - bid) / point` spread calculation, `copy_rates` OHLC candles, per-symbol rounding, canonical-to-broker `.m` symbol mapping (`XAUUSD -> XAUUSD.m`, `USDJPY -> USDJPY.m`, `BTCUSD -> BTCUSD.m`) with strict startup validation, freshness & market-closed entry guards, and broker-to-UTC time conversion.
- **Read-Only Live Feed Verifier (`tools/verify_market_feed.py`)** and **Hardcoded Data Guard (`tools/scan_hardcoded_data.py` + `tests/test_no_hardcoded_market_data.py`)** enforcing the REAL DATA ONLY policy across production code.
- **Trade Replay (`TradeReplayModal.tsx` & `GET /api/trades/replay`)**: Replay any real closed trade over real MT5 historical candles with Play/Pause/Step/Speed controls, real execution events, and linked PNG chart screenshots.
- **Chart Screenshots on Trade (`POST/GET /api/trades/screenshots`)**: Automatic and manual PNG export via `lightweight-charts` saved under gitignored `data/screenshots/`.
- **Real-Data Analytics (`AnalyticsScreen` & `GET /api/analytics/equity`)**: Equity curve from real MT5 `balance_snapshots`, cumulative P&L, cumulative R, and drawdown charts with symbol and date-range filters and honest empty states.
- **Live Signal Grid (`SignalsGridScreen` & `GET /api/signals`)**: Real-time bot setup table with symbol/status filters and click-to-chart navigation.
- **Alert Centre (`AlertCentreScreen` & `/api/alerts`)**: In-app alert log, per-type event toggles, quiet hours (UTC), rate limits, deduplication, and Telegram delivery status logging.
- **Mobile Companion View**: Responsive read-only phone layout (`< 768px`) with bottom tab navigation (`Dashboard`, `Positions`, `Signals`, `Alerts`) and two-step Pause only, plus `docs/MOBILE_REMOTE_ACCESS.md`.

### Removed
- Purged all hardcoded/mock market prices (`2668.40`, `91420`, `154.32`), fake balances (`$25,480`, `$25,728.30`, `$50,420.50`), fake tickets (`88412091`), synthetic candle noise generator (`seededNoise`), and simulated order execution fallbacks from `companion/src/services/dashboardDataAdapter.ts` and `companion/src/services/ipc.ts`.
