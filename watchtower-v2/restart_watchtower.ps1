# restart_watchtower.ps1 — restart the LIVE WatchTower (app.py) the safe way.
#
# Why this file exists (2026-09-20): code changes to WatchTower (Guardian rows
# etc.) only show after app.py restarts. Launching it from a Claude tool shell
# dies at session cleanup, so it must be started through WMI Win32_Process
# Create with the full bat path — same recipe as Helm / SkullVision. This
# script does that and can be run by hand, by Claude, or by a one-shot
# scheduled task after a game.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File restart_watchtower.ps1
#
# Refuses to restart while a game is running (MermaidsTale/AI/Phase != idle is
# not checked here — it checks WatchTower's own /api/game/state) unless -Force.
param([switch]$Force)

$ErrorActionPreference = 'Continue'
$appDir = 'C:\Users\Alchemy\Alchemy-Grimoire\watchtower-v2'
$bat    = Join-Path $appDir 'start-watchtower.bat'
$logp   = Join-Path $appDir 'logs\restart_watchtower.log'
function Log($m) { $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m; Write-Host $line; Add-Content -Path $logp -Value $line -Encoding utf8 }

New-Item -ItemType Directory -Force (Split-Path $logp) | Out-Null
Log "restart requested (Force=$Force)"

# 1. game running? (WatchTower's own view; skip if WT is already down)
if (-not $Force) {
    try {
        $st = Invoke-RestMethod -Uri 'http://localhost:5000/api/game/state' -TimeoutSec 5
        $running = $false
        foreach ($k in 'running','in_progress','game_running','active') { if ($st.PSObject.Properties[$k] -and $st.$k) { $running = $true } }
        if ($st.PSObject.Properties['state'] -and ("$($st.state)" -match 'running|started|in_progress')) { $running = $true }
        if ($running) { Log "a game is running per /api/game/state - NOT restarting (use -Force)"; exit 3 }
    } catch { Log "game-state query failed ($($_.Exception.Message)) - assuming no game" }
}

# 2. stop the live app.py + the cmd window that hosts it
$py = Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*app.py*' -and $_.CommandLine -notlike '*alyssa*' }
foreach ($p in $py) {
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($p.ParentProcessId)" -ErrorAction SilentlyContinue
    Log "stopping app.py pid $($p.ProcessId) (parent $($p.ParentProcessId) $($parent.Name))"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    if ($parent -and $parent.Name -eq 'cmd.exe' -and $parent.CommandLine -like '*start-watchtower*') {
        Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 3

# 3. start fresh through WMI (survives the caller's shell going away)
$cmd = 'cmd /c "' + $bat + '"'
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $appDir }
Log "WMI Create -> ReturnValue $($r.ReturnValue) pid $($r.ProcessId)"

# 4. health check
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try { $h = Invoke-WebRequest -Uri 'http://localhost:5000/api/game/state' -TimeoutSec 3 -UseBasicParsing; if ($h.StatusCode -eq 200) { $ok = $true; break } } catch {}
}
if ($ok) { Log "WatchTower up: /api/game/state 200 after $($i+1) s"; exit 0 }
Log "WatchTower NOT answering on :5000 after 40 s - check the WatchTower window"; exit 1
