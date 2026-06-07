"""constraints -- the UI-interaction CONSTRAINT scope: a Probe of the driver + predicate Constraints over it.

A flow asserts that the observable surface of the headless app CONFORMS to a constraint. A constraint is NOT a
bare bool -- it returns a ``ConformanceResult`` that, on failure, says WHAT failed + WHERE (region / event /
slot / mode) and the OBSERVED-vs-EXPECTED -- an oriented conformance axis. That LOCATED violation is what the
Flow/BDD layers surface on a failure.

Two surfaces, mirroring the rest of the codebase:
  * a DECLARATIVE builder API -- ``region_contains('content', 'ok')`` etc. + combinators ``all_of/any_of/not_``;
  * a terse STRING spec form -- ``"mode==CONFIG & highlighted(state)"`` -- parsed (small, fail-loud) into the same
    Constraint objects, so a spec author can write constraints inline.

Open/closed: constraint builders live in a NAMED registry; ``register_constraint`` adds a builder WITHOUT editing
the parser or the runner. The parser dispatches purely on the registry (a new builder is parseable for free if it
follows the ``name(args)`` / ``key==value`` grammar).

Imports the headless presentation surface (``driver``/``events``/``view``/``viewmodel``) + stdlib ONLY.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple, Type

from glyfi.ui.driver import AppDriver
from glyfi.ui.events import Event, EVENT_TYPES
from glyfi.ui.view import Painting
from glyfi.ui.viewmodel import UI_NORMAL, UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE


# ---- NAMED ui-mode vocabulary (the terse spec's ``mode==X`` values) ---------------------------------------
UI_MODES = (UI_NORMAL, UI_PALETTE, UI_CONFIG, UI_WIDGET, UI_PROMPT, UI_TRAVERSE)
# the event types keyed by NAME (so a spec / builder can name ``TurnRecorded`` etc. without importing the class).
EVENT_BY_NAME: Dict[str, Type[Event]] = {t.__name__: t for t in EVENT_TYPES}


# ===== the PROBE -- the observable surface of a driver at one instant ======================================

@dataclass(frozen=True)
class Probe:
    """A snapshot of EVERYTHING a constraint can observe on a driven app at one instant -- pure data, no driver.

    Built from an ``AppDriver`` via ``Probe.of(driver)``. It captures the painted presentation (regions, status,
    input, mode, highlights), the emitted-event log (+ per-type counts), and read-through model state (transcript
    length, selected index, slot bindings, seq). A constraint reads ONLY a Probe -- so a violation can quote the
    exact observed value, and a flow can keep the snapshot in its trace without holding a live driver.
    """
    regions: Dict[str, List[str]]
    status_line: str
    input_line: str
    mode_ui: str
    highlight_regions: frozenset
    highlight_cells: Dict[str, Tuple[int, int, int]]
    highlight_rows: Dict[str, int]
    event_log: Tuple[Event, ...]
    event_counts: Dict[str, int]
    transcript_len: int
    selected: int
    slots: Dict[str, List[str]]
    seq: int
    clock_now: float

    @staticmethod
    def of(driver: AppDriver) -> 'Probe':
        """Capture the driver's CURRENT observable surface into an immutable Probe (the constraint's read model)."""
        painting: Painting = driver.painting
        log = tuple(driver.events)
        counts: Dict[str, int] = {}
        for ev in log:
            counts[type(ev).__name__] = counts.get(type(ev).__name__, 0) + 1
        vm = driver.vm
        return Probe(
            regions={name: list(lines) for name, lines in painting.regions.items()},
            status_line=driver.status_line(),
            input_line=driver.input_line(),
            mode_ui=vm.mode_ui,
            highlight_regions=painting.highlight_regions,
            highlight_cells=dict(painting.highlight_cells),
            highlight_rows=dict(painting.highlight_rows),
            event_log=log,
            event_counts=counts,
            transcript_len=vm.model.turn_count,
            selected=vm.selected,
            slots={g: list(a) for g, a in vm.config.slots.items()},
            seq=vm.session.seq,
            clock_now=vm.clock.now(),
        )

    def region_text(self, name: str) -> str:
        """The joined text of region ``name`` (newline-joined lines) -- for substring constraints."""
        return '\n'.join(self.regions.get(name, []))


# ===== the CONFORMANCE result -- oriented, LOCATED violations (not a bare bool) =============================

@dataclass(frozen=True)
class Violation:
    """ONE located conformance violation -- WHAT failed + WHERE + the observed-vs-expected (oriented, not 'false').

    ``locus`` is the axis the violation sits on (region / event / slot / mode / input / status / transcript / seq)
    and ``target`` the specific name within it (a region name, an event type, a slot key, ...). ``expected`` and
    ``observed`` carry the orientation -- a reader sees exactly what was wanted vs what the app showed.
    """
    constraint: str
    locus: str
    target: str
    expected: str
    observed: str

    def describe(self) -> str:
        return (f'{self.constraint}: [{self.locus}:{self.target}] '
                f'expected {self.expected!r}, observed {self.observed!r}')


@dataclass(frozen=True)
class ConformanceResult:
    """The result of checking a constraint against a Probe -- ``holds`` + the LOCATED violations (empty if holds)."""
    holds: bool
    violations: Tuple[Violation, ...] = ()

    @staticmethod
    def ok() -> 'ConformanceResult':
        return ConformanceResult(holds=True, violations=())

    @staticmethod
    def fail(*violations: Violation) -> 'ConformanceResult':
        if not violations:
            raise ValueError('ConformanceResult.fail requires at least one located violation (fail loud)')
        return ConformanceResult(holds=False, violations=tuple(violations))

    def describe(self) -> str:
        if self.holds:
            return 'CONFORMS'
        return '; '.join(v.describe() for v in self.violations)


# the locus axes (NAMED -- a violation locates itself on one of these; no bare strings at a build site).
LOCUS_REGION = 'region'
LOCUS_EVENT = 'event'
LOCUS_SLOT = 'slot'
LOCUS_MODE = 'mode'
LOCUS_INPUT = 'input'
LOCUS_STATUS = 'status'
LOCUS_TRANSCRIPT = 'transcript'
LOCUS_SEQ = 'seq'
LOCUS_HIGHLIGHT = 'highlight'
LOCUS_COMPOSITE = 'composite'


# ===== the CONSTRAINT base + the registry ==================================================================

@dataclass(frozen=True)
class Constraint:
    """A predicate over a Probe -- ``.check(probe) -> ConformanceResult``. The atom the flow asserts.

    ``label`` is the human form (used in violations + traces). ``predicate`` does the actual check and returns a
    ConformanceResult (so it can LOCATE its own violation). Constraints are immutable + composable; combinators
    wrap child constraints. A Constraint never touches a live driver -- it reads only the captured Probe.
    """
    label: str
    predicate: Callable[[Probe], ConformanceResult]

    def check(self, probe: Probe) -> ConformanceResult:
        return self.predicate(probe)

    def __and__(self, other: 'Constraint') -> 'Constraint':
        return all_of(self, other)

    def __or__(self, other: 'Constraint') -> 'Constraint':
        return any_of(self, other)

    def __invert__(self) -> 'Constraint':
        return not_(self)


# the builder registry: name -> a callable building a Constraint from parsed args. Open/closed.
ConstraintBuilder = Callable[..., Constraint]
_BUILDERS: Dict[str, ConstraintBuilder] = {}


def register_constraint(name: str, builder: ConstraintBuilder) -> None:
    """Register a NAMED constraint builder. Fail LOUD on a duplicate name (no silent clobber of a constraint)."""
    if name in _BUILDERS:
        raise ValueError(f'constraint builder {name!r} already registered')
    _BUILDERS[name] = builder


def constraint_builder(name: str) -> ConstraintBuilder:
    """The registered builder for ``name`` -- fail LOUD on unknown (a spec naming an unknown constraint is a fault)."""
    if name not in _BUILDERS:
        raise KeyError(f'unknown constraint {name!r} (known: {sorted(_BUILDERS)})')
    return _BUILDERS[name]


def known_constraints() -> List[str]:
    return sorted(_BUILDERS)


# ===== the NAMED constraint builders =======================================================================

def region_contains(name: str, text: str) -> Constraint:
    """The painted region ``name`` CONTAINS ``text`` somewhere in its lines (substring over the joined region)."""
    def _check(probe: Probe) -> ConformanceResult:
        observed = probe.region_text(name)
        if text in observed:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'region_contains({name!r}, {text!r})', locus=LOCUS_REGION, target=name,
            expected=f'contains {text!r}', observed=observed))
    return Constraint(label=f'region_contains({name!r}, {text!r})', predicate=_check)


def region_line(name: str, row: int, text: str) -> Constraint:
    """The painted region ``name`` has EXACTLY ``text`` at line index ``row`` (0-based, after clipping)."""
    def _check(probe: Probe) -> ConformanceResult:
        lines = probe.regions.get(name, [])
        observed = lines[row] if 0 <= row < len(lines) else ''
        if observed == text:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'region_line({name!r}, {row}, {text!r})', locus=LOCUS_REGION, target=f'{name}[{row}]',
            expected=text, observed=observed))
    return Constraint(label=f'region_line({name!r}, {row}, {text!r})', predicate=_check)


def status_is(text: str) -> Constraint:
    """The ephemeral status ticker shows EXACTLY ``text`` right now."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.status_line == text:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'status_is({text!r})', locus=LOCUS_STATUS, target='status_line',
            expected=text, observed=probe.status_line))
    return Constraint(label=f'status_is({text!r})', predicate=_check)


