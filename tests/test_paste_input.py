"""Unit tests for glyfi.ui.paste_input -- the bracketed-paste state machine + helpers (C6).

Pure, data-free: no curses, no network. Uses plain lists and SimpleNamespace VM stubs.
Ported from the downstream consumer's proven paste_input tests (the consumer-owned
keymap_ext Ctrl-O cases are dropped -- that hook lives in consumer code, not the glyfi base).
"""
from __future__ import annotations

import types

from glyfi.ui.paste_input import PasteStateMachine, display_input, paste_insert


_START_BYTES = [27, 91, 50, 48, 48, 126]   # ESC [ 2 0 0 ~
_END_BYTES   = [27, 91, 50, 48, 49, 126]   # ESC [ 2 0 1 ~


def _feed_sequence(sm, ints):
    events = []
    for ch in ints:
        events.extend(sm.feed(ch))
    return events


def _paste_sequence(text):
    return _START_BYTES + [ord(c) for c in text] + _END_BYTES


def _vm(buf='', caret=None):
    return types.SimpleNamespace(
        input_buffer=buf,
        input_caret=(caret if caret is not None else len(buf)),
        mode_ui='NORMAL',
    )


class TestPasteMachineFullSequence:
    def test_single_line_paste(self):
        sm = PasteStateMachine()
        assert _feed_sequence(sm, _paste_sequence('hello')) == [('insert', 'hello')]

    def test_multi_line_paste_kept_verbatim(self):
        sm = PasteStateMachine()
        assert _feed_sequence(sm, _paste_sequence('hello\nworld')) == [('insert', 'hello\nworld')]

    def test_multi_line_never_emits_newline_passthrough(self):
        sm = PasteStateMachine()
        events = _feed_sequence(sm, _paste_sequence('line1\nline2\nline3'))
        assert len(events) == 1 and events[0][0] == 'insert' and '\n' in events[0][1]
        assert [e for e in events if e[0] == 'passthrough' and e[1] == 10] == []

    def test_empty_paste(self):
        sm = PasteStateMachine()
        assert _feed_sequence(sm, _paste_sequence('')) == [('insert', '')]

    def test_special_chars_preserved(self):
        text = 'foo "bar" <baz> & 100%'
        sm = PasteStateMachine()
        assert _feed_sequence(sm, _paste_sequence(text)) == [('insert', text)]

    def test_sm_resets_after_paste(self):
        sm = PasteStateMachine()
        _feed_sequence(sm, _paste_sequence('hello'))
        assert sm.feed(ord('a')) == [('passthrough', ord('a'))]

    def test_no_events_during_accumulation(self):
        sm = PasteStateMachine()
        out = []
        for ch in _START_BYTES[:-1]:
            out.extend(sm.feed(ch))
        assert out == []


class TestPasteMachineStandaloneEsc:
    def test_standalone_esc_emitted_on_flush(self):
        sm = PasteStateMachine()
        assert sm.feed(27) == []
        assert sm.flush() == [('passthrough', 27)]

    def test_esc_then_non_bracket(self):
        sm = PasteStateMachine()
        sm.feed(27)
        events = sm.feed(ord('A'))
        assert ('passthrough', 27) in events and ('passthrough', ord('A')) in events


class TestPasteMachinePartialAbort:
    def test_partial_start_mismatch(self):
        sm = PasteStateMachine()
        for c in (27, 91, 50):
            sm.feed(c)
        events = sm.feed(99)  # 'c' -- not '0' (48)
        assert [e[1] for e in events] == [27, 91, 50, 99]
        assert all(e[0] == 'passthrough' for e in events)

    def test_idle_passthrough(self):
        sm = PasteStateMachine()
        assert sm.feed(ord('z')) == [('passthrough', ord('z'))]


class TestPasteMachineFalseEndMarker:
    def test_esc_inside_paste_not_end(self):
        sm = PasteStateMachine()
        _feed_sequence(sm, _START_BYTES)
        sm.feed(27)
        assert sm.feed(ord('X')) == []          # false alarm; still in paste
        events = _feed_sequence(sm, _END_BYTES)
        assert len(events) == 1 and events[0][0] == 'insert'
        assert chr(27) in events[0][1] and 'X' in events[0][1]


class TestPasteMachineFlush:
    def test_flush_in_idle(self):
        assert PasteStateMachine().flush() == []

    def test_flush_in_match_start_drains_prefix(self):
        sm = PasteStateMachine()
        sm.feed(27)
        sm.feed(91)
        assert sm.flush() == [('passthrough', 27), ('passthrough', 91)]
        assert sm.feed(ord('a')) == [('passthrough', ord('a'))]

    def test_flush_in_paste_mode_no_events(self):
        sm = PasteStateMachine()
        _feed_sequence(sm, _START_BYTES)
        sm.feed(ord('h'))
        assert sm.flush() == []


class TestDisplayInput:
    def test_no_newline(self):
        assert display_input('hello') == 'hello'

    def test_single_newline(self):
        assert display_input('a\nb') == 'a⏎ b'

    def test_multiple_newlines(self):
        assert display_input('a\nb\nc') == 'a⏎ b⏎ c'

    def test_newline_at_end(self):
        assert display_input('hello\n') == 'hello⏎ '


class TestPasteInsert:
    def test_insert_into_empty(self):
        vm = _vm()
        paste_insert(vm, 'hello')
        assert vm.input_buffer == 'hello' and vm.input_caret == 5

    def test_insert_mid_buffer(self):
        vm = _vm('helo', caret=3)
        paste_insert(vm, 'l')
        assert vm.input_buffer == 'hello' and vm.input_caret == 4

    def test_insert_multiline_preserved(self):
        vm = _vm()
        paste_insert(vm, 'line1\nline2')
        assert vm.input_buffer == 'line1\nline2' and '\n' in vm.input_buffer

    def test_insert_never_submits(self):
        vm = _vm()
        submits = []
        vm.submit_input = lambda: submits.append(True)
        paste_insert(vm, 'hello\nworld')
        assert submits == []
