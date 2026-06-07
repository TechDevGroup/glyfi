"""Tests for the PluginLoader: multi-source registration + cross-source conflict policies."""
import pytest

from glyfi.plugins.commands import CommandResult, CommandSpec
from glyfi.plugins.sources import InCodeSource
from glyfi.plugins.loader import (
    CONFLICT_POLICIES, FAIL_LOUD, LoadReport, PluginConflictError, PluginLoader, SKIP_LATER,
    build_default_loader,
)


def _spec(name='x'):
    return CommandSpec(name=name, description='d', handler=lambda inv, ctx: CommandResult())


def _stub_loader(on_conflict=FAIL_LOUD):
    reg = {'commands': {}, 'widgets': {}}
    loader = PluginLoader(
        register_command_spec=lambda spec: reg['commands'].__setitem__(spec.name, spec),
        register_widget=lambda name, factory: reg['widgets'].__setitem__(name, factory),
        command_exists=lambda n: n in reg['commands'],
        widget_exists=lambda n: n in reg['widgets'],
        on_conflict=on_conflict,
    )
    return loader, reg


def test_policies_named():
    assert CONFLICT_POLICIES == (FAIL_LOUD, SKIP_LATER)


def test_loader_registers_from_multiple_sources():
    loader, reg = _stub_loader()
    s1 = InCodeSource(commands=[_spec(name='a')])
    s2 = InCodeSource(commands=[_spec(name='b')], widgets=[('w', object)])
    report = loader.load_all([s1, s2])
    assert set(reg['commands']) == {'a', 'b'}
    assert 'w' in reg['widgets']
    assert sorted(report.commands) == ['a', 'b']
    assert report.widgets == ('w',)


def test_loader_fails_loud_on_cross_source_duplicate():
    loader, _ = _stub_loader(on_conflict=FAIL_LOUD)
    s1 = InCodeSource(commands=[_spec(name='dup')])
    s2 = InCodeSource(commands=[_spec(name='dup')])
    with pytest.raises(PluginConflictError):
        loader.load_all([s1, s2])


def test_loader_fails_loud_on_cross_source_widget_duplicate():
    loader, _ = _stub_loader(on_conflict=FAIL_LOUD)
    s1 = InCodeSource(widgets=[('w', object)])
    s2 = InCodeSource(widgets=[('w', object)])
    with pytest.raises(PluginConflictError):
        loader.load_all([s1, s2])


def test_loader_skip_later_precedence_keeps_first():
    loader, reg = _stub_loader(on_conflict=SKIP_LATER)
    first = _spec(name='dup')
    second = _spec(name='dup')
    report = loader.load_all([InCodeSource(commands=[first]), InCodeSource(commands=[second])])
    assert reg['commands']['dup'] is first         # earlier precedence wins
    assert any('dup' in s for s in report.skipped)


def test_loader_respects_preexisting_registration():
    loader, reg = _stub_loader(on_conflict=FAIL_LOUD)
    reg['commands']['builtin'] = _spec(name='builtin')   # a pre-existing built-in
    with pytest.raises(PluginConflictError):
        loader.load_all([InCodeSource(commands=[_spec(name='builtin')])])


def test_loader_unknown_conflict_policy_fails_loud():
    with pytest.raises(ValueError):
        PluginLoader(lambda s: None, lambda n, f: None, lambda n: False, lambda n: False,
                     on_conflict='bogus')


def test_load_report_describe():
    rep = LoadReport(commands=('a',), widgets=('w',), skipped=('s',))
    text = rep.describe()
    assert 'a' in text and 'w' in text and 's' in text


def test_build_default_loader_returns_loader():
    loader = build_default_loader()
    assert isinstance(loader, PluginLoader)


def test_build_default_loader_registers_into_live_registries():
    """The default loader wires the live palette/widget registries -- an InCodeSource registers through them."""
    from glyfi.plugins import palette as palette_mod
    from glyfi.widgets import host as widget_host

    spec = _spec(name='loader_live_cmd')

    class _W:
        pass

    def _factory():
        from glyfi.widgets.base import Widget

        class _RealWidget(Widget):
            def open(self, ctx): pass
            def lines(self, rect): return []
        return _RealWidget()

    loader = build_default_loader()
    report = loader.load_all([InCodeSource(commands=[spec], widgets=[('loader_live_widget', _factory)])])
    assert 'loader_live_cmd' in report.commands
    assert palette_mod.command_spec('loader_live_cmd') is spec
    assert 'loader_live_widget' in widget_host.known_widgets()
