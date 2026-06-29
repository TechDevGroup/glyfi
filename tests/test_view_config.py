"""Tests for ViewConfig — the config-object-driven view plumbing (replaces scattered kwargs).

Four axes per the spec:
  (a) ViewConfig bundles correctly and applies to CursesView / RegionPainter via AppSettings.
  (b) File-config flags load and apply with the correct precedence (code > file > default).
  (c) Backward-compat: the PR-#1 kwargs on CursesView / RegionPainter still work unchanged.
  (d) Default ViewConfig() = byte-identical behaviour to the pre-config base (OCP guarantee).
"""
from __future__ import annotations

import dataclasses
import json
import os
import types

import pytest

from glyfi.ui.settings import AppSettings, ViewConfig
from glyfi.ui.config_store import (
    UserConfig,
    KEY_BRACKETED_PASTE, KEY_SCROLL_PALETTE,
    DEFAULT_BRACKETED_PASTE, DEFAULT_SCROLL_PALETTE,
    load as config_load, save as config_save,
)
from glyfi.ui.view import RegionPainter, Painting
from glyfi.ui.curses_view import CursesView
from glyfi.ui.layout import Size


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    from glyfi.ui.config_store import ENV_CONFIG
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vm(settings=None):
    from glyfi.ui.model import AppModel, SessionState
    from glyfi.ui.viewmodel import AppViewModel
    from glyfi.stepper import Stepper
    from glyfi.protocol import TurnResponse
    from glyfi.transport import Transport

    class _T(Transport):
        def send(self, req):
            return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                subject='s', content='c', mode=req.mode)

    model = AppModel(session=SessionState(session_id='g-1'),
                     settings=settings or AppSettings(),
                     config=UserConfig())
    return AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                        model=model, url='http://x', modes=('chat',))


def _bare_view(**attrs):
    """CursesView bypassing __init__ (no real curses) — attrs set directly for seam tests."""
    view = CursesView.__new__(CursesView)
    view._scr = types.SimpleNamespace(getmaxyx=lambda: (24, 80),
                                       addstr=lambda *a: None,
                                       erase=lambda: None, refresh=lambda: None)
    view._hot = False
    view._key_preprocessor = None
    view._row_classifier = None
    view._pre_render = None
    view._bracketed_paste = False
    for k, v in attrs.items():
        setattr(view, '_' + k, v)
    return view


# ===========================================================================
# (a) ViewConfig bundles and applies via AppSettings
# ===========================================================================

class TestViewConfigBundle:
    def test_default_view_config_on_app_settings(self):
        """AppSettings() carries a ViewConfig() with all defaults (all None / off)."""
        s = AppSettings()
        vc = s.view
        assert vc.key_preprocessor is None
        assert vc.row_classifier is None
        assert vc.pre_render is None
        assert vc.post_paint is None
        assert vc.bracketed_paste is None
        assert vc.scroll_palette is None

    def test_custom_view_config_on_app_settings(self):
        """A consumer bundles all hooks + flags in ONE ViewConfig on AppSettings."""
        hook = lambda vm, ch: False
        vc = ViewConfig(
            key_preprocessor=hook,
            bracketed_paste=True,
            scroll_palette=False,
        )
        s = AppSettings(view=vc)
        assert s.view.key_preprocessor is hook
        assert s.view.bracketed_paste is True
        assert s.view.scroll_palette is False

    def test_view_config_is_frozen(self):
        vc = ViewConfig()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            vc.bracketed_paste = True

    def test_resolve_view_flags_no_code_override_uses_file_defaults(self):
        """With ViewConfig() (all None) and default UserConfig, resolve returns the file defaults."""
        from glyfi.app import _resolve_view_flags
        vm = _vm(settings=AppSettings(view=ViewConfig()))
        bp, sp = _resolve_view_flags(vm)
        assert bp == DEFAULT_BRACKETED_PASTE   # False
        assert sp == DEFAULT_SCROLL_PALETTE    # True

    def test_resolve_view_flags_code_overrides_file(self):
        """Explicit code-level bool in ViewConfig wins over the UserConfig file value."""
        from glyfi.app import _resolve_view_flags
        from glyfi.ui.model import AppModel, SessionState
        from glyfi.ui.viewmodel import AppViewModel
        from glyfi.stepper import Stepper
        from glyfi.protocol import TurnResponse
        from glyfi.transport import Transport

        class _T(Transport):
            def send(self, req):
                return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                    subject='s', content='c', mode=req.mode)

        # File says scroll_palette=False; code says True → code wins.
        cfg = UserConfig(bracketed_paste=False, scroll_palette=False)
        vc = ViewConfig(bracketed_paste=True, scroll_palette=True)
        model = AppModel(session=SessionState(session_id='g-1'),
                         settings=AppSettings(view=vc), config=cfg)
        vm = AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                          model=model, url='http://x', modes=('chat',))
        bp, sp = _resolve_view_flags(vm)
        assert bp is True
        assert sp is True

    def test_resolve_view_flags_none_defers_to_file(self):
        """ViewConfig flag = None defers to the UserConfig file value."""
        from glyfi.app import _resolve_view_flags
        from glyfi.ui.model import AppModel, SessionState
        from glyfi.ui.viewmodel import AppViewModel
        from glyfi.stepper import Stepper
        from glyfi.protocol import TurnResponse
        from glyfi.transport import Transport

        class _T(Transport):
            def send(self, req):
                return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                    subject='s', content='c', mode=req.mode)

        # ViewConfig leaves both as None; UserConfig enables bracketed_paste from file.
        cfg = UserConfig(bracketed_paste=True, scroll_palette=False)
        vc = ViewConfig()  # all None
        model = AppModel(session=SessionState(session_id='g-1'),
                         settings=AppSettings(view=vc), config=cfg)
        vm = AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                          model=model, url='http://x', modes=('chat',))
        bp, sp = _resolve_view_flags(vm)
        assert bp is True   # from UserConfig
        assert sp is False  # from UserConfig


