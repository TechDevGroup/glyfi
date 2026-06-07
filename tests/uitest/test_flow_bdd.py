"""Structure tests for the FLOW + BDD layers -- a flow drives + checks; a failing flow LOCATES; BDD reports.

Asserts the orchestration layers (not a TUI feature): Flow.run returns a result + trace; a passing flow conforms;
a failing flow's result carries the located violation; run_strict raises FlowError with the trace; the BDD
Feature/Scenario compiles to a flow + renders a readable report; the phrase registry is open/closed.
"""
import os
import curses
import pytest

from glyfi.ui.config_store import ENV_CONFIG
import glyfi.uitest as U
from glyfi.uitest.flow import FlowError
from glyfi.uitest.bdd import register_phrase, CLAUSE_THEN


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def test_flow_passes_and_records_trace():
    res = (U.Flow('open-palette')
           .given(U.fresh_app())
           .when(U.Press('/'))
           .then(U.mode_is('PALETTE'))
           .run())
    assert res.passed
    assert len(res.trace) == 1
    assert res.trace[0].step.startswith('Press')


def test_flow_fail_carries_located_violation_and_trace():
    res = (U.Flow('bad-expectation')
           .given(U.fresh_app())
           .when(U.Press('/'))
           .then(U.mode_is('CONFIG'))      # wrong on purpose
           .run())
    assert not res.passed
    v = res.result.violations[0]
    assert v.locus == 'mode' and v.expected == 'CONFIG' and v.observed == 'PALETTE'


def test_flow_run_strict_raises_with_trace_dump():
    flow = (U.Flow('strict-fail')
            .given(U.fresh_app())
            .when(U.Press('/'))
            .then(U.mode_is('CONFIG')))
    with pytest.raises(FlowError) as exc:
        flow.run_strict()
    assert 'CONFIG' in str(exc.value)
    assert 'trace' in str(exc.value).lower()
    assert exc.value.result.violations[0].observed == 'PALETTE'


def test_flow_requires_a_base_first_fixture():
    with pytest.raises(ValueError):
        (U.Flow('no-base').given(U.scripted_server({})).when(U.Press('/')).then(U.mode_is('PALETTE')).run())


def test_flow_requires_a_then():
    with pytest.raises(ValueError):
        U.Flow('no-then').given(U.fresh_app()).when(U.Press('/')).run()


def test_flow_then_accepts_a_terse_spec():
    res = (U.Flow('terse-then')
           .given(U.fresh_app())
           .when(U.Press('/'), U.Type('config'), U.Press(curses.KEY_ENTER))
           .then(U.parse_constraint('mode==CONFIG & cell_highlighted(state)'))
           .run())
    assert res.passed, res.result.describe()


def test_bdd_scenario_compiles_and_passes():
    sc = (U.Scenario('palette opens CONFIG')
          .given('a fresh app')
          .when('I press', '/')
          .when('I type', 'config')
          .when('I press', curses.KEY_ENTER)
          .then('the app conforms to', 'mode==CONFIG & cell_highlighted(state)'))
    res = sc.run()
    assert res.passed, res.result.describe()


def test_bdd_feature_report_renders():
    feat = U.Feature('palette')
    (feat.scenario('opens config')
     .given('a fresh app').when('I press', '/').when('I type', 'config')
     .when('I press', curses.KEY_ENTER).then('mode is', 'CONFIG'))
    (feat.scenario('a deliberate fail')
     .given('a fresh app').when('I press', '/').then('mode is', 'CONFIG'))   # wrong: it's PALETTE
    report = feat.run()
    rendered = report.render()
    assert 'Feature: palette' in rendered
    assert 'PASS' in rendered and 'FAIL' in rendered
    assert not report.ok
    assert '1/2' in rendered


def test_bdd_unknown_phrase_fails_loud():
    sc = U.Scenario('bogus').given('a fresh app').when('I do nonsense').then('mode is', 'NORMAL')
    with pytest.raises(KeyError):
        sc.compile()


def test_register_phrase_open_closed():
    key = 'the seq stays zero'
    try:
        register_phrase(CLAUSE_THEN, key, lambda: U.seq_is(0))
    except ValueError:
        pass  # already registered by a prior run in the same session
    sc = (U.Scenario('phrase probe').given('a fresh app').when('I press', '/').then(key))
    assert sc.run().passed
