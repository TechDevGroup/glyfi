"""layout -- the UI LAYOUT PASS: anchored regions re-solved against terminal dimensions.

This is the PURE geometry core of the UI -- a tiny layout model with NO terminal, NO curses. It takes a
``Size`` (the pane WxH) and a list of ``Region`` specs (each with an ``Anchor`` + a size hint) and SOLVES
them into concrete ``Rect`` placements -- the same layout pass re-run on every resize (SIGWINCH). Because it
is pure (dims in, rects out) the solver is UNIT-TESTABLE on synthetic dimensions WITHOUT a live terminal --
that is the whole point of separating the layout pass from the renderer.

The anchor model (named vocabulary, no magic strings):
  * ANCHOR_TOP / ANCHOR_BOTTOM   -- a horizontal band of fixed HEIGHT pinned to the top / bottom edge.
  * ANCHOR_LEFT / ANCHOR_RIGHT   -- a vertical band of fixed WIDTH pinned to the left / right edge.
  * ANCHOR_FILL                  -- the residual center region after the edge bands are carved away.

Solve order (deterministic): edge bands are carved off the available rectangle in REGION ORDER (top/bottom
carve rows, left/right carve columns), each shrinking the remaining ``free`` rect; the single FILL region
takes whatever rectangle is left. This makes the layout RESPONSIVE -- give it new dims and every rect re-solves.

Fail LOUD: an unknown anchor, a non-positive size hint on an edge band, more than one FILL region, or a band
that does not fit even after the FILL has fully yielded all raise ``LayoutError`` (never a silent clamp that
hides a mis-spec).

RESPONSIVE SMUSH (content yields first): when the pane is too small to hold every edge band AND the FILL, the
FILL region is the one that SQUEEZES -- it shrinks toward zero so the chrome (title/state/status/input/details)
keeps its minimums. Only when even the edge bands' MINIMUMS don't fit (with the FILL at zero) does the solve
fail loud. ``solve_layout`` does the SMUSH automatically; a region may declare a ``min_size`` (its hard floor)
distinct from its preferred ``size`` -- the smush trims a band from its preferred size down to its ``min_size``
(in reverse region order, so the LAST-listed chrome yields before the first) before the solve fails.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

ANCHOR_TOP = 'top'
ANCHOR_BOTTOM = 'bottom'
ANCHOR_LEFT = 'left'
ANCHOR_RIGHT = 'right'
ANCHOR_FILL = 'fill'
ANCHORS = (ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT, ANCHOR_FILL)
EDGE_ANCHORS = (ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT)
HORIZONTAL_BANDS = (ANCHOR_TOP, ANCHOR_BOTTOM)
VERTICAL_BANDS = (ANCHOR_LEFT, ANCHOR_RIGHT)


class LayoutError(Exception):
    """A fail-loud layout fault -- an unknown anchor, a bad size, multiple FILLs, or a band that won't fit."""


@dataclass(frozen=True)
class Size:
    """The terminal / pane dimensions the layout solves against (cols x rows)."""
    w: int
    h: int


@dataclass(frozen=True)
class Rect:
    """A solved placement -- the concrete rectangle a region occupies (origin x,y + width,height)."""
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def is_empty(self) -> bool:
        return self.w <= 0 or self.h <= 0


@dataclass(frozen=True)
class Region:
    """A LAYOUT region SPEC -- a named region anchored to an edge (or FILL) with a size hint + a min-size floor.

    ``size`` is the PREFERRED band thickness: a HEIGHT (rows) for TOP/BOTTOM, a WIDTH (cols) for LEFT/RIGHT, and
    is IGNORED for FILL (the fill region takes the residual rectangle, so its size is computed, not specified).
    ``min_size`` is the band's HARD FLOOR for the responsive SMUSH: when the pane is too small the solver trims
    a band from ``size`` toward ``min_size`` (after the FILL has fully yielded) -- it NEVER goes below the floor;
    if the floors still don't fit the solve fails loud. ``min_size`` defaults to ``size`` (no give) when 0.
    """
    name: str
    anchor: str
    size: int = 0
    min_size: int = 0

    def __post_init__(self):
        if self.anchor not in ANCHORS:
            raise LayoutError(f'region {self.name!r}: unknown anchor {self.anchor!r} (use {ANCHORS})')
        if self.anchor in EDGE_ANCHORS and self.size <= 0:
            raise LayoutError(f'region {self.name!r}: edge anchor {self.anchor!r} needs a positive size, got {self.size}')
        if self.min_size < 0:
            raise LayoutError(f'region {self.name!r}: min_size must be >= 0, got {self.min_size}')
        if self.min_size > self.size:
            raise LayoutError(f'region {self.name!r}: min_size {self.min_size} exceeds size {self.size}')

    @property
    def floor(self) -> int:
        """The hard minimum band thickness for the smush -- ``min_size`` when set, else the preferred ``size``."""
        return self.min_size if self.min_size > 0 else self.size


