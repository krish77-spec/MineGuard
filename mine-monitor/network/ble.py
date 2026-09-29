import asyncio
import logging
import time

from bleak import (
    BleakScanner,
    BleakClient,
)

from config import (
    SERVICE_UUID,
    PACKET_UUID,
    SCAN_TIME,
)

from models import NodeInfo

from state import (
    state,
    add_event,
)

from network.packets import (
    handle_packet,
)


log = logging.getLogger("ble")


# ============================================================
# SCAN
# ============================================================

async def scan_nodes():
    """
    Scan for mine safety mesh nodes.

    This function is called by the manager.
    The manager ensures only one scan runs at a time.
    """

    state.scanning = True

    state.message = (
        "Scanning for mine nodes..."
    )

    log.info("Scan started")

    add_event(
        "Scanning for mine nodes",
        "SCAN"
    )


    try:

        results = await BleakScanner.discover(
            timeout=SCAN_TIME,
            return_adv=True
        )


        discovered = {}


        for address, result in results.items():

            device, advertisement = result


            services = [
                service.lower()
                for service
                in advertisement.service_uuids
            ]


            # ----------------------------------------------
            # Only accept Mine Safety Mesh nodes
            # ----------------------------------------------

            if (
                SERVICE_UUID.lower()
                not in services
            ):

                continue


            name = (
                device.name
                or advertisement.local_name
                or "UNKNOWN"
            )


            rssi = advertisement.rssi


            node = NodeInfo(

                name=name,

                address=device.address,

                rssi=rssi,

                status="AVAILABLE",

                last_seen=time.time()
            )


            # ----------------------------------------------
            # Preserve existing node information
            # ----------------------------------------------

            if name in state.nodes:

                old = state.nodes[name]

                node.last_heartbeat = (
                    old.last_heartbeat
                )

                node.last_sequence = (
                    old.last_sequence
                )

                node.packets_received = (
                    old.packets_received
                )


            discovered[name] = node


        # ====================================================
        # UPDATE GLOBAL NODE LIST
        # ====================================================

        state.nodes.update(
            discovered
        )


        # ====================================================
        # SELECT STRONGEST NODE
        # ====================================================

        if discovered:

            if (
                state.selected_node is None
                or
                state.selected_node
                not in state.nodes
            ):

                best_node = max(
                    discovered.values(),
                    key=lambda node: node.rssi
                )

                state.selected_node = (
                    best_node.name
                )


            state.message = (
                f"{len(discovered)} "
                f"mine node(s) found"
            )

            log.info(
                "Scan found %d node(s)",
                len(discovered),
            )


        else:

            state.message = (
                "No mine nodes detected"
            )

            log.info("Scan found no nodes")


    except asyncio.CancelledError:

        raise


    except Exception as error:

        state.message = (
            f"Scan error: {error}"
        )

        log.warning("Scan error: %s", error)

        add_event(
            f"Scan error: {error}",
            "ERROR"
        )


    finally:

        state.scanning = False


# ============================================================
# DISCONNECT CALLBACK
# ============================================================

def disconnected_callback(
    client
):
    """
    Called by Bleak when the BLE connection drops.

    This runs in the event loop thread.
    We only update state here — the manager
    handles reconnection scheduling.
    """

    log.info("BLE disconnect callback fired")

    state.connected = False

    state.connecting = False

    state.connected_node = None

    state.client = None


    add_event(
        "Mine node disconnected",
        "WARNING"
    )


    state.message = (
        "Node disconnected - searching..."
    )


# ============================================================
# CONNECT
# ============================================================

async def connect_to_selected():
    """
    Connect to the currently selected node.

    The manager ensures only one connection attempt
    runs at a time via the BLE operations lock.

    Returns True if a live connection was established
    (notifications subscribed). Returns False otherwise.

    This function does NOT block while connected: once
    the connection is established the lock is released
    and the manager's background loop idles on
    state.connected (lock-free) until the bleak
    disconnect callback reports a drop. Blocking here
    would hold the BLE lock for the whole connection
    lifetime and starve every other BLE operation
    (scan/rescan/connect) until disconnect.
    """

    if not state.selected_node:

        return False


    if state.connected:

        return True


    node = state.nodes.get(
        state.selected_node
    )


    if node is None:

        return False


    # --------------------------------------------------------
    # Clean up any existing client before connecting
    # --------------------------------------------------------

    old_client = state.client

    if old_client is not None:

        state.client = None

        try:

            if old_client.is_connected:

                await old_client.disconnect()

        except Exception:

            pass

        old_client = None


    state.connecting = True


    state.message = (
        f"Connecting to {node.name}..."
    )

    log.info(
        "Connection attempt to %s (%s)",
        node.name,
        node.address,
    )

    add_event(
        f"Connecting to {node.name}",
        "CONNECT"
    )


    client = BleakClient(

        node.address,

        disconnected_callback=
        disconnected_callback
    )


    established = False


    try:

        await client.connect()


        if not client.is_connected:

            raise RuntimeError(
                "BLE connection failed"
            )


        state.client = client

        state.connected = True

        state.connecting = False

        state.connected_node = (
            node.name
        )


        node.status = "ONLINE"


        state.message = (
            f"Connected to {node.name}"
        )

        log.info("Connected to %s", node.name)

        add_event(
            f"{node.name} connected",
            "CONNECT"
        )


        # ====================================================
        # SUBSCRIBE
        # ====================================================

        await client.start_notify(
            PACKET_UUID,
            handle_packet
        )


        add_event(
            "Packet notifications active",
            "INFO"
        )


        established = True

        return True


    except asyncio.CancelledError:

        raise


    except Exception as error:

        state.message = (
            f"Connection error: {error}"
        )

        log.warning(
            "Connection error: %s", error
        )

        add_event(
            f"Connection error: {error}",
            "ERROR"
        )

        return False


    finally:

        state.connecting = False


        if not established:

            state.connected = False

            state.connected_node = None

            state.client = None


            try:

                if client.is_connected:

                    await client.disconnect()

            except Exception:

                pass
