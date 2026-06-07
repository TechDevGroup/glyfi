"""Tests for the one-turn-at-a-time stepper: capture, fail-loud-but-visible, seq advance, no loops."""
import pytest

from glyfi.protocol import (
    ProtocolError,
    ROLE_USER,
    TurnRequest,
    TurnResponse,
)
from glyfi.stepper import Stepper, Turn
from glyfi.transport import Transport


class FakeTransport(Transport):
    """Records each request and returns programmed responses/exceptions, one per call."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.sent = []
        self.send_calls = 0

    def send(self, req: TurnRequest) -> TurnResponse:
        self.send_calls += 1
        self.sent.append(req)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _resp(seq, subject="sub", content="ok", mode=""):
    return TurnResponse(session_id="s1", seq=seq, subject=subject, content=content, mode=mode)


def test_turn_ok_property():
    ok = Turn(index=0, request=TurnRequest("s1", 0), response=_resp(1), error=None)
    assert ok.ok is True
    bad = Turn(index=0, request=TurnRequest("s1", 0), response=None, error="boom")
    assert bad.ok is False


def test_turn_is_frozen():
    t = Turn(index=0, request=TurnRequest("s1", 0), response=_resp(1), error=None)
    with pytest.raises(Exception):
        t.index = 5


def test_step_builds_single_user_message_request():
    tr = FakeTransport([_resp(1)])
    st = Stepper(transport=tr, session_id="s1")
    st.step("hello", subject="sub-7", mode="chat")
    req = tr.sent[0]
    assert req.session_id == "s1"
    assert req.seq == 0
    assert req.mode == "chat"
    assert len(req.messages) == 1
    assert req.messages[0].role == ROLE_USER
    assert req.messages[0].content == "hello"
    assert req.messages[0].subject == "sub-7"


def test_step_runs_exactly_once_per_call():
    tr = FakeTransport([_resp(1)])
    st = Stepper(transport=tr, session_id="s1")
    st.step("hello")
    assert tr.send_calls == 1  # never loops/batches


def test_successful_turn_captured_and_seq_advances():
    tr = FakeTransport([_resp(5)])
    st = Stepper(transport=tr, session_id="s1")
    turn = st.step("hello")
    assert turn.ok
    assert turn.index == 0
    assert turn.error is None
    assert turn.response == _resp(5)
    assert st.seq == 5  # advanced to the server's seq
    assert st.spine == [turn]
    assert st.history == [_resp(5)]


def test_failed_turn_captured_visibly_and_seq_unchanged():
    tr = FakeTransport([ProtocolError("http 403 forbidden: denied", type="forbidden", code=403)])
    st = Stepper(transport=tr, session_id="s1", seq=2)
    turn = st.step("hello")
    assert turn.ok is False
    assert turn.response is None
    assert "denied" in turn.error
    assert st.seq == 2  # NOT advanced on a failed turn
    assert st.spine == [turn]
    assert st.history == []  # only staged responses are kept


def test_spine_indices_increment_across_turns():
    tr = FakeTransport([_resp(1), _resp(2)])
    st = Stepper(transport=tr, session_id="s1")
    t0 = st.step("a")
    t1 = st.step("b")
    assert t0.index == 0
    assert t1.index == 1
    assert [t.index for t in st.spine] == [0, 1]
    # second request carries the advanced seq from the first
    assert tr.sent[1].seq == 1


def test_mixed_success_then_failure_keeps_full_spine():
    tr = FakeTransport([_resp(1), ProtocolError("boom", type="bad", code=400)])
    st = Stepper(transport=tr, session_id="s1")
    st.step("a")
    st.step("b")
    assert len(st.spine) == 2
    assert st.spine[0].ok is True
    assert st.spine[1].ok is False
    assert st.seq == 1  # failure left seq at the first turn's advance
    assert len(st.history) == 1


def test_subject_and_mode_default_empty():
    tr = FakeTransport([_resp(1)])
    st = Stepper(transport=tr, session_id="s1")
    st.step("hello")
    req = tr.sent[0]
    assert req.mode == ""
    assert req.messages[0].subject == ""
