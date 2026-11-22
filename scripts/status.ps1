# Status script for Institutional EA MT5 Supervisor and Child Services

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$LogsDir = Join-Path $ProjectRoot "logs"
$LockFile = Join-Path $LogsDir "supervisor.lock"
$TaskName = "InstitutionalEA_MT5_Supervisor"

Write-Host "=========================================================================" -ForegroundColor Cyan
Write-Host "  INSTITUTIONAL EA - MT5 BOT AND BRIDGE SUPERVISOR STATUS REPORT" -ForegroundColor Cyan
Write-Host "=========================================================================" -ForegroundColor Cyan

# 1. Windows Auto-Start Status (Task Scheduler or User Startup Folder)
Write-Host ""
Write-Host "[1. Windows Auto-Start Registration]" -ForegroundColor Yellow
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$StartupVbs = Join-Path ([Environment]::GetFolderPath('Startup')) "InstitutionalEA_MT5_Supervisor.vbs"
if ($Task) {
    $TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "  Method       : Windows Scheduled Task ($TaskName)" -ForegroundColor Green
    Write-Host "  State        : $($Task.State)" -ForegroundColor Cyan
    Write-Host "  Last Run     : $($TaskInfo.LastRunTime)"
    Write-Host "  Last Result  : $($TaskInfo.LastTaskResult)"
} elseif (Test-Path $StartupVbs) {
    Write-Host "  Method       : Windows User Startup Folder (Zero-Admin Mode)" -ForegroundColor Green
    Write-Host "  Launcher     : $StartupVbs" -ForegroundColor Cyan
} else {
    Write-Host "  Status       : Not registered (Install via: powershell -File scripts\install_autostart.ps1)" -ForegroundColor Gray
}

# 2. Supervisor Process & Lockfile Status
Write-Host ""
Write-Host "[2. Supervisor Process]" -ForegroundColor Yellow
if (Test-Path $LockFile) {
    try {
        $LockData = Get-Content $LockFile -Raw | ConvertFrom-Json
        $SupPid = $LockData.pid
        $Proc = Get-Process -Id $SupPid -ErrorAction SilentlyContinue
        if ($Proc) {
            Write-Host "  Status       : RUNNING (PID: $SupPid)" -ForegroundColor Green
            Write-Host "  Start Time   : $($Proc.StartTime)"
            $MemMb = [math]::Round($Proc.WorkingSet64 / 1MB, 2)
            Write-Host "  Memory       : $MemMb MB"
        } else {
            Write-Host "  Status       : STALE LOCK (PID $SupPid not found)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Status       : Lockfile corrupted" -ForegroundColor Red
    }
} else {
    Write-Host "  Status       : STOPPED (No active lockfile)" -ForegroundColor Gray
}

# 3. MT5 Terminal Process
Write-Host ""
Write-Host "[3. MetaTrader 5 Terminal]" -ForegroundColor Yellow
$Mt5Procs = Get-Process -Name "terminal64", "terminal" -ErrorAction SilentlyContinue
if ($Mt5Procs) {
    foreach ($p in $Mt5Procs) {
        Write-Host "  Process      : $($p.Name).exe (PID: $($p.Id)) - RUNNING" -ForegroundColor Green
    }
} else {
    Write-Host "  Process      : CLOSED (terminal64.exe not running)" -ForegroundColor Yellow
}

# 4. Bridge Server Ports & Socket Probe
Write-Host ""
Write-Host "[4. MT5 Bridge Server Ports (5555 / 5556)]" -ForegroundColor Yellow

# Test Port 5555 (EA Socket)
$p5555 = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", 5555, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(1500, $false)
    if ($success -and $tcp.Connected) {
        $p5555 = $true
        $tcp.EndConnect($iar)
    }
    $tcp.Close()
} catch {}

if ($p5555) {
    Write-Host "  Port 5555 (EA Socket)  : ONLINE (Accepting connections)" -ForegroundColor Green
} else {
    Write-Host "  Port 5555 (EA Socket)  : OFFLINE (Port 5555 not listening)" -ForegroundColor Gray
}

# Test Port 5556 (IPC Socket)
$p5556 = $false
$ipcDetails = ""
try {
    $client = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 5556)
    $stream = $client.GetStream()
    $stream.ReadTimeout = 2000
    $stream.WriteTimeout = 2000
    $msg = [System.Text.Encoding]::UTF8.GetBytes("{""action"": ""STATUS""}`n")
    $stream.Write($msg, 0, $msg.Length)
    $buffer = New-Object byte[] 4096
    $bytes = $stream.Read($buffer, 0, $buffer.Length)
    $resp = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $bytes).Trim()
    $client.Close()
    if ($resp) {
        $p5556 = $true
        $json = $resp | ConvertFrom-Json
        $ipcDetails = "Active EA Clients: $($json.active_connections_count) | Status: $($json.status)"
    }
} catch {}

if ($p5556) {
    Write-Host "  Port 5556 (IPC Socket) : ONLINE ($ipcDetails)" -ForegroundColor Green
} else {
    Write-Host "  Port 5556 (IPC Socket) : OFFLINE" -ForegroundColor Gray
}

# 5. Child Processes (Active Bridge & Bot)
Write-Host ""
Write-Host "[5. Supervised Child Processes]" -ForegroundColor Yellow
try {
    $ChildProcs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
        $_.CommandLine -like "*start_bot.py*" -or $_.CommandLine -like "*run_bridge_server.py*"
    }
    if ($ChildProcs) {
        foreach ($cp in $ChildProcs) {
            $tag = if ($cp.CommandLine -like "*start_bot.py*") { "Bot Engine" } else { "Bridge Server" }
            $wsMb = [math]::Round($cp.WorkingSetSize / 1MB, 2)
            Write-Host "  Child        : $tag (PID: $($cp.ProcessId)) - Working Set: $wsMb MB" -ForegroundColor Green
        }
    } else {
        Write-Host "  Child Procs  : None currently running" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Child Procs  : Could not query process list" -ForegroundColor Gray
}

# 6. Recent Logs
Write-Host ""
Write-Host "[6. Recent Log Tails]" -ForegroundColor Yellow
$LogFiles = @(
    @{ Name = "supervisor.log"; Path = (Join-Path $LogsDir "supervisor.log") },
    @{ Name = "bridge.log";     Path = (Join-Path $LogsDir "bridge.log") },
    @{ Name = "bot.log";        Path = (Join-Path $LogsDir "bot.log") }
)

foreach ($lf in $LogFiles) {
    Write-Host ""
    Write-Host "--- Tail: $($lf.Name) ---" -ForegroundColor Cyan
    if (Test-Path $lf.Path) {
        Get-Content $lf.Path -Tail 8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "  (Log file not yet generated)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "=========================================================================" -ForegroundColor Cyan
