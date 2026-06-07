"""plugins.commands -- the COMMAND model + the args->handler PIPELINE (commands stop being arg-less).

This is the spine a slash command flows through once it carries ARGS. A command is no longer a bare
``(name, description, action(vm))`` -- it is a ``CommandSpec`` with an ARG SCHEMA + a HANDLER. The operator's
raw input (``/echo "buy milk"``) is TOKENIZED into structured args and piped to the handler through an injected
``CommandContext`` (the SAME injected-callback pattern the WidgetHost uses -- the handler never imports the
ViewModel; open/closed, no back-import). The handler returns a ``CommandResult`` (lines to push, a status, a
widget to open, events to emit) which a separate APPLIER applies to the app.

SOLID -- the pipeline is three single-responsibility pieces (a fault in one is LOCATED to it):
  * ``ArgTokenizer``  -- raw text -> a token list (quoted strings, ``--flags``/``--key=value``, bare words).
  * ``CommandDispatcher`` -- a parsed ``CommandInvocation`` -> validate against the schema -> call the handler.
  * ``ResultApplier``  -- a ``CommandResult`` -> the app effects (via the injected ``CommandContext`` caps).
``CommandPipeline`` wires the three: ``run(raw, ctx) -> CommandResult`` (parse -> dispatch -> apply).

FAIL LOUD (located): an unknown command, too few/too many args, a bad flag, or a handler fault each raise a
``CommandError`` carrying WHERE it failed (the command name + the offending fragment) -- never a silent no-op.

Self-contained: stdlib + this package's command/context typing only. NO curses, NO ViewModel import (caps are
injected). The events a result carries are opaque objects (duck-typed) so this module stays decoupled.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# ---- NAMED tokenizer literals (no bare quote/flag chars at a scan site) ------------------------------------
FLAG_PREFIX = '--'              # a flag token starts with this (``--all`` / ``--limit=10``)
FLAG_KV_SEP = '='               # a flag may carry a value inline (``--key=value``)
QUOTE_CHARS = ('"', "'")        # a quoted run preserves spaces inside it
ESCAPE_CHAR = '\\'              # inside a quote, ``\"`` is a literal quote, ``\\`` a literal backslash

# ---- NAMED arg-arity sentinel (a positional schema slot that soaks up the REST as one trailing value) ------
ARITY_REST = '*'                # the LAST positional slot may be REST -- collects the remaining tokens joined


class CommandError(Exception):
    """A fail-loud command-pipeline fault -- carries WHERE it failed (command + located fragment).

    ``where`` is the locus (the command name, or ``'<tokenize>'`` for a tokenizer fault) and ``detail`` the
    oriented description (what was expected vs what was seen). A reader sees exactly which command + fragment
    broke -- never a bare ``ValueError`` with no orientation.
    """

    def __init__(self, where: str, detail: str):
        super().__init__(f'[{where}] {detail}')
        self.where = where
        self.detail = detail


# ===== the ARG SCHEMA (what a command accepts) =============================================================

@dataclass(frozen=True)
class ArgSpec:
    """ONE positional arg slot -- a NAMED slot, whether it is required, and an optional REST arity.

    ``name`` labels the slot (used in a located error). ``required`` slots must be present (fail loud if not).
    ``rest`` marks the LAST slot as soaking up every remaining token into one joined value (e.g. a free-text
    ``<text>`` after ``/echo``). A schema validates a tokenized arg list into a positional + flags structure.
    """
    name: str
    required: bool = True
    rest: bool = False


@dataclass(frozen=True)
class ArgSchema:
    """A command's full arg contract -- ordered positional ``ArgSpec``s + the set of allowed flag names.

    ``positionals`` are matched left-to-right against the tokenized positional args; a trailing ``rest`` slot
    collects the remainder. ``flags`` is the set of accepted ``--flag`` / ``--key=value`` names (an unknown
    flag fails loud). An EMPTY schema (no positionals, no flags) is the arg-LESS case -- back-compat preserved.
    """
    positionals: Tuple[ArgSpec, ...] = ()
    flags: Tuple[str, ...] = ()

    def __post_init__(self):
        # a REST slot, if present, MUST be the last positional (otherwise the split is ambiguous) -- fail loud.
        for i, spec in enumerate(self.positionals):
            if spec.rest and i != len(self.positionals) - 1:
                raise ValueError(f'ArgSchema: rest slot {spec.name!r} must be LAST, not at index {i}')
            # a required slot may not follow an optional one (an optional gap makes positional binding ambiguous).
            if spec.required and i > 0 and not self.positionals[i - 1].required:
                raise ValueError(f'ArgSchema: required slot {spec.name!r} follows an optional slot')

    @property
    def has_rest(self) -> bool:
        return bool(self.positionals) and self.positionals[-1].rest

    @property
    def min_positionals(self) -> int:
        return sum(1 for s in self.positionals if s.required)


# ===== the parsed INVOCATION (a command resolved + bound to args) =========================================

@dataclass(frozen=True)
class CommandInvocation:
    """A command resolved by name + its STRUCTURED, schema-validated args -- the unit handed to a handler.

    ``positionals`` maps each positional ``ArgSpec.name`` -> its bound value (a rest slot holds the joined
    remainder). ``flags`` maps each PRESENT flag name -> its value (``True`` for a bare ``--flag``, the string
    for ``--key=value``). ``raw_tokens`` keeps the original token list for a handler that wants it.
    """
    name: str
    positionals: Dict[str, str] = field(default_factory=dict)
    flags: Dict[str, object] = field(default_factory=dict)
    raw_tokens: Tuple[str, ...] = ()

    def arg(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """The bound positional value for ``name`` (or ``default`` if it was an absent optional slot)."""
        return self.positionals.get(name, default)

    def flag(self, name: str, default: object = None) -> object:
        """The flag value for ``name`` (``True`` if it was a bare ``--flag``), or ``default`` if absent."""
        return self.flags.get(name, default)


# ===== the COMMAND RESULT (what a handler asks the app to do) ==============================================

@dataclass(frozen=True)
class CommandResult:
    """The OUTCOME a handler returns -- a declarative effect bundle the applier applies through the injected ctx.

    A handler does NOT touch the app directly; it RETURNS what it wants done and the ``ResultApplier`` performs
    it via the scoped ``CommandContext`` caps (open/closed -- the handler is ViewModel-blind):
      * ``lines``       -- push these display lines into the content view (e.g. ``/echo`` echoes its text);
      * ``status``      -- push this ephemeral status onto the ticker;
      * ``open_widget`` -- open this registered widget by name (the command->widget bridge);
      * ``events``      -- emit these typed events onto the shared bus.
    An EMPTY result is a valid no-effect outcome (a handler may choose to do nothing).
    """
    lines: Tuple[str, ...] = ()
    status: Optional[str] = None
    open_widget: Optional[str] = None
    events: Tuple[object, ...] = ()

    @staticmethod
    def of_status(text: str) -> 'CommandResult':
        return CommandResult(status=text)

    @staticmethod
    def of_lines(lines: List[str], *, status: Optional[str] = None) -> 'CommandResult':
        return CommandResult(lines=tuple(lines), status=status)


# ===== the scoped COMMAND CONTEXT (the handler's + applier's capability surface) ===========================

@dataclass(frozen=True)
class CommandContext:
    """The SCOPED caps a command handler + the applier touch -- the ONLY way the pipeline reaches the wider app.

    Mirrors ``WidgetContext`` (the same injected-callback pattern): a handler never imports the ViewModel. The
    ViewModel wires these to its own methods (push lines, push status, open a widget, emit). Immutable -- a
    handler can't swap its own caps. A handler MAY read nothing here and just return a ``CommandResult``; the
    caps exist for the applier (and for a handler that wants to act imperatively, e.g. an interactive prompt).
    ``current_offset()`` reads the live content scroll offset + ``scroll_to(offset)`` slides the viewport.
    """
    push_lines: Callable[[List[str]], None]
    push_status: Callable[[str], None]
    open_widget: Callable[[str], None]
    emit: Callable[[object], None]
    # ADDITIVE capability -- READ the current content scroll offset and SLIDE the viewport to one. OPTIONAL
    # (defaults to no-ops) so an existing handler/context that never constructs these caps is unchanged.
    scroll_to: Callable[[int], None] = lambda offset: None
    current_offset: Callable[[], int] = lambda: 0
    # ADDITIVE capability -- CAPTURE the live frame (``capture_frame()``) or one named region
    # (``capture_region(name)``) as already-composed text ROWS. OPTIONAL (defaults to None) so an existing
    # handler/context that never wires capture is unchanged; a handler tests for None and fails loud-soft.
    capture_frame: Optional[Callable[[], List[str]]] = None
    capture_region: Optional[Callable[[str], List[str]]] = None


# the handler signature: a resolved invocation + the scoped caps -> a declarative result.
CommandHandler = Callable[[CommandInvocation, CommandContext], CommandResult]


# ===== the COMMAND SPEC (name + description + arg schema + handler) ========================================

@dataclass(frozen=True)
class CommandSpec:
    """A slash command's full contract -- ``name`` + human ``description`` + an ``ArgSchema`` + a ``CommandHandler``.

    This SUPERSEDES the arg-less ``palette.Command``: a spec carries the arg schema + the handler the pipeline
    dispatches to. An arg-LESS command is just a spec with an empty ``ArgSchema`` (back-compat). The plugin
    loader registers specs into the palette; the pipeline dispatches the operator's raw input to ``handler``.
    """
    name: str
    description: str
    handler: CommandHandler
    arg_schema: ArgSchema = field(default_factory=ArgSchema)


# ===== SRP piece 1: the ARG TOKENIZER =====================================================================

class ArgTokenizer:
    """Raw arg text -> a token list. Honors quoted runs (spaces preserved) + ``--flag`` / ``--key=value`` tokens.

    A small, fail-loud scanner: a quoted run keeps spaces + supports ``\\`` escapes inside; an unterminated quote
    FAILS LOUD (located). Flags are recognized at the TOKEN level (a token starting ``--``); their value split
    (bare vs ``=value``) happens in the dispatcher against the schema. This is purely lexical -- no schema here.
    """

    def tokenize(self, raw: str) -> List[str]:
        """Split ``raw`` into tokens (whitespace-separated, quotes preserved). Fail loud on an unterminated quote."""
        tokens: List[str] = []
        i = 0
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch.isspace():
                i += 1
                continue
            if ch in QUOTE_CHARS:
                token, i = self._read_quoted(raw, i)
                tokens.append(token)
            else:
                token, i = self._read_bare(raw, i)
                tokens.append(token)
        return tokens

    def _read_quoted(self, raw: str, i: int) -> Tuple[str, int]:
        quote = raw[i]
        i += 1
        out: List[str] = []
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch == ESCAPE_CHAR and i + 1 < n and raw[i + 1] in (quote, ESCAPE_CHAR):
                out.append(raw[i + 1])
                i += 2
                continue
            if ch == quote:
                return ''.join(out), i + 1
            out.append(ch)
            i += 1
        raise CommandError('<tokenize>', f'unterminated {quote!r}-quoted string in {raw!r}')

    def _read_bare(self, raw: str, i: int) -> Tuple[str, int]:
        n = len(raw)
        start = i
        while i < n and not raw[i].isspace() and raw[i] not in QUOTE_CHARS:
            i += 1
        return raw[start:i], i


# ===== SRP piece 2: the DISPATCHER (validate against the schema, call the handler) =========================

class CommandDispatcher:
    """A resolved ``CommandSpec`` + tokens -> a validated ``CommandInvocation`` -> the handler's ``CommandResult``.

    Splits tokens into FLAGS (``--name`` / ``--name=value``) and POSITIONALS, validates them against the spec's
    ``ArgSchema`` (arity + allowed flags), binds them into a ``CommandInvocation``, then calls the handler. Every
    failure is a LOCATED ``CommandError`` (the command name + the offending fragment). A handler EXCEPTION is
    re-raised as a located ``CommandError`` (the handler fault is attributed to its command, fail-loud).
    """

    def bind(self, spec: CommandSpec, tokens: List[str]) -> CommandInvocation:
        """Validate ``tokens`` against ``spec.arg_schema`` and bind them into a ``CommandInvocation`` (no call yet)."""
        positionals_in, flags_in = self._split(spec, tokens)
        bound_pos = self._bind_positionals(spec, positionals_in)
        return CommandInvocation(name=spec.name, positionals=bound_pos, flags=flags_in,
                                 raw_tokens=tuple(tokens))

    def dispatch(self, spec: CommandSpec, invocation: CommandInvocation,
                 ctx: CommandContext) -> CommandResult:
        """Call ``spec.handler`` with the bound invocation + caps; a handler fault is a LOCATED CommandError."""
        try:
            result = spec.handler(invocation, ctx)
        except CommandError:
            raise
        except Exception as exc:                       # a handler fault is attributed to its command (fail loud)
            raise CommandError(spec.name, f'handler raised {type(exc).__name__}: {exc}') from exc
        if not isinstance(result, CommandResult):
            raise CommandError(spec.name,
                               f'handler returned {type(result).__name__}, expected a CommandResult')
        return result

    def _split(self, spec: CommandSpec, tokens: List[str]) -> Tuple[List[str], Dict[str, object]]:
        """Partition tokens into positionals + a flags map, validating flag names against the schema (fail loud)."""
        positionals: List[str] = []
        flags: Dict[str, object] = {}
        allowed = set(spec.arg_schema.flags)
        for tok in tokens:
            if tok.startswith(FLAG_PREFIX) and len(tok) > len(FLAG_PREFIX):
                name, value = self._parse_flag(tok)
                if name not in allowed:
                    raise CommandError(spec.name,
                                       f'unknown flag --{name} (allowed: {sorted(allowed)})')
                flags[name] = value
            else:
                positionals.append(tok)
        return positionals, flags

    def _parse_flag(self, tok: str) -> Tuple[str, object]:
        body = tok[len(FLAG_PREFIX):]
        if FLAG_KV_SEP in body:
            name, _, value = body.partition(FLAG_KV_SEP)
            return name, value
        return body, True

    def _bind_positionals(self, spec: CommandSpec, given: List[str]) -> Dict[str, str]:
        """Bind given positional tokens to the schema slots (arity-checked; a rest slot joins the remainder)."""
        schema = spec.arg_schema
        specs = schema.positionals
        if not schema.has_rest and len(given) > len(specs):
            raise CommandError(spec.name,
                               f'too many args: expected at most {len(specs)}, got {len(given)} ({given!r})')
        if len(given) < schema.min_positionals:
            missing = [s.name for s in specs if s.required][len(given):]
            raise CommandError(spec.name,
                               f'missing required arg(s) {missing} (got {given!r})')
        bound: Dict[str, str] = {}
        for idx, slot in enumerate(specs):
            if slot.rest:
                bound[slot.name] = ' '.join(given[idx:])
                break
            if idx < len(given):
                bound[slot.name] = given[idx]
        return bound


# ===== SRP piece 3: the RESULT APPLIER (declarative result -> app effects via caps) ========================

class ResultApplier:
    """Apply a ``CommandResult`` to the app through the scoped ``CommandContext`` caps (open/closed, no VM import).

    The single place a result's declarative effects become app mutations -- so a handler stays pure/return-only.
    Order is NAMED + deterministic: events first (record intent), then content lines, then a widget open, then
    the status (the status reads last so it is the final ephemeral message the operator sees).
    """

    def apply(self, result: CommandResult, ctx: CommandContext) -> None:
        for event in result.events:
            ctx.emit(event)
        if result.lines:
            ctx.push_lines(list(result.lines))
        if result.open_widget is not None:
            ctx.open_widget(result.open_widget)
        if result.status is not None:
            ctx.push_status(result.status)


# ===== the PIPELINE (parse -> dispatch -> apply) ==========================================================

class CommandPipeline:
    """The args->handler PIPELINE: ``run(raw, ctx)`` ties the tokenizer + dispatcher + applier over a spec lookup.

    Constructed over a ``resolve(name) -> Optional[CommandSpec]`` lookup (the palette spec registry, injected so
    the pipeline does not import the registry -- open/closed + testable with a stub). ``parse(raw)`` resolves the
    command name + tokenizes + binds the args into a ``CommandInvocation``; ``run`` then dispatches + applies.
    Fail loud (located) at every stage. The leading palette prefix is stripped if present.
    """

    def __init__(self, resolve: Callable[[str], Optional[CommandSpec]], *,
                 prefix: str = '/', tokenizer: Optional[ArgTokenizer] = None,
                 dispatcher: Optional[CommandDispatcher] = None,
                 applier: Optional[ResultApplier] = None):
        self._resolve = resolve
        self._prefix = prefix
        self._tokenizer = tokenizer or ArgTokenizer()
        self._dispatcher = dispatcher or CommandDispatcher()
        self._applier = applier or ResultApplier()

    def split_name(self, raw: str) -> Tuple[str, str]:
        """Split raw input into ``(name, arg_text)`` -- the first whitespace token is the name, the rest is args."""
        body = raw[len(self._prefix):] if raw.startswith(self._prefix) else raw
        body = body.strip()
        if not body:
            raise CommandError('<parse>', f'no command name in {raw!r}')
        name, _, arg_text = body.partition(' ')
        return name, arg_text.strip()

    def resolve(self, name: str) -> CommandSpec:
        """Resolve a registered ``CommandSpec`` by name -- fail loud (located) on an unknown command."""
        spec = self._resolve(name)
        if spec is None:
            raise CommandError(name, f'unknown command {name!r}')
        return spec

    def parse(self, raw: str) -> Tuple[CommandSpec, CommandInvocation]:
        """Resolve + tokenize + bind -- raw input -> ``(spec, CommandInvocation)``. No handler call yet."""
        name, arg_text = self.split_name(raw)
        spec = self.resolve(name)
        tokens = self._tokenizer.tokenize(arg_text)
        invocation = self._dispatcher.bind(spec, tokens)
        return spec, invocation

    def run(self, raw: str, ctx: CommandContext) -> CommandResult:
        """The full pipe: parse -> dispatch -> apply. Returns the ``CommandResult`` (already applied via ``ctx``)."""
        spec, invocation = self.parse(raw)
        result = self._dispatcher.dispatch(spec, invocation, ctx)
        self._applier.apply(result, ctx)
        return result
