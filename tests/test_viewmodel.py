"""Tests for the ViewModel command dispatch + the pure region painter (no live terminal).

The ViewModel is presentation logic; the painter is pure text geometry. These assert the MECHANISM: one ``step``
walks EXACTLY ONE turn (never loops), nav/mode/scroll/config commands mutate presentation state, the painter
spreads the state strip + the details L..R bar and clips to the solved rects, and palette/config overlays produce
highlight data.

A FAKE transport keeps it server-free; config persistence is redirected to a tmp path via the NAMED env.
"""
import os
import pytest

from glyfi.ui.layout import Size
from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import (
    AppSettings, REGION_TITLE, REGION_STATE, REGION_CONTENT, REGION_INPUT, REGION_DETAILS,
    REGION_HEADER_RULE, REGION_STATUS, INPUT_PROMPT,
)
from glyfi.ui.view import RegionPainter
from glyfi.ui.viewmodel import AppViewModel, UI_NORMAL, UI_PALETTE, UI_CONFIG
from glyfi.ui.config_store import UserConfig, SLOT_STATE, ENV_CONFIG
from glyfi.ui.ticker import INPUT_HINT
from glyfi.stepper import Stepper
from glyfi.transport import Transport
from glyfi.protocol import TurnRequest, TurnResponse, ProtocolError
from glyfi.ui.theme import FOCUS_MARKER

MODES = ('chat', 'plan', 'review')


class FakeTransport(Transport):
    """A server-free transport -- echoes a staged response, or fails loud when ``deny`` is set."""

    def __init__(self, deny=False):
        self.deny = deny
        self.calls = 0

    def send(self, req: TurnRequest) -> TurnResponse:
        self.calls += 1
        if self.deny:
            raise ProtocolError('turn DENY', type='denied', code=403)
        m = req.messages[-1]
        return TurnResponse(session_id=req.session_id, seq=req.seq + 1, subject=m.subject,
                            content=f'staged:{m.content}', mode=req.mode)


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _vm(deny=False, settings=None, config=None, modes=MODES):
    transport = FakeTransport(deny=deny)
    stepper = Stepper(transport=transport, session_id='glyfi-1')
    session = SessionState(session_id='glyfi-1')
    model = AppModel(session=session, settings=settings or AppSettings(), config=config or UserConfig())
    return (AppViewModel(stepper=stepper, model=model, url='http://x', modes=modes), transport)


# ===== the walk: exactly one turn, never a loop ============================================================

def test_step_walks_exactly_one_turn_and_stops():
    vm, transport = _vm()
    vm.step('hello', 'sub-1')
    assert transport.calls == 1
    assert vm.model.turn_count == 1
    assert vm.session.seq == 1


def test_two_step_commands_two_turns():
    vm, transport = _vm()
    vm.step('a', 'sub-1')
    vm.step('b', 'sub-1')
    assert transport.calls == 2 and vm.model.turn_count == 2


def test_step_records_turn_and_advances_selection():
    vm, _ = _vm()
    rec = vm.step('hi', 'sub-1')
    assert rec.ok is True
    assert rec.staged_content is not None
    assert vm.selected == rec.index
    assert vm.session.last_subject == 'sub-1'


def test_failed_turn_recorded_and_shown_fail_loud():
    vm, _ = _vm(deny=True)
    rec = vm.step('deny me', 'sub-1')
    assert rec.ok is False
    assert 'DENY' in (rec.error or '')
    assert vm.session.seq == 0
    assert 'FAILED' in vm.last_status


def test_request_prompt_uses_seam_for_exactly_one_turn():
    vm, transport = _vm()
    vm.prompt_seam = lambda: ('sub-1', 'typed text')
    vm.request_prompt()
    assert transport.calls == 1 and vm.model.turn_count == 1


def test_cycle_mode_walks_the_configured_labels():
    vm, _ = _vm(modes=MODES)
    assert vm.mode == MODES[0]
    seen = {vm.mode}
    for _ in range(len(MODES)):
        vm.cycle_mode()
        seen.add(vm.mode)
    assert seen == set(MODES)


