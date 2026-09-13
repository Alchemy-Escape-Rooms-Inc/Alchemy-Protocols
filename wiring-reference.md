# Wiring Reference — A Mermaid's Tale

## Pin Assignment Tables by Device

### New-Cannons (ESP32-S3)
**Devices:** Cannon1, Cannon2
**Firmware:** v3.2.0

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 15 | I2C SDA | IN/OUT | Shared I2C bus |
| GPIO 18 | I2C SCL | IN/OUT | Shared I2C bus |
| GPIO 35 | Button Input | IN | Fire button (digital read) |
| I2C 0x29 | VL6180X | I2C | Reload distance sensor |
| I2C 0x01/0x60-0x6F | ALS31300 | I2C | Aim angle sensor (auto-detect) |

---

### Compass (ESP32-S3)
**Devices:** BlueCompass, RoseCompass, SilverCompass
**Firmware:** v1.0.0

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 4 | Potentiometer ADC | IN | 12-bit (0-4095), 11dB attenuation, maps 0-359° |

---

### CabinDoor (ESP32-S3)
**Firmware:** v1.0.0 / v1.1.0

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 4 | Relay Extend (Relay 1) | OUT | Open door, Active LOW |
| GPIO 5 | Relay Retract (Relay 2) | OUT | Close door, Active LOW |

**Relay Logic:** Active LOW (LOW = relay energized/engaged)

---

### CoveDoor (ESP32)
**Firmware:** v1.0.0

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 2 | MOTOR_IN1 | OUT | XY160D direction A — HIGH+LOW2=open |
| GPIO 5 | MOTOR_IN2 | OUT | XY160D direction B — LOW1+HIGH=close |
| GPIO 4 | MOTOR_ENA | OUT | XY160D PWM speed control (0-255) |
| GPIO 16 | LIMIT_OPEN | IN | Magnetic reed switch, INPUT_PULLUP, active LOW |
| GPIO 32 | LIMIT_CLOSED | IN | Magnetic reed switch, INPUT_PULLUP, active LOW |

**Motor Driver:** XY160D H-bridge, 5kHz PWM, 8-bit resolution (LEDC channel 0)

---

### JungleDoor (ESP32-S3)
**Firmware:** v2.7.0

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 4 | DIR_PIN | OUT | MD13S direction: HIGH=open, LOW=close |
| GPIO 6 | PWM_PIN | OUT | MD13S speed (0-255), typical set=150 |
| GPIO 8 | LIMIT_OPEN | IN | Mechanical limit switch |
| GPIO 7 | LIMIT_CLOSED | IN | Analog input (laser beam), ADC threshold=3600 |
| GPIO 21 | STATUS_LED_OPEN | OUT | Open status indicator |
| GPIO 22 | STATUS_LED_CLOSED | OUT | Closed status indicator |
| GPIO 23 | STATUS_LED_MOVING | OUT | Motion status indicator |

**Motor Driver:** Cytron MD13S

---

### AutomaticSlidingDoor — Arduino R4 WiFi (Cytron MD13S Version)

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| Pin 4 | DIR_PIN | OUT | MD13S direction control |
| Pin 6 | PWM_PIN | OUT | MD13S speed control |
| Pin A2 | OPEN_CMD | IN | Relay command input |
| Pin A4 | CLOSE_CMD | IN | Relay command input |
| Pin 9 | LIMIT_OPEN | IN | Mechanical limit switch |
| Pin 8 | LIMIT_CLOSED | IN | Mechanical limit switch |
| Pin 10 | STATUS_LED_OPEN | OUT | Open status indicator |
| Pin 11 | STATUS_LED_CLOSED | OUT | Closed status indicator |
| Pin 12 | STATUS_LED_MOVING | OUT | Motion status indicator |

**Motor Driver:** Cytron MD13S

---

### AutomaticSlidingDoor — ESP32-S3 Debug Version

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 4 | RPWM | OUT | BTS7960 forward |
| GPIO 5 | LPWM | OUT | BTS7960 reverse |
| GPIO 1 | OPEN_CMD | IN | Relay command (shorts to GND) |
| GPIO 2 | CLOSE_CMD | IN | Relay command (shorts to GND) |
| GPIO 9 | LIMIT_OPEN | IN | LOW when fully open |
| GPIO 18 | LIMIT_CLOSED | IN | LOW when fully closed |
| GPIO 10 | STATUS_LED_OPEN | OUT | Open status indicator |
| GPIO 11 | STATUS_LED_CLOSED | OUT | Closed status indicator |
| GPIO 12 | STATUS_LED_MOVING | OUT | Motion status indicator |

