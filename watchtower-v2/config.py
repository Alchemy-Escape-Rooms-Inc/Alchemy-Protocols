"""
WatchTower V2 Configuration
============================
All settings for MQTT, ClickUp, database, and device registry.
"""

import os

# =============================================================================
# NETWORK
# =============================================================================
MQTT_BROKER = "10.1.10.115"
MQTT_PORT = 1883
WIFI_SSID = "AlchemyGuest"
WIFI_PASSWORD = "VoodooVacation5601"

# =============================================================================
# FLASK
# =============================================================================
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
SECRET_KEY = os.urandom(24).hex()

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "watchtower.db")

# =============================================================================
# CLICKUP
# =============================================================================
CLICKUP_API_TOKEN = os.environ.get("CLICKUP_API_TOKEN", "pk_114238061_3PZ4VQGN7J6D853HXZDYYH9QUMX5GJUD")
CLICKUP_WORKSPACE_ID = "9011667818"
CLICKUP_LIST_ID = "901113164349"  # WatchTower Issues list
CLICKUP_API_URL = "https://api.clickup.com/api/v2"

# =============================================================================
# TINK — RESIDENT FAIRY (Claude chat assistant)
# =============================================================================
# No API key anymore: Tink runs through the Claude Code CLI (`claude -p`),
# billing the operator's Claude subscription. Auth = the CLI's own /login.
TINK_MODEL = "claude-fable-5"
TINK_FALLBACK_MODEL = "claude-opus-4-8"   # CLI --fallback-model if Fable is overloaded/unavailable

# =============================================================================
# ALEXA SMART PLUGS (Power page)
# =============================================================================
# The 8 room switches are Amazon-brand Smart Plugs — cloud-only, no local API
# (verified 2026-07-23: zero open ports, no Matter). Control goes through the
# Alexa web API via alexapy. One interactive Amazon login through the capture
# proxy stores a refresh token under ALEXA_DATA_DIR (git-ignored); after that
# the session renews itself.
ALEXA_URL = "amazon.com"
ALEXA_DATA_DIR = os.path.join(os.path.dirname(__file__), "alexa_data")
ALEXA_PROXY_PORT = 5099   # login-capture proxy; only alive while linking

# =============================================================================
# M3 (MYTHRIC MYSTERY MASTER) PROCESS WATCH
# =============================================================================
# Mystery.exe runs on this same PC. Its audio wedges silently on long runs
# (story engine keeps working, all Mythric audio goes quiet) — the standing
# fix is a full app restart. The dashboard shows a restart banner once uptime
# crosses this line, and a not-running banner if the process is gone.
M3_PROCESS_NAME = "Mystery"        # process name, without .exe
M3_RESTART_AFTER_HOURS = 12
M3_UPTIME_CHECK_INTERVAL_S = 60    # cache window so the 2s poll doesn't spawn PowerShell each time

# =============================================================================
# GUARDIAN — PRE-GAME CHECKLIST GATE + GAME START/STOP CONTROL
# =============================================================================
# The Game Control tab runs the full checklist and will NOT fire the START bat
# unless every blocking item passes. Advisory items show but don't block —
# flip GUARDIAN_BLOCK_ON_WARN to True to make EVERYTHING block.
GUARDIAN_RUN_FRESH_S = 600          # a passing run older than this can't start a game
GUARDIAN_BLOCK_ON_WARN = False      # True = advisory warnings also block game start
GUARDIAN_MIN_FREE_GB = 10           # C: free-space floor (advisory)

SCRIPT_DIR = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original"
AI_DIR = SCRIPT_DIR + r"\AI Character System"
START_BAT = SCRIPT_DIR + r"\START_ESCAPE_ROOM.bat"
STOP_BAT = SCRIPT_DIR + r"\STOP_ESCAPE_ROOM.bat"
MYTHRIC_PATH = r"C:\Program Files (x86)\Mythric Mystery Master\bin\Mystery.exe"
AMT_XML_LIVE = r"C:\Program Files (x86)\Mythric Mystery Master\stories\AMT\AMT.xml"

# TCP endpoints the show depends on: (host, port, what-it-is)
A2F_ENDPOINT = ("10.1.10.229", 52000)        # COMMANDCENTER A2F NIM (face animation; was .228, DHCP moved it 2026-09-13 after a Wi-Fi drop)
ELEVENLABS_ENDPOINT = ("api.elevenlabs.io", 443)  # AI character voices (cloud)

