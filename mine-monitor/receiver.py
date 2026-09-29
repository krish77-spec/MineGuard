import asyncio
import curses
import json
import time
from dataclasses import dataclass, field
from datetime import datetime

from bleak import BleakScanner, BleakClient


# ============================================================
# CONFIGURATION
# ============================================================

SERVICE_UUID = (
    "12345678-1234-5678-1234-56789abcdef0"
)

PACKET_UUID = (
    "12345678-1234-5678-1234-56789abcdef1"
)

SCAN_TIME = 5
RECONNECT_DELAY = 2


# ============================================================
# TUI CONSTANTS
# ============================================================

MAX_EVENTS = 12
MAX_PACKETS = 8
MAX_NODES = 20


# ============================================================
# NODE INFORMATION
# ============================================================

@dataclass
class NodeInfo:

    name: str
    address: str
    rssi: int = 0

    status: str = "DISCOVERED"

    last_seen: float = field(
        default_factory=time.time
    )

    last_heartbeat: float = 0

    last_sequence: int = -1

    packets_received: int = 0


# ============================================================
# APPLICATION STATE
# ============================================================

class MonitorState:

    def __init__(self):

        self.running = True

        self.scanning = False

        self.connected = False

        self.connecting = False

        self.selected_node = None

        self.connected_node = None

        self.client = None

        self.nodes = {}

        self.events = []

        self.packets = []

        self.last_packet_ids = set()

        self.message = "Starting monitor..."

        self.message_time = time.time()

        self.lock = asyncio.Lock()


    # ========================================================
    # EVENT LOG
    # ========================================================

    def add_event(
        self,
        message,
        level="INFO"
    ):

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.events.insert(
            0,
            (
                timestamp,
                level,
                message
            )
        )

        self.events = self.events[:MAX_EVENTS]


    # ========================================================
    # PACKET LOG
    # ========================================================

    def add_packet(
        self,
        packet
    ):

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.packets.insert(
            0,
            (
                timestamp,
                packet
            )
        )

        self.packets = self.packets[:MAX_PACKETS]


# ============================================================
# GLOBAL STATE
# ============================================================

state = MonitorState()


# ============================================================
# HELPER
# ============================================================

def now():
    return time.time()


# ============================================================
# PACKET HANDLER
# ============================================================

def handle_packet(sender, data):

    try:

        packet_text = data.decode(
            "utf-8",
            errors="replace"
        )

        packet = json.loads(packet_text)

    except Exception as e:

        state.add_event(
            f"Invalid packet: {e}",
            "ERROR"
        )

        return


    # ========================================================
    # EXTRACT
    # ========================================================

    version = packet.get("v", "?")

    packet_type = packet.get(
        "type",
        "UNKNOWN"
    )

    origin = packet.get(
        "origin",
        "UNKNOWN"
    )

    packet_sender = packet.get(
        "sender",
        "UNKNOWN"
    )

    sequence = packet.get(
        "seq",
        -1
    )

    priority = packet.get(
        "priority",
        0
    )

    ttl = packet.get(
        "ttl",
        0
    )

    hops = packet.get(
        "hops",
        0
    )

    time_ms = packet.get(
        "time_ms",
        0
    )


    # ========================================================
    # DUPLICATE DETECTION
    #
    # Include node time so a node rebooting and resetting
    # its sequence number does not permanently get ignored.
    # ========================================================

    packet_id = (
        f"{origin}:"
        f"{sequence}:"
        f"{time_ms}"
    )


    if packet_id in state.last_packet_ids:

        return


    state.last_packet_ids.add(
        packet_id
    )


    # Prevent unlimited memory usage

    if len(state.last_packet_ids) > 1000:

        state.last_packet_ids = set(
            list(state.last_packet_ids)[-500:]
        )


    # ========================================================
    # UPDATE NODE INFORMATION
    # ========================================================

    if origin in state.nodes:

        node = state.nodes[origin]

        node.last_seen = now()

        node.last_sequence = sequence

        node.packets_received += 1

        if packet_type == "STATUS":

            node.last_heartbeat = now()


    # ========================================================
    # SAVE PACKET
    # ========================================================

    state.add_packet(
        {
            "type": packet_type,
            "origin": origin,
            "sender": packet_sender,
            "seq": sequence,
            "priority": priority,
            "ttl": ttl,
            "hops": hops,
            "time_ms": time_ms
        }
    )


    # ========================================================
    # EVENTS
    # ========================================================

    if packet_type == "SOS":

        state.add_event(
            f"🚨 SOS from {origin}",
            "SOS"
        )

    elif packet_type == "STATUS":

        state.add_event(
            f"Heartbeat from {origin}",
            "INFO"
        )

    else:

        state.add_event(
            f"{packet_type} from {origin}",
            "INFO"
        )


