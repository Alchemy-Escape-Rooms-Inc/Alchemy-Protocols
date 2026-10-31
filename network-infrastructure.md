# Alchemy Escape Rooms: Network & Infrastructure Reference
## The Alchemy Grimoire — Operations Manual

---

## Physical Network Topology

The Alchemy Escape Rooms system operates on a dedicated subnet within your venue's network. All devices communicate through WiFi and Ethernet connections on a standardized IP address range.

### Network Overview

| Item | Details |
|------|---------|
| **Subnet** | 10.1.10.x (Private IP range) |
| **WiFi SSID** | "AlchemyGuest" |
| **WiFi Password** | VoodooVacuation5601 |
| **Primary MQTT Broker** | 10.1.10.115 (M3 Windows PC) |
| **MQTT Fallback Broker** | 10.1.10.114 (M3 alternate, if .115 unavailable) |
| **All props (ESP32/microcontrollers)** | DHCP-assigned (no static IPs) |

### Known Static IP Addresses

| IP Address | Device | Purpose | Status | Notes |
|------------|--------|---------|--------|-------|
| 10.1.10.115 | M3 Windows PC | MQTT Broker + Game Controller | **ACTIVE** | Primary broker location. Reserve in router DHCP. |
| 10.1.10.114 | M3 Fallback | Backup broker IP | Backup only | Used when .115 was occupied by other device. |
| 10.1.10.130 | Original_Cannon_Legacy code | Incorrect reference | **DEPRECATED** | Found in legacy code. DO NOT USE. Use 10.1.10.115 instead. |
| 10.1.10.228 | Eleven-Labs-Avatar-Project | CAISE AI Server | External | Different broker. Keep isolated. |

### Critical Setup Requirements

- **M3 Windows PC must always use 10.1.10.115** for MQTT broker consistency
- **Ensure your router reserves 10.1.10.115** for the M3 machine (DHCP reservation)
- **All ESP32 devices use DHCP** — they obtain IP addresses automatically from router
- **No microcontroller should have a static IP hardcoded** — this causes address conflicts

---

## MQTT Broker Setup

MQTT (Message Queuing Telemetry Transport) is the communication backbone of Alchemy Escape Rooms. All props, controllers, and monitoring systems talk to each other via MQTT published to the Mosquitto broker.

### Mosquitto Broker Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| **Software** | Mosquitto (open-source MQTT broker) | Message broker for all devices |
| **Host Machine** | M3 Windows PC | Runs Mosquitto service |
| **Primary IP** | 10.1.10.115 | All devices connect here |
| **Port 1860** | M3's primary port + clustering (1861, 1862, 1863) | M3 game controller listens here |
| **Port 1883** | Standard Mosquitto port | Default port for ESP32s and system_checker |
| **Anonymous Access** | Enabled (`allow_anonymous true`) | Devices don't need credentials |

### mosquitto.conf Required Settings

Your Mosquitto configuration file (typically `C:\Program Files\mosquitto\mosquitto.conf`) **must** contain these lines:

```
# Listen on both ports for flexibility
listener 1860 0.0.0.0
listener 1883 0.0.0.0

# Allow devices to connect without authentication
allow_anonymous true

# Persistence (optional but recommended)
persistence true
persistence_location C:\ProgramData\mosquitto\data\
```

**Critical:** Without explicit `listener` lines, Mosquitto defaults to localhost-only, blocking all external connections.

### Windows Firewall Configuration

The M3 Windows PC firewall must allow inbound connections on both MQTT ports.

**To add inbound firewall rules:**

1. Open Windows Defender Firewall → Advanced Settings
2. Click "Inbound Rules" → "New Rule"
3. Create two rules:
   - **Rule 1:** Protocol=TCP, Port=1860, Action=Allow, Direction=Inbound
   - **Rule 2:** Protocol=TCP, Port=1883, Action=Allow, Direction=Inbound
4. Give each rule a descriptive name like "MQTT Broker Port 1860" and "MQTT Broker Port 1883"

**Verification command** (run in Command Prompt on M3):
```
netstat -an | findstr "1860"
netstat -an | findstr "1883"
```

Both should show `LISTENING` if Mosquitto is running correctly.

### Testing the MQTT Broker

Once Mosquitto is running and firewall rules are in place, test connectivity using the command-line MQTT tools installed with Mosquitto.

**To subscribe to all messages** (run on any computer on the network, or on M3):
```
"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v
```
This will print every message published to any MermaidsTale topic in real-time.

**To publish a test message** (in another Command Prompt):
```
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h 10.1.10.115 -p 1883 -t "MermaidsTale/CabinDoor/command" -m "PING"
```

