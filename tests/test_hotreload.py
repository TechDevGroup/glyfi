"""Widget/plugin HOT-RELOAD: a source change reloads the module in place and rebinds the live widget instance to
the freshly-defined class, preserving its state. No TTY, no real edit loop -- a temp module stands in.
"""
import importlib
import os
import sys
import textwrap

from glyfi.ui.layout import Rect
from glyfi.widgets.base import Widget, WidgetContext
from glyfi.widgets.host import WidgetHost, register_widget, snapshot_widgets, restore_widgets
from glyfi.widgets.hotreload import reload_if_changed, resolve_qualname

RECT = Rect(x=0, y=0, w=40, h=6)


def _write(tmp_path, name, version):
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(f"""
        from glyfi.widgets.base import Widget
        class HotW(Widget):
            title = 'hot'
            def open(self, ctx):
                self._n = getattr(self, '_n', 7)
            def lines(self, rect):
                return ['VERSION {version}', 'n=' + str(getattr(self, '_n', '?'))]
    """))


def _import_temp(tmp_path, name):
    d = str(tmp_path)
    sys.modules.pop(name, None)                        # avoid sys.modules caching a prior test's module of this name
    if d not in sys.path:
        sys.path.insert(0, d)
    return importlib.import_module(name)


def _bump_mtime(tmp_path, name):
    p = str(tmp_path / f"{name}.py")
    t = os.path.getmtime(p) + 10
    os.utime(p, (t, t))


def test_reload_if_changed_tracks_mtime(tmp_path):
    name = "hotw_a"
    _write(tmp_path, name, 1)
    mod = _import_temp(tmp_path, name)
    try:
        assert reload_if_changed(mod) is False        # first sight -> no reload
        assert reload_if_changed(mod) is False        # unchanged -> no reload
        _write(tmp_path, name, 2); _bump_mtime(tmp_path, name)
        assert reload_if_changed(mod) is True          # changed -> reloaded
        assert "VERSION 2" in mod.HotW().lines(RECT)[0]
    finally:
        sys.modules.pop(name, None)


def test_resolve_qualname():
    import glyfi.widgets.host as h
    assert resolve_qualname(h, "WidgetHost") is h.WidgetHost
    assert resolve_qualname(h, "Nope.Missing") is None


def test_host_reload_active_rebinds_and_preserves_state(tmp_path):
    name = "hotw_b"
    snap = snapshot_widgets()
    _write(tmp_path, name, 1)
    mod = _import_temp(tmp_path, name)
    try:
        reload_if_changed(mod)                         # prime the mtime cache (first sight)
        register_widget("hotw", mod.HotW)
        host = WidgetHost(push_status=lambda s: None, emit=lambda e: None, on_close=lambda: None)
        w = host.open("hotw")
        w._n = 99                                      # state the reload must preserve
        assert host.lines(RECT)[0] == "VERSION 1"

        _write(tmp_path, name, 2); _bump_mtime(tmp_path, name)
        assert host.reload_active() is True            # module changed -> class swapped in place
        assert host.active is w                        # SAME instance (not re-opened)
        assert host.lines(RECT)[0] == "VERSION 2"      # new render code
        assert host.lines(RECT)[1] == "n=99"           # state preserved across the swap
        assert host.reload_active() is False           # unchanged again -> no swap
    finally:
        restore_widgets(snap)
        sys.modules.pop(name, None)
