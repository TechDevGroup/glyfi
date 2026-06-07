"""catalog -- the runnable BDD SPECS as concern-grouped DATA (one structured source for tests + doc generation).

The BDD tests in ``tests/uitest`` construct their scenarios INLINE (they do not register into a global), so this
module re-expresses the SAME specs -- the same fixtures / actions / constraints over the SAME real ``glyfi.ui``
MVVM (mocked transport, virtual clock, headless + CI-safe) -- as an enumerable catalog. Each entry pairs the
human Given/When/Then text with a ``build_flow()`` that returns a runnable ``Flow``. A spec runs through the
ordinary flow engine, so ``run_strict()`` is the proof that the catalog mirrors the tested behavior.

The catalog is the single source the spec-doc generator enumerates AND a test iterates + runs end to end. It is
ADDITIVE: it imports the public ``glyfi.uitest`` surface + a couple of public ``glyfi.ui`` seams + stdlib only,
and constructs a few small local fixtures (from the public ``Fixture`` contract) for states the registry has no
phrase for (a pushed status, an opened widget). No network: the OpenAI-pane spec captures the no-key state.

Concerns mirror the real feature groupings: command palette, config editor, status ticker, navigation/scroll,
prompt entry, content traverse, input history, the OpenAI context pane.
"""
import curses
from dataclasses import dataclass, field
from typing import Callable, List

import glyfi.uitest as U
from glyfi.uitest.fixtures import Fixture, MockTransport
from glyfi.uitest.flow import Flow

from glyfi.ui.config_store import UserConfig
from glyfi.ui.settings import KEY_TRAVERSE
from glyfi.ui.ticker import DEFAULT_STATUS_TTL_SECONDS, INPUT_HINT
from glyfi.ui.viewmodel import UI_NORMAL, UI_TRAVERSE


# ===== the concern names (mirror the real feature groupings) ===============================================
CONCERN_COMMAND_PALETTE = 'command palette'
CONCERN_CONFIG_EDITOR = 'config editor'
CONCERN_STATUS_TICKER = 'status ticker'
CONCERN_INPUT_HISTORY = 'input history'
CONCERN_CONTENT_SCROLL = 'navigation and scroll'
CONCERN_CONTENT_TRAVERSE = 'content traverse'
CONCERN_PROMPT_ENTRY = 'prompt entry'
CONCERN_ONE_TURN_LAW = 'the one turn law'
CONCERN_OPENAI_PANE = 'the openai context pane'


@dataclass(frozen=True)
class Spec:
    """One catalog SPEC -- the human Given/When/Then text + a ``build_flow`` returning a runnable ``Flow``.

    ``concern`` is the feature grouping; ``name`` is the scenario name. ``given`` / ``when`` / ``then`` are the
    readable clause lines a doc renders above the captured frames. ``build_flow()`` constructs the SAME flow the
    text describes (the runnable proof). ``run_strict()`` drives + checks it, raising on a non-conforming THEN.
    """
    concern: str
    name: str
    given: List[str]
    when: List[str]
    then: List[str]
    build_flow: Callable[[], Flow]

    def run_strict(self) -> 'U.FlowResult':
        return self.build_flow().run_strict()


# ---- small LOCAL fixtures (built from the public Fixture contract -- states the phrase registry has none for)


def _push_status_fixture(text: str) -> Fixture:
    """A layer fixture that pushes an ephemeral status onto the ticker + repaints (the 'a status was pushed' given)."""
    def _setup(ctx):
        ctx.driver.vm.push_status(text)
        ctx.driver.render()
        return ctx
    return Fixture(name='pushed_status', setup=_setup)


def _open_widget_fixture(name: str) -> Fixture:
    """A layer fixture that opens a named widget directly (the host-owned open the never-stuck spec unwinds from)."""
    def _setup(ctx):
        ctx.driver.vm.open_widget(name)
        ctx.driver.render()
        return ctx
    return Fixture(name='open_widget', setup=_setup)


