#!/usr/bin/env python3
"""
mic_probe.py — Live character-microphone health probes for WatchTower.
=======================================================================
2026-09-17: now TWO probes — the Pirate Ship mic (RedBeard) and the Jungle
mic (Evalee, USB TONOR renamed "Jungle Microphone" 09-12). One MicProbe per
mic, ONE listener thread feeding them all; /api/status exposes them as "mic"
(ship) and "mics" (all).

The character mics are NOT MQTT devices (they don't PING/PONG like the
ESP32s), so they can't ride the normal device-status pipeline. Instead this
module opens the SAME physical mics the characters listen through and
measures their live input level in a background thread, then exposes
snapshots the API merges into /api/status.

Why this exists: the recurring "Red Beard goes deaf" failure (mic unplugged
/ muted / zero gain / held by another app / wrong device enumeration) used
to only get caught by the interactive mic_check.py at launch. This makes it
a LIVE, always-on tile on the WatchTower dashboard so the GM can glance and
see the mic is hearing — at any point, not just at startup.

Device names come from the AI's own INPUT_MIC_DEVICE_MAP and the lookup
order + RMS math are the SAME as mic_check.py / camera_conversation_client.py
so this can NEVER drift from what the AI opens.

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

# --- Mic names: single source of truth = the AI's own map --------------------
# The AI System lives next to the game; add it to sys.path so the import works
# regardless of CWD. If that import fails we fall back to the well-known names
# (belt-and-suspenders, same pattern as mic_check.py).
_AI_PATH = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\AI Character System"

MIC_SUBSTR = "Pirate Ship Microphone"
JUNGLE_MIC_SUBSTR = "Jungle Microphone"
try:
    if _AI_PATH not in sys.path and os.path.isdir(_AI_PATH):
        sys.path.insert(0, _AI_PATH)
    from camera_conversation_client import INPUT_MIC_DEVICE_MAP  # type: ignore
    MIC_SUBSTR = INPUT_MIC_DEVICE_MAP.get("redbeard", MIC_SUBSTR)
    JUNGLE_MIC_SUBSTR = INPUT_MIC_DEVICE_MAP.get("evalee_jungle", JUNGLE_MIC_SUBSTR)
    logger.info("mic_probe: mic names from the AI config: '%s', '%s'", MIC_SUBSTR, JUNGLE_MIC_SUBSTR)
except Exception as e:  # noqa: BLE001 - any import/path problem -> fall back
    logger.warning("mic_probe: could not import AI mic config (%s); using default names", e)

# --- Capture / level config (matches mic_check.py) --------------------------
RATE = 16000          # match rtsp_audio_interface input_sample_rate
CHUNK = 1024
SILENT_RMS = 120      # below this = effectively dead/quiet
SPEAK_OK = 600        # a peak above this = a real voice/signal was heard
RECENT_VOICE_SECS = 4.0   # how long a "voice seen" keeps status == online
REOPEN_BACKOFF = 3.0      # seconds to wait before retrying a failed open
OUTSIDE_LOOK_SECS = 15.0  # how often to look for a missing mic (see _Listener)


def _rms(block: bytes) -> float:
    n = len(block) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", block[: n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


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
    """One character mic: its name/room + the live level the listener feeds it."""

    def __init__(self, substr=None, name="Pirate Ship Microphone", room="Ship Deck",
                 listener="Red Beard"):
        self._substr = substr or MIC_SUBSTR   # Windows device-name substring
        self._name = name                     # tile label
        self._room = room                     # dashboard room section
        self._listener = listener             # which character hears through it
        self._lock = threading.Lock()

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
        self._started = False        # has the listener looked for it at least once

    # -- lifecycle (kept so old callers can still do probe.start()) ----------
    def start(self):
        _listener.start()

    def stop(self):
        _listener.stop()

    # -- called ONLY from the listener thread --------------------------------
    def _resolve_index(self, p):
        """Find the mic index in the same order the AI does (MME first, then
        DirectSound, then anything) — but on the listener's own PyAudio
        instance, never a second one (see _Listener)."""
        import pyaudio
        target = self._substr.lower()
        mme = dsound = None
        for i in range(p.get_host_api_count()):
            t = p.get_host_api_info_by_index(i).get("type")
            if t == pyaudio.paMME:
                mme = i
            elif t == pyaudio.paDirectSound:
                dsound = i
        best = {}
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) <= 0 or target not in info["name"].lower():
                continue
            rank = 0 if info.get("hostApi") == mme else 1 if info.get("hostApi") == dsound else 2
            best.setdefault(rank, i)
        return best[min(best)] if best else None

    def _set_fault(self, error, present):
        with self._lock:
            self._present = present
            self._live = False
            self._error = error
            self._level = 0.0
            self._started = True
            if not present:
                self._device_index = None
                self._device_name = None

    def _open(self, p):
        """Find + open this mic on the listener's PyAudio. -> stream or None."""
        idx = self._resolve_index(p)
        if idx is None:
            self._set_fault(f"mic '{self._substr}' not found", present=False)
            return None
        name = p.get_device_info_by_index(idx)["name"]
        try:
            stream = p.open(
                format=p.get_format_from_width(2), channels=1, rate=RATE,
                input=True, input_device_index=idx, frames_per_buffer=CHUNK,
            )
        except Exception as e:  # noqa: BLE001 - exists but won't open
            self._set_fault(f"stream won't open: {e}", present=True)
            with self._lock:
                self._device_index, self._device_name = idx, name
            return None
        with self._lock:
            self._present = True
            self._live = True
            self._device_index = idx
            self._device_name = name
            self._error = None
            self._started = True
        logger.info("mic_probe: listening on '%s' (index %s)", name, idx)
        return stream

    def _feed(self, block):
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


