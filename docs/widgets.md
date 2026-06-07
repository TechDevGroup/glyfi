# Widgets

A **widget** is a self-contained overlay that owns the **content region**: it produces text
lines and reacts to keys. It touches no curses and never reaches into the ViewModel —
everything it does to the surrounding app goes through a scoped `WidgetContext` handed to it
on `open`. The host is the single orchestrator (open/closed), blind to the concrete widget.

Modules: `glyfi/widgets/base.py` (the port), `glyfi/widgets/host.py` (the orchestrator +
registry), `glyfi/widgets/help_widget.py` (the reference widget).

---

## The widget lifecycle

The contract the host drives:

```
 1. open(ctx)        → host opens the widget, hands it the WidgetContext.
                       The widget initializes its own state; it may push a greeting status.
 2. handle_key(key)  → ONE key while active; returns handled:bool.
                       Returning False lets a HOST-level key act (e.g. Esc closes).
                       NEVER auto-loops.
 3. lines(rect)      → the widget's content lines, PURE text (no side effects, no curses).
 4. highlight()      → optional: the selected row within lines (for the focus marker).
 5. close()          → host tears the widget down. Release any state.
```

A widget OWNS the content region only — the chrome (title/state/status/input/details) stays
the app's. The host adds a breadcrumb + accent trim around the widget; the widget just fills
the content.

---

## The `Widget` port

```python
class Widget(ABC):
    title: str = 'widget'                       # the breadcrumb label (override it)

    @abstractmethod
    def open(self, ctx: WidgetContext) -> None: ...
    @abstractmethod
    def lines(self, rect: Rect) -> List[str]: ...

    def handle_key(self, key: int) -> bool:     # default False (host Esc closes)
        return False
    def highlight(self) -> Optional[int]:       # default None (no internal selection)
        return None
    def close(self) -> None:                    # default no-op
        return None
```

Only `open` and `lines` are abstract; the rest have sensible defaults so a read-only widget
is tiny.

---

## The scoped `WidgetContext` capabilities

The `WidgetContext` is the ONLY way a widget touches the wider app (it is immutable — a
widget can't swap its own capabilities):

```python
@dataclass(frozen=True)
class WidgetContext:
    name: str                                   # the widget's registry name (shown in the breadcrumb)
    push_status: Callable[[str], None]          # put an ephemeral status on the ticker
    emit: Callable[[object], None]              # put a typed event on the shared bus
    request_close: Callable[[], None]           # ask the host to close + return to NORMAL
    scroll_to: Callable[[int], None]            # SLIDE the content viewport to an offset (optional)
    current_offset: Callable[[], int]           # READ the current scroll offset (optional)
```

A widget does NOT import or reach into the ViewModel; it calls these NAMED caps. The host
wires them to its own `push_status` / `bus.emit` / close path, so a widget asking to close
goes through ONE close path (the host's).

---

## Worked example: the reference help widget

`glyfi/widgets/help_widget.py` is the reference impl — a read-only, arrow-navigable
help/about overlay that exercises the full port:

```python
import curses
from typing import List, Optional
from glyfi.ui.layout import Rect
from glyfi.widgets.base import Widget, WidgetContext
from glyfi.widgets.host import register_widget

WIDGET_HELP = 'help_widget'
HELP_LINES = ("glyfi — keys & about", "", "NORMAL", "  s   walk ONE turn", ...)
HELP_OPEN_STATUS = 'help — ↑↓ to read, Esc to close'


class HelpWidget(Widget):
    title = 'help'

    def __init__(self):
        self._cursor = 0
        self._ctx: Optional[WidgetContext] = None

    def open(self, ctx: WidgetContext) -> None:
        self._ctx = ctx
        self._cursor = 0
        ctx.push_status(HELP_OPEN_STATUS)          # greeting via the scoped cap

    def handle_key(self, key: int) -> bool:
        if key == curses.KEY_UP:                   # Up/Down move the read cursor (handled)
            self._cursor = max(0, self._cursor - 1)
            return True
        if key == curses.KEY_DOWN:
            self._cursor = min(len(HELP_LINES) - 1, self._cursor + 1)
            return True
        return False                               # everything else: host's Esc still closes

    def lines(self, rect: Rect) -> List[str]:      # PURE text; the host frames + the View clips
        return list(HELP_LINES)

    def highlight(self) -> Optional[int]:          # the cursor row → focus marker + highlight
        return self._cursor


register_widget(WIDGET_HELP, HelpWidget)           # at import: openable by name (open/closed)
```

Note the `import curses` is only for the **key-code constants** (`KEY_UP`/`KEY_DOWN`); the
widget paints no curses.

---

## Registering a factory

A widget is openable by **name** through a zero-arg **factory** (returning a FRESH instance,
so each open gets clean state):

```python
from glyfi.widgets.host import register_widget, widget_factory, known_widgets

register_widget('my_widget', MyWidget)     # fail loud on a duplicate name
known_widgets()                            # every registered name, in order
widget_factory('my_widget')                # the factory (fail loud on unknown)
```

A plugin registers a widget either by calling `register_widget` at import (like the help
widget) or via a manifest `widgets` entry naming a `factory` reference (see
[plugins.md](plugins.md)):

```json
{
  "widgets": [
    {"name": "my_widget", "factory": "glyfi.contrib.mything.widget:MyWidget"}
  ]
}
```

---

## Opening a widget

From a command, return a `CommandResult(open_widget="my_widget")` — the applier opens it
(the command → widget bridge). From the palette, `about` opens the help widget. From the
ViewModel directly, `vm.open_widget("my_widget")`. The `WidgetHost` (single-tenant) closes
any current widget first, builds the scoped `WidgetContext`, and calls `widget.open(ctx)`.

While a widget is up the UI state is `WIDGET`: keys go to the widget first
(`host.handle_key`); if it returns False the host applies host-level keys (Esc closes).

---

## A richer example

The OpenAI context pane (`glyfi/contrib/openai_pane/widget.py`) is a full input-driven
widget: it holds a prompt buffer + a transcript, builds an `OpenAIClient` on `open`,
appends to the buffer on printable keys, and submits ONE completion on Enter. It is authored
entirely against the public `Widget` / `WidgetContext` contract — no core privileges. See
[openai-pane.md](openai-pane.md).
