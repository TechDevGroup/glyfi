"""config_store -- the PERSISTED user UI config: slot bindings + region visibility + theme, JSON-backed.

This is the durable home of the operator's UI CHOICES (separate from the pluggable code-level ``AppSettings``):
which field ALIAS each slot shows (the state strip + the two details groups), which regions are VISIBLE (the
"config flags for showing things"), and the named THEME. It round-trips to a JSON file so the app reopens with
the operator's last layout.

NAMED env (no magic path): ``GLYFI_CONFIG`` overrides the file path; default ``~/.config/glyfi/config.json``.
First run (file missing) -> the DEFAULTS (the dir + file are created on the first ``save``). ``load`` / ``save``
round-trip the dataclass through JSON.

Fail LOUD (hard standard): a malformed JSON file RAISES -- we never silently reset the operator's config to
defaults (that would hide corruption / a botched hand-edit). Missing file -> defaults is the ONLY soft path,
and that is a first-run signal, not a fallback over an error.

stdlib ``json`` / ``os`` only.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

from glyfi.ui.fields import (
    ALIAS_SESSION, ALIAS_SEQ, ALIAS_MODE_FIELD, ALIAS_SUBJECT, ALIAS_TURNS,
    ALIAS_CWD, ALIAS_LOCALTIME,
)
from glyfi.ui.theme import DEFAULT_THEME
from glyfi.ui.ticker import DEFAULT_STATUS_TTL_SECONDS, KEY_STATUS_TTL

# ---- NAMED env + path (no magic literal path) -------------------------------------------------------------
ENV_CONFIG = 'GLYFI_CONFIG'
DEFAULT_CONFIG_REL = os.path.join('.config', 'glyfi', 'config.json')

# ---- NAMED slot-group keys (the placeable areas a config slot lives in) ------------------------------------
SLOT_STATE = 'state'
SLOT_DETAILS_LEFT = 'details_left'
SLOT_DETAILS_RIGHT = 'details_right'
SLOT_GROUPS = (SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT)

# ---- NAMED JSON keys (no bare strings on disk) ------------------------------------------------------------
KEY_SLOTS = 'slots'
KEY_VISIBLE = 'visible'
KEY_THEME = 'theme'
# KEY_STATUS_TTL is owned by the ticker module (its TTL config) -- imported, not redefined, to keep one source.

# ---- NAMED INPUTS-section keys + defaults (the scroll/interaction knobs the config editor's INPUTS area wires)
KEY_SCROLL_DELTA = 'scroll_delta'      # the line-scroll step (rows the content moves per scroll-up/down)
KEY_PAGE_OVERLAP = 'page_overlap'      # rows kept IN VIEW across a PgUp/PgDn (continuity sliver of the prior view)
# the DEFAULT collapse-state of content entries: False = EXPANDED/full wrapped lines (collapse OPT-IN). True
# makes new entries start collapsed (summary-only).
KEY_CONTENT_COLLAPSED_DEFAULT = 'content_collapsed_default'
# defaults (NAMED, never magic): a 1-row line step + a few-row overlap so a page scroll keeps a sliver of context.
DEFAULT_SCROLL_DELTA = 1
DEFAULT_PAGE_OVERLAP = 3
DEFAULT_CONTENT_COLLAPSED = False      # full expanded wrapped lines by default; collapse is opt-in

# ---- NAMED defaults ---------------------------------------------------------------------------------------
DEFAULT_STATE_SLOTS = (ALIAS_SESSION, ALIAS_SEQ, ALIAS_MODE_FIELD, ALIAS_SUBJECT, ALIAS_TURNS)
DEFAULT_DETAILS_LEFT = (ALIAS_CWD,)
DEFAULT_DETAILS_RIGHT = (ALIAS_LOCALTIME,)


def default_config_path() -> str:
    """The config file path -- ``$GLYFI_CONFIG`` if set, else ``~/.config/glyfi/config.json`` (NAMED)."""
    override = os.environ.get(ENV_CONFIG)
    if override:
        return override
    return os.path.join(os.path.expanduser('~'), DEFAULT_CONFIG_REL)


def _default_slots() -> Dict[str, List[str]]:
    return {
        SLOT_STATE: list(DEFAULT_STATE_SLOTS),
        SLOT_DETAILS_LEFT: list(DEFAULT_DETAILS_LEFT),
        SLOT_DETAILS_RIGHT: list(DEFAULT_DETAILS_RIGHT),
    }


@dataclass
class UserConfig:
    """The persisted UI choices -- slot->alias bindings per area, region visibility flags, and a theme name.

    ``slots`` keys are the SLOT_GROUPS (state / details_left / details_right), each an ORDERED list of field
    aliases. ``visible`` maps a region name -> bool (default-visible: a region absent from the map is shown).
    ``theme`` is a named theme key. Mutated in place by the ViewModel's bind commands, then ``save``d.
    """
    slots: Dict[str, List[str]] = field(default_factory=_default_slots)
    visible: Dict[str, bool] = field(default_factory=dict)
    theme: str = DEFAULT_THEME
    status_ttl_seconds: float = DEFAULT_STATUS_TTL_SECONDS
    scroll_delta: int = DEFAULT_SCROLL_DELTA
    page_overlap: int = DEFAULT_PAGE_OVERLAP
    content_collapsed_default: bool = DEFAULT_CONTENT_COLLAPSED
    path: str = ''

    def is_visible(self, region: str) -> bool:
        """A region is visible unless explicitly hidden in config -- default-visible, no flag needed normally.

        ``visible`` is a PASSIVE power-user config key (a JSON edit can hide a region); there is no interactive
        show/hide toggle COMMAND -- the layout regions are fixed/always-shown in the running app.
        """
        return self.visible.get(region, True)

    def to_json(self) -> Dict:
        """The serializable dict (path is runtime-only -- it is NOT persisted into the file)."""
        return {
            KEY_SLOTS: self.slots,
            KEY_VISIBLE: self.visible,
            KEY_THEME: self.theme,
            KEY_STATUS_TTL: self.status_ttl_seconds,
            KEY_SCROLL_DELTA: self.scroll_delta,
            KEY_PAGE_OVERLAP: self.page_overlap,
            KEY_CONTENT_COLLAPSED_DEFAULT: self.content_collapsed_default,
        }


def _from_json(data: Dict, path: str) -> UserConfig:
    """Build a UserConfig from a loaded dict -- merge persisted slot groups over the defaults (forward-compatible)."""
    slots = _default_slots()
    for group, aliases in data.get(KEY_SLOTS, {}).items():
        slots[group] = list(aliases)
    return UserConfig(
        slots=slots,
        visible=dict(data.get(KEY_VISIBLE, {})),
        theme=data.get(KEY_THEME, DEFAULT_THEME),
        status_ttl_seconds=float(data.get(KEY_STATUS_TTL, DEFAULT_STATUS_TTL_SECONDS)),
        scroll_delta=int(data.get(KEY_SCROLL_DELTA, DEFAULT_SCROLL_DELTA)),
        page_overlap=int(data.get(KEY_PAGE_OVERLAP, DEFAULT_PAGE_OVERLAP)),
        content_collapsed_default=bool(data.get(KEY_CONTENT_COLLAPSED_DEFAULT, DEFAULT_CONTENT_COLLAPSED)),
        path=path,
    )


def load(path: str = '') -> UserConfig:
    """Load the user config from ``path`` (or the NAMED default path). Missing file -> defaults (first run).

    Fail LOUD on malformed JSON -- a corrupt / botched-hand-edit file RAISES (``json.JSONDecodeError``); we do
    NOT silently reset to defaults, which would hide the corruption. Only a MISSING file yields defaults.
    """
    resolved = path or default_config_path()
    if not os.path.exists(resolved):
        cfg = UserConfig()
        cfg.path = resolved
        return cfg
    with open(resolved, 'r', encoding='utf-8') as fh:
        data = json.load(fh)            # malformed -> JSONDecodeError, fail loud (NOT caught)
    return _from_json(data, resolved)


def save(cfg: UserConfig, path: str = '') -> str:
    """Persist the config as JSON, creating the parent dir on first save. Returns the written path."""
    resolved = path or cfg.path or default_config_path()
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(resolved, 'w', encoding='utf-8') as fh:
        json.dump(cfg.to_json(), fh, indent=2, sort_keys=True)
    cfg.path = resolved
    return resolved
