import asyncio
import curses

from state import state, acknowledge_alert, get_active_alerts

from network import manager


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


def acknowledge_current_alert():
    """
    Acknowledge the highest-priority active alert.
    """

    alerts = get_active_alerts()

    if not alerts:

        return

    current = alerts[0]

    acknowledge_alert(
        current.alert_id
    )


async def manual_rescan():

    await manager.rescan()


# ============================================================
# REMOTE INPUT (actions go to the backend via HTTP)
# ============================================================

async def _remote_fire(func, *args):

    try:

        await asyncio.to_thread(func, *args)

    except Exception:

        pass


async def handle_remote_input(
    stdscr,
    base_url,
):

    from ui.remote import (
        remote_rescan,
        remote_select,
        remote_acknowledge,
    )


    stdscr.nodelay(True)

    stdscr.keypad(True)


    while state.running:

        try:

            key = stdscr.getch()


            # =================================================
            # QUIT
            # =================================================

            if key in (
                ord("q"),
                ord("Q")
            ):

                state.running = False

                break


            # =================================================
            # RESCAN (backend manager.rescan via API)
            # =================================================

            elif key in (
                ord("r"),
                ord("R")
            ):

                if not state.scanning:

                    asyncio.create_task(
                        _remote_fire(
                            remote_rescan,
                            base_url,
                        )
                    )


            # =================================================
            # NEXT NODE (local highlight, then backend select)
            # =================================================

            elif key in (
                curses.KEY_DOWN,
                ord("j")
            ):

                select_next_node()

                if state.selected_node:

                    asyncio.create_task(
                        _remote_fire(
                            remote_select,
                            base_url,
                            state.selected_node,
                        )
                    )


            # =================================================
            # PREVIOUS NODE
            # =================================================

            elif key in (
                curses.KEY_UP,
                ord("k")
            ):

                select_previous_node()

                if state.selected_node:

                    asyncio.create_task(
                        _remote_fire(
                            remote_select,
                            base_url,
                            state.selected_node,
                        )
                    )


            # =================================================
            # ACKNOWLEDGE ALERT (backend logic via API)
            # =================================================

            elif key in (
                ord("a"),
                ord("A")
            ):

                asyncio.create_task(
                    _remote_fire(
                        remote_acknowledge,
                        base_url,
                    )
                )


        except curses.error:

            pass


        await asyncio.sleep(
            0.1
        )


async def handle_input(
    stdscr
):

    stdscr.nodelay(True)

    stdscr.keypad(True)


    while state.running:

        try:

            key = stdscr.getch()


            # =================================================
            # QUIT
            # =================================================

            if key in (
                ord("q"),
                ord("Q")
            ):

                state.running = False

                break


            # =================================================
            # RESCAN
            # =================================================

            elif key in (
                ord("r"),
                ord("R")
            ):

                if not state.scanning:

                    asyncio.create_task(
                        manual_rescan()
                    )


            # =================================================
            # NEXT NODE
            # =================================================

            elif key in (
                curses.KEY_DOWN,
                ord("j")
            ):

                select_next_node()


            # =================================================
            # PREVIOUS NODE
            # =================================================

            elif key in (
                curses.KEY_UP,
                ord("k")
            ):

                select_previous_node()


            # =================================================
            # ACKNOWLEDGE ALERT
            # =================================================

            elif key in (
                ord("a"),
                ord("A")
            ):

                acknowledge_current_alert()


        except curses.error:

            pass


        await asyncio.sleep(
            0.1
        )