def status_blank() -> Constraint:
    """The ephemeral status line is BLANK (the TTL elapsed / nothing live to show)."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.status_line == '':
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint='status_blank()', locus=LOCUS_STATUS, target='status_line',
            expected='(blank)', observed=probe.status_line))
    return Constraint(label='status_blank()', predicate=_check)


def status_contains(text: str) -> Constraint:
    """The ephemeral status line CONTAINS ``text`` (substring -- handy when the status carries dynamic seq/ids)."""
    def _check(probe: Probe) -> ConformanceResult:
        if text in probe.status_line:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'status_contains({text!r})', locus=LOCUS_STATUS, target='status_line',
            expected=f'contains {text!r}', observed=probe.status_line))
    return Constraint(label=f'status_contains({text!r})', predicate=_check)


def input_is(text: str) -> Constraint:
    """The input + hints line shows EXACTLY ``text`` (use the rendered form, e.g. ``' > foo'``)."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.input_line == text:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'input_is({text!r})', locus=LOCUS_INPUT, target='input_line',
            expected=text, observed=probe.input_line))
    return Constraint(label=f'input_is({text!r})', predicate=_check)


def input_contains(text: str) -> Constraint:
    """The input line CONTAINS ``text`` (substring -- tolerant of the ``' > '`` prompt prefix)."""
    def _check(probe: Probe) -> ConformanceResult:
        if text in probe.input_line:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'input_contains({text!r})', locus=LOCUS_INPUT, target='input_line',
            expected=f'contains {text!r}', observed=probe.input_line))
    return Constraint(label=f'input_contains({text!r})', predicate=_check)


