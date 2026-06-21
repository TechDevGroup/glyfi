"""keymap -- the SHARED modal KEY DISPATCH: one curses key code -> the matching ViewModel command, by mode_ui.

This is the SINGLE place that maps a key to a ViewModel action -- extracted so BOTH the curses runtime adapter
AND the headless driver dispatch keys THROUGH THE SAME function (SRP: one home for the key->command mapping;
open/closed: a new binding is added here, both consumers inherit it). The curses View becomes a thin adapter
(read a getch, hand it here); the driver feeds synthetic key codes here too -- identical behavior, one source.

Importing ``curses`` is for its KEY CODE CONSTANTS only (``curses.KEY_UP`` etc.) -- that import needs NO TTY
(only ``initscr`` does), so this module is safe to import headless. It calls NOTHING that touches a terminal.

Modal dispatch by ``vm.mode_ui``:
  * NORMAL   -- PgUp/PgDn (+ Ctrl-U/Ctrl-D) scroll content; Up/Down recall input HISTORY; Tab cycles the ticker;
                Enter submits the input line; printable keys type into the input buffer; the NAMED command keys
                (s prompt / m mode / / palette / c traverse / q quit) fire their command; Backspace edits the buffer.
  * PALETTE  -- printable type-to-filter; Up/Down select; Enter runs; Esc / empty-backspace cancel.
  * CONFIG   -- Up/Down move; Enter descends/binds; Esc/Backspace go back a level / exit.
  * WIDGET   -- Esc always closes (reserved); else the widget gets first refusal.
  * PROMPT   -- the prompt-entry form; Up/Down between fields; Enter walks ONE turn; Esc/Backspace cancel.
  * TRAVERSE -- the content caret; Up/Down move; Right/Left expand/collapse; Esc exits.

stdlib curses (constants only). NEVER auto-loops the walk.
"""
import curses

from glyfi.ui.viewmodel import (
    AppViewModel, UI_NORMAL, UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE,
)
from glyfi.ui.settings import CTRL_U, CTRL_D, TAB

# ---- NAMED Esc + Enter + Backspace key sets (no bare ints at a dispatch site) ------------------------------
KEY_ESC = 27
KEYS_ENTER = (curses.KEY_ENTER, ord('\n'), ord('\r'))
KEYS_BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
PRINTABLE_LO = 32
PRINTABLE_HI = 127


def dispatch_key(vm: AppViewModel, ch: int) -> None:
    """Route ONE key code to the matching ViewModel action, modal on ``vm.mode_ui``. The single key->command map."""
    if vm.mode_ui == UI_NORMAL:
        _dispatch_normal(vm, ch)
    elif vm.mode_ui == UI_PALETTE:
        _dispatch_palette(vm, ch)
    elif vm.mode_ui == UI_CONFIG:
        _dispatch_config(vm, ch)
    elif vm.mode_ui == UI_WIDGET:
        _dispatch_widget(vm, ch)
    elif vm.mode_ui == UI_PROMPT:
        _dispatch_prompt(vm, ch)
    elif vm.mode_ui == UI_TRAVERSE:
        _dispatch_traverse(vm, ch)


def _dispatch_normal(vm: AppViewModel, ch: int) -> None:
    # destructive-confirm safety (a11y): while a quit-confirm is armed, ONLY a second 'q' confirms; ANY other key
    # cancels it (a stray key can't destroy the session). Check before the normal dispatch so the cancel wins.
    key_char = chr(ch) if 0 <= ch < 256 else ''
    if vm.confirm_pending and vm.model.settings.command_for(key_char) != 'quit':
        vm.cancel_confirm()
        # fall through -- the cancelling key still does its normal job below.
    # content scroll: PgUp/PgDn (+ Ctrl-U/Ctrl-D half-page) -- moved OFF Up/Down (those are input history now).
    if ch == curses.KEY_PPAGE:
        vm.scroll_page_up(); return
    if ch == curses.KEY_NPAGE:
        vm.scroll_page_down(); return
    if ch == CTRL_U:
        vm.scroll_half_up(); return
    if ch == CTRL_D:
        vm.scroll_half_down(); return
    # input HISTORY recall on Up/Down.
    if ch == curses.KEY_UP:
        vm.history_older(); return
    if ch == curses.KEY_DOWN:
        vm.history_newer(); return
    # mid-line input-caret editing on Left/Right -- ONLY while the input line is the active focus (a non-empty
    # buffer). With an EMPTY buffer these are inert (NORMAL has no content-traversal Left/Right -- that is its own
    # mode), so the input-caret binding can never clobber anything.
    if vm.input_buffer:
        if ch == curses.KEY_LEFT:
            vm.input_caret_left(); return
        if ch == curses.KEY_RIGHT:
            vm.input_caret_right(); return
        if ch == curses.KEY_HOME:
            vm.input_caret_home(); return
        if ch == curses.KEY_END:
            vm.input_caret_end(); return
    # Tab cycles the ephemeral ticker ring.
    if ch == TAB:
        vm.cycle_ticker(); return
    # Enter submits the input line (records history; does NOT auto-walk).
    if ch in KEYS_ENTER:
        vm.submit_input(); return
    if ch in KEYS_BACKSPACE:
        vm.input_backspace(); return
    # the palette key (``/``) ENGAGES the palette ONLY from an EMPTY buffer -- it is the deliberate way INTO
    # command entry. Once the operator is typing free text, ``/`` is just a literal character.
    command = vm.model.settings.command_for(key_char)
    if command == 'palette' and not vm.input_buffer:
        vm.open_palette(); return
    # the single-letter command keys (s prompt / m mode / c traverse / q quit) are COMMAND-ONLY while the input
    # field is EMPTY. Once the operator has started typing free text, those keys type their LETTER into the buffer.
    if not vm.input_buffer and command in ('quit', 'prompt', 'mode_cycle', 'traverse'):
        if command == 'quit':
            vm.request_quit(); return
        if command == 'prompt':
            vm.request_prompt(); return
        if command == 'mode_cycle':
            vm.cycle_mode(); return
        if command == 'traverse':
            vm.enter_traverse(); return
    # otherwise a printable key types into the NORMAL input buffer.
    if PRINTABLE_LO <= ch < PRINTABLE_HI:
        vm.input_type(chr(ch))


