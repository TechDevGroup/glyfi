"""Tests for the config-editor multi-level state machine (slot/alias nav + highlighted-area reporting)."""
from glyfi.ui.config_editor import (
    EditorState, build_slot_catalogue, LEVEL_SLOTS, LEVEL_ALIASES, LEVEL_INPUTS, INPUT_KNOBS, REGION_INPUTS,
)
from glyfi.ui.config_store import UserConfig, SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT


def _editor():
    cfg = UserConfig()
    return EditorState(catalogue=build_slot_catalogue(cfg.slots), config=cfg), cfg


def test_catalogue_flattens_groups_in_order():
    cfg = UserConfig()
    cat = build_slot_catalogue(cfg.slots)
    groups = [sp.group for sp in cat]
    assert groups[0] == SLOT_STATE
    assert SLOT_DETAILS_LEFT in groups and SLOT_DETAILS_RIGHT in groups
    assert groups.index(SLOT_DETAILS_LEFT) < groups.index(SLOT_DETAILS_RIGHT)


def test_starts_at_slots_level_highlighting_state():
    ed, _ = _editor()
    assert ed.level == LEVEL_SLOTS
    assert ed.highlight_region() == 'state'   # the first slot is a state slot


def test_moving_to_details_slot_reports_details_area():
    ed, cfg = _editor()
    n_state = len(cfg.slots[SLOT_STATE])
    for _ in range(n_state):
        ed.move_down()
    assert ed.current_slot().group in (SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT)
    assert ed.highlight_region() == 'details'


def test_enter_descends_to_aliases_then_bind_returns_to_slots():
    ed, _ = _editor()
    bind = ed.enter()
    assert bind is None and ed.level == LEVEL_ALIASES
    ed.move_down()
    bind = ed.enter()
    assert bind is not None
    assert ed.level == LEVEL_SLOTS
    assert bind.group == SLOT_STATE and bind.position == 0
    aliases = [a for a, _ in EditorState().aliases()]
    assert bind.alias == aliases[1]


def test_back_at_aliases_returns_without_change():
    ed, _ = _editor()
    ed.enter()
    assert ed.level == LEVEL_ALIASES
    bind = ed.back()
    assert bind is None and ed.level == LEVEL_SLOTS


def test_back_at_slots_signals_exit():
    ed, _ = _editor()
    assert ed.at_top_level() is True
    ed.enter()
    assert ed.at_top_level() is False


def test_nav_clamps_within_each_level():
    ed, cfg = _editor()
    for _ in range(100):
        ed.move_down()
    n_slots = (len(cfg.slots[SLOT_STATE]) + len(cfg.slots[SLOT_DETAILS_LEFT])
               + len(cfg.slots[SLOT_DETAILS_RIGHT]))
    assert ed.slot_index == n_slots + len(INPUT_KNOBS) - 1
    assert ed.is_input_row() is True
    ed.slot_index = 0
    ed.enter()
    for _ in range(100):
        ed.move_down()
    assert ed.alias_index == len(ed.aliases()) - 1


def test_inputs_section_appended_after_slots():
    ed, cfg = _editor()
    n_slots = len(build_slot_catalogue(cfg.slots))
    assert ed.top_len() == n_slots + len(INPUT_KNOBS)
    ed.slot_index = n_slots
    assert ed.is_input_row() is True
    assert ed.current_slot() is None
    assert ed.current_knob() is INPUT_KNOBS[0]
    assert ed.highlight_region() == REGION_INPUTS


def test_inputs_knob_adjusts_value_on_config_clamped():
    ed, cfg = _editor()
    n_slots = len(build_slot_catalogue(cfg.slots))
    ed.slot_index = n_slots                              # land on scroll_delta knob
    knob = ed.current_knob()
    start = getattr(cfg, knob.attr)
    ed.enter()
    assert ed.level == LEVEL_INPUTS
    ed.move_up()                                          # increases (by the knob step)
    assert getattr(cfg, knob.attr) == type(start)(start + knob.step)
    for _ in range(100):
        ed.move_down()
    assert getattr(cfg, knob.attr) == type(start)(knob.floor)
    bind = ed.enter()                                     # commit -> back at SLOTS, no Bind
    assert bind is None and ed.level == LEVEL_SLOTS


def test_inputs_back_returns_to_slots_without_exit():
    ed, _ = _editor()
    n_slots = len(ed.catalogue)
    ed.slot_index = n_slots
    ed.enter()
    assert ed.level == LEVEL_INPUTS
    ed.back()
    assert ed.level == LEVEL_SLOTS and ed.at_top_level() is True
