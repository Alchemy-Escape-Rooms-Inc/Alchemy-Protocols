# Alchemy Escape Rooms — Known Issues & Quirks Registry

This document tracks cross-device firmware issues and per-device quirks across the "A Mermaid's Tale" prop network. It is the living record of things that will confuse future engineers.

> **Source of truth:** Extracted from `alchemy-project-documentation.md` (Section 11) and promoted to a standalone registry. Per-device quirks are also duplicated in each device's own `MANIFEST.h` under `@QUIRK:` tags.

---

## Cross-Device Issues

### 1. PONG Response Topic Inconsistency
Some devices publish `PONG` on `/command`, others on `/status`. WatchTower's System Checker listens on both as a workaround.

- **Standard:** PONG must be published on `/command` (echo back where you received it)
- **Status:** Unresolved on legacy devices — do not replicate in new firmware

---

### 2. Stack Corruption in MQTT Callback
PubSubClient reuses an internal buffer for the topic pointer. If you call `mqtt.publish()` inside the callback before copying the topic to a local buffer, the topic pointer gets corrupted, causing the device to randomly stop responding to commands.

- **Fix:** Always copy topic to a local buffer FIRST, before any publish calls:
```cpp
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    char topicBuf[128];
    strlcpy(topicBuf, topic, sizeof(topicBuf));  // copy FIRST
    // now safe to publish
    mqtt.publish(someTopic, "PONG");
}
```
- **Status:** Fixed in all current firmware. This was the root cause of several "device randomly stops responding" incidents.

---

### 3. Heartbeat Interval Non-Standard
Several devices use 30-second heartbeats instead of the 5-minute (300,000ms) WatchTower standard. This is not harmful but creates unnecessary MQTT traffic and clutters the message log.

- **Standard:** `HEARTBEAT_INTERVAL = 300000` (5 minutes)
- **Affected devices:** JungleDoor, CoveDoor
- **Status:** Low priority — functional but non-standard

---

### 4. Device Name Spaces in MQTT Topics
Device names with spaces (e.g., `"Jungle Door"`) create broken MQTT topics (`MermaidsTale/Jungle Door/command`) that no subscriber will receive. The manifest system catches this because `@DEVICE_NAME` and the actual `DEVICE_NAME` constant must match and both must be PascalCase with no spaces.

- **Standard:** PascalCase, no spaces (e.g., `JungleDoor`)
- **Affected devices:** JungleDoor (fixed in MANIFEST.h, verify deployment)
- **Status:** Fixed in firmware — verify WatchTower config and any external subscribers are updated to match

---

## Per-Device Issues

### JungleDoor
| Issue | Detail |
|---|---|
| Limit switches unreliable | Door operates on 4-second timer fallback rather than reliable limit switch triggering |
| No hardware watchdog | If main loop hangs, device will not auto-recover — requires manual RESET or power cycle |
| Non-standard heartbeat | 30-second interval instead of 5-minute standard |
| Device name space | `"Jungle Door"` → fixed to `"JungleDoor"` in MANIFEST.h — confirm deployed firmware matches |
| Unused pins | LED pins 21, 22, 23 defined but not used |

---

### CoveDoor
| Issue | Detail |
|---|---|
| No hardware watchdog | If main loop hangs, device will not auto-recover — requires manual RESET or power cycle |
| Non-standard heartbeat | 30-second interval instead of 5-minute standard |
| PONG topic | Publishes PONG on `/command` instead of `/status` — WatchTower handles both |
| Legacy LEDC API | Uses `ledcSetup()` / `ledcAttachPin()` — correct for regular ESP32, do not "upgrade" to newer `ledcAttach()` API without verifying board compatibility |
| GPIO33 defective pull-up | This specific board's GPIO 33 internal pull-up only reaches 0.55V — workaround is external 10K pull-up or use GPIO 32 instead |
| GPIO5 boot crash | GPIO 5 is a strapping pin on regular ESP32 — external connections during boot cause invalid flash reads. Avoid GPIO 0, 2, 5, 12, 15 for signals with external connections |

---

*For the MQTT standard these devices should conform to, see [`mqtt-protocol.md`](mqtt-protocol.md).*  
*For how per-device quirks are embedded in firmware, see [`manifest-protocol.md`](manifest-protocol.md) — `@QUIRK:` tag section.*
