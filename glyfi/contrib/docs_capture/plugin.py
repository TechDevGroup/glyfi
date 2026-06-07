"""plugin -- the ``/capture`` command (push the live frame's Markdown screen fence into the content view).

The palette side of documentation capture, authored against ONLY ``glyfi.plugins.commands``:
  * ``capture_handler(invocation, ctx) -> CommandResult`` -- ``/capture [region] [--save <path>]`` reads the live
    frame (or one named region) through the injected capture caps, wraps it as a Markdown screen fence, and
    returns the fence lines for the applier to push into the content view (+ a status). With ``--save`` it also
    writes the Markdown to a file.

A handler is PURE/return-only -- it does NOT touch the ViewModel; it returns a declarative ``CommandResult`` the
applier applies through the injected caps. The capture caps (``ctx.capture_frame`` / ``ctx.capture_region``) are
OPTIONAL: when absent (a context that never wired them) the handler fails LOUD-SOFT -- a clear status, never a
crash.

Self-contained: ``glyfi.plugins.commands`` types only + this package's ``capture`` / ``markdown_flow`` + stdlib.
"""
from glyfi.contrib.docs_capture.capture import screen_fence
from glyfi.contrib.docs_capture.markdown_flow import write_markdown
from glyfi.plugins.commands import CommandContext, CommandInvocation, CommandResult

# ---- NAMED arg / flag names (must match the manifest schema) -----------------------------------------------
ARG_REGION = 'region'           # the optional positional region name (``/capture content``)
FLAG_SAVE = 'save'              # the optional ``--save <path>`` flag -> also write the Markdown to a file

# ---- NAMED status literals (no bare strings at a render site) ----------------------------------------------
STATUS_FRAME = 'captured the full frame as a Markdown screen fence'
STATUS_REGION = 'captured region {region!r} as a Markdown screen fence'
STATUS_SAVED = '{base}; saved to {path}'
STATUS_NO_CAP = 'capture unavailable -- this context did not wire the capture capability'
TITLE_FRAME = 'screen'          # the fence title when capturing the full frame


def capture_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    """``/capture [region] [--save <path>]`` -- render the live frame (or one region) as a Markdown screen fence.

    Reads the rows via ``ctx.capture_region(region)`` when a region arg is given, else ``ctx.capture_frame()``;
    wraps them with ``screen_fence``; returns the fence's lines (the applier pushes them into the content view)
    plus a status. If the capability is ABSENT it fails loud-soft -- a clear status, never a crash. With
    ``--save <path>`` it also writes the Markdown document to ``path``.
    """
    region = (invocation.arg(ARG_REGION, '') or '').strip()
    if region:
        if ctx.capture_region is None:
            return CommandResult.of_status(STATUS_NO_CAP)
        rows = ctx.capture_region(region)
        title = region
        status = STATUS_REGION.format(region=region)
    else:
        if ctx.capture_frame is None:
            return CommandResult.of_status(STATUS_NO_CAP)
        rows = ctx.capture_frame()
        title = TITLE_FRAME
        status = STATUS_FRAME

    markdown = screen_fence(rows, border=True, title=title)
    lines = markdown.split('\n')

    save_path = invocation.flag(FLAG_SAVE)
    if isinstance(save_path, str) and save_path:
        write_markdown(markdown + '\n', save_path)
        status = STATUS_SAVED.format(base=status, path=save_path)

    return CommandResult.of_lines(lines, status=status)
