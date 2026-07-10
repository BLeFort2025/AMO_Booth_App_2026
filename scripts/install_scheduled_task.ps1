<#
.SYNOPSIS
    Install (or update) the monthly data pipeline scheduled task.

.DESCRIPTION
    Creates a Windows Task Scheduler task that runs the Farm Finance
    Dashboard data pipeline on the FIRST THURSDAY of every month at
    9:00 AM Eastern.

    Key features:
      - If the laptop is OFF at 9:00 AM, the task runs at next boot/login
        (StartWhenAvailable = $true)
      - Runs whether or not the user is logged in (if password provided)
      - Won't start if already running (prevents overlapping runs)
      - Auto-stops after 2 hours (safety net)
      - Logs everything to scripts/logs/

.NOTES
    Run this script ONCE as Administrator:
      Right-click PowerShell → "Run as Administrator"
      cd "c:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter"
      .\scripts\install_scheduled_task.ps1

    To remove:
      Unregister-ScheduledTask -TaskName "FarmDashboard_MonthlyPipeline" -Confirm:$false
#>

# -- Check for admin rights --
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "[!] This script needs to run as Administrator." -ForegroundColor Yellow
    Write-Host "  Right-click PowerShell -> 'Run as Administrator', then re-run." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# -- Configuration --
$TaskName    = "FarmDashboard_MonthlyPipeline"
$TaskPath    = "\FarmFinanceDashboard\"
$Description = "Monthly data refresh for the OFA Farm Finance Dashboard. Fetches latest StatCan/OMAFRA data, processes derived metrics, and pushes to GitHub for Streamlit Cloud deployment."

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptPath  = Join-Path $ProjectRoot "scripts\scheduled_update.ps1"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Farm Finance Dashboard - Task Scheduler Installer"     -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Task Name:    $TaskName"
Write-Host "  Schedule:     First Thursday of every month, 9:00 AM"
Write-Host "  Missed runs:  Will execute at next boot/login"
Write-Host "  Script:       $ScriptPath"
Write-Host "  Project:      $ProjectRoot"
Write-Host ""

# -- Remove existing task if present --
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# -- Build task via XML (required for MonthlyDOW "first Thursday" trigger) --
# PowerShell's New-ScheduledTaskTrigger doesn't support "first day-of-week
# in month", so we define the full task as XML and register it directly.
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$Description</Description>
    <Author>$env:USERNAME</Author>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-02T09:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonthDayOfWeek>
        <Weeks>
          <Week>1</Week>
        </Weeks>
        <DaysOfWeek>
          <Thursday />
        </DaysOfWeek>
        <Months>
          <January /><February /><March /><April />
          <May /><June /><July /><August />
          <September /><October /><November /><December />
        </Months>
      </ScheduleByMonthDayOfWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$ScriptPath"</Arguments>
      <WorkingDirectory>$ProjectRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# -- Register the task --
try {
    Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Xml $TaskXml -Force | Out-Null
    Write-Host "  [OK] Task registered successfully!" -ForegroundColor Green
} catch {
    Write-Host "  [X] Failed to register task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Trying fallback method (schtasks)..." -ForegroundColor Yellow

    # Fallback: save XML and import via schtasks
    $XmlPath = Join-Path $env:TEMP "farm_dashboard_task.xml"
    $TaskXml | Out-File -FilePath $XmlPath -Encoding Unicode
    schtasks /create /tn "$TaskPath$TaskName" /xml $XmlPath /f
    Remove-Item $XmlPath -Force -ErrorAction SilentlyContinue

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Task registered via schtasks fallback!" -ForegroundColor Green
    } else {
        Write-Host "  [X] Both methods failed. See errors above." -ForegroundColor Red
        exit 1
    }
}

# -- Verify --
Write-Host ""
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    Write-Host "  -- Verification --" -ForegroundColor Cyan
    Write-Host "  Task State:     $($task.State)"
    Write-Host "  Next Run Time:  $($info.NextRunTime)"
    Write-Host ""
    Write-Host "  -- Quick Reference --" -ForegroundColor Cyan
    Write-Host "  View in GUI:    taskschd.msc -> FarmFinanceDashboard -> $TaskName"
    Write-Host "  Run manually:   Start-ScheduledTask -TaskName '$TaskName' -TaskPath '$TaskPath'"
    Write-Host "  Check status:   Get-ScheduledTaskInfo -TaskName '$TaskName' -TaskPath '$TaskPath'"
    Write-Host "  Remove:         Unregister-ScheduledTask -TaskName '$TaskName' -TaskPath '$TaskPath'"
    Write-Host "  View logs:      Get-Content scripts\logs\pipeline_*.log -Tail 50"
} else {
    Write-Host "  [!] Could not verify - task may not have registered correctly." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
