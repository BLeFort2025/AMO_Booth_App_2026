<#
.SYNOPSIS
    Monthly Data Pipeline - Scheduled Task Wrapper
    Runs the full Farm Finance Dashboard data pipeline.

.DESCRIPTION
    Designed to be triggered by Windows Task Scheduler on the first
    Thursday of every month at 9:00 AM.  If the laptop was off,
    Task Scheduler's "StartWhenAvailable" flag ensures it runs at
    the next boot/login.

    What gets updated:
      - All 117+ StatCan tables (checked for changes via SHA-256 hash)
      - OMAFRA datasets (from configured download URLs)
      - CapEx processing (Table 34-10-0035-01)
      - Output baseline (manufacturing + farm receipts)
      - IO Multipliers & Supply-Use tables
      - Rail transport agri-food share (basket weights)
      - Population estimates (Table 17-10-0155-01)
      - CSD boundaries (one-time download)
      - Climate normals (ECCC Geomet API)
      - Broadband coverage (if manual ZIPs present in data/raw/)
      - Health facilities (if ODHF ZIP present in data/raw/)
      - Census profiles (if Census ZIPs present in data/raw/)

    After the pipeline completes, changed data files are automatically
    committed and pushed to GitHub so the live Streamlit Cloud deployment
    picks up the fresh data.

    A Windows toast notification is shown at the end summarizing
    the result, including any failed datasets.

.NOTES
    Install:  Run scripts/install_scheduled_task.ps1 (as Admin)
    Logs:     scripts/logs/pipeline_YYYY-MM-DD.log
#>

# -- Strict mode --
$ErrorActionPreference = "Continue"   # Don't halt on non-fatal warnings

# -- Paths --
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python      = "C:\Users\ben.lefort\AppData\Local\Programs\Python\Python311\python.exe"
$LogDir      = Join-Path $ProjectRoot "scripts\logs"
$Timestamp   = Get-Date -Format "yyyy-MM-dd_HHmm"
$LogFile     = Join-Path $LogDir "pipeline_$Timestamp.log"

# -- Create log directory --
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# -- Helper: log + console --
function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    
    # Retry logic for Windows file sharing violations
    $retryCount = 0
    $written = $false
    while (-not $written -and $retryCount -lt 5) {
        try {
            Add-Content -Path $LogFile -Value $line -ErrorAction Stop
            $written = $true
        } catch {
            $retryCount++
            Start-Sleep -Milliseconds 100
        }
    }
}

