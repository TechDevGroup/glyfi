"""clock -- the injectable Clock PORT: a monotonic time source the UI's timing reads (never wall-clock directly).

The UI has exactly one piece of *control-flow* timing -- the ephemeral status TICKER's TTL (a pushed status
message clears itself after a configured time-to-live). That timing must be DRIVABLE: in tests a virtual clock
advances deterministically (no sleeps, no wall-clock flake); at runtime curses' periodic ``getch`` timeout
advances a real monotonic clock so the ticker expires on its own. So all such timing reads go through this PORT,
NEVER ``time.monotonic`` / ``time.time`` inline in logic.

(The localtime FIELD -- ``fields.localtime`` -- still calls ``time.localtime`` directly: that is DISPLAY of the
wall clock, not control flow, so it is explicitly out of scope for this port.)

Two impls behind the ``Clock`` port (SOLID -- open/closed: a new clock plugs in without touching callers):
  * ``MonotonicClock`` -- the RUNTIME clock; ``now()`` reads ``time.monotonic`` (monotonic, immune to wall-clock
    jumps -- the right base for a TTL countdown).
  * ``VirtualClock``   -- the TEST clock; ``now()`` returns an accumulator the test advances by hand via
    ``advance(dt)``. Deterministic: no real time passes, the TTL is crossed exactly when the test says so.

stdlib ``time`` only (and only in the runtime impl).
"""
from abc import ABC, abstractmethod

# ---- NAMED time unit (no magic literal at a call site) ----------------------------------------------------
# The Clock works in SECONDS (float); TTL config values are seconds. Named so a call site reads in this unit.
SECONDS = 1.0


class Clock(ABC):
    """The Clock PORT -- a monotonic time source in SECONDS. The UI's TTL/timing reads this, never wall-clock."""

    @abstractmethod
    def now(self) -> float:
        """The current monotonic time in SECONDS. Monotonic non-decreasing -- safe to subtract for an elapsed."""
        raise NotImplementedError('Clock.now -- a concrete clock (monotonic / virtual) must implement this')


class MonotonicClock(Clock):
    """The RUNTIME clock -- ``now()`` reads ``time.monotonic`` (monotonic seconds, immune to wall-clock jumps)."""

    def now(self) -> float:
        import time
        return time.monotonic()


class VirtualClock(Clock):
    """The TEST clock -- a hand-advanced accumulator. ``advance(dt)`` moves it; ``now()`` returns the accumulator.

    Deterministic: no real time passes, so a TTL is crossed EXACTLY when the test advances past it. Fail LOUD on
    a negative advance (a monotonic clock never goes backwards -- a negative step is a test mistake we surface).
    """

    def __init__(self, start: float = 0.0):
        self._now = float(start)

    def now(self) -> float:
        return self._now

    def advance(self, dt: float) -> float:
        """Advance the virtual clock by ``dt`` seconds (must be >= 0 -- monotonic). Returns the new ``now``."""
        if dt < 0:
            raise ValueError(f'VirtualClock.advance: dt must be >= 0 (monotonic), got {dt}')
        self._now += float(dt)
        return self._now