def test_cycle_mode_single_label_is_stable():
    vm, _ = _vm(modes=('chat',))
    vm.cycle_mode()
    assert vm.mode == 'chat'


# ===== scroll windowing (BOTTOM-ANCHORED) =================================================================

def test_scroll_windows_content_to_region_height():
    vm, _ = _vm()
    vm.resize(Size(80, 12))
    for i in range(20):
        vm.step(f'msg{i}', 'sub-1')
    win = vm.windowed_content()
    assert len(win) <= vm.last_layout[REGION_CONTENT].h
    vm.scroll_to_top()
    assert vm.scroll_offset == vm._max_scroll()


def test_new_turn_sticks_to_bottom():
    vm, _ = _vm()
    vm.resize(Size(80, 12))
    for i in range(20):
        vm.step(f'm{i}', 'sub-1')
    assert vm.scroll_offset == 0


def test_bottom_anchored_newest_line_at_window_bottom():
    vm, _ = _vm()
    vm.resize(Size(80, 12))
    for i in range(20):
        vm.step(f'msg{i}', 'sub-1')
    win = vm.windowed_content()
    all_lines = vm.content_lines()
    assert win[-1] == all_lines[-1]


def test_page_up_reveals_older_then_page_down_sticks_back():
    vm, _ = _vm()
    vm.resize(Size(80, 12))
    for i in range(40):
        vm.step(f'm{i}', 'sub-1')
    assert vm.scroll_offset == 0
    vm.scroll_page_up()
    assert vm.scroll_offset > 0
    vm.scroll_page_down()
    vm.scroll_page_down()
    assert vm.scroll_offset == 0


# ===== passive visibility ================================================================================

def test_passive_visibility_drops_region_from_active():
    cfg = UserConfig()
    cfg.visible[REGION_STATE] = False
    vm, _ = _vm(config=cfg)
    active = [r.name for r in vm.active_regions()]
    assert REGION_STATE not in active
    full = _vm()[0].resize(Size(100, 30))
    reduced = vm.resize(Size(100, 30))
    assert reduced[REGION_CONTENT].h == full[REGION_CONTENT].h + 1


def test_no_target_methods_on_viewmodel():
    """The OBSERVE/target surface is DROPPED -- no cycle_target / target attrs survive."""
    vm, _ = _vm()
    for gone in ('cycle_target', 'target', 'target_label'):
        assert not hasattr(vm, gone)


# ===== painter: state strip spread, details L..R, rules ===================================================

def test_painter_produces_fenced_regions_clipped():
    vm, _ = _vm()
    vm.step('hello', 'sub-1')
    layout = vm.resize(Size(80, 24))
    painting = RegionPainter().paint(vm, layout)
    for name in (REGION_TITLE, REGION_STATE, REGION_CONTENT, REGION_INPUT, REGION_DETAILS):
        lines = painting.lines(name)
        rect = layout[name]
        assert len(lines) <= rect.h
        assert all(len(ln) <= rect.w for ln in lines)


def test_painter_state_strip_spreads_slots_across_width():
    vm, _ = _vm()
    vm.step('hi', 'sub-7')
    layout = vm.resize(Size(120, 24))
    strip = RegionPainter().paint(vm, layout).lines(REGION_STATE)[0]
    assert 'glyfi-1' in strip and 'sub-7' in strip and 'chat' in strip


def test_painter_details_bar_left_and_right_justified():
    vm, _ = _vm()
    layout = vm.resize(Size(120, 24))
    rect = layout[REGION_DETAILS]
    line = RegionPainter().paint(vm, layout).lines(REGION_DETAILS)[0]
    assert len(line) <= rect.w
    assert line.startswith('working dir')
    assert line.rstrip().endswith(tuple('0123456789'))


def test_painter_rules_are_full_width():
    vm, _ = _vm()
    layout = vm.resize(Size(80, 24))
    rule = RegionPainter().paint(vm, layout).lines(REGION_HEADER_RULE)[0]
    assert set(rule) == {'─'} and len(rule) == layout[REGION_HEADER_RULE].w


