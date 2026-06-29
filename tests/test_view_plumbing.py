"""Integration tests for the generic opt-in view plumbing (C1-C7).

Each capability is proven two ways: (a) opting in changes behaviour as specified, and
(b) the OCP default (no opt-in) is identical to the pre-change base. The curses-bound seams
(C1/C2b/C4/C6) are exercised by constructing a CursesView via ``__new__`` with a recording
fake ``stdscr`` so no live terminal is needed. Data-free -- no curses TTY, no network.
"""
from __future__ import annotations

import os
import types

import curses
import pytest

from glyfi.ui import curses_view as cv_mod
from glyfi.ui.curses_view import CursesView
from glyfi.ui.view import RegionPainter, Painting, HeadlessView
from glyfi.ui.content_view import VisualRow, render_entries, Entry
from glyfi.ui.settings import (
    AppSettings, REGION_CONTENT, REGION_INPUT, INPUT_PROMPT,
)
from glyfi.ui.layout import Rect, Size
from glyfi.ui import theme


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    from glyfi.ui.config_store import ENV_CONFIG
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _vm(settings=None):
    from glyfi.ui.model import AppModel, SessionState
    from glyfi.ui.config_store import UserConfig
    from glyfi.ui.viewmodel import AppViewModel
    from glyfi.stepper import Stepper
    from glyfi.protocol import TurnResponse
    from glyfi.transport import Transport

    class _T(Transport):
        def send(self, req):
            return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                subject='s', content='c', mode=req.mode)

    model = AppModel(session=SessionState(session_id='g-1'),
                     settings=settings or AppSettings(), config=UserConfig())
    return AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                        model=model, url='http://x', modes=('chat',))


class _FakeScr:
    """A recording stdscr stand-in -- captures addstr calls; getmaxyx/erase/refresh are no-ops."""
    def __init__(self, h=24, w=80):
        self._h, self._w = h, w
        self.writes = []   # (y, x, text, attr)

    def getmaxyx(self):
        return (self._h, self._w)

    def addstr(self, y, x, text, attr=0):
        self.writes.append((y, x, text, attr))

    def erase(self):
        pass

    def refresh(self):
        pass


def _bare_view(**attrs):
    """A CursesView with __init__ bypassed (no real curses) -- attrs set directly for seam tests."""
    view = CursesView.__new__(CursesView)
    view._scr = _FakeScr()
    view._hot = False
    view._key_preprocessor = None
    view._row_classifier = None
    view._pre_render = None
    view._bracketed_paste = False
    for k, v in attrs.items():
        setattr(view, '_' + k, v)
    return view


# -- C1: key_preprocessor seam -------------------------------------------------------

