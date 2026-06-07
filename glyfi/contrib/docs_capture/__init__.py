"""contrib.docs_capture -- render the LIVE UI through the existing View/Painting layer into Markdown.

This is an ORDINARY first-party plugin (no core privileges): it imports only the public ``glyfi.ui`` view /
layout / driver types, the public ``glyfi.plugins`` / ``glyfi.uitest`` contracts, and stdlib. It captures what
the terminal would show -- the SAME ``Painting`` the curses View consumes -- and wraps it as a Markdown
"screen fence" so a runbook / a flow walkthrough can embed real UI state.

Three layers, each behind a public contract:
  * ``capture``       -- the pure Markdown render target over a ``Painting`` + solved layout + ``Size``.
  * ``markdown_flow`` -- a BDD flow trace -> a per-step Markdown document (state embedded between steps).
  * ``plugin``        -- the ``/capture`` command (push the current frame's Markdown into the content view).

``gallery`` is the dogfood: it drives a headless app through representative states and emits one MD document.
"""
