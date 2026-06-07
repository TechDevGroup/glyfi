# one prompt walks EXACTLY one turn (no auto-loop)

### Given

- a fresh app with a scripted transport
- the next prompt is (subj-7, "send it")

### When

- I clear events
- I invoke request_prompt once

### Then

- the transcript length is 1
- exactly one TurnRecorded event was emitted
- the seq is 1
- the content shows the staged reply 'STAGED-7'

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
│ uitest-1               1               chat               subj-7               1 │
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
│ ▾ >#0 [chat] subj-7 <- 'send it'                                                 │
│    ok  seq1: 'STAGED-7'                                                          │
│ turn #0 staged (seq 1) -- STOP, waiting for the next turn                        │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
