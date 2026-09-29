"""
UNDERGROUND MINE MONITOR - Web frontend.

Pure presentation layer. This process owns NO BLE
connection, runs NO network manager, parses NO packets,
and keeps NO monitoring state of its own.

Architecture:

                    ESP32 NODE
                        |
               BLE (backend only)
                        |
                        v
           monitor backend :5000  (sole BLE owner)
                        |
              HTTP API (/api/*)
                        |
                        v
          this Flask app :5001 --- serves dashboard page
                 |                and proxies /api/* to backend
                 v
          Browser dashboard (polls /api/state)

Launch (shared mode, simultaneous with the TUI):

    Terminal 1:  cd mine-monitor && python backend.py
    Terminal 2:  cd web-monitor && python app.py
    Terminal 3:  cd mine-monitor && python main.py --backend http://127.0.0.1:5000
    Browser:     http://127.0.0.1:5001

Only stdlib (urllib) is used for the proxy, so no new
dependencies beyond Flask are required.
"""

import json
import os
import urllib.request
import urllib.error

from flask import Flask, jsonify, request, Response


# ============================================================
# CONFIG
# ============================================================

DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"

WEB_HOST = os.environ.get(
    "MONITOR_WEB_HOST", "127.0.0.1"
)

WEB_PORT = int(
    os.environ.get("MONITOR_WEB_PORT", "5001")
)

# A backend rescan can hold the request for a full BLE
# scan cycle plus the manager round-trip, so the proxy
# waits longer than the backend's own 30s limit.

PROXY_TIMEOUT = 60


def backend_base():
    """Backend URL, read per request so tests and env changes apply."""

    return os.environ.get(
        "MONITOR_BACKEND", DEFAULT_BACKEND_URL
    ).rstrip("/")


# ============================================================
# PROXY (browser <-> backend, no BLE here)
# ============================================================

def forward(method, subpath, payload=None):
    """
    Forward one API call to the backend.

    Returns (http_status, json_dict).
    Backend errors keep their status code.
    An unreachable backend becomes 502 JSON
    so the dashboard shows OFFLINE instead of a
    blank page or traceback.
    """

    url = backend_base() + "/api/" + subpath

    data = None

    if payload is not None:

        data = json.dumps(payload).encode("utf-8")


    forward_request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )


    try:

        with urllib.request.urlopen(
            forward_request,
            timeout=PROXY_TIMEOUT,
        ) as response:

            raw = response.read().decode("utf-8") or "{}"

            return response.status, json.loads(raw)


    except urllib.error.HTTPError as error:

        try:

            raw = error.read().decode("utf-8") or "{}"

            return error.code, json.loads(raw)

        except Exception:

            return error.code, {
                "ok": False,
                "error": f"Backend error {error.code}",
            }


    except Exception:

        return 502, {
            "ok": False,
            "error": "Backend unreachable",
        }


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


@app.route("/api/<path:subpath>", methods=["GET", "POST"])
def api_proxy(subpath):
    """Proxy every /api/* call to the monitor backend."""

    if request.method == "POST":

        status, data = forward(
            "POST",
            subpath,
            request.get_json(silent=True) or {},
        )

    else:

        status, data = forward("GET", subpath)

    return jsonify(data), status


@app.route("/")
def index():
    """Serve the dashboard page (talks to /api/* relatively)."""

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dashboard.html",
    )

    with open(path, "r") as handle:

        return Response(
            handle.read(),
            mimetype="text/html",
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Mine Safety Mesh web frontend - "
            "HTTP proxy to the monitor backend, no BLE."
        )
    )

    parser.add_argument(
        "--backend",
        default=None,
        help=(
            "Monitor backend base URL, e.g. "
            "http://127.0.0.1:5000 "
            "(default: $MONITOR_BACKEND or %(default)s)."
        ),
    )

    parser.add_argument(
        "--host",
        default=WEB_HOST,
        help="Interface to bind (default: %(default)s).",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=WEB_PORT,
        help="Port to listen on (default: %(default)s).",
    )

    args = parser.parse_args()

    if args.backend:

        os.environ["MONITOR_BACKEND"] = args.backend

    app.run(
        host=args.host,
        port=args.port,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":

    main()