def test_painter_content_bottom_anchored_first_msg_at_bottom():
    vm, _ = _vm()
    layout = vm.resize(Size(80, 24))
    vm.step('hello', 'sub-1')
    rect = layout[REGION_CONTENT]
    lines = RegionPainter().paint(vm, layout).lines(REGION_CONTENT)
    assert len(lines) == rect.h
    assert lines[0] == '' and lines[1] == ''
    assert any('hello' in ln for ln in lines)
    assert lines[-1].strip() != ''


def test_painter_status_region_carries_the_ticker_line():
    vm, _ = _vm()
    vm.cycle_mode()                                   # pushes a status onto the ticker
    layout = vm.resize(Size(80, 24))
    painting = RegionPainter().paint(vm, layout)
    assert 'mode' in painting.lines(REGION_STATUS)[0]
    assert painting.lines(REGION_INPUT)[0] == f'{INPUT_PROMPT}{INPUT_HINT}'


def test_painter_title_has_mode_not_target():
    vm, _ = _vm()
    layout = vm.resize(Size(120, 24))
    title = RegionPainter().paint(vm, layout).lines(REGION_TITLE)[0]
    assert '[mode:chat]' in title
    assert 'target' not in title.lower()


# ===== painter: palette + config overlays produce highlight data ==========================================

def test_painter_palette_overlay_highlights_selected_row():
    vm, _ = _vm()
    vm.resize(Size(100, 24))
    vm.open_palette()
    vm.palette_type('c')
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    content = painting.lines(REGION_CONTENT)
    assert any(ln.lstrip().startswith(FOCUS_MARKER) for ln in content), content
    assert painting.lines(REGION_INPUT)[0].strip().startswith('>')


def test_painter_config_overlay_highlights_the_edited_slot_CELL_not_the_line():
    vm, _ = _vm()
    vm.resize(Size(100, 24))
    vm.open_config()
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    assert vm.highlight_region() is None
    assert REGION_STATE not in painting.highlight_regions
    span = painting.highlight_cells.get(REGION_STATE)
    assert span is not None and span[0] == 0 and span[2] > span[1]
    line = painting.regions[REGION_STATE][0]
    assert line[span[1]:span[2]] == vm.state_slots()[0]


def test_painter_state_cell_maps_by_position_not_first_substring_occurrence():
    vm, _ = _vm()                                            # session_id 'glyfi-1' contains a hyphen
    vm.open_config()
    slots = vm.state_slots()
    dash_idx = next(i for i, v in enumerate(slots) if v == '-')
    for _ in range(dash_idx):
        vm.config_down()
    assert vm.highlight_slot().position == dash_idx
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    line = painting.regions[REGION_STATE][0]
    row, start, end = painting.highlight_cells[REGION_STATE]
    assert line[start:end] == '-'
    assert start > line.index('glyfi-1')


def test_painter_config_editor_row_highlights_only_its_VALUE_field():
    vm, _ = _vm()
    vm.open_config()
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    assert REGION_CONTENT not in painting.highlight_rows
    cell = painting.highlight_cells.get(REGION_CONTENT)
    assert cell is not None
    row, start, end = cell
    line = painting.regions[REGION_CONTENT][row]
    assert 'state[0] =' in line
    assert line[start:end] == 'session'


def test_painter_config_inputs_knob_whole_area_highlights_input_fence():
    from glyfi.ui.config_editor import REGION_INPUTS
    vm, _ = _vm()
    vm.open_config()
    for _ in range(len(vm.editor.catalogue)):
        vm.config_down()
    assert vm.editor.is_input_row()
    layout = vm.resize(Size(100, 24))
    painting = RegionPainter().paint(vm, layout)
    assert vm.highlight_region() == REGION_INPUTS
    assert REGION_INPUTS in painting.highlight_regions


def test_resize_re_solves_layout():
    vm, _ = _vm()
    small = vm.resize(Size(80, 24))
    big = vm.resize(Size(120, 40))
    assert small[REGION_CONTENT] != big[REGION_CONTENT]
    assert vm.last_layout == big
