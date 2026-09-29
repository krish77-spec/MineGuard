"""
Tests for the transport-independent protocol layer.

Run with: python -m pytest tests/test_protocol.py -v
"""

import json
import sys
import os

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from models import Packet
from network import protocol


# ============================================================
# SAMPLE PACKETS
# ============================================================

SAMPLE_STATUS = {
    "v": 1,
    "type": "STATUS",
    "origin": "NODE_001",
    "sender": "NODE_001",
    "seq": 5,
    "priority": 0,
    "ttl": 10,
    "hops": 0,
    "time_ms": 25011,
}

SAMPLE_SOS = {
    "v": 1,
    "type": "SOS",
    "origin": "NODE_003",
    "sender": "NODE_003",
    "seq": 1,
    "priority": 1,
    "ttl": 10,
    "hops": 0,
    "time_ms": 1000,
}

SAMPLE_STATUS_WITH_SENSORS = {
    "v": 1,
    "type": "STATUS",
    "origin": "NODE_001",
    "sender": "NODE_001",
    "seq": 6,
    "priority": 0,
    "ttl": 10,
    "hops": 0,
    "time_ms": 27100,
    "temperature_c": 27.4,
    "humidity_percent": 61.0,
}

SAMPLE_STATUS_TEMPERATURE_ONLY = {
    "v": 1,
    "type": "STATUS",
    "origin": "NODE_001",
    "sender": "NODE_001",
    "seq": 7,
    "priority": 0,
    "ttl": 10,
    "hops": 0,
    "time_ms": 28000,
    "temperature_c": 22.0,
}

SAMPLE_STATUS_HUMIDITY_ONLY = {
    "v": 1,
    "type": "STATUS",
    "origin": "NODE_001",
    "sender": "NODE_001",
    "seq": 8,
    "priority": 0,
    "ttl": 10,
    "hops": 0,
    "time_ms": 29000,
    "humidity_percent": 75.5,
}


# ============================================================
# DECODE TESTS
# ============================================================


class TestDecode:

    def test_decode_status(self):
        raw = json.dumps(SAMPLE_STATUS).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.version == 1
        assert packet.packet_type == "STATUS"
        assert packet.origin == "NODE_001"
        assert packet.sender == "NODE_001"
        assert packet.sequence == 5
        assert packet.priority == 0
        assert packet.ttl == 10
        assert packet.hops == 0
        assert packet.time_ms == 25011

    def test_decode_sos(self):
        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.packet_type == "SOS"
        assert packet.origin == "NODE_003"
        assert packet.priority == 1

    def test_decode_invalid_json(self):
        raw = b"not valid json {{{"
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_empty_bytes(self):
        raw = b""
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_non_dict_json(self):
        raw = json.dumps([1, 2, 3]).encode("utf-8")
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_string_json(self):
        raw = json.dumps("just a string").encode("utf-8")
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_missing_origin(self):
        data = SAMPLE_STATUS.copy()
        del data["origin"]
        raw = json.dumps(data).encode("utf-8")
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_missing_sender(self):
        data = SAMPLE_STATUS.copy()
        del data["sender"]
        raw = json.dumps(data).encode("utf-8")
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_missing_type(self):
        data = SAMPLE_STATUS.copy()
        del data["type"]
        raw = json.dumps(data).encode("utf-8")
        packet = protocol.decode(raw)
        assert packet is None

    def test_decode_defaults_for_missing_optional(self):
        data = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_001",
            "sender": "NODE_001",
        }
        raw = json.dumps(data).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.sequence == -1
        assert packet.priority == 0
        assert packet.ttl == 0
        assert packet.hops == 0
        assert packet.time_ms == 0

    def test_decode_numeric_string_fields(self):
        data = SAMPLE_STATUS.copy()
        data["seq"] = "10"
        data["ttl"] = "8"
        data["hops"] = "2"
        raw = json.dumps(data).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.sequence == 10
        assert packet.ttl == 8
        assert packet.hops == 2


# ============================================================
# ENCODE TESTS
# ============================================================


