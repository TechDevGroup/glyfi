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
from typing import Dict
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

    def __init__(self, stdscr, painter: RegionPainter):
        import curses
        self._scr = stdscr
        self._painter = painter
        curses.curs_set(0)
        self._scr.keypad(True)
        theme.init_theme()               # wire color pairs AFTER curses start (guards on has_colors)

    def _current_size(self) -> Size:
        """Read the live terminal dimensions (rows, cols) from curses -- the responsive input."""
        h, w = self._scr.getmaxyx()
        return Size(w=w, h=h)

    def render(self, viewmodel: AppViewModel) -> None:
        """Solve the layout for the CURRENT screen size and paint every region. Re-callable on every resize."""
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
        role_attr = theme.role_attr(painting.role(name))
        if whole_area:
            self._fill_rect(rect, select_attr)
        for row, line in enumerate(painting.lines(name)):
            if row >= rect.h:
                break
            attr = role_attr
            if whole_area:
                attr = select_attr
            if sel_row is not None and row == sel_row:
                attr = select_attr
            self._safe_addstr(rect.y + row, rect.x, line[:rect.w], attr)
            if cell is not None and cell[0] == row:
                self._blit_cell(rect, row, line, cell, select_attr)

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
        """
        import curses
        self._scr.timeout(GETCH_TIMEOUT_MS)
        self.render(viewmodel)
        while not viewmodel.should_quit:
            ch = self._scr.getch()
            if ch == -1:                              # the poll timeout fired (no key) -- tick + repaint to expire the ticker
                viewmodel.bus.emit(Tick(now=viewmodel.clock.now()))
                self.render(viewmodel)
                continue
            if ch == curses.KEY_RESIZE:
                self.render(viewmodel)
                continue
            viewmodel.bus.emit(KeyPressed(key=ch, mode_ui=viewmodel.mode_ui))
            dispatch_key(viewmodel, ch)
            self.render(viewmodel)
