#!/usr/bin/env python3
"""
WatchTower V2 — Alchemy Escape Room Monitoring & Operations Dashboard
======================================================================
Integrates device monitoring (WatchTower) with documentation (Grimoire)
and task management (ClickUp) in a single interface.

Author: Built for Alchemy Escape Rooms Inc.
"""

import os
import subprocess
import sys
import time
import threading
import logging
from datetime import datetime

# Force UTF-8 console output so emoji banners/status lines don't crash on the
# Windows cp1252 console (UnicodeEncodeError). No-op where already UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 - never let console encoding block launch
    pass

from flask import Flask

import config
import guardian
from models.database import init_db
from mqtt import MQTTClient
from routes.api import api, set_mqtt_client
from routes.chat_api import chat_api, init_chat
from routes.guardian_api import guardian_api
from routes.pages import pages
from routes.plugs_api import plugs_api
from routes.say_api import say_api, set_mqtt_client as say_set_mqtt_client
from routes.direct_api import direct_api, set_mqtt_client as direct_set_mqtt_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ── Version stamp (2026-08-18) ──────────────────────────────────────────────
# WatchTower deploys straight from the git repo, so the commit IS the version.
# Computed once at process boot and shown in the nav bar on every page — the
# fast way to confirm a restart actually picked up new code (and from WHICH
# checkout: the retired OneDrive copy that can hijack :5000 shows "no-git").
def _build_version() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    ver = {"commit": "no-git", "commit_date": "", "branch": "",
           "booted": datetime.now().strftime("%m-%d %H:%M")}
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h|%cd|%s", "--date=format:%m-%d %H:%M"],
            cwd=here, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            commit, cdate, subject = out.stdout.strip().split("|", 2)
            # Commit subjects authored via -F files can carry a UTF-8 BOM.
            ver.update(commit=commit, commit_date=cdate,
                       subject=subject.lstrip("﻿"))
        br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=here, capture_output=True, text=True, timeout=5)
        if br.returncode == 0:
            ver["branch"] = br.stdout.strip()
    except Exception:  # noqa: BLE001 - version display must never block launch
        pass
    return ver


WT_VERSION = _build_version()


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # Version stamp available to every template (base.html nav bar).
    @app.context_processor
    def inject_version():
        return {"wt_version": WT_VERSION}

    # Register blueprints
    app.register_blueprint(api)
    app.register_blueprint(guardian_api)
    app.register_blueprint(chat_api)
    app.register_blueprint(pages)
    app.register_blueprint(plugs_api)
    app.register_blueprint(say_api)   # Talk to the Players (/api/say)
    app.register_blueprint(direct_api)  # Direct the Character (/api/direct)

    # Disable caching for development
    @app.after_request
    def add_no_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app


def run_timeout_checker(mqtt_client):
    """Background thread to check for ping timeouts."""
    while True:
        mqtt_client.check_timeouts()
        time.sleep(0.5)


def main():
    print()
    print("=" * 60)
    print("  ⚗️  WatchTower V2 — Alchemy Escape Rooms")
    print("  📖  Grimoire Operations Dashboard")
    print("=" * 60)
    print()

    # Single-instance guard BEFORE the PID file is touched. A second app.py
    # would die on the port bind anyway, but not before overwriting
    # watchtower.pid with its own (soon-dead) PID — and then the START/STOP
    # bats' spare-WatchTower logic would protect the wrong PID and kill the
    # REAL WatchTower. Probe the port first and bow out without side effects.
    import socket as _socket
    try:
        with _socket.create_connection(("127.0.0.1", config.FLASK_PORT), timeout=2):
            already = True
    except OSError:
        already = False
    if already:
        print(f"WatchTower is already running on port {config.FLASK_PORT} — not starting a second copy.")
        print(f"Dashboard: http://localhost:{config.FLASK_PORT}/game")
        return

    # PID file first: the START/STOP bats blanket-kill python.exe but spare
    # this PID, so WatchTower survives pressing its own Start/Stop buttons.
    guardian.write_pid_file()

    # Initialize database
    init_db(config.DATABASE_PATH)
    logger.info(f"Database initialized at {config.DATABASE_PATH}")

    # Initialize MQTT
    mqtt_client = MQTTClient()
    if not mqtt_client.connect():
        print(f"⚠️  Could not connect to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")
        print(f"   Dashboard will work but device status won't update.")
    else:
        print(f"✓  Connected to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")

    # Wire MQTT client into API routes + Guardian
    set_mqtt_client(mqtt_client)
    say_set_mqtt_client(mqtt_client)
    direct_set_mqtt_client(mqtt_client)
    guardian.init(mqtt_client)
    init_chat(mqtt_client)

    # Start timeout checker
    timeout_thread = threading.Thread(target=run_timeout_checker, args=(mqtt_client,), daemon=True)
    timeout_thread.start()

    # 24/7 retained-command watchdog: erases poison retained /command, /reset,
    # /maglock messages even when the AI stack (and its in-session sweeper)
    # is down. See mqtt/retained_watchdog.py for the 2026-08-08 incident.
    try:
        from mqtt.retained_watchdog import watchdog as retained_watchdog
        retained_watchdog.start()
    except Exception as e:  # noqa: BLE001 - watchdog must never block launch
        logger.warning(f"Retained watchdog failed to start: {e}")

    # 24/7 health sentinel: proactive findings (dead sensors, silent boards,
    # WiFi flapping, dead AI launcher…) + the morning Daily Report. Born
    # 2026-08-08 when Cannon1's load sensor screamed FAIL all day unnoticed.
    try:
        import health_sentinel
        health_sentinel.start(mqtt_client)
    except Exception as e:  # noqa: BLE001 - sentinel must never block launch
        logger.warning(f"Health sentinel failed to start: {e}")

    # Start the live Pirate Ship mic probe (opens the same device Red Beard
    # hears through and measures its input level for the dashboard mic tile).
    try:
        from mic_probe import probe as mic_probe
        mic_probe.start()
        logger.info("Mic probe started")
    except Exception as e:  # noqa: BLE001 - mic probe must never block launch
        logger.warning(f"Mic probe failed to start: {e}")

    # Alexa smart-plug manager (Power page). Restores the saved Amazon session
    # in the background; if none exists the page just shows the Link button.
    try:
        from alexa_plugs import manager as plugs_manager
        plugs_manager.start()
        logger.info("Alexa plugs manager started")
    except Exception as e:  # noqa: BLE001 - plug control must never block launch
        logger.warning(f"Alexa plugs manager failed to start: {e}")

    # Create Flask app
    app = create_app()

    print()
    print(f"🌐  Dashboard: http://localhost:{config.FLASK_PORT}")
    print(f"📡  Devices: {len(mqtt_client.devices)} registered")
    print(f"📋  ClickUp List: {config.CLICKUP_LIST_ID}")
    print()
    print("Press Ctrl+C to stop")
    print()

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
