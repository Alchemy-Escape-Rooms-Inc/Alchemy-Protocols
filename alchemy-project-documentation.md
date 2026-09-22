# Alchemy Escape Rooms — WatchTower, Grimoire & Firmware Manifest System
## Complete Project Documentation

**Company:** Alchemy Escape Rooms Inc., Fort Lauderdale, Florida
**Owner/Operator:** Clifford (goes by Joshua in some systems)
**First Game:** "A Mermaid's Tale" — Target opening November 27, 2026
**Documentation Date:** February 14, 2026
**Status:** Pre-opening build phase, approximately 62% complete

---

## TABLE OF CONTENTS

1. System Overview
2. WatchTower V1 — The Original System Checker
3. WatchTower V2 — The Rebuild with Alchemy Branding
4. The Grimoire — Reference Library Integration
5. The Self-Documenting Firmware Manifest System
6. The Hybrid Manifest Architecture (Final Design)
7. Manifest File Specifications
8. Repos Completed So Far
9. Alchemy MQTT Protocol Standard
10. Network Infrastructure
11. Known Issues & Quirks Registry
12. File Locations & Project Structure
13. Glossary of Alchemy-Specific Terms

---

## 1. SYSTEM OVERVIEW

Alchemy Escape Rooms runs a complex IoT infrastructure for their escape room "A Mermaid's Tale." The room uses approximately 29 ESP32 microcontrollers and 4 BAC (Bose/show-control) controllers, all communicating over MQTT via a broker at `10.1.10.115:1883` on the `AlchemyGuest` WiFi network.

The technology stack has three layers:

**Layer 1 — WatchTower:** A Python/Flask web dashboard that monitors all devices in real-time. It sends PING commands via MQTT and tracks which devices respond (PONG). It runs on an M3 machine and serves a web UI at `http://localhost:5000`. This is the "is everything working right now?" tool.

**Layer 2 — The Grimoire:** A reference library integrated into WatchTower that provides detailed documentation for every device — pin assignments, wiring diagrams, reset procedures, troubleshooting steps, and operational notes. This is the "how do I fix this thing?" tool.

**Layer 3 — Firmware Manifests:** A system where every device's firmware carries its own documentation as a structured header file (`MANIFEST.h`). This is the single source of truth — the code describes itself, and all documentation downstream reads from it. This is the "the code IS the documentation" architecture.

The key insight that drives the entire system: **documentation should never be a separate task from engineering.** When an engineer changes a pin assignment in the code, the documentation updates automatically because the documentation IS the code.

---

## 2. WATCHTOWER V1 — THE ORIGINAL SYSTEM CHECKER

**File:** `system_checker.py` (1,841 lines)
**Config:** `config.json`
**Launcher:** `run_checker.bat`
**Dependencies:** `paho-mqtt`, `flask`

WatchTower V1 is a single-file Python application that:

- Connects to the MQTT broker at `10.1.10.115:1883`
- Loads device configuration from `config.json` (29 ESP32 devices + 4 BAC controllers)
- Sends PING commands to ESP32 devices on `MermaidsTale/{DeviceName}/command`
- Listens for PONG responses on both `/command` and `/status` topics
- Monitors BAC controllers passively via heartbeat messages on `{name}/get/heartbeat`
- Serves a card-based dashboard UI with:
  - Device cards that flip to reveal command buttons (PING, STATUS, RESET, PUZZLE_RESET)
  - Color-coded status indicators (green=online, red=offline, grey=untested, blue=testing)
  - A live MQTT message log panel (dark terminal-style, sticky at top)
  - Drag-and-drop card reordering (saved to localStorage)
  - Status bar showing counts of online/offline/unknown devices
- Has smart message filtering: echo suppression, delta thresholds for sensor data, heartbeat hiding, duplicate deduplication
- Timeout handling: 3 seconds for ESP32 (fast PING/PONG), 15 seconds for BAC (waits for heartbeat cycle)

