# Alchemy Escape Rooms: Debug Log & Known Issues
## The Alchemy Grimoire — Operations Manual

---

## Overview

This document tracks all known issues across the Alchemy Escape Rooms system, both resolved and active. Each entry includes:
- **Symptoms** — What the operator or guest notices
- **Root Cause** — Why the issue occurred
- **Fix** — How to resolve it
- **Prevention** — How to avoid it happening again

Use this guide to diagnose problems quickly and escalate appropriately to the technical team.

---

## RESOLVED ISSUES

### 1. Dual Broker Problem

**Status:** ✓ RESOLVED

**Symptoms:**
- Devices couldn't see each other's MQTT messages
- system_checker showed all devices as offline even though they had working WiFi
- Publishing test messages on one port didn't reach subscribers on another port
- MQTT felt completely broken, though logs showed "connected"

**Root Cause:**
Mosquitto was correctly running on **both port 1860 and port 1883**, but the configuration was misunderstood:
- **system_checker** was configured with `broker_port: 1883` in config.json
- **Most ESP32 devices** hardcoded `MQTT_PORT = 1860` in firmware
- When devices connected to *different* ports, they operated on separate MQTT topic namespaces
- It *looked* like a dual-broker system, but was actually a single broker with split routing

**Fix:**
1. Edit `C:\Program Files\mosquitto\mosquitto.conf` to ensure both listeners are present:
   ```
   listener 1860 0.0.0.0
   listener 1883 0.0.0.0
   allow_anonymous true
   ```
2. Verify all devices connect to the **same port**:
   - Check `system_checker/config.json` → `"broker_port": 1883`
   - Check each ESP32 device code → `#define MQTT_PORT 1883`
   - Check M3 Windows software settings → should use 1860 (its own port range)
3. Restart Mosquitto: `net stop Mosquitto` then `net start Mosquitto`
4. Verify with: `netstat -an | findstr "1883"` and `findstr "1860"`

**Prevention:**
- **Standardize all new ESP32 devices to port 1883** (the standard MQTT port)
- **Only M3 software should use port 1860**
- Add this to the ESP32 onboarding template
- Document port assignment in comments within device code

**Lesson Learned:**
Multiple listeners on the same Mosquitto broker are independent connection channels but share the same broker database. Devices on different ports don't interfere with each other; they simply won't see each other's messages. Always verify port alignment as the first troubleshooting step.

---

### 2. IP Address Conflict

**Status:** ✓ RESOLVED

**Symptoms:**
- M3 Windows PC couldn't obtain its IP address 10.1.10.115
- M3 Windows PC obtained fallback IP 10.1.10.114
- Network communication worked on the fallback IP, but configuration and scripts expected .115
- M3 software may show incorrect broker IP

**Root Cause:**
Some device (possibly an ESP32 with hardcoded IP 10.1.10.115) was "squatting" on the address intended for M3. When M3 tried to obtain .115 via DHCP, the router saw the address was in use and assigned .114 instead.

**Fix:**
1. **Identify the squatting device:**
   - Run `arp -a` on M3 or another networked computer to see all IP/MAC mappings
   - Look for 10.1.10.115 and note the MAC address
   - Cross-reference MAC addresses with your device list
2. **Find and fix the hardcoded IP:**
   - Locate the device's firmware source code
   - Search for `10.1.10.115` or `.115`
   - Remove any hardcoded static IP assignment
   - Change to `WiFi.config(INADDR_NONE)` or rely on DHCP
   - Recompile and upload
3. **Reserve .115 in router:**
   - Log into your router's DHCP settings
   - Create a DHCP reservation: MAC address of M3 PC → 10.1.10.115
   - This ensures M3 always gets the intended address
4. **Restart network devices:**
   - Power cycle the router
   - Restart M3 Windows PC
   - Restart any ESP32 devices

**Prevention:**
- **Never hardcode static IPs on ESP32 devices** — always use DHCP
- **Reserve critical infrastructure IPs** (M3 at .115) in router settings
- **Document the MAC address of M3 PC** for future reference
- Add a note in device code comments: `// DHCP only, no static IP`

**Lesson Learned:**
Hardcoded IPs on microcontrollers are a source of confusion and conflicts. The router is the source of truth for IP allocation; trust it.

---

### 3. mosquitto.conf Missing Listeners

**Status:** ✓ RESOLVED

**Symptoms:**
- MQTT connections refused from external devices (ESP32s, network tools)
- Error: `Connection refused` when running `mosquitto_sub.exe`
- Mosquitto process shows as running, but no connectivity
- Only localhost tools can connect (mosquitto_sub on the same machine)

**Root Cause:**
The default `mosquitto.conf` only listens on **localhost (127.0.0.1)**, not on the network interface. Without explicit `listener` lines, external devices can't reach the broker.

**Configuration that doesn't work:**
```
# Default (bad) — only listens on 127.0.0.1
listener 1883 localhost
# OR no listener line at all
```

**Fix:**
1. Open `C:\Program Files\mosquitto\mosquitto.conf` in a text editor
2. Find the `listener` lines (around line 70-80)
3. Replace or add these lines:
   ```
   listener 1860 0.0.0.0
   listener 1883 0.0.0.0
   allow_anonymous true
   ```
   The `0.0.0.0` means "listen on all network interfaces"
4. Save the file
5. Restart Mosquitto: `net stop Mosquitto` then `net start Mosquitto`
6. Verify: `netstat -an | findstr "1883"` should show `LISTENING 0.0.0.0:1883`

**Prevention:**
- Keep a documented, correct `mosquitto.conf` in version control (shared repo)
- Add comments explaining why `0.0.0.0` is needed
- Include the correct config in M3 setup documentation
- Test MQTT connectivity immediately after installing Mosquitto

**Lesson Learned:**
Network firewalls and binding are often the culprit in "can't connect" issues. Always verify the service is listening on all interfaces, not just localhost.

---

### 4. Windows Firewall Blocking MQTT

**Status:** ✓ RESOLVED

**Symptoms:**
- Mosquitto is running (confirmed with `netstat`)
- `mosquitto_sub.exe` works when run on the M3 machine itself
- External ESP32 devices can't connect to MQTT
- Error: `Connection refused` or timeout when connecting from another machine
- Network ping to 10.1.10.115 works, but MQTT doesn't

**Root Cause:**
Windows Defender Firewall was blocking inbound connections on TCP port 1860 and/or 1883. Mosquitto was listening, but the firewall denied incoming packets.

**Fix:**
1. Open **Windows Defender Firewall with Advanced Security**
   - Click Start → search "wf.msc" → Enter
