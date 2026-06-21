"""Tests for the View port + pure RegionPainter + Painting + HeadlessView."""
import os
import pytest

from glyfi.ui.layout import Size, Rect
from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import (
    AppSettings, REGION_TITLE, REGION_CONTENT, REGION_INPUT, REGION_STATUS, INPUT_PROMPT,
)
from glyfi.ui.config_store import UserConfig, ENV_CONFIG
from glyfi.ui.view import RegionPainter, Painting, View, HeadlessView
from glyfi.ui.viewmodel import AppViewModel, CONFIRM_QUIT_PROMPT
from glyfi.ui import theme
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


def _vm(modes=('chat',)):
    transport = FakeTransport()
    stepper = Stepper(transport=transport, session_id='glyfi-1')
    model = AppModel(session=SessionState(session_id='glyfi-1'), settings=AppSettings(), config=UserConfig())
    return AppViewModel(stepper=stepper, model=model, url='http://x', modes=modes)


def test_painting_lines_and_role_defaults():
    p = Painting(regions={'title': ['hi']})
    assert p.lines('title') == ['hi']
    assert p.lines('absent') == []
    assert p.role('title') == theme.ROLE_NORMAL


def test_headless_view_is_a_View_and_captures_painting():
    vm = _vm()
    view = HeadlessView(w=80, h=24)
    assert isinstance(view, View)
    view.render(vm)
    assert isinstance(view.painting, Painting)
    assert REGION_TITLE in view.layout


def test_headless_view_resize_changes_layout():
    vm = _vm()
    view = HeadlessView(w=80, h=24)
    view.render(vm)
    small = view.layout[REGION_CONTENT]
    view.resize(120, 40)
    view.render(vm)
    assert view.layout[REGION_CONTENT] != small


def test_input_hint_dim_role_when_empty():
    vm = _vm()
    layout = vm.resize(Size(80, 24))
    painting = RegionPainter().paint(vm, layout)
    assert painting.role(REGION_INPUT) == theme.ROLE_DIM
    assert painting.lines(REGION_INPUT)[0].startswith(INPUT_PROMPT)


def test_input_caret_renders_at_insertion_point_not_end():
    # the typing cursor must sit at the LIVE input_caret column (mid-line editing), not pinned to the buffer end.
    vm = _vm()
    vm.input_buffer = 'abcdef'
    vm.input_caret = 2                          # caret between 'b' and 'c'
    painter = RegionPainter()
    text, cell = painter._with_input_caret(vm, f'{INPUT_PROMPT}{vm.input_buffer}', width=80)
    assert cell is not None
    _row, start, end = cell
    assert start == len(INPUT_PROMPT) + 2       # insertion point, NOT len(INPUT_PROMPT)+len(buffer)
    assert end == start + 1
    # moving the caret to the end re-pins the cursor at the buffer end.
    vm.input_caret = len(vm.input_buffer)
    _t, cell_end = painter._with_input_caret(vm, f'{INPUT_PROMPT}{vm.input_buffer}', width=80)
    assert cell_end[1] == len(INPUT_PROMPT) + len(vm.input_buffer)


def test_destructive_confirm_uses_red_role_only_here():
    vm = _vm()
    vm.request_quit()                          # arms the confirm latch
    layout = vm.resize(Size(80, 24))
    painting = RegionPainter().paint(vm, layout)
    assert painting.role(REGION_STATUS) == theme.ROLE_DESTRUCTIVE
    assert CONFIRM_QUIT_PROMPT in painting.lines(REGION_STATUS)[0]


def test_content_never_ellipsized_long_line_wraps():
    vm = _vm()
    vm.resize(Size(40, 24))
    vm.step('x' * 200, 'sub-1')               # a very long turn line
    layout = vm.resize(Size(40, 24))
    painting = RegionPainter().paint(vm, layout)
    joined = ' '.join(painting.lines(REGION_CONTENT))
    assert '...' not in joined                 # wrapped, never ellipsized


def test_breadcrumb_present_in_palette_mode():
    vm = _vm()
    vm.open_palette()
    layout = vm.resize(Size(80, 24))
    painting = RegionPainter().paint(vm, layout)
    assert painting.breadcrumb == 'palette'


def test_title_smush_preserves_exit_hint_at_narrow_width():
    vm = _vm()
    layout = vm.resize(Size(28, 24))
    title = RegionPainter().paint(vm, layout).lines(REGION_TITLE)[0]
    # the exit hint (or its terse form) survives narrow widths -- 'quits' is the way-out essence.
    assert 'quits' in title or 'glyfi' in title
    assert len(title) <= layout[REGION_TITLE].w


def test_widget_overlay_renders_widget_lines():
    from glyfi.widgets.help_widget import WIDGET_HELP
    vm = _vm()
    vm.open_widget(WIDGET_HELP)
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    content = painting.lines(REGION_CONTENT)
    assert any('glyfi' in ln for ln in content)
    assert any(ln.lstrip().startswith(theme.FOCUS_MARKER) for ln in content)
