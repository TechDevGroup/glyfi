"""Tests for the allowlist-guarded dotted-ref handler resolution."""
import pytest

from glyfi.plugins import handlers
from glyfi.plugins import refplugin
from glyfi.plugins.handlers import (
    DEFAULT_ALLOWED_PREFIXES, ENV_PLUGIN_ALLOW, HandlerResolveError, allowed_prefixes, resolve_callable,
)


def test_default_allowlist_covers_plugins_widgets_contrib():
    assert DEFAULT_ALLOWED_PREFIXES == ('glyfi.plugins', 'glyfi.widgets', 'glyfi.contrib')


def test_resolve_callable_resolves_a_real_handler():
    fn = resolve_callable('glyfi.plugins.refplugin:echo_handler')
    assert fn is refplugin.echo_handler


@pytest.mark.parametrize('bad', ['no_colon', 'a:b:c', ':missing', 'mod:'])
def test_resolve_callable_fails_loud_on_malformed_ref(bad):
    with pytest.raises(HandlerResolveError):
        resolve_callable(bad)


def test_resolve_callable_forbids_disallowed_prefix():
    with pytest.raises(HandlerResolveError) as exc:
        resolve_callable('os:getcwd')          # not on the allowlist
    assert 'allowed prefix' in str(exc.value)


def test_resolve_callable_fails_loud_on_missing_attr():
    with pytest.raises(HandlerResolveError):
        resolve_callable('glyfi.plugins.refplugin:nope')


def test_resolve_callable_fails_loud_on_non_callable(monkeypatch):
    monkeypatch.setattr(refplugin, 'ARG_TEXT', 'text', raising=True)
    with pytest.raises(HandlerResolveError):
        resolve_callable('glyfi.plugins.refplugin:ARG_TEXT')   # a str attr, not callable


def test_resolve_callable_fails_loud_on_unimportable_module():
    with pytest.raises(HandlerResolveError):
        resolve_callable('glyfi.plugins.no_such_module:fn')


def test_allowlist_widens_via_named_env(monkeypatch):
    monkeypatch.setenv(ENV_PLUGIN_ALLOW, 'some.other.tree')
    assert 'some.other.tree' in allowed_prefixes()


def test_allowlist_env_splits_on_pathsep(monkeypatch):
    import os
    monkeypatch.setenv(ENV_PLUGIN_ALLOW, os.pathsep.join(['a.b', 'c.d']))
    prefixes = allowed_prefixes()
    assert 'a.b' in prefixes and 'c.d' in prefixes


def test_widened_allowlist_lets_a_ref_resolve(monkeypatch):
    monkeypatch.setenv(ENV_PLUGIN_ALLOW, 'os')
    fn = resolve_callable('os:getcwd')
    import os
    assert fn is os.getcwd
