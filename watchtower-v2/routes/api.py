"""
WatchTower V2 API Routes
==========================
REST endpoints for the frontend to consume.
"""

import os
import json
import subprocess
import requests
import logging
import re
import time
from datetime import datetime
from flask import Blueprint, jsonify, request

import config
from models import database as db

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")

# MQTT client reference - set by app.py on startup
mqtt_client = None

# Shared status file the launcher's verify scripts write (audio loopback +
# mic check). Lives next to START_ESCAPE_ROOM.bat on the Desktop.
SYSTEMS_STATUS_FILE = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\watchtower_systems_status.json"

# Consider an MQTT-based system "online" if seen within this many seconds.
AI_BRAIN_FRESH_S = 120
M3_FRESH_S = 120

# Unreal publishes MermaidsTale/Unreal/RoomStatus every 5s (and on every map
# load) — {"map":..,"audioRoom":..}. MUST match roomStatusTopic in the game's
# MQTTClientSubsystem.h. 20s = four missed heartbeats before the light greys.
UNREAL_ROOM_FRESH_S = 20
# The map Unreal must be sitting in before a game starts (ship / pre-game).
UNREAL_PREGAME_MAP = "OceanLevel_Final"
# 2026-08-04: the START bat intentionally boots the build to MainMenu and waits
# for a real player start, so MainMenu is a legitimate pre-game state too.
UNREAL_PREGAME_OK_MAPS = {UNREAL_PREGAME_MAP, "MainMenu"}
# Friendly names for the confirmation light.
UNREAL_MAP_LABELS = {
    "OceanLevel_Final": "Ship (pre-game ✓)",
    "Jungle_TEST": "Jungle",
    "Cave1": "Cove/Cave",
    "MainMenu": "Main Menu",
}


def _unreal_room_state() -> dict:
    """Parsed snapshot of Unreal's room heartbeat: {map, audio_room, age_s}.
    map is None when the heartbeat is absent (old build / game not running)."""
    sig = (mqtt_client.get_system_signals() if mqtt_client else {}).get("unreal_room", {})
    age = sig.get("age_s")
    out = {"map": None, "audio_room": None, "age_s": age}
    detail = sig.get("detail")
    if detail:
        try:
            data = json.loads(detail)
            out["map"] = data.get("map")
            out["audio_room"] = data.get("audioRoom")
        except (ValueError, TypeError):
            out["map"] = detail  # old/odd payload — show it raw rather than hide it
    return out

# Command topic the AI machine's brain_watchdog.py listens on. MUST match the
# topic in: AI Character System\brain_watchdog.py. WatchTower publishes
# "restart" here when the operator hits Reset Brain on the dashboard.
AI_BRAIN_CMD_TOPIC = "MermaidsTale/RedBeard/Cmd"

# Ship wall-camera tuning topic. MUST match cameraTuningTopic in the game's
# Ship.h (escaperoom repo). Published RETAINED so the game re-reads it on
# every subscribe; DELIBERATELY outside MermaidsTale/# because
# game_end_retained_sweeper wildcard-wipes that namespace after every game.
SHIP_CAMERA_TOPIC = "WatchTower/ShipCameraTuning"
# Slider limits mirror the C++ clamps in AShip::HandleCameraTuning.
# "default" = the HOUSE CALIBRATION (2026-09-04): the values every real game
# ran on from 2026-08-25 through 09-01 (game logs, LogShipCameras "Camera
# tuning received"). They are what the sliders show when the broker holds
# nothing, what "Reset" restores, and what _republish_tuning falls back to.
# MUST match DefaultGame.ini [/Script/EscapeRoom.Ship] in the escaperoom repo.
SHIP_CAMERA_FIELDS = {
    "frontViewFOV":   {"min": 20.0, "max": 120.0, "default": 86.5},
    "frontViewPitch": {"min": -45.0, "max": 15.0, "default": -3.0},
    "sideViewFOV":    {"min": 20.0, "max": 120.0, "default": 114.5},
    "sideViewPitch":  {"min": -45.0, "max": 15.0, "default": -9.5},
}

# Evalee/jungle camera + character-scale tuning (2026-08-04). Same contract as
# the ship dials: retained, outside MermaidsTale/# (sweeper namespace), topics
# MUST match CharacterTuningSubsystem in the game (build 08-04 evening+).
# Semantics are RELATIVE to the authored look — offset 0 / scale 1.0 =
# untouched; the game caches per-actor baselines so re-publishes never
# compound. Limits mirror the C++ clamps.
JUNGLE_CAMERA_TOPIC = "WatchTower/JungleCameraTuning"
# Defaults = house calibration 2026-09-04 (live 08-30..09-01): jungle camera
# 3 deg tighter than authored, Evalee 0.75x, RedBeard 1.45x. MUST match
# DefaultGame.ini [/Script/EscapeRoom.CharacterTuningSubsystem].
JUNGLE_CAMERA_FIELDS = {
    "fovOffset":   {"min": -40.0, "max": 40.0, "default": -3.0},
    "pitchOffset": {"min": -30.0, "max": 30.0, "default": 0.0},
}
CHARACTER_SCALE_TOPIC = "WatchTower/CharacterScale"
CHARACTER_SCALE_FIELDS = {
    "redbeardScale": {"min": 0.25, "max": 3.0, "default": 1.45},
    "evaleeScale":   {"min": 0.25, "max": 3.0, "default": 0.75},
}

# Suggested calibration = the HOUSE CALIBRATION (2026-09-04). History: the
# 08-18 "principled" anchor (48/-9 | 58/-11.2, jungle 0/0, scales 1.45/1.0)
# was never what the room actually ran on — the operator tuned by eye on the
# walls and every real game from 08-25 through 09-01 used the numbers below
# (proof: LogShipCameras / LogCharacterTuning lines in the DEV build logs).
# On 09-02 the PC rebooted; mosquitto has no persistence, so every retained
# tuning topic died and WatchTower's cache came up empty. The operator then
# hit Reset / Suggested on 09-04 and got the stale 08-18 anchor = "the reset
# wasn't correct". One source of truth now: the field defaults above.
SUGGESTED_CALIBRATION = {
    "ship":   {k: v["default"] for k, v in SHIP_CAMERA_FIELDS.items()},
    "jungle": {k: v["default"] for k, v in JUNGLE_CAMERA_FIELDS.items()},
    "scale":  {k: v["default"] for k, v in CHARACTER_SCALE_FIELDS.items()},
}


def set_mqtt_client(client):
    global mqtt_client
    mqtt_client = client


