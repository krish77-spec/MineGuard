import logging
import os
import urllib.request

LOG_DIR = os.path.join(
    os.path.dirname(__file__),
    "logs"
)

LOG_FILE = os.path.join(
    LOG_DIR,
    "debug.log"
)


DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"

HEALTH_TIMEOUT = 1.5


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)

    logging.basicConfig(
        filename=LOG_FILE,
        filemode="w",
        level=logging.DEBUG,
        format=(
            "%(asctime)s "
            "[%(name)s] "
            "%(levelname)s: "
            "%(message)s"
        ),
        datefmt="%H:%M:%S",
    )


def backend_reachable(base_url, timeout=HEALTH_TIMEOUT):
    """Probe GET <backend>/api/health. Never raises."""

    try:

        with urllib.request.urlopen(
            base_url.rstrip("/") + "/api/health",
            timeout=timeout,
        ) as response:

            return response.status == 200

    except Exception:

        return False


def resolve_mode(backend_arg, local_flag, probe=backend_reachable):
    """
    Decide which mode the TUI runs in.

    Returns ("remote", url) when the TUI must consume the
    shared backend (presentation only, owns NO BLE), or
    ("local", None) when it owns NetworkManager itself.

    --backend forces remote, --local forces standalone,
    otherwise a reachable backend wins so that a bare
    `python main.py` never creates a second BLE owner
    next to a running backend.
    """

    if local_flag:

        return ("local", None)


    if backend_arg:

        return ("remote", backend_arg)


    if probe(DEFAULT_BACKEND_URL):

        return ("remote", DEFAULT_BACKEND_URL)


    return ("local", None)


from ui.tui import start_tui, start_remote_tui


def main():

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Underground Mine Monitor - "
            "terminal interface"
        )
    )

    parser.add_argument(
        "--backend",
        default=None,
        help=(
            "Force shared-backend mode against a monitor "
            "backend, e.g. http://127.0.0.1:5000. "
            "When omitted, a reachable backend is used "
            "automatically."
        ),
    )

    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Force standalone mode: own the BLE "
            "connection directly (Pi/headless use). "
            "Do NOT use together with a running backend."
        ),
    )

    args = parser.parse_args()

    setup_logging()

    mode, url = resolve_mode(
        args.backend, args.local
    )

    log = logging.getLogger("main")


    if mode == "remote":

        print(
            f"TUI shared mode: using backend {url} "
            "(no local BLE connection)."
        )

        log.info("TUI shared mode, backend %s", url)

        start_remote_tui(url)

    else:

        print(
            "TUI standalone mode: owning the BLE "
            "connection directly."
        )

        log.info("TUI standalone mode")

        start_tui()


if __name__ == "__main__":

    main()
