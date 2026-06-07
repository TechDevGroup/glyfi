from glyfi.ui.content_view import (
    MARKER_COLLAPSED, MARKER_EXPANDED, WRAP_CONTINUATION, TRAVERSE_GUTTER, SUMMARY_ELLIPSIS,
    Entry, VisualRow, wrap_line, render_entries, TraverseCaret,
)


def test_named_markers():
    assert MARKER_COLLAPSED == '▸'
    assert MARKER_EXPANDED == '▾'
    assert WRAP_CONTINUATION == '  '
    assert TRAVERSE_GUTTER == 2
    assert SUMMARY_ELLIPSIS == ' …'


def test_entry_has_body():
    assert not Entry(summary='s').has_body
    assert Entry(summary='s', body=('a',)).has_body


def test_wrap_short_line_single_row():
    assert wrap_line('hi', 10) == ['hi']


def test_wrap_zero_width():
    assert wrap_line('hi', 0) == ['']


def test_wrap_never_ellipsizes_and_continues():
    rows = wrap_line('aaaa bbbb cccc', 6)
    assert len(rows) > 1
    # continuation rows carry the indent
    assert rows[1].startswith(WRAP_CONTINUATION)
    # no ellipsis introduced, all text preserved
    joined = rows[0] + ''.join(r[len(WRAP_CONTINUATION):] for r in rows[1:])
    assert '…' not in ''.join(rows)
    assert 'aaaa' in joined and 'cccc' in joined


def test_wrap_prefers_space_break():
    rows = wrap_line('hello world', 8)
    assert rows[0] == 'hello'


def test_render_collapsed_entry_only_summary_with_hint():
    rows = render_entries([Entry(summary='top', body=('b1', 'b2'), collapsed=True)], 40)
    assert len(rows) == 1
    assert rows[0].is_header
    assert rows[0].text == f'{MARKER_COLLAPSED} top{SUMMARY_ELLIPSIS}'


def test_render_expanded_entry_shows_body():
    rows = render_entries([Entry(summary='top', body=('b1', 'b2'))], 40)
    texts = [r.text for r in rows]
    assert texts[0] == f'{MARKER_EXPANDED} top'
    assert 'b1' in texts and 'b2' in texts
    assert rows[0].is_header
    assert not rows[1].is_header
    assert all(r.entry_index == 0 for r in rows)


def test_render_no_body_uses_collapsed_marker_no_hint():
    rows = render_entries([Entry(summary='solo')], 40)
    assert rows[0].text == f'{MARKER_COLLAPSED} solo'


def test_caret_clamp_empty():
    c = TraverseCaret(offset=5)
    c.clamp(0)
    assert c.offset == 0


def test_caret_up_down_clamped():
    c = TraverseCaret()
    c.up(3)
    assert c.offset == 1
    c.up(3)
    c.up(3)
    c.up(3)
    assert c.offset == 2          # clamped to total-1
    c.down(3)
    assert c.offset == 1
    c.down(3)
    c.down(3)
    assert c.offset == 0          # clamped at bottom


def test_caret_row_index_bottom_counted():
    c = TraverseCaret(offset=0)
    assert c.row_index(5) == 4    # offset 0 = newest/last row
    c.offset = 2
    assert c.row_index(5) == 2
    assert TraverseCaret().row_index(0) == -1


def test_visual_row_fields():
    r = VisualRow(text='x', entry_index=1, is_header=True)
    assert (r.text, r.entry_index, r.is_header) == ('x', 1, True)
