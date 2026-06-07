"""app -- the composition root: wire Model + ViewModel + curses View over the HTTP transport, then run.

This builds the three MVVM layers and launches the curses loop:
  * Model      -- an ``AppModel`` over a ``SessionState`` seeded from the CLI/config (session id).
  * ViewModel  -- an ``AppViewModel`` over a ``Stepper`` (the transport, driven ONE turn at a time).
  * View       -- a ``CursesView`` bound to the ViewModel, painting anchored regions, responsive to resize.

The transport is the SINGLE server link -- the app builds the ``Stepper`` over the HTTP transport only. The walk
stays MANUAL: the curses View drives exactly one turn per operator keystroke and STOPS -- no auto-loop anywhere.
``--list`` discovers the server-exposed subjects and exits (no app launched).

Runtime wiring: the runtime ViewModel uses the DEFAULT event bus (no recording) + a ``MonotonicClock`` (the
ticker TTL reads it; the curses loop's periodic getch-timeout lets it expire). The HEADLESS ``AppDriver`` (a
recording bus + a ``VirtualClock``) is the test seam -- not launched here.
"""
import os
from typing import Tuple

from glyfi.ui.model import AppModel, SessionState
from glyfi.ui.settings import AppSettings
from glyfi.ui.view import RegionPainter
from glyfi.ui.viewmodel import AppViewModel, DEFAULT_MODES
from glyfi.ui import config_store
from glyfi.stepper import Stepper

# Shipped, first-party widget/command plugins live as one-file-per-plugin manifests in this repo-local dir
# (handlers/factories resolve under the default ``glyfi.{plugins,widgets,contrib}`` allowlist -- no env). A
# missing dir is a no-op; first-party plugins are pure file-drops here (no shared-file edit to register one).
BUILTIN_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), 'plugins', 'builtin')


def build_viewmodel(base_url: str, session_id: str, settings: AppSettings,
                    modes: Tuple[str, ...] = DEFAULT_MODES) -> AppViewModel:
    """Wire the MVVM stack over the HTTP transport ONLY -- a pure OpenAI-protocol-shaped client.

    The transport is the SINGLE server link; the Model/ViewModel/View hold no server-internal refs. ``settings``
    is pluggable -- pass a custom ``AppSettings`` to re-anchor regions or rebind keys. The persisted user
    ``UserConfig`` (slot binds / region visibility / theme) is loaded from the NAMED ``GLYFI_CONFIG`` path
    (default ``~/.config/glyfi/config.json``; missing -> defaults, first run) and carried on the Model. ``modes``
    is the configurable mode-label list (the core never interprets the labels).
    """
    from glyfi.transport import HttpTransport
    stepper = Stepper(transport=HttpTransport(base_url), session_id=session_id)
    session = SessionState(session_id=session_id)
    config = config_store.load()
    model = AppModel(session=session, settings=settings, config=config)
    load_plugins()
    return AppViewModel(stepper=stepper, model=model, url=base_url, modes=tuple(modes) or DEFAULT_MODES)


def load_plugins() -> None:
    """Bootstrap the PLUGGABLE command/widget registration -- run the enabled sources in NAMED precedence order.

    PRECEDENCE: in-code -> builtin-manifest (repo-local, first-party) -> filesystem-manifest (user dir). The
    builtin source discovers first-party plugins in ``BUILTIN_PLUGINS_DIR``; the user filesystem source discovers
    one-file-per-plugin manifests in the NAMED ``GLYFI_PLUGINS`` dir (default ``~/.config/glyfi/plugins/``). A
    MISSING dir is a no-op. Fail loud on a bad manifest / collision.
    """
    from glyfi.plugins import build_default_loader, InCodeSource, FilesystemManifestSource
    build_default_loader().load_all([
        InCodeSource(),
        FilesystemManifestSource(BUILTIN_PLUGINS_DIR),
        FilesystemManifestSource(),
    ])


def run(viewmodel: AppViewModel) -> None:
    """Launch the curses app via ``curses.wrapper`` (sets up/tears down the terminal cleanly), then run the loop."""
    import curses
    from glyfi.ui.curses_view import CursesView
    curses.wrapper(lambda stdscr: CursesView(stdscr, RegionPainter()).run(viewmodel))
