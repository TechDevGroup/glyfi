"""widgets.hotreload -- the WIDGET/PLUGIN HOT-RELOAD procedure: reload a widget's module in place on a source
change and rebind the live instance to the freshly-defined class, so edits show LIVE with no stop/start.

THE SPEC (how a widget/plugin becomes hot-reloadable -- no opt-in code per widget):
  * A widget is an instance of some class defined in a module (registered in-code via ``register_widget`` or via
    a manifest's ``module:Class`` ref -- both end up as ``type(widget)``).
  * When hot-reload is enabled (env ``GLYFI_HOTRELOAD=1``, read by the curses View), the host checks the active
    widget's module mtime each frame; on change it ``importlib.reload``s that module and RE-RESOLVES the class by
    its qualname, then rebinds ``widget.__class__`` to it. The instance ``__dict__`` (its state) is untouched, so
    scroll position / selection / data survive -- only the methods (render/keys) update.
  * Fail-safe: a broken edit (syntax error saved mid-keystroke) raises in ``reload`` and is swallowed; the TUI
    keeps running on the last-good code and retries when the file changes again.
  * Cost: one ``os.path.getmtime`` per frame on one file -- negligible at the ~20 Hz curses tick.

This module is intentionally NOT among the reloaded modules (its ``_mtimes`` cache must survive a reload).
"""
from __future__ import annotations

import importlib
import os
from types import ModuleType
from typing import Optional

_mtimes: dict = {}


def reload_if_changed(module: ModuleType) -> bool:
    """Reload ``module`` in place iff its source file changed since the last check. True iff a reload happened."""
    path = getattr(module, "__file__", None)
    if not path:
        return False
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return False
    prev = _mtimes.get(module.__name__)
    _mtimes[module.__name__] = mt
    if prev is None or mt == prev:
        return False                                    # first sight or unchanged -> nothing to do
    try:
        importlib.reload(module)
        return True
    except Exception:
        return False                                    # broken mid-edit: keep last-good code, retry on next change


def resolve_qualname(module: ModuleType, qualname: str) -> Optional[object]:
    """Resolve a (possibly nested) qualname like 'Outer.Inner' against a module; None if any part is missing."""
    obj: object = module
    for part in qualname.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj
