# Alchemy Protocols

**A Living Operations Manual for Alchemy Escape Rooms Inc.**
**Game: "A Mermaid's Tale" — Fort Lauderdale, Florida**
**Last Updated: April 8, 2026**

---

## What Is This?

Alchemy Protocols is the single source of truth for every prop, every wire, every MQTT topic, every debug issue, and every procedure in the "A Mermaid's Tale" escape room. If something breaks at 6 PM on a Friday with a group in the room, this is the document you open.

---

## Table of Contents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Operations Manual](operations-manual.md) | Every prop/device — hardware, pins, MQTT topics, how to reset, how to test |
| 2 | [Network & Infrastructure](network-infrastructure.md) | MQTT broker setup, IP addresses, ports, M3/BAC integration, protocol standard |
| 3 | [Debug Log & Known Issues](debug-log.md) | Documented issues (resolved and active), troubleshooting decision trees |
| 4 | [System Checker Integration](system-checker-integration.md) | WatchTower dashboard — how it works, device inventory, pre-game checklist |
| 5 | [Wiring Reference](wiring-reference.md) | Pin-by-pin tables for every prop, I2C registry, relay logic, voltage levels |
| 6 | [Code Health Report](code-health-report.md) | Audit of all repos — consistency, security, error handling, versions |
| 7 | [TODO & Action Items](todo.md) | Prioritized checklist of open work |
| 8 | [Git Migration Guide](git-migration-guide.md) | Move repos out of OneDrive, folder structure, .gitignore template |
| 9 | [Git Best Practices](git-best-practices.md) | Commit strategy, two-machine workflow, commit message format |

### Protocol Standards (New)

| Document | Description |
|----------|-------------|
| [Manifest Protocol](manifest-protocol.md) | Standard for writing MANIFEST.h firmware files — @TAG reference, C++ namespace, file header template |
| [MQTT Protocol](mqtt-protocol.md) | MQTT broker config, topic structure, required commands, heartbeat standard, naming convention |
| [Quirks Registry](quirks-registry.md) | Cross-device firmware bugs and per-device known issues |

---

## Quick Links

### "Something Is Broken Right Now"
→ Start with the [Troubleshooting Decision Trees](debug-log.md#troubleshooting-decision-trees) in the Debug Log

### "I Need to Reset a Prop"
→ [Operations Manual](operations-manual.md) — find the prop, look at the "How to Reset" section

### "What MQTT Topic Does X Use?"
→ [Operations Manual](operations-manual.md) — every prop has an MQTT Topics table
→ [MQTT Protocol](mqtt-protocol.md) — the protocol standard

### "Is Everything Online Before a Game?"
→ [System Checker](system-checker-integration.md#pre-game-checklist) — pre-game verification procedure

### "I Need to Wire Up a New Prop"
→ [Wiring Reference](wiring-reference.md) — pin tables, I2C addresses, voltage levels

### "What Should I Fix Next?"
→ [TODO](todo.md) — prioritized from critical to nice-to-have

### "How Do I Write a MANIFEST.h?"
→ [Manifest Protocol](manifest-protocol.md) — complete authoring standard with @TAG reference

### "How Do I Use Git Properly?"
→ [Git Best Practices](git-best-practices.md) — commit strategy, two-machine workflow
→ [Git Migration Guide](git-migration-guide.md) — move repos out of OneDrive

---

## GitHub Repositories

| Organization | URL |
|---|---|
| Primary (current) | [Alchemy-Escape-Rooms-Inc](https://github.com/Alchemy-Escape-Rooms-Inc) |
| Legacy (personal) | [AlchemyEscapeRooms](https://github.com/AlchemyEscapeRooms) |

---

## How to Keep This Updated

This document library is only useful if it stays current. When you:

- **Add a new prop** → Add its section to the Operations Manual, Wiring Reference, and WatchTower config
- **Fix a bug** → Add a resolution entry to the Debug Log
- **Change wiring** → Update the Wiring Reference AND the prop's MANIFEST.h
- **Add/change MQTT topics** → Update the Operations Manual AND MQTT Protocol
- **Create a new repo** → Update the Code Health Report
- **Change a MANIFEST.h** → The Grimoire parser will auto-sync at 6 AM; no manual doc update needed

---

*Built by Claude for Clifford at Alchemy Escape Rooms Inc.*
