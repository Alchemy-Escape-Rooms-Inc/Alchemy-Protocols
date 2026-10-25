"""
WatchTower V2 — Room power (Voice Monkey)
=========================================
One ON and one OFF button for the room's smart switches. Each fires a Voice
Monkey trigger, which runs the matching Alexa routine ("room on" / "room off").
Replaced the per-plug Alexa-cloud Power section (alexapy never got past
Amazon's verification wall). Token lives in git-ignored voicemonkey_token.txt.
"""

import logging
import os
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

room_power_api = Blueprint("room_power_api", __name__, url_prefix="/api/room-power")

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "voicemonkey_token.txt")
TRIGGER_URL = "https://api-v3.voicemonkey.io/trigger"
DEVICES = {"on": "room-on-4m7px", "off": "room-off-ltumk"}
WATERFALL_ON = "waterfall-on-clcmb"   # fired by the MQTT client on the in-game Jungle Door OPEN


def _token():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def trigger(device):
    """Fire one Voice Monkey trigger. Returns (ok, reply-or-error)."""
    token = _token()
    if not token:
        return False, "voicemonkey_token.txt missing"
    url = TRIGGER_URL + "?" + urllib.parse.urlencode({"token": token, "device": device})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read(500).decode("utf-8", "replace")
            ok = 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Voice Monkey {device} failed: {e}")
        return False, str(e)
    logger.info(f"Voice Monkey {device} -> {body[:120]}")
    return ok, body[:200]


@room_power_api.route("/<state>", methods=["POST"])
def room_power(state):
    device = DEVICES.get(state)
    if not device:
        return jsonify({"ok": False, "error": "state must be on or off"}), 400
    ok, reply = trigger(device)
    return jsonify({"ok": ok, "state": state, "reply" if ok else "error": reply}), (200 if ok else 502)
