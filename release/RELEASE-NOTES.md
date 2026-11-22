# MT5-001 Companion — Release Notes v1.2.0

**Official Release for the ArcadeFX Trading Ecosystem**  
**Release Date:** November 11, 2026  
**Artifact:** `MT5-001-Companion-Setup.exe`  
**Architecture:** Windows 10 / Windows 11 (64-bit)  
**SHA-256 Checksum:** `6957cbddf60820a365057595adb200a30d462898a77cff890805619b0b4ebcba`

---

## Overview

The MT5-001 Companion desktop application provides institutional-grade trading supervision, telemetry, and bridge communication between local MetaTrader 5 terminals, the autonomous quantitative trading engine, and the **ArcadeFX.live** cloud portal.

---

## Key Features & Improvements in v1.2.0

### 1. ArcadeFX Unified Design System Redesign
- **Dual Visual Themes:** Complete light theme (`#FFFFFF` background, `#F5F5F5` cards, `#FF444F` accent) and dark theme (`#101113` background, `#1B1D21` cards, `#FF525C` accent) with persistent local storage state.
- **Header & Navigation:** Includes real-time UTC/Local clocks, ArcadeFX cloud connection status pill, Telegram connection pill, dynamic trading status badge, and an instant theme toggle.
- **Metrics Dashboard:** High-contrast mark-to-market metrics for Balance, Equity, Daily PnL, Floating Profit/Loss, Margin Level, and Active Trades.
- **Interactive Modals:** Redesigned Settings modal, Cloud Pairing modal, Telegram Remote Control modal, MT5 Setup Wizard, Pre-Flight Diagnostics, and 7-Step Onboarding flow.

### 2. Standalone Zero-Dependency Windows Packaging
- **Self-Contained Python Sidecars:** Includes frozen `mt5_bridge_server.exe`, `mt5_trading_engine.exe`, and `mt5_bot_agent.exe` compiled with PyInstaller. End users do not need to install Python, pip, or external runtime libraries.
- **Automatic Asset Extraction:** Automatically packages and provides `PythonBridgeEA.mq5` and default runtime configuration files upon first launch.
- **Preserved User Configuration:** Safe NSIS installer respects existing user data in `%APPDATA%\MT5-OO1 Companion`. Upgrades and reinstalls do not delete active trading settings, logs, or pairings.

### 3. Preserved Architecture & Safety Mechanisms
- **Port Contracts:** Unmodified TCP socket ports `5555` (MQL5 EA Bridge) and `5556` (Local IPC Switchboard).
- **Execution Safeguards:** Engine defaults to DEMO/SIMULATION mode with real account protection guards.
- **Circuit Breaker:** Hard daily drawdown threshold (3.0% default) and target risk caps enforced.
- **Emergency Liquidation:** Single-click "Close All" positions function with confirmation protection.

---

## Installation & Upgrade Instructions

1. Download `MT5-001-Companion-Setup.exe` from your ArcadeFX.live dashboard.
2. Verify the SHA-256 checksum:
   ```powershell
   Get-FileHash -Algorithm SHA256 .\MT5-001-Companion-Setup.exe
   ```
3. Run the installer. Choose standard installation directory or custom location.
4. Launch the application. The Onboarding Wizard will guide pairing with your ArcadeFX account and deploying `PythonBridgeEA.mq5` into your MetaTrader 5 terminal.
