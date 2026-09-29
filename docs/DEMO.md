# MineGuard — Demo Runbook

A short, repeatable story beats a feature list. This runbook covers the setup,
three demo scripts, and honest answers to the questions judges actually ask.

---

## 0. Pre-demo checklist (10 minutes before)

- [ ] ESP32 powered and showing the normal screen on the OLED (not blank).
- [ ] Serial Monitor at 115200 confirms `NODE_001` is advertising.
- [ ] Bluetooth is **on** on the gateway machine and the terminal app has BLE
      permission (macOS prompts once and blocks silently if denied).
- [ ] No other BLE owner is running (close any old `main.py --local`).
- [ ] `pip install -r requirements-dev.txt` already done — do not install live.
- [ ] Backend starts and `http://127.0.0.1:5000/api/health` returns
      `{"ok": true}`.
- [ ] Dashboard loads at `http://127.0.0.1:5001` and shows **ONLINE**.
- [ ] Browser zoom is set so the SOS overlay is fully visible.
- [ ] Terminal font is large enough for the back row to read.

### Three terminals

```bash
# Terminal 1 — backend (the only process that touches BLE)
cd mine-monitor && python backend.py

# Terminal 2 — web dashboard
cd web-monitor && python app.py

# Terminal 3 — terminal UI (joins the running backend)
cd mine-monitor && python main.py
```

Browser: **http://127.0.0.1:5001**

---

## A. Normal operation (2 minutes)

**Show**

1. Power the node. Within one scan cycle it appears in the dashboard node table
   and in the TUI node list.
2. Point out the columns: RSSI, heartbeat age, packets received, temperature,
   humidity. Then point at the OLED — the same temperature and humidity are on
   the physical node, so the reading is not fabricated on the laptop.
3. Select the node in the dashboard; the TUI selection follows on its next poll
   because both read the same backend state.
4. Unplug and re-power the node. It leaves, then returns on its own — no gateway
   restart, no manual reconnect.

**Say**

> "The node measures temperature and humidity, shows them locally on the OLED,
> and sends a structured packet over BLE every five seconds. The gateway
> validates the packet, tracks node health and exposes it as one shared state.
> Both screens you see are clients of that one state — the browser is not
> talking to the ESP32, and neither is the terminal UI."

**Do not say** that temperature/humidity is subsidence monitoring. It is the
auxiliary sensor on the foundation prototype.

---

## B. Emergency alert (2 minutes)

**Show**

1. Press the SOS button on the node. The OLED switches to its SOS screen and
   the physical event happens in front of the audience.
2. Both the dashboard and the TUI raise a persistent emergency overlay — two
   independent clients showing the *same* alert.
3. Wait through several heartbeats: **the overlay does not clear**. This is the
   point of the whole design.
4. Press `a` in the TUI. The alert clears in the TUI, and the dashboard clears on
   its next poll — one acknowledgement, both clients.
5. Show that the SOS is still in the Recent Events list.

**Say**

> "A heartbeat says the node is alive. An SOS is an operator-actionable event,
> so it stays on screen until a human acknowledges it. Both interfaces share one
> alert lifecycle on the gateway, so acknowledging in either one clears it in
> both. The event history keeps the record — the packet itself is never
> modified."

**Optional:** press SOS twice within a few seconds to demonstrate duplicate
suppression — only one alert appears.

---

## C. Reliability (2 minutes)

Walk the audience through the failures this prototype already fixes, then
demonstrate one:

- Kill the backend and reload the dashboard: it shows **OFFLINE** with
  `502 Backend unreachable` instead of a traceback or a blank page.
- Restart the backend and watch it reconnect and re-populate. 

**Say**

> "A monitoring system is only convincing if it survives normal failures. We hit
> real ones — the node stopped advertising after some disconnects, concurrent
> scans and connects raced each other, and immediate reconnects hammered the
> Bluetooth stack. Those are fixed: explicit advertising restart on the node, a
> single lock around every radio operation, and exponential backoff from two to
> thirty seconds."

