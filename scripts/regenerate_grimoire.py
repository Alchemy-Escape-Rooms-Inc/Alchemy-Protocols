#!/usr/bin/env python3
"""
Alchemy Grimoire — Automated Deep Regeneration Script
=====================================================
Clones all Alchemy Escape Rooms repos, extracts code intelligence,
calls the Claude API for deep analysis, and regenerates all dynamic
Grimoire documents. Pushes the updated Grimoire to GitHub.

Requirements:
    pip install anthropic gitpython

Environment Variables (or set in .env file alongside this script):
    ANTHROPIC_API_KEY  — Your Anthropic API key (required)
    GITHUB_PAT         — GitHub Personal Access Token with repo scope (required)
    CLAUDE_MODEL       — Model to use (default: claude-sonnet-4-5-20250929)

Usage:
    python regenerate_grimoire.py              # Full regeneration
    python regenerate_grimoire.py --scan-only  # Just scan, don't regenerate docs
    python regenerate_grimoire.py --dry-run    # Generate docs but don't push to GitHub
"""

import os
import sys
import json
import re
import shutil
import subprocess
import tempfile
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_ORG = "Alchemy-Escape-Rooms-Inc"
GITHUB_LEGACY_USER = "AlchemyEscapeRooms"
GRIMOIRE_REPO = "Alchemy-Protocols"

# Repos to monitor (add new ones here as you create them)
PRIMARY_REPOS = [
    # Ship / Shattic
    "New-Cannons", "Wireless-Motion-Sensor", "Barrel-Piston", "ShipNavMap",
    # Captain's Quarters
    "Compass", "Captains-Cuffs", "CabinDoor",
    # Cove
    "CoveDoor", "Driftwood", "Balancing-Scale", "LuminousShell",
    # Jungle
    "JungleDoor", "MonkeyDoors", "Ruins-Wall-Panel", "Sun-Dial",
    "WaterFountain", "AutomaticSlidingDoor",
    # Cross-room / Systems
    "WatchTower", "Eleven-Labs-Avatar-Project", "BACIntegration",
    "TridentCabinet",
    # Utility / Sensors
    "hall-sensor-with-mqtt",
]

LEGACY_REPOS = [
    "Original_Cannon_Legacy",  # Wrong broker IP, superseded by New-Cannons
]

# Game areas for organizing props
GAME_AREAS = {
    "Ship / Shattic": ["New-Cannons", "Wireless-Motion-Sensor", "Barrel-Piston", "ShipNavMap"],
    "Captain's Quarters": ["Compass", "Captains-Cuffs", "CabinDoor"],
    "Cove": ["CoveDoor", "Driftwood", "Balancing-Scale", "LuminousShell"],
    "Jungle": ["JungleDoor", "MonkeyDoors", "Ruins-Wall-Panel", "Sun-Dial", "WaterFountain", "AutomaticSlidingDoor"],
    "Cross-Room Systems": ["WatchTower", "Eleven-Labs-Avatar-Project", "BACIntegration", "TridentCabinet"],
    "Legacy / Deprecated": ["Original_Cannon_Legacy", "hall-sensor-with-mqtt"],
}

# Documents to regenerate (dynamic ones only)
DYNAMIC_DOCS = [
    "operations-manual.md",
    "network-infrastructure.md",
    "debug-log.md",
    "system-checker-integration.md",
    "wiring-reference.md",
    "code-health-report.md",
    "todo.md",
    "SUMMARY-REPORT.md",
    "README.md",
]

# Static docs — preserved as-is, never overwritten
STATIC_DOCS = [
    "git-migration-guide.md",
    "git-best-practices.md",
]

# Source file extensions to analyze
SOURCE_EXTENSIONS = {".cpp", ".ino", ".h", ".hpp", ".c", ".js", ".ts", ".py"}

