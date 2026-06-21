"""widgets.base -- the Widget PORT (ABC) + the scoped WidgetContext capability surface.

A ``Widget`` is a self-contained overlay: it produces TEXT LINES for the content rect and reacts to keys; it
touches NO curses and does NOT reach into the ViewModel. Everything it is allowed to do to the surrounding app
goes through the ``WidgetContext`` it is handed on ``open`` -- a SCOPED capability surface (push a status, emit a
bus event, request its own close). This keeps a widget self-contained (SRP) and the host the only orchestrator
(open/closed: the host routes to the widget through these methods, blind to which concrete widget it is).

THE WIDGET LIFECYCLE (the contract the host drives):
  1. ``open(ctx)``       -- the host opens the widget, handing it the ``WidgetContext``. The widget initializes
                            its own state; it may ``ctx.push_status(...)`` a greeting. Called once per open.
  2. ``handle_key(key)`` -- ONE key code while the widget is active; returns ``handled: bool``. When it returns
                            False the host lets a HOST-level key (e.g. Esc to close) act -- so a widget need only
                            handle the keys it cares about. NEVER auto-loops anything.
  3. ``lines(rect)``     -- the widget's CONTENT, clipped to its own taste to ``rect`` (the content Rect). PURE:
                            returns ``List[str]``; no side effects, no curses.
  4. ``highlight()``     -- optional: the selected row within the widget's own lines (for the focus marker /
                            select highlight). Default None (no internal selection).
  5. ``close()``         -- the host tears the widget down (on request_close or a host Esc). Release any state.

A widget OWNS the CONTENT region only -- the chrome (title/state/status/input/details) stays the app's. The host
adds a breadcrumb + accent trim around the widget; the widget itself just fills the content.

Self-contained: ABC + stdlib typing + the layout ``Rect``. NO curses, NO ViewModel import (the context is duck-typed).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from glyfi.ui.layout import Rect


@dataclass(frozen=True)
class WidgetContext:
    """The SCOPED capability surface a widget is handed on ``open`` -- the ONLY way it touches the wider app.

    A widget does NOT import or reach into the ViewModel; it calls these NAMED capabilities. ``push_status`` puts
    an ephemeral status on the ticker (which the menu-up suspension keeps live while the widget is open);
    ``emit`` puts a typed event on the shared bus (reuse the spine -- the host wires this to ``vm.bus.emit``);
    ``request_close`` asks the host to close the widget and return to NORMAL. ``name`` is the widget's registry
    name (the breadcrumb shows it). ``scroll_to(offset)`` SLIDES the content viewport to a scroll offset and
    ``current_offset()`` reads the live one. Immutable -- a widget can't swap its own capabilities.
    """
    name: str
    push_status: Callable[[str], None]
    emit: Callable[[object], None]
    request_close: Callable[[], None]
    # ADDITIVE capability -- SLIDE the content viewport to a scroll offset and READ the current one. OPTIONAL
    # (defaults to no-ops) so existing widgets/contexts that never construct these caps keep working unchanged.
    scroll_to: Callable[[int], None] = lambda offset: None
    current_offset: Callable[[], int] = lambda: 0
    # ADDITIVE capability -- CAPTURE the live frame / one named region as composed text ROWS (for documentation
    # capture). OPTIONAL (defaults to None) so existing widgets/contexts that never wire capture are unchanged.
    capture_frame: Optional[Callable[[], List[str]]] = None
    capture_region: Optional[Callable[[str], List[str]]] = None


class Widget(ABC):
    """The widget PORT -- a self-contained content-region overlay. Concrete widgets (help / ...) plug in.

    Lifecycle: ``open(ctx)`` -> ``handle_key`` / ``lines`` / ``highlight`` while active -> ``close()``. The host
    calls these blind to the concrete type (open/closed). A widget holds its OWN state and renders ONLY text for
    the content rect -- it never paints curses and never mutates the ViewModel except through its ``WidgetContext``.

    ``title`` is the human label the host shows in the breadcrumb (defaults to ``'widget'``); override it.
    """

    #: the human label shown in the host breadcrumb (override per widget).
    title: str = 'widget'

    @abstractmethod
    def open(self, ctx: WidgetContext) -> None:
        """Initialize the widget against its scoped ``ctx`` (called once when the host opens it)."""
        raise NotImplementedError('Widget.open -- a concrete widget must initialize against the WidgetContext')

    @abstractmethod
    def lines(self, rect: Rect) -> List[str]:
        """The widget's content lines for the content ``rect`` (PURE text; the host clips + frames them)."""
        raise NotImplementedError('Widget.lines -- a concrete widget must render its content lines')

    def handle_key(self, key: int) -> bool:
        """React to ONE key code while active; return True iff the widget HANDLED it.

        Default: handle nothing (a read-only widget) -- the host then applies host-level keys (Esc closes). A
        widget overrides this to drive its own selection / input. NEVER loop here -- one key, one reaction.
        """
        return False

    def highlight(self) -> Optional[int]:
        """The selected row within ``lines`` (for the focus marker / select highlight), or None for no selection."""
        return None

    def accents(self, rect: Rect) -> List[Tuple[int, int, int]]:
        """OPTIONAL: cell spans ``(row, start_col, end_col)`` within the widget's content to ACCENT-colour (e.g. a
        metric value), WITHOUT selecting them. Rows index into ``lines(rect)``. Default: none -- existing widgets
        are unchanged. The host forwards these; the View paints them in the ACCENT-2 role."""
        return []

    def close(self) -> None:
        """Release the widget's state (called when the host closes it). Default: nothing to release."""
        return None
