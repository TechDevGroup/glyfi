import pytest

from glyfi.ui.clock import VirtualClock
from glyfi.ui import ticker
from glyfi.ui.ticker import (
    TICKER_STATUS, TICKER_HINTS, TICKER_STATS, TICKER_NOTICES,
    DEFAULT_STATUS_TTL_SECONDS, KEY_STATUS_TTL, INPUT_HINT,
    Ticker, TickerProvider, register_ticker, ticker_ring, ticker_provider,
)


class _Session:
    def __init__(self, seq=0):
        self.seq = seq


class _Model:
    def __init__(self, turn_count=0):
        self.turn_count = turn_count


class _VM:
    def __init__(self, last_status='', seq=0, turn_count=0, mode='chat', menu=False):
        self.last_status = last_status
        self.session = _Session(seq)
        self.model = _Model(turn_count)
        self.mode = mode
        self._menu = menu

    def menu_active(self):
        return self._menu


def test_named_provider_constants():
    assert TICKER_STATUS == 'status'
    assert TICKER_HINTS == 'hints'
    assert TICKER_STATS == 'stats'
    assert TICKER_NOTICES == 'notices'
    assert DEFAULT_STATUS_TTL_SECONDS == 4.0
    assert KEY_STATUS_TTL == 'status_ttl_seconds'


def test_input_hint_neutral():
    assert 'step' not in INPUT_HINT
    assert INPUT_HINT == 'type / for commands · ↑↓ history · Tab ticker'


def test_builtin_ring_order():
    assert ticker_ring()[:4] == [TICKER_STATUS, TICKER_HINTS, TICKER_STATS, TICKER_NOTICES]


def test_register_dup_fails_loud():
    with pytest.raises(ValueError):
        register_ticker(TICKER_STATUS, lambda vm: 'x')


def test_unknown_provider_fails_loud():
    with pytest.raises(KeyError):
        ticker_provider('nope')


def test_provider_stats_and_notices():
    vm = _VM(seq=3, turn_count=2, mode='chat')
    assert ticker_provider(TICKER_STATS).fn(vm) == 'turns 2 · seq 3'
    assert ticker_provider(TICKER_NOTICES).fn(vm) == 'mode chat'


def test_notices_has_no_scope():
    vm = _VM(mode='chat')
    assert 'scope' not in ticker_provider(TICKER_NOTICES).fn(vm)


def test_push_shows_until_ttl_then_blank():
    clk = VirtualClock()
    vm = _VM()
    t = Ticker(ttl_seconds=4.0)
    t.push('hello', clk)
    assert t.current(vm, clk) == 'hello'
    clk.advance(3.9)
    assert t.current(vm, clk) == 'hello'
    clk.advance(0.2)            # now past 4.0
    assert t.current(vm, clk) == ''


def test_ttl_suspended_while_menu_open():
    clk = VirtualClock()
    vm = _VM(menu=True)
    t = Ticker(ttl_seconds=1.0)
    t.push('held', clk)
    clk.advance(100.0)
    assert t.current(vm, clk) == 'held'    # suspended while menu up


def test_resume_rebases_ttl():
    clk = VirtualClock()
    vm = _VM(menu=True)
    t = Ticker(ttl_seconds=2.0)
    t.push('msg', clk)
    clk.advance(10.0)
    # menu closes -> resume re-stamps
    t.resume(clk)
    vm._menu = False
    assert t.current(vm, clk) == 'msg'
    clk.advance(1.9)
    assert t.current(vm, clk) == 'msg'
    clk.advance(0.2)
    assert t.current(vm, clk) == ''


def test_is_expired():
    clk = VirtualClock()
    t = Ticker(ttl_seconds=1.0)
    assert t.is_expired(clk) is True       # nothing pushed
    t.push('x', clk)
    assert t.is_expired(clk) is False
    clk.advance(1.0)
    assert t.is_expired(clk) is True


def test_cycle_moves_to_ring_provider():
    clk = VirtualClock()
    vm = _VM(last_status='stat', seq=1, turn_count=1)
    t = Ticker()
    t.push('stat', clk)
    # first cycle puts us ON the ring at the head (status)
    assert t.cycle() == TICKER_STATUS
    assert t.active_provider() == TICKER_STATUS
    assert t.current(vm, clk) == 'stat'
    # next cycle advances to hints
    assert t.cycle() == TICKER_HINTS
    assert t.current(vm, clk) == INPUT_HINT


def test_provider_dataclass_frozen():
    p = TickerProvider(name='x', fn=lambda vm: '')
    with pytest.raises(Exception):
        p.name = 'y'