# Launcher scripts the START bat calls — all must exist or launch breaks midway.
REQUIRED_LAUNCHER_SCRIPTS = [
    "enforce_displays.py", "audio_enforcer.py", "clear_retained_mqtt.py",
    "gamestart_retained_guard.py", "game_end_retained_sweeper.py",
    "m3_restart_story.py", "verify_routing.py", "a2f_preflight.py",
    "a2f_notify_session_start.py", "ai_launcher.py", "shutdown_ai_gracefully.py",
]
REQUIRED_AI_SCRIPTS = ["verify_audio_loopback.py", "mic_check.py"]

# Python modules a game session silently dies without (checked by import).
# openpyxl: VoicelineBridge disables itself without it -> AI voices silent.
REQUIRED_PY_MODULES = ["paho.mqtt.client", "openpyxl", "pyaudio"]

# AI Character launcher liveness. ai_launcher.py heartbeats
# MermaidsTale/AILauncher/Heartbeat every 30s (HEARTBEAT_INTERVAL_SEC there —
# keep in sync). It is the ONLY receiver of GameStart for the AI side: if it's
# dead or deaf when a game starts, no AI character ever launches and the whole
# game runs silent (the 2026-07-15 failure). 95s = three missed beats + slack.
AI_LAUNCHER_HEARTBEAT_TOPIC = "MermaidsTale/AILauncher/Heartbeat"
AI_LAUNCHER_FRESH_S = 95

# Parley (2026-09-22): the NEW AI character program. It has NO launcher — one
# process, always on, phases waiting|redbeard|jungle|cove|game_over. It keeps
# every old topic (RedBeard/Heartbeat, AI/Phase, AI/Direct[Result]) AND adds
# a retained JSON health beat every 10 s + one JSON receipt per story beat.
# MUST match the topic strings in Parley's own config (parley.yaml / mqtt.py).
AI_STATUS_TOPIC = "MermaidsTale/AI/status"          # retained, every 10 s
AI_BEAT_RESULT_TOPIC = "MermaidsTale/AI/BeatResult"  # one per beat
AI_STATUS_FRESH_S = 30                               # three missed beats
PARLEY_DIR = SCRIPT_DIR + r"\Parley"
PARLEY_BENCH_DIR = PARLEY_DIR + r"\bench"
PARLEY_BENCH_RESULT = PARLEY_BENCH_DIR + r"\last_run.json"      # bench suite
PARLEY_MIC_SELFTEST = PARLEY_BENCH_DIR + r"\mic_selftest.json"  # per-room mics
PARLEY_BENCH_MAX_AGE_D = 7      # bench suite result older than this = stale
PARLEY_MIC_MAX_AGE_D = 2        # mic self-test older than this = stale

# Battle→DefenseOver progression watchdog (2026-08-08). AI/StartBattle marks
# the battle beginning; the packaged game hard-caps the battle (~4m45s, then
# BattleEnded|timeout) and publishes DefenseOver|trigger. M3 event 92 must
# then advance the story — its wire signature is PowderSolved|true (+10s
# built-in delay). Tonight event 92 (type=Single, consumed by the 17:48 game)
# ignored a clean 21:32 DefenseOver|trigger and the story hung until a manual
# GM fire. Deadline = battle cap + event delay + slack; must NEVER be shorter
# than the battle cap or the watchdog would end a live battle early.
BATTLE_WATCHDOG_DEADLINE_S = 390     # 6.5 min after AI/StartBattle|trigger
BATTLE_WATCHDOG_RETRY_WAIT_S = 20    # after republish, before declaring stuck

