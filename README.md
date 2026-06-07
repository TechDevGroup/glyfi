# glyfi

**glyfi** is an extensible, configurable curses TUI framework for terminal apps — a
clean, stdlib-only skeleton you wrap around an agentic / LLM-driven dev workflow (or any
turn-based terminal app). It gives you the parts that are tedious to get right:

- an **MVVM curses core** (a dumb Model, a ViewModel "brain", a pure View);
- a **pure layout solver** with responsive smush;
- a **508/WCAG-aligned semantic theme** (roles-not-hues, focus is always a printed marker);
- a **slash-command palette** + an `args → handler` pipeline;
- a **plugin framework** (in-code / filesystem-manifest / system-API sources);
- a **widget framework** (self-contained content-region overlays);
- an injectable **clock / ticker / input-history**;
- a **persisted config store + editor**;
- a generic **network transport port** + a **one-turn-at-a-time stepper**;
- one first-party reference LLM plugin (an **OpenAI chat-completions context pane**);
- a headless **driver** seam for deterministic tests.

The runtime is **stdlib-only** (Python `curses` + `urllib`). The only optional dev
dependency is `pytest`. Requires **Python ≥ 3.10**.

- Import package: `glyfi` · CLI: `glyfi` · env prefix: `GLYFI_`.

---

## Install

```bash
pip install -e .[dev]
```

This installs `glyfi` in editable mode with the `dev` extra (`pytest`). The runtime has
zero third-party dependencies.

Smoke-check the install:

```bash
python -c "import glyfi; print(glyfi.__version__)"
python -m pytest -q
```

---

## Quickstart

`glyfi` is HTTP-only: point it at a server that speaks its neutral turn protocol
(`POST /v1/turn`, `GET /v1/subjects`).

```bash
# launch the curses app against a running server
glyfi --base-url http://127.0.0.1:8800

# run a specific session id
glyfi --base-url http://127.0.0.1:8800 --session my-session

# discover the server-exposed routable subjects, then exit (no app launched)
glyfi --base-url http://127.0.0.1:8800 --list
```

If `--base-url` is omitted it falls back to `GLYFI_BASE_URL` (default
`http://127.0.0.1:8800`). See [`docs/config.md`](docs/config.md) for the full `GLYFI_*`
environment.

You can also run it as a module:

```bash
python -m glyfi --base-url http://127.0.0.1:8800
```

### The LLM context pane

The bundled first-party plugin opens an OpenAI chat-completions context pane from the
palette with `/ask`. Configure it via `GLYFI_OPENAI_*` env (see
[`docs/openai-pane.md`](docs/openai-pane.md)):

```bash
export GLYFI_OPENAI_API_KEY=sk-...
export GLYFI_OPENAI_MODEL=gpt-4o-mini   # optional; this is the default
glyfi --base-url http://127.0.0.1:8800
# then in the app: press '/', choose 'ask', or type:  /ask summarize this repo
```

---

## Key bindings

NORMAL mode (all rebindable via a custom `AppSettings`):

| key            | action                                                        |
| -------------- | ------------------------------------------------------------- |
| `s`            | open the prompt form (subject + text) and walk **one** turn   |
| `m`            | cycle the current mode label                                  |
| `/`            | open the slash-command palette                                |
| `c`            | enter content traversal (a wrap-aware line caret)             |
| `PgUp` / `PgDn`| scroll the content view (page, minus the overlap sliver)      |
| `↑` / `↓`      | recall older / newer input history                            |
| `Tab`          | cycle the ephemeral status-ticker ring                        |
| `Ctrl-U` / `Ctrl-D` | scroll half a page up / down                            |
| `q`            | quit (destructive-confirm: press `q` again to confirm)        |

Inside any menu (palette / config / widget): `↑`/`↓` navigate, typing filters,
`Enter` chooses, `Esc` / `←` / `Backspace` goes back one level or closes.

---

## Architecture at a glance

