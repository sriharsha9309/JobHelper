$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -m resume_tailor
