"""Tests for the shared modal key dispatch (dispatch_key) across the NAMED ui states."""
import os
import curses
import pytest

from glyfi.ui.keymap import dispatch_key, KEY_ESC, KEYS_ENTER, KEYS_BACKSPACE
from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import AppSettings, TAB
from glyfi.ui.config_store import UserConfig, ENV_CONFIG
from glyfi.ui.viewmodel import (
    AppViewModel, UI_NORMAL, UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE,
)
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


def _vm():
    transport = FakeTransport()
    stepper = Stepper(transport=transport, session_id='glyfi-1')
    model = AppModel(session=SessionState(session_id='glyfi-1'), settings=AppSettings(), config=UserConfig())
    vm = AppViewModel(stepper=stepper, model=model, modes=('chat', 'plan'))
    from glyfi.ui.layout import Size
    vm.resize(Size(80, 24))
    return vm, transport


# ===== NORMAL ============================================================================================

def test_slash_opens_palette_from_empty_buffer():
    vm, _ = _vm()
    dispatch_key(vm, ord('/'))
    assert vm.mode_ui == UI_PALETTE


def test_slash_is_literal_once_typing():
    vm, _ = _vm()
    dispatch_key(vm, ord('a'))               # start typing free text
    dispatch_key(vm, ord('/'))               # now a literal char, NOT the palette
    assert vm.mode_ui == UI_NORMAL
    assert vm.input_buffer == 'a/'


def test_command_letters_fire_only_when_buffer_empty():
    vm, _ = _vm()
    dispatch_key(vm, ord('m'))               # mode_cycle from empty buffer
    assert vm.mode == 'plan'
    # once typing, the same key is a literal
    dispatch_key(vm, ord('x'))
    dispatch_key(vm, ord('m'))
    assert vm.input_buffer == 'xm'
    assert vm.mode == 'plan'


def test_prompt_key_opens_prompt_modal():
    vm, _ = _vm()
    dispatch_key(vm, ord('s'))
    assert vm.mode_ui == UI_PROMPT


def test_traverse_key_enters_traverse():
    vm, _ = _vm()
    dispatch_key(vm, ord('c'))
    assert vm.mode_ui == UI_TRAVERSE


def test_quit_requires_double_q_confirm():
    vm, _ = _vm()
    dispatch_key(vm, ord('q'))
    assert vm.confirm_pending is True and vm.should_quit is False
    dispatch_key(vm, ord('q'))
    assert vm.should_quit is True


def test_stray_key_cancels_quit_confirm():
    vm, _ = _vm()
    dispatch_key(vm, ord('q'))
    assert vm.confirm_pending is True
    dispatch_key(vm, ord('m'))               # any non-quit key cancels the latch
    assert vm.confirm_pending is False


def test_tab_cycles_ticker():
    vm, _ = _vm()
    before = vm.ticker.active_provider()
    dispatch_key(vm, TAB)
    dispatch_key(vm, TAB)
    assert vm.ticker.active_provider() != before or vm.ticker._on_ring


def test_pgup_pgdn_scroll_in_normal():
    from glyfi.ui.layout import Size
    vm, _ = _vm()
    vm.resize(Size(80, 12))
    for i in range(40):
        vm.step(f'm{i}', 'sub-1')
    dispatch_key(vm, curses.KEY_PPAGE)
    assert vm.scroll_offset > 0
    dispatch_key(vm, curses.KEY_NPAGE)
    dispatch_key(vm, curses.KEY_NPAGE)
    assert vm.scroll_offset == 0


# ===== PALETTE ===========================================================================================

def test_palette_type_and_esc_back():
    vm, _ = _vm()
    vm.open_palette()
    dispatch_key(vm, ord('h'))
    assert vm.input_buffer.endswith('h')
    dispatch_key(vm, KEY_ESC)
    assert vm.mode_ui == UI_NORMAL


def test_palette_enter_runs_selected():
    vm, _ = _vm()
    vm.open_palette()
    vm.palette_type('mode')                   # filter to the mode command
    dispatch_key(vm, KEYS_ENTER[0])
    assert vm.mode_ui == UI_NORMAL
    assert vm.mode == 'plan'                   # the mode command cycled


# ===== CONFIG ============================================================================================

def test_config_arrows_and_back_exits():
    vm, _ = _vm()
    vm.open_config()
    dispatch_key(vm, curses.KEY_DOWN)
    assert vm.editor.slot_index == 1
    dispatch_key(vm, KEY_ESC)                  # back at SLOTS -> exit config
    assert vm.mode_ui == UI_NORMAL


def test_config_enter_descends_then_back_ascends():
    vm, _ = _vm()
    vm.open_config()
    dispatch_key(vm, KEYS_ENTER[0])            # SLOTS -> ALIASES
    from glyfi.ui.config_editor import LEVEL_ALIASES
    assert vm.editor.level == LEVEL_ALIASES
    dispatch_key(vm, KEY_ESC)                  # ascend, not exit
    assert vm.mode_ui == UI_CONFIG


# ===== WIDGET ============================================================================================

def test_widget_esc_always_closes():
    from glyfi.widgets.help_widget import WIDGET_HELP
    vm, _ = _vm()
    vm.open_widget(WIDGET_HELP)
    assert vm.mode_ui == UI_WIDGET
    dispatch_key(vm, KEY_ESC)
    assert vm.mode_ui == UI_NORMAL


def test_widget_handles_its_own_key():
    from glyfi.widgets.help_widget import WIDGET_HELP
    vm, _ = _vm()
    vm.open_widget(WIDGET_HELP)
    dispatch_key(vm, curses.KEY_DOWN)          # the widget moves its cursor; mode stays WIDGET
    assert vm.mode_ui == UI_WIDGET


# ===== PROMPT ============================================================================================

def test_prompt_typing_and_submit_walks_one_turn():
    vm, transport = _vm()
    vm.open_prompt()
    for ch in 'sub-1':
        dispatch_key(vm, ord(ch))
    dispatch_key(vm, curses.KEY_DOWN)          # to the text field
    for ch in 'hi':
        dispatch_key(vm, ord(ch))
    dispatch_key(vm, KEYS_ENTER[0])
    assert transport.calls == 1
    assert vm.mode_ui == UI_NORMAL


def test_prompt_up_off_the_top_returns_to_normal():
    vm, _ = _vm()
    vm.open_prompt()
    dispatch_key(vm, curses.KEY_UP)            # Up on the first field exits
    assert vm.mode_ui == UI_NORMAL


def test_prompt_esc_cancels():
    vm, _ = _vm()
    vm.open_prompt()
    dispatch_key(vm, KEY_ESC)
    assert vm.mode_ui == UI_NORMAL


# ===== TRAVERSE ==========================================================================================

def test_traverse_esc_exits():
    vm, _ = _vm()
    vm.enter_traverse()
    dispatch_key(vm, KEY_ESC)
    assert vm.mode_ui == UI_NORMAL


def test_traverse_arrows_move_caret_and_collapse():
    vm, transport = _vm()
    from glyfi.ui.layout import Size
    vm.resize(Size(80, 24))
    for i in range(5):
        vm.step(f'm{i}', 'sub-1')
    vm.enter_traverse()
    dispatch_key(vm, curses.KEY_UP)
    assert vm.traverse_caret.offset >= 1
    dispatch_key(vm, curses.KEY_LEFT)          # collapse the entry the caret sits in (no crash)
    assert vm.mode_ui == UI_TRAVERSE
