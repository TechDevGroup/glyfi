"""Tests for the neutral wire protocol: dataclasses, (de)serializers, NAMED keys, fail-loud."""
import pytest

from glyfi.protocol import (
    F_CODE,
    F_CONTENT,
    F_ERROR,
    F_LABEL,
    F_MESSAGE,
    F_MESSAGES,
    F_MODE,
    F_ROLE,
    F_SEQ,
    F_SESSION_ID,
    F_SUBJECT,
    F_SUBJECTS,
    F_TYPE,
    HTTP_CONTENT_TYPE,
    HTTP_LIST_PATH,
    HTTP_TURN_PATH,
    ROLE_ASSISTANT,
    ROLE_USER,
    ApiError,
    Message,
    ProtocolError,
    TurnRequest,
    TurnResponse,
    error_from_dict,
    error_to_dict,
    request_from_dict,
    request_to_dict,
    response_from_dict,
    response_to_dict,
    subjects_from_dict,
    subjects_to_dict,
)


def test_named_wire_constants_preserved():
    assert HTTP_TURN_PATH == "/v1/turn"
    assert HTTP_LIST_PATH == "/v1/subjects"
    assert HTTP_CONTENT_TYPE == "application/json"
    assert F_SESSION_ID == "session_id"
    assert F_SEQ == "seq"
    assert F_MODE == "mode"
    assert F_MESSAGES == "messages"
    assert F_ROLE == "role"
    assert F_CONTENT == "content"
    assert F_SUBJECT == "subject"
    assert F_ERROR == "error"
    assert F_MESSAGE == "message"
    assert F_TYPE == "type"
    assert F_CODE == "code"
    assert F_SUBJECTS == "subjects"
    assert F_LABEL == "label"
    assert ROLE_USER == "user"
    assert ROLE_ASSISTANT == "assistant"


def test_dataclass_defaults():
    m = Message(role=ROLE_USER, content="hi")
    assert m.subject == ""
    req = TurnRequest(session_id="s1", seq=0)
    assert req.messages == []
    assert req.mode == ""
    resp = TurnResponse(session_id="s1", seq=1, subject="x", content="ok")
    assert resp.mode == ""


def test_dataclasses_are_frozen():
    m = Message(role=ROLE_USER, content="hi")
    with pytest.raises(Exception):
        m.content = "no"


def test_request_round_trip():
    req = TurnRequest(
        session_id="s1",
        seq=3,
        messages=[Message(role=ROLE_USER, content="hello", subject="sub-7")],
        mode="chat",
    )
    payload = request_to_dict(req)
    assert payload == {
        F_SESSION_ID: "s1",
        F_SEQ: 3,
        F_MODE: "chat",
        F_MESSAGES: [{F_ROLE: ROLE_USER, F_CONTENT: "hello", F_SUBJECT: "sub-7"}],
    }
    back = request_from_dict(payload)
    assert back == req


def test_request_from_dict_subject_optional():
    payload = {
        F_SESSION_ID: "s1",
        F_SEQ: 0,
        F_MESSAGES: [{F_ROLE: ROLE_USER, F_CONTENT: "hi"}],
    }
    req = request_from_dict(payload)
    assert req.messages[0].subject == ""
    assert req.mode == ""


def test_request_from_dict_fails_loud_on_missing_field():
    with pytest.raises(KeyError):
        request_from_dict({F_SESSION_ID: "s1", F_SEQ: 0})  # no messages
    with pytest.raises(KeyError):
        request_from_dict({F_SESSION_ID: "s1", F_SEQ: 0, F_MESSAGES: [{F_ROLE: ROLE_USER}]})


def test_response_round_trip():
    resp = TurnResponse(session_id="s1", seq=4, subject="sub-9", content="staged", mode="chat")
    payload = response_to_dict(resp)
    assert payload == {
        F_SESSION_ID: "s1",
        F_SEQ: 4,
        F_SUBJECT: "sub-9",
        F_CONTENT: "staged",
        F_MODE: "chat",
    }
    assert response_from_dict(payload) == resp


def test_response_from_dict_fails_loud():
    with pytest.raises(KeyError):
        response_from_dict({F_SESSION_ID: "s1", F_SEQ: 1, F_SUBJECT: "x"})  # no content


def test_subjects_round_trip():
    listing = [{"subject": "a", "label": "Alpha"}, {"subject": "b", "label": "Beta"}]
    payload = subjects_to_dict(listing)
    assert payload == {F_SUBJECTS: [
        {F_SUBJECT: "a", F_LABEL: "Alpha"},
        {F_SUBJECT: "b", F_LABEL: "Beta"},
    ]}
    assert subjects_from_dict(payload) == listing


def test_subjects_from_dict_fails_loud():
    with pytest.raises(KeyError):
        subjects_from_dict({F_SUBJECTS: [{F_SUBJECT: "a"}]})  # no label


def test_error_round_trip():
    err = ApiError(message="bad thing", type="bad_request", code=400)
    payload = error_to_dict(err)
    assert payload == {F_ERROR: {F_MESSAGE: "bad thing", F_TYPE: "bad_request", F_CODE: 400}}
    assert error_from_dict(payload) == err


def test_error_from_dict_fails_loud():
    with pytest.raises(KeyError):
        error_from_dict({F_ERROR: {F_MESSAGE: "x", F_TYPE: "y"}})  # no code
    with pytest.raises(KeyError):
        error_from_dict({})  # no error key


def test_protocol_error_carries_type_and_code():
    exc = ProtocolError("boom", type="not_found", code=404)
    assert str(exc) == "boom"
    assert exc.type == "not_found"
    assert exc.code == 404


def test_protocol_error_defaults():
    exc = ProtocolError("boom")
    assert exc.type == ""
    assert exc.code == 0
