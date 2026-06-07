# The OpenAI context pane

glyfi ships one first-party LLM plugin: an **OpenAI chat-completions context pane**. It is
the canonical "how do I build an LLM plugin?" tutorial — a real, working pane authored
**entirely against the public plugin / widget / config contracts**, with no core
privileges and stdlib `urllib` only.

It does two things:

- registers a **widget** (`openai_pane`) that POSTs a prompt to an OpenAI chat-completions
  endpoint and renders the assistant reply;
- registers a **command** `/ask <text>` that opens the pane (the command → widget bridge),
  optionally seeding its first prompt.

Files: `glyfi/contrib/openai_pane/{client,widget,plugin}.py` +
`glyfi/plugins/builtin/openai_pane.json`.

---

## Configuration (`GLYFI_OPENAI_*`)

The pane resolves its config from env at the moment the widget opens
(`load_openai_config()`), mirroring `glyfi.config`'s fail-loud style:

| env var                     | default                       | meaning                                          |
| --------------------------- | ----------------------------- | ------------------------------------------------ |
| `GLYFI_OPENAI_BASE_URL`     | `https://api.openai.com/v1`   | the API base (the `/chat/completions` path is appended) |
| `GLYFI_OPENAI_API_KEY`      | (none)                        | required to send; no key → the pane renders a fail-loud line |
| `GLYFI_OPENAI_MODEL`        | `gpt-4o-mini`                 | the model id                                     |
| `GLYFI_OPENAI_ORG`          | (none)                        | optional → an `OpenAI-Organization` header       |
| `GLYFI_OPENAI_TIMEOUT`      | `30.0`                        | request timeout in seconds (must be a positive number) |
| `GLYFI_OPENAI_SYSTEM_PROMPT`| (none)                        | optional system message prepended to every request |

```python
from glyfi.contrib.openai_pane.client import load_openai_config
cfg = load_openai_config()    # OpenAIConfig(base_url, api_key, model, org, timeout, system_prompt)
```

Fail-loud: a non-numeric or non-positive `GLYFI_OPENAI_TIMEOUT` raises
`OpenAIConfigError`. A **missing key is not** a config fault here — the pane surfaces it at
send time instead (it renders `set GLYFI_OPENAI_API_KEY to ask` and refuses to send, no
crash). The api key is held only to build the `Authorization` header — it is never logged
or placed in any error message.

---

## Quickstart

```bash
export GLYFI_OPENAI_API_KEY=sk-...
export GLYFI_OPENAI_MODEL=gpt-4o-mini                 # optional; this is the default
export GLYFI_OPENAI_SYSTEM_PROMPT="You are a terse assistant."   # optional
glyfi --base-url http://127.0.0.1:8800
```

In the app:

1. Press `/`, choose `ask` (or type `/ask`). The pane opens as a widget overlay.
2. Optionally seed a first prompt: `/ask summarize this file`.
3. In the pane: type a prompt, press `Enter`. One Enter = one chat-completions call; the
   reply renders below. It NEVER auto-loops.
4. `Esc` closes the pane.

---

## How `/ask` works (the command → widget bridge)

`glyfi/contrib/openai_pane/plugin.py` is the palette side, authored against ONLY
`glyfi.plugins.commands` + `glyfi.widgets.base`:

```python
from glyfi.plugins.commands import CommandInvocation, CommandContext, CommandResult
from glyfi.contrib.openai_pane.widget import WIDGET_OPENAI

def ask_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    text = (invocation.arg('text', '') or '').strip()
    if text:
        set_pending_prompt(text)                      # one-shot handoff to the pane
        status = 'opened the context pane with your prompt'
    else:
        status = 'opened the context pane'
    return CommandResult(open_widget=WIDGET_OPENAI, status=status)
```

The handler is **pure / return-only**: it stashes the optional `<text>` via a module-level
one-shot seed (`set_pending_prompt` / `take_pending_prompt`) and RETURNS a
`CommandResult(open_widget=…)`. The applier opens the widget; the handler itself POSTs
nothing — the widget owns the LLM call. This is the same `open_widget` bridge any command
can use (see [plugins.md](plugins.md)).

