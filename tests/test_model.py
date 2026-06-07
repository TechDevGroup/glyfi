"""Tests for the MVVM Model (dumb data): SessionState / TurnRecord / AppModel recorders + accessors."""
from glyfi.ui.model import AppModel, SessionState, TurnRecord
from glyfi.ui.settings import AppSettings
from glyfi.ui.config_store import UserConfig


def _record(index, ok=True):
    return TurnRecord(index=index, mode='chat', subject='sub-1', user_text='hi', ok=ok,
                      staged_content='staged' if ok else None,
                      response_seq=index + 1 if ok else None,
                      error=None if ok else 'boom')


def test_session_state_defaults():
    s = SessionState(session_id='s1')
    assert s.seq == 0 and s.mode == '' and s.last_subject == ''


def test_record_turn_appends_and_counts():
    model = AppModel(session=SessionState(session_id='s1'))
    assert model.turn_count == 0
    model.record_turn(_record(0))
    model.record_turn(_record(1))
    assert model.turn_count == 2


def test_turn_at_bounds():
    model = AppModel(session=SessionState(session_id='s1'))
    model.record_turn(_record(0))
    assert model.turn_at(0).index == 0
    assert model.turn_at(5) is None
    assert model.turn_at(-1) is None


def test_set_and_clear_content():
    model = AppModel(session=SessionState(session_id='s1'))
    model.set_content(['a', 'b'])
    assert model.content_buffer == ['a', 'b']
    model.clear_content()
    assert model.content_buffer == []


def test_defaults_for_settings_and_config():
    model = AppModel(session=SessionState(session_id='s1'))
    assert isinstance(model.settings, AppSettings)
    assert isinstance(model.config, UserConfig)


def test_turn_record_is_frozen_and_carries_fields():
    rec = _record(3, ok=False)
    assert rec.ok is False and rec.error == 'boom'
    assert rec.subject == 'sub-1' and rec.mode == 'chat'
    # frozen: a field set raises
    import dataclasses
    try:
        rec.index = 9
        assert False, 'expected frozen'
    except dataclasses.FrozenInstanceError:
        pass
