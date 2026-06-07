"""config_editor -- the traversable SLOT editor: a PURE 2-level menu state machine (mechanism-testable, no curses).

Opening ``/config`` enters CONFIG mode. The editor is a multi-level cursor:

  Level SLOTS   -- a flat 1D list of editable slot POSITIONS, one per slot across the placeable areas (the state
                   strip, then the details-left group, then the details-right group), THEN the INPUTS knobs.
                   Arrows move the cursor; as it moves, the editor REPORTS the screen region the current entry
                   lives in (``highlight_region``) so the View can background-highlight that AREA -- a live
                   preview of what you edit. Enter on a SLOT descends to ALIASES (to rebind it); Enter on an
                   INPUTS knob descends to INPUTS (Up/Down nudges the value). Esc/Backspace EXITS config -> NORMAL.

  Level ALIASES -- a 1D list of the available field aliases (with labels, from the fields registry). Arrows move;
                   Enter BINDS the chosen alias to the slot being edited (the caller persists), then returns to
                   level SLOTS. Esc/Backspace returns to SLOTS without a change.

  Level INPUTS  -- adjust an INPUTS knob in place (Up increases, Down decreases, both clamped); Enter commits.

Everything here is a PURE transition over an ``EditorState`` (level + the cursors + the slot catalogue + the
config). It mutates NOTHING on disk and touches NO curses -- the ViewModel applies the chosen bind to the
``UserConfig`` and saves. ``enter`` at level ALIASES returns a ``Bind`` describing (group, position, alias) so
the caller can apply + persist it; every other transition returns ``None`` for the bind.
"""
from dataclasses import dataclass, field
from typing import List, NamedTuple, Optional, Tuple

from glyfi.ui import fields
from glyfi.ui.config_store import (
    SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT,
    KEY_SCROLL_DELTA, KEY_PAGE_OVERLAP,
)
from glyfi.ui.ticker import KEY_STATUS_TTL

# ---- NAMED levels (the menu depths) -----------------------------------------------------------------------
LEVEL_SLOTS = 'slots'           # the top level: walk the editable slot positions THEN the INPUTS knobs
LEVEL_ALIASES = 'aliases'       # the slot-rebind sublevel (pick a field alias for a slot)
LEVEL_INPUTS = 'inputs'         # the INPUTS-knob adjust sublevel (Up/Down nudges the value, Enter commits)


# ---- the INPUTS section: NAMED interaction KNOBS (scroll delta, pgup/pgdn overlap, status TTL) -------------
class InputKnob(NamedTuple):
    """One editable INPUTS knob -- the config attribute, its JSON key, a label, and the adjust step + bounds."""
    attr: str
    key: str
    label: str
    step: float
    floor: float
    ceil: float


INPUT_KNOBS = (
    InputKnob('scroll_delta', KEY_SCROLL_DELTA, 'scroll delta (rows/step)', 1, 1, 20),
    InputKnob('page_overlap', KEY_PAGE_OVERLAP, 'pgup/pgdn overlap (rows)', 1, 0, 20),
    InputKnob('status_ttl_seconds', KEY_STATUS_TTL, 'status TTL (seconds)', 1.0, 1.0, 60.0),
)
# the screen region the INPUTS knobs conceptually live in (the input fence) -- for the live edit-area highlight.
REGION_INPUTS = 'input'

# ---- NAMED screen regions a slot group maps to (so the View knows which AREA to highlight) -----------------
REGION_FOR_GROUP = {
    SLOT_STATE: 'state',
    SLOT_DETAILS_LEFT: 'details',
    SLOT_DETAILS_RIGHT: 'details',
}
# the ORDER slot groups are walked at level SLOTS (state strip first, then the two details groups).
GROUP_ORDER = (SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT)


class SlotPos(NamedTuple):
    """One editable slot position -- which group it lives in, its index in that group, and its current alias."""
    group: str
    position: int
    alias: str


class Bind(NamedTuple):
    """A requested rebind -- bind ``alias`` to slot ``position`` in ``group`` (the caller applies + persists)."""
    group: str
    position: int
    alias: str


def build_slot_catalogue(slots) -> List[SlotPos]:
    """Flatten the config's slot groups into the 1D list the SLOTS level walks (state, then the two details)."""
    catalogue: List[SlotPos] = []
    for group in GROUP_ORDER:
        for position, alias in enumerate(slots.get(group, [])):
            catalogue.append(SlotPos(group=group, position=position, alias=alias))
    return catalogue