The manifest `glyfi/plugins/builtin/openai_pane.json` wires both the widget factory and the
`/ask` command:

```json
{
  "plugin": "openai-context-pane",
  "widgets": [
    {"name": "openai_pane", "factory": "glyfi.contrib.openai_pane.widget:OpenAIPaneWidget"}
  ],
  "commands": [
    {
      "name": "ask",
      "description": "open the OpenAI context pane (optionally seeded with a first prompt)",
      "handler": "glyfi.contrib.openai_pane.plugin:ask_handler",
      "args": {"positionals": [{"name": "text", "required": false, "rest": true}]}
    }
  ]
}
```

The factory ref resolves under the default allowlist because it includes `glyfi.contrib`.

---

## How the pane uses only the public seams

`glyfi/contrib/openai_pane/widget.py` consumes the `Widget` + `WidgetContext` contracts:

- `open(ctx)` — builds an `OpenAIClient` from `load_openai_config()`, seeds the prompt
  buffer from the one-shot `/ask` text, and pushes a greeting status via
  `ctx.push_status(...)`.
- `handle_key(key)` — printable → append to the prompt buffer; Backspace → edit; Enter →
  submit ONE completion. Returns True for keys it handles, False otherwise (so the host's
  Esc still closes). NEVER auto-loops — one Enter, one call.
- `lines(rect)` — PURE text: the rendered `(user, assistant)` transcript + the live prompt
  line. The host frames it and the View clips it to the content rect.

On submit, the pane builds the message list — `[optional system] + prior (user, assistant)
pairs + the new user prompt` — calls `client.complete(...)` exactly once, appends the reply
to the transcript, clears the buffer, and pushes a status. On an `OpenAIError` it surfaces
the error **in the transcript + status** (fail loud, but visible — never crash the pane).

The pane reaches the surrounding app ONLY through the scoped `WidgetContext` (`push_status`,
`emit`, `request_close`) — it never imports the ViewModel and has no core privileges.

---

## The client and the request/response shape

`glyfi/contrib/openai_pane/client.py` is a tiny stdlib `urllib` client. The OpenAI wire
keys live ONLY here — never in `glyfi.protocol`.

```python
OPENAI_CHAT_PATH = "/chat/completions"     # appended to base_url

class OpenAIClient:
    def __init__(self, config: OpenAIConfig, *, fetch=None): ...
    def complete(self, messages: List[ChatMessage]) -> str: ...
```

**Request** — a standard OpenAI chat-completions body, POSTed to `base_url +
/chat/completions` with an `Authorization: Bearer <key>` header (and an optional
`OpenAI-Organization` header):

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system",    "content": "You are a terse assistant."},
    {"role": "user",      "content": "summarize this file"},
    {"role": "assistant", "content": "..."},
    {"role": "user",      "content": "and the tests?"}
  ]
}
```

**Response** — the client parses `choices[0].message.content`:

```json
{"choices": [{"message": {"role": "assistant", "content": "Here is a summary…"}}]}
```

Fail-loud throughout: an empty key, an HTTP error (it reads the body and raises
`OpenAIError(parsed message, code=status)`), or a malformed response (missing
`choices`/`message`/`content`) all raise `OpenAIError` — never a silent empty reply.

### The injectable fetch seam (for tests)

The HTTP fetch is behind an injectable `fetch` seam so a test can stub the network with no
real socket and no real key:

```python
from glyfi.contrib.openai_pane.client import OpenAIClient, OpenAIConfig, ChatMessage

def fake_fetch(url, body, headers, timeout):
    return '{"choices":[{"message":{"role":"assistant","content":"hi"}}]}'

client = OpenAIClient(OpenAIConfig(api_key="test"), fetch=fake_fetch)
assert client.complete([ChatMessage("user", "hello")]) == "hi"
```

> The pane is a real, working plugin: type a prompt and it POSTs one OpenAI
> chat-completions request and renders the assistant message. The only network call this
> plugin makes is to the OpenAI `/chat/completions` endpoint.
