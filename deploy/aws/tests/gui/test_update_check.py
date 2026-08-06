from __future__ import annotations

import httpx
import pytest

from glow_deploy.gui import update_check


def test_latest_release_tag_returns_tag_on_success(monkeypatch):
    def fake_get(url, timeout=None, headers=None):
        return httpx.Response(200, json={"tag_name": "gui-v1.2.3"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(update_check.httpx, "get", fake_get)

    assert update_check.latest_release_tag() == "gui-v1.2.3"


def test_latest_release_tag_returns_none_on_http_error(monkeypatch):
    def fake_get(url, timeout=None, headers=None):
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(update_check.httpx, "get", fake_get)

    assert update_check.latest_release_tag() is None


def test_latest_release_tag_returns_none_on_network_error(monkeypatch):
    def fake_get(url, timeout=None, headers=None):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(update_check.httpx, "get", fake_get)

    assert update_check.latest_release_tag() is None