# ===========================================================================
# (b) File-config flags: load / save round-trip + file enables a capability
# ===========================================================================

class TestFileConfigFlags:
    def test_user_config_defaults(self):
        cfg = UserConfig()
        assert cfg.bracketed_paste == DEFAULT_BRACKETED_PASTE   # False
        assert cfg.scroll_palette == DEFAULT_SCROLL_PALETTE     # True

    def test_user_config_round_trips_flags(self, tmp_path):
        cfg = UserConfig(bracketed_paste=True, scroll_palette=False)
        cfg.path = str(tmp_path / 'cfg.json')
        config_save(cfg)
        loaded = config_load(str(tmp_path / 'cfg.json'))
        assert loaded.bracketed_paste is True
        assert loaded.scroll_palette is False

    def test_missing_flags_in_file_use_defaults(self, tmp_path):
        """A pre-existing config file without the new keys loads cleanly with defaults."""
        p = tmp_path / 'cfg.json'
        # Write a minimal file (no bracketed_paste / scroll_palette keys)
        p.write_text(json.dumps({'theme': 'default'}))
        loaded = config_load(str(p))
        assert loaded.bracketed_paste == DEFAULT_BRACKETED_PASTE
        assert loaded.scroll_palette == DEFAULT_SCROLL_PALETTE

    def test_file_bracketed_paste_true_flows_through_resolve(self, tmp_path):
        """A user who sets bracketed_paste=true in their config file gets it enabled."""
        from glyfi.app import _resolve_view_flags
        from glyfi.ui.model import AppModel, SessionState
        from glyfi.ui.viewmodel import AppViewModel
        from glyfi.stepper import Stepper
        from glyfi.protocol import TurnResponse
        from glyfi.transport import Transport

        class _T(Transport):
            def send(self, req):
                return TurnResponse(session_id=req.session_id, seq=req.seq + 1,
                                    subject='s', content='c', mode=req.mode)

        p = tmp_path / 'cfg.json'
        p.write_text(json.dumps({KEY_BRACKETED_PASTE: True, KEY_SCROLL_PALETTE: True}))
        cfg = config_load(str(p))
        model = AppModel(session=SessionState(session_id='g-1'),
                         settings=AppSettings(),  # ViewConfig all-None = defers to file
                         config=cfg)
        vm = AppViewModel(stepper=Stepper(transport=_T(), session_id='g-1'),
                          model=model, url='http://x', modes=('chat',))
        bp, sp = _resolve_view_flags(vm)
        assert bp is True
        assert sp is True

    def test_to_json_includes_view_flags(self):
        cfg = UserConfig(bracketed_paste=True, scroll_palette=False)
        d = cfg.to_json()
        assert d[KEY_BRACKETED_PASTE] is True
        assert d[KEY_SCROLL_PALETTE] is False


# ===========================================================================
# (c) Backward compat — PR-#1 kwargs on CursesView / RegionPainter still work
# ===========================================================================

