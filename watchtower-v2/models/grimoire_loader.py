"""
Grimoire Loader
===============
Reads markdown files from the grimoire/ directory and renders them to HTML.
When live manifest data exists for a device, it takes priority over static content.
"""

import os
import re
import markdown
from datetime import datetime

# The grimoire markdown files (operations-manual.md, wiring-reference.md, etc.)
# live at the REPO ROOT (Alchemy-Grimoire/), which is two levels up from this
# file (models/ -> watchtower-v2/ -> repo root). The old path pointed at a
# non-existent watchtower-v2/grimoire/ subdir, which broke the entire Library.
GRIMOIRE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MD_EXTENSIONS = [
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
    "markdown.extensions.nl2br",
    "markdown.extensions.toc",
]


def _render(filename: str) -> str:
    """Read a markdown file and render it to HTML."""
    path = os.path.join(GRIMOIRE_DIR, filename)
    if not os.path.exists(path):
        return f'<p class="grimoire-missing">⚠️ Document not found: {filename}</p>'
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return markdown.markdown(text, extensions=MD_EXTENSIONS)


def get_operations_manual() -> str:
    return _render("operations-manual.md")


def get_wiring_reference() -> str:
    return _render("wiring-reference.md")


def get_network_infrastructure() -> str:
    return _render("network-infrastructure.md")


def get_mqtt_protocol() -> str:
    """The authoritative MQTT / device protocol standard (mqtt-protocol.md),
    shown under Library > Network & MQTT. OTA became mandatory 2026-09-22."""
    return _render("mqtt-protocol.md")


def get_debug_history() -> str:
    return _render("debug-log.md")


def get_code_health() -> str:
    return _render("code-health-report.md")


def get_system_checker_doc() -> str:
    return _render("system-checker-integration.md")


def get_all_sections() -> dict:
    """Return all grimoire sections as rendered HTML. Used by the library page."""
    return {
        "operations": get_operations_manual(),
        "wiring": get_wiring_reference(),
        "network": get_network_infrastructure(),
        "mqtt_protocol": get_mqtt_protocol(),
        "debug_history": get_debug_history(),
        "code_health": get_code_health(),
        "watchtower_doc": get_system_checker_doc(),
    }


# =============================================================================
# SEEDER — parse markdown and extract structured data for SQLite
# =============================================================================

def parse_todo_md() -> list[dict]:
    """
    Parse todo.md and extract all TODO items as structured dicts.
    Returns list of {title, description, priority, device_name}
    """
    path = os.path.join(GRIMOIRE_DIR, "todo.md")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    todos = []
    current_priority = "normal"

    # Map section headers to priority levels
    priority_map = {
        "CRITICAL": "urgent",
        "IMPORTANT": "high",
        "NICE TO HAVE": "low",
    }

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect priority section
        for key, val in priority_map.items():
            if key in line and ("##" in line or "###" in line):
                current_priority = val
                break

        # Detect checkbox items
        if line.startswith("- [ ]") or line.startswith("- [x]"):
            title = re.sub(r"^- \[[ x]\]\s*\*?\*?", "", line).strip()
            title = re.sub(r"\*?\*?$", "", title).strip()

            if not title or len(title) < 3:
                i += 1
                continue

            # Look for device name in bold after the title
            device_name = None
            description_lines = []

            # Scan next lines for sub-items and repo references
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line.startswith("- [ ]") or next_line.startswith("- [x]"):
                    if not next_line.startswith("  ") and not next_line.startswith("\t"):
                        break
                    sub = re.sub(r"^\s*- \[[ x]\]\s*", "", next_line).strip()
                    description_lines.append(sub)
                elif next_line.startswith("**Repo:**"):
                    pass  # skip
                elif next_line.startswith("**File:**"):
                    pass
                elif next_line.startswith("**Severity:**"):
                    pass
                elif next_line == "" and j > i + 3:
                    break
                j += 1

            # Try to extract device name from title patterns
            device_patterns = [
                r"(LuminousShell|ShipNavMap|Balancing.Scale|Sun.Dial|CabinDoor|JungleDoor|"
                r"Original.Cannon|BarrelPiston|CoveSlidingDoor|JungleDoor|Eleven.Labs|"
                r"Compass|Driftwood|Cannon|WaterFountain|CaptainsCuffs|Ruins.Wall|"
                r"WatchTower|AutomaticSlidingDoor|Wireless.Motion)"
            ]
            for pattern in device_patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    device_name = match.group(1)
                    break

            description = "\n".join(description_lines) if description_lines else None

            todos.append({
                "title": title,
                "description": description,
                "priority": current_priority,
                "device_name": device_name,
            })

        i += 1

    return todos


