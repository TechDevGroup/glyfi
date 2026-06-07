"""Tests for the ``/capture`` command -- pushes MD lines via an injected capture cap; graceful when absent."""
import os

from glyfi.contrib.docs_capture.capture import FENCE_MARKER
from glyfi.contrib.docs_capture.plugin import STATUS_NO_CAP, capture_handler
from glyfi.plugins.commands import CommandContext, CommandInvocation


def _ctx(captured_lines, captured_status, *, frame=None, region=None):
    return CommandContext(
        push_lines=lambda lines: captured_lines.extend(lines),
        push_status=lambda s: captured_status.append(s),
        open_widget=lambda name: None,
        emit=lambda ev: None,
        capture_frame=frame,
        capture_region=region,
    )


def test_capture_frame_pushes_md_screen_fence_lines():
    lines, status = [], []
    ctx = _ctx(lines, status, frame=lambda: ['hello', 'world'])
    result = capture_handler(CommandInvocation(name='capture'), ctx)
    # the applier would push result.lines; the handler returns them
    assert result.lines
    assert result.lines[0].startswith(FENCE_MARKER * 3)        # a tilde-fenced MD block
    assert any('hello' in ln for ln in result.lines)
    assert result.status and 'frame' in result.status


def test_capture_region_uses_capture_region_cap():
    captured = {}

    def region_cap(name):
        captured['name'] = name
        return ['region-content']

    ctx = _ctx([], [], region=region_cap)
    result = capture_handler(CommandInvocation(name='capture', positionals={'region': 'content'}), ctx)
    assert captured['name'] == 'content'
    assert any('region-content' in ln for ln in result.lines)
    assert "'content'" in result.status


def test_capture_capability_absent_is_graceful():
    # no capture_frame wired -> a clear status, no crash, no lines
    ctx = _ctx([], [], frame=None)
    result = capture_handler(CommandInvocation(name='capture'), ctx)
    assert result.status == STATUS_NO_CAP
    assert not result.lines


def test_capture_region_capability_absent_is_graceful():
    ctx = _ctx([], [], region=None)
    result = capture_handler(CommandInvocation(name='capture', positionals={'region': 'title'}), ctx)
    assert result.status == STATUS_NO_CAP


def test_capture_save_flag_writes_a_file(tmp_path):
    path = os.path.join(str(tmp_path), 'out', 'cap.md')
    ctx = _ctx([], [], frame=lambda: ['x'])
    result = capture_handler(
        CommandInvocation(name='capture', flags={'save': path}), ctx)
    assert os.path.isfile(path)
    with open(path, encoding='utf-8') as fh:
        body = fh.read()
    assert FENCE_MARKER * 3 in body
    assert path in result.status


# ===== the live command_context wires the capture caps (end-to-end through the VM) =========================

def _driver():
    from glyfi.uitest.fixtures import build_mock_context, MockTransport
    return build_mock_context(MockTransport()).driver


def _capture_spec():
    """Build the ``/capture`` CommandSpec straight from the builtin manifest (no GLOBAL registry mutation).

    The global palette registry is loaded exactly ONCE per test session by the app-smoke bootstrap (a second
    full ``load_plugins`` is a fail-loud collision by design), so these tests build the spec LOCALLY from the
    manifest file and run it through a local pipeline -- exercising the real manifest + handler resolution
    without polluting the shared registry.
    """
    import os
    from glyfi.plugins.sources import load_manifest_file, build_command_spec
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, 'glyfi', 'plugins', 'builtin', 'docs_capture.json')
    manifest = load_manifest_file(path)
    (mc,) = manifest.commands
    return build_command_spec(mc, source=path)


def test_vm_command_context_wires_capture_caps():
    d = _driver()
    ctx = d.vm.command_context()
    assert ctx.capture_frame is not None and ctx.capture_region is not None
    frame = ctx.capture_frame()
    assert frame and all(isinstance(r, str) for r in frame)
    title_rows = ctx.capture_region('title')
    assert title_rows and 'glyfi' in title_rows[0]


def test_capture_command_runs_end_to_end_through_the_pipeline():
    from glyfi.plugins.commands import CommandPipeline
    spec = _capture_spec()
    d = _driver()
    before = list(d.region('content'))
    # a local pipeline resolving ONLY our spec -- the real parse/dispatch/apply path against the live VM caps
    pipeline = CommandPipeline(resolve=lambda name: spec if name == spec.name else None)
    pipeline.run('/capture', d.vm.command_context())
    d.render()
    after = d.region('content')
    assert len(after) >= len(before)                  # the fence lines were pushed into content
    assert any(FENCE_MARKER in ln for ln in after)    # a screen fence landed in the content view


# ===== manifest refs resolve ===============================================================================

def test_manifest_handler_ref_resolves():
    from glyfi.plugins.handlers import resolve_callable
    handler = resolve_callable('glyfi.contrib.docs_capture.plugin:capture_handler')
    assert handler is capture_handler


def test_builtin_manifest_builds_the_capture_spec():
    spec = _capture_spec()
    assert spec.name == 'capture'
    assert spec.handler is capture_handler
    # the optional positional + the --save flag survived the manifest -> ArgSchema translation
    assert spec.arg_schema.positionals[0].name == 'region'
    assert spec.arg_schema.positionals[0].required is False
    assert 'save' in spec.arg_schema.flags
