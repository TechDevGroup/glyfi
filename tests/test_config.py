"""Tests for the GLYFI_* env config loader: NAMED defaults + fail-loud parsing."""
import pytest

from glyfi.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODES,
    DEFAULT_SESSION_SEQ_START,
    DEFAULT_TITLE,
    ENV_BASE_URL,
    ENV_CONFIG,
    ENV_MODES,
    ENV_PLUGIN_ALLOW,
    ENV_PLUGINS,
    ENV_SESSION_SEQ_START,
    ENV_THEME,
    ENV_TITLE,
    Config,
    ConfigError,
    load_config,
)

ALL_ENV = (
    ENV_BASE_URL, ENV_MODES, ENV_SESSION_SEQ_START, ENV_PLUGINS,
    ENV_PLUGIN_ALLOW, ENV_CONFIG, ENV_TITLE, ENV_THEME,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ALL_ENV:
        monkeypatch.delenv(key, raising=False)
    yield


def test_named_env_keys_preserved():
    assert ENV_BASE_URL == "GLYFI_BASE_URL"
    assert ENV_MODES == "GLYFI_MODES"
    assert ENV_SESSION_SEQ_START == "GLYFI_SESSION_SEQ_START"
    assert ENV_PLUGINS == "GLYFI_PLUGINS"
    assert ENV_PLUGIN_ALLOW == "GLYFI_PLUGIN_ALLOW"
    assert ENV_CONFIG == "GLYFI_CONFIG"
    assert ENV_TITLE == "GLYFI_TITLE"
    assert ENV_THEME == "GLYFI_THEME"


def test_named_defaults_preserved():
    assert DEFAULT_BASE_URL == "http://127.0.0.1:8800"
    assert DEFAULT_MODES == ("chat",)
    assert DEFAULT_SESSION_SEQ_START == 0
    assert DEFAULT_TITLE == "glyfi"


def test_defaults_when_env_unset():
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.modes == DEFAULT_MODES
    assert cfg.session_seq_start == DEFAULT_SESSION_SEQ_START
    assert cfg.title == DEFAULT_TITLE
    assert cfg.plugins_dir == ""
    assert cfg.plugin_allow == ()
    assert cfg.config_path == ""
    assert cfg.theme == ""


def test_config_is_frozen():
    cfg = load_config()
    with pytest.raises(Exception):
        cfg.base_url = "x"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv(ENV_BASE_URL, "http://example.test:9000/")
    monkeypatch.setenv(ENV_MODES, "chat, review ,debug")
    monkeypatch.setenv(ENV_SESSION_SEQ_START, "7")
    monkeypatch.setenv(ENV_PLUGINS, "/tmp/plugins")
    monkeypatch.setenv(ENV_PLUGIN_ALLOW, "pkg.mod, other.mod")
    monkeypatch.setenv(ENV_CONFIG, "/tmp/cfg.json")
    monkeypatch.setenv(ENV_TITLE, "My App")
    monkeypatch.setenv(ENV_THEME, "maroon-select")
    cfg = load_config()
    assert cfg.base_url == "http://example.test:9000/"
    assert cfg.modes == ("chat", "review", "debug")
    assert cfg.session_seq_start == 7
    assert cfg.plugins_dir == "/tmp/plugins"
    assert cfg.plugin_allow == ("pkg.mod", "other.mod")
    assert cfg.config_path == "/tmp/cfg.json"
    assert cfg.title == "My App"
    assert cfg.theme == "maroon-select"


def test_bad_seq_fails_loud(monkeypatch):
    monkeypatch.setenv(ENV_SESSION_SEQ_START, "not-a-number")
    with pytest.raises(ConfigError):
        load_config()


def test_empty_modes_fails_loud(monkeypatch):
    monkeypatch.setenv(ENV_MODES, "  , ,")
    with pytest.raises(ConfigError):
        load_config()


def test_single_mode_ok(monkeypatch):
    monkeypatch.setenv(ENV_MODES, "solo")
    assert load_config().modes == ("solo",)


def test_empty_plugin_allow_yields_empty_tuple(monkeypatch):
    monkeypatch.setenv(ENV_PLUGIN_ALLOW, "")
    assert load_config().plugin_allow == ()