**Motor Driver:** BTS7960 H-bridge

---

### BarrelPiston (ESP32)
**Safety Features:** 120ms interlock gap, 5s timeout, 10min watchdog

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 16 | RELAY_ENGAGE | OUT | Engage piston relay, Active HIGH |
| GPIO 17 | RELAY_RETRACT | OUT | Retract piston relay, Active HIGH |
| GPIO 25 | LED_PIN | OUT | Status LED |
| GPIO 2 | GPIO2_CMD | IN/OUT | Dual-purpose: INPUT or OUTPUT via MQTT |
| GPIO 4 | GPIO4_CMD | IN/OUT | Dual-purpose: INPUT or OUTPUT via MQTT |

**Relay Logic:** Active HIGH (HIGH = engaged)

---

### Driftwood (ESP32-S3)
**Firmware:** v2.2.5
**Trigger Threshold:** 2000 magnetic field magnitude

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 15 | I2C SDA | IN/OUT | Shared bus for 8 sensors |
| GPIO 18 | I2C SCL | IN/OUT | Shared bus for 8 sensors |
| I2C 0x60 | ALS31300 #1 | I2C | Hall sensor 1 |
| I2C 0x61 | ALS31300 #2 | I2C | Hall sensor 2 |
| I2C 0x62 | ALS31300 #3 | I2C | Hall sensor 3 |
| I2C 0x63 | ALS31300 #4 | I2C | Hall sensor 4 |
| I2C 0x64 | ALS31300 #5 | I2C | Hall sensor 5 |
| I2C 0x65 | ALS31300 #6 | I2C | Hall sensor 6 |
| I2C 0x66 | ALS31300 #7 | I2C | Hall sensor 7 |
| I2C 0x67 | ALS31300 #8 | I2C | Hall sensor 8 |

---

### CaptainsCuffs (Arduino Mega 2560)
**Total Cuffs:** 8
**Touch Logic:** HIGH = touched
**Hall Logic:** LOW = magnet detected (INPUT_PULLUP)
**Relay Logic:** Active HIGH (HIGH = locked)

| Cuff | Touch Pin | Hall Pin | Relay Pin | Status |
|------|-----------|----------|-----------|--------|
| Cuff 1 | 22 | 30 | 38 | Active |
| Cuff 2 | 23 | 31 | 39 | Active |
| Cuff 3 | 24 | 32 | 40 | Active |
| Cuff 4 | 25 | —1 (DISABLED) | 41 | ⚠️ Hall disabled |
| Cuff 5 | 26 | 34 | 42 | Active |
| Cuff 6 | 27 | —1 (DISABLED) | 43 | ⚠️ Hall disabled |
| Cuff 7 | 28 | 36 | 44 | Active |
| Cuff 8 | 29 | 37 | 45 | Active |

---

### Balancing-Scale (Arduino Nano)

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| Pin 4 | RST_BT | IN | Reset button (INPUT_PULLUP) |
| Pin 5 | CHK_BT | IN | Check button (INPUT_PULLUP) |
| Pin 9/10 | SoftwareSerial1 RX/TX | IN/OUT | RFID Reader 1 (ID-12LA) |
| Pin 11/12 | SoftwareSerial2 RX/TX | IN/OUT | RFID Reader 2 (ID-12LA) |
| SERVO_PIN | Servo Control | OUT | ⚠️ **UNDEFINED IN CODE** |

**RFID:** 2x ID-12LA (125kHz passive)

---

### Wireless-Motion-Sensor (ESP8266)
**Devices:** ShipMotion1, ShipMotion2, ShipMotion3
**Trigger Distance:** 200mm
**Cooldown:** 2 minutes

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 4 (D2) | I2C SDA | IN/OUT | Default ESP8266 I2C pin |
| GPIO 5 (D1) | I2C SCL | IN/OUT | Default ESP8266 I2C pin |
| I2C 0x29 | VL53L0X | I2C | Time-of-flight distance sensor |

---