2. Click **Inbound Rules** (left panel)
3. Click **New Rule** (right panel)
4. Create **Rule 1 (Port 1860):**
   - Choose **Port** → Next
   - Select **TCP**
   - Specific local ports: `1860`
   - Action: **Allow the connection**
   - Direction: **Inbound**
   - Name: `MQTT Broker Port 1860`
   - Finish
5. Repeat for **Rule 2 (Port 1883):**
   - Follow same steps, but port `1883`
   - Name: `MQTT Broker Port 1883`
6. Verify rules are enabled (checkmark in list)
7. Test: `"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v`

**Prevention:**
- Document these firewall rules in M3 setup procedures
- When installing Mosquitto, explicitly add firewall rules at that time
- Test connectivity immediately after setup
- Add a note in the operations manual

**Lesson Learned:**
Firewalls are security features that often silently block legitimate traffic. Always check firewall rules when networking fails, even if the service seems to be running.

---

### 5. mosquitto_sub/pub Not in PATH

**Status:** ✓ RESOLVED

**Symptoms:**
- Trying to run `mosquitto_sub.exe` or `mosquitto_pub.exe` gives error: "command not found" or "is not recognized"
- Full path like `C:\Program Files\mosquitto\mosquitto_sub.exe` works fine
- Shell can't find Mosquitto tools, even though they're installed

**Root Cause:**
Mosquitto installer does not automatically add `C:\Program Files\mosquitto` to the Windows PATH environment variable. Users must add it manually or use full paths.

**Fix (Option 1: Add to PATH):**
1. Open Command Prompt as Administrator
2. Run this command (one line):
   ```
   setx PATH "%PATH%;C:\Program Files\mosquitto"
   ```
3. Close and reopen Command Prompt (PATH changes take effect on new shell)
4. Test: `mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "test"`

**Fix (Option 2: Always use full path):**
```
"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 10.1.10.115 -p 1883 -t "MermaidsTale/#"
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h 10.1.10.115 -p 1883 -t "MermaidsTale/test" -m "HELLO"
```

**Prevention:**
- Include "Add Mosquitto to PATH" as a step in M3 installation documentation
- Provide script that does this automatically (batch file or PowerShell)
- Document the full path in troubleshooting guides

**Lesson Learned:**
Installer defaults aren't always best for developers. Manual PATH setup is simple but easy to forget.

---

### 6. System Checker Port Mismatch

**Status:** ✓ RESOLVED

**Symptoms:**
- system_checker shows all devices as offline (red status)
- MQTT topics are visible with `mosquitto_sub` (broker is working)
- Devices publish their status to MQTT correctly
- system_checker's "heartbeat check" finds no devices

**Root Cause:**
`system_checker/config.json` specified one port (e.g., 1883) while ESP32 devices were configured for a different port (e.g., 1860). system_checker was listening on the right topic names, but on the wrong port, so it never received messages.

**Example (WRONG):**
```json
// config.json
{
  "broker_ip": "10.1.10.115",
  "broker_port": 1883,      // ← system_checker listens here
  ...
}

// ESP32 code
#define MQTT_PORT 1860       // ← devices publish here
```

Result: Different channels, no message arrival.

**Fix:**
1. Check `system_checker/config.json`:
   ```
   "broker_port": 1883
   ```
2. Check each ESP32 device code:
   ```
   #define MQTT_PORT 1883    // or 1860 if that's your standard
   ```
3. **Ensure all devices use the same port** (recommend 1883 for standard)
4. Restart system_checker and reboot ESP32 devices
5. Verify: `mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v` should show all device status messages

**Prevention:**
- **Standardize to port 1883 for all ESP32 devices**
- Comment in config.json: `// Must match MQTT_PORT in all device firmware`
- Add a startup check in system_checker: verify MQTT port is 1883
- Test port alignment before deploying new devices

**Lesson Learned:**
Port mismatches can be subtle because the broker is running fine — it's the device-to-broker alignment that fails. Always verify port consistency as part of deployment.

---

### 7. PONG Response Topic Mismatch

**Status:** ✓ RESOLVED

**Symptoms:**
- system_checker sends PING, waits for response
- PING reaches the device (visible in device logs)
- Device sends PONG, but system_checker doesn't receive it
- system_checker marks device as offline despite working device

**Root Cause:**
Device firmware published PONG to the wrong topic. Typically:
- system_checker sends PING to: `MermaidsTale/{DeviceName}/command`
- Device received PING correctly
- Device published PONG to: `MermaidsTale/{DeviceName}/status` (WRONG)
- system_checker expected PONG on: `MermaidsTale/{DeviceName}/command` (same topic)

**Example (WRONG firmware):**
```cpp
// Receive PING on command topic
if (message_topic == "MermaidsTale/MyDevice/command" &&
    payload == "PING") {
  // WRONG: publish PONG to status topic
  client.publish("MermaidsTale/MyDevice/status", "PONG");
}
```

**Fix (CORRECT firmware):**
```cpp
// Receive PING on command topic
if (message_topic == "MermaidsTale/MyDevice/command" &&
    payload == "PING") {
  // CORRECT: publish PONG to the SAME topic
  client.publish("MermaidsTale/MyDevice/command", "PONG");
}
```

**Prevention:**
- MQTT convention: respond to messages on the same topic they arrived on
- Code review: verify PONG topic matches PING reception topic
- Use the Alchemy MQTT Protocol Standard template for all new devices
- Test PING/PONG manually: `mosquitto_pub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/MyDevice/command" -m "PING"`

**Lesson Learned:**
Request/response patterns in MQTT should use the same topic. Mixing command and status topics for responses breaks monitoring systems.

---

### 8. ESP32 WiFi Connection Stuck in Loop

**Status:** ✓ RESOLVED

**Symptoms:**
- ESP32 powers on, attempts to connect to WiFi
- Serial output shows continuous `WiFi connecting...` messages
- Never progresses beyond WiFi connection
- Device is stuck and non-functional
- No MQTT connection attempt

**Root Cause:**
WiFi state machine not properly reset before reconnecting. The WiFi module retains state from previous attempts, causing infinite retry loop. Missing timeout, so the device hangs indefinitely.

**Example (BAD firmware):**
```cpp
void setup() {
  WiFi.begin("AlchemyGuest", "VoodooVacuation5601");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    // ← No timeout! Device stuck here forever
  }
}
```

