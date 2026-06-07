# Events

glyfi is event-driven: every ViewModel state transition emits a **typed, immutable event**
onto a shared `EventBus`. Subscribers react without the emitter knowing they exist
(open/closed). This document lists every event, when it fires, and how to subscribe and
assert.

Module: `glyfi/ui/events.py`.

---

## The event types

All events are frozen dataclasses subclassing `Event`. The bus dispatches by the event's
**concrete type** — a handler subscribed to `StatusPushed` sees only `StatusPushed`.

| event              | fields                                  | fires when…                                          |
| ------------------ | --------------------------------------- | ---------------------------------------------------- |
| `KeyPressed`       | `key: int`, `mode_ui: str`              | a raw key reaches the ViewModel (curses adapter or headless driver fed it). `mode_ui` is the modal state at press time. |
| `CommandInvoked`   | `name: str`                             | a named command runs (from the palette, a key, or the driver). |
| `ModeChanged`      | `kind: str`, `value: str`               | the mode label changed (`kind='op'`) or the modal UI state changed (`kind='ui'`). |
| `TurnRecorded`     | `index: int`, `ok: bool`                | a turn was recorded onto the transcript; `ok` is the outcome. |
| `StatusPushed`     | `text: str`, `at: float`                | a status message was pushed onto the ephemeral ticker (`at` = clock time). |
| `TickerCycled`     | `provider: str`                         | the ticker ring advanced (`Tab`) to a new provider. |
| `MenuMoved`        | `menu: str`, `index: int`               | a palette/config menu cursor moved; `menu` is `'palette'` or `'config'`. |
| `SlotBound`        | `group: str`, `position: int`, `alias: str` | a config slot was rebound to a field alias.    |
| `InputSubmitted`   | `text: str`                             | the operator submitted the input line (Enter on a non-palette buffer). |
| `HistoryNavigated` | `direction: str`, `buffer: str`         | `↑`/`↓` walked the input history; `direction` is `'older'`/`'newer'`. |
| `Resized`          | `w: int`, `h: int`                      | the layout re-solved for new terminal dimensions.   |
| `Tick`             | `now: float`                            | time advanced — a runtime getch-timeout tick or a test clock advance. |

The full registry, in order:

```python
from glyfi.ui.events import EVENT_TYPES
# (KeyPressed, CommandInvoked, ModeChanged, TurnRecorded, StatusPushed, TickerCycled,
#  MenuMoved, SlotBound, InputSubmitted, HistoryNavigated, Resized, Tick)
```

> `ModeChanged.kind` is `'op'` for a mode-label cycle and `'ui'` for a modal UI state
> change.

---

## The bus

```python
@dataclass
class EventBus:
    record: bool = False          # keep a log of emitted events?
    log: List[Event] = ...
    def subscribe(self, event_type, handler) -> None
    def emit(self, event) -> None
    def clear_log(self) -> None
    def events_of(self, event_type) -> List[Event]
    def last(self, event_type) -> Optional[Event]
```

- `subscribe(type, handler)` registers a handler for **one** concrete event type. Handlers
  fire in subscription order. It fails loud if `event_type` is not an `Event` subclass.
- `emit(event)` records the event iff `record` is on, then dispatches to every handler
  subscribed to its concrete type. The emitter never names a subscriber.
- Recording is **off by default** so a long runtime session does not accrue an unbounded
  list. The headless test driver turns it on.

---

## Subscribing

```python
from glyfi.ui.events import EventBus, TurnRecorded, StatusPushed

bus = EventBus()

def on_turn(event: TurnRecorded) -> None:
    print(f"turn {event.index} ok={event.ok}")

bus.subscribe(TurnRecorded, on_turn)
bus.subscribe(StatusPushed, lambda e: print("status:", e.text))
```

The ViewModel already owns a bus (`vm.bus`); subscribe to it to react to live transitions:

```python
vm.bus.subscribe(TurnRecorded, on_turn)
```

---

## Recording and asserting (the test pattern)

The headless `AppDriver` (`glyfi/ui/driver.py`) turns recording on so you can assert which
events a driven action produced. `build_headless_driver` does this for you:

```python
from glyfi.ui.driver import build_headless_driver
from glyfi.ui.events import KeyPressed, CommandInvoked

driver = build_headless_driver(viewmodel)   # bus.record is now on
driver.press(ord('/'))                       # open the palette

assert driver.events_of(KeyPressed)          # a KeyPressed was recorded
assert driver.last(CommandInvoked) is None   # nothing ran yet

driver.clear_events()                        # scope the next assertions
```

Driver event helpers:

| method                | returns                                            |
| --------------------- | -------------------------------------------------- |
| `driver.events`       | the full recorded log (`List[Event]`)              |
| `driver.events_of(T)` | recorded events of type `T`                         |
| `driver.last(T)`      | the most recent event of type `T`, or `None`       |
| `driver.clear_events()` | clear the log (scope the next action's assertions) |

Under the hood these delegate to `bus.events_of` / `bus.last` / `bus.clear_log`. See
[bdd.md](bdd.md) and [testing.md](testing.md) for full flows.
