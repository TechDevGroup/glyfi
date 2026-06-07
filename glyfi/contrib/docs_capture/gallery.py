"""gallery -- the DOGFOOD: drive a headless app through representative states + emit one Markdown document.

This is documentation capture leveraging itself. It builds a real headless ``AppDriver`` (the same seam the test
framework binds to), drives it through representative UI states with the REAL keymap / commands, and renders each
state as a Markdown screen fence via ``capture.markdown_screen``. ``build_gallery()`` returns one MD document; a
sibling ``build_walkthrough()`` runs a small BDD ``Flow`` through ``flow_to_markdown`` to show the per-step
bridge. ``python -m glyfi.contrib.docs_capture.gallery`` prints both to stdout.

No network: the OpenAI pane is opened with NO API key configured -- its fail-loud line is the captured content
(no request is made). Self-contained: this package's ``capture`` / ``markdown_flow`` + the public driver /
flow / fixture seams + stdlib.
"""
from typing import List, Tuple

from glyfi.contrib.docs_capture.capture import markdown_screen
from glyfi.contrib.docs_capture.detfields import (
    DETERMINISTIC_CWD, DETERMINISTIC_LOCALTIME, pin_deterministic_fields,
)
from glyfi.contrib.docs_capture.markdown_flow import flow_to_markdown
from glyfi.plugins import palette as palette_mod
from glyfi.ui.settings import REGION_CONTENT

# ---- NAMED document literals (no bare '#' at a render site) ------------------------------------------------
GALLERY_TITLE = '# glyfi UI gallery'
GALLERY_INTRO = ('Each section below is a Markdown *screen fence* -- the live headless UI captured through the '
                 'same Painting the curses View renders. Regenerate with '
                 '`python -m glyfi.contrib.docs_capture.gallery`.')
SECTION_HEADING = '## '
WALKTHROUGH_TITLE = 'palette walkthrough'
WALKTHROUGH_INTRO = ('A small BDD flow (open the palette -> type a filter -> open the config editor) rendered '
                     'through `flow_to_markdown` -- the UI state is embedded between the steps.')


def _deterministic_fields() -> None:
    """Pin the live detail fields (cwd / localtime) -- the shared deterministic-fields pin (kept as a thin alias)."""
    pin_deterministic_fields()


def _fresh_driver():
    """A fresh headless driver over a default-echoing mock transport (the gallery's drive surface)."""
    from glyfi.uitest.fixtures import build_mock_context, MockTransport
    # the builtin plugins (incl. /ask + /capture) must be registered so the palette + commands resolve.
    _ensure_plugins_loaded()
    return build_mock_context(MockTransport()).driver


def _ensure_plugins_loaded() -> None:
    """Idempotently bootstrap the first-party plugins so the palette lists ``/ask`` etc. (no-op if already loaded)."""
    if palette_mod.command('ask') is not None:
        return
    from glyfi.app import load_plugins
    load_plugins()


def _empty_screen() -> Tuple[str, str]:
    """(a) the fresh / empty screen -- the NORMAL transcript view before any interaction."""
    d = _fresh_driver()
    return 'fresh screen (NORMAL)', markdown_screen(d, title='fresh screen')


def _palette_filtered() -> Tuple[str, str]:
    """(b) the command palette open + filtered (type a fragment to narrow the slash-command list)."""
    d = _fresh_driver()
    d.invoke('open_palette').type_text('co')
    return 'command palette (filtered)', markdown_screen(d, region=REGION_CONTENT, title='palette: /co')


def _config_editor() -> Tuple[str, str]:
    """(c) the traversable config editor -- slot positions + the INPUTS knobs."""
    d = _fresh_driver()
    d.invoke('open_config')
    return 'config editor', markdown_screen(d, region=REGION_CONTENT, title='config')


def _prompt_modal() -> Tuple[str, str]:
    """(d) the prompt-entry modal -- the subject + text form (walk one turn)."""
    d = _fresh_driver()
    d.invoke('open_prompt')
    return 'prompt-entry modal', markdown_screen(d, region=REGION_CONTENT, title='prompt')


def _openai_pane() -> Tuple[str, str]:
    """(e) the OpenAI context pane open -- with NO API key configured its fail-loud line is the captured content."""
    d = _fresh_driver()
    # run the /ask command through the pipeline so the pane widget opens (no network -- no prompt sent).
    d.vm.run_command_raw(f'{palette_mod.PALETTE_PREFIX}ask')
    d.render()
    return 'OpenAI context pane', markdown_screen(d, region=REGION_CONTENT, title='/ask pane')


def _sections() -> List[Tuple[str, str]]:
    return [_empty_screen(), _palette_filtered(), _config_editor(), _prompt_modal(), _openai_pane()]


def build_gallery() -> str:
    """Drive the headless app through representative states -> one Markdown document (a screen fence per state)."""
    _deterministic_fields()
    blocks: List[str] = [GALLERY_TITLE, GALLERY_INTRO]
    for heading, fence in _sections():
        blocks.append(f'{SECTION_HEADING}{heading}\n\n{fence}')
    return '\n\n'.join(blocks) + '\n'


def build_walkthrough() -> str:
    """A small BDD flow run through ``flow_to_markdown`` -- the per-step UI-state-between-steps bridge demo."""
    from glyfi.uitest.actions import Invoke, Type
    from glyfi.uitest.constraints import mode_is
    from glyfi.uitest.fixtures import fresh_app
    from glyfi.uitest.flow import Flow
    _deterministic_fields()
    _ensure_plugins_loaded()
    flow = (Flow('palette walkthrough')
            .given(fresh_app())
            .when(Invoke('open_palette'), Type('co'), Invoke('open_config'))
            .then(mode_is('CONFIG')))
    result = flow.run()
    return flow_to_markdown(result, title=WALKTHROUGH_TITLE, intro=WALKTHROUGH_INTRO)


# ---- NAMED checked-in doc artifact paths (relative to the repo root) ---------------------------------------
GALLERY_DOC_PATH = 'docs/ui-gallery.md'
WALKTHROUGH_DOC_PATH = 'docs/walkthrough.md'


def write_docs(gallery_path: str = GALLERY_DOC_PATH,
               walkthrough_path: str = WALKTHROUGH_DOC_PATH) -> Tuple[str, str]:
    """Write BOTH committed artifacts -- the UI gallery and the BDD walkthrough -- and return their paths.

    The gallery (the 5 representative UI states) goes to ``gallery_path``; the per-step BDD walkthrough (from
    ``build_walkthrough``) goes to ``walkthrough_path``. Uses the package's stdlib file sink; parent dirs are
    created. Pure capture -- no network.
    """
    from glyfi.contrib.docs_capture.markdown_flow import write_markdown
    write_markdown(build_gallery(), gallery_path)
    write_markdown(build_walkthrough(), walkthrough_path)
    return gallery_path, walkthrough_path


def main(argv: List[str] = None) -> None:
    """Print the gallery + walkthrough to stdout, or with ``--write`` write both checked-in doc artifacts.

    Default (no flag): print the gallery + the walkthrough Markdown to stdout (backward-compatible dogfood).
    With ``--write``: write ``docs/ui-gallery.md`` and ``docs/walkthrough.md`` (and report the paths).
    """
    import sys
    args = sys.argv[1:] if argv is None else argv
    if '--write' in args:
        gallery_path, walkthrough_path = write_docs()
        print(f'wrote {gallery_path}')
        print(f'wrote {walkthrough_path}')
        return
    print(build_gallery())
    print()
    print(build_walkthrough())


if __name__ == '__main__':
    main()
