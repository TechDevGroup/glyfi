"""ticker -- the EPHEMERAL status ticker: a TTL'd status slot + a NAMED, extensible RING of ticker providers.

The status line (its own region, above the input fence) is an EPHEMERAL TICKER, not a sticky status bar:

  * A PUSHED status message shows for a configured TTL, then auto-CLEARS (the line goes blank). The TTL is read
    against the injectable ``Clock`` -- in tests a ``VirtualClock`` crosses the TTL deterministically; at runtime
    a monotonic clock advanced by curses' periodic ``getch`` timeout expires it. NO wall-clock in the logic, NO
    magic literal: the TTL is a NAMED config value.

  * **Tab** cycles the slot through a RING of ticker ITEMS -- each a NAMED PROVIDER ``fn(vm) -> str`` (last
    status · hints · session stats · notices ...), mirroring the ``fields`` alias registry. Pressing Tab
    re-shows / advances the ring. The ring is EXTENSIBLE: ``register_ticker(name, fn)`` adds a provider (fail
    loud on a duplicate name -- two features can't silently clobber a ring slot).

The two pieces are separable + pure (mechanism-testable, no curses):
  * ``register_ticker`` / ``ticker_ring`` -- the NAMED provider ring (open/closed: add a provider, the ring grows).
  * ``Ticker`` -- the PURE TTL state machine: ``push(text, clock)`` stamps a message; ``current(vm, clock)``
    returns what to show RIGHT NOW (the live pushed message until the TTL elapses, else the active ring
    provider's value); ``cycle()`` advances the ring (Tab). It reads the Clock for expiry, mutates nothing else.

Providers read the ViewModel duck-typed. Fail loud on a misconfigured provider (unknown active provider name).
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from glyfi.ui.clock import Clock

# ---- NAMED ticker provider names (the ring slots; no bare strings at a register/select site) ----------------
TICKER_STATUS = 'status'        # the last pushed status message (the default ring head)
TICKER_HINTS = 'hints'          # the input-line-style usage hint
TICKER_STATS = 'stats'          # session stats (turn count / seq)
TICKER_NOTICES = 'notices'      # standing notices (mode)

# ---- NAMED default TTL config key + value (no magic literal; overridable via the config seam) ---------------
# The default time-to-live, in SECONDS, a pushed status stays visible before the ticker auto-clears it.
DEFAULT_STATUS_TTL_SECONDS = 4.0
# the config-store key the TTL persists under (NAMED, like the other config keys).
KEY_STATUS_TTL = 'status_ttl_seconds'

# ---- NAMED hint text (the empty-input hint + the default ring 'hints' provider) -----------------------------
INPUT_HINT = 'type / for commands · ↑↓ history · Tab ticker'


@dataclass(frozen=True)
class TickerProvider:
    """A registered ring item -- a NAMED ``name`` + a pure ``fn(vm) -> str`` rendering its current ticker value."""
    name: str
    fn: Callable[[object], str]


# the ring registry: name -> provider, in registration order (Tab walks this order). Fail-loud on dup.
_RING: Dict[str, TickerProvider] = {}


def register_ticker(name: str, fn: Callable[[object], str]) -> None:
    """Register a ticker ring provider under ``name``. Fail LOUD on a duplicate name (no silent ring clobber)."""
    if name in _RING:
        raise ValueError(f'ticker provider {name!r} already registered')
    _RING[name] = TickerProvider(name=name, fn=fn)


def _provider_status(vm) -> str:
    """The last pushed status text (the message the ticker most recently received) -- empty if none."""
    return str(getattr(vm, 'last_status', '') or '')


def _provider_hints(_vm) -> str:
    return INPUT_HINT


def _provider_stats(vm) -> str:
    return f'turns {vm.model.turn_count} · seq {vm.session.seq}'


def _provider_notices(vm) -> str:
    return f'mode {vm.mode}'


def _register_builtins() -> None:
    """Wire the built-in ring providers, in ring order: status, hints, stats, notices (Tab cycles this order)."""
    register_ticker(TICKER_STATUS, _provider_status)
    register_ticker(TICKER_HINTS, _provider_hints)
    register_ticker(TICKER_STATS, _provider_stats)
    register_ticker(TICKER_NOTICES, _provider_notices)


_register_builtins()


def ticker_ring() -> List[str]:
    """The ring provider names, in registration order (the order Tab walks). The first is the default head."""
    return list(_RING.keys())


def ticker_provider(name: str) -> TickerProvider:
    """The provider registered under ``name`` -- fail LOUD on unknown (a ring pointing at an unknown is a fault)."""
    if name not in _RING:
        raise KeyError(f'unknown ticker provider {name!r} (known: {ticker_ring()})')
    return _RING[name]


@dataclass
class Ticker:
    """The PURE ephemeral-ticker state machine -- a TTL'd pushed message + the active ring provider cursor.

    ``push(text, clock)`` stamps a message with the clock's NOW; ``current(vm, clock)`` returns the live pushed
    message while ``now - pushed_at < ttl_seconds``, else falls through to the active ring provider's value;
    ``cycle()`` advances the ring (Tab) AND re-bases the cursor onto the ring (so Tab always shows a ring item,
    not a stale pushed message). Reads the Clock only for expiry -- no wall-clock, no side effects beyond its own
    fields. ``ttl_seconds`` is injected from config (NAMED), never a literal here.
    """
    ttl_seconds: float = DEFAULT_STATUS_TTL_SECONDS
    _text: str = ''
    _pushed_at: Optional[float] = None
    _ring_index: int = 0
    # when True the slot shows the active RING provider (Tab was pressed); when False it shows the pushed message.
    _on_ring: bool = False

    def push(self, text: str, clock: Clock) -> None:
        """Push a status message onto the ticker -- visible until its TTL elapses, then auto-cleared."""
        self._text = str(text)
        self._pushed_at = clock.now()
        self._on_ring = False

    def resume(self, clock: Clock) -> None:
        """Re-stamp the live pushed message's clock so its TTL restarts -- called when a menu CLOSES (back to NORMAL).

        While a menu was up the TTL was suspended (``current`` ignored expiry); on return to NORMAL we re-base
        ``pushed_at`` to NOW so the message gets its full remaining ephemeral life from the moment focus returns,
        rather than instantly expiring on the stale stamp. No-op when nothing is pushed or we're on the ring.
        """
        if self._pushed_at is not None and not self._on_ring:
            self._pushed_at = clock.now()

    def is_expired(self, clock: Clock) -> bool:
        """True once the pushed message's TTL has elapsed (no message pushed -> True: nothing live to show)."""
        if self._pushed_at is None:
            return True
        return (clock.now() - self._pushed_at) >= self.ttl_seconds

    def active_provider(self) -> str:
        """The NAMED ring provider the cursor currently points at (Tab advances this). Fail loud if ring empty."""
        ring = ticker_ring()
        if not ring:
            raise RuntimeError('ticker ring is empty -- no providers registered')
        return ring[self._ring_index % len(ring)]

    def cycle(self) -> str:
        """Tab -- advance to (and SHOW) the next ring provider. Returns the now-active provider name."""
        ring = ticker_ring()
        if not ring:
            raise RuntimeError('ticker ring is empty -- no providers registered')
        if self._on_ring:
            self._ring_index = (self._ring_index + 1) % len(ring)
        self._on_ring = True
        return self.active_provider()

    def current(self, vm, clock: Clock) -> str:
        """What the ticker shows RIGHT NOW. Two modes, decided by whether Tab put us on the ring:

          * NOT on the ring (the default): the live PUSHED message until its TTL elapses, then BLANK (the
            ephemeral line auto-clears -- the "goes blank" behavior).
          * On the ring (Tab was pressed): the active ring provider's value (the ITEM Tab selected), which
            ignores the TTL -- Tab is the operator explicitly choosing a ring item to dwell on.

        STATUS PERSISTENCE WHILE A MENU IS UP (a11y): the TTL expiry is SUSPENDED while a menu/submenu/palette/
        widget is open -- the ephemeral line must NOT dissipate under the operator while they navigate. The VM
        reports this via the duck-typed ``menu_active()`` (True when ``mode_ui != NORMAL``); ephemerality resumes
        the instant focus returns to NORMAL. The elapsed-while-suspended time is NOT counted (the push effectively
        pauses), so the message is still live for its full remaining TTL after the menu closes.

        Fail LOUD if the active ring provider name is unknown (a misconfigured ring is surfaced, not blanked).
        """
        if not self._on_ring:
            menu_up = bool(getattr(vm, 'menu_active', lambda: False)())
            if self._pushed_at is not None and (menu_up or not self.is_expired(clock)):
                return self._text
            return ''                    # pushed message expired (or never pushed) -> the line goes BLANK
        return ticker_provider(self.active_provider()).fn(vm)
