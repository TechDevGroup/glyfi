"""fields -- the config-driven SLOT field registry: a key ALIAS -> a field provider ``(label, fn(vm)->str)``.

The UI's STATE strip and the DETAILS bar are not hard-coded -- they are sequences of *slots*, each bound (in
the persisted config) to a field ALIAS. This module is the registry that maps an alias to (a) a human LABEL the
config editor shows in its alias picker, and (b) a pure resolver ``fn(vm) -> str`` that renders the live value.

Built-in aliases (every alias name is a NAMED const, no bare strings at a bind site):
  cwd       -- the current working dir, abbreviated to ``~`` under $HOME.
  localtime -- the local wall clock HH:MM:SS (``time.localtime`` + ``strftime`` -- a permitted stdlib clock).
  session / seq / mode / subject / turns / url / title -- live session / VM fields.
  blank     -- the empty string (a deliberate spacer slot).

Extensible: ``register_field(alias, label, fn)`` lets a feature add a provider (fail loud on a duplicate alias,
so two features can't silently clobber each other's slot meaning). ``resolve(alias, vm)`` renders one slot and
FAILS LOUD on an unknown alias -- a slot bound (in config) to an alias the registry doesn't know is a config
fault we surface, never a silent blank.

Imports stdlib (``os`` / ``time``) only; the resolvers read the ViewModel duck-typed.
"""
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

# ---- NAMED field aliases (the bind keys a config slot references) ------------------------------------------
ALIAS_CWD = 'cwd'
ALIAS_LOCALTIME = 'localtime'
ALIAS_SESSION = 'session'
ALIAS_SEQ = 'seq'
ALIAS_MODE_FIELD = 'mode'
ALIAS_SUBJECT = 'subject'
ALIAS_TURNS = 'turns'
ALIAS_URL = 'url'
ALIAS_TITLE = 'title'
ALIAS_BLANK = 'blank'

# ---- NAMED render tunables (no magic literals at a render site) --------------------------------------------
LOCALTIME_FORMAT = '%H:%M:%S'   # the wall-clock format for the localtime field
HOME_ABBREV = '~'               # what $HOME collapses to in the cwd field
SUBJECT_PLACEHOLDER = '-'       # shown for an empty subject id


@dataclass(frozen=True)
class FieldProvider:
    """A registered slot field -- a human ``label`` (shown in the config editor) + a pure ``fn(vm) -> str``."""
    alias: str
    label: str
    fn: Callable[[object], str]


def _cwd(_vm) -> str:
    cwd = os.getcwd()
    home = os.environ.get('HOME', '')
    if home and (cwd == home or cwd.startswith(home + os.sep)):
        return HOME_ABBREV + cwd[len(home):]
    return cwd


def _localtime(_vm) -> str:
    return time.strftime(LOCALTIME_FORMAT, time.localtime())


# The built-in registry: alias -> FieldProvider. Mutated only via register_field (fail-loud on dup).
_REGISTRY: Dict[str, FieldProvider] = {}


def register_field(alias: str, label: str, fn: Callable[[object], str]) -> None:
    """Register a slot field provider under ``alias``. Fail LOUD on a duplicate alias (no silent clobber)."""
    if alias in _REGISTRY:
        raise ValueError(f'field alias {alias!r} already registered (label {_REGISTRY[alias].label!r})')
    _REGISTRY[alias] = FieldProvider(alias=alias, label=label, fn=fn)


def override_field_fn(alias: str, fn: Callable[[object], str]) -> None:
    """Replace the resolver ``fn`` for an already-registered ``alias`` (keeping its label). Fail LOUD on unknown.

    A deliberate seam for callers that need to PIN a slot's rendered value (e.g. deterministic documentation
    capture) without re-registering -- the label the config editor shows is preserved. Unlike ``register_field``
    this does not fail on an existing alias; it requires one (an unknown alias is a fault we surface, not a
    silent new slot).
    """
    if alias not in _REGISTRY:
        raise KeyError(f'unknown field alias {alias!r} (known: {known_aliases()})')
    current = _REGISTRY[alias]
    _REGISTRY[alias] = FieldProvider(alias=alias, label=current.label, fn=fn)


def _register_builtins() -> None:
    """Wire the built-in field providers. Idempotent-safe to call once at import (registry starts empty)."""
    register_field(ALIAS_CWD, 'working dir', _cwd)
    register_field(ALIAS_LOCALTIME, 'local time', _localtime)
    register_field(ALIAS_SESSION, 'session id', lambda vm: str(vm.session.session_id))
    register_field(ALIAS_SEQ, 'sequence', lambda vm: str(vm.session.seq))
    register_field(ALIAS_MODE_FIELD, 'mode', lambda vm: str(vm.mode))
    register_field(ALIAS_SUBJECT, 'subject', lambda vm: str(vm.session.last_subject or SUBJECT_PLACEHOLDER))
    register_field(ALIAS_TURNS, 'turn count', lambda vm: str(vm.model.turn_count))
    register_field(ALIAS_URL, 'server url', lambda vm: str(getattr(vm, 'url', '') or '-'))
    register_field(ALIAS_TITLE, 'title', lambda vm: str(vm.title))
    register_field(ALIAS_BLANK, '(blank)', lambda vm: '')


_register_builtins()


def known_aliases() -> List[str]:
    """Every registered alias, in registration order (the config editor's alias-picker list)."""
    return list(_REGISTRY.keys())


def field_label(alias: str) -> str:
    """The human label for ``alias`` -- fail LOUD on an unknown alias (a bad bind is surfaced, not blanked)."""
    if alias not in _REGISTRY:
        raise KeyError(f'unknown field alias {alias!r} (known: {known_aliases()})')
    return _REGISTRY[alias].label


def alias_choices() -> List[Tuple[str, str]]:
    """``(alias, label)`` pairs for the config editor's alias picker (registration order)."""
    return [(fp.alias, fp.label) for fp in _REGISTRY.values()]


def resolve(alias: str, vm) -> str:
    """Render one slot: look up ``alias`` and call its resolver against the ViewModel. Fail LOUD on unknown.

    A slot bound (in config) to an alias the registry does not know is a CONFIG fault -- we raise, surfacing
    the bad bind, rather than silently rendering a blank that hides the mistake.
    """
    if alias not in _REGISTRY:
        raise KeyError(f'unknown field alias {alias!r} (known: {known_aliases()})')
    return _REGISTRY[alias].fn(vm)


def resolve_labeled(alias: str, vm) -> str:
    """Render one slot as ``label value`` (for the details bar). Blank fields render as just their value."""
    value = resolve(alias, vm)
    if alias == ALIAS_BLANK:
        return value
    return f'{field_label(alias)} {value}'
