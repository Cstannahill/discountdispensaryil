# Starts the API server when nothing is listening on port 8000. A busy or slow server still holds the port, so a running
# sync is never restarted; only a server that is gone is replaced. Meant to be run every few minutes by a scheduled task.
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force $logs | Out-Null
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 }
$stamp = (Get-Date).ToString('s')
Add-Content (Join-Path $logs 'watchdog.log') "$stamp server not listening; starting it"
$python = Join-Path $root '.venv\Scripts\python.exe'
$out = Join-Path $logs 'uvicorn.log'
# Created through WMI so the server is not a child of this task and survives it ending.
$cmd = "cmd /c `"cd /d $root && `"$python`" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 >> `"$out`" 2>&1`""
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $root }
Add-Content (Join-Path $logs 'watchdog.log') "$stamp started pid $($r.ProcessId) rc $($r.ReturnValue)"
