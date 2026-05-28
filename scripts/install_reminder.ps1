# 一次性安装: 注册 Windows Task Scheduler 每日 15:30 提醒
# 用法: 右键 PowerShell "以管理员身份运行" 然后:
#   pwsh -File scripts\install_reminder.ps1

$taskName = "MystockDailyAnalysisReminder"
$scriptPath = (Resolve-Path "$PSScriptRoot\daily_analysis_reminder.ps1").Path

# 删除旧任务(若存在)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建新任务
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At 15:30

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::FromMinutes(2))

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName $taskName `
    -Description "mystock 每日 15:30 提醒打开 Claude Code 跑批量深度分析" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal | Out-Null

Write-Output "✅ 已注册 Task Scheduler: $taskName"
Write-Output "   触发时间: 每日 15:30"
Write-Output "   执行脚本: $scriptPath"
Write-Output ""
Write-Output "测试触发(立即弹一次提醒):"
Write-Output "  Start-ScheduledTask -TaskName $taskName"
Write-Output ""
Write-Output "查看 / 卸载:"
Write-Output "  taskschd.msc 找到 '$taskName',或:"
Write-Output "  Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
