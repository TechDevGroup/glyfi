"""fixtures -- composable FIXTURES + the MOCK transport: build a ready, server-free headless app to drive.

This is the "mock the hook-in points" layer. A flow runs with NO live server: a ``MockTransport`` implements the
transport PORT (``send`` / ``list_subjects``) and returns SCRIPTED responses, so the whole stack --
``MockTransport -> Stepper -> AppViewModel -> build_headless_driver`` -- runs deterministically in CI.

The scripts are CONSTRAINT-MAPPABLE: a script maps a (subject, mode, text) key to a scripted RESPONSE or a
scripted FAULT (a bad-request ``ProtocolError``), so a flow can spec BOTH the happy path AND the fail-loud path
(the stepper captures the fault into the turn; the seq does NOT advance).

Fixtures are NAMED, composable, open/closed (a registry; ``register_fixture`` adds one without editing the runner).
A fixture is ``setup(spec) -> RunContext`` plus an optional ``teardown(ctx)``; composing several layers their
effects onto one context (e.g. ``fresh_app`` then ``scripted_server`` then ``seeded_transcript``).

Imports the app stack + the transport PORT + this package's context + stdlib only. The server is MOCKED here.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from glyfi.ui.clock import VirtualClock
from glyfi.ui.config_store import UserConfig
from glyfi.ui.driver import build_headless_driver, DEFAULT_DRIVE_WIDTH, DEFAULT_DRIVE_HEIGHT
from glyfi.ui.events import EventBus
from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import AppSettings
from glyfi.ui.ticker import Ticker
from glyfi.ui.viewmodel import AppViewModel
from glyfi.stepper import Stepper
from glyfi.transport import Transport
from glyfi.protocol import TurnRequest, TurnResponse, ProtocolError
from glyfi.uitest.context import RunContext


# ---- NAMED fixture defaults (no magic literals) -----------------------------------------------------------
DEFAULT_SESSION_ID = 'uitest-1'
DEFAULT_MODES = ('chat',)


# ===== the MOCK transport (the server-free hook-in point) ==================================================

@dataclass(frozen=True)
class ScriptedFault:
    """A scripted FAULT -- the transport raises a ``ProtocolError`` (bad request) instead of staging.

    Maps a request key to the server's fail-loud envelope (type + HTTP code). The stepper CAPTURES this into the
    turn (``ok=False``, ``error`` set) and the seq does NOT advance -- so a flow can spec the fail-loud path.
    """
    message: str
    type: str
    code: int


@dataclass
class MockTransport(Transport):
    """A scripted, server-FREE transport behind the ``Transport`` PORT -- deterministic, CI-safe.

    ``script`` maps a (subject, mode, text) key -> a ``TurnResponse`` (or a callable building one from the
    request) OR a ``ScriptedFault``. A ``default`` handles any unscripted request (a generic ``staged:<text>``
    echo with an advanced seq) so a flow needn't script every turn. ``subjects`` is the scripted
    ``list_subjects`` listing. ``sent`` records every request for an exactly-one-turn-per-step assertion.

    SCRIPT KEY: a 3-tuple (subject, mode, text); any element may be the wildcard ``ANY`` to match loosely.
    """
    script: Dict[Tuple, object] = field(default_factory=dict)
    subjects: List[Dict[str, str]] = field(default_factory=list)
    default_enabled: bool = True
    sent: List[TurnRequest] = field(default_factory=list)

    ANY = '*'

    def script_response(self, subject: str, mode: str, text: str, content: str, *,
                        seq_advance: int = 1) -> 'MockTransport':
        """Script a successful staged RESPONSE for a (subject, mode, text) key. Returns self (chainable)."""
        self.script[(subject, mode, text)] = _ResponseSpec(content=content, seq_advance=seq_advance)
        return self

    def script_fault(self, subject: str, mode: str, text: str, *, message: str, type: str, code: int) -> 'MockTransport':
        """Script a fail-loud FAULT (bad request) for a key -- the transport raises ProtocolError."""
        self.script[(subject, mode, text)] = ScriptedFault(message=message, type=type, code=code)
        return self

    def _match(self, subject: str, mode: str, text: str) -> Optional[object]:
        """Resolve the scripted entry for a request, honoring the ANY wildcard (exact key wins over wildcards)."""
        for key in ((subject, mode, text), (subject, mode, self.ANY), (subject, self.ANY, self.ANY),
                    (self.ANY, mode, self.ANY), (self.ANY, self.ANY, self.ANY)):
            if key in self.script:
                return self.script[key]
        return None

    def send(self, req: TurnRequest) -> TurnResponse:
        """The transport PORT -- resolve the scripted response/fault for this request. Fail loud on an empty req."""
        self.sent.append(req)
        if not req.messages:
            raise ProtocolError('mock: request carried no messages', type='bad_request', code=400)
        message = req.messages[-1]
        entry = self._match(message.subject, req.mode, message.content)
        if isinstance(entry, ScriptedFault):
            # mirror the HTTP transport's surfaced envelope shape: "http <code> <type>: <message>" so the
            # captured turn error carries the code + type the app shows (the fail-loud envelope, not a bare msg).
            raise ProtocolError(f'http {entry.code} {entry.type}: {entry.message}',
                                type=entry.type, code=entry.code)
        if isinstance(entry, _ResponseSpec):
            return entry.build(req)
        if entry is not None and callable(entry):
            return entry(req)
        if self.default_enabled:
            return TurnResponse(session_id=req.session_id, seq=req.seq + 1, subject=message.subject,
                                content=f'staged:{message.content}', mode=req.mode)
        raise ProtocolError(
            f'http 404 not_found: no scripted response for '
            f'({message.subject!r}, {req.mode!r}, {message.content!r})',
            type='not_found', code=404)

    def list_subjects(self) -> List[Dict[str, str]]:
        """The scripted routable-subject listing (the ``--list`` discovery path)."""
        return list(self.subjects)


@dataclass(frozen=True)
class _ResponseSpec:
    """An internal scripted-response template -- builds a ``TurnResponse`` from the request (advancing the seq)."""
    content: str
    seq_advance: int = 1

    def build(self, req: TurnRequest) -> TurnResponse:
        message = req.messages[-1]
        return TurnResponse(session_id=req.session_id, seq=req.seq + self.seq_advance,
                            subject=message.subject, content=self.content, mode=req.mode)


def build_mock_context(transport: MockTransport, *, w: int = DEFAULT_DRIVE_WIDTH, h: int = DEFAULT_DRIVE_HEIGHT,
                       config: Optional[UserConfig] = None, settings: Optional[AppSettings] = None,
                       session_id: str = DEFAULT_SESSION_ID, modes: Tuple[str, ...] = DEFAULT_MODES,
                       clock_start: float = 0.0) -> RunContext:
    """Wire the FULL headless stack over a MockTransport -> a RunContext (driver + virtual clock + empty trace).

    ``MockTransport -> Stepper -> AppViewModel -> build_headless_driver``. The ViewModel gets a RECORDING bus + a
    VirtualClock + a Ticker tuned to the config TTL -- the deterministic, server-free stack a flow drives.
    Returns a ready ``RunContext``.
    """
    cfg = config or UserConfig()
    clock = VirtualClock(start=clock_start)
    stepper = Stepper(transport=transport, session_id=session_id)
    session = SessionState(session_id=session_id)
    model = AppModel(session=session, settings=settings or AppSettings(), config=cfg)
    vm = AppViewModel(stepper=stepper, model=model, url='mock://uitest', modes=tuple(modes),
                      bus=EventBus(record=True), clock=clock, ticker=Ticker(ttl_seconds=cfg.status_ttl_seconds))
    driver = build_headless_driver(vm, w=w, h=h)
    return RunContext(driver=driver, clock=clock)


# ===== the FIXTURE port + registry =========================================================================

@dataclass
class Fixture:
    """A NAMED, composable fixture -- ``setup(ctx_or_none) -> ctx`` + optional ``teardown(ctx)``.

    The FIRST fixture in a flow's GIVEN (a 'base' fixture like ``fresh_app``) builds the RunContext from nothing;
    later fixtures LAYER onto the existing context (script the server, seed a transcript, resize). ``base`` marks
    a builder that creates the context (vs one that mutates a passed-in context). Open/closed via the registry.
    """
    name: str
    setup: Callable[[Optional[RunContext]], RunContext]
    base: bool = False
    teardown: Optional[Callable[[RunContext], None]] = None


_FIXTURES: Dict[str, Callable[..., Fixture]] = {}


def register_fixture(name: str, builder: Callable[..., Fixture]) -> None:
    """Register a NAMED fixture builder. Fail LOUD on a duplicate name (no silent clobber)."""
    if name in _FIXTURES:
        raise ValueError(f'fixture {name!r} already registered')
    _FIXTURES[name] = builder


def fixture_builder(name: str) -> Callable[..., Fixture]:
    if name not in _FIXTURES:
        raise KeyError(f'unknown fixture {name!r} (known: {sorted(_FIXTURES)})')
    return _FIXTURES[name]


def known_fixtures() -> List[str]:
    return sorted(_FIXTURES)


# ===== the NAMED fixtures ==================================================================================

def fresh_app(size: Tuple[int, int] = (DEFAULT_DRIVE_WIDTH, DEFAULT_DRIVE_HEIGHT),
              config: Optional[UserConfig] = None, transport: Optional[MockTransport] = None) -> Fixture:
    """BASE fixture -- a fresh headless app over a (default-echoing) MockTransport. The usual flow starting point."""
    def _setup(_ctx: Optional[RunContext]) -> RunContext:
        w, h = size
        return build_mock_context(transport or MockTransport(), w=w, h=h, config=config)
    return Fixture(name='fresh_app', setup=_setup, base=True)


def with_subjects(listing: List[Dict[str, str]]) -> Fixture:
    """Layer: set the MockTransport's scripted routable-subject listing (the discovery surface)."""
    def _setup(ctx: Optional[RunContext]) -> RunContext:
        _require(ctx, 'with_subjects')
        _mock(ctx).subjects = list(listing)
        return ctx
    return Fixture(name='with_subjects', setup=_setup)


