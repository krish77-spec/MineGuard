"""
Web-frontend tests.

web-monitor/app.py is a pure presentation layer: it serves
the dashboard page and proxies /api/* to the monitor
backend over HTTP. It owns NO BLE connection, runs NO
network manager, and keeps NO monitoring state.

These tests verify the proxy WITHOUT any backend or BLE
hardware by substituting the forward() helper:

    - page loads with dashboard + SOS overlay markup
    - GET /api/state is forwarded to the backend
    - POST /api/rescan is forwarded
    - POST /api/select forwards its payload
    - POST /api/acknowledge forwards its payload
    - backend error statuses are preserved (e.g. 404)
    - unreachable backend becomes 502 JSON (page still loads)
    - backend URL is configurable
    - the frontend imports no BLE/network/state code
"""

import os
import sys

import pytest


WEB_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "web-monitor",
    )
)

if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


import app as webapp


SAMPLE_SNAPSHOT = {
    "connected": True,
    "network_online": True,
    "connection": "ONLINE",
    "transport": "BLE",
    "scanning": False,
    "message": "Connected to NODE_001",
    "nodes_discovered": 1,
    "connected_node": "NODE_001",
    "selected_node": "NODE_001",
    "nodes": [
        {
            "name": "NODE_001",
            "address": "B4:BF:E9:61:B4:DE",
            "rssi": -65,
            "status": "ONLINE",
            "connected": True,
            "selected": True,
            "last_sequence": 40,
            "packets_received": 41,
            "temperature_c": 27.4,
            "humidity_percent": 76.7,
            "heartbeat_age_s": 3,
        }
    ],
    "selected": None,
    "alerts": [
        {
            "alert_id": "NODE_001:40:99999",
            "alert_type": "SOS",
            "node_id": "NODE_001",
            "timestamp": "12:00:01",
            "priority": 10,
        }
    ],
    "events": [
        {
            "timestamp": "12:00:01",
            "level": "SOS",
            "message": "SOS from NODE_001",
        }
    ],
}


@pytest.fixture
def client():
    webapp.app.config["TESTING"] = True

    with webapp.app.test_client() as test_client:

        yield test_client


def fake_forward(status, data, calls=None):
    """Build a forward() substitute returning canned backend replies."""

    def _forward(method, subpath, payload=None):

        if calls is not None:

            calls.append((method, subpath, payload))

        return status, data

    return _forward


# ============================================================
# PAGE
# ============================================================

def test_page_loads(client):
    response = client.get("/")

    assert response.status_code == 200

    assert (
        b"UNDERGROUND MINE MONITOR"
        in response.data
    )


def test_page_has_sos_overlay_and_actions(client):
    response = client.get("/")

    for marker in (
        b"sos-overlay",
        b"ACKNOWLEDGE",
        b"RESCAN",
        b"/api/state",
    ):
        assert marker in response.data


# ============================================================
# PROXY FORWARDING
# ============================================================

def test_state_forwarded_to_backend(client, monkeypatch):
    calls = []

    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(200, SAMPLE_SNAPSHOT, calls),
    )

    data = client.get("/api/state").get_json()

    assert calls == [("GET", "state", None)]

    assert data["connected_node"] == "NODE_001"

    assert data["nodes"][0]["temperature_c"] == 27.4

    assert data["alerts"][0]["alert_type"] == "SOS"


def test_rescan_forwarded_to_backend(client, monkeypatch):
    calls = []

    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(200, {"ok": True}, calls),
    )

    response = client.post("/api/rescan")

    assert response.status_code == 200

    assert response.get_json() == {"ok": True}

    assert calls == [("POST", "rescan", {})]


def test_select_forwards_payload(client, monkeypatch):
    calls = []

    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(200, {"ok": True}, calls),
    )

    response = client.post(
        "/api/select",
        json={"name": "NODE_001"},
    )

    assert response.get_json() == {"ok": True}

    assert calls == [
        ("POST", "select", {"name": "NODE_001"})
    ]


def test_acknowledge_forwards_payload(client, monkeypatch):
    calls = []

    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(200, {"ok": True}, calls),
    )

    response = client.post(
        "/api/acknowledge",
        json={"alert_id": "NODE_001:40:99999"},
    )

    assert response.get_json() == {"ok": True}

    assert calls == [
        (
            "POST",
            "acknowledge",
            {"alert_id": "NODE_001:40:99999"},
        )
    ]


def test_backend_error_status_preserved(client, monkeypatch):
    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(
            404, {"ok": False, "error": "Unknown node"}
        ),
    )

    response = client.post(
        "/api/select",
        json={"name": "NOPE"},
    )

    assert response.status_code == 404

    assert response.get_json()["ok"] is False


def test_unreachable_backend_becomes_502(client, monkeypatch):
    monkeypatch.setattr(
        webapp,
        "forward",
        fake_forward(
            502, {"ok": False, "error": "Backend unreachable"}
        ),
    )

    response = client.get("/api/state")

    assert response.status_code == 502

    assert response.get_json()["ok"] is False


def test_forward_reports_unreachable_backend(monkeypatch):
    # Port 9 (discard) is never a monitor backend here.

    monkeypatch.setenv(
        "MONITOR_BACKEND", "http://127.0.0.1:9"
    )

    status, data = webapp.forward("GET", "state")

    assert status == 502

    assert data["ok"] is False


def test_backend_url_configurable(monkeypatch):
    monkeypatch.setenv(
        "MONITOR_BACKEND", "http://127.0.0.1:5999"
    )

    assert (
        webapp.backend_base()
        == "http://127.0.0.1:5999"
    )

    monkeypatch.delenv("MONITOR_BACKEND")

    assert (
        webapp.backend_base()
        == webapp.DEFAULT_BACKEND_URL
    )


# ============================================================
# NO BLE IN THE FRONTEND
# ============================================================

def test_frontend_imports_no_ble():
    with open(webapp.__file__) as handle:

        source = handle.read()

    imports = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(
            ("import ", "from ")
        )
    ]

    assert imports, "expected imports"

    for banned in (
        "network",
        "manager",
        "state",
        "bleak",
        "Bleak",
        "monitor_backend",
        "packets",
        "protocol",
    ):
        assert not any(
            banned in line for line in imports
        ), imports


def test_frontend_has_no_manager_thread():
    with open(webapp.__file__) as handle:

        source = handle.read()

    for banned in (
        "manager.start",
        "start_network",
        "run_coro",
        "asyncio",
        "threading",
    ):
        assert banned not in source
