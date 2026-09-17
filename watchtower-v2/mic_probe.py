#!/usr/bin/env python3
"""
mic_probe.py — Live character-microphone health probes for WatchTower.
=======================================================================
2026-09-17: now TWO probes — the Pirate Ship mic (RedBeard) and the Jungle
mic (Evalee, USB TONOR renamed "Jungle Microphone" 09-12). Same class, one
instance per mic; /api/status exposes them as "mic" (ship) and "mics" (all).

The Pirate Ship mic is NOT an MQTT device (it doesn't PING/PONG like the
ESP32s), so it can't ride the normal device-status pipeline. Instead this
module opens the SAME physical mic Red Beard listens through and measures
its live input level in a background thread, then exposes a snapshot the
API merges into /api/status under a top-level "mic" key.

Why this exists: the recurring "Red Beard goes deaf" failure (mic unplugged
/ muted / zero gain / held by another app / wrong device enumeration) used
to only get caught by the interactive mic_check.py at launch. This makes it
a LIVE, always-on tile on the WatchTower dashboard so the GM can glance and
see the mic is hearing — at any point, not just at startup.

Device resolution + RMS math are deliberately the SAME as mic_check.py /
camera_conversation_client.py so this can NEVER drift from what the AI opens.

Status semantics exposed in snapshot():
  status: "online"  -> stream open AND a real voice/signal seen recently
          "idle"    -> stream open, device healthy, but quiet right now
          "offline" -> device not found, or stream won't open (THE bad one)
          "unknown" -> probe hasn't completed its first read yet
"""
import sys
import os
import time
import struct
import threading
import logging

logger = logging.getLogger(__name__)

# --- Resolve the mic the SAME way the AI does -------------------------------
# Pull the AI's own device-resolution helper + canonical name so this probe
# opens EXACTLY the device Red Beard opens. The AI System lives next to the
# game; add it to sys.path so the import works regardless of CWD. If that
# import fails we fall back to the well-known name + a local resolver so the
# probe still works (belt-and-suspenders, same pattern as mic_check.py).
_AI_PATH = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\AI Character System"

MIC_SUBSTR = "Pirate Ship Microphone"
JUNGLE_MIC_SUBSTR = "Jungle Microphone"
_find_input_device_index = None
try:
    if _AI_PATH not in sys.path and os.path.isdir(_AI_PATH):
        sys.path.insert(0, _AI_PATH)
    from camera_conversation_client import (  # type: ignore
        find_input_device_index as _find_input_device_index,
        INPUT_MIC_DEVICE_MAP,
    )
    MIC_SUBSTR = INPUT_MIC_DEVICE_MAP.get("redbeard", MIC_SUBSTR)
    JUNGLE_MIC_SUBSTR = INPUT_MIC_DEVICE_MAP.get("evalee_jungle", JUNGLE_MIC_SUBSTR)
    logger.info("mic_probe: using AI device resolver, mic substr '%s'", MIC_SUBSTR)
except Exception as e:  # noqa: BLE001 - any import/path problem -> fall back
    logger.warning("mic_probe: could not import AI mic config (%s); using default name", e)

# --- Capture / level config (matches mic_check.py) --------------------------
RATE = 16000          # match rtsp_audio_interface input_sample_rate
CHUNK = 1024
SILENT_RMS = 120      # below this = effectively dead/quiet
SPEAK_OK = 600        # a peak above this = a real voice/signal was heard
RECENT_VOICE_SECS = 4.0   # how long a "voice seen" keeps status == online
REOPEN_BACKOFF = 3.0      # seconds to wait before retrying a failed open


def _rms(block: bytes) -> float:
    n = len(block) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", block[: n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


# --- Shared PortAudio bookkeeping (device-list refresh) ---------------------
# PortAudio reads the Windows device list ONCE, when the first PyAudio() in the
# process is created, and keeps it until the LAST one is terminated. With two
# probes one is almost always open, so a mic plugged in later would stay
# "not found" until WatchTower restarted. A probe that can't find its mic
# therefore looks from a fresh process, and if the mic is there it asks every
# probe to close for a moment (_request_rescan) so the list is rebuilt.
OUTSIDE_LOOK_SECS = 15.0
_pa_cond = threading.Condition()
_pa_active = 0        # PyAudio instances currently open in this process
_rescan_gen = 0       # bumped on every refresh request; read loops watch it
_draining = False     # True while waiting for every instance to close


