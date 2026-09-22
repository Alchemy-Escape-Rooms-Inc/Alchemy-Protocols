"""
WatchTower V2 Database
=======================
SQLite persistence for debug logs, device manifests, and incident history.
"""

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DATABASE_PATH = None


def init_db(db_path):
    """Initialize the database and create tables."""
    global DATABASE_PATH
    DATABASE_PATH = db_path

    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS debug_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                device_name TEXT,
                severity TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                description TEXT,
                resolution TEXT,
                resolved INTEGER NOT NULL DEFAULT 0,
                clickup_task_id TEXT,
                created_by TEXT DEFAULT 'system'
            );

            CREATE TABLE IF NOT EXISTS todo_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                device_name TEXT,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'open',
                due_date TEXT,
                assigned_to TEXT,
                clickup_task_id TEXT,
                clickup_task_url TEXT,
                created_by TEXT DEFAULT 'watchtower'
            );

            CREATE TABLE IF NOT EXISTS device_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT UNIQUE NOT NULL,
                firmware_version TEXT,
                board_type TEXT,
                room TEXT,
                description TEXT,
                build_status TEXT,
                code_health TEXT,
                watchtower_compliance TEXT,
                broker_ip TEXT,
                broker_port INTEGER,
                heartbeat_ms INTEGER,
                subscribe_topics TEXT,
                publish_topics TEXT,
                supported_commands TEXT,
                pin_config TEXT,
                components TEXT,
                operations TEXT,
                known_quirks TEXT,
                wiring_diagram TEXT,
                repo_url TEXT,
                ota_enabled TEXT,
                ota_hostname TEXT,
                ota_port INTEGER,
                last_synced TEXT,
                raw_manifest TEXT
            );

            CREATE TABLE IF NOT EXISTS mqtt_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                direction TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload TEXT,
                device_name TEXT
            );

            CREATE TABLE IF NOT EXISTS game_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                topic TEXT NOT NULL,
                event_name TEXT,
                payload TEXT,
                game_session_id TEXT
            );

            CREATE TABLE IF NOT EXISTS guardian_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                started TEXT NOT NULL,
                finished TEXT,
                verdict TEXT,
                total INTEGER, passed INTEGER, failed INTEGER,
                warned INTEGER, skipped INTEGER,
                results_json TEXT,
                trigger_source TEXT DEFAULT 'manual'
            );

            CREATE TABLE IF NOT EXISTS guardian_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                action TEXT NOT NULL,
                target TEXT,
                ok INTEGER,
                output TEXT,
                run_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_guardian_runs_started ON guardian_runs(started);
            CREATE INDEX IF NOT EXISTS idx_debug_device ON debug_log(device_name);
            CREATE INDEX IF NOT EXISTS idx_debug_resolved ON debug_log(resolved);
            CREATE INDEX IF NOT EXISTS idx_todo_status ON todo_items(status);
            CREATE INDEX IF NOT EXISTS idx_todo_device ON todo_items(device_name);
            CREATE INDEX IF NOT EXISTS idx_mqtt_timestamp ON mqtt_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_manifest_device ON device_manifests(device_name);
        """)
        _ensure_columns(db, "device_manifests", {
            # 2026-09-22: OTA became mandatory (mqtt-protocol.md)
            "ota_enabled":  "TEXT",
            "ota_hostname": "TEXT",
            "ota_port":     "INTEGER",
        })


def _ensure_columns(db, table: str, columns: dict):
    """Add any missing columns to an existing table (CREATE IF NOT EXISTS
    never alters a table that already exists)."""
    have = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ctype in columns.items():
        if name not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ctype}")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================================
# DEBUG LOG OPERATIONS
# =============================================================================

def add_debug_entry(device_name, severity, title, description=None, resolution=None, created_by="system"):
    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO debug_log (device_name, severity, title, description, resolution, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (device_name, severity, title, description, resolution, created_by)
        )
        return cursor.lastrowid


def get_debug_entries(device_name=None, resolved=None, limit=100):
    with get_db() as db:
        query = "SELECT * FROM debug_log WHERE 1=1"
        params = []

        if device_name:
            query += " AND device_name = ?"
            params.append(device_name)
        if resolved is not None:
            query += " AND resolved = ?"
            params.append(int(resolved))

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        return [dict(row) for row in db.execute(query, params).fetchall()]


def resolve_debug_entry(entry_id, resolution=None):
    with get_db() as db:
        db.execute(
            "UPDATE debug_log SET resolved = 1, resolution = ? WHERE id = ?",
            (resolution, entry_id)
        )


# =============================================================================
# TODO OPERATIONS
# =============================================================================

def add_todo(title, device_name=None, description=None, priority="normal",
             due_date=None, assigned_to=None, clickup_task_id=None, clickup_task_url=None):
    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO todo_items
               (title, device_name, description, priority, due_date, assigned_to, clickup_task_id, clickup_task_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, device_name, description, priority, due_date, assigned_to, clickup_task_id, clickup_task_url)
        )
        return cursor.lastrowid


def get_todos(device_name=None, status=None, limit=100):
    with get_db() as db:
        query = "SELECT * FROM todo_items WHERE 1=1"
        params = []

        if device_name:
            query += " AND device_name = ?"
            params.append(device_name)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 END, timestamp DESC LIMIT ?"
        params.append(limit)

        return [dict(row) for row in db.execute(query, params).fetchall()]


def update_todo_status(todo_id, status):
    with get_db() as db:
        db.execute("UPDATE todo_items SET status = ? WHERE id = ?", (status, todo_id))


def update_todo_clickup(todo_id, clickup_task_id, clickup_task_url):
    with get_db() as db:
        db.execute(
            "UPDATE todo_items SET clickup_task_id = ?, clickup_task_url = ? WHERE id = ?",
            (clickup_task_id, clickup_task_url, todo_id)
        )


# =============================================================================
# MANIFEST OPERATIONS
# =============================================================================

def upsert_manifest(device_name, manifest_data):
    with get_db() as db:
        fields = ", ".join(f"{k} = ?" for k in manifest_data.keys())
        values = list(manifest_data.values())

        existing = db.execute(
            "SELECT id FROM device_manifests WHERE device_name = ?", (device_name,)
        ).fetchone()

        if existing:
            db.execute(
                f"UPDATE device_manifests SET {fields}, last_synced = datetime('now', 'localtime') WHERE device_name = ?",
                values + [device_name]
            )
        else:
            manifest_data["device_name"] = device_name
            manifest_data["last_synced"] = datetime.now().isoformat()
            placeholders = ", ".join("?" * len(manifest_data))
            columns = ", ".join(manifest_data.keys())
            db.execute(
                f"INSERT INTO device_manifests ({columns}) VALUES ({placeholders})",
                list(manifest_data.values())
            )


def get_manifest(device_name):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM device_manifests WHERE device_name = ?", (device_name,)
        ).fetchone()
        return dict(row) if row else None


def get_all_manifests():
    with get_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM device_manifests ORDER BY device_name").fetchall()]


# =============================================================================
# GUARDIAN OPERATIONS
# =============================================================================

def add_guardian_run(run_id, started, finished, verdict, counts, results_json, trigger_source="manual"):
    with get_db() as db:
        db.execute(
            """INSERT OR REPLACE INTO guardian_runs
               (run_id, started, finished, verdict, total, passed, failed, warned, skipped, results_json, trigger_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, started, finished, verdict,
             counts.get("total", 0), counts.get("pass", 0), counts.get("fail", 0),
             counts.get("warn", 0), counts.get("skip", 0), results_json, trigger_source)
        )


