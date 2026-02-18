from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from canvas_ai.canvas_client import CanvasClient, CanvasClientError


class _Resp:
    def __init__(self, status: int, headers: dict[str, str] | None = None):
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError("boom")
            err.response = SimpleNamespace(status_code=self.status_code)
            raise err

    def json(self):
        return []


def test_retries_then_success(monkeypatch):
    client = CanvasClient("https://x", "t")
    seq = [requests.Timeout(), _Resp(429), _Resp(200)]

    def fake_get(*args, **kwargs):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("canvas_ai.canvas_client.time.sleep", lambda *_: None)
    data = client.list_courses()
    assert data == []


def test_no_retry_on_auth(monkeypatch):
    client = CanvasClient("https://x", "t")

    def fake_get(*args, **kwargs):
        return _Resp(401)

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(CanvasClientError) as exc:
        client.list_courses()
    assert exc.value.status_code == 401
