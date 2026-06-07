"""contrib.openai_pane -- the first-party OpenAI chat-completions CONTEXT PANE (the ONE LLM seam).

Three pieces, each behind a public glyfi contract:
  * ``client``  -- a stdlib-``urllib`` OpenAI chat-completions client (config from ``GLYFI_OPENAI_*`` env);
  * ``widget``  -- ``OpenAIPaneWidget``, a ``Widget`` overlay: type a prompt -> POST -> render the reply;
  * ``plugin``  -- the ``/ask`` command handler (the command->widget bridge) + the widget factory.

It is an ORDINARY plugin -- ZERO core privileges. The ONLY network endpoint is the OpenAI chat-completions
path, and it lives ONLY in ``client``.
"""
