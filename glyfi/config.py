"""config -- the NAMED configuration manager.

Engineering standard (hard): NO magic values. Every tunable is a NAMED key, sourced from the
environment with a NAMED default. Fail LOUD on a malformed value -- never a silent fallback.

Load order: process env wins; otherwise the NAMED default. A ``.env`` file (if present) is injected by
the host, not read here (12-factor).
"""
import os
from dataclasses import dataclass
from typing import Tuple


# ============================================================================================
# NAMED env keys -- one registry, here. No bare strings sprinkled through the code.
# ============================================================================================
ENV_BASE_URL = "GLYFI_BASE_URL"
ENV_MODES = "GLYFI_MODES"                          # CSV of plain mode labels
ENV_SESSION_SEQ_START = "GLYFI_SESSION_SEQ_START"
ENV_PLUGINS = "GLYFI_PLUGINS"                      # plugin manifest directory
ENV_PLUGIN_ALLOW = "GLYFI_PLUGIN_ALLOW"            # CSV allowlist of dotted handler prefixes
ENV_CONFIG = "GLYFI_CONFIG"                        # user UI config path
ENV_TITLE = "GLYFI_TITLE"
ENV_THEME = "GLYFI_THEME"

# ============================================================================================
# NAMED defaults -- every default is named, never inlined at a call site.
# ============================================================================================
DEFAULT_BASE_URL = "http://127.0.0.1:8800"
DEFAULT_MODES = ("chat",)                          # plain labels; the core never interprets them
DEFAULT_SESSION_SEQ_START = 0
DEFAULT_PLUGINS_DIR = ""
DEFAULT_PLUGIN_ALLOW = ""
DEFAULT_CONFIG_PATH = ""
DEFAULT_TITLE = "glyfi"
DEFAULT_THEME = ""


class ConfigError(Exception):
    """Fail-loud config fault -- a malformed value (bad int / empty mode list), never a silent default."""


def _get(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _get_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # fail LOUD -- a bad seq is a config bug, not a silent zero
        raise ConfigError(f"config {key}={raw!r} is not an integer") from exc


def _get_csv(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    raw = os.environ.get(key)
    if raw is None:
        return default
    items = tuple(p.strip() for p in raw.split(",") if p.strip())
    if not items:  # fail LOUD -- an empty mode list leaves the app with nothing to cycle through
        raise ConfigError(f"config {key}={raw!r} resolved to no labels")
    return items


def _get_allow_csv(key: str, default: str) -> Tuple[str, ...]:
    raw = os.environ.get(key, default)
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@dataclass(frozen=True)
class Config:
    """The frozen, resolved configuration -- built once at process start from the NAMED env."""
    base_url: str
    modes: Tuple[str, ...]        # plain labels; the core never interprets them
    session_seq_start: int
    plugins_dir: str
    plugin_allow: Tuple[str, ...]
    config_path: str
    title: str
    theme: str


def load_config() -> Config:
    """Resolve from GLYFI_* env with NAMED defaults. Fail loud (ConfigError) on a bad value."""
    return Config(
        base_url=_get(ENV_BASE_URL, DEFAULT_BASE_URL),
        modes=_get_csv(ENV_MODES, DEFAULT_MODES),
        session_seq_start=_get_int(ENV_SESSION_SEQ_START, DEFAULT_SESSION_SEQ_START),
        plugins_dir=_get(ENV_PLUGINS, DEFAULT_PLUGINS_DIR),
        plugin_allow=_get_allow_csv(ENV_PLUGIN_ALLOW, DEFAULT_PLUGIN_ALLOW),
        config_path=_get(ENV_CONFIG, DEFAULT_CONFIG_PATH),
        title=_get(ENV_TITLE, DEFAULT_TITLE),
        theme=_get(ENV_THEME, DEFAULT_THEME),
    )