**Key Technical Details:**
- ESP32 topic pattern: `MermaidsTale/{DeviceName}/command` (subscribe), responds PONG
- BAC topic pattern: `{ControllerName}/get/heartbeat` (passive monitoring)
- API endpoints: `/api/status`, `/api/ping/<device>`, `/api/ping-all`, `/api/command/<device>/<command>`, `/api/messages`
- The MQTT client subscribes to `#` (wildcard) for the live message panel

**Known Issues in V1:**
- PONG response location is inconsistent across devices — some respond on `/command`, some on `/status`
- The stack corruption bug documented in `MQTT_PING_PONG_FIX_NOTES.txt`: the `mqtt_callback` function in some firmware would corrupt the `topic` pointer when publishing PONG because PubSubClient reuses an internal buffer. Fix was to copy the topic to a local buffer before publishing.

---

## 3. WATCHTOWER V2 — THE REBUILD WITH ALCHEMY BRANDING

WatchTower V2 was a complete rebuild that:

- Integrated Alchemy brand colors and logo
- Added SQLite persistence for incident history
- Added the Grimoire reference library as integrated tabs
- Added live incident feeds with pattern detection
- Added health badges on device cards
- Restructured the codebase into proper Flask templates instead of a single inline HTML string
- Added the concept of device registry cards that combine live status with reference documentation

**Brand Colors Extracted from Logo:**
- Primary Gold: `#C4A265`
- Deep Navy: `#1B2B4B`
- Cream: `#F5F0E8`
- Accent Teal: `#45B7AA`

**Architecture:**
- Python backend with Flask
- SQLite database for persistence
- HTML templates with Jinja2
- MQTT integration via paho-mqtt
- Deployed on M3 machine

---

## 4. THE GRIMOIRE — REFERENCE LIBRARY INTEGRATION

The Grimoire is the documentation layer that was integrated into WatchTower V2. It was designed to answer the question: "It's 6 PM on a Friday, something is broken — how do I fix it?"

**Content Organization (Two Buckets):**

**Bucket 1 — Library Content ("look it up when you need it"):**
- Operations Manual — every prop with hardware specs, pin assignments, reset procedures, test steps
- Wiring Reference — pin tables, I2C registries, relay logic, voltage levels
- Network Infrastructure — broker setup, IP addresses, port configuration
- MQTT Protocol Reference — topic patterns, command standards

**Bucket 2 — Live Content ("what's happening right now"):**
- Debug Log — live incident tracking + historically documented issues (24 known issues with resolutions)
- TODO List — 47 prioritized items (8 critical, 15 important, 24 nice-to-have)
- Code Health Report — repo-level audit data (26 of 31 repos missing READMEs)

**Key Design Decisions:**
- Library content stays as markdown files that WatchTower reads and renders (Option C — Hybrid approach)
- Live content lives in SQLite with persistence and queryability
- The device name is the universal key that connects everything — click a device name anywhere and you can reach all data about that device from every source
- Connections between layers: Debug Log links to Operations Manual sections, Device Registry links to Wiring Reference, TODO items tagged to specific devices

**The Critical Gap That Led to Manifests:**
The original Grimoire was populated from 11 standalone markdown documentation files. But these files were already going stale — they required manual updates whenever hardware or code changed. The question became: how do you keep documentation in sync with code automatically? This led directly to the manifest concept.

---

## 5. THE SELF-DOCUMENTING FIRMWARE MANIFEST SYSTEM

### The Core Concept

Instead of having a smart script that hunts through messy code trying to figure out what a device does, **make the code describe itself.** Every prop's firmware carries a standardized block of metadata declaring everything about itself. The Grimoire doesn't need to be clever about parsing — it just reads the fields.

**Analogy:** A shipping label on a box. You don't open the box to know what's inside — the label tells you. Right now the firmware files are boxes with no labels. The manifest IS the label.

### What the Manifest Declares

Every firmware manifest contains these sections:

