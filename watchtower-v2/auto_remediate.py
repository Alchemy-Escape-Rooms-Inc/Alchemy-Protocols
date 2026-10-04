"""
Auto-Remediation — owner-approved hands-off restarts
=====================================================
2026-08-17 owner directive on the stale-M3 alert: "when this error comes up
don't even bother giving me the correction, just automatically shut down M3
and restart it." Same treatment approved for the dead/deaf AI launcher.

Exactly THREE remediations live here:

  m3_restart    kill + relaunch Mystery.exe (guardian.fixes.fix_restart_m3,
                the standing audio-wedge cure — ~30s, no story data lost).
                Killing M3 releases its COM ports and the relaunch reclaims
                them; that's expected and fine (project_m3_grabs_com_ports).
  ai_launcher   kill any stuck copy + relaunch ai_launcher.py exactly the way
                the START bat step [10/10] does (fix_start_ai_launcher),
                then wait for its MQTT heartbeat.
  rebaseline_routing
                2026-08-17 owner directive on the PC:X drift banner ("write
                the script that does it all in one shot and have it run
                automatically every time this comes up first before letting
                me know"): run rebaseline_routing.py — the name-matched
                AMT.xml remap + snapshot re-baseline + FULL M3 restart +
                verify, the ritual done by hand for every ROUTING_MAP s9-s14
                incident. The script ABORTS itself (never guesses) on
                missing/ambiguous device names, so a held-back or failed
                attempt falls through to the normal alert.

Safety rails (identical for both):
  * NEVER while a game is in progress (M3 story State == Running, same signal
    check_no_game_running gates on) — mid-game the caller keeps the original
    alert so the operator still gets the manual guidance (Reset Brain etc.);
  * anti-loop guard: at most ONE attempt per remediation per
    AUTO_REMEDIATE_COOLDOWN_S (2h), persisted in auto_remediate_state.json so
    a WatchTower restart can't reset the guard;
  * a failed restart reports FAILED and the caller falls back to the original
    alert text — the owner is always told;
  * every attempt lands in the debug log (same trail Guardian fixes leave).

This module never publishes MQTT and never touches WatchTower itself.
"""

import os
import json
import time
import logging
import threading
import subprocess

import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ─────────────────────────────────────────────
# Cooldown state (persisted across WatchTower restarts)
# ─────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(config.AUTO_REMEDIATE_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state: dict):
    try:
        with open(config.AUTO_REMEDIATE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        logger.exception("auto-remediate state file write failed")


def _cooldown_left_s(key: str, cooldown_s: int | None = None) -> float:
    last = _load_state().get(key, {}).get("last_attempt_ts", 0)
    cooldown_s = cooldown_s or config.AUTO_REMEDIATE_COOLDOWN_S
    return max(0.0, cooldown_s - (time.time() - last))


def _mark_attempt(key: str):
    state = _load_state()
    state.setdefault(key, {})["last_attempt_ts"] = time.time()
    _save_state(state)


# ─────────────────────────────────────────────
# Gates + helpers
# ─────────────────────────────────────────────

def game_in_progress(mc) -> bool:
    """Same signal check_no_game_running / game_state() gate on: M3's story
    State is 'Running' and was heard recently. If MQTT is down we can't be
    sure — treat that as in-progress (never risk killing a live game)."""
    if not mc:
        return True
    m3 = mc.get_system_signals().get("m3", {})
    return bool(m3.get("detail") == "Running" and m3.get("age_s") is not None
                and m3["age_s"] <= 600)


def _process_up(name: str) -> bool:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"if (Get-Process -Name {name} -ErrorAction SilentlyContinue) "
             "{ 'YES' } else { 'NO' }"],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
        return out == "YES"
    except Exception:  # noqa: BLE001
        return False


def _debug_entry(severity: str, title: str, description: str):
    try:
        from models import database as db
        db.add_debug_entry(device_name=None, severity=severity, title=title,
                           description=description, created_by="auto_remediate")
    except Exception:  # noqa: BLE001
        logger.exception("auto-remediate debug entry failed")


