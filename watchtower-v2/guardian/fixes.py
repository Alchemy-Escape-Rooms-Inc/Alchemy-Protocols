"""
Guardian Fix Registry
======================
Software-only remediations for known failure modes. Every fix:
  - is ONLY run after the operator clicks Approve in the Game Control tab
    (the API call itself is the permission grant),
  - explains the problem and the action in plain English first,
  - is logged to guardian_actions + the debug log,
  - never publishes to a /command or /reset topic (reboot-loop landmine),
  - never pretends it can fix hardware — those checks carry human_fix
    instructions instead.

Each fix's run(ctx) returns {"ok": bool, "output": str}.
`ctx` is {"mqtt": MQTTClient or None}.
"""

import os
import sys
import time
import logging
import subprocess

import config

logger = logging.getLogger(__name__)

AI_BRAIN_CMD_TOPIC = "MermaidsTale/RedBeard/Cmd"


def _run(cmd, timeout=90, cwd=None):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, cwd=cwd,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out[-2000:]
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# ─────────────────────────────────────────────
# Fix implementations
# ─────────────────────────────────────────────

def fix_clear_retained(ctx):
    """Wipe every retained MermaidsTale/# topic + all /command //reset topics,
    using the same curated script the launcher runs (safe by design)."""
    script = os.path.join(config.SCRIPT_DIR, "clear_retained_mqtt.py")
    if not os.path.exists(script):
        return {"ok": False, "output": "clear_retained_mqtt.py not found"}
    ok1, out1 = _run([sys.executable, script, "wildcard"], cwd=config.SCRIPT_DIR)
    ok2, out2 = _run([sys.executable, script, "commands"], cwd=config.SCRIPT_DIR)
    # Resync the landmine tracker from the broker's actual retained store —
    # wipes done while WatchTower is connected arrive with retain=0 and are
    # otherwise invisible to it (the "still flagging after a wipe" bug).
    mc = ctx.get("mqtt")
    if mc:
        mc.refresh_retained_landmines()
    return {"ok": ok1 and ok2, "output": f"wildcard: {out1}\ncommands: {out2}"}


def fix_restart_m3(ctx):
    """Kill and relaunch Mystery.exe — the standing fix for wedged M3 audio."""
    _run(["taskkill", "/F", "/IM", f"{config.M3_PROCESS_NAME}.exe"], timeout=20)
    time.sleep(2)
    try:
        subprocess.Popen(f'start "" "{config.MYTHRIC_PATH}"', shell=True)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"relaunch failed: {e}"}
    time.sleep(4)
    return {"ok": True, "output": "Mystery.exe restarted — give it ~30s to reload the story, "
                                  "then run the checklist again"}


def fix_m3_volume(ctx):
    """Force every Mystery.exe mixer session to 100% and unmuted."""
    if not os.path.exists(config.SVCL_PATH):
        return {"ok": False, "output": "SoundVolumeView.exe not found"}
    ok1, out1 = _run([config.SVCL_PATH, "/SetVolume", "Mystery.exe", "100"], timeout=20)
    ok2, out2 = _run([config.SVCL_PATH, "/Unmute", "Mystery.exe"], timeout=20)
    return {"ok": ok1 and ok2,
            "output": "Mystery.exe mixer forced to 100% and unmuted on every device"}


def fix_default_output(ctx):
    """Pin the Windows default playback device to the OUT 1-10 Behringer master
    (all three roles — console/multimedia/communications)."""
    if not os.path.exists(config.SVCL_PATH):
        return {"ok": False, "output": "SoundVolumeView.exe not found"}
    results = []
    for role in ("0", "1", "2"):
        ok, _ = _run([config.SVCL_PATH, "/SetDefault",
                      r"BEHRINGER UMC 1820\Device\OUT 1-10\Render", role], timeout=20)
        results.append(ok)
    return {"ok": all(results),
            "output": "Default playback pinned to OUT 1-10 (BEHRINGER) on all three roles"}


def _make_pip_fix(package):
    def fn(ctx):
        ok, out = _run([sys.executable, "-m", "pip", "install", package], timeout=300)
        return {"ok": ok, "output": out}
    return fn


