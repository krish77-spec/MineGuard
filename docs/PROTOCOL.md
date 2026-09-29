# MineGuard — Wire Protocol (v1)

The protocol is a single JSON object per message, UTF-8 encoded, carried as a
BLE GATT notification today. It is **transport-independent by design**: the same
envelope is intended to travel over ESP-NOW, LoRa or any other chosen transport
without changing the gateway's state model, alerting or UI.

Implementation: [`mine-monitor/network/protocol.py`](../mine-monitor/network/protocol.py)

---

## 1. Envelope

| Key | Type | Required | Meaning |
|---|---|---|---|
| `v` | int | yes | Protocol version. Currently only `1` is accepted. |
| `type` | string | yes | Message class: `STATUS`, `SOS`, `UNKNOWN`, future `SENSOR`. |
| `origin` | string | yes | Node that **created** the packet. Never changes while forwarding. |
| `sender` | string | yes | Node that is **transmitting** this copy. Changes at each hop. |
| `seq` | int | yes | Per-origin monotonically increasing sequence number. |
| `priority` | int | yes | `0` normal · `1` warning · `2` critical · `3` emergency. |
| `ttl` | int | yes | Remaining forwarding budget. Decremented per hop. |
| `hops` | int | yes | Number of forwarding steps so far. |
| `time_ms` | int | yes | Node uptime in milliseconds at packet creation. |
| `temperature_c` | number | no | Sensor payload. Present on `STATUS`. Range-checked. |
| `humidity_percent` | number | no | Sensor payload. Present on `STATUS`. Range-checked. |

Optional fields are omitted from the wire form rather than sent as `null`
(`protocol.encode`), and missing optional fields decode to `None`.

### Why `origin` ≠ `sender` matters

This pair is the mesh hook. A relay rewrites `sender` to its own ID, increments
`hops`, decrements `ttl`, and forwards the payload untouched. The gateway keys
node identity, alerts and duplicate suppression on `origin`, so a packet that
travelled four hops is still attributed to the node that sensed it.

The fields exist and are validated **today**, even though only one node is
deployed, because adding them later would be a breaking protocol change.

---

## 2. Examples

### STATUS (heartbeat, priority 0)

```json
{"v":1,"type":"STATUS","origin":"NODE_001","sender":"NODE_001","seq":42,"priority":0,"ttl":10,"hops":0,"time_ms":123456,"temperature_c":27.4,"humidity_percent":61.0}
```

### SOS (emergency, priority 3)

```json
{"v":1,"type":"SOS","origin":"NODE_001","sender":"NODE_001","seq":43,"priority":3,"ttl":10,"hops":0,"time_ms":124001}
```

### Relayed SOS (planned forwarding semantics)

```json
{"v":1,"type":"SOS","origin":"NODE_007","sender":"NODE_003","seq":11,"priority":3,"ttl":8,"hops":2,"time_ms":88310}
```

Still attributed to `NODE_007`: the operator sees the node that pressed SOS, not
the relay that happened to deliver it.

### Future SENSOR packet (illustrative only — not implemented)

```json
{"v":1,"type":"SENSOR","origin":"NODE_014","sender":"NODE_014","seq":101,"priority":1,"ttl":10,"hops":0,"time_ms":123456,"tilt_x_deg":0.42,"tilt_y_deg":0.31,"vibration_rms":0.18,"displacement_mm":2.7,"crack":false}
```

Field names, units and calibration will be finalised during hardware
integration. This example exists to show that the envelope already accommodates
it.

---

## 3. Decode rules

`protocol.decode(raw_bytes)` is **total and never raises**. It returns a `Packet`
or `None`.

1. UTF-8 decode with `errors="replace"` — a corrupt byte cannot throw.
2. `json.loads`; non-object JSON (array, number, string) is rejected.
3. `origin`, `sender` and `type` must be present and non-empty, else `None`.
4. `v` must be an `int`, else `None`.
5. Numeric fields go through `_safe_int` / `_safe_float`, which coerce numerics
   and numeric strings and fall back to a default otherwise.
