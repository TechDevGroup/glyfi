# palette walkthrough

A small BDD flow (open the palette -> type a filter -> open the config editor) rendered through `flow_to_markdown` -- the UI state is embedded between the steps.

## 1. Invoke('open_palette')

~~~text
┌─ mode:PALETTE ───────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › palette  · Esc: close palette -> NORMAL                    │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ ▸ /prompt                     walk exactly one turn (prompts for subject + text) │
│   /clear                            clear the content view / stick to the newest │
│   /config                                     open the traversable config editor │
│   /mode                                             cycle the current mode label │
│   /help                              push the command list into the content view │
│   /about                  open the help/about WIDGET (the pluggable widget seam) │
│   /quit                                                             quit the app │
│   /capture    capture the live screen (or one region) as a Markdown screen fence │
│   /echo                                echo the given text into the content view │
│   /ping                       push a pong status (an arg-less reference command) │
│   /ask      open the OpenAI context pane (optionally seeded with a first prompt) │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│ palette -- Up/Down to navigate, Enter to run, type to filter, Esc to cancel      │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > /                                                                             │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## 2. Type('co')

~~~text
┌─ mode:PALETTE ───────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › palette  · Esc: close palette -> NORMAL                    │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ ▸ /config                                     open the traversable config editor │
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
│ palette -- Up/Down to navigate, Enter to run, type to filter, Esc to cancel      │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > /co                                                                           │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## 3. Invoke('open_config')

~~~text
┌─ mode:CONFIG ────────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › config  · Esc: back / close config -> NORMAL               │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│   -- CONFIG (↑↓ move · Enter edit · Esc/← back) --                               │
│ ▸ state[0] = session                                                             │
│   state[1] = seq                                                                 │
│   state[2] = mode                                                                │
│   state[3] = subject                                                             │
│   state[4] = turns                                                               │
│   details_left[0] = cwd                                                          │
│   details_right[0] = localtime                                                   │
│   -- INPUTS --                                                                   │
│   scroll delta (rows/step): 1                                                    │
│   pgup/pgdn overlap (rows): 3                                                    │
│   status TTL (seconds): 4.0                                                      │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│                                                                                  │
│ config -- arrows move (area highlights), Enter to rebind, Esc to exit            │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > /co                                                                           │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