**Expected behavior:**
- The subscribe window will print the test message with timestamp
- If you see the message, your MQTT broker is working
- If you don't see it, check: firewall rules, mosquitto.conf listeners, and that Mosquitto service is running

### Adding Tools to PATH (Optional but Convenient)

To avoid typing the full path each time, add Mosquitto to your Windows PATH:

1. Open Command Prompt as Administrator
2. Run: `setx PATH "%PATH%;C:\Program Files\mosquitto"`
3. Close and reopen Command Prompt
4. Now you can type just `mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#"` without the full path

---

## M3 Integration

M3 is the **master game controller** for Alchemy Escape Rooms. It's the "brain" that orchestrates all game events, prop interactions, and state transitions. M3 runs the proprietary Escape Room Master software on a Windows PC.

### M3 Architecture & Communication

| Component | Details |
|-----------|---------|
| **Device** | Windows PC running Escape Room Master software |
| **IP Address** | 10.1.10.115 (must be reserved in router) |
| **MQTT Port** | 1860 (primary) with clustering ports 1861, 1862, 1863 |
| **Role** | Publishes commands to props, receives status updates, controls game state |
| **Topic Prefix** | All M3 topics use "MermaidsTale/" |

### How M3 Sends Commands

M3 publishes MQTT messages with this structure:

```
Topic:   MermaidsTale/{PropName}/command
Payload: {CommandName}
```

**Real examples:**
- Topic: `MermaidsTale/CabinDoor/command` → Payload: `OPEN`
- Topic: `MermaidsTale/BarrelPiston/Engaged/command` → Payload: `ENGAGE`
- Topic: `MermaidsTale/Compass/command` → Payload: `RESET`

### M3 Topic Naming — Common Mistakes

**Problem 1: Wrong Property Name in Topic**
- ❌ **Wrong:** `MermaidsTale/Barrels` (M3 sends here)
- ✓ **Correct:** `MermaidsTale/BarrelPiston/Engaged` (actual device listens here)
- **Impact:** M3 sends command, prop never receives it, game gets stuck

**Problem 2: M3 Receiving from Wrong Topic**
- M3 may expect status updates on `/status` but the prop publishes to `/log`
- **Solution:** Verify M3's trigger configuration matches the device's actual topic names (see Debug Log for resolution history)

### Preventing M3 Configuration Errors

1. **Use the Master Topic Reference** (see "Alchemy MQTT Protocol Standard" section below)
2. **Verify each new prop's topics** with: `mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/NewPropName/#" -v`
3. **Test M3 commands manually** before integrating into game logic
4. **Document any prop-specific topic variations** in this Grimoire

---

## BAM / BAC Integration