def parse_debug_log_md() -> list[dict]:
    """
    Parse debug-log.md and extract documented issues as structured dicts.
    Returns list of {title, description, resolution, severity, device_name, resolved}
    """
    path = os.path.join(GRIMOIRE_DIR, "debug-log.md")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    issues = []

    # Split on issue headers (## Issue N or ### Issue or ## ISSUE)
    # The debug log uses sections like "## Issue 1: Title" or "### Title"
    sections = re.split(r'\n(?=#{1,3}\s+(?:Issue|ISSUE|\d+\.|\*\*))', content)

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split("\n")
        if not lines:
            continue

        header = lines[0].strip()
        # Skip table of contents, main headers
        if header.startswith("# ") or "Table of Contents" in header or "Troubleshooting" in header:
            continue

        # Extract title from header
        title = re.sub(r'^#{1,3}\s+', '', header).strip()
        title = re.sub(r'^\d+\.\s+', '', title).strip()
        if not title or len(title) < 5:
            continue

        body = "\n".join(lines[1:])

        # Determine if resolved
        resolved = bool(re.search(r'(?:Resolved|RESOLVED|✅|Fixed|fixed)', body))

        # Extract severity
        severity = "info"
        if re.search(r'(?:CRITICAL|critical|🔴)', body, re.IGNORECASE):
            severity = "critical"
        elif re.search(r'(?:WARNING|warning|⚠️|MEDIUM)', body, re.IGNORECASE):
            severity = "warning"

        # Extract device name
        device_name = None
        device_match = re.search(
            r'(?:Device|Prop|Repo|device):\s*\*?\*?([A-Za-z][A-Za-z0-9\-_]+)\*?\*?',
            body
        )
        if device_match:
            device_name = device_match.group(1)
        else:
            # Try to find device name in title
            known_devices = [
                "LuminousShell", "ShipNavMap", "BalancingScale", "SunDial",
                "CabinDoor", "JungleDoor", "BarrelPiston", "Compass", "Driftwood",
                "Cannon", "WaterFountain", "CaptainsCuffs", "RuinsWallPanel",
                "WatchTower", "Wireless"
            ]
            for dev in known_devices:
                if dev.lower() in title.lower():
                    device_name = dev
                    break

        # Extract resolution if present
        resolution = None
        res_match = re.search(r'(?:Resolution|Fix|Solution|Fixed by)[:\s]+(.+?)(?:\n\n|\Z)', body, re.DOTALL | re.IGNORECASE)
        if res_match:
            resolution = res_match.group(1).strip()[:500]

        description = body[:1000].strip() if body.strip() else None

        issues.append({
            "title": title[:200],
            "description": description,
            "resolution": resolution,
            "severity": severity,
            "device_name": device_name,
            "resolved": resolved,
            "created_by": "grimoire_import",
        })

    return issues


# =============================================================================
# DEVICE INDEX — parse ops manual into individual device sections
# =============================================================================

import re as _re

ROOM_ICONS = {
    "SHIP": "⚓", "SHATTIC": "⚓",
    "CAPTAIN": "🧭", "CABIN": "🧭",
    "COVE": "🐚",
    "JUNGLE": "🌿",
    "CROSS": "🔗",
    "STANDALONE": "🔌",
    "LEGACY": "📦",
    "WATCHTOWER": "📡",
}

def _room_icon(room: str) -> str:
    for key, icon in ROOM_ICONS.items():
        if key in room.upper():
            return icon
    return "📍"

