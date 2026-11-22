# MT5-001 Adaptive Trading Intelligence (ATI) — Windows PowerShell Deployment & Run Guide

## 1. Prerequisites & Environment Check

Open a Windows PowerShell terminal as Administrator or standard user in the repository root:

```powershell
# Navigate to repository root
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"

# Verify Git status
git status

# Verify Python 3.12 Virtual Environment
.\.venv\Scripts\python.exe --version
```

---

## 2. Verify Database & Directory Structure

The ATI subsystem automatically creates and manages its SQLite persistence at `data/ati_intelligence.db`.

```powershell
# Ensure data and config directories exist
if (!(Test-Path "data")) { New-Item -ItemType Directory -Path "data" }
if (!(Test-Path "config")) { New-Item -ItemType Directory -Path "config" }
```

---

## 3. Configuration Verification

Inspect `config/ati_config.json` to confirm safe defaults (`OBSERVATION` mode, live trading disabled):

```powershell
Get-Content config/ati_config.json | ConvertFrom-Json | Format-Custom
```

Key Safety Invariants in `config/ati_config.json`:
- `"mode": "OBSERVATION"`
- `"auto_promotion": false`
- `"autonomous_code_changes": false`
- `"approved_symbols": ["XAUUSD", "BTCUSD", "USDJPY"]`
- `"allow_live_trading_activation": false`

---

## 4. Run Automated Test Suite

Execute the dedicated ATI test suite to verify full functionality:

```powershell
# Run the complete ATI test suite
.\.venv\Scripts\python.exe -m pytest tests\test_ati_historian_and_normalization.py tests\test_ati_auditor.py tests\test_ati_learning.py tests\test_ati_laboratory_and_counterfactual.py tests\test_ati_improvement_and_safety.py tests\test_ati_integration_and_api.py -v
```

Expected result: `26 passed in ~3.2s`.

Run the core regression test suite:

```powershell
# Run core system regression tests
.\.venv\Scripts\python.exe -m pytest tests\test_specialized_three_instrument_universe.py tests\test_cent_account_compatibility.py tests\test_position_sizing.py tests\test_remediation_compliance.py -v
```

Expected result: `80 passed in ~7.6s`.

---

## 5. Starting the System with ATI

### Option A: Launch Bot Engine with ATI in Observation Mode
```powershell
# Run bot engine in safe dry-run / observation mode
.\.venv\Scripts\python.exe scripts\start_bot.py --dry-run
```

### Option B: Launch Local Control Service (Companion Backend) with ATI Endpoints
```powershell
# Start Companion Control Service (port 8765)
.\.venv\Scripts\python.exe companion\service\main.py --host 127.0.0.1 --port 8765
```

---

## 6. Querying ATI via Localhost REST API

Once the Control Service is running, query ATI endpoints via PowerShell:

```powershell
# Read companion authentication token
$Token = Get-Content state\companion_token.txt -ErrorAction SilentlyContinue

# Query ATI Status
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/status" -Headers @{ "Authorization" = "Bearer $Token" }

# Trigger Trade History Synchronization
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/sync" -Method POST -Headers @{ "Authorization" = "Bearer $Token" }

# Query Forensic Audits
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/audits" -Headers @{ "Authorization" = "Bearer $Token" }

# Query Daily Intelligence Report
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/reports/daily" -Headers @{ "Authorization" = "Bearer $Token" }

# Query Execution Quality Metrics
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/execution" -Headers @{ "Authorization" = "Bearer $Token" }
```

---

## 7. Emergency Rollback

If a candidate parameter modification ever needs to be reverted, invoke rollback immediately:

```powershell
# Revert active configuration to previous snapshot
$Body = @{ reason = "Immediate operator rollback" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ati/rollback" -Method POST -Body $Body -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $Token" }
```
