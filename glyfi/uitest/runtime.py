"""runtime -- the SCOPE BINDING: wire the constraint framework to the MVVM event-driven bindings.

This is the framework's OWN scope binding onto the UI MVVM bindings -- the single place that knows the framework
binds to ``glyfi.ui`` (the headless ``AppDriver`` + the typed ``EventBus`` + the ``VirtualClock``). Everything
else in the package takes those as injected ports; this module names the binding explicitly and exposes the
convenience entry that builds a driven, server-free context.

It also surfaces the framework's REGISTRY snapshot (the open/closed extension points) so a caller / a doc / a
coverage check can enumerate what verbs, constraints, fixtures, and BDD phrasings are wired.

Imports the UI bindings + this package + stdlib only.
"""
from dataclasses import dataclass
from typing import List

# the MVVM bindings this framework's scope binds to (NAMED here -- the single declared coupling point).
from glyfi.ui.driver import AppDriver, build_headless_driver        # the Playwright-page seam
from glyfi.ui.events import EVENT_TYPES                             # the observed MVVM transitions
from glyfi.ui.clock import VirtualClock                            # deterministic timing

from glyfi.uitest import actions, constraints, fixtures
from glyfi.uitest.context import RunContext
from glyfi.uitest.fixtures import MockTransport, build_mock_context


# the NAMED event-type names the constraints observe (the MVVM hook-in points the framework binds to).
OBSERVED_EVENTS = tuple(t.__name__ for t in EVENT_TYPES)


@dataclass(frozen=True)
class FrameworkRegistries:
    """A snapshot of the open/closed extension points -- the registered verbs / constraints / fixtures / events."""
    actions: List[str]
    constraints: List[str]
    fixtures: List[str]
    observed_events: List[str]


def registries() -> FrameworkRegistries:
    """Enumerate the framework's registered extension points (for docs / a coverage check / introspection)."""
    return FrameworkRegistries(
        actions=actions.known_actions(),
        constraints=constraints.known_constraints(),
        fixtures=fixtures.known_fixtures(),
        observed_events=list(OBSERVED_EVENTS),
    )


def new_context(transport: MockTransport = None, **kwargs) -> RunContext:
    """The framework entry -- build a driven, server-FREE ``RunContext`` (driver + virtual clock) over a mock.

    A thin alias over ``fixtures.build_mock_context`` so callers import ONE runtime entry. Pass a configured
    ``MockTransport`` (scripts/faults) or get a default-echoing one.
    """
    return build_mock_context(transport or MockTransport(), **kwargs)
