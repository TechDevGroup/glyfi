# Generic Opt-In View Plumbing

> **Phase 1 — SPEC ONLY.** This document is the design brief; implementation follows on the same
> branch. Every capability is an opt-in extension point with a zero-behavior-change default.
> Existing glyfi consumers see NO change unless they explicitly opt in.

---

## Design Principle

These seven capabilities were proven in a downstream consumer (`acraflow/glyfi_client/`) that
extended glyfi by subclassing `CursesView`, `RegionPainter`, and overriding `run()` in a local
wrapper class. The goal here is to offer each capability as a **clean, first-class extension
point in the glyfi base** so:

- Downstream consumers opt in with a single hook/flag — no subclassing required unless they want to.
- The base never changes behavior for consumers that do not opt in (OCP).
- Each capability has a single home (SRP) — not scattered across a god-patch.

### Worked example: how a custom view opts in

The pattern below shows all seven capabilities opted in at once, mirroring what acraflow does:

```python
from glyfi.ui.curses_view import CursesView
from glyfi.ui.view import RegionPainter
from glyfi.ui.settings import AppSettings
from glyfi.ui.paste_input import PasteStateMachine   # C6 — ported from acraflow
from glyfi.ui.input_painter import make_multi_line_input_painter  # C5
from glyfi.ui.input_painter import pre_render_dynamic_height      # C4
from glyfi.ui.list_window import window_around        # C3 — already used by base _palette_overlay

from myapp.keymap_ext import preprocess_key           # C1 — consumer-owned
from myapp.row_classifier import classify_row         # C2 — consumer-owned

def run(vm):
    painter = RegionPainter(
        post_paint=make_multi_line_input_painter(),   # C5
    )
    view = CursesView(
        stdscr,
        painter,
        key_preprocessor=preprocess_key,             # C1
        row_classifier=classify_row,                  # C2
        pre_render=pre_render_dynamic_height,         # C4
        bracketed_paste=True,                         # C6
    )
    import curses
    curses.wrapper(lambda scr: CursesView(scr, painter, ...).run(vm))
```

Custom `AppSettings` (C7, already works today):
```python
app_model = AppModel(
    settings=AppSettings(keys={'/' : 'palette'}),  # only '/' bound; s/m/c/q dropped
)
```

---

## Capability 1 — Key Preprocessor Hook

**Summary:** a `preprocess_key(vm, ch) -> bool` callable called in `CursesView.run()` BEFORE
`dispatch_key`, giving consumers new key/chord bindings without subclassing `run()`.

**Base file:** `glyfi/ui/curses_view.py`

**Exact seam to add:**

```python
# __init__ signature change (keyword-only, default=None preserves OCP):
class CursesView(View):
    def __init__(self, stdscr, painter: RegionPainter, *,
                 key_preprocessor: Optional[Callable[['AppViewModel', int], bool]] = None):
        ...
        self._key_preprocessor = key_preprocessor
```

In `run()`, replace the bare `dispatch_key(viewmodel, ch)` call with:

```python
viewmodel.bus.emit(KeyPressed(key=ch, mode_ui=viewmodel.mode_ui))
if self._key_preprocessor is None or not self._key_preprocessor(viewmodel, ch):
    dispatch_key(viewmodel, ch)
self.render(viewmodel)
```

**OCP default:** `None` → `dispatch_key` called exactly as before. Zero behavior change.

**SRP home:** `curses_view.py` owns the wiring; the preprocessor function itself lives in
consumer code (e.g. `acraflow/glyfi_client/keymap_ext.py:preprocess_key`). No new module needed
in glyfi.

**Opt-in API:** pass `key_preprocessor=fn` to `CursesView(...)`. The function signature:
`def preprocess_key(vm: AppViewModel, ch: int) -> bool`. Return `True` to consume the key
(skip `dispatch_key`); return `False` to pass through unchanged.

**Reference impl:** `acraflow/glyfi_client/keymap_ext.py` — the complete, unit-tested
preprocessor. `acraflow/glyfi_client/pipeline_app.py` lines 996-1058 show the wiring
(`_Ext.run()`).

**Test plan:**
- Headless: pass a `key_preprocessor` spy to `CursesView` via `HeadlessView`-equivalent test;
  assert that `True` return skips `dispatch_key`, `False` passes through.
