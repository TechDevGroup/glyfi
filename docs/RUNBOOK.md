# RUNBOOK

The top-level operator runbook for **glyfi**. Step-by-step, copy-pasteable.

glyfi is an HTTP-only curses TUI: it talks to a server that speaks the neutral turn
protocol (`POST /v1/turn`, `GET /v1/subjects`). This runbook covers launching it, driving
it, and the bundled OpenAI context pane.

---

## 1. Install

```bash
pip install -e .[dev]
python -c "import glyfi; print(glyfi.__version__)"
```

The runtime is stdlib-only; `[dev]` adds `pytest`.

---

## 2. Run the app

```bash
glyfi --base-url http://127.0.0.1:8800
```

Options:

| flag             | meaning                                                              |
| ---------------- | ------------------------------------------------------------------- |
| `--base-url URL` | the server origin; falls back to `GLYFI_BASE_URL` if omitted        |
| `--session S`    | the session id to run over (default `glyfi-1`)                       |
| `--list`         | print the server-exposed routable subjects and exit (no app launch) |

Equivalent module form:

```bash
python -m glyfi --base-url http://127.0.0.1:8800 --session my-session
```

### Discover subjects without launching

```bash
glyfi --base-url http://127.0.0.1:8800 --list
```

This GETs `/v1/subjects` and prints one `subject  (label '…')` per line, then exits. Use
it to see which subjects the server routes before you start a session.

---

## 3. The screen

The default fenced layout (top → bottom):

```
 glyfi                                              [mode:chat]   ← title
 session my-session · seq 0 · mode chat · subject - · turns 0     ← state strip
 ───────────────────────────────────────────────────────────────  header rule
 (content view: transcript / help / a widget overlay)            ← content (FILL)
 ready -- s to prompt, / for the command palette                 ← status (ephemeral ticker)
 ───────────────────────────────────────────────────────────────  input fence top
  > type / for commands · ↑↓ history · Tab ticker                ← input + hint
 ───────────────────────────────────────────────────────────────  input fence bottom
 ~/work                                            12:00:00       ← details bar
```

The **state strip** and the **details bar** are config-bound: each slot shows a field
alias (`session`, `seq`, `mode`, `subject`, `turns`, `cwd`, `localtime`, …). You can
rebind or hide them — see [config.md](config.md).

---

## 4. Key bindings (NORMAL mode)

| key                 | action                                                    |
| ------------------- | --------------------------------------------------------- |
| `s`                 | open the prompt form (subject + text), walk **one** turn  |
| `m`                 | cycle the current mode label                              |
| `/`                 | open the slash-command palette                            |
| `c`                 | enter content traversal (a wrap-aware line caret)         |
| `PgUp` / `PgDn`     | scroll content a page (minus the overlap continuity row)  |
| `Ctrl-U` / `Ctrl-D` | scroll half a page up / down                              |
| `↑` / `↓`           | recall older / newer submitted input                      |
| `Tab`               | cycle the ephemeral status-ticker ring                    |
| `q`                 | quit — press `q` again to confirm, any other key cancels  |

All NORMAL-mode keys are rebindable through a custom `AppSettings` (see
[config.md](config.md)).

---

## 5. Walking a turn

1. Press `s`. The prompt form opens (state `PROMPT`): two fields, **subject** then
   **text**.
2. Type the **subject** (a routing id the server interprets; it may be left as you like —
   the core never interprets it). Press `Tab` / `↓` to move to the **text** field.
3. Type the message **text**.
4. Press `Enter` to submit. glyfi sends **exactly one** `TurnRequest` to the server, then
   STOPS. The staged response is recorded onto the transcript and shown in the content
   view. There is no auto-loop.
5. Press `Esc` (or Backspace on an empty field) to cancel the form.

The mode label sent with the turn is the current `mode` (cycled with `m`). Modes are plain
labels; the core never interprets them.

---

## 6. The command palette

1. Press `/`. The palette opens (state `PALETTE`) with the buffer seeded to `/`.
2. Type to filter; `↑`/`↓` to move the selection; `Enter` to run the selected command.
3. `Esc` / `←` / Backspace (on the bare `/`) closes the palette.

Built-in commands:

| command   | effect                                            |
| --------- | ------------------------------------------------- |
| `prompt`  | open the prompt form (same as `s`)                |
| `clear`   | clear the content view                            |
| `config`  | open the config editor                            |
| `mode`    | cycle the current mode label                      |
| `help`    | push the keybindings/about help into the content  |
| `about`   | open the read-only help widget overlay            |
| `quit`    | request quit (destructive-confirm)                |

Plugins add more commands (e.g. `echo`, `ping`, `ask`). Run a command with arguments by
typing it in full, e.g. `/echo hello world`.

---

## 7. The config editor

1. Press `/` then choose `config` (or run `/config`). State becomes `CONFIG`.
2. `↑`/`↓` walk the combined list of slot positions (state + details groups) followed by
   the input knobs (`scroll_delta`, `page_overlap`, `status_ttl_seconds`).
3. On a **slot** row, `Enter` descends into the alias list; choose an alias with `Enter`
   to rebind that slot to a field. On an **input knob** row, `←`/`→` adjust the value
   within its floor/ceiling.
4. `Esc` / `←` / Backspace backs out one level, then closes.

Changes persist to the `UserConfig` JSON (see [config.md](config.md)).

---

## 8. The OpenAI context pane (`/ask`)

The bundled first-party plugin opens an OpenAI chat-completions pane.

```bash
export GLYFI_OPENAI_API_KEY=sk-...
export GLYFI_OPENAI_MODEL=gpt-4o-mini        # optional; default is gpt-4o-mini
export GLYFI_OPENAI_SYSTEM_PROMPT="You are a terse code reviewer."   # optional
glyfi --base-url http://127.0.0.1:8800
```

In the app:

1. Press `/`, choose `ask` (or type `/ask`). The context pane opens as a widget overlay.
2. Optionally seed a first prompt: `/ask summarize this file` — the text is handed to the
   pane as its opening prompt.
3. In the pane: type a prompt, press `Enter`. The pane POSTs **one** chat-completions
   request and renders the assistant reply below. One Enter = one completion (no loop).
4. `Esc` closes the pane.

If `GLYFI_OPENAI_API_KEY` is not set, the pane renders a fail-loud `set
GLYFI_OPENAI_API_KEY to ask` line and refuses to send (no crash). Full reference:
[openai-pane.md](openai-pane.md).

---

## 9. Content scrolling and traversal

- **Scroll** with `PgUp`/`PgDn` (or `Ctrl-U`/`Ctrl-D`). The content view is bottom-anchored
  and auto-follows new output. Once you scroll up, auto-follow locks and a `▼ N new below`
  indicator counts content that arrived while you were reading; scroll back to the bottom
  to re-enable auto-follow.
- **Traverse** with `c`: a wrap-aware line caret over the content rows (distinct from
  scrolling). `Esc` exits traversal.

---

## 10. Quitting

Press `q`. glyfi shows a destructive-confirm prompt (`quit? press q again to confirm · any
other key cancels`). Press `q` again to quit, or any other key to cancel. This is the only
RED / destructive confirm in the UI (see [theme-a11y.md](theme-a11y.md)).