def get_device_index() -> list:
    path = os.path.join(GRIMOIRE_DIR, "operations-manual.md")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    devices = []
    current_room = "General"
    i = 0

    SKIP_ROOMS = {"TABLE OF CONTENTS", "QUICK REFERENCE", "APPENDIX", "REVISION", "KNOWN ISSUES"}
    SKIP_SECTIONS = {"Overview", "Overview Table", "Compilation", "Logic Errors",
                     "Protocol", "Ambiguous", "Device Health", "MQTT Broker",
                     "WiFi Network", "Serial", "Common Commands", "Firmware"}

    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("## ") and not line.startswith("### "):
            room_name = line[3:].strip()
            if not any(s in room_name.upper() for s in SKIP_ROOMS):
                current_room = room_name.title()
            i += 1
            continue

        if line.startswith("### "):
            section_title = line[4:].strip()
            if any(section_title.startswith(s) for s in SKIP_SECTIONS):
                i += 1
                continue

            m = _re.match(r'^(\d+)\.\s+([A-Z][A-Z0-9\-]+)(.*)', section_title)
            if not m:
                i += 1
                continue

            num = int(m.group(1))
            device_key = m.group(2)
            suffix = m.group(3).strip()
            display_name = device_key.replace("-", " ").title()
            aliases = suffix.strip("()") if suffix.startswith("(") else ""

            description = ""
            j = i + 1
            in_desc = False
            while j < min(i + 40, len(lines)):
                l = lines[j].rstrip()
                if "**Description:**" in l:
                    in_desc = True
                elif in_desc and l.strip() and not l.startswith("#") and not l.startswith("|") and not l.startswith("**") and not l.startswith("-"):
                    description = l.strip()
                    break
                j += 1

            slug = device_key.lower()
            devices.append({
                "num": num,
                "slug": slug,
                "key": device_key,
                "name": display_name,
                "aliases": aliases,
                "room": current_room,
                "room_icon": _room_icon(current_room),
                "description": description,
            })

        i += 1

    return devices


def get_device_section(slug: str):
    path = os.path.join(GRIMOIRE_DIR, "operations-manual.md")
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    slug_upper = slug.upper()
    start_line = None
    device_title = ""
    current_room = "General"

    for i, line in enumerate(lines):
        if line.startswith("## ") and not line.startswith("### "):
            current_room = line[3:].strip().title()
        if line.startswith("### "):
            pattern = r'^\#\#\# \d+\.\s+' + _re.escape(slug_upper)
            if _re.match(pattern, line, _re.IGNORECASE):
                start_line = i
                device_title = line[4:].strip()
                break

    if start_line is None:
        return None

    section_lines = []
    for i, line in enumerate(lines):
        if i < start_line:
            continue
        if i > start_line and (line.startswith("### ") or line.startswith("## ")):
            break
        section_lines.append(line)

    html = markdown.markdown("\n".join(section_lines), extensions=MD_EXTENSIONS)

    alias_match = _re.search(r'\(([^)]+)\)', device_title)
    aliases = alias_match.group(1) if alias_match else ""
    wiring_html = _get_wiring_section(slug_upper)

    return {
        "slug": slug,
        "name": slug_upper.replace("-", " ").title(),
        "room": current_room,
        "aliases": aliases,
        "html": html,
        "wiring_html": wiring_html,
    }


def _get_wiring_section(device_key: str) -> str:
    path = os.path.join(GRIMOIRE_DIR, "wiring-reference.md")
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    start_line = None

    for i, line in enumerate(lines):
        if device_key.lower() in line.lower() and (line.startswith("## ") or line.startswith("### ")):
            start_line = i
            break

    if start_line is None:
        return ""

    section_lines = []
    for i, line in enumerate(lines):
        if i < start_line:
            continue
        if i > start_line and (line.startswith("### ") or line.startswith("## ")):
            break
        section_lines.append(line)

    return markdown.markdown("\n".join(section_lines), extensions=MD_EXTENSIONS) if section_lines else ""