- Pure: `keymap_ext.preprocess_key` is already fully unit-tested in acraflow without curses.
- Confirm `KeyPressed` bus event is emitted before the preprocessor call (for bus subscribers).

**Interactions:**
- C6 (bracketed paste): when both are enabled, passthrough events from `PasteStateMachine.feed`
  go through `preprocess_key` before `dispatch_key` — correct order. See C6 loop pseudocode.
- G12 (gotcha): this is the exact keystone described in `GLYFI_TUI_GOTCHAS.md G12`. The previous
  workaround was a full `run()` override in `_Ext(CursesView)`. With this seam, consumers no
  longer need to copy `run()`.

---

## Capability 2 — Per-Row Semantic Color

**Summary:** dispatch a per-row `ROLE_*` attr in `_blit_region` instead of a single region-level
attr, enabling semantic color for code/error/header/search rows.

Two orthogonal sub-seams:

### 2a — `VisualRow.color_role` field (model layer)

**Base file:** `glyfi/ui/content_view.py`

**Exact seam to add:**

```python
@dataclass(frozen=True)
class VisualRow:
    text: str
    entry_index: int
    is_header: bool
    color_role: str = ''      # ADD: ROLE_* hint for the renderer; '' = no override (ROLE_NORMAL)
```

`render_entries` is unchanged — it produces `color_role=''` for all rows by default. A consumer
that wraps or subclasses `render_entries` can set this field.

**OCP default:** `''` → renderer treats it as "no override", identical to current behavior.

**SRP home:** `content_view.py` (the `VisualRow` model).

**Note:** This seam enables future model-level role annotation. The renderer seam (2b) is what
makes colors visible today. Both are specced; implement together.

### 2b — `row_classifier` on `CursesView` (render layer)

**Base file:** `glyfi/ui/curses_view.py`

**Exact seam to add:**

```python
class CursesView(View):
    def __init__(self, stdscr, painter: RegionPainter, *,
                 key_preprocessor=None,
                 row_classifier: Optional[Callable[[str, str], str]] = None):
        ...
        self._row_classifier = row_classifier
```

In `_blit_region`, replace the single `role_attr` application with per-row dispatch:

```python
def _blit_region(self, name, rect, painting, select_attr):
    if rect.is_empty:
        return
    whole_area = name in painting.highlight_regions
    sel_row = painting.highlight_rows.get(name)
    cell = painting.highlight_cells.get(name)
    accents = painting.accent_cells.get(name, [])
    accent_attr = theme.role_attr(theme.ROLE_ACCENT_2)
    role_attr = theme.role_attr(painting.role(name))
    if whole_area:
        self._fill_rect(rect, select_attr)
    for row, line in enumerate(painting.lines(name)):
        if row >= rect.h:
            break
        # SELECT override wins — selection is never hidden by per-row color (G38, a11y).
        if whole_area or (sel_row is not None and row == sel_row):
            attr = select_attr
        elif self._row_classifier is not None:
            attr = theme.role_attr(self._row_classifier(name, line))
        else:
            attr = role_attr
        self._safe_addstr(rect.y + row, rect.x, line[:rect.w], attr)
        if cell is not None and cell[0] == row:
            self._blit_cell(rect, row, line, cell, select_attr)
        for span in accents:
            if span[0] == row:
                self._blit_cell(rect, row, line, span, accent_attr)
```

**CRITICAL (G38):** The `if whole_area or (sel_row is not None and row == sel_row)` guard
**must appear exactly as shown** before the per-row classifier branch. Both `whole_area` and
`sel_row` checks are required. A selected row must always show `select_attr` — this is an a11y
hard rule.

**OCP default:** `row_classifier=None` → `else: attr = role_attr` — identical to current code.

**SRP home:** `curses_view.py` (the hook wiring). Consumer provides the classifier function
(e.g. `acraflow/glyfi_client/row_color.py:row_role`). An optional utility module
`glyfi/ui/row_classifier.py` may provide base classifier helpers if glyfi wants to ship any
built-in ones (not required for Phase 1).

**Opt-in API:** `CursesView(stdscr, painter, row_classifier=fn)` where
`fn(region_name: str, line: str) -> str` returns a `ROLE_*` constant.

**Reference impl:** `acraflow/glyfi_client/row_color.py:row_role` — complete classifier with
diff sub-classification, spike sentinel, search markers, keep callouts, code fences, headers.
Wired in `pipeline_app.py:run._Ext._blit_region` (the override this seam replaces).