class _Listener:
    """The single background thread that owns PyAudio and feeds every probe.

    2026-09-17 lesson: PortAudio is NOT thread-safe. The first two-mic version
    gave each probe its own thread + PyAudio instance and WatchTower died with
    a segfault seconds after launch. So: one thread, one PyAudio instance,
    every mic's stream opened and read from that same thread.

    PortAudio also reads the Windows device list ONCE per instance, so a mic
    plugged in later stays invisible. While any mic is missing, a throwaway
    subprocess looks at the fresh device list every OUTSIDE_LOOK_SECS; if the
    mic is back, the listener closes everything and re-opens (a ~1 s blip).
    """

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._rescan = threading.Event()   # set by the outside-look helper
        self._looking = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mic-probe", daemon=True)
        self._thread.start()
        logger.info("mic_probe: listener thread started (%s)",
                    ", ".join(f"'{mp._substr}'" for mp in ALL_PROBES))

    def stop(self):
        self._stop.set()

    def _outside_look(self, missing):
        """Short-lived helper thread — subprocess only, never touches PyAudio
        in this process."""
        try:
            for mp in missing:
                if _device_visible_outside(mp._substr):
                    logger.info("mic_probe: '%s' is back — refreshing the device list", mp._substr)
                    self._rescan.set()
                    return
        finally:
            self._looking = False

    def _run(self):
        try:
            import pyaudio
        except Exception as e:  # noqa: BLE001
            for mp in ALL_PROBES:
                mp._set_fault(f"pyaudio unavailable: {e}", present=False)
            logger.warning("mic_probe: pyaudio unavailable: %s", e)
            return

        while not self._stop.is_set():
            p = None
            streams = {}     # probe -> open stream
            try:
                p = pyaudio.PyAudio()
                self._rescan.clear()
                for mp in ALL_PROBES:
                    st = mp._open(p)
                    if st is not None:
                        streams[mp] = st
                last_look = time.monotonic()
                retry_at = time.monotonic() + REOPEN_BACKOFF * 5

                while not self._stop.is_set() and not self._rescan.is_set():
                    if not streams:
                        self._stop.wait(0.5)
                    for mp, st in list(streams.items()):
                        try:
                            mp._feed(st.read(CHUNK, exception_on_overflow=False))
                        except Exception as e:  # noqa: BLE001 - unplugged mid-read
                            mp._set_fault(f"read fault: {e}", present=False)
                            logger.warning("mic_probe: '%s' %s", mp._substr, e)
                            try:
                                st.close()
                            except Exception:  # noqa: BLE001
                                pass
                            del streams[mp]
                    missing = [mp for mp in ALL_PROBES if mp not in streams]
                    now = time.monotonic()
                    if missing and not self._looking and now - last_look >= OUTSIDE_LOOK_SECS:
                        last_look = now
                        self._looking = True
                        threading.Thread(target=self._outside_look, args=(missing,),
                                         name="mic-probe-look", daemon=True).start()
                    # a mic that exists but would not open: plain periodic retry
                    if now >= retry_at and any(mp._present for mp in missing):
                        break
            except Exception as e:  # noqa: BLE001
                logger.warning("mic_probe: listener fault: %s — reopening", e)
            finally:
                for st in streams.values():
                    try:
                        st.stop_stream()
                        st.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    if p is not None:
                        p.terminate()
                except Exception:  # noqa: BLE001
                    pass
            self._stop.wait(1.0 if self._rescan.is_set() else REOPEN_BACKOFF)


# Module-level singletons the app wires up once.
probe = MicProbe()   # Pirate Ship mic (RedBeard) — name kept for old imports
jungle_probe = MicProbe(substr=JUNGLE_MIC_SUBSTR, name="Jungle Microphone",
                        room="Jungle", listener="Evalee")
ALL_PROBES = (probe, jungle_probe)
_listener = _Listener()


def start_all():
    """Start the one listener thread that feeds every probe."""
    _listener.start()
