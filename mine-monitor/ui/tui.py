import asyncio
import curses

from config import UI_REFRESH_RATE

from state import state

from network import manager

from ui.input import handle_input

from ui.layout import setup_colors, draw_screen

async def run_ui(
    stdscr
):

    setup_colors()

    stdscr.keypad(True)

    stdscr.nodelay(True)


    # ========================================================
    # START NETWORK
    # ========================================================

    await manager.start()


    # ========================================================
    # START INPUT
    # ========================================================

    input_task = asyncio.create_task(
        handle_input(stdscr)
    )


    try:

        while state.running:

            draw_screen(
                stdscr
            )


            await asyncio.sleep(
                UI_REFRESH_RATE
            )


    finally:

        state.running = False


        input_task.cancel()

        try:

            await input_task

        except asyncio.CancelledError:

            pass


        await manager.shutdown()


def start_tui():

    curses.wrapper(
        lambda stdscr:
        asyncio.run(
            run_ui(stdscr)
        )
    )


# ============================================================
# REMOTE MODE (presentation only — no BLE ownership)
# ============================================================

async def run_remote_ui(
    stdscr,
    base_url,
):

    from ui.remote import (
        fetch_snapshot,
        apply_snapshot,
    )

    from ui.input import handle_remote_input


    setup_colors()

    stdscr.keypad(True)

    stdscr.nodelay(True)


    state.message = (
        f"Connected to backend {base_url}"
    )


    input_task = asyncio.create_task(
        handle_remote_input(stdscr, base_url)
    )


    last_poll = 0


    try:

        while state.running:

            now = asyncio.get_running_loop().time()


            # ----------------------------------------------
            # Poll backend state (~2 Hz), render at full
            # UI refresh rate using the EXISTING layout
            # ----------------------------------------------

            if now - last_poll >= 0.5:

                last_poll = now

                snapshot = await asyncio.to_thread(
                    fetch_snapshot,
                    base_url,
                )

                if snapshot is not None:

                    apply_snapshot(snapshot)

                else:

                    state.connected = False

                    state.message = (
                        "Backend unreachable"
                    )


            draw_screen(
                stdscr
            )


            await asyncio.sleep(
                UI_REFRESH_RATE
            )


    finally:

        state.running = False


        input_task.cancel()

        try:

            await input_task

        except asyncio.CancelledError:

            pass


def start_remote_tui(base_url):

    curses.wrapper(
        lambda stdscr:
        asyncio.run(
            run_remote_ui(stdscr, base_url)
        )
    )