# ============================================================
# SCAN FOR ANY MINE NODE
# ============================================================

async def scan_nodes():

    state.scanning = True

    state.message = "Scanning for mine nodes..."

    state.add_event(
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
            # Only accept our Mine Safety Mesh service
            # ----------------------------------------------

            if SERVICE_UUID.lower() not in services:

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
                status="AVAILABLE"
            )


            # Preserve previous information

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


        # ----------------------------------------------------
        # Update node list
        # ----------------------------------------------------

        state.nodes.update(
            discovered
        )


        # ----------------------------------------------------
        # Remove nodes that haven't been seen recently
        # ----------------------------------------------------

        cutoff = now() - 30

        for name in list(state.nodes):

            node = state.nodes[name]

            if node.last_seen < cutoff:

                if (
                    name != state.connected_node
                ):

                    del state.nodes[name]


        # ----------------------------------------------------
        # Select strongest node if nothing selected
        # ----------------------------------------------------

        if discovered:

            if (
                state.selected_node is None
                or state.selected_node not in state.nodes
            ):

                best = max(
                    discovered.values(),
                    key=lambda n: n.rssi
                )

                state.selected_node = best.name


            state.message = (
                f"{len(discovered)} mine node(s) found"
            )


        else:

            state.message = (
                "No mine nodes detected"
            )


    except Exception as e:

        state.message = (
            f"Scan error: {e}"
        )

        state.add_event(
            f"Scan error: {e}",
            "ERROR"
        )


    finally:

        state.scanning = False


# ============================================================
# CONNECT TO SELECTED NODE
# ============================================================

async def connect_to_selected():

    if not state.selected_node:

        return


    if state.connected:

        return


    if state.connecting:

        return


    node = state.nodes.get(
        state.selected_node
    )


    if node is None:

        return


    state.connecting = True

    state.message = (
        f"Connecting to {node.name}..."
    )


    state.add_event(
        f"Connecting to {node.name}",
        "CONNECT"
    )


    client = BleakClient(
        node.address,
        disconnected_callback=
        disconnected_callback
    )


    try:

        await client.connect()


        if not client.is_connected:

            raise RuntimeError(
                "BLE connection failed"
            )


        state.client = client

        state.connected = True

        state.connected_node = node.name

        node.status = "ONLINE"

        state.message = (
            f"Connected to {node.name}"
        )


        state.add_event(
            f"{node.name} connected",
            "CONNECT"
        )


        await client.start_notify(
            PACKET_UUID,
            handle_packet
        )


        state.add_event(
            f"{node.name} packet notifications active",
            "INFO"
        )


        # ----------------------------------------------------
        # Keep connection alive
        # ----------------------------------------------------

        while (
            state.running
            and client.is_connected
        ):

            await asyncio.sleep(
                0.5
            )


    except asyncio.CancelledError:

        raise


    except Exception as e:

        state.message = (
            f"Connection failed: {e}"
        )

        state.add_event(
            f"Connection error: {e}",
            "ERROR"
        )


    finally:

        state.connected = False

        state.connecting = False

        state.connected_node = None

        state.client = None


        try:

            if client.is_connected:

                await client.disconnect()

        except Exception:

            pass


