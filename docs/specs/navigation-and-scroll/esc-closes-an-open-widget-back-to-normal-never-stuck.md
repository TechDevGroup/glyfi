# Esc closes an open widget back to NORMAL (never stuck)

### Given

- a fresh app
- a widget opened over the content region

### When

- I press Esc, the reserved host key

### Then

- mode is NORMAL (the modal dead-end is gone)

## 1. Press(27)

~~~text
┌─ mode:NORMAL ────────────────────────────────────────────────────────────────────┐
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
│ help — ↑↓ to read, Esc to close                                                  │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