# =============================================================================
# HEALTH SENTINEL — proactive 24/7 problem reporting (health_sentinel.py)
# =============================================================================
# 2026-08-08: Cannon1's load sensor screamed FAIL in its heartbeat ALL DAY and
# nothing surfaced it until a pre-game scan / log dig. The sentinel watches
# passively around the clock, raises each NEW problem the moment it appears
# (dashboard banner + debug log), and writes a morning Daily Report.
HEALTH_TICK_S = 60                  # detector cadence
HEALTH_DEVICE_SILENT_S = 900        # board silent this long = offline finding
HEALTH_NEVER_SEEN_GRACE_S = 1200    # WT must be up this long before "never seen" counts
HEALTH_FLAP_WINDOW_S = 1800         # flap analysis window
HEALTH_FLAP_GAP_S = 60              # a heartbeat hole this long = one gap
HEALTH_FLAP_MIN_GAPS = 3            # this many gaps in the window = flapping
HEALTH_FLAP_CHATTY_MEDIAN_S = 15    # only boards that normally beat faster than this
HEALTH_ENDPOINT_EVERY_TICKS = 5     # ElevenLabs/A2F TCP probe cadence (x TICK)
HEALTH_SLOW_EVERY_TICKS = 10        # disk + M3-uptime cadence (x TICK)
HEALTH_ROUTING_EVERY_TICKS = 5      # waveOut PC:X drift probe cadence (x TICK)
DAILY_REPORT_HOUR = 9               # local hour to write the Daily Report

# PID file so the START/STOP bats can spare the WatchTower process when they
# blanket-kill python.exe (WatchTower is the control plane pressing the button).
WATCHTOWER_PID_FILE = os.path.join(os.path.dirname(__file__), "watchtower.pid")

# =============================================================================
# AUTO-REMEDIATION (auto_remediate.py)
# =============================================================================
# 2026-08-17 owner directive: the stale-M3 and dead-AI-launcher alerts get
# FIXED automatically (restart the process) instead of just telling him to.
# Gated: never mid-game, and at most one attempt per remediation per cooldown
# (persisted so a WatchTower restart can't reset the loop guard).
AUTO_REMEDIATE_COOLDOWN_S = 7200    # 2h anti-restart-loop guard, per remediation
AUTO_REMEDIATE_STATE_FILE = os.path.join(os.path.dirname(__file__),
                                         "auto_remediate_state.json")

# =============================================================================
# ALYSSA CALLS — phone receptionist call history (routes/calls_api.py)
# =============================================================================
# Alyssa is the ElevenLabs voice agent on the business line. Her call history
# only lives in ElevenLabs; the /calls page pulls it through their API. The
# key + agent id are read from the alyssa-avatar repo's .env (never committed)
# unless ELEVENLABS_API_KEY / ALYSSA_AGENT_ID are set in the environment.
ALYSSA_ENV_PATH = r"C:\Users\Alchemy\Repos\alyssa-avatar\.env"
ALYSSA_AGENT_ID_FALLBACK = "agent_0001kz94d9mzfevvzk5bv046bxkj"
ALYSSA_CALLS_CACHE = os.path.join(os.path.dirname(__file__), "calls_cache.json")
ALYSSA_CALLS_REFRESH_S = 60         # list re-pull cadence while the page is open
ALYSSA_CALLS_PAGE_SIZE = 100        # newest N conversations shown
# Numbers that are "us" (owner/staff test calls) — shown greyed, hideable.
ALYSSA_OWN_NUMBERS = ["+12127773221"]

# =============================================================================
# PRE-GAME READINESS CHECKS
# =============================================================================
# The dashboard's Pre-Game Readiness banner. All checks are suppressed while
# the M3 story State is "Running" (mid-game these would all scream).

# Retained-message landmines: a retained GameStart replays into any client
# that subscribes late (AI launcher has to drop it), and a retained RESET on
# a /command topic reboot-loops the board every time it reconnects.
# Fix tool: clear_retained_mqtt.py wildcard
PREGAME_LANDMINE_TOPICS = ["MermaidsTale/GameStart"]
PREGAME_LANDMINE_SUFFIXES = ["/command", "/reset"]

# Retained-command WATCHDOG (mqtt/retained_watchdog.py): the 24/7 active
# eraser behind the landmine banner. Runs inside WatchTower (the always-up
# process) so poison retained commands get wiped even when the AI stack's
# in-session guard/sweeper aren't running (2026-08-08: retained OPENCABINET
# reboot-looped TridentCabinet for hours off-hours). GameStart is deliberately
# NOT a watchdog suffix — ai_launcher's late-start rescue honors it.
RETAINED_WATCHDOG_PREFIX = "MermaidsTale/"
RETAINED_WATCHDOG_SUFFIXES = ["/command", "/reset", "/maglock"]
RETAINED_WATCHDOG_SWEEP_S = 60          # resubscribe interval = max landmine lifetime
RETAINED_WATCHDOG_HISTORY = 100         # erasures kept for /api/retained-watchdog
RETAINED_WATCHDOG_REPLANT_ALERT = 3     # same topic erased this often = re-planter loose

