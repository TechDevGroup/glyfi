"""plugins.loader -- the PluginLoader: run all enabled sources at bootstrap, register their commands/widgets.

This is the keystone wiring: it runs each enabled ``PluginSource`` in a NAMED PRECEDENCE order and registers the
resulting ``CommandSpec``s + widget factories into the palette/widget REGISTRIES. After ``load_all`` the new
commands are filterable/selectable in the palette + dispatchable through the args->handler pipeline, and the new
widgets are openable by name -- with ZERO edits to any core file.

PRECEDENCE (NAMED, documented): sources run in the order given (the app wires it ``in-code -> filesystem ->
system-api``). The FIRST source to register a name WINS that name; a LATER source re-registering the SAME name
FAILS LOUD by default (no silent clobber -- a name collision across sources is a real conflict the operator must
resolve). Set ``on_conflict=SKIP_LATER`` to instead keep the earlier registration + skip the later (the "earlier
precedence wins, later yields" rule) -- still NAMED, still surfaced (the skipped name is reported).

The loader is the SINGLE registrar (SRP): a source only PRODUCES a ``Registration``; the loader registers. The
registry functions are INJECTED (the palette/widget ``register_*`` + the existing-name probes) so the loader does
not hard-depend on the registries -- open/closed + unit-testable with stub registries.

Self-contained: this package + stdlib only.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from glyfi.plugins.commands import CommandSpec
from glyfi.plugins.sources import PluginSource, Registration

# ---- NAMED conflict policies (no bare string at a dispatch site) ------------------------------------------
FAIL_LOUD = 'fail_loud'                 # a cross-source name collision RAISES (default -- no silent clobber)
SKIP_LATER = 'skip_later'              # earlier precedence wins; the later registration is skipped (+ reported)
CONFLICT_POLICIES = (FAIL_LOUD, SKIP_LATER)


class PluginConflictError(Exception):
    """A fail-loud cross-source registration conflict -- the SAME command/widget name from two sources."""

    def __init__(self, kind: str, name: str, first_source: str, second_source: str):
        super().__init__(f'{kind} {name!r} registered by both {first_source!r} and {second_source!r} '
                         f'(a cross-source name collision -- resolve it or set on_conflict=skip_later)')
        self.kind = kind
        self.name = name


@dataclass(frozen=True)
class LoadReport:
    """The outcome of a load -- what registered + what was skipped (the operator's audit of the plugin bootstrap)."""
    commands: Tuple[str, ...] = field(default_factory=tuple)
    widgets: Tuple[str, ...] = field(default_factory=tuple)
    skipped: Tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> str:
        return (f'plugins loaded -- commands={list(self.commands)} widgets={list(self.widgets)} '
                f'skipped={list(self.skipped)}')


class PluginLoader:
    """Run enabled sources in precedence order; register their commands/widgets into the injected registries.

    Constructed over the registry seams (the palette/widget ``register_*`` + existing-name probes) -- INJECTED so
    the loader is registry-agnostic + testable. ``load_all(sources)`` runs each in order, tracking which names a
    source already claimed so a cross-source collision is caught (per ``on_conflict``). Returns a ``LoadReport``.
    """

    def __init__(self,
                 register_command_spec: Callable[[CommandSpec], None],
                 register_widget: Callable[[str, Callable], None],
                 command_exists: Callable[[str], bool],
                 widget_exists: Callable[[str], bool],
                 *, on_conflict: str = FAIL_LOUD):
        if on_conflict not in CONFLICT_POLICIES:
            raise ValueError(f'unknown on_conflict {on_conflict!r} (known: {CONFLICT_POLICIES})')
        self._register_command_spec = register_command_spec
        self._register_widget = register_widget
        self._command_exists = command_exists
        self._widget_exists = widget_exists
        self._on_conflict = on_conflict

    def load_all(self, sources: List[PluginSource]) -> LoadReport:
        """Run each source in PRECEDENCE order; register its registrations; return a ``LoadReport``. Fail loud."""
        registered_commands: List[str] = []
        registered_widgets: List[str] = []
        skipped: List[str] = []
        origin: dict = {}                  # name -> the source label that first claimed it (for a located conflict)
        for source in sources:
            reg = source.load()            # the source PRODUCES; it never registers (the loader is the registrar)
            self._apply(reg, registered_commands, registered_widgets, skipped, origin)
        return LoadReport(commands=tuple(registered_commands), widgets=tuple(registered_widgets),
                          skipped=tuple(skipped))

    def _apply(self, reg: Registration, reg_cmds: List[str], reg_widgets: List[str],
               skipped: List[str], origin: dict) -> None:
        for spec in reg.commands:
            if self._claimed('command', spec.name, reg.source, origin):
                if self._yield_later('command', spec.name, reg.source, origin, skipped):
                    continue
            self._register_command_spec(spec)
            reg_cmds.append(spec.name)
            origin[('command', spec.name)] = reg.source
        for name, factory in reg.widgets:
            if self._claimed('widget', name, reg.source, origin):
                if self._yield_later('widget', name, reg.source, origin, skipped):
                    continue
            self._register_widget(name, factory)
            reg_widgets.append(name)
            origin[('widget', name)] = reg.source

    def _claimed(self, kind: str, name: str, source: str, origin: dict) -> bool:
        """True if ``name`` is already registered (by an earlier source OR a pre-existing built-in registration)."""
        exists = self._command_exists if kind == 'command' else self._widget_exists
        return ('command' if kind == 'command' else 'widget', name) in origin or exists(name)

    def _yield_later(self, kind: str, name: str, source: str, origin: dict, skipped: List[str]) -> bool:
        """Resolve a collision per the policy -- FAIL_LOUD raises; SKIP_LATER reports + returns True (skip it)."""
        first = origin.get((kind, name), '<pre-registered built-in>')
        if self._on_conflict == SKIP_LATER:
            skipped.append(f'{kind}:{name} (from {source}; kept {first})')
            return True
        raise PluginConflictError(kind, name, first, source)


def build_default_loader(*, on_conflict: str = FAIL_LOUD) -> PluginLoader:
    """A loader wired to the REAL palette/widget registries -- the runtime bootstrap path.

    Wires the injected seams to the live ``palette.register_command_spec`` / ``widgets.register_widget`` + the
    existing-name probes. The app calls this at bootstrap with its source list (in-code -> filesystem -> system-api).
    """
    from glyfi.plugins import palette as palette_mod
    from glyfi.widgets import host as widget_host

    def _command_exists(name: str) -> bool:
        return palette_mod.command(name) is not None

    def _widget_exists(name: str) -> bool:
        return name in widget_host.known_widgets()

    return PluginLoader(
        register_command_spec=palette_mod.register_command_spec,
        register_widget=widget_host.register_widget,
        command_exists=_command_exists,
        widget_exists=_widget_exists,
        on_conflict=on_conflict,
    )
