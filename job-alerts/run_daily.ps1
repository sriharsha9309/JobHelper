$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m job_alerts *>> $log
exit $LASTEXITCODE
