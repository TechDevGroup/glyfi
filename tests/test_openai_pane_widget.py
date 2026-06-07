"""Hermetic tests for the OpenAI context-pane widget + the /ask command->widget bridge -- NO real network.

We stub the LLM call by injecting a fake ``OpenAIClient`` into the widget module, drive the widget through the
public ``Widget`` port (open / handle_key / lines), and verify: the no-key fail-loud render, ONE Enter == ONE
completion (no loop), the message list shape (system + prior pairs + new prompt), error surfacing without a
crash, and the ``/ask`` handler returning a CommandResult that opens the pane + seeds the first prompt.
"""
import pytest

from glyfi.ui.layout import Rect
from glyfi.widgets.base import WidgetContext

import glyfi.contrib.openai_pane.widget as widget_mod
from glyfi.contrib.openai_pane.widget import OpenAIPaneWidget, WIDGET_OPENAI, NO_KEY_LINE
from glyfi.contrib.openai_pane.client import OpenAIConfig, OpenAIError, ChatMessage
from glyfi.contrib.openai_pane.plugin import (
    ask_handler,
    make_widget,
    set_pending_prompt,
    take_pending_prompt,
    ARG_TEXT,
)
from glyfi.plugins.commands import CommandInvocation, CommandContext, CommandResult


RECT = Rect(0, 0, 80, 20)


class _FakeClient:
    """A stand-in OpenAIClient: records every complete() call + returns canned replies (or raises)."""

    def __init__(self, config, replies=None, raises=None):
        self.config = config
        self._replies = list(replies or ["canned reply"])
        self._raises = raises
        self.calls = []

    def complete(self, messages):
        self.calls.append(list(messages))
        if self._raises is not None:
            raise self._raises
        return self._replies.pop(0) if self._replies else "canned reply"


def _ctx(name=WIDGET_OPENAI):
    statuses = []
    events = []
    closed = []
    ctx = WidgetContext(
        name=name,
        push_status=statuses.append,
        emit=events.append,
        request_close=lambda: closed.append(True),
    )
    return ctx, statuses, events, closed


def _install_client(monkeypatch, *, config, replies=None, raises=None):
    """Force the widget to build OUR fake client and OUR config on open (no env, no network)."""
    created = {}

    def fake_load():
        return config

    def fake_client_ctor(cfg, **_kw):
        client = _FakeClient(cfg, replies=replies, raises=raises)
        created["client"] = client
        return client

    monkeypatch.setattr(widget_mod, "load_openai_config", fake_load)
    monkeypatch.setattr(widget_mod, "OpenAIClient", fake_client_ctor)
    return created


def _type(widget, text):
    for ch in text:
        widget.handle_key(ord(ch))


ENTER = 10


# ---- no-key fail-loud render ------------------------------------------------------------------------------

def test_no_key_renders_fail_loud_line_and_does_not_send(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key=""))
    widget = OpenAIPaneWidget()
    ctx, statuses, _events, _closed = _ctx()
    widget.open(ctx)

    rendered = widget.lines(RECT)
    assert any(NO_KEY_LINE == line for line in rendered)

    _type(widget, "hello")
    widget.handle_key(ENTER)
    # never sent
    assert created["client"].calls == []


# ---- one Enter == one completion (no loop) ----------------------------------------------------------------

def test_one_enter_one_completion(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key="k"), replies=["R1", "R2"])
    widget = OpenAIPaneWidget()
    ctx, statuses, _events, _closed = _ctx()
    widget.open(ctx)

    _type(widget, "first")
    widget.handle_key(ENTER)
    assert len(created["client"].calls) == 1

    _type(widget, "second")
    widget.handle_key(ENTER)
    assert len(created["client"].calls) == 2

    rendered = "\n".join(widget.lines(RECT))
    assert "R1" in rendered and "R2" in rendered
    assert "first" in rendered and "second" in rendered


def test_enter_with_empty_buffer_does_not_send(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key="k"))
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)
    widget.handle_key(ENTER)
    assert created["client"].calls == []


