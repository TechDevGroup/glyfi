# Configuration

glyfi is config-driven: process startup reads `GLYFI_*` environment variables, and a
persisted per-user `UserConfig` JSON file carries UI preferences (slot binds, region
visibility, theme, input knobs). This document covers both, plus the slot/field registry
and the in-app config editor.

---

## Startup config (`GLYFI_*` env)

Module: `glyfi/config.py`. Every tunable is a NAMED env key with a NAMED default. A
malformed value FAILS LOUD (`ConfigError`) — never a silent fallback.

| env var                  | default                  | meaning                                          |
| ------------------------ | ------------------------ | ------------------------------------------------ |
| `GLYFI_BASE_URL`         | `http://127.0.0.1:8800`  | the server origin (the transport target)         |
| `GLYFI_MODES`            | `chat`                   | CSV of plain mode labels (must yield ≥ 1 label)  |
| `GLYFI_SESSION_SEQ_START`| `0`                      | the starting sequence number (must be an int)    |
| `GLYFI_PLUGINS`          | (empty)                  | the drop-in plugin manifest directory            |
| `GLYFI_PLUGIN_ALLOW`     | (empty)                  | CSV/`os.pathsep` allowlist of dotted handler prefixes |
| `GLYFI_CONFIG`           | (empty)                  | the persisted `UserConfig` JSON path             |
| `GLYFI_TITLE`            | `glyfi`                  | the title-bar text                               |
| `GLYFI_THEME`            | (empty)                  | the theme name (see [theme-a11y.md](theme-a11y.md)) |

```python
from glyfi.config import load_config
cfg = load_config()        # Config(base_url, modes, session_seq_start, plugins_dir,
                           #        plugin_allow, config_path, title, theme)
```

Resolution order: process env wins; otherwise the NAMED default. A `.env` file (if any) is
injected by the host, not read here (12-factor).

**Fail-loud examples:**

```bash
GLYFI_SESSION_SEQ_START=oops glyfi --base-url http://127.0.0.1:8800
# ConfigError: config GLYFI_SESSION_SEQ_START='oops' is not an integer

GLYFI_MODES=" , ," glyfi --base-url http://127.0.0.1:8800
# ConfigError: config GLYFI_MODES=' , ,' resolved to no labels
```

### Modes

`GLYFI_MODES` is a CSV of plain labels the operator cycles with `m` (or `/mode`). The core
never interprets them; they are sent on the wire as the turn `mode`. Example:

```bash
export GLYFI_MODES=chat,review,plan
glyfi --base-url http://127.0.0.1:8800     # 'm' cycles chat → review → plan → chat
```

---

## The persisted `UserConfig` JSON

Module: `glyfi/ui/config_store.py`. This holds per-user UI preferences and is loaded on
startup (`config_store.load()`), carried on the `AppModel`.

```python
def default_config_path() -> str           # $GLYFI_CONFIG, else ~/.config/glyfi/config.json
def load(path: str = '') -> UserConfig      # missing → defaults; malformed JSON → fail loud
def save(cfg: UserConfig, path: str = '') -> str
```

A **missing** file yields defaults (first run). A **malformed** file FAILS LOUD — it is
NOT silently reset, so a corrupt config is surfaced.

### JSON shape

```json
{
  "slots": {
    "state":         ["session", "seq", "mode", "subject", "turns"],
    "details_left":  ["cwd"],
    "details_right": ["localtime"]
  },
  "visible": {
    "state":   true,
    "details": true
  },
  "theme": "maroon-select",
  "status_ttl_seconds": 4.0,
  "scroll_delta": 1,
  "page_overlap": 3,
  "content_collapsed_default": false
}
```

| key                          | default        | meaning                                              |
| ---------------------------- | -------------- | ---------------------------------------------------- |
| `slots`                      | (see below)    | per-group ordered lists of field aliases             |
| `visible`                    | all true       | which hideable regions show (`state`, `details`)     |
| `theme`                      | `maroon-select`| the theme name                                       |
| `status_ttl_seconds`         | `4.0`          | how long a pushed status stays on the ticker         |
| `scroll_delta`               | `1`            | rows the content moves per line-scroll               |
| `page_overlap`               | `3`            | rows kept in view across a `PgUp`/`PgDn`             |
| `content_collapsed_default`  | `false`        | whether content entries start collapsed              |

The three **slot groups** are `state`, `details_left`, `details_right` (`SLOT_GROUPS`). The
**hideable regions** are `state` and `details` (`HIDEABLE_REGIONS`).

---

## The slot / field alias registry

Module: `glyfi/ui/fields.py`. A *slot* shows a *field*, named by an **alias**. The
registry resolves an alias against the live ViewModel:

| alias        | constant            | shows                                |
| ------------ | ------------------- | ------------------------------------ |
| `cwd`        | `ALIAS_CWD`         | the current working directory (`~`-abbreviated) |
| `localtime`  | `ALIAS_LOCALTIME`   | the local time (`%H:%M:%S`)          |
| `session`    | `ALIAS_SESSION`     | the session id                       |
| `seq`        | `ALIAS_SEQ`         | the current sequence number          |
| `mode`       | `ALIAS_MODE_FIELD`  | the current mode label               |
| `subject`    | `ALIAS_SUBJECT`     | the last resolved subject (or `-`)   |
| `turns`      | `ALIAS_TURNS`       | the transcript turn count            |
| `url`        | `ALIAS_URL`         | the server base URL                  |
| `title`      | `ALIAS_TITLE`       | the app title                        |
| `blank`      | `ALIAS_BLANK`       | an empty spacer                      |

```python
from glyfi.ui.fields import known_aliases, field_label, register_field

known_aliases()                  # every alias, in registration order
field_label('subject')           # the human label for a slot

# register a custom field (fail loud on a duplicate alias):
register_field('host', 'host', lambda vm: vm.url.split('//')[-1])
```

The default slots:

```
state         → session, seq, mode, subject, turns
details_left  → cwd
details_right → localtime
```

---

## The config editor (in-app)

Module: `glyfi/ui/config_editor.py`. Open it with `/config` or by choosing `config` in the
palette (UI state `CONFIG`). It is a pure, traversable state machine.

Three levels:

1. **slots** — the combined top list: every slot position (across the groups) followed by
   the **input knobs** (`scroll_delta`, `page_overlap`, `status_ttl_seconds`).
2. **aliases** — descend from a slot position with `Enter` to rebind it to a different
   field alias.
3. **inputs** — on an input-knob row, adjust the value within its `floor`/`ceil` step.

Navigation: `↑`/`↓` move, `Enter` descends / chooses (a slot bind emits `SlotBound`), `Esc`
/ `←` / Backspace back out a level. Rebinding a slot updates the `UserConfig` slots; saving
persists it via `config_store.save`.

---

## Pluggable `AppSettings`

`GLYFI_TITLE` seeds the title, but the entire fenced layout and key map are pluggable:
construct a custom `AppSettings` (`glyfi/ui/settings.py`) with different `regions` or `keys`
and pass it to `build_viewmodel`. See [architecture.md](architecture.md#the-layout-solver-glyfiuilayoutpy).