def scripted_server(script: Dict[Tuple, object], *, default_enabled: bool = True) -> Fixture:
    """Layer: load a SCRIPT onto the MockTransport (key -> response/fault). Set ``default_enabled=False`` to make

    any unscripted request a 404 fault (so a flow can prove it only ever issues the scripted turns).
    """
    def _setup(ctx: Optional[RunContext]) -> RunContext:
        _require(ctx, 'scripted_server')
        mt = _mock(ctx)
        mt.script.update(script)
        mt.default_enabled = default_enabled
        return ctx
    return Fixture(name='scripted_server', setup=_setup)


def seeded_transcript(turns: List[Tuple[str, str]], *, mode: Optional[str] = None) -> Fixture:
    """Layer: WALK a scripted transcript of N turns (each ``(subject, text)``) -- ONE step per turn, by hand.

    This drives the REAL ``vm.step`` once per turn (no auto-loop -- a literal loop over EXPLICIT turns, each a
    single step), so the seeded transcript is genuine recorded state (not a fabricated list). Each turn echoes
    through the MockTransport's default unless the script overrides it.
    """
    def _setup(ctx: Optional[RunContext]) -> RunContext:
        _require(ctx, 'seeded_transcript')
        vm = ctx.driver.vm
        use_mode = mode or vm.mode
        for subject, text in turns:
            saved = vm.mode
            vm.mode = use_mode
            vm.step(text, subject)          # EXACTLY one turn per explicit entry -- the manual-walk law
            vm.mode = saved
        ctx.driver.render()
        ctx.driver.clear_events()       # scope event assertions to what the FLOW drives, not the seeding
        return ctx
    return Fixture(name='seeded_transcript', setup=_setup)