# -- Toast notification helper --
function Show-PipelineToast {
    param(
        [string]$Title,
        [string]$Message,
        [string]$DetailLine = "",
        [ValidateSet("Success", "Warning", "Error")]
        [string]$Severity = "Success"
    )

    # Pick the hero icon based on severity
    switch ($Severity) {
        "Success" { $icon = "[OK]" }
        "Warning" { $icon = "[WARN]" }
        "Error"   { $icon = "[ERROR]" }
    }

    $FullTitle = "$icon $Title"

    # Build the notification body
    $Body = $Message
    if ($DetailLine) {
        $Body = "$Message`n$DetailLine"
    }

    try {
        # Method 1: BurntToast module (best experience - actionable, persistent)
        if (Get-Module -ListAvailable -Name BurntToast -ErrorAction SilentlyContinue) {
            Import-Module BurntToast -ErrorAction SilentlyContinue

            $Params = @{
                Text    = $FullTitle, $Body
                AppLogo = $null
            }

            # Add a button to open the log file
            if (Test-Path $LogFile) {
                $LogButton = New-BTButton -Content "View Log" -Arguments $LogFile
                $Params["Button"] = $LogButton
            }

            New-BurntToastNotification @Params
            Log "  [NOTIFY] Toast notification sent via BurntToast."
            return
        }
    } catch {
        Log "  [NOTIFY] BurntToast failed: $_. Falling back."
    }

    try {
        # Method 2: Native Windows Toast via .NET (no module needed)
        # Load the required WinRT assemblies
        [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime]

        # Use PowerShell's built-in AppId for the toast
        $AppId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

        # Escape XML special characters in the message
        $EscTitle = [System.Security.SecurityElement]::Escape($FullTitle)
        $EscBody  = [System.Security.SecurityElement]::Escape($Body)

        $ToastXml = @"
<toast duration="long">
  <visual>
    <binding template="ToastGeneric">
      <text>$EscTitle</text>
      <text>$EscBody</text>
      <text placement="attribution">Farm Finance Dashboard</text>
    </binding>
  </visual>
  <audio src="ms-winsoundevent:Notification.Default" />
</toast>
"@

        $XmlDoc = [Windows.Data.Xml.Dom.XmlDocument]::new()
        $XmlDoc.LoadXml($ToastXml)

        $Toast = [Windows.UI.Notifications.ToastNotification]::new($XmlDoc)
        $Notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
        $Notifier.Show($Toast)

        Log "  [NOTIFY] Toast notification sent via WinRT."
        return
    } catch {
        Log "  [NOTIFY] WinRT Toast failed: $_. Falling back to balloon tip."
    }

    try {
        # Method 3: System tray balloon tip (oldest, most compatible fallback)
        Add-Type -AssemblyName System.Windows.Forms
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.Icon = [System.Drawing.SystemIcons]::Information
        $balloon.BallowTipTitle = $FullTitle
        $balloon.BalloonTipText = $Body

        switch ($Severity) {
            "Success" { $balloon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info }
            "Warning" { $balloon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning }
            "Error"   { $balloon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error }
        }

        $balloon.Visible = $true
        $balloon.ShowBalloonTip(15000)   # Show for 15 seconds

        # Clean up after 20 seconds
        Start-Sleep -Seconds 20
        $balloon.Dispose()

        Log "  [NOTIFY] Balloon tip notification shown."
    } catch {
        Log "  [NOTIFY] All notification methods failed: $_"
    }
}

# -- Tracking variables --
$PipelineOutput  = @()
$FailedTables    = @()
$ChangedTables   = @()
$WarningMessages = @()
$DataPushed      = $false

# -- Start --
$StartTime = Get-Date
Log "======================================================="
Log "  Farm Finance Dashboard - Monthly Data Pipeline"
Log "  Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Log "  Project: $ProjectRoot"
Log "  Python:  $Python"
Log "======================================================="

# Verify Python exists
if (-not (Test-Path $Python)) {
    Log "[FATAL] Python not found at: $Python"
    Show-PipelineToast -Title "Pipeline Failed" `
        -Message "Python not found at expected path." `
        -DetailLine "Check: $Python" `
        -Severity Error
    exit 1
}

# -- Run the pipeline --
Log ""
Log ">> Running data pipeline (scripts/run_pipeline.py)..."
Log "  This may take 10-30 minutes depending on network speed."
Log ""

Set-Location $ProjectRoot

# Set environment variables to prevent unicode encoding crashes in python on Windows
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    & $Python -u scripts/run_pipeline.py 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Log "  $line"
        $PipelineOutput += $line

        # Track failures and updates from pipeline output
        if ($line -match "\[ERROR\].*Failed.*?(\d{2}-\d{2}-\d{4}-\d{2})") {
            $FailedTables += $Matches[1]
        }
        if ($line -match "\[WARNING\].*(?:skipped|failed)") {
            $WarningMessages += $line.Trim()
        }
        if ($line -match "Updated: \[(.+)\]") {
            $updates = $Matches[1] -split ",\s*" | ForEach-Object { $_.Replace("'", "").Replace("`"", "") }
            $ChangedTables += $updates
        }
    }
    $PipelineExitCode = $LASTEXITCODE
} catch {
    Log "[ERROR] Pipeline crashed: $_"
    $PipelineExitCode = 1
}

if ($PipelineExitCode -ne 0 -and $null -ne $PipelineExitCode) {
    Log ""
    Log "[WARNING] Pipeline exited with code $PipelineExitCode"
}

# -- Parse pipeline_status.json for authoritative results --
$StatusFile = Join-Path $ProjectRoot "data\pipeline_status.json"
if (Test-Path $StatusFile) {
    try {
        $status = Get-Content $StatusFile -Raw | ConvertFrom-Json
        if ($status.failed_tables) {
            $FailedTables = @($status.failed_tables)
        }
        if ($status.changed_tables) {
            $ChangedTables = @($status.changed_tables)
        }
    } catch {
        Log "  [WARN] Could not parse pipeline_status.json"
    }
}