**Fix (CORRECT firmware):**
```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);  // Give serial time to initialize

  // Clear any previous WiFi state
  WiFi.disconnect(true);   // true = turn off WiFi radio
  delay(1000);

  // Set WiFi mode explicitly
  WiFi.mode(WIFI_STA);
  delay(1000);

  Serial.println("Connecting to WiFi...");
  WiFi.begin("AlchemyGuest", "VoodooVacuation5601");

  int attempts = 0;
  int max_attempts = 60;

  while (WiFi.status() != WL_CONNECTED && attempts < max_attempts) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi connection failed. Restarting...");
    ESP.restart();  // Hard reset after 30 seconds of trying
  }
}
```

**Key changes:**
1. `WiFi.disconnect(true)` — clears previous state
2. `WiFi.mode(WIFI_STA)` — set explicit mode
3. `delay(1000)` — give hardware time to stabilize
4. **Timeout counter** — max 60 attempts (~30 seconds)
5. **Hard reset on failure** — `ESP.restart()` breaks the loop

**Prevention:**
- Use this WiFi template for all new ESP32 devices
- Always include a timeout and restart logic
- Test on a bench before deploying
- Monitor serial output during startup

**Lesson Learned:**
Hardware state machines need explicit resets and timeouts. Don't assume the device will just "try again" — it won't without explicit logic.

---

### 9. BarrelPiston DeviceInfo Wrong Topic

**Status:** ✓ RESOLVED

**Symptoms:**
- BarrelPiston device published its DeviceInfo
- system_checker or M3 couldn't find the DeviceInfo message
- Looked for message on: `MermaidsTale/BarrelPiston/DeviceInfo`
- Device published to: `Barrel/Piston/DeviceInfo` (without prefix)

**Root Cause:**
Firmware hardcoded the topic string without the required `MermaidsTale/` prefix, breaking topic consistency.

**Example (WRONG):**
```cpp
client.publish("Barrel/Piston/DeviceInfo", "...");  // Missing prefix
```

**Fix (CORRECT):**
```cpp
client.publish("MermaidsTale/BarrelPiston/DeviceInfo", "...");
```

**Prevention:**
- All topics must start with `MermaidsTale/`
- Use a macro or constant: `#define TOPIC_PREFIX "MermaidsTale/BarrelPiston"`
- Code review: check all `client.publish()` calls for prefix
- Standardize topic naming in a template

**Lesson Learned:**
Topic naming conventions must be enforced across all firmware. Use constants or macros to prevent typos.

---

### 10. Door Controller PWM Stuck at 0V

**Status:** ✓ RESOLVED

**Symptoms:**
- Motor direction signal (DIR pin) working correctly (toggling 5V)
- Motor PWM signal stuck at 0V, never goes high
- Motor doesn't move (no power)
- Other pins on same microcontroller work fine

**Root Cause:**
Suspected hardware failure — either:
- Arduino pin damaged or internally failed
- Wire broken or loose connection
- Motor driver input shorted to ground

**Fix:**
1. **Diagnose with multimeter:**
   - Set to DC voltage
   - Probe the PWM pin directly: should see 0-5V changes
   - If stuck at 0V, try a different pin on same Arduino
2. **If different pin works:**
   - Original pin is dead, permanently use the new pin
   - Update firmware with new pin number
   - Mark original pin as "not usable" on device documentation
3. **If all pins stuck:**
   - Microcontroller may be failed
   - Swap with known-good replacement
   - Investigate what caused the failure (voltage spike? short?)

**Prevention:**
- Test all pins during initial assembly with multimeter
- Document which pins are tested and working
- Use quality connectors and strain relief on wires
- Protect pins from voltage spikes (diodes, capacitors)

**Lesson Learned:**
Hardware testing should happen before code testing. Use a multimeter to verify pins work before blaming software.

---

### 11. Compass Reset Not Clearing Solved Status

**Status:** ✓ RESOLVED

**Symptoms:**
- Operator sends RESET command to Compass device
- Device reboots and publishes ONLINE status
- Compass appears to reset
- But system_checker or M3 still shows compass as "solved"

**Root Cause:**
RESET command only cleared the immediate state but didn't clear the "solved" flag. Compass maintains two separate topics:
- `MermaidsTale/Compass/status` — device online/offline
- `MermaidsTale/Compass/solved` — puzzle solved flag

Firmware only reset status, not solved flag.

**Example (WRONG):**
```cpp
if (command == "RESET") {
  // Only clear this
  client.publish("MermaidsTale/Compass/status", "ONLINE");
  // But NOT this
  // client.publish("MermaidsTale/Compass/solved", "false");
}
```

**Fix (CORRECT):**
```cpp
if (command == "RESET") {
  // Clear ALL state topics
  client.publish("MermaidsTale/Compass/status", "ONLINE");
  client.publish("MermaidsTale/Compass/solved", "false");
  client.publish("MermaidsTale/Compass/position", "0");  // or initial state
  // Reset any other tracked state
}
```

**Prevention:**
- Document all state topics for each device (status, solved, position, etc.)
- RESET command must publish reset values to ALL state topics
- Code review: verify RESET clears all device state, not just one flag
- Test RESET behavior before deploying

**Lesson Learned:**
Devices often have multiple state topics. RESET must clear them all to be truly effective.

---

### 12. ALS31300 I2C Address Programming

**Status:** ✓ RESOLVED

**Symptoms:**
- Hall sensor (ALS31300) not responding to I2C address expected in firmware
- Firmware tries to read from address 0x60, no response
- Error: "Sensor not found at 0x60"
- All ALS31300 chips respond to default address 0x60, causing conflicts

**Root Cause:**
ALS31300 hall sensors come from factory with a default I2C address of 0x60. When multiple sensors are on the same I2C bus, they all respond to 0x60, causing collisions. Each sensor must be individually programmed with a unique address (0x60-0x67).

**Solution:**
Use the official **Alchemy Escape Rooms ID_Overwrite.ino** sketch to program unique addresses:

1. Program one sensor at a time (disconnect others)
2. Upload ID_Overwrite.ino to Arduino
3. Open Serial Monitor
4. Follow prompts to set address (0x60, 0x61, 0x62, etc.)
5. Verify address programmed (sensor responds at new address)
6. Disconnect, connect next sensor, repeat

**Address Assignment Recommendation:**
- Reserve 0x60 for sensor 0 (first, leftmost)
- Reserve 0x61 for sensor 1
- Reserve 0x62 for sensor 2
- Etc., up to 0x67 for sensor 7

**After Programming:**
Update firmware with correct addresses:
```cpp
ALS31300 sensor0(0x60);  // Sensor 0
ALS31300 sensor1(0x61);  // Sensor 1
ALS31300 sensor2(0x62);  // Sensor 2
```

