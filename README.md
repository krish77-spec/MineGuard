<div align="center">

# MineGuard

### AI-Enabled Smart Mine Subsidence Monitoring & Early Warning Platform

A low-cost, indigenous, **local-first** wireless sensor network for monitoring
ground deformation above underground coal-mine panels.

[![CI](https://github.com/krish77-spec/MineGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/krish77-spec/MineGuard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-working%20prototype-orange.svg)](#project-status)

*Smart India Hackathon prototype · Version 2.0 · September 2026*

</div>

---

## Table of contents

- [What MineGuard is](#what-mineguard-is)
- [Project status](#project-status)
- [System architecture](#system-architecture)
- [Repository layout](#repository-layout)
- [Quickstart](#quickstart)
- [Firmware](#firmware)
- [HTTP API](#http-api)
- [Wire protocol](#wire-protocol)
- [Emergency alert lifecycle](#emergency-alert-lifecycle)
- [Reliability engineering](#reliability-engineering)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Hardware](#hardware)
- [Design principles](#design-principles)
- [Limitations and safety](#limitations-and-safety)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## What MineGuard is

Subsidence above underground coal panels is normally caught late — by periodic
field surveys and post-facto damage assessment. MineGuard's target is continuous,
distributed, **surface-level** deformation monitoring using many low-cost nodes
that relay measurements to a local gateway and raise a persistent early warning.

The central innovation is a **Wireless Surface Mesh Network for Real-Time
Subsidence Detection**: cheap smart nodes spread across the surface above a mine
panel, each measuring deformation-related parameters, forwarding data through
neighbouring nodes, and delivering it to an operator gateway that works **without
internet access**.

### What actually runs today

This repository contains a **working, tested prototype** of the reusable
node → gateway foundation of that system:

- an **ESP32 smart node** that reads temperature/humidity, shows it on a local
  OLED, watches a physical **SOS** button, and emits structured JSON packets;
- **BLE transport** from the node to a Raspberry Pi / laptop gateway;
- a **single-owner Python backend** that scans, connects, validates packets,
  suppresses duplicates, tracks node health and owns the alert lifecycle;
- **two simultaneous operator views** — a `curses` terminal UI and a browser
  dashboard — both watching the same live state, with a persistent SOS overlay
  that only clears on explicit acknowledgement.

### What is deliberately *not* claimed

Tilt, vibration, displacement/stretch and crack sensing, ESP-NOW multi-hop mesh
routing, store-and-forward, AI/ML prediction, GIS and cloud sync are **planned,
not implemented**. See [Project status](#project-status) for the honest line
between the two, and [docs/ROADMAP.md](docs/ROADMAP.md) for the engineering plan.

---

## Project status

### Implemented — verified by the test suite

| Subsystem | Capability |
|---|---|
| **ESP32 node** | Unique node ID, packet generation, BLE GATT server, heartbeat, debounced SOS |
| **DHT11** | Temperature + humidity acquisition with failure handling |
| **OLED** | Local field display (address, RSSI-ish status, sensor values, SOS screen) |
| **SOS** | Physical button → emergency-priority packet → persistent gateway alert |
| **BLE** | Scan, connect, GATT notifications, disconnect callback, advertising recovery |
| **Gateway** | Raspberry Pi / Python service; authoritative shared node + alert state |
| **HTTP API** | `GET /api/state`, `/api/health`, `POST /api/rescan`, `/api/select`, `/api/acknowledge` |
| **TUI** | Node list, RSSI, heartbeat age, sensor values, event history, emergency overlay |
| **Web dashboard** | Live node table, selected-node detail, events, SOS modal, rescan, acknowledge |
| **Protocol** | `v, type, origin, sender, seq, priority, ttl, hops, time_ms` + validated sensor fields |
| **Reliability** | Duplicate suppression, alert lifecycle, single BLE owner, asyncio lock, exponential backoff |
| **Tests** | Protocol, backend/API, shared-state, web-proxy and architecture-boundary tests |

### Planned — not implemented

| Capability | Status | Target role |
|---|---|---|
| Surface subsidence sensors | Planned | Tilt, vibration, displacement/stretch, crack detection |
| Optional node positioning | Planned | Node-localisation for surface mapping — *not* worker tracking |
| ESP-NOW surface mesh | Planned | Multi-hop node-to-node forwarding |
| Routing / self-healing | Planned | Alternate paths, link-quality metrics, route timeout |
| ACK, retry, store-and-forward | Planned | Delivery guarantees for emergency traffic |
| Priority queues | Planned | Emergency traffic ahead of routine telemetry |
| AI/ML analytics | Planned | Anomaly detection, subsidence-zone ranking, severity/progression |
| GIS + web/mobile platform | Planned | Deformation maps and operator/planner/regulator views |
| SMS / email / push alerts | Planned | Automated early-warning notification |
| Optional cloud sync | Planned | Periodic sync while local monitoring stays offline-capable |
| LoRa link | Under evaluation | Long-range or backup path for select deployments |

> **Honest presentation rule.** In any demo, report or pitch, use "implemented"
> only for the first table. Never present the second table as working — that is
> what keeps this project technically credible.

---

## System architecture

One process owns the radio. Everything else observes it.

```
                          ESP32 SMART NODE  (NODE_001)
                     DHT11 · OLED · SOS button · BLE
                                     |
                        BLE (GATT notifications)
                        owned here, and ONLY here
                                     |
                                     v
             +-----------------------------------------------+
             |   mine-monitor/backend.py        :5000        |
             |   monitor_backend.py                          |
             |     · network.manager  (scan/connect/backoff) |
             |     · network.ble      (transport)            |
             |     · network.packets  (processing)           |
             |     · state.py         (nodes, alerts, events)|
             |     · /api/*           (localhost only)       |
             +------------------------+----------------------+
                                      |
                        +-------------+-------------+
                        |                           |
                        v                           v
        web-monitor/app.py  :5001           TUI — remote mode
        Flask page + HTTP proxy             main.py --backend ...
        (owns NO BLE, keeps NO state)       (polls /api/state, posts actions)
                        |
                        v
              Browser dashboard
              http://127.0.0.1:5001
```

Data path in the prototype:

```
DHT11 / SOS  →  ESP32  →  BLE notification  →  protocol decode  →  validate
             →  duplicate suppression  →  node + alert state  →  TUI + web + OLED
```

Future problem-statement data path:

```
Subsidence sensor → ESP32 surface node → neighbouring mesh nodes → multi-hop route
                  → Raspberry Pi gateway → live dashboard → AI/ML analytics
                  → risk zone + early-warning alert
```

The dependency direction is enforced by tests: **UI → Manager → Transport**. The
UI never imports `bleak`, and the packet layer never imports `curses`. That is
what lets the same packet model travel over ESP-NOW or LoRa later without
rewriting the application.

---

## Repository layout

```
MineGuard/
├── espNode/
│   └── espNode.ino            # ESP32 firmware (NimBLE + DHT11 + SSD1306 + SOS)
├── mine-monitor/              # Gateway: the single BLE owner + operator TUI
│   ├── backend.py             # Entry point: standalone backend service (:5000)
│   ├── monitor_backend.py     # Flask API + snapshot builder + network thread
│   ├── main.py                # TUI entry point (auto-detects remote/local mode)
│   ├── config.py              # UUIDs, timings, buffer sizes
│   ├── models.py              # Packet, NodeInfo, Alert, Event, ApplicationState
│   ├── state.py               # Shared state + alert lifecycle
│   ├── network/
│   │   ├── manager.py         # Scan/connect loop, asyncio lock, backoff
│   │   ├── ble.py             # Bleak scan/connect/notify transport
│   │   ├── protocol.py        # Encode / decode / validate / packet_id
│   │   └── packets.py         # Transport-independent packet processing
│   ├── ui/
│   │   ├── tui.py             # curses app bootstrap (local + remote modes)
│   │   ├── layout.py          # Screens, boxes, emergency overlay
│   │   ├── input.py           # Keyboard handling
│   │   └── remote.py          # stdlib HTTP client for shared-backend mode
│   ├── tests/                 # protocol / backend / shared-state / web-proxy tests
│   └── receiver.py            # LEGACY single-file prototype (superseded, kept for history)
├── web-monitor/
│   ├── app.py                 # Flask frontend + /api/* proxy (no BLE)
│   ├── dashboard.html         # Dashboard page (vanilla JS, 1 s polling)
│   └── README.md              # Frontend-specific architecture notes
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROTOCOL.md
│   ├── HARDWARE.md
│   ├── ROADMAP.md
│   ├── DEMO.md
│   └── TROUBLESHOOTING.md
├── .github/workflows/ci.yml   # Test suite on every push
├── requirements-dev.txt
├── CONTRIBUTING.md
├── LICENSE
└── Your demo startup.md       # Three-terminal demo cheat sheet
```

---

## Quickstart

### Requirements

- **Python 3.10+** (CI runs 3.12 and 3.14; the gateway relies on
  loop-agnostic `asyncio.Lock`, which landed in 3.10)
- A Bluetooth LE adapter (macOS, Linux/BlueZ, or Windows)
- Optional: an ESP32 flashed with [`espNode/espNode.ino`](espNode/espNode.ino) and
  the `NODE_001` firmware identity

### 1. Install

```bash
git clone https://github.com/krish77-spec/MineGuard.git
cd MineGuard

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2. Run the demo — three terminals

See [`Your demo startup.md`](Your%20demo%20startup.md) for the one-page version.

**Terminal 1 — backend (the only process that touches BLE)**

```bash
cd mine-monitor
python backend.py
```

**Terminal 2 — web dashboard**

```bash
cd web-monitor
python app.py
```

**Terminal 3 — terminal UI (joins the running backend)**

```bash
cd mine-monitor
python main.py
```

Then open **<http://127.0.0.1:5001>**.

The TUI's second terminal is optional — the dashboard alone is enough to watch
and control the system.

### TUI modes

| Command | Behaviour |
|---|---|
| `python main.py` | Probes `http://127.0.0.1:5000`; if a backend answers it runs in **remote mode** (owns no BLE) |
| `python main.py --backend <url>` | Forces **remote mode** against an explicit backend |
| `python main.py --local` | Forces **standalone mode** — this process owns BLE itself (headless Pi use) |

> ⚠️ Never run two BLE owners at once. Do not run `--local` while `backend.py` is
> running; you will get competing scans and dropped connections.

### TUI keys

| Key | Action |
|---|---|
| `↑` / `↓` (or `k`/`j`) | Move node selection |
| `r` | Rescan for nodes |
| `a` | Acknowledge the highest-priority active alert |
| `q` | Quit |

---

## Firmware

`espNode/espNode.ino` targets an **ESP32 DevKit** and is built for the Arduino
IDE (or `arduino-cli`).

**Libraries:** `NimBLE-Arduino`, `DHT sensor library` (Adafruit), `Adafruit
GFX Library`, `Adafruit SSD1306`.

**Build steps**

1. Open `espNode/espNode.ino` in the Arduino IDE.
2. Select board **ESP32 Dev Module** and the correct serial port.
3. Install the four libraries above via Library Manager.
4. Flash, then open Serial Monitor at **115200 baud**.

**Wiring (prototype)**

| Peripheral | ESP32 pin | Notes |
|---|---|---|
| DHT11 data | GPIO 16 | Plus 3V3 / GND |
| SOS push button | GPIO 4 | `INPUT_PULLUP`, other leg to GND |
| SSD1306 OLED SDA | GPIO 21 | I²C, address `0x3C` |
| SSD1306 OLED SCL | GPIO 22 | I²C |

**Firmware identity and behaviour**

- `NODE_ID` is `NODE_001` — change it per physical node before flashing.
- GATT service `12345678-1234-5678-1234-56789abcdef0`, packet characteristic
  `…def1` (see [`mine-monitor/config.py`](mine-monitor/config.py)).
- SOS is debounced in firmware and sent with emergency priority.
- Advertising is explicitly restarted from the main loop after a disconnect —
  a real-world NimBLE failure mode this prototype already fixes.

Details and the full node wiring rationale: [docs/HARDWARE.md](docs/HARDWARE.md).

---

## HTTP API

Everything is localhost-only by default. The backend serves the API on `:5000`;
the web frontend proxies `/api/*` through `:5001`.

| Method | Path | Body | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | — | Liveness probe. `{"ok": true}`. Never touches BLE. |
| `GET` | `/api/state` | — | Full snapshot: connection, nodes, selection, alerts, events. |
| `POST` | `/api/rescan` | `{}` | Runs the existing `manager.rescan()` under the BLE lock. |
| `POST` | `/api/select` | `{"name": "NODE_001"}` | Select a node. `404` if unknown. |
| `POST` | `/api/acknowledge` | `{"alert_id": "..."}` or `{}` | Clears one alert, or the highest-priority active alert. |
| `GET` | `/` | — | Dashboard HTML (backend also serves it for convenience). |

`GET /api/state` response shape:

```json
{
  "connected": true,
  "network_online": true,
  "connection": "ONLINE",
  "transport": "BLE",
  "scanning": false,
  "message": "Connected to NODE_001",
  "nodes_discovered": 1,
  "connected_node": "NODE_001",
  "selected_node": "NODE_001",
  "nodes": [
    {
      "name": "NODE_001",
      "address": "B4:BF:E9:61:B4:DE",
      "rssi": -65,
      "status": "ONLINE",
      "connected": true,
      "selected": true,
      "last_sequence": 42,
      "packets_received": 41,
      "temperature_c": 27.4,
      "humidity_percent": 61.0,
      "heartbeat_age_s": 3
    }
  ],
  "selected": { "...same shape as a node..." },
  "alerts": [
    {
      "alert_id": "NODE_001:43:124001",
      "alert_type": "SOS",
      "node_id": "NODE_001",
      "timestamp": "12:00:01",
      "priority": 3
    }
  ],
  "events": [
    { "timestamp": "12:00:01", "level": "SOS", "message": "SOS from NODE_001" }
  ]
}
```

If the backend is unreachable, the web frontend returns
`502 {"ok": false, "error": "Backend unreachable"}` and the dashboard shows
**OFFLINE** instead of crashing. Sensor fields render as `--` when unavailable.

---

## Wire protocol

A single JSON envelope carries every message. Both BLE (today) and ESP-NOW
(planned) use the same transport-independent codec in
[`network/protocol.py`](mine-monitor/network/protocol.py).

**Deviation is planned for, not accidental:** `origin` is the node that created
the packet, `sender` is the node that currently transmits it, `hops` increments
per relay and `ttl` decrements — the fields exist and are validated today so the
mesh can be added without a protocol break.

```json
{"v":1,"type":"STATUS","origin":"NODE_001","sender":"NODE_001","seq":42,"priority":0,"ttl":10,"hops":0,"time_ms":123456,"temperature_c":27.4,"humidity_percent":61.0}
```

```json
{"v":1,"type":"SOS","origin":"NODE_001","sender":"NODE_001","seq":43,"priority":3,"ttl":10,"hops":0,"time_ms":124001}
```

Priority levels: `0` normal · `1` warning · `2` critical · `3` emergency.

Planned sensor packet (illustrative only — no such sensor is implemented yet):

```json
{"v":1,"type":"SENSOR","origin":"NODE_014","sender":"NODE_009","seq":101,"priority":1,"ttl":9,"hops":1,"time_ms":123456,"tilt_x_deg":0.42,"tilt_y_deg":0.31,"vibration_rms":0.18,"displacement_mm":2.7,"crack":false}
```

Field-by-field semantics, validation rules and the packet-ID scheme:
[docs/PROTOCOL.md](docs/PROTOCOL.md).

---

## Emergency alert lifecycle

SOS is treated differently from a heartbeat. A heartbeat says *"I am alive"*; an
SOS is an operator-actionable emergency that must stay visible until a human
clears it.

1. The operator presses the physical SOS button.
2. The ESP32 debounces it and emits an `SOS` packet at priority `3`.
3. BLE delivers the packet to the gateway.
4. The protocol layer decodes and validates it.
5. `state.create_alert()` creates one alert keyed by
   `packet_id(packet)` → `"origin:sequence:time_ms"`.
6. **Both** UIs show a persistent overlay. Heartbeats and normal packets never
   dismiss it.
7. Duplicate SOS packets hash to the same packet ID, so no second alert appears.
8. Acknowledge (`a` in the TUI, **ACKNOWLEDGE** in the browser) calls
   `acknowledge_alert()` on the backend — the shared alert disappears for every
   client on its next poll.
9. The SOS entry remains in Recent Events for auditability. The packet itself is
   never modified.

---

## Reliability engineering

These came out of real failures on the bench, not theory:

| Problem | Root cause | Fix in this repo |
|---|---|---|
| ESP32 stopped advertising after disconnect | Advertising restart could fail in some disconnect states | Explicit `NimBLEDevice::startAdvertising()` from the loop |
| BLE operations overlapped | Background scan/connect and manual rescan raced | Single `asyncio.Lock` in `network/manager.py` |
| Reconnect hammering | Immediate retries stressed the BlueZ stack | Exponential backoff `2 → 4 → 8 → 16 → 30 s` |
| Stale client reference | Old `BleakClient` stayed referenced after failure | Explicit state/client cleanup on failure |
| Emergency popup invisible | Wrong `curses` refresh ordering | `noutrefresh` ordering + `curses.doupdate` |
| Callback crash on bad packet | Exceptions escaped the BLE notification callback | Exception isolation + logging in packet handling |

---

## Testing

```bash
cd mine-monitor
python -m pytest tests -v
```

Coverage includes:

- **Protocol** — decode/encode/validate round trips, malformed input, version
  rejection, range checks, packet-ID stability, forwarding semantics, sensor
  field handling.
- **Backend/API** — snapshot shape, live node values, SOS lifecycle, heartbeat
  persistence, duplicate suppression, acknowledgement semantics.
- **Architecture boundaries** — the web frontend imports no BLE code, the remote
  TUI imports no BLE code, only the backend and a `--local` TUI start the network
  manager, and there are no circular imports.
- **Shared state** — two clients observing and mutating the same alerts through
  the live backend, including concurrent rescans never overlapping.
- **Web proxy** — page + SOS overlay markup, forwarding of every `/api/*` route,
  preserved backend error codes, and `502` when the backend is down.

No hardware is required: BLE and the backend connection are substituted with
fakes, and `pytest` exits non-zero on any failure. CI runs the same suite on
every push ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | ESP32 + DHT11 + OLED + SOS + BLE + Pi gateway + TUI + protocol + alert lifecycle | **Completed** |
| 2 | Second/third node, ESP-NOW discovery, neighbour tables, direct node-to-node messaging | Planned |
| 3 | Mesh networking: forwarding, routing, duplicate suppression, route timeout | Planned |
| 4 | Mesh reliability: alternate paths, self-healing, ACK/retry, store-and-forward, priorities | Planned |
| 5 | Subsidence sensing: tilt, vibration, displacement/stretch, crack, optional positioning | Planned |
| 6 | AI/ML: anomaly detection, subsidence-zone prediction, severity/progression estimation | Planned |
| 7 | Operator platform: GIS deformation maps, web/mobile dashboards, notifications | Planned |
| 8 | Field validation: calibration, environmental qualification, power, coverage, reference surveys | Planned |

Full detail, including design rationale and evaluation criteria for radio and
sensor choices: [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Hardware

### Current prototype BOM

| Component | Role | Interface |
|---|---|---|
| ESP32 DevKit | Controller, BLE radio, future mesh node | GPIO / I²C / BLE |
| DHT11 | Temperature + humidity (auxiliary, **not** a subsidence sensor) | GPIO 16 |
| 0.96" SSD1306 OLED | Local field display | I²C (0x3C) |
| Momentary push button | Manual SOS trigger | GPIO 4, `INPUT_PULLUP` |
| Raspberry Pi Zero 2 W (or any laptop) | Mobile monitoring gateway | BLE + Python |

### Planned sensor package

Tilt/inclination · vibration · displacement/stretch · crack detection · optional
low-cost positioning (node localisation, explicitly **not** worker tracking).
Final part selection criteria and bench notes: [docs/HARDWARE.md](docs/HARDWARE.md).

---

## Design principles

**Local-first.** The core monitoring path never needs the internet, MQTT, a
cloud service or a database. A mine with no connectivity still gets its warning.

**One radio owner.** Exactly one process owns BLE. Extra UIs are pure clients —
this eliminates an entire class of race conditions and is enforced by tests.

**Transport-independent semantics.** Packets and state know nothing about BLE.
Swapping in ESP-NOW, LoRa or Zigbee should not require touching the UI.

**Evidence over score.** Future analytics must surface the raw measurements
behind any warning, must never override a deterministic SOS, and must never be
required for the basic monitoring path to function.

**No fake data.** Unimplemented sensor slots show a clearly labelled
"planned, not equipped" state instead of plausible-looking numbers.

---

## Limitations and safety

- MineGuard is a **prototype/research system**. It is **not** certified
  mine-safety equipment.
- BLE currently provides single-node transport; the intended multi-hop mesh is
  **not implemented**.
- Radio performance underground depends on geometry, materials, antenna
  placement and interference — all unvalidated here.
- Self-healing cannot restore a physically isolated area where no alternate path
  exists.
- DHT11 is a low-cost auxiliary sensor and is not a subsidence instrument.
- Bench/USB power is not a field power architecture; future nodes need
  energy-aware sampling and proper power design.
- Tilt and displacement sensors require mechanical reference design, calibration
  and drift compensation that have not been done yet.
- AI predictions depend entirely on data that does not exist yet.
- **Real deployment** would require intrinsically safe or otherwise appropriately
  certified hardware, engineering review, calibration, environmental
  qualification, communications planning and regulatory compliance.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layering, process model, single-BLE-owner rule, concurrency |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Packet fields, validation, packet IDs, forwarding semantics |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Wiring, peripherals, BOM, planned sensor package |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase-by-phase engineering plan and design criteria |
| [docs/DEMO.md](docs/DEMO.md) | Demo scripts A/B/C for judging and field trials |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and their fixes |
| [web-monitor/README.md](web-monitor/README.md) | Frontend-specific notes |
| [Your demo startup.md](Your%20demo%20startup.md) | Three-terminal startup cheat sheet |

---

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
The short version: keep the honesty rule, keep the layering, add a test, and run
`python -m pytest tests` before opening a PR.

---

## License

[MIT](LICENSE) © 2026 Krish Kumar and MineGuard contributors.

<div align="center">
<sub>Built as a Smart India Hackathon prototype. Report it as it is, not as it will be.</sub>
</div>