@dataclass
class EditorState:
    """The PURE multi-level editor cursor -- the current level + the cursors + the slot catalogue + the config.

    The TOP level (SLOTS) walks a COMBINED list: the flattened slot positions FIRST, then the INPUTS knobs. The
    cursor ``slot_index`` indexes that combined list. Entering a SLOT descends to ALIASES (pick a field alias);
    entering an INPUTS knob descends to INPUTS (Up/Down nudges the value, Enter commits). ``config`` is the live
    UserConfig the INPUTS sublevel adjusts in place (the caller persists). All transitions are PURE over state.
    """
    catalogue: List[SlotPos] = field(default_factory=list)
    config: Optional[object] = None      # the live UserConfig (the INPUTS knobs read/adjust it); set by the VM
    level: str = LEVEL_SLOTS
    slot_index: int = 0                  # the cursor over the COMBINED (slots + inputs) top-level list
    alias_index: int = 0
    inputs_index: int = 0                # the cursor over INPUT_KNOBS while at the INPUTS sublevel
    editing: Optional[SlotPos] = None    # the slot being rebound (ALIASES sublevel)
    editing_knob: Optional[InputKnob] = None  # the knob being adjusted (INPUTS sublevel)

    # ---- the COMBINED top-level list: slot positions THEN the INPUTS knobs ----------------------------------
    def top_len(self) -> int:
        """The COMBINED top-level entry count -- the slot positions plus the INPUTS knobs."""
        return len(self.catalogue) + len(INPUT_KNOBS)

    def is_input_row(self, idx: Optional[int] = None) -> bool:
        """True when the (given or current) top-level cursor sits on an INPUTS knob (past the slot positions)."""
        i = self.slot_index if idx is None else idx
        return i >= len(self.catalogue)

    def current_knob(self) -> Optional[InputKnob]:
        """The INPUTS knob under the top-level cursor (None when the cursor is on a slot position)."""
        if not self.is_input_row():
            return None
        ki = self.slot_index - len(self.catalogue)
        if 0 <= ki < len(INPUT_KNOBS):
            return INPUT_KNOBS[ki]
        return None

    def knob_value(self, knob: InputKnob):
        """The current value of a knob (read off the live config) -- '?' if no config is wired (shouldn't happen)."""
        if self.config is None:
            return '?'
        return getattr(self.config, knob.attr)

    # ---- the available alias picker (alias, label) pairs -- the level-ALIASES list --------------------------
    def aliases(self) -> List[Tuple[str, str]]:
        return fields.alias_choices()

    def current_slot(self) -> Optional[SlotPos]:
        if not self.catalogue or self.is_input_row():
            return None
        idx = max(0, min(self.slot_index, len(self.catalogue) - 1))
        return self.catalogue[idx]

    def highlight_region(self) -> Optional[str]:
        """The screen REGION the current entry lives in -- the AREA the View paints (live edit preview).

        A slot position highlights its group's region (state / details); an INPUTS knob highlights the input fence.
        """
        if self.is_input_row():
            return REGION_INPUTS
        slot = self.current_slot()
        if slot is None:
            return None
        return REGION_FOR_GROUP.get(slot.group)

    # ---- PURE transitions: each returns a Bind ONLY on a level-ALIASES Enter (slot rebind); else None -------
    def move_up(self) -> Optional[Bind]:
        if self.level == LEVEL_SLOTS:
            self.slot_index = max(0, self.slot_index - 1)
        elif self.level == LEVEL_ALIASES:
            self.alias_index = max(0, self.alias_index - 1)
        else:  # LEVEL_INPUTS -- Up INCREASES the value (nudge up by the knob step, clamped to the ceiling)
            self._nudge_knob(+1)
        return None

    def move_down(self) -> Optional[Bind]:
        if self.level == LEVEL_SLOTS:
            self.slot_index = min(max(0, self.top_len() - 1), self.slot_index + 1)
        elif self.level == LEVEL_ALIASES:
            self.alias_index = min(max(0, len(self.aliases()) - 1), self.alias_index + 1)
        else:  # LEVEL_INPUTS -- Down DECREASES the value (clamped to the floor)
            self._nudge_knob(-1)
        return None

    def _nudge_knob(self, direction: int) -> None:
        """Adjust the editing knob's value on the live config by its step*direction, clamped to [floor, ceil]."""
        knob = self.editing_knob
        if knob is None or self.config is None:
            return
        current = getattr(self.config, knob.attr)
        nxt = current + knob.step * direction
        nxt = max(knob.floor, min(knob.ceil, nxt))
        # preserve the value's type (int knobs stay int; float knobs stay float) so persistence round-trips.
        setattr(self.config, knob.attr, type(current)(nxt))

    def enter(self) -> Optional[Bind]:
        """Descend a level, or commit. SLOTS->ALIASES (slot) / SLOTS->INPUTS (knob); ALIASES Enter emits a Bind;
        INPUTS Enter commits the (already-applied) value + returns to SLOTS (the caller persists). Bind only on bind."""
        if self.level == LEVEL_SLOTS:
            if self.is_input_row():
                knob = self.current_knob()
                if knob is None:
                    return None
                self.editing_knob = knob
                self.level = LEVEL_INPUTS
                return None
            slot = self.current_slot()
            if slot is None:
                return None
            self.editing = slot
            self.level = LEVEL_ALIASES
            self.alias_index = 0
            return None
        if self.level == LEVEL_INPUTS:
            # the value was nudged in place on the config already; Enter just commits the adjust + ascends.
            self.level = LEVEL_SLOTS
            self.editing_knob = None
            return None
        # LEVEL_ALIASES
        choices = self.aliases()
        if not choices or self.editing is None:
            self.level = LEVEL_SLOTS
            return None
        idx = max(0, min(self.alias_index, len(choices) - 1))
        alias = choices[idx][0]
        bind = Bind(group=self.editing.group, position=self.editing.position, alias=alias)
        self.level = LEVEL_SLOTS
        self.editing = None
        return bind

    def back(self) -> Optional[Bind]:
        """Esc/Backspace -- at a sublevel return to SLOTS (no slot change); at SLOTS this means EXIT (caller closes)."""
        if self.level == LEVEL_ALIASES:
            self.level = LEVEL_SLOTS
            self.editing = None
        elif self.level == LEVEL_INPUTS:
            self.level = LEVEL_SLOTS
            self.editing_knob = None
        return None

    def at_top_level(self) -> bool:
        """True when a ``back`` should EXIT config mode (we are at level SLOTS) rather than ascend a level."""
        return self.level == LEVEL_SLOTS