**Test plan:**
- Unit: headless/pure test confirms `row_classifier` is called per row, SELECT overrides it,
  regions without a classifier use `painting.role()` unchanged.
- Confirm `color_role=''` on `VisualRow` does not break any existing `render_entries` tests
  (frozen field with default — `dataclass(frozen=True)` with `field(default='')` is compatible).

**Gotchas:**
- G38: both `whole_area` AND `sel_row` guards are required. Never simplify to just one.
- G37: `GUTTER_CODE.rstrip()` = `"│"` (bare pipe, no space) for empty code lines; a consumer
  classifier must match both `"│ "` and `"│"` forms (acraflow `row_color.py` already does this).
- G39: diff `│ +`/`│ -` classification is heuristic — the classifier has no fence-type context.
  Known trade-off; document in the consumer classifier.

---

## Capability 3 — Overlay List Windowing

**Summary:** window the palette and widget overlay lists around the selection so long lists
scroll instead of truncating at `_clip_lines`. The consumer sees the cursor row always.

**New module:** `glyfi/ui/list_window.py`

```python
def window_around(
    lines: List[str],
    focus: Optional[int],
    height: int,
) -> Tuple[List[str], Optional[int]]:
    """Return a height-row slice of `lines` that keeps `focus` visible.

    When height >= len(lines), returns (lines, focus) — no windowing, identical behavior.
    When focus is None, returns (lines[:height], None).
    """
```

This is a direct port of `acraflow/glyfi_client/scroll_window.py:window_around` (the
implementation is already pure, tested, and complete — copy verbatim).

**Base file:** `glyfi/ui/view.py`

**Exact seam — `_palette_overlay`:** replace the current implementation body with one that:
1. Builds the full filtered command list (unchanged).
2. Reads `height = layout_rect.h if layout_rect else 24`.
3. If `len(lines) > height`: calls `window_around`, adds `↑ N more` / `↓ N more` indicator
   rows (1 row each), calls `_mark_focus` on the windowed slice, returns.
4. If `len(lines) <= height`: calls `_mark_focus(lines, selected)` as before — **no change in
   behavior when the list fits**.

The exact palette scroll logic (including the two-pass indicator-count calculation) is in
`acraflow/glyfi_client/pipeline_app.py:_ExtPainter._palette_overlay` — port it here.

**Opt-in decision:** unlike the other capabilities, this one can be wired unconditionally into
`_palette_overlay` because: (a) the short-list path is byte-identical to the current behavior,
(b) every glyfi user benefits from a scrollable palette when they add many plugin commands.
This is the one capability where "default ON (but behavior-identical for short lists)" is
appropriate. If the implementer wants to preserve the exact truncation behavior as a fallback,
add `scroll_palette: bool = True` to `RegionPainter.__init__`.

**SRP home:** `glyfi/ui/list_window.py` (the pure helper).

**Reference impl:** `acraflow/glyfi_client/scroll_window.py:window_around` (pure helper);
`acraflow/glyfi_client/pipeline_app.py:_ExtPainter._palette_overlay` (complete scroll +
indicator logic).

**Test plan:**
- Unit: test `window_around` independently (short list → no-op; long list → windowed; focus at
  ends → clamped correctly). The acraflow tests in `tests/test_scroll_window.py` can be ported.
- Integration: `RegionPainter._palette_overlay` test — many commands → cursor stays in view;
  few commands → unchanged output.

**Interactions:**
- `_widget_overlay` can use the same `window_around` helper when a widget has a long list;
  the widget passes its rect height. Widgets should use `window_around` internally (not the base
  painter) since the base `_widget_overlay` delegates to `vm.widgets.lines(rect)`.

---

## Capability 4 — Dynamic Region Height

**Summary:** let a region's `size` track content each frame (e.g. a growable input field) via
a `pre_render` hook called before `viewmodel.resize(size)`.

**Base file:** `glyfi/ui/curses_view.py`

**Exact seam to add:**

```python
class CursesView(View):
    def __init__(self, stdscr, painter: RegionPainter, *,
                 key_preprocessor=None,
                 row_classifier=None,
                 pre_render: Optional[Callable[['AppViewModel'], None]] = None,
                 bracketed_paste: bool = False):
        ...
        self._pre_render = pre_render
```

In `render()`, immediately after the hot-reload guard and **before** `size = self._current_size()`:

