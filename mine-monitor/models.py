from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Alert:

    alert_id: str

    alert_type: str

    node_id: str

    timestamp: str

    priority: int

    packet: object


@dataclass
class NodeInfo:

    name: str

    address: str

    rssi: int = 0

    status: str = "DISCOVERED"

    last_seen: float = 0

    last_heartbeat: float = 0

    last_sequence: int = -1

    packets_received: int = 0

    temperature_c: Optional[float] = None

    humidity_percent: Optional[float] = None


@dataclass
class Packet:

    version: int = 1

    packet_type: str = "UNKNOWN"

    origin: str = "UNKNOWN"

    sender: str = "UNKNOWN"

    sequence: int = -1

    priority: int = 0

    ttl: int = 0

    hops: int = 0

    time_ms: int = 0

    temperature_c: Optional[float] = None

    humidity_percent: Optional[float] = None


@dataclass
class Event:

    timestamp: str

    level: str

    message: str


@dataclass
class ApplicationState:

    running: bool = True

    scanning: bool = False

    connected: bool = False

    connecting: bool = False

    selected_node: Optional[str] = None

    connected_node: Optional[str] = None

    client: object = None

    message: str = "Starting monitor..."

    nodes: dict = field(
        default_factory=dict
    )

    events: list = field(
        default_factory=list
    )

    packets: list = field(
        default_factory=list
    )

    last_packet_ids: set = field(
        default_factory=set
    )

    active_alerts: dict = field(
        default_factory=dict
    )
