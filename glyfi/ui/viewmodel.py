"""viewmodel -- the MVVM VIEWMODEL: presentation state + APP COMMANDS, EVENT-DRIVEN + headless-DRIVABLE.

The ViewModel is the BRAIN of the MVVM split -- it holds presentation state and the commands that mutate it,
and it is the ONLY place that touches the stepper. It imports the client stepper + the client protocol
vocabulary + the client Model/layout/fields/palette/config/events/clock/ticker/history.

It is EVENT-DRIVEN: every STATE TRANSITION emits a typed event onto a shared ``EventBus``. The curses View and a
headless driver BOTH subscribe to the SAME bus and read the SAME presentation state -- so the app is fully
drivable without curses. It is also CLOCK-injected: the ephemeral status ticker's TTL reads an injectable
``Clock`` (virtual in tests, monotonic at runtime) -- never wall-clock in logic.

Presentation state held here (VIEW-state, not data):
  * ``mode``          -- the plain mode label the next turn uses; cycled by a command over ``modes``.
  * ``mode_ui``       -- the MODAL ui state: NORMAL / PALETTE / CONFIG / WIDGET / PROMPT / TRAVERSE.
  * ``selected``      -- the transcript index the operator is navigating (review highlight).
  * ``ticker``        -- the EPHEMERAL status ticker (TTL'd pushed message + a Tab-cycled provider ring).
  * ``last_status``   -- the last pushed status text (the ticker's 'status' ring provider reads it).
  * ``scroll_offset`` -- the top line of the windowed content view (content is BOTTOM-ANCHORED; offset 0 = stuck
                         to the bottom / newest; a positive offset scrolls UP into older history via PgUp/PgDn).
  * ``input_buffer``  -- the input line buffer (slash command in PALETTE; free text in NORMAL).
  * ``history``       -- the in-memory input history (Up/Down recall).
  * ``palette``       -- the PURE palette cursor (engaged in PALETTE mode).
  * ``editor``        -- the PURE config-editor cursor (engaged in CONFIG mode).
  * ``last_layout``   -- the most recent solved layout (name->Rect), recomputed by ``resize``.
  * ``should_quit``   -- set by the quit command; the curses loop reads it to break.

HARD RULE (the operator's law): ``step`` runs EXACTLY ONE turn and returns -- there is no loop, batch, or
replay anywhere in the ViewModel. The View calls ``step`` once per operator action, then waits.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from glyfi.ui.layout import Size, Rect, solve_layout, Region
from glyfi.ui.model import AppModel, TurnRecord, SessionState
from glyfi.ui import fields
from glyfi.plugins import palette as palette_mod
from glyfi.ui import config_store
from glyfi.ui import ticker as ticker_mod
from glyfi.plugins.palette import PaletteState
from glyfi.ui.prompt_state import PromptState, FIELD_LABELS, FIELD_SUBJECT
from glyfi.ui import config_editor as config_editor_mod
from glyfi.ui.config_editor import EditorState, build_slot_catalogue
from glyfi.ui.config_store import SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT
from glyfi.ui.settings import REGION_CONTENT
from glyfi.ui.clock import Clock, MonotonicClock
from glyfi.ui.ticker import Ticker
from glyfi.ui.history import InputHistory, DIR_OLDER, DIR_NEWER
from glyfi.ui.events import (
    EventBus, CommandInvoked, ModeChanged, TurnRecorded, StatusPushed, TickerCycled,
    MenuMoved, SlotBound, InputSubmitted, HistoryNavigated, Resized,
)
from glyfi.widgets.host import WidgetHost
from glyfi.ui.content_view import Entry, VisualRow, render_entries, TraverseCaret, TRAVERSE_GUTTER
from glyfi.plugins.commands import CommandContext, CommandPipeline
from glyfi.stepper import Stepper

# ---- NAMED modal ui states (drive the View's key dispatch) ------------------------------------------------
UI_NORMAL = 'NORMAL'
UI_PALETTE = 'PALETTE'
UI_CONFIG = 'CONFIG'
UI_WIDGET = 'WIDGET'            # a pluggable widget owns the content region
UI_PROMPT = 'PROMPT'           # the prompt-entry form (subject + text) -- a proper modal, not a blocking prompt
UI_TRAVERSE = 'TRAVERSE'       # the CONTENT-TRAVERSAL caret over wrapped content rows (distinct from scrolling)
# the modal states in which a MENU/overlay is "up" (ticker TTL suspends; accent trim + breadcrumb show).
UI_MENU_MODES = (UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE)

# ---- NAMED scroll tunables (no magic literals) ------------------------------------------------------------
HALF_PAGE_DIVISOR = 2           # Ctrl-U / Ctrl-D move half a page
MIN_SCROLL_STEP = 1             # a scroll always moves at least one row (a 0/negative config can't freeze scrolling)

# ---- NAMED menu names (emitted on MenuMoved) --------------------------------------------------------------
MENU_PALETTE = 'palette'
MENU_CONFIG = 'config'
MENU_WIDGET = 'widget'
MENU_PROMPT = 'prompt'
MENU_TRAVERSE = 'traverse'

# ---- NAMED scrollback-lock indicator (shown when locked above the live bottom; ``N`` = unseen lines below) --
NEW_BELOW_FMT = '▼ {n} new below'      # the View renders this when auto-follow is OFF and new content arrived

# ---- NAMED destructive-confirm (a11y: a single Esc/quit never destroys; an explicit confirm step is required) -
CONFIRM_QUIT_PROMPT = 'quit? press q again to confirm · any other key cancels'

# ---- NAMED initial status -----------------------------------------------------------------------------------
INITIAL_STATUS = 'ready -- s to prompt, / for the command palette'

# ---- NAMED default mode-label list (seeded from Config.modes; the core never interprets the labels) --------
DEFAULT_MODES = ('chat',)


@dataclass
class AppViewModel:
    """The MVVM ViewModel -- presentation state + commands, EVENT-DRIVEN, driving the stepper ONE turn at a time.

    Construct over a ``Stepper`` (the transport) and an ``AppModel`` (the data). It emits every transition onto
    ``bus`` and reads ``clock`` for the ticker TTL -- both injectable (a headless driver supplies a recording bus
    + a virtual clock; ``app`` supplies a live bus + a monotonic clock). ``request_prompt`` / ``request_quit``
    are SEAMS the View binds.
    """
    stepper: Stepper
    model: AppModel
    url: str = ''
    mode: str = ''                 # current plain label (seeded from modes[0])
    mode_ui: str = UI_NORMAL
    selected: int = 0
    last_status: str = INITIAL_STATUS
    scroll_offset: int = 0
    # AUTO-FOLLOW: True while the viewport is stuck to the live bottom (new content renders live). Scrolling UP
    # off the bottom turns it OFF (scrollback LOCK -- new content does NOT yank the view); scrolling back to the
    # bottom turns it ON again. ``unseen_below`` counts lines that arrived while locked (the ``N new below`` cue).
    auto_follow: bool = True
    unseen_below: int = 0
    input_buffer: str = ''
    palette: PaletteState = field(default_factory=PaletteState)
    editor: EditorState = field(default_factory=EditorState)
    prompt_form: PromptState = field(default_factory=PromptState)
    # CONTENT-TRAVERSAL: the wrap-aware line caret + per-entry collapse OVERRIDES (entry index -> collapsed bool).
    traverse_caret: TraverseCaret = field(default_factory=TraverseCaret)
    _collapse_overrides: Dict[int, bool] = field(default_factory=dict)
    last_layout: Dict[str, Rect] = field(default_factory=dict)
    should_quit: bool = False
    # the pluggable WIDGET host -- wired in __post_init__ to this VM's status/bus/close path.
    widgets: Optional[WidgetHost] = None
    # the args->handler COMMAND PIPELINE (the slash-command plugin seam) -- wired in __post_init__.
    pipeline: Optional[CommandPipeline] = None
    # destructive-confirm latch (a11y): set by the FIRST quit; a SECOND quit confirms, any other action cancels.
    _confirm_quit: bool = False
    # event-driven + timing seams (injectable; defaults are the runtime impls)
    bus: EventBus = field(default_factory=EventBus)
    clock: Clock = field(default_factory=MonotonicClock)
    ticker: Ticker = field(default_factory=Ticker)
    history: InputHistory = field(default_factory=InputHistory)
    # SEAM the curses View / headless tests inject (prompt-for-one-turn one-shot collect) -- NAMED, not built here.
    prompt_seam: Optional[Callable[[], Optional[tuple]]] = None
    # the configurable mode-label list (seeded from Config.modes); ``cycle_mode`` walks it.
    modes: Tuple[str, ...] = DEFAULT_MODES

    def __post_init__(self):
        # seed the current mode label from the configured list (the core never interprets the labels).
        if not self.modes:
            self.modes = DEFAULT_MODES
        if not self.mode:
            self.mode = self.modes[0]
        # the ticker TTL is config-driven (NAMED, never a literal) -- wire it from the loaded UserConfig.
        self.ticker.ttl_seconds = self.model.config.status_ttl_seconds
        # seed the initial status onto the ticker so the first frame shows it.
        self.ticker.push(self.last_status, self.clock)
        # keep the session's mode label in sync with the seeded mode.
        self.model.session.mode = self.mode
        # wire the pluggable WIDGET host to THIS VM's scoped capabilities (status / bus / close). Open/closed:
        # the host opens registered widgets by name; the VM never names a concrete widget class.
        if self.widgets is None:
            self.widgets = WidgetHost(
                push_status=self.push_status,
                emit=self.bus.emit,
                on_close=self.close_widget,
                scroll_to=self.scroll_to_offset,
                current_offset=self.current_scroll_offset,
            )
        # wire the args->handler PIPELINE to resolve registered CommandSpecs by name (the palette spec registry).
        if self.pipeline is None:
            self.pipeline = CommandPipeline(resolve=palette_mod.command_spec,
                                            prefix=palette_mod.PALETTE_PREFIX)

    # ===== identity / title passthrough ====================================================================
    @property
    def session(self) -> SessionState:
        return self.model.session

    @property
    def title(self) -> str:
        return self.model.settings.title

    @property
    def config(self):
        return self.model.config

    # ===== status -- a PUSH onto the ephemeral ticker (no sticky status bar) ================================
    def push_status(self, text: str) -> None:
        """Push a status message onto the EPHEMERAL ticker -- it shows until its TTL elapses, then auto-clears."""
        self.last_status = str(text)
        self.ticker.push(self.last_status, self.clock)
        self.bus.emit(StatusPushed(text=self.last_status, at=self.clock.now()))

    def status_line(self) -> str:
        """What the STATUS region shows RIGHT NOW -- the live pushed message (until TTL) or the active ring item."""
        return self.ticker.current(self, self.clock)

    def cycle_ticker(self) -> None:
        """Tab -- advance the ephemeral ticker ring to its next provider and emit a TickerCycled event."""
        provider = self.ticker.cycle()
        self.bus.emit(TickerCycled(provider=provider))

    def input_hint(self) -> str:
        """The HINT shown on the input line when the buffer is empty (NOT status -- status has its own line)."""
        return ticker_mod.INPUT_HINT

    def sync_session_from_stepper(self) -> None:
        """Pull the stepper's visible state into the Model's SessionState (post-step refresh)."""
        s = self.model.session
        s.seq = self.stepper.seq
        s.mode = self.mode

    # ===== THE WALK -- exactly one turn, never a loop ======================================================
    def step(self, user_text: str, subject: str) -> TurnRecord:
        """Walk exactly ONE turn at the current ``mode``, record the display result, STOP. Never loops."""
        turn = self.stepper.step(user_text, subject, mode=self.mode)
        if turn.ok:
            resp = turn.response
            record = TurnRecord(index=turn.index, mode=turn.request.mode, subject=subject, user_text=user_text,
                                ok=True, staged_content=resp.content, response_seq=resp.seq, error=None)
            self.push_status(f'turn #{turn.index} staged (seq {resp.seq}) -- STOP, waiting for the next turn')
        else:
            record = TurnRecord(index=turn.index, mode=turn.request.mode, subject=subject, user_text=user_text,
                                ok=False, staged_content=None, response_seq=None, error=turn.error)
            self.push_status(f'turn #{turn.index} FAILED (fail-loud, seq NOT advanced): {turn.error}')
        before = len(self.content_lines())   # measure unseen-content delta for the scrollback-lock indicator
        self.model.record_turn(record)
        self.sync_session_from_stepper()
        self.selected = record.index
        self.session.last_subject = subject
        self.model.clear_content()       # a new turn returns the content view to the transcript
        # a new turn changes the entry set's SHAPE (transcript-indexed) -- drop the collapse overrides + reset the
        # caret so the operator's per-entry choices don't bleed onto the renumbered entries (keyed by transcript idx).
        self._collapse_overrides = {}
        self.traverse_caret = TraverseCaret(offset=0)
        # SCROLLBACK LOCK vs AUTO-FOLLOW: only YANK to the live bottom when we were already following it.
        if self.auto_follow:
            self.scroll_to_bottom()      # following: stick to the freshest turn (live)
        else:
            self.unseen_below += max(0, len(self.content_lines()) - before)
        self.bus.emit(TurnRecorded(index=record.index, ok=record.ok))
        return record

    def request_prompt(self) -> None:
        """Palette/key SEAM -- ENTER the prompt-entry MODAL (subject + text), then walk one turn on submit.

        A wired ``prompt_seam`` (headless tests / a legacy seam) SHORT-CIRCUITS to the one-shot collect-and-walk
        path, preserving the one-turn law for those callers.
        """
        self.bus.emit(CommandInvoked(name='request_prompt'))
        if self.prompt_seam is not None:
            entry = self.prompt_seam()
            if not entry:
                self.push_status('prompt cancelled')
                return
            subject, user_text = entry
            if not str(subject).strip():
                self.push_status('prompt cancelled (no subject)')
                return
            self.step(user_text, str(subject).strip())
            return
        self.open_prompt()

    # ===== PROMPT mode -- the prompt-entry form modal (subject + text), navigated like the palette ==========
    def open_prompt(self) -> None:
        """Open the prompt-entry MODAL -- a fresh 2-field form (subject + text); Up on the first field returns to NORMAL."""
        self.cancel_confirm()
        self.prompt_form = PromptState()
        self.mode_ui = UI_PROMPT
        self.input_buffer = ''
        self.push_status('prompt -- type the subject, ↓ to text, Enter to walk ONE turn, ↑ back to input, Esc cancel')
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))
        self.bus.emit(MenuMoved(menu=MENU_PROMPT, index=self.prompt_form.active))

    def prompt_type(self, ch: str) -> None:
        """Type one char into the ACTIVE prompt field."""
        self.prompt_form.type(ch)

    def prompt_backspace(self) -> None:
        """Backspace the active prompt field; an empty-field backspace CANCELS (symmetric with the palette)."""
        if self.prompt_form.backspace():     # already empty -> the cancel gesture
            self.close_prompt()

    def prompt_up(self) -> None:
        """Up -- focus the previous field; Up on the FIRST field RETURNS to the input box (exits prompt -> NORMAL)."""
        if self.prompt_form.move_up():       # would leave the form upward
            self.close_prompt()
            return
        self.bus.emit(MenuMoved(menu=MENU_PROMPT, index=self.prompt_form.active))

    def prompt_down(self) -> None:
        """Down -- focus the next field (clamped at the last)."""
        self.prompt_form.move_down()
        self.bus.emit(MenuMoved(menu=MENU_PROMPT, index=self.prompt_form.active))

    def prompt_submit(self) -> None:
        """Enter -- walk EXACTLY ONE turn from the form (subject + text), then return to NORMAL. Never loops.

        Fail loud (a11y-soft): a blank subject does NOT walk -- it stays in the form with a status (the subject is
        required). With a non-blank subject it walks one turn (text MAY be empty) and closes back to NORMAL.
        """
        if not self.prompt_form.ready:
            self.push_status('prompt needs a subject (type it, then Enter)')
            return
        subject = self.prompt_form.subject.strip()
        user_text = self.prompt_form.text
        self.mode_ui = UI_NORMAL
        self.input_buffer = ''
        self.ticker.resume(self.clock)
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))
        self.step(user_text, subject)

    def close_prompt(self) -> None:
        """Cancel the prompt modal -- return to NORMAL (Esc / empty-backspace / Up-off-the-top all land here)."""
        if self.mode_ui == UI_PROMPT:
            self._return_to_normal()
            self.push_status('prompt cancelled')

    def request_quit(self) -> None:
        """Palette/key SEAM -- DESTRUCTIVE; requires an explicit CONFIRM (a11y: no quit on a single key).

        The FIRST quit ARMS the confirm latch + shows a destructive-styled confirm prompt; it does NOT quit. A
        SECOND ``request_quit`` (q again) confirms and flags the loop to break (the loop reads ``should_quit``).
        ANY other action cancels the latch (``cancel_confirm``). The confirm prompt is rendered with the
        DESTRUCTIVE (red) role -- the only place red is used.
        """
        self.bus.emit(CommandInvoked(name='request_quit'))
        if self._confirm_quit:
            self.should_quit = True
            return
        self._confirm_quit = True
        self.push_status(CONFIRM_QUIT_PROMPT)

    @property
    def confirm_pending(self) -> bool:
        """True while a destructive confirm is armed (the View shows the prompt in the DESTRUCTIVE/red role)."""
        return self._confirm_quit

    def cancel_confirm(self) -> None:
        """Disarm the destructive-confirm latch (any non-confirming action cancels it -- a11y safety)."""
        if self._confirm_quit:
            self._confirm_quit = False
            self.push_status('quit cancelled')

    # ===== input line: history recall + submit ============================================================
    def history_older(self) -> None:
        """Up -- recall an OLDER submitted input into the buffer (shell-style); emit HistoryNavigated."""
        restored = self.history.older()
        if restored is None:
            return
        self.input_buffer = restored
        self.bus.emit(HistoryNavigated(direction=DIR_OLDER, buffer=self.input_buffer))

    def history_newer(self) -> None:
        """Down -- recall a NEWER submitted input (or the live empty edge); emit HistoryNavigated."""
        restored = self.history.newer()
        if restored is None:
            return
        self.input_buffer = restored
        self.bus.emit(HistoryNavigated(direction=DIR_NEWER, buffer=self.input_buffer))

    def input_type(self, ch: str) -> None:
        """Type one char into the NORMAL-mode input buffer (palette has its own typing path)."""
        self.input_buffer += ch
        self.history.reset()

    def input_backspace(self) -> None:
        """Backspace one char off the NORMAL-mode input buffer."""
        if self.input_buffer:
            self.input_buffer = self.input_buffer[:-1]
            self.history.reset()

    def submit_input(self) -> str:
        """Submit the NORMAL-mode input line -- record it in history, clear the buffer, emit InputSubmitted.

        The app does not auto-walk on submit (the walk stays the manual ``prompt`` modal); submit RECORDS the
        line into history and surfaces it as a status, so the input+hints line + history recall are exercised.
        """
        text = self.input_buffer.strip()
        if text:
            self.history.record(text)
            self.push_status(f'input submitted: {text!r}')
        self.input_buffer = ''
        self.history.reset()
        self.bus.emit(InputSubmitted(text=text))
        return text

    # ===== mode label cycle (config-driven labels; the core never interprets them) =========================
    def cycle_mode(self) -> None:
        """Advance the current mode label through the configured ``modes`` list (wraps)."""
        if not self.modes:
            return
        try:
            idx = self.modes.index(self.mode)
        except ValueError:
            idx = -1
        self.mode = self.modes[(idx + 1) % len(self.modes)]
        self.sync_session_from_stepper()
        self.push_status(f'mode -> {self.mode!r} (applies to the next turn)')
        self.bus.emit(ModeChanged(kind='op', value=self.mode))

    # ===== content view: lines + BOTTOM-ANCHORED scroll windowing =========================================
    def content_lines(self) -> List[str]:
        """The lines the content view shows -- the content buffer if set, else the transcript (oldest->newest)."""
        if self.model.content_buffer:
            return list(self.model.content_buffer)
        return self._transcript_lines()

    def _transcript_lines(self) -> List[str]:
        out: List[str] = []
        for rec in self.model.transcript:
            mark = '>' if rec.index == self.selected else ' '
            out.append(f'{mark}#{rec.index} [{rec.mode}] {rec.subject} <- {rec.user_text!r}')
            if rec.ok:
                out.append(f'   ok  seq{rec.response_seq}: {rec.staged_content!r}')
            else:
                out.append(f'   ERR (seq NOT advanced): {rec.error}')
        return out

    def _content_height(self) -> int:
        rect = self.last_layout.get(REGION_CONTENT)
        return rect.h if rect else 0

    # ===== CONTENT ENTRIES + WRAP + content-traversal caret (no ellipsis; collapsible slot-blocks) ============
    def content_entries(self) -> List[Entry]:
        """Segment the content into ENTRY BLOCKS (one per transcript turn; the generic buffer is one entry).

        Each entry's SUMMARY is its header logical line and its BODY the remaining lines (the staged content / the
        error). The per-entry collapse state is the operator's OVERRIDE if set, else the config default. PURE read.
        """
        default_collapsed = bool(self.config.content_collapsed_default)
        entries: List[Entry] = []
        if self.model.content_buffer:
            # the generic content buffer (help / a pushed result) is ONE entry: first line = summary.
            lines = list(self.model.content_buffer)
            head = lines[0] if lines else ''
            body = tuple(lines[1:])
            entries.append(Entry(summary=head, body=body,
                                 collapsed=self._collapse_overrides.get(0, default_collapsed)))
            return entries
        for i, rec in enumerate(self.model.transcript):
            mark = '>' if rec.index == self.selected else ' '
            summary = f'{mark}#{rec.index} [{rec.mode}] {rec.subject} <- {rec.user_text!r}'
            if rec.ok:
                body = (f'   ok  seq{rec.response_seq}: {rec.staged_content!r}',)
            else:
                body = (f'   ERR (seq NOT advanced): {rec.error}',)
            entries.append(Entry(summary=summary, body=body,
                                 collapsed=self._collapse_overrides.get(i, default_collapsed)))
        return entries

    def _effective_content_width(self, width: int) -> int:
        """The wrap width for the content rows -- reserve the focus-marker GUTTER while in CONTENT-TRAVERSAL."""
        if self.mode_ui == UI_TRAVERSE:
            return max(0, width - TRAVERSE_GUTTER)
        return max(0, width)

    def content_visual_rows(self, width: int) -> List[VisualRow]:
        """The content as WRAPPED visual rows (no ellipsis), honoring collapse state -- the full content surface."""
        return render_entries(self.content_entries(), self._effective_content_width(width))

    def windowed_visual_rows(self, width: int) -> Tuple[List[VisualRow], int]:
        """The BOTTOM-ANCHORED window of wrapped rows for the content rect -> (rows, caret_row_within_window).

        Windows the wrapped rows the same way ``windowed_content`` windows logical lines (newest at the bottom,
        ``scroll_offset`` reveals older). In CONTENT-TRAVERSAL mode the caret's row (counted from the newest) is
        mapped into the returned window so the View can mark it with the focus marker; -1 when not in traverse or
        the caret is outside the window.
        """
        rows = self.content_visual_rows(width)
        height = self._content_height()
        if height <= 0:
            return ([], -1)
        offset = max(0, min(self.scroll_offset, max(0, len(rows) - max(1, height))))
        end = len(rows) - offset
        start = max(0, end - height)
        window = rows[start:end]
        caret_in_window = -1
        if self.mode_ui == UI_TRAVERSE and rows:
            caret_top = self.traverse_caret.row_index(len(rows))   # top-down index over the FULL row set
            if start <= caret_top < end:
                caret_in_window = caret_top - start
        return (window, caret_in_window)

    # ---- content-traversal commands (the wrap-aware caret + collapse/expand; NEVER a scroll) ----------------
    def enter_traverse(self) -> None:
        """Enter CONTENT-TRAVERSAL from NORMAL -- a caret over wrapped content rows, STARTING at the newest (bottom)."""
        self.cancel_confirm()
        self.scroll_to_bottom()
        self.traverse_caret = TraverseCaret(offset=0)
        self.mode_ui = UI_TRAVERSE
        self.input_buffer = ''
        self.push_status('traverse -- ↑↓ move caret (from newest) · → expand · ← collapse · Esc back to NORMAL')
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))
        self.bus.emit(MenuMoved(menu=MENU_TRAVERSE, index=self.traverse_caret.offset))

    def exit_traverse(self) -> None:
        """Exit CONTENT-TRAVERSAL back to NORMAL (Esc -- the reserved unwind; never a dead-end)."""
        if self.mode_ui == UI_TRAVERSE:
            self._return_to_normal()
            self.push_status('traverse closed')

    def _traverse_width(self) -> int:
        rect = self.last_layout.get(REGION_CONTENT)
        return rect.w if rect else 0

    def _traverse_rows(self) -> List[VisualRow]:
        return self.content_visual_rows(self._traverse_width())

    def traverse_up(self) -> None:
        """Move the content caret UP one wrapped visual row (toward older); clamps at the top (oldest)."""
        rows = self._traverse_rows()
        self.traverse_caret.up(len(rows))
        self.bus.emit(MenuMoved(menu=MENU_TRAVERSE, index=self.traverse_caret.offset))

    def traverse_down(self) -> None:
        """Move the content caret DOWN one wrapped visual row (toward newest); clamps at the bottom (newest)."""
        rows = self._traverse_rows()
        self.traverse_caret.down(len(rows))
        self.bus.emit(MenuMoved(menu=MENU_TRAVERSE, index=self.traverse_caret.offset))

    def _caret_entry_index(self) -> Optional[int]:
        """The ENTRY the caret currently sits in (its visual row's ``entry_index``), or None when there are no rows."""
        rows = self._traverse_rows()
        if not rows:
            return None
        row = self.traverse_caret.row_index(len(rows))
        if 0 <= row < len(rows):
            return rows[row].entry_index
        return None

    def traverse_expand(self) -> None:
        """Right -- EXPAND the entry the caret sits in (show its full wrapped body). Re-clamps the caret."""
        idx = self._caret_entry_index()
        if idx is None:
            return
        self._collapse_overrides[idx] = False
        self.traverse_caret.clamp(len(self._traverse_rows()))
        self.push_status('expanded entry -- full wrapped block')

    def traverse_collapse(self) -> None:
        """Left -- COLLAPSE the entry the caret sits in (show only its one-line summary header). Re-clamps the caret."""
        idx = self._caret_entry_index()
        if idx is None:
            return
        self._collapse_overrides[idx] = True
        self.traverse_caret.clamp(len(self._traverse_rows()))
        self.push_status('collapsed entry -- summary only')

    # ---- config-driven scroll STEPS (NAMED via UserConfig; never a magic literal at a scroll site) ----------
    def scroll_delta(self) -> int:
        """The line-scroll step (rows a single scroll-up/down moves) -- from the INPUTS config (>= 1, never 0)."""
        return max(MIN_SCROLL_STEP, int(self.config.scroll_delta))

    def page_step(self) -> int:
        """A PgUp/PgDn shift -- one content slot height MINUS the configurable OVERLAP (a kept sliver of context)."""
        overlap = max(0, int(self.config.page_overlap))
        return max(MIN_SCROLL_STEP, self._content_height() - overlap)

    # scroll model: ``scroll_offset`` counts rows UP FROM THE BOTTOM (0 = stuck to newest, max = top/oldest).
    def _set_offset(self, offset: int) -> None:
        self.scroll_offset = max(0, min(self._max_scroll(), offset))
        if self.scroll_offset == 0:
            self.auto_follow = True
            self.unseen_below = 0
        else:
            self.auto_follow = False

    def scroll_up(self) -> None:
        self._set_offset(self.scroll_offset + self.scroll_delta())

    def scroll_down(self) -> None:
        self._set_offset(self.scroll_offset - self.scroll_delta())

    def scroll_page_up(self) -> None:
        self._set_offset(self.scroll_offset + self.page_step())

    def scroll_page_down(self) -> None:
        self._set_offset(self.scroll_offset - self.page_step())

    def scroll_half_up(self) -> None:
        step = max(MIN_SCROLL_STEP, self._content_height() // HALF_PAGE_DIVISOR)
        self._set_offset(self.scroll_offset + step)

    def scroll_half_down(self) -> None:
        step = max(MIN_SCROLL_STEP, self._content_height() // HALF_PAGE_DIVISOR)
        self._set_offset(self.scroll_offset - step)

    def scroll_to_top(self) -> None:
        """Scroll to the OLDEST content (the top) -- the maximum up-from-bottom offset (locks auto-follow off)."""
        self._set_offset(self._max_scroll())

    def scroll_to_bottom(self) -> None:
        """Stick to the NEWEST content (the bottom) -- offset 0, re-enables auto-follow + clears unseen-below."""
        self._set_offset(0)

    # ---- the SLIDE-TO seam (the additive scroll cap reused by widgets/commands) ----------------------------
    def scroll_to_offset(self, offset: int) -> None:
        """SLIDE the content viewport to ``offset`` (up-from-bottom rows) via the engine's clamped setter."""
        self._set_offset(int(offset))

    def current_scroll_offset(self) -> int:
        """The live content scroll offset (up-from-bottom rows; 0 = stuck to the newest/live bottom)."""
        return self.scroll_offset

    def new_below_indicator(self) -> Optional[str]:
        """The ``▼ N new below`` cue when LOCKED above the bottom with unseen content arrived, else None."""
        if self.auto_follow or self.unseen_below <= 0:
            return None
        return NEW_BELOW_FMT.format(n=self.unseen_below)

    def scroll_fraction(self) -> float:
        """How far through the buffer the viewport BOTTOM sits, 0.0 (top/oldest) .. 1.0 (bottom/newest live)."""
        span = self._max_scroll()
        if span <= 0:
            return 1.0
        return 1.0 - (min(self.scroll_offset, span) / span)

    def _rendered_row_count(self) -> int:
        """The number of RENDERED (wrapped) visual rows at the content rect width -- the true scroll/anchor unit."""
        rect = self.last_layout.get(REGION_CONTENT)
        if rect is None:
            return len(self.content_lines())
        return len(self.content_visual_rows(rect.w))

    def _max_scroll(self) -> int:
        return max(0, self._rendered_row_count() - max(1, self._content_height()))

    def windowed_content(self) -> List[str]:
        """Content windowed BOTTOM-ANCHORED: the newest lines sit at the BOTTOM of the rect, older above."""
        lines = self.content_lines()
        height = self._content_height()
        if height <= 0:
            return []
        offset = max(0, min(self.scroll_offset, self._max_scroll()))
        end = len(lines) - offset
        start = max(0, end - height)
        return lines[start:end]

    def content_top_pad(self) -> int:
        """Blank rows to leave at the TOP of the content rect when content is shorter than it (bottom-anchored)."""
        height = self._content_height()
        rect = self.last_layout.get(REGION_CONTENT)
        if rect is None:
            return max(0, height - len(self.windowed_content()))
        rows, _caret = self.windowed_visual_rows(rect.w)
        return max(0, height - len(rows))

    def clear_content(self) -> None:
        """The ``clear`` command -- drop the content buffer and stick back to the bottom (newest)."""
        self.model.clear_content()
        self.scroll_to_bottom()
        self.push_status('content cleared')

    def push_content_lines(self, lines: List[str]) -> None:
        """Push display lines into the content view (a command handler's ``CommandResult.lines`` lands here)."""
        self.model.set_content(list(lines))
        self.scroll_to_top()

    def push_help(self) -> None:
        """The ``help`` command -- push the palette command list into the content view."""
        lines = ['-- COMMANDS --']
        for cmd in palette_mod.all_commands():
            lines.append(f'/{cmd.name:<16} {cmd.description}')
        self.model.set_content(lines)
        self.scroll_to_top()
        self.push_status('help -- the command palette list (Esc / clear to return to the transcript)')

    # ===== STATE strip + DETAILS bar -- resolve config slots through the fields registry ===================
    def state_slots(self) -> List[str]:
        """The rendered STATE-strip slot values (config slots -> fields.resolve). Fail loud on a bad alias."""
        return [fields.resolve(a, self) for a in self.config.slots.get(SLOT_STATE, [])]

    def details_left(self) -> List[str]:
        return [fields.resolve_labeled(a, self) for a in self.config.slots.get(SLOT_DETAILS_LEFT, [])]

    def details_right(self) -> List[str]:
        return [fields.resolve_labeled(a, self) for a in self.config.slots.get(SLOT_DETAILS_RIGHT, [])]

    # ===== PALETTE mode ===================================================================================
    def open_palette(self) -> None:
        self.cancel_confirm()
        self.mode_ui = UI_PALETTE
        self.input_buffer = palette_mod.PALETTE_PREFIX
        self.palette = PaletteState(buffer=self.input_buffer)
        self.push_status('palette -- Up/Down to navigate, Enter to run, type to filter, Esc to cancel')
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))

    def palette_type(self, ch: str) -> None:
        self.input_buffer += ch
        self.palette.buffer = self.input_buffer
        self.palette.clamp(palette_mod.all_commands())

    def palette_backspace(self) -> None:
        if len(self.input_buffer) > len(palette_mod.PALETTE_PREFIX):
            self.input_buffer = self.input_buffer[:-1]
            self.palette.buffer = self.input_buffer
            self.palette.clamp(palette_mod.all_commands())
        else:
            self.close_modal()

    def palette_up(self) -> None:
        self.palette.move_up(palette_mod.all_commands())
        self.bus.emit(MenuMoved(menu=MENU_PALETTE, index=self.palette.selected))

    def palette_down(self) -> None:
        self.palette.move_down(palette_mod.all_commands())
        self.bus.emit(MenuMoved(menu=MENU_PALETTE, index=self.palette.selected))

    def palette_run(self) -> None:
        """Run the selected (or exact-name) palette command, then return to NORMAL (unless the command stays modal).

        A command that carries an ARG SCHEMA (a registered ``CommandSpec``) flows through the args->handler
        PIPELINE over the RAW input buffer; a legacy arg-less command runs its ``action(vm)``.
        """
        raw = self.input_buffer
        first = self._first_token(raw)
        exact = palette_mod.command(first) if first else None
        if exact is not None:
            cmd = exact
        else:
            cmd = self.palette.select(palette_mod.all_commands())
            raw = ''                                   # a filtered/navigated selection carries no typed args
        if cmd is None:
            self.push_status(f'no command matches {self.palette.filter_term!r}')
            return
        self.mode_ui = UI_NORMAL
        self.input_buffer = ''
        self.bus.emit(CommandInvoked(name=cmd.name))
        if palette_mod.command_spec(cmd.name) is not None:
            self.run_command_raw(raw if raw else f'{palette_mod.PALETTE_PREFIX}{cmd.name}')
        else:
            cmd.action(self)

    def _first_token(self, raw: str) -> str:
        """The leading command-name token of a palette buffer (prefix-stripped, first whitespace-delimited word)."""
        body = raw[len(palette_mod.PALETTE_PREFIX):] if raw.startswith(palette_mod.PALETTE_PREFIX) else raw
        body = body.strip()
        return body.split(' ', 1)[0] if body else ''

    # ===== the args->handler COMMAND PIPELINE seam (slash commands carry args) ==============================
    def command_context(self) -> CommandContext:
        """The SCOPED caps a command handler + the pipeline applier touch -- this VM's content/status/widget/emit."""
        return CommandContext(
            push_lines=self.push_content_lines,
            push_status=self.push_status,
            open_widget=self.open_widget,
            emit=self.bus.emit,
            scroll_to=self.scroll_to_offset,
            current_offset=self.current_scroll_offset,
        )

    def run_command_raw(self, raw: str) -> None:
        """Run a raw slash-command string through the args->handler PIPELINE. Fail loud (located) -> a status."""
        from glyfi.plugins.commands import CommandError
        try:
            self.pipeline.run(raw, self.command_context())
        except CommandError as exc:
            self.push_status(f'command error {exc}')

    def run_command_spec(self, name: str) -> None:
        """Run a registered ``CommandSpec`` by NAME with no typed args (the palette selection / display-action path)."""
        self.run_command_raw(f'{palette_mod.PALETTE_PREFIX}{name}')

    # ===== CONFIG editor mode =============================================================================
    def open_config(self) -> None:
        self.cancel_confirm()
        catalogue = build_slot_catalogue(self.config.slots)
        self.editor = EditorState(catalogue=catalogue, config=self.config)
        self.mode_ui = UI_CONFIG
        self.push_status('config -- arrows move (area highlights), Enter to rebind, Esc to exit')
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))

    def config_up(self) -> None:
        self.editor.move_up()
        self.bus.emit(MenuMoved(menu=MENU_CONFIG, index=self.editor.slot_index))

    def config_down(self) -> None:
        self.editor.move_down()
        self.bus.emit(MenuMoved(menu=MENU_CONFIG, index=self.editor.slot_index))

    def config_enter(self) -> None:
        was_inputs = self.editor.level == config_editor_mod.LEVEL_INPUTS
        bind = self.editor.enter()
        if bind is not None:
            self._apply_bind(bind)
        elif was_inputs:
            # an INPUTS knob was committed (its value already nudged on the config in place) -- persist + re-sync.
            self._persist()
            self.ticker.ttl_seconds = self.config.status_ttl_seconds   # the TTL knob takes effect immediately
            self.push_status('inputs saved')

    def config_back(self) -> None:
        if self.editor.at_top_level():
            self.close_modal()
            self.push_status('config closed')
        else:
            self.editor.back()

    def _apply_bind(self, bind) -> None:
        """Apply a chosen alias rebind to the config slot, persist, rebuild the editor catalogue, emit SlotBound."""
        slots = self.config.slots.setdefault(bind.group, [])
        if 0 <= bind.position < len(slots):
            slots[bind.position] = bind.alias
        else:
            slots.append(bind.alias)
        self._persist()
        self.editor.catalogue = build_slot_catalogue(self.config.slots)
        self.editor.config = self.config
        self.push_status(f'bound {bind.alias!r} to {bind.group}[{bind.position}] -- saved')
        self.bus.emit(SlotBound(group=bind.group, position=bind.position, alias=bind.alias))

    def _persist(self) -> None:
        config_store.save(self.config)

    def highlight_region(self) -> Optional[str]:
        """The screen AREA the View paints while editing (CONFIG mode only).

        Returns the region ONLY for a whole-area highlight -- i.e. an INPUTS knob (the input fence). For a SLOT
        position the highlight is the single field PIECE (``highlight_slot``), not the whole strip/line, so this
        returns None there (the painter highlights just that cell).
        """
        if self.mode_ui != UI_CONFIG:
            return None
        if self.editor.is_input_row():
            return self.editor.highlight_region()
        return None

    def highlight_slot(self):
        """The SLOT position the config caret sits on -- ``(group, position)`` -- so the View highlights JUST that field."""
        if self.mode_ui != UI_CONFIG or self.editor.is_input_row():
            return None
        return self.editor.current_slot()

    def close_modal(self) -> None:
        self._return_to_normal()

    # ===== WIDGET mode -- the pluggable seam (host orchestrates; widgets self-contained) ===================
    def open_widget(self, name: str) -> None:
        """Open the registered widget ``name`` -- it takes the CONTENT region; mode -> UI_WIDGET. Open/closed."""
        self.cancel_confirm()
        self.widgets.open(name)          # fail loud on unknown name
        self.mode_ui = UI_WIDGET
        self.input_buffer = ''
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))
        self.bus.emit(MenuMoved(menu=MENU_WIDGET, index=0))

    def widget_key(self, ch: int) -> bool:
        """Give the active widget first refusal on a key (returns True iff IT handled it -- else the host key acts)."""
        return self.widgets.handle_key(ch)

    def close_widget(self) -> None:
        """Close the active widget + return to NORMAL (the widget's ``request_close`` and a host Esc both land here)."""
        self.widgets.close()
        if self.mode_ui == UI_WIDGET:
            self._return_to_normal()

    # ===== ALWAYS-VISIBLE mode + exit hint (no mode is a dead-end) =========================================
    def exit_hint(self) -> str:
        """How to LEAVE the current mode -- shown ALWAYS so no mode is a dead-end (the never-stuck a11y law)."""
        if self.mode_ui == UI_NORMAL:
            return 'Esc: (none) · q quits'
        if self.mode_ui == UI_WIDGET:
            return 'Esc: close widget -> NORMAL'
        if self.mode_ui == UI_TRAVERSE:
            return 'Esc: exit traverse -> NORMAL'
        if self.mode_ui == UI_PALETTE:
            return 'Esc: close palette -> NORMAL'
        if self.mode_ui == UI_CONFIG:
            return 'Esc: back / close config -> NORMAL'
        if self.mode_ui == UI_PROMPT:
            return 'Esc: cancel prompt -> NORMAL'
        return 'Esc: -> NORMAL'

    def exit_hint_short(self) -> str:
        """The TERSE exit hint -- shown when the full hint will not fit (so the way-out info survives narrow widths)."""
        if self.mode_ui == UI_NORMAL:
            return 'q quits'
        return 'Esc -> NORMAL'

    # ===== menu helpers: breadcrumb, accent depth, menu-active (ticker suspension) ==========================
    def menu_active(self) -> bool:
        """True while a menu/submenu/palette/widget is up -- the ticker reads this to SUSPEND its TTL expiry."""
        return self.mode_ui in UI_MENU_MODES

    def menu_depth(self) -> int:
        """The nesting DEPTH of the active overlay (0 = top level) -- the View picks a PROGRESSIVE accent by it."""
        if self.mode_ui == UI_CONFIG and not self.editor.at_top_level():
            return 1
        return 0

    def breadcrumb(self) -> List[str]:
        """The active overlay's menu PATH (for the breadcrumb) -- empty in NORMAL. Back navigates one level."""
        if self.mode_ui == UI_PALETTE:
            return [MENU_PALETTE]
        if self.mode_ui == UI_WIDGET:
            return [MENU_WIDGET, self.widgets.title()]
        if self.mode_ui == UI_CONFIG:
            crumbs = [MENU_CONFIG]
            if not self.editor.at_top_level() and self.editor.editing is not None:
                tgt = self.editor.editing
                crumbs.append(f'bind {tgt.group}[{tgt.position}]')
            return crumbs
        if self.mode_ui == UI_PROMPT:
            return [MENU_PROMPT, FIELD_LABELS[self.prompt_form.active]]
        if self.mode_ui == UI_TRAVERSE:
            return [MENU_TRAVERSE]
        return []

    def _return_to_normal(self) -> None:
        """The single return-to-NORMAL path -- restore the ticker's ephemerality (the menu-up suspension ends)."""
        self.mode_ui = UI_NORMAL
        self.input_buffer = ''
        self.ticker.resume(self.clock)   # the TTL was suspended while the menu was up -- restart it now
        self.bus.emit(ModeChanged(kind='ui', value=self.mode_ui))

    # ===== the LAYOUT PASS -- active regions filtered by passive visibility config =========================
    def active_regions(self) -> List[Region]:
        """The settings regions filtered by the PASSIVE config visibility -- a hidden region drops so FILL reclaims it."""
        return [r for r in self.model.settings.regions if self.config.is_visible(r.name)]

    def resize(self, size: Size) -> Dict[str, Rect]:
        """The LAYOUT PASS -- re-solve the ACTIVE regions for new terminal dims (SIGWINCH). Emits Resized."""
        self.last_layout = solve_layout(size, self.active_regions())
        self.bus.emit(Resized(w=size.w, h=size.h))
        return self.last_layout

    def selected_turn(self) -> Optional[TurnRecord]:
        return self.model.turn_at(self.selected)
