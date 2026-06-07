# Theme & accessibility

glyfi ships a small **semantic** color palette aligned with Section 508 / WCAG. Every color
is named by its **meaning**, not its hue, and meaning is never encoded in color alone.

Module: `glyfi/ui/theme.py`.

---

## Roles, not hues

A render site asks for a semantic **role**, never a raw xterm index:

| role               | constant            | meaning                                            |
| ------------------ | ------------------- | -------------------------------------------------- |
| normal             | `ROLE_NORMAL`       | default foreground (live content)                  |
| dim                | `ROLE_DIM`          | faded/gray — placeholder + helper/hint text        |
| accent             | `ROLE_ACCENT`       | the active-menu accent trim (depth 0)              |
| accent-2           | `ROLE_ACCENT_2`     | nested-submenu accent trim (depth 1+, progressive) |
| select             | `ROLE_SELECT`       | the selection-highlight background (maroon)        |
| destructive        | `ROLE_DESTRUCTIVE`  | RED — destructive actions ONLY                     |

`ROLES` is the tuple of all roles. `ACCENT_RING = (ROLE_ACCENT, ROLE_ACCENT_2)` is the
progressive accent ring used for nested menu depth.

---

## The accessibility conventions (the laws)

1. **RED is for destructive actions only.** `ROLE_DESTRUCTIVE` is the single red role and
   nothing else may use it. In glyfi the only place it appears is the quit confirm.
2. **Focus / selection is never color-only.** The View ALWAYS prefixes the selected row
   with a printed marker (`FOCUS_MARKER` = `▸`) so the selection survives a no-color
   terminal. The maroon/reverse background is an *additional* cue, not the only one.
3. **Placeholder / helper text renders DIM** (`ROLE_DIM`) so live content stands out from
   hints.
4. **Active-menu accent is progressive.** An open menu/palette/widget shows an accent trim
   (`ACCENT_TRIM` = `┃`); nested depth advances through `ACCENT_RING` so menu depth is
   legible by color — but also by the breadcrumb path, which is not color-dependent.

---

## Named marker characters

These carry meaning independent of color (so they survive a mono terminal):

| marker                | constant             | use                                        |
| --------------------- | -------------------- | ------------------------------------------ |
| `▸`                   | `FOCUS_MARKER`       | prefixes the selected/focused row          |
| (space)               | `FOCUS_MARKER_BLANK` | the non-focused row's leading column       |
| ` › `                 | `BREADCRUMB_SEP`     | joins the progressive-menu breadcrumb path |
| `┃`                   | `ACCENT_TRIM`        | the active-menu accent left rail           |
| `█`                   | `SCROLLBAR_FULL`     | filled portion of the scroll-position bar  |
| `░`                   | `SCROLLBAR_EMPTY`    | empty portion of the scroll-position bar   |
| `▼`                   | `NEW_BELOW_MARKER`   | the "N new below" scrollback-lock indicator |

---

## The palette (color indexes + pairs)

Each role maps to a NAMED xterm-256 index and a NAMED curses color-pair id:

| role          | xterm index (`COLOR_*`)            | pair id (`PAIR_*`)   |
| ------------- | ---------------------------------- | -------------------- |
| select        | fg `231` / bg `131` (light maroon) | `PAIR_SELECT = 1`    |
| dim           | `244` (mid-gray)                   | `PAIR_DIM = 2`       |
| accent        | `39` (cyan-ish)                    | `PAIR_ACCENT = 3`    |
| accent-2      | `213` (magenta-ish)                | `PAIR_ACCENT_2 = 4`  |
| destructive   | `196` (bright red)                 | `PAIR_DESTRUCTIVE = 5` |
| default fg    | `-1` (`COLOR_DEFAULT_FG`)          | (the curses default) |

The theme key is `THEME_MAROON_SELECT = 'maroon-select'` (`DEFAULT_THEME`); `THEMES` is the
registry of known themes.

---

## Mono-terminal fallback

The module imports without a TTY (it imports `curses` lazily, inside the functions). On a
terminal with no color, `init_theme` wires nothing and returns `False`; `role_attr` then
falls back to curses attributes so the meaning still reads:

| role          | mono fallback                       |
| ------------- | ----------------------------------- |
| normal        | `A_NORMAL`                          |
| dim           | `A_DIM`                             |
| accent        | `A_BOLD`                            |
| accent-2      | `A_BOLD \| A_UNDERLINE`             |
| select        | `A_REVERSE`                         |
| destructive   | `A_BOLD \| A_REVERSE`               |

The printed markers (`FOCUS_MARKER`, `ACCENT_TRIM`, the breadcrumb) carry the meaning
regardless of color.

---

## The API

```python
def init_theme(theme: str = DEFAULT_THEME) -> bool   # call AFTER curses starts; True iff color wired
def role_attr(role: str) -> int                      # the curses attr for a role (pair or mono fallback)
def select_attr() -> int                             # the selection highlight attr
def accent_for_depth(depth: int) -> str              # the progressive accent ROLE for a nested depth
```

Fail-loud: `init_theme` raises on an **unknown theme name** (a config fault, never silently
defaulted); `role_attr` raises on an **unknown role**; `accent_for_depth` raises on a
negative depth. A mono terminal is a *capability* gap, not a config fault, so it falls back
rather than raising.

Selecting a theme at runtime is config-driven via `GLYFI_THEME` / the persisted
`UserConfig` (see [config.md](config.md)).