def _dispatch_widget(vm: AppViewModel, ch: int) -> None:
    """WIDGET mode -- Esc is a RESERVED HOST KEY that ALWAYS unwinds toward NORMAL; else the widget gets first refusal.

    NEVER-STUCK LAW: Esc is checked HERE, BEFORE the widget's first refusal -- a widget can never CONSUME Esc and
    trap the operator. AFTER the reserved Esc: the widget handles its own keys (returns True). If it does NOT
    claim a key, the HOST acts: Left-arrow / Backspace also close the widget (widget-FIRST, so a text widget can
    still use Backspace to edit). Anything else the widget didn't claim is ignored."""
    if ch == KEY_ESC:                # RESERVED: Esc always unwinds toward NORMAL -- no widget can trap it.
        vm.close_widget()
        return
    if vm.widget_key(ch):
        return
    if ch == curses.KEY_LEFT or ch in KEYS_BACKSPACE:
        vm.close_widget()


def _dispatch_palette(vm: AppViewModel, ch: int) -> None:
    # ARROW navigation is the PRIMARY interaction; type-to-filter is the SECONDARY fast-jump.
    from glyfi.plugins.palette import PALETTE_PREFIX
    if ch == curses.KEY_UP:
        vm.palette_up()
    elif ch == curses.KEY_DOWN:
        vm.palette_down()
    elif ch in KEYS_ENTER:
        vm.palette_run()
    elif ch == curses.KEY_RIGHT:                    # Right-arrow moves the input caret RIGHT (mid-command editing)
        vm.input_caret_right()
    elif ch == curses.KEY_LEFT and vm.input_caret > len(PALETTE_PREFIX):
        # mid-command: Left moves the caret left within the typed body; only at the prefix boundary does it
        # fall through to the breadcrumb's up-a-level (below) -- so Left never clobbers mid-command editing.
        vm.input_caret_left()
    elif ch == KEY_ESC or ch == curses.KEY_LEFT:    # Esc / Left-at-the-start navigate BACK (breadcrumb up-a-level)
        vm.close_modal()
    elif ch in KEYS_BACKSPACE:
        vm.palette_backspace()
    elif PRINTABLE_LO <= ch < PRINTABLE_HI:
        vm.palette_type(chr(ch))


def _dispatch_prompt(vm: AppViewModel, ch: int) -> None:
    """PROMPT mode -- the prompt-entry form. Up/Down move between fields (Up off the top returns to NORMAL); Enter
    walks ONE turn; Esc cancels; Backspace edits (empty-backspace cancels); printable keys type into the active field.

    A stray Esc is handled HERE as a mode key -- it can NEVER land in a field as ``^[``."""
    if ch == curses.KEY_UP:
        vm.prompt_up()
    elif ch == curses.KEY_DOWN:
        vm.prompt_down()
    elif ch in KEYS_ENTER:
        vm.prompt_submit()
    elif ch == KEY_ESC:
        vm.close_prompt()
    elif ch in KEYS_BACKSPACE:
        vm.prompt_backspace()
    elif PRINTABLE_LO <= ch < PRINTABLE_HI:
        vm.prompt_type(chr(ch))


def _dispatch_traverse(vm: AppViewModel, ch: int) -> None:
    """CONTENT-TRAVERSAL mode -- a wrap-aware LINE CARET over the content, distinct from viewport scrolling.

    Up/Down move the caret ONE WRAPPED VISUAL ROW (counting from the NEWEST entry at the bottom, upward); Right
    EXPANDS the entry the caret sits in, Left COLLAPSES it. Esc exits back to NORMAL (a RESERVED unwind -- never a
    dead-end). This is SEPARATE from PgUp/PgDn viewport scrolling."""
    if ch == KEY_ESC:                         # RESERVED: Esc always unwinds toward NORMAL.
        vm.exit_traverse(); return
    if ch == curses.KEY_UP:
        vm.traverse_up(); return
    if ch == curses.KEY_DOWN:
        vm.traverse_down(); return
    if ch == curses.KEY_RIGHT:
        vm.traverse_expand(); return
    if ch == curses.KEY_LEFT:
        vm.traverse_collapse(); return


def _dispatch_config(vm: AppViewModel, ch: int) -> None:
    if ch == curses.KEY_UP:
        vm.config_up()
    elif ch == curses.KEY_DOWN:
        vm.config_down()
    elif ch in KEYS_ENTER:
        vm.config_enter()
    # Esc / Backspace / Left-arrow all navigate BACK one level (breadcrumb up; exit config at the SLOTS level).
    elif ch in (KEY_ESC, curses.KEY_LEFT) + KEYS_BACKSPACE:
        vm.config_back()
