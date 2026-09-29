"""
Backend + architecture tests.

Verify the single-BLE-owner design:

    ESP32 --BLE--> monitor_backend --API--> browser / remote TUI

Covers:
    A. backend starts, /api/state works and carries
       nodes / selected / events / alerts
    B. live values (RSSI, temp, humidity, packets)
       visible through the API
    C. SOS lifecycle through the backend API
    D. architecture: only the backend owns BLE,
       presentation layers never import network.ble,
       no circular imports
    E. remote TUI sync (snapshot hydration + actions)
"""

import json
import os
import sys
import time

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


import monitor_backend

from models import NodeInfo, Packet

from state import state

from network.packets import process_packet

from ui import remote


# ============================================================
# HELPERS
# ============================================================

def reset_state():
    state.running = True
    state.scanning = False
    state.connected = False
    state.connecting = False
    state.selected_node = None
    state.connected_node = None
    state.client = None
    state.message = "Starting monitor..."
    state.nodes.clear()
    state.events.clear()
    state.packets.clear()
    state.last_packet_ids.clear()
    state.active_alerts.clear()


def make_node(name="NODE_001"):
    node = NodeInfo(
        name=name,
        address="B4:BF:E9:61:B4:DE",
        rssi=-65,
        status="ONLINE",
        last_seen=time.time(),
        last_heartbeat=time.time(),
        last_sequence=39,
        packets_received=39,
        temperature_c=27.4,
        humidity_percent=76.7,
    )

    state.nodes[name] = node

    state.selected_node = name

    state.connected_node = name

    state.connected = True

    return node


def make_sos(
    origin="NODE_001",
    sequence=40,
    time_ms=99999,
):
    return Packet(
        version=1,
        packet_type="SOS",
        origin=origin,
        sender=origin,
        sequence=sequence,
        priority=10,
        ttl=10,
        hops=0,
        time_ms=time_ms,
    )


def make_status(
    origin="NODE_001",
    sequence=41,
    time_ms=100999,
):
    return Packet(
        version=1,
        packet_type="STATUS",
        origin=origin,
        sender=origin,
        sequence=sequence,
        priority=0,
        ttl=10,
        hops=0,
        time_ms=time_ms,
        temperature_c=27.5,
        humidity_percent=76.0,
    )


@pytest.fixture
def client():
    reset_state()

    app = monitor_backend.create_app()

    app.config["TESTING"] = True

    with app.test_client() as test_client:

        yield test_client

    reset_state()


@pytest.fixture
def live():
    """Backend state with a connected node + SOS alert."""

    reset_state()

    make_node()

    process_packet(make_sos())

    yield

    reset_state()


# ============================================================
# A. BACKEND / API
# ============================================================

def test_backend_starts():
    app = monitor_backend.create_app()

    assert app is not None

    rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
    }

    assert "/" in rules

    assert "/api/state" in rules

    assert "/api/health" in rules

    assert "/api/rescan" in rules

    assert "/api/select" in rules

    assert "/api/acknowledge" in rules


def test_api_health(client):
    data = client.get("/api/health").get_json()

    assert data == {"ok": True}


def test_api_state_required_keys(client):
    data = client.get("/api/state").get_json()

    for key in (
        "connected",
        "network_online",
        "connected_node",
        "nodes",
        "selected_node",
        "selected",
        "events",
        "alerts",
    ):
        assert key in data


def test_api_state_json_serializable(client, live):
    data = client.get("/api/state").get_json()

    # Must not leak internal Python objects.

    text = json.dumps(data)

    assert "NODE_001" in text


def test_api_state_empty_backend(client):
    data = client.get("/api/state").get_json()

    assert data["connected"] is False

    assert data["network_online"] is False

    assert data["connected_node"] is None

    assert data["nodes"] == []

    assert data["alerts"] == []


# ============================================================
# B. LIVE VALUES THROUGH THE API
# ============================================================

