"""plumbing_demo -- a self-contained TUI that OPTS INTO all 7 generic view-plumbing capabilities.

Run:  PYTHONPATH=/path/to/glyfi python -m examples.plumbing_demo

No server is needed -- a fake echo transport stands in for the stepper so the demo is purely a
rendering/interaction proof. Every capability is opted in via a single hook/flag (no subclassing):

  C1  key_preprocessor   -- Ctrl-G is a custom chord: it pushes a ">>CHORD FIRED<<" status.
  C2a VisualRow.color_role  -- (model seam; exercised in tests) the renderer honours per-row roles.
  C2b row_classifier     -- content lines are colored by a leading marker (#header / ERR / def / >search).
  C3  list windowing     -- 30 palette commands registered, so the palette scrolls (↑/↓ N more).
  C4  pre_render         -- the input field grows to match the buffer's line count.
  C5  post_paint         -- a multi-line buffer renders across N rows with a correct caret.
  C6  bracketed_paste    -- a pasted multi-line block is inserted as text (newlines never submit).
  C7  widget_keys        -- F2 is bound to the built-in 'about' widget (first-class F-key binding).
"""
from __future__ import annotations

import curses

from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import AppSettings
from glyfi.ui.view import RegionPainter
from glyfi.ui.viewmodel import AppViewModel, DEFAULT_MODES
from glyfi.ui.config_store import UserConfig
from glyfi.ui.curses_view import CursesView
from glyfi.ui.input_painter import make_multi_line_input_painter, make_pre_render_dynamic_height
from glyfi.ui import theme
from glyfi.stepper import Stepper
from glyfi.transport import Transport
from glyfi.protocol import TurnResponse


CTRL_G = 7   # the custom chord key (C1)


class _EchoTransport(Transport):
    """A no-server transport: echoes the latest message back (the demo never hits a real backend)."""
    def send(self, req):
        m = req.messages[-1]
        return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                            subject=m.subject, content=f'echo:{m.content}', mode=req.mode)


# -- C1: a custom key preprocessor (a chord the base run() never knew about) ---------
def preprocess_key(vm, ch: int) -> bool:
    if ch == CTRL_G:
        vm.push_status('>>CHORD FIRED<< (Ctrl-G handled by the C1 key_preprocessor)')
        return True          # consumed -> base dispatch_key is skipped
    return False             # everything else passes through unchanged


# -- C2b: a per-row semantic classifier (leading-marker -> ROLE_*) -------------------
def classify_row(region_name: str, line: str) -> str:
    s = line.lstrip()
    if s.startswith('#'):
        return theme.ROLE_ACCENT        # bold header
    if s.startswith('ERR'):
        return theme.ROLE_DESTRUCTIVE   # bold reverse (the only red)
    if s.startswith('def ') or s.startswith('│'):
        return theme.ROLE_DIM           # dim code
    if s.startswith('>'):
        return theme.ROLE_ACCENT_2      # bold underline search hit
    return theme.ROLE_NORMAL


_SEED_CONTENT = [
    '# Section header (ROLE_ACCENT)',
    'plain narrative line (ROLE_NORMAL)',
    'def some_code():  # code line (ROLE_DIM)',
    '    return 42',
    'ERR: something went wrong (ROLE_DESTRUCTIVE)',
    '> search hit marker (ROLE_ACCENT_2)',
    'another plain line',
    'final newest line',
]


def build_viewmodel() -> AppViewModel:
    # 30 palette commands so the list overflows the content rect (C3 windowing).
    from glyfi.plugins import palette as palette_mod
    existing = {c.name for c in palette_mod.all_commands()}
    for i in range(30):
        name = f'demo_cmd_{i:02d}'
        if name not in existing:
            palette_mod.register_command(name, f'demo command number {i}', lambda vm: None)

    # C7: F2 -> a registered widget. 'help_widget' is shipped by the built-in plugins; fall back to the
    # first registered widget if the built-ins changed, so the demo never binds a non-existent name.
    from glyfi.widgets import host as _wh
    names = [n for n, _ in _wh.snapshot_widgets()]
    widget_name = 'help_widget' if 'help_widget' in names else (names[0] if names else '')
    widget_keys = {curses.KEY_F2: widget_name} if widget_name else {}
    settings = AppSettings(widget_keys=widget_keys)   # C7: F2 -> a registered widget
    model = AppModel(session=SessionState(session_id='demo-1'), settings=settings, config=UserConfig())
    model.set_content(_SEED_CONTENT)                              # seed content for the C2b color demo
    return AppViewModel(stepper=Stepper(transport=_EchoTransport(), session_id='demo-1'),
                        model=model, url='demo://local', modes=DEFAULT_MODES)


def main() -> None:
    # Try to register the built-in plugins (so /config etc. exist); ignore if already loaded.
    try:
        from glyfi.app import load_plugins
        load_plugins()
    except Exception:
        pass
    vm = build_viewmodel()
    painter = RegionPainter(post_paint=make_multi_line_input_painter())     # C5

    def _run(stdscr):
        view = CursesView(
            stdscr,
            painter,
            key_preprocessor=preprocess_key,             # C1
            row_classifier=classify_row,                 # C2b
            pre_render=make_pre_render_dynamic_height(),  # C4
            bracketed_paste=True,                        # C6
        )
        view.run(vm)

    curses.wrapper(_run)


if __name__ == '__main__':
    main()