# ---- the SHARED transcript seed the navigation / traverse specs use ----------------------------------------
_LONG_TEXT = 'fn:a ' + 'x' * 120 + ' tail-marker'   # far wider than the window -> must WRAP, never ellipsize
_TRAVERSE_TURNS = [('subj-1', 'short one'), ('subj-2', 'short two'), ('subj-3', _LONG_TEXT)]


# ===== the flow builders (one per spec -- the SAME drive the tested specs run) ==============================

def _flow_palette_opens_config() -> Flow:
    return (Flow('filter to config and open it')
            .given(U.fresh_app())
            .when(U.Press('/'), U.Type('config'), U.Press(curses.KEY_ENTER))
            .then(U.parse_constraint('mode==CONFIG & cell_highlighted(state)')))


def _flow_config_editor_opens() -> Flow:
    return (Flow('the config editor opens with its bound slots')
            .given(U.fresh_app())
            .when(U.Invoke('open_config'))
            .then(U.mode_is('CONFIG'), U.cell_highlighted('state')))


def _flow_ticker_ttl_and_ring() -> Flow:
    ttl = DEFAULT_STATUS_TTL_SECONDS
    return (Flow('a pushed status expires after its TTL and Tab cycles the ring')
            .given(U.fresh_app(config=UserConfig(status_ttl_seconds=ttl)),
                   _push_status_fixture('a transient notice'))
            .when(U.Delay(ttl * 3), U.ClearEvents(), U.Tab(), U.Tab())
            .then(U.status_is(INPUT_HINT), U.event_emitted('TickerCycled')))


def _flow_input_history_up() -> Flow:
    from glyfi.ui.settings import INPUT_PROMPT
    return (Flow('Up recalls older submitted inputs')
            .given(U.fresh_app())
            .when(U.Type('first-entry'), U.Press(curses.KEY_ENTER),
                  U.Type('second-entry'), U.Press(curses.KEY_ENTER),
                  U.ClearEvents(), U.Press(curses.KEY_UP), U.Press(curses.KEY_UP))
            .then(U.input_is(f'{INPUT_PROMPT}first-entry'), U.event_emitted('HistoryNavigated')))


def _flow_bottom_anchored_pgup() -> Flow:
    turns = [(f'subj-{i}', f'm{i}') for i in range(8)]
    return (Flow('PgUp reveals older turns above the bottom-anchored newest')
            .given(U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)),
                   U.at_size(60, 10), U.seeded_transcript(turns))
            .when(U.Press(curses.KEY_PPAGE))
            .then(U.no_ellipsis('content')))


def _flow_esc_closes_widget() -> Flow:
    import glyfi.widgets.help_widget as help_widget   # importing registers the help widget on the host
    return (Flow('Esc closes an open widget back to NORMAL (never stuck)')
            .given(U.fresh_app(), _open_widget_fixture(help_widget.WIDGET_HELP))
            .when(U.Press(27))                          # 27 = Esc, the reserved host key
            .then(U.mode_is(UI_NORMAL)))


def _flow_content_wraps_no_ellipsis() -> Flow:
    return (Flow('a long content line wraps with no ellipsis')
            .given(U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)),
                   U.at_size(60, 14), U.seeded_transcript(_TRAVERSE_TURNS))
            .when(U.Press(KEY_TRAVERSE))
            .then(U.no_ellipsis('content'), U.region_contains('content', 'tail-marker')))


def _flow_traverse_caret_from_newest() -> Flow:
    return (Flow('the traverse caret starts at the newest row and moves wrap-aware')
            .given(U.fresh_app(config=UserConfig(status_ttl_seconds=4.0)),
                   U.at_size(60, 14), U.seeded_transcript(_TRAVERSE_TURNS))
            .when(U.Press(KEY_TRAVERSE), U.Press(curses.KEY_UP), U.Press(curses.KEY_DOWN))
            .then(U.mode_is(UI_TRAVERSE), U.caret_present('content')))


def _flow_prompt_entry_opens() -> Flow:
    return (Flow('the prompt-entry form opens for one turn')
            .given(U.fresh_app())
            .when(U.Invoke('open_prompt'))
            .then(U.mode_is('PROMPT')))


