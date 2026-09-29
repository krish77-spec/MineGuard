import time
from datetime import datetime

from config import (
    MAX_EVENTS,
    MAX_PACKETS,
)

from models import (
    ApplicationState,
    Alert,
    Event,
)


state = ApplicationState()


def now():
    return time.time()


def add_event(
    message,
    level="INFO"
):

    timestamp = datetime.now().strftime(
        "%H:%M:%S"
    )

    state.events.insert(
        0,
        Event(
            timestamp=timestamp,
            level=level,
            message=message
        )
    )

    state.events = state.events[
        :MAX_EVENTS
    ]


def add_packet(packet):

    timestamp = datetime.now().strftime(
        "%H:%M:%S"
    )

    state.packets.insert(
        0,
        (
            timestamp,
            packet
        )
    )

    state.packets = state.packets[
        :MAX_PACKETS
    ]


def create_alert(packet, alert_id, timestamp):
    """
    Create a persistent emergency alert from a packet.

    Returns the new Alert, or None if an alert with
    this ID already exists (duplicate suppression).
    """

    if alert_id in state.active_alerts:
        return None

    alert = Alert(
        alert_id=alert_id,
        alert_type=packet.packet_type,
        node_id=packet.origin,
        timestamp=timestamp,
        priority=packet.priority,
        packet=packet,
    )

    state.active_alerts[alert_id] = alert

    return alert


def acknowledge_alert(alert_id):
    """
    Remove an active alert by its ID.

    Returns True if the alert was found and removed.
    Returns False if the alert was not found.
    """

    if alert_id in state.active_alerts:
        del state.active_alerts[alert_id]
        return True

    return False


def get_active_alerts():
    """
    Return a list of active alerts sorted by
    priority (highest first), then by timestamp.
    """

    alerts = list(state.active_alerts.values())

    alerts.sort(
        key=lambda a: (-a.priority, a.timestamp),
        reverse=False
    )

    return alerts
