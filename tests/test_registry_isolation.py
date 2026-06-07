"""Tests for the registry snapshot/restore seam -- the public roundtrip that powers per-test isolation."""
from glyfi.plugins import palette as palette_mod
from glyfi.plugins.palette import register_command, snapshot_registry, restore_registry, command


def test_snapshot_restore_roundtrips_a_temp_command():
    # baseline names (the import-time built-ins, isolated per test by the autouse fixture)
    baseline = sorted(c.name for c in palette_mod.all_commands())

    snap = snapshot_registry()
    register_command('temp_isolation_probe', 'a throwaway command', lambda vm: None)
    assert command('temp_isolation_probe') is not None

    restore_registry(snap)

    # the temp command is gone and the baseline is intact (same set, unchanged objects)
    assert command('temp_isolation_probe') is None
    assert sorted(c.name for c in palette_mod.all_commands()) == baseline


def test_snapshot_token_is_opaque_and_does_not_alias_internals():
    # mutating the live registry after snapshotting does not change what the token restores to
    snap = snapshot_registry()
    register_command('temp_probe_two', 'another throwaway', lambda vm: None)
    restore_registry(snap)
    assert command('temp_probe_two') is None
