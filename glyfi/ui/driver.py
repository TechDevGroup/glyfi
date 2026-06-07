"""driver -- the NAMED headless DRIVE seam: ``AppDriver`` drives the event-driven MVVM WITHOUT curses.

This is the clean programmatic surface a constraint-driven test-framework binds to. It wires an ``AppViewModel``
to a ``HeadlessView`` over a SHARED ``EventBus`` (recording on) and an injectable ``Clock`` (a ``VirtualClock``
so time is deterministic), and exposes a small, documented API to drive the app and read it back. The curses View
is the runtime adapter over the SAME event-driven core; the driver is the headless one -- both subscribe to the
same bus and read the same presentation state.

The DRIVE surface (what the test-framework calls -- exactly these methods):
  * ``press(key)``      -- feed a curses key code through the SAME modal dispatch the curses adapter uses.
  * ``invoke(name)``    -- invoke a NAMED command/ViewModel-method by name (prompt/clear/config/mode/quit/...).
  * ``type_text(text)`` -- type characters into the input line (NORMAL / PALETTE / PROMPT, per mode).
  * ``submit()``        -- submit the NORMAL input line (records history, emits InputSubmitted).
  * ``tick(dt)``        -- advance the VirtualClock by ``dt`` seconds + emit a Tick (expires the ticker TTL).
  * ``render()``        -- repaint via the HeadlessView; returns the captured ``Painting``.
  * ``painting`` / ``region(name)`` / ``status_line()`` / ``input_line()`` -- read the current presentation.
  * ``events`` / ``events_of(type)`` / ``last(type)`` -- read the emitted-event log (the bus records).

It NEVER auto-loops the walk -- ``invoke('prompt')`` / a prompt keypress walks exactly one turn via the seam.

stdlib, no curses.
"""
from typing import List, Optional, Type

from glyfi.ui.clock import VirtualClock
from glyfi.ui.events import Event, KeyPressed, CommandInvoked, Tick
from glyfi.ui.keymap import dispatch_key
from glyfi.ui.view import HeadlessView, Painting, RegionPainter, compose_frame
from glyfi.ui.viewmodel import AppViewModel, UI_PALETTE, UI_PROMPT
from glyfi.ui.settings import REGION_INPUT

# ---- NAMED default headless size (a driver/test may resize) -----------------------------------------------
DEFAULT_DRIVE_WIDTH = 80
DEFAULT_DRIVE_HEIGHT = 24