```python
def render(self, viewmodel: AppViewModel) -> None:
    if self._hot:
        viewmodel.reload_active_widget()
    if self._pre_render is not None:          # ← ADD
        self._pre_render(viewmodel)           # ← ADD
    size = self._current_size()
    layout = viewmodel.resize(size)
    ...
```

**CRITICAL (G35):** the hook MUST fire BEFORE `viewmodel.resize(size)` because `resize` reads
`vm.model.settings.regions` to solve the layout. A `pre_render` that mutates
`vm.model.settings` after `resize` is called has no effect on the current frame.

**OCP default:** `None` → `render` behaves exactly as before.

**SRP home:** `curses_view.py` (the hook wiring). The size-computation logic is consumer-side
(e.g. `acraflow/glyfi_client/input_render.py:input_height`).

**Opt-in API:** `CursesView(stdscr, painter, pre_render=my_pre_render)`. The hook signature:
`def my_pre_render(vm: AppViewModel) -> None`. It mutates `vm.model.settings` (via
`dataclasses.replace(vm.model.settings, regions=...)`) to set the new region sizes before the
frame is laid out. `AppSettings` is frozen; replace it entirely — do not attempt in-place mutation.

**Reference impl:** `acraflow/glyfi_client/pipeline_app.py:run._Ext.render` (the pre-render
logic that computes `input_height(buf)`, compares to current size, and swaps the settings if
different). `acraflow/glyfi_client/input_render.py:input_height` is the size function.

**Test plan:**
- Pure: test that a `pre_render` hook that doubles the input region height is reflected in the
  solved layout on that frame.
- Confirm `pre_render=None` produces the same layout as the current code with no hook.
- Confirm the hook fires before `viewmodel.resize` (mock `resize` to assert call order).

**Interactions:**
- C5 (multi-line input rendering): dynamic height is the prerequisite for true multi-row input.
  C4 grows the field; C5 fills the rows. They should both be opted in together for multi-line.
- A `pre_render` hook that does nothing (or makes no change) has zero cost beyond the None check.

---

## Capability 5 — Multi-Line Input Rendering

**Summary:** render an N-line input buffer across N rows with a correct per-row caret position.
A `post_paint` hook on `RegionPainter` patches the REGION_INPUT slice of the Painting after
the base paint completes.

**New module:** `glyfi/ui/input_painter.py`

Port the following from `acraflow/glyfi_client/input_render.py` (pure, unit-tested):

```python
INPUT_MAX_ROWS: int = 6       # hard cap; long buffers scroll internally
INPUT_CONTINUATION: str = '   '   # 3 spaces, same width as INPUT_PROMPT

def buffer_lines(buf: str) -> List[str]: ...
def caret_rowcol(buf: str, caret: int) -> Tuple[int, int]: ...
def visible_window(lines: List[str], caret_row: int, max_rows: int) -> Tuple[int, List[str]]: ...
def input_height(buf: str, max_rows: int = INPUT_MAX_ROWS) -> int: ...
```

Also provide two ready-made hook factories that consumers pass to `CursesView` / `RegionPainter`:

```python
def make_multi_line_input_painter() -> Callable[[AppViewModel, Dict, Painting], Painting]:
    """Return a post_paint hook that patches REGION_INPUT for multi-line buffers.

    For single-line buffers or PALETTE mode: returns painting unchanged.
    For buffers with \\n: replaces REGION_INPUT lines with per-buffer-line rows,
    places the caret cell at the correct (vis_row, col) from caret_rowcol().
    """

def make_pre_render_dynamic_height() -> Callable[[AppViewModel], None]:
    """Return a pre_render hook that grows REGION_INPUT to match the buffer's line count.

    Each frame: computes input_height(buf), reads the current REGION_INPUT Region size,
    replaces vm.model.settings if sizes differ. No-op when height is unchanged.
    """
```

**Base file:** `glyfi/ui/view.py`

**Exact seam to add on `RegionPainter`:**

```python
class RegionPainter:
    def __init__(self, *,
                 post_paint: Optional[Callable[['AppViewModel', Dict, 'Painting'], 'Painting']] = None):
        self._post_paint = post_paint

    def paint(self, vm: AppViewModel, layout: Dict[str, Rect]) -> Painting:
        painting = self._do_paint(vm, layout)   # existing logic, renamed from paint()
        if self._post_paint is not None:
            painting = self._post_paint(vm, layout, painting)
        return painting

    def _do_paint(self, vm: AppViewModel, layout: Dict[str, Rect]) -> Painting:
        # ... existing paint() body here unchanged ...
```

