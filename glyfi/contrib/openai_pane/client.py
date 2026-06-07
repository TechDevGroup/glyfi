"""contrib.openai_pane.client -- a stdlib-only OpenAI chat-completions client + its env-resolved config.

This is the ONE LLM seam: a tiny ``urllib`` POST to a standard OpenAI-spec chat-completions endpoint. It is an
ordinary plugin component -- it touches NO glyfi core, only stdlib. The public surface:

  * ``OpenAIConfig``        -- a frozen config dataclass (base url / api key / model / org / timeout / system).
  * ``load_openai_config()``-- resolve it from ``GLYFI_OPENAI_*`` env (mirrors ``glyfi.config`` fail-loud style;
                               a bad timeout value FAILS LOUD, never a silent default).
  * ``ChatMessage``         -- one ``{role, content}`` chat item (role in ``system``/``user``/``assistant``).
  * ``OpenAIError``         -- the fail-loud transport / HTTP / parse fault (carries the HTTP status code).
  * ``OpenAIClient``        -- ``complete(messages) -> str``: POST ``{model, messages}`` with a Bearer auth
                               header (+ optional organization header), parse ``choices[0].message.content``.

FAIL LOUD: an HTTP error reads the body + raises ``OpenAIError(parsed message, code=status)``; a malformed
response (missing ``choices``/``message``/``content``) raises ``OpenAIError`` -- never a silent empty reply.
NEVER LOG THE API KEY: the key only ever goes into the ``Authorization`` header; it is not in any message/repr.

Self-contained: stdlib ``os`` / ``json`` / ``urllib`` only. The HTTP fetch is behind an injectable seam
(``fetch``) so a test can stub the network with NO real socket and NO real api key.
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional

# ---- the ONLY network endpoint string for the LLM seam (appended to the base url) --------------------------
OPENAI_CHAT_PATH = "/chat/completions"

# ---- NAMED env keys + defaults (PRESERVE spellings; mirror glyfi.config's fail-loud style) -----------------
ENV_BASE_URL = "GLYFI_OPENAI_BASE_URL"
ENV_API_KEY = "GLYFI_OPENAI_API_KEY"
ENV_MODEL = "GLYFI_OPENAI_MODEL"
ENV_ORG = "GLYFI_OPENAI_ORG"
ENV_TIMEOUT = "GLYFI_OPENAI_TIMEOUT"
ENV_SYSTEM_PROMPT = "GLYFI_OPENAI_SYSTEM_PROMPT"

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30.0

# ---- NAMED wire keys (standard OpenAI chat-completions; owned HERE, never in glyfi.protocol) ---------------
KEY_MODEL = "model"
KEY_MESSAGES = "messages"
KEY_ROLE = "role"
KEY_CONTENT = "content"
KEY_CHOICES = "choices"
KEY_MESSAGE = "message"
KEY_ERROR = "error"

# ---- NAMED HTTP literals (no bare header/method strings at a call site) ------------------------------------
HTTP_POST = "POST"
HEADER_CONTENT_TYPE = "Content-Type"
HEADER_AUTHORIZATION = "Authorization"
HEADER_ORGANIZATION = "OpenAI-Organization"
CONTENT_TYPE_JSON = "application/json"
AUTH_BEARER_PREFIX = "Bearer "

# ---- NAMED roles (PRESERVE) -------------------------------------------------------------------------------
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class OpenAIError(Exception):
    """A fail-loud transport / HTTP / parse fault for the chat-completions seam (carries the HTTP status code).

    ``code`` is the HTTP status when the fault is an HTTP error (else 0 for a local transport / parse fault).
    The api key is NEVER part of the message -- only request/response orientation, so the TUI can show it safely.
    """

    def __init__(self, message: str, *, code: int = 0):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OpenAIConfig:
    """The env-resolved config the client + the pane open against (frozen -- no mid-flight mutation).

    ``api_key`` is required to actually SEND -- an empty key is allowed to CONSTRUCT (so the pane can render a
    fail-loud "set the key" line) but ``OpenAIClient.complete`` fails loud if it is empty at send time. ``org``
    + ``system_prompt`` are optional. The key is held only to build the ``Authorization`` header; never logged.
    """
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    org: str = ""
    timeout: float = DEFAULT_TIMEOUT
    system_prompt: str = ""

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class OpenAIConfigError(Exception):
    """A fail-loud config fault -- a malformed ``GLYFI_OPENAI_*`` value (e.g. a non-numeric timeout)."""


def load_openai_config() -> OpenAIConfig:
    """Resolve an ``OpenAIConfig`` from ``GLYFI_OPENAI_*`` env with NAMED defaults. Fail loud on a bad value.

    A missing key is NOT a fault here (the pane renders a fail-loud "set the key" line instead) -- only a
    malformed timeout (a non-float) fails loud, mirroring ``glyfi.config``'s located fail-loud discipline.
    """
    base_url = os.environ.get(ENV_BASE_URL, DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL
    org = os.environ.get(ENV_ORG, "").strip()
    system_prompt = os.environ.get(ENV_SYSTEM_PROMPT, "")
    raw_timeout = os.environ.get(ENV_TIMEOUT, "").strip()
    if raw_timeout:
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise OpenAIConfigError(
                f"{ENV_TIMEOUT}={raw_timeout!r} is not a number") from exc
        if timeout <= 0:
            raise OpenAIConfigError(f"{ENV_TIMEOUT}={raw_timeout!r} must be positive")
    else:
        timeout = DEFAULT_TIMEOUT
    return OpenAIConfig(base_url=base_url.rstrip("/"), api_key=api_key, model=model,
                        org=org, timeout=timeout, system_prompt=system_prompt)


@dataclass(frozen=True)
class ChatMessage:
    """One chat item: a role (``system``/``user``/``assistant``) + its content text -> a wire ``{role, content}``."""
    role: str
    content: str

    def to_wire(self) -> dict:
        return {KEY_ROLE: self.role, KEY_CONTENT: self.content}


# the HTTP fetch seam: (url, body_bytes, headers, timeout) -> response_text. Injectable so a test stubs the
# network with NO real socket. The default is the stdlib ``urllib`` implementation below.
Fetch = Callable[[str, bytes, dict, float], str]


def _urllib_fetch(url: str, body: bytes, headers: dict, timeout: float) -> str:
    """The default fetch: a stdlib ``urllib`` POST. On an ``HTTPError`` read the body + raise ``OpenAIError``."""
    request = urllib.request.Request(url, data=body, headers=headers, method=HTTP_POST)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:                                  # the body may be unreadable -- still fail loud below
            raw = ""
        raise OpenAIError(_http_error_message(exc.code, raw), code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise OpenAIError(f"openai request failed: {exc.reason}") from exc


def _http_error_message(status: int, raw_body: str) -> str:
    """Build a fail-loud message from an HTTP error -- prefer the OpenAI error envelope's ``message`` if present."""
    detail = raw_body.strip()
    try:
        payload = json.loads(raw_body)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get(KEY_ERROR)
        if isinstance(error, dict) and isinstance(error.get(KEY_MESSAGE), str):
            detail = error[KEY_MESSAGE]
        elif isinstance(error, str):
            detail = error
    return f"openai http {status}: {detail}" if detail else f"openai http {status}"


