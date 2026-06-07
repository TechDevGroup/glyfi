"""contrib -- first-party, ordinary plugins built ON TOP of the public glyfi seams (no core privileges).

Everything under here is an ORDINARY plugin: it imports ONLY the public ``glyfi.widgets`` / ``glyfi.plugins``
contracts + stdlib. The one shipped plugin is the OpenAI context pane (``contrib.openai_pane``) -- a real,
working LLM seam that POSTs a chat-completions request and renders the assistant reply in a content pane.
"""
