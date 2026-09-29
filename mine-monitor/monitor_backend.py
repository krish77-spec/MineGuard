"""
Monitor backend — the SINGLE owner of the BLE connection.

Architecture (shared mode, one BLE connection):

                    ESP32 NODE
                        |
                       BLE (owned here, and only here)
                        |
                        v
              +--------------------+
              | backend.py process |  <-- owns:
              | monitor_backend    |      network.manager, network.ble,
              | BLE Manager        |      packet processing, state.py,
              | Packet Processing  |      alert lifecycle
              | Shared State       |
              | localhost API :5000|
              +---------+----------+
                        |
          +-------------+------------+
          |                          |
          v                          v
  web-monitor/app.py           TUI remote mode
  (Flask frontend :5001,       (main.py --backend ...,
   pure HTTP proxy,             polls /api/state,
   owns NO BLE)                 POSTs actions)

The local TUI mode (python main.py on the Pi, no
--backend flag) keeps its previous behavior: that TUI
process itself owns the manager in-process.
Never run two BLE owners at once.
"""

import asyncio
import os
import threading
import time

from flask import Flask, jsonify, request, Response

from state import (
    state,
    get_active_alerts,
    acknowledge_alert,
)

from network import manager


# ============================================================
# CONFIG
# ============================================================

HOST = "127.0.0.1"

PORT = 5000


# ============================================================
# DASHBOARD PAGE SOURCE
# ============================================================

def _dashboard_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "web-monitor",
        "dashboard.html",
    )


def load_dashboard_html():
    """Load the dashboard page served at '/'."""

    with open(_dashboard_path(), "r") as handle:

        return handle.read()


# ============================================================
# BACKGROUND NETWORK THREAD (sole BLE owner)
# ============================================================

_network_loop = None
_network_thread = None


def _network_main():
    """
    Run the existing network manager in its own event loop.

    Same ownership the local TUI has — only here the owner
    is the backend service instead of the TUI.

    The event loop must stay alive for the whole process
    lifetime: the manager's background task AND coroutines
    scheduled from Flask request threads (via run_coro)
    all execute on it.
    """

    global _network_loop

    _network_loop = asyncio.new_event_loop()

    asyncio.set_event_loop(_network_loop)

    _network_loop.run_until_complete(
        _network_supervised()
    )


async def _network_supervised():
    """Own the manager task while the backend is running."""

    await manager.start()

    try:

        while state.running:

            await asyncio.sleep(0.5)

    finally:

        await manager.shutdown()


def start_network():
    """Start the backend network manager once."""

    global _network_thread

    if _network_thread is not None:

        return

    state.running = True

    _network_thread = threading.Thread(
        target=_network_main,
        daemon=True,
    )

    _network_thread.start()


def run_coro(coro):
    """
    Schedule an existing manager coroutine on the
    network event loop and wait for its result.

    Used by RESCAN so the API calls the SAME
    high-level manager function as the TUI.
    The manager's asyncio.Lock still protects
    concurrent BLE operations.
    """

    if _network_loop is None:

        return None

    future = asyncio.run_coroutine_threadsafe(
        coro,
        _network_loop,
    )

    return future.result(timeout=30)


# ============================================================
# STATE SNAPSHOT (serialized — no internal objects leak)
# ============================================================

