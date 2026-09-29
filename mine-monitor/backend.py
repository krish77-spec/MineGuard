"""
Standalone monitor backend process.

This is the SINGLE BLE/network owner in shared mode:

    Terminal 1:  cd mine-monitor && python backend.py
    Terminal 2:  cd mine-monitor && python main.py
                 (auto-joins the backend; --local forces
                 standalone mode, --backend sets the URL)
    Terminal 3:  cd web-monitor && python app.py
    Browser:     http://127.0.0.1:5001

Owns:
    - network.manager (BLE scanning / connection / backoff)
    - packet processing and protocol validation
    - authoritative shared state, alerts, events

Serves a localhost-only HTTP API consumed by the
TUI (remote mode) and the web frontend. No cloud,
internet, MQTT, GSM, or external server required.

Do NOT run another BLE owner at the same time
(e.g. the TUI in standalone local mode).
"""

import argparse
import os
import sys


sys.path.insert(
    0,
    os.path.dirname(os.path.abspath(__file__)),
)


from monitor_backend import run, HOST, PORT


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Mine Safety Mesh monitor backend - "
            "single BLE owner and shared-state API."
        )
    )

    parser.add_argument(
        "--host",
        default=HOST,
        help="Interface to bind (default: %(default)s).",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help="Port to listen on (default: %(default)s).",
    )

    args = parser.parse_args()

    run(
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":

    main()
