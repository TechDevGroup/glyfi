"""actions -- the interaction VERBS: Playwright-like driver steps, ONE class per verb (SRP), open/closed.

A flow's WHEN is a sequence of ``Step`` verbs run against a driven app. Each verb does ONE thing through the
``AppDriver`` drive surface (the SAME seam the curses runtime uses) and records itself onto the run trace. ALL
timing goes through the driver's VirtualClock -- ``Delay`` / ``WaitUntil`` advance it; there is NO wall-clock
anywhere (no ``time.sleep``), so a flow is deterministic and CI-safe.

SOLID:
  * SRP -- each verb is its own small class with a single ``run(ctx)``; the runner (Flow) calls ``run`` blind to
    the concrete verb.
  * OPEN/CLOSED -- verbs live in a NAMED registry; ``register_action`` adds a verb WITHOUT editing the runner or
    any other verb. A new verb is usable in a flow + (if it follows the ``name(args)`` convention) a spec.

Fail LOUD: ``Expect`` raises a ``ConstraintError`` carrying the LOCATED conformance violation; ``WaitUntil``
raises a ``WaitTimeout`` (also located) when the constraint never holds within the budget. No verb silently
no-ops on a fault.

Imports the headless driver + clock + this package's constraints/context + stdlib only.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List

from glyfi.ui.clock import VirtualClock
from glyfi.ui.settings import TAB
from glyfi.uitest.constraints import Constraint, Probe, ConformanceResult
from glyfi.uitest.context import RunContext


# ---- NAMED wait tunables (no magic literals at a call site) ------------------------------------------------
DEFAULT_WAIT_TIMEOUT = 8.0     # seconds of VIRTUAL clock a WaitUntil will advance before giving up
DEFAULT_WAIT_POLL = 0.5        # the VIRTUAL-clock increment WaitUntil advances per poll


class ConstraintError(AssertionError):
    """An ``Expect`` failed -- carries the LOCATED ConformanceResult (oriented violation, not a bare assert)."""

    def __init__(self, result: ConformanceResult):
        super().__init__(result.describe())
        self.result = result


class WaitTimeout(AssertionError):
    """A ``WaitUntil`` exhausted its virtual-clock budget -- carries the still-violated, LOCATED result."""

    def __init__(self, result: ConformanceResult, timeout: float):
        super().__init__(f'wait timed out after {timeout}s of virtual time: {result.describe()}')
        self.result = result
        self.timeout = timeout


# ===== the Step base + registry ============================================================================

class Step:
    """The interaction-verb base -- ``run(ctx)`` drives ONE step against the app + records itself on the trace.

    Concrete verbs implement ``_apply(ctx)`` (the actual drive) and ``label`` (the trace name). The base ``run``
    snapshots a Probe AFTER applying and appends a trace entry, so every flow run carries a step-by-step record
    of what was driven + what the app looked like after it.
    """
    label: str = 'step'

    def _apply(self, ctx: RunContext) -> None:
        raise NotImplementedError(f'{type(self).__name__}._apply must drive the app')

    def run(self, ctx: RunContext) -> None:
        self._apply(ctx)
        ctx.record_step(self.label, Probe.of(ctx.driver))


# the verb registry: name -> a callable building a Step from args. Open/closed.
ActionBuilder = Callable[..., Step]
_ACTIONS: Dict[str, ActionBuilder] = {}


def register_action(name: str, builder: ActionBuilder) -> None:
    """Register a NAMED action verb. Fail LOUD on a duplicate name (no silent clobber of a verb)."""
    if name in _ACTIONS:
        raise ValueError(f'action {name!r} already registered')
    _ACTIONS[name] = builder


def action_builder(name: str) -> ActionBuilder:
    """The registered builder for ``name`` -- fail LOUD on unknown (a spec naming an unknown verb is a fault)."""
    if name not in _ACTIONS:
        raise KeyError(f'unknown action {name!r} (known: {sorted(_ACTIONS)})')
    return _ACTIONS[name]


def known_actions() -> List[str]:
    return sorted(_ACTIONS)


# ===== the NAMED verbs (one class each -- SRP) =============================================================

@dataclass
class Press(Step):
    """Feed a key (curses int OR a single char) through the SAME modal dispatch the runtime uses."""
    key: object

    def __post_init__(self):
        self.label = f'Press({self.key!r})'

    def _apply(self, ctx: RunContext) -> None:
        key = ord(self.key) if isinstance(self.key, str) else int(self.key)
        ctx.driver.press(key)


@dataclass
class Type(Step):
    """Type text into the input line (PALETTE filter path or NORMAL buffer path, per mode)."""
    text: str

    def __post_init__(self):
        self.label = f'Type({self.text!r})'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.type_text(self.text)


@dataclass
class Invoke(Step):
    """Invoke a NAMED command/ViewModel method by name (request_prompt / clear / config / mode / quit / ...).

    For ``request_prompt`` a flow wires the (subject, text) the turn walks via the fixture's prompt seam -- this
    verb just fires the command. Fail loud on an unknown command (handled by the driver).
    """
    command: str

    def __post_init__(self):
        self.label = f'Invoke({self.command!r})'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.invoke(self.command)


@dataclass
class Submit(Step):
    """Submit the NORMAL input line (records history, emits InputSubmitted)."""
    label: str = 'Submit()'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.submit()


@dataclass
class Tab(Step):
    """Press Tab -- advance the ephemeral ticker ring (emits TickerCycled). A NAMED convenience over Press(TAB)."""
    label: str = 'Tab()'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.press(TAB)


@dataclass
class Tick(Step):
    """Advance the VirtualClock by ``dt`` and emit a Tick (the driver's tick -- expires the ticker TTL)."""
    dt: float

    def __post_init__(self):
        self.label = f'Tick({self.dt})'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.tick(self.dt)


@dataclass
class Delay(Step):
    """Advance the VirtualClock by ``dt`` seconds AND emit a Tick (so the TTL crosses) -- the time-passes verb.

    Identical drive to ``Tick`` but named for INTENT: a flow's ``Delay(ttl + eps)`` reads as 'let time pass past
    the TTL'. No wall-clock -- this moves the deterministic virtual clock only.
    """
    dt: float

    def __post_init__(self):
        self.label = f'Delay({self.dt})'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.tick(self.dt)


@dataclass
class WaitUntil(Step):
    """Advance the VirtualClock in ``poll`` increments until ``constraint`` HOLDS or ``timeout`` virtual-seconds.

    The autonomous ``wait_until`` of the framework -- it drives TIME (not wall time) forward, re-probing after
    each poll tick, and STOPS the instant the constraint conforms. On exhausting the budget it FAILS LOUD with a
    ``WaitTimeout`` carrying the still-LOCATED violation. Requires a VirtualClock (deterministic time).
    """
    constraint: Constraint
    timeout: float = DEFAULT_WAIT_TIMEOUT
    poll: float = DEFAULT_WAIT_POLL

    def __post_init__(self):
        self.label = f'WaitUntil({self.constraint.label}, timeout={self.timeout}, poll={self.poll})'

    def _apply(self, ctx: RunContext) -> None:
        if not isinstance(ctx.driver.vm.clock, VirtualClock):
            raise TypeError('WaitUntil requires a VirtualClock on the driver (deterministic time)')
        if self.poll <= 0:
            raise ValueError(f'WaitUntil.poll must be > 0, got {self.poll}')
        # check once at t0 (the constraint may already hold without any time passing)
        result = self.constraint.check(Probe.of(ctx.driver))
        if result.holds:
            return
        elapsed = 0.0
        while elapsed < self.timeout:
            ctx.driver.tick(self.poll)
            elapsed += self.poll
            result = self.constraint.check(Probe.of(ctx.driver))
            if result.holds:
                return
        raise WaitTimeout(result, self.timeout)


@dataclass
class Expect(Step):
    """Assert ``constraint`` HOLDS right now -- fail LOUD with the LOCATED violation if not. An inline THEN.

    Useful mid-WHEN (assert a precondition before driving on). The flow's THEN clause is the same check at the
    end; this verb lets a flow interleave assertions with drive steps.
    """
    constraint: Constraint

    def __post_init__(self):
        self.label = f'Expect({self.constraint.label})'

    def _apply(self, ctx: RunContext) -> None:
        result = self.constraint.check(Probe.of(ctx.driver))
        if not result.holds:
            raise ConstraintError(result)


@dataclass
class ClearEvents(Step):
    """Drop the recorded-event log -- scope the next steps' event assertions (e.g. before the one-turn Invoke)."""
    label: str = 'ClearEvents()'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.clear_events()


@dataclass
class Resize(Step):
    """Resize the synthetic terminal the headless View solves against (re-solves the layout, emits Resized)."""
    w: int
    h: int

    def __post_init__(self):
        self.label = f'Resize({self.w}, {self.h})'

    def _apply(self, ctx: RunContext) -> None:
        ctx.driver.resize(self.w, self.h)


def _register_builtins() -> None:
    """Wire the built-in verbs into the registry (the BDD layer + a spec can name these)."""
    register_action('press', lambda key: Press(key))
    register_action('type', lambda text: Type(text))
    register_action('invoke', lambda command: Invoke(command))
    register_action('submit', lambda: Submit())
    register_action('tab', lambda: Tab())
    register_action('tick', lambda dt: Tick(float(dt)))
    register_action('delay', lambda dt: Delay(float(dt)))
    register_action('wait_until', lambda constraint, **kw: WaitUntil(constraint, **kw))
    register_action('expect', lambda constraint: Expect(constraint))
    register_action('clear_events', lambda: ClearEvents())
    register_action('resize', lambda w, h: Resize(int(w), int(h)))


_register_builtins()
