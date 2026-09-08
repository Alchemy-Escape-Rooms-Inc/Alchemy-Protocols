"""
WatchTower V2 MQTT Client
===========================
Handles broker connection, device ping/pong, message filtering, and live feed.
Ported from V1 system_checker.py with cleaner architecture.
"""

import os
import re
import time
import uuid
import threading
import logging
from collections import deque
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json

# Operator tuning (ship cameras / jungle camera / character scale) mirrored to
# disk (2026-09-04). The broker has NO persistence, so a PC reboot on 09-02
# silently erased every retained WatchTower/* tuning topic and the room came
# back on stale defaults. This file is the durable copy: seeded into the
# cache at boot, re-published on connect and on every Unreal boot.
TUNING_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tuning_state.json")
TUNING_TOPIC_ATTRS = {
    "WatchTower/ShipCameraTuning":   "ship_camera_tuning",
    "WatchTower/JungleCameraTuning": "jungle_camera_tuning",
    "WatchTower/CharacterScale":     "character_scale_tuning",
}
from typing import Dict, Optional, List, Callable

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# MQTT SESSION LOGGING
# ─────────────────────────────────────────────
# One .txt per Watchtower process boot, named mqtt_YYYY-MM-DD_HHMMSS.txt,
# written to watchtower-v2/logs/. Files older than 24h are purged on startup.

MQTT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)
MQTT_LOG_PREFIX = "mqtt_"
MQTT_LOG_SUFFIX = ".txt"
MQTT_LOG_RETENTION = timedelta(hours=24)
MQTT_LOG_NAME_FORMAT = "%Y-%m-%d_%H%M%S"


def _purge_old_mqtt_logs():
    """Delete session logs whose filename timestamp is older than 24h."""
    if not os.path.isdir(MQTT_LOG_DIR):
        return
    cutoff = datetime.now() - MQTT_LOG_RETENTION
    for name in os.listdir(MQTT_LOG_DIR):
        if not (name.startswith(MQTT_LOG_PREFIX) and name.endswith(MQTT_LOG_SUFFIX)):
            continue
        stem = name[len(MQTT_LOG_PREFIX):-len(MQTT_LOG_SUFFIX)]
        try:
            file_ts = datetime.strptime(stem, MQTT_LOG_NAME_FORMAT)
        except ValueError:
            continue
        if file_ts < cutoff:
            try:
                os.remove(os.path.join(MQTT_LOG_DIR, name))
                logger.info(f"Purged old MQTT log: {name}")
            except OSError as e:
                logger.warning(f"Could not purge {name}: {e}")


def _open_mqtt_session_log():
    """Create logs/ if missing, purge stale files, open a new session file."""
    os.makedirs(MQTT_LOG_DIR, exist_ok=True)
    _purge_old_mqtt_logs()
    stamp = datetime.now().strftime(MQTT_LOG_NAME_FORMAT)
    path = os.path.join(MQTT_LOG_DIR, f"{MQTT_LOG_PREFIX}{stamp}{MQTT_LOG_SUFFIX}")
    f = open(path, "a", encoding="utf-8", buffering=1)  # line-buffered
    f.write(f"# Watchtower MQTT session log — started {datetime.now().isoformat()}\n")
    logger.info(f"MQTT session log: {path}")
    return f, path


# Accept a PONG/status reply this long after a ping was sent, even if the
# ping already "timed out" — slow-waking boards answer late, not never.
LATE_PONG_GRACE_S = 60


