# a long content line wraps with no ellipsis

### Given

- a fresh app on a narrow window
- a seeded transcript whose newest turn carries a long wrapping text

### When

- I enter content traverse

### Then

- no content line is ellipsized
- the wrapped tail 'tail-marker' is present

## 1. Press('c')

~~~text
┌─ mode:TRAVERSE ──────────────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: exit traverse -> NORMAL           │
│ uitest-1          3          chat          subj-3          3 │
│ ──────────────────────────────────────────────────────────── │
│     xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│     xxxxxxxx tail-marker'                                    │
│      ok  seq3: 'staged:fn:a                                  │
│     xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│     xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│ ▸   xxxxxxxx tail-marker'                                    │
│ traverse -- ↑↓ move caret (from newest) · → expand · ← co... │
│ ──────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker             │
│ ──────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                      local time 00:00:00 │
└──────────────────────────────────────────────────────────────┘
~~~
