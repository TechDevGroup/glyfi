"""widgets -- the PLUGGABLE widget framework: the seam a widget plugin plugs into.

A WIDGET is a self-contained overlay that OWNS the CONTENT region while open, with the rest of the app chrome
(title / state / status / input / details) intact. The framework is three NAMED pieces:

  * ``Widget`` (``base.py``) -- the PORT (ABC): lifecycle ``open(ctx)`` / ``close()``, input ``handle_key(key)``,
    render ``lines(rect)`` + optional ``highlight()``. PURE-ish: geometry/text only, NO curses.
  * ``WidgetContext`` (``base.py``) -- what a widget is handed on ``open``: a SCOPED capability surface
    (push_status / emit / request_close) so a widget never reaches into the ViewModel's internals.
  * ``WidgetHost`` + ``register_widget`` (``host.py``) -- the OPEN/CLOSED registry + the active-widget orchestrator
    the ViewModel routes keys to while a widget is up. Add a widget with ``register_widget(name, factory)``; the
    host is never edited (SOLID: host orchestrates, widgets are self-contained).

The ONE reference widget shipped here (``help_widget.py``) proves the seam end to end; a real widget registers the
same way. Self-contained: this package + layout + stdlib only, NO curses (except key-code constants).
"""
from glyfi.widgets.base import Widget, WidgetContext
from glyfi.widgets.host import (
    WidgetError, WidgetHost, known_widgets, register_widget, widget_factory,
)
from glyfi.widgets.help_widget import WIDGET_HELP, HelpWidget

__all__ = [
    "Widget", "WidgetContext", "WidgetHost", "register_widget", "widget_factory",
    "known_widgets", "WidgetError", "HelpWidget", "WIDGET_HELP",
]
