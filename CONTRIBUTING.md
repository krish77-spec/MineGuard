# Contributing to MineGuard

Thanks for looking at MineGuard. This is a prototype built for a Smart India
Hackathon problem statement, and contributions that keep it honest and working
are very welcome.

## Ground rules

1. **Never claim more than the code does.** Anything not demonstrable on the
   current prototype stays labelled *planned*. This is the single most important
   rule in this repository.
2. **Keep the layering.** `UI → Manager → Transport`. The UI must not import
   `bleak`; the packet/protocol layer must not import `curses`. There are tests
   that fail if you break this — that is deliberate.
3. **One BLE owner.** Only `mine-monitor/backend.py` (or a TUI started with
   `--local`) may start the network manager. New UIs must be pure HTTP clients.
4. **No fake data.** Unimplemented sensors render a clearly labelled
   "planned, not equipped" state — never a plausible-looking number.
5. **Add a test.** Behaviour changes need coverage in `mine-monitor/tests/`.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run the suite before and after your change:

```bash
cd mine-monitor
python -m pytest tests -v
```

No ESP32 or BLE adapter is required for the tests — the transport is faked.

## Project conventions

- Standard library first. `bleak` for BLE and `Flask` for HTTP are the only
  runtime dependencies, and the HTTP clients use `urllib` — keep it that way
  unless there is a strong reason not to.
- No cloud, MQTT, database, WebSocket or internet dependency in the core
  monitoring path. Local-first is a feature, not a limitation.
- Comments explain *why*, not *what*. The existing code is deliberately
  vertical in style (`def foo(\n    arg\n):`) — match the surrounding file.
- Terminal UI changes must keep working at 80×24.
- The dashboard is vanilla HTML/CSS/JS in a single file; no build step.

## Sending a change

1. Fork the repository and create a branch: `git checkout -b feature/short-name`
   (or `fix/short-name`).
2. Make the change, add tests, run `python -m pytest tests`.
3. Describe the *why* in the commit message and reference the issue if there
   is one.
4. Open a pull request. Small, focused PRs get reviewed fastest.

## Reporting a bug

Please include:

- what you expected vs. what happened;
- the exact command you ran and the full traceback;
- `mine-monitor/logs/debug.log` (it is written fresh on each TUI start);
- whether an ESP32 was connected, and your OS / BlueZ version.

## Good first issues

- Add a `boot_id` to the packet protocol so `packet_id()` stays unique across
  ESP32 reboots (see `docs/PROTOCOL.md`).
- Add tests for malformed GATT notifications at the transport boundary.
- Add a `--version` flag to the backend and TUI entry points.
- Add a screenshot/GIF of the dashboard and TUI to the README.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
