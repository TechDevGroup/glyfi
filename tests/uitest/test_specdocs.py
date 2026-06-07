"""The spec-doc GENERATOR is deterministic, one-file-per-spec + an index, and leaks no machine/trace specifics.

Asserts: ``generate_spec_docs`` is byte-stable across two calls; it emits exactly one file per catalog spec plus
the index; every spec file carries at least one full-frame screen fence; and no generated file leaks the real
cwd / wall clock or any forbidden token.
"""
import os
import re

import pytest

from glyfi.ui.config_store import ENV_CONFIG
from glyfi.contrib.openai_pane.client import ENV_API_KEY
from glyfi.uitest import catalog as C
from glyfi.contrib.docs_capture import specdocs


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    os.environ.pop(ENV_API_KEY, None)
    yield
    os.environ.pop(ENV_CONFIG, None)


def test_generate_is_byte_stable_across_two_calls():
    first = specdocs.generate_spec_docs()
    second = specdocs.generate_spec_docs()
    assert first == second                       # identical keys AND identical bytes per file


def test_one_file_per_spec_plus_the_index():
    docs = specdocs.generate_spec_docs()
    index_key = f'{specdocs.SPECS_DIRNAME}/{specdocs.INDEX_NAME}'
    assert index_key in docs
    spec_files = [k for k in docs if k != index_key]
    assert len(spec_files) == len(C.all_specs())
    # every spec key is specs/<concern>/<spec>.md and unique
    assert len(set(spec_files)) == len(spec_files)
    for key in spec_files:
        assert key.startswith(f'{specdocs.SPECS_DIRNAME}/') and key.endswith('.md')
        assert 'glyph' not in key                # slugs / filenames must not contain the forbidden token


def test_every_spec_file_has_a_full_frame_fence():
    docs = specdocs.generate_spec_docs()
    index_key = f'{specdocs.SPECS_DIRNAME}/{specdocs.INDEX_NAME}'
    for key, text in docs.items():
        if key == index_key:
            continue
        assert '~~~text' in text, f'{key} must carry at least one full-frame screen fence'


def test_index_links_every_concern_and_spec():
    docs = specdocs.generate_spec_docs()
    index = docs[f'{specdocs.SPECS_DIRNAME}/{specdocs.INDEX_NAME}']
    for concern in C.concerns():
        assert f'## {concern}' in index
    for spec in C.all_specs():
        assert f'[{spec.name}]' in index


_FORBIDDEN = re.compile(
    r'glyph|glyphon|glyphlang|wordnet|silo|molecule|codec|preamble|directive|'
    r'glyphon_id|anthropic|co-authored|glyphmon',
    re.IGNORECASE,
)


def test_no_forbidden_or_machine_specific_leak():
    docs = specdocs.generate_spec_docs()
    real_cwd = os.getcwd()
    for key, text in docs.items():
        assert not _FORBIDDEN.search(text), f'forbidden token leaked into {key}'
        assert real_cwd not in text, f'the real cwd leaked into {key}'


def test_write_spec_docs_writes_the_tree(tmp_path):
    root = str(tmp_path / 'docs')
    written = specdocs.write_spec_docs(root=root)
    assert written == sorted(written)
    # one file per spec + the index, all present on disk
    assert len(written) == len(C.all_specs()) + 1
    for path in written:
        assert os.path.isfile(path)
    # a second write is byte-identical (determinism on disk)
    snapshot = {p: open(p, encoding='utf-8').read() for p in written}
    specdocs.write_spec_docs(root=root)
    for p, content in snapshot.items():
        assert open(p, encoding='utf-8').read() == content
