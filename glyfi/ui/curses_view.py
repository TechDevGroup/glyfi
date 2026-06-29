"""curses_view -- the CURSES View impl: binds the pure Painting to terminal windows; modal, responsive.

This is the concrete, RUNTIME View -- it reads the live terminal dimensions, drives the ViewModel's layout pass,
paints each fenced region into a curses window (applying the highlight to the config-edit AREA and the selected
overlay ROW), and re-solves on SIGWINCH (resize). It is the ONLY app module that touches ``curses`` besides
``theme``. All geometry + line production lives in the pure ``RegionPainter`` / solver.

This is a THIN ADAPTER over the event-driven core: key dispatch is the SHARED ``keymap.dispatch_key`` (the SAME
mapping the headless driver uses -- one source of the key->command map). It NEVER auto-loops the walk. ``run``
blocks on ``getch`` with a periodic TIMEOUT so the ephemeral status TICKER can EXPIRE on its own (the timeout
just wakes the loop to repaint so an expired ticker clears). Modal dispatch by ``vm.mode_ui`` (see ``keymap``).

``curses`` is imported lazily inside the methods (guarded) so this module imports safely on a headless machine.
"""
from typing import Callable, Dict, Optional
from glyfi.ui.layout import Size, Rect
from glyfi.ui.view import View, RegionPainter, Painting
from glyfi.ui.viewmodel import AppViewModel
from glyfi.ui.keymap import dispatch_key
from glyfi.ui.events import KeyPressed, Tick
from glyfi.ui import theme

# the getch poll TIMEOUT (ms) -- 50ms is the poll/repaint cadence: wakes the blocking loop periodically so an
# expired ticker repaints/clears. NAMED, not a magic literal; it is a repaint cadence, NOT a walk timeout.
GETCH_TIMEOUT_MS = 50