# Grep patterns for extracting intelligence
PATTERNS = {
    "pin_definitions": r'#define\s+\w*(?:PIN|GPIO|LED|SERVO|RELAY|BUTTON|SENSOR|MOTOR)\w*\s+\d+|const\s+(?:int|uint8_t)\s+\w*(?:Pin|pin|GPIO)\w*\s*=\s*\d+',
    "mqtt_topics": r'(?:publish|subscribe|client\.(?:publish|subscribe))\s*\(\s*["\']([^"\']+)["\']',
    "broker_ips": r'(?:MQTT_BROKER|broker|mqtt_server|server)\s*[=:]\s*["\']?([\d\.]+)["\']?',
    "wifi_creds": r'(?:ssid|SSID|password|WIFI_PASS|wifi_password)\s*[=:]\s*["\']([^"\']+)["\']',
    "i2c_addresses": r'(?:0x[0-9A-Fa-f]{2})|(?:Wire\.begin\s*\(\s*(\d+)\s*,\s*(\d+)\s*\))',
    "version_strings": r'(?:VERSION|version|FW_VERSION|FIRMWARE)\s*[=:]\s*["\']?([^"\';\s]+)',
    "heartbeat_intervals": r'(?:heartbeat|HEARTBEAT|ping_interval|PING_INTERVAL)\s*[=:]\s*(\d+)',
    "serial_baud": r'Serial\.begin\s*\(\s*(\d+)\s*\)',
    "exposed_secrets": r'(?:api[_-]?key|API[_-]?KEY|secret|SECRET|token|TOKEN)\s*[=:]\s*["\']([^"\']{10,})["\']',
    "todos_fixmes": r'(?:TODO|FIXME|BUG|HACK|XXX|WORKAROUND)\s*[:\-]?\s*(.*)',
    "relay_logic": r'(?:HIGH|LOW)\s*.*(?:relay|RELAY)|(?:relay|RELAY).*(?:HIGH|LOW)',
    "pwm_usage": r'(?:ledcWrite|analogWrite|ledcSetup|ledcAttachPin)\s*\(',
    "spi_usage": r'(?:SPI\.begin|MOSI|MISO|SCK|CS_PIN)',
    "protocol_commands": r'(?:PING|PONG|RESET|PUZZLE_RESET|STATUS|BOOT)',
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("grimoire")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file if present alongside this script."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def clone_repo(org: str, repo: str, dest: str, token: str) -> bool:
    """Clone a repo. Returns True on success."""
    url = f"https://x-access-token:{token}@github.com/{org}/{repo}.git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, os.path.join(dest, repo)],
        capture_output=True, text=True, timeout=120,
    )
    return result.returncode == 0


def read_source_files(repo_path: str) -> dict[str, str]:
    """Read all source files from a repo. Returns {relative_path: content}."""
    sources = {}
    repo = Path(repo_path)
    for ext in SOURCE_EXTENSIONS:
        for f in repo.rglob(f"*{ext}"):
            # Skip build artifacts, libraries, node_modules
            rel = str(f.relative_to(repo))
            if any(skip in rel for skip in [".pio/", "build/", "node_modules/", ".git/", "lib/"]):
                continue
            try:
                content = f.read_text(errors="replace")
                if len(content) < 100_000:  # Skip huge generated files
                    sources[rel] = content
            except Exception:
                pass
    return sources


def extract_patterns(sources: dict[str, str]) -> dict[str, list[dict]]:
    """Extract all intelligence patterns from source files."""
    findings = {name: [] for name in PATTERNS}
    for filepath, content in sources.items():
        for pattern_name, pattern in PATTERNS.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                findings[pattern_name].append({
                    "file": filepath,
                    "match": match.group(0).strip(),
                    "line": content[:match.start()].count("\n") + 1,
                    "groups": [g for g in match.groups() if g] if match.groups() else [],
                })
    return findings


def get_repo_metadata(repo_path: str) -> dict:
    """Get git metadata for a repo."""
    meta = {}
    result = run_git(["log", "-1", "--format=%aI|||%s|||%an"], repo_path)
    if result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split("|||")
        if len(parts) >= 3:
            meta["last_commit_date"] = parts[0]
            meta["last_commit_msg"] = parts[1]
            meta["last_author"] = parts[2]

    result = run_git(["rev-list", "--count", "HEAD"], repo_path)
    if result.returncode == 0:
        meta["commit_count"] = int(result.stdout.strip())

    # Check for key files
    repo = Path(repo_path)
    meta["has_readme"] = any(repo.glob("README*"))
    meta["has_gitignore"] = (repo / ".gitignore").exists()
    meta["has_license"] = any(repo.glob("LICENSE*"))
    meta["has_platformio"] = (repo / "platformio.ini").exists()
    meta["has_main_src"] = (
        (repo / "src" / "main.cpp").exists()
        or (repo / "src" / "main.ino").exists()
        or any((repo / "src").glob("*.ino")) if (repo / "src").exists() else False
    )

    return meta


