# the traverse caret starts at the newest row and moves wrap-aware

### Given

- a fresh app on a narrow window
- a seeded transcript whose newest turn carries a long wrapping text

### When

- I enter content traverse
- I press Up one wrapped visual row
- I press Down back toward the newest row

### Then

- mode is TRAVERSE
- a caret marks a content row

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

## 2. Press(259)

~~~text
┌─ mode:TRAVERSE ──────────────────────────────────────────────┐
│ glyfi  [mode:chat]  · Esc: exit traverse -> NORMAL           │
│ uitest-1          3          chat          subj-3          3 │
│ ──────────────────────────────────────────────────────────── │
│     xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│     xxxxxxxx tail-marker'                                    │
│      ok  seq3: 'staged:fn:a                                  │
│     xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│ ▸   xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx │
│     xxxxxxxx tail-marker'                                    │
│ traverse -- ↑↓ move caret (from newest) · → expand · ← co... │
│ ──────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker             │
│ ──────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                      local time 00:00:00 │
└──────────────────────────────────────────────────────────────┘
~~~

## 3. Press(258)

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
