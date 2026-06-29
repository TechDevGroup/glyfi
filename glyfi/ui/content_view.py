"""content_view -- the PURE wrap + collapse/expand + caret model for the content region (no curses, no VM).

The content region used to CLIP each logical line to the width with an ellipsis -- which dropped text off the
edge (a hard no). This module replaces that with WRAP-AWARE rendering + a content-traversal caret:

  * WRAP -- a logical line longer than the width is WRAPPED into several VISUAL ROWS (never ellipsized). The
    wrap is width-aware and continuation-marked (a leading indent on wrapped rows so a block reads as one unit).
  * ENTRIES -- the content is segmented into ENTRY BLOCKS (one per transcript turn; the generic content buffer is
    one block). Each entry has a SUMMARY header (its first logical line) and a BODY (the rest). An entry can be
    COLLAPSED (show only the summary, marked) or EXPANDED (show the full wrapped body, marked).
  * CARET -- the content-traversal caret indexes the FLATTENED VISUAL ROWS, counted FROM THE NEWEST (bottom) row
    upward (offset 0 = the newest row). Moving up increases the offset; moving down decreases it. Right/Left
    expand/collapse the ENTRY the caret currently sits in.

This is the layer the ViewModel's content-traversal commands drive and the View renders. PURE: dataclasses +
stdlib only -- a test asserts the produced rows + caret directly.
"""
from dataclasses import dataclass
from typing import List, Tuple

# ---- NAMED markers (a11y: NON-COLOR chars -- the collapse/expand + caret state survive a mono terminal) -------
MARKER_COLLAPSED = '▸'      # a collapsed entry (its body is hidden) -- Right to expand
MARKER_EXPANDED = '▾'       # an expanded entry (its full wrapped body shows) -- Left to collapse
WRAP_CONTINUATION = '  '         # the leading indent prefixed to a WRAPPED continuation row (reads as one block)
TRAVERSE_GUTTER = 2              # cols the content-traversal focus marker occupies -- reserved from wrap width
SUMMARY_ELLIPSIS = ' …'          # appended to a COLLAPSED summary ONLY (a hint there is hidden body; never on text)


@dataclass(frozen=True)
class Entry:
    """One content ENTRY block -- a SUMMARY (the header logical line) + its BODY (the remaining logical lines).

    An entry maps to one transcript turn (header = the turn line, body = its staged-content / error lines) or to
    the whole generic content buffer (header = its first line, body = the rest). ``collapsed`` is per-entry UI
    state. PURE data -- the View never sees the raw transcript, only these segmented entries.
    """
    summary: str
    body: Tuple[str, ...] = ()
    collapsed: bool = False

    @property
    def has_body(self) -> bool:
        return len(self.body) > 0


@dataclass(frozen=True)
class VisualRow:
    """ONE rendered VISUAL ROW after wrapping + collapse -- the text + which ENTRY it belongs to + its role.

    ``entry_index`` ties the row back to its source entry (so the caret knows which entry to expand/collapse).
    ``is_header`` marks the entry's summary row (carries the collapse/expand marker). ``text`` is already wrapped
    to width (never ellipsized). The View paints these directly; the caret indexes into the row LIST.

    ``color_role`` (C2a) is an OPTIONAL ``ROLE_*`` hint for the renderer -- a model-level semantic-color seam.
    Default ``''`` means "no override" (the renderer treats the row as ROLE_NORMAL), so ``render_entries``
    produces rows identical to today; a consumer that wraps/subclasses ``render_entries`` may set it.
    """
    text: str
    entry_index: int
    is_header: bool
    color_role: str = ''


def wrap_line(text: str, width: int) -> List[str]:
    """Wrap one logical line to ``width`` columns -- NEVER ellipsize; split into continuation rows instead.

    A line that fits is returned as a single row. A longer line is split at ``width`` boundaries (preferring a
    space break when one exists in the tail window so a word is not severed mid-token where avoidable), with each
    continuation row prefixed by ``WRAP_CONTINUATION`` so the block reads as one unit. ``width <= 0`` -> [''].
    """
    if width <= 0:
        return ['']
    if len(text) <= width:
        return [text]
    rows: List[str] = []
    remaining = text
    first = True
    while remaining:
        budget = width if first else max(1, width - len(WRAP_CONTINUATION))
        if len(remaining) <= budget:
            chunk, remaining = remaining, ''
        else:
            # prefer a space break within the budget window (avoid severing a word) -- fall back to a hard cut.
            cut = remaining.rfind(' ', 0, budget + 1)
            if cut <= 0:
                cut = budget
            chunk, remaining = remaining[:cut], remaining[cut:].lstrip(' ')
        rows.append(chunk if first else f'{WRAP_CONTINUATION}{chunk}')
        first = False
        if not remaining:
            break
    return rows


def render_entries(entries: List[Entry], width: int) -> List[VisualRow]:
    """Flatten ENTRIES into wrapped VISUAL ROWS, honoring each entry's collapse state. PURE; never ellipsizes body.

    For each entry (in order, oldest->newest):
      * the SUMMARY becomes a header row carrying the collapsed / expanded marker -- a collapsed entry
        WITH a body appends a faint ``…`` hint (there is hidden content), an expanded one does not.
      * if the entry is EXPANDED, its body logical lines are each WRAPPED (full text, no ellipsis) into rows.
      * a collapsed entry contributes ONLY its summary row.
    The returned list is the render order top->bottom; the caret counts offsets from the LAST (newest) row.
    """
    rows: List[VisualRow] = []
    for idx, entry in enumerate(entries):
        marker = MARKER_EXPANDED if (not entry.collapsed and entry.has_body) else MARKER_COLLAPSED
        hint = SUMMARY_ELLIPSIS if (entry.collapsed and entry.has_body) else ''
        for r in wrap_line(f'{marker} {entry.summary}{hint}', width):
            rows.append(VisualRow(text=r, entry_index=idx, is_header=True))
        if not entry.collapsed:
            for line in entry.body:
                for r in wrap_line(line, width):
                    rows.append(VisualRow(text=r, entry_index=idx, is_header=False))
    return rows


@dataclass
class TraverseCaret:
    """The CONTENT-TRAVERSAL caret -- a wrap-aware line cursor over the visual rows, counted from the NEWEST (bottom).

    ``offset`` is rows-from-the-bottom (0 = the newest/last visual row). ``up`` increases it (toward older),
    ``down`` decreases it (toward newest), both CLAMPED to the live row count. ``row_index(total)`` maps the
    offset to a TOP-DOWN index for the renderer. The caret is re-clamped whenever the row set changes (a
    collapse/expand shrinks/grows the rows) so it never points past the end.
    """
    offset: int = 0

    def clamp(self, total_rows: int) -> None:
        if total_rows <= 0:
            self.offset = 0
            return
        self.offset = max(0, min(self.offset, total_rows - 1))

    def up(self, total_rows: int) -> None:
        self.offset += 1
        self.clamp(total_rows)

    def down(self, total_rows: int) -> None:
        self.offset -= 1
        self.clamp(total_rows)

    def row_index(self, total_rows: int) -> int:
        """The TOP-DOWN row index the caret sits on (offset counted from the bottom). -1 when there are no rows."""
        if total_rows <= 0:
            return -1
        return total_rows - 1 - max(0, min(self.offset, total_rows - 1))