def _attempt(key: str, mc, what: str, restart_fn, verify_fn,
             verify_timeout_s: int, cooldown_s: int | None = None) -> dict:
    """Run one gated remediation. Returns
    {"ran": bool, "ok": bool|None, "note": str} — ran=False means a gate
    held it back and the caller must keep the ORIGINAL alert text."""
    cooldown_s = cooldown_s or config.AUTO_REMEDIATE_COOLDOWN_S
    with _lock:
        if game_in_progress(mc):
            return {"ran": False, "ok": None,
                    "note": "auto-restart held back: a game looks live right now "
                            "(M3 story Running)"}
        left = _cooldown_left_s(key, cooldown_s)
        if left > 0:
            return {"ran": False, "ok": None,
                    "note": f"auto-restart already tried in the last "
                            f"{cooldown_s // 60} min "
                            f"({int(left / 60)} min of loop-guard left) — "
                            "it needs a human look"}
        _mark_attempt(key)

    logger.warning(f"Auto-remediation firing: {what}")
    try:
        result = restart_fn()
    except Exception as e:  # noqa: BLE001
        result = {"ok": False, "output": f"restart crashed: {e}"}

    ok = bool(result.get("ok"))
    if ok:
        # The fix launched; now prove the patient actually came back.
        ok = False
        deadline = time.time() + verify_timeout_s
        while time.time() < deadline:
            if verify_fn():
                ok = True
                break
            time.sleep(3)

    note = (f"auto-restarted OK ({result.get('output', '').strip()})" if ok
            else f"auto-restart FAILED — {result.get('output', '').strip() or 'came back but never verified alive'}")
    _debug_entry("info" if ok else "error",
                 f"Auto-fix {'succeeded' if ok else 'FAILED'}: {what}",
                 f"{note}\n\nFired automatically per the owner's standing "
                 "instruction (no Approve click). Loop guard: at most one "
                 f"attempt per {config.AUTO_REMEDIATE_COOLDOWN_S // 3600}h.")
    try:
        from models import database as db
        db.add_guardian_action("auto_fix", key, ok, note)
    except Exception:  # noqa: BLE001
        pass
    return {"ran": True, "ok": ok, "note": note}


# ─────────────────────────────────────────────
# The two approved remediations
# ─────────────────────────────────────────────

def try_restart_m3(mc) -> dict:
    """Stale Mystery.exe (audio-wedge limit) → kill + relaunch it, then verify
    the process is back (its uptime naturally resets, so the stale checks go
    green on their own next pass)."""
    if not os.path.exists(config.MYTHRIC_PATH):
        return {"ran": False, "ok": None,
                "note": f"auto-restart impossible: {config.MYTHRIC_PATH} not found"}

    def _restart():
        from guardian import fixes as guardian_fixes  # lazy: avoids import cycles
        return guardian_fixes.fix_restart_m3({"mqtt": mc})

    return _attempt("m3_restart", mc,
                    "restart stale Mystery.exe (M3 audio-wedge limit)",
                    _restart, lambda: _process_up(config.M3_PROCESS_NAME),
                    verify_timeout_s=30)


def try_start_ai_launcher(mc) -> dict:
    """Dead/deaf ai_launcher.py → kill any stuck copy and relaunch it the way
    the START bat does, then wait for a FRESH MQTT heartbeat (30s interval).
    PRE-GAME ONLY by the shared gate — mid-game the cure is Reset Brain."""

    def _restart():
        from guardian import fixes as guardian_fixes  # lazy: avoids import cycles
        return guardian_fixes.fix_start_ai_launcher({"mqtt": mc})

    parley = (config.AI_SYSTEM_DEFAULT or "v1").lower() == "v2"   # the fix starts Parley then, so verify Parley

    def _verify():
        if not mc:
            return False
        if parley:
            return mc.parley_alive()
        age = mc.get_system_signals().get("ai_launcher", {}).get("age_s")
        return age is not None and age <= 40

    return _attempt("ai_launcher", mc,
                    "start Parley (AI characters V2), replacing any old AI program" if parley
                    else "restart dead/deaf ai_launcher.py (AI Character supervisor)",
                    _restart, _verify, verify_timeout_s=45)


def try_rebaseline_routing(mc) -> dict:
    """waveOut PC:X drift (the ROUTING_MAP s9-s14 re-enum class) →
    rebaseline_routing.py heals it end-to-end: Behringer name restore +
    default-output re-pin if needed, name-matched AMT.xml PC:X remap,
    snapshot re-baseline, FULL M3 restart, verify. Exit 0 = healed (or
    nothing needed). The script aborts rather than guess on any missing/
    ambiguous device name, so 'ran but not ok' = a real topology loss that
    needs the owner (bench the gear / fix hardware).
    Cooldown is 30 min (not the 2h default): back-to-back drifts are normal
    when a projector is being power-cycled, and a successful heal is
    idempotent — a second run on a healthy list is a no-op."""
    script = os.path.join(config.SCRIPT_DIR, "rebaseline_routing.py")
    if not os.path.exists(script):
        return {"ran": False, "ok": None,
                "note": f"auto-heal impossible: {script} not found"}

    def _heal():
        import sys as _sys
        try:
            proc = subprocess.run(
                [_sys.executable, script], cwd=config.SCRIPT_DIR,
                capture_output=True, text=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW)
            tail = "\n".join((proc.stdout or "").strip().splitlines()[-12:])
            return {"ok": proc.returncode == 0, "output": tail}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "rebaseline_routing.py timed out (300s)"}

    def _verify():
        import sys as _sys
        try:
            proc = subprocess.run(
                [_sys.executable, script, "--detect"], cwd=config.SCRIPT_DIR,
                capture_output=True, text=True, timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return proc.returncode == 0
        except Exception:  # noqa: BLE001
            return False

    return _attempt("rebaseline_routing", mc,
                    "rebaseline audio routing (waveOut PC:X drift — AMT remap "
                    "+ snapshot + full M3 restart)",
                    _heal, _verify, verify_timeout_s=30, cooldown_s=1800)
