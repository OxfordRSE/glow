"""PyInstaller entry point: start the local server and open a browser tab.

A frozen build has no visible console — this is also how the app is run from
source for local dev/manual smoke-testing (`uv run glow-deploy-gui`).
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from glow_deploy.gui.app import create_app

_HOST = "127.0.0.1"
# Arbitrary fixed port bound purely as a single-instance mutex — the actual
# server below still runs on a separate, freshly allocated port.
_SINGLE_INSTANCE_LOCK_PORT = 47632


def _acquire_single_instance_lock() -> socket.socket:
    """Bind a fixed local port as a mutex; a second launch fails here and exits.

    ponytail: a bound-socket mutex, not a PID-file with staleness handling —
    good enough for a single local desktop app; revisit if a crashed process
    ever needs to release this cleanly on its own.
    """
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind((_HOST, _SINGLE_INSTANCE_LOCK_PORT))
    except OSError:
        print("Glow Deploy is already running.", file=sys.stderr)
        sys.exit(1)
    return lock_socket


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((_HOST, 0))
        return probe.getsockname()[1]


def _open_browser_when_ready(host: str, port: int, url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(url)


def main() -> None:
    lock_socket = _acquire_single_instance_lock()
    try:
        port = _free_port()
        url = f"http://{_HOST}:{port}"
        app = create_app()

        threading.Thread(
            target=_open_browser_when_ready, args=(_HOST, port, url), daemon=True
        ).start()
        uvicorn.run(app, host=_HOST, port=port, log_level="info")
    finally:
        lock_socket.close()


if __name__ == "__main__":
    main()