def get_guardian_runs(limit=20):
    with get_db() as db:
        return [dict(row) for row in db.execute(
            "SELECT run_id, started, finished, verdict, total, passed, failed, warned, skipped, trigger_source "
            "FROM guardian_runs ORDER BY started DESC LIMIT ?", (limit,)
        ).fetchall()]


def add_guardian_action(action, target=None, ok=None, output=None, run_id=None):
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO guardian_actions (action, target, ok, output, run_id) VALUES (?, ?, ?, ?, ?)",
            (action, target, None if ok is None else int(ok), output, run_id)
        )
        return cursor.lastrowid


def get_guardian_actions(limit=50):
    with get_db() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM guardian_actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]


def has_open_debug_entry(title):
    """True if an unresolved debug_log entry with this exact title exists
    (used by Guardian to avoid re-logging the same failure every run)."""
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM debug_log WHERE title = ? AND resolved = 0 LIMIT 1", (title,)
        ).fetchone()
        return row is not None


# =============================================================================
# MQTT LOG OPERATIONS
# =============================================================================

def log_mqtt_message(direction, topic, payload, device_name=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO mqtt_log (direction, topic, payload, device_name) VALUES (?, ?, ?, ?)",
            (direction, topic, payload[:500] if payload else "", device_name)
        )
        # Trim old messages - keep last 5000
        db.execute("""
            DELETE FROM mqtt_log WHERE id NOT IN (
                SELECT id FROM mqtt_log ORDER BY id DESC LIMIT 5000
            )
        """)


def get_mqtt_log(limit=100, device_name=None):
    with get_db() as db:
        query = "SELECT * FROM mqtt_log"
        params = []

        if device_name:
            query += " WHERE device_name = ?"
            params.append(device_name)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        return [dict(row) for row in db.execute(query, params).fetchall()]