**CRITICAL (G36):** `Painting` is frozen (`@dataclass(frozen=True)`). The `post_paint` hook
must use `dataclasses.replace(painting, regions=new_regions, highlight_cells=new_cells)` to
patch it — never direct attribute assignment.

**OCP default:** `RegionPainter()` with no `post_paint` → `_do_paint` result returned directly,
identical behavior. `HeadlessView` constructs `RegionPainter()` with no args — unchanged.

**SRP home:** `view.py` (the `post_paint` hook wiring + rename); `glyfi/ui/input_painter.py`
(the pure multi-line logic + hook factories).

**Opt-in API:**
```python
painter = RegionPainter(post_paint=make_multi_line_input_painter())
view = CursesView(stdscr, painter, pre_render=make_pre_render_dynamic_height())
```

**Reference impl:**
- Pure helpers: `acraflow/glyfi_client/input_render.py` (buffer_lines, caret_rowcol,
  visible_window, input_height).
- `post_paint` logic: `acraflow/glyfi_client/pipeline_app.py:run._ExtPainter.paint` — the
  complete multi-line patch (build display lines, clip, compute caret cell, replace Painting).
- `pre_render` logic: `acraflow/glyfi_client/pipeline_app.py:run._Ext.render` (dynamic height
  settings-swap).

**Test plan:**
- Port `acraflow/tests/test_input_render.py` → `glyfi/tests/test_input_painter.py`.
- Pure: `buffer_lines`, `caret_rowcol`, `visible_window`, `input_height` with edge cases.
- `post_paint=None`: `RegionPainter().paint()` output unchanged (existing tests stay green).
- `post_paint=make_multi_line_input_painter()`: single-line buffer → no change; buffer with `\n`
  → REGION_INPUT has N lines; caret cell is at `(vis_row, len(INPUT_PROMPT)+ccol, ...)`.

**Gotchas:**
- G33: the caret column is `len(INPUT_PROMPT) + ccol` for ALL rows, because `INPUT_CONTINUATION`
  is defined at exactly the same width as `INPUT_PROMPT`. The column math is identical on any row.
- G34: PALETTE mode — `post_paint` must skip multi-line patching when `vm.mode_ui == UI_PALETTE`.
- G35: `pre_render` (C4) MUST fire before `viewmodel.resize()`. The `post_paint` (C5) runs after
  `paint()` — these are on different sides of `resize`. Both must be opted in together.
- G36: frozen `Painting` — always use `replace()`.

---

## Capability 6 — Bracketed Paste

**Summary:** enable terminal bracketed paste mode so pasted newlines never trigger submission.
An escape-sequence accumulator (`PasteStateMachine`) in `CursesView.run()` converts the raw
getch stream into either passthrough chars or insert-text events.

**New module:** `glyfi/ui/paste_input.py`

Port from `acraflow/glyfi_client/paste_input.py` verbatim:

```python
class PasteStateMachine:
    def feed(self, ch: int) -> List[Tuple[str, ...]]: ...   # ('passthrough', int) | ('insert', str)
    def flush(self) -> List[Tuple[str, ...]]: ...           # drain pending ESC on timeout

def display_input(buffer: str) -> str: ...   # replace \n with ⏎ for single-line display
def paste_insert(vm, text: str) -> None: ... # insert text at caret position
```

**Base file:** `glyfi/ui/curses_view.py`

**Exact seam:** add `bracketed_paste: bool = False` to `CursesView.__init__`. In `run()`,
replace the current loop with the bracketed-paste-aware form when the flag is True:

