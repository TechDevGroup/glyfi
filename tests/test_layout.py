import pytest

from glyfi.ui.layout import (
    ANCHORS, ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT, ANCHOR_FILL,
    EDGE_ANCHORS, HORIZONTAL_BANDS, VERTICAL_BANDS,
    LayoutError, Size, Rect, Region, solve_layout, free_rect_after,
)


def test_named_anchor_tuples():
    assert ANCHORS == (ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT, ANCHOR_FILL)
    assert EDGE_ANCHORS == (ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT)
    assert HORIZONTAL_BANDS == (ANCHOR_TOP, ANCHOR_BOTTOM)
    assert VERTICAL_BANDS == (ANCHOR_LEFT, ANCHOR_RIGHT)


def test_rect_area_and_empty():
    assert Rect(0, 0, 4, 3).area == 12
    assert not Rect(0, 0, 4, 3).is_empty
    assert Rect(0, 0, 0, 3).is_empty
    assert Rect(0, 0, 4, 0).is_empty


def test_region_rejects_unknown_anchor():
    with pytest.raises(LayoutError):
        Region(name='x', anchor='middle', size=1)


def test_region_rejects_nonpositive_edge_size():
    with pytest.raises(LayoutError):
        Region(name='x', anchor=ANCHOR_TOP, size=0)


def test_region_rejects_negative_min_and_min_over_size():
    with pytest.raises(LayoutError):
        Region(name='x', anchor=ANCHOR_TOP, size=2, min_size=-1)
    with pytest.raises(LayoutError):
        Region(name='x', anchor=ANCHOR_TOP, size=2, min_size=3)


def test_region_floor_defaults_to_size():
    assert Region(name='x', anchor=ANCHOR_TOP, size=3).floor == 3
    assert Region(name='x', anchor=ANCHOR_TOP, size=3, min_size=1).floor == 1


def test_fill_takes_residual():
    regions = [
        Region(name='top', anchor=ANCHOR_TOP, size=2),
        Region(name='bot', anchor=ANCHOR_BOTTOM, size=1),
        Region(name='body', anchor=ANCHOR_FILL),
    ]
    placed = solve_layout(Size(10, 10), regions)
    assert placed['top'] == Rect(0, 0, 10, 2)
    assert placed['bot'] == Rect(0, 9, 10, 1)
    assert placed['body'] == Rect(0, 2, 10, 7)


def test_left_right_carve_columns():
    regions = [
        Region(name='l', anchor=ANCHOR_LEFT, size=3),
        Region(name='r', anchor=ANCHOR_RIGHT, size=2),
        Region(name='c', anchor=ANCHOR_FILL),
    ]
    placed = solve_layout(Size(10, 5), regions)
    assert placed['l'] == Rect(0, 0, 3, 5)
    assert placed['r'] == Rect(8, 0, 2, 5)
    assert placed['c'] == Rect(3, 0, 5, 5)


def test_multi_fill_fails_loud():
    regions = [Region(name='a', anchor=ANCHOR_FILL), Region(name='b', anchor=ANCHOR_FILL)]
    with pytest.raises(LayoutError):
        solve_layout(Size(10, 10), regions)


def test_smush_fill_yields_first():
    # bands fit exactly (no floor needed); the FILL squeezes to the residual first.
    regions = [
        Region(name='top', anchor=ANCHOR_TOP, size=2),
        Region(name='bot', anchor=ANCHOR_BOTTOM, size=2),
        Region(name='body', anchor=ANCHOR_FILL),
    ]
    placed = solve_layout(Size(10, 4), regions)
    assert placed['top'].h == 2
    assert placed['bot'].h == 2
    assert placed['body'].h == 0     # FILL yielded all of its real-estate first


def test_smush_trims_chrome_to_floor_reverse_order():
    regions = [
        Region(name='top', anchor=ANCHOR_TOP, size=3, min_size=1),
        Region(name='bot', anchor=ANCHOR_BOTTOM, size=3, min_size=1),
        Region(name='body', anchor=ANCHOR_FILL),
    ]
    placed = solve_layout(Size(10, 4), regions)
    # last-listed band (bot) yields first toward its floor
    assert placed['top'].h == 3
    assert placed['bot'].h == 1
    assert placed['body'].h == 0


def test_smush_fails_when_floors_dont_fit():
    regions = [
        Region(name='top', anchor=ANCHOR_TOP, size=3, min_size=3),
        Region(name='bot', anchor=ANCHOR_BOTTOM, size=3, min_size=3),
    ]
    with pytest.raises(LayoutError):
        solve_layout(Size(10, 4), regions)


def test_free_rect_after():
    regions = [Region(name='top', anchor=ANCHOR_TOP, size=2)]
    assert free_rect_after(Size(8, 6), regions) == Rect(0, 2, 8, 4)