class TestEncode:

    def test_encode_roundtrip(self):
        original = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=5,
            priority=0,
            ttl=10,
            hops=0,
            time_ms=25011,
        )

        encoded = protocol.encode(original)
        decoded = protocol.decode(encoded)

        assert decoded is not None
        assert decoded.version == original.version
        assert decoded.packet_type == original.packet_type
        assert decoded.origin == original.origin
        assert decoded.sender == original.sender
        assert decoded.sequence == original.sequence
        assert decoded.priority == original.priority
        assert decoded.ttl == original.ttl
        assert decoded.hops == original.hops
        assert decoded.time_ms == original.time_ms

    def test_encode_returns_bytes(self):
        packet = Packet(
            origin="NODE_001",
            sender="NODE_001",
            packet_type="STATUS",
        )
        encoded = protocol.encode(packet)
        assert isinstance(encoded, bytes)

    def test_encode_wire_format_keys(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=5,
            priority=0,
            ttl=10,
            hops=0,
            time_ms=25011,
        )

        encoded = protocol.encode(packet)
        data = json.loads(encoded.decode("utf-8"))

        assert "v" in data
        assert "type" in data
        assert "origin" in data
        assert "sender" in data
        assert "seq" in data
        assert "priority" in data
        assert "ttl" in data
        assert "hops" in data
        assert "time_ms" in data


# ============================================================
# VALIDATE TESTS
# ============================================================


class TestValidate:

    def test_valid_packet(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=5,
            priority=0,
            ttl=10,
            hops=0,
            time_ms=25011,
        )
        valid, reason = protocol.validate(packet)
        assert valid is True
        assert reason is None

    def test_unsupported_version(self):
        packet = Packet(
            version=99,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "version" in reason.lower()

    def test_missing_type(self):
        packet = Packet(
            version=1,
            packet_type="",
            origin="NODE_001",
            sender="NODE_001",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "type" in reason.lower()

    def test_missing_origin(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="",
            sender="NODE_001",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "origin" in reason.lower()

    def test_missing_sender(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "sender" in reason.lower()

    def test_invalid_sequence_type(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence="not_int",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "sequence" in reason.lower()

    def test_invalid_ttl_type(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            ttl="high",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "ttl" in reason.lower()

    def test_invalid_hops_type(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            hops=3.5,
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "hops" in reason.lower()


# ============================================================
# PACKET ID TESTS
# ============================================================


class TestPacketId:

    def test_packet_id_format(self):
        packet = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )
        pid = protocol.packet_id(packet)
        assert pid == "NODE_001:5:25011"

    def test_duplicate_detection(self):
        packet1 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )
        packet2 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )

        id1 = protocol.packet_id(packet1)
        id2 = protocol.packet_id(packet2)

        assert id1 == id2

    def test_different_sequence_not_duplicate(self):
        packet1 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )
        packet2 = Packet(
            origin="NODE_001",
            sequence=6,
            time_ms=25011,
        )

        id1 = protocol.packet_id(packet1)
        id2 = protocol.packet_id(packet2)

        assert id1 != id2

    def test_different_origin_not_duplicate(self):
        packet1 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )
        packet2 = Packet(
            origin="NODE_002",
            sequence=5,
            time_ms=25011,
        )

        id1 = protocol.packet_id(packet1)
        id2 = protocol.packet_id(packet2)

        assert id1 != id2

    def test_different_time_not_duplicate(self):
        packet1 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25011,
        )
        packet2 = Packet(
            origin="NODE_001",
            sequence=5,
            time_ms=25012,
        )

        id1 = protocol.packet_id(packet1)
        id2 = protocol.packet_id(packet2)

        assert id1 != id2


# ============================================================
# FORWARDING SEMANTICS TESTS
# ============================================================


class TestForwardingSemantics:

    def test_forwarded_packet_preserves_origin_and_seq(self):
        original = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_007",
            "sender": "NODE_007",
            "seq": 42,
            "priority": 0,
            "ttl": 10,
            "hops": 0,
            "time_ms": 5000,
        }

        forwarded_by_004 = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_007",
            "sender": "NODE_004",
            "seq": 42,
            "priority": 0,
            "ttl": 9,
            "hops": 1,
            "time_ms": 5000,
        }

        forwarded_by_002 = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_007",
            "sender": "NODE_002",
            "seq": 42,
            "priority": 0,
            "ttl": 8,
            "hops": 2,
            "time_ms": 5000,
        }

        pkt_orig = protocol.decode(
            json.dumps(original).encode("utf-8")
        )
        pkt_fwd1 = protocol.decode(
            json.dumps(forwarded_by_004).encode("utf-8")
        )
        pkt_fwd2 = protocol.decode(
            json.dumps(forwarded_by_002).encode("utf-8")
        )

        assert pkt_orig is not None
        assert pkt_fwd1 is not None
        assert pkt_fwd2 is not None

        # Origin and sequence must remain unchanged
        assert pkt_fwd1.origin == pkt_orig.origin
        assert pkt_fwd1.sequence == pkt_orig.sequence
        assert pkt_fwd2.origin == pkt_orig.origin
        assert pkt_fwd2.sequence == pkt_orig.sequence

        # Sender, hops, and ttl change
        assert pkt_fwd1.sender == "NODE_004"
        assert pkt_fwd1.hops == 1
        assert pkt_fwd1.ttl == 9

        assert pkt_fwd2.sender == "NODE_002"
        assert pkt_fwd2.hops == 2
        assert pkt_fwd2.ttl == 8

    def test_forwarded_packet_same_time_ms_same_id(self):
        """Forwarded packets with same origin/seq/time_ms
        should be detected as duplicates."""

        pkt1_data = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_007",
            "sender": "NODE_007",
            "seq": 42,
            "ttl": 10,
            "hops": 0,
            "time_ms": 5000,
        }

        pkt2_data = {
            "v": 1,
            "type": "STATUS",
            "origin": "NODE_007",
            "sender": "NODE_004",
            "seq": 42,
            "ttl": 9,
            "hops": 1,
            "time_ms": 5000,
        }

        pkt1 = protocol.decode(
            json.dumps(pkt1_data).encode("utf-8")
        )
        pkt2 = protocol.decode(
            json.dumps(pkt2_data).encode("utf-8")
        )

        assert protocol.packet_id(pkt1) == \
               protocol.packet_id(pkt2)


