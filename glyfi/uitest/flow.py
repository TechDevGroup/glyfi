"""flow -- the FLOW: a BDD-shaped scenario that drives the headless app autonomously, then checks conformance.

``Flow(name).given(*fixtures).when(*steps).then(*constraints).run()`` is the autonomous drive surface -- the
"interface with the system to drive interactions" of the framework. Given fixtures build/layer a ``RunContext``;
when steps drive the app (recording a TRACE); then constraints are checked against the FINAL Probe. A failure
FAILS LOUD with the LOCATED conformance violation + the full step trace.

SOLID: the Flow ORCHESTRATES; it knows NOTHING of concrete verbs/constraints/fixtures -- it calls their
interfaces (``Fixture.setup``, ``Step.run``, ``Constraint.check``). A new verb/constraint/fixture works in a
flow without touching this module.

Imports this package's fixtures/actions/constraints/context + stdlib only.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from glyfi.uitest.actions import Step
from glyfi.uitest.constraints import Constraint, ConformanceResult, Violation, Probe
from glyfi.uitest.context import RunContext
from glyfi.uitest.fixtures import Fixture


class FlowError(AssertionError):
    """A flow's THEN did not conform -- carries the located result + the trace dump (fail loud, never silent)."""

    def __init__(self, name: str, result: ConformanceResult, trace_dump: str):
        super().__init__(f'flow {name!r} FAILED conformance:\n  {result.describe()}\n--- trace ---\n{trace_dump}')
        self.flow_name = name
        self.result = result
        self.trace_dump = trace_dump


@dataclass(frozen=True)
class FlowResult:
    """The outcome of a flow run -- ``passed`` + the final conformance + the trace (for a report / debugging)."""
    name: str
    passed: bool
    result: ConformanceResult
    trace: Tuple
    final_probe: Probe

    def describe(self) -> str:
        head = f'FLOW {self.name}: {"PASS" if self.passed else "FAIL"}'
        if self.passed:
            return head
        return f'{head}\n  {self.result.describe()}'


@dataclass
class Flow:
    """A BDD-shaped flow -- ``given`` fixtures, ``when`` steps, ``then`` constraints; ``run`` executes + checks.

    The clauses are fluent builders (each returns self). ``run`` (a) sets up the context through the fixtures in
    order (the first builds it, the rest layer), (b) runs each step (recording the trace), (c) checks the THEN
    constraints against the final probe, and returns a ``FlowResult``. ``run_strict`` raises ``FlowError`` on a
    non-conforming THEN (the pytest-facing entry); ``run`` returns the result without raising (the report-facing
    entry). Fixture teardowns run in REVERSE order in a finally, always.
    """
    name: str
    fixtures: List[Fixture] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)

    def given(self, *fixtures: Fixture) -> 'Flow':
        self.fixtures.extend(fixtures)
        return self

    def when(self, *steps: Step) -> 'Flow':
        self.steps.extend(steps)
        return self

    def then(self, *constraints: Constraint) -> 'Flow':
        self.constraints.extend(constraints)
        return self

    def run(self) -> FlowResult:
        """Execute the flow and return a ``FlowResult`` (does NOT raise on a non-conforming THEN -- report path)."""
        if not self.fixtures:
            raise ValueError(f'flow {self.name!r} has no GIVEN fixture (needs a base, e.g. fresh_app)')
        if not self.fixtures[0].base:
            raise ValueError(f'flow {self.name!r}: the first GIVEN must be a BASE fixture (builds the context)')
        ctx: Optional[RunContext] = None
        applied: List[Fixture] = []
        try:
            for fx in self.fixtures:
                ctx = fx.setup(ctx)
                applied.append(fx)
            for step in self.steps:
                step.run(ctx)
            result = self._check(ctx)
            final = ctx.probe()
            return FlowResult(name=self.name, passed=result.holds, result=result,
                              trace=tuple(ctx.trace), final_probe=final)
        finally:
            for fx in reversed(applied):
                if fx.teardown is not None and ctx is not None:
                    fx.teardown(ctx)

    def run_strict(self) -> FlowResult:
        """Execute + FAIL LOUD (raise ``FlowError`` with the located violation + trace) if the THEN does not hold."""
        # run inside its own try so we can dump the trace even on a constraint failure
        ctx: Optional[RunContext] = None
        applied: List[Fixture] = []
        try:
            for fx in self.fixtures:
                ctx = fx.setup(ctx)
                applied.append(fx)
            for step in self.steps:
                step.run(ctx)
            result = self._check(ctx)
            if not result.holds:
                raise FlowError(self.name, result, ctx.trace_dump())
            return FlowResult(name=self.name, passed=True, result=result,
                              trace=tuple(ctx.trace), final_probe=ctx.probe())
        finally:
            for fx in reversed(applied):
                if fx.teardown is not None and ctx is not None:
                    fx.teardown(ctx)

    def _check(self, ctx: RunContext) -> ConformanceResult:
        if not self.constraints:
            raise ValueError(f'flow {self.name!r} has no THEN constraint (a flow must assert something)')
        probe = ctx.probe()
        violations: List[Violation] = []
        for c in self.constraints:
            r = c.check(probe)
            if not r.holds:
                violations.extend(r.violations)
        if not violations:
            return ConformanceResult.ok()
        return ConformanceResult.fail(*violations)
