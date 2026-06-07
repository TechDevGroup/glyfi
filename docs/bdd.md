# BDD / uitest harness

glyfi ships a headless behaviour-driven test harness that drives the **real** MVVM surface
with a mocked transport and a virtual clock — fully headless and CI-safe (no terminal, no
network, no wall-clock). Every runnable example below is framed around the generic transport
or the OpenAI pane / palette / config — the harness asserts on the app's own behaviour.

The harness layers, bottom-up:

```
 AppDriver            programmatic drive surface over the live ViewModel (glyfi/ui/driver.py)
 MockTransport        a scripted Transport double (no network)
 Probe / Constraint   snapshot the app + a composable assertion DSL
 actions (Step verbs) Press / Type / Invoke / Submit / Tab / Tick / WaitUntil / Expect …
 Flow given/when/then run fixtures → steps → check constraints
 Scenario / Feature   a phrase registry mapping natural language → flows (the .feature mirror)
```

The human-readable spec mirror lives at `glyfi/uitest/specs/core.feature`.

---

## The headless driver (the foundation)

`glyfi/ui/driver.py::AppDriver` is the drive seam. `build_headless_driver(viewmodel)` wires
a recording bus so you can assert events. The drive calls chain:

```python
from glyfi.ui.driver import build_headless_driver

driver = build_headless_driver(viewmodel)        # recording bus + HeadlessView
driver.press(ord('/'))                            # feed a key through the real modal dispatch
driver.type_text('config')                        # type into the active input target
driver.press(10)                                  # Enter (run the exact-name command)

assert driver.vm.mode_ui == 'CONFIG'
```

| drive call          | does                                                              |
| ------------------- | ---------------------------------------------------------------- |
| `press(key)`        | feed a curses key code through the same `dispatch_key` the runtime uses |
| `invoke(name)`      | run a named palette command or same-named VM method (fail loud on unknown) |
| `type_text(text)`   | type into the active target (PALETTE filter / PROMPT field / NORMAL buffer) |
| `submit()`          | submit the NORMAL input line (emits `InputSubmitted`)            |
| `tick(dt)`          | advance the `VirtualClock` by `dt` + emit `Tick` (expires the ticker TTL) |
| `resize(w, h)`      | resize the synthetic terminal and repaint                        |

Read calls: `region(name)`, `status_line()`, `input_line()`, `painting`, plus the event
helpers `events`, `events_of(T)`, `last(T)`, `clear_events()` (see [events.md](events.md)).
`tick` requires a `VirtualClock` on the ViewModel — deterministic time, never wall-clock.

---

## MockTransport (no network)

`MockTransport` is a scripted `Transport` double. Script exact responses and faults; an
unscripted send falls back to a default echo:

```python
from glyfi.uitest.fixtures import MockTransport

transport = (MockTransport()
    .script_response(subject="subj-7", mode="chat", text="send it",
                     content="STAGED-7", seq_advance=1)
    .script_fault(subject="subj-9", mode="chat", text="forbidden",
                  message="forbidden", type="permission", code=403))
```

`MockTransport.ANY` (`'*'`) is a wildcard for any subject/mode/text. `transport.sent`
records every `TurnRequest` it received — assert on it to prove **exactly one** request was
issued (the one-turn law).

---

## Fixtures

`glyfi/uitest/fixtures.py` builds ready-to-drive apps. Compose a base fixture (`fresh_app`)
with refining fixtures:

| fixture                          | sets up                                                        |
| -------------------------------- | ------------------------------------------------------------- |
| `fresh_app(size, config, transport)` | a fresh app over a `MockTransport` + a recording bus + a `VirtualClock` (the BASE fixture) |
| `with_subjects(listing)`         | a scripted `/v1/subjects` listing                              |
| `scripted_server(script)`        | a `MockTransport` with scripted turns                          |
| `seeded_transcript(turns, mode)` | walks `vm.step` once per turn (honoring the one-turn law)      |
| `at_size(w, h)`                  | a specific synthetic terminal size                            |
| `with_prompt_entry(subject, text)` | wires `vm.prompt_seam` to supply one (subject, text) headlessly |

`build_mock_context(transport, …)` returns a `RunContext` (a driver + a `VirtualClock` +
a trace) directly when you want to skip the fixture layer.

---

## The constraint DSL

`glyfi/uitest/constraints.py` snapshots the app into a `Probe` and offers composable
`Constraint` builders. The named builders:

```
region_contains  region_line  status_is  status_blank  status_contains
input_is  input_contains  mode_is  highlighted  cell_highlighted
event_emitted  event_count  slot_bound  transcript_len  seq_is  selected_is
no_ellipsis  caret_present
```

…plus the combinators `all_of` / `any_of` / `not_` (and `&` / `|` / `~` on a `Constraint`).

