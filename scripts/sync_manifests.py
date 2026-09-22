"""
Manifest Sync — WatchTower V2
==============================
Reads MANIFEST.h files from device repos on disk and syncs their
data into the WatchTower SQLite database.

Usage:
    python scripts/sync_manifests.py                    # scan all repos
    python scripts/sync_manifests.py --repo /path/to    # single repo
    python scripts/sync_manifests.py --dry-run          # preview only
    python scripts/sync_manifests.py --list             # show found repos

The script scans REPO_BASE_DIR for any folder containing a MANIFEST.h,
parses the #define values, and calls db.upsert_manifest().

MANIFEST.h expected format (any subset of fields is OK):
    #define DEVICE_NAME        "JungleDoor"
    #define FIRMWARE_VERSION   "v2.1.0"
    #define BOARD_TYPE         "ESP32-S3"
    #define ROOM               "Jungle"
    #define DESCRIPTION        "Motorized sliding door..."
    #define BUILD_STATUS       "compiles"
    #define CODE_HEALTH        "good"
    #define BROKER_IP          "10.1.10.115"
    #define BROKER_PORT        1883
    #define HEARTBEAT_MS       300000
    #define REPO_URL           "https://github.com/AlchemyEscapeRooms/JungleDoor"
    #define KNOWN_QUIRKS       "PWM on pin 5 needs pull-down"
    #define SUBSCRIBE_TOPICS   "MermaidsTale/JungleDoor/command"
    #define PUBLISH_TOPICS     "MermaidsTale/JungleDoor/status,MermaidsTale/JungleDoor/heartbeat"
    #define SUPPORTED_COMMANDS "open,close,stop,reset,ping,status"
    #define PIN_CONFIG         "PWM=5,DIR=4,LIMIT_OPEN=34,LIMIT_CLOSE=35"
    #define COMPONENTS         "A4988,VNH5019"
    #define WATCHTOWER_COMPLIANCE "full"
"""

import sys
import os
import re
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from models import database as db

# =============================================================================
# CONFIGURATION — adjust REPO_BASE_DIR for your M3 setup
# =============================================================================

# Default repo root on M3 — override with --base or REPO_BASE_DIR env var
REPO_BASE_DIR = os.environ.get(
    "REPO_BASE_DIR",
    os.path.expanduser("~/escape-room-repos")   # adjust to your actual path
)

# Fields in MANIFEST.h and their DB column names
FIELD_MAP = {
    "DEVICE_NAME":            "device_name",
    "FIRMWARE_VERSION":       "firmware_version",
    "BOARD_TYPE":             "board_type",
    "ROOM":                   "room",
    "DESCRIPTION":            "description",
    "BUILD_STATUS":           "build_status",
    "CODE_HEALTH":            "code_health",
    "WATCHTOWER_COMPLIANCE":  "watchtower_compliance",
    "BROKER_IP":              "broker_ip",
    "BROKER_PORT":            "broker_port",
    "HEARTBEAT_MS":           "heartbeat_ms",
    "SUBSCRIBE_TOPICS":       "subscribe_topics",
    "PUBLISH_TOPICS":         "publish_topics",
    "SUPPORTED_COMMANDS":     "supported_commands",
    "PIN_CONFIG":             "pin_config",
    "COMPONENTS":             "components",
    "KNOWN_QUIRKS":           "known_quirks",
    "REPO_URL":               "repo_url",
    "OTA_ENABLED":            "ota_enabled",
    "OTA_HOSTNAME":           "ota_hostname",
    "OTA_PORT":               "ota_port",
}

INT_FIELDS = {"broker_port", "heartbeat_ms", "ota_port"}

