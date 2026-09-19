"""
Guardian Checklist Definitions
================================
Every item that must be true before a game of A Mermaid's Tale can start.
Each check returns (status, detail) where status is one of:
    "pass"  — item verified good
    "fail"  — item broken (blocks game start if severity is "blocking")
    "warn"  — item off but the launcher or a human can absorb it
    "skip"  — item could not be evaluated (missing dep / not applicable now)

Checks receive a shared `ctx` dict: {"mqtt": MQTTClient} plus anything a
check caches for later checks (e.g. the device ping sweep results).

Severity:
    "blocking" — a fail here means the game WILL go wrong; start is refused.
    "advisory" — degraded-but-playable, or the START bat itself repairs it.
                 (config.GUARDIAN_BLOCK_ON_WARN=True makes these block too.)
"""

import os
import csv
import sys
import json
import re
import time
import socket
import shutil
import logging
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Optional

import config
from mqtt import DeviceStatus, DeviceType

logger = logging.getLogger(__name__)

# BAC controllers heartbeat every 5 min (HEARTBEAT_STANDARD); allow 2 cycles + slack.
BAC_HEARTBEAT_FRESH_S = 630

# When this module was loaded ≈ when WatchTower booted (used to tell "BAC is
# dead" apart from "WatchTower restarted and hasn't heard a heartbeat yet").
_PROCESS_START = time.time()


@dataclass
class Check:
    id: str
    title: str
    category: str
    severity: str                     # "blocking" | "advisory"
    layman: str                       # plain-English what/why for the operator
    func: Callable                    # (ctx) -> (status, detail)
    fix_id: Optional[str] = None      # auto-fix in guardian.fixes, if any
    human_fix: Optional[str] = None   # plain instructions when only a human can fix it
    ignorable: bool = False           # operator may Ignore a fail/warn for one run


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _tcp_check(host: str, port: int, timeout=4.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "pass", f"{host}:{port} answered"
    except OSError as e:
        return "fail", f"{host}:{port} unreachable ({e})"


def _powershell(cmd: str, timeout=10) -> str:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def _process_running(name: str) -> bool:
    out = _powershell(
        f"if (Get-Process -Name {name} -ErrorAction SilentlyContinue) "
        "{ 'YES' } else { 'NO' }"
    )
    return out == "YES"


# ─────────────────────────────────────────────
# Connections
# ─────────────────────────────────────────────

def check_broker_tcp(ctx):
    return _tcp_check(config.MQTT_BROKER, config.MQTT_PORT)


def check_wt_mqtt(ctx):
    mc = ctx.get("mqtt")
    if mc and mc.connected:
        return "pass", "WatchTower is live on the broker"
    return "fail", "WatchTower's own MQTT connection is down — device checks are blind"


def check_internet_voices(ctx):
    host, port = config.ELEVENLABS_ENDPOINT
    status, detail = _tcp_check(host, port, timeout=6.0)
    return status, detail


def check_a2f_endpoint(ctx):
    host, port = config.A2F_ENDPOINT
    return _tcp_check(host, port, timeout=4.0)


def check_docker(ctx):
    try:
        rc = subprocess.run(["docker", "version"], capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW).returncode
        if rc == 0:
            return "pass", "Docker daemon answering"
        return "warn", "Docker daemon not responding — the launcher will start Docker Desktop itself"
    except FileNotFoundError:
        return "warn", "docker CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return "warn", "docker version timed out — daemon likely starting up"


# ─────────────────────────────────────────────
# Files & Builds
# ─────────────────────────────────────────────

def check_game_build(ctx):
    try:
        names = sorted(
            (n for n in os.listdir(config.UNREAL_BUILDS_DIR)
             if n.startswith("Windows_") and n.endswith("_DEV")),
            reverse=True,
        )
    except OSError as e:
        return "fail", f"builds folder unreadable: {e}"
    for n in names:
        if os.path.exists(os.path.join(config.UNREAL_BUILDS_DIR, n, "EscapeRoom.exe")):
            ctx["newest_build"] = n
            return "pass", f"launching {n}"
    return "fail", "no build folder with EscapeRoom.exe found"


def check_bats_exist(ctx):
    missing = [p for p in (config.START_BAT, config.STOP_BAT) if not os.path.exists(p)]
    if missing:
        return "fail", "missing: " + ", ".join(os.path.basename(m) for m in missing)
    return "pass", "START + STOP launchers on disk"


def check_launcher_scripts(ctx):
    missing = [s for s in config.REQUIRED_LAUNCHER_SCRIPTS
               if not os.path.exists(os.path.join(config.SCRIPT_DIR, s))]
    missing += [f"AI\\{s}" for s in config.REQUIRED_AI_SCRIPTS
                if not os.path.exists(os.path.join(config.AI_DIR, s))]
    if missing:
        return "fail", "missing: " + ", ".join(missing)
    total = len(config.REQUIRED_LAUNCHER_SCRIPTS) + len(config.REQUIRED_AI_SCRIPTS)
    return "pass", f"all {total} launch scripts present"


def check_mythric_installed(ctx):
    if os.path.exists(config.MYTHRIC_PATH):
        return "pass", "Mystery.exe installed"
    return "fail", f"not found: {config.MYTHRIC_PATH}"


def _amt_blank_topics(path):
    """{element-name: True} for every element with topic=\"\" in an AMT xml."""
    tree = ET.parse(path)
    out = set()
    for elem in tree.iter():
        if "topic" in elem.attrib and elem.attrib["topic"].strip() == "":
            out.add(elem.attrib.get("name") or elem.attrib.get("id") or elem.tag)
    return out


def check_amt_xml(ctx):
    """The live story file. An editor save can WIPE a device's topic to \"\",
    deafening its triggers (the 2026-07-03 item3 save hit Cannons/BattleEnded/
    MapSolved). Some devices are legitimately topic-less (audio-only), so a
    wipe = blank in LIVE but non-blank in the newest backup."""
    import glob
    path = config.AMT_XML_LIVE
    if not os.path.exists(path):
        return "fail", f"live story file missing: {path}"
    try:
        live_blank = _amt_blank_topics(path)
    except ET.ParseError as e:
        return "fail", f"AMT.xml does not parse: {e}"

    baks = sorted(glob.glob(os.path.join(config.SCRIPT_DIR, "logs", "*AMT*")),
                  key=os.path.getmtime, reverse=True)
    if not baks:
        return "pass", (f"story file parses ({len(live_blank)} known topic-less devices; "
                        "no backup found to diff against)")
    try:
        bak_blank = _amt_blank_topics(baks[0])
    except ET.ParseError:
        return "pass", f"story file parses (newest backup unreadable, wipe-diff skipped)"
    wiped = live_blank - bak_blank
    if wiped:
        shown = ", ".join(sorted(wiped)[:8]) + ("…" if len(wiped) > 8 else "")
        return "fail", (f"{len(wiped)} device topic(s) WIPED vs backup "
                        f"{os.path.basename(baks[0])}: {shown}")
    return "pass", f"story file parses, no wiped topics vs {os.path.basename(baks[0])}"


def check_disk_space(ctx):
    try:
        free_gb = shutil.disk_usage("C:\\").free / (1024 ** 3)
    except OSError as e:
        return "skip", f"could not read disk usage: {e}"
    if free_gb < config.GUARDIAN_MIN_FREE_GB:
        return "warn", f"only {free_gb:.1f} GB free on C: (floor {config.GUARDIAN_MIN_FREE_GB} GB)"
    return "pass", f"{free_gb:.0f} GB free on C:"


# ─────────────────────────────────────────────
# Software Environment
# ─────────────────────────────────────────────

def _make_module_check(module: str):
    def fn(ctx):
        rc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).returncode
        if rc == 0:
            return "pass", f"{module} imports"
        return "fail", f"'import {module}' fails in {os.path.basename(sys.executable)}"
    return fn


