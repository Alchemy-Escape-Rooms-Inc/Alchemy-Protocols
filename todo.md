# TODO & Action Items — Alchemy Escape Rooms Grimoire

**Last Updated:** 2026-02-12
**Total Open Items:** 47
**Critical Blockers:** 8

---

## 🔴 CRITICAL — Game-Day Failures

These items block gameplay and must be fixed before next operation.

- [ ] **Fix LuminousShell compilation**
  - [ ] Define `lightPin` constant
  - [ ] Fix `client` vs `mqtt` variable naming
  - [ ] Test LED output on ESP32/8266
  - **Repo:** [LuminousShell](https://github.com/Alchemy-Escape-Rooms-Inc/LuminousShell)
  - **File:** `LuminousShell.ino`
  - **Severity:** CRITICAL — Device won't compile

- [ ] **Fix ShipNavMap compilation**
  - [ ] Fix `CGRB` → `CRGB` typo in includes
  - [ ] Fix undefined variable names in LED array
  - [ ] Fix backwards WiFi reconnect logic
  - [ ] Verify FastLED library version compatibility
  - **Repo:** [ShipNavMap](https://github.com/Alchemy-Escape-Rooms-Inc/ShipNavMap)
  - **File:** `ShipCoordinate.ino`
  - **Severity:** CRITICAL — Device won't compile

- [x] **Fix Balancing-Scale bugs** ✅ RESOLVED, firmware is ESP32 v1.4.9
  - [x] Define `SERVO_PIN` constant (GPIO 13)
  - [x] Fix `isAlreadyStored()` return value
  - [x] Implement `checkSuccess()` function logic
  - [x] Test servo movement and weight detection
  - **Repo:** [Balancing-Scale](https://github.com/Alchemy-Escape-Rooms-Inc/Balancing-Scale)
  - **File:** `Code/BalancingScale/BalancingScale.ino`

- [ ] **Fix Sun-Dial assignment bugs**
  - [ ] Line 262: Change `==` to `=` (assignment)
  - [ ] Line 280: Change `==` to `=` (assignment)
  - [ ] Line 297: Change `==` to `=` (assignment)
  - [ ] Line 317: Change `==` to `=` (assignment)
  - [ ] Test all four dials with expected inputs
  - **Repo:** [Sun-Dial](https://github.com/Alchemy-Escape-Rooms-Inc/Sun-Dial)
  - **File:** `Sand_dial_new_boards_FINAL.ino`
  - **Severity:** CRITICAL — Puzzle unsolvable due to logic errors

- [ ] **Rotate exposed API keys** (SECURITY)
  - [ ] Regenerate OpenAI API key and update Eleven-Labs-Avatar-Project
  - [ ] Regenerate ElevenLabs DID agent credentials
  - [ ] Regenerate Alpaca API key/secret and update AI-Bot
  - [ ] Regenerate NewsAPI key and update AI-Bot
  - [ ] Regenerate Plaid sandbox credentials and update SafetoSpend
  - [ ] Review git history and consider force-push if credentials not rotated in 24h
  - **Repos:** Eleven-Labs-Avatar-Project, AI-Bot, SafetoSpend
  - **Severity:** CRITICAL — Production credentials exposed in public repos

- [ ] **Fix CabinDoor WiFi creds**
  - [ ] Replace `"YOUR_SSID"` with actual WiFi network name
  - [ ] Replace `"YOUR_PASSWORD"` with actual WiFi password
  - [ ] Verify WiFi connection on first startup
  - **Repo:** [CabinDoor](https://github.com/Alchemy-Escape-Rooms-Inc/CabinDoor)
  - **File:** `CabinDoor_S3.ino` lines 45-46
  - **Severity:** CRITICAL — Device cannot connect to network

- [ ] **Fix JungleDoor topic name**
  - [ ] Remove space in DEVICE_NAME: `"Jungle Door"` → `"JungleDoor"`
  - [ ] Update all topic subscriptions to use new name without space
  - [ ] Verify MQTT connection with new topic name
  - **Repo:** [JungleDoor](https://github.com/Alchemy-Escape-Rooms-Inc/JungleDoor)
  - **File:** `JungleDoor.ino` line XX
  - **Severity:** CRITICAL — Topic name incompatible with broker standards

- [ ] **Deprecate Original_Cannon_Legacy**
  - [ ] Wrong MQTT broker IP (10.1.10.130 instead of 10.1.10.115)
  - [ ] No error recovery or reconnection logic
  - [ ] Migrate all dependencies to New-Cannons (superior implementation)
  - [ ] Archive repository and add deprecation notice to README
  - **Repo:** [Original_Cannon_Legacy](https://github.com/Alchemy-Escape-Rooms-Inc/Original_Cannon_Legacy)
  - **Severity:** CRITICAL — Wrong broker prevents gameplay

---

## 🟡 IMPORTANT — Reliability & Maintainability

These items improve stability and standardization. High priority but not game-blocking.

### Network & MQTT Standardization

| Task | Status | Repos Affected | Details |
|------|--------|----------------|---------|
| Add PING/PONG health check to BarrelPiston | - [ ] | BarrelPiston | Implement keep-alive mechanism |
| Add 5-min heartbeat to CabinDoor | - [ ] | CabinDoor | Send status message every 5 minutes |
| Add 5-min heartbeat to BarrelPiston | - [ ] | BarrelPiston | Currently has no heartbeat |
| Standardize CoveSlidingDoor heartbeat (30s → 5min) | - [ ] | CoveSlidingDoor | Reduce frequency to reduce load |
| Standardize JungleDoor heartbeat (30s → 5min) | - [ ] | JungleDoor | Reduce frequency to reduce load |
| Fix Eleven-Labs broker IP (10.1.10.228 → 10.1.10.115) | - [ ] | Eleven-Labs-Avatar-Project | Use correct main broker |
| Fix Eleven-Labs topic naming (smarthome/*, escaperoom/* → MermaidsTale/*) | - [ ] | Eleven-Labs-Avatar-Project | Standardize to main convention |
| Align hall-sensor topics to standard (sensor/* → MermaidsTale/Driftwood/*) | - [ ] | hall-sensor-with-mqtt | Match other sensor implementations |

### Network Connectivity — Add WiFi+MQTT

These devices currently have no network connection and should be networked for integration:

| Device | Current Status | Target | Effort | Files |
|--------|----------------|--------|--------|-------|
| CaptainsCuffs | Serial-only | WiFi+MQTT | Medium | Captains-Cuffs.ino |
| Ruins-Wall-Panel | Standalone | WiFi+MQTT | Medium | Ruins_Wall_Panel.ino |
| Sun-Dial | Standalone (2 boards) | WiFi+MQTT | High | Sand_dial_new_boards_FINAL.ino |
| WaterFountain | Standalone | WiFi+MQTT | Medium | WaterFountain.ino |
| Balancing-Scale | WiFi+MQTT (done) | WiFi+MQTT | Done | Code/BalancingScale/BalancingScale.ino |

- [ ] **Add WiFi+MQTT to CaptainsCuffs**
  - [ ] Add ESP32 or ESP8266 module for WiFi
  - [ ] Implement standard MQTT connection pattern (see New-Cannons)
  - [ ] Test topic: `MermaidsTale/CaptainsCuffs/command`
  - **Repo:** [Captains-Cuffs](https://github.com/Alchemy-Escape-Rooms-Inc/Captains-Cuffs)

- [ ] **Add WiFi+MQTT to Ruins-Wall-Panel**
  - [ ] Upgrade from Arduino Mega to ESP32-S3 (same board as others)
  - [ ] Implement MQTT connection
  - [ ] Preserve existing servo/relay logic
  - **Repo:** [Ruins-Wall-Panel](https://github.com/Alchemy-Escape-Rooms-Inc/Ruins-Wall-Panel)

- [ ] **Add WiFi+MQTT to Sun-Dial**
  - [ ] Coordinate both Arduino boards with single WiFi module
  - [ ] Implement master/slave communication between boards
  - [ ] Test MQTT with both dial positions
  - **Repo:** [Sun-Dial](https://github.com/Alchemy-Escape-Rooms-Inc/Sun-Dial)

- [ ] **Add WiFi+MQTT to WaterFountain**
  - [ ] Upgrade from Arduino to ESP32-S3
  - [ ] Implement MQTT control for pump
  - [ ] Add water level sensor integration
  - **Repo:** [WaterFountain](https://github.com/Alchemy-Escape-Rooms-Inc/WaterFountain)

- [x] **Add WiFi+MQTT to Balancing-Scale** ✅ RESOLVED, classic ESP32, not an ESP32-S3
  - [x] Upgrade from Arduino Nano to ESP32
  - [x] Implement MQTT status reporting
  - [x] Test weight detection over network
  - **Repo:** [Balancing-Scale](https://github.com/Alchemy-Escape-Rooms-Inc/Balancing-Scale)

### Device-Specific Improvements

- [ ] **Update WatchTower config**
  - [ ] Mark non-built devices as NOT_INSTALLED
  - [ ] Verify all active devices are tracked
  - **Repo:** [WatchTower](https://github.com/Alchemy-Escape-Rooms-Inc/WatchTower)
  - **File:** config.json

- [ ] **Decide production version: AutomaticSlidingDoor**
  - [ ] Compare Arduino R4 vs ESP32-S3 implementations
  - [ ] Benchmark performance and power consumption
  - [ ] Choose one board type for standardization
  - **Repo:** [AutomaticSlidingDoor](https://github.com/Alchemy-Escape-Rooms-Inc/AutomaticSlidingDoor)

- [ ] **Merge CabinDoor repos into one canonical repository**
  - [ ] Compare CabinDoor and CabinDoor_S3 implementations
  - [ ] Keep CabinDoor_S3 (ESP32-S3, more modern)
  - [ ] Deprecate CabinDoor repo
  - [ ] Add migration notes for anyone using old repo
  - **Repos:** CabinDoor, CabinDoor_S3

- [ ] **Add RESET/STATUS to Wireless-Motion-Sensor**
  - [ ] Implement MQTT RESET command to clear detection state
  - [ ] Add /status topic to report motion state
  - [ ] Test commands from WatchTower dashboard
  - **Repo:** [Wireless-Motion-Sensor](https://github.com/Alchemy-Escape-Rooms-Inc/Wireless-Motion-Sensor)

- [ ] **Fix Wireless-Motion hardcoded client ID**
  - [ ] Make client ID based on MAC address or device serial
  - [ ] Prevents conflicts with multiple units in same room
  - [ ] Test with 2+ sensors deployed simultaneously
  - **Repo:** [Wireless-Motion-Sensor](https://github.com/Alchemy-Escape-Rooms-Inc/Wireless-Motion-Sensor)

---

## 🟢 NICE TO HAVE — Professionalism & Scaling

Lower priority but improves code quality and attractiveness for open-source/team collaboration.

### Documentation

- [ ] **Add README to 28 repos** (only 3 have adequate ones: HallSensor, WatchTower, Compass)
  - [ ] Include: Purpose, hardware requirements, wiring diagram link, MQTT topics, build instructions
  - [ ] Use template from git-best-practices.md
  - **Affected Repos:** AutomaticSlidingDoor, BACIntegration, Balancing-Scale, Barrel-Piston, CabinDoor, Captains-Cuffs, Coming-Soon-Page, CoveSlidingDoor, Driftwood, ESP-IDE, Eleven-Labs-Avatar-Project, GravityGamesDocumentation, JungleDoor, LuminousShell, Master-Puzzle-Outline, New-Cannons, Original_Cannon_Legacy, PirateWheel, Ruins-Wall-Panel, SafetoSpend, ShipNavMap, Sun-Dial, Taz, WaterFountain, Wireless-Motion-Sensor, hall-sensor-with-mqtt (26 repos)

### .gitignore & Security

| Task | Status | Count | Details |
|------|--------|-------|---------|
| Add .gitignore to remaining repos | - [ ] | 26 repos | Use template from git-best-practices.md |
| Add LICENSE to all repos | - [ ] | 30 repos | Use MIT license (only SafetoSpend has one) |

- [ ] **Create standard .gitignore template**
  - [ ] Ignore: `*.elf`, `*.bin`, `build/`, `.vscode/`, `.env`, `*.pem`, `node_modules/`
  - [ ] See git-migration-guide.md for full template
  - [ ] Apply to all 26 repos without .gitignore
  - **Reference:** `/sessions/elegant-dazzling-ptolemy/mnt/Alchemy Grimoire/Alchemy-Grimoire/git-migration-guide.md`

### Version Control & Firmware Management

| Task | Status | Details |
|------|--------|---------|
| Add firmware version strings to all unversioned devices | - [ ] | 20+ devices need semantic versioning (v1.0.0 format) |
| Create shared WiFi+MQTT Arduino library | - [ ] | Reduce code duplication across 13+ ESP32 projects |
| Standardize serial baud rates | - [ ] | Currently mixed (9600 vs 115200) — choose one standard |
| Clean up stale branches | - [ ] | AI-Bot: 4 branches, Taz: 1 branch, Driftwood: 1 branch |

### Hardware & Deployment

- [ ] **Move all repos out of OneDrive**
  - [ ] See git-migration-guide.md for detailed procedure
  - [ ] Backup OneDrive copies before migration
  - [ ] Verify all repos are accessible on GitHub

- [ ] **Add OTA firmware update to all ESP32 devices**
  - [ ] Implement ArduinoOTA library in all 13+ ESP32 repos
  - [ ] Test wireless firmware push from WatchTower
  - [ ] Document update procedure

- [ ] **Consider mDNS for MQTT broker discovery**
  - [ ] Simplify broker IP configuration
  - [ ] Use `mqtt.local` instead of hardcoded IP
  - [ ] Implement across all MQTT clients

### Missing Device Repositories

These 8 physical devices exist but have no code repos. Create repositories for them:

| Device | Room | Type | Priority |
|--------|------|------|----------|
| Hieroglyphics | ? | ? | - [ ] |
| TridentReveal | ? | ? | - [ ] |
| StarCharts | ? | ? | - [ ] |
| MonkeyTombEntrance | ? | ? | - [ ] |
| TridentCabinet | ? | ? | - [ ] |
| MagicMirror2 | ? | ? | - [ ] |
| StarTable | ? | ? | - [ ] |
| TridentAltar | ? | ? | - [ ] |

- [ ] **Create repositories for 8 missing devices**
  - [ ] Determine what hardware/purpose each device has
  - [ ] Create GitHub repos with proper board type and MQTT topics
  - [ ] Add initial firmware skeletons
  - [ ] Add to WatchTower device registry

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| CRITICAL items | 8 | 🔴 BLOCKING |
| IMPORTANT items | 15 | 🟡 HIGH PRIORITY |
| NICE TO HAVE items | 24 | 🟢 MEDIUM PRIORITY |
| **TOTAL** | **47** | **Open** |

### Quick Reference: Blocking Issues

These 8 items **must** be resolved before next game operation:

1. LuminousShell — Won't compile
2. ShipNavMap — Won't compile
3. ~~Balancing-Scale — Logic bugs prevent completion~~ ✅ RESOLVED (ESP32 v1.4.9)
4. Sun-Dial — Assignment operator bugs
5. API keys — Exposed in repositories
6. CabinDoor — No WiFi credentials
7. JungleDoor — Topic name has space
8. Original_Cannon — Wrong broker IP

---

## Related Documents

- [Code Health Report](./code-health-report.md) — Detailed analysis of all 31 repos
- [Git Best Practices](./git-best-practices.md) — Standards and workflow guidelines
- [Git Migration Guide](./git-migration-guide.md) — How to migrate repos from OneDrive to GitHub
- [Network Infrastructure](./network-infrastructure.md) — MQTT broker and device networking details
- [Operations Manual](./operations-manual.md) — Day-to-day procedures and troubleshooting


