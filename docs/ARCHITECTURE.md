# MineGuard — Architecture

This document explains *why* the code is arranged the way it is, so that the
future surface-mesh work can be added without redesigning the application.

---

## 1. The one rule that shapes everything

**Exactly one process owns the radio at a time.**

BLE is a single-connection resource. If a scan runs while another component
connects, or two components both call `BleakScanner`, the stack starts dropping
connections, the ESP32 stops advertising, and the monitoring workflow becomes
unreliable for reasons that look like hardware faults but are actually
architecture faults.

MineGuard therefore promotes the network owner to a **service**:

| Mode | Who owns BLE | When to use |
|---|---|---|
| **Shared** (default) | `mine-monitor/backend.py` | The normal demo: dashboard + TUI + API all at once |
| **Standalone** (`main.py --local`) | the TUI process itself | A headless Raspberry Pi with a single terminal |

Everything else — the web dashboard, the remote TUI, any future mobile client —
is a **pure HTTP client**. It reads `GET /api/state` and posts actions. It never
imports `bleak`.

This is enforced by tests, not convention:

- `test_web_frontend_owns_no_ble`
- `test_remote_client_imports_no_ble`
- `test_only_backend_and_local_tui_start_manager`
- `test_no_circular_imports`

---

## 2. Process and thread model

```
┌─────────────────────────────────────────────────────────────┐
│ backend.py  (process A)                                     │
│                                                             │
│  main thread            Flask HTTP server  (:5000)          │
│      │                        │                             │
│      │ spawns                 │ run_coro(coro)              │
│      v                        v                             │
│  network thread         asyncio.run_coroutine_threadsafe    │
│  (daemon)                     │                             │
│      │                        │                             │
│      v                        v                             │
│  asyncio event loop  <────────┘                             │
│      └── manager.start()  →  scan → connect → notify loop   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ web-monitor/app.py  (process B)                             │
│  Flask on :5001 — serves dashboard.html, proxies /api/*     │
│  NO BLE, NO state, NO packet parsing                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ main.py  (process C, optional)                              │
│  curses TUI — polls /api/state every 0.5 s, posts actions   │
│  NO BLE in the default (remote) mode                        │
└─────────────────────────────────────────────────────────────┘
```

Notes on the bridging:

- The network manager lives in its **own daemon thread with its own event loop**,
  created by `_network_main()`. That loop must outlive every request, because
  both the manager's background task and coroutines scheduled from Flask request
  threads run on it.
- Flask request handlers are synchronous, so `run_coro()` uses
  `asyncio.run_coroutine_threadsafe(...).result(timeout=30)` to run the *existing*
  manager coroutine and block until it finishes. No BLE logic is duplicated in
  the API layer.
- Even with several clients hitting `/api/rescan` simultaneously, the manager's
  single `asyncio.Lock` serialises the actual radio operation. There is a test
  for exactly that (`test_concurrent_rescans_never_overlap`).

---

## 3. Layers

```
        ui/tui.py  ui/layout.py  ui/input.py        ← presentation (curses)
        ui/remote.py                                ← presentation (HTTP client)
        web-monitor/app.py + dashboard.html         ← presentation (browser)
                        │
                        ▼
        network/manager.py                          ← orchestration & locking
                        │
                        ▼
        network/ble.py                              ← transport (Bleak)
                        │
                        ▼
        network/packets.py                          ← transport-independent processing
                        │
        network/protocol.py                         ← encode / decode / validate
                        │
                        ▼
        models.py + state.py                        ← data model & shared state
```

| Layer | File | Responsibility | Must never |
|---|---|---|---|
| Model | `models.py` | `Packet`, `NodeInfo`, `Alert`, `Event`, `ApplicationState` dataclasses | Import anything project-specific |
| State | `state.py` | The single `ApplicationState` instance; event/packet buffers; alert create/ack/list | Know about transports |
| Protocol | `network/protocol.py` | `encode`, `decode`, `validate`, `packet_id` — pure functions, never raises on `decode` | Import BLE or UI |
| Processing | `network/packets.py` | Duplicate suppression, node/heartbeat updates, event + alert creation | Know whether data came from BLE, ESP-NOW or LoRa |
| Transport | `network/ble.py` | Scan, connect, GATT notify, disconnect callback | Contain business rules |
| Orchestration | `network/manager.py` | Scan/connect loop, `asyncio.Lock`, exponential backoff, `rescan()`, `shutdown()` | Render anything |
| API | `monitor_backend.py` | Snapshot builder, Flask routes, network thread bootstrap | Parse packets or talk to BLE directly |
| Presentation | `ui/*`, `web-monitor/*` | Render state, send commands | Import `bleak` |

The dependency arrow only ever points **down**. `ui/tui.py` imports
`network.manager`; `network.ble` imports `network.packets`; `network.packets`
imports `state` and `protocol`. Nothing below imports anything above.

