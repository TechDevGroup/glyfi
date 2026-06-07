# PgUp reveals older turns above the bottom-anchored newest

### Given

- a fresh app on a small window
- a seeded transcript of eight turns (the newest sits at the bottom)

### When

- I press PgUp to scroll older turns into view

### Then

- no content line is ellipsized

## 1. Press(339)

~~~text
┌─ mode:NORMAL ────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: (none) · q quits                  │
│ uitest-1          8          chat          subj-7          8 │
│ ──────────────────────────────────────────────────────────── │
│    ok  seq7: 'staged:m6'                                     │
│ ▾ >#7 [chat] subj-7 <- 'm7'                                  │
│ turn #7 staged (seq 8) -- STOP, waiting for the next turn    │
│ ──────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker             │
│ ──────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                      local time 00:00:00 │
└──────────────────────────────────────────────────────────────┘
~~~