1. **Identity** — Device name, description, room/zone, board type, firmware version, repo URL, build status, code health rating, WatchTower compliance
2. **Network Configuration** — WiFi SSID/password, broker IP/port, MQTT topics (subscribe + publish), supported commands, heartbeat interval
3. **Pin Configuration** — Every physical pin with number, purpose, and direction (INPUT/OUTPUT/PWM/I2C/ANALOG)
4. **Motor/Sensor Configuration** — PWM settings, speed values, thresholds, calibration data
5. **Timing Constants** — Heartbeat intervals, reconnect timers, debounce periods
6. **Components** — List of major hardware components with purpose and wiring details
7. **Operations** — Reset procedures (software, puzzle, hardware), test procedures, physical location of the device
8. **Known Quirks** — Documented issues, workarounds, things that will confuse future engineers
9. **Dependencies** — Libraries and versions
10. **Wiring Summary** — ASCII wiring diagram showing physical connections

### How the 6 AM Pipeline Works

1. At 6 AM, a script on the M3 machine does a `git pull` on every repo
2. The parser finds MANIFEST.h in each firmware project
3. It reads `@TAG` markers in the comments (e.g., `@DEVICE_NAME`, `@PIN:LIMIT_OPEN`, `@BROKER_IP`)
4. It extracts the values and stores them in the Grimoire's SQLite database
5. It generates a "Morning Report" showing what changed overnight
6. When you open WatchTower, every device card reflects the latest code

### Why This Is Better Than External Documentation

- The engineer fills out the manifest once when creating the prop
- When they change a pin, they update one line in MANIFEST.h — the Grimoire updates automatically
- If the manifest declares `BROKER_IP: 10.1.10.115` and WatchTower's config says `10.1.10.115`, the script can verify they match
- If a device name has a space ("Jungle Door" vs "JungleDoor"), the script catches the mismatch
- Documentation can never drift from code because they are literally the same file

---

## 6. THE HYBRID MANIFEST ARCHITECTURE (Final Design)

### The Problem with Documentation-Only Manifests

An early version of the manifest was purely documentation — structured comments that the parser could read but that the compiler ignored. The problem: engineers would still hardcode values in `main.cpp` separately, and those values could drift from the manifest.

### The Solution: Dual-Purpose Lines

Every line in MANIFEST.h serves TWO masters simultaneously:

1. **The Compiler** reads it as real C++ code (constants in a `manifest::` namespace)
2. **The Grimoire Parser** reads it as tagged text (looking for `@TAG` patterns in comments)

**Example of a dual-purpose line:**
```cpp
inline constexpr int RPWM_PIN = 4;    // @PIN:RPWM | BTS7960 RPWM — forward/open direction PWM
```

The compiler sees: `inline constexpr int RPWM_PIN = 4;` — a real constant it can use.
The parser sees: `@PIN:RPWM | BTS7960 RPWM — forward/open direction PWM` — metadata for the Grimoire.

### The Bridge Pattern

The firmware's main source file (`main.cpp` or `.ino`) includes MANIFEST.h and creates bridge aliases so existing code doesn't need to change:

```cpp
#include "MANIFEST.h"

// Bridge: all code below still uses these names, but values come from manifest
#define DEVICE_NAME       manifest::DEVICE_NAME
#define FIRMWARE_VERSION  manifest::FIRMWARE_VERSION

const char* WIFI_SSID     = manifest::WIFI_SSID;
const char* WIFI_PASSWORD = manifest::WIFI_PASSWORD;
```

**Key Design Principle:** Zero changes to function calls or logic. The bridge maps old names to new manifest sources. If anything breaks, you delete the `#include` and the bridge block, uncomment the original hardcoded values, and you're back to the original code. Safe rollback in under 60 seconds.

### PlatformIO vs Arduino IDE Projects

