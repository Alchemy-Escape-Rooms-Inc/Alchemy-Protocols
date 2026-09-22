"""
Health Sentinel — proactive 24/7 problem reporting
===================================================
2026-08-08: Cannon1's cannonball load sensor heartbeated 'VL6180X:FAIL' ALL
DAY and nothing surfaced it until a pre-game scan and a log dig. The operator
should never have to ASK whether the room is healthy.

The sentinel runs inside WatchTower (the always-up process) and watches
passively — no pings, no scans:

  * every NEW problem raises immediately: a red/amber banner on the dashboard
    (via /api/status "health") + a debug-log entry (deduped while open);
  * recovery clears the finding automatically;
  * a Daily Report is written at config.DAILY_REPORT_HOUR (or on WatchTower's
    first tick of the day if it boots later) — and on demand via
    /api/health?report=now.

Detectors (all thresholds in config HEALTH_*):
  sensor FAIL        board self-test tokens (Device.sensor_faults)
  board offline      LWT retained OFFLINE, or silent > HEALTH_DEVICE_SILENT_S,
                     or never heard since WatchTower started
  WiFi flapping      chatty boards (median beat <= 15s) with 3+ heartbeat
                     holes > 60s in 30 min — the CaptainsCuffs class where a
                     dropout swallows the solve publish
  reboot looping     active boot loops (mqtt boot_events)
  retained replant   the retained watchdog erasing the same topic 3+ times
  AI launcher dead   M3 story Running but no AILauncher heartbeat
  game gone deaf     M3 story Running but Unreal's RoomStatus heartbeat lost
                     (the cove MQTT-death class)
  voices internet    ElevenLabs TCP unreachable (2 consecutive probes)
  face server        A2F endpoint TCP unreachable (2 consecutive probes)
  disk space         C: below the Guardian floor
  M3 stale           Mystery.exe uptime past the audio-wedge limit — this one
                     AUTO-RESTARTS M3 (auto_remediate.py, 2026-08-17 owner
                     directive) when no game is live; alert only on fail/gate
  routing drift      waveOut PC:X order no longer matches the snapshot (the
                     ROUTING_MAP s9-s14 NVIDIA/USB re-enum class) — this one
                     AUTO-HEALS via rebaseline_routing.py (auto_remediate,
                     2026-08-17 owner directive: fix it FIRST, tell after);
                     alert only when the heal is held back or fails
"""

import os
import sys
import time
import socket
import shutil
import logging
import threading
import statistics
import subprocess
from datetime import datetime, date

import config
import auto_remediate

logger = logging.getLogger(__name__)

_mc = None
_lock = threading.Lock()
_findings: dict = {}          # id -> {id, severity, title, detail, since}
_last_report: dict | None = None
_report_date: str | None = None
_started_at = time.time()
_endpoint_fails = {"voices": 0, "a2f": 0}
_tick_n = 0
_m3_uptime_h: float | None = None


# ─────────────────────────────────────────────
# Findings registry
# ─────────────────────────────────────────────

def _set_finding(fid: str, severity: str, title: str, detail: str,
                 device_name: str | None = None):
    """Open (or refresh) a finding. A NEW finding logs + writes one debug-log
    entry (deduped on the open-entry title, same pattern Guardian uses)."""
    with _lock:
        is_new = fid not in _findings
        entry = _findings.get(fid, {"since": datetime.now().isoformat()})
        entry.update({"id": fid, "severity": severity, "title": title,
                      "detail": detail})
        _findings[fid] = entry
    if not is_new:
        return
    logger.error(f"Health sentinel NEW finding [{severity}]: {title} — {detail}")
    try:
        from models import database as db
        db_title = f"Health: {title}"
        if not db.has_open_debug_entry(db_title):
            db.add_debug_entry(
                device_name=device_name,
                severity="error" if severity == "error" else "warning",
                title=db_title,
                description=(f"{detail}\n\nSpotted automatically by the 24/7 health "
                             "sentinel — no scan was run. It clears itself when the "
                             "problem stops; fix guidance: see the matching Guardian "
                             "checklist item / device page."),
                created_by="health_sentinel",
            )
    except Exception:  # noqa: BLE001
        logger.exception("Health finding debug entry failed")


