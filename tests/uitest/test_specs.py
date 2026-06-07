"""BDD SPECS exercising the REAL TUI through the constraint framework -- the integration proof + downstream driver.

These are runnable flows over the ACTUAL ``glyfi.ui`` MVVM (mocked transport, virtual clock) -- so they
demonstrate the framework AND pin the core TUI behaviors. They are the "interface with the system to drive
interactions autonomously" surface, headless + CI-safe (no live server).

Covered: command palette -> CONFIG + highlight; ephemeral ticker TTL + Tab ring; input history Up; bottom-anchored
content + PgUp; the one-turn law (exactly one TurnRecorded, seq advanced) + the scripted-fault fail-loud path.
"""
import os
import curses
import pytest

from glyfi.ui.config_store import ENV_CONFIG, UserConfig
from glyfi.ui.ticker import DEFAULT_STATUS_TTL_SECONDS
import glyfi.uitest as U
from glyfi.uitest.fixtures import MockTransport


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    os.environ[ENV_CONFIG] = str(tmp_path / 'config.json')
    yield
    os.environ.pop(ENV_CONFIG, None)


# ===== SPEC 1 -- command palette ===========================================================================
# Given a fresh app, When I open the palette, filter to `config`, and Enter,
# Then mode==CONFIG and the targeted area (state strip) is highlighted.
def test_spec_command_palette_opens_config():
    (U.Flow('command palette filters to config and opens it')
     .given(U.fresh_app())
     .when(U.Press('/'), U.Type('config'), U.Press(curses.KEY_ENTER))
     .then(U.parse_constraint('mode==CONFIG & cell_highlighted(state)'))
     .run_strict())


# ===== SPEC 2 -- ephemeral ticker ==========================================================================
# Given a pushed status, Then status_is(...); When time passes past the TTL, Then status_blank();
# When I press Tab, Then the ring advanced (hints provider shown) AND TickerCycled emitted.
def test_spec_ephemeral_ticker_ttl_and_ring():
    ttl = DEFAULT_STATUS_TTL_SECONDS
    ctx = U.new_context(config=UserConfig(status_ttl_seconds=ttl))
    ctx.driver.vm.push_status('a transient notice')
    ctx.driver.render()
    assert U.status_is('a transient notice').check(ctx.probe()).holds
    # time passes past the TTL -> the ephemeral line goes blank (autonomous wait on the virtual clock)
    U.WaitUntil(U.status_blank(), timeout=ttl * 3, poll=1.0).run(ctx)
    assert U.status_blank().check(ctx.probe()).holds
    # Tab advances the ring AND emits TickerCycled
    U.ClearEvents().run(ctx)
    U.Tab().run(ctx)
    p = ctx.probe()
    assert U.event_emitted('TickerCycled').check(p).holds
    # the ring's first Tab lands on the 'status' provider head; a second Tab advances to 'hints'
    U.Tab().run(ctx)
    from glyfi.ui.ticker import INPUT_HINT
    assert U.status_is(INPUT_HINT).check(ctx.probe()).holds


# ===== SPEC 3 -- input history =============================================================================
# Given two submitted inputs, When I press Up twice, Then input_is(<older entry>) and HistoryNavigated emitted.
def test_spec_input_history_up_recall():
    ctx = U.new_context()
    # submit two inputs (the manual way -- type then Enter, one at a time)
    U.Type('first-entry').run(ctx)
    U.Press(curses.KEY_ENTER).run(ctx)
    U.Type('second-entry').run(ctx)
    U.Press(curses.KEY_ENTER).run(ctx)
    U.ClearEvents().run(ctx)
    U.Press(curses.KEY_UP).run(ctx)         # -> newest recalled ('second-entry')
    U.Press(curses.KEY_UP).run(ctx)         # -> older ('first-entry')
    p = ctx.probe()
    from glyfi.ui.settings import INPUT_PROMPT
    assert U.input_is(f'{INPUT_PROMPT}first-entry').check(p).holds, p.input_line
    assert U.event_emitted('HistoryNavigated').check(p).holds


# ===== SPEC 4 -- bottom-anchored content ===================================================================
# Given a seeded transcript of N turns, Then the NEWEST turn occupies the BOTTOM row of the content region;
# When I press PgUp, Then older turns are revealed.
def test_spec_bottom_anchored_content_and_pgup():
    turns = [('subj-1', 'msg-one'), ('subj-2', 'msg-two'), ('subj-3', 'msg-three')]
    ctx = U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)).setup(None)
    ctx = U.seeded_transcript(turns).setup(ctx)
    p = ctx.probe()
    content = p.regions['content']
    # the NEWEST turn's user text is in the LAST content lines (bottom-anchored)
    assert 'msg-three' in content[-1] or "'msg-three'" in '\n'.join(content[-2:]), content
    # the freshest turn lives at the bottom; the oldest is NOT visible until we scroll up on a tiny window
    ctx2 = U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)).setup(None)
    ctx2 = U.at_size(60, 10).setup(ctx2)            # small window so older turns scroll off
    ctx2 = U.seeded_transcript([(f'subj-{i}', f'm{i}') for i in range(8)]).setup(ctx2)
    before = '\n'.join(ctx2.probe().regions['content'])
    U.Press(curses.KEY_PPAGE).run(ctx2)             # PgUp reveals older turns
    after = '\n'.join(ctx2.probe().regions['content'])
    assert before != after, 'PgUp should reveal older content'


# ===== SPEC 5 -- the ONE-TURN LAW + the scripted-fault fail-loud path =======================================
# Given a scripted transport, When I invoke 'request_prompt' ONCE, Then transcript_len==1 AND exactly ONE
# TurnRecorded AND seq advanced -- proving NO auto-loop. Then a scripted fault shows the envelope + seq NOT advanced.
def test_spec_one_turn_law_no_autoloop():
    mt = MockTransport().script_response('subj-7', 'chat', 'send it', 'STAGED-7')
    (U.Flow('invoke request_prompt walks EXACTLY one turn -- no auto-loop')
     .given(U.fresh_app(transport=mt),
            U.with_prompt_entry('subj-7', 'send it'))
     .when(U.ClearEvents(), U.Invoke('request_prompt'))   # ClearEvents scopes the count to this one step
     .then(U.transcript_len(1),
           U.event_count('TurnRecorded', 1),
           U.seq_is(1),
           U.region_contains('content', 'STAGED-7'))
     .run_strict())
    assert len(mt.sent) == 1                          # exactly ONE request issued for ONE prompt


def test_spec_fault_is_fail_loud_seq_not_advanced():
    mt = MockTransport().script_fault('subj-9', 'chat', 'forbidden',
                                      message='turn was gated', type='turn_gate_denied', code=403)
    ctx = U.fresh_app(transport=mt).setup(None)
    ctx = U.with_prompt_entry('subj-9', 'forbidden').setup(ctx)
    U.ClearEvents().run(ctx)
    U.Invoke('request_prompt').run(ctx)
    p = ctx.probe()
    # the fault is SHOWN (the failed turn's record carries the 403 in the transcript) and the seq did NOT advance
    assert U.transcript_len(1).check(p).holds
    assert U.seq_is(0).check(p).holds, 'a faulted turn must NOT advance the seq'
    assert U.region_contains('content', '403').check(p).holds or \
           U.region_contains('content', 'ERR').check(p).holds, p.regions['content']
    # exactly one TurnRecorded even on the fault path -- still one explicit turn, no retry-loop
    assert U.event_count('TurnRecorded', 1).check(p).holds