```python
def run(self, viewmodel: AppViewModel) -> None:
    import sys
    if self._bracketed_paste:
        sys.stdout.write('\033[?2004h')
        sys.stdout.flush()
    paste_sm = PasteStateMachine() if self._bracketed_paste else None

    try:
        self._scr.timeout(GETCH_TIMEOUT_MS)
        self.render(viewmodel)
        while not viewmodel.should_quit:
            ch = self._scr.getch()
            if ch == -1:
                if paste_sm is not None:
                    for ev in paste_sm.flush():
                        self._dispatch_paste_event(ev, viewmodel)
                viewmodel.bus.emit(Tick(now=viewmodel.clock.now()))
                self.render(viewmodel)
                continue
            if ch == curses.KEY_RESIZE:
                if paste_sm is not None:
                    for ev in paste_sm.flush(): pass   # flush safely on resize
                self.render(viewmodel)
                continue
            if paste_sm is not None:
                events = paste_sm.feed(ch)
                for ev in events:
                    self._dispatch_paste_event(ev, viewmodel)
                if events:
                    self.render(viewmodel)
            else:
                viewmodel.bus.emit(KeyPressed(key=ch, mode_ui=viewmodel.mode_ui))
                if self._key_preprocessor is None or not self._key_preprocessor(viewmodel, ch):
                    dispatch_key(viewmodel, ch)
                self.render(viewmodel)
    finally:
        if self._bracketed_paste:
            try:
                sys.stdout.write('\033[?2004l')
                sys.stdout.flush()
            except Exception:
                pass

def _dispatch_paste_event(self, ev, viewmodel: AppViewModel) -> None:
    """Dispatch one PasteStateMachine event."""
    from glyfi.ui.paste_input import paste_insert
    kind = ev[0]
    if kind == 'passthrough':
        pch = ev[1]
        viewmodel.bus.emit(KeyPressed(key=pch, mode_ui=viewmodel.mode_ui))
        if self._key_preprocessor is None or not self._key_preprocessor(viewmodel, pch):
            dispatch_key(viewmodel, pch)
    elif kind == 'insert':
        paste_insert(viewmodel, ev[1])
```

**CRITICAL (G31):** `\033[?2004l` must be written in `finally` — always, even on exception.
Leaving the terminal in `?2004h` mode breaks subsequent programs (paste wrappers visible as
literal garbage). The `try/except` around the `finally` flush guards against a broken pipe on
teardown.

**CRITICAL (G32):** `paste_sm.flush()` must be called on EVERY `ch == -1` path. A standalone
ESC keystroke is held in `MATCH_START` state until `flush()` on the next ~50ms timeout — not
dispatching immediately. Without `flush()`, the ESC never reaches `dispatch_key`.

**OCP default:** `bracketed_paste=False` → the `paste_sm` branch is never entered; the loop
is byte-identical to the current code. No `sys.stdout` writes.

**SRP home:** `glyfi/ui/paste_input.py` (the `PasteStateMachine` + helpers);
`curses_view.py` (the loop wiring).

**Reference impl:** `acraflow/glyfi_client/paste_input.py` (complete SM, tested);
`acraflow/glyfi_client/pipeline_app.py:run._Ext.run()` (loop wiring).

**Test plan:**
- Port `acraflow/tests/test_paste_input.py` → `glyfi/tests/test_paste_input.py`.
- `PasteStateMachine` unit tests: complete paste (`\e[200~text\n\e[201~`) → `('insert', 'text\n')`;
  partial start marker → passthroughs; flush on timeout → ESC emitted; mid-paste timeout →
  paste continues uninterrupted; false-alarm end marker → absorbed into paste.
- `bracketed_paste=False` (default): existing `run()` tests unchanged.

**Interactions:**
- C1 (preprocess_key): passthrough events from the paste SM go through `preprocess_key` before
  `dispatch_key` — the `_dispatch_paste_event` helper handles this. If C1 is not opted in
  (`key_preprocessor=None`), the None-check short-circuits to `dispatch_key` directly.

---

## Capability 7 — Configurable Command-Keymap

**Status:** largely already extensible via `AppSettings.keys`. This section documents what works
today, what was worked around in acraflow, and where the remaining gap is.

**What is already extensible today (no base change needed):**

`AppSettings(keys: Dict[str, str])` maps single printable-char strings to one of the five
named normal-mode commands: `'quit'`, `'prompt'`, `'mode_cycle'`, `'palette'`, `'traverse'`.
Passing a custom dict drops unwanted bindings and rebinds or removes others:

```python
# Drop s/m/c/q; keep only '/' → palette (the acraflow pattern):
AppModel(settings=AppSettings(keys={'/' : 'palette'}))
```

Widget-opening F-keys are on `AppModel` via `AppSettings` (not `keys`). The acraflow approach
(`AppSettings(..., widget_keys={curses.KEY_F2: 'traces', curses.KEY_F3: 'pipeline'})`) requires
a `widget_keys` field if it does not already exist — check whether `AppSettings` already carries
this and add it if not.

