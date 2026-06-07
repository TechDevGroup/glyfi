"""Tests for the headless AppDriver + the view refinements (status region, input hints, bottom-anchor).

The ViewModel is driven WITHOUT curses through the SAME event bus + pure painter the runtime uses.
"""
import os
import curses
import pytest

from glyfi.ui.clock import VirtualClock
from glyfi.ui.events import (
    EventBus, ModeChanged, TurnRecorded, StatusPushed, TickerCycled, InputSubmitted, Resized,
)
from glyfi.ui.driver import build_headless_driver, AppDriver
from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import AppSettings, REGION_STATUS, REGION_INPUT, REGION_INPUT_RULE, INPUT_PROMPT, TAB
from glyfi.ui.config_store import UserConfig, ENV_CONFIG
from glyfi.ui.ticker import Ticker, INPUT_HINT
from glyfi.ui.viewmodel import AppViewModel
from glyfi.stepper import Stepper
from glyfi.transport import Transport
from glyfi.protocol import TurnRequest, TurnResponse


class FakeTransport(Transport):
    def __init__(self):
        self.calls = 0

    def send(self, req: TurnRequest) -> TurnResponse:
        self.calls += 1
        m = req.messages[-1]
        return TurnResponse(session_id=req.session_id, seq=req.seq + 1, subject=m.subject,
                            content=f'staged:{m.content}', mode=req.mode)


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _driver(ttl=4.0, w=80, h=24):
    transport = FakeTransport()
    stepper = Stepper(transport=transport, session_id='glyfi-1')
    session = SessionState(session_id='glyfi-1')
    config = UserConfig(status_ttl_seconds=ttl)
    model = AppModel(session=session, settings=AppSettings(), config=config)
    vm = AppViewModel(stepper=stepper, model=model, url='http://x', modes=('chat',),
                      bus=EventBus(record=True), clock=VirtualClock(), ticker=Ticker(ttl_seconds=ttl))
    return build_headless_driver(vm, w=w, h=h), transport


def test_build_headless_driver_returns_appdriver_with_recording_bus():
    d, _ = _driver()
    assert isinstance(d, AppDriver)
    assert d.vm.bus.record is True


def test_frame_seam_returns_usable_painting_layout_size():
    """The public capture seam: ``frame()`` (+ ``layout`` / ``size``) returns the current frame with no private reach."""
    from glyfi.ui.layout import Rect, Size
    from glyfi.ui.view import Painting

    d, _ = _driver(w=80, h=24)
    painting, layout, size = d.frame()

    assert isinstance(painting, Painting)
    assert isinstance(size, Size)
    assert (size.w, size.h) == (80, 24)
    # the layout is the solved region->Rect map and is non-empty for a rendered frame
    assert layout and all(isinstance(rect, Rect) for rect in layout.values())
    # the seam mirrors the property accessors and the underlying view (a pure read of the same frame)
    assert painting is d.painting
    assert layout is d.layout is d.view.layout
    assert size is d.size is d.view.size


def test_status_has_its_own_region_above_the_input_fence():
    d, _ = _driver()
    status_rect = d.view.layout[REGION_STATUS]
    fence_rect = d.view.layout[REGION_INPUT_RULE]
    assert status_rect.y == fence_rect.y - 1
    assert d.region(REGION_STATUS)


def test_input_line_shows_hint_when_empty_and_buffer_when_typed():
    d, _ = _driver()
    assert d.input_line() == f'{INPUT_PROMPT}{INPUT_HINT}'
    d.type_text('hello')
    assert d.input_line() == f'{INPUT_PROMPT}hello'
    d.invoke('mode')
    assert 'mode ' not in d.input_line()


def test_push_status_visible_then_clears_past_ttl():
    d, _ = _driver(ttl=4.0)
    d.invoke('mode')
    assert 'mode' in d.status_line()
    d.tick(5.0)
    assert 'mode' not in d.status_line()


def test_tab_cycles_the_ticker_ring_and_emits():
    d, _ = _driver()
    d.clear_events()
    d.press(TAB)
    assert d.last(TickerCycled) is not None
    d.press(TAB)
    assert d.status_line() == INPUT_HINT


def test_up_down_restore_prior_inputs():
    d, _ = _driver()
    d.type_text('alpha'); d.submit()
    d.type_text('beta'); d.submit()
    assert d.input_line() == f'{INPUT_PROMPT}{INPUT_HINT}'
    d.press(curses.KEY_UP)
    assert d.input_line() == f'{INPUT_PROMPT}beta'
    d.press(curses.KEY_UP)
    assert d.input_line() == f'{INPUT_PROMPT}alpha'
    d.press(curses.KEY_DOWN)
    assert d.input_line() == f'{INPUT_PROMPT}beta'


def test_an_event_is_emitted_per_transition():
    d, _ = _driver()
    d.clear_events()
    d.invoke('mode')
    assert d.last(ModeChanged) is not None and d.last(StatusPushed) is not None
    d.clear_events()
    d.resize(100, 30)
    assert d.last(Resized) is not None


def test_headless_drive_one_input_submission_painting_and_events():
    d, _ = _driver()
    d.clear_events()
    d.type_text('drive me')
    assert d.input_line() == f'{INPUT_PROMPT}drive me'
    d.submit()
    sub = d.last(InputSubmitted)
    assert sub is not None and sub.text == 'drive me'
    assert d.input_line() == f'{INPUT_PROMPT}{INPUT_HINT}'
    assert 'drive me' in d.status_line()


def test_headless_prompt_walks_exactly_one_turn():
    d, transport = _driver()
    d.vm.prompt_seam = lambda: ('sub-1', 'one turn')
    d.clear_events()
    d.invoke('prompt')
    assert transport.calls == 1
    assert d.last(TurnRecorded) is not None
    assert d.vm.model.turn_count == 1


def test_invoke_unknown_name_fails_loud():
    d, _ = _driver()
    with pytest.raises(KeyError):
        d.invoke('nope_not_a_command')


def test_tick_requires_virtual_clock():
    from glyfi.ui.clock import MonotonicClock
    transport = FakeTransport()
    stepper = Stepper(transport=transport, session_id='glyfi-1')
    model = AppModel(session=SessionState(session_id='glyfi-1'), config=UserConfig())
    vm = AppViewModel(stepper=stepper, model=model, modes=('chat',),
                      bus=EventBus(record=True), clock=MonotonicClock())
    d = build_headless_driver(vm)
    with pytest.raises(TypeError):
        d.tick(1.0)
