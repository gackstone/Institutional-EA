<#
.SYNOPSIS
    Uninstalls Arcade Fx MT5 Supervisor Windows Scheduled Task and terminates running instances.
#>

$TaskName = "ArcadeFX_MT5_Supervisor"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$LockFile = Join-Path $ProjectRoot "logs\supervisor.lock"

Write-Host "=========================================================================" -ForegroundColor Yellow
Write-Host "  ARCADE FX - MT5 SUPERVISOR UNINSTALLER" -ForegroundColor Yellow
Write-Host "=========================================================================" -ForegroundColor Yellow

# 1. Stop and remove Scheduled Task
Write-Host "Stopping and removing Windows Scheduled Task '$TaskName'..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 2. Remove User Startup folder fallback launcher if present
$StartupDir = [Environment]::GetFolderPath('Startup')
$VbsFile = Join-Path $StartupDir "ArcadeFX_MT5_Supervisor.vbs"
if (Test-Path $VbsFile) {
    Write-Host "Removing User Startup launcher ($VbsFile)..." -ForegroundColor Cyan
    Remove-Item $VbsFile -Force -ErrorAction SilentlyContinue
}

# 3. Terminate running supervisor if active via lockfile
if (Test-Path $LockFile) {
    try {
        $LockContent = Get-Content $LockFile -Raw | ConvertFrom-Json
        $PidToStop = $LockContent.pid
        if ($PidToStop) {
            Write-Host "Stopping active supervisor process (PID: $PidToStop)..." -ForegroundColor Cyan
            Stop-Process -Id $PidToStop -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

# 4. Clean up any leftover child processes
try {
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
        $_.CommandLine -like "*start_bot.py*" -or $_.CommandLine -like "*run_bridge_server.py*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {}

Write-Host "SUCCESS: $TaskName has been uninstalled." -ForegroundColor Green