```
        ┌──────────────────────────────────────────────────────────────┐
        │ Transport (port)  ──HTTP──▶  /v1/turn  ·  /v1/subjects         │
        │   HttpTransport (urllib) | MockTransport (tests)               │
        └───────────────┬──────────────────────────────────────────────┘
                        │ one TurnRequest / TurnResponse
                ┌───────▼───────┐
                │   Stepper     │  walks EXACTLY one turn, never loops
                └───────┬───────┘
                        │
   Model (dumb data) ───┤ AppModel · SessionState · TurnRecord
                        │
   ViewModel (brain) ───┤ AppViewModel — presentation state + commands
                        │   (request_prompt, cycle_mode, open_palette, ...)
                        │
                        ├──emit──▶ EventBus (typed) ──▶ subscribers
                        │
   View (pure) ─────────┤ RegionPainter → Painting → CursesView / HeadlessView
                        │
   Seams ───────────────┤ Plugins (commands+widgets) · Theme · Clock · Ticker
```

- **MVVM split.** The **Model** (`glyfi/ui/model.py`) is dumb data. The **ViewModel**
  (`glyfi/ui/viewmodel.py`) is the brain: all presentation state and commands. The
  **View** is pure — a `RegionPainter` turns the ViewModel into an immutable `Painting`,
  which either `CursesView` renders to a terminal or `HeadlessView` captures for tests.
- **Typed EventBus** (`glyfi/ui/events.py`). Every ViewModel transition emits a typed,
  immutable event; subscribers (repaint, ticker, the test driver) react without the
  emitter knowing they exist.
- **Plugin + widget seams.** Commands and widgets register through open/closed registries
  fed by plugin **sources** (in-code, filesystem manifest, system-API). Handler/factory
  references resolve under a NAMED allowlist.
- **Transport port + one-turn Stepper.** The `Transport` ABC is the only server seam; the
  `Stepper` walks exactly one turn per call and stops — it never loops, batches, or
  replays.

Full write-up: [`docs/architecture.md`](docs/architecture.md).

---

## Documentation

| doc | what it covers |
| --- | --- |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md)         | Operator runbook: run the app, every key, the palette, the config editor, the OpenAI pane, `--list`. |
| [`docs/architecture.md`](docs/architecture.md) | The MVVM split, the EventBus, the layout solver + smush, the Transport port + Stepper law. |
| [`docs/events.md`](docs/events.md)           | Every event type, when it fires, how to subscribe, and how the driver records + asserts events. |
| [`docs/theme-a11y.md`](docs/theme-a11y.md)   | The 508/WCAG semantic theme: roles, RED-for-destructive, printed focus markers, mono fallback. |
| [`docs/config.md`](docs/config.md)           | `GLYFI_*` env, the persisted `UserConfig` JSON, the slot/field alias registry, the config editor. |
| [`docs/plugins.md`](docs/plugins.md)         | Plugin authoring with a full copy-paste manifest + handler module example. |
| [`docs/widgets.md`](docs/widgets.md)         | Widget authoring: the lifecycle, the scoped `WidgetContext`, registering a factory. |
| [`docs/openai-pane.md`](docs/openai-pane.md) | The first-party OpenAI context pane — the canonical "LLM plugin" tutorial. |
| [`docs/bdd.md`](docs/bdd.md)                 | The BDD / uitest harness: flows, the constraint DSL, `MockTransport`, the headless driver. |
| [`docs/testing.md`](docs/testing.md)         | Running `pytest`, the testability seams, and writing a headless flow. |

---

## License

glyfi is released under the **glyfi Source-Available License, Version 1.0** — a custom,
source-available (NOT MIT / NOT OSI-approved) license. In short:

- You may **use, study, modify, strip down, and redistribute** the Software and your
  Derivative Works freely, in source or compiled form.
- **Attribution is mandatory:** keep the copyright notice and the license, and credit the
  original author (Landan Parker) in your source and in any user-facing "about" / docs of
  a Derivative Work.
- **Commercializing the Core** (selling it, or offering it as a paid hosted / SaaS service
  whose revenue is primarily attributable to the Core) requires **prior written
  permission**. Ordinary use, internal use, research, and building plugins/modules on top
  of glyfi do **not** require permission.

Separate commercial terms are available on request. See [`LICENSE`](LICENSE) for the full
text. Contact: **Landan Parker — landanparker@gmail.com**.