# ============================================================
# DISCONNECTED CALLBACK
# ============================================================

def disconnected_callback(client):

    state.connected = False

    state.connected_node = None

    state.client = None

    state.add_event(
        "Mine node disconnected",
        "WARNING"
    )

    state.message = (
        "Node disconnected - searching..."
    )


# ============================================================
# BACKGROUND NETWORK TASK
# ============================================================

async def network_manager():

    while state.running:

        try:

            # ------------------------------------------------
            # If connected, just wait
            # ------------------------------------------------

            if state.connected:

                await asyncio.sleep(
                    1
                )

                continue


            # ------------------------------------------------
            # Scan
            # ------------------------------------------------

            await scan_nodes()


            # ------------------------------------------------
            # Connect to best node
            # ------------------------------------------------

            if (
                not state.connected
                and state.selected_node
            ):

                await connect_to_selected()


            await asyncio.sleep(
                RECONNECT_DELAY
            )


        except asyncio.CancelledError:

            break


        except Exception as e:

            state.add_event(
                f"Network manager error: {e}",
                "ERROR"
            )

            await asyncio.sleep(
                RECONNECT_DELAY
            )


# ============================================================
# TUI COLORS
# ============================================================

def setup_colors():

    if not curses.has_colors():

        return


    curses.start_color()

    curses.use_default_colors()


    curses.init_pair(
        1,
        curses.COLOR_GREEN,
        -1
    )

    curses.init_pair(
        2,
        curses.COLOR_RED,
        -1
    )

    curses.init_pair(
        3,
        curses.COLOR_YELLOW,
        -1
    )

    curses.init_pair(
        4,
        curses.COLOR_CYAN,
        -1
    )

    curses.init_pair(
        5,
        curses.COLOR_WHITE,
        -1
    )


# ============================================================
# SAFE ADD STRING
# ============================================================

def put(
    win,
    y,
    x,
    text,
    attr=0
):

    try:

        max_y, max_x = win.getmaxyx()

        if y < 0 or y >= max_y:

            return


        if x < 0 or x >= max_x:

            return


        available = max_x - x - 1

        if available <= 0:

            return


        win.addnstr(
            y,
            x,
            text,
            available,
            attr
        )

    except curses.error:

        pass


# ============================================================
# DRAW BOX
# ============================================================

def draw_box(
    win,
    y,
    x,
    h,
    w,
    title=""
):

    try:

        win.addch(
            y,
            x,
            curses.ACS_ULCORNER
        )

        win.addch(
            y,
            x + w - 1,
            curses.ACS_URCORNER
        )

        win.addch(
            y + h - 1,
            x,
            curses.ACS_LLCORNER
        )

        win.addch(
            y + h - 1,
            x + w - 1,
            curses.ACS_LRCORNER
        )


        for i in range(
            x + 1,
            x + w - 1
        ):

            win.addch(
                y,
                i,
                curses.ACS_HLINE
            )

            win.addch(
                y + h - 1,
                i,
                curses.ACS_HLINE
            )


        for i in range(
            y + 1,
            y + h - 1
        ):

            win.addch(
                i,
                x,
                curses.ACS_VLINE
            )

            win.addch(
                i,
                x + w - 1,
                curses.ACS_VLINE
            )


        if title:

            put(
                win,
                y,
                x + 2,
                f" {title} "
            )


    except curses.error:

        pass


# ============================================================
# DRAW HEADER
# ============================================================

def draw_header(stdscr):

    height, width = stdscr.getmaxyx()


    title = (
        " UNDERGROUND MINE MONITOR "
    )


    put(
        stdscr,
        0,
        2,
        title,
        curses.A_BOLD
    )


    # Gateway status

    if state.connected:

        status = "● ONLINE"

        attr = (
            curses.color_pair(1)
            | curses.A_BOLD
        )

    elif state.connecting:

        status = "◐ CONNECTING"

        attr = (
            curses.color_pair(3)
            | curses.A_BOLD
        )

    else:

        status = "○ SEARCHING"

        attr = (
            curses.color_pair(3)
            | curses.A_BOLD
        )


    put(
        stdscr,
        0,
        max(35, width - 22),
        status,
        attr
    )


    put(
        stdscr,
        1,
        2,
        "Gateway: Raspberry Pi / Linux"
    )

    put(
        stdscr,
        1,
        max(35, width - 28),
        "Transport: BLE"
    )


