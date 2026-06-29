"""paste_input -- bracketed paste support for the glyfi TUI (C6).

Enables terminal bracketed paste mode (``\\e[?2004h``/``l``) and provides a pure state
machine that recognises paste start/end markers from the one-char-at-a-time ``getch()``
stream, collects the pasted chars, and delivers them as a single ``('insert', text)``
event. Newlines inside a paste are kept verbatim -- they NEVER reach ``dispatch_key`` and
therefore NEVER trigger ``submit_input``.

``display_input(buffer)`` renders embedded ``\\n`` as the visible ``⏎`` marker so the
operator sees line breaks in a single-row input field while the real buffer keeps ``\\n``
and ``submit_input`` sends the true multi-line text.

OCP default: this module is inert unless a consumer passes ``bracketed_paste=True`` to
``CursesView``. With the flag off, ``CursesView.run`` never constructs a ``PasteStateMachine``
and never writes the ``?2004h``/``?2004l`` escapes -- the loop is byte-identical to today.

All functions are pure / data-free and unit-tested in ``tests/test_paste_input.py``. Ported
verbatim from the downstream consumer's proven implementation (acraflow/glyfi_client).
"""
from __future__ import annotations

# -- Bracketed paste byte sequences --------------------------------------------------
#   Start: ESC [ 2 0 0 ~   (27  91  50  48  48  126)
#   End:   ESC [ 2 0 1 ~   (27  91  50  48  49  126)
_START: tuple = (27, 91, 50, 48, 48, 126)
_END:   tuple = (27, 91, 50, 48, 49, 126)

_IDLE        = 'idle'
_MATCH_START = 'match_start'
_IN_PASTE    = 'in_paste'
_MATCH_END   = 'match_end'


class PasteStateMachine:
    """Recognises bracketed-paste markers from a one-char-at-a-time ``getch()`` stream.

    States
    ------
    IDLE        Default; routes chars as passthroughs or starts matching the start marker.
    MATCH_START ESC (27) seen; collecting _START bytes to confirm paste begins.
    IN_PASTE    Inside a paste block; accumulating chars until end marker is detected.
    MATCH_END   Possible end marker (ESC) seen inside paste; matching _END bytes.

    Returns per call
    ----------------
    feed(ch) / flush() -> list of:
      ('passthrough', int)  dispatch this int to preprocess_key / dispatch_key normally
      ('insert', str)       paste complete; insert this text into the input buffer

    flush() drains any pending start-marker prefix on getch() timeout (-1) so a
    standalone ESC press is always emitted within one poll cycle (~50 ms).
    """

    def __init__(self) -> None:
        self._state: str = _IDLE
        self._start_idx: int = 0           # how many bytes of _START matched
        self._end_idx: int = 0             # how many bytes of _END matched (inside paste)
        self._paste_chars: list = []       # accumulated paste code points
        self._pending_end: list = []       # partial _END bytes while MATCH_END

    def reset(self) -> None:
        """Reset to IDLE, discarding any in-progress prefix or paste."""
        self._state = _IDLE
        self._start_idx = 0
        self._end_idx = 0
        self._paste_chars = []
        self._pending_end = []

    # -- public API ------------------------------------------------------------------

    def feed(self, ch: int) -> list:
        """Process one integer from getch(). Returns a list of (kind, value) events."""
        if self._state == _IDLE:
            return self._feed_idle(ch)
        if self._state == _MATCH_START:
            return self._feed_match_start(ch)
        if self._state == _IN_PASTE:
            return self._feed_in_paste(ch)
        if self._state == _MATCH_END:
            return self._feed_match_end(ch)
        # defensive: unknown state
        self.reset()
        return [('passthrough', ch)]

    def flush(self) -> list:
        """Call on getch() timeout (ch == -1).

        Emits any prefix chars held in MATCH_START as passthroughs and resets to IDLE
        so a standalone ESC keystroke is never held forever. In-paste states (IN_PASTE,
        MATCH_END) are left intact -- a paste stream that arrives in multiple getch()
        bursts continues uninterrupted.
        """
        if self._state == _MATCH_START:
            events = [('passthrough', c) for c in _START[:self._start_idx]]
            self.reset()
            return events
        # IDLE / IN_PASTE / MATCH_END: no action on timeout.
        return []

    # -- state handlers --------------------------------------------------------------

    def _feed_idle(self, ch: int) -> list:
        if ch == _START[0]:              # ESC (27) -- could be start of paste marker
            self._state = _MATCH_START
            self._start_idx = 1
            return []
        return [('passthrough', ch)]

    def _feed_match_start(self, ch: int) -> list:
        if ch == _START[self._start_idx]:
            self._start_idx += 1
            if self._start_idx == len(_START):
                # Full start marker matched: enter paste accumulation.
                self._state = _IN_PASTE
                self._paste_chars = []
            return []
        else:
            # Mismatch: emit all held prefix chars, then the current char, as passthroughs.
            events = [('passthrough', c) for c in _START[:self._start_idx]]
            events.append(('passthrough', ch))
            self.reset()
            return events

    def _feed_in_paste(self, ch: int) -> list:
        if ch == _END[0]:               # ESC (27) -- could be start of end marker
            self._state = _MATCH_END
            self._end_idx = 1
            self._pending_end = [ch]
            return []
        self._paste_chars.append(ch)
        return []

    def _feed_match_end(self, ch: int) -> list:
        if ch == _END[self._end_idx]:
            self._end_idx += 1
            self._pending_end.append(ch)
            if self._end_idx == len(_END):
                # Full end marker matched: paste complete.
                text = _ints_to_str(self._paste_chars)
                self.reset()
                return [('insert', text)]
            return []
        else:
            # False alarm: pending_end bytes are literal paste content.
            self._paste_chars.extend(self._pending_end)
            self._paste_chars.append(ch)
            self._pending_end = []
            self._end_idx = 0
            self._state = _IN_PASTE
            return []


def _ints_to_str(ints: list) -> str:
    """Convert a list of Unicode code-point ints to a str. Out-of-range values are skipped."""
    return ''.join(chr(c) for c in ints if 0 <= c <= 0x10FFFF)


# -- Display transform ---------------------------------------------------------------

def display_input(buffer: str) -> str:
    """Replace every ``\\n`` with the visible ``⏎`` (U+23CE) marker + a space.

    Used when rendering the input line so the operator sees embedded newlines without
    curses interpreting them as literal newline control chars. The real buffer is
    unchanged; submit_input reads the buffer directly and sends the true multi-line text.

    Pure / no side-effects.
    """
    return buffer.replace('\n', '⏎ ')


# -- Buffer insert helper ------------------------------------------------------------

def paste_insert(vm, text: str) -> None:
    """Insert pasted text at the current caret position.

    Newlines in the pasted text are kept as-is (they display as ``⏎`` via display_input /
    the multi-line input painter and are sent as genuine multi-line text when the operator
    presses Enter -- never as Enter keystrokes mid-paste).

    VM attrs are accessed via getattr with safe defaults so a SimpleNamespace test stub
    only needs to set the attrs it cares about.
    """
    buf   = getattr(vm, 'input_buffer', '')
    caret = getattr(vm, 'input_caret', len(buf))
    new_buf = buf[:caret] + text + buf[caret:]
    vm.input_buffer = new_buf
    vm.input_caret  = caret + len(text)
