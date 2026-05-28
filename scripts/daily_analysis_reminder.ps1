# mystock daily analysis reminder
# Triggered by Windows Task Scheduler at 15:30 each day
# Uses .NET NotifyIcon BalloonTip (Windows 11 auto-upgrades to native Toast)

$ErrorActionPreference = "SilentlyContinue"

# 1. Skip if backend container not running
$backendRunning = docker ps --filter "name=mystock-backend" --filter "status=running" --format "{{.Names}}" 2>$null
if (-not $backendRunning) {
    "[$(Get-Date -Format 'HH:mm:ss')] mystock-backend not running, skip reminder" | Out-Host
    exit 0
}

# 2. Show notification via NotifyIcon BalloonTip (works on PS 5.1 + 7, no WinRT/BurntToast needed)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Information
$icon.Visible = $true
$icon.BalloonTipTitle = [char]0x1F4CA + " mystock daily analysis"
$icon.BalloonTipText = "Open Claude Code and say:`n`"" + [char]0x5BF9 + [char]0x6240 + [char]0x6709 + [char]0x81EA + [char]0x9009 + [char]0x80A1 + [char]0x8DD1 + [char]0x6DF1 + [char]0x5EA6 + [char]0x5206 + [char]0x6790 + "`"`n(~30-60 min, sub-agents in parallel)"
$icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$icon.ShowBalloonTip(15000)

# Keep alive 17s so the balloon has time to render
Start-Sleep -Seconds 17
$icon.Dispose()

"[$(Get-Date -Format 'HH:mm:ss')] reminder shown" | Out-Host
exit 0