# ============================================================
# IMPORT / INTEGRATION TESTS
# ============================================================


class TestImports:

    def test_protocol_imports(self):
        assert hasattr(protocol, "decode")
        assert hasattr(protocol, "encode")
        assert hasattr(protocol, "validate")
        assert hasattr(protocol, "packet_id")

    def test_packets_module_imports(self):
        from network import packets

        assert hasattr(packets, "process_packet")
        assert hasattr(packets, "handle_packet")

    def test_no_circular_imports(self):
        """Verify all modules can be imported
        without circular dependency errors."""

        import importlib
        import network.protocol
        import network.packets
        import network.ble
        import network.manager
        import state
        import models
        import config

        importlib.reload(network.protocol)
        importlib.reload(network.packets)
        importlib.reload(network.ble)
        importlib.reload(network.manager)

    def test_handle_packet_rejects_invalid_json(self):
        """handle_packet should not crash on bad data."""

        from network import packets
        from state import state

        initial_events = len(state.events)

        packets.handle_packet(
            "BLE_SENDER",
            b"not json at all"
        )

        assert len(state.events) > initial_events
        last_event = state.events[0]
        assert "Invalid" in last_event.message


# ============================================================
# SENSOR DECODE TESTS
# ============================================================


class TestSensorDecode:

    def test_decode_status_without_sensors(self):
        raw = json.dumps(SAMPLE_STATUS).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.temperature_c is None
        assert packet.humidity_percent is None

    def test_decode_status_with_both_sensors(self):
        raw = json.dumps(
            SAMPLE_STATUS_WITH_SENSORS
        ).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.temperature_c == 27.4
        assert packet.humidity_percent == 61.0

    def test_decode_status_temperature_only(self):
        raw = json.dumps(
            SAMPLE_STATUS_TEMPERATURE_ONLY
        ).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.temperature_c == 22.0
        assert packet.humidity_percent is None

    def test_decode_status_humidity_only(self):
        raw = json.dumps(
            SAMPLE_STATUS_HUMIDITY_ONLY
        ).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.temperature_c is None
        assert packet.humidity_percent == 75.5

    def test_decode_sos_without_sensors(self):
        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.packet_type == "SOS"
        assert packet.temperature_c is None
        assert packet.humidity_percent is None


# ============================================================
# SENSOR ENCODE TESTS
# ============================================================


