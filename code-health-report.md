# Code Health Report — Alchemy Escape Rooms Grimoire

**Generated:** 2026-02-12
**Total Repositories:** 31 (27 Primary Org + 4 Legacy)
**Overall Status:** 🔴 CRITICAL — Multiple compilation failures, security exposures, and network inconsistencies

---

## Repository Overview (ALL 31 repos)

### Primary Org (Alchemy-Escape-Rooms-Inc) — 27 repos

| Repo | Type | Board | README | .gitignore | LICENSE | Commits | Last Updated | Health |
|------|------|-------|--------|------------|---------|---------|--------------|--------|
| AutomaticSlidingDoor | Door controller | Arduino R4/ESP32-S3 | ❌ | ❌ | ❌ | 13 | Nov 2025 | ⚠️ FAIR |
| BACIntegration | Documentation | N/A | ⚠️ minimal | ❌ | ❌ | 2 | Dec 2024 | 📄 Docs only |
| Balancing-Scale | Puzzle | Arduino Nano | ✅ | ❌ | ❌ | 49 | Jan 2026 | ❌ BROKEN |
| Barrel-Piston | Piston controller | ESP32 | ❌ | ❌ | ❌ | 2 | Oct 2025 | ✅ GOOD |
| CabinDoor | Door controller | ESP32-S3 | ❌ | ❌ | ❌ | 1 | Jan 2026 | ⚠️ Placeholder creds |
| Captains-Cuffs | Puzzle | Arduino Mega | ⚠️ minimal | ❌ | ❌ | 3 | Feb 2026 | ⚠️ FAIR (no MQTT) |
| Coming-Soon-Page | Website | N/A | ❌ | ❌ | ❌ | 10 | Nov 2025 | 🌐 Not hardware |
| Compass | Puzzle | ESP32-S3 | ✅ | ❌ | ❌ | 2 | Feb 2026 | ✅ EXCELLENT |
| CoveSlidingDoor | Door controller | ESP32-S3 | ❌ | ❌ | ❌ | 1 | Feb 2026 | ✅ GOOD |
| Driftwood | Puzzle | ESP32-S3 | ❌ | ❌ | ❌ | 2 | Jan 2026 | ✅ EXCELLENT |
| ESP-IDE | Template | ESP32-S3 | ⚠️ minimal | ❌ | ❌ | 2 | Dec 2024 | 📄 Template |
| Eleven-Labs-Avatar-Project | AI Game Master | Node.js | ❌ | ❌ | ❌ | 2 | Nov 2025 | ❌ SECURITY (exposed keys) |
| GravityGamesDocumentation | Documentation | N/A | ❌ | ❌ | ❌ | 3 | Oct 2025 | 📄 Docs only |
| HallSensor | Sensor Library | ESP32 | ✅ | ✅ | ❌ | 7 | Oct 2025 | ✅ GOOD (library) |
| JungleDoor | Door controller | ESP32-S3 | ❌ | ❌ | ❌ | 1 | Feb 2026 | ✅ GOOD |
| LuminousShell | Sensor/LED | ESP32/8266 | ❌ | ❌ | ❌ | 2 | Feb 2026 | ❌ BROKEN (won't compile) |
| Master-Puzzle-Outline | Documentation | N/A | ❌ | ❌ | ❌ | 1 | Sep 2025 | 📄 Docs only |
| New-Cannons | Puzzle | ESP32-S3 | ❌ | ✅ | ❌ | 28 | Jan 2026 | ✅ EXCELLENT |
| Original_Cannon_Legacy | Legacy cannon | ESP32 | ✅ | ✅ | ❌ | 8 | Aug 2025 | ❌ DEPRECATED (wrong IP) |
| PirateWheel | CAD designs | N/A | ✅ | ❌ | ❌ | 3 | Dec 2024 | 📄 Design only |
| Ruins-Wall-Panel | Puzzle | Arduino Mega | ❌ | ❌ | ❌ | 22 | Dec 2025 | ⚠️ FAIR (no network) |
| ShipNavMap | LED display | ESP8266/32 | ❌ | ❌ | ❌ | 2 | Feb 2026 | ❌ BROKEN (won't compile) |
| Sun-Dial | Puzzle | 2x Arduino | ❌ | ❌ | ❌ | 1 | Oct 2025 | ⚠️ BUGS (== vs =) |
| WatchTower | Dashboard | Python | ✅ | ❌ | ❌ | 2 | Jan 2026 | ✅ GOOD |
| WaterFountain | Puzzle | Arduino | ❌ | ❌ | ❌ | 6 | Nov 2025 | ⚠️ FAIR (no network) |
| Wireless-Motion-Sensor | Sensor | ESP8266 | ❌ | ❌ | ❌ | 11 | Jan 2026 | ⚠️ FAIR |
| hall-sensor-with-mqtt | Sensor | ESP32-S3 | ❌ | ✅ | ❌ | 1 | Oct 2025 | ⚠️ Non-standard topics |

### Legacy Account (AlchemyEscapeRooms) — 4 repos

| Repo | Type | Board | README | .gitignore | LICENSE | Commits | Last Updated | Health |
|------|------|-------|--------|------------|---------|---------|--------------|--------|
| AI-Bot | Trading bot | Python | ❌ | ✅ | ❌ | 26 | Dec 2025 | ❌ SECURITY (API keys) |
| CabinDoor_S3 | Door controller | ESP32-S3 | ❌ | ✅ | ❌ | 2 | Feb 2026 | ✅ GOOD |
| SafetoSpend | Finance app | Python | ✅ | ❌ | ✅ | 1 | Jan 2026 | ❌ SECURITY (no .gitignore) |
| Taz | Trading bot | Python | ❌ | ✅ | ❌ | 6 | Dec 2025 | Not escape-room |

---

## Broker IP Consistency

Table showing what IP each repo uses:

| IP Address | Status | Repos |
|------------|--------|-------|
| 10.1.10.115 | ✅ CORRECT | New-Cannons, Compass, CabinDoor, CabinDoor_S3, CoveSlidingDoor, JungleDoor, Driftwood, BarrelPiston, Wireless-Motion, LuminousShell, ShipNavMap, hall-sensor-with-mqtt, WatchTower |
| 10.1.10.130 | ❌ WRONG | Original_Cannon_Legacy |
| 10.1.10.228 | ⚠️ DIFFERENT SERVER | Eleven-Labs-Avatar-Project |
| N/A | ⚠️ No network | CaptainsCuffs, BalancingScale, Ruins-Wall-Panel, SunDial, WaterFountain, AutomaticSlidingDoor (Arduino R4) |

---

## MQTT Port Consistency

| Port | Status | Usage |
|------|--------|-------|
| 1883 | ✅ Standard | All networked devices use this consistently |
| 1860 | ⚠️ Custom | M3 game controller (configured in mosquitto.conf, not in device code) |

---

## Topic Naming Audit

**Standard Format:** `MermaidsTale/{PropName}/command`, `/status`, `/log`

### Compliant Repos ✅
- New-Cannons
- Compass
- CabinDoor
- CoveSlidingDoor
- Driftwood
- JungleDoor (except space in name)

### Partial Compliance ⚠️
| Repo | Issue |
|------|-------|
| BarrelPiston | Uses `/Engaged`, `/Retract` instead of `/command` |
| Wireless-Motion | Flat topic structure |
| LuminousShell | Uses `Shell1` instead of standard naming |

### Non-Compliant ❌
| Repo | Topic Structure |
|------|-----------------|
| hall-sensor-with-mqtt | `sensor/*` prefix |
| Eleven-Labs | `smarthome/*`, `escaperoom/*` |
| Original_Cannon | No `/command` structure |
| ShipNavMap | Mixed prefix |

---

## Missing .gitignore (26 of 31 repos)

Repos WITHOUT .gitignore:
1. AutomaticSlidingDoor
2. BACIntegration
3. Balancing-Scale
4. Barrel-Piston
5. CabinDoor
6. Captains-Cuffs
7. Coming-Soon-Page
8. Compass
9. CoveSlidingDoor
10. Driftwood
11. ESP-IDE
12. Eleven-Labs-Avatar-Project
13. GravityGamesDocumentation
14. JungleDoor
15. LuminousShell
16. Master-Puzzle-Outline
17. New-Cannons (has .gitignore ✅)
18. Original_Cannon_Legacy (has .gitignore ✅)
19. PirateWheel
20. Ruins-Wall-Panel
21. SafetoSpend
22. ShipNavMap
23. Sun-Dial
24. WatchTower
25. WaterFountain
26. Wireless-Motion-Sensor

**Repos WITH .gitignore (5 total):**
- AI-Bot ✅
- CabinDoor_S3 ✅
- HallSensor ✅
- New-Cannons ✅
- Original_Cannon_Legacy ✅
- Taz ✅
- hall-sensor-with-mqtt ✅

---

## Firmware Version Tracking

| Device | Version | Location |
|--------|---------|----------|
| New-Cannons | 3.2.0 | src/main.cpp line 19 |
| Compass | 1.0.0 | BlueCompass/src/main.cpp |
| CabinDoor | 1.0.0 | CabinDoor_S3.ino |
| CabinDoor_S3 | 1.1.0 | CabinDoor_S3.ino |
| CoveSlidingDoor | 1.0.0 | src/main.cpp |
| Driftwood | 2.2.5 | Code define |
| JungleDoor | 2.7.0 | JungleDoor.ino line 42 |
| **All others** | None | **No version string** |

---

## Error Handling Quality

| Rating | Count | Devices |
|--------|-------|---------|
| EXCELLENT | 3 | New-Cannons, Driftwood, JungleDoor |
| GOOD | 5 | CoveSlidingDoor, BarrelPiston, CabinDoor_S3, Compass, WatchTower |
| FAIR | 3 | Wireless-Motion-Sensor, AutomaticSlidingDoor, CaptainsCuffs |
| POOR | 4 | WaterFountain, Ruins-Wall-Panel, Sun-Dial, Original_Cannon_Legacy |
| BROKEN | 3 | LuminousShell (won't compile), ShipNavMap (won't compile), Balancing-Scale (logic bugs) |

---

## Security Concerns

### 🔴 CRITICAL ISSUES

| Repo | Issue | Details |
|------|-------|---------|
| Eleven-Labs-Avatar-Project | Exposed API Keys | .env committed with OpenAI API key (sk-proj-...), ElevenLabs DID agent ID and client key |
| AI-Bot | Exposed API Keys | .env.txt committed with Alpaca API key/secret, NewsAPI key |
| SafetoSpend | Multiple Issues | .env committed with Plaid sandbox credentials, **NO .gitignore at all** |

### 🟡 MEDIUM ISSUES

| Repo | Issue | Details |
|------|-------|---------|
| All ESP32 repos | Hardcoded WiFi Creds | `AlchemyGuest` / `VoodooVacation5601` in source code (acceptable for local network but documented) |
| CabinDoor | Placeholder Credentials | "YOUR_SSID"/"YOUR_PASSWORD" never replaced |

---

## Summary Statistics

| Metric | Count | Percentage |
|--------|-------|-----------|
| Total Repos | 31 | 100% |
| With README | 8 | 26% |
| With .gitignore | 7 | 23% |
| With LICENSE | 1 | 3% |
| Compilation-Ready | 28 | 90% |
| Broken (won't compile) | 3 | 10% |
| Network-Enabled | 24 | 77% |
| Standalone/Isolated | 7 | 23% |
| Security Issues | 3 CRITICAL | 10% |
| MQTT-Compliant | 6 | 19% |

---

## Recommended Priority Actions

1. **IMMEDIATE:** Rotate exposed API keys (Eleven-Labs, AI-Bot, SafetoSpend)
2. **URGENT:** Fix compilation errors (LuminousShell, ShipNavMap, Balancing-Scale)
3. **THIS WEEK:** Standardize MQTT topics and broker IPs
4. **THIS MONTH:** Add .gitignore to all remaining repos
5. **THIS QUARTER:** Add README and version tracking to all hardware repos


---

## Auto-Scan Update — 2026-02-24 06:19 AM EST

The following repos were updated since the last Grimoire revision:


### LuminousShell (updated)
- Source files: 1 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-03 06:14 AM EST

The following repos were updated since the last Grimoire revision:


### Ruins-Wall-Panel (updated)
- Source files: 4 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-07 06:06 AM EST

The following repos were updated since the last Grimoire revision:


### JungleDoor (updated)
- Source files: 2 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-08 07:06 AM EST

The following repos were updated since the last Grimoire revision:


### LuminousShell (updated)
- Source files: 1 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-10 07:14 AM EST

The following repos were updated since the last Grimoire revision:


### JungleDoor (updated)
- Source files: 2 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected

### LuminousShell (updated)
- Source files: 1 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-11 07:15 AM EST

The following repos were updated since the last Grimoire revision:


### New-Cannons (updated)
- Source files: 29 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: Yes | Main source: Yes
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected

### JungleDoor (updated)
- Source files: 2 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected

### Driftwood (updated)
- Source files: 17 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: Yes | Main source: No
- Broker IPs found (verify correctness)

### Ruins-Wall-Panel (updated)
- Source files: 4 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected

### WaterFountain (updated)
- Source files: 2 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No

### Eleven-Labs-Avatar-Project (updated)
- Source files: 0 C/C++, 8 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*

---

## Auto-Scan Update — 2026-03-12 07:14 AM EST

The following repos were updated since the last Grimoire revision:


### JungleDoor (updated)
- Source files: 2 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected

### LuminousShell (updated)
- Source files: 1 C/C++, 0 JS/TS, 0 Python
- PlatformIO config: No | Main source: No
- Broker IPs found (verify correctness)
- ⚠️ Potential exposed secrets detected


*Full regeneration recommended via Cowork. This is an automated snapshot only.*
