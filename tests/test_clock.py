import pytest

from glyfi.ui.clock import SECONDS, Clock, MonotonicClock, VirtualClock


def test_seconds_unit():
    assert SECONDS == 1.0


def test_clock_is_abstract():
    with pytest.raises(TypeError):
        Clock()


def test_monotonic_clock_non_decreasing():
    c = MonotonicClock()
    a = c.now()
    b = c.now()
    assert isinstance(a, float)
    assert b >= a


def test_virtual_clock_starts_and_advances():
    c = VirtualClock(start=10.0)
    assert c.now() == 10.0
    assert c.advance(2.5) == 12.5
    assert c.now() == 12.5


def test_virtual_clock_default_start_zero():
    assert VirtualClock().now() == 0.0


def test_virtual_clock_negative_advance_fails_loud():
    c = VirtualClock()
    with pytest.raises(ValueError):
        c.advance(-1.0)
