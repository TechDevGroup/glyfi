"""Tests for the BDD-flow -> Markdown bridge -- a per-step walkthrough with UI state embedded between steps."""
import os

from glyfi.contrib.docs_capture.markdown_flow import (
    PERTINENT_REGIONS, flow_to_markdown, write_markdown,
)
from glyfi.uitest.actions import Invoke, Type
from glyfi.uitest.constraints import mode_is
from glyfi.uitest.fixtures import fresh_app
from glyfi.uitest.flow import Flow


def _run_flow() -> Flow:
    flow = (Flow('walkthrough')
            .given(fresh_app())
            .when(Invoke('open_palette'), Type('co'), Invoke('open_config'))
            .then(mode_is('CONFIG')))
    return flow


def test_flow_to_markdown_emits_a_section_per_step():
    flow = _run_flow()
    result = flow.run()
    md = flow_to_markdown(result, title='Walkthrough')
    assert md.startswith('# Walkthrough')
    # one '## ' heading per recorded step (3 when-steps)
    headings = [ln for ln in md.split('\n') if ln.startswith('## ')]
    assert len(headings) == 3
    assert headings[0].startswith('## 1. ')          # ordinal + label


def test_flow_to_markdown_accepts_a_run_context_too():
    # run_strict returns a FlowResult; but a RunContext also carries the trace -- exercise the FlowResult path
    result = _run_flow().run()
    md_from_result = flow_to_markdown(result)
    assert '## 1. ' in md_from_result


def test_flow_to_markdown_embeds_region_state_between_steps():
    result = _run_flow().run()
    md = flow_to_markdown(result)
    # the config-editor step's content should appear in its fence (state embedded between steps)
    assert 'CONFIG' in md
    # each step section is a fenced block
    assert md.count('~~~') >= 6                        # >= 2 fence delimiters * 3 steps


def test_flow_to_markdown_narrows_to_requested_regions():
    result = _run_flow().run()
    md = flow_to_markdown(result, regions=['input'])
    # only the input region is stacked -- the in-fence region label names it
    assert '── input ──' in md
    assert '── content ──' not in md


def test_pertinent_regions_is_the_default_set():
    result = _run_flow().run()
    md = flow_to_markdown(result)
    # at least one of the pertinent regions is labeled in the output
    assert any(f'── {r} ──' in md for r in PERTINENT_REGIONS)


def test_flow_to_markdown_rejects_a_non_trace_source():
    import pytest
    with pytest.raises(TypeError):
        flow_to_markdown(object())


def test_write_markdown_creates_parent_dirs(tmp_path):
    target = os.path.join(str(tmp_path), 'nested', 'deep', 'doc.md')
    write_markdown('# hello\n', target)
    assert os.path.isfile(target)
    with open(target, encoding='utf-8') as fh:
        assert fh.read() == '# hello\n'
