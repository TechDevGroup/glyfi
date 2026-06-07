# Testing

glyfi is built for testability: the curses runtime is a thin adapter, and the substance
lives behind pure, injectable seams you can drive headless. This doc covers running the
suite, the testability seams, and writing a headless flow.

---

## Running the suite

```bash
pip install -e .[dev]      # installs pytest
python -m pytest -q        # run the whole suite
```

Run a subset:

```bash
python -m pytest tests/test_viewmodel.py -q
python -m pytest -k openai -q
python -m pytest -q -x      # stop at the first failure
```

`testpaths = ["tests"]` is configured in `pyproject.toml`, so a bare `pytest` finds the
suite. The runtime has zero third-party dependencies, so the only thing `[dev]` adds is
`pytest` itself.

---

## The testability seams

Every hard-to-test concern is behind an injectable port, so tests run with no terminal, no
network, and deterministic time:

| seam              | port / real impl                          | test double                              |
| ----------------- | ----------------------------------------- | ---------------------------------------- |
| time              | `Clock` ABC → `MonotonicClock`            | `VirtualClock` (advance time by hand)    |
| the terminal      | `View` ABC → `CursesView`                 | `HeadlessView` (captures the `Painting`) |
| the server        | `Transport` ABC → `HttpTransport`         | `MockTransport` (scripted turns)         |
| events            | `EventBus`                                | `EventBus(record=True)` (assert the log) |
| one turn          | `Stepper` (the one-turn law)              | a stepper over a `MockTransport`         |

Because the View is pure, you assert on the rendered `Painting` directly — no screen
scraping. Because the clock is injectable, a TTL-expiry test advances a `VirtualClock`
instead of sleeping. Because the bus records, you assert exactly which events a transition
produced.

### VirtualClock

```python
from glyfi.ui.clock import VirtualClock

clock = VirtualClock(start=0.0)
clock.now()           # 0.0
clock.advance(5.0)    # 5.0  (fail loud on a negative dt)
```

### HeadlessView

```python
from glyfi.ui.view import HeadlessView, RegionPainter

view = HeadlessView(painter=RegionPainter(), w=80, h=24)
view.render(viewmodel)            # solves layout for the synthetic size, captures the frame
painting = view.painting
painting.lines("content")         # the painted lines of a region
```

### MockTransport

```python
from glyfi.uitest.fixtures import MockTransport

transport = MockTransport().script_response(
    subject="s1", mode="chat", text="hi", content="STAGED", seq_advance=1)
transport.sent                    # every TurnRequest it received (assert there was exactly one)
```

---

## Writing a headless flow (the quick path)

The fastest way to drive the live app is the `AppDriver`:

```python
from glyfi.ui.driver import build_headless_driver
from glyfi.ui.events import TurnRecorded

def test_palette_opens_config(make_viewmodel):
    vm = make_viewmodel()                     # however your suite builds an AppViewModel
    driver = build_headless_driver(vm)        # recording bus + HeadlessView

    driver.press(ord('/'))                    # open the palette
    driver.type_text('config')                # filter to 'config'
    driver.press(10)                          # Enter → run it

    assert driver.vm.mode_ui == 'CONFIG'
    assert 'state' in driver.painting.highlight_cells
```

Asserting on time + events:

```python
from glyfi.ui.events import Tick, StatusPushed

driver.clear_events()
driver.tick(10.0)                              # advance the VirtualClock past the status TTL
assert driver.status_line() == ''              # the ephemeral status auto-cleared
assert driver.events_of(Tick)                  # a Tick was emitted
```

For the higher-level `given/when/then` flows, the constraint DSL, and the natural-language
scenario layer, see [bdd.md](bdd.md).

---

## Testing a plugin

A handler is pure — call it directly with a built invocation and a stub context, and assert
on the returned `CommandResult` (no app needed). See the reference
`tests` for `refplugin` (echo/ping) and the OpenAI client/widget tests
(`test_openai_client.py`, `test_openai_pane_widget.py`), which stub the network via the
injectable `fetch` seam (see [openai-pane.md](openai-pane.md#the-injectable-fetch-seam-for-tests)).