def test_live_node_values(client, live):
    data = client.get("/api/state").get_json()

    assert data["connected"] is True

    assert data["network_online"] is True

    assert data["connected_node"] == "NODE_001"

    node = data["nodes"][0]

    assert node["rssi"] == -65

    assert node["connected"] is True

    selected = data["selected"]

    assert selected["temperature_c"] == 27.4

    assert selected["humidity_percent"] == 76.7

    assert selected["packets_received"] >= 1

    assert selected["last_sequence"] == 40


# ============================================================
# C. SOS LIFECYCLE THROUGH THE BACKEND API
# ============================================================

def test_sos_alert_exposed(client, live):
    data = client.get("/api/state").get_json()

    assert len(data["alerts"]) == 1

    alert = data["alerts"][0]

    assert alert["node_id"] == "NODE_001"

    assert alert["alert_type"] == "SOS"

    assert any(
        "SOS" in event["message"]
        for event in data["events"]
    )


def test_heartbeat_keeps_alert(client, live):
    process_packet(make_status())

    data = client.get("/api/state").get_json()

    assert len(data["alerts"]) == 1


def test_duplicate_sos_single_alert(client, live):
    process_packet(make_sos())

    data = client.get("/api/state").get_json()

    assert len(data["alerts"]) == 1


def test_acknowledge_clears_alert_keeps_event(client, live):
    response = client.post(
        "/api/acknowledge",
        json={},
    )

    assert response.get_json() == {"ok": True}

    data = client.get("/api/state").get_json()

    assert data["alerts"] == []

    assert any(
        "SOS" in event["message"]
        for event in data["events"]
    )


# ============================================================
# D. ARCHITECTURE — ONE BLE OWNER
# ============================================================

def _project_sources():
    root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
        )
    )

    sources = {}

    for base in ("mine-monitor", "web-monitor"):

        basedir = os.path.join(root, base)

        for dirpath, _, filenames in os.walk(basedir):

            if ".venv" in dirpath:

                continue

            if "tests" in dirpath.split(os.sep):

                continue

            for name in filenames:

                if not name.endswith(".py"):

                    continue

                path = os.path.join(dirpath, name)

                with open(path) as handle:

                    sources[
                        os.path.relpath(path, root)
                    ] = handle.read()

    return sources


def test_web_frontend_owns_no_ble():
    sources = _project_sources()

    launcher = sources["web-monitor/app.py"]

    for banned in (
        "network.ble",
        "from network",
        "import manager",
        "manager.start",
        "monitor_backend",
        "Bleak",
        "handle_packet",
        "process_packet",
        "acknowledge_alert",
        "create_alert",
    ):
        assert banned not in launcher


def test_backend_entry_delegates_to_service():
    root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
        )
    )

    path = os.path.join(root, "backend.py")

    with open(path) as handle:

        source = handle.read()

    # The entry point only launches monitor_backend.run();
    # it must not own BLE primitives itself.

    assert "monitor_backend" in source

    assert "run(" in source

    for banned in (
        "manager.start",
        "from network",
        "import manager",
        "from state",
        "import state",
        "Bleak",
    ):
        assert banned not in source


def test_remote_client_imports_no_ble():
    with open(remote.__file__) as handle:

        source = handle.read()

    imports = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(
            ("import ", "from ")
        )
    ]

    assert imports, "expected stdlib imports"

    for banned in (
        "network",
        "curses",
        "bleak",
        "flask",
    ):
        assert not any(
            banned in line for line in imports
        ), imports


def test_only_backend_and_local_tui_start_manager():
    sources = _project_sources()

    owners = sorted(
        name
        for name, source in sources.items()
        if "manager.start(" in source
    )

    # monitor_backend is the service owner; ui/tui.py keeps
    # the local Pi/headless mode where the TUI process
    # itself is the backend. No other file may own BLE.

    assert owners == [
        "mine-monitor/monitor_backend.py",
        "mine-monitor/ui/tui.py",
    ]
def test_no_circular_imports():
    import ui.tui
    import ui.input
    import ui.remote
    import app as web_launcher

    assert web_launcher.app is not None


def test_backend_imports_manager():
    with open(monitor_backend.__file__) as handle:

        source = handle.read()

    assert "from network import manager" in source