class TestSensorEncode:

    def test_encode_roundtrip_with_sensors(self):
        original = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=6,
            priority=0,
            ttl=10,
            hops=0,
            time_ms=27100,
            temperature_c=27.4,
            humidity_percent=61.0,
        )

        encoded = protocol.encode(original)
        decoded = protocol.decode(encoded)

        assert decoded is not None
        assert decoded.temperature_c == 27.4
        assert decoded.humidity_percent == 61.0

    def test_encode_roundtrip_without_sensors(self):
        original = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=5,
            priority=0,
            ttl=10,
            hops=0,
            time_ms=25011,
        )

        encoded = protocol.encode(original)
        decoded = protocol.decode(encoded)

        assert decoded is not None
        assert decoded.temperature_c is None
        assert decoded.humidity_percent is None

    def test_encode_includes_sensor_keys(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=6,
            temperature_c=25.0,
            humidity_percent=50.0,
        )

        encoded = protocol.encode(packet)
        data = json.loads(encoded.decode("utf-8"))

        assert "temperature_c" in data
        assert "humidity_percent" in data

    def test_encode_omits_null_sensors(self):
        packet = Packet(
            version=1,
            packet_type="SOS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=1,
        )

        encoded = protocol.encode(packet)
        data = json.loads(encoded.decode("utf-8"))

        assert "temperature_c" not in data
        assert "humidity_percent" not in data


# ============================================================
# SENSOR VALIDATE TESTS
# ============================================================


