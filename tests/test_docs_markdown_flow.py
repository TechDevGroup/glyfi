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


def test_flow_to_markdown_full_frame_emits_one_full_frame_fence_per_step():
    result = _run_flow().run()
    md = flow_to_markdown(result, full_frame=True)
    # default is full-frame: one fence per step (3 steps) and each is a TRUE full screenshot, NOT stacked regions
    headings = [ln for ln in md.split('\n') if ln.startswith('## ')]
    assert len(headings) == 3
    # exactly one opening + one closing fence delimiter per step -> 2 per step
    assert md.count('~~~text') == 3
    # the full frame shows the whole UI -- the stacked-region in-fence labels are NOT present
    assert '── content ──' not in md
    assert '── title ──' not in md
    # and the rule fences (full-width region rules) appear -- proof it is the composed full screen, not regions
    assert '────────' in md


def test_flow_to_markdown_full_frame_is_the_default():
    result = _run_flow().run()
    assert flow_to_markdown(result) == flow_to_markdown(result, full_frame=True)


def test_flow_to_markdown_full_frame_off_falls_back_to_stacked_regions():
    result = _run_flow().run()
    md = flow_to_markdown(result, full_frame=False)
    # the legacy stacked-region rendering -- the in-fence region labels are back
    assert '── content ──' in md
    assert '── input ──' in md


def test_flow_to_markdown_narrows_to_requested_regions():
    result = _run_flow().run()
    md = flow_to_markdown(result, regions=['input'], full_frame=False)
    # only the input region is stacked -- the in-fence region label names it
    assert '── input ──' in md
    assert '── content ──' not in md


def test_pertinent_regions_is_the_default_set_for_the_stacked_fallback():
    result = _run_flow().run()
    # the pertinent set governs the STACKED fallback (full_frame off / no frame); at least one region is labeled
    md = flow_to_markdown(result, full_frame=False)
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