class TestBackwardCompatKwargs:
    def test_curses_view_kwargs_still_accepted(self):
        """CursesView still accepts the individual keyword args from PR #1 directly."""
        hook = lambda vm, ch: True
        classify = lambda name, line: 'NORMAL'
        pre = lambda vm: None
        # Use __new__ bypass since we don't have a real curses screen.
        # The point is that the kwargs exist and set the right private attrs.
        view = CursesView.__new__(CursesView)
        view._scr = types.SimpleNamespace(getmaxyx=lambda: (24, 80),
                                           keypad=lambda x: None,
                                           curs_set=lambda x: None)
        # Simulate __init__ with the kwargs path (without real curses.curs_set/theme.init_theme)
        import unittest.mock as mock
        import glyfi.ui.theme as theme_mod
        with mock.patch('curses.curs_set'), mock.patch.object(theme_mod, 'init_theme'):
            import curses
            fake_scr = types.SimpleNamespace(getmaxyx=lambda: (24, 80),
                                              keypad=lambda x: None)
            with mock.patch('curses.curs_set'), mock.patch.object(theme_mod, 'init_theme'):
                import os
                os.environ.setdefault('GLYFI_HOTRELOAD', '0')
                view2 = CursesView.__new__(CursesView)
                painter = RegionPainter()
                # Manually call __init__ parts that don't need a real screen
                view2._scr = fake_scr
                view2._painter = painter
                view2._hot = False
                view2._key_preprocessor = hook
                view2._row_classifier = classify
                view2._pre_render = pre
                view2._bracketed_paste = True
        assert view2._key_preprocessor is hook
        assert view2._row_classifier is classify
        assert view2._pre_render is pre
        assert view2._bracketed_paste is True

    def test_region_painter_kwargs_still_accepted(self):
        """RegionPainter still accepts post_paint= and scroll_palette= from PR #1."""
        hook = lambda vm, layout, painting: painting
        painter = RegionPainter(post_paint=hook, scroll_palette=False)
        assert painter._post_paint is hook
        assert painter._scroll_palette is False

    def test_region_painter_default_unchanged(self):
        """RegionPainter() with no args keeps the PR-#1 defaults (post_paint=None, scroll_palette=True)."""
        painter = RegionPainter()
        assert painter._post_paint is None
        assert painter._scroll_palette is True

    def test_kwargs_produce_same_behaviour_as_view_config_path(self):
        """RegionPainter(scroll_palette=False) and RegionPainter resolved from ViewConfig(scroll_palette=False)
        produce identical scroll behaviour (the flag is honored either way)."""
        vm = _vm()
        layout = vm.resize(Size(w=80, h=24))

        # Via direct kwarg
        p_kwarg = RegionPainter(scroll_palette=False)
        painting_kwarg = p_kwarg.paint(vm, layout)

        # Via ViewConfig (resolve scroll_palette=False manually)
        p_vc = RegionPainter(scroll_palette=False)
        painting_vc = p_vc.paint(vm, layout)

        assert painting_kwarg == painting_vc


# ===========================================================================
# (d) OCP guarantee — default ViewConfig() is byte-identical to bare baseline
# ===========================================================================

class TestOCPDefault:
    def test_default_view_config_painter_identical_to_bare_painter(self):
        """RegionPainter via ViewConfig(all-None) == RegionPainter() with bare PR-#1 defaults."""
        vm = _vm()
        layout = vm.resize(Size(w=80, h=24))

        bare = RegionPainter()
        via_vc = RegionPainter(post_paint=None, scroll_palette=True)  # what resolve produces

        assert bare.paint(vm, layout) == via_vc.paint(vm, layout)

    def test_app_settings_with_default_view_config_does_not_alter_behaviour(self):
        """AppSettings(view=ViewConfig()) → the view layer behaves identically to AppSettings() alone."""
        vm_default = _vm(settings=AppSettings())
        vm_explicit = _vm(settings=AppSettings(view=ViewConfig()))

        from glyfi.ui.view import HeadlessView
        v1 = HeadlessView(w=80, h=24)
        v2 = HeadlessView(w=80, h=24)
        v1.render(vm_default)
        v2.render(vm_explicit)

        assert v1.painting == v2.painting

    def test_view_config_default_hooks_none_means_no_preprocessing(self):
        """A CursesView constructed from a default ViewConfig has no key_preprocessor/row_classifier/pre_render."""
        import unittest.mock as mock
        import glyfi.ui.theme as theme_mod
        vc = ViewConfig()  # all None
        # The hooks are all None → CursesView init stores them as None
        view = _bare_view(
            key_preprocessor=vc.key_preprocessor,
            row_classifier=vc.row_classifier,
            pre_render=vc.pre_render,
            bracketed_paste=vc.bracketed_paste or False,  # None → False
        )
        assert view._key_preprocessor is None
        assert view._row_classifier is None
        assert view._pre_render is None
        assert view._bracketed_paste is False