### LuminousShell (ESP32/ESP8266)
**Devices:** SeaShells
**Trigger Distance:** 50mm
**Light Duration:** 5 seconds

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| lightPin | LED Control | OUT | ⚠️ **UNDEFINED IN CODE** |
| I2C 0x29 | VL53L0X | I2C | Time-of-flight distance sensor |

---

### ShipNavMap (ESP8266/ESP32)

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| A0 | WS2812B Data | OUT | 15 LEDs, NeoPixel protocol (FastLED) |

---

### Ruins-Wall-Panel (Arduino Mega)
**Total LEDs:** 910 (WS2812B)
**Button Matrix:** 5 rows × 7 columns = 35 positions

| Pin Range | Function | Direction | Notes |
|-----------|----------|-----------|-------|
| A0 | WS2812B Data | OUT | 910-LED addressable strip |
| Pins 9-13 | Row Inputs | IN | 5 rows (INPUT_PULLUP) |
| Pins 2-8 | Column Outputs | OUT | 7 columns (active HIGH) |

**Button Matrix Scan:** Set column HIGH, read row pins

---

### Sun-Dial Board 1 (Arduino Mega) — Sensor/Bezel Controller

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| A0 | IR_INNER_0 | IN | Inner wheel zero position sensor |
| A1 | IR_INNER_COUNTER | IN | Inner wheel counter sensor |
| A2 | IR_OUTER_0 | IN | Outer wheel zero position sensor |
| A3 | IR_OUTER_COUNTER | IN | Outer wheel counter sensor |
| Pin 2 | HOUSE_1 | OUT | Relay output, Active HIGH |
| Pin 3 | HOUSE_2 | OUT | Relay output, Active HIGH |
| Pin 4 | HOUSE_3 | OUT | Relay output, Active HIGH |
| Pin 5 | HOUSE_4 | OUT | Relay output, Active HIGH |
| Pin 6 | HOUSE_5 | OUT | Relay output, Active HIGH |
| Pin 7 | HOUSE_6 | OUT | Relay output, Active HIGH |
| Pin 8 | INNER_CONTROL | OUT | Signal to motor board |
| Pin 9 | OUTER_CONTROL | OUT | Signal to motor board |
| Pin 10 | STEPPER_I_ENABLE | OUT | Inner stepper enable |
| Pin 11 | STEPPER_O_ENABLE | OUT | Outer stepper enable |
| Pin 12 | CHOOSE Button | IN | INPUT_PULLUP |
| Pin 13 | STEPPERS_ENABLE | OUT | Master stepper enable |
| I2C 0x40 | PCA9685 | I2C | PWM driver board 1 |
| I2C 0x41 | PCA9685 | I2C | PWM driver board 2 |

---

### Sun-Dial Board 2 (Arduino Uno) — Motor Controller

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| Pin 4 | ROTATE_INNER | IN | Manual button (INPUT_PULLUP) |
| Pin 5 | ROTATE_OUTER | IN | Manual button (INPUT_PULLUP) |
| Pin 10 | INNER_CONTROL | IN | Input from Board 1 |
| Pin 11 | OUTER_CONTROL | IN | Input from Board 1 |
| A0 | OUTER_STEPPER_DIR | OUT | Stepper direction |
| A1 | OUTER_STEPPER_STEP | OUT | Stepper step pulse |
| A2 | INNER_STEPPER_DIR | OUT | Stepper direction |
| A3 | INNER_STEPPER_STEP | OUT | Stepper step pulse |

---

### WaterFountain (Arduino Uno/Nano)

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| A0 | POT0 | IN | Potentiometer 1 input |
| A1 | POT1 | IN | Potentiometer 2 input |
| A2 | POT2 | IN | Potentiometer 3 input |
| I2C 0x40 | PCA9685 | I2C | PWM servo driver |

**Servo Mapping to PCA9685 Channels:**
- POT0 → Channels {0, 1, 3, 6}
- POT1 → Channels {2, 4, 7}
- POT2 → Channels {5, 8, 9}

**Total Servos:** 10 (connected to PCA9685)

---

### Original_Cannon_Legacy (ESP32) — DEPRECATED
**Status:** ⚠️ **DEPRECATED** — Use New-Cannons (ESP32-S3) instead

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 45 | DMX_TX | OUT | DMX serial transmission |
| GPIO 46 | DMX_RX | IN | DMX serial reception |
| GPIO 47 | DMX_EN | OUT | DMX driver enable |
| I2C 0x01 | ALS31300 | I2C | Hall sensor (angle) |
| I2C 0x29 | VL6180X | I2C | Distance sensor (reload) |

