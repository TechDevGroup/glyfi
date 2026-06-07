"""events -- the typed EventBus + NAMED event types: the event-driven spine the ViewModel emits onto.

Every ViewModel STATE TRANSITION emits a typed event onto a shared bus; subscribers (the curses View's
repaint, the ticker, a headless driver's capture) react WITHOUT the emitter knowing they exist.

SOLID:
  * OPEN/CLOSED -- ``emit`` references NO concrete subscriber. You add a subscriber with ``subscribe`` and the
    emitter is untouched; new event TYPES are new NAMED classes (no edit to the bus).
  * SRP -- each event is one NAMED fact (a key was pressed, a command was invoked, a turn was recorded, ...);
    each handler does ONE thing. The bus does ONE thing: route ``emit(event)`` to the handlers for its type.

Events are immutable data (frozen dataclasses). The bus dispatches by the event's CONCRETE TYPE -- a handler
subscribed to ``StatusPushed`` sees only ``StatusPushed`` events. Pure-importable: NO curses, stdlib only.

NAMED event types (one per ViewModel transition the framework observes):
  KeyPressed · CommandInvoked · ModeChanged · TurnRecorded · StatusPushed · TickerCycled · MenuMoved ·
  SlotBound · InputSubmitted · HistoryNavigated · Resized · Tick
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Type


# ===== the NAMED event types (immutable facts -- one per observed transition) ==============================

@dataclass(frozen=True)
class Event:
    """Base of every event -- a NAMED, immutable fact about a ViewModel transition. Dispatched by type."""


@dataclass(frozen=True)
class KeyPressed(Event):
    """A raw key reached the ViewModel (the curses adapter / headless driver fed it). ``key`` is the curses int."""
    key: int
    mode_ui: str


@dataclass(frozen=True)
class CommandInvoked(Event):
    """A NAMED command ran (palette / key / driver). ``name`` is the command/command-method name."""
    name: str


@dataclass(frozen=True)
class ModeChanged(Event):
    """The mode label or the modal UI state changed. ``kind`` is 'op' or 'ui'; ``value`` the new value."""
    kind: str
    value: str


@dataclass(frozen=True)
class TurnRecorded(Event):
    """A turn was recorded onto the transcript. ``index`` is the turn index; ``ok`` its outcome."""
    index: int
    ok: bool


@dataclass(frozen=True)
class StatusPushed(Event):
    """A status message was pushed onto the ephemeral ticker (it shows until its TTL elapses). ``text``/``at``."""
    text: str
    at: float


@dataclass(frozen=True)
class TickerCycled(Event):
    """The ticker ring advanced (Tab) to a new provider. ``provider`` is the now-active provider name."""
    provider: str


@dataclass(frozen=True)
class MenuMoved(Event):
    """A palette / config menu cursor moved. ``menu`` is 'palette' or 'config'; ``index`` the new row."""
    menu: str
    index: int


@dataclass(frozen=True)
class SlotBound(Event):
    """A config slot was rebound to a field alias. ``group``/``position``/``alias`` describe the bind."""
    group: str
    position: int
    alias: str


@dataclass(frozen=True)
class InputSubmitted(Event):
    """The operator submitted the input line (Enter on a non-palette buffer). ``text`` is the submitted text."""
    text: str


@dataclass(frozen=True)
class HistoryNavigated(Event):
    """Up/Down walked the input history. ``direction`` is 'older'/'newer'; ``buffer`` the restored buffer."""
    direction: str
    buffer: str


@dataclass(frozen=True)
class Resized(Event):
    """The layout re-solved for new terminal dims. ``w``/``h`` are the new size."""
    w: int
    h: int


@dataclass(frozen=True)
class Tick(Event):
    """Time advanced (a runtime getch-timeout tick / a test clock advance). ``now`` is the clock's reading."""
    now: float


# the full NAMED event-type registry (handy for the framework + a coverage check that every type is reachable).
EVENT_TYPES: Tuple[Type[Event], ...] = (
    KeyPressed, CommandInvoked, ModeChanged, TurnRecorded, StatusPushed, TickerCycled,
    MenuMoved, SlotBound, InputSubmitted, HistoryNavigated, Resized, Tick,
)


# ===== the bus (open/closed dispatch by concrete event type) ===============================================

Handler = Callable[[Event], None]


@dataclass
class EventBus:
    """A small typed pub/sub bus -- ``subscribe(type, handler)`` / ``emit(event)``; dispatch by concrete type.

    OPEN/CLOSED: ``emit`` never names a subscriber; subscribers register themselves. Handlers for a type fire in
    subscription order. ``record`` (optional) keeps an emitted-event log -- a headless driver reads it to assert
    the events a transition produced (the bus stays the single observation point; logging is off by default so a
    long runtime session does not accrue an unbounded list -- the driver turns it on).
    """
    _handlers: Dict[Type[Event], List[Handler]] = field(default_factory=dict)
    record: bool = False
    log: List[Event] = field(default_factory=list)

    def subscribe(self, event_type: Type[Event], handler: Handler) -> None:
        """Register ``handler`` for events of ``event_type`` (and only that concrete type). Fail loud on a non-type."""
        if not (isinstance(event_type, type) and issubclass(event_type, Event)):
            raise TypeError(f'subscribe: event_type must be an Event subclass, got {event_type!r}')
        self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: Event) -> None:
        """Dispatch ``event`` to every handler subscribed to its CONCRETE type. Emitter knows no subscriber."""
        if self.record:
            self.log.append(event)
        for handler in self._handlers.get(type(event), []):
            handler(event)

    def clear_log(self) -> None:
        """Drop the recorded-event log (a driver clears it between driven actions to scope its assertions)."""
        self.log.clear()

    def events_of(self, event_type: Type[Event]) -> List[Event]:
        """The recorded events of a given type (driver-side query; empty unless ``record`` was on)."""
        return [e for e in self.log if type(e) is event_type]

    def last(self, event_type: Type[Event]) -> Optional[Event]:
        """The most-recently recorded event of a type, or None (driver convenience)."""
        matches = self.events_of(event_type)
        return matches[-1] if matches else None
