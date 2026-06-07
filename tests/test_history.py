from glyfi.ui.history import (
    InputHistory, DIR_OLDER, DIR_NEWER, SEAM_INPUT_HISTORY_SCOPE,
)


def test_named_constants():
    assert DIR_OLDER == 'older'
    assert DIR_NEWER == 'newer'
    assert SEAM_INPUT_HISTORY_SCOPE == 'input_history_scope'


def test_empty_history_returns_none():
    h = InputHistory()
    assert h.older() is None
    assert h.newer() is None


def test_record_appends_and_snaps_cursor():
    h = InputHistory()
    h.record('one')
    h.record('two')
    assert h.entries == ['one', 'two']
    assert h.cursor == 2          # live edge


def test_record_ignores_empty():
    h = InputHistory()
    h.record('')
    assert h.entries == []


def test_older_walks_back():
    h = InputHistory()
    h.record('a')
    h.record('b')
    assert h.older() == 'b'
    assert h.older() == 'a'
    assert h.older() == 'a'       # clamped at oldest


def test_newer_returns_to_live_edge():
    h = InputHistory()
    h.record('a')
    h.record('b')
    h.older()                     # b
    h.older()                     # a
    assert h.newer() == 'b'
    assert h.newer() == ''        # past newest -> live edge (blank)


def test_reset_snaps_to_live_edge():
    h = InputHistory()
    h.record('a')
    h.older()
    h.reset()
    assert h.cursor == len(h.entries)


def test_scope_default_none():
    assert InputHistory().scope is None
