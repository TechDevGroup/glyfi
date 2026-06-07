"""markdown_flow -- a BDD flow TRACE -> a per-step Markdown document (UI state embedded between steps).

A ``Flow`` records a ``TraceEntry`` per ``when`` step: the verb label + the ``Probe`` snapshot AND the full
composed screen frame, both taken right after that step drove the app. This bridge turns that trace into a
Markdown walkthrough -- ONE section per step, each with a heading (the step label) and a screen fence, so the
reader sees what the UI showed BETWEEN the steps (the "embed the scenario state between steps" goal).

By default (``full_frame=True``) each step's section is a TRUE full-frame screenshot of the WHOLE UI -- the
composed full-screen grid the ``TraceEntry`` carries (the same rows a terminal would show). When ``full_frame``
is off, or for a step with no recorded frame, the bridge falls back to the pertinent regions STACKED -- each
clearly labeled, padded to a constant width, and wrapped in one screen fence (the region text the constraints
saw). The frame is presentation-only and additive; constraints never read it.

Self-contained: ``capture`` + ``glyfi.uitest`` types (``FlowResult`` / ``RunContext`` / ``TraceEntry`` / ``Probe``)
+ stdlib only. No network, no curses, no app mutation.
"""
import os
from typing import List, Optional, Sequence

from glyfi.contrib.docs_capture.capture import pad_block, screen_fence
from glyfi.uitest.constraints import Probe
from glyfi.uitest.context import RunContext, TraceEntry
from glyfi.uitest.flow import FlowResult

# ---- NAMED Markdown heading + label literals (no bare '#' / ':' at a render site) --------------------------
DOC_HEADING = '# '              # the document title heading level
STEP_HEADING = '## '            # a per-step section heading level
REGION_LABEL = '── '            # the in-fence label prefix marking a stacked region's start
REGION_LABEL_SUFFIX = ' ──'     # the in-fence label suffix
STEP_NUMBER_SEP = '. '          # between a step ordinal and its label ('1. open palette')

# ---- NAMED pertinent region set (what a step's screen shows when ``regions`` is not narrowed) --------------
# The operator-facing chrome + the content overlay -- the regions a walkthrough reader cares about per step.
from glyfi.ui.settings import (  # noqa: E402 -- NAMED region constants, imported after the module docstring
    REGION_TITLE, REGION_STATE, REGION_CONTENT, REGION_STATUS, REGION_INPUT, REGION_DETAILS,
)
PERTINENT_REGIONS = (REGION_TITLE, REGION_STATE, REGION_CONTENT, REGION_STATUS, REGION_INPUT, REGION_DETAILS)


def _trace_of(source) -> List[TraceEntry]:
    """Pull the per-step ``TraceEntry`` list off a ``FlowResult`` or a ``RunContext`` (fail loud on neither)."""
    if isinstance(source, RunContext):
        return list(source.trace)
    if isinstance(source, FlowResult):
        return list(source.trace)
    trace = getattr(source, 'trace', None)
    if trace is not None:
        return list(trace)
    raise TypeError(f'flow_to_markdown: expected a FlowResult or RunContext, got {type(source).__name__}')


def _probe_screen_rows(probe: Probe, regions: Sequence[str]) -> List[str]:
    """Stack the pertinent regions' painted lines (each under a clear label) into one constant-width row block."""
    rows: List[str] = []
    for region in regions:
        lines = probe.regions.get(region, [])
        if not lines:
            continue
        if rows:
            rows.append('')
        rows.append(f'{REGION_LABEL}{region}{REGION_LABEL_SUFFIX}')
        rows.extend(lines)
    if not rows:
        rows = ['(no painted regions for this step)']
    return pad_block(rows)


def _step_section(index: int, entry: TraceEntry, regions: Sequence[str], border: bool, full_frame: bool) -> str:
    """One step's Markdown section -- a heading (ordinal + label) + a screen fence.

    When ``full_frame`` is set AND the step recorded a composed full frame, the fence is a single TRUE screenshot
    of the whole UI (the full-screen grid). Otherwise it falls back to the pertinent regions STACKED -- exactly
    the prior behaviour (the cleanest faithful thing the Probe alone supports).
    """
    heading = f'{STEP_HEADING}{index}{STEP_NUMBER_SEP}{entry.step}'
    if full_frame and entry.frame:
        rows = list(entry.frame)
    else:
        rows = _probe_screen_rows(entry.probe, regions)
    fence = screen_fence(rows, border=border, title=f'mode:{entry.probe.mode_ui}')
    return f'{heading}\n\n{fence}'


def flow_to_markdown(source, *, title: Optional[str] = None, intro: Optional[str] = None,
                     regions: Optional[Sequence[str]] = None, border: bool = True,
                     full_frame: bool = True) -> str:
    """Render a flow's recorded trace as a per-step Markdown walkthrough -- UI state embedded between steps.

    ``source`` is a ``FlowResult`` or a ``RunContext`` (whatever carries the per-step trace). For EACH recorded
    step a section is emitted: a heading from the step label + a screen fence of that step's UI state.

    ``full_frame`` (default True): when the step recorded a composed full frame (``TraceEntry.frame``), the
    section shows a TRUE full-frame screenshot of the WHOLE UI -- a real screenshot between steps. When False, or
    when no frame was recorded for a step, the section falls back to the pertinent regions STACKED (the full
    ``PERTINENT_REGIONS`` set when ``regions`` is None, else just those). An optional ``title`` becomes the doc
    heading and ``intro`` a lead paragraph. Deterministic; pure string assembly.
    """
    entries = _trace_of(source)
    pertinent = tuple(regions) if regions is not None else PERTINENT_REGIONS
    blocks: List[str] = []
    if title:
        blocks.append(f'{DOC_HEADING}{title}')
    if intro:
        blocks.append(intro)
    if not entries:
        blocks.append('_(the flow recorded no steps)_')
    for i, entry in enumerate(entries, start=1):
        blocks.append(_step_section(i, entry, pertinent, border, full_frame))
    return '\n\n'.join(blocks) + '\n'


def write_markdown(text: str, path: str) -> None:
    """Write ``text`` to ``path`` (creating parent dirs) -- the stdlib file sink for a captured document."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
