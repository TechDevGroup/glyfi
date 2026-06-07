# the config editor opens with its bound slots

### Given

- a fresh app

### When

- I invoke open_config

### Then

- mode is CONFIG
- the state strip cell is highlighted

## 1. Invoke('open_config')

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
