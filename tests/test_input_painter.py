"""Unit tests for glyfi.ui.input_painter -- pure multi-row input helpers + the C5/C4 hooks.

The pure geometry layer (buffer_lines / caret_rowcol / visible_window / input_height) is ported
from the downstream consumer's proven input_render tests. The hook-factory tests prove the
opt-in post_paint (C5) and pre_render (C4) seams patch/grow correctly and are no-ops by default.
Pure, data-free -- no curses, no network.
"""
from __future__ import annotations

import os
import types

import pytest

from glyfi.ui.input_painter import (
    INPUT_MAX_ROWS, INPUT_CONTINUATION,
    buffer_lines, caret_rowcol, visible_window, input_height,
    make_multi_line_input_painter, make_pre_render_dynamic_height, pre_render_dynamic_height,
)
from glyfi.ui.settings import INPUT_PROMPT, REGION_INPUT, AppSettings
from glyfi.ui.layout import Rect
from glyfi.ui.view import RegionPainter, Painting


# -- pure geometry -------------------------------------------------------------------

class TestBufferLines:
    def test_empty(self):
        assert buffer_lines('') == ['']

    def test_single(self):
        assert buffer_lines('hello') == ['hello']

    def test_split(self):
        assert buffer_lines('a\nb\nc') == ['a', 'b', 'c']

    def test_trailing_newline(self):
        assert buffer_lines('hello\n') == ['hello', '']


class TestCaretRowcol:
    def test_start(self):
        assert caret_rowcol('hello', 0) == (0, 0)

    def test_end(self):
        assert caret_rowcol('hello', 5) == (0, 5)

    def test_clamp_high(self):
        assert caret_rowcol('hello', 99) == (0, 5)

    def test_just_after_newline(self):
        assert caret_rowcol('hello\nworld', 6) == (1, 0)

    def test_mid_second_line(self):
        assert caret_rowcol('hello\nworld', 9) == (1, 3)

    def test_after_trailing_newline(self):
        assert caret_rowcol('hello\n', 6) == (1, 0)


class TestVisibleWindow:
    def test_short_no_scroll(self):
        assert visible_window(['a', 'b', 'c'], 0, 6) == (0, ['a', 'b', 'c'])

    def test_long_caret_at_end(self):
        lines = list('abcdefghij')
        assert visible_window(lines, 9, 4) == (6, ['g', 'h', 'i', 'j'])

    def test_long_caret_in_middle(self):
        lines = list('abcdefghij')
        assert visible_window(lines, 5, 4) == (3, ['d', 'e', 'f', 'g'])

    def test_caret_always_in_window(self):
        lines = list(range(20))
        for cr in range(20):
            start, vis = visible_window(lines, cr, 6)
            assert start <= cr < start + len(vis)


class TestInputHeight:
    def test_empty(self):
        assert input_height('') == 1

    def test_single(self):
        assert input_height('hello') == 1

    def test_two(self):
        assert input_height('hello\nworld') == 2

    def test_capped(self):
        assert input_height('\n'.join(['x'] * (INPUT_MAX_ROWS + 3))) == INPUT_MAX_ROWS

    def test_custom_max(self):
        assert input_height('a\nb\nc\nd\ne', max_rows=3) == 3

    def test_palette_style_no_newline(self):
        assert input_height('search term') == 1


class TestContinuationWidth:
    def test_same_width_as_prompt(self):
        assert len(INPUT_CONTINUATION) == len(INPUT_PROMPT)


# -- C5 post_paint hook factory ------------------------------------------------------

def _vm_stub(buf, caret=None, mode='NORMAL'):
    vm = types.SimpleNamespace(input_buffer=buf,
                               input_caret=(caret if caret is not None else len(buf)),
                               mode_ui=mode)
    return vm


class TestMultiLinePostPaint:
    def test_single_line_buffer_unchanged(self):
        hook = make_multi_line_input_painter()
        layout = {REGION_INPUT: Rect(x=0, y=0, w=40, h=1)}
        before = Painting(regions={REGION_INPUT: [f'{INPUT_PROMPT}hello']})
        after = hook(_vm_stub('hello'), layout, before)
        assert after.regions[REGION_INPUT] == before.regions[REGION_INPUT]

    def test_palette_mode_unchanged(self):
        hook = make_multi_line_input_painter()
        layout = {REGION_INPUT: Rect(x=0, y=0, w=40, h=3)}
        before = Painting(regions={REGION_INPUT: [f'{INPUT_PROMPT}a\nb']})
        after = hook(_vm_stub('a\nb', mode='PALETTE'), layout, before)
        assert after is before  # G34: palette skipped (returns the same object)

    def test_multi_line_buffer_renders_n_rows(self):
        hook = make_multi_line_input_painter()
        layout = {REGION_INPUT: Rect(x=0, y=0, w=40, h=6)}
        before = Painting(regions={REGION_INPUT: ['placeholder']})
        after = hook(_vm_stub('hello\nworld', caret=8), layout, before)
        rows = after.regions[REGION_INPUT]
        assert len(rows) == 2
        assert rows[0] == f'{INPUT_PROMPT}hello'
        assert rows[1] == f'{INPUT_CONTINUATION}world'
        # caret at index 8 -> row 1, col 2 ('wo|rld'); cell col = len(prompt)+2
        cell = after.highlight_cells[REGION_INPUT]
        assert cell[0] == 1
        assert cell[1] == len(INPUT_PROMPT) + 2

    def test_no_input_region_returns_unchanged(self):
        hook = make_multi_line_input_painter()
        before = Painting(regions={})
        assert hook(_vm_stub('a\nb'), {}, before) is before


# -- C4 pre_render hook factory ------------------------------------------------------

@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    from glyfi.ui.config_store import ENV_CONFIG
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _real_vm():
    from glyfi.ui.model import AppModel, SessionState
    from glyfi.ui.config_store import UserConfig
    from glyfi.ui.viewmodel import AppViewModel
    from glyfi.stepper import Stepper
    from glyfi.protocol import TurnRequest, TurnResponse
    from glyfi.transport import Transport

    class _T(Transport):
        def send(self, req):
            return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                subject='s', content='c', mode=req.mode)

    model = AppModel(session=SessionState(session_id='g-1'), settings=AppSettings(), config=UserConfig())
    return AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                        model=model, url='http://x', modes=('chat',))


def _input_size(vm):
    return next(r.size for r in vm.model.settings.regions if r.name == REGION_INPUT)


class TestPreRenderDynamicHeight:
    def test_single_line_keeps_height_1(self):
        vm = _real_vm()
        pre_render_dynamic_height(vm)
        assert _input_size(vm) == 1

    def test_multi_line_grows_height(self):
        vm = _real_vm()
        vm.input_buffer = 'a\nb\nc'
        make_pre_render_dynamic_height()(vm)
        assert _input_size(vm) == 3

    def test_growth_capped_at_max(self):
        vm = _real_vm()
        vm.input_buffer = '\n'.join(['x'] * 20)
        make_pre_render_dynamic_height()(vm)
        assert _input_size(vm) == INPUT_MAX_ROWS

    def test_shrinks_back_when_buffer_clears(self):
        vm = _real_vm()
        vm.input_buffer = 'a\nb'
        hook = make_pre_render_dynamic_height()
        hook(vm)
        assert _input_size(vm) == 2
        vm.input_buffer = 'oneline'
        hook(vm)
        assert _input_size(vm) == 1
