# Alchemy Escape Rooms — MQTT Protocol Standard

This document is the **authoritative standard** for MQTT communication across all ESP32 devices in "A Mermaid's Tale." Every device connected to WatchTower must conform to this protocol.

> **Source of truth:** Extracted from `alchemy-project-documentation.md` (Section 9) and promoted to a standalone standard document.

---

## Broker & Network

| Setting | Value |
|---|---|
| **Broker IP** | `10.1.10.115` |
| **Broker Port** | `1883` |
| **WiFi SSID** | `AlchemyGuest` |
| **WiFi Password** | `VoodooVacation5601` |
| **Topic Pattern** | `MermaidsTale/{DeviceName}/{suffix}` |

---

## Standard Topic Suffixes

| Suffix | Direction | Purpose |
|---|---|---|
| `/command` | Subscribe | Receive commands from WatchTower/game controller |
| `/status` | Publish | State changes, heartbeat messages |
| `/log` | Publish | Mirrored serial output for remote debugging |
| `/limit` | Publish | Limit switch events (door controllers only) |

---

## Required Commands (WatchTower Protocol)

Every WatchTower-compliant device must support all four of these commands:

| Command | Response | Description |
|---|---|---|
| `PING` | `PONG` | Health check — System Checker sends this periodically |
| `STATUS` | State string with diagnostics | Full status report (state, uptime, RSSI, version, **IP**, etc.) |
| `RESET` | `OK` then reboot | Software reboot — stops all actuators first |
| `PUZZLE_RESET` | `OK` | Reset game state without rebooting — re-read sensors, sync state |

---

## Standard Boot Sequence

Every device must follow this sequence on power-on or reboot:

1. Initialize hardware (pins, sensors, motors)
2. Connect to WiFi (`AlchemyGuest`)
3. Start the OTA listener (`ArduinoOTA.begin()`, see below) - **mandatory**
4. Connect to MQTT broker (`10.1.10.115:1883`)
5. Subscribe to `MermaidsTale/{DeviceName}/command`
6. Publish `ONLINE` on `/status` and a boot line on `/log` that includes the board's IP
7. Begin heartbeat loop

---

## Over-the-Air Updates (MANDATORY since 2026-09-22)

Every Wi-Fi board (ESP32, ESP32-S3, ESP8266) **must** accept firmware updates over the network via `ArduinoOTA`. Once a board is installed in a room, the USB cable is never needed again: a new build is pushed over Wi-Fi and the board reboots into it, exactly like a USB flash.

| Requirement | Value |
|---|---|
| **Library** | `ArduinoOTA` (bundled with the esp32 and esp8266 Arduino cores) |
| **Hostname** | `{DeviceName}` - identical to `DEVICE_NAME` |
| **Password** | Same as the Wi-Fi password (see *Broker & Network* above); boards are only reachable on the guest LAN |
| **Port** | `3232` (ESP32 / S3) or `8266` (ESP8266) - library defaults, do not change |
| **Where in code** | `ArduinoOTA.begin()` right after Wi-Fi connects; `ArduinoOTA.handle()` every `loop()` |
| **On start** | `onStart` must stop every actuator (motor, relay, pump, solenoid) and publish `OTA update starting` on `/log` |
| **Discoverability** | `STATUS` reply must include `IP:x.x.x.x`; the boot line on `/log` must include the IP |
| **Manifest** | `OTA_ENABLED "yes"`, `OTA_HOSTNAME "{DeviceName}"`, `OTA_PORT 3232` or `8266` in `MANIFEST.h` |

Reference implementation (ESP32 / S3 and ESP8266, drop in as-is):

```cpp
#include <ArduinoOTA.h>

void setupOTA() {                         // call once, after Wi-Fi is up
  ArduinoOTA.setHostname(DEVICE_NAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() { stopAllActuators(); mqttLogf("OTA update starting"); });
  ArduinoOTA.onEnd([]()   { Serial.println("OTA done, rebooting"); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA error %u\n", e); });
  ArduinoOTA.begin();
}
// in loop():  ArduinoOTA.handle();
```

Flashing over the air (after the one-time USB flash that puts OTA on the board):

```
arduino-cli compile --fqbn <fqbn> --export-binaries <sketch dir>
arduino-cli upload  --fqbn <fqbn> -p <board IP> --upload-field password=<Wi-Fi password> <sketch dir>
```

`arduino-cli board list` shows OTA-ready boards as **network ports** with their IP. Get a board's IP from its `STATUS` reply or the WatchTower device card.

**Compliance:** a board without OTA is at most `partial` WatchTower compliance. The Device Manifests page marks every board **OTA yes / OTA REQUIRED**. Existing boards get OTA added at their next firmware touch; new boards ship with it from the first flash.

---

## Heartbeat Standard

- **Interval:** `300000` ms (5 minutes) — this is the WatchTower standard
- **Format:** `HEARTBEAT:{state}:UP{uptime}s:RSSI{signal}`
- **Topic:** `/status`

> ⚠️ Some older devices (JungleDoor, CoveDoor) use 30-second heartbeats. This is non-standard and creates unnecessary MQTT traffic. New devices must use 5 minutes.

---

## Device Naming Convention

- PascalCase, no spaces, no special characters
- Examples: `Cannon1`, `JungleDoor`, `CoveDoor`, `BarrelPiston`, `ShipMotion1`
- The device name must be **identical** across: firmware code, MQTT topics, WatchTower config, and Grimoire registry
- A space in a device name (e.g., `Jungle Door`) creates a broken MQTT topic and the device will never receive commands

---

## PONG Response Topic

The standard is to publish `PONG` on the **same topic the command was received on** (`/command`). WatchTower listens on both `/command` and `/status` as a workaround for legacy devices, but all new devices must PONG on `/command`.

---

*For the cross-device issues and known deviations from this standard, see [`quirks-registry.md`](quirks-registry.md).*  
*For how these values are declared in firmware, see [`manifest-protocol.md`](manifest-protocol.md).*
