# MineGuard — Roadmap

The problem statement asks for a distributed, intelligent, surface-subsidence
monitoring platform. MineGuard is being built in phases so that every phase is
demonstrable before the next is claimed.

**Phase 1 is complete and in this repository. Phases 2–8 are not.**

| Phase | Scope | Status |
|---|---|---|
| 1 | Node/gateway foundation | **Completed** |
| 2 | Multi-node communication (ESP-NOW) | Planned |
| 3 | Mesh networking | Planned |
| 4 | Mesh reliability | Planned |
| 5 | Surface subsidence sensing | Planned |
| 6 | AI/ML analytics | Planned |
| 7 | Operator platform (GIS, web/mobile, notifications) | Planned |
| 8 | Field validation and production readiness | Planned |

---

## Phase 1 — Node/gateway foundation (completed)

ESP32 + DHT11 + OLED + SOS + BLE + Raspberry Pi gateway + TUI + web dashboard +
structured packet protocol + persistent alert lifecycle + BLE recovery.

Why this is a real milestone and not a placeholder: the **transport-independent
seams** are in place. Packets and state know nothing about BLE, exactly one
process owns the radio, and the gateway already exposes a stable HTTP snapshot
contract. Everything that follows is additive.

Evidence: `mine-monitor/tests/` covers protocol, API, alert lifecycle, shared
multi-client state and the architectural boundaries.

---

## Phase 2 — Multi-node communication

Second and third nodes, and direct ESP32-to-ESP32 messaging.

- **ESP-NOW** is the primary candidate for the student prototype: no access
  point, no internet, low latency, acceptable range for surface deployment.
  It was chosen over Wi-Fi mesh and Zigbee because it needs no infrastructure
  and works with the hardware already on hand.
- `NODE_ID` becomes genuinely distinct per node; discovery must tolerate nodes
  joining and leaving without restarting the gateway.
- **Neighbour table**: last-seen time, link quality / RSSI where available,
  and the node's surface deployment position (or later, its positioning data).
- **Node health**: stale/offline detection surfaced to the operator instead of
  silently disappearing nodes.
- Node count must scale without redesigning the gateway (the current state
  model is dictionary-based and bounded, so this is a matter of limits and UI,
  not architecture).

Exit criteria: three nodes visible simultaneously, each with its own sensor
readings and heartbeat age, with a node power-cycled and recovered without
gateway restart.

---

## Phase 3 — Mesh networking

- **Forwarding**: a node that receives a packet not addressed to itself relays
  it toward the gateway. `origin` stays; `sender`, `hops` and `ttl` change.
- **Routing**: choose a usable path; ESP-NOW peers plus a simple cost metric is
  the starting point. No single gateway-adjacent hop should be a hard
  dependency.
- **Duplicate suppression** across the mesh — reuse the `packet_id` scheme
  already in the protocol layer.
- **Route timeout**: discard stale routes and rediscover rather than forwarding
  into a link that no longer exists.
- **Link-quality metric**: RSSI alone is a poor predictor; combine RSSI,
  packet loss, availability, hop count and route stability.

Exit criteria: a packet from a node with no direct gateway link arrives at the
gateway with correct `origin`, incremented `hops`, decremented `ttl`, and no
duplicate processing.

---

## Phase 4 — Mesh reliability

| Feature | Purpose |
|---|---|
| Alternate paths / self-healing | Recover from a failed link or node without operator action |
| ACK + retry | Delivery assurance for important packets, especially emergencies |
| Store-and-forward | Retain important packets while no route exists; forward on recovery |
| Priority queues | Emergency traffic ahead of routine telemetry — an SOS must not queue behind telemetry |
| Duplicate suppression | Already in the protocol layer; extend across multi-hop paths |

Honest limitation to state in any demo: **self-healing cannot repair a
physically isolated area**. If no alternate radio path exists, no routing
policy can invent one. Coverage planning is a hardware problem.

Exit criteria: a link failure mid-transmission recovers automatically, and an
SOS generated while the gateway path is down is delivered after recovery and
still opens exactly one alert.

---

## Phase 5 — Surface subsidence sensing

This is the phase that turns the foundation into the project described in the
problem statement. Tilt/inclination, vibration, displacement/stretch and crack
detection, plus optional node positioning (node localisation for mapping —
explicitly *not* worker tracking).

Engineering work that is easy to underestimate and must be planned for:

- mechanical reference design and mounting for tilt/displacement;
- calibration and long-term **drift** compensation;
- environmental robustness (dust, water, temperature cycling);
- sampling rates that satisfy both the measurement and the power budget;
- a node-level "data quality" flag so a drifting or saturated sensor is
  reported as unhealthy instead of producing confident nonsense.

Each new measurement is added as an optional packet field plus a UI row — the
transport, state model and alerting stay untouched.

Exit criteria: three or more nodes on a mock panel showing live deformation
values, with a deliberately moved node producing a visible change.

---

## Phase 6 — AI/ML analytics

Where the "smart" in the problem statement gets earned.

- Build historical time-series datasets from tilt, vibration, displacement and
  crack measurements. **This data does not exist yet** — it is the true
  prerequisite, and acquisition starts in Phase 5.
- Anomaly detection against local and historical baselines.
- Multi-sensor fusion instead of single-readings thresholds.
- Spatial correlation across neighbouring nodes.
- Rank/estimate possible subsidence-risk zones, severity and progression.
- Report model accuracy and validation honestly.

Rules that constrain the design:

1. Never described as guaranteed or exact collapse prediction.
2. Never overrides a deterministic signal such as a manual SOS.
3. Never required for basic sensing, transport or local monitoring to work.
4. Never hides the raw measurements behind an opaque score.

Exit criteria: anomaly detection that has been validated against held-out
data, with its false-positive rate stated openly.

---

## Phase 7 — Operator platform

GIS deformation/risk maps, web and mobile dashboards for operators, planners and
regulators, live maps, risk zones and historical trends, plus automated SMS /
email / mobile notifications.

Because the gateway is already an HTTP service with a stable snapshot contract,
this phase consumes `/api/state` (and new read-only analytics routes) rather
than modifying the core. Keep the local-first property: notifications and maps
are enhancements, and losing connectivity must never stop monitoring.

---

## Phase 8 — Field validation and production readiness

- Calibration against reference survey data.
- Environmental qualification and coverage testing over real terrain.
- Power optimisation over a realistic deployment window.
- Certified/appropriate hardware, security hardening, maintenance strategy and
  mine-site validation under applicable regulations.

Only after this phase can MineGuard be described as anything other than a
prototype.

---

## Explicitly out of scope

Deliberately removed to keep the architecture focused and honest:

| Removed | Decision |
|---|---|
| GIS mapping in the current build | Phase 7 |
| GPS / worker tracking | Not this project — optional node positioning is not worker tracking |
| Cloud-dependent monitoring | Never for the core path; optional sync in Phase 7 |
| MQTT as a required protocol | Not used; HTTP + BLE/ESP-NOW suffice |
| GSM/4G emergency communication | Phase 7 notification work at the earliest |
| UWB displacement sensing | Rejected on cost/complexity for this prototype |
| React dashboard / FastAPI backend | Current Flask + vanilla stack is sufficient and dependency-light |
| Cloud LLM explanation layer | Not needed to prove the concept, and adds a network dependency |

---

## What "done" means for each phase

A phase is complete only when its behaviour can be **demonstrated on real
hardware** and is covered by tests. Until then it is labelled *planned* in the
README, the pitch and the demo script. This rule is the reason the project has
stayed credible: the architecture diagram and the working demo agree with each
other.
