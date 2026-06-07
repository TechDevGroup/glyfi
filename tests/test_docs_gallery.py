"""Tests for the gallery's DETERMINISTIC, neutral capture -- the committed artifacts must be reproducible.

The generated docs embed a details bar whose live ``cwd`` / ``localtime`` fields would otherwise leak the real
working directory and the real wall clock (both machine-specific / non-deterministic). The gallery pins those
two fields to fixed neutral placeholders for its capture run only; these tests assert the output is byte-stable
across runs, carries the neutral placeholders, and never embeds the real working directory in any form.
"""
import os

from glyfi.contrib.docs_capture.gallery import (
    DETERMINISTIC_CWD, DETERMINISTIC_LOCALTIME, build_gallery, build_walkthrough,
)


def _home_abbreviated(path):
    """The ``~``-abbreviated form of ``path`` when it is under $HOME, else None."""
    home = os.environ.get('HOME', '')
    if home and path.startswith(home):
        return '~' + path[len(home):]
    return None


def test_gallery_is_byte_stable_across_runs():
    assert build_gallery() == build_gallery()


def test_walkthrough_is_byte_stable_across_runs():
    assert build_walkthrough() == build_walkthrough()


def test_gallery_carries_neutral_placeholders():
    out = build_gallery()
    assert DETERMINISTIC_CWD in out          # the pinned working-dir placeholder
    assert DETERMINISTIC_LOCALTIME in out    # the pinned fixed clock


def test_neutral_cwd_placeholder_is_machine_independent():
    # the placeholder is a fixed value, never the real working directory or its abbreviated form
    assert DETERMINISTIC_CWD == '~/glyfi'
    real_cwd = os.getcwd()
    assert DETERMINISTIC_CWD != real_cwd
    assert DETERMINISTIC_CWD != _home_abbreviated(real_cwd)


def test_gallery_does_not_leak_real_cwd():
    out = build_gallery()
    real_cwd = os.getcwd()
    assert real_cwd not in out               # the live working directory never appears
    abbreviated = _home_abbreviated(real_cwd)
    if abbreviated is not None:
        assert abbreviated not in out        # nor its $HOME-abbreviated form


def test_walkthrough_does_not_leak_real_cwd():
    out = build_walkthrough()
    real_cwd = os.getcwd()
    assert real_cwd not in out
    abbreviated = _home_abbreviated(real_cwd)
    if abbreviated is not None:
        assert abbreviated not in out