def mode_is(ui: str) -> Constraint:
    """The modal UI state is ``ui`` (NORMAL / PALETTE / CONFIG). Fail loud on an unknown mode name in the spec."""
    if ui not in UI_MODES:
        raise ValueError(f'mode_is: unknown ui mode {ui!r} (known: {UI_MODES})')

    def _check(probe: Probe) -> ConformanceResult:
        if probe.mode_ui == ui:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'mode_is({ui!r})', locus=LOCUS_MODE, target='mode_ui',
            expected=ui, observed=probe.mode_ui))
    return Constraint(label=f'mode_is({ui!r})', predicate=_check)


def highlighted(region: str) -> Constraint:
    """The screen AREA ``region`` is highlighted (selected) right now (the config editor's targeted area)."""
    def _check(probe: Probe) -> ConformanceResult:
        if region in probe.highlight_regions:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'highlighted({region!r})', locus=LOCUS_HIGHLIGHT, target=region,
            expected=f'{region} highlighted', observed=f'highlighted={sorted(probe.highlight_regions)}'))
    return Constraint(label=f'highlighted({region!r})', predicate=_check)


def cell_highlighted(region: str) -> Constraint:
    """A single FIELD/cell within ``region`` is highlighted (a column SPAN), not the whole region/line.

    The config caret on a SLOT highlights JUST that slot's piece -- this asserts a cell span is present for the
    region (the operator's steer: highlight the piece, not the whole line). Use ``highlighted`` for a whole-area.
    """
    def _check(probe: Probe) -> ConformanceResult:
        span = probe.highlight_cells.get(region)          # (row, start, end)
        if span is not None and span[2] > span[1]:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'cell_highlighted({region!r})', locus=LOCUS_HIGHLIGHT, target=region,
            expected=f'a cell span within {region}', observed=f'cells={dict(probe.highlight_cells)}'))
    return Constraint(label=f'cell_highlighted({region!r})', predicate=_check)


