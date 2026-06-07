"""Smoke tests for the composition root (app.build_viewmodel / load_plugins) + the CLI (--list, argparse).

No curses is launched; we assert the wiring builds a drivable ViewModel and that the CLI ``--list`` path
prints the transport's subjects through a stubbed transport (no real network).
"""
import os
import io
import pytest

from glyfi.ui.settings import AppSettings
from glyfi.ui.viewmodel import AppViewModel
from glyfi.ui.config_store import ENV_CONFIG


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def test_build_viewmodel_wires_a_drivable_vm():
    # build_viewmodel runs the plugin bootstrap; the module-global registries make a SECOND full bootstrap a
    # fail-loud collision (by design), so we build exactly ONCE here and reuse the result for the frame check.
    from glyfi.app import build_viewmodel
    from glyfi.ui.driver import build_headless_driver
    vm = build_viewmodel(base_url='http://127.0.0.1:8800', session_id='glyfi-1',
                         settings=AppSettings(title='glyfi'), modes=('chat', 'plan'))
    assert isinstance(vm, AppViewModel)
    assert vm.session.session_id == 'glyfi-1'
    assert vm.modes == ('chat', 'plan')
    assert vm.mode == 'chat'
    assert vm.title == 'glyfi'
    # the wired stack renders a frame
    d = build_headless_driver(vm)
    assert d.render().lines


def test_plugin_bootstrap_registers_the_builtins():
    """After the (single) plugin bootstrap, the built-in palette commands are registered + filterable."""
    from glyfi.plugins import palette as palette_mod
    names = [c.name for c in palette_mod.all_commands()]
    assert 'prompt' in names and 'help' in names and 'quit' in names


def test_cli_list_prints_subjects(monkeypatch, capsys):
    from glyfi import cli

    class StubTransport:
        def __init__(self, base_url):
            self.base_url = base_url

        def list_subjects(self):
            return [{'subject': 'sub-1', 'label': 'alpha'}, {'subject': 'sub-2', 'label': 'beta'}]

    monkeypatch.setattr('glyfi.transport.HttpTransport', StubTransport)
    cli.main(['--base-url', 'http://x', '--list'])
    out = capsys.readouterr().out
    assert 'sub-1' in out and 'alpha' in out
    assert 'sub-2' in out and 'beta' in out


def test_cli_main_module_importable():
    import glyfi.__main__ as m
    assert hasattr(m, 'main')


def test_version_exposed():
    import glyfi
    assert isinstance(glyfi.__version__, str) and glyfi.__version__