def _read_launcher_status() -> dict:
    """Read the JSON the launcher's verify scripts wrote (may be absent)."""
    try:
        if os.path.exists(SYSTEMS_STATUS_FILE):
            with open(SYSTEMS_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read launcher status: {e}")
    return {}


# Cached like the M3 watch — the dashboard's 2s poll must not spawn a
# PowerShell per request.
_playback_cache = {"ts": 0.0, "result": None}


def _windows_default_playback() -> dict:
    """Query the current Windows default playback device (AudioDeviceCmdlets).
    Returns {status, name}. 'online' only if default is the OUT 1-10 master
    and not muted — that's the room-wide audio path the launcher pins."""
    now = time.time()
    if (_playback_cache["result"] is not None
            and now - _playback_cache["ts"] < 5):
        return _playback_cache["result"]
    ps = (
        "$d = Get-AudioDevice -Playback; "
        "$m = Get-AudioDevice -PlaybackMute; "
        "Write-Output ($d.Name + '|' + $m)"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
        name, _, muted = out.partition("|")
        is_master = "OUT 1-10" in name
        is_muted = muted.strip().lower() == "true"
        if is_master and not is_muted:
            result = {"status": "online", "name": name}
        elif is_muted:
            result = {"status": "offline", "name": f"{name} (MUTED)"}
        else:
            result = {"status": "warn", "name": name or "unknown"}
    except Exception as e:  # noqa: BLE001
        result = {"status": "unknown", "name": f"query failed: {e}"}
    _playback_cache["ts"] = now
    _playback_cache["result"] = result
    return result


# M3 restart watch — Mystery.exe runs on this same PC and its audio wedges
# silently on long runs (standing fix: full app restart). Result is cached so
# the dashboard's 2s poll doesn't spawn a PowerShell per request.
_m3_watch_cache = {"ts": 0.0, "result": None}


def _m3_restart_check() -> dict:
    """Return the M3 restart-banner state:
    {needed, level, headline, detail}. needed=False -> no banner."""
    now = time.time()
    if (_m3_watch_cache["result"] is not None
            and now - _m3_watch_cache["ts"] < config.M3_UPTIME_CHECK_INTERVAL_S):
        return _m3_watch_cache["result"]

    ps = (
        f"$p = Get-Process -Name {config.M3_PROCESS_NAME} -ErrorAction SilentlyContinue "
        "| Select-Object -First 1; "
        "if ($p) { $p.StartTime.ToString('o') } else { 'NOT_RUNNING' }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
    except Exception as e:  # noqa: BLE001 - watcher must never break /status
        out = f"ERROR {e}"

    if out == "NOT_RUNNING":
        result = {
            "needed": True, "level": "offline",
            "headline": "M3 is NOT running",
            "detail": f"{config.M3_PROCESS_NAME}.exe not found — start M3 or no room audio will play.",
        }
    elif out.startswith("ERROR") or not out:
        result = {"needed": False, "level": "unknown",
                  "headline": "", "detail": out or "uptime query returned nothing"}
    else:
        try:
            started = datetime.fromisoformat(out)
            uptime_h = (datetime.now(started.tzinfo) - started).total_seconds() / 3600.0
            if uptime_h >= config.M3_RESTART_AFTER_HOURS:
                detail = (f"Mystery.exe up {uptime_h:.1f}h (limit {config.M3_RESTART_AFTER_HOURS}h) — "
                          "M3 audio goes silent on long runs. Restart M3 before the next game.")
                # If a game is in progress, tell the operator to wait it out.
                signals = mqtt_client.get_system_signals() if mqtt_client else {}
                m3 = signals.get("m3", {})
                if m3.get("detail") == "Running" and m3.get("age_s") is not None \
                        and m3["age_s"] <= M3_FRESH_S:
                    detail += " (game in progress — restart after it ends)"
                result = {"needed": True, "level": "warn",
                          "headline": "M3 needs a restart", "detail": detail}
            else:
                result = {"needed": False, "level": "online", "headline": "",
                          "detail": f"Mystery.exe up {uptime_h:.1f}h"}
        except Exception as e:  # noqa: BLE001
            result = {"needed": False, "level": "unknown",
                      "headline": "", "detail": f"could not parse start time '{out}': {e}"}

    _m3_watch_cache["ts"] = now
    _m3_watch_cache["result"] = result
    return result


# Unreal build watch — the START bat launches the newest Windows_*_DEV
# folder; flag if EscapeRoom isn't running, is running an older build, or
# left a fresh crash folder. Cached like the M3 watch.
_unreal_watch_cache = {"ts": 0.0, "result": None}


def _newest_build_dir() -> str:
    """Newest packaged build folder name (Windows_*_DEV sorts chronologically)."""
    try:
        names = [n for n in os.listdir(config.UNREAL_BUILDS_DIR)
                 if n.startswith("Windows_") and n.endswith("_DEV")]
        return max(names) if names else ""
    except OSError:
        return ""


def _unreal_check() -> list:
    """Return a list of pre-game issue dicts for the Unreal packaged build."""
    now = time.time()
    if (_unreal_watch_cache["result"] is not None
            and now - _unreal_watch_cache["ts"] < config.M3_UPTIME_CHECK_INTERVAL_S):
        return _unreal_watch_cache["result"]

    issues = []
    newest = _newest_build_dir()
    ps = (
        f"Get-Process -Name {config.UNREAL_PROCESS_NAME} -ErrorAction SilentlyContinue "
        "| ForEach-Object { $_.Path }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
        paths = [p for p in out.splitlines() if p.strip()]
    except Exception as e:  # noqa: BLE001
        paths = []
        logger.warning(f"unreal process query failed: {e}")

    if not paths:
        issues.append({
            "icon": "🎮", "name": "Unreal not running",
            "detail": f"{config.UNREAL_PROCESS_NAME}.exe not found — launch the game "
                      f"(newest build: {newest or 'none on disk'}).",
        })
    elif newest and not any(newest in p for p in paths):
        running = os.path.basename(os.path.dirname(paths[0]))
        issues.append({
            "icon": "🎮", "name": "Unreal running an OLD build",
            "detail": f"running from '{running or paths[0]}' but newest on disk is "
                      f"'{newest}' — restart via the START bat.",
        })

    # Fresh crash folders in the newest build's Saved\Crashes.
    if newest:
        crash_dir = os.path.join(config.UNREAL_BUILDS_DIR, newest,
                                 "EscapeRoom", "Saved", "Crashes")
        try:
            fresh_cutoff = now - config.UNREAL_CRASH_FRESH_H * 3600
            fresh = [n for n in os.listdir(crash_dir)
                     if os.path.getmtime(os.path.join(crash_dir, n)) > fresh_cutoff]
            if fresh:
                issues.append({
                    "icon": "💥", "name": "Recent Unreal crash",
                    "detail": f"{len(fresh)} crash folder(s) under {newest} in the last "
                              f"{config.UNREAL_CRASH_FRESH_H}h — check Saved\\Crashes.",
                })
        except OSError:
            pass  # no Crashes folder = no crashes

    _unreal_watch_cache["ts"] = now
    _unreal_watch_cache["result"] = issues
    return issues


# M3 per-app mixer volumes — Windows reapplies a remembered per-device app
# volume to every new Mystery.exe session (a 15% Ship slider silenced all M3
# SFX through multiple restarts, 2026-07-04). Cached like the other watches.
_appvol_cache = {"ts": 0.0, "result": None}


def _m3_appvolume_check() -> list:
    """Flag Mystery.exe audio sessions that are muted or below the floor."""
    now = time.time()
    if (_appvol_cache["result"] is not None
            and now - _appvol_cache["ts"] < config.M3_UPTIME_CHECK_INTERVAL_S):
        return _appvol_cache["result"]

    issues = []
    if os.path.exists(config.SVCL_PATH):
        import csv as _csv
        import tempfile
        dump = os.path.join(tempfile.gettempdir(), "watchtower_svv.csv")
        try:
            subprocess.run([config.SVCL_PATH, "/scomma", dump],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            with open(dump, newline="", encoding="utf-8-sig") as f:
                for row in _csv.DictReader(f):
                    if "Mystery.exe" not in (row.get("Process Path") or ""):
                        continue
                    vol_txt = (row.get("Volume Percent") or "").rstrip("%")
                    vol = float(vol_txt) if vol_txt else None
                    muted = (row.get("Muted") or "").lower() == "yes"
                    dev = row.get("Device Name") or "?"
                    if muted:
                        issues.append({
                            "icon": "🔇", "name": f"M3 MUTED on {dev}",
                            "detail": "Mystery.exe session muted in the Windows mixer — "
                                      "unmute or run SoundVolumeView /SetVolume Mystery.exe 100.",
                        })
                    elif vol is not None and vol < config.M3_APP_VOLUME_MIN:
                        issues.append({
                            "icon": "🔉", "name": f"M3 app volume {vol:.0f}% on {dev}",
                            "detail": f"below the {config.M3_APP_VOLUME_MIN:.0f}% floor — Windows "
                                      "reapplies this to every session; SFX will be near-silent. "
                                      "Fix: SoundVolumeView /SetVolume Mystery.exe 100.",
                        })
        except Exception as e:  # noqa: BLE001
            logger.warning(f"m3 app volume check failed: {e}")

    _appvol_cache["ts"] = now
    _appvol_cache["result"] = issues
    return issues


# LIVE Unreal audio-session check (2026-08-02) — where is the game's render
# session ACTUALLY playing right now? The loopback verify only proves the
# chain at launcher-verify time; mid-game the UE mixer can silently fall back
# to the Windows default device (Behringer OUT 1-10 = the room speaker cubes)
# after an endpoint invalidation, and nothing surfaced it ("unreal audio ran
# somewhere else" 08-01 + 08-02). Rule: Unreal must render ONLY on NVIDIA
# projector endpoints (MQTTClientSubsystem RoomNameSubstrings rationale).
_unreal_session_cache = {"ts": 0.0, "result": None}


def _unreal_audio_session_check() -> dict:
    """Return {'state': 'ok'|'wrong'|'none', 'device': str} for the live
    UnrealGame/EscapeRoom render session."""
    now = time.time()
    if (_unreal_session_cache["result"] is not None
            and now - _unreal_session_cache["ts"] < config.M3_UPTIME_CHECK_INTERVAL_S):
        return _unreal_session_cache["result"]

    result = {"state": "none", "device": ""}
    if os.path.exists(config.SVCL_PATH):
        import csv as _csv
        import tempfile
        dump = os.path.join(tempfile.gettempdir(), "watchtower_svv_unreal.csv")
        try:
            subprocess.run([config.SVCL_PATH, "/scomma", dump],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            with open(dump, newline="", encoding="utf-8-sig") as f:
                for row in _csv.DictReader(f):
                    if (row.get("Type") or "") != "Application":
                        continue
                    ident = (row.get("Process Path") or "") + (row.get("Name") or "")
                    if "UnrealGame" not in ident and "EscapeRoom" not in ident:
                        continue
                    dev = row.get("Device Name") or "?"
                    result = {
                        "state": "ok" if "NVIDIA" in dev.upper() else "wrong",
                        "device": dev,
                    }
                    if result["state"] == "wrong":
                        break  # a wrong-device session is the headline
        except Exception as e:  # noqa: BLE001
            logger.warning(f"unreal audio session check failed: {e}")

    _unreal_session_cache["ts"] = now
    _unreal_session_cache["result"] = result
    return result


def _pregame_checks() -> dict:
    """Assemble the Pre-Game Readiness banner state. Suppressed mid-game:
    every check here is about the idle/reset state before a GameStart."""
    if not mqtt_client:
        return {"ok": True, "issues": [], "suppressed": None}

    if (mqtt_client.get_system_signals().get("m3") or {}).get("detail") == "Running":
        return {"ok": True, "issues": [], "suppressed": "game in progress"}

    pre = mqtt_client.get_pregame_signals()
    issues = []

    # Retained GameStart is its own headline — the AI launcher drops it on
    # startup, so a late-launched AI sits silent until a fresh publish.
    landmines = dict(pre["landmines"])
    gs = landmines.pop("MermaidsTale/GameStart", None)
    if gs:
        issues.append({
            "icon": "🧨", "name": "Retained GameStart on the broker",
            "detail": f"payload '{gs}' will replay into every late subscriber — "
                      "clear it (clear_retained_mqtt.py) before the next game.",
        })
    for topic, payload in sorted(landmines.items()):
        issues.append({
            "icon": "🧨", "name": f"Retained command: {topic}",
            "detail": f"payload '{payload[:60]}' replays on every reconnect (reboot-loop "
                      "risk) — clear with clear_retained_mqtt.py wildcard.",
        })

    # Boards stuck in a reboot loop lose puzzle state mid-game. Only an
    # ACTIVE loop (recent boot event) is bannered — a board quiet since the
    # fix has recovered.
    for device, info in sorted(pre["boot_loops"].items()):
        if info["last_age_s"] > config.PREGAME_BOOTLOOP_QUIET_S:
            continue
        issues.append({
            "icon": "🔁", "name": f"{device} is boot-looping",
            "detail": f"{info['count']} reboots in the last "
                      f"{config.PREGAME_BOOTLOOP_WINDOW_S // 60} min (latest "
                      f"{int(info['last_age_s'])}s ago) — check power/retained "
                      "commands before starting.",
        })

    # Room reset: props physically in their start positions.
    for row in config.PREGAME_PROP_STATES:
        state = pre["props"].get(row["topic"])
        if state is None:
            continue  # board hasn't reported since WatchTower started — device tile covers it
        rej = row.get("reject_re")
        bad = (bool(re.search(rej, state["payload"], re.I)) if rej
               else row["expect"].lower() not in state["payload"].lower())
        if bad:
            age = f" ({int(state['age_s'])}s ago)" if state["age_s"] > 60 else ""
            want = "not SOLVED (send PUZZLE_RESET)" if rej else f"'{row['expect']}'"
            issues.append({
                "icon": "🚪", "name": f"{row['label']} not in start position",
                "detail": f"{row['topic']} = '{state['payload'][:60]}'{age} — expected "
                          f"{want}.",
            })

    issues.extend(_unreal_check())
    issues.extend(_m3_appvolume_check())

    # Unreal room confirmation — the game must be sitting in the ship start
    # map before a GameStart. Caught live 2026-08-01: a blank retained-erase
    # on JungleEntered flipped the game (and its background track) into the
    # jungle right after GameReset; nothing surfaced it until guests heard it.
    ur = _unreal_room_state()
    if ur["age_s"] is not None and ur["age_s"] <= UNREAL_ROOM_FRESH_S \
            and ur["map"] and ur["map"] not in UNREAL_PREGAME_OK_MAPS:
        label = UNREAL_MAP_LABELS.get(ur["map"], ur["map"])
        issues.append({
            "icon": "🗺️", "name": f"Unreal is sitting in {label}",
            "detail": f"map '{ur['map']}' (audio→{ur['audio_room'] or '?'}) — "
                      f"expected '{UNREAL_PREGAME_MAP}' before a game. Fire a "
                      "GameStart/reset or restart the build to return to the ship.",
        })

    return {"ok": not issues, "issues": issues, "suppressed": None}


def _fmt_age(ts: str) -> str:
    """Human 'verified 16:42' style label from an ISO timestamp."""
    try:
        return "verified " + datetime.fromisoformat(ts).strftime("%H:%M")
    except Exception:
        return "no data"


def _helm_tile() -> dict:
    """Systems tile for Helm, from its own 2 s MermaidsTale/Audio/status beat
    (same health read the Talk-to-the-Players panel gates on)."""
    tile = {"name": "Helm (Sound)", "icon": "🎚️"}
    try:
        from routes.say_api import _helm_health
        h = _helm_health()
    except Exception as e:  # noqa: BLE001
        tile.update(status="unknown", detail=f"health read failed: {e}")
        return tile
    if h["ok"]:
        detail = "running · owns " + (h.get("device") or "the Behringer")
        try:
            sig = (mqtt_client.get_system_signals() if mqtt_client else {}).get("helm_audio", {})
            data = json.loads(sig.get("detail") or "{}")
            up = data.get("uptime_s")
            if up is not None:
                detail += f" · up {int(up) // 3600}h{(int(up) % 3600) // 60:02d}m"
            if data.get("xruns"):
                detail += f" · {data['xruns']} audio hiccups"
        except Exception:  # noqa: BLE001
            pass
        tile.update(status="online", detail=detail)
    else:
        tile.update(status="offline",
                    detail=(h.get("reason") or "Helm not ready") + " — the whole room is SILENT")
    return tile


def _parley_tile_state(sig: dict, game_running: bool):
    """AI Character Brain tile for Parley (v2, 2026-09-22), from its retained
    MermaidsTale/AI/status JSON beat (every 10 s). Returns (status, detail) or
    None when no Parley beat has ever been seen (caller keeps the v1 path).
    OFFLINE when the beat says ok=false (LWT 'parley offline' / 'stopped') or
    when it has gone stale (> AI_STATUS_FRESH_S) while a game is running."""
    data = sig.get("detail")
    age = sig.get("age_s")
    if not isinstance(data, dict) or age is None:
        return None
    ver = data.get("version") or "?"
    if age > config.AI_STATUS_FRESH_S:
        seen = f"last Parley status {int(age)}s ago"
        if game_running:
            return "offline", (f"GAME RUNNING but Parley v{ver} has gone silent ({seen}) — "
                               "characters are dead; restart Parley")
        return "warn", f"Parley v{ver} silent ({seen}) — not running, or its MQTT dropped"
    if data.get("ok") is not True:
        reason = data.get("reason") or "not ok"
        return "offline", (f"Parley reports DOWN: {reason} ({int(age)}s ago)"
                           + (" — GAME RUNNING with silent characters!" if game_running else ""))

    phase = data.get("phase") or "?"
    agent = data.get("agent") or "none"
    sess = data.get("session") or {}
    if sess:
        sess_txt = (f"session {'open' if sess.get('open') else 'closed'}"
                    f" ({sess.get('agent') or agent}, {sess.get('reconnects', 0)} reconnects)")
    else:
        sess_txt = f"no session · {data.get('reconnects', 0)} reconnects"
    beats = data.get("beats") or {}
    beats_txt = (f"beats {beats.get('spoken', 0)} spoken"
                 f"/{beats.get('late', 0)} late/{beats.get('lost', 0)} lost"
                 f"/{beats.get('canned', 0)} canned")
    mics = data.get("mic") or {}
    mic_bits = [f"{room} {'OK' if (m or {}).get('ok') else 'FAIL'}"
                for room, m in sorted(mics.items())]
    mic_txt = "mic " + (" ".join(mic_bits) if mic_bits else "?")
    problems = data.get("config_problems") or []
    config_ok = data.get("config_ok", True)
    config_txt = "config OK" if config_ok else ("config PROBLEMS: " + "; ".join(map(str, problems))[:160])
    detail = (f"Parley v{ver} · phase {phase} · agent {agent} · {sess_txt} · "
              f"{beats_txt} · {mic_txt} · {config_txt} · {int(age)}s ago")
    # A mic FAIL is shown in the text but does not colour the tile: a quiet
    # room reads as a "failed" level check (mic_selftest 09-22: ship 0.5 rms).
    return ("online" if config_ok else "warn"), detail


@api.route("/ai/beats")
def get_ai_beats():
    """Parley (2026-09-22): the last 20 BeatResult receipts (oldest first)
    plus the latest AI/status dict. Empty lists / null when the old AI program
    is running — the Direct-the-Character card treats that as 'nothing yet'."""
    if not mqtt_client:
        return jsonify({"status": None, "status_age_s": None, "beats": [], "last": None})
    sig = mqtt_client.get_system_signals().get("ai_status", {})
    detail = sig.get("detail") if isinstance(sig.get("detail"), dict) else None
    beats = mqtt_client.get_ai_beat_results()
    return jsonify({
        "status": detail,
        "status_age_s": sig.get("age_s"),
        "status_fresh": (sig.get("age_s") is not None
                         and sig["age_s"] <= config.AI_STATUS_FRESH_S),
        "beats": beats,
        "last": beats[-1] if beats else None,
    })


def _build_systems(summary: dict) -> list:
    """Assemble the Systems group tiles (first group on the dashboard).
    Mixes live signals (broker, RedBeard/Talking, Windows default) with the
    launcher's last verify results (audio loopback per room, mic check)."""
    signals = mqtt_client.get_system_signals() if mqtt_client else {}
    launcher = _read_launcher_status()
    tiles = []

    # 1. MQTT Broker — live, authoritative.
    tiles.append({
        "name": "MQTT Broker", "icon": "📡",
        "status": "online" if summary.get("broker_connected") else "offline",
        "detail": f"{config.MQTT_BROKER}:{config.MQTT_PORT}",
    })

    # 2. AI Character Brain — RedBeard traffic seen recently on MQTT.
    #    GAME-AWARE (2026-07-15): while a game is RUNNING, a silent brain is a
    #    hard OFFLINE — including the "never came up at all" case (age None),
    #    which used to read as a quiet grey "unknown" tile with NO banner.
    #    That gap hid today's failure: ai_launcher started after GameStart's
    #    retained copy was guard-erased, the brain never launched, and the
    #    registry showed a greyed tile instead of a red alert. Pre-game /
    #    post-reset, a silent brain is NORMAL (it only runs during games), so
    #    the quiet warn/unknown behavior is kept for those states.
    ai = signals.get("ai_brain", {})
    ai_age = ai.get("age_s")
    ai_online = ai_age is not None and ai_age <= AI_BRAIN_FRESH_S
    m3sig = signals.get("m3", {})
    game_running = (m3sig.get("detail") == "Running"
                    and m3sig.get("age_s") is not None and m3sig["age_s"] <= 120)
    launcher_sig = signals.get("ai_launcher", {})
    launcher_age = launcher_sig.get("age_s")
    launcher_alive = launcher_age is not None and launcher_age <= AI_BRAIN_FRESH_S
    parley = _parley_tile_state(signals.get("ai_status", {}), game_running)
    if parley is not None:
        # Parley (v2, 2026-09-22) has reported at least once this WatchTower
        # run — its 10 s JSON beat is richer truth than RedBeard traffic.
        ai_status, ai_detail = parley
    elif ai_online:
        ai_status = "online"
        ai_detail = f"RedBeard {ai.get('detail','')} {int(ai_age)}s ago"
    elif game_running:
        ai_status = "offline"
        seen = (f"last RedBeard traffic {int(ai_age)}s ago" if ai_age is not None
                else "NO RedBeard traffic since WatchTower started")
        rescue = ("Reset Brain will relaunch it" if launcher_alive
                  else "ai_launcher is ALSO down — Reset Brain won't work, restart via START bat")
        ai_detail = f"GAME RUNNING but the AI is silent ({seen}) — {rescue}"
    elif ai_age is not None:
        ai_status = "warn"
        ai_detail = f"RedBeard {ai.get('detail','')} {int(ai_age)}s ago"
    else:
        ai_status = "unknown"
        ai_detail = "no RedBeard traffic yet (normal between games)"
    tiles.append({
        "name": "AI Character Brain", "icon": "🧠",
        "status": ai_status,
        "detail": ai_detail,
        "launcher_alive": launcher_alive,
        "game_running": game_running,
        "parley": parley is not None,
    })

    # 3. M3 Story Engine (Mythric game runner) — State=Running.
    #    2026-09-17 audit: was "M3 Audio". Since Helm (08-29) M3 plays no sound
    #    itself — it sends cues to Helm — so the tile is named for what it
    #    really watches: is the story engine running.
    m3 = signals.get("m3", {})
    m3_age = m3.get("age_s")
    m3_running = m3_age is not None and m3_age <= M3_FRESH_S and (m3.get("detail") == "Running")
    tiles.append({
        "name": "M3 Story Engine", "icon": "📖",
        "status": "online" if m3_running else ("warn" if m3_age is not None else "unknown"),
        "detail": (f"State={m3.get('detail')} ({int(m3_age)}s ago)" if m3_age is not None
                   else "M3 State not seen"),
    })

    # 3.5 Helm — the ONE program that makes sound (since 2026-08-29). M3 cues,
    #     Unreal's mix and the AI voices all play through it. Added 09-17:
    #     it was only visible on the /game Guardian checklist, never here.
    helm = _helm_tile()
    tiles.append(helm)
    helm_ok = helm["status"] == "online"

    # 4 & 5. Unreal Audio + Each Speaker — from the launcher's per-room
    #    audio loopback verify (tone played -> heard back via camera mic).
    loop = launcher.get("audio_loopback")
    if loop:
        rooms = loop.get("rooms", [])
        passed = [r for r in rooms if r.get("status") == "PASS"]
        failed = [r for r in rooms if r.get("status") == "FAIL"]
        spk_status = "offline" if failed else ("online" if passed else "warn")
        spk_detail = (f"{len(failed)} FAIL: " + ", ".join(r["room"] for r in failed)
                      if failed else f"{len(passed)}/{len(rooms)} rooms heard")
        tiles.append({
            "name": "Room Speakers", "icon": "🔊",
            "status": spk_status,
            "detail": f"{spk_detail} · {_fmt_age(loop.get('ts',''))}",
        })
        # Unreal audio shares the same physical path; surface the same verify
        # but framed as the game-audio chain reaching the rooms.
        tiles.append({
            "name": "Unreal Audio", "icon": "🎮",
            "status": "offline" if failed else ("online" if passed else "warn"),
            "detail": f"room audio path · {_fmt_age(loop.get('ts',''))}",
        })
    else:
        for nm, ic in (("Room Speakers", "🔊"), ("Unreal Audio", "🎮")):
            tiles.append({"name": nm, "icon": ic, "status": "unknown",
                          "detail": "run launcher audio verify"})

    # LIVE override for the Unreal Audio tile (2026-08-02): the loopback stamp
    # is launcher-verify-time truth; this is NOW truth. A session rendering on
    # anything non-NVIDIA (classic: Behringer default fallback = room speaker
    # cubes) turns the tile red mid-game, when it actually matters.
    # 2026-09-17 audit: under Helm the projector endpoints are DISABLED and the
    # game streams its mix straight to Helm, so "not on NVIDIA" is no longer
    # wrong — it would paint a false red every game. The old rule only runs
    # when Helm is down (legacy fallback path).
    ua = ({"state": "helm", "device": ""} if helm_ok
          else _unreal_audio_session_check())
    for tile in tiles:
        if tile["name"] != "Unreal Audio":
            continue
        if ua["state"] == "helm":
            tile["detail"] = "game sound plays through Helm · " + tile["detail"]
        elif ua["state"] == "wrong":
            tile["status"] = "offline"
            tile["detail"] = (f"LIVE: game session rendering on '{ua['device']}' — "
                              "NOT a projector endpoint! Game audio is playing in the "
                              "wrong place (UE watchdog should re-swap within ~15s; "
                              "if it persists, restart the build).")
        elif ua["state"] == "ok":
            tile["detail"] = f"live: {ua['device']} · " + tile["detail"]
        break

    # 5.5 Unreal Room — the confirmation light: which map/room the packaged
    #     game is ACTUALLY sitting in, from its 5s RoomStatus heartbeat.
    #     Pre-game the only green state is the ship start map; mid-game any
    #     fresh heartbeat is green (jungle/cove are then expected).
    ur = _unreal_room_state()
    ur_age = ur["age_s"]
    ur_fresh = ur_age is not None and ur_age <= UNREAL_ROOM_FRESH_S
    if not ur_fresh:
        ur_status = "unknown" if ur_age is None else "offline"
        ur_detail = ("no RoomStatus heartbeat yet — game not running or build "
                     "predates the heartbeat" if ur_age is None
                     else f"heartbeat lost {int(ur_age)}s ago — game hung or MQTT deaf")
    else:
        label = UNREAL_MAP_LABELS.get(ur["map"], ur["map"] or "?")
        ur_detail = f"{label} · audio→{ur['audio_room'] or '?'} · {int(ur_age)}s ago"
        if game_running:
            ur_status = "online"
        else:
            ur_status = "online" if ur["map"] in UNREAL_PREGAME_OK_MAPS else "warn"
    tiles.append({
        "name": "Unreal Room", "icon": "🗺️",
        "status": ur_status,
        "detail": ur_detail,
    })

    # 6. AI Audio (ElevenLabs path) — proven by the mic check + AI brain alive.
    #    ElevenLabs has no MQTT signal; the launcher's mic_check confirms the
    #    full hear/speak loop the AI uses. Pair it with the brain liveness.
    mic = launcher.get("mic_check")
    jmic = launcher.get("mic_check_jungle")   # 2026-09-17: Evalee's jungle mic
    if mic:
        ms = mic.get("status")
        js = jmic.get("status") if jmic else None
        any_fail = ms == "FAIL" or js == "FAIL"
        all_pass = ms == "PASS" and js in ("PASS", None)
        tiles.append({
            "name": "AI Audio (ElevenLabs)", "icon": "🗣️",
            "status": "online" if (all_pass and ai_online) else (
                "offline" if any_fail else "warn"),
            "detail": (f"ship mic {ms} · jungle mic {js or 'not tested'} · "
                       f"{_fmt_age(mic.get('ts',''))}"),
        })
    else:
        tiles.append({"name": "AI Audio (ElevenLabs)", "icon": "🗣️",
                      "status": "unknown", "detail": "run launcher mic check"})

    # 7. Windows Speakers — live default-device query.
    #    2026-09-17 audit: RETIRED while Helm is up. Nothing in the game plays
    #    on the Windows default device any more (Helm owns the Behringer), so
    #    the tile sat permanently yellow on "Computer Monitor" and meant
    #    nothing. It only comes back if Helm is down (legacy fallback path).
    if not helm_ok:
        win = _windows_default_playback()
        tiles.append({
            "name": "Windows Speakers", "icon": "🪟",
            "status": win["status"], "detail": win["name"],
        })

    return tiles


# =============================================================================
# DEVICE STATUS
# =============================================================================

@api.route("/status")
def get_status():
    if mqtt_client:
        summary = mqtt_client.get_status_summary()
        # The Pirate Ship mic is not an MQTT device — attach its live probe
        # snapshot as a separate "mic" block (rendered as its own tile).
        # 2026-09-17: "mics" = every character mic (ship + jungle), each tile
        # lands in its own room; "mic" (ship only) kept for older readers.
        try:
            from mic_probe import ALL_PROBES
            summary["mics"] = [mp.snapshot() for mp in ALL_PROBES]
            summary["mic"] = summary["mics"][0]
        except Exception as e:  # noqa: BLE001 - never let the mic break /status
            summary["mic"] = {"status": "unknown", "error": f"probe error: {e}"}
            summary["mics"] = []
        # Systems group (infrastructure health) — first group on the dashboard.
        try:
            summary["systems"] = _build_systems(summary)
        except Exception as e:  # noqa: BLE001 - never let systems break /status
            summary["systems"] = []
            logger.warning(f"systems build failed: {e}")
        # M3 restart banner — only "needed" when uptime is past the limit or
        # the process is gone (see config.M3_RESTART_AFTER_HOURS).
        try:
            summary["m3_restart"] = _m3_restart_check()
        except Exception as e:  # noqa: BLE001 - never let the watcher break /status
            summary["m3_restart"] = {"needed": False}
            logger.warning(f"m3 restart check failed: {e}")
        # Pre-Game Readiness banner (suppressed while a game is running).
        try:
            summary["pregame"] = _pregame_checks()
        except Exception as e:  # noqa: BLE001 - never let readiness break /status
            summary["pregame"] = {"ok": True, "issues": [], "suppressed": None}
            logger.warning(f"pregame checks failed: {e}")
        # 24/7 health sentinel findings + latest daily report (dashboard banner).
        try:
            import health_sentinel
            summary["health"] = health_sentinel.snapshot()
        except Exception as e:  # noqa: BLE001 - never let the sentinel break /status
            summary["health"] = {"findings": [], "report": None}
            logger.warning(f"health snapshot failed: {e}")
        return jsonify(summary)
    return jsonify({"error": "MQTT client not initialized"}), 500


@api.route("/health")
def get_health():
    """Health sentinel view: open findings + the latest Daily Report.
    ?report=now forces a fresh report (also written to the debug log)."""
    import health_sentinel
    if request.args.get("report") == "now":
        health_sentinel.generate_report(force=True)
    return jsonify(health_sentinel.snapshot())


@api.route("/ping/<device_name>")
def ping_device(device_name):
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    result = mqtt_client.ping_device(device_name)
    return jsonify({"device": device_name, "ping_sent": result})


@api.route("/ping-all")
def ping_all():
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    mqtt_client.ping_all()
    return jsonify({"status": "pinging all devices"})


@api.route("/retained-watchdog")
def retained_watchdog_stats():
    """24/7 retained-command watchdog: connection state + recent erasures.
    Quick truth for "did something plant a poison retained command overnight"."""
    try:
        from mqtt.retained_watchdog import watchdog
        return jsonify(watchdog.get_stats())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@api.route("/reset-brain", methods=["POST"])
def reset_brain():
    """Tell the AI machine to relaunch the AI Character brain (ai_launcher.py).
    Publishes a restart command on AI_BRAIN_CMD_TOPIC; brain_watchdog.py on the
    AI machine picks it up, kills the old process tree, and re-launches."""
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    result = mqtt_client.publish_raw(AI_BRAIN_CMD_TOPIC, "restart")
    if "error" in result:
        return jsonify(result), 503
    logger.info("Reset Brain command published to %s", AI_BRAIN_CMD_TOPIC)
    return jsonify({"ok": True, **result})


@api.route("/command/<device_name>/<command>")
def send_command(device_name, command):
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    result = mqtt_client.send_command(device_name, command)
    return jsonify(result)


@api.route("/ship-camera", methods=["GET"])
def get_ship_camera():
    """Current ship wall-camera tuning for the /game sliders. Values come from
    the retained broker message (seeded on WatchTower's subscribe), falling
    back to the DefaultGame.ini defaults baked into the build."""
    values = {k: spec["default"] for k, spec in SHIP_CAMERA_FIELDS.items()}
    source = "defaults"
    raw = getattr(mqtt_client, "ship_camera_tuning", "") if mqtt_client else ""
    if raw:
        try:
            for k, v in json.loads(raw).items():
                if k in values:
                    values[k] = float(v)
            source = "retained"
        except (ValueError, TypeError):
            logger.warning("Unparseable retained ship-camera payload: %r", raw)
    return jsonify({"values": values, "source": source,
                    "limits": SHIP_CAMERA_FIELDS, "topic": SHIP_CAMERA_TOPIC})


@api.route("/ship-camera", methods=["POST"])
def set_ship_camera():
    """Publish retained ship wall-camera tuning; the game applies it live
    (AShip::HandleCameraTuning) — at the menu, pre-start, or mid-game."""
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    body = request.get_json(silent=True) or {}
    values = {}
    for key, spec in SHIP_CAMERA_FIELDS.items():
        if key not in body:
            return jsonify({"error": f"missing field {key}"}), 400
        try:
            v = float(body[key])
        except (ValueError, TypeError):
            return jsonify({"error": f"{key} is not a number"}), 400
        values[key] = max(spec["min"], min(spec["max"], v))
    payload = json.dumps(values)
    result = mqtt_client.publish_raw(SHIP_CAMERA_TOPIC, payload, retain=True)
    if "error" in result:
        return jsonify(result), 503
    mqtt_client.remember_tuning(SHIP_CAMERA_TOPIC, payload)  # readback + disk
    logger.info("Ship camera tuning published (retained): %s", payload)
    return jsonify({"ok": True, "values": values})


def _tuning_get(fields, topic, attr):
    """Shared GET for a retained slider channel (see /ship-camera docstring)."""
    values = {k: spec["default"] for k, spec in fields.items()}
    source = "defaults"
    raw = getattr(mqtt_client, attr, "") if mqtt_client else ""
    if raw:
        try:
            for k, v in json.loads(raw).items():
                if k in values:
                    values[k] = float(v)
            source = "retained"
        except (ValueError, TypeError):
            logger.warning("Unparseable retained %s payload: %r", topic, raw)
    return jsonify({"values": values, "source": source,
                    "limits": fields, "topic": topic})


def _tuning_post(fields, topic, attr, label):
    """Shared POST for a retained slider channel: clamp, publish retained,
    seed the instant readback attr (see /ship-camera docstring)."""
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    body = request.get_json(silent=True) or {}
    values = {}
    for key, spec in fields.items():
        if key not in body:
            return jsonify({"error": f"missing field {key}"}), 400
        try:
            v = float(body[key])
        except (ValueError, TypeError):
            return jsonify({"error": f"{key} is not a number"}), 400
        values[key] = max(spec["min"], min(spec["max"], v))
    payload = json.dumps(values)
    result = mqtt_client.publish_raw(topic, payload, retain=True)
    if "error" in result:
        return jsonify(result), 503
    mqtt_client.remember_tuning(topic, payload)
    logger.info("%s published (retained): %s", label, payload)
    return jsonify({"ok": True, "values": values})


@api.route("/jungle-camera", methods=["GET"])
def get_jungle_camera():
    """Evalee/jungle camera offsets for the /game sliders (0 = authored)."""
    return _tuning_get(JUNGLE_CAMERA_FIELDS, JUNGLE_CAMERA_TOPIC, "jungle_camera_tuning")


@api.route("/jungle-camera", methods=["POST"])
def set_jungle_camera():
    """Publish retained jungle-camera offsets; the game applies them live
    (UCharacterTuningSubsystem) — build 2026-08-04 evening or newer."""
    return _tuning_post(JUNGLE_CAMERA_FIELDS, JUNGLE_CAMERA_TOPIC,
                        "jungle_camera_tuning", "Jungle camera tuning")


@api.route("/character-scale", methods=["GET"])
def get_character_scale():
    """RedBeard/Evalee scale multipliers for the /game sliders (1.0 = authored)."""
    return _tuning_get(CHARACTER_SCALE_FIELDS, CHARACTER_SCALE_TOPIC, "character_scale_tuning")


@api.route("/character-scale", methods=["POST"])
def set_character_scale():
    """Publish retained character-scale multipliers; the game applies them live
    (UCharacterTuningSubsystem) — build 2026-08-04 evening or newer."""
    return _tuning_post(CHARACTER_SCALE_FIELDS, CHARACTER_SCALE_TOPIC,
                        "character_scale_tuning", "Character scale tuning")


@api.route("/version")
def get_version():
    """Which code this WatchTower process is running (git commit stamped at
    boot — see app._build_version) plus when the process started."""
    from app import WT_VERSION  # lazy: app.py imports this module at startup
    return jsonify(WT_VERSION)


@api.route("/tuning/suggested-calibration", methods=["POST"])
def apply_suggested_calibration():
    """One-click anchor: publish the SUGGESTED_CALIBRATION values (see the
    constant's rationale — horizon-matched pitches, authored FOV pair,
    life-size RedBeard) on all three retained tuning channels. The operator
    tweaks from there with the sliders."""
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    channels = [
        (SHIP_CAMERA_FIELDS, SHIP_CAMERA_TOPIC, "ship_camera_tuning",
         SUGGESTED_CALIBRATION["ship"]),
        (JUNGLE_CAMERA_FIELDS, JUNGLE_CAMERA_TOPIC, "jungle_camera_tuning",
         SUGGESTED_CALIBRATION["jungle"]),
        (CHARACTER_SCALE_FIELDS, CHARACTER_SCALE_TOPIC, "character_scale_tuning",
         SUGGESTED_CALIBRATION["scale"]),
    ]
    applied = {}
    for fields, topic, attr, suggested in channels:
        values = {k: max(spec["min"], min(spec["max"], float(suggested[k])))
                  for k, spec in fields.items()}
        payload = json.dumps(values)
        result = mqtt_client.publish_raw(topic, payload, retain=True)
        if "error" in result:
            return jsonify(result), 503
        mqtt_client.remember_tuning(topic, payload)
        applied[topic] = values
    logger.info("Suggested calibration published (retained): %s", applied)
    return jsonify({"ok": True, "applied": applied})


# =============================================================================
# MQTT FEED
# =============================================================================

@api.route("/messages")
def get_messages():
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"messages": mqtt_client.get_feed(limit)})


# =============================================================================
# DEBUG LOG
# =============================================================================

@api.route("/debug-log", methods=["GET"])
def get_debug_log():
    device = request.args.get("device")
    resolved = request.args.get("resolved")
    if resolved is not None:
        resolved = resolved.lower() == "true"
    entries = db.get_debug_entries(device_name=device, resolved=resolved)
    return jsonify({"entries": entries})


@api.route("/debug-log", methods=["POST"])
def add_debug_log():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    entry_id = db.add_debug_entry(
        device_name=data.get("device_name"),
        severity=data.get("severity", "info"),
        title=data["title"],
        description=data.get("description"),
        resolution=data.get("resolution"),
        created_by=data.get("created_by", "manual")
    )
    return jsonify({"id": entry_id, "status": "created"})


@api.route("/debug-log/<int:entry_id>/resolve", methods=["POST"])
def resolve_debug_log(entry_id):
    data = request.get_json() or {}
    db.resolve_debug_entry(entry_id, data.get("resolution"))
    return jsonify({"status": "resolved"})


# =============================================================================
# TODO / CLICKUP INTEGRATION
# =============================================================================

@api.route("/todos", methods=["GET"])
def get_todos():
    device = request.args.get("device")
    status = request.args.get("status")
    todos = db.get_todos(device_name=device, status=status)
    return jsonify({"todos": todos})


@api.route("/todos", methods=["POST"])
def create_todo():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    # Create in ClickUp first
    clickup_result = _create_clickup_task(data)

    # Create locally
    todo_id = db.add_todo(
        title=data["title"],
        device_name=data.get("device_name"),
        description=data.get("description"),
        priority=data.get("priority", "normal"),
        due_date=data.get("due_date"),
        assigned_to=data.get("assigned_to"),
        clickup_task_id=clickup_result.get("id"),
        clickup_task_url=clickup_result.get("url")
    )

    return jsonify({
        "id": todo_id,
        "clickup_task_id": clickup_result.get("id"),
        "clickup_url": clickup_result.get("url"),
        "status": "created"
    })


@api.route("/todos/<int:todo_id>/status", methods=["POST"])
def update_todo_status(todo_id):
    data = request.get_json() or {}
    new_status = data.get("status", "done")
    db.update_todo_status(todo_id, new_status)
    return jsonify({"status": "updated"})


# =============================================================================
# MANIFEST / GRIMOIRE
# =============================================================================

@api.route("/manifests")
def get_manifests():
    manifests = db.get_all_manifests()
    return jsonify({"manifests": manifests})


@api.route("/manifests/<device_name>")
def get_manifest(device_name):
    manifest = db.get_manifest(device_name)
    if manifest:
        return jsonify(manifest)
    return jsonify({"error": f"No manifest for {device_name}"}), 404


# =============================================================================
# WORKSPACE INFO
# =============================================================================

@api.route("/workspace/members")
def get_workspace_members():
    """Get ClickUp workspace members for assignment dropdown."""
    try:
        headers = {"Authorization": config.CLICKUP_API_TOKEN}
        resp = requests.get(
            f"{config.CLICKUP_API_URL}/team/{config.CLICKUP_WORKSPACE_ID}/member",
            headers=headers,
            timeout=5
        )
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        logger.error(f"Failed to get ClickUp members: {e}")

    return jsonify({"members": []})


@api.route("/gravity-games/topics")
def get_gravity_games_topics():
    """Return the full Gravity Games MQTT topic table."""
    return jsonify({"topics": config.GRAVITY_GAMES_TOPICS})


# =============================================================================
# CLICKUP HELPER
# =============================================================================

def _create_clickup_task(data: dict) -> dict:
    """Create a task in ClickUp's WatchTower Issues list."""
    if not config.CLICKUP_API_TOKEN:
        logger.warning("No ClickUp API token configured - skipping ClickUp task creation")
        return {}

    try:
        # Map priority names to ClickUp values
        priority_map = {"urgent": 1, "high": 2, "normal": 3, "low": 4}

        task_data = {
            "name": data["title"],
            "description": data.get("description", ""),
            "priority": priority_map.get(data.get("priority", "normal"), 3),
        }

        # Add device tag
        if data.get("device_name"):
            task_data["tags"] = [data["device_name"]]
            task_data["description"] = f"**Device:** {data['device_name']}\n\n{task_data['description']}"

        # Add due date (ClickUp wants Unix ms)
        if data.get("due_date"):
            try:
                dt = datetime.strptime(data["due_date"], "%Y-%m-%d")
                task_data["due_date"] = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }

        resp = requests.post(
            f"{config.CLICKUP_API_URL}/list/{config.CLICKUP_LIST_ID}/task",
            headers=headers,
            json=task_data,
            timeout=10
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            logger.info(f"Created ClickUp task: {result.get('id')} - {data['title']}")
            return {"id": result.get("id"), "url": result.get("url")}
        else:
            logger.error(f"ClickUp API error {resp.status_code}: {resp.text}")
            return {}

    except Exception as e:
        logger.error(f"Failed to create ClickUp task: {e}")
        return {}