def _smush_sizes(regions: List[Region], anchor_group: Tuple[str, ...], available: int) -> Dict[str, int]:
    """Resolve the EFFECTIVE band thickness for each band in ``anchor_group``, smushing to fit ``available``.

    The FILL yields FIRST (it is not in this group -- its residual just shrinks, handled by the caller). Within
    this group: every band starts at its PREFERRED ``size``; if the sum exceeds ``available`` we trim bands from
    ``size`` down to their ``floor`` in REVERSE region order (the LAST-listed chrome yields before the first),
    one row at a time, until the group fits. Fail LOUD if the floors STILL don't fit (chrome can't be honored).
    """
    bands = [r for r in regions if r.anchor in anchor_group]
    sizes = {r.name: r.size for r in bands}
    total = sum(sizes.values())
    if total <= available:
        return sizes
    overflow = total - available
    for region in reversed(bands):
        give = sizes[region.name] - region.floor
        if give <= 0:
            continue
        take = min(give, overflow)
        sizes[region.name] -= take
        overflow -= take
        if overflow <= 0:
            break
    if overflow > 0:
        floors = {r.name: r.floor for r in bands}
        raise LayoutError(
            f'cannot fit {anchor_group} bands in {available}: even the minimums '
            f'{floors} (sum {sum(floors.values())}) exceed the available space')
    return sizes


def solve_layout(size: Size, regions: List[Region]) -> Dict[str, Rect]:
    """The LAYOUT PASS -- carve the pane into one Rect per region; re-run on every resize. SMUSH: content yields first.

    Edge bands are carved off the free rectangle in region order (TOP/BOTTOM take rows, LEFT/RIGHT take cols),
    each shrinking the remaining free rect; the lone FILL region takes whatever is left (it YIELDS first -- when
    the pane is small the FILL shrinks toward an empty rect so the chrome keeps its size). If the chrome bands
    alone still over-run the pane, each band is trimmed from its preferred ``size`` toward its ``min_size`` floor
    (last-listed first) -- the responsive SMUSH. Returns a name->Rect map. Fail LOUD on more than one FILL, or on
    bands whose MINIMUMS cannot fit even with the FILL fully yielded.
    """
    fills = [r for r in regions if r.anchor == ANCHOR_FILL]
    if len(fills) > 1:
        raise LayoutError(f'layout has {len(fills)} FILL regions; at most one is allowed')
    h_sizes = _smush_sizes(regions, HORIZONTAL_BANDS, size.h)
    v_sizes = _smush_sizes(regions, VERTICAL_BANDS, size.w)
    free_x, free_y, free_w, free_h = (0, 0, size.w, size.h)
    placed: Dict[str, Rect] = {}
    for region in regions:
        if region.anchor == ANCHOR_FILL:
            continue
        if region.anchor in HORIZONTAL_BANDS:
            band = h_sizes[region.name]
            if region.anchor == ANCHOR_TOP:
                placed[region.name] = Rect(free_x, free_y, free_w, band)
                free_y += band
            else:
                placed[region.name] = Rect(free_x, free_y + free_h - band, free_w, band)
            free_h -= band
        else:
            band = v_sizes[region.name]
            if region.anchor == ANCHOR_LEFT:
                placed[region.name] = Rect(free_x, free_y, band, free_h)
                free_x += band
            else:
                placed[region.name] = Rect(free_x + free_w - band, free_y, band, free_h)
            free_w -= band
    for region in fills:
        placed[region.name] = Rect(free_x, free_y, max(0, free_w), max(0, free_h))
    return placed


def free_rect_after(size: Size, regions: List[Region]) -> Rect:
    """The residual rectangle left after carving every EDGE band -- the FILL area (handy for tests/diagnostics)."""
    solved = solve_layout(size, list(regions) + [Region(name='__free__', anchor=ANCHOR_FILL)])
    return solved['__free__']
