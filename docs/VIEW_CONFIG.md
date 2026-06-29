# ViewConfig — Config-Object-Driven View Plumbing

> **Replaces scattered kwargs with a single config object.** The seven view-plumbing
> capabilities (C1–C7) merged in the generic plumbing PR are now configured by building ONE
> `ViewConfig` and placing it on `AppSettings.view` — no scattered kwarg overrides at the
> call site.

---

## The Conventional Pattern

```python
from glyfi.ui.settings import AppSettings, ViewConfig
from glyfi.ui.input_painter import make_multi_line_input_painter, make_pre_render_dynamic_height

from myapp.keymap_ext import preprocess_key    # C1 — consumer-owned
from myapp.row_color import row_role           # C2b — consumer-owned

settings = AppSettings(
    title='myapp',
    view=ViewConfig(
        key_preprocessor=preprocess_key,                   # C1
        row_classifier=row_role,                           # C2b
        pre_render=make_pre_render_dynamic_height(),       # C4
        post_paint=make_multi_line_input_painter(),        # C5
        bracketed_paste=True,                              # C6
        # scroll_palette defaults to None → file/default (True = windowing on)
    ),
)

vm = build_viewmodel(url, session_id, settings)
run(vm)   # app.py:run() reads settings.view and threads it to CursesView + RegionPainter
```

**Before (the old scattered-kwargs pattern — still works, backward compat):**

```python
# This still works — the PR-#1 kwargs are preserved on CursesView / RegionPainter.
painter = RegionPainter(post_paint=make_multi_line_input_painter())
CursesView(stdscr, painter, bracketed_paste=True, key_preprocessor=fn, ...).run(vm)
```

---

## ViewConfig Fields

Defined in `glyfi/ui/settings.py`.

### Callable hooks (code-level; not file-serializable)

| Field | Capability | Signature | Default |
|---|---|---|---|
| `key_preprocessor` | C1 key hook | `fn(vm, ch) -> bool` | `None` (off) |
| `row_classifier` | C2b per-row color | `fn(region, line) -> ROLE_*` | `None` (off) |
| `pre_render` | C4 dynamic height | `fn(vm) -> None` | `None` (off) |
| `post_paint` | C5 multi-line input | `fn(vm, layout, painting) -> Painting` | `None` (off) |

### Serializable flags (`Optional[bool]`)

| Field | Capability | UserConfig key | Default |
|---|---|---|---|
| `bracketed_paste` | C6 bracketed paste | `bracketed_paste` | `None` → `False` |
| `scroll_palette` | C3 palette windowing | `scroll_palette` | `None` → `True` |

`None` = defer to the `UserConfig` file value. `True`/`False` = code-level override (highest
priority).

---

## Precedence Rule

```
explicit ViewConfig flag (non-None)  >  UserConfig file value  >  default
```

- A code-level `ViewConfig(bracketed_paste=True)` always wins, even if the file says `false`.
- `ViewConfig(bracketed_paste=None)` (the default) defers to whatever the user's config file
  says; if the key is absent from the file, the hard default applies.
- This means a power user can enable `bracketed_paste: true` in their
  `~/.config/glyfi/config.json` without touching code, and a consumer who wants to enforce
  the flag can override from code.

---

## File-Loadable Flags

Add to `~/.config/glyfi/config.json` (or the path in `$GLYFI_CONFIG`):

```json
{
  "bracketed_paste": true,
  "scroll_palette": false
}
```

Both keys are forward-compatible: an old config file without them loads cleanly (defaults apply).

---

## app.py Threading

`glyfi/app.py:run()` is the single place that resolves and threads the config:

```
viewmodel.model.settings.view   (ViewConfig — code level)
       ↓ merge (code > file > default)
viewmodel.model.config          (UserConfig — file level)
       ↓
RegionPainter(post_paint=…, scroll_palette=…)
CursesView(stdscr, painter, key_preprocessor=…, row_classifier=…,
           pre_render=…, bracketed_paste=…)
```

The merge is performed by `_resolve_view_flags(viewmodel)` (in `app.py`).

---

## OCP Guarantee

`ViewConfig()` with all defaults produces **byte-identical behaviour** to the pre-config baseline:
- All hooks are `None` → the corresponding code paths are skipped exactly as before.
- `bracketed_paste=None` → resolves to `False` (the pre-plumbing default).
- `scroll_palette=None` → resolves to `True` (the current windowing-on default, identical to
  the PR-#1 `RegionPainter(scroll_palette=True)` default).

---

## Backward Compatibility

The individual kwargs on `CursesView` and `RegionPainter` introduced in PR #1 are **preserved
unchanged**. Consumers who construct those objects directly with kwargs (not routing through
`AppSettings.view`) continue to work without modification.