def _flow_one_turn_no_autoloop() -> Flow:
    mt = MockTransport().script_response('subj-7', 'chat', 'send it', 'STAGED-7')
    return (Flow('one prompt walks EXACTLY one turn (no auto-loop)')
            .given(U.fresh_app(transport=mt), U.with_prompt_entry('subj-7', 'send it'))
            .when(U.ClearEvents(), U.Invoke('request_prompt'))
            .then(U.transcript_len(1), U.event_count('TurnRecorded', 1),
                  U.seq_is(1), U.region_contains('content', 'STAGED-7')))


def _flow_fault_is_fail_loud() -> Flow:
    mt = MockTransport().script_fault('subj-9', 'chat', 'forbidden',
                                      message='turn was gated', type='turn_gate_denied', code=403)
    return (Flow('a scripted fault is fail-loud and does NOT advance the seq')
            .given(U.fresh_app(transport=mt), U.with_prompt_entry('subj-9', 'forbidden'))
            .when(U.ClearEvents(), U.Invoke('request_prompt'))
            .then(U.transcript_len(1), U.seq_is(0),
                  U.event_count('TurnRecorded', 1), U.region_contains('content', '403')))


def _flow_openai_pane_no_key() -> Flow:
    """Open the context pane from the palette with NO api key set -- the captured state is the fail-loud no-key line."""
    from glyfi.contrib.openai_pane.widget import NO_KEY_LINE
    ensure_plugins_loaded()
    return (Flow('/ask from the palette opens the context pane (no-key state)')
            .given(U.fresh_app())
            .when(U.Press('/'), U.Type('ask'), U.Press(curses.KEY_ENTER))
            .then(U.mode_is('WIDGET'), U.region_contains('content', NO_KEY_LINE)))


def ensure_plugins_loaded() -> None:
    """Idempotently bootstrap the first-party plugins so ``/ask`` resolves in the palette (no-op if already loaded).

    Loading is process-global and changes the palette command list, so a deterministic doc capture loads the
    plugins ONCE up front (before any spec runs) -- otherwise the first vs. later runs would paint a different
    command list. The catalog test + the generator both call this so every spec sees the same registered set.
    """
    from glyfi.plugins import palette as palette_mod
    if palette_mod.command('ask') is not None:
        return
    from glyfi.app import load_plugins
    load_plugins()


# ===== the catalog (concern-grouped, in a stable order) ====================================================

