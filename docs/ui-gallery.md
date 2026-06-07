# glyfi UI gallery

Each section below is a Markdown *screen fence* -- the live headless UI captured through the same Painting the curses View renders. Regenerate with `python -m glyfi.contrib.docs_capture.gallery`.

## fresh screen (NORMAL)

~~~text
┌─ fresh screen ───────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: (none) · q quits                                      │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│ ready -- s to prompt, / for the command palette                                  │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## command palette (filtered)

~~~text
┌─ palette: /co ───────────────────────────────────────────────────────────────────┐
│ ▸ /config                                     open the traversable config editor │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## config editor

~~~text
┌─ config ───────────────────────────────────────────┐
│   -- CONFIG (↑↓ move · Enter edit · Esc/← back) -- │
│ ▸ state[0] = session                               │
│   state[1] = seq                                   │
│   state[2] = mode                                  │
│   state[3] = subject                               │
│   state[4] = turns                                 │
│   details_left[0] = cwd                            │
│   details_right[0] = localtime                     │
│   -- INPUTS --                                     │
│   scroll delta (rows/step): 1                      │
│   pgup/pgdn overlap (rows): 3                      │
│   status TTL (seconds): 4.0                        │
└────────────────────────────────────────────────────┘
~~~

## prompt-entry modal

~~~text
┌─ prompt ─────────────────────────────────────────────────────────────────────────┐
│   -- PROMPT (type · ↓ next field · Enter walk ONE turn · ↑ back to input · Es... │
│ ▸ subject:                                                                       │
│   text:                                                                          │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## OpenAI context pane

~~~text
┌─ /ask pane ──────────────────────────────────────┐
│ set GLYFI_OPENAI_API_KEY to ask (no api key set) │
│                                                  │
│ type a prompt, Enter to ask, Esc to close        │
│                                                  │
│ >                                                │
└──────────────────────────────────────────────────┘
~~~
