"""BDD specs for the NAVIGATION wave -- the never-stuck reserved-Esc fix and the wrap-aware CONTENT-TRAVERSAL
caret + collapse/expand + no-ellipsis, driven headless through the framework.

These pin the fixes a live session surfaced:
  (a) NEVER-STUCK: Esc closes a widget back to NORMAL (the modal dead-end is gone).
  (b) CONTENT-TRAVERSAL: a long content line WRAPS (no ``...``); the caret moves wrap-aware from the newest entry;
      Left/Right collapse/expand the entry under the caret.

CI-safe (mock transport, virtual clock); MANUAL one-turn (every step is one explicit drive call).
"""
import os
import curses
import pytest

import glyfi.widgets.help_widget as help_widget   # importing registers WIDGET_HELP on the host
from glyfi.ui.config_store import ENV_CONFIG, UserConfig
from glyfi.ui.settings import KEY_TRAVERSE
from glyfi.ui.viewmodel import UI_NORMAL, UI_WIDGET, UI_TRAVERSE
import glyfi.uitest as U


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


# ===== SPEC A -- NEVER-STUCK: reserved Esc closes an open widget back to NORMAL =============================
def test_spec_esc_closes_widget_to_normal():
    ctx = U.fresh_app().setup(None)
    # open a widget directly (it takes the content region; mode -> WIDGET).
    ctx.driver.vm.open_widget(help_widget.WIDGET_HELP)
    ctx.driver.render()
    assert ctx.driver.vm.mode_ui == UI_WIDGET
    # Esc MUST unwind to NORMAL from the widget (reserved host key -- never a dead-end).
    U.Press(27).run(ctx)                          # 27 = Esc
    p = ctx.probe()
    assert U.mode_is(UI_NORMAL).check(p).holds, f'Esc must close the widget, got {p.mode_ui}'


# ===== SPEC B -- CONTENT-TRAVERSAL: wrap (no ellipsis) + caret from newest + collapse/expand ================
def _seed_long_transcript(w=60, h=14):
    """An app with a transcript whose newest turn carries a LONG user text (forces a wrap) -- the traverse subject."""
    long_text = 'fn:a ' + 'x' * 120 + ' tail-marker'   # far wider than 60 cols -> must wrap, never ellipsize
    turns = [('subj-1', 'short one'), ('subj-2', 'short two'), ('subj-3', long_text)]
    ctx = U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)).setup(None)
    ctx = U.at_size(w, h).setup(ctx)
    ctx = U.seeded_transcript(turns).setup(ctx)
    return ctx, long_text


def test_spec_content_wraps_no_ellipsis():
    ctx, long_text = _seed_long_transcript()
    p = ctx.probe()
    # the long line WRAPPED -- no ``...`` truncation anywhere in the content region.
    assert U.no_ellipsis('content').check(p).holds, p.regions['content']
    # the tail of the long text (which a clip would have dropped) is PRESENT somewhere in the wrapped content.
    assert U.region_contains('content', 'tail-marker').check(p).holds, p.regions['content']


def test_spec_content_traversal_caret_from_newest_and_collapse_expand():
    ctx, _ = _seed_long_transcript()
    # enter CONTENT-TRAVERSAL via the named key (c) -- a caret over wrapped rows, starting at the newest (bottom).
    U.Press(KEY_TRAVERSE).run(ctx)
    p = ctx.probe()
    assert U.mode_is(UI_TRAVERSE).check(p).holds
    assert U.caret_present('content').check(p).holds        # the focus marker is on a content row
    vm = ctx.driver.vm
    assert vm.traverse_caret.offset == 0                    # starts at the newest visual row
    # move the caret UP one wrapped visual row (toward older) -- it is wrap-aware (one VISUAL row, not one entry).
    U.Press(curses.KEY_UP).run(ctx)
    assert vm.traverse_caret.offset == 1
    U.Press(curses.KEY_DOWN).run(ctx)                       # back down toward newest
    assert vm.traverse_caret.offset == 0
    # the caret sits in the NEWEST entry (the long one). Collapse it (Left) -> a one-line summary header.
    rows_expanded = len(vm.content_visual_rows(vm.last_layout['content'].w))
    U.Press(curses.KEY_LEFT).run(ctx)
    rows_collapsed = len(vm.content_visual_rows(vm.last_layout['content'].w))
    assert rows_collapsed < rows_expanded, 'collapse must reduce the visual-row count (body hidden)'
    # Expand it again (Right) -> the full wrapped block returns.
    U.Press(curses.KEY_RIGHT).run(ctx)
    rows_reexpanded = len(vm.content_visual_rows(vm.last_layout['content'].w))
    assert rows_reexpanded == rows_expanded, 'expand must restore the full wrapped block'
    # Esc exits traverse -> NORMAL (never a dead-end).
    U.Press(27).run(ctx)
    assert U.mode_is(UI_NORMAL).check(ctx.probe()).holds


def test_spec_default_content_is_expanded_full():
    # the steer: the DEFAULT is full expanded wrapped lines (collapse is opt-in). Assert a fresh entry is
    # expanded (its body row is present in the content) without any operator collapse action.
    ctx, _ = _seed_long_transcript()
    p = ctx.probe()
    assert U.region_contains('content', 'tail-marker').check(p).holds   # body visible by default = expanded
