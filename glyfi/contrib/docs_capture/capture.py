"""capture -- a Markdown render TARGET over the SAME ``Painting`` the curses/headless Views consume.

This is the MVVM-consistent capture point: it does NOT re-implement rendering. It reads the already-painted
``Painting`` (region -> clipped lines) + the solved layout (region -> ``Rect``) + the pane ``Size`` and composes
them into a deterministic full-screen grid -- exactly what a terminal would show. The grid is then wrapped as a
Markdown-compliant fenced block (a "screen fence") so a runbook or a flow walkthrough can embed real UI state.

Public surface (all NAMED constants -- no magic literals):
  * ``frame_rows(painting, layout, size)`` -- the exact full-screen grid (region lines placed at their Rect).
  * ``region_rows(painting, region)``      -- one named region's lines, padded to a common width.
  * ``sub_rows(rows, rect)``               -- slice a column/row sub-rectangle out of a row block.
  * ``screen_fence(rows, ...)``            -- wrap rows as a Markdown fenced block (MD-safe; optional box border).
  * ``markdown_screen(driver, ...)``       -- the convenience over an ``AppDriver``'s current painting/layout/size.
  * ``MarkdownView``                       -- a ``View`` whose ``render(vm)`` produces the screen fence (symmetry).

Self-contained: ``glyfi.ui.view`` / ``glyfi.ui.layout`` / ``glyfi.ui.driver`` types + stdlib only. No curses, no
network, no ViewModel mutation. Deterministic: the same painting/layout/size always yields the same Markdown.
"""
from typing import Dict, List, Optional

from glyfi.ui.driver import AppDriver
from glyfi.ui.layout import Rect, Size
from glyfi.ui.view import Painting, View
from glyfi.ui.viewmodel import AppViewModel

# ---- NAMED fill / pad literals (no bare space/char at a compose site) --------------------------------------
BLANK_CELL = ' '                # the fill character for gaps and right-padding (one screen cell)
EMPTY_ROW = ''                  # a row with no content yet (filled to width by the composer)

# ---- NAMED Markdown fence literals (tilde fence -- safe even if the rows contain backticks) ----------------
FENCE_MARKER = '~'              # the fence delimiter char (a tilde run; never a backtick, so backticks are safe)
FENCE_MIN_LEN = 3               # the minimum fence length (Markdown requires at least three)
FENCE_INFO_DEFAULT = 'text'     # the default info string on the fence's opening line (a plain-text code block)

# ---- NAMED box-border chars (a clean frame around the captured screen; BORDER_* / FRAME_* names) -----------
BORDER_HORIZONTAL = '─'         # the top/bottom edge run
BORDER_VERTICAL = '│'           # the left/right edge
BORDER_TOP_LEFT = '┌'
BORDER_TOP_RIGHT = '┐'
BORDER_BOTTOM_LEFT = '└'
BORDER_BOTTOM_RIGHT = '┘'
FRAME_TITLE_PAD = ' '           # the single space framing a title within the top edge ('─ title ─')
FRAME_PAD = ' '                 # the single space between a vertical edge and the row content


def _row_width(rows: List[str]) -> int:
    """The widest row in a block (0 for an empty block) -- the common width every row pads up to."""
    return max((len(r) for r in rows), default=0)


def _pad_to(text: str, width: int) -> str:
    """Right-pad ``text`` with blank cells to exactly ``width`` columns (a longer row is left untouched)."""
    if len(text) >= width:
        return text
    return text + BLANK_CELL * (width - len(text))


def pad_block(rows: List[str], width: Optional[int] = None) -> List[str]:
    """Pad every row in ``rows`` to a CONSTANT width (the widest row, or ``width`` if given) -- columns line up."""
    target = width if width is not None else _row_width(rows)
    return [_pad_to(r, target) for r in rows]


def frame_rows(painting: Painting, layout: Dict[str, Rect], size: Size) -> List[str]:
    """Compose the EXACT full-screen grid -- every region's lines placed at its ``Rect`` (x, y), gaps blank-filled.

    Deterministic: builds a ``size.h`` x ``size.w`` grid of blank cells, then stamps each region's painted lines
    into the rows starting at its rect origin (clipping to the rect's width/height so a region never bleeds past
    its placement). Every row is padded to ``size.w`` so the result is a clean rectangle -- what the terminal
    would show. Regions absent from the layout (or the painting) simply leave their area blank.
    """
    grid: List[List[str]] = [[BLANK_CELL] * size.w for _ in range(size.h)]
    for region, rect in layout.items():
        lines = painting.lines(region)
        for dy in range(rect.h):
            row_index = rect.y + dy
            if not (0 <= row_index < size.h) or dy >= len(lines):
                continue
            text = lines[dy]
            for dx, ch in enumerate(text):
                col = rect.x + dx
                if dx >= rect.w or not (0 <= col < size.w):
                    break
                grid[row_index][col] = ch
    return [''.join(row) for row in grid]


def region_rows(painting: Painting, region: str) -> List[str]:
    """The painted lines of ONE named region, padded to a common (widest-row) width so they align as a block."""
    return pad_block(list(painting.lines(region)))