**PlatformIO projects** (like New-Cannons, CoveDoor):
- MANIFEST.h goes in the `include/` folder
- main.cpp uses `#include "MANIFEST.h"` (PlatformIO automatically searches `include/`)
- Bridge lives at top of `src/main.cpp`
- Has separate `MqttConfig.h` in `include/` that can also bridge to manifest values

**Arduino IDE projects** (like JungleDoor):
- MANIFEST.h goes in the same folder as the `.ino` file
- The `.ino` file uses `#include "MANIFEST.h"` directly
- No separate `include/` folder structure
- Bridge is simpler — just `#define` aliases at top of `.ino`

---

## 7. MANIFEST FILE SPECIFICATIONS

### Required @TAG Markers (Grimoire Parser)

```
@MANIFEST:IDENTITY          — Section start marker
@PROP_NAME                  — WatchTower-facing device name
@DESCRIPTION                — Human-readable description of what the prop does
@ROOM                       — Room/zone the prop belongs to
@BOARD                      — Board type (ESP32, ESP32-S3, Arduino Mega, etc.)
@FIRMWARE_VERSION           — Firmware version string
@REPO                       — GitHub repository URL
@BUILD_STATUS               — INSTALLED, IN_DEVELOPMENT, DEPRECATED, NOT_BUILT
@CODE_HEALTH                — EXCELLENT, GOOD, FAIR, BROKEN
@WATCHTOWER                 — COMPLIANT, PARTIAL, NONE

@MANIFEST:NETWORK           — Section start
@DEVICE_NAME                — MQTT client ID and topic base
@WIFI_SSID                  — WiFi network name
@WIFI_PASS                  — WiFi password
@BROKER_IP                  — MQTT broker IP address
@BROKER_PORT                — MQTT broker port
@HEARTBEAT_MS               — Heartbeat interval in milliseconds
@SUBSCRIBE                  — Topic subscriptions (one per line)
@PUBLISH                    — Topic publications (one per line)
@COMMAND                    — Supported commands (one per line)

@MANIFEST:PINS              — Section start
@PIN:{name}                 — Pin assignment with description

@MANIFEST:MOTOR             — Section start (if applicable)
@MOTOR:{param}              — Motor configuration parameters
@PWM:{param}                — PWM channel/frequency/resolution
@DOOR:{param}               — Door timing parameters

@MANIFEST:THRESHOLDS        — Section start (if applicable)
@THRESHOLD:{name}           — Sensor thresholds
@DEBOUNCE:{name}            — Debounce timing values

@MANIFEST:TIMING            — Section start
@TIMING:{name}              — Timing constants

@MANIFEST:COMPONENTS        — Section start
@COMPONENT                  — Hardware component entry
@PURPOSE                    — What it does
@DETAIL                     — Wiring and configuration details

@MANIFEST:OPERATIONS        — Section start
@LOCATION                   — Physical location of the device
@RESET:SOFTWARE             — Software reset procedure
@RESET:PUZZLE               — Puzzle reset procedure
@RESET:HARDWARE             — Hardware reset procedure
@OPERATION:{name}           — Operational procedure
@TEST:STEP{n}               — Test procedure steps
@QUIRK:{name}               — Known quirks and issues

@MANIFEST:DEPENDENCIES      — Section start
@LIB                        — Library dependency

@MANIFEST:WIRING            — Section start (ASCII wiring diagram)
```

### C++ Namespace Structure

All compilable constants live in the `manifest::` namespace:

```cpp
namespace manifest {
    // Identity
    inline constexpr const char* DEVICE_NAME = "CoveDoor";
    inline constexpr const char* FIRMWARE_VERSION = "1.0.0";

    // Network
    inline constexpr const char* WIFI_SSID = "AlchemyGuest";
    inline constexpr const char* WIFI_PASSWORD = "VoodooVacation5601";
    inline constexpr const char* MQTT_SERVER = "10.1.10.115";
    inline constexpr int MQTT_PORT = 1883;

    // Pins
    inline constexpr int RPWM_PIN = 4;
    inline constexpr int LPWM_PIN = 5;
    // ... etc
}
```