def _clear_finding(fid: str):
    with _lock:
        gone = _findings.pop(fid, None)
    if gone:
        logger.info(f"Health sentinel finding CLEARED: {gone['title']}")


def snapshot() -> dict:
    """For /api/status + /api/health: open findings (errors first, oldest
    first within a severity) and the latest daily report."""
    with _lock:
        finds = sorted(_findings.values(),
                       key=lambda f: (f["severity"] != "error", f["since"]))
        return {"findings": finds, "report": _last_report}


# ─────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────

def _device_snapshot():
    """Copy the fields we need under the client lock, then analyze unlocked."""
    out = []
    with _mc.lock:
        for name, d in _mc.devices.items():
            out.append({
                "name": name,
                "room": d.room,
                "sensor_faults": list(d.sensor_faults),
                "last_seen": d.last_seen,
                "offline_lwt": d.offline_lwt,
                "arrivals": list(d.arrivals),
            })
    return out


def _room_awake(devices) -> bool:
    """The props are on smart plugs and legitimately powered down overnight —
    a dark room must NOT flood the banner with per-board offline findings
    (discovered 05:27 on 2026-08-09: 18 boards 'not heard from' at dawn).
    The room counts as awake once a meaningful chunk of boards is talking;
    only then is ONE silent board a real anomaly worth flagging."""
    fresh = sum(1 for d in devices
                if d["last_seen"] is not None and
                (datetime.now() - d["last_seen"]).total_seconds() < config.HEALTH_DEVICE_SILENT_S)
    return fresh >= max(3, len(devices) // 4)


def _check_devices(now: float):
    devices = _device_snapshot()
    awake = _room_awake(devices)
    for d in devices:
        name = d["name"]

        # 1. Sensor self-test FAIL (the Cannon1 VL6180X class).
        fid = f"sensor:{name}"
        if d["sensor_faults"]:
            _set_finding(fid, "error", f"{name} sensor dead",
                         f"{name} is online but self-reports failed sensor(s): "
                         f"{', '.join(d['sensor_faults'])} — its puzzle cannot be "
                         "completed until this is fixed", device_name=name)
        else:
            _clear_finding(fid)

        # 2. Board offline (LWT, long silence, or never heard) — only judged
        #    while the room is AWAKE; a powered-down room clears these.
        fid = f"offline:{name}"
        if not awake:
            _clear_finding(fid)
        elif d["offline_lwt"]:
            _set_finding(fid, "error", f"{name} offline (LWT)",
                         f"the broker itself reported {name}'s connection died "
                         "(retained OFFLINE) and it hasn't come back",
                         device_name=name)
        elif d["last_seen"] is not None:
            silent_s = (datetime.now() - d["last_seen"]).total_seconds()
            if silent_s > config.HEALTH_DEVICE_SILENT_S:
                _set_finding(fid, "error", f"{name} silent",
                             f"no MQTT traffic from {name} for "
                             f"{int(silent_s / 60)} min — board likely dead or off "
                             "WiFi (check power / power-cycle it)",
                             device_name=name)
            else:
                _clear_finding(fid)
        elif now - _started_at > config.HEALTH_NEVER_SEEN_GRACE_S:
            _set_finding(fid, "warn", f"{name} not heard from",
                         f"{name} has produced no MQTT traffic since WatchTower "
                         f"started {int((now - _started_at) / 60)} min ago",
                         device_name=name)

        # 3. WiFi flapping (chatty boards with repeated heartbeat holes).
        fid = f"flap:{name}"
        arr = [t for t in d["arrivals"] if now - t <= config.HEALTH_FLAP_WINDOW_S]
        if len(arr) >= 20:
            diffs = [b - a for a, b in zip(arr, arr[1:])]
            med = statistics.median(diffs)
            gaps = sum(1 for x in diffs if x > config.HEALTH_FLAP_GAP_S)
            if med <= config.HEALTH_FLAP_CHATTY_MEDIAN_S and gaps >= config.HEALTH_FLAP_MIN_GAPS:
                _set_finding(fid, "warn", f"{name} WiFi flapping",
                             f"{name} normally reports every ~{med:.0f}s but had "
                             f"{gaps} dropouts >{config.HEALTH_FLAP_GAP_S}s in the last "
                             f"{config.HEALTH_FLAP_WINDOW_S // 60} min — puzzle events "
                             "can arrive late or get swallowed (the cuffs 45s-late-"
                             "solve bug); check RSSI / AP", device_name=name)
            else:
                _clear_finding(fid)


def _check_boot_loops():
    loops = _mc.get_pregame_signals().get("boot_loops", {})
    active = {n: i for n, i in loops.items()
              if i["last_age_s"] <= config.PREGAME_BOOTLOOP_QUIET_S}
    for name, info in active.items():
        _set_finding(f"bootloop:{name}", "error", f"{name} reboot-looping",
                     f"{name} rebooted {info['count']}x, last "
                     f"{int(info['last_age_s'])}s ago — usually a retained command "
                     "on its topic; check the retained watchdog / power-cycle",
                     device_name=name)
    with _lock:
        stale = [fid for fid in _findings
                 if fid.startswith("bootloop:") and fid.split(":", 1)[1] not in active]
    for fid in stale:
        _clear_finding(fid)


def _check_replants():
    try:
        from mqtt.retained_watchdog import watchdog
        with watchdog.lock:
            counts = dict(watchdog.erase_counts)
    except Exception:  # noqa: BLE001
        return
    hot = {t: c for t, c in counts.items()
           if c >= config.RETAINED_WATCHDOG_REPLANT_ALERT}
    for topic, c in hot.items():
        _set_finding(f"replant:{topic}", "warn", "retained command re-planter",
                     f"the watchdog has erased a retained command on {topic} "
                     f"{c}x since WatchTower started — something (usually M3) keeps "
                     "re-planting it")
    # replant counts only ever grow; leave open findings in place.


def _check_stack():
    """AI launcher + Unreal heartbeat, judged against the M3 story state."""
    signals = _mc.get_system_signals()
    m3 = signals.get("m3", {})
    game_running = (m3.get("detail") == "Running" and m3.get("age_s") is not None
                    and m3["age_s"] <= 600)

    la = signals.get("ai_launcher", {}).get("age_s")
    # Parley (2026-09-22) has no launcher: its fresh ok=true AI/status beat
    # counts as the AI program being up, so a Parley game never trips this.
    parley_up = _mc.parley_alive() if hasattr(_mc, "parley_alive") else False
    if game_running and not parley_up and (la is None or la > 300):
        seen = f"last heartbeat {int(la)}s ago" if la is not None else "never heard"
        _set_finding("ai_launcher", "error", "AI Character program down",
                     f"M3's story is Running but the AI launcher is silent ({seen}) "
                     "— characters won't launch for a game; use the Guardian "
                     "one-click fix or the START bat")
    else:
        _clear_finding("ai_launcher")

    ur = signals.get("unreal_room", {}).get("age_s")
    if game_running and ur is not None and ur > 300:
        _set_finding("unreal_deaf", "error", "game heartbeat lost",
                     f"a game is running but Unreal's RoomStatus heartbeat stopped "
                     f"{int(ur / 60)} min ago — the game is hung or its MQTT went "
                     "deaf (the cove crash class)")
    else:
        _clear_finding("unreal_deaf")


def _tcp_ok(host, port, timeout=5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_endpoints():
    for key, (host, port), title, sev, detail in (
        ("voices", config.ELEVENLABS_ENDPOINT, "internet for AI voices down", "error",
         "ElevenLabs is unreachable — RedBeard/Evalee would be MUTE in a game; "
         "check the internet connection / router"),
        ("a2f", config.A2F_ENDPOINT, "face animation server down", "warn",
         "the A2F endpoint (COMMANDCENTER) is unreachable — characters would talk "
         "with frozen faces; check the machine + Docker container"),
    ):
        if _tcp_ok(host, port):
            _endpoint_fails[key] = 0
            _clear_finding(f"endpoint:{key}")
        else:
            _endpoint_fails[key] += 1
            if _endpoint_fails[key] >= 2:
                _set_finding(f"endpoint:{key}", sev, title, detail)


def _check_slow():
    global _m3_uptime_h
    # Disk space.
    try:
        free_gb = shutil.disk_usage("C:\\").free / (1024 ** 3)
        if free_gb < config.GUARDIAN_MIN_FREE_GB:
            _set_finding("disk", "warn", "disk filling up",
                         f"only {free_gb:.1f} GB free on C: (floor "
                         f"{config.GUARDIAN_MIN_FREE_GB} GB) — Unreal/logs/audio "
                         "caches can crash mid-game on a full disk")
        else:
            _clear_finding("disk")
    except OSError:
        pass
    # M3 uptime (audio-wedge limit).
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$p = Get-Process -Name {config.M3_PROCESS_NAME} -ErrorAction "
             "SilentlyContinue | Select-Object -First 1; "
             "if ($p) { $p.StartTime.ToString('o') } else { 'NOT_RUNNING' }"],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
        if out and out != "NOT_RUNNING":
            started = datetime.fromisoformat(out)
            _m3_uptime_h = (datetime.now(started.tzinfo) - started).total_seconds() / 3600.0
            if _m3_uptime_h >= config.M3_RESTART_AFTER_HOURS:
                # 2026-08-17 owner directive: don't just tell him to restart
                # it — DO it. auto_remediate gates (never mid-game, one shot
                # per 2h) and a held-back/failed attempt falls through to the
                # original alert text so the owner is always told.
                res = auto_remediate.try_restart_m3(_mc)
                if res["ran"] and res["ok"]:
                    _clear_finding("m3_stale")
                    logger.warning(f"M3 was stale ({_m3_uptime_h:.1f}h) and was "
                                   f"auto-restarted: {res['note']}")
                else:
                    stale_msg = (f"Mystery.exe has been up {_m3_uptime_h:.1f}h (limit "
                                 f"{config.M3_RESTART_AFTER_HOURS}h) — its audio silently "
                                 "dies on long runs; restart it before the next game")
                    if res["ran"]:  # attempted but never came back — escalate
                        _set_finding("m3_stale", "error", "M3 auto-restart FAILED",
                                     f"{stale_msg} ({res['note']})")
                    else:
                        _set_finding("m3_stale", "warn", "M3 story engine stale",
                                     f"{stale_msg} ({res['note']})")
            else:
                _clear_finding("m3_stale")
        else:
            _m3_uptime_h = None
            _clear_finding("m3_stale")
    except Exception:  # noqa: BLE001
        pass


def _check_routing():
    """waveOut PC:X drift: probe with rebaseline_routing.py --detect
    (read-only device enumeration vs the last-known-good snapshot, ~3s).
    On drift, AUTO-HEAL through auto_remediate's gates (never mid-game,
    30-min loop guard); the heal itself does name restore / default re-pin /
    AMT remap / snapshot / full M3 restart / verify, and ABORTS rather than
    guess on a missing or ambiguous device name. Held-back or failed heal →
    banner finding, so the owner is always told; success is reported via the
    auto-fix debug-log entry only (owner directive: fix first, tell after)."""
    script = os.path.join(config.SCRIPT_DIR, "rebaseline_routing.py")
    if not os.path.exists(script):
        return
    try:
        proc = subprocess.run(
            [sys.executable, script, "--detect"], cwd=config.SCRIPT_DIR,
            capture_output=True, text=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        return
    if proc.returncode == 0:
        _clear_finding("routing_drift")
        return
    if proc.returncode != 4:
        return  # dependency problem — the Guardian checklist surfaces those
    tail = "; ".join(ln for ln in (proc.stdout or "").splitlines()
                     if ln.startswith(("DRIFT:", "CANNOT")))[:400]
    res = auto_remediate.try_rebaseline_routing(_mc)
    if res["ran"] and res["ok"]:
        _clear_finding("routing_drift")
        logger.warning(f"PC:X routing drift auto-healed: {res['note']}")
        return
    _set_finding(
        "routing_drift",
        "error" if res["ran"] else "warn",
        "routing auto-heal FAILED" if res["ran"] else "audio routing drifted",
        "the waveOut device order no longer matches the last-known-good "
        "snapshot — M3's PC:X sounds would fire into the WRONG rooms. "
        f"[{tail}] ({res['note']})")


# ─────────────────────────────────────────────
# Daily report
# ─────────────────────────────────────────────

def generate_report(force: bool = False) -> dict:
    """Compose the Daily Report from live state. Written to the debug log
    once per calendar day (or every call with force=True for ?report=now)."""
    global _last_report, _report_date
    today = date.today().isoformat()
    now = time.time()

    with _lock:
        finds = sorted(_findings.values(),
                       key=lambda f: (f["severity"] != "error", f["since"]))
    devices = _device_snapshot()
    fresh, silent = [], []
    for d in devices:
        if d["last_seen"] is not None and \
                (datetime.now() - d["last_seen"]).total_seconds() < config.HEALTH_DEVICE_SILENT_S:
            fresh.append(d["name"])
        else:
            silent.append(d["name"])

    lines = [f"Daily Report — {today}"]
    if finds:
        lines.append(f"⚠ {len(finds)} open problem(s):")
        for f in finds:
            mark = "🔴" if f["severity"] == "error" else "🟡"
            lines.append(f"  {mark} {f['title']} — {f['detail']} (since {f['since'][11:16]})")
    else:
        lines.append("✅ No open problems — every detector is green.")
    lines.append(f"Boards heard recently: {len(fresh)}/{len(devices)}"
                 + (f" (quiet: {', '.join(silent)})" if silent else ""))
    if not _room_awake(devices):
        lines.append("Room looks POWERED DOWN (props on smart plugs) — per-board "
                     "offline checks are suspended until boards wake up.")
    if _m3_uptime_h is not None:
        lines.append(f"M3 uptime: {_m3_uptime_h:.1f}h"
                     + (" — restart before first game!"
                        if _m3_uptime_h >= config.M3_RESTART_AFTER_HOURS else ""))
    try:
        from mqtt.retained_watchdog import watchdog
        stats = watchdog.get_stats()
        if stats.get("total_erased"):
            lines.append(f"Retained watchdog: erased {stats['total_erased']} "
                         "poison retained command(s) since WatchTower started")
    except Exception:  # noqa: BLE001
        pass
    lines.append("Reminder: run the Pre-Game Checklist before the first game — "
                 "this report is the passive view only (no pings were sent).")

    report = {"date": today, "generated": datetime.now().isoformat(),
              "lines": lines, "open_findings": len(finds)}
    already_written = (_report_date == today)
    _last_report = report
    _report_date = today

    if force or not already_written:
        try:
            from models import database as db
            db.add_debug_entry(
                device_name=None, severity="info",
                title=f"📋 Daily Report {today}",
                description="\n".join(lines[1:]),
                created_by="health_sentinel",
            )
            logger.info(f"Daily report written ({len(finds)} open findings)")
        except Exception:  # noqa: BLE001
            logger.exception("Daily report debug entry failed")
    return report


# ─────────────────────────────────────────────
# Loop
# ─────────────────────────────────────────────

def _loop():
    global _tick_n
    while True:
        time.sleep(config.HEALTH_TICK_S)
        _tick_n += 1
        now = time.time()
        for fn, every in ((lambda: _check_devices(now), 1),
                          (_check_boot_loops, 1),
                          (_check_stack, 1),
                          (_check_replants, 1),
                          (_check_endpoints, config.HEALTH_ENDPOINT_EVERY_TICKS),
                          (_check_routing, config.HEALTH_ROUTING_EVERY_TICKS),
                          (_check_slow, config.HEALTH_SLOW_EVERY_TICKS)):
            if _tick_n % every == 0:
                try:
                    fn()
                except Exception:  # noqa: BLE001 - one broken detector never stops the rest
                    logger.exception("Health detector failed")
        # Daily report: at the configured hour — or on the first tick of a new
        # day past that hour (covers WatchTower booting mid-morning).
        try:
            if datetime.now().hour >= config.DAILY_REPORT_HOUR and \
                    _report_date != date.today().isoformat():
                generate_report()
        except Exception:  # noqa: BLE001
            logger.exception("Daily report generation failed")


def start(mqtt_client):
    global _mc
    _mc = mqtt_client
    t = threading.Thread(target=_loop, name="health-sentinel", daemon=True)
    t.start()
    logger.info(f"Health sentinel started (tick {config.HEALTH_TICK_S}s, "
                f"daily report at {config.DAILY_REPORT_HOUR}:00)")
