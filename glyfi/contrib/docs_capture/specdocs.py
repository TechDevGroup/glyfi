"""specdocs -- turn the concern-grouped BDD spec catalog into a tree of per-spec Markdown documents.

For each CONCERN -> each SPEC the generator pins the deterministic detail fields, RUNS the spec's flow (capturing
the full-frame trace -- a real screenshot per step), and renders one Markdown document via ``flow_to_markdown``
prefaced with the scenario's Given/When/Then text. The docs therefore come from the SAME specs the catalog test
runs, so they cannot drift from tested behavior. An index lists every concern -> its specs with relative links.

Output is deterministic + trace-free: the detail-field pin removes the real cwd / wall clock, and the catalog
flows use a virtual clock + a mocked transport (no network -- the context-pane spec captures the no-key state).

Self-contained: the spec catalog + this package's ``markdown_flow`` / ``detfields`` + stdlib only.
"""
import os
import re
from typing import Dict, List

from glyfi.contrib.docs_capture.detfields import pin_deterministic_fields
from glyfi.contrib.docs_capture.markdown_flow import flow_to_markdown, write_markdown
from glyfi.uitest import catalog as catalog_mod
from glyfi.uitest.catalog import Spec

# ---- NAMED layout literals (no bare '#' / path tokens at a render site) ------------------------------------
SPECS_DIRNAME = 'specs'                 # the subtree all generated spec docs live under (relative to the root)
INDEX_NAME = 'README.md'                # the per-tree index file name
MD_SUFFIX = '.md'
DOC_HEADING = '# '
SECTION_HEADING = '## '
CLAUSE_HEADING = '### '
INDEX_TITLE = 'BDD spec docs'
INDEX_INTRO = ('Every document below is generated from the runnable BDD spec catalog '
               '(`glyfi.uitest.catalog`) -- the SAME specs the test suite runs. Each file shows one '
               "scenario's Given/When/Then and a full-frame screen capture after every step. Regenerate "
               'with `python -m glyfi.contrib.docs_capture.specdocs --write`.')
GIVEN_LABEL = 'Given'
WHEN_LABEL = 'When'
THEN_LABEL = 'Then'


def _slug(text: str) -> str:
    """A lowercase, hyphenated, filesystem-safe slug (alphanumerics + single hyphens; no leading/trailing hyphen)."""
    lowered = text.lower()
    cleaned = re.sub(r'[^a-z0-9]+', '-', lowered)
    return cleaned.strip('-') or 'spec'


def _clause_block(label: str, lines: List[str]) -> str:
    """One Given/When/Then clause block -- a heading + a bullet per line (the readable scenario text)."""
    bullets = '\n'.join(f'- {line}' for line in lines)
    return f'{CLAUSE_HEADING}{label}\n\n{bullets}'


def _spec_intro(spec: Spec) -> str:
    """The scenario's Given/When/Then text, rendered above the captured per-step frames."""
    return '\n\n'.join((
        _clause_block(GIVEN_LABEL, spec.given),
        _clause_block(WHEN_LABEL, spec.when),
        _clause_block(THEN_LABEL, spec.then),
    ))


def _spec_path(spec: Spec) -> str:
    """The relative output path for a spec doc -- ``specs/<concern-slug>/<spec-slug>.md``."""
    return f'{SPECS_DIRNAME}/{_slug(spec.concern)}/{_slug(spec.name)}{MD_SUFFIX}'


def _render_spec(spec: Spec) -> str:
    """Run the spec's flow (capturing the full-frame trace) -> a per-step Markdown doc prefaced with its text."""
    result = spec.build_flow().run()
    return flow_to_markdown(result, title=spec.name, intro=_spec_intro(spec), full_frame=True)


def _render_index() -> str:
    """The index document -- every concern -> its specs, as relative links into the tree."""
    blocks: List[str] = [f'{DOC_HEADING}{INDEX_TITLE}', INDEX_INTRO]
    for concern in catalog_mod.concerns():
        lines = [f'{SECTION_HEADING}{concern}', '']
        for spec in catalog_mod.specs_for(concern):
            rel = f'{_slug(concern)}/{_slug(spec.name)}{MD_SUFFIX}'   # relative to the index (already in specs/)
            lines.append(f'- [{spec.name}]({rel})')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) + '\n'


def generate_spec_docs() -> Dict[str, str]:
    """Generate the whole spec-doc tree as a map of relative path -> Markdown (deterministic, trace-free).

    Pins the deterministic detail fields once, then for each catalog spec renders a per-step full-frame document
    keyed at ``specs/<concern>/<spec>.md``, plus the ``specs/README.md`` index. Pure: returns the content map
    (no files written). Byte-stable across calls (virtual clock + mocked transport + pinned detail fields).
    """
    pin_deterministic_fields()
    catalog_mod.ensure_plugins_loaded()      # load plugins ONCE up front so the palette list is stable across runs
    docs: Dict[str, str] = {}
    for spec in catalog_mod.all_specs():
        docs[_spec_path(spec)] = _render_spec(spec)
    docs[f'{SPECS_DIRNAME}/{INDEX_NAME}'] = _render_index()
    return docs


def write_spec_docs(root: str = 'docs') -> List[str]:
    """Write the whole generated tree under ``root`` (creating dirs) and return the written paths (sorted)."""
    written: List[str] = []
    for rel, text in generate_spec_docs().items():
        path = os.path.join(root, rel)
        write_markdown(text, path)
        written.append(path)
    return sorted(written)


def main(argv: List[str] = None) -> None:
    """``--write`` writes the whole ``docs/specs/**`` tree; no flag prints the index + a written-file count.

    Default (no flag): print the index document + the number of spec files that WOULD be written (a dry preview,
    backward-friendly with the gallery's CLI). With ``--write``: write every file under ``docs/specs/`` and
    report the paths.
    """
    import sys
    args = sys.argv[1:] if argv is None else argv
    if '--write' in args:
        paths = write_spec_docs()
        for path in paths:
            print(f'wrote {path}')
        print(f'wrote {len(paths)} files')
        return
    docs = generate_spec_docs()
    spec_files = [p for p in docs if not p.endswith(INDEX_NAME)]
    print(docs[f'{SPECS_DIRNAME}/{INDEX_NAME}'])
    print(f'({len(spec_files)} spec docs would be written under {SPECS_DIRNAME}/)')


if __name__ == '__main__':
    main()