class DeviceStatus(Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    TESTING = "testing"


class DeviceType(Enum):
    BAC = "bac"
    ESP32 = "esp32"


@dataclass
class Device:
    name: str
    device_type: DeviceType
    topic_base: str
    icon: str = "📡"
    color: str = "#4A90D9"
    room: str = ""
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_test: Optional[datetime] = None
    response_time_ms: Optional[int] = None
    last_error: Optional[str] = None
    commands: list = field(default_factory=lambda: ["PING", "STATUS", "RESET", "PUZZLE_RESET"])
    needs_protocol: bool = False
    # Sensor self-test faults from the board's own /status heartbeat, e.g.
    # Cannon "ONLINE | v3.2.0 | VL6180X:FAIL | ALS31300:OK" -> ["VL6180X"].
    # 2026-08-08: Cannon1's load sensor screamed FAIL all day while the board
    # answered pings, so it passed every sweep and nothing said a word.
    sensor_faults: list = field(default_factory=list)
    sensor_faults_since: Optional[datetime] = None
    # Passive liveness for the health sentinel: last time ANY message arrived
    # under this device's topic base, recent arrival times (flap detection —
    # the 2026-08-08 CaptainsCuffs class: heartbeat holes swallow solves),
    # and whether the board's LWT stamped retained OFFLINE on /status.
    last_seen: Optional[datetime] = None
    arrivals: deque = field(default_factory=lambda: deque(maxlen=400))
    offline_lwt: bool = False


class MQTTClient:
    """Manages MQTT connection, device health checking, and message feed."""

    def __init__(self, on_message_callback: Optional[Callable] = None):
        self.devices: Dict[str, Device] = {}
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.lock = threading.Lock()

        # Message feed (in-memory ring buffer for live UI)
        self.message_feed: List[dict] = []
        self.max_feed_messages = config.MAX_MESSAGES

        # Smart filtering state
        self.recent_sent: List[tuple] = []
        self.last_values: Dict[str, float] = {}
        self.last_payloads: Dict[str, str] = {}

        # Systems-group signal tracking: last time we saw evidence each
        # infrastructure system is alive on MQTT (used by /api/status systems).
        #   ai_brain    -> any MermaidsTale/RedBeard/* traffic (AI Character process)
        #   ai_launcher -> MermaidsTale/AILauncher/* heartbeat (ai_launcher.py —
        #                  the process that receives the Reset Brain command; if
        #                  it's dead, the Reset button publishes into the void)
        #   m3          -> M3/Stories/AMT/State == "Running" (game runner)
        self.system_signals: Dict[str, dict] = {
            "ai_brain":    {"last_seen": None, "detail": None},
            "ai_launcher": {"last_seen": None, "detail": None},
            "m3":          {"last_seen": None, "detail": None},
            #   unreal_room -> MermaidsTale/Unreal/RoomStatus heartbeat (5s from
            #                  the packaged game): {"map":..,"audioRoom":..} —
            #                  which map/room Unreal is ACTUALLY sitting in.
            #                  Drives the pre-game room-confirmation light.
            "unreal_room": {"last_seen": None, "detail": None},
            #   helm_audio  -> MermaidsTale/Audio/status (retained, every 2 s
            #                  from Helm): {"ok":bool,"device":..} or
            #                  {"ok":false,"reason":..}. ok=false with Helm
            #                  running = the Behringer is gone/grabbed (09-06:
            #                  UMC1820 dropped off USB; :52100 still answered).
            "helm_audio":  {"last_seen": None, "detail": None},
            #   unreal_boot -> stamped when the RoomStatus heartbeat (re)appears
            #                  after >20s of silence = a fresh game process
            #                  (or WatchTower itself just started listening).
            "unreal_boot": {"last_seen": None, "detail": None},
            #   wheel       -> MermaidsTale/WheelPos (BP_Ship publishes the
            #                  Fanatec wheel angle every tick it changes, ship
            #                  map only) = proof the game is actually READING
            #                  the steering wheel. Drives Guardian pirate_wheel.
            "wheel":       {"last_seen": None, "detail": None},
            #   ai_phase    -> MermaidsTale/AI/Phase "<phase>|<agent>" from the
            #                  brain (30 s heartbeat + on change): who is live.
            #   ai_direct_result -> MermaidsTale/AI/DirectResult (JSON): the
            #                  brain's answer to a Direct-the-Character note.
            "ai_phase":    {"last_seen": None, "detail": None},
            "ai_direct_result": {"last_seen": None, "detail": None},
        }

        # Last retained WatchTower/ShipCameraTuning payload (JSON string) —
        # seeded by the broker's retained replay on subscribe, updated on every
        # publish. Read by /api/ship-camera GET for the /game sliders.
        self.ship_camera_tuning: str = ""
        # Same contract for the Evalee/jungle camera + character-scale sliders
        # (2026-08-04): WatchTower/JungleCameraTuning, WatchTower/CharacterScale.
        self.jungle_camera_tuning: str = ""
        self.character_scale_tuning: str = ""
        self._tuning_state_lock = threading.Lock()
        self._load_tuning_state()

        # Pre-game readiness tracking (see routes/api.py _pregame_checks):
        #   retained_landmines  topic -> payload for retained GameStart/command/
        #                       reset messages still sitting on the broker
        #   prop_states         topic -> {payload, ts} for the room-reset topics
        #                       in config.PREGAME_PROP_STATES
        #   boot_events         device -> [datetime] of reboot evidence (uptime
        #                       went backwards or a boot/reboot log line)
        self.retained_landmines: Dict[str, str] = {}
        self.prop_states: Dict[str, dict] = {}
        self.boot_events: Dict[str, List[datetime]] = {}
        self._last_uptimes: Dict[str, float] = {}
        self._pregame_prop_rows = {row["topic"]: row for row in config.PREGAME_PROP_STATES}

        # AI-dead-at-GameStart sentry: single-flight guard so near-simultaneous
        # GameStart deliveries can't run two rescues (= two launchers spawned).
        self._ai_sentry_lock = threading.Lock()

        # Tuning re-publish single-flight: Unreal-boot detection can fire off
        # several RoomStatus beats in a row (heartbeat + post-LoadMap publish);
        # only one delayed re-publish should run per boot.
        self._tuning_republish_lock = threading.Lock()
        self._last_tuning_republish: float = 0.0

        # Battle→DefenseOver progression watchdog state (see config
        # BATTLE_WATCHDOG_*): armed on AI/StartBattle|trigger, satisfied by
        # PowderSolved|true (event 92's wire signature), disarmed on any
        # game-end signal.
        self._battle_watch_lock = threading.Lock()
        self._battle_watch = {"armed_at": None, "defenseover_at": None, "advanced_at": None}

        # External callback for new messages (used by SSE)
        self.on_message_callback = on_message_callback

        # Per-session raw MQTT log file (purges files >24h old on boot)
        try:
            self._session_log_file, self._session_log_path = _open_mqtt_session_log()
        except Exception as e:
            logger.error(f"Failed to open MQTT session log: {e}")
            self._session_log_file = None
            self._session_log_path = None

        # Load devices from config
        self._load_devices()

    def _load_devices(self):
        """Load device registry from config."""
        for bac in config.BAC_CONTROLLERS:
            self.devices[bac["name"]] = Device(
                name=bac["name"],
                device_type=DeviceType.BAC,
                topic_base=bac["name"],
                icon=bac.get("icon", "🎛️"),
                color=bac.get("color", "#4A90D9"),
                room="Zone Controller"
            )

        for esp in config.ESP32_DEVICES:
            self.devices[esp["name"]] = Device(
                name=esp["name"],
                device_type=DeviceType.ESP32,
                topic_base=esp.get("topic", esp["name"]),
                icon=esp.get("icon", "📡"),
                color=esp.get("color", "#4A90D9"),
                room=esp.get("room", ""),
                commands=esp.get("commands", ["PING", "STATUS", "RESET", "PUZZLE_RESET"]),
                needs_protocol=esp.get("needs_protocol", False)
            )

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            self.client = mqtt.Client(client_id=f"watchtower_v2_{uuid.uuid4().hex[:8]}")
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            logger.info(f"Connecting to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")
            # connect_async + loop_start: paho keeps retrying in the background if the
            # broker isn't up yet (START bat race, 2026-07-02: a failed one-shot connect
            # left WatchTower blind all night — 0-byte mqtt_*.txt wire log).
            self.client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, 60)
            self.client.reconnect_delay_set(min_delay=1, max_delay=10)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            # Subscribe to everything for the live feed
            client.subscribe("#")
            # Specific subscriptions for device responses
            client.subscribe("MermaidsTale/+/status")
            client.subscribe("MermaidsTale/+/command")
            client.subscribe("+/get/#")
            # Broker (re)start with no persistence = retained tuning gone.
            # Re-publish our durable copy once the retained replay (if any)
            # has had a moment to overwrite the disk-seeded cache.
            self._schedule_tuning_republish("MQTT (re)connect")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8").strip()
        except:
            payload = str(msg.payload)

        now = datetime.now()

        # Raw session log — captures EVERYTHING pre-filter (so compass-style
        # diagnostics aren't hidden by _should_show_message).
        if self._session_log_file is not None:
            try:
                ts = now.strftime("%H:%M:%S.%f")[:-3]
                self._session_log_file.write(f"[{ts}] {topic} | {payload}\n")
            except Exception:
                pass

        # Systems-group signal capture (pre-filter, so quiet heartbeats count).
        self._note_system_signal(topic, payload, now)

        # AI-dead-at-GameStart sentry (2026-08-08): the Guardian checklist gates
        # the START bat, but a game can also begin straight from M3 (GameStart on
        # the wire) with nothing checking the AI side. The instant a LIVE
        # GameStart lands, verify ai_launcher is alive — and rescue it if not,
        # so a game can never run start-to-finish with silent characters.
        if topic == "MermaidsTale/GameStart" and not msg.retain:
            threading.Thread(target=self._gamestart_ai_sentry,
                             name="gamestart-ai-sentry", daemon=True).start()

        # Ship-camera tuning readback: the broker replays the retained value on
        # our '#' subscribe, so the /game sliders always show what the game is
        # actually using — even right after a WatchTower restart.
        if topic in TUNING_TOPIC_ATTRS and payload:
            self.remember_tuning(topic, payload)

        # Pre-game readiness capture (retained landmines, prop states, reboots).
        try:
            self._note_pregame(topic, payload, now, bool(msg.retain))
        except Exception:  # noqa: BLE001 - never let readiness break the feed
            pass

        # Add to feed if it passes filters
        if self._should_show_message(topic, payload):
            device_name = self._extract_device_name(topic)
            message = {
                "timestamp": now.strftime("%H:%M:%S"),
                "timestamp_full": now.isoformat(),
                "direction": "RX",
                "topic": topic,
                "payload": payload[:200] if payload else "",
                "device": device_name
            }
            with self.lock:
                self.message_feed.insert(0, message)
                if len(self.message_feed) > self.max_feed_messages:
                    self.message_feed.pop()

            if self.on_message_callback:
                try:
                    self.on_message_callback(message)
                except:
                    pass

        # Passive per-device liveness stamp (health sentinel).
        try:
            self._stamp_device_seen(topic, payload, now)
        except Exception:  # noqa: BLE001
            pass

        # Sensor self-test capture from board /status heartbeats (pre-filter).
        try:
            self._note_sensor_health(topic, payload, now)
        except Exception:  # noqa: BLE001 - never let health parsing break the feed
            logger.exception("Sensor-health parse failed")

        # Battle→DefenseOver progression watchdog (2026-08-08: story hung after
        # the battle because M3 event 92, type=Single, ignored DefenseOver).
        try:
            self._note_battle_watchdog(topic, payload, bool(msg.retain))
        except Exception:  # noqa: BLE001
            logger.exception("Battle watchdog update failed")

        # Process device health responses
        self._process_device_response(topic, payload, now)

    def _note_battle_watchdog(self, topic: str, payload: str, retain: bool):
        """Track the battle phase so the story can never hang at its end.
        2026-08-08 21:32: the battle timed out, Unreal published a clean
        DefenseOver|trigger, and M3 event 92 (type=Single — already consumed
        by the 17:48 game) IGNORED it: 'Defeat Enemy Pirates' never completed
        and the jungle never powered up until a manual GM fire 3 min later.
        Armed on AI/StartBattle|trigger; satisfied by PowderSolved|true
        (event 92's wire signature, published +10s after it fires); disarmed
        by any game-end signal. At the deadline the timer (re)publishes
        DefenseOver|trigger and raises a debug alert either way."""
        if retain:
            return
        if topic == "MermaidsTale/AI/StartBattle" and payload == "trigger":
            with self._battle_watch_lock:
                if self._battle_watch["armed_at"] is not None:
                    return  # already watching this battle
                armed_at = time.time()
                self._battle_watch = {"armed_at": armed_at,
                                      "defenseover_at": None, "advanced_at": None}
            logger.info("Battle watchdog ARMED — expecting the story to advance within "
                        f"{config.BATTLE_WATCHDOG_DEADLINE_S}s")
            threading.Thread(target=self._battle_watchdog_timer, args=(armed_at,),
                             name="battle-watchdog", daemon=True).start()
        elif topic == "MermaidsTale/DefenseOver" and payload == "trigger":
            with self._battle_watch_lock:
                if self._battle_watch["armed_at"] is not None:
                    self._battle_watch["defenseover_at"] = time.time()
        elif topic == "MermaidsTale/PowderSolved" and payload.lower() == "true":
            with self._battle_watch_lock:
                if self._battle_watch["armed_at"] is not None:
                    self._battle_watch["advanced_at"] = time.time()
        elif topic in ("MermaidsTale/GameReset", "MermaidsTale/GameSuccess",
                       "MermaidsTale/GameFail", "MermaidsTale/GameStart"):
            with self._battle_watch_lock:
                if self._battle_watch["armed_at"] is not None:
                    self._battle_watch = {"armed_at": None,
                                          "defenseover_at": None, "advanced_at": None}

    def _battle_watchdog_timer(self, armed_at: float):
        time.sleep(config.BATTLE_WATCHDOG_DEADLINE_S)
        with self._battle_watch_lock:
            state = dict(self._battle_watch)
        if state["armed_at"] != armed_at:
            return  # game ended/reset, or a different battle re-armed
        if state["advanced_at"] is not None:
            return  # event 92 ran — story advanced on its own

        seen = ("Unreal DID publish DefenseOver|trigger but M3 never advanced the story "
                "(event 92 deaf — the type=Single consumed-state bug)"
                if state["defenseover_at"] is not None
                else "DefenseOver|trigger never appeared on the wire (Unreal battle end lost?)")
        logger.error(f"Battle watchdog: story did not advance "
                     f"{config.BATTLE_WATCHDOG_DEADLINE_S}s after StartBattle — {seen}. "
                     "Publishing DefenseOver|trigger rescue.")
        self.publish_raw("MermaidsTale/DefenseOver", "trigger")

        time.sleep(config.BATTLE_WATCHDOG_RETRY_WAIT_S)
        with self._battle_watch_lock:
            state = dict(self._battle_watch)
        rescued = state["armed_at"] == armed_at and state["advanced_at"] is not None
        try:
            from models import database as db
            title = "Battle end did not advance the story"
            if not db.has_open_debug_entry(title):
                db.add_debug_entry(
                    device_name=None,
                    severity="warning" if rescued else "error",
                    title=title,
                    description=(f"{seen}.\n\nWatchTower republished MermaidsTale/DefenseOver='trigger'. "
                                 + ("The story advanced after the republish (PowderSolved|true seen) — "
                                    "game rescued, but fix M3 event 92 (Single→Recurring) so this "
                                    "stops recurring."
                                    if rescued else
                                    "The story STILL did not advance — fire the 'DefenseOver' event "
                                    "manually in M3 NOW (GM view), and fix event 92 (Single→Recurring) "
                                    "after the game.")),
                    created_by="watchtower",
                )
        except Exception:  # noqa: BLE001
            logger.exception("Battle watchdog debug entry failed")

    def _stamp_device_seen(self, topic: str, payload: str, now: datetime):
        """Record that a device's board produced ANY traffic — passive
        liveness the health sentinel reads (a board can be hours dead without
        anyone pinging it; last_seen catches that without a scan). Also mirrors
        the board's LWT: a retained OFFLINE on /status is the broker itself
        reporting the connection died."""
        with self.lock:
            for device in self.devices.values():
                base = device.topic_base
                if not (topic.startswith(f"MermaidsTale/{base}/")
                        or topic.startswith(f"{base}/")):
                    continue
                device.last_seen = now
                device.arrivals.append(time.time())
                if topic.endswith("/status"):
                    up = payload.strip().upper()
                    if up == "OFFLINE":
                        device.offline_lwt = True
                    elif up:
                        device.offline_lwt = False
                break

    # Sensor self-test tokens in /status heartbeats: "VL6180X:FAIL",
    # "ALS31300:OK" (Cannon v3.2.0 format). Colon required, so free-text log
    # lines like "PUZZLE_RESET FAILED" can never false-match.
    _SENSOR_FAIL_RE = re.compile(r"\b([A-Za-z0-9_]+):FAIL\b")
    _SENSOR_OK_RE = re.compile(r"\b[A-Za-z0-9_]+:OK\b")

    def _note_sensor_health(self, topic: str, payload: str, now: datetime):
        """A board that answers PING while one of its SENSORS is dead passes
        every sweep and silently breaks its puzzle mid-game (2026-08-08:
        Cannon1 heartbeated 'VL6180X:FAIL' all day — the cannonball load
        sensor — and the game started anyway). Parse every /status payload
        for self-test tokens: FAIL tokens set the device's fault list (and
        raise a debug-log alert ONCE per fault), an all-OK self-test clears
        it. Payloads with no self-test tokens (PONG, SOLVED…) are ignored —
        CompassTrio answers commands on /status and must not clear faults."""
        if not topic.startswith("MermaidsTale/") or not topic.endswith("/status"):
            return
        base = topic[len("MermaidsTale/"):-len("/status")]
        device = None
        with self.lock:
            for d in self.devices.values():
                if d.topic_base == base:
                    device = d
                    break
        if device is None:
            return

        faults = sorted(set(self._SENSOR_FAIL_RE.findall(payload)))
        if faults:
            with self.lock:
                new = [f for f in faults if f not in device.sensor_faults]
                if device.sensor_faults != faults:
                    device.sensor_faults = faults
                if device.sensor_faults_since is None:
                    device.sensor_faults_since = now
            for fault in new:
                title = f"Sensor FAIL: {device.name} {fault}"
                logger.error(f"{title} — board is online but self-reports a dead sensor "
                             f"(status: {payload[:120]})")
                try:
                    from models import database as db
                    if not db.has_open_debug_entry(title):
                        db.add_debug_entry(
                            device_name=device.name, severity="error",
                            title=title,
                            description=(f"{device.name} is answering pings but its /status heartbeat "
                                         f"self-reports the {fault} sensor as FAILED:\n\n  {payload}\n\n"
                                         "Its puzzle can NOT be completed in this state, and the "
                                         "pre-game checklist will block the next game start until the "
                                         "sensor reports OK again (check wiring/power on the sensor, "
                                         "then power-cycle the board)."),
                            created_by="watchtower",
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("Sensor-fault debug entry failed")
        elif self._SENSOR_OK_RE.search(payload):
            with self.lock:
                if device.sensor_faults:
                    logger.info(f"Sensor recovered on {device.name}: "
                                f"{', '.join(device.sensor_faults)} now OK")
                    device.sensor_faults = []
                    device.sensor_faults_since = None

    def _process_device_response(self, topic: str, payload: str, now: datetime):
        """Check if message is a response to a ping or a BAC heartbeat."""
        with self.lock:
            for device_name, device in self.devices.items():
                # BAC passive heartbeat monitoring
                if device.device_type == DeviceType.BAC:
                    expected_prefix = f"{device.topic_base}/get/"
                    if topic.lower().startswith(expected_prefix.lower()) or \
                       (device.topic_base.lower() in topic.lower() and "/get/" in topic.lower()):
                        if device.status != DeviceStatus.ONLINE:
                            logger.info(f"✓ BAC {device_name} heartbeat detected")
                        device.status = DeviceStatus.ONLINE
                        device.last_error = None
                        device.last_test = now
                        continue

                # ESP32 - process if we're waiting for a response, OR if the
                # board answers LATE. Observed 2026-07-10 (BarrelPiston): a
                # power-saving ESP32 took 12s to process the first PING after
                # idle (then ~200ms on later pings), so the 3s timeout stamped
                # it offline and its perfectly good PONG was discarded here.
                # A matching response within the grace window after a failed
                # ping is proof of life — flip it back online.
                if device.status != DeviceStatus.TESTING:
                    late_ok = (
                        device.status == DeviceStatus.OFFLINE
                        and device.last_test is not None
                        and (now - device.last_test).total_seconds() <= LATE_PONG_GRACE_S
                    )
                    # 2026-08-13 (StarTable): an explicit PONG is unambiguous
                    # proof of life no matter how stale the last test is — a
                    # raw PING sent from the device page (not a full test
                    # cycle) got a PONG back that was discarded here because
                    # the board had been offline >60s, so the tile stayed red
                    # while the wire showed it alive. Accept bare PONGs always.
                    # UNKNOWN counts too: after a WatchTower restart every
                    # tile is UNKNOWN, and a PONG then (2026-08-13, StarTable
                    # again) was still discarded by the OFFLINE-only guard.
                    explicit_pong = (
                        device.status in (DeviceStatus.OFFLINE, DeviceStatus.UNKNOWN)
                        and payload.strip().upper() == "PONG"
                    )
                    if not (late_ok or explicit_pong):
                        continue

                is_match = False
                if device.device_type == DeviceType.ESP32:
                    command_topic = f"MermaidsTale/{device.topic_base}/command"
                    status_topic = f"MermaidsTale/{device.topic_base}/status"
                    # 2026-07-09: some boards (TridentCabinet, CaptainsCuffs)
                    # answer PING with PONG on their /message topic, not
                    # /status or /command. Without this they only "passed" a
                    # ping sweep by racing their periodic ONLINE heartbeat on
                    # /status — a dead firmware with a live heartbeat looked
                    # healthy. PONG-only match here: /message also carries
                    # general log lines, which must NOT count as a ping reply.
                    message_topic = f"MermaidsTale/{device.topic_base}/message"

                    if (topic == command_topic and payload == "PONG") or \
                       (topic == status_topic and payload == "PONG") or \
                       (topic == status_topic) or \
                       (topic == message_topic and payload.upper() == "PONG"):
                        is_match = True

                if is_match:
                    if device.last_test:
                        response_ms = int((now - device.last_test).total_seconds() * 1000)
                        # If the PONG arrived long after the last real test
                        # (explicit-PONG revival), a "response time" of
                        # minutes is meaningless — don't record one.
                        if response_ms <= LATE_PONG_GRACE_S * 1000:
                            device.response_time_ms = response_ms
                        else:
                            device.response_time_ms = None
                    device.last_test = now
                    device.status = DeviceStatus.ONLINE
                    device.last_error = None
                    logger.info(f"✓ {device_name} responded ({device.response_time_ms}ms)")
                    return

    def _should_show_message(self, topic: str, payload: str) -> bool:
        """Smart filtering - ported from V1."""
        # Only show device-related topics
        if not ("MermaidsTale" in topic or
                any(d in topic for d in ["Shattic", "Captain", "Cove", "Jungle"])):
            return False

        # Hidden topics (heartbeats)
        if any(pattern in topic for pattern in config.HIDDEN_TOPICS):
            return False

        # Echo suppression
        with self.lock:
            for sent_topic, sent_payload in self.recent_sent:
                if sent_topic == topic and sent_payload == payload:
                    self.recent_sent.remove((sent_topic, sent_payload))
                    return False

        # Duplicate suppression
        if any(pattern in topic for pattern in config.DEDUP_TOPICS):
            with self.lock:
                last = self.last_payloads.get(topic)
                self.last_payloads[topic] = payload
                if last == payload:
                    return False

        # Delta filtering for sensor data
        if any(pattern in topic for pattern in config.DELTA_TOPICS):
            try:
                numbers = re.findall(r'[-+]?\d*\.?\d+', payload)
                if numbers:
                    value = float(numbers[-1])
                    with self.lock:
                        last_val = self.last_values.get(topic)
                        if last_val is not None and abs(value - last_val) < config.DELTA_THRESHOLD:
                            return False
                        self.last_values[topic] = value
            except (ValueError, IndexError):
                pass

        return True

    def _gamestart_ai_sentry(self):
        """A game just started (live GameStart on the wire). ai_launcher.py is
        the ONLY GameStart receiver on the AI side — if its heartbeat is stale,
        no AI character will ever launch and the game runs silent end to end
        (the 2026-07-15 failure). This sentry respawns the launcher, waits for
        its heartbeat, gives its own late-start rescue ~20s to boot the brain
        (it asks /api/game/state, which now reports the game running), then
        force-launches the brain via Cmd=restart if it's still silent. Every
        firing lands in the debug log so the operator knows the game started
        in a rescued state."""
        if not self._ai_sentry_lock.acquire(blocking=False):
            return  # a sentry from a near-simultaneous GameStart is already on it
        try:
            t0 = time.time()

            def _launcher_age():
                return self.get_system_signals().get("ai_launcher", {}).get("age_s")

            age = _launcher_age()
            if age is not None and age <= config.AI_LAUNCHER_FRESH_S:
                return  # supervisor alive — it spawns the brain itself, as designed

            seen = (f"last heartbeat {int(age)}s ago" if age is not None
                    else "no heartbeat since WatchTower started")
            logger.error(f"GameStart fired but the AI launcher is DEAD ({seen}) — "
                         "respawning it now so the game doesn't run silent")

            # Respawn via the guardian fix (lazy import: guardian imports this
            # module at load, so a top-level import here would be circular).
            try:
                from guardian import fixes as guardian_fixes
                result = guardian_fixes.fix_start_ai_launcher({"mqtt": self})
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "output": f"respawn crashed: {e}"}

            outcome = [f"respawn: {'OK' if result.get('ok') else 'FAILED'} — {result.get('output', '')}"]
            heartbeat = False
            if result.get("ok"):
                deadline = time.time() + 45
                while time.time() < deadline:
                    time.sleep(2)
                    age = _launcher_age()
                    if age is not None and age <= 40:
                        heartbeat = True
                        break
            if heartbeat:
                # The fresh launcher missed GameStart itself; its late-start
                # rescue asks WatchTower whether a game is running (~3s after
                # boot) and launches the brain. Give that path 20s, then force
                # it: Cmd=restart makes the launcher launch the brain directly.
                time.sleep(20)
                b_age = self.get_system_signals().get("ai_brain", {}).get("age_s")
                if b_age is not None and b_age <= (time.time() - t0):
                    outcome.append("brain traffic seen — rescue complete")
                else:
                    self.publish_raw("MermaidsTale/RedBeard/Cmd", "restart")
                    outcome.append("brain still silent after respawn — published "
                                   "Cmd=restart to force-launch it")
            elif result.get("ok"):
                outcome.append("respawned launcher never heartbeated within 45s — "
                               "AI is still down, needs hands on the machine")

            try:
                from models import database as db
                db.add_debug_entry(
                    device_name=None, severity="error",
                    title="Game started with the AI Character program DEAD",
                    description=(f"A live GameStart fired while ai_launcher was dead/silent ({seen}). "
                                 "WatchTower's sentry intervened so the game wouldn't run with "
                                 "silent characters.\n\n" + "\n".join(outcome) +
                                 "\n\nIf the characters are still quiet, use Reset Brain on the "
                                 "dashboard or restart via the START bat."),
                    created_by="watchtower",
                )
            except Exception:  # noqa: BLE001
                logger.exception("AI sentry debug-log entry failed")
            logger.error("AI GameStart sentry outcome: " + " | ".join(outcome))
        finally:
            self._ai_sentry_lock.release()

    def _note_system_signal(self, topic: str, payload: str, now: datetime):
        """Record live evidence that infrastructure systems are alive.
        Used by the dashboard's Systems group (separate from device tiles)."""
        # AI Character brain: any RedBeard traffic means the AI process is up
        # and publishing (e.g. MermaidsTale/RedBeard/Talking).
        if topic.startswith("MermaidsTale/RedBeard"):
            sig = self.system_signals["ai_brain"]
            sig["last_seen"] = now
            sig["detail"] = topic.split("/", 2)[-1]
        # ai_launcher.py heartbeat — proves the Reset Brain command has a
        # live receiver. Deliberately NOT under RedBeard/* so a dead brain
        # can't be masked by a healthy launcher (and vice versa).
        elif topic.startswith("MermaidsTale/AILauncher"):
            sig = self.system_signals["ai_launcher"]
            sig["last_seen"] = now
            sig["detail"] = payload or "alive"
        # M3 / Mythric game runner: State=Running on the AMT story.
        elif topic == "M3/Stories/AMT/State":
            sig = self.system_signals["m3"]
            sig["last_seen"] = now
            sig["detail"] = payload
        # Pirate wheel angle (2026-09-06): BP_Ship publishes pre_<deg> while
        # the wheel is plugged in AND the game is in the ship map. Any beat
        # here = wheel on + being read. ~18 msg/s while turning, silent when
        # the wheel sits still (09-05 log: idle gaps up to 83s).
        elif topic == "MermaidsTale/WheelPos":
            sig = self.system_signals["wheel"]
            sig["last_seen"] = now
            sig["detail"] = payload
        # AI brain phase + Direct-the-Character result (routes/direct_api.py).
        elif topic == "MermaidsTale/AI/Phase":
            sig = self.system_signals["ai_phase"]
            sig["last_seen"] = now
            sig["detail"] = payload
        elif topic == "MermaidsTale/AI/DirectResult":
            sig = self.system_signals["ai_direct_result"]
            sig["last_seen"] = now
            sig["detail"] = payload
        # Helm audio brain health: raw JSON, parsed by routes/say_api.py.
        elif topic == "MermaidsTale/Audio/status":
            sig = self.system_signals["helm_audio"]
            sig["last_seen"] = now
            sig["detail"] = payload
        # Unreal room heartbeat: raw JSON payload, parsed by the API layer.
        elif topic == "MermaidsTale/Unreal/RoomStatus":
            sig = self.system_signals["unreal_room"]
            prev = sig["last_seen"]
            sig["last_seen"] = now
            sig["detail"] = payload
            # Unreal (re)boot detector (2026-08-18): the heartbeat is every 5s,
            # so first-ever / >20s-gap means a fresh game process just came up.
            # The TotalMQTT plugin NEVER delivers broker-retained messages on
            # subscribe, so a fresh boot runs default camera/scale tuning even
            # though the broker holds the operator's numbers. Re-publish the
            # three retained tuning payloads a few seconds after boot (letting
            # the game's SUBSCRIBEs land) so every boot starts on the saved
            # calibration instead of drifting back to defaults.
            if prev is None or (now - prev).total_seconds() > 20:
                self.system_signals["unreal_boot"]["last_seen"] = now
                self.system_signals["unreal_boot"]["detail"] = payload
                self._schedule_tuning_republish("Unreal boot detected")

    def _schedule_tuning_republish(self, reason: str):
        """Kick off a one-shot delayed re-publish of the three retained tuning
        payloads (ship camera / jungle camera / character scale). Debounced to
        once per 30s so a boot's burst of RoomStatus beats runs it once."""
        with self._tuning_republish_lock:
            if time.time() - self._last_tuning_republish < 30:
                return
            self._last_tuning_republish = time.time()
        logger.info(f"Scheduling tuning re-publish in 3s ({reason})")
        threading.Thread(target=self._republish_tuning, name="tuning-republish",
                         daemon=True).start()

    def _republish_tuning(self):
        """Re-publish whatever tuning we know (broker-retained values mirrored
        into the attrs below) so a freshly booted Unreal — whose MQTT plugin
        never replays broker-retained messages on subscribe — still starts on
        the operator's saved calibration. 3s delay lets the game's connect-time
        SUBSCRIBEs land first. Retained + idempotent, so re-sends are safe."""
        time.sleep(3.0)
        for topic, attr in TUNING_TOPIC_ATTRS.items():
            payload = getattr(self, attr, "")
            if not payload:
                # Nothing cached and nothing on disk: publish the house
                # calibration so the room never runs on the build's bare
                # defaults just because the broker forgot.
                payload = self._house_default_payload(topic)
                if payload:
                    self.remember_tuning(topic, payload)
                    logger.info(f"No saved tuning for {topic}; using house defaults")
            if payload and self.client and self.connected:
                self.client.publish(topic, payload, retain=True)
                logger.info(f"Re-published retained tuning {topic} = {payload}")

    @staticmethod
    def _house_default_payload(topic: str) -> str:
        """House-calibration JSON for a tuning topic, from the slider field
        tables in routes/api.py (lazy import: api imports us at boot)."""
        try:
            from routes import api as _api  # noqa: WPS433
            fields = {
                "WatchTower/ShipCameraTuning":   _api.SHIP_CAMERA_FIELDS,
                "WatchTower/JungleCameraTuning": _api.JUNGLE_CAMERA_FIELDS,
                "WatchTower/CharacterScale":     _api.CHARACTER_SCALE_FIELDS,
            }.get(topic)
            if not fields:
                return ""
            return json.dumps({k: float(v["default"]) for k, v in fields.items()})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"House default lookup failed for {topic}: {e}")
            return ""

    def remember_tuning(self, topic: str, payload: str):
        """Cache a tuning payload for readback/re-publish AND mirror it to
        TUNING_STATE_FILE so it survives a broker restart (no persistence)
        and a WatchTower restart alike. Called by the /game slider POSTs,
        the suggested-calibration button, and the wire readback."""
        attr = TUNING_TOPIC_ATTRS.get(topic)
        if not attr or not payload:
            return
        if getattr(self, attr, "") == payload:
            return
        setattr(self, attr, payload)
        self._save_tuning_state()

    def _load_tuning_state(self):
        """Seed the tuning cache from disk at boot (broker replay, if the
        broker still has the topics, overwrites it moments later)."""
        try:
            if not os.path.exists(TUNING_STATE_FILE):
                return
            with open(TUNING_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            for topic, attr in TUNING_TOPIC_ATTRS.items():
                payload = data.get(topic)
                if isinstance(payload, dict):
                    setattr(self, attr, json.dumps(payload))
            logger.info(f"Tuning state loaded from {TUNING_STATE_FILE}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not load tuning state: {e}")

    def _save_tuning_state(self):
        try:
            data = {"saved": datetime.now().isoformat(timespec="seconds")}
            for topic, attr in TUNING_TOPIC_ATTRS.items():
                payload = getattr(self, attr, "")
                if payload:
                    try:
                        data[topic] = json.loads(payload)
                    except ValueError:
                        continue
            tmp = TUNING_STATE_FILE + ".tmp"
            with self._tuning_state_lock:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, TUNING_STATE_FILE)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not save tuning state: {e}")

    # Uptime formats seen on the wire: JungleDoor "18:55:04", BarrelPiston
    # "450", Cannon status "...Uptime:68117833ms...", CoveDoor "...UP325114s...".
    _UPTIME_MS_RE = re.compile(r"Uptime:(\d+)ms", re.IGNORECASE)
    _UPTIME_S_RE = re.compile(r"\bUP(\d+)s\b", re.IGNORECASE)
    _HMS_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")

    def _parse_uptime_s(self, topic: str, payload: str) -> Optional[float]:
        """Best-effort seconds-of-uptime from a message, else None."""
        if topic.endswith("/uptime"):
            m = self._HMS_RE.match(payload)
            if m:
                h, mi, s = (int(x) for x in m.groups())
                return h * 3600 + mi * 60 + s
            if payload.isdigit():
                return float(payload)
            return None
        m = self._UPTIME_MS_RE.search(payload)
        if m:
            return int(m.group(1)) / 1000.0
        m = self._UPTIME_S_RE.search(payload)
        if m:
            return float(m.group(1))
        return None

    def _note_pregame(self, topic: str, payload: str, now: datetime, retained: bool):
        """Track the signals behind the dashboard's Pre-Game Readiness banner."""
        # 1. Retained landmines. The retain flag is only set on retained-store
        #    replay at (re)subscribe — a live publish reaches an already-
        #    subscribed client with retain=0 even when the publisher set it
        #    (MQTT-3.3.1-9). So: add only on retained delivery, but pop on ANY
        #    empty payload — an empty publish on a landmine topic is only ever
        #    a wipe, and gating the pop on the flag left cleared landmines
        #    flagged until WatchTower reconnected.
        if topic in config.PREGAME_LANDMINE_TOPICS \
                or any(topic.endswith(s) for s in config.PREGAME_LANDMINE_SUFFIXES):
            with self.lock:
                if not payload:
                    self.retained_landmines.pop(topic, None)
                elif retained:
                    self.retained_landmines[topic] = payload

        # 2. Prop start-position states (room-reset check). Skip transient
        #    command replies — CompassTrio answers PING/RESET on its /status
        #    topic, and a stored "PONG" would mask the real SOLVED/UNSOLVED
        #    state until the next 5-min heartbeat. A row's "valid" substring
        #    additionally rejects payloads that aren't state reports at all —
        #    CoveDoor's /command carries raw commands AND a phantom v1.3.4
        #    board's maglock-less STATUS echo alongside the real reply.
        row = self._pregame_prop_rows.get(topic)
        if row is not None:
            low = payload.strip().lower()
            # Empty payload = a retained wipe, never a state — don't store it.
            if low and low not in config.PREGAME_PROP_TRANSIENT_PAYLOADS \
                    and row.get("valid", "").lower() in low:
                with self.lock:
                    self.prop_states[topic] = {"payload": payload, "ts": now}

        # 3. Reboot evidence: an explicit boot/reboot log line, or a device
        #    uptime that went backwards. Live messages only — a retained boot
        #    line replayed on our own reconnect is not a fresh reboot.
        if retained:
            return
        boot = False
        low = payload.lower()
        if "boot complete" in low or "rebooting" in low:
            boot = True
        else:
            up = self._parse_uptime_s(topic, payload)
            if up is not None:
                last = self._last_uptimes.get(topic)
                self._last_uptimes[topic] = up
                if last is not None and up + 30 < last:
                    boot = True
        if boot:
            device = self._extract_device_name(topic) or topic
            cutoff = now - timedelta(seconds=config.PREGAME_BOOTLOOP_WINDOW_S)
            with self.lock:
                events = [t for t in self.boot_events.get(device, []) if t > cutoff]
                events.append(now)
                self.boot_events[device] = events

    def refresh_retained_landmines(self):
        """Rebuild the landmine dict from the broker's actual retained store.
        Clearing it and resubscribing makes the broker replay every retained
        message with retain=1, so anything wiped (or planted) while we were
        already connected is reconciled within a second or two."""
        with self.lock:
            self.retained_landmines.clear()
        if self.client and self.connected:
            try:
                self.client.unsubscribe("#")
                self.client.subscribe("#")
            except Exception:  # noqa: BLE001 - a failed refresh just leaves the dict empty
                logger.exception("Retained-landmine resubscribe failed")

    def get_pregame_signals(self) -> dict:
        """Snapshot for the Pre-Game Readiness checks in /api/status."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=config.PREGAME_BOOTLOOP_WINDOW_S)
        with self.lock:
            landmines = dict(self.retained_landmines)
            props = {
                t: {"payload": s["payload"], "age_s": (now - s["ts"]).total_seconds()}
                for t, s in self.prop_states.items()
            }
            boot_loops = {}
            for dev, times in self.boot_events.items():
                recent = [t for t in times if t > cutoff]
                if len(recent) >= config.PREGAME_BOOTLOOP_COUNT:
                    boot_loops[dev] = {
                        "count": len(recent),
                        "last_age_s": (now - max(recent)).total_seconds(),
                    }
        return {"landmines": landmines, "props": props, "boot_loops": boot_loops}

    def get_system_signals(self) -> dict:
        """Snapshot of system signals with seconds-since-last-seen, for the API."""
        now = datetime.now()
        out = {}
        with self.lock:
            for key, sig in self.system_signals.items():
                last = sig["last_seen"]
                out[key] = {
                    "last_seen": last.isoformat() if last else None,
                    "age_s": (now - last).total_seconds() if last else None,
                    "detail": sig["detail"],
                }
        return out

    def _extract_device_name(self, topic: str) -> Optional[str]:
        """Extract device name from MQTT topic."""
        parts = topic.split("/")
        if len(parts) > 1 and parts[0] == "MermaidsTale":
            return parts[1]
        elif len(parts) > 0:
            return parts[0]
        return None

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def ping_device(self, device_name: str) -> bool:
        """Send a ping to a specific device."""
        if device_name not in self.devices or not self.connected:
            return False

        device = self.devices[device_name]
        with self.lock:
            device.status = DeviceStatus.TESTING
            device.last_test = datetime.now()
            device.response_time_ms = None

        if device.device_type == DeviceType.ESP32:
            topic = f"MermaidsTale/{device.topic_base}/command"
            self.client.publish(topic, "PING")
            self._track_sent(topic, "PING")
            logger.info(f"→ Pinged {device_name} on {topic}")
        else:
            logger.info(f"→ Waiting for BAC {device_name} heartbeat")

        return True

    def ping_all(self):
        """Ping all devices."""
        for name in self.devices:
            self.ping_device(name)

    def send_command(self, device_name: str, command: str) -> dict:
        """Send a command to a device."""
        if device_name not in self.devices:
            return {"error": f"Unknown device: {device_name}"}
        if not self.connected:
            return {"error": "MQTT not connected"}

        device = self.devices[device_name]

        if device.device_type == DeviceType.ESP32:
            topic = f"MermaidsTale/{device.topic_base}/command"
        else:
            topic = f"{device.topic_base}/set/{command.lower()}"

        self.client.publish(topic, command)
        self._track_sent(topic, command)

        # Add TX to feed
        message = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_full": datetime.now().isoformat(),
            "direction": "TX",
            "topic": topic,
            "payload": command,
            "device": device_name
        }
        with self.lock:
            self.message_feed.insert(0, message)
            if len(self.message_feed) > self.max_feed_messages:
                self.message_feed.pop()

        return {"device": device_name, "command": command, "topic": topic, "sent": True}

    def publish_raw(self, topic: str, payload: str, retain: bool = False) -> dict:
        """Publish an arbitrary topic/payload (not tied to the device registry).
        Used for infrastructure commands like the AI-brain restart, which target
        a listener on the AI machine rather than a registered ESP32/BAC device.
        retain=True persists the value on the broker (ship-camera tuning)."""
        if not self.connected:
            return {"error": "MQTT not connected"}

        self.client.publish(topic, payload, retain=retain)
        self._track_sent(topic, payload)

        message = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_full": datetime.now().isoformat(),
            "direction": "TX",
            "topic": topic,
            "payload": payload,
            "device": "WatchTower",
        }
        with self.lock:
            self.message_feed.insert(0, message)
            if len(self.message_feed) > self.max_feed_messages:
                self.message_feed.pop()

        return {"topic": topic, "payload": payload, "sent": True}

    def check_timeouts(self):
        """Mark devices as offline if they didn't respond in time."""
        now = datetime.now()
        with self.lock:
            for device in self.devices.values():
                if device.status == DeviceStatus.TESTING and device.last_test:
                    elapsed = (now - device.last_test).total_seconds()
                    timeout = config.BAC_PING_TIMEOUT if device.device_type == DeviceType.BAC else config.ESP32_PING_TIMEOUT
                    if elapsed > timeout:
                        device.status = DeviceStatus.OFFLINE
                        device.last_error = "No response"

    def get_status_summary(self) -> dict:
        """Get full status summary for API."""
        self.check_timeouts()
        summary = {
            "broker_connected": self.connected,
            "broker_host": config.MQTT_BROKER,
            "broker_port": config.MQTT_PORT,
            "timestamp": datetime.now().isoformat(),
            "devices": {},
            "counts": {"online": 0, "offline": 0, "unknown": 0, "testing": 0}
        }

        with self.lock:
            for name, device in self.devices.items():
                summary["devices"][name] = {
                    "type": device.device_type.value,
                    "status": device.status.value,
                    "icon": device.icon,
                    "color": device.color,
                    "room": device.room,
                    "topic": device.topic_base,
                    "last_test": device.last_test.isoformat() if device.last_test else None,
                    "response_ms": device.response_time_ms,
                    "error": device.last_error,
                    "commands": device.commands,
                    "needs_protocol": device.needs_protocol,
                    "grimoire_slug": config.GRIMOIRE_SLUG_MAP.get(name),
                    "sensor_faults": list(device.sensor_faults),
                }
                summary["counts"][device.status.value] += 1

        return summary

    def get_feed(self, limit=50) -> list:
        """Get recent messages from the feed."""
        with self.lock:
            return self.message_feed[:limit]

    def _track_sent(self, topic, payload):
        """Track sent messages for echo suppression."""
        with self.lock:
            self.recent_sent.insert(0, (topic, payload))
            if len(self.recent_sent) > 20:
                self.recent_sent.pop()
