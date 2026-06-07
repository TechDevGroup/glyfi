# /ask from the palette opens the context pane (no-key state)

### Given

- a fresh app with the context-pane plugin loaded

### When

- I press '/' to open the slash palette
- I type 'ask' to select the /ask command
- I press Enter to bridge to opening the pane widget

### Then

- the pane widget is active (mode is WIDGET)
- with no api key set the pane shows its fail-loud no-key line (no request is made)

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

## 2. Type('ask')

~~~text
┌─ mode:PALETTE ───────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › palette  · Esc: close palette -> NORMAL                    │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ ▸ /ask      open the OpenAI context pane (optionally seeded with a first prompt) │
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
│  > /ask                                                                          │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~

## 3. Press(343)

~~~text
┌─ mode:WIDGET ────────────────────────────────────────────────────────────────────┐
│ glyfi  [mode:chat]  › widget › context  · Esc: close widget -> NORMAL            │
│ uitest-1                 0                chat                -                0 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ set GLYFI_OPENAI_API_KEY to ask (no api key set)                                 │
│                                                                                  │
│ type a prompt, Enter to ask, Esc to close                                        │
│                                                                                  │
│ >                                                                                │
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
│ opened the context pane                                                          │
│ ──────────────────────────────────────────────────────────────────────────────── │
│  > type / for commands · ↑↓ history · Tab ticker                                 │
│ ──────────────────────────────────────────────────────────────────────────────── │
│ working dir ~/glyfi                                          local time 00:00:00 │
└──────────────────────────────────────────────────────────────────────────────────┘
~~~
