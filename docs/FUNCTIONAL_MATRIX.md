# Companion Functional Audit Matrix

End-to-end plumbing trace for every interactive action across all Companion screens (`UI -> preload.cjs -> IPC -> main.cjs -> HTTP -> Control Service -> MT5/ZMQ -> UI`).

| Screen | Action / Element | UI Handler | Preload / IPC | Backend Route / Handler | Status |
|---|---|---|---|---|---|
| **Global Top Bar / Sidebar** | Service Status Pill + `Reconnect` | `handleReconnectService` (`App.tsx`) | `reconnect-control-service` / `onControlServiceStatus` | Electron supervisor restarts `mt5_control_service` and polls `GET /health` | **VERIFIED** |
| **Dashboard** | `Pause` / `Resume` | `executeControlAction` (`CoreTradingScreens.tsx`) | `control-request` | `POST /api/engine/pause`, `POST /api/engine/resume` | **VERIFIED** (offline fails cleanly with MT5 safety note) |
| **Dashboard** | `Stop` / `Clear Stop` | `executeControlAction` (`CoreTradingScreens.tsx`) | `control-request` | `POST /api/engine/stop`, `POST /api/engine/clear-emergency-stop` | **VERIFIED** |
| **Dashboard** | `Close All` (2-step confirm) | `handleConfirmModalAction` (`CoreTradingScreens.tsx`) | `control-request` | `POST /api/trades/close-all-bot` | **VERIFIED** (mocked MT5; never touches live orders in tests) |
| **Dashboard** | Live Chart (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m` × `M1`..`H4`) | `loadCandles` (`CoreTradingScreens.tsx`) | `control-request` | `GET /api/market/candles` (`MT5SyncService.get_candles`) | **VERIFIED** (returns accurate `status_reason` when closed/offline) |
| **Dashboard** | Chart Screenshot PNG | `handleSaveScreenshot` | `control-request` | `POST /api/trades/screenshots`, `GET /api/trades/screenshots/file` | **VERIFIED** (stored in writable `data_dir/data/screenshots`) |
| **Dashboard** | KPIs & Status Chips (Balance, Equity, DD, ZMQ 5555/5556) | `refreshStatus` (`App.tsx`) | `control-request` + SSE `/api/events` | `GET /api/status` (`MT5SyncService.get_snapshot` + real TCP probe) | **VERIFIED** |
| **Positions** | `BE+`, `Tighten SL`, `Close 50%`, `Close` | `PositionsScreen` (`ExecutionRiskScreens.tsx`) | `control-request` / `close-position` | `POST /api/trades/modify`, `POST /api/trades/close` | **VERIFIED** (tighten-only R9.3 validated) |
| **Signals** | Live Signal Grid + Jump to Chart | `SignalsScreen` (`SignalsAlertsScreens.tsx`) | `control-request` | `GET /api/signals` | **VERIFIED** |
| **Alerts** | Alert Centre + Save Settings + Test Alert | `AlertsScreen` (`SignalsAlertsScreens.tsx`) | `control-request` | `GET /api/alerts`, `POST /api/alerts/settings`, `POST /api/alerts/test` | **VERIFIED** |
| **Trade History** | History Table + Trade Replay Modal | `TradeHistoryScreen`, `TradeReplayModal` | `control-request` | `GET /api/trades/history`, `GET /api/trades/replay` | **VERIFIED** |
| **Analytics** | Equity Curve, Net P&L, Profit Factor | `AnalyticsScreen` (`MonitoringSettingsScreens.tsx`) | `control-request` | `GET /api/analytics/equity` | **VERIFIED** |
| **MT5 Terminal** | `Scan` | `MT5ConnectionScreen.scan` | `scan-mt5-terminals` | `scanMT5Terminals()` (`main.cjs`, matches `origin.txt`, reads `#property version`, `.ex5`) | **VERIFIED** |
| **MT5 Terminal** | `Sync MT5` | `MT5ConnectionScreen.handleConnect` | `control-request` | `POST /api/mt5/connect` (passes `terminal_path`, surfaces `mt5.last_error()`) | **VERIFIED** |
| **MT5 Terminal** | `Deploy EA` | `MT5ConnectionScreen.handleDeployEA` | `deploy-ea` -> `control-request` | `POST /api/mt5/deploy-ea` (`deploy_ea_pipeline`: DEMO guard, backup, SHA-256 copy, `metaeditor64.exe /compile`, rollback, `common.ini` check) | **VERIFIED** |
| **MT5 Terminal** | `Launch` | `MT5ConnectionScreen` | `launch-mt5` | `main.cjs` (duplicate-instance guard; tracks PID) | **VERIFIED** |
| **Operations** | Run Allowlisted Ops + Audit | `OperationsCentreScreen` | `control-request` | `GET /api/operations`, `POST /api/operations/run` | **VERIFIED** |
| **Logs** | Filter / Clear Event Logs | `LogsScreen` | `control-request` | `GET /api/logs`, `POST /api/logs/clear` | **VERIFIED** |
| **System Health** | Live Startup & Runtime Self-Check | `SystemHealthScreen` | `control-request` | `GET /api/health/selfcheck`, `GET /api/audit` | **VERIFIED** |
| **Settings** | Telegram / Pairing / Glossary | `SettingsScreen` | `get-telegram-status`, `get-pairing-status` | Electron config + `POST /api/telegram/test` | **VERIFIED** |
