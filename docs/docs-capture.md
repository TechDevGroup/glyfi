# Documentation capture

glyfi can render its **live UI** into Markdown. The same `Painting` the curses View paints
to the terminal is composed into a deterministic full-screen grid and wrapped as a
Markdown-compliant **screen fence** — so a runbook, a changelog, or a BDD walkthrough can
embed exactly what the operator would see.

This is an ordinary first-party plugin (`glyfi/contrib/docs_capture/`): it imports only the
public `glyfi.ui` / `glyfi.plugins` / `glyfi.uitest` contracts + stdlib. No core privileges,
no network.

Three layers:

- **`capture.py`** — the pure Markdown render target over a `Painting` + solved layout + `Size`.
- **`markdown_flow.py`** — a BDD flow trace → a per-step Markdown document.
- **`plugin.py`** + `glyfi/plugins/builtin/docs_capture.json` — the `/capture` command.

`gallery.py` is the dogfood: it drives a headless app through representative states and emits
one Markdown document.

---

## The screen-fence format

A screen fence is a Markdown fenced code block carrying the captured screen rows. It is
**MVVM-consistent**: capture reads the already-painted `Painting`, it never re-implements
rendering.

```
~~~text
┌─ screen ─────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: (none) · q quits   │
│ ...                                           │
└───────────────────────────────────────────────┘
~~~
```

### MD-compliance guarantees

