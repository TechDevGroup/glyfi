# a scripted fault is fail-loud and does NOT advance the seq

### Given

- a fresh app with a scripted fault for (subj-9, "forbidden")
- the next prompt is (subj-9, "forbidden")

### When

- I clear events
- I invoke request_prompt once

### Then

- the transcript length is 1 (the failed turn is recorded, never swallowed)
- the seq is 0 (a faulted turn must NOT advance the seq)
- exactly one TurnRecorded event was emitted (no retry loop)
- the content shows the 403 fail-loud envelope

## 1. ClearEvents()

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
│ ready -- s to prompt, / for the command palette                                  │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## 2. Invoke('request_prompt')

~~~text
┌─ mode:NORMAL ────────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: (none) · q quits                                      │
│ uitest-1               0               chat               subj-9               1 │
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
│ ▾ >#0 [chat] subj-9 <- 'forbidden'                                               │
│    ERR (seq NOT advanced): http 403 turn_gate_denied: turn was gated             │
│ turn #0 FAILED (fail-loud, seq NOT advanced): http 403 turn_gate_denied: turn... │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