# =============================================================================
# "Fancy" manifest format (manifest-protocol.md style)
# =============================================================================
# Newer repos (CoveDoor, JungleDoor, WaterFountain, New-Cannons, ...) use a
# comment-tag format instead of flat #defines. Three tag styles:
#
#   1. Header tags — standalone comment lines in the IDENTITY block:
#        // @PROP_NAME:        CoveDoor
#        // @BOARD:            ESP32-DevKitC (regular ESP32)
#
#   2. Trailing tags — a tag naming the value defined on that code line:
#        inline constexpr const char* FIRMWARE_VERSION = "1.3.0"; // @FIRMWARE_VERSION
#        inline constexpr int MQTT_PORT = 1883;                   // @BROKER_PORT
#
#   3. Repeating tags — one line per entry, joined with commas:
#        // @SUBSCRIBE:  MermaidsTale/CoveDoor/command  | description
#        // @COMMAND:    PING                           | description

# Standalone "// @TAG: value" lines
# (some manifests, e.g. CompassTrio, put ALL fields in header form —
#  including the ones that are usually trailing tags on code lines)
FANCY_HEADER_MAP = {
    "PROP_NAME":        "device_name",
    "DEVICE_NAME":      "device_name",
    "DESCRIPTION":      "description",
    "ROOM":             "room",
    "BOARD":            "board_type",
    "REPO":             "repo_url",
    "BUILD_STATUS":     "build_status",
    "CODE_HEALTH":      "code_health",
    "WATCHTOWER":       "watchtower_compliance",
    "FIRMWARE_VERSION": "firmware_version",
    "BROKER_IP":        "broker_ip",
    "BROKER_PORT":      "broker_port",
    "HEARTBEAT_MS":     "heartbeat_ms",
    "OTA_ENABLED":      "ota_enabled",
    "OTA_HOSTNAME":     "ota_hostname",
    "OTA_PORT":         "ota_port",
}

# "// @TAG" trailing a code line; value = string literal or integer in the code
FANCY_TRAILING_MAP = {
    "DEVICE_NAME":      "device_name",
    "FIRMWARE_VERSION": "firmware_version",
    "BROKER_IP":        "broker_ip",
    "BROKER_PORT":      "broker_port",
    "HEARTBEAT_MS":     "heartbeat_ms",
    "TOPIC_PREFIX":     None,   # recognized but not stored
    "OTA_HOSTNAME":     "ota_hostname",
    "OTA_PORT":         "ota_port",
    "OTA_PASSWORD":     None,   # never stored
}

# Repeating "// @TAG: value | description" lines, comma-joined into one column
FANCY_MULTI_MAP = {
    "SUBSCRIBE": "subscribe_topics",
    "PUBLISH":   "publish_topics",
    "COMMAND":   "supported_commands",
}


def parse_fancy_manifest(raw: str) -> dict:
    """Extract @TAG-style fields from a fancy-format MANIFEST.h."""
    data = {}
    multi = {}

    for line in raw.splitlines():
        stripped = line.strip().lstrip("*").strip()

        # Style 1 & 3: standalone comment tag "// @TAG: value"
        m = re.match(r'^//\s*@([A-Z_]+):\s*(.+)$', stripped) or \
            re.match(r'^@([A-Z_]+):\s*(.+)$', stripped)
        if m:
            tag, val = m.group(1), m.group(2).strip()
            if tag in FANCY_MULTI_MAP:
                # keep the value, drop the "| description" tail
                entry = val.split("|")[0].strip()
                if entry:
                    multi.setdefault(FANCY_MULTI_MAP[tag], []).append(entry)
            elif tag in FANCY_HEADER_MAP:
                # first occurrence wins (multi-line descriptions continue untagged)
                data.setdefault(FANCY_HEADER_MAP[tag], val)
            continue

        # Style 2: trailing tag on a code line (tag NOT followed by ":",
        # so "@WIFI:CONNECT_ATTEMPTS"-style sub-keys are ignored)
        m = re.search(r'//\s*@([A-Z_]+)\b(?!:)', line)
        if m and m.group(1) in FANCY_TRAILING_MAP:
            column = FANCY_TRAILING_MAP[m.group(1)]
            if column is None:
                continue
            code = line[:m.start()]
            vm = re.search(r'"([^"]*)"', code)
            if not vm:
                vm = re.search(r'=\s*(\d+)', code)
            if vm:
                # trailing tags label the real firmware constant — they
                # override header tags (e.g. @DEVICE_NAME beats @PROP_NAME)
                data[column] = vm.group(1).strip()

    for column, values in multi.items():
        data[column] = ",".join(values)
    return data