---

## 8. REPOS COMPLETED SO FAR

### 8a. New-Cannons (Gold Standard — First Manifest)

**Repo:** https://github.com/Alchemy-Escape-Rooms-Inc/New-Cannons
**Board:** ESP32-S3
**Framework:** PlatformIO (Arduino)
**Room:** Pirate Ship
**Description:** Twin cannons with distance sensors (VL6180X time-of-flight) and magnetic angle sensors (ALS31300 hall effect) that fire when the compass puzzle is solved. Uses relays to trigger pneumatic solenoids.
**Code Health:** EXCELLENT — 28 commits, best repo in the fleet
**WatchTower:** COMPLIANT

**Files Modified:**
- `include/MANIFEST.h` — NEW FILE, the gold standard template
- `include/MqttConfig.h` — Modified to bridge from MANIFEST.h (re-exports as `cfg::` namespace)
- `src/main.cpp` — Modified config namespace and VERSION define to reference `manifest::` values

**Key Details:**
- Has two instances (Cannon1, Cannon2) controlled by one codebase
- Uses I2C sensors: VL6180X at 0x29, ALS31300 at 0x60
- MQTT topics follow standard pattern: `MermaidsTale/Cannon1/command`
- Heartbeat: 5 minutes (300,000ms) — WatchTower standard
- Has relay control for pneumatic cannon firing

**Output Location:** `/mnt/user-data/outputs/New-Cannons-Manifest/`

---

### 8b. JungleDoor

**Repo:** https://github.com/Alchemy-Escape-Rooms-Inc/JungleDoor
**Board:** ESP32-S3
**Framework:** Arduino IDE (single .ino file, NOT PlatformIO)
**Room:** Transitions FROM Pirate Ship (The Shattic) TO Jungle
**Description:** Secret sliding door hidden in the ship wall. Players don't know it's a door until it opens, revealing the path to the next room. Uses a Cytron MD13S motor driver (DIR + PWM control, not dual H-bridge).
**Code Health:** GOOD
**WatchTower:** PARTIAL (30-second heartbeat instead of 5-minute standard, no hardware watchdog)

**Files Modified:**
- `JungleDoor/MANIFEST.h` — NEW FILE (same folder as .ino since Arduino IDE)
- `JungleDoor/JungleDoor.ino` — Modified to bridge all values from MANIFEST.h

**Critical Issues Documented:**
1. **Limit Switch Reliability** — BOTH limit switches are unreliable. The door runs on a 4-second timer as primary stop mechanism. Limit switch code exists but isn't depended on. Risk: if door travel slows (friction, grime, motor wear), timer window is insufficient.
2. **Device Name Space Bug** — Code had `"Jungle Door"` (with space), creating topics like `MermaidsTale/Jungle Door/command`. Should be `"JungleDoor"` (no space). This is a BREAKING CHANGE requiring coordinated WatchTower config update.
3. **No Hardware Watchdog** — Loop hang requires manual power cycle.
4. **Unused Status LEDs** — Pins 21, 22, 23 defined but never used (no physical LEDs installed). Three GPIO pins wasted.

**Design Rationale for Mixed Limit Switches:**
- CLOSED side uses a hidden laser beam break sensor (analog, threshold 3600) because you can't put a visible mechanical switch on a wall that players don't know is a door
- OPEN side uses a standard mechanical switch (INPUT_PULLUP, active LOW) because by the time the door is open, the secret is already revealed