def sub_rows(rows: List[str], rect: Rect) -> List[str]:
    """Slice a column/row SUB-RECTANGLE out of a row block (capture a palette / area / slot by its extents).

    Pads the source to a constant width first (so a short row does not under-cut the column slice), then takes
    ``rect.h`` rows starting at ``rect.y`` and the ``[rect.x : rect.x + rect.w]`` column span of each. The result
    is itself a clean, constant-width block.
    """
    padded = pad_block(rows)
    out: List[str] = []
    for dy in range(max(0, rect.h)):
        src = rect.y + dy
        if not (0 <= src < len(padded)):
            out.append(EMPTY_ROW)
            continue
        out.append(padded[src][rect.x:rect.x + rect.w])
    return pad_block(out)


def _fence_run(rows: List[str]) -> str:
    """Pick a fence delimiter run LONGER than any fence-marker run inside ``rows`` (escalate to stay MD-safe).

    A fenced block is closed by the first line that is the fence delimiter. If a captured row somehow contains a
    run of the fence marker, the fence must be LONGER than that run so the block is not closed early. We scan for
    the longest marker run on any row and pick one longer (never below the Markdown minimum of three).
    """
    longest = 0
    for row in rows:
        run = 0
        for ch in row:
            if ch == FENCE_MARKER:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return FENCE_MARKER * max(FENCE_MIN_LEN, longest + 1)


def _box(rows: List[str], width: int, title: Optional[str]) -> List[str]:
    """Wrap a constant-width row block in a clean box border (an optional ``title`` set into the top edge).

    Each body row is framed ``'│ <row> │'`` -- the content occupies ``width`` columns plus a single ``FRAME_PAD``
    on each side, so the horizontal edges span ``width + 2`` to align flush with the body's vertical edges.
    """
    span = width + 2 * len(FRAME_PAD)
    top = _edge_with_title(span, title)
    bottom = BORDER_BOTTOM_LEFT + BORDER_HORIZONTAL * span + BORDER_BOTTOM_RIGHT
    body = [BORDER_VERTICAL + FRAME_PAD + _pad_to(r, width) + FRAME_PAD + BORDER_VERTICAL for r in rows]
    return [top] + body + [bottom]


def _edge_with_title(span: int, title: Optional[str]) -> str:
    """The TOP edge over ``span`` columns -- a horizontal run, optionally carrying ``'─ title ─'`` (clipped to fit)."""
    if not title:
        return BORDER_TOP_LEFT + BORDER_HORIZONTAL * span + BORDER_TOP_RIGHT
    label = f'{BORDER_HORIZONTAL}{FRAME_TITLE_PAD}{title}{FRAME_TITLE_PAD}'
    if len(label) > span:
        label = label[:span]
    fill = span - len(label)
    return BORDER_TOP_LEFT + label + BORDER_HORIZONTAL * fill + BORDER_TOP_RIGHT


def screen_fence(rows: List[str], *, border: bool = True, info: str = FENCE_INFO_DEFAULT,
                 title: Optional[str] = None) -> str:
    """Wrap ``rows`` as a Markdown fenced block -- one MD string. MD-compliant + column-aligned.

    Guarantees:
      * a TILDE fence (``~~~``) -- safe even when the captured rows contain backticks (a backtick fence would be
        closed by a row of backticks; a tilde fence is not);
      * the fence ESCALATES (gets longer) if a row contains a run of the tilde marker, so the block never closes
        early on its own content;
      * every row is padded to a CONSTANT width so columns line up under a monospace renderer;
      * with ``border=True`` a clean box is drawn around the rows (NAMED ``BORDER_*`` chars) with an optional
        ``title`` set into the top edge.
    """
    width = _row_width(rows)
    body = _box(rows, width, title) if border else pad_block(rows, width)
    fence = _fence_run(body)
    opening = f'{fence}{info}' if info else fence
    return '\n'.join([opening, *body, fence])


def markdown_screen(driver: AppDriver, *, region: Optional[str] = None, sub: Optional[Rect] = None,
                    border: bool = True, title: Optional[str] = None) -> str:
    """The convenience over an ``AppDriver`` -- the current frame, or one ``region``, or a ``sub``-rect, as MD.

    Reads the driver's CURRENT painting + solved layout + synthetic size (the frame a terminal would show), picks
    the requested rows (full frame by default; a single region; or a sub-rectangle of the full frame), and wraps
    them with ``screen_fence``. Pure read -- it never drives the app.
    """
    painting, layout, size = driver.frame()
    if region is not None:
        rows = region_rows(painting, region)
        title = title if title is not None else region
    else:
        rows = frame_rows(painting, layout, size)
        if sub is not None:
            rows = sub_rows(rows, sub)
    return screen_fence(rows, border=border, title=title)


class MarkdownView(View):
    """A ``View`` target whose ``render(vm)`` produces the screen fence -- "Markdown is just another View target".

    It solves the layout against a fixed ``Size`` and paints with the SAME pure ``RegionPainter`` the curses /
    headless Views use, then composes + fences the frame. The latest Markdown is kept on ``markdown`` for the
    caller to read. This makes the capture path explicitly an MVVM View, not a side-channel.
    """

    def __init__(self, size: Size, *, border: bool = True, title: Optional[str] = None):
        from glyfi.ui.view import RegionPainter
        self._size = size
        self._painter = RegionPainter()
        self._border = border
        self._title = title
        self.markdown: str = ''

    def render(self, viewmodel: AppViewModel) -> None:
        """Solve + paint the frame, then compose + fence it into ``self.markdown`` (the View's output target)."""
        layout = viewmodel.resize(self._size)
        painting = self._painter.paint(viewmodel, layout)
        rows = frame_rows(painting, layout, self._size)
        self.markdown = screen_fence(rows, border=self._border, title=self._title)
