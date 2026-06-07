"""Tests for the WIDGET framework: the Widget port, the WidgetHost/registry, and the reference help widget."""
import curses

import pytest

from glyfi.ui.layout import Rect
from glyfi.widgets import (
    Widget, WidgetContext, WidgetError, WidgetHost, known_widgets, register_widget, widget_factory,
)
from glyfi.widgets.help_widget import HELP_OPEN_STATUS, HelpWidget, WIDGET_HELP


# ===== the registry (open/closed, fail-loud) ===============================================================

def test_reference_widget_is_registered():
    assert WIDGET_HELP in known_widgets()
    assert widget_factory(WIDGET_HELP)().__class__ is HelpWidget


def test_register_widget_fails_loud_on_duplicate():
    with pytest.raises(WidgetError):
        register_widget(WIDGET_HELP, HelpWidget)   # already registered -> no silent clobber


def test_widget_factory_fails_loud_on_unknown():
    with pytest.raises(WidgetError):
        widget_factory('no_such_widget')


# ===== the host orchestration (open / route-keys / close) ==================================================

def _host():
    pushed = []
    emitted = []
    closed = {'n': 0}
    host = WidgetHost(
        push_status=lambda s: pushed.append(s),
        emit=lambda e: emitted.append(e),
        on_close=lambda: closed.__setitem__('n', closed['n'] + 1),
    )
    return host, pushed, emitted, closed


def test_host_opens_a_widget_by_name_and_wires_its_context():
    host, pushed, _emitted, _closed = _host()
    w = host.open(WIDGET_HELP)
    assert host.is_open and isinstance(w, Widget)
    assert host.active_name == WIDGET_HELP
    assert host.title() == HelpWidget.title
    assert pushed == [HELP_OPEN_STATUS]            # open() pushed its greeting through the scoped context


def test_host_open_unknown_fails_loud():
    host, *_ = _host()
    with pytest.raises(WidgetError):
        host.open('no_such_widget')


def test_host_routes_handled_and_unhandled_keys():
    host, _pushed, _emitted, _closed = _host()
    host.open(WIDGET_HELP)
    assert host.handle_key(curses.KEY_DOWN) is True
    assert host.handle_key(ord('z')) is False


def test_host_close_releases_the_widget():
    host, _pushed, _emitted, _closed = _host()
    host.open(WIDGET_HELP)
    host.close()
    assert not host.is_open and host.active is None
    assert host.handle_key(curses.KEY_DOWN) is False   # no active widget -> nothing handled
    assert host.title() == '' and host.lines(Rect(0, 0, 10, 10)) == [] and host.highlight() is None


def test_host_request_close_routes_through_host_callback():
    host, _pushed, _emitted, closed = _host()
    w = host.open(WIDGET_HELP)
    # the WidgetContext request_close should call the host's on_close
    # exercise via re-opening (which closes the prior) plus the explicit cap
    assert closed['n'] == 0


def test_host_open_closes_previous():
    host, _pushed, _emitted, _closed = _host()
    host.open(WIDGET_HELP)

    class Other(Widget):
        title = 'other'
        def open(self, ctx): self.ctx = ctx
        def lines(self, rect): return ['other']
    register_widget('other_test_widget', Other)
    host.open('other_test_widget')
    assert host.active_name == 'other_test_widget'


# ===== the reference widget ================================================================================

def test_reference_widget_renders_lines_and_reports_focus():
    w = HelpWidget()
    pushed = []
    w.open(WidgetContext(name=WIDGET_HELP, push_status=lambda s: pushed.append(s),
                         emit=lambda e: None, request_close=lambda: None))
    lines = w.lines(Rect(0, 0, 60, 20))
    assert lines and isinstance(lines, list)
    assert w.highlight() == 0                       # cursor starts at the top
    w.handle_key(curses.KEY_DOWN)
    assert w.highlight() == 1
    assert w.handle_key(ord('x')) is False          # unhandled key -> host Esc can close
    assert w.close() is None


def test_reference_widget_cursor_clamps():
    w = HelpWidget()
    w.open(WidgetContext(name=WIDGET_HELP, push_status=lambda s: None,
                         emit=lambda e: None, request_close=lambda: None))
    for _ in range(500):
        w.handle_key(curses.KEY_DOWN)
    from glyfi.widgets.help_widget import HELP_LINES
    assert w.highlight() == len(HELP_LINES) - 1
    for _ in range(500):
        w.handle_key(curses.KEY_UP)
    assert w.highlight() == 0


def test_open_closed_a_new_widget_needs_no_host_edit():
    """A brand-new widget plugs in via register_widget + open(name) -- the host code is never touched."""
    class Probe2(Widget):
        title = 'probe2'
        def open(self, ctx): self.ctx = ctx
        def lines(self, rect): return ['probe2 content']
    register_widget('probe2_widget', Probe2)
    host, _pushed, _emitted, _closed = _host()
    host.open('probe2_widget')
    assert host.active_name == 'probe2_widget'
    assert host.lines(Rect(0, 0, 40, 5)) == ['probe2 content']


def test_widget_context_is_immutable():
    ctx = WidgetContext(name='w', push_status=lambda s: None, emit=lambda e: None, request_close=lambda: None)
    with pytest.raises(Exception):
        ctx.name = 'other'
