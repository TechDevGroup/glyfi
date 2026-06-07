import pytest

from glyfi.ui import theme


def test_roles_tuple_and_values():
    assert theme.ROLE_NORMAL == 'normal'
    assert theme.ROLE_DIM == 'dim'
    assert theme.ROLE_ACCENT == 'accent'
    assert theme.ROLE_ACCENT_2 == 'accent2'
    assert theme.ROLE_SELECT == 'select'
    assert theme.ROLE_DESTRUCTIVE == 'destructive'
    assert theme.ROLES == (
        theme.ROLE_NORMAL, theme.ROLE_DIM, theme.ROLE_ACCENT,
        theme.ROLE_ACCENT_2, theme.ROLE_SELECT, theme.ROLE_DESTRUCTIVE,
    )
    assert theme.ACCENT_RING == (theme.ROLE_ACCENT, theme.ROLE_ACCENT_2)


def test_theme_keys():
    assert theme.THEME_MAROON_SELECT == 'maroon-select'
    assert theme.DEFAULT_THEME == theme.THEME_MAROON_SELECT
    assert theme.THEMES == (theme.THEME_MAROON_SELECT,)


def test_color_indexes_preserved():
    assert theme.COLOR_SELECT_BG == 131
    assert theme.COLOR_SELECT_FG == 231
    assert theme.COLOR_DIM == 244
    assert theme.COLOR_ACCENT == 39
    assert theme.COLOR_ACCENT_2 == 213
    assert theme.COLOR_DESTRUCTIVE == 196
    assert theme.COLOR_DEFAULT_FG == -1


def test_pair_ids():
    assert theme.PAIR_SELECT == 1
    assert theme.PAIR_DIM == 2
    assert theme.PAIR_ACCENT == 3
    assert theme.PAIR_ACCENT_2 == 4
    assert theme.PAIR_DESTRUCTIVE == 5


def test_marker_chars():
    assert theme.FOCUS_MARKER == '▸'
    assert theme.FOCUS_MARKER_BLANK == ' '
    assert theme.BREADCRUMB_SEP == ' › '
    assert theme.ACCENT_TRIM == '┃'
    assert theme.SCROLLBAR_FULL == '█'
    assert theme.SCROLLBAR_EMPTY == '░'
    assert theme.NEW_BELOW_MARKER == '▼'


def test_init_theme_unknown_fails_loud():
    with pytest.raises(ValueError):
        theme.init_theme('no-such-theme')


def test_role_attr_unknown_role_fails_loud():
    with pytest.raises(ValueError):
        theme.role_attr('bogus')


def test_accent_for_depth_progressive():
    assert theme.accent_for_depth(0) == theme.ROLE_ACCENT
    assert theme.accent_for_depth(1) == theme.ROLE_ACCENT_2
    assert theme.accent_for_depth(2) == theme.ROLE_ACCENT     # wraps the ring


def test_accent_for_depth_negative_fails_loud():
    with pytest.raises(ValueError):
        theme.accent_for_depth(-1)