# ---- message list shape (system + prior pairs + new prompt) -----------------------------------------------

def test_message_list_includes_system_and_prior_pairs(monkeypatch):
    cfg = OpenAIConfig(api_key="k", system_prompt="be brief")
    created = _install_client(monkeypatch, config=cfg, replies=["A1", "A2"])
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)

    _type(widget, "q1")
    widget.handle_key(ENTER)
    _type(widget, "q2")
    widget.handle_key(ENTER)

    second = created["client"].calls[1]
    assert all(isinstance(m, ChatMessage) for m in second)
    pairs = [(m.role, m.content) for m in second]
    assert pairs == [
        ("system", "be brief"),
        ("user", "q1"),
        ("assistant", "A1"),
        ("user", "q2"),
    ]


def test_no_system_message_when_no_system_prompt(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key="k"))
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)
    _type(widget, "hi")
    widget.handle_key(ENTER)
    sent = created["client"].calls[0]
    assert [m.role for m in sent] == ["user"]


# ---- editing ----------------------------------------------------------------------------------------------

def test_backspace_edits_buffer(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key="k"))
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)
    _type(widget, "helloX")
    widget.handle_key(8)   # backspace
    widget.handle_key(ENTER)
    sent = created["client"].calls[0]
    assert sent[-1].content == "hello"


def test_unhandled_key_returns_false(monkeypatch):
    _install_client(monkeypatch, config=OpenAIConfig(api_key="k"))
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)
    assert widget.handle_key(27) is False   # Esc -> host handles close


# ---- error surfacing (visible, no crash) ------------------------------------------------------------------

def test_error_is_surfaced_not_raised(monkeypatch):
    _install_client(monkeypatch, config=OpenAIConfig(api_key="k"),
                    raises=OpenAIError("openai http 500: boom", code=500))
    widget = OpenAIPaneWidget()
    ctx, statuses, _events, _closed = _ctx()
    widget.open(ctx)
    _type(widget, "hi")
    handled = widget.handle_key(ENTER)   # must NOT raise
    assert handled is True
    rendered = "\n".join(widget.lines(RECT))
    assert "error" in rendered.lower()
    assert any("error" in s.lower() for s in statuses)


# ---- the /ask command -> widget bridge --------------------------------------------------------------------

def _cmd_ctx():
    opened = []
    statuses = []
    return CommandContext(
        push_lines=lambda lines: None,
        push_status=statuses.append,
        open_widget=opened.append,
        emit=lambda e: None,
    ), opened, statuses


def test_ask_handler_opens_pane():
    take_pending_prompt()   # clear any prior seed
    inv = CommandInvocation(name="ask", positionals={})
    ctx, _opened, _statuses = _cmd_ctx()
    result = ask_handler(inv, ctx)
    assert isinstance(result, CommandResult)
    assert result.open_widget == WIDGET_OPENAI
    assert take_pending_prompt() == ""   # no text -> nothing seeded


def test_ask_handler_seeds_pending_prompt():
    take_pending_prompt()   # clear
    inv = CommandInvocation(name="ask", positionals={ARG_TEXT: "summarize this"})
    ctx, _opened, _statuses = _cmd_ctx()
    result = ask_handler(inv, ctx)
    assert result.open_widget == WIDGET_OPENAI
    assert take_pending_prompt() == "summarize this"


def test_pane_consumes_pending_prompt_on_open(monkeypatch):
    created = _install_client(monkeypatch, config=OpenAIConfig(api_key="k"), replies=["A"])
    set_pending_prompt("seeded question")
    widget = OpenAIPaneWidget()
    ctx, *_ = _ctx()
    widget.open(ctx)
    # the seeded prompt is in the buffer -> one Enter sends it.
    widget.handle_key(ENTER)
    sent = created["client"].calls[0]
    assert sent[-1].content == "seeded question"
    # one-shot: a second fresh open sees no seed.
    assert take_pending_prompt() == ""


def test_make_widget_returns_pane():
    assert isinstance(make_widget(), OpenAIPaneWidget)
