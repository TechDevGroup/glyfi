from glyfi.ui.prompt_state import (
    PromptState, FIELD_SUBJECT, FIELD_TEXT, FIELD_COUNT, FIELD_LABELS,
)


def test_named_field_constants():
    assert FIELD_SUBJECT == 0
    assert FIELD_TEXT == 1
    assert FIELD_COUNT == 2
    assert FIELD_LABELS == ('subject', 'text')


def test_defaults():
    p = PromptState()
    assert p.subject == ''
    assert p.text == ''
    assert p.active == FIELD_SUBJECT


def test_value_and_active_value():
    p = PromptState(subject='s', text='t', active=FIELD_TEXT)
    assert p.value(FIELD_SUBJECT) == 's'
    assert p.value(FIELD_TEXT) == 't'
    assert p.active_value == 't'


def test_ready_requires_subject():
    assert not PromptState().ready
    assert not PromptState(subject='   ').ready
    assert PromptState(subject='id').ready
    assert PromptState(subject='id', text='').ready   # text may be empty


def test_type_edits_active_field():
    p = PromptState()
    p.type('a')
    p.type('b')
    assert p.subject == 'ab'
    p.active = FIELD_TEXT
    p.type('x')
    assert p.text == 'x'


def test_backspace_signals_empty():
    p = PromptState(subject='ab')
    assert p.backspace() is False
    assert p.subject == 'a'
    assert p.backspace() is False
    assert p.subject == ''
    assert p.backspace() is True   # already empty -> cancel gesture


def test_move_up_from_first_exits():
    p = PromptState(active=FIELD_TEXT)
    assert p.move_up() is False
    assert p.active == FIELD_SUBJECT
    assert p.move_up() is True      # already first -> exit signal


def test_move_down_clamps():
    p = PromptState(active=FIELD_SUBJECT)
    p.move_down()
    assert p.active == FIELD_TEXT
    p.move_down()
    assert p.active == FIELD_TEXT   # clamped at last