---

### hall-sensor-with-mqtt (ESP32-S3)

| Pin | Function | Direction | Notes |
|-----|----------|-----------|-------|
| GPIO 18 | I2C SCL | IN/OUT | Shared bus |
| GPIO 15 | I2C SDA | IN/OUT | Shared bus |
| I2C 0x60-0x67 | ALS31300 (×8) | I2C | Hall sensor array |

---

### Star-Charts: StarTableSprite driver (ESP32-S3) → MedeaWiz Sprite DV-S1

| ESP32-S3 pin | Goes to | Notes |
|---|---|---|
| GPIO 40 | Sprite I/O plug screw 2 (trigger / serial RX) | idle HIGH 3.3 V, 300 ms LOW pulse per constellation (v3.0.0). v2.x wrongly used GPIO 4. |
| GND | Sprite I/O plug screw 4 | shared ground is required |
| GPIO 18 | (unused) | reserved for Sprite serial TX (screw 3) if Serial Control ever works |
| USB-C | 5 V supply, own adaptor | do NOT feed the S3 from the Sprite's screw 1 (100 mA max) |

Sprite I/O plug (screw-terminal adaptor): 1 = 5 V out, 2 = RX/trigger in, 3 = TX out, 4 = GND. Player settings: Play Mode = Video Control Mode, Control Mode = Trigger Low with Interrupt (it will not save Serial Control), firmware ≥ 20210416 for next-file-per-trigger.

### Star-Charts: StarTableBridge (ESP32) ← Star_Table_FINAL table controller (ESP32)

| Bridge pin | From table controller | Notes |
|---|---|---|
| GPIO 22 (INPUT_PULLDOWN) | HOUSE_OUTPUT_1 = GPIO 22 | star found, 250-750 ms HIGH pulse |
| GPIO 23 (INPUT_PULLDOWN) | HOUSE_OUTPUT_2 = GPIO 2 | constellation solved, 500 ms HIGH pulse |
| GND | GND | shared |
| USB | own 5 V brick | keep it off the NeoPixel supply |

Both are 3.3 V ESP32s, no level shifting. Bridge WiFi: needs a spot with RSSI better than about -65; at -70+ it freezes and watchdog-reboots during play.

## I2C Address Master Registry

**Complete mapping of all I2C addresses across the escape room:**

| Address | Chip Model | Device(s) | Purpose | Notes |
|---------|-----------|-----------|---------|-------|
| 0x01 | ALS31300 | Original_Cannon_Legacy | Hall effect angle sensor | Default address before programming |
| 0x29 | VL53L0X | Wireless-Motion-Sensor (ShipMotion1/2/3), LuminousShell (SeaShells) | Time-of-flight distance | Trigger on proximity |
| 0x29 | VL6180X | New-Cannons (Cannon1/2), Original_Cannon_Legacy | Distance + ambient light | Reload detection |
| 0x40 | PCA9685 | Sun-Dial Board 1, WaterFountain | 16-ch PWM driver | Servo control |
| 0x41 | PCA9685 | Sun-Dial Board 1 | 16-ch PWM driver | Second PWM board |
| 0x60 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 1 | Programmed address |
| 0x61 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 2 | Programmed address |
| 0x62 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 3 | Programmed address |
| 0x63 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 4 | Programmed address |
| 0x64 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 5 | Programmed address |
| 0x65 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 6 | Programmed address |
| 0x66 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 7 | Programmed address |
| 0x67 | ALS31300 | Driftwood, hall-sensor-with-mqtt | Hall sensor 8 | Programmed address |

**⚠️ Notes on I2C Address Conflicts:**
- Address 0x29 is used by **both VL53L0X and VL6180X** — these must be on **separate buses** or use address reprogramming
- ALS31300 default address is 0x01; addresses 0x60–0x67 are programmed via I2C register writes
- PCA9685 is a 16-channel PWM driver; multiple units can coexist on same bus with different addresses (0x40–0x5F available)

---

## Relay Logic Summary Table

**Quick reference for relay activation logic across all devices:**