def event_emitted(type_name: str) -> Constraint:
    """AT LEAST ONE event of the NAMED type was emitted (since the last clear). ``type_name`` is e.g. 'TurnRecorded'."""
    if type_name not in EVENT_BY_NAME:
        raise ValueError(f'event_emitted: unknown event type {type_name!r} (known: {sorted(EVENT_BY_NAME)})')

    def _check(probe: Probe) -> ConformanceResult:
        count = probe.event_counts.get(type_name, 0)
        if count >= 1:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'event_emitted({type_name!r})', locus=LOCUS_EVENT, target=type_name,
            expected='>= 1 emitted', observed=f'{count} emitted'))
    return Constraint(label=f'event_emitted({type_name!r})', predicate=_check)


def event_count(type_name: str, n: int) -> Constraint:
    """EXACTLY ``n`` events of the NAMED type were emitted (the one-turn law uses ``event_count('TurnRecorded',1)``)."""
    if type_name not in EVENT_BY_NAME:
        raise ValueError(f'event_count: unknown event type {type_name!r} (known: {sorted(EVENT_BY_NAME)})')

    def _check(probe: Probe) -> ConformanceResult:
        count = probe.event_counts.get(type_name, 0)
        if count == n:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'event_count({type_name!r}, {n})', locus=LOCUS_EVENT, target=type_name,
            expected=f'exactly {n}', observed=str(count)))
    return Constraint(label=f'event_count({type_name!r}, {n})', predicate=_check)


def slot_bound(group: str, index: int, alias: str) -> Constraint:
    """Config slot ``group[index]`` is bound to field ``alias`` (the SlotBound result observed in config state)."""
    def _check(probe: Probe) -> ConformanceResult:
        aliases = probe.slots.get(group, [])
        observed = aliases[index] if 0 <= index < len(aliases) else '(unbound)'
        if observed == alias:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'slot_bound({group!r}, {index}, {alias!r})', locus=LOCUS_SLOT,
            target=f'{group}[{index}]', expected=alias, observed=observed))
    return Constraint(label=f'slot_bound({group!r}, {index}, {alias!r})', predicate=_check)


def transcript_len(n: int) -> Constraint:
    """The transcript holds EXACTLY ``n`` recorded turns (the one-turn law asserts ``transcript_len(1)``)."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.transcript_len == n:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'transcript_len({n})', locus=LOCUS_TRANSCRIPT, target='transcript',
            expected=str(n), observed=str(probe.transcript_len)))
    return Constraint(label=f'transcript_len({n})', predicate=_check)


def seq_is(n: int) -> Constraint:
    """The session seq (as the app sees it) is EXACTLY ``n`` (a failed turn must NOT advance it -- assert it stays)."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.seq == n:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'seq_is({n})', locus=LOCUS_SEQ, target='seq',
            expected=str(n), observed=str(probe.seq)))
    return Constraint(label=f'seq_is({n})', predicate=_check)


