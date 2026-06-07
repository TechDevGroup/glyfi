from glyfi.ui import settings
from glyfi.ui.settings import (
    REGION_TITLE, REGION_STATE, REGION_HEADER_RULE, REGION_CONTENT, REGION_STATUS,
    REGION_INPUT_RULE, REGION_INPUT, REGION_STATUS_RULE, REGION_DETAILS, HIDEABLE_REGIONS,
    RULE_CHAR, INPUT_PROMPT, SLOT_SEP, DETAILS_GROUP_SEP,
    INPUT_HINT_LONG, INPUT_HINT_MED, INPUT_HINT_SHORT, INPUT_HINT_VARIANTS,
    KEY_QUIT, KEY_PROMPT, KEY_MODE_CYCLE, KEY_PALETTE, KEY_TRAVERSE,
    KEY_SCROLL_PAGE_UP, KEY_TICKER_CYCLE, CTRL_U, CTRL_D, TAB, DEFAULT_TITLE,
    AppSettings,
)
from glyfi.ui.layout import ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_FILL


def test_region_names():
    assert REGION_TITLE == 'title'
    assert REGION_STATE == 'state'
    assert REGION_HEADER_RULE == 'header_rule'
    assert REGION_CONTENT == 'content'
    assert REGION_STATUS == 'status'
    assert REGION_INPUT_RULE == 'input_rule'
    assert REGION_INPUT == 'input'
    assert REGION_STATUS_RULE == 'status_rule'
    assert REGION_DETAILS == 'details'
    assert HIDEABLE_REGIONS == (REGION_STATE, REGION_DETAILS)


def test_render_chars():
    assert RULE_CHAR == '─'
    assert INPUT_PROMPT == ' > '
    assert SLOT_SEP == '  '
    assert DETAILS_GROUP_SEP == '  '


def test_hint_variants_neutral_and_ordered():
    assert INPUT_HINT_VARIANTS == (INPUT_HINT_LONG, INPUT_HINT_MED, INPUT_HINT_SHORT)
    for h in INPUT_HINT_VARIANTS:
        assert 'step' not in h


def test_keybindings():
    assert KEY_QUIT == 'q'
    assert KEY_PROMPT == 's'
    assert KEY_MODE_CYCLE == 'm'
    assert KEY_PALETTE == '/'
    assert KEY_TRAVERSE == 'c'
    assert KEY_SCROLL_PAGE_UP == 'page_up'
    assert KEY_TICKER_CYCLE == 'ticker_cycle'
    assert CTRL_U == 21
    assert CTRL_D == 4
    assert TAB == 9
    assert DEFAULT_TITLE == 'glyfi'


def test_no_target_cycle_key():
    assert not hasattr(settings, 'KEY_TARGET_CYCLE')


def test_default_settings_title_and_keys():
    s = AppSettings()
    assert s.title == 'glyfi'
    assert s.keys == {
        'q': 'quit', 's': 'prompt', 'm': 'mode_cycle', '/': 'palette', 'c': 'traverse',
    }


def test_command_for():
    s = AppSettings()
    assert s.command_for('q') == 'quit'
    assert s.command_for('z') == ''


def test_default_regions_anchors_and_order():
    s = AppSettings()
    by_name = {r.name: r for r in s.regions}
    assert by_name[REGION_TITLE].anchor == ANCHOR_TOP
    assert by_name[REGION_STATE].anchor == ANCHOR_TOP
    assert by_name[REGION_HEADER_RULE].anchor == ANCHOR_TOP
    assert by_name[REGION_CONTENT].anchor == ANCHOR_FILL
    for name in (REGION_DETAILS, REGION_STATUS_RULE, REGION_INPUT, REGION_INPUT_RULE, REGION_STATUS):
        assert by_name[name].anchor == ANCHOR_BOTTOM
    # exactly one FILL
    assert sum(1 for r in s.regions if r.anchor == ANCHOR_FILL) == 1


def test_default_regions_solve():
    from glyfi.ui.layout import solve_layout, Size
    s = AppSettings()
    placed = solve_layout(Size(80, 24), list(s.regions))
    assert set(placed) == {r.name for r in s.regions}
    assert placed[REGION_CONTENT].h > 0
