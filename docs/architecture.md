# Architecture

glyfi is an **MVVM** curses TUI framework built on a few pure, testable seams. This
document maps the layers, the typed event spine, the layout solver, and the transport /
stepper.

---

## The big picture

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │  Transport (port, ABC)                                                │
 │    HttpTransport  ──HTTP──▶  POST /v1/turn  ·  GET /v1/subjects        │
 │    MockTransport  (test double, scripted)                             │
 └───────────────────────────────┬─────────────────────────────────────┘
                                  │  TurnRequest ▶ / ◀ TurnResponse
                          ┌───────▼────────┐
                          │    Stepper     │  walks EXACTLY one turn, then STOPS
                          │  session + seq │  captures a Turn on the spine
                          └───────┬────────┘
                                  │
      Model  (dumb data)  ────────┤   AppModel · SessionState · TurnRecord
      glyfi/ui/model.py           │   transcript, content buffer — NO logic
                                  │
      ViewModel (the brain) ──────┤   AppViewModel
      glyfi/ui/viewmodel.py       │   presentation state + every command
                                  │   request_prompt · cycle_mode · open_palette
                                  │   open_config · open_widget · step · scroll_*
                                  │
                                  ├──emit──▶  EventBus (typed)  ──▶  subscribers
                                  │           glyfi/ui/events.py
                                  │
      View   (pure)  ─────────────┤   RegionPainter → Painting (immutable)
      glyfi/ui/view.py            │      CursesView   → a real terminal
                                  │      HeadlessView → captured for tests
                                  │
      Seams ──────────────────────┤   Plugins (commands + widgets) · Theme
                                  │   Clock · Ticker · InputHistory · Fields
                                  └─────────────────────────────────────────
```

---

## The MVVM split

### Model — dumb data (`glyfi/ui/model.py`)

The Model holds state and nothing else: no presentation logic, no I/O.

- `SessionState` — `session_id`, `seq`, `mode` (current label), `last_subject`.
- `TurnRecord` — a frozen record of one walked turn (index, mode, subject, user text, ok,
  staged content, response seq, error).
- `AppModel` — the session, the `AppSettings`, the persisted `UserConfig`, the transcript
  (`List[TurnRecord]`), and the content buffer. Methods are trivial accessors
  (`record_turn`, `set_content`, `turn_at`, `turn_count`).

### ViewModel — the brain (`glyfi/ui/viewmodel.py`)

`AppViewModel` owns all presentation state and every command. It is event-driven and fully
headless-drivable (no curses import). Highlights of the public command surface:

- **The walk:** `step(user_text, subject) -> TurnRecord` — drives the `Stepper` exactly
  once, records the turn, syncs the session from the stepper, clears content, and emits
  `TurnRecorded`. It NEVER loops.
- **Prompt form:** `request_prompt()`, `open_prompt`, `prompt_type`, `prompt_backspace`,
  `prompt_up`, `prompt_down`, `prompt_submit`, `close_prompt`.
- **Modes:** `cycle_mode()` advances through `self.modes` (configurable plain labels) and
  emits `ModeChanged(kind='op', …)`.
- **Palette:** `open_palette`, `palette_type`, `palette_up`, `palette_down`, `palette_run`.
- **Config editor:** `open_config`, `config_up`, `config_down`, `config_enter`,
  `config_back`, `close_modal`.
- **Widgets:** `open_widget(name)`, `widget_key(ch)`, `close_widget`.
- **Content + scroll:** `content_lines`, `windowed_content`, the `scroll_*` family, the
  `traverse_*` family, `clear_content`, `push_help`.
- **Quit:** `request_quit()` with a destructive-confirm latch (`confirm_pending`,
  `cancel_confirm`) — the only RED gesture in the UI.

The ViewModel runs through a small set of modal UI states:
`NORMAL`, `PALETTE`, `CONFIG`, `WIDGET`, `PROMPT`, `TRAVERSE` (the `UI_*` constants).

### View — pure (`glyfi/ui/view.py`)

The View is split so painting is pure and testable:

- `RegionPainter.paint(vm, layout) -> Painting` — turns the ViewModel + a solved layout
  into an immutable `Painting` (per-region text lines, highlight regions/cells/rows, region
  roles, a breadcrumb). No curses, no mutation.
- `View` (ABC) with `render(viewmodel)`.
- `CursesView` (`glyfi/ui/curses_view.py`) — the ONLY runtime curses adapter (besides the
  theme's lazy color setup). Its loop is just getch-with-timeout → `dispatch_key` → repaint.
- `HeadlessView` — solves layout for a synthetic size and captures the `Painting` + layout
  so tests can assert on rendered output with no terminal.

Modal key dispatch is centralized in `glyfi/ui/keymap.py::dispatch_key(vm, ch)` — the
single key → command map, switched on `vm.mode_ui`.

---

## The typed EventBus (`glyfi/ui/events.py`)

Every ViewModel state transition emits a typed, immutable event onto a shared bus.
Subscribers (the repaint, the ticker, the test driver) react without the emitter knowing
they exist (open/closed). Dispatch is by **concrete type**.

The NAMED event types (and their fields):

| event              | fields                       | fires when…                         |
| ------------------ | ---------------------------- | ----------------------------------- |
| `KeyPressed`       | `key:int, mode_ui:str`       | a raw key reaches the ViewModel     |
| `CommandInvoked`   | `name:str`                   | a named command runs                |
| `ModeChanged`      | `kind:str, value:str`        | a mode label (`'op'`) or modal UI (`'ui'`) state changes |
| `TurnRecorded`     | `index:int, ok:bool`         | a turn is recorded onto the transcript |
| `StatusPushed`     | `text:str, at:float`         | a status is pushed onto the ticker  |
| `TickerCycled`     | `provider:str`               | the ticker ring advances (`Tab`)    |
| `MenuMoved`        | `menu:str, index:int`        | a palette/config cursor moves       |
| `SlotBound`        | `group:str, position:int, alias:str` | a config slot is rebound    |
| `InputSubmitted`   | `text:str`                   | the input line is submitted         |
| `HistoryNavigated` | `direction:str, buffer:str`  | `↑`/`↓` walk the input history      |
| `Resized`          | `w:int, h:int`               | the layout re-solves for a new size |
| `Tick`             | `now:float`                  | time advances (runtime timeout / test clock) |

`EVENT_TYPES` is the full registry tuple, in that order. The bus:

```python
from glyfi.ui.events import EventBus, TurnRecorded