**What is NOT extensible today (and requires C1 / preprocess_key):**

Binding a key to a NEW command verb — one not in the five named ones (`quit/prompt/mode_cycle/
palette/traverse`) — requires C1 (the `preprocess_key` hook). The hook runs before `dispatch_key`
and returns True to consume the key, so custom commands fire before the base dispatch sees it.
There is no need to add command names to the base for consumer-defined behavior.

**One small addition to consider:** expose `AppSettings.widget_keys: Dict[int, str]` as an
official field (if not already present) so F-key → widget bindings are a first-class setting
rather than a downstream convention. Scope this conservatively: add the field if absent; wiring
it in `keymap._dispatch_normal` is a separate mechanical step.

**SRP home:** `glyfi/ui/settings.py` for the field addition; `glyfi/ui/keymap.py` for the
dispatch wiring of `widget_keys`.

**Reference impl:** `acraflow/glyfi_client/pipeline_app.py:_CHAT_KEYS`,
`build_pipeline_viewmodel` (the `AppSettings(keys=..., widget_keys=...)` construction pattern).

---

## Implementation Order (for the opus implementer)

Recommended build order to minimize interdependence:

1. **C3** — `glyfi/ui/list_window.py` + `_palette_overlay` change. Pure module; no hook wiring.
2. **C6** — `glyfi/ui/paste_input.py` (pure SM port); `CursesView.__init__` `bracketed_paste`
   flag + `run()` paste-aware loop.
3. **C1** — `CursesView.__init__` `key_preprocessor` + `run()` wiring. Tiny change; high impact.
4. **C2a** — `VisualRow.color_role` field. One-line dataclass change; all existing tests pass.
5. **C2b** — `CursesView.__init__` `row_classifier` + `_blit_region` per-row logic.
6. **C4** — `CursesView.__init__` `pre_render` + `render()` hook. Prerequisite for C5.
7. **C5** — `glyfi/ui/input_painter.py` + `RegionPainter.__init__` `post_paint` + `_do_paint`
   rename.
8. **C7** — audit `AppSettings` for `widget_keys`; add if absent; wire in `keymap`.

After each step: run `python -m pytest -q` in the worktree. The suite must stay GREEN.

---

## Trickiest Seams (watch list for implementer)

1. **C5: the `paint()` rename to `_do_paint()`** — `HeadlessView.render` calls
   `self._painter.paint(viewmodel, self.layout)` (line 515 in view.py). After the rename, the
   public `paint()` now wraps `_do_paint()` + `post_paint`. `HeadlessView` is unchanged since it
   calls the public `paint()`. However, every test that mocks or subclasses `RegionPainter` and
   overrides `paint()` must be checked — they override the public method (correct), but any that
   override `_do_paint()` (unlikely since it's new) would be wrong. Audit all tests that
   subclass `RegionPainter`.

2. **C6+C1 loop interaction** — the paste-aware `run()` must keep `preprocess_key` in the
   passthrough event path AND in the non-paste path. If C6 is opted in but C1 is not
   (`key_preprocessor=None`), the None check must still short-circuit correctly. The
   `_dispatch_paste_event` helper centralizes this; do not duplicate the logic.

3. **C2b select-override order (G38)** — the `if whole_area or (sel_row is not None and row ==
   sel_row)` guard must appear FIRST, before the `row_classifier` branch. Getting this wrong
   makes selected rows show their content color instead of the select highlight — an a11y failure
   that is invisible in automated tests but obvious in a live terminal.

4. **C4 timing (G35)** — `pre_render` fires before `self._current_size()`, not after. If the
   implementer places the hook between `size = self._current_size()` and `viewmodel.resize(size)`,
   the layout still sees the old settings. Place it at the very top of `render()`.

5. **C3 palette indicator row count** — the `↑ N more` / `↓ N more` indicator rows consume 1
   row each from the available height, so `avail = height - num_ind` must be recalculated after
   the first pass determines whether each indicator is needed. The acraflow two-pass logic in
   `_ExtPainter._palette_overlay` handles this correctly; port it exactly.

---

## Baseline

Glyfi test suite: **524 passed in 1.89s** on `feat/generic-view-plumbing` before any changes.
All implementation steps must keep the suite at 524+ passing with 0 failures.