# Room-reset positions: prop state topics and the substring (case-insensitive)
# their payload must contain before a game can start. Add rows as props gain
# state topics; remove a row if its start position turns out to be different.
# Row fields:
#   label / topic / expect — display name, state topic, required substring.
#   warn: True   — row WARNS instead of blocking the start (check_prop_positions).
#   valid: "s"   — only payloads containing s (case-insens.) are stored as state;
#                  shuts out command chatter and the phantom CoveDoor v1.3.4
#                  board (replies on the same topic WITHOUT a MAGLOCK field).
#   query: {topic, payload} — published by the checklist to elicit fresh state
#                  (STATUS diag); boards whose state isn't broadcast passively.
PREGAME_PROP_STATES = [
    {"label": "Jungle door",     "topic": "MermaidsTale/JungleDoor/system/DoorState",   "expect": "closed"},
    # CoveDoor: limit switches read CLEAR even with the door physically shut
    # (verified live 2026-08-18 STATUS probe) — "closed" is NOT sensed. The
    # maglock IS reported, and an energized maglock is what holds this door,
    # so locked stands in for closed+locked. STATUS reply lands on /command
    # (the command-echo firmware quirk); valid filter keeps out both raw
    # commands and the phantom v1.3.4 board's maglock-less reply.
    {"label": "Cove door locked (maglock)", "topic": "MermaidsTale/CoveDoor/command",
     "expect": "maglock:locked", "valid": "maglock:",
     "query": {"topic": "MermaidsTale/CoveDoor/command", "payload": "STATUS"}},
    # CabinDoor: no passive state broadcast; STATUS reply on /status carries
    # the piston reed — LIMIT_CLOSED:ACTIVE = door shut (live-verified
    # 2026-08-18, the reed works). No separate lock: the piston holds it.
    {"label": "Cabin door closed (piston reed)", "topic": "MermaidsTale/CabinDoor/status",
     "expect": "limit_closed:active", "valid": "limit_",
     "query": {"topic": "MermaidsTale/CabinDoor/command", "payload": "STATUS"}},
    # BarrelPiston has NO position sensor (continuous mode) — "retracted"
    # cannot be sensed. Best observable: /state (retained) must be STOPPED,
    # i.e. not left EXTENDING/RETRACTING/SAFETY.
    {"label": "Barrel piston idle (position not sensed)",
     "topic": "MermaidsTale/BarrelPiston/state", "expect": "stopped"},
    {"label": "Trident cabinet", "topic": "MermaidsTale/TridentCabinet/system/Cabinet", "expect": "closed"},
    # Puzzles left SOLVED from the last game (staff forgot the physical reset).
    # CompassTrio: retained heartbeat "HEARTBEAT:UNSOLVED:..." every 5 min; a
    # solve latches retained "SOLVED" (and stays SOLVED after PUZZLE_RESET if
    # the compasses are still physically aligned — exactly what we're catching).
    # Driftwood: "ACTIVE | Sensors: ..." vs "SOLVED | ..." every 60s.
    {"label": "Compass trio",    "topic": "MermaidsTale/CompassTrio/status",            "expect": "unsolved"},
    # MiniBarrels (rum recipe): status is ONLINE / HEARTBEAT:RUNNING:... when
    # reset, SOLVED / HEARTBEAT:SOLVED:... after a solve. 2026-09-18 play: the
    # story's reset never reached the board (wrong topics), so it sat SOLVED
    # with all five lights green from the previous game and guests lost 22 min.
    # "reject_re" = regex that must NOT match (UNSOLVED-style substrings make a
    # plain "expect" useless here).
    {"label": "Mini barrels (rum recipe)", "topic": "MermaidsTale/MiniBarrels/status",
     "reject_re": r"(^|:)SOLVED(:|$)"},
    {"label": "Driftwood",       "topic": "MermaidsTale/Driftwood/status",              "expect": "active"},
    # MonkeyDoorsTotems: the board publishes NO door-position topic (verified
    # against the full 2026-07-24 wire logs — only status/log heartbeats, PONG,
    # /message strings, and the three totem beams below). Totems Off is the
    # start state and the nearest observable proxy for "guardian doors closed /
    # puzzle reset"; a physically ajar door with reset totems is invisible on
    # MQTT (would need a firmware change to detect).
    {"label": "Monkey totem (sundial)",       "topic": "MermaidsTale/MonkeyDoorsTotems/system/SundialTotem",       "expect": "off"},
    {"label": "Monkey totem (driftwood)",     "topic": "MermaidsTale/MonkeyDoorsTotems/system/DriftwoodTotem",     "expect": "off"},
    {"label": "Monkey totem (waterfountain)", "topic": "MermaidsTale/MonkeyDoorsTotems/system/WaterfountainTotem", "expect": "off"},
    # Shattic BAC inputs must read On before a game starts. Owner wants a
    # WARNING, not a blocked start, so "warn": True routes these to the warn
    # bucket in check_prop_positions (2026-08-18). Note the BAC topic layout:
    # <Device>/get/... with On/Off payloads, no MermaidsTale/ root.
    {"label": "Shattic input0",  "topic": "Shattic/get/input0",  "expect": "on", "warn": True},
    {"label": "Captain's magic mirror power (Shattic input1)",
     "topic": "Shattic/get/input1", "expect": "on", "warn": True},
    # Water fountain pump relay is INVERTED (Off = water FLOWS — see
    # fountain-boot-off): fountain OFF means Jungle/get/Relay_1 reads "On".
    # Warn-only: fountain_boot_off.py auto-cures it on board boot, and a
    # GameReset turns it off too.
    {"label": "Water fountain off (relay reads On — inverted wiring)",
     "topic": "Jungle/get/Relay_1", "expect": "on", "warn": True},
]