**Physical Location:** The Shattic (Ship's Attic) — Alchemy team's internal name for the attic space above the Pirate Ship room

**Output Location:** `/mnt/user-data/outputs/JungleDoor-Manifest/`

---

### 8c. CoveDoor (CoveSlidingDoor)

**Repo:** https://github.com/Alchemy-Escape-Rooms-Inc/CoveSlidingDoor
**Board:** Changed from ESP32-S3 to regular ESP32 (per Clifford's request during this session)
**Framework:** PlatformIO (Arduino)
**Room:** Transitions FROM Monkey Altar Room TO Cove
**Description:** Secret sliding door from the Monkey Altar Room into the Cove. Same concept as JungleDoor (hidden door, players don't know it exists until it opens) but different motor driver and both limit switches are mechanical.
**Code Health:** GOOD
**WatchTower:** COMPLIANT (has PUZZLE_RESET, standard commands)

**Files Modified:**
- `include/MANIFEST.h` — NEW FILE
- `src/main.cpp` — Modified to bridge all values from MANIFEST.h, updated serial banner from "ESP32-S3" to "ESP32"
- `platformio.ini` — Changed board from `esp32-s3-devkitc-1` to `esp32dev`, removed S3-specific USB CDC build flags, renamed environment from `[env:esp32s3]` to `[env:esp32]`

**Key Differences from JungleDoor:**
- Uses BTS7960 Dual H-Bridge motor driver (2 PWM pins: RPWM for open, LPWM for close) instead of Cytron MD13S (DIR + PWM)
- Both limit switches are mechanical with INPUT_PULLUP — no laser beam
- Limit switches WORK RELIABLY (unlike JungleDoor)
- Has PUZZLE_RESET command (JungleDoor doesn't)
- PONG and STATUS responses go on `/command` topic (JungleDoor puts PONG on `/status`)

**Board Change Implications (ESP32-S3 → Regular ESP32):**
- Limit switch pins changed from GPIO 38/39 to GPIO 32/33 because on the regular ESP32, pins 34-39 are input-only with NO internal pull-up resistors. `INPUT_PULLUP` silently fails on those pins. GPIO 32/33 fully support `INPUT_PULLUP`.
- The `ledcSetup()`/`ledcAttachPin()` API used in the code is correct for regular ESP32. The newer `ledcAttach()` API is ESP32-S3/Arduino 3.x specific. Do NOT modernize to newer API.
- USB CDC build flags removed from platformio.ini (regular ESP32 uses standard UART, not USB CDC)

**Physical Location:** Hidden above the door frame, accessible from above

**Output Location:** `/mnt/user-data/outputs/CoveDoor-Manifest/`

---

## 9. ALCHEMY MQTT PROTOCOL STANDARD

All ESP32 devices in the "A Mermaid's Tale" room follow the Alchemy MQTT Protocol:

**Broker:** `10.1.10.115:1883`
**WiFi:** SSID `AlchemyGuest`, Password `VoodooVacation5601`
**Topic Pattern:** `MermaidsTale/{DeviceName}/{suffix}`

**Standard Suffixes:**
| Suffix | Direction | Purpose |
|--------|-----------|---------|
| `/command` | Subscribe | Receive commands from WatchTower/game controller |
| `/status` | Publish | State changes, heartbeat messages |
| `/log` | Publish | Mirrored serial output for remote debugging |
| `/limit` | Publish | Limit switch events (door controllers only) |

**Required Commands (WatchTower Protocol):**
| Command | Response | Description |
|---------|----------|-------------|
| `PING` | `PONG` | Health check — System Checker sends this periodically |
| `STATUS` | State string with diagnostics | Full status report (state, uptime, RSSI, version, etc.) |
| `RESET` | `OK` then reboot | Software reboot — stops all actuators first |
| `PUZZLE_RESET` | `OK` | Reset game state without rebooting — re-read sensors, sync state |

**Over-the-Air Updates (MANDATORY since 2026-09-22):** every Wi-Fi board runs `ArduinoOTA` (hostname = DeviceName, password = Wi-Fi password, port 3232 ESP32 / 8266 ESP8266) so firmware is pushed over the LAN after the one-time USB flash. `STATUS` replies include `IP:x.x.x.x`. Boards without OTA are at most `partial` compliance. Full spec: [`mqtt-protocol.md`](mqtt-protocol.md).

**Standard Boot Sequence:**
1. Initialize hardware (pins, sensors, motors)
2. Connect to WiFi (`AlchemyGuest`)
3. Connect to MQTT broker (`10.1.10.115:1883`)
4. Subscribe to `MermaidsTale/{DeviceName}/command`
5. Publish `ONLINE` on `/status`
6. Begin heartbeat loop

**Heartbeat Standard:**
- Interval: 300,000ms (5 minutes) — this is the WatchTower standard
- Format: `HEARTBEAT:{state}:UP{uptime}s:RSSI{signal}`
- Published on `/status` topic
- Note: Some older devices use 30-second heartbeats (JungleDoor, CoveDoor) — these are non-standard but functional

**Device Naming Convention:**
- PascalCase, no spaces, no special characters
- Examples: `Cannon1`, `JungleDoor`, `CoveDoor`, `BarrelPiston`, `ShipMotion1`
- The device name must be consistent across: firmware code, MQTT topics, WatchTower config, and Grimoire registry

---

## 10. NETWORK INFRASTRUCTURE

| Resource | Address | Notes |
|----------|---------|-------|
| MQTT Broker | `10.1.10.115:1883` | Mosquitto on M3 machine |
| WiFi Network | `AlchemyGuest` | Password: `VoodooVacation5601` |
| WatchTower Dashboard | `http://localhost:5000` | Flask app on M3 |
| GitHub Organization | `Alchemy-Escape-Rooms-Inc` | All firmware repos |

**BAC Controllers (Bose/Show Control):**
- Shattic, Captain, Cove, Jungle
- Topic pattern: `{ControllerName}/get/heartbeat` (passive monitoring)
- Do not use PING/PONG — monitored via heartbeat presence

---

## 11. KNOWN ISSUES & QUIRKS REGISTRY

### Cross-Device Issues

1. **PONG Response Location Inconsistency** — Some devices respond to PING with PONG on `/command`, others on `/status`. WatchTower's System Checker listens on both as a workaround. The standard should be `/command` (echo back where you received it).

2. **Stack Corruption in MQTT Callback** — PubSubClient reuses an internal buffer for the topic pointer. If you `mqtt.publish()` inside the callback before copying the topic to a local buffer, the topic pointer gets corrupted. Fix: Always copy topic to `char topicBuf[128]` FIRST, before any publish calls. This was the root cause of several "device randomly stops responding" issues.

3. **Heartbeat Interval Non-Standard** — Several devices use 30-second heartbeats instead of the 5-minute (300,000ms) WatchTower standard. This isn't harmful but creates unnecessary MQTT traffic and clutters the message log.

4. **Device Name Spaces** — JungleDoor firmware had "Jungle Door" with a space, creating broken MQTT topics. All device names must be PascalCase with no spaces. The manifest system catches this because `@DEVICE_NAME` and the actual `DEVICE_NAME` constant must match.

### Per-Device Issues

**JungleDoor:**
- Limit switches unreliable — operates on 4-second timer
- No hardware watchdog
- 30-second heartbeat (non-standard)
- Device name had space (fixed in manifest but not yet deployed)
- Unused LED pins 21, 22, 23

**CoveDoor:**
- No hardware watchdog
- 30-second heartbeat (non-standard)
- PONG goes to `/command` instead of `/status`
- Uses older `ledcSetup()` API — correct for regular ESP32, do not upgrade

---

## 12. FILE LOCATIONS & PROJECT STRUCTURE

### Local Development Machine (Clifford's PC)
```
C:\Users\joshua\Repos\
├── New-Cannons/
│   ├── include/
│   │   ├── MANIFEST.h          ← NEW (single source of truth)
│   │   └── MqttConfig.h        ← MODIFIED (bridges to manifest)
│   ├── src/
│   │   └── main.cpp            ← MODIFIED (config references manifest)
│   └── platformio.ini
├── JungleDoor/
│   ├── MANIFEST.h              ← NEW (same folder as .ino for Arduino IDE)
│   └── JungleDoor.ino          ← MODIFIED (bridges to manifest)
├── CoveSlidingDoor/
│   ├── include/
│   │   └── MANIFEST.h          ← NEW
│   ├── src/
│   │   └── main.cpp            ← MODIFIED
│   └── platformio.ini          ← MODIFIED (ESP32-S3 → ESP32)
└── [27 other repos...]
```

### GitHub Organization
```
https://github.com/Alchemy-Escape-Rooms-Inc/
├── New-Cannons
├── JungleDoor
├── CoveSlidingDoor
├── ESP-IDE                     ← Template repo for new props
└── [28 other repos...]
```

### WatchTower/Grimoire (M3 Machine)
```
[WatchTower installation directory]/
├── system_checker.py           ← Main application (V1 or V2)
├── config.json                 ← Device registry (29 ESP32 + 4 BAC)
├── run_checker.bat             ← Launcher
├── requirements.txt            ← paho-mqtt, flask
├── WATCHTOWER_CODING_STANDARDS.md
├── operations-manual.md        ← Grimoire library content
├── wiring-reference.md         ← Grimoire library content
├── network-infrastructure.md   ← Grimoire library content
├── debug-log.md                ← Grimoire live content
├── todo.md                     ← Grimoire live content
├── code-health-report.md       ← Grimoire live content
└── SUMMARY-REPORT.md
```

---

## 13. GLOSSARY OF ALCHEMY-SPECIFIC TERMS

| Term | Meaning |
|------|---------|
| **WatchTower** | The monitoring dashboard that pings all devices and shows their status |
| **Grimoire** | The reference library integrated into WatchTower — documentation, wiring, procedures |
| **Manifest** | The `MANIFEST.h` file in each firmware repo — single source of truth |
| **The Shattic** | Ship's Attic — the physical attic space above the Pirate Ship room |
| **BAC** | Bose/show-control controllers — 4 zone controllers (Shattic, Captain, Cove, Jungle) |
| **System Checker** | The PING/PONG health check component of WatchTower |
| **Morning Report** | The 6 AM change report generated by the Grimoire parser pipeline |
| **Bridge** | The `#define` block in main.cpp that maps old variable names to manifest:: values |
| **Alchemy MQTT Protocol** | The standardized MQTT communication pattern all ESP32 devices follow |
| **PUZZLE_RESET** | Command that resets game state without rebooting the device — used between game sessions |
| **A Mermaid's Tale** | The name of the first escape room game |
| **Device Registry** | The Grimoire section showing every device with its status, specs, and documentation |
| **PascalCase** | Naming convention for device names (e.g., `CoveDoor`, not `cove_door` or `Cove Door`) |

---

## APPENDIX: HOW TO USE THIS DOCUMENT

This document exists because the manifest system, WatchTower, and Grimoire concepts span multiple conversation sessions and involve architectural decisions that aren't obvious from the code alone. If you're a Claude instance (Cowork, Code, or otherwise) being asked about any of these systems:

1. **The manifest is the single source of truth.** All device documentation lives in `MANIFEST.h` inside each firmware repo. The Grimoire reads from it. WatchTower's config mirrors it. If something disagrees, the manifest wins.

2. **The bridge pattern is intentionally conservative.** We deliberately chose NOT to refactor function calls or rename variables throughout the codebase. The bridge maps old names to new manifest sources. This makes rollback trivial.

3. **Not all repos have manifests yet.** As of this writing, only New-Cannons, JungleDoor, and CoveDoor have been converted. There are approximately 28 other repos remaining.

4. **The 6 AM parser pipeline is designed but not yet built.** The manifest file format (with @TAG markers) is ready for it, but the actual Python script that pulls repos and extracts tags into the Grimoire database hasn't been written yet.

5. **Test before deploying.** The manifest changes are additive — they add a file and modify bridge lines. They should not change device behavior. But always compile, flash, and verify before pushing to GitHub.