| Device | Relay Type | When HIGH | When LOW | Logic |
|--------|-----------|-----------|---------|-------|
| CabinDoor | Solenoid relay | OFF (door inactive) | Energized (door moves) | **Active LOW** |
| BarrelPiston | Solenoid relay | Engaged (piston extends) | OFF (retracted) | **Active HIGH** |
| CaptainsCuffs | Latch relay | Locked | Unlocked | **Active HIGH** |
| Sun-Dial (HOUSE_1–6) | Output relay | Active/energized | OFF | **Active HIGH** |
| CoveSlidingDoor | BTS7960 H-bridge | RPWM forward, LPWM off | LPWM reverse, RPWM off | **N/A (motor driver)** |
| JungleDoor | Cytron MD13S | DIR controls direction, PWM controls speed | PWM=0 stops motor | **N/A (motor driver)** |
| AutomaticSlidingDoor | BTS7960 or MD13S | Motor moves per DIR/PWM | PWM=0 stops | **N/A (motor driver)** |

---

## Voltage & Power Reference

**Logic level and power supply specifications:**

| Board/Chip | Logic Level | Power Supply | Notes | 5V Tolerant? |
|-----------|-------------|--------------|-------|--------------|
| ESP32 | 3.3V | 5V USB or 3.3V regulated | GPIO output is 3.3V | **NO** |
| ESP32-S3 | 3.3V | 5V USB or 3.3V regulated | GPIO output is 3.3V, more stable | **NO** |
| ESP8266 | 3.3V | 3.3V regulated (≥500mA) | GPIO NOT 5V tolerant | **NO** |
| Arduino Mega 2560 | 5V | 7–12V barrel, 5V USB, or 9V battery | 5V GPIO output | **YES** |
| Arduino Uno | 5V | 7–12V barrel, 5V USB, or 9V battery | 5V GPIO output | **YES** |
| Arduino Nano | 5V | 5V USB mini, 7–12V raw | 5V GPIO output | **YES** |
| Arduino R4 WiFi | 3.3V/5V mixed | 5V USB-C | Some pins 5V tolerant; check datasheet | **Partial** |
| PCA9685 | 3.3V/5V logic | 5V logic, external V+ for servos | Can operate at 3.3V or 5V logic | **N/A** |
| BTS7960 H-bridge | 3.3V/5V logic | Match controller, separate motor power | PWM input logic level must match controller | **Variable** |
| Cytron MD13S | 3.3V/5V logic | Match controller, separate motor power | Works with 3.3V or 5V logic inputs | **Variable** |

**⚠️ Critical Voltage Notes:**
- **ESP32/ESP32-S3 are NOT 5V tolerant.** Use voltage dividers or level shifters when interfacing with 5V Arduino output.
- **Level shifters required** for any 5V→3.3V signals (e.g., Arduino Mega relay outputs to ESP32 inputs).
- **Motor power is separate** from logic power; BTS7960/MD13S can drive high-current motors independently.

---

## BAC Controller Terminal Wiring

**For Shattic, Captain, Cove, Jungle BAC modules:**

| Terminal | Function | Type | Details |
|----------|----------|------|---------|
| Inputs 0–7 | Digital inputs | DIN | Active High default; JP1/JP2 configurable for channels 0–3 |
| Outputs 0–7 | Relay outputs | SPDT (Form-C) | 10A @ 125V AC rated; **recommend ≤2A @ 24V DC** |
| Power | 12V or 24V DC | DC supply | Jumper-selectable on board |
| Common | GND | Reference | Shared return for all signals |

**Terminal Block Pinout (typical):**
```
[Input 0] [Input 1] [Input 2] [Input 3] [Input 4] [Input 5] [Input 6] [Input 7]
[Output 0 NO] [Output 0 COM] [Output 1 NO] [Output 1 COM] ... [Output 7 NO] [Output 7 COM]
[12V/24V+] [GND]
```

**Configuration Notes:**
- **Low Side (default):** Relay coil grounded; output HIGH = relay energized
- **High Side:** Relay coil at +V; output HIGH = relay de-energized (less common)
- **Load Ratings:** 2A @ 24V DC is safe for most escape room solenoids; 10A is absolute max for short-term/motor loads

---

## Quick Troubleshooting Reference

### I2C Bus Diagnostics
- **No devices detected:** Check SDA/SCL voltages (should be ~3.3V or 5V with pull-ups), verify terminal resistors (typically 4.7kΩ)
- **Address conflict:** Use I2C scanner to map all active addresses; reprogram ALS31300 to avoid 0x29 overlap with VL53L0X
- **Intermittent communication:** Check for loose solder joints, verify pull-up resistors on shared bus, reduce bus speed if needed

