"""
Transport-independent packet protocol.

Handles encoding, decoding, validation, and identification
of mine safety mesh packets.

Both BLE and ESP-NOW use this same protocol layer.
"""

import json

from models import Packet


# ============================================================
# PROTOCOL VERSION
# ============================================================

SUPPORTED_VERSIONS = {1}


# ============================================================
# WIRE FORMAT KEYS
# ============================================================

KEY_VERSION = "v"
KEY_TYPE = "type"
KEY_ORIGIN = "origin"
KEY_SENDER = "sender"
KEY_SEQUENCE = "seq"
KEY_PRIORITY = "priority"
KEY_TTL = "ttl"
KEY_HOPS = "hops"
KEY_TIME_MS = "time_ms"
KEY_TEMPERATURE = "temperature_c"
KEY_HUMIDITY = "humidity_percent"


# ============================================================
# DECODE
# ============================================================

def decode(raw_data):
    """
    Decode raw bytes into a Packet.

    Returns a Packet on success.
    Returns None on any error (malformed JSON, missing
    fields, unsupported version, etc.).

    Never raises exceptions.
    """

    try:
        text = raw_data.decode("utf-8", errors="replace")
        data = json.loads(text)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    return _dict_to_packet(data)


# ============================================================
# ENCODE
# ============================================================

def encode(packet):
    """
    Encode a Packet into bytes.

    Uses the wire format compatible with the current ESP32:

        v, type, origin, sender, seq, priority, ttl,
        hops, time_ms

    Returns bytes suitable for transmission.
    """

    data = {
        KEY_VERSION: packet.version,
        KEY_TYPE: packet.packet_type,
        KEY_ORIGIN: packet.origin,
        KEY_SENDER: packet.sender,
        KEY_SEQUENCE: packet.sequence,
        KEY_PRIORITY: packet.priority,
        KEY_TTL: packet.ttl,
        KEY_HOPS: packet.hops,
        KEY_TIME_MS: packet.time_ms,
    }

    if packet.temperature_c is not None:
        data[KEY_TEMPERATURE] = packet.temperature_c

    if packet.humidity_percent is not None:
        data[KEY_HUMIDITY] = packet.humidity_percent

    return json.dumps(data).encode("utf-8")


# ============================================================
# VALIDATE
# ============================================================

def validate(packet):
    """
    Validate a decoded Packet.

    Returns (True, None) if valid.
    Returns (False, reason) if invalid.

    Checks:
        - protocol version is supported
        - packet_type is present and non-empty
        - origin is present and non-empty
        - sender is present and non-empty
        - sequence is numeric
        - priority is numeric
        - ttl is numeric
        - hops is numeric
        - time_ms is numeric
    """

    if packet.version not in SUPPORTED_VERSIONS:
        return (
            False,
            f"Unsupported version: {packet.version}"
        )

    if not packet.packet_type:
        return (False, "Missing packet type")

    if not packet.origin:
        return (False, "Missing origin")

    if not packet.sender:
        return (False, "Missing sender")

    for field_name, value in [
        ("sequence", packet.sequence),
        ("priority", packet.priority),
        ("ttl", packet.ttl),
        ("hops", packet.hops),
        ("time_ms", packet.time_ms),
    ]:
        if not isinstance(value, int):
            return (
                False,
                f"Invalid {field_name}: "
                f"expected int, got "
                f"{type(value).__name__}"
            )

    if packet.temperature_c is not None:
        if not isinstance(
            packet.temperature_c, (int, float)
        ):
            return (
                False,
                "Invalid temperature_c: "
                "expected numeric"
            )
        if not (-40 <= packet.temperature_c <= 80):
            return (
                False,
                "Invalid temperature_c: "
                "out of range"
            )

    if packet.humidity_percent is not None:
        if not isinstance(
            packet.humidity_percent, (int, float)
        ):
            return (
                False,
                "Invalid humidity_percent: "
                "expected numeric"
            )
        if not (0 <= packet.humidity_percent <= 100):
            return (
                False,
                "Invalid humidity_percent: "
                "out of range"
            )

    return (True, None)


# ============================================================
# PACKET ID
# ============================================================

def packet_id(packet):
    """
    Generate a unique ID for a packet.

    Format: "origin:sequence:time_ms"

    This identifies a specific packet from a specific
    origin with a specific sequence and timestamp.

    Future improvement: when boot_id / session_id are
    added to the ESP32 protocol, this function should
    incorporate them to handle sequence resets after
    reboot. For now, origin+sequence+time_ms is
    sufficient because time_ms changes with each packet.
    """

    return (
        f"{packet.origin}:"
        f"{packet.sequence}:"
        f"{packet.time_ms}"
    )


# ============================================================
# INTERNAL
# ============================================================

def _dict_to_packet(data):
    """
    Convert a JSON dict to a Packet dataclass.

    Applies defaults for missing fields.
    Validates numeric types.
    Returns None if critical fields are invalid.
    """

    origin = data.get(KEY_ORIGIN)
    if not origin:
        return None

    sender = data.get(KEY_SENDER)
    if not sender:
        return None

    packet_type = data.get(KEY_TYPE)
    if not packet_type:
        return None

    version = data.get(KEY_VERSION, 1)
    if not isinstance(version, int):
        return None

    sequence = _safe_int(
        data.get(KEY_SEQUENCE), -1
    )
    priority = _safe_int(
        data.get(KEY_PRIORITY), 0
    )
    ttl = _safe_int(data.get(KEY_TTL), 0)
    hops = _safe_int(data.get(KEY_HOPS), 0)
    time_ms = _safe_int(
        data.get(KEY_TIME_MS), 0
    )

    temperature_c = data.get(KEY_TEMPERATURE)
    humidity_percent = data.get(KEY_HUMIDITY)

    if temperature_c is not None:
        temperature_c = _safe_float(
            temperature_c, None
        )

    if humidity_percent is not None:
        humidity_percent = _safe_float(
            humidity_percent, None
        )

    return Packet(
        version=version,
        packet_type=packet_type,
        origin=origin,
        sender=sender,
        sequence=sequence,
        priority=priority,
        ttl=ttl,
        hops=hops,
        time_ms=time_ms,
        temperature_c=temperature_c,
        humidity_percent=humidity_percent,
    )


def _safe_int(value, default):
    """
    Convert a value to int, returning default on failure.
    """

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default

    return default


def _safe_float(value, default):
    """
    Convert a value to float, returning default on failure.
    """

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default

    return default
