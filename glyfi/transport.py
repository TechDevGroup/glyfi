"""transport -- the transport PORT + a urllib-only HTTP impl.

The client speaks ONLY the chat-shaped turn endpoint over HTTP (stdlib ``urllib`` -- zero-dep, matching
the stdlib-only ethos). It imports nothing from a server package; the port keeps the client testable
against a mock transport or a live HTTP server without changing callers.

A non-200 surfaces the server's fail-loud error envelope as a ``ProtocolError`` (never a silent
empty/partial response). ``list_subjects`` GETs the server-exposed listing of routable subjects.
"""
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Dict, List

from glyfi.protocol import (
    HTTP_CONTENT_TYPE,
    HTTP_LIST_PATH,
    HTTP_TURN_PATH,
    ProtocolError,
    TurnRequest,
    TurnResponse,
    error_from_dict,
    request_to_dict,
    response_from_dict,
    subjects_from_dict,
)


class Transport(ABC):
    """The transport PORT -- send one TurnRequest, get a TurnResponse; plus an optional listing call."""

    @abstractmethod
    def send(self, req: TurnRequest) -> TurnResponse:
        ...

    def list_subjects(self) -> List[Dict[str, str]]:
        """List the server-exposed routable subjects. Optional -- not every transport supports it."""
        raise NotImplementedError


class HttpTransport(Transport):
    """urllib-only OpenAI-protocol-shaped client. Non-200 -> ProtocolError from the server's error envelope.

    ``base_url`` is the server origin (e.g. ``http://127.0.0.1:8800``); the endpoint paths are the NAMED
    ``HTTP_TURN_PATH`` / ``HTTP_LIST_PATH``. The client surfaces the server's fail-loud envelope as a
    ``ProtocolError`` -- it imports no server error type, only the protocol-level error.
    """

    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")
        self._turn_url = self._base + HTTP_TURN_PATH
        self._list_url = self._base + HTTP_LIST_PATH

    def send(self, req: TurnRequest) -> TurnResponse:
        body = json.dumps(request_to_dict(req)).encode("utf-8")
        http_req = urllib.request.Request(
            self._turn_url, data=body, method="POST",
            headers={"Content-Type": HTTP_CONTENT_TYPE},
        )
        try:
            with urllib.request.urlopen(http_req) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._envelope_error(exc) from exc
        return response_from_dict(payload)

    def list_subjects(self) -> List[Dict[str, str]]:
        """GET the server-exposed listing of routable subjects. Fail LOUD on a non-200."""
        http_req = urllib.request.Request(self._list_url, method="GET")
        try:
            with urllib.request.urlopen(http_req) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._envelope_error(exc) from exc
        return subjects_from_dict(payload)

    @staticmethod
    def _envelope_error(exc: urllib.error.HTTPError) -> ProtocolError:
        """Read the server's fail-loud error envelope off the failed response and build a ProtocolError."""
        err = error_from_dict(json.loads(exc.read().decode("utf-8")))
        return ProtocolError(
            f"http {err.code} {err.type}: {err.message}", type=err.type, code=err.code
        )
