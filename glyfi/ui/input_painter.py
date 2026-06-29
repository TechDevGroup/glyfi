"""input_painter -- pure helpers + ready-made hooks for true multi-row input rendering (C5).

Given a buffer string with embedded ``\\n`` chars, compute the correct display rows, the
caret ``(row, col)`` position, and a visible window for long buffers that exceed
``INPUT_MAX_ROWS``. The pure helpers (``buffer_lines`` / ``caret_rowcol`` / ``visible_window``
/ ``input_height``) are data-free -- no curses, no vm, no I/O.

Two ready-made hook factories wire the helpers into the base seams without subclassing:

  * ``make_multi_line_input_painter()`` -> a ``post_paint`` hook for ``RegionPainter`` (C5):
    patches REGION_INPUT to render an N-line buffer across N rows with a correct caret cell.
  * ``make_pre_render_dynamic_height()`` -> a ``pre_render`` hook for ``CursesView`` (C4):
    grows REGION_INPUT to match the buffer's line count BEFORE the layout is solved.

For multi-line input both hooks must be opted in together (C4 grows the field, C5 fills it).

OCP default: neither hook exists unless a consumer constructs and passes it. A single-line
buffer (or PALETTE mode) is left unchanged by both hooks, so opting in costs nothing until
the buffer actually contains a newline.

Pure helpers ported verbatim from the downstream consumer's proven ``input_render`` module
(acraflow/glyfi_client); the hook factories port its ``_ExtPainter.paint`` / ``_Ext.render``
wiring into reusable callables.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Callable, Dict, List, Tuple

INPUT_MAX_ROWS = 6  # hard cap: field never grows beyond this many rows; long buffers scroll internally
# Continuation-line indent: same width as INPUT_PROMPT (' > ', 3 chars) so all lines are visually aligned.
# NAMED here so the painter can compute caret_col = len(INPUT_PROMPT) regardless of which row it's on (G33).
INPUT_CONTINUATION = '   '  # 3 spaces, width = len(INPUT_PROMPT)


def buffer_lines(buf: str) -> List[str]:
    """Split buffer at ``\\n`` into display lines.

    Empty buffer -> ``['']`` (one empty line; the field shows at height 1 with the hint text).
    Trailing ``\\n`` -> empty string as the last element (caret can sit on an empty final row).

    Pure / no side-effects.
    """
    if not buf:
        return ['']
    return buf.split('\n')


def caret_rowcol(buf: str, caret: int) -> Tuple[int, int]:
    """Compute ``(row, col)`` of ``caret`` within ``buf`` when rendered line-by-line.

    row -- 0-indexed line number in ``buffer_lines(buf)`` the caret falls on.
    col -- character offset WITHIN that line (before the INPUT_PROMPT/continuation prefix).

    Caret is clamped to ``[0, len(buf)]``. Pure / no side-effects.
    """
    caret = max(0, min(caret, len(buf)))
    text_before = buf[:caret]
    rows = text_before.split('\n')
    row = len(rows) - 1
    col = len(rows[-1])
    return row, col


def visible_window(lines: List[str], caret_row: int, max_rows: int) -> Tuple[int, List[str]]:
    """Return ``(start_row, visible_slice)`` -- a window of at most ``max_rows`` lines including ``caret_row``.

    When the buffer has <= ``max_rows`` lines, ``start_row=0`` and the full list is returned
    (no scrolling). Otherwise the window is centred on the caret, clamped to the buffer bounds.

    Pure / no side-effects.
    """
    n = len(lines)
    if n <= max_rows:
        return 0, lines
    half = max_rows // 2
    start = caret_row - half
    start = max(0, min(start, n - max_rows))
    return start, lines[start:start + max_rows]


def input_height(buf: str, max_rows: int = INPUT_MAX_ROWS) -> int:
    """How many rows the input field needs to display this buffer (1 .. ``max_rows``).

    Single-line or empty buffer -> 1 (identical to today's behaviour).
    Each ``\\n`` adds one row, capped at ``max_rows``.

    Pure / no side-effects.
    """
    if not buf:
        return 1
    return min(max_rows, buf.count('\n') + 1)


# -- Ready-made hook factories -------------------------------------------------------

def make_multi_line_input_painter() -> Callable:
    """Return a ``post_paint`` hook that patches REGION_INPUT for multi-line buffers (C5).

    For single-line buffers or PALETTE mode (G34): returns the painting unchanged.
    For buffers with ``\\n``: replaces REGION_INPUT lines with per-buffer-line rows and
    places the caret cell at the correct ``(vis_row, col)`` from ``caret_rowcol()``.

    The returned hook signature is ``(vm, layout, painting) -> Painting``. ``Painting`` is
    frozen (G36) so it is patched via ``dataclasses.replace`` -- never attribute assignment.
    """
    def post_paint(vm, layout, painting):
        from glyfi.ui.view import _clip_lines             # private but stable; base is read-only
        from glyfi.ui.settings import REGION_INPUT, INPUT_PROMPT
        from glyfi.ui.viewmodel import UI_PALETTE
        if REGION_INPUT not in layout:
            return painting
        buf = getattr(vm, 'input_buffer', '')
        if getattr(vm, 'mode_ui', None) == UI_PALETTE or '\n' not in buf:
            return painting                                # single-line or palette: no change (G34)
        rect = layout[REGION_INPUT]
        lines = buffer_lines(buf)
        caret = max(0, min(getattr(vm, 'input_caret', 0), len(buf)))
        crow, ccol = caret_rowcol(buf, caret)
        start_row, visible = visible_window(lines, crow, INPUT_MAX_ROWS)
        # Build display lines: absolute row 0 (when the window starts at 0) gets INPUT_PROMPT;
        # continuation rows get INPUT_CONTINUATION. Both are the same width so
        # caret_col = len(INPUT_PROMPT) + ccol is correct for any row (G33).
        result = []
        for i, line_text in enumerate(visible):
            prefix = INPUT_PROMPT if (i == 0 and start_row == 0) else INPUT_CONTINUATION
            result.append(f'{prefix}{line_text}')
        clipped = _clip_lines(result, rect)
        vis_crow = crow - start_row
        caret_cell = None
        if bool(buf) and 0 <= vis_crow < rect.h:
            caret_col = len(INPUT_PROMPT) + ccol          # same width for PROMPT and CONTINUATION (G33)
            if caret_col < rect.w:
                caret_cell = (vis_crow, caret_col, caret_col + 1)
        new_regions = dict(painting.regions)
        new_regions[REGION_INPUT] = clipped
        new_cells = dict(painting.highlight_cells)
        if caret_cell is not None:
            new_cells[REGION_INPUT] = caret_cell
        else:
            new_cells.pop(REGION_INPUT, None)
        return replace(painting, regions=new_regions, highlight_cells=new_cells)
    return post_paint


def make_pre_render_dynamic_height(max_rows: int = INPUT_MAX_ROWS) -> Callable:
    """Return a ``pre_render`` hook that grows REGION_INPUT to match the buffer's line count (C4).

    Each frame: computes ``input_height(buf)``, reads the current REGION_INPUT Region size,
    and replaces ``vm.model.settings`` (frozen AppSettings) when the sizes differ -- so the
    layout solver carves the taller input band on this frame. No-op when the height is
    unchanged (the common single-line case is one ``buf.count('\\n')`` + a comparison).

    MUST be wired so it fires BEFORE ``viewmodel.resize(size)`` (G35); ``CursesView.render``
    calls the ``pre_render`` hook at the top of the frame, before the layout solve.
    The FILL region (REGION_CONTENT) absorbs the height delta automatically.

    The returned hook signature is ``(vm) -> None``.
    """
    def pre_render(vm):
        from glyfi.ui.settings import REGION_INPUT
        buf = getattr(vm, 'input_buffer', '')
        needed = input_height(buf, max_rows)
        regions = vm.model.settings.regions
        cur = next((r for r in regions if r.name == REGION_INPUT), None)
        if cur is not None and cur.size != needed:
            new_regions = tuple(
                replace(r, size=needed) if r.name == REGION_INPUT else r
                for r in regions
            )
            vm.model.settings = replace(vm.model.settings, regions=new_regions)
    return pre_render


# A ready-made instance for the common case (the spec's worked example imports this name).
pre_render_dynamic_height: Callable = make_pre_render_dynamic_height()