def _pa_open(pyaudio, stop_event):
    """Create a PyAudio instance (waits out a refresh). -> (instance, gen)."""
    global _pa_active, _draining
    with _pa_cond:
        while _draining and _pa_active > 0:
            if stop_event.is_set():
                return None, _rescan_gen
            _pa_cond.wait(0.5)
        _draining = False
        _pa_active += 1
        gen = _rescan_gen
    try:
        return pyaudio.PyAudio(), gen
    except Exception:
        with _pa_cond:
            _pa_active -= 1
            _pa_cond.notify_all()
        raise


def _pa_close(p):
    global _pa_active
    try:
        p.terminate()
    except Exception:  # noqa: BLE001
        pass
    with _pa_cond:
        _pa_active = max(0, _pa_active - 1)
        _pa_cond.notify_all()


def _request_rescan():
    global _rescan_gen, _draining
    with _pa_cond:
        _rescan_gen += 1
        _draining = True
        _pa_cond.notify_all()


def _device_visible_outside(substr: str) -> bool:
    """Does a FRESH process see a recording device with this name?"""
    import subprocess
    code = ("import sys, pyaudio; p = pyaudio.PyAudio(); t = sys.argv[1].lower(); "
            "print(any(p.get_device_info_by_index(i).get('maxInputChannels', 0) > 0 "
            "and t in p.get_device_info_by_index(i)['name'].lower() "
            "for i in range(p.get_device_count()))); p.terminate()")
    try:
        out = subprocess.run(
            [sys.executable, "-c", code, substr], capture_output=True, text=True,
            timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        return "True" in out
    except Exception as e:  # noqa: BLE001
        logger.debug("mic_probe: outside look failed: %s", e)
        return False


class MicProbe:
    """Background thread that keeps one character mic open and measures level."""

    def __init__(self, substr=None, name="Pirate Ship Microphone", room="Ship Deck",
                 listener="Red Beard"):
        self._substr = substr or MIC_SUBSTR   # Windows device-name substring
        self._name = name                     # tile label
        self._room = room                     # dashboard room section
        self._listener = listener             # which character hears through it
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()

        # Snapshot fields (guarded by _lock)
        self._present = False        # device exists in the enumeration
        self._live = False           # stream currently open and reading
        self._device_name = None
        self._device_index = None
        self._level = 0.0            # most recent RMS
        self._peak = 0.0            # rolling peak (decays)
        self._last_voice_ts = 0.0   # monotonic time we last saw SPEAK_OK
        self._last_read_ts = 0.0    # monotonic time of last successful read
        self._error = None
        self._started = False        # has the loop completed at least one cycle
        self._last_outside_look = 0.0  # last fresh-process device-list look

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"mic-probe-{self._room}", daemon=True)
        self._thread.start()
        logger.info("mic_probe: probe thread started for '%s'", self._substr)

    def stop(self):
        self._stop.set()

    # -- the probe loop ------------------------------------------------------
    def _resolve_index(self, p):
        """Find the mic index the same way the AI does, with a local fallback."""
        idx = None
        if _find_input_device_index is not None:
            try:
                idx = _find_input_device_index(self._substr)
            except Exception as e:  # noqa: BLE001
                logger.debug("mic_probe: AI resolver error (%s); using local scan", e)
                idx = None
        if idx is None:
            target = self._substr.lower()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and target in info["name"].lower():
                    idx = i
                    break
        return idx

    def _run(self):
        try:
            import pyaudio
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._error = f"pyaudio unavailable: {e}"
                self._started = True
            logger.warning("mic_probe: %s", self._error)
            return

        while not self._stop.is_set():
            p = None
            stream = None
            try:
                p, my_gen = _pa_open(pyaudio, self._stop)
                if p is None:
                    break
                idx = self._resolve_index(p)

                if idx is None:
                    with self._lock:
                        self._present = False
                        self._live = False
                        self._device_index = None
                        self._device_name = None
                        self._error = f"mic '{self._substr}' not found"
                        self._level = 0.0
                        self._started = True
                    # PortAudio only re-scans USB devices when EVERY instance in
                    # this process is closed, and the other probe keeps one open.
                    # So look from a fresh process; if the mic is back, ask all
                    # probes to let go for a moment so the list refreshes.
                    now = time.monotonic()
                    if now - self._last_outside_look >= OUTSIDE_LOOK_SECS:
                        self._last_outside_look = now
                        if _device_visible_outside(self._substr):
                            logger.info("mic_probe: '%s' is back — refreshing the device list", self._substr)
                            _request_rescan()
                    continue

                name = p.get_device_info_by_index(idx)["name"]
                try:
                    stream = p.open(
                        format=p.get_format_from_width(2), channels=1, rate=RATE,
                        input=True, input_device_index=idx, frames_per_buffer=CHUNK,
                    )
                except Exception as e:  # noqa: BLE001 - exists but won't open
                    with self._lock:
                        self._present = True
                        self._live = False
                        self._device_index = idx
                        self._device_name = name
                        self._error = f"stream won't open: {e}"
                        self._level = 0.0
                        self._started = True
                    continue

                with self._lock:
                    self._present = True
                    self._live = True
                    self._device_index = idx
                    self._device_name = name
                    self._error = None
                logger.info("mic_probe: listening on '%s' (index %s)", name, idx)

                # Read until told to stop, the stream faults, or another probe
                # asks for a device-list refresh.
                while not self._stop.is_set() and _rescan_gen == my_gen:
                    block = stream.read(CHUNK, exception_on_overflow=False)
                    level = _rms(block)
                    now = time.monotonic()
                    with self._lock:
                        self._level = level
                        # peak decays slowly so the meter doesn't stick high
                        self._peak = max(level, self._peak * 0.9)
                        self._last_read_ts = now
                        if level >= SPEAK_OK:
                            self._last_voice_ts = now
                        self._started = True

            except Exception as e:  # noqa: BLE001 - stream fault mid-read, etc.
                with self._lock:
                    self._live = False
                    self._error = f"read fault: {e}"
                    self._level = 0.0
                logger.warning("mic_probe: %s — reopening", e)
            finally:
                try:
                    if stream is not None:
                        stream.stop_stream()
                        stream.close()
                except Exception:  # noqa: BLE001
                    pass
                if p is not None:
                    _pa_close(p)
                # (a `continue` above still lands here first, then backs off)
                rescanning = _draining
                if not rescanning:
                    self._sleep(REOPEN_BACKOFF)

    def _sleep(self, secs):
        # Interruptible sleep so stop() is responsive.
        self._stop.wait(secs)

    # -- snapshot for the API ------------------------------------------------
    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if not self._started:
                status = "unknown"
            elif not self._present or not self._live:
                status = "offline"
            elif (now - self._last_voice_ts) <= RECENT_VOICE_SECS:
                status = "online"
            else:
                status = "idle"

            level = self._level
            peak = self._peak
            # how long since we last had a real read (staleness guard)
            age = (now - self._last_read_ts) if self._last_read_ts else None
            return {
                "name": self._name,
                "listener": self._listener,
                "device_name": self._device_name,
                "device_index": self._device_index,
                "icon": "🎤",
                "color": "#4A90D9",
                "room": self._room,
                "status": status,
                "present": self._present,
                "live": self._live,
                "level": round(level, 1),
                "peak": round(peak, 1),
                "silent_rms": SILENT_RMS,
                "speak_ok": SPEAK_OK,
                "error": self._error,
                "age_secs": round(age, 1) if age is not None else None,
            }


# Module-level singletons the app wires up once.
probe = MicProbe()   # Pirate Ship mic (RedBeard) — name kept for old imports
jungle_probe = MicProbe(substr=JUNGLE_MIC_SUBSTR, name="Jungle Microphone",
                        room="Jungle", listener="Evalee")
ALL_PROBES = (probe, jungle_probe)
