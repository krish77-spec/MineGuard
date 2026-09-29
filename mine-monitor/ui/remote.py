"""
Remote backend client for the TUI.

Used when the TUI runs against the monitor backend
instead of owning the BLE connection itself:

    python main.py --backend http://127.0.0.1:5000

Only stdlib is used (urllib) so this also works on a
minimal Raspberry Pi image without extra dependencies.

This module never imports network.ble or network.manager.
All BLE ownership stays in monitor_backend.
"""

import json
import time
import urllib.request
import urllib.error

from models import NodeInfo, Event, Alert

from state import state


TIMEOUT = 4


# ============================================================
# HTTP HELPERS
# ============================================================

def _http_get(url):
    """GET JSON from the backend. Returns dict or None."""

    try:

        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:

            return json.loads(
                response.read().decode("utf-8")
            )

    except Exception:

        return None


def _http_post(url, payload):
    """POST JSON to the backend. Returns dict or None."""

    try:

        data = json.dumps(payload or {}).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(
            request, timeout=TIMEOUT
        ) as response:

            return json.loads(
                response.read().decode("utf-8")
            )

    except Exception:

        return None


# ============================================================
# STATE SYNC (backend -> local state for rendering)
# ============================================================

def fetch_snapshot(base_url):
    """Fetch GET /api/state from the backend."""

    return _http_get(base_url.rstrip("/") + "/api/state")


def apply_snapshot(snapshot):
    """
    Hydrate the local state singleton from a backend
    snapshot so the EXISTING curses layout (draw_screen,
    including the SOS overlay) renders backend data
    unchanged.
    """

    if not snapshot:

        return False


    state.connected = bool(
        snapshot.get("connected", False)
    )

    state.scanning = bool(
        snapshot.get("scanning", False)
    )

    state.connecting = (
        snapshot.get("connection") == "CONNECTING"
        and not state.scanning
    )

    state.connected_node = snapshot.get(
        "connected_node"
    )

    state.selected_node = snapshot.get(
        "selected_node"
    )

    state.message = snapshot.get(
        "message", ""
    ) or ""


    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    nodes = {}

    for entry in snapshot.get("nodes", []):

        if "name" not in entry:

            continue

        age = entry.get("heartbeat_age_s")

        nodes[entry["name"]] = NodeInfo(
            name=entry.get("name", "UNKNOWN"),
            address=entry.get("address", ""),
            rssi=entry.get("rssi", 0),
            status=entry.get("status", "DISCOVERED"),
            last_seen=time.time(),
            last_heartbeat=(
                time.time() - age
                if age is not None
                else 0
            ),
            last_sequence=entry.get(
                "last_sequence", -1
            ),
            packets_received=entry.get(
                "packets_received", 0
            ),
            temperature_c=entry.get("temperature_c"),
            humidity_percent=entry.get(
                "humidity_percent"
            ),
        )

    state.nodes = nodes


    # --------------------------------------------------------
    # Events (newest first, as served)
    # --------------------------------------------------------

    state.events = [
        Event(
            timestamp=entry.get("timestamp", ""),
            level=entry.get("level", "INFO"),
            message=entry.get("message", ""),
        )
        for entry in snapshot.get("events", [])
    ]


    # --------------------------------------------------------
    # Active alerts (packet is backend-side only; the TUI
    # overlay only needs id/type/node/timestamp/priority)
    # --------------------------------------------------------

    alerts = {}

    for entry in snapshot.get("alerts", []):

        if "alert_id" not in entry:

            continue

        alerts[entry["alert_id"]] = Alert(
            alert_id=entry["alert_id"],
            alert_type=entry.get("alert_type", "SOS"),
            node_id=entry.get("node_id", "UNKNOWN"),
            timestamp=entry.get("timestamp", ""),
            priority=entry.get("priority", 0),
            packet=None,
        )

    state.active_alerts = alerts


    return True


# ============================================================
# ACTIONS (TUI -> backend, same operations as local mode)
# ============================================================

def remote_rescan(base_url):
    """Ask the backend to run manager.rescan()."""

    result = _http_post(
        base_url.rstrip("/") + "/api/rescan", {}
    )

    return bool(result and result.get("ok"))


def remote_select(base_url, name):
    """Ask the backend to select a node."""

    result = _http_post(
        base_url.rstrip("/") + "/api/select",
        {"name": name},
    )

    return bool(result and result.get("ok"))


def remote_acknowledge(base_url, alert_id=None):
    """
    Acknowledge via the backend (existing
    state.acknowledge_alert logic, highest-priority
    first when no id is given — like the 'a' key).
    """

    result = _http_post(
        base_url.rstrip("/") + "/api/acknowledge",
        {"alert_id": alert_id} if alert_id else {},
    )

    return bool(result and result.get("ok"))