def test_network_loop_stays_alive_for_run_coro():
    """
    Regression test: the backend event loop must keep
    running (not just start the manager and park in
    time.sleep), otherwise run_coro() can never execute
    and POST /api/rescan always times out.
    """

    import asyncio

    reset_state()

    monitor_backend._network_loop = None

    monitor_backend._network_thread = None

    monitor_backend.start_network()

    try:

        assert (
            monitor_backend._network_thread
            is not None
        )

        deadline = time.time() + 10

        while monitor_backend._network_loop is None:

            assert time.time() < deadline

            time.sleep(0.05)


        async def probe():
            return "alive"

        assert (
            monitor_backend.run_coro(probe())
            == "alive"
        )

        assert monitor_backend._network_loop.is_running()

    finally:

        state.running = False

        monitor_backend._network_thread.join(
            timeout=15
        )

        assert not (
            monitor_backend._network_thread.is_alive()
        )

        monitor_backend._network_loop = None

        monitor_backend._network_thread = None

        reset_state()


# ============================================================
# E. REMOTE TUI SYNC
# ============================================================

def test_apply_snapshot_hydrates_state(live):
    snapshot = monitor_backend.build_snapshot()

    reset_state()

    assert remote.apply_snapshot(snapshot) is True

    assert state.connected is True

    assert state.connected_node == "NODE_001"

    assert state.selected_node == "NODE_001"

    assert "NODE_001" in state.nodes

    node = state.nodes["NODE_001"]

    assert node.temperature_c == 27.4

    assert node.humidity_percent == 76.7

    assert len(state.active_alerts) == 1

    assert any(
        "SOS" in event.message
        for event in state.events
    )


def test_apply_snapshot_empty_is_false():
    assert remote.apply_snapshot(None) is False

    assert remote.apply_snapshot({}) is False


def test_apply_snapshot_skips_malformed_entries():
    reset_state()

    snapshot = {
        "connected": False,
        "connection": "OFFLINE",
        "scanning": False,
        "connected_node": None,
        "selected_node": None,
        "message": "",
        "nodes": [{"rssi": -70}],
        "events": [],
        "alerts": [{"node_id": "NODE_001"}],
    }

    assert remote.apply_snapshot(snapshot) is True

    assert state.nodes == {}

    assert state.active_alerts == {}

    reset_state()


def test_fetch_snapshot_uses_api(monkeypatch):
    seen = {}

    def fake_get(url):
        seen["url"] = url

        return {"ok": True}

    monkeypatch.setattr(
        remote,
        "_http_get",
        fake_get,
    )

    result = remote.fetch_snapshot(
        "http://127.0.0.1:5000"
    )

    assert result == {"ok": True}

    assert seen["url"] == (
        "http://127.0.0.1:5000/api/state"
    )


def test_remote_actions_hit_api(monkeypatch):
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))

        return {"ok": True}

    monkeypatch.setattr(
        remote,
        "_http_post",
        fake_post,
    )

    base = "http://127.0.0.1:5000"

    assert remote.remote_rescan(base) is True

    assert remote.remote_select(base, "NODE_001") is True

    assert remote.remote_acknowledge(base) is True

    paths = [url for url, _ in calls]

    assert f"{base}/api/rescan" in paths

    assert f"{base}/api/select" in paths

    assert f"{base}/api/acknowledge" in paths

    assert ("NODE_001" in str(calls))


# ============================================================
# H. NON-BLOCKING CONNECT + SHUTDOWN + MODE RESOLUTION
# ============================================================
#
# Regression tests for the rescan-while-connected hang:
# connect_to_selected() must establish the connection and
# return (releasing the BLE lock) instead of blocking
# inside the lock for the whole connection lifetime.


class FakeBleakClient:
    """Minimal bleak stand-in: connects instantly, stays up."""

    fail_connect = False

    instances = []

    def __init__(self, address, disconnected_callback=None):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.disconnect_called = False
        self.notified = []
        FakeBleakClient.instances.append(self)

    async def connect(self):
        if FakeBleakClient.fail_connect:
            raise RuntimeError("mock radio failure")
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_called = True
        self.is_connected = False

    async def start_notify(self, uuid, callback):
        self.notified.append((uuid, callback))