class OpenAIClient:
    """The chat-completions client -- ``complete(messages) -> str`` via a single ``urllib`` POST. stdlib only.

    The HTTP fetch is behind an injectable ``fetch`` seam (defaults to the stdlib ``urllib`` impl) so a test can
    stub the network with NO real socket / NO real key. ``complete`` builds the standard OpenAI body
    ``{model, messages:[{role,content}]}``, sends it with a ``Bearer`` auth header (+ optional org header), and
    parses ``choices[0].message.content`` -- failing loud (``OpenAIError``) on a missing key, an HTTP error, or a
    malformed response. The api key is held ONLY to build the auth header; it is never logged or put in an error.
    """

    def __init__(self, config: OpenAIConfig, *, fetch: Optional[Fetch] = None):
        self._config = config
        self._fetch = fetch or _urllib_fetch

    @property
    def config(self) -> OpenAIConfig:
        return self._config

    def _url(self) -> str:
        return self._config.base_url.rstrip("/") + OPENAI_CHAT_PATH

    def _headers(self) -> dict:
        headers = {
            HEADER_CONTENT_TYPE: CONTENT_TYPE_JSON,
            HEADER_AUTHORIZATION: AUTH_BEARER_PREFIX + self._config.api_key,
        }
        if self._config.org:
            headers[HEADER_ORGANIZATION] = self._config.org
        return headers

    def complete(self, messages: List[ChatMessage]) -> str:
        """Send ``messages`` to the chat-completions endpoint and return the assistant content. Fail loud throughout.

        Requires a non-empty api key (else ``OpenAIError``). POSTs ``{model, messages}`` with the Bearer auth
        header; parses ``choices[0].message.content``. NEVER loops / batches -- one call, one completion.
        """
        if not self._config.has_key:
            raise OpenAIError(f"no api key set ({ENV_API_KEY}); cannot send")
        if not messages:
            raise OpenAIError("cannot send an empty message list")
        body = json.dumps({
            KEY_MODEL: self._config.model,
            KEY_MESSAGES: [m.to_wire() for m in messages],
        }).encode("utf-8")
        raw = self._fetch(self._url(), body, self._headers(), self._config.timeout)
        return self._parse_content(raw)

    def _parse_content(self, raw: str) -> str:
        """Parse ``choices[0].message.content`` out of a response body -- fail loud (located) on any bad shape."""
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise OpenAIError(f"openai response is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise OpenAIError(f"openai response must be a JSON object, got {type(payload).__name__}")
        choices = payload.get(KEY_CHOICES)
        if not isinstance(choices, list) or not choices:
            raise OpenAIError("openai response has no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise OpenAIError("openai response choice is not an object")
        message = first.get(KEY_MESSAGE)
        if not isinstance(message, dict):
            raise OpenAIError("openai response choice has no message")
        content = message.get(KEY_CONTENT)
        if not isinstance(content, str):
            raise OpenAIError("openai response message has no string content")
        return content
