"""Tests for the transport port + HttpTransport.

The HTTP tests are HERMETIC: they stub the ``urllib.request.urlopen`` seam (and synthesize HTTPError
bodies) so no real network is touched.
"""
import io
import json
import urllib.error

import pytest

from glyfi import transport as transport_mod
from glyfi.protocol import (
    F_CODE,
    F_ERROR,
    F_MESSAGE,
    F_TYPE,
    HTTP_CONTENT_TYPE,
    HTTP_LIST_PATH,
    HTTP_TURN_PATH,
    ProtocolError,
    TurnRequest,
    error_to_dict,
    ApiError,
    Message,
    ROLE_USER,
    response_to_dict,
    subjects_to_dict,
    TurnResponse,
)
from glyfi.transport import HttpTransport, Transport


class _FakeResponse:
    """A context-manager stand-in for an urlopen() response."""

    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def _http_error(status: int, envelope: dict) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps(envelope).encode("utf-8"))
    return urllib.error.HTTPError(
        url="http://x", code=status, msg="err", hdrs=None, fp=body
    )


class _Recorder:
    """Captures the last urllib.request.Request and returns a programmed response/exception."""

    def __init__(self, result):
        self._result = result
        self.last_request = None

    def __call__(self, http_req, *args, **kwargs):
        self.last_request = http_req
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_transport_port_is_abstract():
    with pytest.raises(TypeError):
        Transport()


def test_default_list_subjects_raises_not_implemented():
    class Bare(Transport):
        def send(self, req):
            raise AssertionError("not used")

    with pytest.raises(NotImplementedError):
        Bare().list_subjects()


def test_base_url_trailing_slash_stripped():
    t = HttpTransport("http://host:8800/")
    assert t._turn_url == "http://host:8800" + HTTP_TURN_PATH
    assert t._list_url == "http://host:8800" + HTTP_LIST_PATH


def test_send_posts_and_parses(monkeypatch):
    resp = TurnResponse(session_id="s1", seq=2, subject="sub", content="hi", mode="chat")
    rec = _Recorder(_FakeResponse(response_to_dict(resp)))
    monkeypatch.setattr(transport_mod.urllib.request, "urlopen", rec)

    t = HttpTransport("http://host:8800")
    req = TurnRequest(
        session_id="s1", seq=1,
        messages=[Message(role=ROLE_USER, content="hi", subject="sub")], mode="chat",
    )
    out = t.send(req)
    assert out == resp

    # the request was a POST to the turn url with the JSON content type + serialized body
    sent = rec.last_request
    assert sent.full_url == "http://host:8800" + HTTP_TURN_PATH
    assert sent.method == "POST"
    assert sent.headers["Content-type"] == HTTP_CONTENT_TYPE
    assert json.loads(sent.data.decode("utf-8"))["session_id"] == "s1"


def test_send_non_200_raises_protocol_error(monkeypatch):
    envelope = error_to_dict(ApiError(message="denied", type="forbidden", code=403))
    rec = _Recorder(_http_error(403, envelope))
    monkeypatch.setattr(transport_mod.urllib.request, "urlopen", rec)

    t = HttpTransport("http://host:8800")
    req = TurnRequest(session_id="s1", seq=0, messages=[Message(ROLE_USER, "x")])
    with pytest.raises(ProtocolError) as ei:
        t.send(req)
    assert ei.value.type == "forbidden"
    assert ei.value.code == 403
    assert "denied" in str(ei.value)


def test_list_subjects_gets_and_parses(monkeypatch):
    listing = [{"subject": "a", "label": "Alpha"}]
    rec = _Recorder(_FakeResponse(subjects_to_dict(listing)))
    monkeypatch.setattr(transport_mod.urllib.request, "urlopen", rec)

    t = HttpTransport("http://host:8800")
    out = t.list_subjects()
    assert out == listing
    assert rec.last_request.full_url == "http://host:8800" + HTTP_LIST_PATH
    assert rec.last_request.method == "GET"


def test_list_subjects_non_200_raises_protocol_error(monkeypatch):
    envelope = error_to_dict(ApiError(message="gone", type="not_found", code=404))
    rec = _Recorder(_http_error(404, envelope))
    monkeypatch.setattr(transport_mod.urllib.request, "urlopen", rec)

    t = HttpTransport("http://host:8800")
    with pytest.raises(ProtocolError) as ei:
        t.list_subjects()
    assert ei.value.code == 404
    assert ei.value.type == "not_found"
