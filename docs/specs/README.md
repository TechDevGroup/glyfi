# BDD spec docs

Every document below is generated from the runnable BDD spec catalog (`glyfi.uitest.catalog`) -- the SAME specs the test suite runs. Each file shows one scenario's Given/When/Then and a full-frame screen capture after every step. Regenerate with `python -m glyfi.contrib.docs_capture.specdocs --write`.

## command palette

- [filter to config and open it](command-palette/filter-to-config-and-open-it.md)

## config editor

- [the config editor opens with its bound slots](config-editor/the-config-editor-opens-with-its-bound-slots.md)

## status ticker

- [a pushed status expires after its TTL and Tab cycles the ring](status-ticker/a-pushed-status-expires-after-its-ttl-and-tab-cycles-the-ring.md)

## input history

- [Up recalls older submitted inputs](input-history/up-recalls-older-submitted-inputs.md)

## navigation and scroll

- [PgUp reveals older turns above the bottom-anchored newest](navigation-and-scroll/pgup-reveals-older-turns-above-the-bottom-anchored-newest.md)
- [Esc closes an open widget back to NORMAL (never stuck)](navigation-and-scroll/esc-closes-an-open-widget-back-to-normal-never-stuck.md)

## content traverse

- [a long content line wraps with no ellipsis](content-traverse/a-long-content-line-wraps-with-no-ellipsis.md)
- [the traverse caret starts at the newest row and moves wrap-aware](content-traverse/the-traverse-caret-starts-at-the-newest-row-and-moves-wrap-aware.md)

## prompt entry

- [the prompt-entry form opens for one turn](prompt-entry/the-prompt-entry-form-opens-for-one-turn.md)

## the one turn law

- [one prompt walks EXACTLY one turn (no auto-loop)](the-one-turn-law/one-prompt-walks-exactly-one-turn-no-auto-loop.md)
- [a scripted fault is fail-loud and does NOT advance the seq](the-one-turn-law/a-scripted-fault-is-fail-loud-and-does-not-advance-the-seq.md)

## the openai context pane

- [/ask from the palette opens the context pane (no-key state)](the-openai-context-pane/ask-from-the-palette-opens-the-context-pane-no-key-state.md)
