"""plugins.handlers -- resolve a manifest HANDLER REFERENCE (a dotted ``module:callable``) to a real callable.

A manifest entry names its handler/factory as a STRING -- ``glyfi.plugins.refplugin:echo_handler``
(``module:attribute``). This module resolves that string to the actual callable by IMPORT, fail-loud + GUARDED:
  * the form must be exactly ``module:attribute`` (fail loud on a malformed ref);
  * the module must be IMPORTABLE + the attribute must EXIST + be CALLABLE (fail loud otherwise);
  * the module must be on an ALLOWED IMPORT PREFIX (a NAMED allowlist) -- a manifest can't import arbitrary
    system modules. The default allowlist is the glyfi plugin/widget/contrib tree; extend it via
    ``GLYFI_PLUGIN_ALLOW`` (a NAMED, ``os.pathsep``-separated env of additional allowed module prefixes -- the
    operator opts a plugin tree in).

This keeps the filesystem/system-API sources SAFE-by-default (no silent arbitrary-code import) while staying
open/closed (the operator widens the allowlist by NAMED env, never by editing code).

Self-contained: stdlib ``importlib`` / ``os`` only.
"""
import importlib
import os
from typing import Callable, Tuple

# ---- NAMED handler-reference syntax (no bare ':' magic at a parse site) -----------------------------------
REF_SEP = ':'                          # ``module:attribute``

# ---- NAMED allowlist of importable module PREFIXES (a manifest may only resolve refs under these) ----------
DEFAULT_ALLOWED_PREFIXES = ('glyfi.plugins', 'glyfi.widgets', 'glyfi.contrib')
# NAMED env to WIDEN the allowlist (``os.pathsep``-separated additional module prefixes the operator opts in).
ENV_PLUGIN_ALLOW = 'GLYFI_PLUGIN_ALLOW'


class HandlerResolveError(Exception):
    """A fail-loud handler-reference fault -- a malformed ref, a forbidden prefix, or an unimportable target."""

    def __init__(self, ref: str, detail: str):
        super().__init__(f'handler ref {ref!r}: {detail}')
        self.ref = ref
        self.detail = detail


def allowed_prefixes() -> Tuple[str, ...]:
    """The module prefixes a manifest handler ref may resolve under -- the defaults + any NAMED-env additions."""
    extra = os.environ.get(ENV_PLUGIN_ALLOW, '')
    additions = tuple(p.strip() for p in extra.split(os.pathsep) if p.strip())
    return DEFAULT_ALLOWED_PREFIXES + additions


def _split_ref(ref: str) -> Tuple[str, str]:
    if ref.count(REF_SEP) != 1:
        raise HandlerResolveError(ref, f'must be exactly one {REF_SEP!r}-separated module{REF_SEP}attribute')
    module, _, attr = ref.partition(REF_SEP)
    module = module.strip()
    attr = attr.strip()
    if not module or not attr:
        raise HandlerResolveError(ref, f'both module and attribute are required ({REF_SEP}-separated)')
    return module, attr


def _check_allowed(ref: str, module: str) -> None:
    allowed = allowed_prefixes()
    if not any(module == p or module.startswith(p + '.') for p in allowed):
        raise HandlerResolveError(ref, f'module {module!r} is not on an allowed prefix {allowed} '
                                       f'(widen via the {ENV_PLUGIN_ALLOW} env)')


def resolve_callable(ref: str) -> Callable:
    """Resolve a dotted ``module:attribute`` reference to a CALLABLE. Fail loud (located) at every failure point.

    Guards the import against the NAMED allowlist (a manifest can't pull arbitrary system modules), then imports
    the module + fetches the attribute + asserts it is callable. Used for BOTH a command handler and a widget
    factory reference (both are callables resolved the same way).
    """
    module, attr = _split_ref(ref)
    _check_allowed(ref, module)
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        raise HandlerResolveError(ref, f'module {module!r} is not importable: {exc}') from exc
    if not hasattr(mod, attr):
        raise HandlerResolveError(ref, f'module {module!r} has no attribute {attr!r}')
    target = getattr(mod, attr)
    if not callable(target):
        raise HandlerResolveError(ref, f'{attr!r} on {module!r} is not callable (got {type(target).__name__})')
    return target