- **Tilde fence.** The fence delimiter is a run of `~` (never a backtick), so captured rows
  that contain backticks (`` ``` ``) cannot close the block early.
- **Escalation.** If a captured row somehow contains a run of `~`, the fence is made *longer*
  than that run, so the block is never closed by its own content.
- **Constant width.** Every row is padded to one common width, so columns line up under any
  monospace renderer.
- **Clean box border (optional).** With `border=True` a box is drawn around the rows
  (`BORDER_*` / `FRAME_*` named chars) with an optional `title` set into the top edge. The
  horizontal edges span the body width plus the frame padding, so the corners are flush with
  the vertical edges.

Capture is **deterministic** — the same painting/layout/size always yields the same Markdown.

---

## `capture.py` API

```python
from glyfi.contrib.docs_capture.capture import (
    frame_rows, region_rows, sub_rows, screen_fence, markdown_screen,
)
from glyfi.ui.layout import Rect

# full-screen grid: each region's lines placed at its Rect (x, y), gaps blank-filled, padded to size.w
rows = frame_rows(painting, layout, size)

# one named region's lines, padded to a common width
title_rows = region_rows(painting, 'title')

# slice a column/row sub-rectangle (e.g. a palette area or a slot) out of a row block
slot = sub_rows(rows, Rect(x=0, y=0, w=20, h=3))

# wrap any row block as a Markdown screen fence
md = screen_fence(rows, border=True, title='screen')

# convenience over a live AppDriver (full frame / one region / a sub-rect)
md = markdown_screen(driver)                       # full frame
md = markdown_screen(driver, region='content')     # one region
md = markdown_screen(driver, sub=Rect(0, 0, 40, 5))# a sub-rectangle of the frame
```

`MarkdownView(size)` is a `View` whose `render(vm)` produces the screen fence — making
"Markdown is just another View target" explicit. It paints with the same `RegionPainter` the
curses and headless Views use.

---

## The `/capture` command

`/capture [region] [--save <path>]`

- with no argument it captures the **full frame**;
- with a `region` argument (`/capture content`) it captures just that named region;
- the resulting screen fence is pushed into the content view (and a status is shown);
- with `--save <path>` it **also** writes the Markdown document to `path` (parent dirs are
  created).

If the capture capability is not wired into the command context the command **fails
loud-soft** — it shows a clear status and never crashes.

The command is registered by the builtin manifest
`glyfi/plugins/builtin/docs_capture.json` under the default allowlist (the handler resolves
under `glyfi.contrib`, no env needed).

### The capture seam

`/capture` reads the live frame through two **optional, additive** capabilities on
`CommandContext` (mirrored on `WidgetContext`):

```python
capture_frame:  Optional[Callable[[], List[str]]] = None   # the full frame as composed rows
capture_region: Optional[Callable[[str], List[str]]] = None# one named region's rows
```

They default to `None` (so any context that never wires them is unchanged) and are wired in
`AppViewModel.command_context()` to `capture_frame_rows()` / `capture_region_rows()`, which
paint the current state through the `RegionPainter` and compose it.

### Configuration

`--save` takes an **explicit path** — there is no implicit output directory, so capture
never writes anywhere you did not name. Point it wherever your docs live, e.g.
`/capture --save docs/screens/config.md`.

---

## BDD flow → Markdown (`flow_to_markdown`)

A `Flow` records a `TraceEntry` per `when` step (the verb label + the `Probe` taken right
after it drove the app). `flow_to_markdown` turns that trace into a walkthrough: **one
section per step**, each with a heading (the step label) and a screen fence of the pertinent
regions — so the reader sees the UI state *between* the steps.

The stored `Probe` carries the painted region lines but not full screen geometry, so a
step's screen is rendered as the pertinent regions **stacked**, each clearly labeled
(`── content ──`) and padded to a constant width inside one fence.

```python
from glyfi.uitest.actions import Invoke, Type
from glyfi.uitest.constraints import mode_is
from glyfi.uitest.fixtures import fresh_app
from glyfi.uitest.flow import Flow
from glyfi.contrib.docs_capture.markdown_flow import flow_to_markdown, write_markdown

flow = (Flow('palette walkthrough')
        .given(fresh_app())
        .when(Invoke('open_palette'), Type('co'), Invoke('open_config'))
        .then(mode_is('CONFIG')))

result = flow.run()                                # a FlowResult (a RunContext also works)
md = flow_to_markdown(result, title='Walkthrough',
                      intro='open the palette, filter, open config',
                      regions=None)                # None = the pertinent set; or pass ['content', 'input']
write_markdown(md, 'docs/walkthrough.md')
```

`flow_to_markdown` accepts a `FlowResult` **or** a `RunContext` (whatever carries the
trace), and fails loud on anything else.

---

## Regenerating `docs/ui-gallery.md` and `docs/walkthrough.md`

The gallery drives a headless app through representative states (fresh screen, filtered
palette, config editor, prompt modal, the OpenAI pane with no API key) and emits one
Markdown document — plus a BDD walkthrough.

```bash
python -m glyfi.contrib.docs_capture.gallery          # prints the gallery + walkthrough MD
```

To regenerate **both** checked-in artifacts — `docs/ui-gallery.md` (the 5 UI states) and
`docs/walkthrough.md` (the per-step BDD walkthrough) — pass `--write`:

```bash
python -m glyfi.contrib.docs_capture.gallery --write  # writes docs/ui-gallery.md + docs/walkthrough.md
```

`--write` calls `gallery.write_docs()`; with no flag the command prints to stdout unchanged.

The OpenAI pane section is captured with **no API key configured**, so its fail-loud line is
the rendered content — no request is ever made.

---

## Files

- `glyfi/contrib/docs_capture/capture.py` — the pure Markdown render target.
- `glyfi/contrib/docs_capture/markdown_flow.py` — the BDD-trace bridge + the file sink.
- `glyfi/contrib/docs_capture/plugin.py` — the `/capture` handler.
- `glyfi/plugins/builtin/docs_capture.json` — the command manifest.
- `glyfi/contrib/docs_capture/gallery.py` — the dogfood gallery + walkthrough.
- `glyfi/contrib/docs_capture/detfields.py` — the shared deterministic detail-field pin.
- `glyfi/contrib/docs_capture/specdocs.py` — the per-spec doc generator
  (`python -m glyfi.contrib.docs_capture.specdocs --write` → `docs/specs/**`).
- `glyfi/uitest/catalog.py` — the concern-grouped runnable spec catalog the generator reads.
- Tests: `tests/test_docs_capture.py`, `tests/test_docs_markdown_flow.py`,
  `tests/test_docs_capture_plugin.py`.
