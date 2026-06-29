"""list_window -- pure list-windowing helper for scrollable overlay/palette panes.

C3 (Overlay List Windowing): ``window_around(lines, focus, height)`` keeps the focused
row always visible in a height-row slice, scrolling the window as focus moves past either
edge -- the standard "keep cursor in view" behaviour. The palette overlay (and any widget
with a long list) uses this so a selection below the fold is never unreachable.

OCP default: when ``height >= len(lines)`` the full list is returned unchanged -- a short
list that already fits is byte-identical to no windowing, so wiring this into the palette
overlay changes nothing for consumers with few commands.

Pure / testable -- no curses, no network, no side-effects. Ported verbatim from the
downstream consumer's proven ``scroll_window.window_around`` (acraflow/glyfi_client).
"""
from __future__ import annotations
from typing import List, Optional, Tuple


def window_around(
    lines: List[str],
    focus: Optional[int],
    height: int,
) -> Tuple[List[str], Optional[int]]:
    """Return a height-row slice of ``lines`` that keeps ``focus`` visible.

    Args:
        lines:  The full list of lines to window.
        focus:  The index in ``lines`` that must remain visible (the cursor row).
                None means "no cursor" -- returns the top slice of length height.
        height: Maximum number of rows in the visible window.

    Returns:
        ``(visible_lines, focus_in_window)``:
          - visible_lines:    The slice of ``lines`` that fits in ``height`` rows.
          - focus_in_window:  The index of ``focus`` within visible_lines, or
                              None when focus is None or lines is empty.

    Edge cases handled:
        - height <= 0             -> ([], None)
        - height >= len(lines)    -> (lines, focus) -- all fit, no scrolling (OCP default)
        - Empty lines             -> ([], None)
        - focus=None              -> (lines[:height], None) -- top slice
        - focus out of [0, n-1]   -> clamped to valid range before windowing
    """
    if height <= 0 or not lines:
        return ([], None)
    n = len(lines)
    if height >= n:
        # Everything fits -- no windowing needed (identical to current behaviour).
        f = max(0, min(focus, n - 1)) if focus is not None else None
        return (list(lines), f)
    if focus is None:
        return (lines[:height], None)
    # Clamp focus to a valid index.
    f = max(0, min(focus, n - 1))
    # Centre the window on `f`; clamp the start to [0, n-height].
    start = f - height // 2
    start = max(0, min(start, n - height))
    visible = lines[start:start + height]
    return (visible, f - start)