def test_connect_returns_true_without_blocking(monkeypatch):
    import asyncio

    from network import manager, ble

    reset_state()

    FakeBleakClient.instances.clear()
    FakeBleakClient.fail_connect = False

    make_node()
    state.connected = False
    state.connected_node = None

    monkeypatch.setattr(
        ble, "BleakClient", FakeBleakClient
    )

    async def run():
        return await asyncio.wait_for(
            ble.connect_to_selected(), timeout=2
        )

    result = asyncio.run(run())

    try:

        assert result is True

        assert state.connected is True

        assert state.connected_node == "NODE_001"

        assert state.client is not None

        assert len(FakeBleakClient.instances) == 1

        assert (
            len(FakeBleakClient.instances[0].notified)
            == 1
        )

        # The BLE lock must be free afterwards.

        assert manager._ble_lock.locked() is False

    finally:

        reset_state()
        FakeBleakClient.instances.clear()


def test_connect_failure_cleans_up(monkeypatch):
    import asyncio

    from network import ble

    reset_state()

    FakeBleakClient.instances.clear()
    FakeBleakClient.fail_connect = True

    make_node()
    state.connected = False
    state.connected_node = None

    monkeypatch.setattr(
        ble, "BleakClient", FakeBleakClient
    )

    result = asyncio.run(ble.connect_to_selected())

    try:

        assert result is False

        assert state.connected is False

        assert state.connecting is False

        assert state.client is None

    finally:

        FakeBleakClient.fail_connect = False
        FakeBleakClient.instances.clear()
        reset_state()


def test_shutdown_disconnects_live_client():
    import asyncio

    from network import manager

    reset_state()

    client = FakeBleakClient("addr")
    client.is_connected = True

    state.client = client
    state.connected = True
    state.connected_node = "NODE_001"

    asyncio.run(manager.shutdown())

    try:

        assert client.disconnect_called is True

        assert state.client is None

        assert state.connected is False

    finally:

        reset_state()


def test_rescan_while_connected_returns_fast(monkeypatch):
    import asyncio

    from network import manager, ble

    reset_state()

    make_node()

    async def fast_scan():
        state.scanning = True
        state.scanning = False

    def forbidden_connect():
        raise AssertionError(
            "must not reconnect while already connected"
        )

    monkeypatch.setattr(ble, "scan_nodes", fast_scan)
    monkeypatch.setattr(
        ble, "connect_to_selected", forbidden_connect
    )

    async def run():
        return await asyncio.wait_for(
            manager.rescan(), timeout=5
        )

    asyncio.run(run())

    reset_state()


def test_resolve_mode_matrix():
    from main import resolve_mode, DEFAULT_BACKEND_URL

    assert resolve_mode(
        None, True, probe=lambda url: True
    ) == ("local", None)

    assert resolve_mode(
        "http://x:1", False, probe=lambda url: False
    ) == ("remote", "http://x:1")

    assert resolve_mode(
        None, False, probe=lambda url: True
    ) == ("remote", DEFAULT_BACKEND_URL)

    assert resolve_mode(
        None, False, probe=lambda url: False
    ) == ("local", None)


def test_backend_reachable_false_on_closed_port():
    from main import backend_reachable

    assert (
        backend_reachable("http://127.0.0.1:9") is False
    )


def test_backend_reachable_true_against_live_app():
    import threading

    from werkzeug.serving import make_server

    from main import backend_reachable

    server = make_server(
        "127.0.0.1",
        0,
        monitor_backend.create_app(),
    )

    url = f"http://127.0.0.1:{server.server_port}"

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    try:

        assert backend_reachable(url) is True

    finally:

        server.shutdown()

        thread.join(timeout=10)


# ============================================================
# F. LIVE SHARED-BACKEND INTEGRATION (real HTTP, no BLE)
# ============================================================
#
# One backend serves real sockets. The web proxy and the
# remote-TUI helpers talk to it over HTTP exactly like the
# deployed processes do. This proves both interfaces can
# observe and mutate the SAME live state simultaneously.