bus = EventBus(record=True)               # record=True keeps a log (off by default)
bus.subscribe(TurnRecorded, lambda e: print("turn", e.index, e.ok))
# ... vm emits ...
bus.events_of(TurnRecorded)               # query the recorded log
bus.last(TurnRecorded)                    # most recent of a type
```

See [events.md](events.md) for the full subscribe/record/assert pattern.

---

## The layout solver (`glyfi/ui/layout.py`)

A pure function carves a terminal `Size` into named `Rect`s:

```python
solve_layout(size: Size, regions: List[Region]) -> Dict[str, Rect]
```

- A `Region` has a `name`, an `anchor` (`top`/`bottom`/`left`/`right`/`fill`), a `size`
  (edge thickness), and a `min_size` floor.
- Edge regions carve deterministically in region order; the single `FILL` region takes the
  residual.
- **Responsive smush:** when the terminal is too small, the FILL content yields its space
  first; then chrome bands are trimmed toward their floor in REVERSE region order. This
  keeps the chrome (title, input, hints) legible instead of letting content shove it
  off-screen.
- Fail-loud on more than one FILL region, an unknown anchor, a non-positive edge size, or
  floors that cannot fit.

The default fenced region set lives in `glyfi/ui/settings.py` (`AppSettings.regions`):
`title`, `state`, `header_rule` anchored TOP; `details`, `status_rule`, `input`,
`input_rule`, `status` anchored BOTTOM; `content` is the FILL. `AppSettings` is pluggable —
construct a custom one to re-anchor, resize, or rebind.

---

## The Transport port + one-turn Stepper

### Transport (`glyfi/transport.py`)

```python
class Transport(ABC):
    @abstractmethod
    def send(self, req: TurnRequest) -> TurnResponse: ...
    def list_subjects(self) -> List[Dict[str, str]]: ...   # optional
```

`HttpTransport` is a urllib-only client: `send` POSTs `request_to_dict(req)` to
`/v1/turn`; `list_subjects` GETs `/v1/subjects`. A non-200 surfaces the server's fail-loud
error envelope as a `ProtocolError` (never a silent partial response). The neutral wire
shape lives in `glyfi/protocol.py`:

```
TurnRequest  → {session_id, seq, mode, messages:[{role, content, subject}]}
TurnResponse → {session_id, seq, subject, content, mode}
```

The `subject` is an opaque routing id — the core never interprets it. (The OpenAI pane is
a *separate* seam with its own OpenAI wire keys; those never appear in `glyfi.protocol`.)

### Stepper (`glyfi/stepper.py`)

```python
@dataclass
class Stepper:
    transport: Transport
    session_id: str
    seq: int = 0
    spine: List[Turn] = ...
    history: List[TurnResponse] = ...
    def step(self, user_text, subject="", mode="") -> Turn: ...
```

**The hard law:** `step()` runs **exactly one** turn and stops — it never loops, batches,
or replays. It builds a `TurnRequest` with a single user message, sends it, and captures
either the `TurnResponse` or the surfaced `ProtocolError` into a `Turn` on the `spine`. The
seq advances **only** on success. A failed turn is captured *visibly* (`Turn.ok == False`,
`Turn.error` set) so the TUI can show the error envelope — fail loud, but never swallow.

The ViewModel's `step` wraps this: it walks one stepper turn, builds a `TurnRecord`, pushes
status, records it on the Model, syncs the session seq from the stepper, clears the content,
and emits `TurnRecorded`.

---

## Composition root (`glyfi/app.py`, `glyfi/cli.py`)

`cli.main` parses `--base-url / --session / --list`, resolves `GLYFI_*` config, and either
prints `--list` and exits or calls `build_viewmodel(...)` then `run(...)`.

`build_viewmodel` wires `HttpTransport → Stepper → AppModel → AppViewModel`, loads the
persisted `UserConfig`, and calls `load_plugins()`. `load_plugins` runs the plugin sources
in precedence order (in-code → builtin manifests → user dir) via `build_default_loader()`.
`run` launches the curses loop through `curses.wrapper`.
