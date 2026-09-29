import curses
import time

from config import (
    MIN_TERMINAL_WIDTH,
    MIN_TERMINAL_HEIGHT,
)

from state import state, get_active_alerts


# ============================================================
# COLORS
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

    curses.init_pair(
        6,
        curses.COLOR_WHITE,
        curses.COLOR_RED
    )

    curses.init_pair(
        7,
        curses.COLOR_YELLOW,
        curses.COLOR_RED
    )


# ============================================================
# SAFE TEXT
# ============================================================

def put(
    win,
    y,
    x,
    text,
    attr=0
):

    try:

        height, width = win.getmaxyx()


        if y < 0 or y >= height:

            return


        if x < 0 or x >= width:

            return


        available = (
            width - x - 1
        )


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
# BOX
# ============================================================

def draw_box(
    win,
    y,
    x,
    height,
    width,
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
            x + width - 1,
            curses.ACS_URCORNER
        )

        win.addch(
            y + height - 1,
            x,
            curses.ACS_LLCORNER
        )

        win.addch(
            y + height - 1,
            x + width - 1,
            curses.ACS_LRCORNER
        )


        for i in range(
            x + 1,
            x + width - 1
        ):

            win.addch(
                y,
                i,
                curses.ACS_HLINE
            )

            win.addch(
                y + height - 1,
                i,
                curses.ACS_HLINE
            )


        for i in range(
            y + 1,
            y + height - 1
        ):

            win.addch(
                i,
                x,
                curses.ACS_VLINE
            )

            win.addch(
                i,
                x + width - 1,
                curses.ACS_VLINE
            )


        if title:

            put(
                win,
                y,
                x + 2,
                f" {title} ",
                curses.A_BOLD
            )


    except curses.error:

        pass


# ============================================================
# HEADER
# ============================================================

def draw_header(stdscr):

    height, width = stdscr.getmaxyx()


    put(
        stdscr,
        0,
        2,
        "UNDERGROUND MINE MONITOR",
        curses.A_BOLD
    )


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
        max(35, width - 20),
        status,
        attr
    )


    put(
        stdscr,
        1,
        2,
        "Gateway: Mobile Linux Gateway"
    )


    put(
        stdscr,
        1,
        max(35, width - 25),
        "Transport: BLE"
    )


# ============================================================
# NODE LIST
# ============================================================

def draw_nodes(
    stdscr,
    y,
    x,
    height,
    width
):

    draw_box(
        stdscr,
        y,
        x,
        height,
        width,
        "MINE NODES"
    )


    nodes = list(
        state.nodes.values()
    )


    nodes.sort(
        key=lambda node: node.rssi,
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
        nodes
    ):

        row = y + 1 + index


        if row >= y + height - 1:

            break


        selected = (
            node.name
            == state.selected_node
        )


        if (
            node.name
            == state.connected_node
        ):

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


        put(
            stdscr,
            row,
            x + width - 13,
            node.status[:10]
        )


# ============================================================
# SELECTED NODE
# ============================================================

