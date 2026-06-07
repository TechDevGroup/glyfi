"""Tests for the persisted user UI config (JSON round-trip, default-on-missing, fail-loud on malformed)."""
import json
import os
import pytest

from glyfi.ui.config_store import (
    UserConfig, load, save, default_config_path, ENV_CONFIG,
    SLOT_STATE, SLOT_DETAILS_LEFT, SLOT_DETAILS_RIGHT, DEFAULT_STATE_SLOTS,
    DEFAULT_SCROLL_DELTA, DEFAULT_PAGE_OVERLAP, KEY_SCROLL_DELTA, KEY_PAGE_OVERLAP,
)
from glyfi.ui.ticker import DEFAULT_STATUS_TTL_SECONDS


def test_default_path_honors_named_env(monkeypatch, tmp_path):
    target = str(tmp_path / 'custom.json')
    monkeypatch.setenv(ENV_CONFIG, target)
    assert default_config_path() == target


def test_load_missing_file_yields_defaults(tmp_path):
    path = str(tmp_path / 'absent.json')
    cfg = load(path)
    assert list(cfg.slots[SLOT_STATE]) == list(DEFAULT_STATE_SLOTS)
    assert cfg.is_visible('state') is True
    assert cfg.path == path


def test_save_then_load_round_trips(tmp_path):
    path = str(tmp_path / 'config.json')
    cfg = UserConfig()
    cfg.slots[SLOT_STATE] = ['session', 'seq']
    cfg.visible['details'] = False
    cfg.theme = 'maroon-select'
    written = save(cfg, path)
    assert os.path.exists(written)
    reloaded = load(path)
    assert reloaded.slots[SLOT_STATE] == ['session', 'seq']
    assert reloaded.is_visible('details') is False
    assert reloaded.theme == 'maroon-select'


def test_save_creates_parent_dir(tmp_path):
    path = str(tmp_path / 'nested' / 'dir' / 'config.json')
    save(UserConfig(), path)
    assert os.path.exists(path)


def test_malformed_json_fails_loud(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{ this is not valid json ]')
    with pytest.raises(json.JSONDecodeError):
        load(str(path))


def test_visible_is_passive_power_user_key(tmp_path):
    path = str(tmp_path / 'config.json')
    cfg = UserConfig()
    assert cfg.is_visible('state') is True
    cfg.visible['state'] = False            # a power-user JSON edit hides a region (no interactive toggle)
    save(cfg, path)
    reloaded = load(path)
    assert reloaded.is_visible('state') is False


def test_status_ttl_round_trips_with_named_default(tmp_path):
    path = str(tmp_path / 'config.json')
    cfg = UserConfig()
    assert cfg.status_ttl_seconds == DEFAULT_STATUS_TTL_SECONDS
    cfg.status_ttl_seconds = 9.5
    save(cfg, path)
    assert load(path).status_ttl_seconds == 9.5


def test_load_merges_persisted_groups_over_defaults(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'slots': {SLOT_STATE: ['mode']}, 'visible': {}, 'theme': 'maroon-select'}))
    cfg = load(str(path))
    assert cfg.slots[SLOT_STATE] == ['mode']
    assert SLOT_DETAILS_LEFT in cfg.slots and SLOT_DETAILS_RIGHT in cfg.slots


def test_inputs_section_keys_round_trip_with_named_defaults(tmp_path):
    path = str(tmp_path / 'config.json')
    cfg = UserConfig()
    assert cfg.scroll_delta == DEFAULT_SCROLL_DELTA
    assert cfg.page_overlap == DEFAULT_PAGE_OVERLAP
    cfg.scroll_delta = 5
    cfg.page_overlap = 2
    save(cfg, path)
    reloaded = load(path)
    assert reloaded.scroll_delta == 5 and reloaded.page_overlap == 2
    with open(path, 'r', encoding='utf-8') as fh:
        on_disk = json.load(fh)
    assert on_disk[KEY_SCROLL_DELTA] == 5 and on_disk[KEY_PAGE_OVERLAP] == 2


def test_inputs_missing_keys_fall_back_to_defaults(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'slots': {}, 'visible': {}, 'theme': 'maroon-select'}))
    cfg = load(str(path))
    assert cfg.scroll_delta == DEFAULT_SCROLL_DELTA
    assert cfg.page_overlap == DEFAULT_PAGE_OVERLAP
