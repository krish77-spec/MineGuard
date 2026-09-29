"""
High-level network manager.

The UI interacts with this module instead of directly
with BLE or other transport layers.

Manages:
    - BLE scanning
    - BLE connection
    - Reconnection with exponential backoff
    - Concurrent operation prevention via lock
"""

import asyncio
import logging

from config import RECONNECT_DELAY
from state import state, add_event
from network import ble


log = logging.getLogger("manager")


_network_task = None

_ble_lock = asyncio.Lock()

_reconnect_delay = RECONNECT_DELAY

MAX_RECONNECT_DELAY = 30


# ============================================================
# BACKGROUND NETWORK LOOP
# ============================================================

async def _run():
    """
    Background scan and connect loop.

    Uses a lock to prevent concurrent BLE operations.
    Implements exponential backoff after disconnects.
    """

    global _reconnect_delay

    while state.running:

        try:

            # ----------------------------------------------
            # If connected, wait and check again
            # ----------------------------------------------

            if state.connected:

                await asyncio.sleep(1)

                continue


            # ----------------------------------------------
            # Acquire BLE lock — only one operation at a time
            # ----------------------------------------------

            async with _ble_lock:

                # ------------------------------------------
                # Scan for nodes
                # ------------------------------------------

                if state.scanning:

                    await asyncio.sleep(1)

                    continue


                await ble.scan_nodes()


                # ------------------------------------------
                # Connect if a node was found
                # ------------------------------------------

                if (
                    state.selected_node
                    and not state.connected
                    and not state.connecting
                ):

                    connected = (
                        await ble
                        .connect_to_selected()
                    )

                    if connected:

                        # ------------------------------
                        # Reset backoff on success
                        # ------------------------------

                        _reconnect_delay = (
                            RECONNECT_DELAY
                        )

                        log.info(
                            "Connection successful "
                            "- backoff reset"
                        )

                    else:

                        # ------------------------------
                        # Increase backoff on failure
                        # ------------------------------

                        _reconnect_delay = min(
                            _reconnect_delay * 2,
                            MAX_RECONNECT_DELAY,
                        )

                        log.info(
                            "Connection failed "
                            "- backoff %ds",
                            _reconnect_delay,
                        )


            # ----------------------------------------------
            # Wait before next cycle (outside lock)
            # ----------------------------------------------

            await asyncio.sleep(
                _reconnect_delay
            )


        except asyncio.CancelledError:

            break


        except Exception as error:

            log.error(
                "Network manager error: %s",
                error,
            )

            add_event(
                f"Network error: {error}",
                "ERROR"
            )

            await asyncio.sleep(
                _reconnect_delay
            )


# ============================================================
# PUBLIC API
# ============================================================

async def start():
    """Start the background network management task."""

    global _network_task

    _network_task = asyncio.create_task(_run())


async def scan():
    """Trigger a BLE scan for mine nodes."""

    async with _ble_lock:

        await ble.scan_nodes()


async def connect():
    """Connect to the currently selected node."""

    async with _ble_lock:

        await ble.connect_to_selected()


async def rescan():
    """Scan for nodes and connect if possible."""

    async with _ble_lock:

        if state.scanning:

            return


        await ble.scan_nodes()


        if (
            not state.connected
            and state.selected_node
            and not state.connecting
        ):

            await ble.connect_to_selected()


async def shutdown():
    """Cancel the background network task."""

    global _network_task

    if _network_task:

        _network_task.cancel()

        try:

            await _network_task

        except asyncio.CancelledError:

            pass

        _network_task = None


    # --------------------------------------------------------
    # Tidy teardown of a live connection.
    #
    # connect_to_selected() returns right after subscribing
    # (it no longer blocks inside the BLE lock while
    # connected), so an orderly shutdown disconnects here
    # instead of in the connect path. Unexpected drops are
    # still reported by the bleak disconnect callback.
    # --------------------------------------------------------

    client = state.client

    state.client = None

    state.connected = False

    state.connecting = False

    state.connected_node = None


    if client is not None:

        try:

            if client.is_connected:

                await client.disconnect()

        except Exception:

            pass