class AppDriver:
    """The headless DRIVE surface over the event-driven MVVM -- the seam a constraint test-framework binds to.

    Constructed over a built ``AppViewModel`` (the caller wires it with a recording bus + a VirtualClock), it
    owns a ``HeadlessView`` and gives the programmatic drive API. ``prompt_seam`` may be set on the VM so
    ``invoke('prompt')`` walks one turn from a supplied (subject, text) without an interactive terminal.
    """

    def __init__(self, viewmodel: AppViewModel, view: Optional[HeadlessView] = None,
                 w: int = DEFAULT_DRIVE_WIDTH, h: int = DEFAULT_DRIVE_HEIGHT):
        self.vm = viewmodel
        self.view = view or HeadlessView(painter=RegionPainter(), w=w, h=h)
        self.render()

    # ---- drive: keys / commands / input / time --------------------------------------------------------------
    def press(self, key: int) -> 'AppDriver':
        """Feed a curses key code through the SAME modal dispatch the curses adapter uses, then repaint."""
        self.vm.bus.emit(KeyPressed(key=key, mode_ui=self.vm.mode_ui))
        dispatch_key(self.vm, key)
        return self.render_chain()

    def invoke(self, name: str) -> 'AppDriver':
        """Invoke a NAMED command/ViewModel method by name (the palette/key command vocabulary), then repaint.

        Resolves a registered palette command's action first; otherwise a same-named zero-arg VM method. Fail
        LOUD on an unknown name (a driven command that does not exist is a test-spec fault, not a silent no-op).
        """
        from glyfi.plugins import palette as palette_mod
        cmd = palette_mod.command(name)
        if cmd is not None:
            self.vm.bus.emit(CommandInvoked(name=name))
            cmd.action(self.vm)
            return self.render_chain()
        method = getattr(self.vm, name, None)
        if callable(method):
            self.vm.bus.emit(CommandInvoked(name=name))
            method()
            return self.render_chain()
        raise KeyError(f'AppDriver.invoke: unknown command/method {name!r}')

    def type_text(self, text: str) -> 'AppDriver':
        """Type each character into the active input target (PALETTE filter / PROMPT field / NORMAL buffer), repaint."""
        for ch in text:
            if self.vm.mode_ui == UI_PALETTE:
                self.vm.palette_type(ch)
            elif self.vm.mode_ui == UI_PROMPT:
                self.vm.prompt_type(ch)
            else:
                self.vm.input_type(ch)
        return self.render_chain()

    def submit(self) -> 'AppDriver':
        """Submit the NORMAL input line (records history, emits InputSubmitted), then repaint."""
        self.vm.submit_input()
        return self.render_chain()

    def tick(self, dt: float) -> 'AppDriver':
        """Advance the VirtualClock by ``dt`` seconds and emit a Tick (this is what expires the ticker TTL)."""
        clock = self.vm.clock
        if not isinstance(clock, VirtualClock):
            raise TypeError('AppDriver.tick requires a VirtualClock on the ViewModel (deterministic time)')
        now = clock.advance(dt)
        self.vm.bus.emit(Tick(now=now))
        return self.render_chain()

    # ---- read: painting / presentation / events -------------------------------------------------------------
    def render(self) -> Painting:
        """Repaint via the HeadlessView and return the captured Painting (the frame a terminal would show)."""
        self.view.render(self.vm)
        return self.view.painting

    def render_chain(self) -> 'AppDriver':
        """Repaint and return self (so drive calls chain: ``d.press(k).type_text('x').submit()``)."""
        self.render()
        return self

    @property
    def painting(self) -> Painting:
        return self.view.painting

    @property
    def layout(self):
        """The current solved region->Rect map the View painted against (the public capture seam)."""
        return self.view.layout

    @property
    def size(self):
        """The synthetic terminal ``Size`` the View solves against (the public capture seam)."""
        return self.view.size

    def frame(self):
        """The current frame triple ``(painting, layout, size)`` -- the public seam for an external capture target.

        A pure read of the latest painted frame: the ``Painting`` (per-region lines + highlight data), the solved
        ``layout`` (region->``Rect``), and the synthetic ``Size``. External code composes a screen from these
        WITHOUT reaching into any private attribute.
        """
        return self.painting, self.layout, self.size

    def frame_text(self) -> List[str]:
        """The current frame composed into the full-screen grid rows (every region placed at its ``Rect``).

        A pure read: delegates to the CORE ``compose_frame`` over the latest ``(painting, layout, size)`` -- the
        exact full rectangle a terminal would show, blank-filled in the gaps and padded to the synthetic width.
        """
        return compose_frame(*self.frame())

    def region(self, name: str) -> List[str]:
        """The painted lines of region ``name`` in the current frame."""
        return self.view.painting.lines(name)

    def status_line(self) -> str:
        """What the ephemeral status ticker shows right now (the live drive read of the status region)."""
        return self.vm.status_line()

    def input_line(self) -> str:
        """The current input + hints line text (the buffer when typing, else the hint)."""
        lines = self.view.painting.lines(REGION_INPUT)
        return lines[0] if lines else ''

    @property
    def events(self) -> List[Event]:
        """The emitted-event log since the bus started recording (driver clears it via ``clear_events``)."""
        return list(self.vm.bus.log)

    def events_of(self, event_type: Type[Event]) -> List[Event]:
        return self.vm.bus.events_of(event_type)

    def last(self, event_type: Type[Event]) -> Optional[Event]:
        return self.vm.bus.last(event_type)

    def clear_events(self) -> 'AppDriver':
        """Drop the recorded-event log (scope the next drive action's event assertions)."""
        self.vm.bus.clear_log()
        return self

    def resize(self, w: int, h: int) -> 'AppDriver':
        """Resize the synthetic terminal the headless View solves against, then repaint."""
        self.view.resize(w, h)
        return self.render_chain()


def build_headless_driver(viewmodel: AppViewModel, w: int = DEFAULT_DRIVE_WIDTH,
                          h: int = DEFAULT_DRIVE_HEIGHT) -> AppDriver:
    """Convenience: turn the bus recording ON and return an AppDriver over the ViewModel (the framework's entry)."""
    viewmodel.bus.record = True
    return AppDriver(viewmodel, w=w, h=h)