def check_clickup_token(ctx):
    if config.CLICKUP_API_TOKEN:
        return "pass", "task sync configured"
    return "warn", "no ClickUp token — issues won't sync to task list"


# ─────────────────────────────────────────────
# Audio
# ─────────────────────────────────────────────

def check_out_master(ctx):
    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' "
            "-and $_.Name -match 'OUT 1-10' } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'MISSING' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and out != "MISSING":
        return "pass", out
    return "fail", "OUT 1-10 room-wide master not in Windows playback devices"


def check_default_output(ctx):
    """Unreal's opening ambience plays to the Windows DEFAULT output until the
    game pins its main mix itself (RoomAudioSubsystem per-projector feeds,
    2026-08-03 — ROUTING_MAP §12), so the default no longer carries the
    opening soundtrack; it remains the safe landing zone if XAudio2 ever
    chases a default-device change, and must stay the room-wide Behringer
    master. Driver/Windows updates love drifting it (2026-07-24: default
    drifted to a 6%-volume projector endpoint = silent opening soundtrack,
    back when the opening DID ride the default)."""
    # 2026-08-29 HELM: nothing game-side plays on the Windows default any more
    # (Unreal streams its mix to Helm; M3 sends cues; Helm owns OUT 1-10
    # exclusively). While Helm is up this check is informational only.
    import socket as _s
    try:
        with _s.create_connection(("127.0.0.1", 52100), timeout=0.3):
            return "skip", "Helm mode: no program uses the Windows default device (Helm owns the Behringer directly)"
    except OSError:
        pass

    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' "
            "-and $_.Default } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'NONE' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and "OUT 1-10" in out:
        return "pass", f"default output = {out}"
    return "fail", (f"Windows default output is '{out}' — must be OUT 1-10 "
                    "(BEHRINGER master); Unreal's opening ambience follows the default")


def check_pirate_mic(ctx):
    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' "
            "-and $_.Name -match 'Pirate Ship' } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'MISSING' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and out != "MISSING":
        return "pass", out
    return "fail", "'Pirate Ship Microphone' not in Windows recording devices"


