"""Tests for the plugin SOURCE adapters: in-code, filesystem-manifest, system-api."""
import os
import shutil

import pytest

from glyfi.plugins import refplugin
from glyfi.plugins.commands import ArgSchema, CommandResult, CommandSpec
from glyfi.plugins.sources import (
    DEFAULT_PLUGINS_REL, ENV_PLUGINS, FilesystemManifestSource, InCodeSource, Registration,
    SystemApiSource, build_command_spec, default_plugins_dir, load_manifest_file,
)
from glyfi.plugins.manifest import ManifestCommand


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'plugins')
FIXTURE_DIR_YAML = os.path.join(os.path.dirname(__file__), 'fixtures', 'plugins_yaml')


def _spec(name='x'):
    return CommandSpec(name=name, description='d', handler=lambda inv, ctx: CommandResult())


# ===== in-code =============================================================================================

def test_in_code_source():
    spec = _spec(name='x')
    reg = InCodeSource(commands=[spec], widgets=[('w', object)]).load()
    assert reg.commands == (spec,)
    assert reg.widgets == (('w', object),)


def test_in_code_source_empty():
    reg = InCodeSource().load()
    assert reg.commands == () and reg.widgets == ()


# ===== default dir =========================================================================================

def test_default_plugins_dir_honors_env(monkeypatch):
    monkeypatch.setenv(ENV_PLUGINS, '/somewhere/plugins')
    assert default_plugins_dir() == '/somewhere/plugins'


def test_default_plugins_dir_falls_back_home(monkeypatch):
    monkeypatch.delenv(ENV_PLUGINS, raising=False)
    expected = os.path.join(os.path.expanduser('~'), DEFAULT_PLUGINS_REL)
    assert default_plugins_dir() == expected
    assert DEFAULT_PLUGINS_REL == os.path.join('.config', 'glyfi', 'plugins')


# ===== filesystem ==========================================================================================

def test_filesystem_source_discovers_and_resolves(tmp_path, monkeypatch):
    shutil.copy(os.path.join(FIXTURE_DIR, 'echo.json'), tmp_path / 'echo.json')
    monkeypatch.setenv(ENV_PLUGINS, str(tmp_path))
    src = FilesystemManifestSource()
    assert src.directory == str(tmp_path)
    reg = src.load()
    names = sorted(c.name for c in reg.commands)
    assert names == ['echo', 'ping']
    echo = next(c for c in reg.commands if c.name == 'echo')
    assert echo.handler is refplugin.echo_handler
    assert echo.arg_schema.has_rest


def test_filesystem_source_missing_dir_is_empty(tmp_path):
    src = FilesystemManifestSource(directory=str(tmp_path / 'absent'))
    assert src.load().commands == ()


def test_filesystem_source_yaml_fixture(tmp_path):
    shutil.copy(os.path.join(FIXTURE_DIR_YAML, 'echo.yaml'), tmp_path / 'echo.yaml')
    reg = FilesystemManifestSource(directory=str(tmp_path)).load()
    assert sorted(c.name for c in reg.commands) == ['echo', 'ping']


def test_filesystem_discover_only_manifest_extensions(tmp_path):
    shutil.copy(os.path.join(FIXTURE_DIR, 'echo.json'), tmp_path / 'echo.json')
    (tmp_path / 'README.md').write_text('not a manifest')
    src = FilesystemManifestSource(directory=str(tmp_path))
    assert [os.path.basename(p) for p in src.discover()] == ['echo.json']


# ===== system-api ==========================================================================================

def test_system_api_source_via_mock_fetch():
    canned = '{"commands": [{"name": "remote", "handler": "glyfi.plugins.refplugin:ping_handler"}]}'
    src = SystemApiSource('http://example/manifest', fetch=lambda url: canned)
    reg = src.load()
    assert reg.commands[0].name == 'remote'
    assert reg.commands[0].handler is refplugin.ping_handler


def test_system_api_source_requires_url():
    with pytest.raises(ValueError):
        SystemApiSource('')


# ===== manifest -> CommandSpec ============================================================================

def test_build_command_spec_resolves_handler():
    mc = ManifestCommand(name='ping', description='d',
                         handler='glyfi.plugins.refplugin:ping_handler')
    spec = build_command_spec(mc, source='t')
    assert spec.name == 'ping' and spec.handler is refplugin.ping_handler
    assert isinstance(spec.arg_schema, ArgSchema)


def test_load_manifest_file_validates_fixture():
    man = load_manifest_file(os.path.join(FIXTURE_DIR, 'echo.json'))
    assert [c.name for c in man.commands] == ['echo', 'ping']
    assert man.commands[0].positionals[0].rest is True


def test_registration_is_immutable():
    reg = Registration(source='s')
    with pytest.raises(Exception):
        reg.source = 'other'   # frozen
