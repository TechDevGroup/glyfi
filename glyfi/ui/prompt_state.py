"""prompt_state -- the PURE prompt-entry cursor: a 2-FIELD form (subject + text) navigated like a menu.

Walking ONE turn needs two operator inputs -- the routing subject and the turn text. This is a proper MODAL
state (UI_PROMPT) instead of a blocking curses prompt, so it lives in the SAME event-driven MVVM + keymap as
the palette/config/widget overlays (Esc/Backspace exit, a focus arrow marks the active field, headless-drivable
and constraint-testable). This module is the PURE cursor over the two fields -- no curses, no ViewModel.

The form is two NAMED fields walked with Up/Down (the focus arrow marks the active one, exactly like the
palette/config list). Typing edits the active field; Up on the FIRST field RETURNS to the input box (exits the
prompt); Down past the last field stays on the last (clamped). ``ready`` is true once the subject is non-blank
-- submitting then walks EXACTLY one turn (the one-turn law: one submit, one turn, never a loop).

stdlib dataclasses only.
"""
from dataclasses import dataclass

# ---- NAMED field indices + labels (no bare ints/strings at a render/dispatch site) -------------------------
FIELD_SUBJECT = 0               # the subject field (walked FIRST -- Up here returns to the input box)
FIELD_TEXT = 1                  # the turn-text field
FIELD_COUNT = 2
FIELD_LABELS = ('subject', 'text')


@dataclass
class PromptState:
    """The PURE prompt-entry cursor -- the two field buffers + which field is active. Mechanism-testable, no curses.

    ``active`` is the focused field index (FIELD_SUBJECT / FIELD_TEXT); the View marks it with the focus arrow.
    ``subject`` and ``text`` are the field buffers typing edits. ``move_up`` returns True when it would leave the
    form upward (the caller exits the prompt -> NORMAL, 'goes back to the input box'); ``move_down`` clamps at
    the last field.
    """
    subject: str = ''
    text: str = ''
    active: int = FIELD_SUBJECT

    def value(self, field: int) -> str:
        return self.subject if field == FIELD_SUBJECT else self.text

    @property
    def active_value(self) -> str:
        return self.value(self.active)

    @property
    def ready(self) -> bool:
        """True once the subject is non-blank -- the minimum to walk a turn (text MAY be empty)."""
        return bool(self.subject.strip())

    def type(self, ch: str) -> None:
        """Append one char to the ACTIVE field's buffer."""
        if self.active == FIELD_SUBJECT:
            self.subject += ch
        else:
            self.text += ch

    def backspace(self) -> bool:
        """Delete one char from the active field. Returns True iff the field was ALREADY empty (nothing to delete).

        The caller uses the empty signal to EXIT the prompt (a backspace on an empty form is the 'cancel' gesture
        -- symmetric with the palette's empty-backspace-closes behavior).
        """
        cur = self.active_value
        if not cur:
            return True
        if self.active == FIELD_SUBJECT:
            self.subject = self.subject[:-1]
        else:
            self.text = self.text[:-1]
        return False

    def move_up(self) -> bool:
        """Up -- focus the previous field. Returns True when ALREADY on the first field (the caller exits to NORMAL).

        'If you go up, it goes back to the input box': Up on FIELD_SUBJECT leaves the form upward -> the caller
        returns to the NORMAL input line.
        """
        if self.active == FIELD_SUBJECT:
            return True
        self.active -= 1
        return False

    def move_down(self) -> None:
        """Down -- focus the next field (clamped at the last; Down past the end stays put)."""
        self.active = min(FIELD_COUNT - 1, self.active + 1)