# ============================================================
# DRAW NODE LIST
# ============================================================

def draw_nodes(
    stdscr,
    y,
    x,
    h,
    w
):

    draw_box(
        stdscr,
        y,
        x,
        h,
        w,
        " MINE NODES "
    )


    nodes = list(
        state.nodes.values()
    )


    nodes.sort(
        key=lambda n: n.rssi,
        reverse=True
    )


    if not nodes:

        put(
            stdscr,
            y + 2,
            x + 2,
            "No mine nodes discovered."
        )

        return


    for index, node in enumerate(
        nodes[:MAX_NODES]
    ):

        row = y + 1 + index


        if row >= y + h - 1:

            break


        selected = (
            node.name
            == state.selected_node
        )


        if node.name == state.connected_node:

            symbol = "●"

            attr = (
                curses.color_pair(1)
                | curses.A_BOLD
            )

        else:

            symbol = "○"

            attr = curses.color_pair(4)


        if selected:

            attr |= curses.A_REVERSE


        text = (
            f"{symbol} "
            f"{node.name:<12} "
            f"{node.rssi:>4} dBm"
        )


        put(
            stdscr,
            row,
            x + 2,
            text,
            attr
        )


        status = node.status

        if (
            node.name
            == state.connected_node
        ):

            status = "ONLINE"


        put(
            stdscr,
            row,
            x + w - 13,
            status[:10]
        )


# ============================================================
# DRAW SELECTED NODE
# ============================================================

def draw_selected(
    stdscr,
    y,
    x,
    h,
    w
):

    draw_box(
        stdscr,
        y,
        x,
        h,
        w,
        " SELECTED NODE "
    )


    if not state.selected_node:

        put(
            stdscr,
            y + 2,
            x + 2,
            "No node selected."
        )

        return


    node = state.nodes.get(
        state.selected_node
    )


    if not node:

        return


    online = (
        node.name
        == state.connected_node
    )


    put(
        stdscr,
        y + 2,
        x + 2,
        f"Node       : {node.name}"
    )


    put(
        stdscr,
        y + 3,
        x + 2,
        f"Address    : {node.address}"
    )


    put(
        stdscr,
        y + 4,
        x + 2,
        f"RSSI       : {node.rssi} dBm"
    )


    put(
        stdscr,
        y + 5,
        x + 2,
        "Status     : "
    )


    if online:

        put(
            stdscr,
            y + 5,
            x + 15,
            "● ONLINE",
            curses.color_pair(1)
            | curses.A_BOLD
        )

    else:

        put(
            stdscr,
            y + 5,
            x + 15,
            "○ AVAILABLE",
            curses.color_pair(3)
        )


    # Last heartbeat

    if node.last_heartbeat:

        age = int(
            now()
            - node.last_heartbeat
        )

        heartbeat = f"{age}s ago"

    else:

        heartbeat = "Never"


    put(
        stdscr,
        y + 6,
        x + 2,
        f"Heartbeat  : {heartbeat}"
    )


    put(
        stdscr,
        y + 7,
        x + 2,
        f"Last Seq   : {node.last_sequence}"
    )


    put(
        stdscr,
        y + 8,
        x + 2,
        f"Packets    : {node.packets_received}"
    )


# ============================================================
# DRAW NETWORK STATUS
# ============================================================

