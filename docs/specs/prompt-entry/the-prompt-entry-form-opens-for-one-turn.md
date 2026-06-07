# the prompt-entry form opens for one turn

### Given

- a fresh app

### When

- I invoke open_prompt

### Then

- mode is PROMPT

## 1. Invoke('open_prompt')

~~~text
┌─ mode:PROMPT ────────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › prompt › subject  · Esc: cancel prompt -> NORMAL           │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│   -- PROMPT (type · ↓ next field · Enter walk ONE turn · ↑ back to input · Es... │
│ ▸ subject:                                                                       │
│   text:                                                                          │
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
│ prompt -- type the subject, ↓ to text, Enter to walk ONE turn, ↑ back to inpu... │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