class TestSensorValidate:

    def test_valid_with_sensors(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=6,
            temperature_c=27.4,
            humidity_percent=61.0,
        )
        valid, reason = protocol.validate(packet)
        assert valid is True

    def test_valid_without_sensors(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            sequence=5,
        )
        valid, reason = protocol.validate(packet)
        assert valid is True

    def test_invalid_temperature_type(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            temperature_c="hot",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "temperature" in reason.lower()

    def test_invalid_temperature_range_low(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            temperature_c=-50,
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "temperature" in reason.lower()

    def test_invalid_temperature_range_high(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            temperature_c=90,
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "temperature" in reason.lower()

    def test_invalid_humidity_type(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            humidity_percent="wet",
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "humidity" in reason.lower()

    def test_invalid_humidity_range_low(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            humidity_percent=-10,
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "humidity" in reason.lower()

    def test_invalid_humidity_range_high(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            humidity_percent=110,
        )
        valid, reason = protocol.validate(packet)
        assert valid is False
        assert "humidity" in reason.lower()

    def test_valid_boundary_temperature(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            temperature_c=-40,
            humidity_percent=0,
        )
        valid, reason = protocol.validate(packet)
        assert valid is True

    def test_valid_boundary_humidity(self):
        packet = Packet(
            version=1,
            packet_type="STATUS",
            origin="NODE_001",
            sender="NODE_001",
            temperature_c=80,
            humidity_percent=100,
        )
        valid, reason = protocol.validate(packet)
        assert valid is True


# ============================================================
# NODEINFO SENSOR TESTS
# ============================================================


class TestNodeInfoSensors:

    def test_nodeinfo_updated_with_temperature(self):
        from models import NodeInfo
        from network import packets
        from state import state

        node = NodeInfo(
            name="NODE_001",
            address="AA:BB:CC:DD:EE:FF",
        )
        state.nodes["NODE_001"] = node

        pkt_data = SAMPLE_STATUS_WITH_SENSORS.copy()
        packet = protocol.decode(
            json.dumps(pkt_data).encode("utf-8")
        )

        packets._update_node(packet)

        assert node.temperature_c == 27.4

    def test_nodeinfo_updated_with_humidity(self):
        from models import NodeInfo
        from network import packets
        from state import state

        node = NodeInfo(
            name="NODE_001",
            address="AA:BB:CC:DD:EE:FF",
        )
        state.nodes["NODE_001"] = node

        pkt_data = SAMPLE_STATUS_WITH_SENSORS.copy()
        packet = protocol.decode(
            json.dumps(pkt_data).encode("utf-8")
        )

        packets._update_node(packet)

        assert node.humidity_percent == 61.0

    def test_missing_sensors_do_not_erase_existing(self):
        from models import NodeInfo
        from network import packets
        from state import state

        node = NodeInfo(
            name="NODE_001",
            address="AA:BB:CC:DD:EE:FF",
            temperature_c=25.0,
            humidity_percent=55.0,
        )
        state.nodes["NODE_001"] = node

        pkt_data = SAMPLE_STATUS.copy()
        packet = protocol.decode(
            json.dumps(pkt_data).encode("utf-8")
        )

        packets._update_node(packet)

        assert node.temperature_c == 25.0
        assert node.humidity_percent == 55.0

    def test_sos_packets_continue_working(self):
        from models import NodeInfo
        from state import state

        node = NodeInfo(
            name="NODE_003",
            address="AA:BB:CC:DD:EE:FF",
            temperature_c=20.0,
            humidity_percent=40.0,
        )
        state.nodes["NODE_003"] = node

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)

        assert packet is not None
        assert packet.packet_type == "SOS"
        assert packet.temperature_c is None
        assert packet.humidity_percent is None

    def test_duplicate_detection_with_sensors(self):
        from network import packets
        from state import state

        state.last_packet_ids.clear()

        pkt1_data = SAMPLE_STATUS_WITH_SENSORS.copy()
        packet1 = protocol.decode(
            json.dumps(pkt1_data).encode("utf-8")
        )

        pkt2_data = SAMPLE_STATUS_WITH_SENSORS.copy()
        packet2 = protocol.decode(
            json.dumps(pkt2_data).encode("utf-8")
        )

        pid1 = protocol.packet_id(packet1)
        pid2 = protocol.packet_id(packet2)

        assert pid1 == pid2


# ============================================================
# SOS ALERT TESTS
# ============================================================


class TestSOSAlerts:

    def _reset_state(self):
        from state import state
        state.last_packet_ids.clear()
        state.active_alerts.clear()
        state.events.clear()
        state.nodes.clear()

    def test_sos_creates_persistent_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)

        packets.process_packet(packet)

        assert len(state.active_alerts) == 1

        pid = protocol.packet_id(packet)
        alert = state.active_alerts.get(pid)

        assert alert is not None
        assert alert.alert_type == "SOS"
        assert alert.node_id == "NODE_003"

    def test_heartbeat_does_not_remove_sos_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        sos_packet = protocol.decode(raw)
        packets.process_packet(sos_packet)

        sos_pid = protocol.packet_id(sos_packet)

        state.last_packet_ids.discard(
            protocol.packet_id(
                protocol.decode(
                    json.dumps(SAMPLE_STATUS).encode("utf-8")
                )
            )
        )

        raw_status = json.dumps(SAMPLE_STATUS).encode("utf-8")
        status_packet = protocol.decode(raw_status)
        packets.process_packet(status_packet)

        assert sos_pid in state.active_alerts
        assert len(state.active_alerts) == 1

    def test_status_does_not_remove_sos_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        sos_packet = protocol.decode(raw)
        packets.process_packet(sos_packet)

        sos_pid = protocol.packet_id(sos_packet)

        state.last_packet_ids.clear()

        raw_status = json.dumps(SAMPLE_STATUS).encode("utf-8")
        status_packet = protocol.decode(raw_status)
        packets.process_packet(status_packet)

        assert sos_pid in state.active_alerts

    def test_acknowledge_removes_alert(self):
        self._reset_state()
        from network import packets
        from state import state, acknowledge_alert

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        pid = protocol.packet_id(packet)

        assert pid in state.active_alerts

        result = acknowledge_alert(pid)

        assert result is True
        assert pid not in state.active_alerts

    def test_historical_event_remains_after_ack(self):
        self._reset_state()
        from network import packets
        from state import state, acknowledge_alert

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        pid = protocol.packet_id(packet)

        initial_events = len(state.events)

        acknowledge_alert(pid)

        assert len(state.events) == initial_events

        sos_events = [
            e for e in state.events
            if "SOS" in e.message
        ]

        assert len(sos_events) > 0

    def test_multiple_sos_alerts_coexist(self):
        self._reset_state()
        from network import packets
        from state import state

        sos1 = {
            "v": 1,
            "type": "SOS",
            "origin": "NODE_001",
            "sender": "NODE_001",
            "seq": 1,
            "priority": 3,
            "ttl": 10,
            "hops": 0,
            "time_ms": 1000,
        }

        sos2 = {
            "v": 1,
            "type": "SOS",
            "origin": "NODE_002",
            "sender": "NODE_002",
            "seq": 1,
            "priority": 3,
            "ttl": 10,
            "hops": 0,
            "time_ms": 2000,
        }

        packet1 = protocol.decode(
            json.dumps(sos1).encode("utf-8")
        )
        packets.process_packet(packet1)

        packet2 = protocol.decode(
            json.dumps(sos2).encode("utf-8")
        )
        packets.process_packet(packet2)

        assert len(state.active_alerts) == 2

    def test_duplicate_sos_does_not_create_duplicate_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)

        packets.process_packet(packet)

        initial_count = len(state.active_alerts)

        state.last_packet_ids.discard(
            protocol.packet_id(packet)
        )

        packets.process_packet(packet)

        assert len(state.active_alerts) == initial_count

    def test_alert_id_uses_packet_id(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        expected_id = protocol.packet_id(packet)

        assert expected_id in state.active_alerts

    def test_normal_heartbeat_does_not_become_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_STATUS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        assert len(state.active_alerts) == 0

    def test_acknowledge_nonexistent_returns_false(self):
        self._reset_state()
        from state import acknowledge_alert

        result = acknowledge_alert("nonexistent:id")

        assert result is False

    def test_sos_event_still_in_recent_events(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        sos_events = [
            e for e in state.events
            if "SOS" in e.message
        ]

        assert len(sos_events) == 1
        assert sos_events[0].level == "SOS"

    def test_acknowledge_only_removes_one_alert(self):
        self._reset_state()
        from network import packets
        from state import state, acknowledge_alert

        sos1 = {
            "v": 1,
            "type": "SOS",
            "origin": "NODE_001",
            "sender": "NODE_001",
            "seq": 1,
            "priority": 3,
            "ttl": 10,
            "hops": 0,
            "time_ms": 1000,
        }

        sos2 = {
            "v": 1,
            "type": "SOS",
            "origin": "NODE_002",
            "sender": "NODE_002",
            "seq": 1,
            "priority": 3,
            "ttl": 10,
            "hops": 0,
            "time_ms": 2000,
        }

        packet1 = protocol.decode(
            json.dumps(sos1).encode("utf-8")
        )
        packets.process_packet(packet1)

        packet2 = protocol.decode(
            json.dumps(sos2).encode("utf-8")
        )
        packets.process_packet(packet2)

        assert len(state.active_alerts) == 2

        pid1 = protocol.packet_id(packet1)

        acknowledge_alert(pid1)

        assert len(state.active_alerts) == 1

        pid2 = protocol.packet_id(packet2)

        assert pid2 in state.active_alerts


# ============================================================
# PERSISTENCE LIFECYCLE TESTS
# ============================================================


class TestAlertPersistenceLifecycle:

    def _reset_state(self):
        from state import state
        state.events.clear()
        state.packets.clear()
        state.nodes.clear()
        state.active_alerts.clear()
        state.last_packet_ids.clear()
        state.selected_node = None

    def test_sos_persists_through_heartbeats(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        assert len(state.active_alerts) == 1

        for i in range(5):
            heartbeat = {
                "v": 1,
                "type": "STATUS",
                "origin": "NODE_001",
                "sender": "NODE_001",
                "seq": 100 + i,
                "priority": 0,
                "ttl": 10,
                "hops": 0,
                "time_ms": 5000 + (i * 5000),
            }
            hb_packet = protocol.decode(
                json.dumps(heartbeat).encode("utf-8")
            )
            packets.process_packet(hb_packet)

            assert len(state.active_alerts) == 1, (
                f"Alert lost after heartbeat {i}"
            )

    def test_sos_acknowledge_clears_alert(self):
        self._reset_state()
        from network import packets
        from state import state, acknowledge_alert

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        assert len(state.active_alerts) == 1

        pid = protocol.packet_id(packet)
        result = acknowledge_alert(pid)

        assert result is True
        assert len(state.active_alerts) == 0

    def test_sos_event_persists_after_acknowledge(self):
        self._reset_state()
        from network import packets
        from state import state, acknowledge_alert

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packet = protocol.decode(raw)
        packets.process_packet(packet)

        pid = protocol.packet_id(packet)
        acknowledge_alert(pid)

        assert len(state.active_alerts) == 0

        sos_events = [
            e for e in state.events
            if "SOS" in e.message
        ]
        assert len(sos_events) >= 1

    def test_handle_packet_sos_creates_alert(self):
        self._reset_state()
        from network import packets
        from state import state

        raw = json.dumps(SAMPLE_SOS).encode("utf-8")
        packets.handle_packet("BLE_DEVICE", raw)

        assert len(state.active_alerts) == 1

    def test_handle_packet_exception_is_isolated(self):
        self._reset_state()
        from network import packets
        from state import state

        packets.handle_packet(
            "BLE_DEVICE",
            b"not valid json at all"
        )

        assert len(state.active_alerts) == 0
