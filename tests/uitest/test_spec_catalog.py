"""The spec CATALOG is runnable end to end -- every concern-grouped spec drives + conforms (the docs source of truth).

This iterates the WHOLE catalog and ``run_strict()``s each spec, so the generated spec docs (which run the SAME
flows) provably come from tested behavior. CI-safe: mock transport, virtual clock, no network (the context-pane
spec captures the no-key state).
"""
import os

import pytest

from glyfi.ui.config_store import ENV_CONFIG
from glyfi.uitest import catalog as C
from glyfi.contrib.openai_pane.client import ENV_API_KEY


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    os.environ.pop(ENV_API_KEY, None)            # the context-pane spec must capture the NO-KEY state (no network)
    yield
    os.environ.pop(ENV_CONFIG, None)


def test_catalog_has_concerns_each_with_at_least_one_spec():
    concerns = C.concerns()
    assert concerns, 'the catalog must expose at least one concern'
    for concern in concerns:
        assert C.specs_for(concern), f'concern {concern!r} must have at least one spec'


def test_catalog_specs_are_partitioned_by_concern():
    # every spec is reachable through specs_for(its concern); the union is the whole catalog (no orphans).
    grouped = [spec for concern in C.concerns() for spec in C.specs_for(concern)]
    assert len(grouped) == len(C.all_specs())


@pytest.mark.parametrize('spec', C.all_specs(), ids=lambda s: f'{s.concern}::{s.name}')
def test_every_catalog_spec_runs_and_conforms(spec):
    spec.run_strict()         # raises FlowError (located violation + trace) on a non-conforming THEN


def test_each_spec_carries_given_when_then_text():
    for spec in C.all_specs():
        assert spec.given and spec.when and spec.then, f'{spec.name} must carry full Given/When/Then text'