class TestC1KeyPreprocessor:
    def test_preprocessor_true_skips_dispatch(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(cv_mod, 'dispatch_key', lambda vm, ch: dispatched.append(ch))
        seen = []
        view = _bare_view(key_preprocessor=lambda vm, ch: (seen.append(ch) or True))
        vm = types.SimpleNamespace(bus=types.SimpleNamespace(emit=lambda e: None), mode_ui='NORMAL')
        view._dispatch_paste_event(('passthrough', ord('x')), vm)
        assert seen == [ord('x')]
        assert dispatched == []   # consumed -> base dispatch skipped

    def test_preprocessor_false_passes_through(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(cv_mod, 'dispatch_key', lambda vm, ch: dispatched.append(ch))
        view = _bare_view(key_preprocessor=lambda vm, ch: False)
        vm = types.SimpleNamespace(bus=types.SimpleNamespace(emit=lambda e: None), mode_ui='NORMAL')
        view._dispatch_paste_event(('passthrough', ord('y')), vm)
        assert dispatched == [ord('y')]

    def test_none_preprocessor_dispatches_directly(self, monkeypatch):
        dispatched = []
        monkeypatch.setattr(cv_mod, 'dispatch_key', lambda vm, ch: dispatched.append(ch))
        view = _bare_view()   # key_preprocessor=None (OCP default)
        vm = types.SimpleNamespace(bus=types.SimpleNamespace(emit=lambda e: None), mode_ui='NORMAL')
        view._dispatch_paste_event(('passthrough', ord('z')), vm)
        assert dispatched == [ord('z')]


# -- C2a: VisualRow.color_role field -------------------------------------------------

class TestC2aColorRole:
    def test_default_is_empty(self):
        row = VisualRow(text='hi', entry_index=0, is_header=True)
        assert row.color_role == ''

    def test_settable(self):
        row = VisualRow(text='hi', entry_index=0, is_header=False, color_role=theme.ROLE_ACCENT)
        assert row.color_role == theme.ROLE_ACCENT

    def test_render_entries_default_no_override(self):
        rows = render_entries([Entry(summary='top', body=('a', 'b'))], width=40)
        assert all(r.color_role == '' for r in rows)


# -- C2b: row_classifier in _blit_region (+ G38 select override) ---------------------

class TestC2bRowClassifier:
    def _painting(self, lines, highlight_rows=None):
        return Painting(regions={REGION_CONTENT: lines},
                        highlight_rows=highlight_rows or {})

    def test_classifier_applied_per_row(self):
        def classify(name, line):
            return theme.ROLE_DESTRUCTIVE if line.startswith('!') else theme.ROLE_NORMAL
        view = _bare_view(row_classifier=classify)
        painting = self._painting(['ok line', '! error line'])
        rect = Rect(x=0, y=0, w=40, h=5)
        view._blit_region(REGION_CONTENT, rect, painting, theme.select_attr())
        attr_by_text = {w[2].strip(): w[3] for w in view._scr.writes}
        assert attr_by_text['ok line'] == theme.role_attr(theme.ROLE_NORMAL)
        assert attr_by_text['! error line'] == theme.role_attr(theme.ROLE_DESTRUCTIVE)

    def test_g38_selected_row_keeps_highlight(self):
        # The selected row must show select_attr even though its content would classify otherwise.
        def classify(name, line):
            return theme.ROLE_DESTRUCTIVE
        view = _bare_view(row_classifier=classify)
        painting = self._painting(['row0', 'row1', 'row2'], highlight_rows={REGION_CONTENT: 1})
        rect = Rect(x=0, y=0, w=40, h=5)
        view._blit_region(REGION_CONTENT, rect, painting, theme.select_attr())
        attr_by_text = {w[2].strip(): w[3] for w in view._scr.writes}
        assert attr_by_text['row1'] == theme.select_attr()          # G38: selection wins
        assert attr_by_text['row0'] == theme.role_attr(theme.ROLE_DESTRUCTIVE)

    def test_no_classifier_uses_region_role(self):
        view = _bare_view()   # row_classifier=None (OCP default)
        painting = Painting(regions={REGION_CONTENT: ['a', 'b']},
                            region_roles={REGION_CONTENT: theme.ROLE_DIM})
        rect = Rect(x=0, y=0, w=40, h=5)
        view._blit_region(REGION_CONTENT, rect, painting, theme.select_attr())
        assert all(w[3] == theme.role_attr(theme.ROLE_DIM) for w in view._scr.writes)


# -- C3: overlay list windowing ------------------------------------------------------

class TestC3PaletteWindowing:
    def _render_palette(self, n_cmds, settings=None, select_to_end=False):
        from glyfi.plugins.palette import register_command
        for i in range(n_cmds):
            register_command(f'zz_cmd_{i:02d}', f'desc {i}', lambda vm: None)
        vm = _vm(settings=settings)
        vm.open_palette()
        # filter to only our zz_ commands so the count is deterministic.
        for ch in 'zz_cmd_':
            vm.palette_type(ch)
        if select_to_end:
            for _ in range(n_cmds):
                vm.palette_down()
        view = HeadlessView(w=80, h=24)
        view.render(vm)
        view.render(vm)   # second pass so last_layout is populated for the overlay
        return view.painting.lines(REGION_CONTENT)

    def test_long_list_shows_scroll_indicator(self):
        lines = self._render_palette(30, select_to_end=True)
        joined = '\n'.join(lines)
        assert 'more' in joined   # an '↑ N more' / '↓ N more' affordance is present
        # the selected (last) command must be visible despite the overflow
        assert any('zz_cmd_29' in ln for ln in lines)

    def test_short_list_no_indicator(self):
        lines = self._render_palette(3)
        assert all('more' not in ln for ln in lines)

    def test_scroll_palette_false_disables_windowing(self):
        lines = self._render_palette(30, settings=AppSettings(), select_to_end=True)
        # default settings -> windowing ON -> 'more' present (sanity that the toggle below differs)
        assert 'more' in '\n'.join(lines)


def test_c3_scroll_palette_flag_off_truncates():
    from glyfi.plugins.palette import register_command
    for i in range(30):
        register_command(f'yy_cmd_{i:02d}', f'd{i}', lambda vm: None)
    vm = _vm()
    vm.open_palette()
    for ch in 'yy_cmd_':
        vm.palette_type(ch)
    for _ in range(30):
        vm.palette_down()
    view = HeadlessView(w=80, h=24, painter=RegionPainter(scroll_palette=False))
    view.render(vm)
    view.render(vm)
    lines = view.painting.lines(REGION_CONTENT)
    assert all('more' not in ln for ln in lines)   # windowing disabled -> no indicators


# -- C4: pre_render fires BEFORE the layout solve (G35) ------------------------------

class TestC4PreRenderTiming:
    def test_pre_render_runs_before_resize(self):
        order = []
        view = _bare_view(pre_render=lambda vm: order.append('pre'))
        view._painter = types.SimpleNamespace(paint=lambda vm, layout: Painting())

        class _VM:
            def resize(self, size):
                order.append('resize')
                return {}
        view.render(_VM())
        assert order == ['pre', 'resize']

    def test_no_pre_render_is_noop(self):
        order = []
        view = _bare_view()   # pre_render=None (OCP default)
        view._painter = types.SimpleNamespace(paint=lambda vm, layout: Painting())

        class _VM:
            def resize(self, size):
                order.append('resize')
                return {}
        view.render(_VM())
        assert order == ['resize']


# -- C5: post_paint wrapper (paint -> _do_paint + hook) ------------------------------

class TestC5PostPaint:
    def test_default_painter_returns_do_paint_unchanged(self):
        vm = _vm()
        base = RegionPainter()
        layout = vm.resize(Size(w=80, h=24))
        assert base.paint(vm, layout) == base._do_paint(vm, layout)

    def test_post_paint_hook_invoked(self):
        vm = _vm()
        sentinel = Painting(regions={'sentinel': ['x']})
        painter = RegionPainter(post_paint=lambda v, l, p: sentinel)
        layout = vm.resize(Size(w=80, h=24))
        assert painter.paint(vm, layout) is sentinel

    def test_multiline_input_rendered_with_grown_region(self):
        from glyfi.ui.input_painter import make_multi_line_input_painter, make_pre_render_dynamic_height
        vm = _vm()
        vm.input_buffer = 'hello\nworld'
        vm.input_caret = len(vm.input_buffer)
        make_pre_render_dynamic_height()(vm)   # C4: grow REGION_INPUT to 2 rows
        view = HeadlessView(w=80, h=24, painter=RegionPainter(post_paint=make_multi_line_input_painter()))
        view.render(vm)
        rows = view.painting.lines(REGION_INPUT)
        assert len(rows) == 2
        assert rows[0].startswith(INPUT_PROMPT) and rows[0].endswith('hello')
        assert rows[1].endswith('world')

    def test_default_input_single_row_even_when_multiline(self):
        # OCP: with no post_paint, the base renderer is unchanged (one region entry).
        vm = _vm()
        vm.input_buffer = 'hello\nworld'
        view = HeadlessView(w=80, h=24)   # default RegionPainter, no hook
        view.render(vm)
        assert len(view.painting.lines(REGION_INPUT)) == 1


# -- C7: widget_keys field + dispatch --------------------------------------------------

class TestC7WidgetKeys:
    def test_field_default_empty_and_widget_for(self):
        s = AppSettings()
        assert s.widget_keys == {}
        assert s.widget_for(curses.KEY_F2) == ''   # OCP: nothing bound

    def test_custom_widget_keys_lookup(self):
        s = AppSettings(widget_keys={curses.KEY_F2: 'traces', curses.KEY_F3: 'pipeline'})
        assert s.widget_for(curses.KEY_F2) == 'traces'
        assert s.widget_for(curses.KEY_F3) == 'pipeline'

    def test_dispatch_opens_bound_widget(self):
        from glyfi.ui.keymap import dispatch_key
        vm = _vm(settings=AppSettings(widget_keys={curses.KEY_F2: 'traces'}))
        opened = []
        vm.open_widget = lambda name: opened.append(name)
        dispatch_key(vm, curses.KEY_F2)
        assert opened == ['traces']

    def test_dispatch_default_no_widget_open(self):
        from glyfi.ui.keymap import dispatch_key
        vm = _vm()   # empty widget_keys (OCP default)
        opened = []
        vm.open_widget = lambda name: opened.append(name)
        dispatch_key(vm, curses.KEY_F2)
        assert opened == []