# -- Git: commit and push if data changed --
Log ""
Log ">> Checking for data changes to commit..."

try {
    # Stage data directories that the pipeline writes to
    & git add data/latest data/archive data/derived data/manifest.json data/pipeline_status.json config/io_baskets.yml 2>&1 | Out-Null

    # Check if there are staged changes
    $diff = & git diff --cached --stat 2>&1
    if ($diff) {
        Log "  Changes detected:"
        $diff | ForEach-Object { Log "    $_" }

        $commitMsg = "data: monthly pipeline refresh $(Get-Date -Format 'yyyy-MM-dd')"
        & git commit -m $commitMsg 2>&1 | ForEach-Object { Log "  $_" }

        Log "  Pushing to remote..."
        & git push 2>&1 | ForEach-Object { Log "  $_" }
        Log "  [OK] Changes pushed - Streamlit Cloud will auto-redeploy."
        $DataPushed = $true
    } else {
        Log "  No data changes detected. Nothing to commit."
    }
} catch {
    Log "[WARNING] Git operations failed: $_"
    Log "  Data was updated locally but NOT pushed to GitHub."
    Log "  You can push manually with: git add data/ ; git commit -m 'data refresh' ; git push"
    $WarningMessages += "Git push failed - data updated locally only."
}

# -- Cleanup: keep only last 6 months of logs --
$CutoffDate = (Get-Date).AddMonths(-6)
Get-ChildItem $LogDir -Filter "pipeline_*.log" | Where-Object { $_.LastWriteTime -lt $CutoffDate } | ForEach-Object {
    Log "  Cleaning old log: $($_.Name)"
    Remove-Item $_.FullName -Force
}

# -- Build summary and send notification --
$Duration = (Get-Date) - $StartTime
$DurationStr = "{0:mm} min {0:ss} sec" -f $Duration

$nChanged = $ChangedTables.Count
$nFailed  = $FailedTables.Count
$nWarns   = $WarningMessages.Count

Log ""
Log "======================================================="
Log "  Pipeline complete: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Log "  Duration: $DurationStr"
Log "  Tables updated: $nChanged"
Log "  Tables failed:  $nFailed"
Log "  Warnings:       $nWarns"
Log "  Data pushed:    $DataPushed"
Log "  Log:            $LogFile"
Log "======================================================="

# -- Send Windows toast notification --
if ($PipelineExitCode -ne 0 -and $null -ne $PipelineExitCode -and $PipelineExitCode -ne 0) {
    # Pipeline script itself crashed
    Show-PipelineToast -Title "Pipeline Error" `
        -Message "The data pipeline crashed (exit code $PipelineExitCode)." `
        -DetailLine "Check log: $LogFile" `
        -Severity Error

} elseif ($nFailed -gt 0) {
    # Some datasets failed
    $failedList = ($FailedTables | Select-Object -First 5) -join ", "
    $moreText = if ($nFailed -gt 5) { " (+$($nFailed - 5) more)" } else { "" }

    $detail = "Failed: $failedList$moreText"
    if ($nChanged -gt 0) {
        $detail = "$nChanged tables updated successfully.`n$detail"
    }

    Show-PipelineToast -Title "Pipeline Complete - $nFailed Failed" `
        -Message $detail `
        -DetailLine "Duration: $DurationStr - check log for details." `
        -Severity Warning

} elseif ($nChanged -gt 0) {
    # All good, some data updated
    $pushMsg = if ($DataPushed) { "Changes pushed to Streamlit Cloud." } else { "No git push needed." }
    Show-PipelineToast -Title "Pipeline Complete" `
        -Message "$nChanged dataset(s) updated. $pushMsg" `
        -DetailLine "Duration: $DurationStr" `
        -Severity Success

} else {
    # All good, no changes
    Show-PipelineToast -Title "Pipeline Complete - No Changes" `
        -Message "All datasets checked - no new data available this month." `
        -DetailLine "Duration: $DurationStr" `
        -Severity Success
}
