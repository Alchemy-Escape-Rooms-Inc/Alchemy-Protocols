"""
WatchTower V2 — Alyssa Calls API
=================================
Who has called the business line, straight from ElevenLabs.

    GET /api/calls            -> {calls:[...], fetched_at, error?}
    GET /api/calls/<conv_id>  -> {transcript:[{role, secs, text}], ...}

The list endpoint already carries the title/outcome/sentiment; the caller's
phone number only appears in the per-conversation detail (dynamic variable
system__caller_id), so each conversation is fetched once and remembered in
calls_cache.json — finished calls never change, so the cache is permanent.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

import config

logger = logging.getLogger(__name__)

calls_api = Blueprint("calls_api", __name__, url_prefix="/api/calls")

EL_BASE = "https://api.elevenlabs.io/v1/convai"

_lock = threading.Lock()
_list_cache = {"at": 0.0, "calls": [], "error": None}
_detail_cache = {}          # conversation_id -> enriched dict (persisted)
_cache_loaded = False


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------
def _read_env_file(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _creds():
    env = _read_env_file(config.ALYSSA_ENV_PATH)
    key = os.environ.get("ELEVENLABS_API_KEY") or env.get("ELEVENLABS_API_KEY")
    agent = (os.environ.get("ALYSSA_AGENT_ID") or env.get("ELEVENLABS_AGENT_ID")
             or config.ALYSSA_AGENT_ID_FALLBACK)
    return key, agent


def _get(path, key, timeout=20):
    req = urllib.request.Request(EL_BASE + path, headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# persistent detail cache
# ---------------------------------------------------------------------------
def _load_cache():
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    try:
        with open(config.ALYSSA_CALLS_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _detail_cache.update(data)
    except (OSError, ValueError):
        pass


def _save_cache():
    tmp = config.ALYSSA_CALLS_CACHE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_detail_cache, f)
        os.replace(tmp, config.ALYSSA_CALLS_CACHE)
    except OSError as e:
        logger.warning("calls cache save failed: %s", e)


# ---------------------------------------------------------------------------
# enrichment
# ---------------------------------------------------------------------------
def _fetch_detail(conv_id, key):
    """One conversation -> the few fields the page needs (+ transcript)."""
    d = _get(f"/conversations/{conv_id}", key)
    md = d.get("metadata") or {}
    dyn = ((d.get("conversation_initiation_client_data") or {})
           .get("dynamic_variables") or {})
    phone = md.get("phone_call") or {}
    caller = (dyn.get("system__caller_id") or phone.get("external_number")
              or phone.get("caller_id") or "")
    analysis = d.get("analysis") or {}
    transcript = []
    for t in d.get("transcript") or []:
        msg = (t.get("message") or "").strip()
        if not msg:
            continue
        transcript.append({
            "role": t.get("role") or "",
            "secs": t.get("time_in_call_secs"),
            "text": msg,
        })
    return {
        "caller": caller,
        "called_number": dyn.get("system__called_number") or phone.get("agent_number") or "",
        "summary": analysis.get("transcript_summary") or "",
        "transcript": transcript,
        "termination_reason": md.get("termination_reason") or "",
    }


def _enrich(rows, key):
    """Fill caller/summary/transcript for rows not yet in the cache.
    Finished calls (done/failed) stick forever; anything still live is re-pulled."""
    _load_cache()
    missing = [r["conversation_id"] for r in rows
               if r["conversation_id"] not in _detail_cache
               or r["status"] not in ("done", "failed")]
    if missing:
        def work(cid):
            try:
                return cid, _fetch_detail(cid, key)
            except Exception as e:  # noqa: BLE001
                logger.warning("calls detail %s failed: %s", cid, e)
                return cid, None
        with ThreadPoolExecutor(max_workers=6) as ex:
            for cid, det in ex.map(work, missing):
                if det is not None:
                    _detail_cache[cid] = det
        _save_cache()
    for r in rows:
        det = _detail_cache.get(r["conversation_id"]) or {}
        r["caller"] = det.get("caller", "")
        r["summary"] = det.get("summary", "")
        r["termination_reason"] = r.get("termination_reason") or det.get("termination_reason", "")
        r["has_transcript"] = bool(det.get("transcript"))
        r["is_own_number"] = r["caller"] in config.ALYSSA_OWN_NUMBERS
    return rows


def _pull(key, agent):
    rows = []
    cursor = None
    while len(rows) < config.ALYSSA_CALLS_PAGE_SIZE:
        q = f"/conversations?agent_id={agent}&page_size=100"
        if cursor:
            q += f"&cursor={cursor}"
        j = _get(q, key)
        for c in j.get("conversations") or []:
            sent = c.get("sentiment_analysis") or {}
            rows.append({
                "conversation_id": c.get("conversation_id"),
                "start": c.get("start_time_unix_secs"),
                "secs": c.get("call_duration_secs") or 0,
                "status": c.get("status") or "",
                "direction": c.get("direction") or "",
                "source": c.get("conversation_initiation_source") or "",
                "title": c.get("call_summary_title") or "",
                "call_successful": c.get("call_successful") or "",
                "termination_reason": c.get("termination_reason") or "",
                "tools": c.get("tool_names") or [],
                "sentiment": sent.get("overall_label") or "",
                "frustration": sent.get("overall_frustration_score"),
                "messages": c.get("message_count") or 0,
            })
        cursor = j.get("next_cursor")
        if not j.get("has_more") or not cursor:
            break
    rows = rows[:config.ALYSSA_CALLS_PAGE_SIZE]
    return _enrich(rows, key)


def _calls(force=False):
    key, agent = _creds()
    if not key:
        return {"calls": [], "fetched_at": None,
                "error": f"No ElevenLabs key — set ELEVENLABS_API_KEY or put it in {config.ALYSSA_ENV_PATH}"}
    with _lock:
        fresh = time.time() - _list_cache["at"] < config.ALYSSA_CALLS_REFRESH_S
        if fresh and not force and _list_cache["calls"]:
            return {"calls": _list_cache["calls"], "fetched_at": _list_cache["at"],
                    "error": None, "cached": True}
        try:
            rows = _pull(key, agent)
            _list_cache.update(at=time.time(), calls=rows, error=None)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:  # noqa: BLE001
                pass
            _list_cache["error"] = f"ElevenLabs HTTP {e.code}: {body}"
            logger.warning("calls pull failed: %s", _list_cache["error"])
        except Exception as e:  # noqa: BLE001
            _list_cache["error"] = f"ElevenLabs unreachable: {e}"
            logger.warning("calls pull failed: %s", e)
        return {"calls": _list_cache["calls"], "fetched_at": _list_cache["at"] or None,
                "error": _list_cache["error"], "cached": False}


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@calls_api.route("", methods=["GET"])
def list_calls():
    force = request.args.get("refresh") in ("1", "true")
    out = _calls(force=force)
    out["own_numbers"] = config.ALYSSA_OWN_NUMBERS
    return jsonify(out)


@calls_api.route("/<conv_id>", methods=["GET"])
def call_detail(conv_id):
    _load_cache()
    det = _detail_cache.get(conv_id)
    if det is None:
        key, _agent = _creds()
        if not key:
            return jsonify({"error": "no ElevenLabs key"}), 503
        try:
            det = _fetch_detail(conv_id, key)
            _detail_cache[conv_id] = det
            _save_cache()
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 502
    return jsonify({"conversation_id": conv_id, **det})
