"""widgets.host -- the WidgetHost orchestrator + the open/closed widget registry (``register_widget``).

The HOST is the single place the ViewModel routes to while a widget is up. It is SOLID:
  * OPEN/CLOSED -- a new widget is added with ``register_widget(name, factory)``; the host code is NEVER edited
    to learn about it (the host opens a widget by NAME through the registry, blind to the concrete class). This
    is the SEAM the next wave of widgets plugs into.
  * SRP -- the host ORCHESTRATES (open / route-keys / close / expose the active widget); the widget is
    self-contained (its own state + render + key handling). The host holds NO widget-specific logic.

The host owns at most ONE active widget at a time (the content region is single-tenant). ``open(name)``
instantiates the registered factory, builds the widget's scoped ``WidgetContext`` (wired to the host's
push_status / emit / request_close callbacks), and calls ``widget.open(ctx)``. ``handle_key`` gives the active
widget first refusal; ``close`` tears it down. ``active`` / ``lines`` / ``highlight`` expose it to the View.

Self-contained: widget base + layout + stdlib only. NO curses, NO ViewModel import (callbacks are injected).
"""
from typing import Callable, Dict, List, Optional

from glyfi.ui.layout import Rect
from glyfi.widgets.base import Widget, WidgetContext


class WidgetError(Exception):
    """A fail-loud widget fault -- an unknown widget name, a duplicate registration, or a bad factory."""


# ---- the registry: name -> a zero-arg factory building a fresh Widget. Open/closed; fail-loud on dup. -------
WidgetFactory = Callable[[], Widget]
_WIDGETS: Dict[str, WidgetFactory] = {}


def register_widget(name: str, factory: WidgetFactory) -> None:
    """Register a widget FACTORY under ``name`` (the open/closed seam). Fail LOUD on a duplicate name.

    ``factory`` is a zero-arg callable returning a FRESH ``Widget`` instance (so each open gets clean state).
    A plugin calls this at import time to make its widget openable by name -- no host edit required.
    """
    if name in _WIDGETS:
        raise WidgetError(f'widget {name!r} already registered (no silent clobber)')
    _WIDGETS[name] = factory


def widget_factory(name: str) -> WidgetFactory:
    """The registered factory for ``name`` -- fail LOUD on unknown (an open of an unregistered widget is a fault)."""
    if name not in _WIDGETS:
        raise WidgetError(f'unknown widget {name!r} (known: {known_widgets()})')
    return _WIDGETS[name]


def known_widgets() -> List[str]:
    """Every registered widget name, in registration order (the palette / discovery surface)."""
    return list(_WIDGETS.keys())


# ---- snapshot / restore: a public seam for ISOLATED, repeatable widget registration ------------------------
# The widget registry is process-global (factories register once at import). To register a set of widgets and
# roll back to a known baseline -- embedding several app instances in one process, or isolating per-test
# registrations -- capture it with ``snapshot_widgets()`` and return to that baseline with ``restore_widgets``.
def snapshot_widgets() -> object:
    """Capture the current widget registry as an OPAQUE, immutable token (for ``restore_widgets``).

    The returned token is a frozen copy of the name->factory mapping; callers cannot mutate the registry through
    it. No behaviour change to the live registry -- this only reads it.
    """
    return tuple(_WIDGETS.items())


def restore_widgets(snapshot: object) -> None:
    """Reset the widget registry to exactly the contents captured by ``snapshot_widgets()``.

    Clears the registry and repopulates it from the token -- any registration made after the snapshot is dropped,
    and anything removed is put back. Idempotent for a given token.
    """
    _WIDGETS.clear()
    _WIDGETS.update(snapshot)  # type: ignore[arg-type]


class WidgetHost:
    """The active-widget orchestrator -- opens a registered widget by name, routes keys, closes it. Single-tenant.

    Constructed with the three host CALLBACKS a widget's ``WidgetContext`` needs (push_status / emit /
    request_close) -- the ViewModel injects these (wired to its ticker / bus / close path). The host instantiates
    a widget through the registry (open/closed) and never names a concrete widget class.
    """

    def __init__(self, push_status: Callable[[str], None], emit: Callable[[object], None],
                 on_close: Callable[[], None],
                 scroll_to: Optional[Callable[[int], None]] = None,
                 current_offset: Optional[Callable[[], int]] = None):
        self._push_status = push_status
        self._emit = emit
        self._on_close = on_close
        # ADDITIVE scroll caps -- a widget that marks/jumps content positions slides the viewport through these.
        # OPTIONAL (default no-ops) so a host built without them is unchanged.
        self._scroll_to = scroll_to or (lambda offset: None)
        self._current_offset = current_offset or (lambda: 0)
        self._active: Optional[Widget] = None
        self._active_name: str = ''

    # ---- orchestration ------------------------------------------------------------------------------------
    def open(self, name: str) -> Widget:
        """Open the registered widget ``name`` (closing any current one first), wire its scoped context, return it.

        Fail LOUD on an unknown name. The widget gets a ``WidgetContext`` whose ``request_close`` routes through
        the host (so a widget asking to close goes through ONE close path -- the host's, which also notifies the VM).
        """
        if self._active is not None:
            self.close()
        widget = widget_factory(name)()      # fail loud on unknown name
        if not isinstance(widget, Widget):
            raise WidgetError(f'widget factory {name!r} did not build a Widget, got {type(widget).__name__!r}')
        ctx = WidgetContext(
            name=name,
            push_status=self._push_status,
            emit=self._emit,
            request_close=self._on_close,
            scroll_to=self._scroll_to,
            current_offset=self._current_offset,
        )
        self._active = widget
        self._active_name = name
        widget.open(ctx)
        return widget

    def handle_key(self, key: int) -> bool:
        """Give the active widget first refusal on a key; return True iff IT handled it (else the host/VM acts)."""
        if self._active is None:
            return False
        return bool(self._active.handle_key(key))

    def close(self) -> None:
        """Close + release the active widget (idempotent -- closing with no active widget is a no-op)."""
        if self._active is None:
            return
        self._active.close()
        self._active = None
        self._active_name = ''

    # ---- read (the View reads these) -----------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._active is not None

    @property
    def active(self) -> Optional[Widget]:
        return self._active

    @property
    def active_name(self) -> str:
        return self._active_name

    def lines(self, rect: Rect) -> List[str]:
        """The active widget's content lines for ``rect`` (empty when no widget is open)."""
        if self._active is None:
            return []
        return self._active.lines(rect)

    def highlight(self) -> Optional[int]:
        """The active widget's selected row (or None) -- the View's focus marker / select-highlight input."""
        if self._active is None:
            return None
        return self._active.highlight()

    def title(self) -> str:
        """The active widget's human title (for the host breadcrumb), or '' when none is open."""
        if self._active is None:
            return ''
        return self._active.title
