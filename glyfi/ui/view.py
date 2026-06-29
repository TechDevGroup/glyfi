"""view -- the MVVM VIEW port + a PURE region PAINTER (VM state -> per-region text lines + highlight data).

The View is the DUMB renderer of the MVVM split -- it binds to the ViewModel, reads its presentation state, and
paints regions; it holds NO presentation logic (that is the ViewModel) and NO data (that is the Model). To keep
the View MECHANISM-TESTABLE without a live terminal, the painting is split:

  * ``RegionPainter`` -- a PURE function-object: given the ViewModel + a solved layout (name->Rect), it produces
    a ``Painting`` -- per-region clipped text lines + PURE highlight data (which whole AREAS to highlight, and
    which overlay ROW is selected). NO curses, NO terminal -- just text geometry + highlight intent.

  * ``View`` (ABC) -- the View PORT: ``render(viewmodel)`` paints the current frame. The curses impl binds the
    Painting (and the highlight data) to actual windows; a test impl captures the Painting. Pluggable.

The painter renders each NAMED fenced region from VM/Model state:
  * title       -- the title + the current mode label + the breadcrumb + the exit hint.
  * state       -- the STATE strip: config slots spread across the width.
  * *_rule      -- full-width RULE_CHAR fences (header_rule / input_rule / status_rule).
  * content     -- the BOTTOM-ANCHORED content view (newest at the bottom), OR a PALETTE / CONFIG overlay.
  * status      -- the EPHEMERAL ticker line (its own region above the input fence; blank when the ticker is idle).
  * input       -- the input + HINTS line: ``> {buffer}`` when typing, else a ``> {hint}``.
  * details     -- the details bar: left group left-justified, right group right-justified, spread by space fill.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple
from glyfi.ui.layout import Rect, Size
from glyfi.ui.settings import (
    REGION_TITLE, REGION_STATE, REGION_HEADER_RULE, REGION_CONTENT, REGION_STATUS, REGION_INPUT_RULE,
    REGION_INPUT, REGION_STATUS_RULE, REGION_DETAILS, RULE_CHAR, INPUT_PROMPT, SLOT_SEP, DETAILS_GROUP_SEP,
    INPUT_HINT_VARIANTS,
)
from glyfi.plugins import palette as palette_mod
from glyfi.ui import theme
from glyfi.ui.viewmodel import (
    AppViewModel, UI_NORMAL, UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE,
)
from glyfi.ui.prompt_state import FIELD_LABELS
ELLIPSIS = '...'


@dataclass(frozen=True)
class Painting:
    """A painted frame -- per-region clipped text lines + PURE highlight + SEMANTIC ROLE data (a11y palette).

    Pure data (no terminal dependency -- a test asserts it directly):
      * ``regions``           -- region name -> its clipped text lines.
      * ``highlight_regions`` -- the set of regions to fill with the SELECT background (edit preview).
      * ``highlight_cells``   -- region -> a ``(row, start_col, end_col)`` SPAN to highlight WITHIN that row's line
                                 (the single FIELD the config caret sits on -- the state-strip slot piece AND the
                                 config-editor row's value -- just that field, never the whole region/row/line).
      * ``highlight_rows``    -- region -> the selected/focused row index (also marked with the focus marker in text).
      * ``region_roles``      -- region -> a SEMANTIC theme ROLE for its whole text (dim hint / accent trim /
                                 destructive confirm). The curses View maps the role to a color/attr.
      * ``breadcrumb``        -- the active overlay's menu path (rendered into the title/overlay; '' in NORMAL).
    """
    regions: Dict[str, List[str]] = field(default_factory=dict)
    highlight_regions: FrozenSet[str] = frozenset()
    highlight_cells: Dict[str, Tuple[int, int, int]] = field(default_factory=dict)
    highlight_rows: Dict[str, int] = field(default_factory=dict)
    region_roles: Dict[str, str] = field(default_factory=dict)
    # ADDITIVE: a widget may ACCENT-colour specific cell spans within its content (e.g. a metric value) WITHOUT
    # selecting them -- region -> a list of (row, start_col, end_col) spans rendered in the ACCENT-2 role. Default
    # empty so every existing region/widget is unchanged.
    accent_cells: Dict[str, List[Tuple[int, int, int]]] = field(default_factory=dict)
    breadcrumb: str = ''

    def lines(self, region: str) -> List[str]:
        return self.regions.get(region, [])

    def role(self, region: str) -> str:
        """The semantic theme role for a region's text (default NORMAL) -- the curses View maps it to an attr."""
        return self.region_roles.get(region, theme.ROLE_NORMAL)


FRAME_BLANK_CELL = ' '          # the fill character for gaps and right-padding (one screen cell)


def compose_frame(painting: 'Painting', layout: Dict[str, Rect], size: Size) -> List[str]:
    """Compose the EXACT full-screen grid -- every region's lines placed at its ``Rect`` (x, y), gaps blank-filled.

    The pure CORE composer of a full frame: builds a ``size.h`` x ``size.w`` grid of blank cells, then stamps
    each region's painted lines into the rows starting at its rect origin (clipping to the rect's width/height so
    a region never bleeds past its placement). Every row is padded to ``size.w`` so the result is a clean
    rectangle -- exactly what a terminal would show. Regions absent from the layout (or the painting) leave their
    area blank. Deterministic; no terminal dependency -- the same painting/layout/size always yields the same rows.
    """
    grid: List[List[str]] = [[FRAME_BLANK_CELL] * size.w for _ in range(size.h)]
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


def _clip_line(text: str, width: int) -> str:
    """Fit one line to ``width`` columns -- truncate with an ellipsis when too long (never overflow a region)."""
    if width <= 0:
        return ''
    if len(text) <= width:
        return text
    if width <= len(ELLIPSIS):
        return text[:width]
    return text[:width - len(ELLIPSIS)] + ELLIPSIS


def _clip_lines(lines: List[str], rect: Rect) -> List[str]:
    """Fit a block of lines to a rect -- clip each line to the width, keep at most ``rect.h`` lines."""
    clipped = [_clip_line(ln, rect.w) for ln in lines]
    return clipped[:max(0, rect.h)]


def _rule(width: int) -> str:
    """A full-width fence rule -- RULE_CHAR repeated to ``width`` columns."""
    return RULE_CHAR * max(0, width)


def _fit_hint(width: int) -> str:
    """Pick the WIDEST NAMED hint variant that FITS ``width`` (after the prompt prefix) -- never ellipsis off-screen."""
    budget = max(0, width - len(INPUT_PROMPT))
    for variant in INPUT_HINT_VARIANTS:          # widest -> narrowest
        if len(variant) <= budget:
            return variant
    return INPUT_HINT_VARIANTS[-1]               # the shortest; the clip trims it if even that overruns


def _mark_focus(lines: List[str], sel_row: Optional[int]) -> List[str]:
    """Prefix the selected row with the FOCUS MARKER and the others with a blank gutter -- 508: not color-only."""
    if sel_row is None:
        return lines
    out: List[str] = []
    for i, ln in enumerate(lines):
        gutter = theme.FOCUS_MARKER if i == sel_row else theme.FOCUS_MARKER_BLANK
        out.append(f'{gutter} {ln}')
    return out


def _spread(items: List[str], width: int) -> str:
    """Spread items across ``width`` -- justify them with even gaps (left-anchored, right item flush-right)."""
    items = [s for s in items if s != '']
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    joined = SLOT_SEP.join(items)
    if len(joined) >= width:
        return joined
    total_text = sum(len(s) for s in items)
    gaps = len(items) - 1
    spare = width - total_text
    base = spare // gaps
    extra = spare % gaps
    out = items[0]
    for i, s in enumerate(items[1:]):
        pad = base + (1 if i < extra else 0)
        out += ' ' * pad + s
    return out


def _left_right(left: str, right: str, width: int) -> str:
    """Left text left-justified, right text right-justified, spread by space fill."""
    if width <= 0:
        return ''
    combined = len(left) + len(right)
    if combined >= width:
        return _clip_line(left + ' ' + right, width)
    return left + ' ' * (width - combined) + right


class RegionPainter:
    """The PURE View painter -- ViewModel state + a solved layout -> a ``Painting`` (lines + highlight data).

    C5 (post_paint hook): a consumer may pass ``post_paint=fn`` to patch the produced ``Painting`` after the
    base paint completes (e.g. multi-line input rendering). ``fn(vm, layout, painting) -> Painting`` runs on the
    result of ``_do_paint``; because ``Painting`` is frozen (G36) the hook must patch via ``dataclasses.replace``.
    OCP default: ``post_paint=None`` -> ``_do_paint``'s result is returned directly, byte-identical to today.
    ``HeadlessView`` constructs ``RegionPainter()`` with no args, so the default path is unchanged.

    C3 (scroll_palette): defaults True -> the palette overlay windows long lists around the selection (a short
    list that fits is byte-identical to truncation, so this is behavior-preserving). Set ``scroll_palette=False``
    to restore the exact pre-windowing truncation behaviour.
    """

    def __init__(self, *,
                 post_paint=None,
                 scroll_palette: bool = True):
        self._post_paint = post_paint
        self._scroll_palette = scroll_palette

    def paint(self, vm: AppViewModel, layout: Dict[str, Rect]) -> Painting:
        """The PUBLIC paint entry point -- run the base paint, then the optional C5 ``post_paint`` hook.

        Every caller (``CursesView._blit`` path, ``HeadlessView.render``) uses this method; the rename of the
        base body to ``_do_paint`` is invisible to them. The hook, when present, returns a (replaced) Painting.
        """
        painting = self._do_paint(vm, layout)
        if self._post_paint is not None:
            painting = self._post_paint(vm, layout, painting)
        return painting

    def _do_paint(self, vm: AppViewModel, layout: Dict[str, Rect]) -> Painting:
        """Produce the full frame -- clipped line-blocks per region + highlight + SEMANTIC ROLE + breadcrumb data."""
        regions: Dict[str, List[str]] = {}
        highlight_rows: Dict[str, int] = {}
        region_roles: Dict[str, str] = {}

        crumb = theme.BREADCRUMB_SEP.join(vm.breadcrumb())   # the active overlay's menu path (a11y wayfinding)

        if REGION_TITLE in layout:
            # ALWAYS-VISIBLE: title + mode label + the breadcrumb + the Esc EXIT HINT (the never-stuck law).
            # RESPONSIVE: the EXIT HINT is preserved as the width shrinks; less-critical decorations (crumb, then
            # mode) drop FIRST so the hint never ellipsizes off-screen (a11y).
            title = self._fit_title(vm, crumb, layout[REGION_TITLE].w)
            regions[REGION_TITLE] = _clip_lines([title], layout[REGION_TITLE])
            if crumb:
                region_roles[REGION_TITLE] = theme.accent_for_depth(vm.menu_depth())
        if REGION_STATE in layout:
            rect = layout[REGION_STATE]
            regions[REGION_STATE] = _clip_lines([_spread(vm.state_slots(), rect.w)], rect)
        for rule_region in (REGION_HEADER_RULE, REGION_INPUT_RULE, REGION_STATUS_RULE):
            if rule_region in layout:
                regions[rule_region] = _clip_lines([_rule(layout[rule_region].w)], layout[rule_region])
        content_value_cell = None                        # a (row, start, end) field span for a config-editor row
        if REGION_CONTENT in layout:
            rect = layout[REGION_CONTENT]
            lines, sel_row = self._content_lines(vm, rect)
            bottom_anchored, sel_row = self._anchor_content(vm, lines, sel_row, rect)
            regions[REGION_CONTENT] = _clip_lines(bottom_anchored, rect)
            content_value_cell = self._config_row_value_cell(vm, regions[REGION_CONTENT], sel_row)
            if sel_row is not None and content_value_cell is None:
                highlight_rows[REGION_CONTENT] = sel_row   # full-row select where there is no single field to mark
            if vm.mode_ui in (UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_TRAVERSE):
                region_roles[REGION_CONTENT] = theme.accent_for_depth(vm.menu_depth())
        if REGION_STATUS in layout:
            status_text, status_role = self._status_line(vm)
            regions[REGION_STATUS] = _clip_lines([status_text], layout[REGION_STATUS])
            region_roles[REGION_STATUS] = status_role
        input_caret_cell = None
        if REGION_INPUT in layout:
            rect = layout[REGION_INPUT]
            text, role = self._input_line(vm, rect.w)
            text, input_caret_cell = self._with_input_caret(vm, text, rect.w)
            regions[REGION_INPUT] = _clip_lines([text], rect)
            region_roles[REGION_INPUT] = role
        if REGION_DETAILS in layout:
            rect = layout[REGION_DETAILS]
            left = DETAILS_GROUP_SEP.join(vm.details_left())
            right = DETAILS_GROUP_SEP.join(vm.details_right())
            regions[REGION_DETAILS] = _clip_lines([_left_right(left, right, rect.w)], rect)

        highlight = frozenset()
        area = vm.highlight_region()
        if area is not None and area in layout:
            highlight = frozenset({area})
        highlight_cells = self._slot_cell_span(vm, regions)
        if content_value_cell is not None:
            highlight_cells[REGION_CONTENT] = content_value_cell
        if input_caret_cell is not None:
            highlight_cells[REGION_INPUT] = input_caret_cell      # the typing CURSOR (a reverse-video block bar)
        accent_cells: Dict[str, List[Tuple[int, int, int]]] = {}
        if vm.mode_ui == UI_WIDGET and REGION_CONTENT in layout:   # let the active widget accent metric spans
            spans = vm.widgets.accents(layout[REGION_CONTENT])
            if spans:
                accent_cells[REGION_CONTENT] = list(spans)
        return Painting(regions=regions, highlight_regions=highlight, highlight_cells=highlight_cells,
                        accent_cells=accent_cells,
                        highlight_rows=highlight_rows, region_roles=region_roles, breadcrumb=crumb)

    def _fit_title(self, vm: AppViewModel, crumb: str, width: int) -> str:
        """Assemble the title strip RESPONSIVELY -- preserve the never-stuck EXIT HINT; drop decorations first.

        Priority order (widest -> narrowest), each variant a PROGRESSIVE drop of the LEAST-critical piece. The
        brand TITLE is the persistent anchor; the EXIT HINT (the way out) is preserved as the width shrinks,
        dropping to a TERSE hint before vanishing -- it never ellipsizes off-screen (a11y):
          1. title  [mode]  › crumb  · <exit hint>
          2. title  [mode]  · <exit hint>           (drop the crumb)
          3. title  · <exit hint>                    (drop the mode decoration)
          4. title  · <short exit hint>              (terse hint -- still names the way out)
          5. title                                   (degenerate width -- the brand anchor holds the row)
        """
        hint = vm.exit_hint()
        short = vm.exit_hint_short()
        base = vm.title
        mode = f'[mode:{vm.mode}]'
        crumb_piece = f'{theme.BREADCRUMB_SEP.strip()} {crumb}' if crumb else ''
        variants = [
            '  '.join(p for p in (base, mode, crumb_piece) if p) + f'  · {hint}',
            '  '.join(p for p in (base, mode) if p) + f'  · {hint}',
            f'{base}  · {hint}',
            f'{base}  · {short}',
            base,
        ]
        for variant in variants:
            if len(variant) <= width:
                return variant
        return variants[-1]

    def _with_input_caret(self, vm: AppViewModel, text: str, width: int):
        """Place the typing CURSOR at the insertion point -> ``(text_with_caret_room, (row, start, end))``.

        The cursor is a one-cell reverse-video BLOCK bar (reusing the SELECT accent). It sits at the INSERTION
        COLUMN, which is the live ``input_caret`` position within the buffer (mid-line ←/→ editing -- not pinned
        to the end). Shown only while the operator is editing (NORMAL with a buffer, or PALETTE).
        """
        editing = vm.mode_ui == UI_PALETTE or (vm.mode_ui == UI_NORMAL and bool(vm.input_buffer))
        if not editing:
            return text, None
        caret = max(0, min(vm.input_caret, len(vm.input_buffer)))  # clamp to the buffer (defensive)
        caret_col = len(INPUT_PROMPT) + caret                     # insertion point = the caret within the buffer
        if caret_col >= width:
            return text, None                                    # off-screen (over-long input) -> no caret cell
        return text, (0, caret_col, caret_col + 1)

    def _config_row_value_cell(self, vm: AppViewModel, content_lines: List[str], sel_row):
        """The ``(row, start, end)`` span of the config-editor SELECTED slot row's VALUE field (the alias)."""
        from glyfi.ui.config_editor import LEVEL_SLOTS
        if vm.mode_ui != UI_CONFIG:
            return None
        ed = vm.editor
        if ed.level != LEVEL_SLOTS or ed.is_input_row():
            return None
        marker = ' = '                                    # the row format is ``<group>[<pos>] = <alias>``
        row = self._focused_row(content_lines)
        if row is None or marker not in content_lines[row]:
            return None
        line = content_lines[row]
        at = line.find(marker)
        start = at + len(marker)
        end = len(line.rstrip())
        if end <= start:
            return None
        return (row, start, end)

    def _focused_row(self, content_lines: List[str]):
        """The index of the focus-marked row in a config/menu overlay, or None when none is marked."""
        for i, line in enumerate(content_lines):
            if line.startswith(theme.FOCUS_MARKER):
                return i
        return None

    def _slot_cell_span(self, vm: AppViewModel, regions: Dict[str, List[str]]) -> Dict[str, Tuple[int, int]]:
        """The ``(start_col, end_col)`` span of the slot piece the config caret sits on -- a CELL, not the line."""
        slot = vm.highlight_slot()
        if slot is None:
            return {}
        region, pieces, target_idx = self._region_pieces_for_slot(vm, slot)
        if region is None or not regions.get(region):
            return {}
        line = regions[region][0]
        if not (0 <= target_idx < len(pieces)) or not pieces[target_idx]:
            return {}
        # Walk the pieces LEFT-TO-RIGHT in order, consuming each one's span from a running cursor -- so a SHORT
        # value (e.g. an unset ``-``) maps to ITS OWN slot, never to a substring of an EARLIER piece.
        cursor = 0
        for idx, piece in enumerate(pieces):
            if not piece:
                continue
            found = line.find(piece, cursor)
            if found < 0:
                return {}
            if idx == target_idx:
                return {region: (0, found, found + len(piece))}   # the strip is a single row -> row 0
            cursor = found + len(piece)
        return {}

    def _region_pieces_for_slot(self, vm: AppViewModel, slot):
        """Map a ``SlotPos`` to ``(region, ordered_rendered_pieces, index_within_pieces)`` for the cell locator."""
        from glyfi.ui.config_store import SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT
        if slot.group == SLOT_STATE:
            return REGION_STATE, vm.state_slots(), slot.position
        if slot.group == SLOT_DETAILS_LEFT:
            left = vm.details_left()
            return REGION_DETAILS, left + vm.details_right(), slot.position
        if slot.group == SLOT_DETAILS_RIGHT:
            left = vm.details_left()
            return REGION_DETAILS, left + vm.details_right(), len(left) + slot.position
        return None, [], 0

    def _anchor_content(self, vm: AppViewModel, lines, sel_row, rect: Rect):
        """BOTTOM-ANCHOR the NORMAL content: pad the top with blank rows so the newest line sits at the rect bottom."""
        if vm.mode_ui != UI_NORMAL or vm.model.content_buffer:
            return (lines, sel_row)
        pad = vm.content_top_pad()
        if pad <= 0:
            return (lines, sel_row)
        padded = [''] * pad + list(lines)
        shifted = (sel_row + pad) if sel_row is not None else None
        return (padded, shifted)

    def _status_line(self, vm: AppViewModel):
        """The STATUS region text + its semantic ROLE.

        A DESTRUCTIVE confirm pending -> the prompt rendered in the DESTRUCTIVE (red) role (the ONLY red use). A
        SCROLLBACK LOCK with unseen content -> the ``▼ N new below`` indicator in the ACCENT role. Otherwise the
        ephemeral ticker text, in NORMAL role.
        """
        if vm.confirm_pending:
            return (vm.status_line(), theme.ROLE_DESTRUCTIVE)
        new_below = vm.new_below_indicator()
        if new_below is not None:
            return (new_below, theme.ROLE_ACCENT)
        return (vm.status_line(), theme.ROLE_NORMAL)

    def _input_line(self, vm: AppViewModel, width: int):
        """The input + HINTS line text + its semantic ROLE."""
        if vm.mode_ui in (UI_PALETTE,):
            return (f'{INPUT_PROMPT}{vm.input_buffer}', theme.ROLE_NORMAL)
        if vm.input_buffer:
            return (f'{INPUT_PROMPT}{vm.input_buffer}', theme.ROLE_NORMAL)
        return (f'{INPUT_PROMPT}{_fit_hint(width)}', theme.ROLE_DIM)

    def _content_lines(self, vm: AppViewModel, rect: Rect):
        """The content region -- a PALETTE / CONFIG / WIDGET overlay when engaged, else the scroll-windowed content."""
        if vm.mode_ui == UI_PALETTE:
            return self._palette_overlay(vm)
        if vm.mode_ui == UI_CONFIG:
            return self._config_overlay(vm)
        if vm.mode_ui == UI_WIDGET:
            return self._widget_overlay(vm, rect)
        if vm.mode_ui == UI_PROMPT:
            return self._prompt_overlay(vm)
        if vm.mode_ui == UI_TRAVERSE:
            return self._traverse_content(vm, rect)
        # NORMAL: the WRAP-AWARE windowed content (no ellipsis -- long lines wrap to full text).
        rows, _caret = vm.windowed_visual_rows(rect.w)
        return ([r.text for r in rows], None)

    def _traverse_content(self, vm: AppViewModel, rect: Rect):
        """CONTENT-TRAVERSAL: the wrapped windowed rows with the caret row carrying the focus marker."""
        rows, caret_in_window = vm.windowed_visual_rows(rect.w)
        lines = [r.text for r in rows]
        if 0 <= caret_in_window < len(lines):
            lines = _mark_focus(lines, caret_in_window)
        return (lines, None)

    def _prompt_overlay(self, vm: AppViewModel):
        """The prompt-entry FORM -- the two fields (subject + text) with the focus arrow on the active one."""
        lines = ['-- PROMPT (type · ↓ next field · Enter walk ONE turn · ↑ back to input · Esc cancel) --']
        for i, label in enumerate(FIELD_LABELS):
            lines.append(f'{label}: {vm.prompt_form.value(i)}')
        return (_mark_focus(lines, vm.prompt_form.active + 1), None)   # +1 for the header row

    def _widget_overlay(self, vm: AppViewModel, rect: Rect):
        """The active widget's content -- the host's widget owns the content region while UI_WIDGET is up."""
        lines = vm.widgets.lines(rect)
        sel = vm.widgets.highlight()
        if sel is not None:
            lines = _mark_focus(lines, sel)
            sel = None                       # the marker is now in the text; no separate row-highlight needed
        return (lines, sel)

    def _palette_overlay(self, vm: AppViewModel):
        """The slash-command list. ARROW-navigable (PRIMARY); type-to-filter narrows it (SECONDARY fast-jump).

        C3 (Overlay List Windowing): when the filtered list is longer than the content rect can show, the list
        is WINDOWED around the selected row (so a selection below the fold stays reachable) and ``↑ N more`` /
        ``↓ N more`` affordance rows mark the hidden head/tail. When the list FITS (or ``scroll_palette`` is
        False) the path is byte-identical to the pre-windowing behaviour -- ``_mark_focus`` over the full list.
        """
        rows = vm.palette.filtered(palette_mod.all_commands())
        layout_rect = vm.last_layout.get(REGION_CONTENT)
        col = max(0, (layout_rect.w if layout_rect else 0) - 2)   # leave room for the 2-col focus gutter
        lines = []
        for cmd in rows:
            name = f'/{cmd.name}'
            lines.append(_left_right(name, cmd.description, col))
        if not lines:
            return ([f'(no command matches {vm.palette.filter_term!r})'], None)
        n = len(lines)
        selected = vm.palette.selected
        height = layout_rect.h if layout_rect else 0
        # Short list (or windowing disabled): unchanged behaviour -- mark focus over the full list. height<=0
        # (no solved layout yet) also takes this path so we never window against an unknown rect.
        if not self._scroll_palette or height <= 0 or n <= height:
            return (_mark_focus(lines, selected), None)
        # Long list: window around the selection, reserving 1 row per needed scroll indicator.
        f = max(0, min(selected, n - 1))
        # Tentative pass: assume BOTH indicators are needed to size ``avail``.
        avail = max(1, height - 2)
        start = max(0, min(f - avail // 2, n - avail))
        ind_above = start > 0
        ind_below = (start + avail) < n
        # Second pass: recompute with the EXACT indicator count (each indicator costs 1 row).
        num_ind = (1 if ind_above else 0) + (1 if ind_below else 0)
        avail = max(1, height - num_ind)
        start = max(0, min(f - avail // 2, n - avail))
        ind_above = start > 0
        ind_below = (start + avail) < n
        visible = lines[start:start + avail]
        focus_in_window = f - start
        result = list(_mark_focus(visible, focus_in_window))
        # Indicator rows use a 2-space indent matching the FOCUS_MARKER_BLANK + ' ' gutter of non-focused rows.
        if ind_above:
            result = [f'  ↑ {start} more'] + result
        if ind_below:
            result = result + [f'  ↓ {n - (start + avail)} more']
        return (result, None)

    def _config_overlay(self, vm: AppViewModel):
        """The config editor -- SLOTS (slot positions + the INPUTS knobs), or the ALIASES / INPUTS sublevel."""
        from glyfi.ui.config_editor import LEVEL_SLOTS, LEVEL_ALIASES, LEVEL_INPUTS, INPUT_KNOBS
        ed = vm.editor
        if ed.level == LEVEL_SLOTS:
            lines = ['-- CONFIG (↑↓ move · Enter edit · Esc/← back) --']
            for sp in ed.catalogue:
                lines.append(f'{sp.group}[{sp.position}] = {sp.alias}')
            lines.append('-- INPUTS --')
            for knob in INPUT_KNOBS:
                lines.append(f'{knob.label}: {ed.knob_value(knob)}')
            sel = self._config_slots_row(ed)
            return (_mark_focus(lines, sel), None)
        if ed.level == LEVEL_INPUTS:
            knob = ed.editing_knob
            lines = [f'-- INPUTS: {knob.label} (↑ increase · ↓ decrease · Enter save · Esc/← cancel) --',
                     f'{knob.label} = {ed.knob_value(knob)}   [range {knob.floor}..{knob.ceil}, step {knob.step}]']
            return (_mark_focus(lines, 1), None)
        # LEVEL_ALIASES
        target = ed.editing
        lines = [f'-- CONFIG: bind alias for {target.group}[{target.position}] (Enter bind · Esc/← cancel) --']
        for alias, label in ed.aliases():
            lines.append(f'{alias:<12} {label}')
        return (_mark_focus(lines, ed.alias_index + 1), None)

    def _config_slots_row(self, ed) -> int:
        """Map the SLOTS combined cursor (slot positions then INPUTS knobs) to its TEXT row, skipping 2 headers."""
        n_slots = len(ed.catalogue)
        if ed.slot_index < n_slots:
            return ed.slot_index + 1                 # +1 for the top header
        return ed.slot_index + 2                      # +1 top header, +1 the '-- INPUTS --' header


class View(ABC):
    """The View PORT -- bind to a ViewModel and render the current frame. Curses / headless impls plug in."""

    @abstractmethod
    def render(self, viewmodel: AppViewModel) -> None:
        """Paint the current frame from the ViewModel's presentation state. Fail loud on a render fault."""
        raise NotImplementedError('View.render -- a concrete View (curses / headless) must implement this')


class HeadlessView(View):
    """A terminal-FREE View -- it implements the SAME View port as ``CursesView`` but captures the Painting.

    It solves the layout against a fixed synthetic ``Size`` (no live terminal) and paints with the pure
    ``RegionPainter``, keeping the latest ``Painting`` + ``layout`` for inspection. This is the View the headless
    ``AppDriver`` reads -- the SAME pure painter the curses View uses, so what the driver asserts is what the
    terminal would show. stdlib-only, no curses.
    """

    def __init__(self, size: Rect = None, painter: 'RegionPainter' = None, w: int = 80, h: int = 24):
        from glyfi.ui.layout import Size
        self._size = Size(w=w, h=h)
        self._painter = painter or RegionPainter()
        self.painting: Painting = Painting()
        self.layout: Dict[str, Rect] = {}

    @property
    def size(self):
        """The synthetic ``Size`` the headless View solves against (the public read of the backing ``_size``)."""
        return self._size

    def resize(self, w: int, h: int) -> None:
        """Set the synthetic terminal size the headless View solves against (a driver's resize action)."""
        from glyfi.ui.layout import Size
        self._size = Size(w=w, h=h)

    def render(self, viewmodel: AppViewModel) -> None:
        """Solve the layout for the synthetic size + paint with the pure painter; capture the Painting + layout."""
        self.layout = viewmodel.resize(self._size)
        self.painting = self._painter.paint(viewmodel, self.layout)
