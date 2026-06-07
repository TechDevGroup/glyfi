"""plugins.palette -- the slash-command PALETTE: a NAMED command registry + a PURE filter/nav state machine.

When the operator types ``/`` into the input line the app enters PALETTE mode: the content area overlays a 1D
list of commands (``name`` left, ``description`` right); arrow keys move the selection (the selected row is
highlighted by the View), Enter runs the selected (or exact-name-matched) command, Esc clears the buffer back to
NORMAL.

Two pure pieces, both mechanism-testable with NO curses:
  * the COMMAND REGISTRY -- each command is a NAMED ``Command(name, description, action(vm)->None)``. Built-ins
    cover prompt / clear / config / mode / help / about / quit. Extensible via ``register_command`` (fail loud on
    a duplicate name -- no silent clobber) and ``register_command_spec`` (the args->handler pipeline path).
  * ``PaletteState`` -- the (filter string, selected index) cursor. ``filtered(commands)`` returns the commands
    whose name contains the filter (the leading ``/`` is stripped before matching); ``move_up`` / ``move_down``
    clamp the selection within the filtered list; ``select`` returns the chosen command (exact-name match first,
    else the selected row), or None when the filtered list is empty.

Self-contained: pure stdlib + this package's types; the command actions call ViewModel methods duck-typed.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from glyfi.plugins.commands import CommandSpec

# ---- NAMED command names (no bare strings at a register/dispatch site) -------------------------------------
CMD_PROMPT = 'prompt'
CMD_CLEAR = 'clear'
CMD_CONFIG = 'config'
CMD_MODE = 'mode'
CMD_HELP = 'help'
CMD_ABOUT = 'about'             # opens the reference HELP WIDGET (proves the pluggable widget seam)
CMD_QUIT = 'quit'

# the prefix that ENGAGES the palette (the input buffer starts with this).
PALETTE_PREFIX = '/'

# the registry name of the reference widget the ``about`` command opens (NAMED; no bare string at the register site).
from glyfi.widgets.help_widget import WIDGET_HELP as _HELP_WIDGET_NAME


@dataclass(frozen=True)
class Command:
    """A palette command -- a NAMED ``name`` + a human ``description`` (shown right) + ``action(vm) -> None``."""
    name: str
    description: str
    action: Callable[[object], None]


# the registry: name -> Command. Mutated only via register_command (fail-loud on dup).
_COMMANDS: Dict[str, Command] = {}
# the PARALLEL spec registry: name -> CommandSpec (the args->handler pipeline resolves these). A command may live
# in BOTH (an arg-bearing plugin command) or just ``_COMMANDS`` (an arg-less built-in calling vm methods).
_SPECS: Dict[str, CommandSpec] = {}


def register_command(name: str, description: str, action: Callable[[object], None]) -> None:
    """Register an ARG-LESS palette command (a ``vm``-calling action). Fail LOUD on a duplicate name (no clobber).

    This is the in-code seam for the built-ins (prompt / clear / ...): the action takes the ViewModel and runs a
    zero-arg method. Plugin commands that carry ARGS register a ``CommandSpec`` via ``register_command_spec``.
    """
    if name in _COMMANDS:
        raise ValueError(f'palette command {name!r} already registered')
    _COMMANDS[name] = Command(name=name, description=description, action=action)


def register_command_spec(spec: CommandSpec) -> None:
    """Register a ``CommandSpec`` (name + description + arg schema + handler) the args->handler PIPELINE dispatches.

    Adds the spec to BOTH the spec registry (so the pipeline resolves it by name) and the display registry (so the
    palette lists + filters + selects it). Fail LOUD on a duplicate name in EITHER registry (no silent clobber --
    the loader's cross-source dedup relies on this). The display ``action`` runs the command with NO args (the
    palette's Enter-on-selection path); typed args flow through the pipeline (``palette_run`` reads the buffer).
    """
    if spec.name in _SPECS:
        raise ValueError(f'command spec {spec.name!r} already registered')
    if spec.name in _COMMANDS:
        raise ValueError(f'palette command {spec.name!r} already registered (name collision with a built-in)')
    _SPECS[spec.name] = spec
    # the display action runs the spec via the VM's pipeline with the CURRENT input buffer (so a selection with
    # no typed args still dispatches the handler) -- the VM owns the pipeline wiring (open/closed, no VM import here).
    _COMMANDS[spec.name] = Command(name=spec.name, description=spec.description,
                                   action=lambda vm: vm.run_command_spec(spec.name))


def command_spec(name: str) -> Optional[CommandSpec]:
    """The ``CommandSpec`` registered under ``name`` (for the pipeline's resolver), or None if it is arg-less."""
    return _SPECS.get(name)


# ---- snapshot / restore: a public seam for ISOLATED, repeatable registration -------------------------------
# The command/spec registries are process-global (registration happens once at import + at bootstrap). To run a
# block of registrations and roll back to a known baseline -- embedding several app instances in one process, or
# isolating per-test registrations -- capture the current registry with ``snapshot_registry()``, register freely,
# then ``restore_registry(snapshot)`` to return both dicts to exactly the captured contents.
def snapshot_registry() -> object:
    """Capture the current command + spec registries as an OPAQUE, immutable token (for ``restore_registry``).

    The returned token is a frozen copy of the registry mapping; callers cannot mutate registry internals through
    it. Holds the SAME ``Command`` / ``CommandSpec`` objects (these are themselves immutable specs), so the copy
    is cheap. No behaviour change to the live registries -- this only reads them.
    """
    return (tuple(_COMMANDS.items()), tuple(_SPECS.items()))


def restore_registry(snapshot: object) -> None:
    """Reset the command + spec registries to exactly the contents captured by ``snapshot_registry()``.

    Clears both registries and repopulates them from the token -- any registration made after the snapshot is
    dropped, and anything removed is put back. Idempotent for a given token.
    """
    commands, specs = snapshot  # type: ignore[misc]
    _COMMANDS.clear()
    _COMMANDS.update(commands)
    _SPECS.clear()
    _SPECS.update(specs)


def _register_builtins() -> None:
    """Wire the built-in palette commands. Each action is ONE explicit operator action -- never an auto-loop."""
    register_command(CMD_PROMPT, 'walk exactly one turn (prompts for subject + text)',
                     lambda vm: vm.request_prompt())
    register_command(CMD_CLEAR, 'clear the content view / stick to the newest', lambda vm: vm.clear_content())
    register_command(CMD_CONFIG, 'open the traversable config editor', lambda vm: vm.open_config())
    register_command(CMD_MODE, 'cycle the current mode label', lambda vm: vm.cycle_mode())
    register_command(CMD_HELP, 'push the command list into the content view', lambda vm: vm.push_help())
    register_command(CMD_ABOUT, 'open the help/about WIDGET (the pluggable widget seam)',
                     lambda vm: vm.open_widget(_HELP_WIDGET_NAME))
    register_command(CMD_QUIT, 'quit the app', lambda vm: vm.request_quit())


_register_builtins()


def all_commands() -> List[Command]:
    """Every registered command, in registration order (the palette's full list before filtering)."""
    return list(_COMMANDS.values())


def command(name: str) -> Optional[Command]:
    """The command registered under ``name``, or None."""
    return _COMMANDS.get(name)


def _strip_prefix(text: str) -> str:
    """Drop a single leading palette prefix (``/``) and surrounding whitespace -- the bare filter term."""
    body = text[len(PALETTE_PREFIX):] if text.startswith(PALETTE_PREFIX) else text
    return body.strip()


@dataclass
class PaletteState:
    """The PURE palette cursor -- the current filter buffer + the selected row within the filtered list.

    No curses, no rendering: ``filtered`` computes the visible commands, ``move_up`` / ``move_down`` clamp the
    selection, ``select`` resolves the chosen command. The View reads ``selected`` to highlight a row.
    """
    buffer: str = PALETTE_PREFIX
    selected: int = 0

    @property
    def filter_term(self) -> str:
        return _strip_prefix(self.buffer)

    def filtered(self, commands: List[Command]) -> List[Command]:
        """The commands whose name contains the (prefix-stripped) filter term -- substring, case-insensitive."""
        term = self.filter_term.lower()
        if not term:
            return list(commands)
        return [c for c in commands if term in c.name.lower()]

    def clamp(self, commands: List[Command]) -> None:
        """Keep ``selected`` within the current filtered list (call after the buffer changes)."""
        n = len(self.filtered(commands))
        if n == 0:
            self.selected = 0
        else:
            self.selected = max(0, min(self.selected, n - 1))

    def move_up(self, commands: List[Command]) -> None:
        self.selected = max(0, self.selected - 1)
        self.clamp(commands)

    def move_down(self, commands: List[Command]) -> None:
        self.selected = self.selected + 1
        self.clamp(commands)

    def select(self, commands: List[Command]) -> Optional[Command]:
        """Resolve the chosen command -- an EXACT-name match on the filter term wins; else the selected row."""
        term = self.filter_term
        exact = command(term)
        if exact is not None:
            return exact
        rows = self.filtered(commands)
        if not rows:
            return None
        idx = max(0, min(self.selected, len(rows) - 1))
        return rows[idx]
