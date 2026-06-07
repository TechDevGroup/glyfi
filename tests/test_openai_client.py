"""Hermetic tests for the OpenAI chat-completions client + its env config -- NO real network, NO real api key.

The HTTP fetch is injected (the ``fetch`` seam), so every test stubs the network. We verify: the request shape
(model + messages + Bearer header + the org header only when set), the response parse, an HTTPError mapping to a
fail-loud ``OpenAIError``, the env config fail-loud on a bad timeout, and that the api key NEVER leaks into an
error message.
"""
import json

import pytest

from glyfi.contrib.openai_pane.client import (
    ChatMessage,
    OpenAIClient,
    OpenAIConfig,
    OpenAIConfigError,
    OpenAIError,
    OPENAI_CHAT_PATH,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    ENV_ORG,
    ENV_TIMEOUT,
    ENV_SYSTEM_PROMPT,
    load_openai_config,
)


def _ok_body(content="hello there"):
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})


class _Recorder:
    """A fetch stub that records the call args and returns a canned body (or raises a canned error)."""

    def __init__(self, body=None, raises=None):
        self.body = body if body is not None else _ok_body()
        self.raises = raises
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.body


# ---- request shape ----------------------------------------------------------------------------------------

def test_complete_posts_model_and_messages_with_bearer():
    rec = _Recorder()
    cfg = OpenAIConfig(base_url="https://example.test/v1", api_key="sk-secret", model="gpt-test")
    client = OpenAIClient(cfg, fetch=rec)

    out = client.complete([ChatMessage("user", "hi")])

    assert out == "hello there"
    call = rec.calls[0]
    assert call["url"] == "https://example.test/v1" + OPENAI_CHAT_PATH
    sent = json.loads(call["body"].decode("utf-8"))
    assert sent["model"] == "gpt-test"
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert call["headers"]["Authorization"] == "Bearer sk-secret"
    assert call["timeout"] == cfg.timeout


def test_org_header_only_present_when_set():
    rec_no_org = _Recorder()
    OpenAIClient(OpenAIConfig(api_key="k"), fetch=rec_no_org).complete([ChatMessage("user", "x")])
    assert "OpenAI-Organization" not in rec_no_org.calls[0]["headers"]

    rec_org = _Recorder()
    OpenAIClient(OpenAIConfig(api_key="k", org="org-123"), fetch=rec_org).complete([ChatMessage("user", "x")])
    assert rec_org.calls[0]["headers"]["OpenAI-Organization"] == "org-123"


def test_system_and_pair_message_order_preserved_on_the_wire():
    rec = _Recorder()
    client = OpenAIClient(OpenAIConfig(api_key="k"), fetch=rec)
    client.complete([
        ChatMessage("system", "be terse"),
        ChatMessage("user", "q1"),
        ChatMessage("assistant", "a1"),
        ChatMessage("user", "q2"),
    ])
    sent = json.loads(rec.calls[0]["body"].decode("utf-8"))
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "user"]


# ---- response parse ---------------------------------------------------------------------------------------

def test_parse_extracts_first_choice_content():
    rec = _Recorder(body=_ok_body("the answer"))
    out = OpenAIClient(OpenAIConfig(api_key="k"), fetch=rec).complete([ChatMessage("user", "x")])
    assert out == "the answer"


@pytest.mark.parametrize("bad", [
    "{not json",
    json.dumps({"choices": []}),
    json.dumps({"choices": [{}]}),
    json.dumps({"choices": [{"message": {}}]}),
    json.dumps({}),
])
def test_malformed_response_fails_loud(bad):
    rec = _Recorder(body=bad)
    with pytest.raises(OpenAIError):
        OpenAIClient(OpenAIConfig(api_key="k"), fetch=rec).complete([ChatMessage("user", "x")])


# ---- HTTP error mapping -----------------------------------------------------------------------------------

def test_httperror_from_default_fetch_maps_to_openai_error():
    import io
    import urllib.error

    body = json.dumps({"error": {"message": "you are rate limited", "type": "rate_limit", "code": 429}})

    def boom(url, data=None, headers=None, timeout=None):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {},
                                     io.BytesIO(body.encode("utf-8")))

    # drive the REAL default fetch by stubbing urlopen only.
    import glyfi.contrib.openai_pane.client as client_mod
    original = client_mod.urllib.request.urlopen
    client_mod.urllib.request.urlopen = boom
    try:
        with pytest.raises(OpenAIError) as exc:
            OpenAIClient(OpenAIConfig(api_key="k")).complete([ChatMessage("user", "x")])
    finally:
        client_mod.urllib.request.urlopen = original
    assert exc.value.code == 429
    assert "you are rate limited" in str(exc.value)


def test_no_key_fails_loud_without_leaking():
    client = OpenAIClient(OpenAIConfig(api_key=""), fetch=_Recorder())
    with pytest.raises(OpenAIError) as exc:
        client.complete([ChatMessage("user", "x")])
    assert ENV_API_KEY in str(exc.value)


def test_api_key_never_in_error_text():
    secret = "sk-do-not-leak-me"
    rec = _Recorder(raises=OpenAIError("openai http 500: boom", code=500))
    client = OpenAIClient(OpenAIConfig(api_key=secret), fetch=rec)
    with pytest.raises(OpenAIError) as exc:
        client.complete([ChatMessage("user", "x")])
    assert secret not in str(exc.value)


# ---- env config -------------------------------------------------------------------------------------------

def _clear_env(monkeypatch):
    for key in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL, ENV_ORG, ENV_TIMEOUT, ENV_SYSTEM_PROMPT):
        monkeypatch.delenv(key, raising=False)


def test_load_config_defaults(monkeypatch):
    _clear_env(monkeypatch)
    cfg = load_openai_config()
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.api_key == ""
    assert cfg.model == DEFAULT_MODEL
    assert cfg.timeout == DEFAULT_TIMEOUT
    assert cfg.has_key is False


def test_load_config_reads_env(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_BASE_URL, "https://proxy.test/v1/")
    monkeypatch.setenv(ENV_API_KEY, "sk-abc")
    monkeypatch.setenv(ENV_MODEL, "gpt-x")
    monkeypatch.setenv(ENV_ORG, "org-9")
    monkeypatch.setenv(ENV_TIMEOUT, "12.5")
    monkeypatch.setenv(ENV_SYSTEM_PROMPT, "be nice")
    cfg = load_openai_config()
    assert cfg.base_url == "https://proxy.test/v1"   # trailing slash stripped
    assert cfg.api_key == "sk-abc"
    assert cfg.model == "gpt-x"
    assert cfg.org == "org-9"
    assert cfg.timeout == 12.5
    assert cfg.system_prompt == "be nice"
    assert cfg.has_key is True


def test_load_config_bad_timeout_fails_loud(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_TIMEOUT, "not-a-number")
    with pytest.raises(OpenAIConfigError):
        load_openai_config()


def test_load_config_nonpositive_timeout_fails_loud(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_TIMEOUT, "0")
    with pytest.raises(OpenAIConfigError):
        load_openai_config()