**Prevention:**
- Program sensor addresses during assembly, before integration
- **Document which physical sensor gets which address** (e.g., "Top sensor = 0x60, Middle = 0x61")
- Keep ID_Overwrite.ino in a safe, version-controlled location
- Test all sensors respond at their assigned addresses before system integration

**Lesson Learned:**
I2C bus conflicts happen when devices share addresses. Always assign unique addresses during assembly for multi-sensor systems.

---

### 13. MFRC522 RFID Daisy-Chain Failure

**Status:** ✓ RESOLVED

**Symptoms:**
- Multiple RFID readers on same system
- Only the first reader responds to card scans
- Second and subsequent readers show no activity
- System can't read cards from readers 2, 3, 4, etc.

**Root Cause:**
MFRC522 RFID readers cannot share the SPI Chip Select (CS) pin. The SPI bus protocol requires each device to have its own CS pin for independent selection. When multiple readers share the same CS pin, only one is ever selected at a time, and the others are ignored.

**Example (WRONG — won't work):**
```cpp
#define CS_PIN_1 10    // Reader 1 CS
#define CS_PIN_2 10    // Reader 2 CS — SAME PIN!
// Result: Only reader 1 ever responds

MFRC522 rfid1(CS_PIN_1, RST_PIN);
MFRC522 rfid2(CS_PIN_2, RST_PIN);
```

**Fix (CORRECT — each reader gets unique CS pin):**
```cpp
#define CS_PIN_1 10    // Reader 1 CS
#define CS_PIN_2 9     // Reader 2 CS — Different pin
#define CS_PIN_3 8     // Reader 3 CS — Different pin
// Result: All three readers respond independently

MFRC522 rfid1(CS_PIN_1, RST_PIN);
MFRC522 rfid2(CS_PIN_2, RST_PIN);
MFRC522 rfid3(CS_PIN_3, RST_PIN);
```

**SPI Bus Wiring (Correct):**
```
All readers share:
- MOSI (SPI pin 11)
- MISO (SPI pin 12)
- CLK (SPI pin 13)

Each reader gets unique:
- CS (Chip Select) — one pin per reader
- RST (Reset) — can be shared or individual (test both)
```

**Prevention:**
- Design PCB or wiring harness with individual CS pins from the start
- Reserve pins 10, 9, 8, 7, 6 for CS (one per reader)
- Document pin assignments in firmware and schematic
- Test multi-reader setup on bench before deployment

**Lesson Learned:**
SPI is a shared-bus protocol; CS pins are how devices get selected. Never share CS pins between devices.

---

### 14. ESP-IDF Version Compatibility

**Status:** ✓ RESOLVED

**Symptoms:**
- Trying to compile ESP-DMX library or certain WiFi code
- Compiler error: "incompatible ESP-IDF version"
- Project requires ESP-IDF 4.4.x but system has 5.3.2
- Can't upgrade library, can't compile code

**Root Cause:**
ESP-IDF (Espressif IoT Development Framework) had breaking API changes between major versions. Some libraries, particularly ESP-DMX, depend on specific IDF versions due to deep hardware integration.

**Example error:**
```
error: ESP-IDF v5.3.2 is incompatible. This library requires v4.4.x
```

**Fix:**
1. **Downgrade ESP-IDF to v4.4.x:**
   - In Arduino IDE: Tools → Board → esp32 → Edit Settings
   - Or use `idf.py --version` and `idf.py install-python-env` for manual install
   - Select version 4.4.x (or latest 4.4.x patch)
2. **Verify version:**
   - Open Arduino IDE → Sketch → Include Library → Manage Libraries
   - Search "esp32" → version should show 4.4.x
3. **Test compilation:**
   - Compile a simple DMX sketch to verify

**Prevention:**
- Document required ESP-IDF version in each repository's README
- Keep README up to date when upgrading or downgrading
- Test compilation on fresh development machines before pushing
- Use version pinning in platformio.ini or Arduino Board Manager settings

**Lesson Learned:**
Firmware development depends on specific framework versions. Always document and test version compatibility, especially for low-level libraries like DMX.

---

### 15. System Checker False Positives

**Status:** ✓ RESOLVED

**Symptoms:**
- system_checker shows all devices as online (green checkmarks)
- Some devices haven't even been built yet (no hardware exists)
- system_checker dashboard shows 100% system operational
- Operator thinks system is fully functional when many devices are missing

**Root Cause:**
system_checker's topic-matching logic was too broad. Instead of waiting for a specific PONG or STATUS response, it matched **any message** on the base topic path. This meant:
- Device publishes: `MermaidsTale/NewDevice/log "Device started"`
- system_checker received ANY message on `MermaidsTale/NewDevice` and marked it as online
- No actual PONG response was required

**Example (WRONG logic):**
```python
# Bad: matches any message on topic
if "MermaidsTale/NewDevice" in message_topic:
    device_status = "ONLINE"  # False positive!
```

**Fix (CORRECT logic):**
```python
# Good: only matches specific PONG or STATUS response
if message_topic == "MermaidsTale/NewDevice/command" and payload == "PONG":
    device_status = "ONLINE"
elif message_topic == "MermaidsTale/NewDevice/status" and payload == "ONLINE":
    device_status = "ONLINE"
else:
    device_status = "OFFLINE"  # Don't trust other topics
```

**Prevention:**
- PING/PONG must be strict: require exact message match, not just topic match
- Implement heartbeat timeout: if no message in 2x heartbeat interval, mark offline
- Add a "NOT_INSTALLED" status for devices under development
- Code review: verify system_checker logic is strict, not permissive

**Lesson Learned:**
Monitoring systems must be strict about what constitutes "online." Permissive matching leads to false positives and hidden problems.

---

### 16. M3 Wrong MQTT Topic Names

**Status:** ✓ RESOLVED

**Symptoms:**
- M3 game controller sends commands (visible in Mosquitto logs)
- Devices never receive or respond to M3 commands
- Operator changes game logic in M3, but props don't react
- M3 trigger configuration seems correct, but props don't move

**Root Cause:**
M3 MQTT trigger was configured with incorrect topic names. Examples:
- M3 configured to send `MermaidsTale/Barrels` but device listens to `MermaidsTale/BarrelPiston/Engaged`
- M3 sends `MermaidsTale/Door` but device topic is `MermaidsTale/CabinDoor`
- M3 uses wrong capitalization or spacing (e.g., "Barrel Piston" instead of "BarrelPiston")

**Example (WRONG M3 config):**
```
M3 Trigger:
  Topic to publish: MermaidsTale/Barrels/command    ← Wrong topic name
  Message: ENGAGE

Actual device listens to:
  MermaidsTale/BarrelPiston/Engaged/command       ← Different name
```

**Fix:**
1. **Document actual device topics:**
   - Use `mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v` to see all real topics
   - List all device topics in M3 configuration
2. **Update M3 triggers** to match actual device topics
3. **Test each M3 trigger manually:**
   - Open M3's trigger configuration
   - Find a trigger
   - Compare topic name to actual device output
   - Correct if needed
4. **Verify with MQTT pub/sub:**
   ```
   mosquitto_pub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/BarrelPiston/Engaged/command" -m "ENGAGE"
   ```
   Device should respond immediately

**Prevention:**
- Maintain a **Master Topic Reference Document** (see Network & Infrastructure Reference in this Grimoire)
- Require M3 configuration review before game deployment
- Test all M3 triggers on a test system before running live game
- Add comments in M3 trigger config with device name and purpose

**Lesson Learned:**
Topic names are the contract between M3 and devices. Any mismatch breaks the entire interaction. Maintain a single source of truth for topic names.

---

## NEW ISSUES FOUND IN CODE AUDIT

### 17. LuminousShell — Won't Compile (lightPin undefined)

**Status:** ⚠️ ACTIVE

**File:** `/sessions/elegant-dazzling-ptolemy/repos/LuminousShell/Code/LuminousShell/LuminousShell.ino`

**Symptoms:**
- Compilation fails with error: `error: 'lightPin' was not declared in this scope`
- LuminousShell device cannot be built or deployed

**Root Cause:**
1. Variable `lightPin` is used in code but never defined with `#define` or `int lightPin = XX;`
2. Additional issue: code references undefined variable `client` (should be `mqtt` or properly declared)
3. MQTT variable naming inconsistency throughout file

**Code location (line ~XX):**
```cpp
// Missing: #define lightPin 14 (or appropriate pin)

void setup() {
  pinMode(lightPin, OUTPUT);  // ← Error: lightPin undefined
}

void onMQTTMessage(...) {
  client.publish(...);  // ← Error: client undefined (should be mqtt or proper variable)
}
```

**Fix (immediate):**
1. Add pin definition at top of file:
   ```cpp
   #define LIGHT_PIN 14  // Adjust pin number as needed
   ```
2. Replace all instances of `lightPin` with `LIGHT_PIN`
3. Fix MQTT client variable name — either:
   - Declare: `WiFiClient mqttClient;` then `PubSubClient client(mqttClient);`
   - Or rename all `client.` calls to match declared variable name
4. Verify compilation succeeds
5. Test on hardware

**Prevention:**
- Code review before commit: verify all variables are declared
- Enable compiler warnings: Arduino IDE → Preferences → Show verbose output during compilation
- Compile locally before pushing to repository

**Action Items:**
- [ ] Fix lightPin definition
- [ ] Fix MQTT client variable names
- [ ] Test compilation
- [ ] Test on hardware
- [ ] Merge fix to main branch

---

### 18. ShipNavMap — Won't Compile (multiple errors)

**Status:** ⚠️ ACTIVE

**File:** `/sessions/elegant-dazzling-ptolemy/repos/ShipNavMap/Code/ShipCoordinates/ShipCoordinate.ino`

**Symptoms:**
- Multiple compilation errors prevent building
- ShipNavMap device cannot be deployed

**Root Causes:**

**Error 1: CGRB() typo instead of CRGB()**
```cpp
// Line ~XX: WRONG
CGRB(255, 0, 0);  // ← Typo, should be CRGB

// CORRECT
CRGB(255, 0, 0);
```

**Error 2: Undefined client variable**
```cpp
// client variable used but never declared
client.publish("MermaidsTale/ShipNavMap/status", "ONLINE");  // ← Error

// Need to declare
WiFiClient mqttClient;
PubSubClient client(mqttClient);
```

**Error 3: Backwards reconnect logic**
```cpp
// WRONG: reconnects when already connected
if (client.connected()) {
    client.connect(...);
}

// CORRECT: reconnects when NOT connected
if (!client.connected()) {
    client.connect(...);
}
```

**Fix (immediate):**
1. Replace all `CGRB(` with `CRGB(`
2. Declare MQTT client properly:
   ```cpp
   WiFiClient mqttClient;
   PubSubClient client(mqttClient);
   ```
3. Fix reconnect logic:
   ```cpp
   if (!client.connected()) {
       // Attempt reconnect
       client.connect(...);
   }
   ```
4. Verify compilation succeeds

**Prevention:**
- Code review: check for typos in function names (CRGB vs CGRB)
- Verify all variables are declared before use
- Logic review: if/!if conditions should be checked carefully
- Compile locally before committing

**Action Items:**
- [ ] Fix CGRB typo
- [ ] Declare MQTT client
- [ ] Fix reconnect logic
- [ ] Test compilation
- [ ] Test on hardware
- [ ] Update ShipNavMap code in repository

---

### 19. Balancing-Scale — Multiple Logic Bugs

**Status:** ⚠️ ACTIVE

**File:** `/sessions/elegant-dazzling-ptolemy/repos/Balancing-Scale/Balancing_Scale.ino`

**Symptoms:**
- Device compiles but doesn't function correctly
- Servo doesn't move properly
- Weight detection always fails
- Game logic doesn't respond to scale state changes

**Root Causes:**

**Bug 1: SERVO_PIN undefined**
```cpp
// Used but never defined
servo.attach(SERVO_PIN);  // ← Error: SERVO_PIN not defined

// Fix: Add definition
#define SERVO_PIN 9  // Adjust to actual pin
```

**Bug 2: isAlreadyStored() always returns false**
```cpp
// WRONG: function doesn't actually return the value
bool isAlreadyStored() {
    return storedWeight == currentWeight;  // ← Never reached? Check logic
}

// Investigate: Is this even called? Does logic make sense?
```

**Bug 3: checkSuccess() is empty/incomplete**
```cpp
// WRONG: empty function
bool checkSuccess() {
    // No code here!
    return false;  // Always fails
}

// Should probably implement:
bool checkSuccess() {
    return (currentWeight == targetWeight);
}
```

**Fix (immediate):**
1. Define SERVO_PIN:
   ```cpp
   #define SERVO_PIN 9  // Update to actual GPIO pin
   ```
2. Verify isAlreadyStored() logic is correct:
   - Check if storedWeight and currentWeight are being set
   - Verify comparison makes sense for the game mechanic
3. Implement checkSuccess():
   ```cpp
   bool checkSuccess() {
       // Return true if scale is balanced correctly
       return (currentWeight >= minTargetWeight &&
               currentWeight <= maxTargetWeight);
   }
   ```
4. Test on hardware: place objects on scale, verify success detection

**Prevention:**
- Implement all functions before marking code as "done"
- Don't leave stub functions empty — either implement or remove
- Test game logic on hardware before deployment
- Code review: verify all variable definitions and function implementations

**Action Items:**
- [ ] Define SERVO_PIN with correct GPIO number
- [ ] Verify isAlreadyStored() logic
- [ ] Implement checkSuccess() function
- [ ] Test weight detection with actual objects
- [ ] Test servo response
- [ ] Test game win condition
- [ ] Merge fixes to main branch

---

### 20. Sun-Dial — Assignment Operator Bug (4 instances)

**Status:** ⚠️ ACTIVE

**File:** `/sessions/elegant-dazzling-ptolemy/repos/Sun-Dial/Sand_dial_new_boards_FINAL.ino`

**Symptoms:**
- Lightshow behavior incorrect
- break_from_lightshow flag never actually breaks from loop
- Code logic flow doesn't work as expected
- Device behavior unpredictable during game

**Root Cause:**
Four lines use comparison operator `==` where assignment operator `=` is needed:

```cpp
// Line 262: WRONG (comparison, doesn't assign)
if (some_condition) {
    break_from_lightshow == 0;  // ← Just compares, result discarded
}

// Should be:
break_from_lightshow = 0;  // ← Actually assigns value
```

**Affected lines:**
- Line 262: `break_from_lightshow == 0`
- Line 280: `break_from_lightshow == 0`
- Line 297: `break_from_lightshow == 0`
- Line 317: `break_from_lightshow == 0`

**Fix (immediate):**
Change all four instances of `==` to `=`:

```cpp
// Line 262
- break_from_lightshow == 0;
+ break_from_lightshow = 0;

// Line 280
- break_from_lightshow == 0;
+ break_from_lightshow = 0;

// Line 297
- break_from_lightshow == 0;
+ break_from_lightshow = 0;

// Line 317
- break_from_lightshow == 0;
+ break_from_lightshow = 0;
```

**Verification:**
1. Find all four instances: `Ctrl+F` search for `break_from_lightshow ==`
2. Replace each with `break_from_lightshow =`
3. Verify no other logic issues
4. Test lightshow behavior on hardware

**Prevention:**
- Enable compiler warnings: Arduino IDE → Preferences → Show verbose output
- Use a linter: add static analysis to CI/CD pipeline
- Code review: look for `==` in statement context (should be rare)
- Test behavioral logic on hardware before deployment

**Action Items:**
- [ ] Fix all 4 instances of == → =
- [ ] Test lightshow sequence
- [ ] Test lightshow can be interrupted
- [ ] Merge fixes to main branch

---

### 21. Original_Cannon_Legacy — Wrong MQTT Broker IP

**Status:** ⚠️ ACTIVE — DEPRECATION RECOMMENDED

**File:** `Original_Cannon_Legacy` (design source or firmware)

**Symptoms:**
- Original cannon devices can't connect to MQTT system
- New cannon devices (Cannon1, Cannon2) work fine
- MQTT connections refused or timeout
- Device shows connected to wrong broker IP

**Root Cause:**
Hardcoded MQTT broker IP is incorrect:
```cpp
// WRONG: uses non-existent/wrong IP
#define MQTT_BROKER "10.1.10.130"

// Should be: (or remove entirely and use the new New-Cannons code)
#define MQTT_BROKER "10.1.10.115"
```

**Fix (Option 1: Update to correct IP):**
1. Find all instances of `10.1.10.130` in code
2. Replace with `10.1.10.115`
3. Recompile and deploy

**Fix (Option 2: Deprecate in favor of New-Cannons — RECOMMENDED):**
Since New-Cannons (Cannon1, Cannon2) are the newer, correct implementation:
1. Stop using Original_Cannon_Legacy code
2. Migrate to New-Cannons firmware
3. Archive Original_Cannon_Legacy code as historical reference
4. Document deprecation in README

**Prevention:**
- Never hardcode IPs in device firmware — use defines or config files
- Keep a "Broker Address Reference" document for cross-referencing
- Code review: verify IP addresses match network documentation
- Prefer New-Cannons over Original_Cannon_Legacy going forward

**Recommendation:**
**Deprecate Original_Cannon_Legacy entirely.** New-Cannons is the correct, working implementation. Maintaining two versions of the same device is error-prone.

**Action Items:**
- [ ] Verify New-Cannons are deployed and working in all locations
- [ ] Mark Original_Cannon_Legacy as DEPRECATED in README
- [ ] Archive Original_Cannon_Legacy source code
- [ ] Remove Original_Cannon_Legacy from active deployment documentation

---

### 22. Eleven-Labs-Avatar-Project — Exposed API Keys

**Status:** 🔴 CRITICAL — SECURITY BREACH

**File:** `Eleven-Labs-Avatar-Project/.env` (committed to git)

**Symptoms:**
- Credentials visible in public/shared repository
- Anyone with repo access can see API keys
- OpenAI and ElevenLabs API keys exposed

**Root Cause:**
1. `.env` file committed to git (should never happen)
2. No `.gitignore` to prevent committing sensitive files
3. Credentials hardcoded in repository instead of using environment variables or secure config

**Fix (IMMEDIATE — EMERGENCY):**

**Step 1: Rotate ALL API keys immediately**
- OpenAI: Log in → API Keys → Revoke all exposed keys → Create new keys
- ElevenLabs: Log in → API Keys → Revoke all exposed keys → Create new keys
- Update any systems using these keys with new keys ASAP

**Step 2: Clean git history**
```bash
# Remove .env from git history (requires force push)
git filter-branch --tree-filter 'rm -f Eleven-Labs-Avatar-Project/.env' --prune-empty -f HEAD

# Force push to remote (warning: rewrites history, affects all collaborators)
git push origin --force
```

**Step 3: Add .gitignore**
Create `.gitignore` in repository root:
```
.env
.env.local
.env.*.local
*.key
*.pem
secret*.json
```

**Step 4: Use environment variables instead**
Instead of `.env` in git, use:
```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load from local .env (not in git)

api_key = os.getenv("OPENAI_API_KEY")
eleven_labs_key = os.getenv("ELEVENLABS_API_KEY")
```

**Prevention:**
- **Never commit `.env` files** to any repository
- Add `.gitignore` to every project: include `.env`, `*.key`, `secrets/*`
- Use environment variables or secure configuration management
- Use pre-commit hooks to prevent committing sensitive files
- Code review: check for API keys before approving PRs
- Educate developers: credential exposure is a critical security issue

**Action Items:**
- [ ] **IMMEDIATELY rotate all exposed API keys** (OpenAI, ElevenLabs)
- [ ] Update Eleven-Labs-Avatar-Project with new keys
- [ ] Add `.gitignore` to Eleven-Labs-Avatar-Project
- [ ] Remove `.env` from git history (requires force push)
- [ ] Review other repositories for similar exposures
- [ ] Document API key handling policy for team

---

### 23. CabinDoor — Placeholder WiFi Credentials

**Status:** ⚠️ ACTIVE

**File:** `/sessions/elegant-dazzling-ptolemy/repos/CabinDoor/CabinDoor_S3.ino`

**Symptoms:**
- CabinDoor device won't connect to WiFi
- Serial output shows WiFi connection failure
- Device has placeholder credentials instead of real network

**Root Cause:**
Firmware contains hardcoded placeholder values:
```cpp
// WRONG: placeholder credentials
#define WIFI_SSID "YOUR_SSID"
#define WIFI_PASSWORD "YOUR_PASSWORD"
```

**Fix (immediate):**
1. Update both constants with actual network details:
   ```cpp
   #define WIFI_SSID "AlchemyGuest"
   #define WIFI_PASSWORD "VoodooVacuation5601"
   ```
2. Recompile and upload to device
3. Verify device connects to WiFi and MQTT

**Prevention:**
- Never leave placeholder values in device code
- Use a configuration template but never commit without real values
- Code review: catch placeholders before merge
- Document actual WiFi credentials in a secure location (not in git)

**Action Items:**
- [ ] Update WiFi SSID to "AlchemyGuest"
- [ ] Update WiFi password to "VoodooVacuation5601"
- [ ] Verify device connects to WiFi
- [ ] Verify device connects to MQTT
- [ ] Merge updated code

---

### 24. JungleDoor — Space in MQTT Topic Name

**Status:** ✓ RESOLVED — Fixed in MANIFEST.h v3.3.0 (2026-03-17). DEVICE_NAME is now "JungleDoor" (no space). Confirm deployed firmware matches.

**Symptoms:**
- M3 sends commands to JungleDoor
- Device doesn't receive commands
- WatchTower configuration expects "JungleDoor" (no space)
- Actual device topic has space: "Jungle Door"

**Root Cause:**
Device name defined with space:
```cpp
// WRONG: includes space
#define DEVICE_NAME "Jungle Door"

// Results in topic:
// MermaidsTale/Jungle Door/command  ← Space breaks MQTT routing
```

WatchTower expects:
```
MermaidsTale/JungleDoor/command     ← No space
```

**Fix (immediate):**
Remove space from device name:
```cpp
// CORRECT: no space
#define DEVICE_NAME "JungleDoor"

// Results in topic:
// MermaidsTale/JungleDoor/command  ← Matches WatchTower config
```

Recompile, upload, and verify device responds to commands.

**Prevention:**
- Device names must be CamelCase with no spaces
- Code review: verify DEVICE_NAME has no spaces
- Test MQTT topic names match WatchTower configuration
- Update naming standards documentation

**Action Items:**
- [ ] Remove space from DEVICE_NAME ("Jungle Door" → "JungleDoor")
- [ ] Verify device connects to MQTT at correct topic
- [ ] Verify M3/WatchTower commands reach device
- [ ] Merge updated code

---

## Troubleshooting Decision Trees

Use these flowcharts when diagnosing problems. Follow the decision path that matches your symptoms.

### Decision Tree 1: "Prop Not Responding"

```
START: Prop not responding to M3 commands
│
├─ Step 1: Is the prop powered?
│  ├─ NO: Check power supply, check USB connection, check battery
│  │      Resolve power issue → Restart prop → Retest
│  │
│  └─ YES: Continue to Step 2
│
├─ Step 2: Is WiFi connected?
│  ├─ NO: Check Serial output (open Arduino Serial Monitor)
│  │      Look for "WiFi connecting..." or WiFi error
│  │      Check SSID is "AlchemyGuest"
│  │      Check password is "VoodooVacuation5601"
│  │      Check router is online, no WiFi outage
│  │      → See Issue #8 (WiFi stuck in loop) if applicable
│  │
│  └─ YES: Proceed to Step 3
│
├─ Step 3: Is MQTT connected?
│  ├─ NO: Run on M3:
│  │      mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v
│  │      Look for ANY message from the device
│  │      If no messages: device isn't reaching broker
│  │      → Check router firewall allows device to reach 10.1.10.115
│  │      → Check mosquitto.conf listeners are 1860 and 1883
│  │      → See Issue #3 (Missing listeners) or #4 (Firewall blocking)
│  │
│  └─ YES: Proceed to Step 4
│
├─ Step 4: Is the topic name correct?
│  ├─ NO: Compare device code topic to WatchTower/M3 config topic
│  │      Update code to match WatchTower
│  │      See Network & Infrastructure Reference for correct topic names
│  │      → See Issue #9 (Wrong topic) or #24 (Space in topic)
│  │
│  └─ YES: Proceed to Step 5
│
├─ Step 5: Is the port correct?
│  ├─ NO: Check device code MQTT_PORT
│  │      Check mosquitto.conf listeners
│  │      Ensure device uses port 1883 (standard)
│  │      → See Issue #6 (Port mismatch)
│  │
│  └─ YES: Proceed to Step 6
│
├─ Step 6: Is the broker IP correct?
│  ├─ NO: Device hardcoded to wrong IP (e.g., 10.1.10.130)
│  │      Change to 10.1.10.115
│  │      → See Issue #21 (Wrong broker IP)
│  │
│  └─ YES: Proceed to Step 7
│
└─ Step 7: Manual command test
   Send PING directly:
   mosquitto_pub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/[DeviceName]/command" -m "PING"
   Watch mosquitto_sub window for "PONG" response
   ├─ Device responds PONG: Working! Issue is with M3 config, not prop
   │                        Check M3 trigger topic names
   │
   └─ No response: Device has deeper issue, escalate to hardware check
                    Verify device code has MQTT setup (WiFi, MQTT client init)
                    Check Serial Monitor for errors
```

### Decision Tree 2: "System Checker Shows False Positive"

```
START: System Checker shows device as ONLINE (green) when it shouldn't
│
├─ Step 1: Is the device actually built and installed?
│  ├─ NO: Mark device as "NOT_INSTALLED" in system_checker config
│  │      Don't track devices that don't exist
│  │
│  └─ YES: Proceed to Step 2
│
├─ Step 2: Is the topic matching too broad?
│  ├─ YES: system_checker config likely uses wildcard match "MermaidsTale/Device*"
│  │       Instead, require specific PONG response:
│  │       Code should verify message_topic = "...../command" AND payload = "PONG"
│  │       → See Issue #15 (False positives)
│  │
│  └─ NO: Proceed to Step 3
│
└─ Step 3: Is the device on the wrong port?
   Run: mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v
   AND: mosquitto_sub.exe -h 10.1.10.115 -p 1860 -t "MermaidsTale/#" -v
   ├─ Messages appear on 1860 but system_checker listens to 1883:
   │  → See Issue #6 (Port mismatch)
   │  → Align all devices to port 1883
   │
   └─ Messages appear on both or match system_checker port:
      Investigate why system_checker marked device online without PONG
      Review system_checker source code logic
```

### Decision Tree 3: "MQTT Messages Not Arriving"

```
START: Published messages not reaching subscribers
│
├─ Step 1: Is Mosquitto running?
│  ├─ NO: On M3, run: net start Mosquitto
│  │      Then: netstat -an | findstr "1883"
│  │      Should show LISTENING state
│  │      If not: Mosquitto service didn't start
│  │           Check Windows Event Viewer for errors
│  │
│  └─ YES: Proceed to Step 2
│
├─ Step 2: Is Windows Firewall blocking inbound?
│  ├─ YES: Add rules for TCP 1860 and 1883 in Windows Firewall
│  │       → See Issue #4 (Windows Firewall blocking)
│  │
│  └─ NO: Proceed to Step 3
│
├─ Step 3: Is there a port mismatch?
│  ├─ YES: All devices must use same port (recommend 1883)
│  │       Check config files, source code, mosquitto.conf
│  │       → See Issue #6 (Port mismatch)
│  │
│  └─ NO: Proceed to Step 4
│
└─ Step 4: Is the topic name exactly right?
   MQTT topics are case-sensitive
   ├─ YES: Debug with manual pub/sub:
   │       Publisher: mosquitto_pub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/Test/command" -m "HELLO"
   │       Subscriber: mosquitto_sub.exe -h 10.1.10.115 -p 1883 -t "MermaidsTale/#" -v
   │       If message appears in subscriber window: MQTT is working, issue is elsewhere
   │
   └─ NO: Fix topic name (case-sensitive, no spaces)
          Republish and retest
```

---

## Event Log & Resolution Tracking

Use this template to track issues as they occur, when they're resolved, and by whom.

### Event Log Template

```markdown
## [Issue ID] [Date] — [Brief Title]

**Reported by:** [Name]
**Severity:** CRITICAL / HIGH / MEDIUM / LOW
**Status:** OPEN / IN_PROGRESS / RESOLVED / NEEDS_MORE_INFO

### Symptom
[What the operator or system noticed]

### Diagnosis
[What tests were run, what was found]

### Root Cause
[What actually caused the problem]

### Resolution
[What was done to fix it]

### Resolution Time
[Date time opened] → [Date time closed] = [Duration]

### Escalation
- Level 1 (Ops/Troubleshooting): [Yes/No] — [Notes if needed]
- Level 2 (Hardware Tech): [Yes/No] — [Notes if needed]
- Level 3 (Software Dev): [Yes/No] — [Notes if needed]

### Prevention
[How to avoid this in the future]

### Notes
[Any additional context]

---
```

### Quick Incident Entry Template

For quick notes on temporary issues:

```
Date: ___________
Device: _________
Symptom: _______________________________
Quick Fix: ______________________________
Resolved: YES / NO / PARTIAL
Next Steps: _____________________________
```

---

## End of Debug Log & Known Issues

*Last updated: 2026*
*Active issues: 8 (Compilation errors: LuminousShell, ShipNavMap. Logic bugs: Balancing-Scale, Sun-Dial. Config issues: CabinDoor, JungleDoor. CRITICAL: Eleven-Labs-Avatar-Project keys exposed.)*
*Next review: When deploying new device or after any field issue*


---

### 25. Projectors — Wrong Display Output Assignments / Not Detected After Reboot

**Status:** ✓ RESOLVED

**Symptoms:**
- Projectors not detected by Windows after reboot or hardware changes
- Projectors outputting to wrong displays / wrong resolution
- Windows assigning projector outputs incorrectly from stale memory
- Display arrangement scrambled after moving to different ports

**Root Cause:**
Windows stores monitor/projector EDID and display configuration data in the registry. Over time (especially after connecting different monitors, rebooting, or changing ports), these entries become stale. Windows reads the old cached configuration instead of detecting hardware fresh, causing wrong output assignments.

**Fix:**

**Step 1 — Open Registry Editor as Admin**
- Press `Win + R` → type `regedit` → right-click → **Run as administrator**

**Step 2 — Delete subfolders in these registry locations**

Location 1:
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\DISPLAY
```
Delete all subfolders inside `DISPLAY` (e.g. DEL4048, GSV0808...). Do NOT delete the `DISPLAY` folder itself.

Location 2:
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Configuration
```
Delete all subfolders inside `Configuration`. Do NOT delete the `Configuration` folder itself.

Location 3 (recommended):
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Connectivity
```
Delete all subfolders inside `Connectivity`.

**Step 3 — If you get "Error deleting key" (permissions issue)**
1. Right-click the stubborn key → **Permissions** → **Advanced**
2. Change **Owner** to `Administrators`
3. Check **"Replace owner on subcontainers and objects"**
4. Click **Apply**
5. Grant `Administrators` **Full Control**
6. Retry the delete

**Step 4 — Device Manager cleanup**
1. Open **Device Manager**
2. Click **View** → **Show hidden devices**
3. Expand **Monitors**
4. Uninstall **all entries** (including grayed-out ghost monitors)

**Step 5 — Reboot**
Windows re-detects all connected projectors/monitors fresh and rebuilds registry entries from scratch.

**Step 6 — Reassign outputs**
After reboot, re-enter your display output assignments and projector mapping from scratch.

**Prevention:**
- Run this procedure any time projectors are physically moved to different ports
- Before a show opening if projectors behave unexpectedly after a PC reboot
- If new displays/monitors were connected to the PC at any point

**Lesson Learned:**
Windows aggressively caches monitor configurations. The registry doesn't clean itself — every display that was ever connected leaves an entry. Clearing all three registry locations (DISPLAY, Configuration, Connectivity) plus removing ghost monitors in Device Manager is the complete reset. Doing only one or two locations may not fully resolve the issue.


