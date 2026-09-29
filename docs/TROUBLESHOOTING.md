# MineGuard — Troubleshooting

---

## Dashboard shows OFFLINE / "Backend unreachable"

The web frontend owns **no** BLE connection. It only proxies `/api/*` to the
backend.

- Is Terminal 1 (`cd mine-monitor && python backend.py`) actually running?
- Does `curl http://127.0.0.1:5000/api/health` return `{"ok": true}`?
- Is the backend on a different port? Point the frontend at it:
  `python app.py --backend http://127.0.0.1:5000` (or set `MONITOR_BACKEND`).
- `502 {"ok": false, "error": "Backend unreachable"}` is the *designed* response,
  not a crash — the page is still correct, it just has no data.

## The page shows raw JSON instead of the dashboard

You opened the backend port. The backend also serves the page at `/` for
convenience, but the dashboard is meant to be viewed on
**http://127.0.0.1:5001**. Opening `http://127.0.0.1:5000/api/state` shows the raw
snapshot by design.

## Node never appears in the list

1. **Is the ESP32 powered and showing its normal OLED screen?** A blank OLED
   usually means a sensor I²C wiring problem at boot.
2. **Open Serial Monitor at 115200.** Look for the node identifier and
   advertising confirmation. A node that is not advertising cannot be found by
   any gateway.
3. **Bluetooth permissions.** On macOS, the terminal app must be granted
   Bluetooth access. A denied prompt is silent afterwards and looks identical to
   "no nodes nearby". Check System Settings → Privacy & Security → Bluetooth.
4. **BLE adapter present?** Virtual machines and some CI/container environments
   have none. `bleak` will scan forever and find nothing.
5. **Distance and interference.** Bench-range and through-a-desk are different
   problems. Move the node closer before debugging software.
6. **Something else is already connected.** A phone that paired earlier, or a
   second gateway, can hold the connection.

## TUI says standalone mode but no nodes appear

You likely have two BLE owners fighting. Check whether `backend.py` is running;
if it is, stop the standalone TUI and run `python main.py` (no `--local`), which
auto-joins the running backend.

`python main.py` probes `http://127.0.0.1:5000` and prefers remote mode
specifically to prevent this. `--local` overrides that on purpose.

## "Address already in use" on :5000 or :5001

Something is already listening.

```bash
lsof -i :5000
lsof -i :5001
```

Either stop that process or move the service:

```bash
python backend.py --port 5100
python app.py --backend http://127.0.0.1:5100 --port 5101
python main.py --backend http://127.0.0.1:5100
```

## Node connects, then keeps dropping

This is the failure class the current code already addresses — check in order:

1. **Advertising recovery.** The firmware explicitly calls
   `NimBLEDevice::startAdvertising()` from `loop()` after a disconnect. If a
   custom build removed that, the node is unreachable after the first drop.
2. **Backoff.** Reconnect delays grow `2 → 4 → 8 → 16 → 30 s` on purpose. A node
   returning after ~30 s is behaving correctly, not broken.
3. **BlueZ on Linux.** Very aggressive immediate retries can wedge the stack;
   the backoff exists for that reason. Restarting `bluetoothd` clears it.
4. **Power.** A USB cable that browns out under radio load produces exactly this
   symptom. Try another cable and port.

## SOS alert does not appear

- **Did the packet leave the node?** Serial Monitor should show the debounced
  press and the SOS send. If the button reads as permanently low, check for a
  solder bridge and that `INPUT_PULLUP` is used with the other leg on GND.
- **Debounce.** Presses shorter than 50 ms are ignored.
- **Was the packet rejected?** `monitor_backend` logs the validation reason. The
  most likely causes are a version mismatch or a non-integer field.
- **Did the `SOS` type survive?** A packet whose `type` is empty is rejected at
  decode time.
- **Duplicate suppression.** If the same `origin:sequence:time_ms` was already
  seen, no second alert is created — that is correct behaviour.

## Alert will not go away

By design, only an explicit acknowledgement clears it. Heartbeats and normal
status packets never dismiss an alert. Acknowledge with `a` in the TUI,
**ACKNOWLEDGE** in the dashboard, or:

```bash
curl -X POST http://127.0.0.1:5000/api/acknowledge \
     -H 'Content-Type: application/json' -d '{}'
```

An empty body acknowledges the highest-priority active alert.

## Sensor values show `--`

The gateway had no value to report: the DHT11 read failed on the node, or the
field was absent from the last packet. This is intentional — the UI never
invents a number. Check the node's serial log for the DHT11 failure line.

## Tests fail

- Use a virtual environment; system Python may not have the dependencies.
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements-dev.txt
  cd mine-monitor && python -m pytest tests -v
  ```
- Run from `mine-monitor`; `test_backend.py` imports `monitor_backend`, `models`
  and `state` from that directory.
- Port conflicts can break the live-backend tests — make sure nothing else is
  bound to the ports those tests use.
- No BLE adapter is required. If a test appears to need hardware, that is a bug;
  the transport is faked deliberately.

## Where to look first, always

`mine-monitor/logs/debug.log` — written fresh on each TUI start, with timestamps
and the module that logged each line. Most issues are visible in the first ten
lines.