If the room asks for the mesh demo, use script D below and be explicit about
status.

---

## D. Future mesh (architecture only — do not fake it)

**Do not** place three dummy nodes and imply a mesh exists. Instead walk the
diagram and explain what is already in the code to support it:

1. The packet envelope already has `origin`, `sender`, `hops` and `ttl`, and the
   gateway already validates them. `origin` never changes while forwarding, so a
   relayed packet is still attributed to the node that sensed it.
2. Duplicate suppression is keyed on `packet_id`, which is exactly what a mesh
   needs to stop a packet looping.
3. The transport seam is real: `network/packets.py` takes a decoded packet and
   does not know whether it arrived over BLE, ESP-NOW or anything else.

**Say**

> "Three or more nodes over a mock panel using ESP-NOW, multi-hop forwarding,
> routing and store-and-forward are the next phases — they are designed for, not
> built. What is built is the part that makes them possible without rewriting
> the application."

Then state the target in one sentence: *a wireless surface mesh network for
real-time subsidence detection*.

---

## What is implemented vs. planned — say it out loud

Judges reward precision. Lead with the boundary:

| Implemented (demonstrable now) | Planned (roadmap) |
|---|---|
| ESP32 node, DHT11, OLED, SOS button | Tilt, vibration, displacement, crack sensors |
| BLE single-node transport | ESP-NOW multi-hop surface mesh |
| Packet protocol with mesh-ready fields | Routing, self-healing, ACK/retry, store-and-forward |
| Pi/local gateway with shared state | AI/ML anomaly detection and risk-zone prediction |
| TUI + web dashboard + persistent alerts | GIS maps, mobile app, SMS/email notifications |
| Duplicate suppression, reconnect/backoff | Certification, field validation, production hardware |

---

## Likely questions and honest answers

**"Have you actually measured subsidence?"**
No. This is the sensing, transport and alerting foundation. Deformation sensing
is the next phase, and it needs tilt/displacement hardware and calibration work
that has not been done yet.

**"Why not just use LoRa?"**
It is on the evaluation list for long-range or backup links. ESP-NOW comes first
because it needs no additional radio module, no duty-cycle constraints and no
gateway infrastructure for the short-range mesh.

**"Why not just use Wi-Fi?"**
It is not local-first. A mine panel with no internet and no access point should
still deliver data and warnings, so the core path cannot depend on Wi-Fi
infrastructure.

**"How is BLE going to cover a whole panel?"**
It is not — BLE is the single-node link in the current prototype. Coverage comes
from the mesh phase. Underlying radio range depends on terrain, vegetation,
antenna placement and interference, all of which need field measurement.

**"Isn't AI prediction the whole point?"**
It is a major layer of the problem statement, and it is deliberately not claimed
yet. Anomaly detection trained on data that does not exist would be a demo
trick. Phase 5 produces the data, Phase 6 uses it, and we will report accuracy
and false-positive rates when we have them.

**"Can you guarantee a collapse warning?"**
No, and nobody should claim that from a student prototype. MineGuard is a
decision-support and early-warning system, and its deterministic SOS path works
regardless of the analytics.

**"What about certification for underground use?"**
Ordinary ESP32 boards and breakout sensors are not certified for hazardous mine
environments. Real deployment needs intrinsically safe or otherwise certified
hardware, engineering review and regulatory compliance — stated plainly in the
README and the docs.

---

## If the hardware fails on stage

Keep the story running; the software is the demonstrator.

1. **Node not found:** check the OLED and the serial log. If the node is dead,
   restart the backend and show the dashboard's OFFLINE handling, then use the
   architecture walkthrough (script D). The alert lifecycle can also be shown
   from the test suite: `python -m pytest tests -v`.
2. **Backend won't start:** check the port (`lsof -i :5000`) and whether an old
   `main.py --local` is still holding BLE.
3. **Dashboard stuck OFFLINE:** that is the designed behaviour when no backend
   answers — restart Terminal 1 and reload.

A recorded backup video of scripts A and B is worth having before any live
judging session.
