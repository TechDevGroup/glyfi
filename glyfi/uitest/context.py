"""context -- the RunContext + the TRACE: the per-flow run state a verb drives against and records onto.

A flow's verbs all run against ONE ``RunContext``: it holds the driven ``AppDriver`` (the Playwright-page), the
VirtualClock (so verbs can read/advance deterministic time), and the growing TRACE. The trace is the step-by-step
record a failing flow surfaces -- each entry is a verb label + the Probe snapshot taken right after it ran (the
clock value, the painted surface, the events). Kept SEPARATE from the constraint/action modules so both can import
it without a cycle.

Imports the headless driver/clock + this package's Probe + stdlib only.
"""
from dataclasses import dataclass, field
from typing import List, Tuple

from glyfi.ui.clock import VirtualClock
from glyfi.ui.driver import AppDriver
from glyfi.uitest.constraints import Probe


@dataclass(frozen=True)
class TraceEntry:
    """ONE recorded step in a flow run -- the verb's label + the Probe captured right after it drove the app.

    ``frame`` is an ADDITIVE, presentation-only snapshot: the full composed screen grid (the rows a terminal
    would show) taken at the SAME instant as the ``probe``. It is immutable (a tuple of rows), defaults empty,
    and is IGNORED by every constraint -- it exists only so a walkthrough renderer can show a real full-frame
    screenshot of the whole UI at each step.
    """
    step: str
    probe: Probe
    frame: Tuple[str, ...] = ()

    def describe(self) -> str:
        return (f'{self.step}  @t={self.probe.clock_now:.3g}  mode={self.probe.mode_ui}  '
                f'status={self.probe.status_line!r}  events={self.probe.event_counts}')


@dataclass
class RunContext:
    """The per-flow run state -- the driven app + its virtual clock + the accumulating trace.

    A fixture builds this (driver + clock from a mocked stack). Verbs read ``driver`` to drive + ``record_step``
    to append a trace entry. The Flow reads the final driver for its THEN probe, and the trace for a failure dump.
    """
    driver: AppDriver
    clock: VirtualClock
    trace: List[TraceEntry] = field(default_factory=list)

    def record_step(self, step: str, probe: Probe) -> None:
        """Append a trace entry (the verb label + the post-step Probe + the full composed frame) -- the run record.

        The frame snapshot is the driver's CURRENT full-screen grid, taken at the SAME instant as ``probe`` (the
        step's effect already applied). It is presentation-only -- additive and ignored by constraints.
        """
        frame = tuple(self.driver.frame_text())
        self.trace.append(TraceEntry(step=step, probe=probe, frame=frame))

    def probe(self) -> Probe:
        """Capture the driver's CURRENT observable surface (the Flow's THEN reads this)."""
        return Probe.of(self.driver)

    def trace_dump(self) -> str:
        """The full run trace as readable lines (surfaced alongside a located violation on a flow failure)."""
        if not self.trace:
            return '(no steps run)'
        return '\n'.join(f'  {i}. {e.describe()}' for i, e in enumerate(self.trace))
