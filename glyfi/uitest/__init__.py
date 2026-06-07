"""uitest -- a CONSTRAINT-DRIVEN, EVENT-BOUND TUI test-DRIVING mini-framework (Playwright, but constraint-based).

Interaction flows are expressed as a CONSTRAINT spec (with delays / wait_until / fixtures / mocks) that drive the
headless MVVM app autonomously, plus BDD specs that demonstrate it and drive downstream TUI development. It BINDS
to the already-event-driven, headless-drivable MVVM (``glyfi.ui`` -- the ``AppDriver`` page seam, the typed
``EventBus`` of named transitions, the ``VirtualClock``); it does NOT rebuild those.

The layers (each its own module, SOLID -- a registry per extension axis):
  * ``constraints`` -- the Probe (observable surface) + Constraint predicates returning oriented, LOCATED
    conformance results; a declarative builder API + a terse string-spec parser; ``register_constraint``.
  * ``actions``     -- interaction VERBS (Press/Type/Invoke/Submit/Tab/Tick/Delay/WaitUntil/Expect/...), one
    class per verb; all timing on the VirtualClock (no wall-clock); ``register_action``.
  * ``fixtures``    -- the ``MockTransport`` (scripted, server-free) + composable fixtures (fresh_app, scripted_
    server, seeded_transcript, ...) building a ready ``RunContext``; ``register_fixture``.
  * ``flow``        -- ``Flow(name).given(...).when(...).then(...)`` -- drives the app, records a trace, checks
    conformance, fails loud with the located violation + trace.
  * ``bdd``         -- a Gherkin-ish ``Feature``/``Scenario`` over flows + a readable report; ``register_phrase``.
  * ``runtime``     -- the scope binding to the MVVM event-driven bindings + the registry snapshot.

This package imports ``glyfi.ui.*`` (+ the transport/stepper PORTS it mocks) + stdlib ONLY.
"""
from glyfi.uitest.constraints import (
    Probe, Constraint, ConformanceResult, Violation,
    region_contains, region_line, status_is, status_blank, status_contains,
    input_is, input_contains, mode_is, highlighted, cell_highlighted, event_emitted, event_count,
    slot_bound, transcript_len, seq_is, selected_is, no_ellipsis, caret_present,
    all_of, any_of, not_,
    parse_constraint, register_constraint, known_constraints, SpecSyntaxError,
)
from glyfi.uitest.actions import (
    Step, Press, Type, Invoke, Submit, Tab, Tick, Delay, WaitUntil, Expect, ClearEvents, Resize,
    register_action, known_actions, ConstraintError, WaitTimeout,
)
from glyfi.uitest.context import RunContext, TraceEntry
from glyfi.uitest.fixtures import (
    MockTransport, ScriptedFault, build_mock_context, Fixture,
    fresh_app, with_subjects, scripted_server, seeded_transcript, at_size, with_prompt_entry,
    register_fixture, known_fixtures,
)
from glyfi.uitest.flow import Flow, FlowResult, FlowError
from glyfi.uitest.bdd import (
    Feature, Scenario, FeatureReport, Phrase, register_phrase,
)
from glyfi.uitest.runtime import registries, new_context, FrameworkRegistries, OBSERVED_EVENTS

__all__ = [
    # constraints
    'Probe', 'Constraint', 'ConformanceResult', 'Violation',
    'region_contains', 'region_line', 'status_is', 'status_blank', 'status_contains',
    'input_is', 'input_contains', 'mode_is', 'highlighted', 'cell_highlighted', 'event_emitted', 'event_count',
    'slot_bound', 'transcript_len', 'seq_is', 'selected_is', 'no_ellipsis', 'caret_present',
    'all_of', 'any_of', 'not_',
    'parse_constraint', 'register_constraint', 'known_constraints', 'SpecSyntaxError',
    # actions
    'Step', 'Press', 'Type', 'Invoke', 'Submit', 'Tab', 'Tick', 'Delay', 'WaitUntil', 'Expect',
    'ClearEvents', 'Resize', 'register_action', 'known_actions', 'ConstraintError', 'WaitTimeout',
    # context
    'RunContext', 'TraceEntry',
    # fixtures
    'MockTransport', 'ScriptedFault', 'build_mock_context', 'Fixture',
    'fresh_app', 'with_subjects', 'scripted_server', 'seeded_transcript', 'at_size', 'with_prompt_entry',
    'register_fixture', 'known_fixtures',
    # flow
    'Flow', 'FlowResult', 'FlowError',
    # bdd
    'Feature', 'Scenario', 'FeatureReport', 'Phrase', 'register_phrase',
    # runtime
    'registries', 'new_context', 'FrameworkRegistries', 'OBSERVED_EVENTS',
]