def no_ellipsis(region: str) -> Constraint:
    """The painted region ``region`` shows NO trailing-ellipsis truncation (``...``) -- the no-ellipsis wrap law.

    Long content lines must WRAP to full text, never get clipped with ``...`` off the edge. This asserts the
    region's painted lines contain no ``...`` run (the overflow marker the old clip produced).
    """
    def _check(probe: Probe) -> ConformanceResult:
        observed = probe.region_text(region)
        if '...' not in observed:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'no_ellipsis({region!r})', locus=LOCUS_REGION, target=region,
            expected='no ... truncation (lines wrap to full text)', observed=observed))
    return Constraint(label=f'no_ellipsis({region!r})', predicate=_check)


def caret_present(region: str) -> Constraint:
    """The content-traversal CARET (the focus marker) is present in region ``region`` -- the wrap-aware line cursor."""
    from glyfi.ui import theme

    def _check(probe: Probe) -> ConformanceResult:
        observed = probe.region_text(region)
        if theme.FOCUS_MARKER in observed:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'caret_present({region!r})', locus=LOCUS_REGION, target=region,
            expected=f'contains the caret marker {theme.FOCUS_MARKER!r}', observed=observed))
    return Constraint(label=f'caret_present({region!r})', predicate=_check)


def selected_is(n: int) -> Constraint:
    """The selected transcript index is ``n`` (review-highlight cursor)."""
    def _check(probe: Probe) -> ConformanceResult:
        if probe.selected == n:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=f'selected_is({n})', locus=LOCUS_TRANSCRIPT, target='selected',
            expected=str(n), observed=str(probe.selected)))
    return Constraint(label=f'selected_is({n})', predicate=_check)


# ===== combinators (compose constraints; the violation locus is COMPOSITE) =================================

def all_of(*constraints: Constraint) -> Constraint:
    """Conjunction -- holds iff EVERY child holds; on failure carries the LOCATED violations of all failed children."""
    if not constraints:
        raise ValueError('all_of requires at least one constraint (fail loud)')
    label = 'all_of(' + ', '.join(c.label for c in constraints) + ')'

    def _check(probe: Probe) -> ConformanceResult:
        violations: List[Violation] = []
        for c in constraints:
            r = c.check(probe)
            if not r.holds:
                violations.extend(r.violations)
        if not violations:
            return ConformanceResult.ok()
        return ConformanceResult.fail(*violations)
    return Constraint(label=label, predicate=_check)


def any_of(*constraints: Constraint) -> Constraint:
    """Disjunction -- holds iff ANY child holds; on failure carries every child's violation (none satisfied)."""
    if not constraints:
        raise ValueError('any_of requires at least one constraint (fail loud)')
    label = 'any_of(' + ', '.join(c.label for c in constraints) + ')'

    def _check(probe: Probe) -> ConformanceResult:
        violations: List[Violation] = []
        for c in constraints:
            r = c.check(probe)
            if r.holds:
                return ConformanceResult.ok()
            violations.extend(r.violations)
        return ConformanceResult.fail(Violation(
            constraint=label, locus=LOCUS_COMPOSITE, target='any_of',
            expected='at least one child holds',
            observed='; '.join(v.describe() for v in violations)))
    return Constraint(label=label, predicate=_check)


def not_(constraint: Constraint) -> Constraint:
    """Negation -- holds iff the child does NOT; on failure locates that the child unexpectedly held."""
    label = f'not_({constraint.label})'

    def _check(probe: Probe) -> ConformanceResult:
        r = constraint.check(probe)
        if not r.holds:
            return ConformanceResult.ok()
        return ConformanceResult.fail(Violation(
            constraint=label, locus=LOCUS_COMPOSITE, target='not_',
            expected=f'{constraint.label} does NOT hold', observed='it held'))
    return Constraint(label=label, predicate=_check)


