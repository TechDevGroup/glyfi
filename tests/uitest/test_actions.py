"""Structure tests for the uitest ACTION verbs -- each verb drives the app; WaitUntil/Delay drive the VirtualClock.

Asserts the verbs (not a TUI feature): each verb does its one drive through the driver; Tick/Delay/WaitUntil move
the deterministic VirtualClock (NO wall-clock); WaitUntil succeeds + times out (located); Expect fails loud with
the located violation; the verb registry is open/closed.
"""
import os
import pytest

from glyfi.ui.config_store import ENV_CONFIG, UserConfig
from glyfi.ui.events import TickerCycled
import glyfi.uitest as U
from glyfi.uitest.actions import (
    register_action, known_actions, ConstraintError, WaitTimeout, Step, DEFAULT_WAIT_POLL,
)


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _ctx(ttl=4.0):
    return U.new_context(config=UserConfig(status_ttl_seconds=ttl))


def test_press_drives_modal_dispatch():
    ctx = _ctx()
    U.Press('/').run(ctx)          # '/' opens the palette via the SAME keymap the runtime uses
    assert ctx.driver.vm.mode_ui == 'PALETTE'


def test_type_into_palette_filter():
    ctx = _ctx()
    U.Press('/').run(ctx)
    U.Type('conf').run(ctx)
    assert ctx.driver.vm.palette.filter_term == 'conf'


def test_tab_cycles_ticker_and_emits():
    ctx = _ctx()
    U.ClearEvents().run(ctx)
    U.Tab().run(ctx)
    assert ctx.driver.events_of(TickerCycled)


def test_tick_advances_virtual_clock():
    ctx = _ctx()
    before = ctx.clock.now()
    U.Tick(2.5).run(ctx)
    assert ctx.clock.now() == before + 2.5


def test_delay_advances_clock_no_wallclock():
    ctx = _ctx()
    U.Delay(10.0).run(ctx)
    assert ctx.clock.now() == 10.0       # purely virtual -- no real seconds passed


def test_trace_is_recorded_per_step():
    ctx = _ctx()
    U.Press('/').run(ctx)
    U.Type('x').run(ctx)
    assert len(ctx.trace) == 2
    assert ctx.trace[0].step.startswith('Press')
    assert ctx.trace[1].step.startswith('Type')


def test_expect_passes_silently_when_holds():
    ctx = _ctx()
    U.Expect(U.mode_is('NORMAL')).run(ctx)     # no raise


def test_expect_fails_loud_with_located_violation():
    ctx = _ctx()
    with pytest.raises(ConstraintError) as exc:
        U.Expect(U.mode_is('CONFIG')).run(ctx)
    assert not exc.value.result.holds
    assert exc.value.result.violations[0].locus == 'mode'


def test_wait_until_succeeds_by_advancing_clock():
    ctx = _ctx(ttl=4.0)
    # a pushed status clears after the TTL; WaitUntil should advance the clock until status_blank holds
    ctx.driver.vm.push_status('hi')
    assert ctx.driver.status_line() == 'hi'
    U.WaitUntil(U.status_blank(), timeout=10.0, poll=1.0).run(ctx)
    assert ctx.driver.status_line() == ''
    assert ctx.clock.now() >= 4.0            # it DID advance virtual time to cross the TTL


def test_wait_until_times_out_located():
    ctx = _ctx()
    with pytest.raises(WaitTimeout) as exc:
        # mode never becomes CONFIG just by waiting -> timeout, located
        U.WaitUntil(U.mode_is('CONFIG'), timeout=3.0, poll=1.0).run(ctx)
    assert exc.value.timeout == 3.0
    assert exc.value.result.violations[0].target == 'mode_ui'


def test_wait_until_holds_immediately_without_advancing():
    ctx = _ctx()
    before = ctx.clock.now()
    U.WaitUntil(U.mode_is('NORMAL'), timeout=5.0, poll=1.0).run(ctx)
    assert ctx.clock.now() == before          # already held -> no clock advance


def test_wait_until_rejects_nonpositive_poll():
    ctx = _ctx()
    with pytest.raises(ValueError):
        U.WaitUntil(U.status_blank(), timeout=5.0, poll=0.0).run(ctx)


def test_register_action_open_closed():
    name = 'noop_probe'
    if name not in known_actions():
        class _Noop(Step):
            label = 'Noop()'
            def _apply(self, ctx):
                pass
        register_action(name, lambda: _Noop())
    assert name in known_actions()


def test_register_action_fails_loud_on_dup():
    with pytest.raises(ValueError):
        register_action('press', lambda key: U.Press(key))