### GPIO/Relay Issues
- **Relay not energizing:** Verify relay logic (Active HIGH vs. LOW), check power to relay coil, measure GPIO voltage (should match logic level)
- **Motor won't move:** Confirm DIR/PWM pins and logic, verify motor power supply is separate and adequate, test with PWM at 50% (e.g., 128/255)
- **LED not lighting:** Verify GPIO output level matches LED logic (3.3V for ESP32, 5V for Arduino), check for proper pull-up/pull-down configuration

### ESP32/Arduino Compatibility
- **Signal not received on 3.3V board from 5V Arduino:** Use 1kΩ + 2kΩ voltage divider (5V Arduino output → divider → 3.3V ESP input)
- **Bootloader not responding:** Hold BOOT button, power cycle, or use `esptool.py` with `--before=default_reset`

---

## Cable & Connector Recommendations

| Connection Type | Recommended | Gauge | Notes |
|-----------------|-------------|-------|-------|
| I2C (SDA/SCL) | Twisted pair, shielded | 22–24 AWG | Keep runs <10ft; use 4.7kΩ pull-ups per bus |
| GPIO digital signals | Single wire or twisted pair | 22–24 AWG | Shield if near high-current motor lines |
| Relay coil power | Separate twisted pair | 18–20 AWG | Use diodes across coil for EMI suppression |
| Motor power (H-bridge) | Heavy gauge | 16–18 AWG | Keep separate from logic lines; <6ft recommended |
| Servo signal | 3-pin servo connector | 22–24 AWG | PWM on dedicated pin; PCA9685 can drive 16 servos |
| Potentiometer | Twisted pair (3-wire) | 22–24 AWG | Shield center wire; connect GND and 3.3V/5V to outer pins |

---

## Firmware Version Tracking

| Device | Current Version | Last Updated | Status |
|--------|-----------------|---------------|--------|
| New-Cannons (Cannon1/2) | v3.2.0 | — | Production |
| Compass (Blue/Rose/Silver) | v1.0.0 | — | Production |
| CabinDoor | v1.0.0 / v1.1.0 | — | Production (dual versions) |
| CoveSlidingDoor | v1.0.0 | — | Production |
| JungleDoor | v2.7.0 | — | Production |
| Driftwood | v2.2.5 | — | Production |
| Original_Cannon_Legacy | (deprecated) | — | **DEPRECATED** — use New-Cannons |
| Wireless-Motion-Sensor | (no version) | — | Production |
| LuminousShell | (no version) | — | Production |
| Other boards | (no version) | — | Production |

---

## Safety Warnings & Best Practices

### Electrical Safety
- **Always disconnect power** before rewiring or troubleshooting
- **Use fused power supplies** for all 12V/24V circuits; 1–2A fuses typical
- **Never daisy-chain relay coils** without inline diodes (1N4148 or similar) to prevent back-EMF damage
- **Insulate all exposed contacts** on relay terminals; label high-voltage sections

### Motor Safety
- **Set PWM limits** (e.g., max 200/255) to prevent mechanical jam or excessive force
- **Test limit switches** before activation; confirm LOW signal when mechanical stop engaged
- **Use 120ms interlocks** between extend/retract commands (BarrelPiston reference) to prevent simultaneous coil energization
- **Monitor current draw** on H-bridge/motor controller; thermal shutdown typically at 80°C

### I2C & Sensor Safety
- **Verify I2C address uniqueness** before deploying multiple sensors on same bus (use I2C scanner tool)
- **Apply 4.7kΩ pull-ups** on each I2C bus (SDA and SCL); do not add pull-ups in parallel (causes excess current)
- **Shield long I2C runs** (>10ft) to reduce noise and capacitive coupling

### Firmware & Configuration
- **Back up current firmware** before flashing updates
- **Test new firmware on dev board** before deploying to production device
- **Document any custom pin mappings** in this reference after field modifications

---

## Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-12 | Technical Team | Initial comprehensive reference for "A Mermaid's Tale" |

---

**Last Updated:** 2026-02-12
**Contact:** Alchemy Escape Rooms Technical Support
**Backup Location:** `/mnt/Alchemy Grimoire/backups/wiring-reference-[date].md`

