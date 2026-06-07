"""contrib.openai_pane.widget -- the OpenAI CONTEXT PANE widget (a ``Widget`` overlay over the content region).

A real, working LLM pane authored ENTIRELY against the public widget contract (no core privileges):
  * ``open(ctx)``       -- build an ``OpenAIClient`` from ``load_openai_config()``; push a greeting status; seed
                           the prompt buffer from the one-shot ``/ask <text>`` pending seed (if any).
  * ``handle_key(key)`` -- a printable key appends to the prompt buffer; Backspace edits it; ENTER submits ONE
                           completion (system? + prior (user,assistant) pairs + the new prompt), appends the
                           reply to the transcript, clears the buffer. Returns True for keys it handles, False
                           otherwise (so the host's Esc still closes). NEVER auto-loops -- one Enter, one call.
  * ``lines(rect)``     -- the rendered transcript + the live prompt line (PURE text; the host frames/clips it).

NO api key -> the pane renders a fail-loud "set ``GLYFI_OPENAI_API_KEY``" line and refuses to send (the client
already fails loud, but the pane surfaces it as content + status so the operator sees it without a crash).

Self-contained: the widget base + layout ``Rect`` + this plugin's client + stdlib (curses for KEY CODES only).
"""
from typing import List, Optional

import curses

from glyfi.ui.layout import Rect
from glyfi.widgets.base import Widget, WidgetContext

from glyfi.contrib.openai_pane.client import (
    ChatMessage,
    OpenAIClient,
    OpenAIError,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    ENV_API_KEY,
    load_openai_config,
)

# ---- NAMED widget name (the registry key + the /ask command's open_widget target) --------------------------
WIDGET_OPENAI = 'openai_pane'

# ---- NAMED render literals (no bare strings scattered at a render site) -------------------------------------
PANE_TITLE = 'context'
USER_PREFIX = 'you> '
ASSISTANT_PREFIX = 'ai> '
PROMPT_PREFIX = '> '
EMPTY_HINT = 'type a prompt, Enter to ask, Esc to close'
NO_KEY_LINE = f'set {ENV_API_KEY} to ask (no api key set)'

# ---- NAMED status literals (pushed through the scoped WidgetContext) ----------------------------------------
OPEN_STATUS = 'context — type a prompt, Enter to ask, Esc to close'
OPEN_NO_KEY_STATUS = f'context — set {ENV_API_KEY} to ask'
SENDING_STATUS = 'asking…'
REPLY_STATUS = 'reply received'

# ---- NAMED printable key bounds (mirrors the keymap; curses only for the special key codes) ----------------
PRINTABLE_LO = 32
PRINTABLE_HI = 127
KEYS_ENTER = (curses.KEY_ENTER, 10, 13)
KEYS_BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)


def _pending_prompt() -> str:
    """The one-shot ``/ask <text>`` seed (if any), consumed at open. Imported lazily to avoid an import cycle."""
    from glyfi.contrib.openai_pane.plugin import take_pending_prompt
    return take_pending_prompt()


class OpenAIPaneWidget(Widget):
    """A chat-completions context pane -- type a prompt, Enter POSTs ONE completion, the reply renders below.

    Holds: the prompt input buffer, a transcript of ``(user, assistant)`` pairs, the ``OpenAIClient`` built on
    ``open`` from ``load_openai_config()``, and its scoped ``WidgetContext``. It drives the MVVM pluggable
    surface PURELY via the public seams -- it renders text into the content region and pushes status through the
    context. Model / system prompt / org all come from ``GLYFI_OPENAI_*`` config (config-driven, no hard-coding).
    """

    title = PANE_TITLE

    def __init__(self):
        self._ctx: Optional[WidgetContext] = None
        self._client: Optional[OpenAIClient] = None
        self._system_prompt: str = ''
        self._buffer: str = ''
        # the rendered transcript: a list of (role, content) pairs in send order.
        self._transcript: List[tuple] = []
        self._has_key: bool = False

    # ---- lifecycle ----------------------------------------------------------------------------------------
    def open(self, ctx: WidgetContext) -> None:
        """Build the client from env config, seed the prompt from the one-shot ``/ask`` text, push a greeting."""
        self._ctx = ctx
        config = load_openai_config()
        self._client = OpenAIClient(config)
        self._system_prompt = config.system_prompt
        self._has_key = config.has_key
        self._buffer = _pending_prompt()
        self._transcript = []
        ctx.push_status(OPEN_STATUS if self._has_key else OPEN_NO_KEY_STATUS)

    def handle_key(self, key: int) -> bool:
        """ONE key: printable -> buffer, Backspace -> edit, Enter -> ONE completion. Never loops; never blocks Esc."""
        if key in KEYS_ENTER:
            return self._submit()
        if key in KEYS_BACKSPACE:
            if self._buffer:
                self._buffer = self._buffer[:-1]
            return True
        if PRINTABLE_LO <= key < PRINTABLE_HI:
            self._buffer += chr(key)
            return True
        return False

    # ---- the ONE completion (one Enter == one call; NEVER auto-loops) -------------------------------------
    def _submit(self) -> bool:
        """Build the message list, call ``client.complete`` EXACTLY once, append the reply, clear the buffer."""
        prompt = self._buffer.strip()
        if not prompt:
            return True
        ctx = self._ctx
        if not self._has_key or self._client is None:
            if ctx is not None:
                ctx.push_status(OPEN_NO_KEY_STATUS)
            return True
        messages = self._build_messages(prompt)
        if ctx is not None:
            ctx.push_status(SENDING_STATUS)
        try:
            reply = self._client.complete(messages)
        except OpenAIError as exc:
            # fail loud BUT visible -- surface the error in the transcript + status, never crash the pane.
            self._transcript.append((ROLE_USER, prompt))
            self._transcript.append((ROLE_ASSISTANT, f'[error] {exc}'))
            self._buffer = ''
            if ctx is not None:
                ctx.push_status(f'openai error: {exc}')
            return True
        self._transcript.append((ROLE_USER, prompt))
        self._transcript.append((ROLE_ASSISTANT, reply))
        self._buffer = ''
        if ctx is not None:
            ctx.push_status(REPLY_STATUS)
        return True

    def _build_messages(self, prompt: str) -> List[ChatMessage]:
        """[optional system] + the prior (user,assistant) transcript + the new user prompt -- in send order."""
        messages: List[ChatMessage] = []
        if self._system_prompt:
            messages.append(ChatMessage(ROLE_SYSTEM, self._system_prompt))
        for role, content in self._transcript:
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage(ROLE_USER, prompt))
        return messages

    # ---- render (PURE text) -------------------------------------------------------------------------------
    def lines(self, rect: Rect) -> List[str]:
        """The transcript pairs + the live prompt line (PURE text; the host frames + the View clips to ``rect``)."""
        out: List[str] = []
        if not self._has_key:
            out.append(NO_KEY_LINE)
            out.append('')
        if not self._transcript:
            out.append(EMPTY_HINT)
        for role, content in self._transcript:
            prefix = USER_PREFIX if role == ROLE_USER else ASSISTANT_PREFIX
            body = content.split('\n')
            out.append(f'{prefix}{body[0]}')
            for extra in body[1:]:
                out.append(f'  {extra}')
        out.append('')
        out.append(f'{PROMPT_PREFIX}{self._buffer}')
        return out

    def highlight(self) -> Optional[int]:
        """The live prompt row carries focus (the last rendered line) -- the View marks it for the operator."""
        return None