def build_snapshot():
    """
    Read-only JSON-safe view of the backend state.

    No BLE logic here. No packet parsing here.
    Only converts state.py dataclasses into plain
    dictionaries for API consumers.
    """

    # --------------------------------------------------------
    # Connection status (same logic as TUI header)
    # --------------------------------------------------------

    if state.connected:

        connection = "ONLINE"

    elif state.connecting or state.scanning:

        connection = "CONNECTING"

    else:

        connection = "OFFLINE"


    # --------------------------------------------------------
    # Nodes (never hardcoded — renders whatever was found)
    # --------------------------------------------------------

    nodes = []

    for node in state.nodes.values():

        nodes.append(
            {
                "name": node.name,
                "address": node.address,
                "rssi": node.rssi,
                "status": node.status,
                "connected": (
                    node.name
                    == state.connected_node
                ),
                "selected": (
                    node.name
                    == state.selected_node
                ),
                "last_sequence": (
                    node.last_sequence
                ),
                "packets_received": (
                    node.packets_received
                ),
                "temperature_c": (
                    node.temperature_c
                ),
                "humidity_percent": (
                    node.humidity_percent
                ),
                "heartbeat_age_s": (
                    int(
                        time.time()
                        - node.last_heartbeat
                    )
                    if node.last_heartbeat
                    else None
                ),
            }
        )

    nodes.sort(
        key=lambda n: n["rssi"],
        reverse=True,
    )


    # --------------------------------------------------------
    # Selected node detail
    # --------------------------------------------------------

    selected = None

    if state.selected_node:

        node = state.nodes.get(
            state.selected_node
        )

        if node is not None:

            selected = next(
                (
                    n
                    for n in nodes
                    if n["name"] == node.name
                ),
                None,
            )


    # --------------------------------------------------------
    # Active alerts (highest priority first — same order
    # as the TUI overlay via get_active_alerts())
    # --------------------------------------------------------

    alerts = []

    for alert in get_active_alerts():

        alerts.append(
            {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type,
                "node_id": alert.node_id,
                "timestamp": alert.timestamp,
                "priority": alert.priority,
            }
        )


    # --------------------------------------------------------
    # Recent events (newest first, bounded by MAX_EVENTS
    # in state.py — we only slice for safety)
    # --------------------------------------------------------

    events = [
        {
            "timestamp": event.timestamp,
            "level": event.level,
            "message": event.message,
        }
        for event in state.events[:20]
    ]


    return {
        "connected": state.connected,
        "network_online": state.connected,
        "connection": connection,
        "transport": "BLE",
        "scanning": state.scanning,
        "message": state.message,
        "nodes_discovered": len(state.nodes),
        "connected_node": state.connected_node,
        "selected_node": state.selected_node,
        "nodes": nodes,
        "selected": selected,
        "alerts": alerts,
        "events": events,
    }


# ============================================================
# FLASK APP FACTORY
# ============================================================

def create_app():
    """Create the backend Flask application (API + page)."""

    app = Flask(__name__)


    @app.route("/api/state")
    def api_state():
        """Live monitoring state for all presentation layers."""

        return jsonify(build_snapshot())


    @app.route("/api/health")
    def api_health():
        """Liveness probe (does not touch BLE state)."""

        return jsonify({"ok": True})


    @app.route("/api/rescan", methods=["POST"])
    def api_rescan():
        """
        Call the EXISTING high-level manager rescan.

        Same function the local TUI calls on the 'r' key.
        """

        try:

            run_coro(manager.rescan())

            return jsonify({"ok": True})

        except Exception as error:

            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            str(error)
                            or type(error).__name__
                        ),
                    }
                ),
                500,
            )


    @app.route("/api/select", methods=["POST"])
    def api_select():
        """Select a node by name."""

        data = request.get_json(silent=True) or {}

        name = data.get("name")

        if name in state.nodes:

            state.selected_node = name

            return jsonify({"ok": True})

        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Unknown node",
                }
            ),
            404,
        )


    @app.route("/api/acknowledge", methods=["POST"])
    def api_acknowledge():
        """
        Acknowledge an alert via the EXISTING logic.

        Default (no alert_id given): acknowledge the
        highest-priority active alert — exactly like the
        local TUI 'a' key via acknowledge_current_alert().

        Historical events are preserved. The packet is
        never modified.
        """

        data = request.get_json(silent=True) or {}

        alert_id = data.get("alert_id")


        if alert_id:

            ok = acknowledge_alert(alert_id)

            return jsonify({"ok": ok})


        alerts = get_active_alerts()

        if not alerts:

            return jsonify({"ok": False})

        ok = acknowledge_alert(
            alerts[0].alert_id
        )

        return jsonify({"ok": ok})


    @app.route("/")
    def index():
        """Serve the dashboard page."""

        return Response(
            load_dashboard_html(),
            mimetype="text/html",
        )


    return app


# ============================================================
# ENTRY POINT
# ============================================================

def run(host=HOST, port=PORT):
    """Start the BLE manager, then serve the API + page."""

    start_network()

    create_app().run(
        host=host,
        port=port,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":

    run()