# Some boards answer PING/RESET on the SAME /status topic that carries their
# puzzle state (CompassTrio replies "PONG"/"OK" there). Those transients must
# not overwrite the tracked SOLVED/UNSOLVED state — with a 5-min heartbeat, a
# stored "PONG" would false-fail the prop-position gate for minutes.
PREGAME_PROP_TRANSIENT_PAYLOADS = {"pong", "ok", "online", "offline", "resetting", "rebooting"}

# Reboot-loop detection: N boot events (uptime went backwards, or a
# "Boot complete"/"rebooting" log line) within the window = boot loop.
# QUIET_S: if the LAST boot event is older than this, the loop has STOPPED
# (fix worked / board recovered) — report history, don't fail the gate.
# 2026-07-10: BalancingScale kept failing the checklist for 10 min AFTER a
# successful retained-RESET wipe because old events hadn't aged out yet.
PREGAME_BOOTLOOP_COUNT = 3
PREGAME_BOOTLOOP_WINDOW_S = 600
PREGAME_BOOTLOOP_QUIET_S = 120

# Unreal packaged-build watch: the START bat launches the newest
# Windows_*_DEV folder; flag if EscapeRoom.exe is not running, or is running
# from an older build folder than the newest one on disk.
UNREAL_BUILDS_DIR = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\EscapeRoom Pirate"
UNREAL_PROCESS_NAME = "EscapeRoom"
UNREAL_CRASH_FRESH_H = 24   # flag crash folders newer than this

# Windows per-app volume watch: Windows remembers Mystery.exe's mixer volume
# PER OUTPUT DEVICE and reapplies it to every new session — a slider dragged
# to 15% on Ship silenced all M3 SFX across restarts (2026-07-04). Flag any
# M3 session that is muted or below the floor.
SVCL_PATH = r"C:\Tools\svcl\SoundVolumeView.exe"
M3_APP_VOLUME_MIN = 90.0

# =============================================================================
# DEVICE TIMEOUTS
# =============================================================================
ESP32_PING_TIMEOUT = 3.0   # seconds
BAC_PING_TIMEOUT = 15.0    # seconds (waits for heartbeat cycle)
HEARTBEAT_STANDARD = 300000  # 5 minutes in ms

# =============================================================================
# MQTT MESSAGE FILTERING
# =============================================================================
DELTA_THRESHOLD = 2  # degrees - only show sensor changes greater than this
DELTA_TOPICS = ["/Hor", "/Ver", "/angle", "/distance"]
HIDDEN_TOPICS = ["/heartbeat", "/get/heartbeat"]
DEDUP_TOPICS = ["/Loaded", "/Fired", "/triggered"]
MAX_MESSAGES = 200

