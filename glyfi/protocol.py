"""protocol -- the neutral wire types shared by client and server.

The shape mirrors an OpenAI chat request/response: a request carries a ``messages`` array of
role/content items; both request and response carry a SESSION id and a SEQ. The unit of work is a
single turn. The client holds opaque ``subject`` routing ids only -- the core never interprets them.

  Message (request item):  role + content + an opaque routing subject id.
  TurnRequest:             session id + seq + a list of messages + an optional plain mode label.
  TurnResponse:            session id + (advanced) seq + the staged content + the subject it resolved
                           to + the mode it ran in.

Stateless server: the request carries everything; the server persists nothing required to serve the
next turn. Turn-tracking is the caller's responsibility (see the stepper).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


# the OpenAI-spec wire surface -- NAMED endpoint paths + JSON keys, no bare strings on the wire.
HTTP_TURN_PATH = "/v1/turn"            # the chat-shaped turn endpoint (a `messages` array)
HTTP_LIST_PATH = "/v1/subjects"        # GET: the server-exposed listing of routable subjects
HTTP_CONTENT_TYPE = "application/json"

# JSON field names (OpenAI chat-shaped: a `messages` array of role/content items).
F_SESSION_ID = "session_id"
F_SEQ = "seq"
F_MODE = "mode"
F_MESSAGES = "messages"        # the OpenAI-spec chat array
F_ROLE = "role"
F_CONTENT = "content"
F_SUBJECT = "subject"
F_ERROR = "error"              # OpenAI-spec error envelope: {"error": {...}}
F_MESSAGE = "message"
F_TYPE = "type"
F_CODE = "code"
F_SUBJECTS = "subjects"        # the listing response: an array of {subject, label}
F_LABEL = "label"              # the human-facing label a subject was registered for

# the two chat roles (user/assistant only).
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    """One chat turn item: role + content + an opaque routing subject id (core never interprets it)."""
    role: str
    content: str
    subject: str = ""


@dataclass(frozen=True)
class TurnRequest:
    """Stateless request: session id + seq + the messages + an optional plain mode label."""
    session_id: str
    seq: int
    messages: List[Message] = field(default_factory=list)
    mode: str = ""


@dataclass(frozen=True)
class TurnResponse:
    """Staged response: session id + (advanced) seq + content + the subject it resolved to + the mode."""
    session_id: str
    seq: int
    subject: str
    content: str
    mode: str = ""


@dataclass(frozen=True)
class ApiError:
    """OpenAI-spec error-envelope payload under the "error" key. Fail loud, never silent."""
    message: str
    type: str          # e.g. "bad_request" | "not_found"
    code: int          # the HTTP status the server set


class ProtocolError(Exception):
    """Client-side fail-loud protocol fault. Carries wire type/code so the TUI can show the envelope.

    The client never imports server internals. When the server returns a fail-loud error envelope, the
    HTTP transport surfaces it as THIS error; the stepper catches it to render the fault visibly.
    """

    def __init__(self, message: str, *, type: str = "", code: int = 0):
        super().__init__(message)
        self.type = type
        self.code = code


# ============================================================================================
# Wire (de)serialization -- pure stdlib JSON-able dicts. The HTTP transport carries these shapes.
# Fail LOUD on a missing required field (KeyError, never a silent default).
# ============================================================================================
def request_to_dict(req: TurnRequest) -> Dict[str, Any]:
    """A TurnRequest -> the OpenAI-chat-shaped request dict (a `messages` array of role items)."""
    return {
        F_SESSION_ID: req.session_id,
        F_SEQ: req.seq,
        F_MODE: req.mode,
        F_MESSAGES: [
            {F_ROLE: m.role, F_CONTENT: m.content, F_SUBJECT: m.subject}
            for m in req.messages
        ],
    }


def request_from_dict(payload: Dict[str, Any]) -> TurnRequest:
    """The request dict -> a TurnRequest. Fail LOUD on a missing required field (KeyError)."""
    messages = [
        Message(role=m[F_ROLE], content=m[F_CONTENT], subject=m.get(F_SUBJECT, ""))
        for m in payload[F_MESSAGES]
    ]
    return TurnRequest(
        session_id=payload[F_SESSION_ID],
        seq=payload[F_SEQ],
        messages=messages,
        mode=payload.get(F_MODE, ""),
    )


def response_to_dict(resp: TurnResponse) -> Dict[str, Any]:
    """A TurnResponse -> the response dict (subject + advanced seq + staged content + mode)."""
    return {
        F_SESSION_ID: resp.session_id,
        F_SEQ: resp.seq,
        F_SUBJECT: resp.subject,
        F_CONTENT: resp.content,
        F_MODE: resp.mode,
    }


def response_from_dict(payload: Dict[str, Any]) -> TurnResponse:
    """The response dict -> a TurnResponse. Fail LOUD on a missing required field."""
    return TurnResponse(
        session_id=payload[F_SESSION_ID],
        seq=payload[F_SEQ],
        subject=payload[F_SUBJECT],
        content=payload[F_CONTENT],
        mode=payload.get(F_MODE, ""),
    )


def subjects_to_dict(listing: List[Dict[str, str]]) -> Dict[str, Any]:
    """The server-exposed routable subjects -> the listing dict ({subjects: [{subject, label}, ...]})."""
    return {F_SUBJECTS: [{F_SUBJECT: s[F_SUBJECT], F_LABEL: s[F_LABEL]} for s in listing]}


def subjects_from_dict(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """The listing dict -> a list of {subject, label}. Fail LOUD on a missing field."""
    return [{F_SUBJECT: s[F_SUBJECT], F_LABEL: s[F_LABEL]} for s in payload[F_SUBJECTS]]


def error_to_dict(err: ApiError) -> Dict[str, Any]:
    """An ApiError -> the OpenAI-spec error envelope: {"error": {message, type, code}}."""
    return {F_ERROR: {F_MESSAGE: err.message, F_TYPE: err.type, F_CODE: err.code}}


def error_from_dict(payload: Dict[str, Any]) -> ApiError:
    """The error envelope -> an ApiError. Fail LOUD on a malformed envelope."""
    e = payload[F_ERROR]
    return ApiError(message=e[F_MESSAGE], type=e[F_TYPE], code=e[F_CODE])