def fix_rebaseline_routing(ctx):
    """The ROUTING_MAP s9-s14 drift cure in one shot: rebaseline_routing.py
    (Behringer name restore + default re-pin if needed, name-matched AMT.xml
    PC:X remap, snapshot re-baseline, FULL M3 restart, verify). The script
    aborts rather than guess on any missing/ambiguous device name."""
    script = os.path.join(config.SCRIPT_DIR, "rebaseline_routing.py")
    if not os.path.exists(script):
        return {"ok": False, "output": f"{script} not found"}
    ok, out = _run([sys.executable, script], timeout=300, cwd=config.SCRIPT_DIR)
    tail = "\n".join(out.splitlines()[-12:])
    return {"ok": ok, "output": tail}


GPU_FIX_SCRIPT = r"C:\Tools\svcl\gpu_reenumerate_fix.ps1"


def fix_gpu_reenumerate(ctx):
    """ROUTING_MAP.md §9 cure for NVIDIA endpoint drift/re-enum: restart the
    RTX 4070 PCI device (elevated script), then a FULL M3 restart so
    Mystery.exe rebinds to the restored device list. Screens blink ~2s."""
    if not os.path.exists(GPU_FIX_SCRIPT):
        return {"ok": False, "output": f"{GPU_FIX_SCRIPT} not found"}
    ok, out = _run(
        ["powershell", "-NoProfile", "-Command",
         "Start-Process powershell -Verb RunAs -Wait -ArgumentList "
         f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{GPU_FIX_SCRIPT}'"],
        timeout=180)
    if not ok:
        return {"ok": False,
                "output": "Elevation failed — the UAC prompt was cancelled or timed out. "
                          "It appears on the PHYSICAL console: click YES there and approve "
                          f"this fix again. ({out or 'no output'})"}
    time.sleep(3)
    m3 = fix_restart_m3(ctx)
    return {"ok": m3["ok"],
            "output": "GPU device restarted (screens blinked ~2s, endpoints should be "
                      "back in order). Then: " + m3["output"]}


def fix_restart_unreal(ctx):
    """Kill EscapeRoom.exe and relaunch the newest packaged build (same pick
    rule as the START bat / check_game_build) so Unreal comes back fullscreen
    on its correct display, sitting in the ship start map."""
    exe = None
    try:
        names = sorted(
            (n for n in os.listdir(config.UNREAL_BUILDS_DIR)
             if n.startswith("Windows_") and n.endswith("_DEV")),
            reverse=True)
        for n in names:
            cand = os.path.join(config.UNREAL_BUILDS_DIR, n, "EscapeRoom.exe")
            if os.path.exists(cand):
                exe = cand
                break
    except OSError as e:  # noqa: BLE001
        return {"ok": False, "output": f"builds folder unreadable: {e}"}
    if not exe:
        return {"ok": False, "output": "no build folder with EscapeRoom.exe found"}
    _run(["taskkill", "/F", "/IM", f"{config.UNREAL_PROCESS_NAME}.exe"], timeout=20)
    time.sleep(3)
    # Same flags as START_ESCAPE_ROOM.bat step [9/10] (incl. the 2026-07-06
    # Lumen async-compute crash fix).
    args = ('-log -ResX=1920 -ResY=1080 -FrameRateLimit=60 '
            '-ExecCmds="r.ScreenPercentage 100, r.TSR.History.ScreenPercentage 100, '
            'sg.ShadowQuality 2, sg.GlobalIlluminationQuality 2, sg.ReflectionQuality 2, '
            'r.Lumen.HardwareRayTracing 0, r.RayTracing.Shadows 0, r.Lumen.AsyncCompute 0"')
    try:
        subprocess.Popen(f'start "" "{exe}" {args}', shell=True,
                         cwd=os.path.dirname(exe))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"relaunch failed: {e}"}
    # CRITICAL (bat step [9.5]): UE in borderless-fullscreen IGNORES window
    # position settings (rewrites them to -1 at boot) and picks its own
    # monitor — a bare relaunch lands on the wrong screen. The mover script
    # waits up to 90s for the window, then forces it onto the operator monitor.
    mover = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\move_main_window.ps1"
    if os.path.exists(mover):
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy",
                              "Bypass", "-File", mover],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            mover_note = " + window mover launched (snaps it to the operator monitor within ~90s)"
        except Exception as e:  # noqa: BLE001
            mover_note = f" (window mover failed to launch: {e})"
    else:
        mover_note = " (WARNING: move_main_window.ps1 not found — window may sit on the wrong screen)"
    return {"ok": True,
            "output": f"EscapeRoom.exe restarted from {os.path.basename(os.path.dirname(exe))}"
                      f"{mover_note} — give it ~60s to reach the ship start map, "
                      "then re-run the checklist"}