def _version_tuple(version: str) -> tuple:
    """'v1.10.2' -> (1, 10, 2) for comparing duplicate device manifests."""
    return tuple(int(x) for x in re.findall(r"\d+", version or "")) or (0,)


def find_manifests(base_dir: str) -> list[str]:
    """Walk base_dir and return paths to all MANIFEST.h files found."""
    found = []
    if not os.path.isdir(base_dir):
        return found
    for root, dirs, files in os.walk(base_dir):
        # Skip .git and build directories
        dirs[:] = [d for d in dirs if d not in {".git", "build", ".pio", "node_modules"}]
        for fname in files:
            if fname == "MANIFEST.h":
                found.append(os.path.join(root, fname))
    return found


def parse_manifest(path: str) -> dict | None:
    """
    Parse a MANIFEST.h file and return a dict of DB fields.
    Returns None if DEVICE_NAME is not found.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        print(f"  ⚠️  Cannot read {path}: {e}")
        return None

    data = {}

    for macro, column in FIELD_MAP.items():
        # Match:  #define MACRO_NAME   "value"   or   #define MACRO_NAME   123
        pattern = rf'#\s*define\s+{re.escape(macro)}\s+"([^"]*)"'
        m = re.search(pattern, raw)
        if m:
            val = m.group(1).strip()
            data[column] = int(val) if column in INT_FIELDS and val.isdigit() else val
            continue

        # Try unquoted integer
        pattern_int = rf'#\s*define\s+{re.escape(macro)}\s+(\d+)'
        m = re.search(pattern_int, raw)
        if m:
            data[column] = int(m.group(1)) if column in INT_FIELDS else m.group(1)

    # Fancy @TAG format — fills any gaps the flat #define scan left
    for column, val in parse_fancy_manifest(raw).items():
        if column not in data:
            data[column] = int(val) if column in INT_FIELDS and str(val).isdigit() else val

    if "device_name" not in data:
        print(f"  ⚠️  No DEVICE_NAME in {path} — skipping")
        return None
    # OTA is MANDATORY (mqtt-protocol.md, 2026-09-22). The manifest may
    # declare OTA_ENABLED; if it doesn't, look at the firmware next to it
    # for ArduinoOTA so the WatchTower page shows the truth for every board.
    if "ota_enabled" not in data:
        data["ota_enabled"] = "yes" if _source_has_ota(os.path.dirname(path)) else "no"
    data["ota_enabled"] = str(data["ota_enabled"]).strip().lower()
    if data["ota_enabled"] in ("true", "1", "on"):
        data["ota_enabled"] = "yes"
    if data["ota_enabled"] == "yes" and "ota_hostname" not in data:
        data["ota_hostname"] = data["device_name"]
    data["raw_manifest"] = raw[:4000]  # store truncated raw text
    return data


def _source_has_ota(manifest_dir: str) -> bool:
    """True if any .ino/.cpp/.h in the manifest's own repo calls ArduinoOTA.begin().

    Scans from the manifest's folder up to the repo root (first parent that
    holds a .git) and never beyond it - a MANIFEST.h sitting at a repo root
    must not pick up a sibling repo's firmware."""
    repo_root = manifest_dir
    for _ in range(4):
        if os.path.isdir(os.path.join(repo_root, ".git")):
            break
        parent = os.path.dirname(repo_root)
        if parent == repo_root or os.path.isfile(os.path.join(parent, "MANIFEST.h")):
            break
        if any(os.path.isdir(os.path.join(parent, d, ".git"))
               for d in os.listdir(parent) if d != os.path.basename(repo_root)):
            break   # parent is a folder OF repos, not a repo
        repo_root = parent
    roots = [repo_root]
    seen = set()
    for root_dir in roots:
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "build", ".pio", "node_modules"}]
            if root.count(os.sep) - root_dir.count(os.sep) > 3:
                continue
            for fname in files:
                if not fname.endswith((".ino", ".cpp", ".h")):
                    continue
                fpath = os.path.join(root, fname)
                if fpath in seen:
                    continue
                seen.add(fpath)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        if "ArduinoOTA.begin" in f.read():
                            return True
                except OSError:
                    pass
    return False


