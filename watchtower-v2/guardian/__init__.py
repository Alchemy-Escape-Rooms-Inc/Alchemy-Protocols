"""
Guardian — Pre-Game Checklist Gate + Game Start/Stop Control
=============================================================
The room cannot start unless every blocking checklist item passes.

Flow:
  1. Operator hits "Run Pre-Game Checklist" (or "Start Game", which runs it).
  2. Guardian executes every check in guardian/checks.py, streaming progress.
  3. Verdict READY  -> the Start Game button fires START_ESCAPE_ROOM.bat.
     Verdict BLOCKED -> start is REFUSED server-side; each failure shows a
     plain-English explanation plus either an approve-to-run software fix
     (guardian/fixes.py) or human instructions, then re-run to verify.
  4. Every run, fix, and start/stop is persisted (guardian_runs /
     guardian_actions) and failures are logged to the debug log once.

The START/STOP bats blanket-kill python.exe by design; they now spare the PID
in watchtower.pid (written at boot) so WatchTower survives pressing its own
buttons.
"""

import os
import json
import time
import uuid
import logging
import threading
import subprocess
from datetime import datetime

import config
from models import database as db
from . import checks as checks_mod
from . import fixes as fixes_mod

logger = logging.getLogger(__name__)

_mqtt_client = None
_runs = {}                 # run_id -> run dict (in-memory, newest wins)
_runs_lock = threading.Lock()
_active_run_id = None      # only one checklist run at a time

# Props the operator has benched for THIS round: the checklist skips their
# ping (and their start-position rows), so the game can start without them.
# Cleared automatically the moment a game start fires.
_benched = set()
_benched_lock = threading.Lock()
# 2026-08-28: persist the bench across WatchTower restarts (every self-edit
# restart was wiping it and the operator had to re-tick EPSON PJ etc.). It
# still auto-clears on game start - that lifecycle is unchanged.
_BENCH_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "bench_state.json")


def _save_bench():
    try:
        with open(_BENCH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(_benched), f)
    except OSError as e:
        logger.warning(f"bench state not saved: {e}")


def _load_bench():
    try:
        with open(_BENCH_STATE_FILE, "r", encoding="utf-8") as f:
            names = json.load(f)
        with _benched_lock:
            _benched.clear()
            _benched.update(n for n in names if isinstance(n, str))
        if _benched:
            logger.info(f"Guardian bench restored from disk: {', '.join(sorted(_benched))}")
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning(f"bench state not loaded: {e}")

# Non-MQTT gear the operator can bench alongside the prop boards (same panel,
# same per-round lifecycle). Benching gear excuses routing_verify [FAIL] lines
# that NAME it — e.g. a physically dead projector whose audio endpoint cannot
# verify until the hardware is repaired (08-15: left ship projector down).
BENCH_GEAR = {
    # 08-28 operator renamed the NVIDIA HDMI endpoints; "EPSON PJ" no longer
    # exists. These four are the current Windows names (camera-mic roll-call
    # 08-28: "Jungle Projector" {9cf85bd9} = the live ship-front+cove+jungle
    # leg, "Right Projector" {c07d32c5} = live ship side, "Front Ship
    # Projector" {720c88f8} + "Left Ship Projector" {9250f946} = SILENT legs).
    # Bench whichever name routing_verify flags until its projector is live.
    "Front Ship Projector": {"room": "Gear (non-prop)", "icon": "📽️"},
    "Left Ship Projector": {"room": "Gear (non-prop)", "icon": "📽️"},
    "Right Projector": {"room": "Gear (non-prop)", "icon": "📽️"},
    "Jungle Projector": {"room": "Gear (non-prop)", "icon": "📽️"},
    # 09-06: Fanatec steering wheel — benching it makes Guardian's
    # pirate_wheel check skip for the round (wheel off / no map crossing).
    "Pirate Wheel": {"room": "Gear (non-prop)", "icon": "🎡"},
}


def init(mqtt_client):
    global _mqtt_client
    _mqtt_client = mqtt_client
    _load_bench()


