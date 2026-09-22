"""
Guardian API Routes
====================
Checklist runs, permission-gated fixes, and the game start/stop gate.
Start is enforced SERVER-SIDE: no fresh passing checklist, no game.
"""

import logging
from flask import Blueprint, jsonify, request

import guardian
from models import database as db

logger = logging.getLogger(__name__)

guardian_api = Blueprint("guardian_api", __name__, url_prefix="/api")


# ─────────────────────────────────────────────
# Checklist
# ─────────────────────────────────────────────

@guardian_api.route("/guardian/run", methods=["POST"])
def run_checklist():
    run = guardian.start_run(trigger=(request.get_json(silent=True) or {}).get("trigger", "manual"))
    return jsonify(run)


@guardian_api.route("/guardian/run/<run_id>")
def get_run(run_id):
    run = guardian.get_run(run_id)
    if not run:
        return jsonify({"error": "unknown run"}), 404
    return jsonify(run)


@guardian_api.route("/guardian/latest")
def latest():
    run = guardian.latest_run()
    return jsonify({"run": run, "history": db.get_guardian_runs(limit=10)})


@guardian_api.route("/guardian/ignore", methods=["POST"])
def ignore_item():
    """Operator override for ignorable items (e.g. props in start position):
    marks the item ignored on THAT run and recomputes the verdict, so a
    fresh-enough run unlocks Start without a re-run."""
    data = request.get_json() or {}
    run_id, item_id = data.get("run_id"), data.get("item_id")
    if not run_id or not item_id:
        return jsonify({"ok": False, "message": "run_id and item_id required"}), 400
    run, message, code = guardian.ignore_item(run_id, item_id)
    return jsonify({"ok": code == 200, "message": message, "run": run}), code


# ─────────────────────────────────────────────
# Bench — props sitting this round out
# ─────────────────────────────────────────────

@guardian_api.route("/guardian/bench", methods=["GET"])
def get_bench():
    """Full prop roster + which props are currently benched."""
    return jsonify(guardian.bench_info())


@guardian_api.route("/guardian/bench", methods=["POST"])
def set_bench():
    """Replace the benched set. Benched props are skipped by the checklist
    (no PING, no start-position row) so the game can start without them.
    The bench auto-clears when a game start fires."""
    data = request.get_json() or {}
    names = data.get("benched")
    if not isinstance(names, list):
        return jsonify({"ok": False, "message": "benched (list of names) required"}), 400
    benched, message, code = guardian.set_benched(names)
    return jsonify({"ok": code == 200, "message": message, "benched": benched}), code


# ─────────────────────────────────────────────
# Fixes — POSTing here IS the operator's approval
# ─────────────────────────────────────────────

@guardian_api.route("/guardian/fix", methods=["POST"])
def apply_fix():
    data = request.get_json() or {}
    fix_id = data.get("fix_id")
    if not fix_id:
        return jsonify({"error": "fix_id required"}), 400
    result = guardian.apply_fix(fix_id)
    return jsonify(result), (200 if result.get("ok") else 500)


# ─────────────────────────────────────────────
# Game control
# ─────────────────────────────────────────────

@guardian_api.route("/game/start", methods=["POST"])
def game_start():
    data = request.get_json() or {}
    ok, message, code = guardian.start_game(data.get("run_id"), data.get("ai_system"))
    return jsonify({"ok": ok, "message": message}), code


@guardian_api.route("/game/stop", methods=["POST"])
def game_stop():
    data = request.get_json() or {}
    if not data.get("confirm"):
        return jsonify({"ok": False, "message": "confirm required"}), 400
    ok, message, code = guardian.stop_game()
    return jsonify({"ok": ok, "message": message}), code


@guardian_api.route("/game/state")
def game_state():
    return jsonify(guardian.game_state())