class CursesView(View):
    """The curses View -- paints the Painting (with highlight) into windows, modal key dispatch, one turn/keystroke.

    Constructed with the curses ``stdscr`` and a ``RegionPainter`` (the pure painter). ``render`` solves the
    layout for the current screen size and blits each region; ``run`` is the operator-driven, MODAL keystroke loop.
    """

    def __init__(self, stdscr, painter: RegionPainter, *,
                 key_preprocessor: Optional[Callable[['AppViewModel', int], bool]] = None,
                 row_classifier: Optional[Callable[[str, str], str]] = None,
                 pre_render: Optional[Callable[['AppViewModel'], None]] = None,
                 bracketed_paste: bool = False):
        """Construct the curses View. The four keyword-only hooks are opt-in extension points (OCP):

          * ``key_preprocessor`` (C1): ``fn(vm, ch) -> bool`` called BEFORE ``dispatch_key``; True consumes the key.
          * ``row_classifier`` (C2b): ``fn(region_name, line) -> ROLE_*`` for per-row semantic color in ``_blit_region``.
          * ``pre_render`` (C4): ``fn(vm) -> None`` called at the TOP of ``render`` (before the layout solve, G35).
          * ``bracketed_paste`` (C6): enable terminal bracketed paste so pasted newlines never submit.

        Every hook defaults to None/False, so with no opt-in this View behaves byte-identically to before.
        """
        import curses
        import os
        self._scr = stdscr
        self._painter = painter
        self._hot = os.environ.get("GLYFI_HOTRELOAD") == "1"   # dev: hot-reload the active widget on source change
        self._key_preprocessor = key_preprocessor
        self._row_classifier = row_classifier
        self._pre_render = pre_render
        self._bracketed_paste = bracketed_paste
        curses.curs_set(0)
        self._scr.keypad(True)
        theme.init_theme()               # wire color pairs AFTER curses start (guards on has_colors)

    def _current_size(self) -> Size:
        """Read the live terminal dimensions (rows, cols) from curses -- the responsive input."""
        h, w = self._scr.getmaxyx()
        return Size(w=w, h=h)

    def render(self, viewmodel: AppViewModel) -> None:
        """Solve the layout for the CURRENT screen size and paint every region. Re-callable on every resize."""
        if self._hot:                                  # pick up live widget edits BEFORE painting this frame
            viewmodel.reload_active_widget()
        if self._pre_render is not None:               # C4: dynamic region sizing -- MUST run BEFORE the layout
            self._pre_render(viewmodel)                # solve (G35), since resize() reads vm.model.settings.regions
        size = self._current_size()
        layout: Dict[str, Rect] = viewmodel.resize(size)
        painting: Painting = self._painter.paint(viewmodel, layout)
        self._scr.erase()
        select = theme.select_attr()
        for name, rect in layout.items():
            self._blit_region(name, rect, painting, select)
        self._scr.refresh()

    def _blit_region(self, name: str, rect: Rect, painting: Painting, select_attr: int) -> None:
        """Put a region's clipped lines onto the screen, applying the SELECT highlight + the SEMANTIC ROLE attr."""
        if rect.is_empty:
            return
        whole_area = name in painting.highlight_regions
        sel_row = painting.highlight_rows.get(name)
        cell = painting.highlight_cells.get(name)        # a (row, start, end) col span to highlight WITHIN that row
        accents = painting.accent_cells.get(name, [])    # (row, start, end) spans to ACCENT-colour (not select)
        accent_attr = theme.role_attr(theme.ROLE_ACCENT_2)
        role_attr = theme.role_attr(painting.role(name))
        if whole_area:
            self._fill_rect(rect, select_attr)
        for row, line in enumerate(painting.lines(name)):
            if row >= rect.h:
                break
            # C2b + G38 (a11y, HARD): the SELECT override wins -- a selected/filled row ALWAYS shows select_attr,
            # never its per-row content color. BOTH the whole_area AND the sel_row guards must precede the
            # classifier branch. Only an unselected row consults the (optional) row_classifier; with no classifier
            # opted in this falls through to the region-level role_attr -- byte-identical to before.
            if whole_area or (sel_row is not None and row == sel_row):
                attr = select_attr
            elif self._row_classifier is not None:
                attr = theme.role_attr(self._row_classifier(name, line))
            else:
                attr = role_attr
            self._safe_addstr(rect.y + row, rect.x, line[:rect.w], attr)
            if cell is not None and cell[0] == row:
                self._blit_cell(rect, row, line, cell, select_attr)
            for span in accents:                          # overlay metric-value spans in the accent-2 colour
                if span[0] == row:
                    self._blit_cell(rect, row, line, span, accent_attr)

    def _blit_cell(self, rect: Rect, row: int, line: str, cell, select_attr: int) -> None:
        """Overlay just the ``(row, start, end)`` column span of a row with the SELECT attr -- a single field highlight."""
        _row, start, end = cell
        start = max(0, min(start, rect.w))
        end = max(start, min(end, rect.w))
        if end <= start:
            return
        seg = line[start:end]
        if len(seg) < (end - start):
            seg = seg + ' ' * ((end - start) - len(seg))   # pad past the line end so the caret cell shows
        self._safe_addstr(rect.y + row, rect.x + start, seg, select_attr)

    def _fill_rect(self, rect: Rect, attr: int) -> None:
        """Paint a rect's background with ``attr`` (blank rows) -- the whole-area edit preview."""
        blank = ' ' * rect.w
        for row in range(rect.h):
            self._safe_addstr(rect.y + row, rect.x, blank, attr)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        """Write text (with an attr), swallowing the harmless bottom-right-corner curses error (a known quirk)."""
        import curses
        try:
            self._scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def run(self, viewmodel: AppViewModel) -> None:
        """The OPERATOR-DRIVEN, MODAL loop -- one keystroke -> SHARED dispatch -> repaint -> wait. NEVER auto-loops.

        ``getch`` is given a periodic TIMEOUT so the loop wakes even with no key, lets the monotonic Clock advance
        the ephemeral ticker past its TTL, and repaints. A timeout returns ``-1`` -- no key, no walk; we just emit
        a Tick (for any subscriber) and repaint. A real key goes through the SAME ``keymap`` the headless driver
        uses (one source of the key->command mapping).

        C1 (key_preprocessor): each key goes through the preprocessor (if opted in) BEFORE ``dispatch_key``;
        returning True consumes the key. C6 (bracketed_paste): when opted in, raw getch ints are fed through a
        ``PasteStateMachine`` so a pasted block's newlines are inserted as text, never dispatched as Enter. Both
        paths share ``_dispatch_paste_event`` so the C1 seam is honored identically in the paste and non-paste
        routes. With both hooks at their defaults the loop is byte-identical to the original.
        """
        import curses
        import sys
        if self._bracketed_paste:                      # C6/G31: enable bracketed paste; ALWAYS restored in finally
            sys.stdout.write('\033[?2004h')
            sys.stdout.flush()
        paste_sm = None
        if self._bracketed_paste:
            from glyfi.ui.paste_input import PasteStateMachine
            paste_sm = PasteStateMachine()
        try:
            self._scr.timeout(GETCH_TIMEOUT_MS)
            self.render(viewmodel)
            while not viewmodel.should_quit:
                ch = self._scr.getch()
                if ch == -1:                          # the poll timeout fired (no key) -- tick + repaint to expire the ticker
                    if paste_sm is not None:          # C6/G32: drain a pending ESC prefix so a lone Esc is emitted
                        for ev in paste_sm.flush():
                            self._dispatch_paste_event(ev, viewmodel)
                    viewmodel.bus.emit(Tick(now=viewmodel.clock.now()))
                    self.render(viewmodel)
                    continue
                if ch == curses.KEY_RESIZE:
                    if paste_sm is not None:          # flush pending prefix safely on resize
                        for ev in paste_sm.flush():
                            self._dispatch_paste_event(ev, viewmodel)
                    self.render(viewmodel)
                    continue
                if paste_sm is not None:
                    events = paste_sm.feed(ch)        # may buffer (no events) while matching a paste marker
                    for ev in events:
                        self._dispatch_paste_event(ev, viewmodel)
                    if events:
                        self.render(viewmodel)
                else:
                    viewmodel.bus.emit(KeyPressed(key=ch, mode_ui=viewmodel.mode_ui))
                    if self._key_preprocessor is None or not self._key_preprocessor(viewmodel, ch):
                        dispatch_key(viewmodel, ch)   # C1: preprocessor first; True = consumed (skip dispatch)
                    self.render(viewmodel)
        finally:
            if self._bracketed_paste:                 # C6/G31: ALWAYS restore -- a terminal left in ?2004h is broken
                try:
                    sys.stdout.write('\033[?2004l')
                    sys.stdout.flush()
                except Exception:
                    pass

    def _dispatch_paste_event(self, ev, viewmodel: AppViewModel) -> None:
        """Dispatch one ``PasteStateMachine`` event (C6), honoring the C1 preprocessor seam for passthroughs.

        A ``('passthrough', ch)`` int is routed exactly like a normal keystroke -- emit ``KeyPressed``, then the
        preprocessor (if any) before ``dispatch_key``; if C1 is not opted in the None-check short-circuits to
        ``dispatch_key`` directly. An ``('insert', text)`` event inserts pasted text at the caret (newlines kept
        verbatim -- never dispatched as Enter, so a multi-line paste never submits).
        """
        from glyfi.ui.paste_input import paste_insert
        kind = ev[0]
        if kind == 'passthrough':
            pch = ev[1]
            viewmodel.bus.emit(KeyPressed(key=pch, mode_ui=viewmodel.mode_ui))
            if self._key_preprocessor is None or not self._key_preprocessor(viewmodel, pch):
                dispatch_key(viewmodel, pch)
        elif kind == 'insert':
            paste_insert(viewmodel, ev[1])