def fix_start_ai_launcher(ctx):
    """(Re)start ai_launcher.py — the AI Character program's supervisor and the
    only GameStart receiver on the AI side. Kills any existing launcher (and any
    orphaned character brain) FIRST so two launchers can never both spawn a
    brain on the next GameStart (= double RedBeard voices). PRE-GAME ONLY:
    mid-game the right button is Reset Brain (Cmd restart), not this.

    When the house AI program is Parley (config.AI_SYSTEM_DEFAULT == "v2") this
    starts PARLEY instead. 2026-10-04: with Parley offline the auto-fix brought
    up the old launcher, the check went green on its heartbeat, and a game not
    started from the Start button would have run on the old program."""
    if (config.AI_SYSTEM_DEFAULT or "v1").lower() == "v2":
        return fix_start_parley(ctx)
    script = os.path.join(config.SCRIPT_DIR, "ai_launcher.py")
    if not os.path.exists(script):
        return {"ok": False, "output": f"{script} not found"}
    # Command-line match on the two AI scripts only — never touches WatchTower's
    # app.py or the retained guard/sweeper pythons.
    _run(["powershell", "-NoProfile", "-Command",
          "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -match "
          "'ai_launcher\\.py|camera_conversation_client\\.py' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], timeout=30)
    time.sleep(1)
    try:
        # Visible console window, same as START bat step [10/10] — the AI's
        # session log streams there and the operator uses it.
        subprocess.Popen(f'start "AI Characters" cmd /k python "{script}"',
                         shell=True, cwd=config.SCRIPT_DIR)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"launch failed: {e}"}
    return {"ok": True,
            "output": "ai_launcher.py started in its own 'AI Characters' console window. "
                      "Its first heartbeat lands within ~30s — re-run the checklist after."}


def fix_start_parley(ctx):
    """Start Parley (the V2 AI character program) the way START bat step [2.96]
    does. The old program is stopped FIRST: both would answer GameStart (two
    RedBeards), and Parley's single-instance lock refuses to run beside the old
    client anyway. A Parley that is already up is asked to stop cleanly, then
    any leftover process is removed. PRE-GAME ONLY."""
    script = os.path.join(config.PARLEY_DIR, "parley.py")
    if not os.path.exists(script):
        return {"ok": False, "output": f"{script} not found"}
    stopper = os.path.join(config.PARLEY_DIR, "stop_parley.py")
    if os.path.exists(stopper):          # closes its ElevenLabs sessions; harmless when it is not running
        _run([sys.executable, stopper], timeout=30, cwd=config.PARLEY_DIR)
    # Command-line match on the AI scripts only — never touches WatchTower's
    # app.py or the retained guard/sweeper pythons.
    _run(["powershell", "-NoProfile", "-Command",
          "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -match "
          "'ai_launcher\\.py|camera_conversation_client\\.py|parley\\.py' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], timeout=30)
    time.sleep(1)
    try:
        subprocess.Popen(f'start "Parley" /min cmd /c "cd /d "{config.PARLEY_DIR}" && python parley.py"',
                         shell=True, cwd=config.PARLEY_DIR)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"launch failed: {e}"}
    return {"ok": True,
            "output": "Old AI program stopped; Parley started in its own minimised 'Parley' window. "
                      "Its first status beat lands within ~10s — re-run the checklist after."}


def fix_restart_brain(ctx):
    """Ask the AI machine's brain_watchdog to relaunch the AI character brain."""
    mc = ctx.get("mqtt")
    if not mc or not mc.connected:
        return {"ok": False, "output": "MQTT not connected — can't reach the brain watchdog"}
    result = mc.publish_raw(AI_BRAIN_CMD_TOPIC, "restart")
    if "error" in result:
        return {"ok": False, "output": result["error"]}
    return {"ok": True, "output": f"restart published on {AI_BRAIN_CMD_TOPIC} — "
                                  "give the brain ~30s to come back"}


# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────
# title/problem/action are the plain-English text shown on the Approve dialog.

def fix_start_helm(ctx):
    """Start the Helm audio brain minimized (same as START bat step [2.95/9])."""
    import os, time, socket
    helm_dir = os.path.join(config.SCRIPT_DIR, "Helm")
    subprocess.Popen(["powershell", "-NoProfile", "-Command",
                      f'Start-Process -FilePath python -ArgumentList "helm.py" -WorkingDirectory "{helm_dir}" -WindowStyle Minimized'],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(20):
        time.sleep(0.5)
        try:
            with socket.create_connection(("127.0.0.1", 52100), timeout=0.3):
                return {"ok": True, "output": "Helm started and listening on :52100"}
        except OSError:
            continue
    return {"ok": False, "output": "Helm did not come up within 10s - see Helm/logs/helm.log"}


FIXES = {
    "start_helm": {
        "title": "Start the Helm audio brain",
        "problem": "Helm is not running, so nothing can reach the room speakers: "
                   "M3's cues and the AI voices are all routed through it.",
        "action": "Launch Helm/helm.py minimized (it opens the Behringer OUT 1-10 "
                  "exclusively and starts listening for cues on MQTT). ~5 seconds.",
        "run": fix_start_helm,
    },
    "clear_retained": {
        "title": "Wipe stale MQTT leftovers",
        "problem": "Old retained messages are sitting on the broker and will replay "
                   "into devices the moment they reconnect — that's how games "
                   "self-start and boards reboot-loop.",
        "action": "Run the same safe wipe the launcher uses (clear_retained_mqtt.py "
                  "wildcard + commands). Device status repopulates within seconds.",
        "run": fix_clear_retained,
    },
    "restart_m3": {
        "title": "Restart the M3 story engine",
        "problem": "Mystery.exe has been running long enough that its audio is at "
                   "risk of silently dying mid-game (known long-run bug).",
        "action": "Close Mystery.exe and start it fresh. Takes about 30 seconds; "
                  "no story data is lost.",
        "run": fix_restart_m3,
    },
    "restart_m3_full": {
        "title": "Full M3 restart — rebind audio devices",
        "problem": "Mystery.exe locks in its speaker numbers ONCE, at startup. The "
                   "Windows device list has shifted since then (projectors going to "
                   "sleep or waking up does this), so M3 would fire sound effects "
                   "into the WRONG rooms.",
        "action": "Fully close every Mystery.exe process and relaunch it so it "
                  "re-binds to the current device list — the safe fix from "
                  "ROUTING_MAP.md section 8 (never the enforcer). Takes ~30s, no "
                  "story data is lost. Do NOT use mid-game. Re-run the checklist "
                  "after.",
        "run": fix_restart_m3,
    },
    "fix_m3_volume": {
        "title": "Restore M3's mixer volume",
        "problem": "Windows remembered a turned-down (or muted) volume slider for the "
                   "story engine and reapplies it every launch — sound effects "
                   "come out near-silent.",
        "action": "Force Mystery.exe to 100% volume and unmuted on every output device.",
        "run": fix_m3_volume,
    },
    "fix_default_output": {
        "title": "Re-pin the Windows default speaker",
        "problem": "The Windows default output drifted off the Behringer master — "
                   "Unreal's opening soundtrack plays to the default, so it's "
                   "currently going to the wrong (possibly dead) output.",
        "action": "Set 'OUT 1-10 (BEHRINGER UMC 1820)' as the Windows default "
                  "playback device on all three roles.",
        "run": fix_default_output,
    },
    "pip_openpyxl": {
        "title": "Install the missing Excel library",
        "problem": "Python can't load 'openpyxl'. The AI voiceline bridge needs it and "
                   "silently disables itself without it — scripted character lines "
                   "just don't play.",
        "action": "Run: pip install openpyxl",
        "run": _make_pip_fix("openpyxl"),
    },
    "pip_paho": {
        "title": "Install the missing MQTT library",
        "problem": "Python can't load 'paho-mqtt'; every helper script needs it to talk "
                   "to the room.",
        "action": "Run: pip install paho-mqtt",
        "run": _make_pip_fix("paho-mqtt"),
    },
    "pip_pyaudio": {
        "title": "Install the missing audio library",
        "problem": "Python can't load 'pyaudio'; the AI can't hear mics or route audio "
                   "without it.",
        "action": "Run: pip install pyaudio",
        "run": _make_pip_fix("pyaudio"),
    },
    "rebaseline_routing": {
        "title": "Rebaseline audio routing (one-shot drift cure)",
        "problem": "The Windows audio device order shifted (a projector endpoint "
                   "came or went, the USB interface re-enumerated, or the default "
                   "output moved), so M3's numbered speaker channels point at the "
                   "WRONG devices — sound effects would fire into the wrong rooms.",
        "action": "Run rebaseline_routing.py: restore Behringer names / re-pin the "
                  "default if needed, rewrite AMT.xml's PC:X numbers by matching "
                  "device NAMES against the last-known-good snapshot, re-baseline "
                  "the snapshot, fully restart Mystery.exe, and re-verify. Backs "
                  "up AMT.xml first; refuses to guess if a needed device is "
                  "missing. Do NOT use mid-game (it restarts M3). Takes ~30s.",
        "run": fix_rebaseline_routing,
    },
    "gpu_reenumerate": {
        "title": "Restart GPU audio endpoints + full M3 restart",
        "problem": "The NVIDIA HDMI audio endpoints vanished, renamed themselves, or the "
                   "whole Windows device list re-shuffled (the 07-21/07-30 incident class) — "
                   "so M3's speaker numbers and Unreal's room names point at the wrong or "
                   "missing outputs.",
        "action": "Run the documented ROUTING_MAP.md section 9 cure: restart the RTX 4070 "
                  "PCI device via the elevated fix script (all screens blink ~2 seconds — "
                  "if a UAC prompt appears on the physical console, click YES), then fully "
                  "restart Mystery.exe so it rebinds. Do NOT use mid-game. Re-run the "
                  "checklist after.",
        "run": fix_gpu_reenumerate,
    },
    "restart_unreal": {
        "title": "Restart the Unreal game build",
        "problem": "Unreal is sitting in the wrong map/screen state (e.g. jungle "
                   "visuals + music on the ship screens, the 08-01 incident) or its "
                   "window landed on the wrong display — guests would board to the "
                   "wrong scene.",
        "action": "Force-close EscapeRoom.exe and relaunch the newest packaged build "
                  "(the same one the START bat picks). It comes back fullscreen on "
                  "its configured display in the ship start map. Takes ~60s. Do NOT "
                  "use mid-game. Re-run the checklist after.",
        "run": fix_restart_unreal,
    },
    "start_ai_launcher": {
        "title": "Start the AI Character program",
        "problem": "The AI program that makes RedBeard and Evalee talk is not running, "
                   "is deaf, or the OLD program is up where Parley should be. In this "
                   "state the next game would run with silent characters, or on the "
                   "old program.",
        "action": "Stop any AI program that is running (old launcher, old brain, a "
                  "stuck Parley), then start the house AI program fresh: Parley when "
                  "AI_SYSTEM_DEFAULT is v2 (minimised 'Parley' window, first status "
                  "beat in ~10s), otherwise ai_launcher.py ('AI Characters' window, "
                  "heartbeat in ~30s). PRE-GAME ONLY — mid-game use Reset Brain "
                  "instead. Then re-run the checklist.",
        "run": fix_start_ai_launcher,
    },
    "restart_brain": {
        "title": "Restart the AI character brain",
        "problem": "The AI character process has gone quiet.",
        "action": "Publish a restart command to the brain watchdog (same as the "
                  "dashboard's Reset Brain button).",
        "run": fix_restart_brain,
    },
}


def get_fix_info(fix_id):
    fix = FIXES.get(fix_id)
    if not fix:
        return None
    return {"id": fix_id, "title": fix["title"],
            "problem": fix["problem"], "action": fix["action"]}