def at_size(w: int, h: int) -> Fixture:
    """Layer: resize the synthetic terminal the headless View solves against."""
    def _setup(ctx: Optional[RunContext]) -> RunContext:
        _require(ctx, 'at_size')
        ctx.driver.resize(w, h)
        return ctx
    return Fixture(name='at_size', setup=_setup)


def with_prompt_entry(subject: str, text: str) -> Fixture:
    """Layer: wire the ViewModel's prompt SEAM so ``Invoke('request_prompt')`` walks ONE turn from (subject, text).

    The runtime's ``request_prompt`` opens an interactive prompt for (subject, text); headless, we hand it a fixed
    entry. This is how the one-turn-law flow drives a prompt by command name without a terminal. It returns ONE
    entry then cancels further prompts (so re-invoking does NOT silently re-walk -- still one explicit turn each).
    """
    def _setup(ctx: Optional[RunContext]) -> RunContext:
        _require(ctx, 'with_prompt_entry')
        box = {'entry': (subject, text)}

        def _prompt():
            entry = box['entry']
            box['entry'] = None      # consume -- a second Invoke gets a cancel, not a silent re-walk
            return entry
        ctx.driver.vm.prompt_seam = _prompt
        return ctx
    return Fixture(name='with_prompt_entry', setup=_setup)


# ---- helpers -----------------------------------------------------------------------------------------------
def _require(ctx: Optional[RunContext], who: str) -> None:
    if ctx is None:
        raise ValueError(f'{who} is a LAYER fixture -- it needs a base fixture (e.g. fresh_app) before it')


def _mock(ctx: RunContext) -> MockTransport:
    transport = ctx.driver.vm.stepper.transport
    if not isinstance(transport, MockTransport):
        raise TypeError('this fixture requires a MockTransport-backed context (use fresh_app as the base)')
    return transport


def _register_builtins() -> None:
    """Wire the built-in fixtures into the registry (the BDD layer can name these)."""
    register_fixture('fresh_app', fresh_app)
    register_fixture('with_subjects', with_subjects)
    register_fixture('scripted_server', scripted_server)
    register_fixture('seeded_transcript', seeded_transcript)
    register_fixture('at_size', at_size)
    register_fixture('with_prompt_entry', with_prompt_entry)


_register_builtins()
