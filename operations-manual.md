# ALCHEMY ESCAPE ROOMS — "A MERMAID'S TALE" OPERATIONS MANUAL

**Version:** 1.0
**Last Updated:** February 2025
**Audience:** Technical staff, game operators, maintenance technicians
**Scope:** Complete hardware inventory, firmware details, troubleshooting, and testing procedures

---

## TABLE OF CONTENTS

1. [Network & Infrastructure](#network--infrastructure)
2. [Ship/Shattic Area](#shipshattic-area)
3. [Captain's Quarters](#captains-quarters)
4. [Cove Area](#cove-area)
5. [Jungle Area](#jungle-area)
6. [Cross-Room Systems](#cross-room-systems)
7. [Standalone Devices (No WiFi/MQTT)](#standalone-devices-no-wifimqtt)
8. [Legacy & Deprecated Hardware](#legacy--deprecated-hardware)
9. [Known Issues & Critical Bugs](#known-issues--critical-bugs)
10. [Quick Reference](#quick-reference)

---

## NETWORK & INFRASTRUCTURE

### WiFi Network
- **SSID:** AlchemyGuest
- **Password:** VoodooVacation5601
- **Frequency:** Standard 2.4GHz (verify no 5GHz forcing)

### MQTT Broker
- **Host:** 10.1.10.115
- **Port:** 1883
- **Protocol:** MQTT 3.1.1
- **Broker Software:** Mosquitto (standard config assumed)

### BAC Controllers (Building Automation Control)
All BAC units managed via **BAM (Building Automation Manager)** software. They provide relay control for non-WiFi devices.

| Device Name | Area | Function | Heartbeat Topic | Command Topic Pattern |
|---|---|---|---|---|
| **Shattic** | Ship/Shattic | Ship area relay control | `Shattic/get/heartbeat` | `Shattic/set/Output_X/on` \.off |
| **Captain** | Captain's Quarters | Captain's area relay control | `Captain/get/heartbeat` | `Captain/set/Output_X/on` \.off |
| **Cove** | Cove | Cove area relay control | `Cove/get/heartbeat` | `Cove/set/Output_X/on` \.off |
| **Jungle** | Jungle | Jungle area relay control | `Jungle/get/heartbeat` | `Jungle/set/Output_X/on` \.off |

**Heartbeat Frequency:** Every 10 seconds
**Command Response:** BACs acknowledge state changes via status publish

---

## SHIP/SHATTIC AREA

### Overview
The Ship area contains motion-triggered events, cannon firing mechanisms, and navigation displays. Controlled primarily by **Shattic BAC** with WiFi-enabled smart props.

---

### 1. NEW-CANNONS (Cannon1, Cannon2)

**Description:**
Two interactive cannons that detect when they are loaded (via proximity sensor) and track when players fire them. Firing triggers game events and audio cues.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v3.2.0 |
| I2C Bus | SDA=GPIO15, SCL=GPIO18 |
| I2C Sensor 1 | VL6180X (proximity) at address 0x29 |
| I2C Sensor 2 | ALS31300 (hall/magnetic) at address 0x01; auto-detect fallback 0x60–0x6F |
| Physical Button | GPIO35 (optional manual trigger) |

**Pin Assignments:**

| Pin | Function | GPIO |
|---|---|---|
| I2C Data | SDA | GPIO 15 |
| I2C Clock | SCL | GPIO 18 |
| Button Input | Manual trigger | GPIO 35 |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/Cannon{id}/command` | Sub | `{"action":"PING"}` | Receive commands from game controller |
| `MermaidsTale/Cannon{id}/status` | Pub | `{"state":"Ready","loaded":true}` | Publish current status |
| `MermaidsTale/Cannon{id}/log` | Pub | `"Loaded detected"` | Debug/event logging |
| `MermaidsTale/Cannon{id}/Loaded` | Pub | `true` \| `false` | Loaded state (proximity sensor) |
| `MermaidsTale/Cannon{id}/Fired` | Pub | timestamp or `"fired"` | Fire event trigger |

**How to Reset:**
```
Publish to: MermaidsTale/Cannon{id}/command
Payload: {"action":"RESET"}
```
Monitor `status` topic for confirmation. Reset clears internal state but does not power-cycle.

**How to Test:**
1. **Proximity Detection:** Move hand slowly toward the cannon muzzle (within ~5cm). Monitor `Loaded` topic for `true`.
2. **Firing Simulation:** Press GPIO35 button on board, or publish `{"action":"FIRE"}` to command topic. Check `Fired` topic for event.
3. **MQTT Connectivity:** Publish `{"action":"PING"}` to command topic. Expect `PONG` response on status topic within 2 seconds.
4. **WiFi Reconnection:** Disable WiFi; verify device reconnects and publishes heartbeat within 10 seconds after WiFi restores.

**Dependencies:**
- WiFi network (AlchemyGuest) must be operational
- MQTT broker (10.1.10.115:1883) must be reachable
- I2C sensors must be present and functional

**Physical Location:**
- Cannon1: Ship bow/forward area
- Cannon2: Ship mid/aft area

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/New-Cannons

---

### 2. WIRELESS-MOTION-SENSOR (ShipMotion1, ShipMotion2, ShipMotion3)

**Description:**
Time-of-flight motion sensors that detect player movement in specific ship zones. Trigger ambient sounds, lighting changes, or puzzle hints when motion is detected. Features cooldown period to prevent spam.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP8266 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| I2C Sensor | VL53L0X (time-of-flight) at default address 0x29 |
| Trigger Distance | 200 mm (adjustable in firmware) |
| Cooldown Period | 120,000 ms (2 minutes) |

**Pin Assignments:**

| Pin | Function | Details |
|---|---|---|
| Default SDA | I2C Data | Standard ESP8266 default |
| Default SCL | I2C Clock | Standard ESP8266 default |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/ShipMotion2` | Pub | `"triggered"` | Motion detected |
| `MermaidsTale/ShipMotion2` | Pub | `"Searching"` | Waiting for next motion event |
| `MermaidsTale/ShipMotion2` | Pub | `"Cooldown"` | In cooldown period |
| `MermaidsTale/ShipMotion2` | Pub | `"Connected!"` | Boot message (device online) |
| `MermaidsTale/#` | Sub | (any) | Subscribes to all game topics (general awareness) |

**⚠️ Protocol Status: PARTIAL**
Missing heartbeat, PING/PONG, and RESET commands. No active monitoring of device health.

**How to Reset:**
Currently no MQTT reset command implemented. Must power-cycle physically.

**How to Test:**
1. **Connectivity:** Wait for boot and monitor MQTT for `"Connected!"` message.
2. **Motion Detection:** Move hands/body within 200 mm of sensor. Expect `"triggered"` on topic within 1 second.
3. **Cooldown:** After trigger, device publishes `"Cooldown"` and will not trigger again for 120 seconds.
4. **Distance Tuning:** If trigger distance is wrong, firmware edit required (see source code).

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- No external dependencies; standalone sensor module

**Physical Location:**
- ShipMotion1: Forward ship zone
- ShipMotion2: Mid ship zone
- ShipMotion3: Aft ship zone

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Wireless-Motion-Sensor

---

### 3. BARREL-PISTON

**Description:**
A pneumatic piston that pushes a barrel or prop as a gameplay event trigger. Uses relay-controlled solenoids with safety interlocks to prevent simultaneous engage/retract commands.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | Latest (version not specified) |
| Relay Logic | Active HIGH (HIGH = energized) |
| Interlock Gap | 120 ms (enforced delay between opposite commands) |
| Command Timeout | 5 seconds (max time to accept a new command) |
| Watchdog Reboot | 10 minute inactivity timeout |
| State Machine | STOPPED, ENGAGING, RETRACTING, SAFETY |

**Pin Assignments:**

| Pin | Function | GPIO | Logic |
|---|---|---|---|
| Engage Relay | Push barrel out | GPIO 16 | HIGH = energize |
| Retract Relay | Pull barrel in | GPIO 17 | HIGH = energize |
| Status LED | Visual feedback | GPIO 25 | Active HIGH |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/BarrelPiston/Engaged` | Pub | `true` \| `false` | Current engagement state |
| `MermaidsTale/BarrelPiston/Retract` | Sub | `true` \| `false` | Command to retract piston |
| `MermaidsTale/BarrelPiston/Status` | Pub | `{"state":"ENGAGING"}` | Full state machine status |
| `MermaidsTale/BarrelPiston/Safety` | Pub | `"Interlock active"` | Safety alert if dual-relay triggered |
| `MermaidsTale/BarrelPiston/DeviceInfo` | Pub | `{"board":"ESP32","timeout":5000}` | Device metadata |
| `MermaidsTale/BarrelPiston/GPIO2` | Pub | GPIO state | Legacy/debug topic |
| `MermaidsTale/BarrelPiston/GPIO4` | Pub | GPIO state | Legacy/debug topic |
| `MermaidsTale/BarrelPiston/GPIO2/State` | Pub | `0` \| `1` | Pin state |
| `MermaidsTale/BarrelPiston/GPIO4/State` | Pub | `0` \| `1` | Pin state |

**How to Reset:**
```
Publish to: MermaidsTale/BarrelPiston/Retract
Payload: true
```
Waits for 120 ms safety gap, then energizes retract relay. Monitor `Status` topic for completion.

**How to Test:**
1. **Engage Piston:** Publish `true` to `MermaidsTale/BarrelPiston/Engaged`. Monitor `Status` topic; should show `"ENGAGING"`.
2. **Retract Piston:** Publish `true` to `/Retract`. Should show `"RETRACTING"` on status, then `"STOPPED"`.
3. **Interlock Test:** Send engage then retract commands within 100 ms. Device should enforce 120 ms gap; monitor `/Safety` topic for warnings.
4. **Watchdog Test:** Do not send commands for 10+ minutes. Device should reboot automatically (check WiFi reconnect log).

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- Physical solenoid relays and pneumatic system

**Physical Location:**
- Ship/Shattic area (barrel or prop mechanism)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Barrel-Piston

---

### 4. SHIP-NAV-MAP

**Description:**
A dynamic LED display showing a ship navigation map. Uses addressable WS2812B RGB LEDs to light up waypoints and navigation paths as players solve puzzles.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP8266 or ESP32 (unclear in firmware) |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| LED Type | WS2812B (Neopixel) addressable RGB |
| LED Count | 15 total |
| LED Control Pin | A0 (analog pin converted to digital) |
| LED Library | FastLED |

**Pin Assignments:**

| Pin | Function | Type |
|---|---|---|
| A0 | WS2812B data line | Digital (FastLED) |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/ShipMap` | Sub | `{"action":"light","led":5,"color":"#FF0000"}` | Control specific LEDs |
| `ShipMap/summary` | Pub | `{"lit_count":7,"pattern":"waypoint"}` | Status summary |
| `MermaidsTale/#` | Sub | (any) | Subscribes to all game topics |

**⚠️ CRITICAL BUGS FOUND:**

| Issue | Impact | Fix |
|---|---|---|
| CGRB typo (should be CRGB) | Code will NOT compile | Change `AddressableStrip<CGRB>` to `CRGB` |
| Variable name mismatch (mqtt vs client) | Undefined symbol error | Standardize variable naming throughout |
| Backwards WiFi reconnect logic | Device may disconnect unexpectedly | Review reconnect conditional |

**How to Reset:**
Not defined. Requires power-cycle or firmware fix before deployment.

**How to Test:**
**CANNOT TEST** — Code does not compile in current state. Must fix bugs first.

**Dependencies:**
- FastLED library
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)

**Physical Location:**
- Ship area (wall-mounted or stand-mounted display)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/ShipNavMap

**Deployment Status:** ⚠️ **NOT PRODUCTION READY** — Critical compilation errors must be resolved.

---

## CAPTAIN'S QUARTERS

### Overview
Captain's Quarters features puzzles requiring compass navigation, physical lock interactions (cuffs), and door mechanisms. Controlled by **Captain BAC** for relay functions.

---

### 5. COMPASS (BlueCompass, RoseCompass, SilverCompass)

**Description:**
Interactive compass props that players must rotate to point in a specific direction. Each compass reads potentiometer position and translates it to a compass bearing (0–359 degrees). Solves when pointed at the correct direction.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v1.0.0 |
| Potentiometer Input | GPIO 4 (ADC channel) |
| ADC Resolution | 12-bit (0–4095 raw counts) |
| Bearing Mapping | 4095 raw → 359 degrees (linear scale) |
| Protocol | Full Watchtower (see below) |

**Pin Assignments:**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| Potentiometer | Directional input | GPIO 4 | Analog in (ADC) |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/BlueCompass/command` | Sub | `{"action":"PING"}` | Receive game commands |
| `MermaidsTale/BlueCompass/status` | Pub | `{"bearing":45,"locked":false}` | Current compass state |
| `MermaidsTale/BlueCompass/log` | Pub | `"Bearing: 45°"` | Debug logging |
| `MermaidsTale/BlueCompass/direction` | Pub | `"NE"` | Human-readable direction |
| `BlueCompassSolved` | Pub | `true` | Puzzle solved event |

**Watchtower Protocol Features:**
- **Boot Status:** Device publishes startup confirmation
- **Heartbeat:** Every 5 minutes (topic: derived from device name)
- **PING/PONG:** Responds to `PING` command with `PONG`
- **RESET:** Resets internal state without power-cycle
- **WiFi/MQTT Reconnect:** Automatic with exponential backoff

**Known Fix (v1.0.0):**
Startup grace period prevents RESET command from creating boot loops. Device waits ~2 seconds after boot before accepting RESET.

**How to Reset:**
```
Publish to: MermaidsTale/BlueCompass/command
Payload: {"action":"RESET"}
```
Monitor `status` topic for `"locked":false` confirmation.

**How to Test:**
1. **Potentiometer Reading:** Slowly rotate compass dial. Monitor `/direction` topic; should cycle through directions (N, NE, E, SE, etc.) smoothly.
2. **Bearing Precision:** Rotate to a known bearing (e.g., North). Publish `{"action":"PING"}` to command. Expect `PONG` within 2 seconds on status.
3. **Solve Event:** Rotate compass to target bearing (depends on puzzle logic). Monitor `BlueCompassSolved` topic for `true` event.
4. **Heartbeat:** Wait 5 minutes with no commands. Should see heartbeat publish every 300 seconds.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- Potentiometer must be mechanically linked to compass dial

**Physical Location:**
- Blue Compass: Captain's quarters left wall
- Rose Compass: Captain's quarters center
- Silver Compass: Captain's quarters right wall

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Compass

---

### 6. CAPTAINS-CUFFS

**Description:**
Eight magnetic locking cuffs on a captain's mannequin or display. Players must touch all cuffs simultaneously (within a time window) to trigger the puzzle. Each cuff has a capacitive touch sensor and independent relay lock.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | Arduino Mega 2560 |
| WiFi/MQTT | NONE — Standalone (serial only) |
| Serial Baud Rate | 9600 |
| Touch Sensors | 8x capacitive touch (pins 22–29) |
| Hall Sensors (Magnets) | 8x hall effect (pins 30, 31, 32, 34, 36, 37; cuffs 3 & 5 disabled with -1) |
| Relay Outputs | 8x relays (pins 38–45) |
| Relay Logic | Active HIGH (HIGH = locked) |
| Puzzle Logic | All engaged cuffs must be touched simultaneously (within time window) |

**Pin Assignments:**

| Cuff # | Touch Pin | Hall Pin | Relay Pin | Enabled? |
|---|---|---|---|---|
| 1 | 22 | 30 | 38 | Yes |
| 2 | 23 | 31 | 39 | Yes |
| 3 | 24 | 32 | 40 | **No** (-1) |
| 4 | 25 | (n/a) | 41 | Yes |
| 5 | 26 | 34 | 42 | **No** (-1) |
| 6 | 27 | (n/a) | 43 | Yes |
| 7 | 28 | 36 | 44 | Yes |
| 8 | 29 | 37 | 45 | Yes |

**Serial Commands:**

| Command | Response | Function |
|---|---|---|
| `status` | Cuff state table | Read current lock/touch state for all 8 |
| `reset` | `"Reset complete"` | Clear touch buffers and reset timing |
| `open all` | Energize relays to unlock | Unlock all cuffs (debugging only) |
| `close all` | De-energize relays to lock | Lock all cuffs |
| `test relays` | Test each relay sequentially | Verify relay hardware |
| `test sensors` | Show capacitive touch readings | Debug touch sensor noise |
| `test magnets` | Show hall sensor readings | Debug magnet/position sensors |

**How to Reset:**
```
Serial connection (9600 baud): Send "reset"
```

**How to Test:**
1. **Touch Sensors:** Open serial monitor at 9600 baud. Type `test sensors`. Touch each cuff; capacitive values should spike when touched.
2. **Hall Sensors:** Type `test magnets`. Should show 6 active sensors (cuffs 1, 2, 4, 6, 7, 8); cuffs 3 & 5 show -1 (disabled).
3. **Relays:** Type `test relays`. Each relay pin (38–45) should cycle briefly; listen for clicking sounds.
4. **Simultaneous Touch Puzzle:** Lock all cuffs (`close all`). Touch all enabled cuffs within 2–3 seconds. Monitor `status` output for puzzle completion flag.

**Dependencies:**
- No WiFi/MQTT — Serial connection only
- Arduino IDE or serial terminal for diagnosis
- Capacitive touch library (built into Mega 2560)

**Physical Location:**
- Captain's quarters (mannequin or wall display)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Captains-Cuffs

---

### 7. CABIN-DOOR

**Description:**
A motorized cabin door that players must unlock to progress. Uses linear actuator (piston) controlled by dual relays. Features timeout safety to prevent over-extension.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 (actual); **PLACEHOLDER in primary repo** |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v1.0.0 (primary) or v1.1.0 (legacy CabinDoor_S3) |
| Relay Type | Active LOW (LOW = energized, must pull to GND) |
| Piston Timeout | 8 seconds (primary) or 15 seconds (legacy) |
| Safety | Relay interlock prevents simultaneous extend/retract |

**Pin Assignments:**

| Pin | Function | GPIO | Logic |
|---|---|---|---|
| Extend Relay | Push door open | GPIO 4 | LOW = energize |
| Retract Relay | Pull door closed | GPIO 5 | LOW = energize |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/CabinDoor/command` | Sub | `{"action":"PING"}` | Receive commands |
| `MermaidsTale/CabinDoor/status` | Pub | `{"state":"Open"}` | Door state (Open/Closed/Moving) |
| `MermaidsTale/CabinDoor/log` | Pub | `"Door opened"` | Event logging |

**Supported Commands:**
- `PING` — Heartbeat check
- `STATUS` — Query current state
- `RESET` — Clear internal state
- `PUZZLE_RESET` — Reset puzzle flags
- `OPEN` — Extend piston (timeout: 8s or 15s)
- `CLOSE` — Retract piston (timeout: 8s or 15s)
- `STOP` — Stop piston immediately

**How to Reset:**
```
Publish to: MermaidsTale/CabinDoor/command
Payload: {"action":"PUZZLE_RESET"}
```

**How to Test:**
1. **Door Opening:** Publish `{"action":"OPEN"}` to command. Monitor status for `"Moving"` then `"Open"`.
2. **Door Closing:** Publish `{"action":"CLOSE"}`. Expect `"Moving"` then `"Closed"`.
3. **Timeout Test:** Send `OPEN` command. If piston does not respond to limit switch, door should auto-stop after 8 seconds (primary) or 15 seconds (legacy).
4. **Emergency Stop:** While door is moving, publish `{"action":"STOP"}`. Should halt immediately.

**⚠️ Firmware Ambiguity:**
Two versions exist:
- **Primary repo:** v1.0.0, 8-second timeout, placeholder WiFi creds
- **Legacy repo (CabinDoor_S3):** v1.1.0, 15-second timeout, actual WiFi creds

Verify which version is deployed on your device.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- Linear actuator piston and relay hardware

**Physical Location:**
- Captain's quarters (entrance door or interior door)

**Source Code:**
- Primary: https://github.com/Alchemy-Escape-Rooms-Inc/CabinDoor
- Legacy: https://github.com/AlchemyEscapeRooms/CabinDoor_S3

---



## COVE AREA

### Overview
Cove features underwater-themed puzzles: sliding doors, driftwood magnetic sensing, balance scales, and luminous shells. Controlled by **Cove BAC** with mixed WiFi and standalone devices.

---

### 8. STAR-CHARTS (StarTable, StarTableSprite, Star Table Sprite player)

**Description:**
The Star Table constellation puzzle and its constellation screen. Guests place ten magnetic stars on the table; each completed constellation (turtle, mermaid, trident, seahorse, boat) should play a chime through M3 and advance the picture on the Sprite screen. It is THREE separate boxes and none of them is wired to the others except as noted below. Repo: `Alchemy-Escape-Rooms-Inc/StarTable` (clone at `Repos\StarTable`). Live notes: `Repos\StarTable\log.txt` is not used; the working session log is `C:\Users\Alchemy\log.txt`.

**The three parts:**

| Part | Board | Where | Talks to |
|---|---|---|---|
| Table controller (`Star_Table_FINAL`) | ESP32, no WiFi/MQTT | inside the table, runs 1422 NeoPixels + 10 hall sensors | pulses two wires to the bridge: OUT1 = star found, OUT2 = constellation solved |
| **StarTableBridge** (`StarTableBridge.ino` v1.2.1) | ESP32, WiFi | beside the table (moved 09-2026, see signal note) | publishes `MermaidsTale/StarTable/Star=triggered` and `MermaidsTale/StarTable/constellation=solved`; after 5 solves `status=SOLVED` (retained) |
| **StarTableSprite driver** (`StarTableSprite.ino` v3.0.0) | ESP32-S3, WiFi, IP 10.1.10.113 | at the Sprite player, a different part of the room | listens for the bridge's `constellation=solved` and presses the Sprite player's trigger input once per solve |
| Sprite player | MedeaWiz Sprite DV-S1 (HDMI video player, USB stick) | drives the constellation screen | no network; only the trigger/serial jack |

**MQTT topics:**
- `MermaidsTale/StarTable/Star` — `triggered` then `clear` 0.5 s later, per star. M3 event 157 "Star Twinkle" plays the chime.
- `MermaidsTale/StarTable/constellation` — `solved` then `clear`, per constellation. M3 event 158 plays the constellation chime. The Sprite driver advances the screen on this.
- `MermaidsTale/StarTable/status` — `ONLINE` / `SOLVED` (retained) / `OFFLINE` (LWT) / `HEARTBEAT:...` every 5 min. M3 event 45 "StarTable Solved" fires on `SOLVED`.
- `MermaidsTale/StarTable/command` — `PING`, `STATUS`, `RESET`, `PUZZLE_RESET`. M3 Cove Reset (event 63) sends `PUZZLE_RESET` here. **The Sprite driver also listens on this topic** for `PUZZLE_RESET` (listen only, never replies there).
- `MermaidsTale/StarTableSprite/command` — `PING`, `STATUS`, `RESET`, `PUZZLE_RESET`, `PULSE` (one uncounted test press), `ALIGN` (zero the count without pressing).
- `MermaidsTale/StarTableSprite/status`, `/log` — presence, heartbeat, and a log line for every press.
- M3 device 13 "Star Chart" must have topic `MermaidsTale/StarTable` (it was `StarChart` until 08-11-2026 and nothing ever fired).

**How the screen works now (v3.0.0, 2026-09-13) — READ THIS BEFORE TOUCHING THE SPRITE PLAYER:**

1. The Sprite player is in **Control Mode = Trigger Low with Interrupt**, Play Mode = Video Control Mode. It plays file 000 in a loop. Each time its trigger input is pulled to ground it plays the NEXT file on the stick (001, 002, 003, 004, then wraps to 001). That "next file per trigger" behaviour needs player firmware 20210416 or newer.
2. The driver board pulls GPIO 40 to ground for 300 ms per constellation. GPIO 40 goes to **screw 2** on the player's I/O plug, driver GND to **screw 4**. The line idles at 3.3 V.
3. Trigger mode plays a file ONCE and then falls back to 000. There is no "hold" in trigger mode. So the slide files on the stick are **10-minute loops** of each 30-second clip (originals in `Repos\StarTable\media\originals`). A slide therefore holds for 10 minutes, then the turtle returns until the next solve.
4. The driver counts presses (saved in flash, survives its own reboot). On `PUZZLE_RESET` it presses the remaining times so the player wraps back to "next = 001" for the next game. Those catch-up presses flash the remaining slides, and the last one stays up for up to 10 minutes.
5. **If anyone power-cycles the Sprite player**, its pointer goes back to 001 but the driver's count does not. Send `MermaidsTale/StarTableSprite/command = ALIGN` before the next game or the slides come up one off.

**Why it is done this way (the half-day lesson, 2026-09-13):**
- The Sprite player has a proper serial "loop this file and hold" command (0xFC), but it only works in **Control Mode = Serial Control**, and **this player will not save that setting**. You select Serial Control, press Enter, exit with Return-Return, go back in, and it reads Trigger Low with Interrupt again. Factory reset and a firmware reload (latest `Sprite_20210416_FW.img` from medeawiz.com/Downloads.html, copy to the stick, blue File key, select the .img, Yes) were NOT yet tried and are the only remaining software fixes; otherwise it is a faulty player.
- In any Trigger mode the player ignores serial bytes completely. A 2 ms serial burst is far too short to count as a button press, so serial commands do nothing at all, not even a flicker.
- Before that, the driver firmware (v2.x) was sending on **GPIO 4** while the wire was on **GPIO 40**, so nothing ever left the board. The driver's log said "advance -> file 001" every time and was telling the truth about itself; it cannot see the player. A log line from the driver proves nothing about the screen.
- Setup menu confusion: **Play Mode** = Video Control Mode (correct, leave it) and **Control Mode** = Serial Control / Trigger... are two different lines one after the other.
- Remote: generic DVD-type IR remote, must point straight at the front of the player. Test it with a phone camera (visible flash). No remote = no way to change Control Mode; the serial setup commands cannot change it. The serial path (v2 code) is kept in the driver behind `SPRITE_MODE_SERIAL` for a player that does hold Serial Control.

**Sprite player I/O plug (screw-terminal adaptor that came with it):**

| Screw | Function |
|---|---|
| 1 | 5 V out (100 mA max — do NOT power the ESP32-S3 from it) |
| 2 | Trigger input / serial RX into the player |
| 3 | Serial TX out of the player (status byte ~1/s in Serial mode) |
| 4 | Ground |

**Bridge problems (open as of 2026-09-13):**
- The bridge was moved to "a more accessible area" and has the worst WiFi signal in the building (-69 to -75 where every other board is -63 or better). At that spot it **freezes and watchdog-reboots every 1-2 minutes while guests are placing stars**, drops messages, and delays others by 20 s. Star chimes are lost outright during a freeze; constellations are caught later but the chime edge may be missed by M3 when `solved` and `clear` arrive in the same millisecond. Fix = move it back toward the access point / away from metal. A freeze that correlates with table activity (NeoPixel noise on the pulse wires) is a second suspect.
- Boot log line tells you why it restarted: `reset=POWERON` = someone re-plugged it, `reset=WDT` = it froze and rebooted itself, `reset=BROWNOUT` = power supply.
- v1.2.1 firmware details: pulses are caught by interrupts and must hold HIGH 100 ms to count; count is saved in flash; the table's OUT2 line held high too long inflates the count; after 5 it publishes SOLVED and goes quiet until `PUZZLE_RESET`.
- The bridge and the Sprite driver count separately. Any missed message leaves them out of step until the next `PUZZLE_RESET`. Planned fix: bridge publishes a retained count and the driver just shows that number.
- Broker log is the truth: `Alchemy-Grimoire\watchtower-v2\logs\mqtt_*.txt`. Grep `StarTable` and look at the timestamps before theorising.

**Quick checks (in this order):**
1. `mosquitto_pub -h 10.1.10.115 -t MermaidsTale/StarTable/command -m STATUS` → `PLAYING|n/5|UP:..|V1.2.1|RSSI..|IP..|RST..`. No reply = bridge dead or frozen; re-plug it and read `reset=` on its boot line.
2. `mosquitto_pub -h 10.1.10.115 -t MermaidsTale/StarTableSprite/command -m STATUS` → `IDLE|v3.0.0|..|SENT0/4|NEXT001|MODETRIGGER|Q0`.
3. Screen test without the table: `mosquitto_pub ... -t MermaidsTale/StarTable/constellation -m solved` → driver logs "trigger pulse n/4" and the next slide should play. If the log line appears but the screen does nothing: meter GPIO 40 (3.3 V idle, dips to 0 V for 0.3 s on `PULSE`), then the same at screw 2 vs screw 4, then the player's Control Mode.
4. After a player power-cycle: `... StarTableSprite/command -m ALIGN`.

**Status:** Screen path VERIFIED working 2026-09-13 16:42 (v3.0.0 + 10-minute slides). Bridge reliability at its current location is the open problem.

---

### 9. COVE-SLIDING-DOOR

**Description:**
A motorized horizontal sliding door that opens and closes to block/allow player passage. Uses H-bridge motor control with PWM ramp profile and dual limit switches.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v1.0.0 |
| Motor Driver | XY160D H-bridge (IN1/IN2/ENA) |
| PWM Frequency | 5 kHz, 8-bit resolution (0–255) |
| Motor Ramp Profile | 500ms ramp-up, 3s full speed, 500ms ramp-down |
| Limit Switches | 2x magnetic reed switches (OPEN=GPIO16, CLOSED=GPIO32) |
| Heartbeat | 30 seconds (non-standard; most use 5 min) |
| Protocol | Full Watchtower |

**Pin Assignments:**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| IN1 | Motor direction A | GPIO 2 | Digital out |
| IN2 | Motor direction B | GPIO 5 | Digital out |
| ENA | PWM speed control | GPIO 4 | PWM out |
| LIMIT_OPEN | Door fully open | GPIO 16 | Digital in (magnetic reed) |
| LIMIT_CLOSED | Door fully closed | GPIO 32 | Digital in (magnetic reed) |
| LED_OPEN | Status LED (open) | GPIO 21 | Digital out |
| LED_CLOSED | Status LED (closed) | GPIO 22 | Digital out |
| LED_MOVING | Status LED (moving) | GPIO 23 | Digital out |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/CoveDoor/command` | Sub | `{"action":"OPEN"}` | Receive commands |
| `MermaidsTale/CoveDoor/status` | Pub | `{"state":"Open"}` | Door state |
| `MermaidsTale/CoveDoor/log` | Pub | `"Door opening..."` | Event logging |
| `MermaidsTale/CoveDoor/limit` | Pub | `{"open":true,"closed":false}` | Limit switch states |

**How to Reset:**
```
Publish to: MermaidsTale/CoveDoor/command
Payload: {"action":"RESET"}
```

**How to Test:**
1. **Motor Control:** Publish `{"action":"OPEN"}`. Monitor LEDs; LED_MOVING should light, then LED_OPEN when door reaches limit.
2. **Ramp Profile:** Watch current draw during open command. Should see gradual increase (500ms), plateau (3s), then decrease (500ms).
3. **Limit Switches:** Manually push door to fully open/closed. Monitor `/limit` topic; one value should become `true`.
4. **Heartbeat:** Wait 30 seconds with no commands. Should see heartbeat publish on status topic.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- Motor, H-bridge, limit switches, LEDs

**Physical Location:**
- Cove area (underwater-themed entrance or passage)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/CoveDoor

---

### 10. DRIFTWOOD

**Description:**
A prop with embedded magnetic sensors that detects when magnets are brought into proximity. Players place magnetic tokens on hotspots; sensor array confirms correct placement. Uses 8x hall effect sensors for multi-point detection.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v2.2.5 |
| I2C Bus | SDA=GPIO15, SCL=GPIO18 |
| Hall Sensors | 8x ALS31300 at addresses 0x60–0x67 (one per address) |
| Trigger Threshold | Magnetic field magnitude >2000 (ADC units) |
| Status Updates | 60-second interval |
| Protocol | Full Watchtower |

**Pin Assignments:**

| Pin | Function | GPIO |
|---|---|---|
| I2C Data | SDA | GPIO 15 |
| I2C Clock | SCL | GPIO 18 |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/Driftwood/log` | Pub | `"Sensor 2 triggered"` | Debug event logging |
| `MermaidsTale/Driftwood/status` | Pub | `{"sensors":[0,0,1000,0,...]}` | All 8 sensor readings |
| `MermaidsTale/Driftwood/reset` | Sub | `true` | Reset puzzle state |
| `MermaidsTale/Driftwood/command` | Sub | `{"action":"PING"}` | Receive commands |
| `MermaidsTale/Driftwood/sensors` | Pub | `{"active":[2,5],"threshold":2000}` | Sensors exceeding threshold |

**Supported Commands:**
- `PING` — Heartbeat check
- `STATUS` — Query current sensor state
- `DIAG` — Extended diagnostics
- `RESET` — Clear puzzle flags
- `PUZZLE_RESET` — Full reset

**How to Reset:**
```
Publish to: MermaidsTale/Driftwood/command
Payload: {"action":"PUZZLE_RESET"}
```

**How to Test:**
1. **Sensor Baseline:** Publish `{"action":"DIAG"}`. Monitor `/status` for baseline readings (all near 0 with no magnet nearby).
2. **Magnet Detection:** Bring a strong magnet close to driftwood. Monitor `/sensors` topic; affected sensor value should exceed 2000.
3. **Multi-Sensor Test:** Place magnets on multiple hotspots. `/status` should show values >2000 for each active sensor.
4. **Threshold Tuning:** If sensitivity is wrong, threshold (2000) is configurable in firmware.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- 8x ALS31300 hall sensors (I2C)
- Magnetic tokens or magnets for interaction

**Physical Location:**
- Cove area (centerpiece or wall installation)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Driftwood

---

### 11. BALANCING-SCALE

**Description:**
A mechanical balance scale prop with RFID readers. Players place tagged items on each side. The scale must balance (equal weight or RFID tag count) to solve the puzzle.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | Arduino Nano |
| WiFi/MQTT | NONE — Standalone (serial only) |
| Serial Baud Rate | 9600 |
| RFID Reader Type | ID-12LA (125 kHz) |
| RFID Reader 1 | SoftwareSerial pins 9–10 |
| RFID Reader 2 | SoftwareSerial pins 11–12 |
| Buttons | RST=GPIO 4, CHK=GPIO 5 |
| Servo | Pin UNDEFINED — **BUG** |
| Puzzle Logic | Check if balance matches expected weight |

**Pin Assignments:**

| Pin | Function | Type |
|---|---|---|
| 4 | Reset button | Digital in |
| 5 | Check/submit button | Digital in |
| 9–10 | RFID Reader 1 (soft serial) | Rx/Tx |
| 11–12 | RFID Reader 2 (soft serial) | Rx/Tx |
| ? (UNDEFINED) | Servo control | Digital out |

**MQTT Topics:**
None — Standalone device (no network).

**⚠️ CRITICAL BUGS:**

| Issue | Impact | Workaround |
|---|---|---|
| `SERVO_PIN` undefined | Code will NOT compile | Define `#define SERVO_PIN X` before `Servo` initialization |
| `isAlreadyStored()` always returns `false` | Duplicate items may not register correctly | Implement item tracking array |
| `checkSuccess()` empty function | Puzzle completion never triggers | Add balance verification logic |

**How to Reset:**
```
Press RST button on device
```

**How to Test:**
**CANNOT FULLY TEST** — Code has critical compilation errors. Must fix SERVO_PIN and function implementations first.

**Partial Testing (after fixes):**
1. **RFID Reading:** Place tagged item on Reader 1 side. Monitor serial output for tag ID.
2. **Balance Check:** Place equal weights on both sides. Press CHK button. Servo should move to indicate balanced (after implementation).

**Dependencies:**
- Arduino Nano microcontroller
- 2x ID-12LA RFID readers
- Servo motor (pin TBD)
- Balance scale mechanism

**Physical Location:**
- Cove area (table-mounted puzzle)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Balancing-Scale

**Deployment Status:** ⚠️ **NOT PRODUCTION READY** — Critical bugs prevent compilation and execution.

---

### 12. LUMINOUS-SHELL (SeaShells)

**Description:**
Decorative shells that light up (glow) when a player's hand is brought very close (proximity detected). Uses time-of-flight sensor and addressable LED for visual effect.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32 or ESP8266 (unclear) |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| I2C Sensor | VL53L0X time-of-flight at default address 0x29 |
| Trigger Distance | 50 mm (very close proximity) |
| Light-Up Duration | 5000 ms (5 seconds) |
| LED Pin | UNDEFINED — **BUG** |

**Pin Assignments:**

| Pin | Function | Status |
|---|---|---|
| Default SDA | I2C data | Standard |
| Default SCL | I2C clock | Standard |
| Light control | LED output | **NOT DEFINED** |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/Shell1` | Pub | `"LightingUp"` | Shell lighting event |
| `MermaidsTale/Shell1` | Pub | `"TurnedOff"` | Shell turning off event |
| `MermaidsTale/Shell1` | Pub | `"Connected!"` | Boot message |
| `MermaidsTale/Shell1` | Pub | `"Searching"` | Waiting for proximity |
| `MermaidsTale/#` | Sub | (any) | Subscribe to all game events |

**⚠️ CRITICAL BUGS:**

| Issue | Impact | Workaround |
|---|---|---|
| `lightPin` UNDEFINED | Code will NOT compile | Add `#define lightPin GPIO_X` |
| Variable name mismatch (mqtt vs client) | Undefined symbol error | Standardize variable throughout |

**How to Reset:**
Not implemented. Requires firmware update and bug fixes.

**How to Test:**
**CANNOT TEST** — Code does not compile. Must fix lightPin definition and variable naming first.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- VL53L0X time-of-flight sensor
- Addressable LED (WS2812B or similar)

**Physical Location:**
- Cove area (multiple shells scattered on surfaces)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/LuminousShell

**Deployment Status:** ⚠️ **NOT PRODUCTION READY** — Critical compilation errors prevent deployment.

---

## JUNGLE AREA

### Overview
Jungle Area contains mystical puzzles: hieroglyphic panels, sun dial mechanisms, water fountain servo displays, and a motorized door. Controlled by **Jungle BAC**.

---

### 13. JUNGLE-DOOR

**Description:**
A motorized sliding door to the jungle area. Features PWM motor control, limit switches, and status LEDs. Similar to CoveSlidingDoor but with laser-based limit detection.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |
| Firmware Version | v3.3.0 |
| Motor Driver | MD13S (direction + PWM) |
| Motor Speed | 150 / 255 (59% max speed) |
| Limit CLOSED | Laser beam sensor (analog, GPIO 7) with ADC threshold 3600 |
| Limit OPEN | Standard digital switch (GPIO 8) |
| Heartbeat | 30 seconds |
| Protocol | Full Watchtower |
| **NOTE:** Topic name is `JungleDoor` (no space) — fixed in firmware v3.3.0 |

**Pin Assignments:**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| DIR | Motor direction | GPIO 4 | Digital out |
| PWM | Motor speed | GPIO 6 | PWM out |
| LIMIT_OPEN | Open limit switch | GPIO 8 | Digital in |
| LIMIT_CLOSED | Closed limit (laser) | GPIO 7 | Analog in (ADC) |
| LED_OPEN | Status LED (open) | GPIO 21 | Digital out |
| LED_CLOSED | Status LED (closed) | GPIO 22 | Digital out |
| LED_MOVING | Status LED (moving) | GPIO 23 | Digital out |

**MQTT Topics:**

| Topic | Direction | Payload Example | Purpose |
|---|---|---|---|
| `MermaidsTale/JungleDoor/command` | Sub | `{"action":"OPEN"}` | Receive commands |
| `MermaidsTale/JungleDoor/status` | Pub | `{"state":"Open"}` | Door state |
| `MermaidsTale/JungleDoor/log` | Pub | `"Door moving..."` | Event logging |
| `MermaidsTale/JungleDoor/limit` | Pub | `{"open":true,"closed":false}` | Limit switch state |

**How to Reset:**
```
Publish to: MermaidsTale/JungleDoor/command
Payload: {"action":"RESET"}
```

**How to Test:**
1. **Door Opening:** Publish `{"action":"OPEN"}` to command. LED_MOVING should light; then LED_OPEN when fully open.
2. **Laser Limit:** Close door manually until laser beam is interrupted. Monitor `/limit` topic; `closed` should become `true`.
3. **Motor Speed:** Door should move at 150/255 speed (about 59%). Adjust in firmware if too slow/fast.
4. **Heartbeat:** Every 30 seconds, device publishes heartbeat on status.

**Topic Name:** Use `JungleDoor` (no space). Fixed in firmware v3.3.0 — the space bug is resolved.

**Dependencies:**
- WiFi network (AlchemyGuest)
- MQTT broker (10.1.10.115:1883)
- MD13S motor driver
- Laser sensor + receiver for closed limit

**Physical Location:**
- Jungle area (entrance or passage door)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/JungleDoor

---

### 14. RUINS-WALL-PANEL (Hieroglyphics)

**Description:**
An interactive wall panel with a 5x7 grid of illuminated buttons and LEDs. Players press buttons in a specific sequence to solve the puzzle. Features RGB addressable LEDs and sound feedback.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | Arduino Mega 2560 |
| WiFi/MQTT | NONE — Standalone (serial only) |
| Serial Baud Rate | 9600 |
| Button Matrix | 5 rows × 7 columns (custom wired) |
| LED Type | 910x WS2812B (Neopixel) RGB addressable LEDs |
| LED Library | FastLED |
| LED Control Pin | A0 (analog pin used as digital) |
| Correct Sequence | 11 → 9 → 0 → 4 → 15 → 14 → 20 (7-button sequence) |

**Pin Assignments:**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| A0 | WS2812B data (LED control) | A0 | Digital out |
| Row outputs | Matrix row drivers | 9–13 | Digital out |
| Column inputs | Matrix column sensors | 2–8 | Digital in |

**Row / Column Mapping:**

| Row Pin | GPIO | Columns Driven |
|---|---|---|
| Row 1 | 9 | Cols 2–8 |
| Row 2 | 10 | Cols 2–8 |
| Row 3 | 11 | Cols 2–8 |
| Row 4 | 12 | Cols 2–8 |
| Row 5 | 13 | Cols 2–8 |

**MQTT Topics:**
None — Standalone device (no network).

**Serial Commands:**
Not documented in firmware. Likely controlled via button matrix only.

**How to Reset:**
Power-cycle the Arduino Mega. No remote reset command.

**How to Test:**
1. **Button Matrix:** Use Arduino IDE serial monitor (9600 baud). Physically press each button; watch for acknowledgment in code (may require adding debug serial prints).
2. **LED Test:** Run FastLED color test (cycle through colors). All 910 LEDs should light.
3. **Sequence Entry:** Press buttons in correct sequence (11→9→0→4→15→14→20). Monitor for puzzle completion indicator (sound, LED pattern, or serial output).

**Dependencies:**
- Arduino Mega 2560
- FastLED library (version TBD)
- 910x WS2812B LEDs
- 5×7 button matrix wiring
- Optional audio speaker (if sound feedback is implemented)

**Physical Location:**
- Jungle area (wall-mounted panel, "hieroglyphics" or "rune" themed)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Ruins-Wall-Panel

---

### 15. SUN-DIAL

**Description:**
A complex puzzle using two concentric rotating dials controlled by stepper motors. Players align the dials to one of 5 correct combinations. Sensors detect beam position; PWM controls determine success.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | TWO BOARDS — Arduino Mega (sensors) + Arduino Uno (motors) |
| WiFi/MQTT | NONE — Standalone (serial only) |
| Serial Baud Rate | Not specified |
| Stepper Motors | 2x stepper (outer and inner dials) |
| Motor Driver | 2x PCA9685 PWM drivers at 0x40 and 0x41 (I2C) |
| IR Sensors | 4x infrared sensors (outer & inner, counter and 0° reference) |
| Correct Combinations | 5 valid pairings: (2,3), (3,6), (6,7), (8,9), (9,1) |

**Pin Assignments — Board 1 (Mega, Sensors):**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| IR_OUTER_COUNTER | Outer dial position (counter ref) | A3 | Analog in |
| IR_OUTER_0 | Outer dial at 0° | A2 | Analog in |
| IR_INNER_COUNTER | Inner dial position (counter ref) | A1 | Analog in |
| IR_INNER_0 | Inner dial at 0° | A0 | Analog in |
| OUTER_CONTROL | Outer motor control | 9 | PWM out |
| INNER_CONTROL | Inner motor control | 8 | PWM out |
| STEPPER_O_ENABLE | Outer stepper enable | 11 | Digital out |
| STEPPER_I_ENABLE | Inner stepper enable | 10 | Digital out |
| CHOOSE | Selection button | 12 | Digital in |
| STEPPERS_ENABLE | Master enable | 13 | Digital out |
| HOUSE pins 1–6 | House position detectors | 2–7 | Digital in |

**Pin Assignments — Board 2 (Uno, Motors):**

| Pin | Function | GPIO | Type |
|---|---|---|---|
| OUTER_CONTROL | Outer stepper control | 11 | PWM out |
| INNER_CONTROL | Inner stepper control | 10 | PWM out |
| ROTATE_INNER | Inner stepper CW/CCW | 4 | Digital out |
| ROTATE_OUTER | Outer stepper CW/CCW | 5 | Digital out |
| OUTER_STEPPER_DIR | Outer stepper direction | A0 | Digital out |
| OUTER_STEPPER_STEP | Outer stepper step pulse | A1 | PWM out |
| INNER_STEPPER_DIR | Inner stepper direction | A2 | Digital out |
| INNER_STEPPER_STEP | Inner stepper step pulse | A3 | PWM out |

**I2C Devices (PCA9685 PWM Drivers):**

| Address | Purpose | Channels |
|---|---|---|
| 0x40 | PWM control 1 | 0–15 |
| 0x41 | PWM control 2 | 0–15 |

**MQTT Topics:**
None — Standalone device.

**⚠️ CRITICAL BUGS:**

| Line | Issue | Impact | Fix |
|---|---|---|---|
| 262 | `motor_speed = = value` (double `=`) | Assignment fails; variable not set | Change to `motor_speed = value` |
| 280 | `angle_increment = = 1` | Increment not applied | Change to `angle_increment = 1` |
| 297 | `timeout_ms = = 5000` | Timeout not set | Change to `timeout_ms = 5000` |
| 317 | `success = = true` | Success flag never set | Change to `success = true` |

**How to Reset:**
Power-cycle both Arduino boards.

**How to Test:**
1. **IR Sensor Baseline:** Without dials, monitor analog values on A0–A3. Should be steady ~0 or ~1023 depending on light.
2. **Stepper Motor Test:** Send PWM command to outer/inner control pins. Dials should rotate.
3. **Position Sensing:** Rotate outer dial slowly; IR_OUTER_COUNTER and IR_OUTER_0 should toggle as dial rotates past reference points.
4. **Correct Combination:** Manually align dials to (2,3). Press CHOOSE button (GPIO 12). Device should confirm success (if bugs are fixed).

**⚠️ Note:**
Code will NOT execute correctly until all 4 assignment operator bugs are fixed (lines 262, 280, 297, 317). Must recompile and re-upload firmware.

**Dependencies:**
- 2x Arduino boards (Mega + Uno)
- 2x PCA9685 I2C PWM drivers
- 2x stepper motors + drivers
- 4x IR sensors
- 6x house/position detectors

**Physical Location:**
- Jungle area (centerpiece or pedestal, "sun dial" or "astrology" themed)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Sun-Dial

**Deployment Status:** ⚠️ **NOT PRODUCTION READY** — 4 critical assignment operator bugs must be fixed.

---

### 16. WATER-FOUNTAIN

**Description:**
A decorative water fountain with servo-controlled valves/nozzles. Three potentiometers allow players to control the height and spray pattern of water jets. Primarily a visual/interactive element.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | Arduino Uno or Nano |
| WiFi/MQTT | NONE — Standalone (serial only) |
| PWM Driver | PCA9685 at I2C address 0x40 |
| Servos Controlled | 10 total (channels 0–9 on PCA9685) |
| Potentiometers | 3x analog input for user control |
| Servo Mapping | Pot1 → Servos 0,1,3,6 / Pot2 → Servos 2,4,7 / Pot3 → Servos 5,8,9 |
| Serial | DISABLED (all serial code commented out) |

**Pin Assignments:**

| Pin | Function | Type |
|---|---|---|
| A0 | Potentiometer 1 input | Analog in |
| A1 | Potentiometer 2 input | Analog in |
| A2 | Potentiometer 3 input | Analog in |
| I2C SDA | PCA9685 data | Standard |
| I2C SCL | PCA9685 clock | Standard |

**PCA9685 Servo Channels:**

| Channel | Servos | Controlled By |
|---|---|---|
| 0 | Servo 0 | Pot 1 |
| 1 | Servo 1 | Pot 1 |
| 2 | Servo 2 | Pot 2 |
| 3 | Servo 3 | Pot 1 |
| 4 | Servo 4 | Pot 2 |
| 5 | Servo 5 | Pot 3 |
| 6 | Servo 6 | Pot 1 |
| 7 | Servo 7 | Pot 2 |
| 8 | Servo 8 | Pot 3 |
| 9 | Servo 9 | Pot 3 |

**MQTT Topics:**
None — Standalone device.

**Serial Commands:**
**DISABLED** — All serial communication code is commented out.

**How to Reset:**
Power-cycle the Arduino Uno/Nano.

**How to Test:**
1. **Potentiometer Reading:** Manually edit firmware to uncomment serial debug and re-upload. Read A0–A2 values; should vary 0–1023 as you turn pots.
2. **Servo Movement:** Move Pot1. Servos 0, 1, 3, 6 should move (arm or spray nozzles).
3. **Multi-Pot Test:** Move Pot2; servos 2, 4, 7 should respond. Move Pot3; servos 5, 8, 9 should respond.
4. **Fountain Effect:** Observe water spray height/pattern change as you adjust pots.

**Dependencies:**
- Arduino Uno or Nano
- PCA9685 I2C PWM driver
- 10x servo motors
- 3x potentiometers
- Water pump and nozzle system

**Physical Location:**
- Jungle area (centerpiece fountain display)

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/WaterFountain

---

### 17. AUTOMATIC-SLIDING-DOOR

**Description:**
⚠️ **Two conflicting implementations exist.** Hardware and firmware details are inconsistent.

**Status — Primary Version:**

| Component | Specification |
|---|---|
| Microcontroller | Arduino UNO R4 WiFi |
| WiFi/MQTT | NONE (this version) |
| Serial | 9600 baud (assumed) |

**Status — Debug Version:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | 10.1.10.115:1883 |

**Arduino R4 Pins:**

| Pin | Function | Type |
|---|---|---|
| 4 | Motor direction (DIR) | Digital out |
| 6 | Motor PWM | PWM out |
| A2 | Open command button | Analog in |
| A4 | Close command button | Analog in |
| 9 | Open limit switch | Digital in |
| 8 | Closed limit switch | Digital in |
| 10 | Open status LED | Digital out |
| 11 | Closed status LED | Digital out |
| 12 | Moving status LED | Digital out |

**ESP32 Pins:**

| Pin | Function | Type |
|---|---|---|
| 4 | Right PWM (RPWM) | PWM out |
| 5 | Left PWM (LPWM) | PWM out |
| 1 | Open command | Digital in |
| 2 | Close command | Digital in |
| 9 | Open limit | Digital in |
| 18 | Closed limit | Digital in |
| 10 | Open LED | Digital out |
| 11 | Closed LED | Digital out |
| 12 | Moving LED | Digital out |

**How to Determine Which Version is Deployed:**
1. Power on the device.
2. Look for LED indicators or WiFi connection attempt.
3. Check for MQTT messages on `MermaidsTale/cove_sliding_door/#` (indicates ESP32 version).
4. If silent and no WiFi, likely Arduino R4 version.

**⚠️ Ambiguity Note:**
It is **unclear which version is in production**. Contact your hardware lead to confirm. Both versions may need to be supported.

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/AutomaticSlidingDoor

**Deployment Status:** ⚠️ **REQUIRES CLARIFICATION** — Determine which board/firmware is deployed on your system.

---

## CROSS-ROOM SYSTEMS

### Overview
These systems provide game-wide orchestration, monitoring, and feedback. Not tied to a specific room area.

---

### 18. WATCH-TOWER (System Health Monitoring)

**Description:**
A Python Flask-based web dashboard that monitors the health and status of all MQTT-connected devices. Displays device heartbeats, connectivity, and command/response latencies. Critical for ops staff to spot problems.

**Technology Stack:**

| Component | Specification |
|---|---|
| Language | Python 3 |
| Framework | Flask (web server) |
| MQTT Client | paho-mqtt |
| Dashboard | HTML/CSS/JavaScript (frontend) |
| Data Storage | Local JSON or SQLite (TBD) |
| Port | TBD (likely 5000 or 8080) |

**Monitored Devices:**
All devices publishing to `MermaidsTale/#` topics. WatchTower subscribes to all topics and tracks:
- **Last heartbeat timestamp**
- **WiFi connection status**
- **MQTT publish/subscribe activity**
- **Command latency** (time from command publish to status response)
- **Error count**

**Configuration:**

| Setting | Value |
|---|---|
| MQTT Host | 10.1.10.115 |
| MQTT Port | 1883 |
| MQTT Subscribe | `MermaidsTale/#` |
| Update Interval | 5–10 seconds (TBD) |

**Access:**
WatchTower dashboard URL: **TBD** (likely `http://127.0.0.1:5000` or similar)

**How to Test:**
1. **Launch WatchTower:** Run Python Flask app. Server should start on configured port.
2. **View Dashboard:** Open browser to WatchTower URL. Should display list of all active devices.
3. **Device Status:** Click on any device. Should show last heartbeat, active commands, and history.
4. **Send Test Command:** From WatchTower UI, publish a PING command to a device. Monitor response latency.

**Documentation:**
WatchTower configuration and deployment details covered in **system-checker-integration.md** (separate document).

**Source Code:**
WatchTower is a Python dashboard; not a separate GitHub repo. Likely integrated into main repo or operations manual directory.

---

### 19. CAISE / ELEVEN-LABS AVATAR PROJECT (AI Game Master)

**Description:**
An interactive AI game master powered by ElevenLabs text-to-speech and Anthropic Claude. Provides real-time hints, flavor text, and feedback to players via speakers. Runs Node.js application with MQTT integration.

**Technology Stack:**

| Component | Specification |
|---|---|
| Language | Node.js (JavaScript) |
| MQTT Broker | 10.1.10.228:1883 (separate from main 10.1.10.115:1883!) |
| AI Provider | Anthropic Claude API |
| Voice Provider | ElevenLabs text-to-speech API |
| Port | TBD (web interface or direct socket) |

**⚠️ CRITICAL SECURITY ISSUE:**
This repository **CONTAINS EXPOSED API KEYS** in the source code. Do NOT commit or push to public GitHub without removing all credentials.

**Typical Flow:**
1. Game event occurs (device status change).
2. MQTT message published to 10.1.10.228:1883.
3. CAISE listens and passes context to Claude API.
4. Claude generates contextual flavor text or hint.
5. ElevenLabs converts response to voice.
6. Audio played through speaker system.

**MQTT Topics (10.1.10.228:1883):**
Separate MQTT broker from main room system. Topics likely follow `game/#` or `ai_master/#` convention (exact topics TBD).

**Configuration (Sensitive):**

| Key | Status |
|---|---|
| ElevenLabs API Key | ⚠️ EXPOSED in repo |
| Anthropic API Key | ⚠️ EXPOSED in repo |
| MQTT Username/Password | TBD |

**Action Required:**
1. **Immediately rotate all API keys** from ElevenLabs and Anthropic.
2. **Remove keys from GitHub** — use `.env` file or secrets manager.
3. **Re-upload firmware/config** with new keys only.

**How to Test:**
1. **MQTT Connection:** Subscribe to 10.1.10.228:1883. Publish a game event. Should see CAISE acknowledgment.
2. **Voice Playback:** Trigger a hint or flavor text event. Speaker system should play voice-synthesized audio.
3. **Latency:** Measure time from event to voice output. Should be <3 seconds.

**Dependencies:**
- Node.js runtime
- ElevenLabs API account (with credits)
- Anthropic Claude API account
- Separate MQTT broker (10.1.10.228:1883)
- Audio output speaker system

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Eleven-Labs-Avatar-Project

**Deployment Status:** ⚠️ **SECURITY ISSUE** — API keys exposed. Must be rotated and secured before production use.

---

## STANDALONE DEVICES (No WiFi/MQTT)

These devices operate independently with no network connectivity. Control is via physical buttons, serial commands, or BAC relays.

### Overview Table:

| Device | Board | Control Method | Location |
|---|---|---|---|
| Captain's Cuffs | Arduino Mega | Serial (9600) + buttons | Captain's Quarters |
| Ruins-Wall-Panel | Arduino Mega | Button matrix | Jungle |
| Sun-Dial | Mega + Uno | Buttons + potentiometers | Jungle |
| Water-Fountain | Uno/Nano | Potentiometers | Jungle |
| Balancing-Scale | Arduino Nano | RFID + buttons | Cove |

**Serial Connection Details:**

| Device | Port | Baud Rate | Connector |
|---|---|---|---|
| Captain's Cuffs | COM? (TBD) | 9600 | DB-9 or USB |
| Ruins-Wall-Panel | COM? (TBD) | 9600 | DB-9 or USB |
| Sun-Dial (Board 1 & 2) | COM? (TBD) | TBD | DB-9 or USB |
| Balancing-Scale | COM? (TBD) | 9600 | USB (Nano) |

**Diagnostic Tools:**
- **Arduino IDE Serial Monitor** — Monitor output and send commands
- **PuTTY** — Alternative serial terminal (Windows)
- **screen** — Serial terminal on Linux/Mac
  ```bash
  screen /dev/ttyUSB0 9600  # Linux
  screen /dev/tty.usbserial 9600  # macOS
  ```

---

## LEGACY & DEPRECATED HARDWARE

### 20. ORIGINAL-CANNON-LEGACY

**Description:**
The original cannon implementation, replaced by **New-Cannons** (v3.2.0). Do NOT use in production. Included here for historical reference and parts salvage.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32 (ESP-IDF, C firmware) |
| MQTT Broker | ⚠️ **WRONG IP:** 10.1.10.130:1883 (should be 10.1.10.115:1883) |
| Firmware Protocol | NONE (no WiFi reconnect, no heartbeat, no PING/PONG) |
| I2C Sensors | VL6180X at 0x29, ALS31300 at 0x01 |
| DMX Interface | TX=45, RX=46, EN=47 (rarely used) |

**MQTT Topics:**

| Topic | Direction | Purpose |
|---|---|---|
| `MermaidsTale/Cannon{id}Loaded` | Pub | Loaded state |
| `MermaidsTale/Cannon{id}Fired` | Pub | Fire event |
| `MermaidsTale/Cannon{id}Hor` | Pub | Horizontal position (unknown unit) |

**Why Deprecated:**
- Wrong MQTT broker IP
- No health monitoring (no heartbeat, PING/PONG)
- Missing safety features
- Replaced by New-Cannons with Full Watchtower protocol

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/Original_Cannon_Legacy

**Status:** **LEGACY — DO NOT DEPLOY**

---

### 21. HALL-SENSOR-WITH-MQTT

**Description:**
An alternative implementation of hall sensor detection, related to the **Driftwood** puzzle. Similar purpose but different codebase.

**Hardware Specifications:**

| Component | Specification |
|---|---|
| Microcontroller | ESP32-S3 (ESP-IDF, C firmware) |
| WiFi Network | AlchemyGuest / VoodooVacation5601 |
| MQTT Broker | mqtt://10.1.10.115:1883 |
| I2C Sensors | 8x ALS31300 at addresses 0x60–0x67 |
| Trigger Threshold | 3000 (slightly higher than Driftwood's 2000) |

**MQTT Topics:**

| Topic | Direction | Payload | Purpose |
|---|---|---|---|
| `sensor/status` | Pub | `{"sensors":[...]}` | Current sensor readings |
| `sensor/debug` | Pub | Debug messages | Detailed logging |
| `sensor/reset` | Sub | `true` | Reset puzzle state |
| `sensor/status/request` | Sub | `true` | Request status update |
| `alchemy/driftwood` | Pub | `"solved"` | Driftwood puzzle completion |

**Relationship to Driftwood:**
Unknown. May be:
- Alternative implementation for testing
- Separate puzzle using hall sensors
- Backup hardware
- Work-in-progress replacement

**Status:** Unclear. Verify with your lead whether this is deployed alongside Driftwood.

**Source Code:**
https://github.com/Alchemy-Escape-Rooms-Inc/hall-sensor-with-mqtt

---

## DEVICES IN WATCHTOWER CONFIG WITH NO REPO FOUND

The following devices are listed in WatchTower's configuration file but have **NO corresponding GitHub repository**. Firmware status, implementation details, and specifications are **unknown**.

| Device Name | Likely Function | Status |
|---|---|---|
| **Hieroglyphics** | Button puzzle panel (possibly Ruins-Wall-Panel?) | ⚠️ NO REPO |
| **TridentReveal** | Unknown puzzle mechanic | ⚠️ NO REPO |
| **SeaShells** | Interactive shells (possibly LuminousShell?) | ⚠️ NO REPO |
| **StarCharts** | Navigation/astronomy puzzle | ⚠️ NO REPO |
| **MonkeyTombEntrance** | Decorative or entrance mechanic | ⚠️ NO REPO |
| **TridentCabinet** | Locking cabinet or display | ⚠️ NO REPO |
| **MagicMirror2** | Interactive mirror prop | ⚠️ NO REPO |
| **StarTable** | Puzzle table or display | ⚠️ NO REPO |
| **TridentAltar** | Decorative or interaction point | ⚠️ NO REPO |

**Action Required:**
1. **Search internal documentation** for these device names.
2. **Check hardware directly** — may have unique board labels or serial numbers.
3. **Query your team** — these may be in-progress, decommissioned, or using alternate naming.
4. **Update this manual** once firmware repositories are located or status confirmed.

---

## KNOWN ISSUES & CRITICAL BUGS

This section summarizes all critical issues found during the audit. **DO NOT deploy devices with unresolved critical bugs.**

### Compilation Errors (Cannot Deploy)

| Device | Bug | Impact | Fix |
|---|---|---|---|
| **ShipNavMap** | CGRB typo (should be CRGB) | Code will NOT compile | Change `AddressableStrip<CGRB>` to `CRGB` |
| **ShipNavMap** | Variable mismatch (mqtt vs client) | Undefined symbol | Standardize variable names |
| **ShipNavMap** | Backwards reconnect logic | Device disconnects unexpectedly | Review WiFi reconnect conditional |
| **LuminousShell** | `lightPin` UNDEFINED | Code will NOT compile | Add `#define lightPin GPIO_X` |
| **LuminousShell** | Variable mismatch (mqtt vs client) | Undefined symbol | Standardize variable names |
| **BalancingScale** | `SERVO_PIN` UNDEFINED | Code will NOT compile | Define `#define SERVO_PIN X` |
| **SunDial** | 4x double `==` instead of `=` (lines 262, 280, 297, 317) | Assignment operators fail; code executes but variables not set | Change `==` to `=` on all 4 lines |

### Logic Errors (Runs but Fails Puzzle)

| Device | Bug | Impact | Workaround |
|---|---|---|---|
| **BalancingScale** | `isAlreadyStored()` always returns `false` | Duplicate items don't register | Implement item tracking array |
| **BalancingScale** | `checkSuccess()` empty function | Puzzle never completes | Add balance verification logic |

### Protocol / Configuration Issues

| Device | Issue | Impact | Action |
|---|---|---|---|
| **JungleDoor** | Topic has space: `Jungle Door` not `JungleDoor` | Easy to typo in MQTT commands | Always use space in topic; document prominently |
| **OriginalCannonLegacy** | MQTT broker wrong IP (10.1.10.130 instead of 10.1.10.115) | Cannot connect to game system | Do NOT use; replace with New-Cannons |
| **WaterFountain** | Serial communication DISABLED (all code commented out) | Cannot send commands via serial | Uncomment serial code if remote control needed |
| **CabinDoor (primary)** | WiFi creds are PLACEHOLDER ("YOUR_SSID"/"YOUR_PASSWORD") | Cannot connect to network | Use legacy CabinDoor_S3 repo or update firmware |
| **CabinDoor** | Two firmware versions with different timeouts (8s vs 15s) | Unclear which is production | Verify firmware version deployed on hardware |
| **ElevenLabsAI** | API keys exposed in source code | Severe security breach | Rotate all API keys; use .env file |
| **WirelessMotionSensor** | No MQTT heartbeat, PING/PONG, or RESET commands | No health monitoring | Consider upgrading to Full Watchtower protocol |

### Ambiguous Implementations

| Device | Issue | Action |
|---|---|---|
| **AutomaticSlidingDoor** | Two conflicting board types (Arduino R4 vs ESP32) | Determine which version is deployed |
| **LuminousShell vs SeaShells** | Two possible names for same device? | Clarify naming convention |
| **ShipNavMap / ESP8266 vs ESP32** | Board type unclear in firmware | Check PCB silkscreen or run device test |
| **hall-sensor-with-mqtt** | Unclear relationship to Driftwood | Determine if both should be deployed |

---

## QUICK REFERENCE

### Device Health Checklist

Use this table during shift setup or troubleshooting.

| Device | WiFi Status | MQTT Reachable | Recent Heartbeat | Functional? | Notes |
|---|---|---|---|---|---|
| Cannon1 | ☐ | ☐ | ☐ | ☐ | v3.2.0 |
| Cannon2 | ☐ | ☐ | ☐ | ☐ | v3.2.0 |
| ShipMotion1 | ☐ | ☐ | ☐ | ☐ | ESP8266; no heartbeat |
| ShipMotion2 | ☐ | ☐ | ☐ | ☐ | ESP8266; no heartbeat |
| ShipMotion3 | ☐ | ☐ | ☐ | ☐ | ESP8266; no heartbeat |
| BarrelPiston | ☐ | ☐ | ☐ | ☐ | ESP32 |
| ShipNavMap | ☐ | ☐ | ☐ | ☐ | **BLOCKED:** Compilation errors |
| BlueCompass | ☐ | ☐ | ☐ | ☐ | v1.0.0 |
| RoseCompass | ☐ | ☐ | ☐ | ☐ | v1.0.0 |
| SilverCompass | ☐ | ☐ | ☐ | ☐ | v1.0.0 |
| CaptainsCuffs | ☐ | N/A | N/A | ☐ | Serial only |
| CabinDoor | ☐ | ☐ | ☐ | ☐ | **Firmware ambiguity** |
| CoveSlidingDoor | ☐ | ☐ | ☐ | ☐ | v1.0.0; 30s heartbeat |
| Driftwood | ☐ | ☐ | ☐ | ☐ | v2.2.5 |
| BalancingScale | ☐ | N/A | N/A | ☐ | **BLOCKED:** Logic errors |
| LuminousShell | ☐ | ☐ | ☐ | ☐ | **BLOCKED:** lightPin undefined |
| JungleDoor | ☐ | ☐ | ☐ | ☐ | v3.3.0 |
| RuinsWallPanel | ☐ | N/A | N/A | ☐ | Serial only |
| SunDial | ☐ | N/A | N/A | ☐ | **BLOCKED:** 4x assignment bugs |
| WaterFountain | ☐ | N/A | N/A | ☐ | Serial disabled |
| AutomaticSlidingDoor | ☐ | ☐ or N/A | ☐ or N/A | ☐ | **Ambiguous:** Verify board type |

### MQTT Broker Endpoints

| Purpose | Host | Port | Protocol |
|---|---|---|---|
| **Main Game System** | 10.1.10.115 | 1883 | MQTT 3.1.1 |
| **AI Game Master (CAISE)** | 10.1.10.228 | 1883 | MQTT 3.1.1 |

### WiFi Network

| Parameter | Value |
|---|---|
| SSID | AlchemyGuest |
| Password | VoodooVacation5601 |
| Frequency | 2.4 GHz (verify no 5 GHz forcing) |

### Serial Connections (Standalone Devices)

| Device | Baud Rate | Connection Type |
|---|---|---|
| Captain's Cuffs | 9600 | USB or DB-9 |
| Ruins-Wall-Panel | 9600 | USB or DB-9 |
| Sun-Dial | TBD | USB or DB-9 |
| Balancing-Scale | 9600 | USB (Nano) |

### Common Commands (MQTT)

| Command | Topic | Payload | Purpose |
|---|---|---|---|
| PING | `{Device}/command` | `{"action":"PING"}` | Check connectivity |
| RESET | `{Device}/command` | `{"action":"RESET"}` | Clear internal state |
| STATUS | `{Device}/command` | `{"action":"STATUS"}` | Query current state |
| PUZZLE_RESET | `{Device}/command` | `{"action":"PUZZLE_RESET"}` | Reset puzzle flags |

### Firmware Versions Summary

| Device | Version | Status |
|---|---|---|
| New-Cannons | v3.2.0 | ✓ Current |
| Compass | v1.0.0 | ✓ Current |
| CabinDoor (primary) | v1.0.0 | ⚠️ Incomplete (placeholder creds) |
| CabinDoor (legacy) | v1.1.0 | ⚠️ Recommended |
| CoveSlidingDoor | v1.0.0 | ✓ Current |
| Driftwood | v2.2.5 | ✓ Current |
| JungleDoor | v3.3.0 | ✓ Current |
| WirelessMotionSensor | (not versioned) | ⚠️ Partial Watchtower |
| LuminousShell | (not versioned) | ❌ **NOT DEPLOYABLE** |
| ShipNavMap | (not versioned) | ❌ **NOT DEPLOYABLE** |
| BalancingScale | (not versioned) | ❌ **NOT DEPLOYABLE** |
| SunDial | (not versioned) | ❌ **NOT DEPLOYABLE** |

---

## APPENDIX: DOCUMENTATION REPOSITORIES (Non-Hardware)

These repos provide design documents, CAD files, and configuration references but do NOT contain device firmware.

| Repository | Purpose | Format |
|---|---|---|
| **HallSensor** | ALS31300 driver library (no MQTT) | C/Arduino |
| **ESP-IDE** | Template project + I2C scanner utility | C/Arduino |
| **Master-Puzzle-Outline** | Complete puzzle flow diagrams | PDF |
| **BACIntegration** | BAC wiring and relay documentation | DOCX, PPTX |
| **GravityGamesDocumentation** | MQTT test logs, game flow | DOCX, PPTX |
| **PirateWheel** | Mechanical CAD designs (non-electronic) | CAD format |
| **Coming-Soon-Page** | Landing page HTML | HTML/CSS |

---

## REVISION HISTORY

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2025-02-12 | Operations Team | Initial comprehensive audit and manual generation |
| 1.1 | 2026-09-13 | Claude Code session | Star-Charts section rewritten: three-board layout, Sprite player trigger-mode design (v3.0.0), player gotchas, bridge signal problem |

---

**END OF DOCUMENT**

This manual is the definitive source for Alchemy Escape Rooms "A Mermaid's Tale" operations. Keep it updated as firmware is deployed, bugs are fixed, and new devices are added. For questions or corrections, contact your technical lead.