_CATALOG: List[Spec] = [
    Spec(CONCERN_COMMAND_PALETTE, 'filter to config and open it',
         given=['a fresh app'],
         when=["I press '/' to open the slash palette",
               "I type 'config' to filter the command list",
               'I press Enter to run the exact-name config command'],
         then=['mode is CONFIG and the state strip cell is highlighted'],
         build_flow=_flow_palette_opens_config),

    Spec(CONCERN_CONFIG_EDITOR, 'the config editor opens with its bound slots',
         given=['a fresh app'],
         when=['I invoke open_config'],
         then=['mode is CONFIG', 'the state strip cell is highlighted'],
         build_flow=_flow_config_editor_opens),

    Spec(CONCERN_STATUS_TICKER, 'a pushed status expires after its TTL and Tab cycles the ring',
         given=['a fresh app', 'a status "a transient notice" was pushed onto the ticker'],
         when=['time passes beyond the status TTL on the virtual clock',
               'I clear events',
               'I press Tab to advance the ticker ring',
               "I press Tab again to advance to the 'hints' provider"],
         then=['the status shows the input hint', 'a TickerCycled event was emitted'],
         build_flow=_flow_ticker_ttl_and_ring),

    Spec(CONCERN_INPUT_HISTORY, 'Up recalls older submitted inputs',
         given=['a fresh app'],
         when=['I submit "first-entry"', 'I submit "second-entry"', 'I clear events',
               'I press Up to recall the newest submission',
               'I press Up again to recall the older one'],
         then=['the input is " > first-entry"', 'a HistoryNavigated event was emitted'],
         build_flow=_flow_input_history_up),

    Spec(CONCERN_CONTENT_SCROLL, 'PgUp reveals older turns above the bottom-anchored newest',
         given=['a fresh app on a small window',
                'a seeded transcript of eight turns (the newest sits at the bottom)'],
         when=['I press PgUp to scroll older turns into view'],
         then=['no content line is ellipsized'],
         build_flow=_flow_bottom_anchored_pgup),

    Spec(CONCERN_CONTENT_SCROLL, 'Esc closes an open widget back to NORMAL (never stuck)',
         given=['a fresh app', 'a widget opened over the content region'],
         when=['I press Esc, the reserved host key'],
         then=['mode is NORMAL (the modal dead-end is gone)'],
         build_flow=_flow_esc_closes_widget),

    Spec(CONCERN_CONTENT_TRAVERSE, 'a long content line wraps with no ellipsis',
         given=['a fresh app on a narrow window',
                'a seeded transcript whose newest turn carries a long wrapping text'],
         when=['I enter content traverse'],
         then=['no content line is ellipsized', "the wrapped tail 'tail-marker' is present"],
         build_flow=_flow_content_wraps_no_ellipsis),

    Spec(CONCERN_CONTENT_TRAVERSE, 'the traverse caret starts at the newest row and moves wrap-aware',
         given=['a fresh app on a narrow window',
                'a seeded transcript whose newest turn carries a long wrapping text'],
         when=['I enter content traverse', 'I press Up one wrapped visual row',
               'I press Down back toward the newest row'],
         then=['mode is TRAVERSE', 'a caret marks a content row'],
         build_flow=_flow_traverse_caret_from_newest),

    Spec(CONCERN_PROMPT_ENTRY, 'the prompt-entry form opens for one turn',
         given=['a fresh app'],
         when=['I invoke open_prompt'],
         then=['mode is PROMPT'],
         build_flow=_flow_prompt_entry_opens),

    Spec(CONCERN_ONE_TURN_LAW, 'one prompt walks EXACTLY one turn (no auto-loop)',
         given=['a fresh app with a scripted transport', 'the next prompt is (subj-7, "send it")'],
         when=['I clear events', "I invoke request_prompt once"],
         then=['the transcript length is 1', 'exactly one TurnRecorded event was emitted',
               'the seq is 1', "the content shows the staged reply 'STAGED-7'"],
         build_flow=_flow_one_turn_no_autoloop),

    Spec(CONCERN_ONE_TURN_LAW, 'a scripted fault is fail-loud and does NOT advance the seq',
         given=['a fresh app with a scripted fault for (subj-9, "forbidden")',
                'the next prompt is (subj-9, "forbidden")'],
         when=['I clear events', 'I invoke request_prompt once'],
         then=['the transcript length is 1 (the failed turn is recorded, never swallowed)',
               'the seq is 0 (a faulted turn must NOT advance the seq)',
               'exactly one TurnRecorded event was emitted (no retry loop)',
               "the content shows the 403 fail-loud envelope"],
         build_flow=_flow_fault_is_fail_loud),

    Spec(CONCERN_OPENAI_PANE, '/ask from the palette opens the context pane (no-key state)',
         given=['a fresh app with the context-pane plugin loaded'],
         when=["I press '/' to open the slash palette",
               "I type 'ask' to select the /ask command",
               'I press Enter to bridge to opening the pane widget'],
         then=['the pane widget is active (mode is WIDGET)',
               'with no api key set the pane shows its fail-loud no-key line (no request is made)'],
         build_flow=_flow_openai_pane_no_key),
]


# ===== the enumeration surface =============================================================================

def all_specs() -> List[Spec]:
    """Every catalog spec, in a stable order (the whole tested corpus as data)."""
    return list(_CATALOG)


def concerns() -> List[str]:
    """The concern names in first-seen order (each grouping appears once)."""
    seen: List[str] = []
    for spec in _CATALOG:
        if spec.concern not in seen:
            seen.append(spec.concern)
    return seen


def specs_for(concern: str) -> List[Spec]:
    """Every spec under ``concern`` (in catalog order). Empty when the concern is unknown."""
    return [spec for spec in _CATALOG if spec.concern == concern]