def draw_network_status(
    stdscr,
    y,
    x,
    h,
    w
):

    draw_box(
        stdscr,
        y,
        x,
        h,
        w,
        " NETWORK STATUS "
    )


    online_count = sum(
        1
        for node in state.nodes.values()
        if node.name == state.connected_node
    )


    put(
        stdscr,
        y + 2,
        x + 2,
        f"Nodes discovered : {len(state.nodes)}"
    )


    put(
        stdscr,
        y + 3,
        x + 2,
        f"Connected        : "
        f"{state.connected_node or 'NONE'}"
    )


    if state.connected:

        network_status = "ONLINE"

        attr = (
            curses.color_pair(1)
            | curses.A_BOLD
        )

    elif state.scanning:

        network_status = "SEARCHING"

        attr = (
            curses.color_pair(3)
            | curses.A_BOLD
        )

    else:

        network_status = "OFFLINE"

        attr = (
            curses.color_pair(2)
            | curses.A_BOLD
        )


    put(
        stdscr,
        y + 4,
        x + 2,
        "Network          :"
    )

    put(
        stdscr,
        y + 4,
        x + 20,
        network_status,
        attr
    )


    put(
        stdscr,
        y + 5,
        x + 2,
        f"Last action      : {state.message}"
    )


# ============================================================
# DRAW EVENTS
# ============================================================

def draw_events(
    stdscr,
    y,
    x,
    h,
    w
):

    draw_box(
        stdscr,
        y,
        x,
        h,
        w,
        " RECENT EVENTS "
    )


    events = state.events


    for index, event in enumerate(
        events[:h - 2]
    ):

        row = y + 1 + index

        timestamp, level, message = event


        if level == "SOS":

            attr = (
                curses.color_pair(2)
                | curses.A_BOLD
            )

        elif level == "ERROR":

            attr = curses.color_pair(2)

        elif level == "WARNING":

            attr = curses.color_pair(3)

        elif level == "CONNECT":

            attr = curses.color_pair(1)

        else:

            attr = curses.color_pair(5)


        text = (
            f"{timestamp}  {message}"
        )


        put(
            stdscr,
            row,
            x + 2,
            text,
            attr
        )


# ============================================================
# DRAW PACKETS
# ============================================================

def draw_packets(
    stdscr,
    y,
    x,
    h,
    w
):

    draw_box(
        stdscr,
        y,
        x,
        h,
        w,
        " RECENT PACKETS "
    )


    for index, item in enumerate(
        state.packets[:h - 2]
    ):

        row = y + 1 + index

        timestamp, packet = item


        packet_type = packet["type"]

        origin = packet["origin"]

        sequence = packet["seq"]

        hops = packet["hops"]


        if packet_type == "SOS":

            attr = (
                curses.color_pair(2)
                | curses.A_BOLD
            )

        elif packet_type == "STATUS":

            attr = curses.color_pair(4)

        else:

            attr = curses.color_pair(5)


        text = (
            f"{timestamp} "
            f"{packet_type:<7} "
            f"{origin:<10} "
            f"SEQ:{sequence:<4} "
            f"H:{hops}"
        )


        put(
            stdscr,
            row,
            x + 2,
            text,
            attr
        )


# ============================================================
# DRAW FOOTER
# ============================================================

def draw_footer(
    stdscr
):

    height, width = stdscr.getmaxyx()


    if height < 5:

        return


    put(
        stdscr,
        height - 2,
        2,
        "↑↓ Select Node    R Rescan    Q Quit",
        curses.A_BOLD
    )


    put(
        stdscr,
        height - 1,
        2,
        "Mine Safety Mesh • Phase 2"
    )


# ============================================================
# MAIN DRAW
# ============================================================

