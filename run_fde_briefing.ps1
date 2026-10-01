# Runs the FDE Briefing once: scrape, compose, send through desktop Outlook.
# Invoked daily by the "FDE Briefing" Windows Task Scheduler job; safe to run by hand.
#   powershell -ExecutionPolicy Bypass -File run_fde_briefing.ps1

$ErrorActionPreference = "Continue"
$repo   = $PSScriptRoot
$python = "C:\Users\Galaxeye\miniconda3\envs\isr-gpt\python.exe"
$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("fde_briefing_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

$env:KMP_DUPLICATE_LIB_OK = "TRUE"
$env:PYTHONIOENCODING     = "utf-8"

# FDE_MAIL_METHOD=outlook sends through classic desktop Outlook — start it if it
# isn't open. (The new Store "Outlook for Windows" can't be automated; use smtp then.)
if (-not (Get-Process OUTLOOK -ErrorAction SilentlyContinue)) {
    try {
        Start-Process "outlook.exe" -ErrorAction Stop
        Start-Sleep -Seconds 45
    } catch {
        "classic Outlook not found; continuing (fine for FDE_MAIL_METHOD=smtp)" | Out-File -Append -Encoding utf8 $log
    }
}

Set-Location $repo
& $python -m fde.run_daily *>> $log
"exit code: $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log

# Keep two weeks of logs.
Get-ChildItem $logDir -Filter "fde_briefing_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force
exit $LASTEXITCODE