6. Missing `seq` becomes `-1`; missing `priority`/`ttl`/`hops`/`time_ms` become
   `0`; missing sensor values become `None`.

This tolerance is deliberate: a partially corrupted field should cost the field,
not the packet, and never the monitoring session.

---

## 4. Validation rules

`protocol.validate(packet)` returns `(True, None)` or `(False, reason)`.
Decoding a packet does **not** imply trusting it; the gateway validates before
processing.

| Check | Rejects when |
|---|---|
| Version | `v` not in `SUPPORTED_VERSIONS` (`{1}`) |
| Type | empty / falsy |
| Origin | empty / falsy |
| Sender | empty / falsy |
| Integer fields | `seq`, `priority`, `ttl`, `hops`, `time_ms` not `int` |
| Temperature | non-numeric, or outside `-40 … 80 °C` |
| Humidity | non-numeric, or outside `0 … 100 %` |

Values outside the numeric ranges are named in the rejection reason so field
debugging is a single log read.

---

## 5. Packet identity and duplicate suppression

```python
def packet_id(packet):
    return f"{packet.origin}:{packet.sequence}:{packet.time_ms}"
```

The gateway keeps `state.last_packet_ids` and processes each packet ID once.
This is what stops a relayed or re-advertised SOS from creating a second overlay
in the operator's faces.

**Known limitation.** If a node reboots and its sequence *and* millisecond
counter both reset to a previously seen combination, an old ID could recur. This
has not been observed in practice (uptime keeps advancing), but the correct fix
is a `boot_id` / session token added to the envelope and folded into
`packet_id()`. That is recorded as a good-first-issue in
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## 6. Forwarding semantics (planned)

`protocol.decode` and the `Packet` fields already support these rules; only the
mesh transport and a router are missing.

1. On receipt, look up `packet_id`; if already seen, **drop** silently.
2. If we are not the gateway and `ttl > 1`: `sender = NODE_ID`, `hops += 1`,
   `ttl -= 1`, enqueue for forwarding.
3. `origin`, `seq`, `time_ms`, `priority` and any payload are **never** modified
   in transit.
4. If the destination is the gateway itself, hand the packet to
   `packets.process_packet()`.
5. If `ttl` reaches 0, drop and log — bounded lifetime prevents a packet
   circulating forever after a topology change.

Priority ordering (`3` before `0`) is the planned queue discipline: an SOS must
never sit behind a backlog of telemetry.

---

## 7. Transport mapping

| Transport | Carrier | Status |
|---|---|---|
| **BLE** | GATT notification on the packet characteristic | **Implemented** |
| ESP-NOW | direct ESP32 frames carrying the same UTF-8 JSON | Planned |
| LoRa | serialised JSON frames, duty-cycle limited | Under evaluation |

BLE identifiers (`mine-monitor/config.py`):

- Service UUID: `12345678-1234-5678-1234-56789abcdef0`
- Packet characteristic UUID: `12345678-1234-5678-1234-56789abcdef1`

A one-byte or JSON-envelope version prefix would be needed for a byte-oriented
transport; the JSON body itself stays as specified here.

---

## 8. Compatibility policy

- `v` is the only negotiation mechanism. A gateway that does not support a
  version rejects the packet and logs it — it does not crash.
- **Adding** an optional field is a non-breaking change: unknown keys are ignored
  by `_dict_to_packet`, and missing keys decode to defaults.
- **Renaming or retyping** an existing field, tightening a required field, or
  changing the meaning of `sender`/`origin` is a breaking change and requires
  bumping `v`.
- Firmware `NODE_ID` and protocol constants live at the top of
  [`espNode/espNode.ino`](../espNode/espNode.ino) so a node can be re-identified
  without touching logic.
