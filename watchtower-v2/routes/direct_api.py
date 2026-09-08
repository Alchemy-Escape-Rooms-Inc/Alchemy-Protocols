"""Direct the Character — GM notes to the LIVE AI character (2026-09-08).

Why: in the first paying game (09-05) the GM launched a SECOND copy of the
AI Character program mid-game to type a hint to Red Beard. That copy had no
audio and no session; the real one kept talking. The program's stdin typing
path lives on a minimized launcher window nobody can reach during a show.

How: this API publishes the GM's note on MermaidsTale/AI/Direct. The live
brain (state_manager.py, TOPIC_AI_DIRECT) turns it into a private stage
direction for whichever character is active and answers on
MermaidsTale/AI/DirectResult (JSON). Who is live comes from
MermaidsTale/AI/Phase ("<phase>|<agent>", every 30 s heartbeat + on change).

Three modes, chosen on the card:
  direct  plain note      -> the character improvises 1-2 short lines from it
  say     "say: <words>"  -> the character speaks those words near-verbatim
  quiet   "quiet: <note>" -> silent context for the character's NEXT reply

Difference from Talk to the Players (/api/say): that one renders YOUR text
with the character's voice through Helm — no AI involved. This one hands the
note to the live AI so the character stays in character and in the flow.
"""

import json
import logging
import threading
import time
from datetime import datetime

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

direct_api = Blueprint("direct_api", __name__, url_prefix="/api/direct")

TOPIC_DIRECT = "MermaidsTale/AI/Direct"
TOPIC_RESULT = "MermaidsTale/AI/DirectResult"

MODES = {
    "direct": "Direct (character improvises from your note)",
    "say":    "Say it (near word-for-word)",
    "quiet":  "Quiet nudge (shapes the next reply, no line now)",
}
AGENT_LABELS = {
    "redbeard": "Red Beard", "evalee_jungle": "Evalee (jungle)",
    "evalee_cove": "Evalee (cove)", "none": "nobody",
}
PHASE_LABELS = {
    "waiting": "waiting for the skull key (cabin)", "redbeard_live": "ship",
    "evalee_jungle_live": "jungle", "evalee_cove_live": "cove",
    "cove_unreal": "finale (characters silent)", "game_over": "game over",
}

_mqtt_client = None
_history = []          # newest first, max 12
_lock = threading.Lock()


def set_mqtt_client(client):
    global _mqtt_client
    _mqtt_client = client


def _signal(key: str) -> dict:
    sig = (_mqtt_client.get_system_signals() if _mqtt_client else {}).get(key, {})
    return {"age_s": sig.get("age_s"), "detail": sig.get("detail")}


def _live() -> dict:
    """Who the brain says is live, from MermaidsTale/AI/Phase."""
    brain = _signal("ai_brain")
    phase_sig = _signal("ai_phase")
    out = {"brain_up": brain["age_s"] is not None and brain["age_s"] < 120,
           "brain_age_s": brain["age_s"], "phase": None, "agent": "none",
           "phase_label": None, "agent_label": AGENT_LABELS["none"], "fresh": False}
    detail = phase_sig["detail"] or ""
    if "|" in detail and phase_sig["age_s"] is not None and phase_sig["age_s"] < 90:
        phase, agent = detail.split("|", 1)
        out.update(phase=phase, agent=agent or "none", fresh=True,
                   phase_label=PHASE_LABELS.get(phase, phase),
                   agent_label=AGENT_LABELS.get(agent, agent))
    return out


def _match_result(entry: dict):
    """Attach the brain's DirectResult to a history entry once it arrives."""
    res = _signal("ai_direct_result")
    detail = res["detail"]
    if not detail or res["age_s"] is None or res["age_s"] > 30:
        return
    try:
        data = json.loads(detail)
    except (ValueError, TypeError):
        return
    if data.get("text", "")[:60] == entry["text"][:60] and data.get("mode") == entry["mode"]:
        entry["ok"] = bool(data.get("ok"))
        entry["error"] = data.get("error")
        entry["agent_label"] = AGENT_LABELS.get(data.get("agent", "none"), data.get("agent"))
        entry["settled"] = True


def _context() -> dict:
    with _lock:
        for e in _history:
            if not e.get("settled"):
                _match_result(e)
        hist = list(_history[:12])
    live = _live()
    return {
        "live": live,
        "modes": [{"id": k, "label": v} for k, v in MODES.items()],
        "history": hist,
    }


@direct_api.route("/context")
def direct_context():
    return jsonify(_context())


@direct_api.route("", methods=["POST"])
def direct():
    body = request.get_json(silent=True) or {}
    text = " ".join(str(body.get("text", "")).split()).strip()
    mode = str(body.get("mode") or "direct").lower()
    if not text:
        return jsonify({"ok": False, "error": "Nothing to send — type a note first."}), 400
    if len(text) > 500:
        return jsonify({"ok": False, "error": "Keep it under 500 characters — the character only speaks one or two lines from it."}), 400
    if mode not in MODES:
        return jsonify({"ok": False, "error": f"Unknown mode '{mode}'."}), 400
    if _mqtt_client is None or not getattr(_mqtt_client, "connected", False):
        return jsonify({"ok": False, "error": "WatchTower is not connected to the MQTT broker."}), 503
    live = _live()
    if not live["brain_up"]:
        return jsonify({"ok": False, "error": "The AI Character program is not running (no brain heartbeat) — nothing would hear this.",
                        "live": live}), 503
    if live["fresh"] and live["agent"] == "none":
        return jsonify({"ok": False,
                        "error": f"No character is live right now ({live['phase_label']}). Red Beard wakes on the skull key; Evalee on the jungle door.",
                        "live": live}), 409
    payload = text if mode == "direct" else f"{mode}: {text}"
    res = _mqtt_client.publish_raw(TOPIC_DIRECT, payload)
    if isinstance(res, dict) and res.get("error"):
        return jsonify({"ok": False, "error": res["error"]}), 503
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"), "text": text, "mode": mode,
        "mode_label": MODES[mode].split(" (")[0], "agent_label": live["agent_label"],
        "ok": None, "error": None, "settled": False, "sent_at": time.time(),
    }
    with _lock:
        _history.insert(0, entry)
        del _history[12:]
    logger.info(f"DIRECT [{mode} -> {live['agent']}] {text!r}")
    return jsonify({"ok": True, "sent": entry, "live": live})
