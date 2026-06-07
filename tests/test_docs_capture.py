"""Tests for the documentation-capture CORE -- frame composition, region/sub slicing, padding, MD-safe fences."""
from glyfi.contrib.docs_capture.capture import (
    BORDER_BOTTOM_LEFT, BORDER_TOP_LEFT, FENCE_MARKER, FENCE_MIN_LEN, frame_rows, markdown_screen,
    pad_block, region_rows, screen_fence, sub_rows,
)
from glyfi.ui.layout import Rect, Size
from glyfi.ui.view import Painting


def _painting() -> Painting:
    return Painting(regions={
        'title': ['hi'],
        'content': ['line one', 'two'],
        'status': ['ok'],
    })


def _layout():
    return {
        'title': Rect(x=0, y=0, w=10, h=1),
        'content': Rect(x=0, y=1, w=10, h=2),
        'status': Rect(x=0, y=3, w=10, h=1),
    }


# ===== frame composition ===================================================================================

def test_frame_rows_places_regions_at_their_rect_and_pads_to_width():
    rows = frame_rows(_painting(), _layout(), Size(w=10, h=4))
    assert len(rows) == 4
    assert all(len(r) == 10 for r in rows)          # every row padded to size.w
    assert rows[0] == 'hi' + ' ' * 8               # title at (0,0)
    assert rows[1].startswith('line one')          # content first line at y=1
    assert rows[2].startswith('two')               # content second line at y=2
    assert rows[3].startswith('ok')                # status at y=3


def test_frame_rows_blank_fills_gaps_and_is_deterministic():
    painting = Painting(regions={'title': ['x']})
    layout = {'title': Rect(x=2, y=1, w=4, h=1)}
    rows_a = frame_rows(painting, layout, Size(w=8, h=3))
    rows_b = frame_rows(painting, layout, Size(w=8, h=3))
    assert rows_a == rows_b                          # deterministic
    assert rows_a[0] == ' ' * 8                      # row 0 is all blank
    assert rows_a[1] == '  x     '                   # 'x' stamped at x=2,y=1
    assert all(len(r) == 8 for r in rows_a)


def test_frame_rows_clips_region_text_to_its_rect_width():
    painting = Painting(regions={'a': ['abcdefgh']})
    layout = {'a': Rect(x=0, y=0, w=3, h=1)}
    rows = frame_rows(painting, layout, Size(w=8, h=1))
    assert rows[0] == 'abc     '                     # only 3 cols stamped, rest blank to width 8


# ===== region + sub slicing + padding ======================================================================

def test_region_rows_pads_to_common_width():
    rows = region_rows(_painting(), 'content')
    assert rows == ['line one', 'two     ']          # 'two' padded to 8 (widest row)


def test_region_rows_empty_region_is_empty_block():
    assert region_rows(_painting(), 'missing') == []


def test_sub_rows_slices_column_and_row_subrectangle():
    block = ['ABCDEF', 'abcdef', '123456']
    out = sub_rows(block, Rect(x=1, y=0, w=3, h=2))
    assert out == ['BCD', 'bcd']


def test_sub_rows_pads_short_rows_before_slicing():
    block = ['long row here', 'x']                   # second row much shorter
    out = sub_rows(block, Rect(x=2, y=0, w=4, h=2))
    assert len(out) == 2 and all(len(r) == 4 for r in out)
    assert out[1] == '    '                          # the short row's column slice is blank, not under-cut


def test_pad_block_constant_width():
    out = pad_block(['a', 'bbb', 'cc'])
    assert out == ['a  ', 'bbb', 'cc ']
    out2 = pad_block(['a', 'bb'], width=5)
    assert out2 == ['a    ', 'bb   ']


# ===== fence MD-safety + escalation ========================================================================

def test_screen_fence_uses_tilde_fence_safe_with_backticks():
    fence = screen_fence(['```code```'], border=False)
    lines = fence.split('\n')
    assert lines[0].startswith(FENCE_MARKER * FENCE_MIN_LEN)   # tilde fence, not backtick
    assert lines[-1] == FENCE_MARKER * FENCE_MIN_LEN
    assert '```code```' in fence                               # backticks survive untouched


def test_screen_fence_escalates_when_rows_contain_the_marker():
    # a row carrying a run of tildes longer than the minimum forces a longer fence
    long_run = FENCE_MARKER * (FENCE_MIN_LEN + 2)
    fence = screen_fence([long_run], border=False)
    opening = fence.split('\n')[0]
    closing = fence.split('\n')[-1]
    assert len(opening.rstrip('text')) > len(long_run)         # fence longer than the inner run
    assert closing == opening.rstrip('text')                   # closing matches the escalated fence
    # the block is not closed early: the inner run line still appears between the fences
    assert long_run in fence.split('\n')[1:-1]


def test_screen_fence_rows_are_constant_width():
    fence = screen_fence(['a', 'bbbb', 'cc'], border=False)
    body = fence.split('\n')[1:-1]
    assert len({len(r) for r in body}) == 1                    # all body rows equal width


def test_screen_fence_border_draws_a_box():
    fence = screen_fence(['hello'], border=True)
    body = fence.split('\n')[1:-1]
    assert body[0].startswith(BORDER_TOP_LEFT)
    assert body[-1].startswith(BORDER_BOTTOM_LEFT)
    # the top edge spans the same width as the framed body rows (flush vertical edges)
    assert len(body[0]) == len(body[1]) == len(body[-1])


def test_screen_fence_border_title_in_top_edge():
    fence = screen_fence(['a wide enough row'], border=True, title='demo')
    top = fence.split('\n')[1]
    assert 'demo' in top
    assert top.startswith(BORDER_TOP_LEFT)


def test_screen_fence_info_string_default_and_custom():
    assert screen_fence(['x'], border=False).split('\n')[0].endswith('text')
    assert screen_fence(['x'], border=False, info='').split('\n')[0] == FENCE_MARKER * FENCE_MIN_LEN


# ===== markdown_screen over a driver =======================================================================

def _driver():
    from glyfi.uitest.fixtures import build_mock_context, MockTransport
    return build_mock_context(MockTransport()).driver


def test_markdown_screen_full_frame_is_md_compliant_and_aligned():
    md = markdown_screen(_driver(), title='frame')
    lines = md.split('\n')
    assert lines[0].startswith(FENCE_MARKER * FENCE_MIN_LEN)
    assert lines[-1].startswith(FENCE_MARKER)
    body = lines[1:-1]
    assert len({len(r) for r in body}) == 1                    # column-aligned rectangle
    assert 'frame' in body[0]                                   # title on the top edge


def test_markdown_screen_single_region():
    md = markdown_screen(_driver(), region='title')
    assert 'title' in md.split('\n')[1]                         # region name became the title


def test_markdown_screen_sub_rect():
    d = _driver()
    md = markdown_screen(d, sub=Rect(x=0, y=0, w=12, h=1), border=False)
    body = md.split('\n')[1:-1]
    assert len(body) == 1 and len(body[0]) == 12