# =============================================================================
# DEVICE REGISTRY
# =============================================================================
# Device type constants
DEVICE_TYPE_ESP32 = "esp32"
DEVICE_TYPE_BAC = "bac"

# BAC Controllers
BAC_CONTROLLERS = [
    {"name": "Shattic", "icon": "🚢", "color": "#4A90D9"},
    {"name": "Captain", "icon": "🎖️", "color": "#C4A265"},
    {"name": "Cove", "icon": "🏝️", "color": "#45B7AA"},
    {"name": "Jungle", "icon": "🌴", "color": "#7B68D9"},
]

# ESP32 Devices - organized by room
# Reconciled against live MQTT 2026-06-19 (see WATCHTOWER_TILE_RECONCILIATION_2026-06-19.md).
# topic = the live MermaidsTale/<topic>/... base the firmware actually publishes under.
ESP32_DEVICES = [
    # Captain's Cabin
    # (MagicMirror tile retired 2026-08-11: nothing ever published on
    # MermaidsTale/MagicMirror/* - the captain's-quarters mirror is a Nano with
    # no WiFi. Its role in the roster is superseded by StarTableSprite (Cove),
    # which is what the old "magic mirror" bench board actually became.)
    {"name": "Captains-Cuffs", "topic": "CaptainsCuffs", "icon": "⛓️", "color": "#C4A265", "room": "Captain's Cabin"},
    {"name": "CabinDoor", "topic": "CabinDoor", "icon": "🚪", "color": "#C4A265", "room": "Captain's Cabin"},

    # Ship Deck / Shattic
    {"name": "CompassTrio", "topic": "CompassTrio", "icon": "🧭", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Cannon1", "topic": "Cannon1", "icon": "💣", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Cannon2", "topic": "Cannon2", "icon": "💣", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "BarrelPiston", "topic": "BarrelPiston", "icon": "🛢️", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "MiniBarrels", "topic": "MiniBarrels", "icon": "🥃", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Balancing-Scale", "topic": "BalancingScale", "icon": "⚖️", "color": "#4A90D9", "room": "Ship Deck"},
    # Card name matches the topic ("SunDial") as of 2026-07-11; the board is
    # the stateless MQTT bridge for the Sand Dial Arduino (SunDial_Bridge FW).
    # Firmware subscribes/publishes on MermaidsTale/SunDial/... per MANIFEST.h.
    {"name": "SunDial", "topic": "SunDial", "icon": "☀️", "color": "#4A90D9", "room": "Ship Deck",
     "commands": ["PING", "STATUS", "RESET", "PUZZLE_RESET", "CLEAR_STATUS"]},

    # Jungle
    {"name": "JungleDoor", "topic": "JungleDoor", "icon": "🚪", "color": "#45B7AA", "room": "Jungle"},
    {"name": "Driftwood", "topic": "Driftwood", "icon": "🪵", "color": "#45B7AA", "room": "Jungle"},
    {"name": "WaterFountain", "topic": "WaterFountain", "icon": "⛲", "color": "#45B7AA", "room": "Jungle"},
    {"name": "MonkeyDoorsTotems", "topic": "MonkeyDoorsTotems", "icon": "🐒", "color": "#45B7AA", "room": "Jungle"},
    {"name": "TridentCabinet", "topic": "TridentCabinet", "icon": "🔱", "color": "#7B68D9", "room": "Jungle"},
    {"name": "Ruins-Wall-Panel", "topic": "RuinsWall", "icon": "🧱", "color": "#7B68D9", "room": "Jungle"},

    # Cove
    {"name": "CoveDoor", "topic": "CoveDoor", "icon": "🚪", "color": "#D97B9F", "room": "Cove"},
    # The cove constellation trial (M3 event #45). StarTableBridge v1.1.0 is a
    # GPIO-to-MQTT bridge; the table controller itself (Star_Table_FINAL) has
    # no MQTT. 5-min ONLINE/SOLVED heartbeat, answers PING with PONG on
    # /command. Registered 2026-08-10 — fw was WatchTower-compliant since
    # 07-09 but this entry was never added, so WT never tracked it.
    {"name": "StarTable", "topic": "StarTable", "icon": "🌟", "color": "#D97B9F", "room": "Cove"},
    # MedeaWiz Sprite video driver for the star table (StarTableSprite v2.0.0,
    # ESP32-S3, flashed 2026-08-11). Advances the constellation video on
    # StarTable/constellation="solved"; listen-only on StarTable/command for
    # PUZZLE_RESET (never replies there). Own full WT protocol + LWT on
    # MermaidsTale/StarTableSprite/*.
    {"name": "StarTableSprite", "topic": "StarTableSprite", "icon": "📽️", "color": "#D97B9F", "room": "Cove"},
]


# =============================================================================
# GRIMOIRE SLUG MAP
# Maps config device names → grimoire device page slugs
# Multiple devices can share a slug (e.g. Cannon1+Cannon2 → new-cannons)
# =============================================================================
GRIMOIRE_SLUG_MAP = {
    # Ship Deck
    "Cannon1":           "new-cannons",
    "Cannon2":           "new-cannons",
    "BarrelPiston":      "barrel-piston",
    "MiniBarrels":       "mini-barrels",
    "Balancing-Scale":   "balancing-scale",
    "SunDial":           "sun-dial",
    # Captain's Cabin
    "CompassTrio":       "compass",
    "Captains-Cuffs":    "captains-cuffs",
    "CabinDoor":         "cabin-door",
    # Cove
    "CoveDoor":          "cove-sliding-door",
    "Driftwood":         "driftwood",
    # Jungle
    "JungleDoor":        "jungle-door",
    "Ruins-Wall-Panel":  "ruins-wall-panel",
    "TridentCabinet":    "trident-cabinet",
    "MonkeyDoorsTotems": "monkey-doors-totems",
    "WaterFountain":     "water-fountain",
}

# Gravity Games VR Topics (game flow triggers, NOT device management)
GRAVITY_GAMES_TOPICS = [
    {"topic": "MermaidsTale/GameReset", "event": "Game Restart", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/GameStart", "event": "Game Start", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/DeskDrawer", "event": "Desk Drawer", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/MirrorSensor", "event": "Mirror Sensor", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/CabinDoorOpened", "event": "Cabin Door Opened", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/ShipMotion1", "event": "Ship Motion 1", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/ShipMotion2", "event": "Ship Motion 2", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/ShipMotion3", "event": "Ship Motion 3", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/WhaleSurface", "event": "Whale Surface", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/CompassTrio/status", "event": "Compasses", "payload": "SOLVED", "occurrence": "Once"},
    {"topic": "MermaidsTale/SkullKeySolved", "event": "Skull Key Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WheelPos", "event": "Wheel Position", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Hor", "event": "Cannon 1 Aimed", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Hor", "event": "Cannon 2 Aimed", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Loaded", "event": "Cannon 1 Loaded", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Loaded", "event": "Cannon 2 Loaded", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Fired", "event": "Cannon 1 Fired", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Fired", "event": "Cannon 2 Fired", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/DefenseOver", "event": "Defense Over", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/RumBarrels", "event": "Rum Barrels", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/BalanceScale", "event": "Balancing Scale", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/Swords", "event": "Swords", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/SailUnfurled", "event": "Sail Unfurled", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/SailPosition", "event": "Sail Position", "payload": "pre_n (percent)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/MapSolved", "event": "Map Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleDoor", "event": "Jungle Door", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleEntered", "event": "Jungle Entered", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleMotion1", "event": "Jungle Motion 1", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/JungleMotion2", "event": "Jungle Motion 2", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/JungleMotion3", "event": "Jungle Motion 3", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/CryptexSolved", "event": "Cryptex Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WaterfallSolved", "event": "Waterfall Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/DriftwoodSolved", "event": "Driftwood Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/MonkeyGuardianDoor", "event": "Monkey Guardian Door", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/TridentReveal", "event": "Trident Reveal", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/HieroglyphicsSolved", "event": "Hieroglyphics Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/CoveEntered", "event": "Cove Entered", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/SeaShells", "event": "Sea Shells", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/StarCharts", "event": "Star Charts", "payload": "triggered", "occurrence": "Multiple"},
    {"topic": "MermaidsTale/CelestialSolved", "event": "Celestial Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/AlterSolved", "event": "Alter Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/GameSuccess", "event": "Game Success", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WaterfallFinale", "event": "Waterfall Finale", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/GameFail", "event": "Game Fail", "payload": "triggered", "occurrence": "Once"},
]