BAM (Alchemy Escape Rooms' hardware management system) controls BAC controllers, which are relay-based switches that activate physical mechanisms.

### BAC Controllers Overview

| Controller | Location | Purpose |
|------------|----------|---------|
| **Shattic** | Shatter-themed room | Manages breakable objects, effects |
| **Captain** | Captain/Ship room | Door locks, motor controls |
| **Cove** | Cove room | Door mechanisms, water effects |
| **Jungle** | Jungle room | Sliding doors, trap mechanisms |

### BAC Heartbeat & Status Monitoring

Each BAC controller publishes a heartbeat every **10 seconds** to signal it's alive:

```
Topic:  {BACname}/get/heartbeat
Value:  (timestamp or simple heartbeat)
```

**Example:**
- `Shattic/get/heartbeat` — published by Shattic BAC every 10 seconds
- `Captain/get/heartbeat` — published by Captain BAC every 10 seconds

If a heartbeat stops appearing for 30 seconds, the BAC is offline or disconnected.

### BAC Command Structure

To activate or deactivate a relay output on a BAC controller:

```
Topic (turn ON):   {BACname}/set/Output_X/on
Topic (turn OFF):  {BACname}/set/Output_X/off
```

Where **X** is the output number (e.g., Output_0, Output_1, Output_2, etc.)

**Real examples:**
- `Captain/set/Output_2/on` — Activates relay 2 on Captain BAC (e.g., door lock solenoid)
- `Shattic/set/Output_5/off` — Deactivates relay 5 on Shattic BAC

### BAC Relay Specifications

| Spec | Rating | Safe Operating Range |
|------|--------|----------------------|
| **Type** | Form-C SPDT (Single-Pole Double-Throw) | Switchable common + 2 positions |
| **Voltage** | 10A @ 125V (max rated) | **Recommended: ≤2A @ 24V** |
| **Current** | 10A maximum across all coils | Use at ≤50% of max to extend relay life |
| **Coil Voltage** | 24V DC (standard for BAC) | Check BAC datasheet for exact coil voltage |

**Key Operating Principle:** Each BAC relay has three terminals:
- **Common (COM):** Shared terminal
- **Normally Open (NO):** Connected when relay is OFF
- **Normally Closed (NC):** Connected when relay is ON

Use Form-C (SPDT) relays to switch between two different circuits with a single relay.

### BAC Input Modes (Configuration via Jumpers)

BAC controllers have digital inputs (0-3) that can be configured to respond to either Active-High or Active-Low signals:

| Input Mode | Signal Level | Usage | Jumper Setting |
|------------|--------------|-------|-----------------|
| **Active High** | HIGH = triggered | Standard button/sensor | JP1/JP2 in default position |
| **Active Low** | LOW = triggered | Inverted sensors | Move JP1/JP2 to alternate position |

Check the BAC hardware manual or silk-screen labels for jumper positions. Most inputs default to Active-High.

### BAC Output Modes

BAC outputs can also be configured for how they switch:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Low Side (default)** | Grounds the load when activated | Typical for solenoid coils, DC motors |
| **High Side** | Supplies voltage to load when activated | Less common, check circuit design |

---

## Port Conflict Troubleshooting

A common source of confusion: Mosquitto can listen on **multiple ports simultaneously**, and this is intentional. However, each device must connect to the **same port** as every other device, or they won't see each other's messages.

### The Dual-Broker Problem (RESOLVED)

**What happened:** Mosquitto was correctly configured with both listeners (1860 and 1883), but devices were split:
- **ESP32 props** connected to port **1860**
- **system_checker** connected to port **1883**
- **M3** connected to port **1860**

Result: Props and system_checker couldn't see each other's messages. It *looked* like the broker was down, but actually it was working — just on two separate logical connections.

**Why this happened:** Both listeners exist in a single Mosquitto instance, so they share the same broker database. However, if a device connects to port 1860 and another to port 1883, MQTT topic filtering still works within each port's connections. In practice, this isn't truly separate brokers — it's confusing routing.

### How to Diagnose Port Issues

1. **Check mosquitto.conf:**
   ```
   C:\Program Files\mosquitto\mosquitto.conf
   ```
   Look for lines starting with `listener`. You should see:
   ```
   listener 1860 0.0.0.0
   listener 1883 0.0.0.0
   ```

2. **Check system_checker config.json:**
   ```
   Look for "broker_port": 1883
   ```

3. **Check ESP32 device code:**
   ```
   Search for MQTT_PORT or #define MQTT_PORT
   Should be 1883 or 1860 (must match config.json)
   ```

4. **Verify active connections:**
   ```
   netstat -an | findstr "1860"
   netstat -an | findstr "1883"
   ```
   You should see one or more `LISTENING` entries and possibly `ESTABLISHED` entries (devices connected).

### Port Standardization Rule

**Going forward: All new ESP32 devices should use port 1883** (the standard MQTT port). Reserve port 1860 for M3 only.

**Migration plan for existing devices:**
- If a prop currently uses 1860, test it on 1883 first
- Update config and code to use 1883
- Verify it still works with M3
- Document the change in this Grimoire

---

## Alchemy MQTT Protocol Standard

Every device connected to Alchemy Escape Rooms must follow this protocol for reliable communication. Think of it as the "common language" all props speak.

### WiFi Connection

**SSID:** `AlchemyGuest`
**Password:** `VoodooVacuation5601`
**Type:** WPA2 Personal
**Frequency:** 2.4 GHz (most reliable for ESP32)

All ESP32 devices should auto-connect on startup using hardcoded SSID and password. If connection fails after 60 attempts, the device should restart.

### MQTT Broker Connection

**Broker IP:** `10.1.10.115`
**Port:** `1883` (standard) or `1860` (M3 only)
**Keep-Alive:** 60 seconds (standard for MQTT)
**Clean Session:** true (reconnect with fresh state)

### Topic Structure

Every device publishes and subscribes to topics following this pattern:

```
MermaidsTale/{PropName}/{TopicType}/{Message}
```

| Part | Example | Notes |
|------|---------|-------|
| **MermaidsTale** | (prefix) | All Alchemy topics start here |
| **PropName** | CabinDoor, BarrelPiston, Compass | Device identifier, no spaces |
| **TopicType** | command, status, log | Purpose of the message |
| **Message** | OPEN, ONLINE, ERROR | Actual payload |

### Required Boot Sequence

When an ESP32 prop starts up:

1. **Initialize hardware** (pins, sensors, motors)
2. **Connect to WiFi "AlchemyGuest"**
3. **Connect to MQTT broker 10.1.10.115:1883**
4. **Publish status message:**
   ```
   Topic:   MermaidsTale/{PropName}/status
   Payload: ONLINE
   ```
5. **Enter normal operation loop**

### Heartbeat Requirements

Every device must publish a heartbeat (status ping) periodically to prove it's alive:

```
Topic:   MermaidsTale/{PropName}/status
Payload: ONLINE (or similar alive signal)
Frequency: Every 300,000 milliseconds (5 minutes)
```

Some devices may use 30-second or 60-second heartbeats; see the Protocol Compliance Audit table below for device-specific variations.

### PING / PONG Mechanism

**System Checker** can verify device availability by sending a PING:

```
System Checker publishes:
  Topic:   MermaidsTale/{PropName}/command
  Payload: PING

Device responds:
  Topic:   MermaidsTale/{PropName}/command
  Payload: PONG
```

Devices should always respond to PING within 5 seconds, or System Checker marks them as offline.

### RESET Command

Devices must support a RESET command to clear state and restart:

```
Topic:   MermaidsTale/{PropName}/command
Payload: RESET
```

**Device behavior on RESET:**
- Stop all motors/actuators
- Clear all solved/engaged flags
- Reset internal variables to startup state
- Publish ONLINE status
- Return to waiting for commands

### PUZZLE_RESET Command

Some devices track puzzle-specific state (e.g., "is this puzzle solved?"). PUZZLE_RESET clears only game-logic state, not hardware state:

```
Topic:   MermaidsTale/{PropName}/command
Payload: PUZZLE_RESET
```

**Device behavior on PUZZLE_RESET:**
- Keep hardware running if in motion
- Clear the "solved" flag
- Reset game-logic counters
- Don't perform full restart

### STATUS Command

M3 or System Checker can request current device state:

```
Request:
  Topic:   MermaidsTale/{PropName}/command
  Payload: STATUS

Device responds:
  Topic:   MermaidsTale/{PropName}/status
  Payload: (current state, e.g., "ENGAGED", "IDLE", "ERROR")
```

### Last Will & Testament (LWT)

MQTT supports "Last Will" — a message sent automatically if a device disconnects unexpectedly:

```
LWT Topic:    MermaidsTale/{PropName}/status
LWT Payload:  OFFLINE
Trigger:      Device disconnects without graceful shutdown
```

**Implementation:** Set the LWT when establishing MQTT connection:
```
client.will_set("MermaidsTale/MyDevice/status", "OFFLINE")
```

If a device loses WiFi or power, the broker will auto-publish "OFFLINE" to that device's status topic after 60 seconds (MQTT keep-alive timeout).

### Message Format & Case Sensitivity

- **Topic names are case-sensitive:** `MermaidsTale/CabinDoor/command` ≠ `mermaidstale/cabin door/command`
- **Payloads are usually case-sensitive:** Send "ONLINE", not "Online" or "online" (check device code)
- **Spaces in topic names break MQTT routing:** Use CamelCase or under_scores, never spaces
- **Special characters in payloads:** JSON payloads should be valid; test with `mosquitto_pub`

---

## Protocol Compliance Audit Table

This table shows which devices fully comply with the Alchemy MQTT Protocol Standard, and which have gaps or issues.

| Device | Broker IP | Port | Boot Status | Heartbeat | PING/PONG | RESET | PUZZLE_RESET | STATUS | LWT | Notes |
|--------|-----------|------|-------------|-----------|-----------|-------|--------------|--------|-----|-------|
| **New-Cannons (Cannon1/2)** | 10.1.10.115 | 1883 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Fully compliant |
| **Compass (Blue/Rose/Silver)** | 10.1.10.115 | 1883 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Fully compliant |
| **CabinDoor** | 10.1.10.115 | 1883 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | **Missing heartbeat** |
| **CoveSlidingDoor** | 10.1.10.115 | 1883 | ✓ | ⚠ | ✓ | ✓ | ✓ | ✓ | ✓ | **Heartbeat 30s not 5min** |
| **JungleDoor** | 10.1.10.115 | 1883 | ✓ | ⚠ | ✓ | ✓ | ✓ | ✓ | ✓ | **Heartbeat 30s not 5min** (non-standard); topic space bug resolved in v3.3.0 |
| **BarrelPiston** | 10.1.10.115 | 1883 | ✓ | ✗ | ✗ | ✓ | ⚠ | ⚠ | ✓ | **No heartbeat, no PING/PONG** |
| **Driftwood** | 10.1.10.115 | 1883 | ✓ | ⚠ | ✓ | ✓ | ✓ | ✓ | ✓ | **Heartbeat 60s not 5min** |
| **Wireless-Motion-Sensor** | 10.1.10.115 | 1883 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | **No heartbeat, no commands** (sensor only) |
| **LuminousShell** | 10.1.10.115 | 1883 | ? | ? | ? | ? | ? | ? | ? | **❌ WON'T COMPILE** — undefined lightPin variable |
| **ShipNavMap** | 10.1.10.115 | 1883 | ? | ? | ? | ? | ? | ? | ? | **❌ WON'T COMPILE** — CGRB() typo, undefined client |
| **AutomaticSlidingDoor** | 10.1.10.115 | 1883 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **ESP32 version compliant**; Arduino R4 lacks MQTT |
| **Original_Cannon_Legacy** | **10.1.10.130** | 1883 | ✓ | ⚠ | ⚠ | ⚠ | ✗ | ⚠ | ✗ | **❌ WRONG BROKER IP** — use New-Cannons instead |
| **hall-sensor-with-mqtt** | 10.1.10.115 | 1883 | ✓ | ⚠ | ✓ | ✗ | ✗ | ✗ | ✓ | **Different topic structure** (sensor/*) |
| **Eleven-Labs-Avatar-Project** | **10.1.10.228** | 1883 | ✓ | ✓ | ? | ? | ? | ? | ⚠ | **Different broker IP**, isolated system |
| **CaptainsCuffs** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **❌ NO NETWORK** — mechanical only |
| **BalancingScale** | 10.1.10.115 | 1883 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **ESP32 v1.4.9**, board IP 10.1.10.201, OTA 3232 |
| **Ruins-Wall-Panel** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **❌ NO NETWORK** — status unknown |
| **SunDial** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **❌ NO NETWORK** — has bugs in logic layer |
| **WaterFountain** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **❌ NO NETWORK** — water sensor only |

### Legend

| Symbol | Meaning |
|--------|---------|
| **✓** | Fully implemented and working |
| **⚠** | Partially implemented or non-standard timing |
| **✗** | Not implemented |
| **?** | Unknown (device won't compile, can't test) |
| **N/A** | Not applicable (no network capability) |
| **❌** | Critical issue blocking use |

### Action Items from Compliance Audit

1. **Fix LuminousShell & ShipNavMap compilation errors** (see Debug Log)
2. **Update Original_Cannon_Legacy** to use 10.1.10.115, or deprecate in favor of New-Cannons
3. **Standardize heartbeat intervals** to 5 minutes across all devices (currently varies: 30s, 60s, 5min)
4. ~~**Remove space from "Jungle Door"** → "JungleDoor"~~ ✅ RESOLVED in MANIFEST v3.3.0
5. **Add MQTT heartbeat to CabinDoor & BarrelPiston**
6. **Verify CoveSlidingDoor, JungleDoor, Driftwood** can tolerate standardized 5-minute heartbeat
7. **Plan network integration** for CaptainsCuffs, Ruins-Wall-Panel, SunDial, WaterFountain

---

## Quick Reference: Topic Naming

Use this as a copy-paste reference when configuring M3 or adding new devices.

### Current Devices & Their Topics

```
MermaidsTale/Cannon1/command         (New cannon #1)
MermaidsTale/Cannon2/command         (New cannon #2)
MermaidsTale/Compass/command         (All compass variants: Blue, Rose, Silver)
MermaidsTale/CabinDoor/command       (Cabin door lock/unlock)
MermaidsTale/CoveSlidingDoor/command (Cove sliding door)
MermaidsTale/JungleDoor/command      (Jungle sliding door)
MermaidsTale/BarrelPiston/Engaged/command     (Barrel piston engagement)
MermaidsTale/Driftwood/command       (Driftwood interactive device)
MermaidsTale/AutomaticSlidingDoor/command     (Auto door)
```

### Template for New Devices

When adding a new networked prop, use:
```
MermaidsTale/{DeviceName}/command   (receive commands from M3)
MermaidsTale/{DeviceName}/status    (publish status/heartbeat)
MermaidsTale/{DeviceName}/log       (publish diagnostic logs)
```

Where `{DeviceName}` is:
- **CamelCase** (no spaces, no underscores)
- **Descriptive** (CabinDoor, not Door1)
- **Consistent** with hardware labeling

---

## End of Network & Infrastructure Reference

*Last updated: 2026*
*Next review: When adding new networked device*

