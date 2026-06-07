# filter to config and open it

### Given

- a fresh app

### When

- I press '/' to open the slash palette
- I type 'config' to filter the command list
- I press Enter to run the exact-name config command

### Then

- mode is CONFIG and the state strip cell is highlighted

## 1. Press('/')

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

## 2. Type('config')

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
│  > /config                                                                       │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## 3. Press(343)

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
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
