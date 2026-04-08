# Alchemy Grimoire — Summary Report

**Date: February 12, 2026**
**Analyst: Claude (Cowork)**
**For: Clifford, Alchemy Escape Rooms Inc.**

---

## 1. Total Repos Analyzed

| Source | Count | Escape Room Related | Other |
|--------|-------|--------------------:|------:|
| Alchemy-Escape-Rooms-Inc (org) | 27 | 23 | 4 (docs/web) |
| AlchemyEscapeRooms (personal) | 4 | 1 | 3 (trading/finance) |
| **Total** | **31** | **24** | **7** |

The 3 non-escape-room repos on the personal account (AI-Bot, Taz, SafetoSpend) are trading bots and a finance app — they have security issues (exposed API keys) but aren't part of the escape room system.

---

## 2. Total Props Documented

| Category | Count | Details |
|----------|------:|---------|
| BAC Controllers | 4 | Shattic, Captain, Cove, Jungle |
| ESP32/Arduino Props (with repos) | 18 | Cannons, Compass, Doors, Piston, Driftwood, Cuffs, Scale, Motion, Shells, Map, Panel, Dial, Fountain |
| Props in WatchTower Config (no repo) | 8 | Hieroglyphics, TridentReveal, StarCharts, MonkeyTombEntrance, TridentCabinet, MagicMirror2, StarTable, TridentAltar |
| Software Systems | 3 | WatchTower, CAISE/ElevenLabs, M3 |
| **Total Devices** | **33** | |

---

## 3. Protocol Compliance

### Alchemy MQTT Protocol (Watchtower Standard)

| Status | Count | Devices |
|--------|------:|---------|
| ✅ Fully Compliant | 4 | New-Cannons (x2), Compass (x3), Driftwood |
| ⚠️ Mostly Compliant | 4 | CabinDoor (no heartbeat), CoveSlidingDoor (30s heartbeat), JungleDoor (30s heartbeat — topic space resolved v3.3.0), BarrelPiston (no PING/PONG) |
| ⚠️ Partially Compliant | 2 | Wireless-Motion-Sensor (no PING/PONG/reset), AutomaticSlidingDoor (ESP32 version only) |
| ❌ Non-Compliant | 3 | hall-sensor-with-mqtt (different topics), Eleven-Labs (different broker), Original_Cannon_Legacy (wrong IP) |
| ❌ No Network | 5 | CaptainsCuffs, Balancing-Scale, Ruins-Wall-Panel, Sun-Dial, WaterFountain |
| ❌ Broken Code | 2 | LuminousShell (won't compile), ShipNavMap (won't compile) |
| ⚠️ Unknown | 8 | Props with no repo (Hieroglyphics, TridentReveal, etc.) |

**Bottom line: 4 out of ~20 networked devices are fully Watchtower-compliant.** The rest need varying levels of work.

---

## 4. Network Configuration Issues Found

| Issue | Severity | Details |
|-------|----------|---------|
| Original_Cannon_Legacy uses 10.1.10.130 | Critical | Should be 10.1.10.115 (or deprecate entirely) |
| Eleven-Labs-Avatar uses 10.1.10.228 | Critical | Different server — can't talk to props |
| JungleDoor topic space | ~~High~~ | ✅ RESOLVED in MANIFEST v3.3.0 — DEVICE_NAME = "JungleDoor" |
| CoveSlidingDoor 30s heartbeat | Medium | Should be 5min per standard |
| JungleDoor 30s heartbeat | Medium | Should be 5min per standard |
| CabinDoor placeholder credentials | Critical | Won't connect to WiFi with "YOUR_SSID" |
| BarrelPiston no PING/PONG | Medium | WatchTower can't health-check it |
| 5 standalone devices have no network | Medium | Can't be monitored or controlled remotely |

---

## 5. Top 10 Most Critical Issues (Ranked)