def draw_selected(
    stdscr,
    y,
    x,
    height,
    width
):

    draw_box(
        stdscr,
        y,
        x,
        height,
        width,
        "SELECTED NODE"
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
        "Status     :"
    )


    if node.name == state.connected_node:

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


    if node.last_heartbeat:

        age = int(
            time.time()
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


    if node.temperature_c is not None:

        temp = f"{node.temperature_c:.1f} C"

    else:

        temp = "--"


    put(
        stdscr,
        y + 9,
        x + 2,
        f"Temperature: {temp}"
    )


    if node.humidity_percent is not None:

        hum = f"{node.humidity_percent:.1f} %"

    else:

        hum = "--"


    put(
        stdscr,
        y + 10,
        x + 2,
        f"Humidity   : {hum}"
    )


# ============================================================
# NETWORK STATUS
# ============================================================

def draw_network_status(
    stdscr,
    y,
    x,
    height,
    width
):

    draw_box(
        stdscr,
        y,
        x,
        height,
        width,
        "NETWORK STATUS"
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
        "Connected        : "
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
# EVENTS
# ============================================================

def draw_events(
    stdscr,
    y,
    x,
    height,
    width
):

    draw_box(
        stdscr,
        y,
        x,
        height,
        width,
        "RECENT EVENTS"
    )


    for index, event in enumerate(
        state.events
    ):

        row = y + 1 + index


        if row >= y + height - 1:

            break


        if event.level == "SOS":

            attr = (
                curses.color_pair(2)
                | curses.A_BOLD
            )

        elif event.level == "ERROR":

            attr = curses.color_pair(2)

        elif event.level == "WARNING":

            attr = curses.color_pair(3)

        elif event.level == "CONNECT":

            attr = curses.color_pair(1)

        else:

            attr = curses.color_pair(5)


        put(
            stdscr,
            row,
            x + 2,
            f"{event.timestamp} "
            f"{event.message}",
            attr
        )


# ============================================================
# FOOTER
# ============================================================

def draw_footer(
    stdscr
):

    height, width = stdscr.getmaxyx()


    if state.active_alerts:

        put(
            stdscr,
            height - 2,
            2,
            "↑↓ Select Node   R Rescan   "
            "A Acknowledge   Q Quit",
            curses.A_BOLD
        )

    else:

        put(
            stdscr,
            height - 2,
            2,
            "↑↓ Select Node   R Rescan   Q Quit",
            curses.A_BOLD
        )


    put(
        stdscr,
        height - 1,
        2,
        "Underground Mine Safety Mesh"
    )


# ============================================================
# EMERGENCY OVERLAY
# ============================================================

def draw_emergency_overlay(
    stdscr
):

    alerts = get_active_alerts()

    if not alerts:

        return


    current = alerts[0]

    height, width = stdscr.getmaxyx()


    popup_height = min(15, height - 2)
    popup_width = min(52, width - 4)


    start_y = max(
        0,
        (height - popup_height) // 2
    )
    start_x = max(
        0,
        (width - popup_width) // 2
    )


    try:

        win = curses.newwin(
            popup_height,
            popup_width,
            start_y,
            start_x
        )

    except curses.error:

        return


    win.erase()


    border_attr = (
        curses.color_pair(6)
        | curses.A_BOLD
    )

    try:

        win.attron(border_attr)

        win.border()

        win.attroff(border_attr)

    except curses.error:

        pass


    title = "!!! EMERGENCY !!!"

    title_x = max(
        1,
        (popup_width - len(title)) // 2
    )

    put(
        win,
        2,
        title_x,
        title,
        curses.color_pair(6)
        | curses.A_BOLD
    )


    subtitle = "SOS ALERT"

    sub_x = max(
        1,
        (popup_width - len(subtitle)) // 2
    )

    put(
        win,
        4,
        sub_x,
        subtitle,
        curses.color_pair(7)
        | curses.A_BOLD
    )


    put(
        win,
        6,
        4,
        f"NODE: {current.node_id}",
        curses.color_pair(6)
        | curses.A_BOLD
    )


    put(
        win,
        7,
        4,
        f"TIME: {current.timestamp}",
        curses.color_pair(6)
    )


    message = "EMERGENCY SIGNAL RECEIVED"

    msg_x = max(
        1,
        (popup_width - len(message)) // 2
    )

    put(
        win,
        9,
        msg_x,
        message,
        curses.color_pair(6)
        | curses.A_BOLD
    )


    if len(alerts) > 1:

        count_text = (
            f"ACTIVE ALERTS: {len(alerts)}"
        )

        count_x = max(
            1,
            (popup_width - len(count_text)) // 2
        )

        put(
            win,
            11,
            count_x,
            count_text,
            curses.color_pair(7)
            | curses.A_BOLD
        )


    ack_text = "[ A ] ACKNOWLEDGE"

    ack_x = max(
        1,
        (popup_width - len(ack_text)) // 2
    )

    put(
        win,
        popup_height - 2,
        ack_x,
        ack_text,
        curses.color_pair(7)
        | curses.A_BOLD
    )


    try:

        win.noutrefresh()

    except curses.error:

        pass


# ============================================================
# COMPLETE SCREEN
# ============================================================

def draw_screen(
    stdscr
):

    stdscr.erase()


    height, width = (
        stdscr.getmaxyx()
    )


    if (
        width < MIN_TERMINAL_WIDTH
        or
        height < MIN_TERMINAL_HEIGHT
    ):

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
            f"Minimum: "
            f"{MIN_TERMINAL_WIDTH}x"
            f"{MIN_TERMINAL_HEIGHT}"
        )

        stdscr.refresh()

        return


    draw_header(
        stdscr
    )


    top = 3

    usable_height = (
        height - 6
    )


    left_width = (
        width // 2
    )

    right_width = (
        width - left_width
    )


    nodes_height = (
        usable_height // 2
    )


    status_height = (
        usable_height
        - nodes_height
    )


    selected_height = (
        usable_height // 2
    )


    events_height = (
        usable_height
        - selected_height
    )


    # Left

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


    # Right

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


    stdscr.noutrefresh()


    draw_emergency_overlay(
        stdscr
    )


    curses.doupdate()
