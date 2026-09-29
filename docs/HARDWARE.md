# MineGuard — Hardware

Two parts: what is on the bench **today**, and the sensor package the problem
statement requires **next**. The boundary between them is stated explicitly,
because claiming future hardware is the fastest way to lose credibility.

---

## 1. Current prototype node

| Component | Role | Interface | Status |
|---|---|---|---|
| ESP32 DevKit | Controller, BLE radio, future mesh node | GPIO / I²C / BLE | Implemented |
| DHT11 | Temperature + humidity (auxiliary, **not** a subsidence sensor) | GPIO 16 | Implemented |
| 0.96" SSD1306 OLED | Local field display | I²C, address `0x3C` | Implemented |
| Momentary push button | Manual SOS trigger | GPIO 4, `INPUT_PULLUP` | Implemented |
| Raspberry Pi Zero 2 W (or any laptop) | Mobile monitoring gateway | BLE + Python | Implemented |
| LoRa module | Long-range / backup option | SPI / radio | Under evaluation |
| Tilt / vibration / displacement / crack sensors | Subsidence sensing package | analog / I²C / SPI | Planned |

Total prototype cost is deliberately in the hobbyist range: the entire point of
the problem statement is an **indigenous, low-cost** monitoring layer that can be
deployed at many points rather than one expensive instrument.

---

## 2. Wiring

| Peripheral | ESP32 pin | Notes |
|---|---|---|
| DHT11 data | GPIO 16 | Plus 3V3 and GND. The DHT11 breakout usually needs the module (not bare sensor) pull-up. |
| SOS button | GPIO 4 | `pinMode(SOS_PIN, INPUT_PULLUP)`; the other leg goes to GND, so pressing pulls the pin low. |
| OLED SDA | GPIO 21 | Default ESP32 I²C SDA. |
| OLED SCL | GPIO 22 | Default ESP32 I²C SCL. |
| Power | USB | Bench power only — **not** a field power architecture. |

```
                +-----------------------+
                |      ESP32 DevKit     |
                |                       |
   DHT11 data --| GPIO 16               |
   OLED SDA  ---| GPIO 21               |
   OLED SCL  ---| GPIO 22               |
   SOS button --| GPIO 4 ---[ GND ]     |   (INPUT_PULLUP, active low)
                |      3V3 --- VCC      |
                |      GND --- GND      |
                +-----------------------+
```

**Note on the BLE characteristic.** The firmware constant is named `SOS_UUID`
but carries **all** packets (`STATUS` and `SOS` alike) on
`12345678-1234-5678-1234-56789abcdef1`, matching `PACKET_UUID` in
[`mine-monitor/config.py`](../mine-monitor/config.py). The name is a historical
artefact of Phase 2; message type is a protocol field, not a characteristic.

---

## 3. Firmware behaviour

Source: [`espNode/espNode.ino`](../espNode/espNode.ino)

| Setting | Value | Purpose |
|---|---|---|
| `NODE_ID` | `NODE_001` | Change per physical node before flashing |
| `PROTOCOL_VERSION` | `1` | Must match `SUPPORTED_VERSIONS` in the gateway |
| `DEFAULT_TTL` | `10` | Forwarding budget for future multi-hop use |
| `HEARTBEAT_INTERVAL` | 5000 ms | Status packet cadence |
| `DHT_READ_INTERVAL` | 2000 ms | DHT11 is a slow sensor; reading faster returns stale data |
| `DEBOUNCE_DELAY` | 50 ms | SOS button debounce |
| `OLED_UPDATE_INTERVAL` | 100 ms | Display refresh |
| GATT service | `…abcdef0` | Advertised service |
| Packet characteristic | `…abcdef1` | Notify characteristic |

Libraries: `NimBLE-Arduino`, `DHT sensor library` (Adafruit),
`Adafruit GFX Library`, `Adafruit SSD1306`.

**Sequencing in `loop()`**: debounce and read the button → read DHT11 on its own
interval → send heartbeat on its own interval → update the OLED → if a disconnect
flagged it, call `NimBLEDevice::startAdvertising()`.

That last line exists because of a real field failure: after certain disconnect
states the node silently stopped advertising, and the gateway could no longer
find it. Restarting advertising explicitly from the main loop fixed it. It is
the kind of bug that only shows up when the hardware is on a table and someone
unplugs it.

The DHT11 read failure path is also explicit — a failed read logs and keeps the
last known values rather than publishing garbage.

---

## 4. Gateway host

Anything that runs Python 3.9+ with a Bluetooth LE adapter:

| Platform | BLE notes |
|---|---|
| Raspberry Pi Zero 2 W | The intended mobile gateway. BlueZ; run as root or with the right capabilities. |
| Linux laptop | BlueZ; `bleak` uses the D-Bus backend. |
| macOS | Native CoreBluetooth backend; BLE permissions must be granted to the terminal app. |
| Windows | WinRT backend; requires Windows 10 build 16299+. |

The gateway needs no internet access, no MQTT broker, no database and no cloud
account. That is a design requirement, not a packaging accident.

---

## 5. Planned subsidence sensor package

Candidate sensors for the next phase, with the selection criteria that will
actually decide between parts:

| Sensor | Measures | Selection criteria |
|---|---|---|
| Tilt / inclination | Change in ground angle relative to a reference | Resolution in the 0.01° class, temperature drift, long-term stability, cost |
| Vibration | Abnormal vibration signatures vs. a learned baseline | Bandwidth, sampling rate, mounting, immunity to wind and traffic |
| Displacement / stretch | Relative distance change between fixed reference points | Range vs. resolution, mechanical referencing, thermal expansion error |
| Crack detection | Crack initiation and growth | Sensitivity, gap range, installation on irregular surfaces |
| Optional positioning | Node location context for mapping and zone analysis | Cost, accuracy, GNSS availability under canopy — **node** localisation, never worker tracking |

Additional criteria that apply to all of them: power consumption (nodes must run
from battery/solar), calibration story, drift compensation, environmental
robustness (dust, water, temperature cycling), and procurement availability in
India. None of these parts has been purchased or integrated yet.

Structured fields go into the existing packet envelope, so a new sensor means a
new optional field plus a UI row — not a new architecture.

---

## 6. Power, packaging and certification

The current build runs from USB on a bench. A deployable surface node needs:

- battery or solar power with an energy budget over the full deployment window;
- energy-aware sampling (duty-cycled radios and sensors, not continuous
  streaming);
- enclosure rated for the environment, with antenna placement that survives it;
- power/battery monitoring reported in the node's telemetry;
- a serviceable mounting and referencing scheme for the deformation sensors —
  the mechanical reference is a large part of the measurement error budget.

**Certification:** ordinary hobby ESP32 boards and breakout sensors are **not**
certified for hazardous underground coal-mine deployment. Real deployment
requires intrinsically safe or otherwise appropriately certified equipment,
engineering review, calibration, environmental qualification, communications
planning and compliance with applicable regulations and mine-safety rules. This
prototype is a bench/field-trial demonstrator and must be described as such.