def check_jungle_mic(ctx):
    """2026-09-17: Evalee's USB TONOR, renamed "Jungle Microphone" on 09-12.
    Windows ties that name to the USB PORT — move the mic to another port and
    it comes back as a plain "Microphone (N- TONOR...)" and Evalee quietly
    falls back to the slow, echoey camera audio."""
    try:
        out = _powershell(
            "$r = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' }; "
            "$d = $r | Where-Object { $_.Name -match 'Jungle Microphone' } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'MISSING|' + (($r | Where-Object { $_.Name -match 'TONOR' "
            "-and $_.Name -notmatch 'Pirate Ship' } | ForEach-Object { $_.Name }) -join '; ') }",
            timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and not out.startswith("MISSING"):
        return "pass", out
    stray = (out or "").partition("|")[2].strip()
    if stray:
        return "fail", ("'Jungle Microphone' not in Windows recording devices, but an unnamed "
                        f"TONOR is plugged in: {stray} — the mic probably moved to a different "
                        "USB port and lost its name")
    return "fail", "'Jungle Microphone' not in Windows recording devices"


def check_m3_app_volume(ctx):
    """Windows remembers Mystery.exe's mixer volume PER DEVICE and reapplies
    it forever — a 15% Ship slider silenced all M3 SFX across restarts."""
    if not os.path.exists(config.SVCL_PATH):
        return "skip", "SoundVolumeView not installed — can't audit per-app volume"
    if not _process_running(config.M3_PROCESS_NAME):
        return "skip", "Mystery.exe not running yet — will be checked after launch"
    dump = os.path.join(tempfile.gettempdir(), "guardian_svv.csv")
    try:
        subprocess.run([config.SVCL_PATH, "/scomma", dump], capture_output=True, timeout=20,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        problems = []
        with open(dump, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if "Mystery.exe" not in (row.get("Process Path") or ""):
                    continue
                vol_txt = (row.get("Volume Percent") or "").rstrip("%")
                vol = float(vol_txt) if vol_txt else None
                muted = (row.get("Muted") or "").lower() == "yes"
                dev = row.get("Device Name") or "?"
                if muted:
                    problems.append(f"MUTED on {dev}")
                elif vol is not None and vol < config.M3_APP_VOLUME_MIN:
                    problems.append(f"{vol:.0f}% on {dev}")
        if problems:
            return "fail", "; ".join(problems)
        return "pass", f"all Mystery.exe sessions ≥{config.M3_APP_VOLUME_MIN:.0f}%"
    except Exception as e:  # noqa: BLE001
        return "skip", f"volume audit failed: {e}"


def _prepend_detail(result, note):
    """Prefix a note onto a check result tuple (2- or 3-form)."""
    if len(result) == 3:
        return result[0], note + result[1], result[2]
    return result[0], note + result[1]


def _check_routing_verify_raw(ctx, _healed=False):
    """verify_routing.py cross-checks M3 AMT.xml PC:X refs, Unreal room
    substrings, and the AI output map against the live device list. The
    verifier itself is read-only; since 2026-08-17 (owner directive: "run it
    automatically first, then let me know") this CHECK auto-fires the
    matching remediation through auto_remediate's gates (never mid-game,
    loop-guarded) and re-verifies — the operator only sees a fail when the
    cure was held back or didn't take."""
    script = os.path.join(config.SCRIPT_DIR, "verify_routing.py")
    if not os.path.exists(script):
        return "skip", "verify_routing.py not found"
    try:
        proc = subprocess.run(
            [sys.executable, script], cwd=config.SCRIPT_DIR,
            capture_output=True, text=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return "fail", "verify_routing.py timed out (120s)"
    if proc.returncode == 0:
        return "pass", "M3 / Unreal / AI audio routing all agree with the live device list"
    if proc.returncode == 3:
        return "skip", "routing verify dependency missing (exit 3)"
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-6:])
    # Only real [FAIL] lines — the "RESULT: N FAIL / ..." summary line used to
    # sneak into this list and poison the all-M3 triage below (button never
    # showed even when a full M3 restart was the whole cure).
    fails = [ln.strip() for ln in (proc.stdout or "").splitlines()
             if ln.strip().startswith("[FAIL]")]
    # Benched gear (Bench Props panel): a physically dead projector's endpoint
    # CANNOT verify until the hardware is repaired, so fails that literally
    # name a benched item are excused for this round — same lifecycle as a
    # benched prop board (auto-clears when the game starts).
    benched = ctx.get("benched", set())
    excused = [f for f in fails if any(b.lower() in f.lower() for b in benched)]
    if excused:
        fails = [f for f in fails if f not in excused]
        if not fails:
            return "skip", ("BENCHED by operator — every routing fail names "
                            "benched gear: " + "; ".join(excused[:3]))
    detail = "; ".join(fails[:4]) or tail or f"exit {proc.returncode}"
    if len(fails) > 4:
        detail += f" ...and {len(fails) - 4} more fails"
    if excused:
        detail += (f" || {len(excused)} fail(s) excused — benched gear: "
                   + ", ".join(sorted(benched)))
    # Failure triage (ROUTING_MAP.md §8): if EVERY fail is an M3-* index
    # mismatch — no missing endpoints ("matches NO live"), no Behringer
    # rename ("OUT 0X" raw names) — then M3 is simply holding a stale device
    # list and the documented cure is a FULL Mystery.exe restart. Offer that
    # as a one-click fix. Anything else still needs human eyes first (wake
    # the projectors / run the rename script), so no button.
    all_text = " ".join(fails)  # triage against EVERY fail, not just the 4 shown
    if fails and all("M3-" in f for f in fails) \
            and "matches NO live" not in all_text and "OUT 0" not in all_text:
        # M3 holding a stale binding — auto-restart it (owner-approved class,
        # same remediation the stale-uptime detector fires), button fallback.
        if not _healed:
            import auto_remediate
            res = auto_remediate.try_restart_m3(ctx.get("mqtt"))
            if res["ran"] and res["ok"]:
                return _prepend_detail(
                    _check_routing_verify_raw(ctx, _healed=True),
                    "AUTO-FIXED: full M3 restart (stale device binding) || ")
            detail += f" || auto-restart: {res['note']}"
        return ("fail",
                detail + " || All endpoints present — M3 is holding a stale device "
                         "list; the one-click Full M3 restart below is the fix.",
                "restart_m3_full")
    # Endpoint MISSING outright ("matches NO live") with intact Behringer
    # names: rebaseline can't conjure a device back — the ROUTING_MAP s9 ELD
    # cure (GPU device restart) sometimes can, so that stays a one-click.
    # Topology losses (dead projector) need benching/hardware — human either way.
    if fails and "matches NO live" in all_text and "OUT 0" not in all_text:
        kinds = sorted({f.split()[1] for f in fails if len(f.split()) > 1})
        detail += (" || Failure types [" + ", ".join(kinds) + "] include a "
                   "MISSING endpoint — auto-rebaseline refuses to guess around "
                   "that. If the gear should be working, the one-click below "
                   "runs the ROUTING_MAP section 9 GPU-restart cure (screens "
                   "blink ~2s; click YES on any UAC prompt at the physical "
                   "console). If the gear is genuinely down, bench it or fix "
                   "the hardware, then re-run.")
        return "fail", detail, "gpu_reenumerate"
    # Index drift / re-enum with every needed name present — the exact class
    # rebaseline_routing.py cures end-to-end (name-matched AMT remap +
    # snapshot re-baseline + full M3 restart + verify). Auto-fire it, then
    # re-verify; the button is the fallback when the gates hold it back.
    if fails and "OUT 0" not in all_text:
        kinds = sorted({f.split()[1] for f in fails if len(f.split()) > 1})
        if not _healed:
            import auto_remediate
            res = auto_remediate.try_rebaseline_routing(ctx.get("mqtt"))
            if res["ran"] and res["ok"]:
                return _prepend_detail(
                    _check_routing_verify_raw(ctx, _healed=True),
                    "AUTO-HEALED: rebaseline_routing ran (name-matched AMT "
                    "remap + snapshot + full M3 restart) || ")
            detail += f" || auto-heal: {res['note']}"
        detail += (" || Failure types [" + ", ".join(kinds) + "] = the device "
                   "list drifted (re-enum class). One-click fix below runs "
                   "rebaseline_routing.py — the ROUTING_MAP s9-s14 cure in one "
                   "shot. Re-run the checklist after.")
        return "fail", detail, "rebaseline_routing"
    # Behringer names collapsed to raw OUT 0X: rebaseline_routing.py runs the
    # RESTORE_BEHRINGER_NAMES.ps1 recovery itself (no admin needed) before
    # remapping — offer it here too.
    if fails:
        if not _healed:
            import auto_remediate
            res = auto_remediate.try_rebaseline_routing(ctx.get("mqtt"))
            if res["ran"] and res["ok"]:
                return _prepend_detail(
                    _check_routing_verify_raw(ctx, _healed=True),
                    "AUTO-HEALED: rebaseline_routing ran (Behringer name "
                    "restore + AMT remap + full M3 restart) || ")
            detail += f" || auto-heal: {res['note']}"
        detail += (" || Behringer names collapsed to raw OUT 0X — the one-click "
                   "below runs rebaseline_routing.py, which restores the names "
                   "(RESTORE_BEHRINGER_NAMES.ps1, no admin) and remaps in one "
                   "shot. NEVER FINISH_AUDIO_RENAME.ps1 (svcl zombie trap).")
        return "fail", detail, "rebaseline_routing"
    return "fail", detail


def _routing_plain_english_v1(detail: str) -> str:
    """(superseded same day by _routing_plain_english below — kept for reference)
    2026-08-26 (operator: 'reword the explanation, it's a mess'): translate
    verify_routing's [FAIL] codes into plain sentences for the 'What this
    means' box. The raw codes stay in the detail line for logs/debugging."""
    import re
    fails = [seg.strip() for seg in re.split(r";\s*(?=\[FAIL\])", detail)
             if seg.strip().startswith("[FAIL]")]
    lines = []
    missing = []
    for f in fails:
        f = f.split(" || ")[0]
        m = re.search(r"Unreal feed (\w+): substring '([^']+)' matches NO live", f)
        if m:
            feed, name = m.groups()
            missing.append(name)
            lines.append(f"• The game (Unreal) sends its '{feed}' room sound to a "
                         f"speaker output called '{name}' — Windows no longer has "
                         f"an output by that name (projector dead, unplugged, or renamed).")
            continue
        m = re.search(r"M3-ANCHOR\s+'([^']+)' is live at PC:(\d+).*?but AMT\.xml plays NOTHING", f)
        if m:
            name, idx = m.groups()
            lines.append(f"• The story engine (M3) has no sounds pointed at '{name}' "
                         f"any more — it's now speaker #{idx} and M3's cue numbers "
                         f"shifted with the device list.")
            continue
        m = re.search(r"M3-ANCHOR\s+PC:(\d+) should be '([^']+)'.*?live device there is '([^']+)'", f)
        if m:
            idx, want, have = m.groups()
            lines.append(f"• M3 speaker #{idx} should be '{want}' but Windows now has "
                         f"'{have}' in that slot — the device list re-shuffled.")
            continue
        m = re.search(r"M3-RANGE.*?PC:(\d+).*?only PC:0-(\d+) exist", f)
        if m:
            idx, top = m.groups()
            lines.append(f"• M3 plays a sound on speaker #{idx}, but only #0–#{top} "
                         f"exist right now — that cue would go nowhere.")
            continue
        if "OUT 0" in f:
            lines.append("• The Behringer outputs lost their friendly names "
                         "(showing raw 'OUT 0X') — everything keyed on those names is blind.")
            continue
        lines.append("• " + re.sub(r"^\[FAIL\]\s+\S+\s+", "", f))
    if not lines:
        return ("Checks that the story engine (M3), the game (Unreal), and the AI "
                "voices all agree on which physical speaker each sound goes to.")
    tail = ""
    if missing:
        tail = (" Bottom line: a speaker output is MISSING, and no script can "
                "invent one — if that projector is dead/unplugged, bench it in "
                "Bench Props (or repair it); if it was REPLACED and now shows up "
                "under a new name, the routing needs a rebaseline (tell Tink).")
    elif any("M3" in ln or "speaker #" in ln for ln in lines):
        tail = (" Bottom line: every output exists, the numbering just drifted — "
                "the one-click fix below re-maps and restarts M3.")
    return "What the cross-check found:\n" + "\n".join(lines) + "\n" + tail.strip()



def check_helm_status(ctx):
    """Helm = the ONE audio brain (2026-08-28). Since AMT.xml audio actions are
    MQTT cues, M3 plays NOTHING unless Helm is up and owns the Behringer."""
    import socket as _s, os as _os, re as _re
    try:
        with _s.create_connection(("127.0.0.1", 52100), timeout=0.5):
            pass
    except OSError:
        return "fail", "Helm audio brain is NOT running (nothing on :52100) - every M3 cue and AI voice is silent"
    logp = _os.path.join(config.SCRIPT_DIR, "Helm", "logs", "helm.log")
    try:
        with open(logp, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-20000:]
        opens = [m.start() for m in _re.finditer(r"device OPEN", tail)]
        fails = [m.start() for m in _re.finditer(r"device open failed|stream finished/aborted", tail)]
        if fails and (not opens or fails[-1] > opens[-1]):
            return "fail", "Helm is running but its audio device is NOT open (see Helm/logs/helm.log) - Behringer unplugged or grabbed by another app?"
    except OSError:
        pass
    return "pass", "Helm up on :52100, Behringer OUT 1-10 open (exclusive)"

def check_routing_verify(ctx, _healed=False):
    """Wrapper: run the real check, then swap the static 'What this means'
    text for a plain-English translation of THIS run's failures."""
    result = _check_routing_verify_raw(ctx, _healed=_healed)
    status, detail = result[0], result[1]
    if status != "fail":
        return result
    layman, human = _routing_plain_english(detail)
    extra = {"layman": layman, "human_fix": human}
    if len(result) == 3:
        if isinstance(result[2], dict):
            extra = {**result[2], **extra}
        else:
            extra["fix"] = result[2]
    return status, detail, extra


def _routing_plain_english(detail: str):
    """2026-08-26 v2 (operator: 'I don't understand it, rewrite it'): no
    jargon at all. Groups the failures into a short PROBLEM / WHY / DO THIS.
    Returns (what_this_means, human_fix)."""
    import re
    fails = [seg.strip() for seg in re.split(r";\s*(?=\[FAIL\])", detail)
             if seg.strip().startswith("[FAIL]")]
    missing = []        # names the game/story look for that Windows doesn't have
    m3_drift = False    # story engine's speaker numbering is off
    names_lost = False  # Behringer outputs lost their names
    other = []
    for f in fails:
        f = f.split(" || ")[0]
        m = re.search(r"substring '([^']+)' matches NO live", f)
        if m:
            missing.append(m.group(1))
            continue
        if "OUT 0" in f:
            names_lost = True
            continue
        if re.search(r"M3-(ANCHOR|LIVE|RANGE)", f):
            m3_drift = True
            continue
        other.append(re.sub(r"^\[FAIL\]\s+\S+\s+", "", f))

    problem, why, todo = [], [], []
    if missing:
        uniq = sorted(set(missing))
        problem.append("The game is trying to play sound through a projector output "
                       "that Windows doesn't have any more: "
                       + ", ".join(f"'{n}'" for n in uniq) + ".")
        why.append("Projector outputs only exist while that projector is plugged in "
                   "and awake. A dead, unplugged, or swapped projector makes its "
                   "output disappear (a new projector shows up under a NEW name).")
        todo.append("If that projector is dead or unplugged: open Bench Props and "
                    "tick its name, then re-run.")
        todo.append("If it was just replaced: tell Tink 'the new projector is in' - "
                    "the sound map has to be re-pointed at the new name (2 min).")
        todo.append("If it should be working: check its power/HDMI, then try the "
                    "GPU-restart fix button.")
    if m3_drift:
        problem.append("The story engine (M3) has its speakers numbered wrong - "
                       "some sound cues would come out of the wrong speaker or none.")
        why.append("Windows re-shuffled the speaker list (this happens whenever a "
                   "projector or USB audio device comes or goes) and M3 is still "
                   "using the old numbering.")
        if not missing:
            todo.append("Approve the one-click fix below - it re-numbers M3's speakers "
                        "and restarts it. Nothing else needed.")
        else:
            todo.append("M3's numbering gets fixed automatically as part of the "
                        "re-point above; sort the projector out first.")
    if names_lost:
        problem.append("The Behringer speaker outputs lost their names (showing as "
                       "'OUT 01', 'OUT 02'...).")
        why.append("A Windows/driver hiccup wiped the friendly names everything "
                   "else keys on.")
        todo.append("Approve the one-click fix - it restores the names and re-maps.")
    for o in other:
        problem.append(o)
    if not problem:
        return ("Checks that the story engine, the game, and the AI voices all "
                "agree on which real speaker each sound comes out of.", None)
    text = ("PROBLEM: " + " ".join(problem)
            + "\n\nWHY: " + " ".join(why)
            + "\n\nDO THIS:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(todo)))
    return text, "See the DO THIS steps above."


# ─────────────────────────────────────────────
# MQTT State
# ─────────────────────────────────────────────

def check_retained_landmines(ctx):
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    with mc.lock:
        mines = dict(mc.retained_landmines)
    if not mines:
        return "pass", "no retained GameStart / command / reset topics on the broker"
    shown = ", ".join(sorted(mines)[:5]) + ("…" if len(mines) > 5 else "")
    return "warn", f"{len(mines)} retained landmine(s): {shown} (the launcher wipes these, or fix now)"


def check_boot_loops(ctx):
    """Fail only on an ACTIVE loop (a boot event in the last QUIET_S seconds).
    A board that looped but has been quiet since the fix is recovered — old
    events sitting in the 10-min window must not keep failing the gate."""
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    loops = mc.get_pregame_signals()["boot_loops"]
    active = {d: i for d, i in loops.items()
              if i["last_age_s"] <= config.PREGAME_BOOTLOOP_QUIET_S}
    if active:
        detail = ", ".join(f"{d} ({i['count']}x, last {int(i['last_age_s'])}s ago)"
                           for d, i in sorted(active.items()))
        return "fail", f"actively reboot-looping: {detail}"
    if loops:
        detail = ", ".join(f"{d} quiet for {int(i['last_age_s'])}s after {i['count']} reboots"
                           for d, i in sorted(loops.items()))
        return "pass", f"loop STOPPED (recovered): {detail}"
    return "pass", "no boards reboot-looping"


# A state answered within this window after our query counts as fresh; any
# older stored value is "what we happened to overhear once", not an answer.
_QUERY_FRESH_S = 10


def _prop_row_benched(row, benched):
    """Topic layout is MermaidsTale/<DeviceName>/... for prop boards, or
    <DeviceName>/get/... for BAC zone controllers (Shattic/Jungle) — a
    benched device's rows are excused whichever segment carries the name."""
    parts = row["topic"].split("/")
    return parts[0] in benched or (len(parts) > 1 and parts[1] in benched)


def _active_state_refresh(mc, props, benched):
    """Two kinds of prop rows can't be judged from passive traffic alone:

    1. BAC zone controllers (<Device>/get/...) publish inputs on CHANGE only
       and retain nothing — after a WatchTower restart their rows sit unseen
       forever. An empty <Device>/set/refresh makes the board dump every
       get/ topic (verified live on Shattic 2026-08-18: 120-topic dump;
       get/refresh does NOT work, that's the board's own announcement).
       Asked only when the row is unseen.
    2. Rows with a "query" (CoveDoor maglock, CabinDoor reed) whose state
       lives in a STATUS diag reply. Queried EVERY run — a stored maglock
       state from hours ago says nothing about the door right now.
    """
    unseen_bacs = {row["topic"].split("/")[0]
                   for row in config.PREGAME_PROP_STATES
                   if not row["topic"].startswith("MermaidsTale/")
                   and row["topic"] not in props
                   and not _prop_row_benched(row, benched)}
    query_rows = [row for row in config.PREGAME_PROP_STATES
                  if row.get("query") and not _prop_row_benched(row, benched)]
    if not unseen_bacs and not query_rows:
        return props
    for dev in sorted(unseen_bacs):
        mc.publish_raw(f"{dev}/set/refresh", "")
    for row in query_rows:
        mc.publish_raw(row["query"]["topic"], row["query"]["payload"])

    def _settled(snapshot):
        for row in config.PREGAME_PROP_STATES:
            if _prop_row_benched(row, benched):
                continue
            state = snapshot.get(row["topic"])
            if row.get("query"):
                if state is None or state["age_s"] > _QUERY_FRESH_S:
                    return False
            elif not row["topic"].startswith("MermaidsTale/") and state is None:
                return False
        return True

    deadline = time.time() + 6
    while time.time() < deadline:
        time.sleep(0.5)
        props = mc.get_pregame_signals()["props"]
        if _settled(props):
            break
    return props


def check_prop_positions(ctx):
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    benched = ctx.get("benched", set())
    props = mc.get_pregame_signals()["props"]
    props = _active_state_refresh(mc, props, benched)
    wrong, warn_wrong, unseen, benched_rows, checked = [], [], 0, 0, 0
    for row in config.PREGAME_PROP_STATES:
        if _prop_row_benched(row, benched):
            benched_rows += 1
            continue
        bucket = warn_wrong if row.get("warn") else wrong
        state = props.get(row["topic"])
        # A queried row (STATUS diag / BAC refresh) with no fresh answer is
        # NOT "fine, just quiet" — we asked and the board didn't say. List it
        # as unknown rather than silently passing. Passive-only rows that
        # simply haven't spoken since a WatchTower restart stay a footnote.
        queried = bool(row.get("query"))
        if state is None:
            if queried or row.get("warn"):
                bucket.append(f"{row['label']} — state UNKNOWN (no answer to "
                              "state query)")
            else:
                unseen += 1
            continue
        if queried and state["age_s"] > _QUERY_FRESH_S:
            bucket.append(f"{row['label']} — no fresh STATUS reply (last heard "
                          f"'{state['payload'][:40]}' {int(state['age_s'] / 60)} min ago)")
            continue
        checked += 1
        rej = row.get("reject_re")
        if rej and re.search(rej, state["payload"], re.I):
            bucket.append(f"{row['label']} = '{state['payload'][:40]}' "
                          f"(still SOLVED from the last game — send PUZZLE_RESET)")
            continue
        if rej:
            continue
        if row["expect"].lower() not in state["payload"].lower():
            shown = state["payload"]
            if "|" in shown:
                # STATUS diag payloads: show the field the expectation is
                # about (MAGLOCK:UNLOCKED), not a truncated diag string.
                key = row["expect"].split(":")[0].lower()
                shown = next((s for s in shown.split("|")
                              if key in s.lower()), shown)
            bucket.append(f"{row['label']} = '{shown[:40]}' "
                          f"(want {row['expect']})")
    if wrong or warn_wrong:
        lines = [f"• {w}" for w in wrong]
        lines += [f"• {w} [warn-only]" for w in warn_wrong]
        detail = "NOT in start position:\n" + "\n".join(lines)
        if wrong:
            return "fail", detail
        return "warn", (detail + "\nAll warn-only — the game CAN still start; "
                        "check these before guests board")
    notes = []
    if unseen:
        notes.append(f"{unseen} not reported yet")
    if benched_rows:
        notes.append(f"{benched_rows} skipped for benched props")
    note = f" ({'; '.join(notes)})" if notes else ""
    return "pass", f"all {checked} monitored props in start position{note}"


# ─────────────────────────────────────────────
# Game Systems
# ─────────────────────────────────────────────

def check_m3_freshness(ctx):
    """Stale Mystery.exe is the #1 known killer: audio wedges silently on
    long runs. If it's up past the limit, restart before the game."""
    out = _powershell(
        f"$p = Get-Process -Name {config.M3_PROCESS_NAME} -ErrorAction SilentlyContinue "
        "| Select-Object -First 1; if ($p) { $p.StartTime.ToString('o') } else { 'NOT_RUNNING' }")
    if out == "NOT_RUNNING":
        return "pass", "Mystery.exe not running — launcher starts it fresh"
    try:
        from datetime import datetime
        started = datetime.fromisoformat(out)
        uptime_h = (datetime.now(started.tzinfo) - started).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return "skip", f"could not parse Mystery.exe start time: {out!r}"
    if uptime_h >= config.M3_RESTART_AFTER_HOURS:
        return "fail", (f"Mystery.exe up {uptime_h:.1f}h "
                        f"(limit {config.M3_RESTART_AFTER_HOURS}h) — audio wedge risk")
    return "pass", f"Mystery.exe up {uptime_h:.1f}h"


def check_no_game_running(ctx):
    mc = ctx.get("mqtt")
    signals = mc.get_system_signals() if mc else {}
    m3 = signals.get("m3", {})
    if m3.get("detail") == "Running" and m3.get("age_s") is not None and m3["age_s"] <= 120:
        return "fail", "M3 story state is 'Running' — a game looks live right now"
    if _process_running(config.UNREAL_PROCESS_NAME):
        return "warn", "a stale EscapeRoom.exe is up — the launcher clears it automatically", {
            "layman": ("No game is actually in progress — a leftover/idle EscapeRoom.exe "
                       "is running. Harmless: the START bat kills any running copy before "
                       "launching fresh."),
            "human_fix": "No action needed — launch normally.",
        }
    return "pass", "no game in progress"


def _ai_launcher_process_running() -> bool:
    """True if a python process is running ai_launcher.py (command-line match,
    so WatchTower's own app.py / the guard+sweeper scripts never false-match)."""
    out = _powershell(
        "if (Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match 'ai_launcher\\.py' }) "
        "{ 'YES' } else { 'NO' }", timeout=20)
    return out == "YES"


def check_ai_launcher(ctx):
    """The AI Character program's supervisor (ai_launcher.py) is the ONLY
    receiver of GameStart on the AI side — it spawns the character brain when
    a game begins. 2026-07-15: it sat dead through a whole game and RedBeard/
    Evalee never existed, with nothing blocking the start. The brain itself
    only runs DURING games, so pre-game the launcher heartbeat
    (MermaidsTale/AILauncher/Heartbeat, every 30s) is the health signal."""
    mc = ctx.get("mqtt")
    if not mc or not mc.connected:
        return "skip", "WatchTower's MQTT is down — can't hear the launcher heartbeat"

    def _age():
        return mc.get_system_signals().get("ai_launcher", {}).get("age_s")

    age = _age()
    if age is not None and age <= config.AI_LAUNCHER_FRESH_S:
        return "pass", f"launcher heartbeat {int(age)}s ago"

    if _ai_launcher_process_running():
        # Right after a WatchTower restart we may simply not have heard a beat
        # yet (30s interval) — wait one full interval out before judging.
        deadline = time.time() + 40
        while time.time() < deadline:
            time.sleep(2)
            age = _age()
            if age is not None and age <= config.AI_LAUNCHER_FRESH_S:
                return "pass", f"launcher heartbeat {int(age)}s ago"
        return "fail", ("ai_launcher.py process is UP but its heartbeat is silent — its MQTT "
                        "connection is dead, so GameStart would never reach it and the AI "
                        "characters would never launch")

    if not _process_running(config.M3_PROCESS_NAME):
        return "pass", ("not running — normal before launch: M3 isn't up either (so no game "
                        "can start), and the START bat launches the AI at step [10/10]")
    return "fail", ("NOT RUNNING while the game stack is up — a game started now would run "
                    "with NO AI characters (RedBeard/Evalee silent the whole game)")


# Unreal publishes MermaidsTale/Unreal/RoomStatus every 5s ({"map","audioRoom"}).
# MUST match roomStatusTopic in the game's MQTTClientSubsystem.h and the mirror
# constants in routes/api.py. 20s = four missed heartbeats.
UNREAL_ROOM_FRESH_S = 20
UNREAL_PREGAME_MAP = "OceanLevel_Final"
# 2026-08-04: the START bat INTENTIONALLY boots the build to MainMenu and waits
# for a real player start (auto-firing GameStart would skip the menu). So a
# fresh launch legitimately sits in MainMenu — it's a valid pre-game state,
# same as the ship map. The 08-01 incident this check exists for was Unreal
# stuck in the JUNGLE, which both these sets still catch.
UNREAL_PREGAME_OK_MAPS = {UNREAL_PREGAME_MAP, "MainMenu"}


def check_unreal_room(ctx):
    """The packaged game must be sitting in the ship start map (screens AND
    background track) before guests board. 2026-08-01: a blank retained-erase
    on JungleEntered flipped Unreal into the jungle right after a GameReset —
    jungle music in the ship room and nothing flagged it."""
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    sig = mc.get_system_signals().get("unreal_room", {})
    age = sig.get("age_s")
    if age is None:
        # Override the static text: the 08-01 jungle story + "force-close and
        # relaunch" fix only make sense for a RUNNING game in the wrong map.
        return "warn", ("no RoomStatus heartbeat seen — Unreal not running yet, or the "
                        "running build predates the heartbeat (pre 2026-08-01)"), {
            "layman": ("Unreal isn't running at all right now — normal before launch: "
                       "the START bat boots the game itself (into MainMenu, a valid "
                       "start state). The wrong-map hazard this check guards against "
                       "only applies to an already-running game."),
            "fix": None,
            "human_fix": ("Nothing to do if you're launching via the START bat — it "
                          "boots Unreal for you. Only investigate if a game build "
                          "should already be up."),
        }
    if age > UNREAL_ROOM_FRESH_S:
        return "fail", f"RoomStatus heartbeat lost {int(age)}s ago — game hung or its MQTT went deaf"
    try:
        data = json.loads(sig.get("detail") or "{}")
    except ValueError:
        data = {}
    map_name = data.get("map") or "?"
    room = data.get("audioRoom") or "?"
    if map_name in UNREAL_PREGAME_OK_MAPS:
        return "pass", f"Unreal in '{map_name}' (audio→{room}) — ship start map confirmed"
    return "fail", f"Unreal is sitting in '{map_name}' (audio→{room}) — not the ship start map"


# ─────────────────────────────────────────────
# Pirate wheel (Fanatec force-feedback wheel = the ship's steering)
# ─────────────────────────────────────────────

# Fanatec wheel base = USB VID_0EB7 / PID_0007. It only enumerates while the
# base is POWERED ON, so "on the USB bus" == "switched on". Every earlier
# plug-in leaves a ghost entry in PnP with Status=Unknown — -PresentOnly
# filters those out (09-06: 4 ghosts on 4 different hub paths, 0 present).
WHEEL_USB_ID = "VID_0EB7&PID_0007"
# BP_Ship publishes MermaidsTale/WheelPos = pre_<angle> every tick the angle
# changes, SHIP MAP ONLY (09-05 wire log: stream starts 35s after the USB
# arrival, idle gaps up to 83s while the wheel sits still, stops dead the
# second Unreal loads the jungle). So "no angle lately" is not "not read".
WHEEL_READ_FRESH_S = 600
WHEEL_CATEGORY = "Prop Boards — Ship Deck"
WHEEL_BENCH_NAME = "Pirate Wheel"          # BENCH_GEAR key in guardian/__init__


def check_pirate_wheel(ctx):
    """Wheel ON = Fanatec base present on USB (-PresentOnly). Wheel READ =
    the game has published a WheelPos angle recently, or at least once since
    this Unreal booted (idle wheel = no new reports, not a fault)."""
    if WHEEL_BENCH_NAME in ctx.get("benched", ()):
        return "skip", "BENCHED by operator for this round"
    like = f"'USB\\{WHEEL_USB_ID}\\*'"
    try:
        out = _powershell(
            "$p = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.InstanceId -like {like} }}); "
            "if ($p.Count -gt 0) { 'PRESENT ' + $p[0].Status } else { "
            f"$g = Get-PnpDevice | Where-Object {{ $_.InstanceId -like {like} }} | "
            "ForEach-Object { (Get-PnpDeviceProperty -InstanceId $_.InstanceId "
            "-KeyName DEVPKEY_Device_LastRemovalDate -ErrorAction SilentlyContinue).Data } | "
            "Sort-Object -Descending | Select-Object -First 1; 'ABSENT ' + $g }",
            timeout=40)
    except Exception as e:  # noqa: BLE001
        return "skip", f"USB device query failed: {e}"

    mc = ctx.get("mqtt")
    sig = mc.get_system_signals() if mc else {}
    wheel = sig.get("wheel", {})
    w_age = wheel.get("age_s")
    angle = (wheel.get("detail") or "?").replace("pre_", "")
    try:
        angle = f"{float(angle):.0f}°"
    except ValueError:
        pass

    if out.startswith("ABSENT"):
        last = out[6:].strip()
        return "fail", ("Fanatec wheel base is NOT on the USB bus — powered off or unplugged"
                        + (f" (last seen leaving {last})" if last else ""))
    if not out.startswith("PRESENT"):
        return "skip", f"unexpected USB query result: {out!r}"
    usb = out[7:].strip() or "?"
    if usb.upper() != "OK":
        return "fail", (f"wheel is on the USB bus but Windows reports status '{usb}' — "
                        "driver/port fault, reseat the USB cable")

    if w_age is not None and w_age <= WHEEL_READ_FRESH_S:
        return "pass", (f"wheel ON (USB OK) and the game is reading it — "
                        f"angle {angle} reported {int(w_age)}s ago")
    boot_age = sig.get("unreal_boot", {}).get("age_s")
    if w_age is not None and boot_age is not None and w_age <= boot_age:
        return "pass", (f"wheel ON (USB OK); game read it this boot — last angle {angle} "
                        f"{int(w_age)}s ago (a still wheel sends nothing new)")
    room_age = sig.get("unreal_room", {}).get("age_s")
    if room_age is None or room_age > UNREAL_ROOM_FRESH_S:
        return "warn", ("wheel ON (USB OK) but Unreal isn't running, so nothing is reading "
                        "it yet"), {
            "layman": ("The wheel is powered and Windows sees it. Only the game can prove "
                       "it's being READ, and the game isn't up yet — normal before the "
                       "START bat. Re-run once Unreal is on the ship."),
            "human_fix": ("Launch via the START bat, then give the wheel a turn and re-run "
                          "the checklist."),
        }
    since = f"for {int(w_age)}s" if w_age is not None else "since WatchTower started"
    return "warn", (f"wheel ON (USB OK) but the game hasn't reported a wheel angle {since} "
                    "— give the wheel a turn and re-run"), {
        "layman": ("The wheel is powered and Windows sees it, but the game hasn't sent a "
                   "steering angle. A wheel nobody is touching sends nothing, so first "
                   "just turn it. If a turn still reports nothing, the game grabbed its "
                   "controller list before the wheel was on (08-25 failure) — it re-polls "
                   "at the skull key / course start, or restart the build."),
        "human_fix": ("Turn the wheel a quarter turn each way, re-run. Still nothing: "
                      "restart the game build via the START bat (wheel powered FIRST)."),
    }


# ─────────────────────────────────────────────
# Device sweep (one checklist item per prop board)
# ─────────────────────────────────────────────

def _ensure_device_sweep(ctx):
    """Ping every ESP32, wait for answers, then RETRY the silent ones with a
    generous wait. A power-saving ESP32 can take >10s to process its first
    PING after idle (BarrelPiston, 2026-07-10: 12s first reply, 200ms after)
    — the first ping wakes it, the retry proves it. Late PONGs inside
    LATE_PONG_GRACE_S flip a board back online (mqtt module), so the retry
    wait just has to outlast the wake-up. BACs are judged on their passive
    heartbeat instead (pinging them only wipes their known state)."""
    if ctx.get("sweep_done"):
        return
    mc = ctx["mqtt"]
    benched = ctx.get("benched", set())
    # Benched boards sit the round out — don't ping them, and above all don't
    # spend the 15s straggler retry waiting on a board we know is down.
    esp_names = [n for n, d in mc.devices.items()
                 if d.device_type == DeviceType.ESP32 and n not in benched]

    # 2026-08-26 (operator): the WaterFountain ESP32 shares the pump's
    # relay-switched power (Jungle relay 1, INVERTED: "On" = relay energized =
    # water + board OFF; "Off" = water + board ON). It is normally OFF, so a
    # plain ping always fails. To test it we must switch the fountain ON, wait
    # for the board to boot (~7s per the 08-26 wire log), ping, then switch it
    # OFF again. Never mid-game (M3 event 65 owns it during a game). Non-retained
    # publishes only - a retained relay command is the reboot-loop poison.
    fountain_powered = False
    if "WaterFountain" in esp_names:
        m3 = mc.get_system_signals().get("m3", {})
        game_live = (m3.get("detail") == "Running" and m3.get("age_s") is not None
                     and m3["age_s"] <= 120)
        if not game_live:
            mc.publish_raw("Jungle/set/relay1", "Off")   # fountain + board ON
            fountain_powered = True
            time.sleep(10)

    for name in esp_names:
        mc.ping_device(name)
    deadline = time.time() + config.ESP32_PING_TIMEOUT + 2
    while time.time() < deadline:
        with mc.lock:
            testing = any(d.status == DeviceStatus.TESTING for d in mc.devices.values())
        if not testing:
            break
        time.sleep(0.4)
    mc.check_timeouts()

    with mc.lock:
        stragglers = [n for n in esp_names
                      if mc.devices[n].status == DeviceStatus.OFFLINE]
    if stragglers:
        for name in stragglers:
            mc.ping_device(name)
        deadline = time.time() + 15  # outlast a slow wake, not just the 3s timeout
        while time.time() < deadline:
            mc.check_timeouts()
            with mc.lock:
                if all(mc.devices[n].status == DeviceStatus.ONLINE for n in stragglers):
                    break
            time.sleep(0.5)
        mc.check_timeouts()
    if fountain_powered:
        mc.publish_raw("Jungle/set/relay1", "On")        # fountain + board OFF again
    ctx["sweep_done"] = True


def _make_device_check(name: str):
    def fn(ctx):
        if name in ctx.get("benched", ()):
            return "skip", ("BENCHED by operator — sitting this round out; "
                            "the game will start without this prop answering")
        mc = ctx.get("mqtt")
        if not mc or not mc.connected:
            return "skip", "MQTT down — can't reach the board"
        _ensure_device_sweep(ctx)
        dev = mc.devices[name]
        if dev.device_type == DeviceType.BAC:
            if dev.last_test is None:
                # BACs heartbeat every 5 min; right after a WatchTower restart
                # silence is expected, not proof of death. Still a fail (the
                # gate must not pass an unproven zone controller), but say why.
                wt_up = time.time() - _PROCESS_START
                if wt_up < BAC_HEARTBEAT_FRESH_S:
                    return "fail", (f"no heartbeat yet — WatchTower restarted {int(wt_up)}s ago "
                                    "and BACs report every 5 min; re-run the checklist in a few minutes")
                return "fail", "no heartbeat seen since WatchTower started"
            from datetime import datetime
            age = (datetime.now() - dev.last_test).total_seconds()
            if age <= BAC_HEARTBEAT_FRESH_S:
                return "pass", f"heartbeat {int(age)}s ago"
            return "fail", f"last heartbeat {int(age / 60)} min ago"
        if dev.status == DeviceStatus.ONLINE:
            # A board that answers PING with a dead SENSOR passes every sweep
            # and silently breaks its puzzle mid-game — 2026-08-08: Cannon1
            # heartbeated 'VL6180X:FAIL' (the cannonball load sensor) all day,
            # the battle could never be won, and nothing said a word.
            if dev.sensor_faults:
                return "fail", ("board is ONLINE but SELF-REPORTS dead sensor(s): "
                                + ", ".join(dev.sensor_faults) +
                                " — its puzzle cannot be completed in this state")
            ms = f" ({dev.response_time_ms}ms)" if dev.response_time_ms else ""
            return "pass", f"answered ping{ms}"
        return "fail", f"no ping response ({dev.status.value})"
    return fn


# ─────────────────────────────────────────────
# The checklist
# ─────────────────────────────────────────────

def build_checklist(mqtt_client) -> list:
    checks = [
        # Connections
        Check("broker_tcp", "MQTT broker answering", "Connections", "blocking",
              "The message hub every prop, the story engine, and the game talk through. "
              "Nothing in the room works without it.",
              check_broker_tcp,
              human_fix="Check the broker PC (10.1.10.115) is on and Mosquitto is running."),
        Check("wt_mqtt", "WatchTower connected to broker", "Connections", "blocking",
              "WatchTower itself must be on the broker to test the prop boards below.",
              check_wt_mqtt),
        Check("internet_voices", "Internet for AI voices (ElevenLabs)", "Connections", "blocking",
              "The characters' voices are generated in the cloud — no internet means "
              "RedBeard and Evalee go mute mid-show.",
              check_internet_voices,
              human_fix="Check the internet connection / router. Voices cannot work offline."),
        Check("a2f_endpoint", "Face animation server (COMMANDCENTER)", "Connections", "advisory",
              "Drives RedBeard's mouth movement. If down, he still talks but his face freezes.",
              check_a2f_endpoint,
              human_fix="Check COMMANDCENTER (10.1.10.229) is on and its A2F Docker container is up."),
        Check("docker", "Docker daemon", "Connections", "advisory",
              "Runs the local face-animation container. The launcher can start Docker "
              "Desktop itself, it just adds ~2 min to launch.",
              check_docker),

        # Files & Builds
        Check("game_build", "Packaged game build on disk", "Files & Builds", "blocking",
              "The actual Unreal game the players see. The launcher auto-picks the "
              "newest dated build folder.",
              check_game_build),
        Check("bats_exist", "START / STOP launcher files", "Files & Builds", "blocking",
              "The two batch files that boot and shut down the whole room.",
              check_bats_exist),
        Check("launcher_scripts", "Launch helper scripts", "Files & Builds", "blocking",
              "The launcher calls ~13 helper scripts (retained-MQTT guards, audio "
              "verify, AI launcher…). A missing one breaks launch midway.",
              check_launcher_scripts),
        Check("mythric_installed", "M3 story engine installed", "Files & Builds", "blocking",
              "Mythric Mystery Master runs the story: puzzle triggers, room audio, cues.",
              check_mythric_installed),
        Check("amt_xml", "Story file (AMT.xml) intact", "Files & Builds", "blocking",
              "The story's wiring. A device with a blanked-out topic goes DEAF — its "
              "puzzle triggers silently never fire (this exact bug killed triggers on 7/3).",
              check_amt_xml,
              human_fix="Restore AMT.xml from the newest backup in EscapeRoom Pirate Original\\logs, "
                        "then fully restart M3."),
        Check("disk_space", "Disk space on C:", "Files & Builds", "advisory",
              "Unreal, logs, and audio caches all live on C:. A full disk crashes mid-game.",
              check_disk_space),

        # Software Environment
        Check("py_paho", "Python MQTT library", "Software Environment", "blocking",
              "Every helper script talks MQTT through this library.",
              _make_module_check("paho.mqtt.client"), fix_id="pip_paho"),
        Check("py_openpyxl", "Python Excel library (openpyxl)", "Software Environment", "blocking",
              "The AI's voiceline bridge silently disables itself without it — "
              "characters' scripted lines just don't play, no error shown.",
              _make_module_check("openpyxl"), fix_id="pip_openpyxl"),
        Check("py_pyaudio", "Python audio library (pyaudio)", "Software Environment", "blocking",
              "How the AI hears the mics and plays sound to the right speakers.",
              _make_module_check("pyaudio"), fix_id="pip_pyaudio"),
        Check("clickup_token", "ClickUp task sync", "Software Environment", "advisory",
              "Lets WatchTower file issues to the task list automatically.",
              check_clickup_token),

        # Audio
        Check("out_master", "Room-wide speaker master (OUT 1-10)", "Audio", "blocking",
              "The Behringer output every room hears. If Windows can't see it, the whole "
              "room is silent.",
              check_out_master,
              human_fix="Check the Behringer UMC1820 USB cable and power, then re-run."),
        Check("default_output", "Windows default output = Behringer master", "Audio", "blocking",
              "Unreal's opening soundtrack plays to whatever Windows calls the default "
              "output until the game's first room swap. Driver updates drift it — on "
              "07-24 it landed on a dead projector endpoint at 6% volume and the "
              "opening music vanished.",
              check_default_output, fix_id="fix_default_output",
              human_fix="Windows Sound settings → set 'OUT 1-10 (BEHRINGER UMC 1820)' as the "
                        "default output device, or approve the auto-fix."),
        Check("pirate_mic", "Pirate Ship microphone present", "Audio", "advisory",
              "How RedBeard hears the players. The AI voices (ElevenLabs) still play "
              "fine without it, so a missing mic doesn't block the show — but RedBeard "
              "can't hear answers, so grab the backup mic (always encouraged).",
              check_pirate_mic, ignorable=True,
              human_fix="Plug in / reseat the TONOR 'Pirate Ship Microphone' USB mic — or "
                        "swap in the backup mic — then re-run."),
        Check("jungle_mic", "Jungle microphone present", "Audio", "advisory",
              "How Evalee hears the players in the jungle. Without it she falls back "
              "to the camera's microphone — she still works, but hears late and hears "
              "her own echo, so answers get slow and confused.",
              check_jungle_mic, ignorable=True,
              human_fix="Plug the jungle TONOR USB mic back into the SAME USB port it was "
                        "in (Windows remembers the 'Jungle Microphone' name per port). If it "
                        "shows up as a plain 'Microphone (TONOR...)', it needs renaming — ask "
                        "Claude to re-apply the Jungle Microphone name — then re-run."),
        Check("m3_app_volume", "M3 mixer volume not turned down", "Audio", "blocking",
              "Windows remembers a per-app volume slider forever — a slider once left at "
              "15% silenced every sound effect through multiple restarts.",
              check_m3_app_volume, fix_id="fix_m3_volume"),
        Check("helm_status", "Helm audio brain running + owns the Behringer", "Audio", "blocking",
              "Since 2026-08-28 Helm is the only program that plays sound: M3's story "
              "cues and the AI voices are all sent to it. No Helm = silent room.",
              check_helm_status, fix_id="start_helm"),
        Check("routing_verify", "Audio routing cross-check", "Audio", "blocking",
              "Verifies the story engine, the game, and the AI all agree on which "
              "physical speaker each sound goes to. Wrong = SFX in the wrong room.",
              check_routing_verify,
              human_fix="Drift auto-heals first (rebaseline_routing.py via auto_remediate — "
                        "never mid-game, loop-guarded); you only see this fail when the heal "
                        "was held back or couldn't run. If a one-click fix is offered below, "
                        "approve it and re-run. A MISSING endpoint means gear: wake/power the "
                        "projector (or GPU-restart cure) — a physically DEAD projector can be "
                        "checked in Bench Props to excuse it for this round. "
                        "NEVER run audio_channel_enforcer.py."),

        # MQTT State
        Check("retained_landmines", "No stale MQTT leftovers", "MQTT State", "advisory",
              "Old 'retained' messages replay into devices when they reconnect — a stale "
              "GameStart re-triggers the game, a stale RESET reboot-loops a board. The "
              "launcher wipes these automatically, but wiping now is safer.",
              check_retained_landmines, fix_id="clear_retained"),
        Check("boot_loops", "No boards reboot-looping", "MQTT State", "blocking",
              "A board stuck rebooting loses its puzzle state mid-game.",
              check_boot_loops, fix_id="clear_retained",
              human_fix="If clearing retained MQTT doesn't stop it, power-cycle the board."),
        Check("prop_positions", "Props in start position", "MQTT State", "blocking",
              "Every prop with a readable start state, listed by name when it's wrong: "
              "jungle door closed, cove door locked (maglock — its limit switches can't "
              "sense closed), cabin door closed (piston reed), barrel piston idle (it "
              "has no position sensor), trident cabinet shut, compasses unsolved, "
              "driftwood unsolved, monkey totems off, Shattic inputs 0/1 (captain's "
              "magic mirror) on, water fountain off. Blocking rows stop the start until "
              "fixed or Ignored; warn-only rows (Shattic inputs, fountain) just warn.",
              check_prop_positions,
              human_fix="Walk the room and physically reset anything listed (scramble the "
                        "compasses, pull the driftwood pieces), then re-run — "
                        "or click Ignore to start this game anyway.",
              ignorable=True),

        # Game Systems
        Check("m3_freshness", "M3 story engine fresh (not stale)", "Game Systems", "blocking",
              "Mystery.exe's audio silently dies on long runs. Past 12 hours it must be "
              "restarted before a game.",
              check_m3_freshness, fix_id="restart_m3"),
        Check("ai_launcher", "AI Character program (launcher) alive", "Game Systems", "blocking",
              "The AI launcher is what boots RedBeard and Evalee the moment a game "
              "starts. If it's dead or deaf, the start signal fires into the void and "
              "the whole game runs with SILENT characters — no one notices until "
              "guests are mid-game (this exact failure happened on 7/15).",
              check_ai_launcher, fix_id="start_ai_launcher",
              human_fix="Open a console in 'EscapeRoom Pirate Original' and run "
                        "'python ai_launcher.py' (or approve the one-click fix), wait ~30s "
                        "for its first heartbeat, then re-run the checklist."),
        Check("no_game_running", "No game currently in progress", "Game Systems", "blocking",
              "Starting the launcher during a live game would kill it for the players inside.",
              check_no_game_running),
        Check("unreal_room", "Unreal sitting in the ship start map", "Game Systems", "blocking",
              "The game screens and background track must be on the SHIP before guests "
              "board. On 08-01 a reset silently flipped Unreal into the jungle — jungle "
              "music playing over the ship room with nothing flagging it.",
              check_unreal_room, fix_id="restart_unreal",
              human_fix="Fire a GameStart from the Game page (or restart the build via the "
                        "START bat) to put Unreal back on the ship, then re-run.",
              ignorable=True),
    ]

    # One checklist item per prop board — the room can't run with a dead puzzle.
    if mqtt_client:
        for name, dev in sorted(mqtt_client.devices.items(),
                                key=lambda kv: (kv[1].room, kv[0])):
            kind = "zone controller" if dev.device_type == DeviceType.BAC else "prop board"
            checks.append(Check(
                f"device_{name}", f"{dev.icon} {name}", f"Prop Boards — {dev.room}",
                "blocking",
                f"The {kind} for {name} ({dev.room}). If it doesn't answer, its puzzle "
                "is dead and the game can't be completed."
                + (" This board is normally powered OFF (it shares the pump relay), so "
                   "the checklist switches the fountain on, pings it, then switches it "
                   "off again - expect ~10s of water." if name == "WaterFountain" else ""),
                _make_device_check(name),
                human_fix=f"Check power/network on {name}. Try PING from the Device Registry; "
                          "power-cycle the board if it stays silent.",
            ))

    # Pirate wheel (2026-09-06): not an MQTT board, but it lives with the
    # Ship Deck props on the /game checklist — slot it right after them.
    wheel_check = Check(
        "pirate_wheel", "🎡 Pirate Wheel (feedback motor) on + being read", WHEEL_CATEGORY,
        "blocking",
        "The ship's steering wheel — the game reads it to steer the map crossing. "
        "The Fanatec base only shows up on USB while it's powered ON, so 'present' "
        "means 'on'; 'being read' means the game is publishing the wheel angle. "
        "On 08-25 the wheel was off at launch and guests spun a dead wheel the "
        "whole voyage. Idle wheel = no new angle, so a warn just asks for a turn.",
        check_pirate_wheel, ignorable=True,
        human_fix="Power on the Fanatec wheel base and check its USB cable to the PC, "
                  "then re-run. If it's on but unread, turn the wheel and re-run; "
                  "if still unread, restart the build (START bat) with the wheel on. "
                  "No wheel this round? Bench 'Pirate Wheel' in Bench Props or Ignore.",
    )
    ship_idx = [i for i, c in enumerate(checks) if c.category == WHEEL_CATEGORY]
    checks.insert(ship_idx[-1] + 1 if ship_idx else len(checks), wheel_check)

    return checks