def draw_ui(
    stdscr
):

    stdscr.erase()

    height, width = stdscr.getmaxyx()


    # --------------------------------------------------------
    # Minimum terminal size
    # --------------------------------------------------------

    if width < 80 or height < 24:

        put(
            stdscr,
            1,
            2,
            "Terminal too small."
        )

        put(
            stdscr,
            2,
            2,
            "Minimum recommended size: 80x24"
        )

        stdscr.refresh()

        return


    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    draw_header(
        stdscr
    )


    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------

    top = 3

    bottom = height - 3

    usable_height = bottom - top


    left_width = width // 2

    right_width = width - left_width


    # Left side

    nodes_height = (
        usable_height // 2
    )


    status_height = (
        usable_height
        - nodes_height
    )


    draw_nodes(
        stdscr,
        top,
        0,
        nodes_height,
        left_width
    )


    draw_network_status(
        stdscr,
        top + nodes_height,
        0,
        status_height,
        left_width
    )


    # Right side

    selected_height = (
        usable_height // 2
    )


    events_height = (
        usable_height
        - selected_height
    )


    draw_selected(
        stdscr,
        top,
        left_width,
        selected_height,
        right_width
    )


    draw_events(
        stdscr,
        top + selected_height,
        left_width,
        events_height,
        right_width
    )


    draw_footer(
        stdscr
    )


    stdscr.refresh()


# ============================================================
# USER INPUT
# ============================================================

async def handle_input(
    stdscr
):

    stdscr.nodelay(True)

    stdscr.keypad(True)


    while state.running:

        try:

            key = stdscr.getch()


            # ------------------------------------------------
            # Quit
            # ------------------------------------------------

            if key in (
                ord("q"),
                ord("Q")
            ):

                state.running = False

                break


            # ------------------------------------------------
            # Rescan
            # ------------------------------------------------

            elif key in (
                ord("r"),
                ord("R")
            ):

                if not state.scanning:

                    asyncio.create_task(
                        manual_rescan()
                    )


            # ------------------------------------------------
            # Select next node
            # ------------------------------------------------

            elif key in (
                curses.KEY_DOWN,
                ord("j")
            ):

                select_next_node()


            # ------------------------------------------------
            # Select previous node
            # ------------------------------------------------

            elif key in (
                curses.KEY_UP,
                ord("k")
            ):

                select_previous_node()


        except curses.error:

            pass


        await asyncio.sleep(
            0.1
        )


# ============================================================
# MANUAL RESCAN
# ============================================================

async def manual_rescan():

    if state.scanning:

        return


    await scan_nodes()


    # --------------------------------------------------------
    # If not connected, connect to selected node
    # --------------------------------------------------------

    if (
        not state.connected
        and state.selected_node
    ):

        await connect_to_selected()


# ============================================================
# SELECT NEXT NODE
# ============================================================

def select_next_node():

    names = list(
        state.nodes.keys()
    )


    if not names:

        return


    if state.selected_node not in names:

        state.selected_node = names[0]

        return


    index = names.index(
        state.selected_node
    )


    index += 1

    if index >= len(names):

        index = 0


    state.selected_node = names[index]


# ============================================================
# SELECT PREVIOUS NODE
# ============================================================

def select_previous_node():

    names = list(
        state.nodes.keys()
    )


    if not names:

        return


    if state.selected_node not in names:

        state.selected_node = names[0]

        return


    index = names.index(
        state.selected_node
    )


    index -= 1

    if index < 0:

        index = len(names) - 1


    state.selected_node = names[index]


# ============================================================
# UI LOOP
# ============================================================

async def ui_loop(
    stdscr
):

    setup_colors()


    stdscr.timeout(0)


    # Start network manager

    network_task = asyncio.create_task(
        network_manager()
    )


    input_task = asyncio.create_task(
        handle_input(stdscr)
    )


    try:

        while state.running:

            draw_ui(
                stdscr
            )

            await asyncio.sleep(
                0.1
            )


    finally:

        state.running = False


        network_task.cancel()

        input_task.cancel()


        try:

            await network_task

        except asyncio.CancelledError:

            pass


        try:

            await input_task

        except asyncio.CancelledError:

            pass


# ============================================================
# CURSES ENTRY
# ============================================================

def run_tui():

    curses.wrapper(
        lambda stdscr:
        asyncio.run(
            ui_loop(stdscr)
        )
    )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    try:

        run_tui()

    except KeyboardInterrupt:

        pass

    finally:

        state.running = False