def sync_manifest(manifest_data: dict, dry_run: bool = False) -> bool:
    name = manifest_data["device_name"]
    if dry_run:
        print(f"  [DRY RUN] Would sync: {name}")
        for k, v in manifest_data.items():
            if k != "raw_manifest":
                print(f"    {k:<28} = {str(v)[:60]}")
        return True
    try:
        db.upsert_manifest(name, manifest_data)
        return True
    except Exception as e:
        print(f"  ❌ DB error for {name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Sync MANIFEST.h files to WatchTower DB")
    parser.add_argument("--base", help="Override repo base directory", default=REPO_BASE_DIR)
    parser.add_argument("--repo", help="Sync a single specific repo directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--list", action="store_true", help="List found MANIFEST.h files and exit")
    args = parser.parse_args()

    db.init_db(config.DATABASE_PATH)

    print()
    print("=" * 62)
    print("  🔄 WatchTower Manifest Sync")
    print("=" * 62)

    if args.dry_run:
        print("  🔍 DRY RUN — no DB writes\n")

    base = args.base
    if args.repo:
        manifests = []
        candidate = os.path.join(args.repo, "MANIFEST.h")
        if os.path.exists(candidate):
            manifests = [candidate]
        else:
            # Search within the given path
            manifests = find_manifests(args.repo)
    else:
        print(f"  Scanning: {base}\n")
        manifests = find_manifests(base)

    if not manifests:
        print(f"  ⚠️  No MANIFEST.h files found under: {base}")
        print()
        print("  Tips:")
        print("  - Set REPO_BASE_DIR env var to your repo root")
        print("  - Or use --base /path/to/repos")
        print("  - Or use --repo /path/to/specific-repo")
        print()
        return

    if args.list:
        print(f"  Found {len(manifests)} MANIFEST.h file(s):\n")
        for m in manifests:
            print(f"  {m}")
        print()
        return

    print(f"  Found {len(manifests)} manifest(s)\n")

    synced = 0
    failed = 0
    skipped_dupes = 0
    seen = {}  # device_name -> (version_tuple, path) of what we already synced

    for manifest_path in manifests:
        repo_name = os.path.basename(os.path.dirname(manifest_path))
        print(f"  📄 {repo_name}")
        print(f"     {manifest_path}")

        data = parse_manifest(manifest_path)
        if data is None:
            failed += 1
            continue

        print(f"     Device: {data['device_name']} | "
              f"FW: {data.get('firmware_version', '?')} | "
              f"Board: {data.get('board_type', '?')}")

        # Duplicate guard: stale clones (e.g. CoveDoor-master) must not
        # clobber the real repo's newer version — keep the highest FW only
        name = data["device_name"]
        version = _version_tuple(data.get("firmware_version"))
        if name in seen and version <= seen[name][0]:
            print(f"     ⏭️  Duplicate of {name} "
                  f"(already have v{'.'.join(map(str, seen[name][0]))} "
                  f"from {seen[name][1]}) — skipping older/equal copy")
            skipped_dupes += 1
            print()
            continue
        seen[name] = (version, manifest_path)

        if sync_manifest(data, dry_run=args.dry_run):
            print(f"     {'[DRY RUN]' if args.dry_run else '✅'} Synced")
            synced += 1
        else:
            failed += 1
        print()

    print("─" * 62)
    print(f"  {'Would sync' if args.dry_run else 'Synced'}: {synced}  |  Failed: {failed}"
          + (f"  |  Duplicates skipped: {skipped_dupes}" if skipped_dupes else ""))
    print()

    if synced > 0 and not args.dry_run:
        print("  ✅ Manifest data is now live in WatchTower.")
        print("  📋 View at: http://10.1.10.115:5000/library → Device Manifests")
    print()


if __name__ == "__main__":
    main()
