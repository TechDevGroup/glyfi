"""Shared pytest fixtures.

The command/spec/widget registries are process-global: registration happens once at import (the built-ins) and
again whenever a test runs the plugin bootstrap (``load_plugins`` / ``build_viewmodel``) or registers its own
command/widget. Because the bootstrap is fail-loud on a duplicate name, a registration leaking from one test
into the next would make a later bootstrap collide. The autouse fixture below snapshots both registries before
each test and restores them after (try/finally), so every test starts from the same baseline -- the import-time
built-ins only -- and nothing it registers leaks. Uses the public snapshot/restore seam (no registry internals).
"""
import pytest

from glyfi.plugins.palette import snapshot_registry, restore_registry
from glyfi.widgets.host import snapshot_widgets, restore_widgets


@pytest.fixture(autouse=True)
def _isolated_registries():
    """Snapshot the command + widget registries before each test and restore them after (per-test isolation)."""
    commands = snapshot_registry()
    widgets = snapshot_widgets()
    try:
        yield
    finally:
        restore_registry(commands)
        restore_widgets(widgets)
