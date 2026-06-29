"""Unit tests for glyfi.ui.list_window.window_around -- the pure list-windowing helper (C3).

Exhaustive coverage of the edge cases documented in the module docstring. Data-free, pure:
no curses, no network. Ported from the downstream consumer's proven scroll_window tests.
"""
from __future__ import annotations

from glyfi.ui.list_window import window_around


LINES = [f"line {i}" for i in range(10)]  # indices 0..9


class TestWindowAroundBasic:
    def test_height_greater_than_len_returns_all(self):
        vis, f = window_around(LINES, focus=5, height=20)
        assert vis == LINES
        assert f == 5

    def test_height_equal_to_len_returns_all(self):
        vis, f = window_around(LINES, focus=0, height=10)
        assert vis == LINES
        assert f == 0

    def test_height_equal_to_len_focus_at_end(self):
        vis, f = window_around(LINES, focus=9, height=10)
        assert vis == LINES
        assert f == 9

    def test_focus_near_top_starts_at_zero(self):
        vis, f = window_around(LINES, focus=0, height=5)
        assert vis == LINES[:5]
        assert f == 0

    def test_focus_near_bottom_ends_at_last(self):
        vis, f = window_around(LINES, focus=9, height=5)
        assert vis == LINES[5:10]
        assert f == 4

    def test_focus_in_middle_is_inside_window(self):
        vis, f = window_around(LINES, focus=5, height=5)
        assert len(vis) == 5
        assert vis[f] == LINES[5]

    def test_cursor_row_is_always_visible(self):
        for height in range(1, len(LINES) + 1):
            for focus in range(len(LINES)):
                vis, f = window_around(LINES, focus=focus, height=height)
                assert 0 <= f < len(vis)
                assert vis[f] == LINES[focus]


class TestWindowAroundEdgeCases:
    def test_focus_none_returns_top_slice(self):
        vis, f = window_around(LINES, focus=None, height=4)
        assert vis == LINES[:4]
        assert f is None

    def test_height_zero_returns_empty(self):
        vis, f = window_around(LINES, focus=5, height=0)
        assert vis == []
        assert f is None

    def test_height_negative_returns_empty(self):
        vis, f = window_around(LINES, focus=5, height=-1)
        assert vis == []
        assert f is None

    def test_empty_lines_returns_empty(self):
        assert window_around([], focus=0, height=5) == ([], None)
        assert window_around([], focus=None, height=5) == ([], None)

    def test_height_1_returns_focus_row_only(self):
        vis, f = window_around(LINES, focus=7, height=1)
        assert vis == [LINES[7]]
        assert f == 0

    def test_focus_clamped_high(self):
        vis, f = window_around(LINES, focus=100, height=3)
        assert vis[-1] == LINES[-1]
        assert vis[f] == LINES[-1]

    def test_focus_clamped_negative(self):
        vis, f = window_around(LINES, focus=-1, height=3)
        assert vis[0] == LINES[0]
        assert f == 0

    def test_single_item_list(self):
        assert window_around(["only"], focus=0, height=5) == (["only"], 0)


class TestWindowAroundReturnContract:
    def test_visible_never_exceeds_height(self):
        for height in range(1, 12):
            for focus in range(len(LINES)):
                vis, _ = window_around(LINES, focus=focus, height=height)
                assert len(vis) <= height

    def test_returned_list_is_a_copy(self):
        vis, _ = window_around(LINES, focus=0, height=10)
        vis[0] = "MODIFIED"
        assert LINES[0] != "MODIFIED"