def _register_builtins() -> None:
    """Wire the built-in constraint builders into the registry (the terse parser dispatches on these names)."""
    register_constraint('region_contains', region_contains)
    register_constraint('region_line', region_line)
    register_constraint('status_is', status_is)
    register_constraint('status_blank', status_blank)
    register_constraint('status_contains', status_contains)
    register_constraint('input_is', input_is)
    register_constraint('input_contains', input_contains)
    register_constraint('mode_is', mode_is)
    register_constraint('highlighted', highlighted)
    register_constraint('cell_highlighted', cell_highlighted)
    register_constraint('event_emitted', event_emitted)
    register_constraint('event_count', event_count)
    register_constraint('slot_bound', slot_bound)
    register_constraint('transcript_len', transcript_len)
    register_constraint('seq_is', seq_is)
    register_constraint('selected_is', selected_is)
    register_constraint('no_ellipsis', no_ellipsis)
    register_constraint('caret_present', caret_present)


_register_builtins()


# ===== the terse STRING spec parser (small, fail-loud) =====================================================
# Grammar (small + flat; combinators are infix; no precedence beyond left-to-right within one operator class):
#   spec    := disjunct
#   disjunct:= conjunct ('|' conjunct)*           -- '|' is any_of
#   conjunct:= atom ('&' atom)*                   -- '&' is all_of
#   atom    := '!' atom                           -- '!' is not_
#            | '(' disjunct ')'
#            | sugar                              -- 'mode==CONFIG'  /  'highlighted(state)'  /  'seq==3'
#   sugar   := KEY '==' VALUE                     -- KEY in {mode, status, input, seq, transcript}
#            | NAME '(' ARG (',' ARG)* ')'        -- a registered builder; ARG is an int or a (quoted/bare) string
#            | NAME                               -- a zero-arg registered builder (e.g. status_blank)
SPEC_AND = '&'
SPEC_OR = '|'
SPEC_NOT = '!'
SPEC_EQ = '=='
# the ``key==value`` sugar maps a terse key to a registered builder taking the value as its single argument.
_EQ_SUGAR: Dict[str, str] = {
    'mode': 'mode_is',
    'status': 'status_is',
    'input': 'input_is',
    'seq': 'seq_is',
    'transcript': 'transcript_len',
    'selected': 'selected_is',
}
# which builders take INT args at which positions (so the parser coerces; everything else is a string arg).
_INT_ARG_BUILDERS: Dict[str, Tuple[int, ...]] = {
    'seq_is': (0,),
    'transcript_len': (0,),
    'selected_is': (0,),
    'event_count': (1,),
    'region_line': (1,),
    'slot_bound': (1,),
}


class SpecSyntaxError(ValueError):
    """A terse-spec PARSE fault -- fail LOUD with the offending fragment (never a silent always-true constraint)."""


def parse_constraint(spec: str) -> Constraint:
    """Parse a terse spec string into a Constraint. Fail LOUD (``SpecSyntaxError``) on any malformed fragment."""
    parser = _SpecParser(spec)
    constraint = parser.parse_disjunct()
    parser.expect_end()
    return constraint