def check_compilation(repo_path: str) -> dict:
    """Quick compilation check — look for obvious errors without actually compiling."""
    issues = []
    sources = read_source_files(repo_path)

    for filepath, content in sources.items():
        # Check for undefined references (common patterns)
        if "lightPin" in content and "#define lightPin" not in content and "const" not in content.split("lightPin")[0].split("\n")[-1]:
            issues.append(f"{filepath}: 'lightPin' used but never defined")
        if "CGRB" in content and "CRGB" in content:
            issues.append(f"{filepath}: Possible typo 'CGRB' (should be 'CRGB'?)")
        if "SERVO_PIN" in content and "#define SERVO_PIN" not in content:
            if "const" not in content.split("SERVO_PIN")[0].split("\n")[-1]:
                issues.append(f"{filepath}: 'SERVO_PIN' used but never defined")

        # Check for assignment vs comparison bugs
        for match in re.finditer(r'(\w+)\s*==\s*(0|1|true|false|HIGH|LOW)\s*;', content):
            line_num = content[:match.start()].count("\n") + 1
            issues.append(f"{filepath}:{line_num}: Possible bug — '==' used instead of '=' in assignment: {match.group(0)}")

    return {"compilable": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# Claude API Integration
# ---------------------------------------------------------------------------

def call_claude(prompt: str, system_prompt: str, model: str, max_tokens: int = 8192) -> str:
    """Call the Claude API and return the response text."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    log.info(f"  Calling Claude API ({model})...")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    usage = response.usage
    log.info(f"  Tokens: {usage.input_tokens} in, {usage.output_tokens} out")
    return text


SYSTEM_PROMPT = """You are an expert technical writer generating documentation for Alchemy Escape Rooms Inc.,
an escape room business in Fort Lauderdale, FL. The game is called "A Mermaid's Tale" and uses
ESP32/Arduino props connected via MQTT (Mosquitto broker at 10.1.10.115:1883), BAC controllers
managed by BAM software, and the M3 master game control system.

Key facts:
- WiFi SSID: AlchemyGuest, Password: <not stored in Git — see venue credentials record>
- MQTT Broker: 10.1.10.115, Standard Port: 1883, M3 Port: 1860
- Network subnet: 10.1.10.x
- WatchTower is the Python Flask system checker dashboard
- The "Watchtower Protocol" standard requires: WiFi auto-connect, MQTT boot status,
  5-min heartbeat, PING/PONG health check, RESET/PUZZLE_RESET handlers
- Escape Room Techs BAC controllers: Shattic, Captain, Cove, Jungle
- CAISE is the AI game master (ElevenLabs/Node.js) on broker 10.1.10.228
- Standalone devices (no WiFi): CaptainsCuffs, Ruins-Wall-Panel, SunDial, WaterFountain, BalancingScale

Write in clear, practical language. Use markdown formatting with tables where appropriate.
This documentation is used by the owner/developer (Clifford) who works solo and needs
quick reference material, not academic prose. Be specific — include actual pin numbers,
topic names, IP addresses, and code snippets when referencing data."""


def generate_document(doc_name: str, scan_data: dict, model: str) -> str:
    """Generate a single Grimoire document using Claude API."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build doc-specific prompts with relevant data
    if doc_name == "code-health-report.md":
        prompt = build_code_health_prompt(scan_data, timestamp)
    elif doc_name == "wiring-reference.md":
        prompt = build_wiring_reference_prompt(scan_data, timestamp)
    elif doc_name == "debug-log.md":
        prompt = build_debug_log_prompt(scan_data, timestamp)
    elif doc_name == "operations-manual.md":
        prompt = build_operations_manual_prompt(scan_data, timestamp)
        return call_claude(prompt, SYSTEM_PROMPT, model, max_tokens=16384)
    elif doc_name == "network-infrastructure.md":
        prompt = build_network_infra_prompt(scan_data, timestamp)
    elif doc_name == "system-checker-integration.md":
        prompt = build_system_checker_prompt(scan_data, timestamp)
    elif doc_name == "todo.md":
        prompt = build_todo_prompt(scan_data, timestamp)
    elif doc_name == "SUMMARY-REPORT.md":
        prompt = build_summary_report_prompt(scan_data, timestamp)
    elif doc_name == "README.md":
        prompt = build_readme_prompt(scan_data, timestamp)
    else:
        return ""

    return call_claude(prompt, SYSTEM_PROMPT, model, max_tokens=8192)


# ---------------------------------------------------------------------------
# Prompt Builders — one per document
# ---------------------------------------------------------------------------

def _format_repo_data(scan_data: dict, repo_names: list[str] = None) -> str:
    """Format repo scan data for inclusion in prompts."""
    repos = scan_data.get("repos", {})
    if repo_names:
        repos = {k: v for k, v in repos.items() if k in repo_names}

    sections = []
    for name, data in sorted(repos.items()):
        section = f"\n### {name}\n"
        meta = data.get("metadata", {})
        section += f"- Commits: {meta.get('commit_count', '?')}, Last: {meta.get('last_commit_date', '?')}\n"
        section += f"- README: {meta.get('has_readme', False)}, .gitignore: {meta.get('has_gitignore', False)}, PlatformIO: {meta.get('has_platformio', False)}\n"

        # Source code excerpts (trimmed)
        sources = data.get("sources", {})
        if sources:
            main_files = [f for f in sources if "main" in f.lower() or f.endswith(".ino")]
            if not main_files:
                main_files = list(sources.keys())[:2]
            for f in main_files[:2]:
                content = sources[f]
                # Trim to first 300 lines to stay within token limits
                lines = content.split("\n")[:300]
                section += f"\n**{f}** ({len(lines)} lines shown):\n```\n"
                section += "\n".join(lines)
                section += "\n```\n"

        # Pattern findings
        findings = data.get("findings", {})
        for pattern_name in ["pin_definitions", "mqtt_topics", "broker_ips", "wifi_creds",
                             "i2c_addresses", "exposed_secrets", "todos_fixmes"]:
            matches = findings.get(pattern_name, [])
            if matches:
                section += f"\n**{pattern_name}:**\n"
                for m in matches[:15]:
                    section += f"  - `{m['match']}` ({m['file']}:{m['line']})\n"

        # Compilation check
        comp = data.get("compilation", {})
        if comp.get("issues"):
            section += f"\n**Compilation issues:**\n"
            for issue in comp["issues"]:
                section += f"  - {issue}\n"

        sections.append(section)

    return "\n".join(sections)


def build_code_health_prompt(scan_data: dict, timestamp: str) -> str:
    return f"""Generate the code-health-report.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This document should contain:
1. A header noting this was auto-generated with the timestamp
2. A repository overview table with columns: Repo | Type | Board | README | .gitignore | LICENSE | Commits | Last Updated | Health Score (A/B/C/D/F)
3. Broker IP consistency audit — which repos use the correct IP (10.1.10.115) vs wrong ones
4. MQTT topic naming audit — which follow MermaidsTale/ prefix convention
5. Security concerns — any exposed API keys, hardcoded passwords, placeholder credentials
6. Compilation readiness — which repos have obvious code bugs
7. Error handling quality ratings
8. Summary statistics and recommended priority actions

Here is the scan data for all {len(scan_data.get('repos', {}))} repositories:

{_format_repo_data(scan_data)}
"""


def build_wiring_reference_prompt(scan_data: dict, timestamp: str) -> str:
    return f"""Generate the wiring-reference.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This document should contain:
1. A header noting this was auto-generated with the timestamp
2. Pin assignment tables for EVERY device — organized by game area
3. I2C address master registry (every 0x address found across all repos)
4. Relay logic summary table (which devices use Active HIGH vs Active LOW)
5. Voltage & power reference (3.3V vs 5V logic levels)
6. PWM/ADC usage summary
7. SPI bus assignments if any
8. Serial baud rates per device
9. Cable and connector notes
10. Safety warnings

Game areas: {json.dumps(GAME_AREAS, indent=2)}

Here is the scan data with pin definitions and I2C addresses:

{_format_repo_data(scan_data)}
"""


def build_debug_log_prompt(scan_data: dict, timestamp: str) -> str:
    # Collect all compilation issues and TODOs across repos
    all_issues = []
    all_todos = []
    for name, data in scan_data.get("repos", {}).items():
        comp = data.get("compilation", {})
        for issue in comp.get("issues", []):
            all_issues.append(f"[{name}] {issue}")
        for todo in data.get("findings", {}).get("todos_fixmes", []):
            all_todos.append(f"[{name}] {todo['file']}:{todo['line']} — {todo['match']}")

    return f"""Generate the debug-log.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This document should contain:
1. A header noting this was auto-generated with the timestamp
2. A section for RESOLVED issues — include these known-resolved issues from historical records:
   - Dual broker problem (port 1860 vs 1883)
   - IP address conflict (10.1.10.115 vs .114)
   - Mosquitto config missing listeners
   - Windows firewall blocking MQTT
   - mosquitto_sub/pub not in PATH
   - system_checker port mismatch
   - PONG response topic mismatch
   - ESP32 WiFi connection stuck in loop
   - BarrelPiston DeviceInfo wrong topic
   - Door controller PWM stuck at 0V
   - Compass reset not clearing solved status
   - ALS31300 I2C address programming
   - MFRC522 RFID daisy-chain failure
   - ESP-IDF version compatibility
   - system_checker false positives
   - M3 wrong MQTT topic names

3. A section for ACTIVE issues found in the current code scan:
{chr(10).join(all_issues)}

4. TODO/FIXME items found in source code:
{chr(10).join(all_todos[:50])}

5. Three troubleshooting decision trees:
   - "Prop Not Responding" — step by step from physical check to code debug
   - "System Checker False Positive" — how to distinguish real failures from monitoring bugs
   - "MQTT Messages Not Arriving" — network, broker, topic, QoS checklist

6. An event log template for documenting future issues

For each resolved issue, provide: what happened, what the symptoms were, what the root cause was, and how it was fixed.
For each active issue, provide: what's broken, which file/line, severity (CRITICAL/HIGH/MEDIUM/LOW), and suggested fix.

Here is the full code scan data:

{_format_repo_data(scan_data)}
"""


def build_operations_manual_prompt(scan_data: dict, timestamp: str) -> str:
    return f"""Generate the operations-manual.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This is the most important document — the complete hardware and software reference for every prop
in "A Mermaid's Tale" escape room. It should contain:

1. Network & Infrastructure overview (WiFi, MQTT broker, M3, BAM)
2. For EACH prop, organized by game area:
   - Hardware table (board type, sensors, actuators, power requirements)
   - Pin assignment table (GPIO → function)
   - MQTT topics (publish and subscribe)
   - Reset procedure (how to reset the prop manually and via MQTT)
   - Test steps (how to verify the prop is working)
   - Known issues and quirks
3. BAC controller section (Shattic, Captain, Cove, Jungle) — what each controls
4. Cross-room systems (WatchTower, CAISE, M3)
5. Standalone devices section (no WiFi connectivity)
6. Legacy/deprecated devices
7. Quick reference tables at the end

Game areas: {json.dumps(GAME_AREAS, indent=2)}

Here is the complete scan data for all devices:

{_format_repo_data(scan_data)}
"""


def build_network_infra_prompt(scan_data: dict, timestamp: str) -> str:
    # Extract all network-related findings
    all_broker_ips = []
    all_wifi = []
    all_topics = []
    all_heartbeats = []
    for name, data in scan_data.get("repos", {}).items():
        findings = data.get("findings", {})
        for m in findings.get("broker_ips", []):
            all_broker_ips.append(f"[{name}] {m['match']}")
        for m in findings.get("wifi_creds", []):
            all_wifi.append(f"[{name}] {m['match']}")
        for m in findings.get("mqtt_topics", []):
            all_topics.append(f"[{name}] {m['match']}")
        for m in findings.get("heartbeat_intervals", []):
            all_heartbeats.append(f"[{name}] {m['match']}")

    return f"""Generate the network-infrastructure.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This document should contain:
1. Physical network topology (subnet 10.1.10.x, WiFi setup, router/switch details)
2. MQTT Broker setup (Mosquitto on Windows, dual port config: 1883 standard + 1860 M3)
3. All known static IP addresses
4. M3 integration details
5. BAM/BAC integration
6. The Alchemy MQTT Protocol Standard (WiFi connect, MQTT connect, boot status, heartbeat, PING/PONG, RESET/PUZZLE_RESET, STATUS, LWT, message format)
7. Protocol compliance audit table — every device vs every protocol feature
8. Port conflict troubleshooting section
9. Topic naming convention and examples
10. Template for adding new devices to the network

Broker IPs found across repos:
{chr(10).join(all_broker_ips)}

WiFi credentials found:
{chr(10).join(all_wifi)}

MQTT topics found:
{chr(10).join(all_topics[:50])}

Heartbeat intervals:
{chr(10).join(all_heartbeats)}
"""


def build_system_checker_prompt(scan_data: dict, timestamp: str) -> str:
    watchtower_data = scan_data.get("repos", {}).get("WatchTower", {})
    watchtower_sources = watchtower_data.get("sources", {})
    config_json = ""
    for fname, content in watchtower_sources.items():
        if "config" in fname.lower() and fname.endswith(".json"):
            config_json = content
            break

    return f"""Generate the system-checker-integration.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This document should contain:
1. WatchTower architecture overview (3 layers: MQTT subscriber, device tracker, web dashboard)
2. Device inventory from config.json
3. BAC vs ESP32 monitoring differences
4. The "needs_protocol" flag — what it means, which devices have it
5. Devices marked NOT_INSTALLED
6. Known bugs and quirks
7. How to add new devices to WatchTower
8. Recommended improvements
9. Pre-game checklist (7-step verification procedure)
10. Quick reference (device status meanings)

WatchTower config.json:
```json
{config_json}
```

WatchTower source code:
{chr(10).join(f"**{f}:**{chr(10)}```{chr(10)}{c[:500]}{chr(10)}```" for f, c in list(watchtower_sources.items())[:5])}
"""


def build_todo_prompt(scan_data: dict, timestamp: str) -> str:
    # Collect all issues
    critical = []
    important = []
    nice_to_have = []

    for name, data in scan_data.get("repos", {}).items():
        meta = data.get("metadata", {})
        comp = data.get("compilation", {})
        findings = data.get("findings", {})

        # Critical: won't compile or security issues
        if comp.get("issues"):
            critical.append(f"Fix {name}: {'; '.join(comp['issues'][:3])}")
        if findings.get("exposed_secrets"):
            critical.append(f"SECURITY: Rotate exposed keys in {name}")

        # Important: missing protocol compliance, wrong IPs
        broker_ips = [m["match"] for m in findings.get("broker_ips", [])]
        if broker_ips and not any("10.1.10.115" in ip for ip in broker_ips):
            important.append(f"Fix broker IP in {name}: currently {broker_ips[0]}")

        # Nice to have: missing docs
        if not meta.get("has_readme"):
            nice_to_have.append(f"Add README to {name}")
        if not meta.get("has_gitignore"):
            nice_to_have.append(f"Add .gitignore to {name}")

    return f"""Generate the todo.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

Organize into three priority tiers with checkboxes:

## CRITICAL — Game-Day Failures (blocks gameplay)
{chr(10).join(f"- {item}" for item in critical)}

## IMPORTANT — Reliability & Maintainability
{chr(10).join(f"- {item}" for item in important)}
Plus: standardize all devices to Watchtower Protocol, add WiFi+MQTT to standalone devices

## NICE TO HAVE — Professionalism & Scaling
{chr(10).join(f"- {item}" for item in nice_to_have[:20])}

Use markdown checkboxes (- [ ]) for each item. Add brief descriptions of what needs to be done
and why it matters. Group related items together.
"""


def build_summary_report_prompt(scan_data: dict, timestamp: str) -> str:
    repo_count = len(scan_data.get("repos", {}))
    broken = sum(1 for d in scan_data["repos"].values() if d.get("compilation", {}).get("issues"))
    has_secrets = sum(1 for d in scan_data["repos"].values() if d.get("findings", {}).get("exposed_secrets"))

    return f"""Generate the SUMMARY-REPORT.md document for the Alchemy Grimoire.
Auto-generated on {timestamp}.

This is the executive summary. It should contain:
1. Header with generation timestamp
2. Total repos analyzed: {repo_count} ({len(PRIMARY_REPOS)} primary org + {len(LEGACY_REPOS)} legacy)
3. Total devices documented (count from WatchTower config + standalone)
4. Protocol compliance summary (how many devices implement full Watchtower Protocol)
5. Top 10 critical issues ranked by impact
6. Immediate next steps (30 min, 2-3 hours, 2 weeks, ongoing)
7. Key statistics: {broken} repos with compilation issues, {has_secrets} with exposed secrets

Keep this concise — it's a one-page overview for quick scanning.

Repository data summary:
{_format_repo_data(scan_data)}
"""


def build_readme_prompt(scan_data: dict, timestamp: str) -> str:
    repo_count = len(scan_data.get("repos", {}))
    return f"""Generate the README.md for the Alchemy Grimoire repository.
Auto-generated on {timestamp}.

This is the table of contents and entry point. It should contain:
1. Title: "Alchemy Protocols"
2. Subtitle: "Complete Operations Manual for A Mermaid's Tale"
3. Last updated timestamp
4. Table of contents linking to all documents with brief descriptions and approximate line counts
5. Quick links section for common tasks:
   - "Prop not responding?" → debug-log.md
   - "Need pin assignments?" → wiring-reference.md
   - "Setting up a new device?" → operations-manual.md + network-infrastructure.md
   - "Pre-game checklist?" → system-checker-integration.md
   - "Git help?" → git-best-practices.md
6. GitHub org links
7. Note about auto-generation schedule

Documents in the Grimoire: {json.dumps(DYNAMIC_DOCS + STATIC_DOCS)}
Total repos monitored: {repo_count}
GitHub org: https://github.com/{GITHUB_ORG}
"""


# ---------------------------------------------------------------------------
# Main Workflow
# ---------------------------------------------------------------------------

def scan_all_repos(work_dir: str, token: str) -> dict:
    """Clone and scan all repos. Returns comprehensive scan data."""
    scan_data = {"repos": {}, "scan_time": datetime.now(timezone.utc).isoformat()}
    repos_dir = os.path.join(work_dir, "repos")
    os.makedirs(repos_dir, exist_ok=True)

    all_repos = [(GITHUB_ORG, r) for r in PRIMARY_REPOS] + [(GITHUB_LEGACY_USER, r) for r in LEGACY_REPOS]

    for org, repo in all_repos:
        log.info(f"Cloning {org}/{repo}...")
        success = clone_repo(org, repo, repos_dir, token)
        if not success:
            log.warning(f"  Failed to clone {org}/{repo}, skipping")
            continue

        repo_path = os.path.join(repos_dir, repo)
        log.info(f"  Scanning {repo}...")

        sources = read_source_files(repo_path)
        findings = extract_patterns(sources)
        metadata = get_repo_metadata(repo_path)
        compilation = check_compilation(repo_path)

        scan_data["repos"][repo] = {
            "org": org,
            "sources": sources,
            "findings": findings,
            "metadata": metadata,
            "compilation": compilation,
        }

        log.info(f"  {repo}: {len(sources)} source files, {metadata.get('commit_count', '?')} commits, "
                 f"{'BROKEN' if compilation['issues'] else 'OK'}")

    return scan_data


def regenerate_docs(scan_data: dict, grimoire_dir: str, model: str):
    """Regenerate all dynamic Grimoire documents."""
    for doc_name in DYNAMIC_DOCS:
        log.info(f"Generating {doc_name}...")
        try:
            content = generate_document(doc_name, scan_data, model)
            if content:
                doc_path = os.path.join(grimoire_dir, doc_name)
                Path(doc_path).write_text(content, encoding="utf-8")
                lines = content.count("\n") + 1
                log.info(f"  Wrote {doc_name} ({lines} lines)")
            else:
                log.warning(f"  Empty response for {doc_name}, skipping")
        except Exception as e:
            log.error(f"  Failed to generate {doc_name}: {e}")


def push_to_github(grimoire_dir: str, token: str):
    """Commit and push updated Grimoire to GitHub."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    run_git(["config", "user.name", "Grimoire Bot"], grimoire_dir)
    run_git(["config", "user.email", "grimoire-bot@alchemy-escape-rooms.com"], grimoire_dir)
    run_git(["add", "-A"], grimoire_dir)

    # Check if there are changes
    result = run_git(["diff", "--staged", "--quiet"], grimoire_dir)
    if result.returncode == 0:
        log.info("No changes detected — Grimoire is already up to date.")
        return

    run_git(["commit", "-m", f"Auto-regeneration: {timestamp}\n\nFull deep scan of all repos with Claude API analysis."], grimoire_dir)
    result = run_git(["push", "origin", "main"], grimoire_dir)
    if result.returncode == 0:
        log.info("Successfully pushed updated Grimoire to GitHub!")
    else:
        log.error(f"Push failed: {result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Regenerate the Alchemy Grimoire")
    parser.add_argument("--scan-only", action="store_true", help="Scan repos but don't regenerate docs")
    parser.add_argument("--dry-run", action="store_true", help="Generate docs but don't push to GitHub")
    parser.add_argument("--model", default=None, help="Claude model to use")
    parser.add_argument("--output-dir", default=None, help="Output directory for generated docs")
    args = parser.parse_args()

    load_env()

    # Validate environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    github_pat = os.environ.get("GITHUB_PAT")
    model = args.model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    if not api_key:
        log.error("ANTHROPIC_API_KEY not set. Get one at https://console.anthropic.com/")
        sys.exit(1)
    if not github_pat:
        log.error("GITHUB_PAT not set. Create one at https://github.com/settings/tokens")
        sys.exit(1)

    log.info("=" * 60)
    log.info("ALCHEMY GRIMOIRE — Deep Regeneration")
    log.info(f"Model: {model}")
    log.info(f"Repos: {len(PRIMARY_REPOS)} primary + {len(LEGACY_REPOS)} legacy")
    log.info("=" * 60)

    # Create temp working directory
    work_dir = tempfile.mkdtemp(prefix="grimoire_")
    log.info(f"Working directory: {work_dir}")

    try:
        # Step 1: Clone and scan all repos
        log.info("\n[1/4] Scanning all repositories...")
        scan_data = scan_all_repos(work_dir, github_pat)
        log.info(f"Scanned {len(scan_data['repos'])} repos successfully.")

        # Save scan data for debugging
        scan_path = os.path.join(work_dir, "scan_data.json")
        # Remove source code from saved data (too large)
        save_data = {
            "scan_time": scan_data["scan_time"],
            "repos": {
                name: {k: v for k, v in data.items() if k != "sources"}
                for name, data in scan_data["repos"].items()
            }
        }
        Path(scan_path).write_text(json.dumps(save_data, indent=2, default=str))
        log.info(f"Scan data saved to {scan_path}")

        if args.scan_only:
            log.info("--scan-only: Skipping document regeneration.")
            return

        # Step 2: Clone the Grimoire repo
        log.info("\n[2/4] Cloning Grimoire repository...")
        grimoire_dir = os.path.join(work_dir, GRIMOIRE_REPO)
        if args.output_dir:
            grimoire_dir = args.output_dir
            os.makedirs(grimoire_dir, exist_ok=True)
        else:
            clone_repo(GITHUB_ORG, GRIMOIRE_REPO, work_dir, github_pat)

        # Step 3: Regenerate documents
        log.info("\n[3/4] Regenerating Grimoire documents with Claude API...")
        regenerate_docs(scan_data, grimoire_dir, model)

        if args.dry_run:
            log.info(f"--dry-run: Documents saved to {grimoire_dir} but not pushed.")
            return

        # Step 4: Push to GitHub
        log.info("\n[4/4] Pushing to GitHub...")
        push_to_github(grimoire_dir, github_pat)

        log.info("\n" + "=" * 60)
        log.info("GRIMOIRE REGENERATION COMPLETE")
        log.info(f"View at: https://github.com/{GITHUB_ORG}/{GRIMOIRE_REPO}")
        log.info("=" * 60)

    finally:
        # Cleanup temp directory
        if not args.output_dir and not args.dry_run:
            shutil.rmtree(work_dir, ignore_errors=True)
            log.info("Cleaned up temporary files.")
        else:
            log.info(f"Working files preserved at: {work_dir}")


if __name__ == "__main__":
    main()