---

## 4. Why `network/packets.py` is separate from `network/ble.py`

`network/ble.py` produces a `bytes` payload from a GATT notification.
`network/packets.py` takes a **decoded `Packet`**. That seam is the entire
transport substitution point:

```
BLE notification  ─┐
ESP-NOW callback  ─┼──►  protocol.decode(bytes) ──► packets.process_packet(pkt)
LoRa driver       ─┘
```

Adding ESP-NOW later means writing a new transport module that calls
`protocol.decode()` and `process_packet()`. It does not mean touching the state
model, the alert lifecycle, the snapshot builder, the dashboard or the TUI.

`packets.process_packet()` is exception-isolated on purpose: a malformed packet
must never escape into a radio callback and take down the notification thread.

---

## 5. State and the alert lifecycle

There is one module-level `ApplicationState` instance in `state.py`. It holds:

- **nodes** — `dict[name] → NodeInfo`, populated only from observed traffic
  (`MAX_NODES` bounded); nothing is ever hardcoded.
- **events** — newest-first bounded event log (audit trail for operators).
- **packets** — newest-first bounded raw packet buffer for the TUI.
- **last_packet_ids** — the duplicate-suppression set.
- **active_alerts** — `dict[alert_id] → Alert`, ordered for display by
  `get_active_alerts()` (highest priority first).

```
SOS packet                     heartbeat / STATUS packet
     │                                    │
     ▼                                    ▼
packet_id = origin:seq:time_ms     update node, refresh heartbeat
     │                                    │
     ▼                                    ▼
create_alert() ── duplicate? ──► no      active_alerts untouched
     │  yes → return None
     ▼
active_alerts[id] = Alert   ← survives every later heartbeat
     │
     ▼
both UIs render the overlay until a human acknowledges
     │
     ▼
acknowledge_alert(id) → removed from active_alerts, stays in events
```

Two properties matter for safety:

1. **Alerts are not cleared by traffic.** Only `acknowledge_alert()` removes one.
2. **Packets are immutable.** Acknowledgement changes UI state, never the
   evidence.

Known limitation: `packet_id` is `origin:sequence:time_ms`, which is sufficient
today because `time_ms` moves with every packet, but would collide if a node
rebooted and reset its sequence while the clock also reset. Adding a `boot_id`
to the protocol is the documented fix (see `docs/PROTOCOL.md`).

---

## 6. Failure handling

| Failure | Where it is handled | Behaviour |
|---|---|---|
| Malformed JSON / bad types | `protocol.decode`, `protocol.validate` | Return `None` / `(False, reason)`; never raise |
| Duplicate packet | `packets.process_packet` | Suppressed via `packet_id` |
| ESP32 disconnects | `ble.disconnected_callback` | Clean up client, flag advertising restart, trigger reconnect |
| Repeated disconnect | `manager` backoff | `2 → 4 → 8 → 16 → 30 s` |
| Concurrent BLE operations | `manager` `asyncio.Lock` | Serialised |
| Exception inside a BLE callback | `packets.handle_packet` | Logged and isolated |
| Backend unreachable | `web-monitor/app.py` | `502 {"ok": false, ...}`; dashboard shows OFFLINE |
| No sensor values | snapshot builder | `null` → dashboard renders `--` |

---

## 7. Verified invariants

These are asserted in `mine-monitor/tests/`, so a refactor that breaks the
architecture fails CI rather than the demo:

1. Only the backend (and a `--local` TUI) may start the network manager.
2. The web frontend imports no BLE, no `network.*`, no `state`.
3. The remote TUI client imports no BLE.
4. There are no circular imports between `ui`, `network`, `state`, `models`.
5. `main.py` resolves to remote mode whenever a backend is reachable.
6. Two clients observing the same backend see the same node and the same alert,
   and either one can acknowledge it for both.
7. Concurrent rescans never overlap.
8. The backend's network loop stays alive for `run_coro()`.

---

## 8. Where the future mesh plugs in

| Future capability | Touch point | Everything else that stays unchanged |
|---|---|---|
| ESP-NOW transport | new `network/espnow.py` calling `protocol.decode` + `process_packet` | state, alerts, API, both UIs |
| Mesh forwarding | `hops` / `ttl` / `sender` rewrite inside the transport layer, before `process_packet` | protocol envelope, packet IDs, snapshot |
| New sensors | new optional fields in `Packet` + `protocol` validation + snapshot + UI rows | transport, manager, alerting |
| AI/ML layer | new consumer of `state` + persisted time series, exposed as a new read-only API route | all existing behaviour |
| Cloud/mobile client | another HTTP client of `/api/state` | nothing — it is already a service |

The last row is the payoff: because the gateway is already a service with a
stable snapshot contract, a future mobile app or GIS layer is additive.