There is also a terse recursive-descent **spec parser**, `parse_constraint(spec)`, with a
small grammar (`&`, `|`, `!`, `()`, `key==value`, `name(args)`):

```python
from glyfi.uitest.constraints import parse_constraint, Probe

c = parse_constraint("mode==CONFIG & cell_highlighted(state)")
result = c.check(Probe.of(driver))
assert result.ok
```

---

## Step verbs

`glyfi/uitest/actions.py` wraps drive calls as composable `Step` verbs (each snapshots a
`Probe` after applying): `Press`, `Type`, `Invoke`, `Submit`, `Tab`, `Tick`, `Delay`,
`WaitUntil`, `Expect`, `ClearEvents`, `Resize`. `WaitUntil` polls by advancing the
`VirtualClock` (`DEFAULT_WAIT_TIMEOUT` / `DEFAULT_WAIT_POLL`), so a TTL expiry test never
sleeps on the wall clock.

---

## Flows (given / when / then)

`glyfi/uitest/flow.py::Flow` runs fixtures in order, then steps, then checks constraints
against the final `Probe` (teardown reverses in a `finally`). It fails loud if there is no
base fixture or no THEN.

```python
from glyfi.uitest.flow import Flow
from glyfi.uitest.fixtures import fresh_app
from glyfi.uitest.actions import Press, Type, Expect
from glyfi.uitest.constraints import parse_constraint

result = (Flow()
    .given(fresh_app())
    .when(Press(ord('/')), Type('config'), Press(10))
    .then(parse_constraint("mode==CONFIG & cell_highlighted(state)"))
    .run())

assert result.ok
```

---

## Scenarios, Features, and the phrase registry

`glyfi/uitest/bdd.py` maps natural-language phrases (`Given`/`When`/`Then`) onto the
fixtures / actions / constraints via a `Phrase` registry, so a `Scenario` reads like the
`.feature` mirror. The built-in vocabulary covers the core flows: a fresh app, the palette,
the OpenAI pane, the ticker, input history, bottom-anchored content, and the one-turn law.

The runnable scenarios mirror `glyfi/uitest/specs/core.feature`. Examples from it:

```gherkin
Feature: command palette
  Scenario: filter to config and open it
    Given a fresh app
    When  I press '/'
    And   I type 'config'
    And   I press <Enter>
    Then  the app conforms to "mode==CONFIG & cell_highlighted(state)"

Feature: the OpenAI context pane
  Scenario: /ask from the palette opens the OpenAI pane
    Given a fresh app with the openai_pane plugin loaded
    When  I press '/'
    And   I type 'ask hello there'
    And   I press <Enter>
    Then  the OpenAI pane is the active widget

Feature: the one-turn law (no auto-loop)
  Scenario: a prompt walks EXACTLY one turn
    Given a fresh app with a scripted transport
    And   the next prompt is (subj-7, "send it")
    When  I clear events
    And   I invoke 'request_prompt'
    Then  the transcript length is 1
    And   exactly 1 "TurnRecorded" event was emitted
    And   the seq is 1
    And   region 'content' contains "STAGED-7"
```

`Feature.run()` / `run_strict()` compile each scenario to a flow and produce a
`FeatureReport`.

---

## Generating spec docs

The runnable specs are exposed as a concern-grouped catalog in `glyfi/uitest/catalog.py`
(`concerns()`, `specs_for(concern)`, `all_specs()`), and a generator turns each spec into a
Markdown document:

```
python -m glyfi.contrib.docs_capture.specdocs --write
```

This writes a per-spec tree under `docs/specs/`:

```
docs/specs/README.md                      # the index: every concern -> its specs
docs/specs/<concern-slug>/<spec-slug>.md  # one file per scenario
```

Each spec file shows the scenario's Given/When/Then text followed by a **full-frame screen
capture after every step**. The docs come from the **same specs the tests run** —
`tests/uitest/test_spec_catalog.py` iterates the whole catalog and `run_strict()`s each spec,
and the generator renders those same flows, so a doc cannot drift from tested behavior. Output
is deterministic and trace-free (the cwd / clock detail fields are pinned to neutral
placeholders; the virtual clock + mocked transport mean no network — the context-pane spec
captures the no-key state). With no flag the command prints the index plus a written-file count
instead of writing.

---

## Runtime registries

`glyfi/uitest/runtime.py` exposes `registries()` (the registered actions / constraints /
fixtures / observed events as a `FrameworkRegistries`) and `new_context(transport=None,
**kwargs)` for building a fresh `RunContext`. These are the discovery surface a custom step
verb or constraint registers into.

> Every runnable scenario here drives the generic transport (`/v1/turn`, `/v1/subjects`) or
> the OpenAI pane via its public command/widget seams. No other backend endpoint is
> involved.