@pytest.fixture
def live_backend_url():
    """
    Backend with a connected node + SOS alert, served on
    a real localhost socket. The BLE manager is NOT
    started; state is seeded through the real packet
    pipeline (process_packet).
    """

    import threading

    from werkzeug.serving import make_server

    reset_state()

    make_node()

    process_packet(make_sos())

    server = make_server(
        "127.0.0.1",
        0,
        monitor_backend.create_app(),
    )

    url = (
        f"http://127.0.0.1:{server.server_port}"
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    yield url

    server.shutdown()

    thread.join(timeout=10)

    reset_state()


@pytest.fixture
def web_client(live_backend_url, monkeypatch):
    import app as webapp

    monkeypatch.setenv(
        "MONITOR_BACKEND", live_backend_url
    )

    webapp.app.config["TESTING"] = True

    with webapp.app.test_client() as test_client:

        yield test_client


def test_web_and_tui_see_same_node(live_backend_url, web_client):
    web_data = web_client.get(
        "/api/state"
    ).get_json()

    tui_snapshot = remote.fetch_snapshot(
        live_backend_url
    )

    assert web_data["connected_node"] == "NODE_001"

    assert tui_snapshot["connected_node"] == "NODE_001"

    for view in (
        web_data["nodes"][0],
        tui_snapshot["nodes"][0],
    ):
        assert view["rssi"] == -65

        assert view["temperature_c"] == 27.4

        assert view["humidity_percent"] == 76.7

        assert view["packets_received"] >= 1


def test_web_and_tui_see_same_sos(live_backend_url, web_client):
    web_alerts = web_client.get(
        "/api/state"
    ).get_json()["alerts"]

    tui_alerts = remote.fetch_snapshot(
        live_backend_url
    )["alerts"]

    assert len(web_alerts) == 1

    assert len(tui_alerts) == 1

    assert (
        web_alerts[0]["alert_id"]
        == tui_alerts[0]["alert_id"]
    )

    assert web_alerts[0]["alert_type"] == "SOS"


def test_web_acknowledge_clears_shared_alert(
    live_backend_url, web_client
):
    response = web_client.post(
        "/api/acknowledge",
        json={},
    )

    assert response.get_json() == {"ok": True}

    # The TUI view of the SAME backend loses the alert...

    tui_alerts = remote.fetch_snapshot(
        live_backend_url
    )["alerts"]

    assert tui_alerts == []

    # ...while the SOS stays in shared event history.

    events = remote.fetch_snapshot(
        live_backend_url
    )["events"]

    assert any(
        "SOS" in event["message"] for event in events
    )


def test_tui_acknowledge_clears_shared_alert(
    live_backend_url, web_client
):
    assert remote.remote_acknowledge(
        live_backend_url
    ) is True

    # The web view of the SAME backend loses the alert.

    web_alerts = web_client.get(
        "/api/state"
    ).get_json()["alerts"]

    assert web_alerts == []


def test_heartbeat_and_duplicates_via_shared_backend(
    live_backend_url, web_client
):
    process_packet(make_status())

    process_packet(make_sos())

    web_alerts = web_client.get(
        "/api/state"
    ).get_json()["alerts"]

    assert len(web_alerts) == 1


def test_backend_error_status_reaches_browser(
    live_backend_url, web_client
):
    response = web_client.post(
        "/api/select",
        json={"name": "NOPE"},
    )

    assert response.status_code == 404


# ============================================================
# G. RESCAN SERIALIZATION (one BLE op at a time)
# ============================================================

def test_concurrent_rescans_never_overlap(monkeypatch):
    import asyncio

    from network import manager, ble

    reset_state()

    active = 0

    max_active = 0

    async def slow_scan():
        nonlocal active, max_active

        state.scanning = True

        active += 1

        max_active = max(max_active, active)

        try:

            await asyncio.sleep(0.2)

        finally:

            active -= 1

            state.scanning = False

    monkeypatch.setattr(
        ble, "scan_nodes", slow_scan
    )

    async def both():
        await asyncio.gather(
            manager.rescan(),
            manager.rescan(),
        )

    asyncio.run(both())

    assert max_active == 1

    reset_state()
