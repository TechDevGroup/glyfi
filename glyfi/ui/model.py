"""model -- the MVVM MODEL: client-side state (session + per-turn display records + the display Settings).

The Model is the DATA layer of the MVVM split. It holds:
  * ``SessionState``   -- the live session identity + protocol-level fields the app displays (session id, seq,
                          current mode label, last subject). This mirrors the stepper's visible state, kept as a
                          plain client-side record.
  * ``TurnRecord``     -- a per-turn DISPLAY record distilled from a walked turn: the request echo + EITHER the
                          staged response fields OR the fail-loud error. This is a presentation-shaped view of
                          the stepper's ``Turn`` -- the Model does NOT re-walk or re-interpret; it records.
  * ``AppSettings``    -- the pluggable display settings (anchors/keys/title), carried on the Model so the View
                          and ViewModel read one source of appearance truth.

MVVM discipline: the Model is DUMB DATA -- it holds state, exposes simple recorders/accessors, and contains NO
presentation logic (that lives in the ViewModel) and NO rendering (that lives in the View). It imports the
client protocol-shaped types only -- never a server module.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from glyfi.ui.settings import AppSettings
from glyfi.ui.config_store import UserConfig


@dataclass
class SessionState:
    """The live, displayable session state -- the protocol-level fields the state strip shows. Plain data."""
    session_id: str
    seq: int = 0
    mode: str = ""          # current plain mode label
    last_subject: str = ''


@dataclass(frozen=True)
class TurnRecord:
    """A per-turn DISPLAY record -- the presentation-shaped distillate of one walked turn (request + outcome).

    ``ok`` True carries the staged response fields; ``ok`` False carries the fail-loud error (shown, never
    swallowed). This is the Model's record of what the operator walked -- the View renders the transcript from
    a list of these; nothing here re-interprets the response.
    """
    index: int
    mode: str
    subject: str
    user_text: str
    ok: bool
    staged_content: Optional[str]
    response_seq: Optional[int]
    error: Optional[str]


@dataclass
class AppModel:
    """The MVVM Model -- session state + the recorded turn transcript + the display settings + the user CONFIG.

    The ViewModel mutates this Model in response to commands (record a turn, advance seq, select a turn, rebind a
    slot); the View reads it to render. The Model itself contains no command/render logic -- it is the single data
    home. ``config`` is the persisted user UI choices (slot binds / visibility / theme); ``content_buffer`` is a
    generic line buffer commands like ``help`` push display lines into (the View shows the transcript by default,
    the content buffer when one is set -- e.g. after ``help``).
    """
    session: SessionState
    settings: AppSettings = field(default_factory=AppSettings)
    config: UserConfig = field(default_factory=UserConfig)
    transcript: List[TurnRecord] = field(default_factory=list)
    content_buffer: List[str] = field(default_factory=list)

    def record_turn(self, record: TurnRecord) -> None:
        """Append a walked turn's display record to the transcript (the operator-driven history)."""
        self.transcript.append(record)

    def set_content(self, lines: List[str]) -> None:
        """Replace the generic content buffer (e.g. the ``help`` command pushes the command list here)."""
        self.content_buffer = list(lines)

    def clear_content(self) -> None:
        """Drop the generic content buffer (the content view falls back to the transcript)."""
        self.content_buffer = []

    @property
    def turn_count(self) -> int:
        return len(self.transcript)

    def turn_at(self, index: int) -> Optional[TurnRecord]:
        """The turn record at ``index`` (transcript order), or None if out of range -- the View tolerates None."""
        if 0 <= index < len(self.transcript):
            return self.transcript[index]
        return None
