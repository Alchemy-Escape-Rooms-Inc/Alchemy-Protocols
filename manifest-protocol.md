# Alchemy Escape Rooms — MANIFEST.h Protocol

This document is the **authoritative standard** for writing `MANIFEST.h` files across all Alchemy Escape Rooms firmware repos. Every prop that connects to the WatchTower system must have a `MANIFEST.h` that conforms to this protocol.

> **Source of truth:** This file was extracted from `alchemy-project-documentation.md` (Sections 5, 6, and 7) and promoted to a standalone standard document.

---

## Table of Contents

1. [The Self-Documenting Firmware Manifest System](#1-the-self-documenting-firmware-manifest-system)
2. [The Hybrid Manifest Architecture (Final Design)](#2-the-hybrid-manifest-architecture-final-design)
3. [Manifest File Specifications](#3-manifest-file-specifications)

---

## 1. THE SELF-DOCUMENTING FIRMWARE MANIFEST SYSTEM

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

## 2. THE HYBRID MANIFEST ARCHITECTURE (Final Design)

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

## 3. MANIFEST FILE SPECIFICATIONS

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
@END:IDENTITY               — Section end marker

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
@END:NETWORK                — Section end marker

@MANIFEST:PINS              — Section start
@PIN:{name}                 — Pin assignment with description
@END:PINS                   — Section end marker

@MANIFEST:MOTOR             — Section start (if applicable)
@MOTOR:{param}              — Motor configuration parameters
@PWM:{param}                — PWM channel/frequency/resolution
@DOOR:{param}               — Door timing parameters
@END:MOTOR                  — Section end marker

@MANIFEST:THRESHOLDS        — Section start (if applicable)
@THRESHOLD:{name}           — Sensor thresholds
@DEBOUNCE:{name}            — Debounce timing values
@END:THRESHOLDS             — Section end marker

@MANIFEST:TIMING            — Section start
@TIMING:{name}              — Timing constants
@END:TIMING                 — Section end marker

@MANIFEST:COMPONENTS        — Section start
@COMPONENT                  — Hardware component entry
@PURPOSE                    — What it does
@DETAIL                     — Wiring and configuration details
@END:COMPONENTS             — Section end marker

@MANIFEST:OPERATIONS        — Section start
@LOCATION                   — Physical location of the device
@RESET:SOFTWARE             — Software reset procedure
@RESET:PUZZLE               — Puzzle reset procedure
@RESET:HARDWARE             — Hardware reset procedure
@OPERATION:{name}           — Operational procedure
@TEST:STEP{n}               — Test procedure steps
@QUIRK:{name}               — Known quirks and issues
@END:OPERATIONS             — Section end marker

@MANIFEST:DEPENDENCIES      — Section start
@LIB                        — Library dependency
@END:DEPENDENCIES           — Section end marker

@MANIFEST:WIRING            — Section start (ASCII wiring diagram)
@END:WIRING                 — Section end marker
```

### C++ Namespace Structure

All compilable constants live in the `manifest::` namespace:

```cpp
namespace manifest {
    // Identity
    inline constexpr const char* DEVICE_NAME      = "CoveDoor";
    inline constexpr const char* FIRMWARE_VERSION  = "1.0.0";

    // Network
    inline constexpr const char* WIFI_SSID     = "AlchemyGuest";
    inline constexpr const char* WIFI_PASSWORD = "VoodooVacation5601";
    inline constexpr const char* MQTT_SERVER   = "10.1.10.115";
    inline constexpr int         MQTT_PORT     = 1883;

    // Pins
    inline constexpr int RPWM_PIN = 4;
    inline constexpr int LPWM_PIN = 5;
    // ... etc
} // namespace manifest
```

### Naming Conventions

- **Device names** must be PascalCase with no spaces (e.g., `JungleDoor`, not `Jungle Door`)
- **MQTT topics** are built dynamically: `"MermaidsTale/" + DEVICE_NAME + "/{suffix}"`
- **Heartbeat standard** is `300000` ms (5 minutes) — do not use 30s or 60s unless there is a documented reason
- **Firmware versions** follow `MAJOR.MINOR.PATCH` semver format

### File Header Template

Every MANIFEST.h must open with this header block:

```cpp
/**
 * ============================================================================
 *  ALCHEMY ESCAPE ROOMS — FIRMWARE MANIFEST
 * ============================================================================
 *
 *  THIS FILE IS THE SINGLE SOURCE OF TRUTH.
 *
 *  It serves two masters simultaneously:
 *
 *    1. THE COMPILER — Every constant the firmware needs (pins, IPs, ports,
 *       thresholds, timing) is defined here as real C++ code. The firmware
 *       #includes this file and uses these values directly.
 *
 *    2. THE GRIMOIRE PARSER — A Python script running on M3 at 6 AM reads
 *       this file as plain text and extracts values tagged with @FIELD_NAME
 *       in the comments. Those values populate the WatchTower Grimoire
 *       device registry, wiring reference, and operations manual.
 *
 *  Because both systems read from the same lines, the documentation can
 *  never drift from the firmware. Change a pin number here, and the Grimoire
 *  updates automatically. There is no second file to keep in sync.
 *
 *  RULES:
 *    1. Every field marked [REQUIRED] must be filled in before deployment.
 *    2. Update this file FIRST when changing hardware, pins, or topics.
 *    3. The 6 AM parser looks for @TAG patterns — don't rename them.
 *    4. Descriptive-only sections (operations, quirks) are pure comments.
 *       Constants sections are real code + comment tags on the same line.
 *    5. This file is the sole source of configuration values — the .ino
 *       or main.cpp file should reference these constants, not hardcode its own.
 *
 *  LAST UPDATED: YYYY-MM-DD
 *  MANIFEST VERSION: X.X
 * ============================================================================
 */

#pragma once
#include <cstdint>
```

---

*For a complete real-world example, see `MANIFEST.h` in the [JungleDoor](https://github.com/Alchemy-Escape-Rooms-Inc/JungleDoor) repo (v3.3, the current reference implementation).*
