"""stepper -- the turn-based stepper. ONE turn at a time, by hand; NEVER auto-loops.

The operator walks a conversation: type a message -> step the server ONCE -> see the response + the
visible state -> STOP, waiting for the next turn. A conversation is the operator-driven sequence of
turns over ONE session id (id + seq); the stepper holds the TURN SPINE so the operator can review it.

Design rules (honored exactly):
  * NO auto-advance: ``step`` runs EXACTLY ONE turn and returns; there is no loop, batch, or replay.
  * Fail LOUD, but VISIBLE: a malformed/denied turn is CAPTURED into the turn record (so the TUI can
    show the error envelope) -- the fault is surfaced, never silently swallowed. ``Turn.ok`` is the flag.
  * The stepper owns the transport PORT + the session id + the seq + a one-turn ``send``.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from glyfi.protocol import (
    Message,
    ProtocolError,
    ROLE_USER,
    TurnRequest,
    TurnResponse,
)
from glyfi.transport import Transport


@dataclass(frozen=True)
class Turn:
    """ONE captured turn -- the request snapshot + EITHER the staged response OR the fail-loud error.

    ``ok`` is True when the server staged a response; False when the turn failed loud (malformed /
    denied / unknown subject). On a failed turn ``response`` is None and ``error`` carries the surfaced
    message -- the fault is captured for DISPLAY, never swallowed.
    """
    index: int                          # 0-based position on the spine (NOT the engine seq)
    request: TurnRequest                # the literal request snapshot the operator issued this turn
    response: Optional[TurnResponse]    # the staged response (None on a failed turn)
    error: Optional[str]                # the fail-loud error message (None on a successful turn)

    @property
    def ok(self) -> bool:
        return self.response is not None


@dataclass
class Stepper:
    """Turn-based stepper over ONE session id. Holds the transport + session id + seq + the TURN SPINE.

    The operator calls ``step`` once per turn, by hand. HARD LAW: ``step`` runs EXACTLY one turn and
    STOPS -- never loops/batches/replays. The ``spine`` is the operator-driven history of turns over this
    session; ``history`` keeps the staged responses for review.
    """
    transport: Transport
    session_id: str
    seq: int = 0
    spine: List[Turn] = field(default_factory=list)
    history: List[TurnResponse] = field(default_factory=list)

    def step(self, user_text: str, subject: str = "", mode: str = "") -> Turn:
        """Walk exactly ONE turn: send the message, capture the staged response or the fail-loud error.

        Builds a ``TurnRequest`` with a single user message, sends it, and captures either the
        ``TurnResponse`` or the surfaced ``ProtocolError`` into a ``Turn`` appended to the spine. The seq
        advances ONLY on success. Returns the captured ``Turn`` and STOPS -- the operator drives the next
        turn by hand. This method runs a SINGLE turn; it does not loop, batch, or auto-advance.
        """
        index = len(self.spine)
        request = TurnRequest(
            session_id=self.session_id,
            seq=self.seq,
            messages=[Message(role=ROLE_USER, content=user_text, subject=subject)],
            mode=mode,
        )
        try:
            response = self.transport.send(request)
        except ProtocolError as exc:
            # fail LOUD but VISIBLE -- capture the surfaced fault into the turn for the TUI to display.
            turn = Turn(index=index, request=request, response=None, error=str(exc))
            self.spine.append(turn)
            return turn
        self.seq = response.seq          # advance the client-held seq to the server's
        self.history.append(response)
        turn = Turn(index=index, request=request, response=response, error=None)
        self.spine.append(turn)
        return turn