def write_pid_file():
    """Record our PID so the START/STOP bats' python-kill spares us."""
    try:
        with open(config.WATCHTOWER_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        logger.info(f"PID file written: {config.WATCHTOWER_PID_FILE} ({os.getpid()})")
    except OSError as e:
        logger.warning(f"Could not write PID file: {e}")


# ─────────────────────────────────────────────
# Benched props (sit this round out)
# ─────────────────────────────────────────────

def get_benched():
    with _benched_lock:
        return sorted(_benched)


def bench_info():
    """Everything the bench UI needs: the full prop roster + current bench."""
    devices = []
    if _mqtt_client:
        with _mqtt_client.lock:
            for name, dev in sorted(_mqtt_client.devices.items(),
                                    key=lambda kv: (kv[1].room, kv[0])):
                devices.append({"name": name, "room": dev.room, "icon": dev.icon,
                                "type": dev.device_type.value,
                                "status": dev.status.value})
    for name, gear in sorted(BENCH_GEAR.items()):
        devices.append({"name": name, "room": gear["room"], "icon": gear["icon"],
                        "type": "gear", "status": "gear"})
    return {"benched": get_benched(), "devices": devices}


def set_benched(names):
    """Replace the benched set. Returns (benched|None, message, http_status)."""
    if _mqtt_client is None:
        return None, "MQTT client not ready — try again in a moment.", 503
    names = list(dict.fromkeys(names))
    unknown = [n for n in names
               if n not in _mqtt_client.devices and n not in BENCH_GEAR]
    if unknown:
        return None, f"Unknown device(s): {', '.join(unknown)}", 400
    with _benched_lock:
        added = sorted(set(names) - _benched)
        removed = sorted(_benched - set(names))
        _benched.clear()
        _benched.update(names)
        benched_now = sorted(_benched)
        _save_bench()
    if not added and not removed:
        return benched_now, "Bench unchanged.", 200
    parts = []
    if added:
        parts.append("benched " + ", ".join(added))
    if removed:
        parts.append("un-benched " + ", ".join(removed))
    msg = "; ".join(parts)
    logger.info(f"Guardian bench change by operator: {msg}")
    try:
        db.add_guardian_action("bench", ", ".join(benched_now) or "(empty)", True, msg)
    except Exception:  # noqa: BLE001
        logger.exception("Guardian bench logging failed")
    return benched_now, (f"Bench updated ({msg}). Re-run the checklist for it "
                         "to take effect."), 200


def _clear_bench_after_start(run_id):
    """The bench is per-round: once the game start fires, it's spent."""
    with _benched_lock:
        if not _benched:
            return
        spent = ", ".join(sorted(_benched))
        _benched.clear()
        _save_bench()
    logger.info(f"Guardian bench cleared after game start: {spent}")
    try:
        db.add_guardian_action("bench", "(cleared)", True,
                               f"bench auto-cleared after game start — was: {spent}",
                               run_id)
    except Exception:  # noqa: BLE001
        logger.exception("Guardian bench-clear logging failed")


# ─────────────────────────────────────────────
# Checklist runs
# ─────────────────────────────────────────────

def _item_dict(check):
    return {
        "id": check.id,
        "title": check.title,
        "category": check.category,
        "severity": check.severity,
        "layman": check.layman,
        "fix": fixes_mod.get_fix_info(check.fix_id) if check.fix_id else None,
        "human_fix": check.human_fix,
        "ignorable": check.ignorable,
        "status": "pending",
        "detail": "",
    }


def start_run(trigger="manual"):
    """Kick off a checklist run in a background thread. Returns the run dict
    (or the currently-running one, so double-clicks don't double-run)."""
    global _active_run_id
    with _runs_lock:
        if _active_run_id:
            active = _runs.get(_active_run_id)
            if active and active["status"] == "running":
                return active
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        checklist = checks_mod.build_checklist(_mqtt_client)
        run = {
            "run_id": run_id,
            "status": "running",
            "trigger": trigger,
            "started": datetime.now().isoformat(),
            "finished": None,
            "verdict": None,
            "counts": {"total": len(checklist), "pass": 0, "fail": 0, "warn": 0, "skip": 0},
            "blockers": [],
            "items": [_item_dict(c) for c in checklist],
        }
        _runs[run_id] = run
        _active_run_id = run_id
        # keep memory bounded
        if len(_runs) > 20:
            for old in sorted(_runs)[:-20]:
                if old != run_id:
                    _runs.pop(old, None)
    thread = threading.Thread(target=_execute_run, args=(run_id, checklist), daemon=True)
    thread.start()
    return run


def _recompute_verdict(run):
    """Derive blockers + verdict from item statuses. Called when a run
    finishes and again whenever the operator Ignores an item — an
    'ignored' status drops the item out of both lists."""
    blockers = [it for it in run["items"]
                if it["status"] == "fail" and it["severity"] == "blocking"]
    warns = [it for it in run["items"] if it["status"] in ("fail", "warn")
             and it not in blockers]
    blocked = bool(blockers) or (config.GUARDIAN_BLOCK_ON_WARN and warns)

    run["blockers"] = [{"id": b["id"], "title": b["title"], "detail": b["detail"]}
                       for b in blockers]
    run["verdict"] = "blocked" if blocked else "ready"


def ignore_item(run_id, item_id):
    """Operator override: mark one ignorable fail/warn item as ignored for
    THIS run only and recompute the verdict. The next checklist run checks
    it again from scratch. Returns (run|None, message, http_status)."""
    run = _runs.get(run_id)
    if run is None:
        return None, "Unknown checklist run — re-run the checklist.", 404
    if run["status"] != "finished":
        return None, "Checklist still running — wait for the verdict.", 409
    item = next((it for it in run["items"] if it["id"] == item_id), None)
    if item is None:
        return None, f"No checklist item '{item_id}'.", 404
    if not item.get("ignorable"):
        return None, f"'{item['title']}' cannot be ignored — fix it and re-run.", 403
    if item["status"] == "ignored":
        return run, f"'{item['title']}' is already ignored for this run.", 200
    if item["status"] not in ("fail", "warn"):
        return None, f"'{item['title']}' is not failing — nothing to ignore.", 409

    prev = item["status"]
    item["status"] = "ignored"
    item["detail"] = f"IGNORED by operator (was {prev}: {item['detail']})"
    run["counts"][prev] = max(0, run["counts"].get(prev, 0) - 1)
    run["counts"]["ignored"] = run["counts"].get("ignored", 0) + 1
    _recompute_verdict(run)

    logger.info(f"Guardian item IGNORED by operator: {item_id} on run {run_id} "
                f"(verdict now {run['verdict'].upper()})")
    try:
        db.add_guardian_action("ignore", item_id, True,
                               f"operator ignored '{item['title']}' — {item['detail']}",
                               run_id)
    except Exception:  # noqa: BLE001
        logger.exception("Guardian ignore logging failed")
    return run, f"'{item['title']}' ignored for this game.", 200


# Checks the owner has pre-approved for HANDS-OFF remediation (2026-08-17
# directive: "don't even bother giving me the correction, just restart it").
# A fail on these runs the fix WITHOUT the Approve click, then re-runs the
# check so the item shows the fresh truth. The gates (never mid-game, one
# attempt per 2h) and the fall-back-to-plain-alert live in auto_remediate.py.
AUTO_FIX_CHECKS = {"m3_freshness", "ai_launcher"}


def _try_auto_fix(check, ctx, detail):
    """Attempt the pre-approved remediation for a failed check. Returns the
    item's final (status, detail) — the original fail text is kept whenever
    a gate held the fix back or it didn't stick."""
    import auto_remediate
    try:
        if check.id == "m3_freshness":
            res = auto_remediate.try_restart_m3(_mqtt_client)
        else:
            res = auto_remediate.try_start_ai_launcher(_mqtt_client)
    except Exception as e:  # noqa: BLE001 - a crashed fix never crashes the run
        logger.exception(f"Guardian auto-fix for {check.id} crashed")
        return "fail", f"{detail} (auto-fix crashed: {e})"
    if not res["ran"]:
        return "fail", f"{detail} ({res['note']})"
    if not res["ok"]:
        return "fail", f"{detail} — {res['note']}"
    # Fix verified — re-run the check so the verdict reflects reality.
    try:
        rerun = check.func(ctx)
        status, fresh = rerun[0], rerun[1]
    except Exception as e:  # noqa: BLE001
        status, fresh = "warn", f"re-check after the fix crashed: {e}"
    return status, f"AUTO-FIXED without an Approve click ({res['note']}) — {fresh}"


def _execute_run(run_id, checklist):
    global _active_run_id
    run = _runs[run_id]
    ctx = {"mqtt": _mqtt_client, "benched": set(get_benched())}
    for i, check in enumerate(checklist):
        item = run["items"][i]
        item["status"] = "running"
        try:
            result = check.func(ctx)
            # Checks may return (status, detail) or (status, detail, fix_id) —
            # the 3-tuple form attaches a one-click fix for THIS failure mode
            # only (e.g. routing_verify offers the full M3 restart only when a
            # restart is actually the documented cure).
            if len(result) == 3:
                status, detail, extra = result
                if isinstance(extra, dict):
                    # Per-outcome overrides (2026-08-18): a check may replace
                    # its static description/fix when THIS outcome makes the
                    # always-there text misleading (e.g. unreal_room's warn
                    # "not running yet" vs the 08-01 wrong-map story).
                    # Keys: "layman", "human_fix" (str or None),
                    # "fix" (fix_id str, or None to suppress the static fix).
                    if "layman" in extra:
                        item["layman"] = extra["layman"]
                    if "human_fix" in extra:
                        item["human_fix"] = extra["human_fix"]
                    if "fix" in extra:
                        fid = extra["fix"]
                        item["fix"] = fixes_mod.get_fix_info(fid) if fid else None
                else:
                    item["fix"] = fixes_mod.get_fix_info(extra)
            else:
                status, detail = result
        except Exception as e:  # noqa: BLE001 - a crashed check is a failed check
            status, detail = "fail", f"check crashed: {e}"
            logger.exception(f"Guardian check {check.id} crashed")
        if status == "fail" and check.id in AUTO_FIX_CHECKS:
            status, detail = _try_auto_fix(check, ctx, detail)
        item["status"] = status
        item["detail"] = detail
        run["counts"][status] = run["counts"].get(status, 0) + 1

    _recompute_verdict(run)
    run["finished"] = datetime.now().isoformat()
    run["status"] = "finished"
    with _runs_lock:
        _active_run_id = None

    # Persist + log failures (once per open issue, so reruns don't spam).
    try:
        db.add_guardian_run(
            run_id, run["started"], run["finished"], run["verdict"],
            {"total": run["counts"]["total"], **run["counts"]},
            json.dumps(run["items"]), run["trigger"],
        )
        for it in run["items"]:
            if it["status"] != "fail":
                continue
            title = f"Guardian: {it['title']} failed"
            if not db.has_open_debug_entry(title):
                db.add_debug_entry(
                    device_name=it["id"][7:] if it["id"].startswith("device_") else None,
                    severity="error" if it["severity"] == "blocking" else "warning",
                    title=title,
                    description=f"{it['detail']}\n\nWhy it matters: {it['layman']}",
                    created_by="guardian",
                )
    except Exception:  # noqa: BLE001
        logger.exception("Guardian run persistence failed")

    logger.info(f"Guardian run {run_id}: {run['verdict'].upper()} "
                f"({run['counts']['fail']} fail / {run['counts']['warn']} warn "
                f"/ {run['counts']['pass']} pass)")


def get_run(run_id):
    return _runs.get(run_id)


def latest_run():
    with _runs_lock:
        if not _runs:
            return None
        return max(_runs.values(), key=lambda r: r["started"])


# ─────────────────────────────────────────────
# Fixes (the API call = operator approval)
# ─────────────────────────────────────────────

def apply_fix(fix_id):
    fix = fixes_mod.FIXES.get(fix_id)
    if not fix:
        return {"ok": False, "output": f"unknown fix '{fix_id}'"}
    logger.info(f"Guardian fix APPROVED by operator: {fix_id}")
    result = fix["run"]({"mqtt": _mqtt_client})
    try:
        db.add_guardian_action("fix", fix_id, result["ok"], result["output"])
        db.add_debug_entry(
            device_name=None, severity="info",
            title=f"Guardian fix run: {fix['title']}",
            description=f"Result: {'OK' if result['ok'] else 'FAILED'}\n{result['output']}",
            resolution=result["output"] if result["ok"] else None,
            created_by="guardian",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Guardian fix logging failed")
    return result


# ─────────────────────────────────────────────
# Game start / stop
# ─────────────────────────────────────────────

def _launch_bat(path, extra_env=None):
    """Fire a bat in its own console window, detached from us. The window has
    to be visible on the game PC — the launcher has interactive steps (mic
    check, routing retry) a human answers there."""
    env = None
    if extra_env:
        env = {**os.environ, **extra_env}
    subprocess.Popen(
        f'start "" /D "{os.path.dirname(path)}" "{path}"',
        shell=True,
        env=env,
    )


def start_game(run_id, ai_system=None):
    """The gate. Refuses unless the given run finished READY within the
    freshness window. There is deliberately NO override here — fix the
    blockers or don't start."""
    run = _runs.get(run_id) if run_id else None
    if run is None:
        return False, ("No checklist run supplied. Run the Pre-Game Checklist first — "
                       "the game only starts off a fresh passing checklist."), 409
    if run["status"] != "finished":
        return False, "Checklist still running — wait for the verdict.", 409
    if run["verdict"] != "ready":
        names = ", ".join(b["title"] for b in run["blockers"][:6])
        return False, (f"BLOCKED — {len(run['blockers'])} show-stopper(s) failed: {names}. "
                       "Fix them and re-run the checklist."), 409
    age = (datetime.now() - datetime.fromisoformat(run["finished"])).total_seconds()
    if age > config.GUARDIAN_RUN_FRESH_S:
        return False, (f"That passing checklist is {int(age / 60)} min old "
                       f"(limit {config.GUARDIAN_RUN_FRESH_S // 60} min). "
                       "Re-run it — things change."), 409
    if not os.path.exists(config.START_BAT):
        return False, f"START bat missing: {config.START_BAT}", 500

    # 2026-08-24: bench passthrough. If WatchTower's routing check was skipped
    # because every FAIL named operator-benched gear (dead ship-left projector),
    # tell the bat so its own verify gate auto-skips instead of stalling at
    # "Press ENTER to retry, or S to skip" (tonight's 23:10 launch hang).
    extra_env = None
    for it in run["items"]:
        if (it["id"] == "routing_verify" and it["status"] == "skip"
                and it["detail"].startswith("BENCHED by operator")):
            extra_env = {"WT_ROUTING_BENCH_SKIP": "1"}
            break
    # 2026-09-22: AI character program switch (Parley V2 vs the old client).
    ai = (ai_system or config.AI_SYSTEM_DEFAULT or "v1").lower()
    if ai not in ("v1", "v2"):
        return False, f"Unknown AI system '{ai_system}' (v1 or v2).", 400
    extra_env = {**(extra_env or {}), "AI_SYSTEM": ai}
    ai_label = "Parley V2" if ai == "v2" else "old AI client (v1)"
    _launch_bat(config.START_BAT, extra_env)
    db.add_guardian_action("game_start", config.START_BAT, True,
                           f"launched off passing run {run_id}, AI={ai}", run_id)
    logger.info(f"Guardian: START_ESCAPE_ROOM.bat fired (run {run_id}, AI_SYSTEM={ai})")
    _clear_bench_after_start(run_id)
    return True, (f"Launcher fired with the AI characters on {ai_label}. Watch its console "
                  "window on the game PC — it has interactive steps (mic check, routing "
                  "verify). Systems will come online on the dashboard over the next ~3 minutes."), 200


def stop_game():
    if not os.path.exists(config.STOP_BAT):
        return False, f"STOP bat missing: {config.STOP_BAT}", 500
    _launch_bat(config.STOP_BAT)
    db.add_guardian_action("game_stop", config.STOP_BAT, True, "stop launched")
    logger.info("Guardian: STOP_ESCAPE_ROOM.bat fired")
    return True, "Shutdown launched — all game systems are being stopped.", 200


# Game-state snapshot for the UI (cached — PowerShell spawns are slow).
_state_cache = {"ts": 0.0, "procs": {}}


def game_state():
    now = time.time()
    if now - _state_cache["ts"] > 5:
        procs = {}
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "foreach ($n in @('EscapeRoom','Mystery')) { "
                 "if (Get-Process -Name $n -ErrorAction SilentlyContinue) "
                 "{ Write-Output ($n + '=1') } else { Write-Output ($n + '=0') } }"],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
            for line in out.splitlines():
                name, _, val = line.strip().partition("=")
                if name:
                    procs[name] = val == "1"
        except Exception:  # noqa: BLE001
            pass
        _state_cache["ts"] = now
        _state_cache["procs"] = procs
    procs = _state_cache["procs"]

    m3 = {}
    if _mqtt_client:
        m3 = _mqtt_client.get_system_signals().get("m3", {})
    game_running = (m3.get("detail") == "Running"
                    and m3.get("age_s") is not None and m3["age_s"] <= 120)

    return {
        "unreal_running": procs.get("EscapeRoom", False),
        "m3_running": procs.get("Mystery", False),
        "m3_state": m3.get("detail"),
        "game_in_progress": game_running,
        "recent_actions": db.get_guardian_actions(limit=8),
    }
