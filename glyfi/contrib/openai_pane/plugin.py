"""contrib.openai_pane.plugin -- the ``/ask`` command handler + the widget factory (the command->widget bridge).

The palette side of the OpenAI pane, authored against ONLY ``glyfi.plugins.commands`` + ``glyfi.widgets.base``:
  * ``ask_handler(invocation, ctx) -> CommandResult`` -- ``/ask <text>`` returns
    ``CommandResult(open_widget=WIDGET_OPENAI, status=…)`` so the operator opens the pane from the palette. The
    optional ``<text>`` is stashed via a module-level ONE-SHOT seed (``set_pending_prompt`` / ``take_pending_prompt``)
    that the widget consumes as its first prompt on ``open`` -- engine-blind, no core privilege.
  * ``make_widget()`` -- the widget factory the manifest names (``module:callable``), kept here so the manifest's
    factory ref resolves to a plain zero-arg callable.

A handler is PURE/return-only -- it does NOT touch the ViewModel; it returns a declarative ``CommandResult`` the
applier applies through the injected caps. The pending-prompt seed is a tiny module-global handoff between the
command (which has the text) and the widget (which renders it) -- the same one-shot ``set_pending_*`` pattern.

Self-contained: ``glyfi.plugins.commands`` + ``glyfi.widgets.base`` types only + stdlib.
"""
from typing import Optional

from glyfi.plugins.commands import CommandInvocation, CommandContext, CommandResult
from glyfi.widgets.base import Widget

from glyfi.contrib.openai_pane.widget import OpenAIPaneWidget, WIDGET_OPENAI

# ---- NAMED arg + status literals (no bare strings at a render site) -----------------------------------------
ARG_TEXT = 'text'                       # the ``/ask`` positional REST slot name (must match the manifest schema)
OPEN_STATUS = 'opened the context pane'
OPEN_WITH_PROMPT_STATUS = 'opened the context pane with your prompt'

# ---- the ONE-SHOT pending-prompt seed (a module-global handoff: command -> the widget's first prompt) -------
_PENDING_PROMPT: Optional[str] = None


def set_pending_prompt(text: str) -> None:
    """Stash ``text`` as the pane's first prompt (consumed once by the next widget ``open``). Overwrites any prior."""
    global _PENDING_PROMPT
    _PENDING_PROMPT = text


def take_pending_prompt() -> str:
    """Consume the pending prompt (one-shot): return it + clear the seed. Empty string when nothing is pending."""
    global _PENDING_PROMPT
    text = _PENDING_PROMPT or ''
    _PENDING_PROMPT = None
    return text


def ask_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    """``/ask <text>`` -- open the context pane (the command->widget bridge); stash ``<text>`` as its first prompt.

    PURE/return-only: it seeds the pending prompt (if text was given) and RETURNS a ``CommandResult`` asking the
    applier to open ``WIDGET_OPENAI``. It does not POST anything itself -- the widget owns the LLM call.
    """
    text = (invocation.arg(ARG_TEXT, '') or '').strip()
    if text:
        set_pending_prompt(text)
        status = OPEN_WITH_PROMPT_STATUS
    else:
        status = OPEN_STATUS
    return CommandResult(open_widget=WIDGET_OPENAI, status=status)


def make_widget() -> Widget:
    """The zero-arg widget factory the manifest names -- a fresh ``OpenAIPaneWidget`` per open (open/closed)."""
    return OpenAIPaneWidget()
