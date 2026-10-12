param(
    [string]$At = "8:00AM",
    [string]$TaskName = "JobAlertsDaily"
)

$script = Join-Path $PSScriptRoot "run_daily.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
# StartWhenAvailable: if the PC was off/asleep at 8 AM, run as soon as it is back.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily AI job finder - updates jobs.html and companies.html" -Force | Out-Null

Write-Host "Registered '$TaskName' daily at $At. Test now with: Start-ScheduledTask -TaskName $TaskName"
