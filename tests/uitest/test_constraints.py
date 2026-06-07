"""Structure tests for the uitest CONSTRAINT scope -- the Probe + oriented LOCATED conformance + the terse parser.

Asserts the constraint axis itself (not a TUI feature): a constraint returns a ConformanceResult that LOCATES the
violation (locus + target + observed-vs-expected, not a bare bool); combinators compose; the terse spec parser
round-trips and FAILS LOUD on bad syntax; the registry is open/closed.
"""
import os
import pytest

from glyfi.ui.config_store import ENV_CONFIG
import glyfi.uitest as U
from glyfi.uitest.constraints import (
    Probe, parse_constraint, register_constraint, known_constraints, SpecSyntaxError,
    LOCUS_MODE, LOCUS_STATUS, LOCUS_EVENT, LOCUS_REGION, Constraint, ConformanceResult,
)


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


def _probe():
    return Probe.of(U.new_context().driver)


def test_probe_captures_observable_surface():
    p = _probe()
    assert p.mode_ui == 'NORMAL'
    assert p.transcript_len == 0
    assert p.seq == 0
    assert 'content' in p.regions
    assert isinstance(p.event_counts, dict)


def test_constraint_holds_returns_ok():
    p = _probe()
    r = U.mode_is('NORMAL').check(p)
    assert r.holds
    assert r.violations == ()


def test_violation_is_oriented_and_located():
    p = _probe()
    r = U.mode_is('CONFIG').check(p)
    assert not r.holds
    v = r.violations[0]
    assert v.locus == LOCUS_MODE
    assert v.target == 'mode_ui'
    assert v.expected == 'CONFIG'
    assert v.observed == 'NORMAL'
    # the description carries WHAT + WHERE + observed-vs-expected (not just 'false')
    assert 'CONFIG' in v.describe() and 'NORMAL' in v.describe() and LOCUS_MODE in v.describe()


def test_status_constraint_locus():
    p = _probe()
    r = U.status_is('definitely-not-the-status').check(p)
    assert not r.holds and r.violations[0].locus == LOCUS_STATUS


def test_event_count_locates_event_axis():
    p = _probe()
    r = U.event_count('TurnRecorded', 5).check(p)
    assert not r.holds
    v = r.violations[0]
    assert v.locus == LOCUS_EVENT and v.target == 'TurnRecorded'
    assert v.expected == 'exactly 5'


def test_all_of_collects_every_failed_child():
    p = _probe()
    r = U.all_of(U.mode_is('CONFIG'), U.seq_is(99)).check(p)
    assert not r.holds
    assert len(r.violations) == 2          # BOTH children located, not short-circuited


def test_any_of_holds_when_one_child_holds():
    p = _probe()
    assert U.any_of(U.mode_is('CONFIG'), U.mode_is('NORMAL')).check(p).holds


def test_not_inverts():
    p = _probe()
    assert U.not_(U.mode_is('CONFIG')).check(p).holds
    assert not U.not_(U.mode_is('NORMAL')).check(p).holds


def test_operator_sugar_composes():
    p = _probe()
    assert (U.mode_is('NORMAL') & U.seq_is(0)).check(p).holds
    assert (U.mode_is('CONFIG') | U.mode_is('NORMAL')).check(p).holds
    assert (~U.mode_is('CONFIG')).check(p).holds


# ---- terse spec parser ------------------------------------------------------------------------------------

def test_parser_eq_sugar():
    p = _probe()
    assert parse_constraint('mode==NORMAL').check(p).holds
    assert parse_constraint('seq==0').check(p).holds
    assert parse_constraint('transcript==0').check(p).holds


def test_parser_name_call_form():
    p = _probe()
    # a zero-arg call form parses + checks (a fresh app seeds an initial status, so the line is NOT blank)
    assert not parse_constraint('status_blank()').check(p).holds
    assert parse_constraint("region_contains('content', '')").check(p).holds


def test_parser_combinators_and_negation():
    p = _probe()
    assert parse_constraint('mode==NORMAL & seq==0').check(p).holds
    assert parse_constraint('mode==CONFIG | mode==NORMAL').check(p).holds
    assert parse_constraint('!mode==CONFIG').check(p).holds
    assert parse_constraint('(mode==CONFIG | mode==NORMAL) & seq==0').check(p).holds


def test_parser_int_coercion():
    # event_count's 2nd arg is coerced to int (the registry marks the int positions)
    c = parse_constraint("event_count('TurnRecorded', 0)")
    assert c.check(_probe()).holds


def test_parser_fails_loud_on_unknown_constraint():
    with pytest.raises(KeyError):
        parse_constraint('no_such_constraint()')


def test_parser_fails_loud_on_unknown_sugar_key():
    with pytest.raises(SpecSyntaxError):
        parse_constraint('bogus==X')


def test_parser_fails_loud_on_trailing_input():
    with pytest.raises(SpecSyntaxError):
        parse_constraint('mode==NORMAL ) extra')


def test_parser_fails_loud_on_unterminated_string():
    with pytest.raises(SpecSyntaxError):
        parse_constraint("region_contains('content', 'oops)")


def test_parser_fails_loud_on_bad_int_arg():
    with pytest.raises(SpecSyntaxError):
        parse_constraint('seq==notanint')


def test_register_constraint_is_open_closed():
    name = 'always_true_probe'
    if name not in known_constraints():
        register_constraint(name, lambda: Constraint(label=name, predicate=lambda _p: ConformanceResult.ok()))
    assert name in known_constraints()
    # and the parser can now resolve it for free (dispatches on the registry)
    assert parse_constraint('always_true_probe()').check(_probe()).holds


def test_register_constraint_fails_loud_on_dup():
    with pytest.raises(ValueError):
        register_constraint('mode_is', lambda ui: U.mode_is(ui))


def test_conformance_fail_requires_a_violation():
    with pytest.raises(ValueError):
        ConformanceResult.fail()