| # | Issue | Impact | Fix Effort |
|---|-------|--------|------------|
| 1 | **Exposed API keys** (Eleven-Labs .env, AI-Bot .env.txt, SafetoSpend .env) | Security breach risk — rotate immediately | 30 min |
| 2 | **LuminousShell won't compile** (undefined lightPin, variable mismatch) | Prop cannot be deployed | 15 min |
| 3 | **ShipNavMap won't compile** (CRGB typo, variable errors, logic bug) | Prop cannot be deployed | 15 min |
| 4 | **Balancing-Scale logic bugs** (SERVO_PIN undefined, always-false function, empty checkSuccess) | Puzzle can never be solved | 1 hour |
| 5 | **Sun-Dial == instead of =** (4 instances) | Light show can't be interrupted properly | 10 min |
| 6 | **CabinDoor placeholder WiFi creds** | Door controller can't connect | 5 min |
| 7 | **JungleDoor space in MQTT topic** | WatchTower can't find it, M3 commands may fail | 5 min |
| 8 | **Original_Cannon_Legacy wrong broker IP** | Cannon talks to nonexistent broker | Deprecate it |
| 9 | **8 devices in WatchTower with no code repos** | Can't verify, update, or debug firmware | Varies |
| 10 | **5 props with zero network connectivity** | No remote monitoring, no game integration | Days each |

---

## 6. Immediate Next Steps

Here's what I recommend you do first, in order:

### Today (30 minutes)
1. **Rotate the exposed API keys** — Change your OpenAI, ElevenLabs, Alpaca, NewsAPI, and Plaid credentials. The old ones are in git history permanently.
2. **Add .gitignore files** to the repos that have .env files committed (Eleven-Labs-Avatar-Project, SafetoSpend, AI-Bot)

### This Week (2-3 hours)
3. **Fix the 4 compilation/logic bugs** — LuminousShell, ShipNavMap, Balancing-Scale, Sun-Dial. These are quick code fixes.
4. **Fix CabinDoor WiFi credentials** and **JungleDoor topic name**. Both are one-line changes.
5. **Move your repos out of OneDrive** — Follow the migration guide. This prevents future git corruption.

### Next Two Weeks
6. **Add PING/PONG and heartbeat** to the 4 "mostly compliant" devices (CabinDoor, CoveSlidingDoor, JungleDoor, BarrelPiston)
7. **Update WatchTower config** — Mark unbuilt devices as NOT_INSTALLED, fix CoveSlidingDoor topic mismatch
8. **Decide what to do about the 5 offline props** — CaptainsCuffs, Balancing-Scale, Ruins-Wall-Panel, Sun-Dial, WaterFountain. Adding WiFi/MQTT is a bigger project but makes everything monitorable.

### Ongoing
9. **Use this Grimoire** — When you fix something, log it. When you add a prop, document it. When you change wiring, update it.
10. **Follow the git practices guide** — Pull before you edit, push before you leave. Use descriptive commit messages.

---

## Repository Health at a Glance

```
EXCELLENT  ████████░░░░░░░░░░░░  4 repos  (New-Cannons, Compass, Driftwood, JungleDoor)
GOOD       ██████████░░░░░░░░░░  5 repos  (CoveSlidingDoor, BarrelPiston, CabinDoor_S3, HallSensor, WatchTower)
FAIR       ████████░░░░░░░░░░░░  4 repos  (Wireless-Motion, AutoSlidingDoor, CaptainsCuffs, Ruins-Wall-Panel)
POOR       ████░░░░░░░░░░░░░░░░  2 repos  (WaterFountain, Sun-Dial)
BROKEN     ██████░░░░░░░░░░░░░░  3 repos  (LuminousShell, ShipNavMap, Balancing-Scale)
SECURITY   ██████░░░░░░░░░░░░░░  3 repos  (Eleven-Labs, AI-Bot, SafetoSpend)
DOCS/OTHER ██████████████░░░░░░  7 repos  (BACIntegration, GravityGamesDocs, etc.)
DEPRECATED ██░░░░░░░░░░░░░░░░░░  1 repo   (Original_Cannon_Legacy)
NOT ESCAPE ████░░░░░░░░░░░░░░░░  2 repos  (AI-Bot, Taz — trading bots)
```

---

*This report was generated from a complete audit of 31 GitHub repositories, totaling approximately 6,000+ lines of firmware source code across both the Alchemy-Escape-Rooms-Inc organization and AlchemyEscapeRooms personal account.*

