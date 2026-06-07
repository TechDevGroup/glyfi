"""Structure tests for the uitest FIXTURES + the MockTransport -- the server-free, scripted hook-in point.

Asserts the mock/fixture layer (not a TUI feature): the MockTransport stays behind the transport PORT and scripts
responses/faults; the full headless stack builds from a mock; fixtures compose (base + layers) and are open/closed;
seeding a transcript walks ONE real turn per entry (no auto-loop).
"""
import os
import pytest

from glyfi.ui.config_store import ENV_CONFIG
from glyfi.transport import Transport
from glyfi.protocol import ProtocolError, TurnRequest
import glyfi.uitest as U
from glyfi.uitest.fixtures import (
    MockTransport, ScriptedFault, build_mock_context, register_fixture, known_fixtures, Fixture,
)


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def test_mock_is_a_transport_port():
    assert isinstance(MockTransport(), Transport)


def test_mock_default_echo_response_advances_seq():
    mt = MockTransport()
    ctx = build_mock_context(mt)
    rec = ctx.driver.vm.step('hello', 'subj-1')
    assert rec.ok
    assert rec.staged_content == 'staged:hello'
    assert ctx.driver.vm.session.seq == 1
    assert len(mt.sent) == 1                  # exactly one request issued for one step


def test_mock_scripted_response():
    mt = MockTransport().script_response('subj-7', 'chat', 'go', 'CUSTOM-OUT')
    ctx = build_mock_context(mt)
    rec = ctx.driver.vm.step('go', 'subj-7')
    assert rec.staged_content == 'CUSTOM-OUT'


def test_mock_scripted_fault_is_captured_seq_not_advanced():
    mt = MockTransport().script_fault('subj-9', 'chat', 'denyme',
                                      message='turn was gated', type='turn_gate_denied', code=403)
    ctx = build_mock_context(mt)
    rec = ctx.driver.vm.step('denyme', 'subj-9')
    assert not rec.ok
    assert '403' in rec.error and 'turn_gate_denied' in rec.error
    assert ctx.driver.vm.session.seq == 0     # fail-loud: seq does NOT advance on a faulted turn


def test_mock_wildcard_match():
    mt = MockTransport().script_response(MockTransport.ANY, MockTransport.ANY, MockTransport.ANY, 'WILD')
    ctx = build_mock_context(mt)
    assert ctx.driver.vm.step('anything', 'subj-x').staged_content == 'WILD'


def test_mock_default_disabled_is_404():
    mt = MockTransport(default_enabled=False)
    ctx = build_mock_context(mt)
    rec = ctx.driver.vm.step('unscripted', 'subj-z')
    assert not rec.ok and '404' in rec.error


def test_mock_list_subjects():
    mt = MockTransport(subjects=[{'subject': 'subj-1', 'label': 'alpha'}])
    assert mt.list_subjects()[0]['label'] == 'alpha'


def test_mock_empty_messages_fails_loud():
    mt = MockTransport()
    with pytest.raises(ProtocolError):
        mt.send(TurnRequest(session_id='s', seq=0, messages=[], mode='chat'))


def test_fresh_app_is_a_base_fixture():
    fx = U.fresh_app()
    assert fx.base
    ctx = fx.setup(None)
    assert ctx.driver.vm.mode_ui == 'NORMAL'


def test_layer_fixture_requires_a_base():
    with pytest.raises(ValueError):
        U.scripted_server({}).setup(None)


def test_seeded_transcript_walks_one_turn_per_entry():
    mt = MockTransport()
    ctx = U.fresh_app(transport=mt).setup(None)
    ctx = U.seeded_transcript([('subj-1', 'a'), ('subj-2', 'b'), ('subj-3', 'c')]).setup(ctx)
    assert ctx.driver.vm.model.turn_count == 3
    assert len(mt.sent) == 3                    # exactly N requests for N seeded turns -- no auto-loop multiplier
    assert ctx.driver.vm.session.seq == 3


def test_with_prompt_entry_wires_one_shot_prompt():
    ctx = U.fresh_app().setup(None)
    ctx = U.with_prompt_entry('subj-5', 'driven-text').setup(ctx)
    ctx.driver.invoke('request_prompt')         # walks the wired entry once
    assert ctx.driver.vm.model.turn_count == 1
    ctx.driver.invoke('request_prompt')         # prompt consumed -> a cancel, NOT a silent re-walk
    assert ctx.driver.vm.model.turn_count == 1


def test_at_size_resizes():
    ctx = U.fresh_app().setup(None)
    ctx = U.at_size(40, 12).setup(ctx)
    assert ctx.driver.view._size.w == 40


def test_register_fixture_open_closed_and_dup_guard():
    name = 'noop_fixture_probe'
    if name not in known_fixtures():
        register_fixture(name, lambda: Fixture(name=name, setup=lambda c: c))
    assert name in known_fixtures()
    with pytest.raises(ValueError):
        register_fixture('fresh_app', U.fresh_app)
