<#
.SYNOPSIS
    Installs Institutional EA MT5 Supervisor as an autonomous background Windows Scheduled Task.

.DESCRIPTION
    Configures a robust scheduled task that automatically launches the Institutional EA supervisor
    using pythonw.exe (completely hidden, zero console windows) on user logon and/or system startup.
    Includes auto-restart on failure, execution on battery, and multiple instance protection.

.PARAMETER AtStartup
    If specified, also registers a boot/startup trigger (requires Administrator rights).
.PARAMETER RunWhetherOrNotLoggedOn
    If specified with admin rights, runs whether or not the user is logged on.
#>

[CmdletBinding()]
param (
    [switch]$AtStartup = $false,
    [switch]$RunWhetherOrNotLoggedOn = $false
)

$TaskName = "InstitutionalEA_MT5_Supervisor"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$SupervisorScript = Join-Path $ScriptDir "supervisor.py"

Write-Host "=========================================================================" -ForegroundColor Cyan
Write-Host "  INSTITUTIONAL EA - AUTONOMOUS MT5 SUPERVISOR INSTALLER" -ForegroundColor Cyan
Write-Host "=========================================================================" -ForegroundColor Cyan
Write-Host "Project Root : $ProjectRoot"
Write-Host "Supervisor   : $SupervisorScript"

# 1. Resolve Pythonw executable
$PythonwExe = $null

# Check for local venv in project root
$VenvPaths = @(
    (Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"),
    (Join-Path $ProjectRoot "venv\Scripts\pythonw.exe"),
    (Join-Path $ProjectRoot "env\Scripts\pythonw.exe")
)

foreach ($p in $VenvPaths) {
    if (Test-Path $p) {
        $PythonwExe = $p
        Write-Host "Discovered project virtualenv interpreter: $PythonwExe" -ForegroundColor Green
        break
    }
}

if (-not $PythonwExe) {
    $SysPythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if ($SysPythonw -and (Test-Path $SysPythonw)) {
        $PythonwExe = $SysPythonw
        Write-Host "Using system pythonw interpreter: $PythonwExe" -ForegroundColor Green
    }
}

if (-not $PythonwExe) {
    $SysPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($SysPython) {
        $PythonwCandidate = Join-Path (Split-Path -Parent $SysPython) "pythonw.exe"
        if (Test-Path $PythonwCandidate) {
            $PythonwExe = $PythonwCandidate
            Write-Host "Resolved pythonw from python directory: $PythonwExe" -ForegroundColor Green
        } else {
            $PythonwExe = $SysPython
            Write-Host "pythonw.exe not found; falling back to python.exe: $PythonwExe" -ForegroundColor Yellow
        }
    }
}

if (-not $PythonwExe) {
    Write-Error "Python was not found. Please install Python 3.10+ and check 'Add to PATH' or create a venv."
    exit 1
}

# 2. Configure Scheduled Task Triggers
$Triggers = @()
$Triggers += New-ScheduledTaskTrigger -AtLogOn

if ($AtStartup) {
    $IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($IsAdmin) {
        $Triggers += New-ScheduledTaskTrigger -AtStartup
        Write-Host "Configured AtStartup trigger (System Boot)." -ForegroundColor Green
    } else {
        Write-Warning "AtStartup trigger requires Administrator privileges. Running with AtLogOn only."
    }
}

# 3. Configure Action
$Action = New-ScheduledTaskAction -Execute $PythonwExe -Argument ('"{0}"' -f $SupervisorScript) -WorkingDirectory $ProjectRoot

# 4. Configure Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -StartWhenAvailable

# 5. Configure Principal
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($IsAdmin) {
    $LogonType = if ($RunWhetherOrNotLoggedOn) { "S4U" } else { "Interactive" }
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType $LogonType -RunLevel Highest
    Write-Host "Elevated privileges detected. Registering task with highest privileges." -ForegroundColor Green
} else {
    Write-Host "Standard user context (non-admin). Registering task under current user profile." -ForegroundColor Yellow
    $Principal = $null
}

# 6. Register Task Idempotently
$InstalledViaTask = $false
try {
    Write-Host "Registering Windows Scheduled Task '$TaskName'..." -ForegroundColor Cyan
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if ($Principal) {
        Register-ScheduledTask -TaskName $TaskName -Trigger $Triggers -Action $Action -Principal $Principal -Settings $Settings -Description 'Institutional EA Autonomous MT5 Bot and Bridge Supervisor' -ErrorAction Stop | Out-Null
    } else {
        Register-ScheduledTask -TaskName $TaskName -Trigger $Triggers -Action $Action -Settings $Settings -Description 'Institutional EA Autonomous MT5 Bot and Bridge Supervisor' -ErrorAction Stop | Out-Null
    }
    
    # 7. Start the task immediately
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $InstalledViaTask = $true
    Write-Host "SUCCESS: $TaskName has been registered in Task Scheduler and started." -ForegroundColor Green
} catch {
    Write-Warning "Windows Task Scheduler registration requires Administrator elevation ($($_.Exception.Message))."
    Write-Host "Falling back to User Startup Folder autostart (seamless zero-admin mode)..." -ForegroundColor Yellow

    $StartupDir = [Environment]::GetFolderPath('Startup')
    $VbsFile = Join-Path $StartupDir "InstitutionalEA_MT5_Supervisor.vbs"
    $VbsContent = "Set WshShell = CreateObject(""WScript.Shell"")`r`nWshShell.CurrentDirectory = ""$ProjectRoot""`r`nWshShell.Run """"""$PythonwExe"""" """"$SupervisorScript"""""", 0, False`r`n"
    [System.IO.File]::WriteAllText($VbsFile, $VbsContent)
    Write-Host "Configured invisible startup launcher: $VbsFile" -ForegroundColor Green

    # Launch supervisor immediately in background
    Start-Process $PythonwExe -ArgumentList ('"{0}"' -f $SupervisorScript) -WorkingDirectory $ProjectRoot
    Write-Host "SUCCESS: Institutional EA Supervisor started in background." -ForegroundColor Green
}

$SupLog = Join-Path $ProjectRoot "logs\supervisor.log"
Write-Host "The supervisor runs silently in the background with zero terminal popup." -ForegroundColor Green
Write-Host "Logs are streaming to: $SupLog" -ForegroundColor Green
