import pytest

from glyfi.ui.events import (
    Event, KeyPressed, CommandInvoked, ModeChanged, TurnRecorded, StatusPushed,
    TickerCycled, MenuMoved, SlotBound, InputSubmitted, HistoryNavigated, Resized, Tick,
    EVENT_TYPES, EventBus,
)


def test_event_types_registry_order():
    assert EVENT_TYPES == (
        KeyPressed, CommandInvoked, ModeChanged, TurnRecorded, StatusPushed, TickerCycled,
        MenuMoved, SlotBound, InputSubmitted, HistoryNavigated, Resized, Tick,
    )
    for t in EVENT_TYPES:
        assert issubclass(t, Event)


def test_event_fields():
    assert KeyPressed(key=5, mode_ui='NORMAL').key == 5
    assert KeyPressed(key=5, mode_ui='NORMAL').mode_ui == 'NORMAL'
    assert CommandInvoked(name='prompt').name == 'prompt'
    mc = ModeChanged(kind='op', value='chat')
    assert (mc.kind, mc.value) == ('op', 'chat')
    assert TurnRecorded(index=2, ok=True).ok is True
    assert StatusPushed(text='hi', at=1.0).at == 1.0
    assert TickerCycled(provider='stats').provider == 'stats'
    assert MenuMoved(menu='palette', index=3).index == 3
    sb = SlotBound(group='state', position=1, alias='mode')
    assert (sb.group, sb.position, sb.alias) == ('state', 1, 'mode')
    assert InputSubmitted(text='x').text == 'x'
    hn = HistoryNavigated(direction='older', buffer='b')
    assert (hn.direction, hn.buffer) == ('older', 'b')
    assert Resized(w=80, h=24).w == 80
    assert Tick(now=2.5).now == 2.5


def test_events_are_frozen():
    e = Tick(now=1.0)
    with pytest.raises(Exception):
        e.now = 2.0


def test_subscribe_and_dispatch_by_concrete_type():
    bus = EventBus()
    seen = []
    bus.subscribe(KeyPressed, lambda e: seen.append(e))
    bus.emit(KeyPressed(key=1, mode_ui='NORMAL'))
    bus.emit(Tick(now=1.0))     # different type -> not delivered
    assert len(seen) == 1
    assert seen[0].key == 1


def test_subscribe_rejects_non_event():
    bus = EventBus()
    with pytest.raises(TypeError):
        bus.subscribe(int, lambda e: None)
    with pytest.raises(TypeError):
        bus.subscribe(object(), lambda e: None)


def test_record_log_and_queries():
    bus = EventBus(record=True)
    bus.emit(KeyPressed(key=1, mode_ui='NORMAL'))
    bus.emit(KeyPressed(key=2, mode_ui='PALETTE'))
    bus.emit(Tick(now=3.0))
    assert len(bus.log) == 3
    keys = bus.events_of(KeyPressed)
    assert [e.key for e in keys] == [1, 2]
    assert bus.last(KeyPressed).key == 2
    assert bus.last(Resized) is None
    bus.clear_log()
    assert bus.log == []


def test_record_off_by_default():
    bus = EventBus()
    bus.emit(Tick(now=1.0))
    assert bus.log == []
    assert bus.events_of(Tick) == []
