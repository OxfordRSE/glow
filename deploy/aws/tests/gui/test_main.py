"""Single-instance guard and free-port allocation for the packaged app's
entry point (gui/main.py) — the parts that don't require actually starting
uvicorn or opening a browser.
"""

from __future__ import annotations

import socket

import pytest

from glow_deploy.gui import main


def test_free_port_returns_a_bindable_port():
    port = main._free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((main._HOST, port))  # must not raise


def test_single_instance_lock_refuses_a_second_acquire():
    first = main._acquire_single_instance_lock()
    try:
        with pytest.raises(SystemExit):
            main._acquire_single_instance_lock()
    finally:
        first.close()


def test_single_instance_lock_can_be_reacquired_after_release():
    first = main._acquire_single_instance_lock()
    first.close()

    second = main._acquire_single_instance_lock()
    second.close()
