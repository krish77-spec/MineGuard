# Web Monitor

Local web dashboard for the Mine Safety Mesh project.
Pure presentation layer over the single monitor backend.

## Architecture (one BLE owner, simultaneous UIs)

```
                    ESP32 NODE
                        |
           BLE (owned by backend ONLY)
                        |
                        v
              +--------------------+
              | backend.py :5000   |  <-- ONE process owns:
              | monitor_backend    |      network.manager, network.ble,
              | BLE Manager        |      packet processing, state.py,
              | Packet Processing  |      alert lifecycle
              | Shared State + API |
              +---------+----------+
                        |
          +-------------+------------+
          |                          |
          v                          v
  web app :5001                TUI remote mode
  (Flask frontend,             (main.py --backend ...,
   pure HTTP proxy,             polls /api/state,
   owns NO BLE)                 POSTs actions)
          |
          v
  Browser dashboard (polls /api/state)
```

- `../mine-monitor/backend.py` is the backend service.
  It is the ONLY component that talks to the ESP32.
- `app.py` in this folder serves the dashboard page and
  forwards `/api/*` to the backend. It contains no BLE
  logic and never imports `network`, `state`, or `bleak`.
- The TUI views the SAME live backend with remote mode.
  Both UIs observe and mutate the same shared alerts.

Never run two BLE owners at once (e.g. backend +
standalone local TUI simultaneously). One backend =
one BLE connection.

## Run all three simultaneously

Terminal 1 — backend (sole BLE owner):

```bash
cd mine-monitor
python backend.py
```

Terminal 2 — web frontend:

```bash
cd web-monitor
python app.py
```

Terminal 3 — TUI viewing the same backend:

```bash
cd mine-monitor
python main.py
```

A bare `python main.py` automatically joins a running
backend (shared mode, owns NO BLE). Use
`python main.py --backend <url>` to point at a backend
explicitly, or `python main.py --local` to force
standalone mode.

Browser:

```
http://127.0.0.1:5001
```

Backend API is on `http://127.0.0.1:5000`.
The TUI in standalone mode (`python main.py` with no
flags, for the headless Raspberry Pi) still owns BLE
itself exactly as before — just never run it at the
same time as `backend.py`.

## What it shows

- Header with ONLINE / CONNECTING / OFFLINE + transport (BLE)
- Mine nodes panel (all discovered nodes, never hardcoded)
- Selected node detail (address, RSSI, status, heartbeat,
  sequence, packets, temperature, humidity)
- Network status (nodes discovered, connected node, last action)
- Recent events (newest first, bounded)
- Persistent SOS emergency overlay with ACKNOWLEDGE button
- RESCAN button, click-to-select nodes, 1-second live polling

## How SOS alerts work

1. An SOS packet arrives over BLE and the backend's
   `network/packets.py` creates ONE persistent alert via
   `state.create_alert()` (keyed by `protocol.packet_id()`).
2. `GET /api/state` exposes `alerts` (highest priority first)
   to every client.
3. The browser polls through the proxy every second; the
   remote TUI polls the backend every 0.5s. While the alert
   exists, BOTH popups stay visible. Heartbeats and normal
   packets never clear it — clearing only happens through
   `acknowledge_alert()` on the backend.
4. ACKNOWLEDGE from either UI posts to the backend, which
   removes the shared alert. The other UI sees it disappear
   on its next poll. The SOS entry stays in Recent Events;
   the packet is never modified.
5. Duplicate SOS packets map to the same packet ID, so no
   duplicate alert is created (existing suppression logic).

## Rescan

RESCAN from either UI reaches the backend's
`manager.rescan()`, still guarded by the existing asyncio
BLE lock and exponential backoff — only one BLE operation
ever runs at a time.

## Install

```bash
cd web-monitor
python -m venv .venv          # optional
source .venv/bin/activate     # optional
pip install -r requirements.txt
```

The proxy uses only stdlib (`urllib`), so no new
dependencies beyond Flask are required.

(BLE support also needs `bleak`, already used by `mine-monitor`.)

## API (served by the backend, proxied by this app)

- `GET /` — dashboard page (served here)
- `GET /api/health` — liveness probe
- `GET /api/state` — full snapshot (connected,
  network_online, nodes, selected, alerts, events,
  connection status)
- `POST /api/rescan` — run existing `manager.rescan()`
- `POST /api/select` — `{"name": "NODE_001"}`
- `POST /api/acknowledge` — `{"alert_id": "..."}` or
  `{}` for highest-priority (TUI behavior)

Live updates use simple polling (`GET /api/state`
every ~1s browser / ~0.5s remote TUI). No WebSockets,
SSE, MQTT, cloud, or database.

## Offline behavior

If the backend is down, the page still loads and the API
returns `502 {"ok": false, "error": "Backend unreachable"}`;
the dashboard shows OFFLINE instead of crashing.
If the ESP32 is off or BLE fails, the backend reports
OFFLINE / searching state instead of crashing.
Sensor fields show `--` when unavailable.

## Troubleshooting

Dashboard stuck on OFFLINE / "Backend unreachable"?
The web frontend owns NO BLE connection — start the
backend first (Terminal 1 above), then reload the page.

Opened `http://127.0.0.1:5000` and see raw JSON instead
of the dashboard? That is the backend API port. The
dashboard page is on `http://127.0.0.1:5001`
(or `/` on the backend port also serves the page).

## What is implemented

- Everything listed above; future sensor slots
  (tilt, vibration, displacement, crack) appear only as a
  clearly labeled "planned, not equipped" note with no
  fake readings.

## Future work (NOT implemented)

- Mesh / ESP-NOW / LoRa transports
- Tilt, vibration, displacement, crack sensors
- AI/ML subsidence prediction, GIS, cloud sync,
  mobile notifications
