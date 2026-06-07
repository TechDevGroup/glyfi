"""bdd -- the BDD layer: a Gherkin-ish Feature/Scenario model over flows + a readable report runner.

A thin, SOLID layer over ``flow.py`` so specs READ as Given/When/Then and DRIVE downstream TUI development. A
``Scenario`` is built from PHRASES -- ``given('a fresh app')``, ``when('I type', '/')``, ``then('mode is', 'CONFIG')``
-- mapped through a small STEP-PHRASE registry to fixtures / actions / constraints. The phrase registry is
open/closed: ``register_phrase`` adds a phrasing WITHOUT editing the runner (new Given/When/Then read naturally).

A scenario COMPILES to a ``Flow`` (so the BDD layer reuses the flow engine verbatim -- one execution path). The
runner executes scenarios and renders a readable BDD REPORT (pass/fail per scenario, the LOCATED violation on a
failure). It does NOT re-implement drive/conformance -- it composes the lower layers.

Imports this package's flow/fixtures/actions/constraints + stdlib only.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from glyfi.uitest.actions import Step
from glyfi.uitest.constraints import Constraint, parse_constraint
from glyfi.uitest.fixtures import Fixture
from glyfi.uitest.flow import Flow, FlowResult


# ---- the three clause kinds (a phrase registers under one) -------------------------------------------------
CLAUSE_GIVEN = 'given'
CLAUSE_WHEN = 'when'
CLAUSE_THEN = 'then'
CLAUSES = (CLAUSE_GIVEN, CLAUSE_WHEN, CLAUSE_THEN)


@dataclass(frozen=True)
class Phrase:
    """A registered BDD phrasing -- a clause kind + a human phrase + a ``build(*args)`` -> Fixture/Step/Constraint."""
    clause: str
    phrase: str
    build: Callable[..., object]


# the phrase registry, keyed (clause, phrase). Open/closed: register_phrase adds a phrasing.
_PHRASES: Dict[Tuple[str, str], Phrase] = {}


def register_phrase(clause: str, phrase: str, build: Callable[..., object]) -> None:
    """Register a BDD phrasing under (clause, phrase). Fail LOUD on a duplicate or an unknown clause kind."""
    if clause not in CLAUSES:
        raise ValueError(f'register_phrase: unknown clause {clause!r} (known: {CLAUSES})')
    key = (clause, phrase)
    if key in _PHRASES:
        raise ValueError(f'BDD phrase {key!r} already registered')
    _PHRASES[key] = Phrase(clause=clause, phrase=phrase, build=build)


def _resolve(clause: str, phrase: str, args: Tuple) -> object:
    key = (clause, phrase)
    if key not in _PHRASES:
        known = sorted(p for (c, p) in _PHRASES if c == clause)
        raise KeyError(f'unknown {clause} phrase {phrase!r} (known {clause} phrases: {known})')
    return _PHRASES[key].build(*args)


# ===== the Scenario / Feature model ========================================================================

@dataclass
class Scenario:
    """A Gherkin-ish scenario -- Given/When/Then phrase clauses that COMPILE to a Flow (the one execution path).

    Each clause records (phrase, args); ``compile`` resolves them through the phrase registry into fixtures /
    steps / constraints and builds a ``Flow``. ``run`` compiles + runs (report path); ``run_strict`` fails loud.
    """
    name: str
    _given: List[Tuple[str, Tuple]] = field(default_factory=list)
    _when: List[Tuple[str, Tuple]] = field(default_factory=list)
    _then: List[Tuple[str, Tuple]] = field(default_factory=list)

    def given(self, phrase: str, *args) -> 'Scenario':
        self._given.append((phrase, args))
        return self

    def when(self, phrase: str, *args) -> 'Scenario':
        self._when.append((phrase, args))
        return self

    def then(self, phrase: str, *args) -> 'Scenario':
        self._then.append((phrase, args))
        return self

    def compile(self) -> Flow:
        """Resolve the phrase clauses through the registry into a ready ``Flow`` (reusing the flow engine)."""
        fixtures: List[Fixture] = [self._as(CLAUSE_GIVEN, p, a, Fixture) for p, a in self._given]
        steps: List[Step] = [self._as(CLAUSE_WHEN, p, a, Step) for p, a in self._when]
        constraints: List[Constraint] = [self._as(CLAUSE_THEN, p, a, Constraint) for p, a in self._then]
        return Flow(name=self.name).given(*fixtures).when(*steps).then(*constraints)

    def _as(self, clause: str, phrase: str, args: Tuple, kind: type):
        obj = _resolve(clause, phrase, args)
        if not isinstance(obj, kind):
            raise TypeError(f'{clause} phrase {phrase!r} built a {type(obj).__name__}, expected {kind.__name__}')
        return obj

    def run(self) -> FlowResult:
        return self.compile().run()

    def run_strict(self) -> FlowResult:
        return self.compile().run_strict()


@dataclass
class Feature:
    """A named Feature -- a group of scenarios + a readable run report. The downstream-dev-driving spec surface."""
    name: str
    scenarios: List[Scenario] = field(default_factory=list)

    def scenario(self, name: str) -> Scenario:
        sc = Scenario(name=name)
        self.scenarios.append(sc)
        return sc

    def run(self) -> 'FeatureReport':
        """Run every scenario (report path -- no raise) and collect the results into a ``FeatureReport``."""
        results = [(sc.name, sc.run()) for sc in self.scenarios]
        return FeatureReport(feature=self.name, results=results)


@dataclass(frozen=True)
class FeatureReport:
    """A rendered BDD report -- per-scenario pass/fail + the located violation on a failure. ``ok`` is all-green."""
    feature: str
    results: List[Tuple[str, FlowResult]]

    @property
    def ok(self) -> bool:
        return all(r.passed for _name, r in self.results)

    def render(self) -> str:
        """A readable Gherkin-style report block (one line per scenario; the located violation under a failure)."""
        lines = [f'Feature: {self.feature}']
        for name, result in self.results:
            mark = 'PASS' if result.passed else 'FAIL'
            lines.append(f'  Scenario: {name} ... {mark}')
            if not result.passed:
                lines.append(f'      ! {result.result.describe()}')
        lines.append(f'  ==> {"ALL PASS" if self.ok else "FAILURES"} '
                     f'({sum(1 for _n, r in self.results if r.passed)}/{len(self.results)})')
        return '\n'.join(lines)


# ===== the built-in phrase vocabulary (natural Given/When/Then over the registries) ========================

def _register_builtins() -> None:
    """Wire a natural-reading default phrase vocabulary. Each maps to a fixture / verb / constraint builder.

    These are thin -- they call the same registries the declarative API uses. A spec author adds a phrasing with
    ``register_phrase`` (open/closed) rather than editing this.
    """
    from glyfi.uitest import actions as A
    from glyfi.uitest import constraints as C
    from glyfi.uitest import fixtures as F

    # ---- GIVEN (fixtures) ----
    register_phrase(CLAUSE_GIVEN, 'a fresh app', lambda: F.fresh_app())
    register_phrase(CLAUSE_GIVEN, 'a fresh app of size', lambda w, h: F.fresh_app(size=(int(w), int(h))))
    register_phrase(CLAUSE_GIVEN, 'the server scripts', lambda script, **kw: F.scripted_server(script, **kw))
    register_phrase(CLAUSE_GIVEN, 'a seeded transcript', lambda turns, **kw: F.seeded_transcript(turns, **kw))
    register_phrase(CLAUSE_GIVEN, 'the listed subjects', lambda listing: F.with_subjects(listing))
    register_phrase(CLAUSE_GIVEN, 'the next prompt is', lambda subject, text: F.with_prompt_entry(subject, text))
    register_phrase(CLAUSE_GIVEN, 'the terminal size', lambda w, h: F.at_size(int(w), int(h)))

    # ---- WHEN (verbs) ----
    register_phrase(CLAUSE_WHEN, 'I type', lambda text: A.Type(text))
    register_phrase(CLAUSE_WHEN, 'I press', lambda key: A.Press(key))
    register_phrase(CLAUSE_WHEN, 'I submit', lambda: A.Submit())
    register_phrase(CLAUSE_WHEN, 'I invoke', lambda command: A.Invoke(command))
    register_phrase(CLAUSE_WHEN, 'I press Tab', lambda: A.Tab())
    register_phrase(CLAUSE_WHEN, 'time passes', lambda dt: A.Delay(float(dt)))
    register_phrase(CLAUSE_WHEN, 'I wait until', lambda spec, **kw: A.WaitUntil(parse_constraint(spec), **kw))
    register_phrase(CLAUSE_WHEN, 'I clear events', lambda: A.ClearEvents())

    # ---- THEN (constraints -- accept a terse SPEC string, parsed) ----
    register_phrase(CLAUSE_THEN, 'the app conforms to', lambda spec: parse_constraint(spec))
    register_phrase(CLAUSE_THEN, 'mode is', lambda ui: C.mode_is(ui))
    register_phrase(CLAUSE_THEN, 'the status is', lambda text: C.status_is(text))
    register_phrase(CLAUSE_THEN, 'the status is blank', lambda: C.status_blank())
    register_phrase(CLAUSE_THEN, 'the input is', lambda text: C.input_is(text))
    register_phrase(CLAUSE_THEN, 'region contains', lambda name, text: C.region_contains(name, text))
    register_phrase(CLAUSE_THEN, 'an event was emitted', lambda type_name: C.event_emitted(type_name))
    register_phrase(CLAUSE_THEN, 'exactly N events', lambda type_name, n: C.event_count(type_name, int(n)))
    register_phrase(CLAUSE_THEN, 'the transcript length is', lambda n: C.transcript_len(int(n)))
    register_phrase(CLAUSE_THEN, 'the seq is', lambda n: C.seq_is(int(n)))
    register_phrase(CLAUSE_THEN, 'the area is highlighted', lambda region: C.highlighted(region))


_register_builtins()
