"""widgets.help_widget -- the ONE reference widget: a read-only help/about overlay that PROVES the seam.

This exists to demonstrate + test the pluggable widget framework end to end -- a real widget is authored the same
way. It is deliberately TRIVIAL: a scrollable read-only list of the app's keybindings + a short about blurb. It
exercises the full port:
  * ``open(ctx)`` pushes a greeting status (which the menu-up suspension keeps live while the widget is open);
  * ``handle_key`` navigates the line cursor on Up/Down (returns True), ignores everything else (returns False
    so the host's Esc-closes still works);
  * ``lines(rect)`` renders the content (PURE text);
  * ``highlight()`` reports the cursor row (so the View shows the focus marker / select highlight);
  * ``close()`` is a no-op (read-only, no state to release).

Registered under ``WIDGET_HELP`` at import so it is openable by name through the host (open/closed: no host edit).

Self-contained: widget base + layout + stdlib only. NO curses except the key-code constants.
"""
from typing import List, Optional

import curses

from glyfi.ui.layout import Rect
from glyfi.widgets.base import Widget, WidgetContext
from glyfi.widgets.host import register_widget

# ---- NAMED widget name (the registry key + the palette/keymap reference) -----------------------------------
WIDGET_HELP = 'help_widget'

# ---- NAMED static content (no magic strings scattered at a render site) ------------------------------------
HELP_TITLE = 'help'
HELP_LINES = (
    'glyfi — keys & about',
    '',
    'NORMAL',
    '  s            walk ONE turn (prompts subject + text, then STOPS)',
    '  m            cycle the current mode label',
    '  /            open the slash-command palette',
    '  c            traverse the content view',
    '  PgUp / PgDn  scroll content (page, minus the overlap sliver)',
    '  ↑ / ↓        recall input history',
    '  Tab          cycle the ephemeral status ticker ring',
    '  q            quit',
    '',
    'MENUS (palette / config / widgets)',
    '  ↑ / ↓        navigate the list (PRIMARY interaction)',
    '  type         filter / fast-jump (SECONDARY)',
    '  Enter        choose',
    '  Esc / ← / ⌫  back one level (breadcrumb) / close',
    '',
    'about: a pluggable, extensible curses TUI skeleton — widgets, scroll-lock,',
    'responsive smush, and a 508/WCAG-aligned semantic theme.',
)
# the greeting pushed on open (NAMED) -- the menu-up suspension keeps it live while the widget is up.
HELP_OPEN_STATUS = 'help — ↑↓ to read, Esc to close'


class HelpWidget(Widget):
    """A read-only, arrow-navigable help/about widget -- the reference impl proving the widget seam + its test."""

    title = HELP_TITLE

    def __init__(self):
        self._cursor = 0
        self._ctx: Optional[WidgetContext] = None

    def open(self, ctx: WidgetContext) -> None:
        """Initialize: reset the cursor + push the greeting status through the scoped context."""
        self._ctx = ctx
        self._cursor = 0
        ctx.push_status(HELP_OPEN_STATUS)

    def handle_key(self, key: int) -> bool:
        """Up/Down move the read cursor (handled); everything else is unhandled (the host's Esc still closes)."""
        if key == curses.KEY_UP:
            self._cursor = max(0, self._cursor - 1)
            return True
        if key == curses.KEY_DOWN:
            self._cursor = min(len(HELP_LINES) - 1, self._cursor + 1)
            return True
        return False

    def lines(self, rect: Rect) -> List[str]:
        """The help content (PURE text). The host frames it (breadcrumb + accent trim); the View clips to ``rect``."""
        return list(HELP_LINES)

    def highlight(self) -> Optional[int]:
        """The read cursor row -- the View marks it with the focus marker + the select highlight."""
        return self._cursor


def _register_builtins() -> None:
    """Register the reference help widget so it is openable by name through the host (open/closed seam)."""
    register_widget(WIDGET_HELP, HelpWidget)


_register_builtins()