class _SpecParser:
    """A tiny recursive-descent parser over the terse spec grammar. Stateful cursor over ``text``; fail-loud."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.n = len(text)

    # ---- char-level helpers --------------------------------------------------------------------------------
    def _skip_ws(self) -> None:
        while self.pos < self.n and self.text[self.pos].isspace():
            self.pos += 1

    def _peek(self) -> str:
        self._skip_ws()
        return self.text[self.pos] if self.pos < self.n else ''

    def expect_end(self) -> None:
        self._skip_ws()
        if self.pos != self.n:
            raise SpecSyntaxError(f'trailing input at {self.pos}: {self.text[self.pos:]!r} (full spec {self.text!r})')

    # ---- grammar -------------------------------------------------------------------------------------------
    def parse_disjunct(self) -> Constraint:
        parts = [self.parse_conjunct()]
        while self._peek() == SPEC_OR:
            self.pos = self.text.index(SPEC_OR, self.pos) + 1
            parts.append(self.parse_conjunct())
        return parts[0] if len(parts) == 1 else any_of(*parts)

    def parse_conjunct(self) -> Constraint:
        parts = [self.parse_atom()]
        while self._peek() == SPEC_AND:
            self.pos = self.text.index(SPEC_AND, self.pos) + 1
            parts.append(self.parse_atom())
        return parts[0] if len(parts) == 1 else all_of(*parts)

    def parse_atom(self) -> Constraint:
        ch = self._peek()
        if ch == SPEC_NOT:
            self.pos = self.text.index(SPEC_NOT, self.pos) + 1
            return not_(self.parse_atom())
        if ch == '(':
            self.pos = self.text.index('(', self.pos) + 1
            inner = self.parse_disjunct()
            if self._peek() != ')':
                raise SpecSyntaxError(f"expected ')' at {self.pos} in {self.text!r}")
            self.pos = self.text.index(')', self.pos) + 1
            return inner
        return self._parse_sugar()

    def _parse_sugar(self) -> Constraint:
        ident = self._read_ident()
        if not ident:
            raise SpecSyntaxError(f'expected a constraint at {self.pos} in {self.text!r}')
        # key==value sugar
        self._skip_ws()
        if self.text[self.pos:self.pos + len(SPEC_EQ)] == SPEC_EQ:
            self.pos += len(SPEC_EQ)
            value = self._read_value()
            if ident not in _EQ_SUGAR:
                raise SpecSyntaxError(f'unknown sugar key {ident!r} (known: {sorted(_EQ_SUGAR)}) in {self.text!r}')
            builder_name = _EQ_SUGAR[ident]
            return self._build(builder_name, [value])
        # name(args) or bare name
        if self._peek() == '(':
            self.pos = self.text.index('(', self.pos) + 1
            args = self._read_args()
            return self._build(ident, args)
        return self._build(ident, [])

    def _build(self, name: str, raw_args: List[str]) -> Constraint:
        builder = constraint_builder(name)          # fail loud on unknown
        int_positions = _INT_ARG_BUILDERS.get(name, ())
        coerced: List[object] = []
        for i, arg in enumerate(raw_args):
            if i in int_positions:
                try:
                    coerced.append(int(arg))
                except ValueError as exc:
                    raise SpecSyntaxError(f'{name}: arg {i} must be an int, got {arg!r}') from exc
            else:
                coerced.append(arg)
        return builder(*coerced)

    # ---- token readers -------------------------------------------------------------------------------------
    def _read_ident(self) -> str:
        self._skip_ws()
        start = self.pos
        while self.pos < self.n and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
            self.pos += 1
        return self.text[start:self.pos]

    def _read_value(self) -> str:
        """A bare or quoted value for ``key==value`` -- reads up to a combinator / paren / end."""
        self._skip_ws()
        if self.pos < self.n and self.text[self.pos] in ('"', "'"):
            return self._read_quoted()
        start = self.pos
        while self.pos < self.n and self.text[self.pos] not in (SPEC_AND, SPEC_OR, ')'):
            self.pos += 1
        return self.text[start:self.pos].strip()

    def _read_quoted(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        start = self.pos
        while self.pos < self.n and self.text[self.pos] != quote:
            self.pos += 1
        if self.pos >= self.n:
            raise SpecSyntaxError(f'unterminated string in {self.text!r}')
        value = self.text[start:self.pos]
        self.pos += 1
        return value

    def _read_args(self) -> List[str]:
        """Read ``arg, arg, ...)`` -- each arg a quoted string or a bare token; consume the closing paren."""
        args: List[str] = []
        if self._peek() == ')':
            self.pos = self.text.index(')', self.pos) + 1
            return args
        while True:
            self._skip_ws()
            if self.pos < self.n and self.text[self.pos] in ('"', "'"):
                args.append(self._read_quoted())
            else:
                start = self.pos
                while self.pos < self.n and self.text[self.pos] not in (',', ')'):
                    self.pos += 1
                args.append(self.text[start:self.pos].strip())
            ch = self._peek()
            if ch == ',':
                self.pos = self.text.index(',', self.pos) + 1
                continue
            if ch == ')':
                self.pos = self.text.index(')', self.pos) + 1
                return args
            raise SpecSyntaxError(f"expected ',' or ')' at {self.pos} in {self.text!r}")
