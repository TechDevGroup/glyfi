import pytest

from glyfi.ui import fields
from glyfi.ui.fields import (
    ALIAS_CWD, ALIAS_LOCALTIME, ALIAS_SESSION, ALIAS_SEQ, ALIAS_MODE_FIELD,
    ALIAS_SUBJECT, ALIAS_TURNS, ALIAS_URL, ALIAS_TITLE, ALIAS_BLANK,
    LOCALTIME_FORMAT, HOME_ABBREV, SUBJECT_PLACEHOLDER,
    register_field, known_aliases, field_label, alias_choices, resolve, resolve_labeled,
)


class _Session:
    def __init__(self, session_id='sess', seq=2, last_subject=''):
        self.session_id = session_id
        self.seq = seq
        self.last_subject = last_subject


class _Model:
    def __init__(self, turn_count=4):
        self.turn_count = turn_count


class _VM:
    def __init__(self, last_subject='', mode='chat', title='glyfi', url='http://x'):
        self.session = _Session(last_subject=last_subject)
        self.model = _Model()
        self.mode = mode
        self.title = title
        self.url = url


def test_alias_constants():
    assert ALIAS_CWD == 'cwd'
    assert ALIAS_LOCALTIME == 'localtime'
    assert ALIAS_SESSION == 'session'
    assert ALIAS_SEQ == 'seq'
    assert ALIAS_MODE_FIELD == 'mode'
    assert ALIAS_SUBJECT == 'subject'
    assert ALIAS_TURNS == 'turns'
    assert ALIAS_URL == 'url'
    assert ALIAS_TITLE == 'title'
    assert ALIAS_BLANK == 'blank'


def test_render_tunables():
    assert LOCALTIME_FORMAT == '%H:%M:%S'
    assert HOME_ABBREV == '~'
    assert SUBJECT_PLACEHOLDER == '-'


def test_dropped_aliases_absent():
    aliases = known_aliases()
    for gone in ('op', 'charset', 'scope', 'gid'):
        assert gone not in aliases


def test_known_aliases_contains_expected():
    aliases = set(known_aliases())
    assert {ALIAS_SUBJECT, ALIAS_MODE_FIELD, ALIAS_SESSION, ALIAS_SEQ, ALIAS_TURNS} <= aliases


def test_resolve_subject_placeholder_and_value():
    assert resolve(ALIAS_SUBJECT, _VM(last_subject='')) == SUBJECT_PLACEHOLDER
    assert resolve(ALIAS_SUBJECT, _VM(last_subject='abc')) == 'abc'


def test_resolve_mode_session_seq_turns():
    vm = _VM(mode='chat')
    assert resolve(ALIAS_MODE_FIELD, vm) == 'chat'
    assert resolve(ALIAS_SESSION, vm) == 'sess'
    assert resolve(ALIAS_SEQ, vm) == '2'
    assert resolve(ALIAS_TURNS, vm) == '4'


def test_field_label_known_and_unknown():
    assert field_label(ALIAS_SUBJECT) == 'subject'
    with pytest.raises(KeyError):
        field_label('nope')


def test_resolve_unknown_fails_loud():
    with pytest.raises(KeyError):
        resolve('nope', _VM())


def test_register_dup_fails_loud():
    with pytest.raises(ValueError):
        register_field(ALIAS_SUBJECT, 'dup', lambda vm: '')


def test_alias_choices_pairs():
    choices = dict(alias_choices())
    assert choices[ALIAS_SUBJECT] == 'subject'


def test_resolve_labeled():
    vm = _VM(last_subject='id1')
    assert resolve_labeled(ALIAS_SUBJECT, vm) == 'subject id1'
    assert resolve_labeled(ALIAS_BLANK, vm) == ''
