"""
Transport-independent packet processor.

Processes already-decoded Packet objects.
Handles duplicate suppression, node state updates,
and event generation.

Does NOT know whether the packet arrived via BLE,
ESP-NOW, or any other transport.
"""

import time
import logging
import traceback
from datetime import datetime

from models import Packet
from state import (
    state,
    add_event,
    add_packet,
    create_alert,
)
from network import protocol


log = logging.getLogger("packets")


# ============================================================
# PROCESS PACKET
# ============================================================

def process_packet(packet):
    """
    Process a validated Packet object.

    This is the primary entry point for packet processing.
    All transports should decode raw bytes into a Packet
    and then call this function.

    Handles:
        - duplicate suppression
        - node state updates
        - heartbeat tracking
        - packet history storage
        - event generation (SOS, STATUS, generic)
    """

    pid = protocol.packet_id(packet)

    if pid in state.last_packet_ids:
        log.debug(
            "DUPLICATE SUPPRESSED pid=%s", pid
        )
        return

    log.debug(
        "NEW PACKET pid=%s type=%s",
        pid,
        packet.packet_type,
    )

    state.last_packet_ids.add(pid)

    if len(state.last_packet_ids) > 1000:
        state.last_packet_ids = set(
            list(state.last_packet_ids)[-500:]
        )

    _update_node(packet)

    add_packet(packet)

    _create_event(packet)


# ============================================================
# HANDLE PACKET (BLE COMPATIBILITY)
# ============================================================

def handle_packet(sender, data):
    """
    BLE notification callback.

    Decodes raw bytes using the protocol layer,
    then delegates to process_packet().

    The 'sender' argument is the BLE connection
    identity (transport metadata) and is NOT used
    to overwrite packet.sender. The packet's own
    sender field is the logical network sender.
    """

    log.info(
        "BLE NOTIFICATION RECEIVED "
        "data_len=%d data_type=%s",
        len(data),
        type(data).__name__,
    )

    try:
        packet = protocol.decode(data)

        if packet is None:
            log.warning(
                "DECODE FAILED raw=%r", data
            )
            add_event(
                "Invalid packet received",
                "ERROR"
            )
            return

        log.info(
            "DECODE OK packet_type=%s "
            "origin=%s seq=%s priority=%s",
            packet.packet_type,
            packet.origin,
            packet.sequence,
            packet.priority,
        )

        valid, reason = protocol.validate(packet)

        if not valid:
            log.warning(
                "VALIDATE FAILED reason=%s", reason
            )
            add_event(
                f"Invalid packet: {reason}",
                "ERROR"
            )
            return

        log.info(
            "VALIDATE OK - calling process_packet()"
        )
        process_packet(packet)

        log.info(
            "process_packet() completed "
            "active_alerts=%d events=%d",
            len(state.active_alerts),
            len(state.events),
        )

    except Exception as error:
        log.error(
            "EXCEPTION in handle_packet: %s",
            error,
        )
        log.error(traceback.format_exc())
        add_event(
            f"Notification callback error: {error}",
            "ERROR"
        )


# ============================================================
# NODE UPDATE
# ============================================================

def _update_node(packet):
    """
    Update the originating node's state based on
    the received packet.
    """

    node = state.nodes.get(packet.origin)

    if not node:
        return

    node.last_seen = time.time()
    node.last_sequence = packet.sequence
    node.packets_received += 1

    if packet.packet_type == "STATUS":
        node.last_heartbeat = time.time()

    if packet.temperature_c is not None:
        node.temperature_c = packet.temperature_c

    if packet.humidity_percent is not None:
        node.humidity_percent = packet.humidity_percent


# ============================================================
# EVENT GENERATION
# ============================================================

def _create_event(packet):
    """
    Create an appropriate event for a received packet.
    For SOS packets, also register a persistent alert.
    """

    timestamp = datetime.now().strftime(
        "%H:%M:%S"
    )

    if packet.packet_type == "SOS":
        log.info(
            "SOS EVENT CREATION origin=%s seq=%s",
            packet.origin,
            packet.sequence,
        )
        add_event(
            f"SOS from {packet.origin}",
            "SOS"
        )

        pid = protocol.packet_id(packet)

        log.info(
            "SOS ALERT CREATION pid=%s", pid
        )

        alert = create_alert(
            packet,
            pid,
            timestamp
        )

        log.info(
            "SOS ALERT RESULT created=%s "
            "active_alerts=%d",
            alert is not None,
            len(state.active_alerts),
        )

    elif packet.packet_type == "STATUS":
        add_event(
            f"Heartbeat from {packet.origin}",
            "INFO"
        )

    else:
        add_event(
            f"{packet.packet_type} "
            f"from {packet.origin}",
            "INFO"
        )
