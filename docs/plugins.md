# Plugins

glyfi has a small, safe-by-default plugin framework. A plugin contributes **commands**
(slash-commands with structured args) and/or **widgets** (content-region overlays — see
[widgets.md](widgets.md)). You can add a plugin three ways, and the simplest is a **file
drop**: a manifest in the plugins directory + a handler module on an allowlisted import
prefix. **No core file is edited to register a plugin.**

This doc walks a complete, copy-paste example, then covers the args → handler pipeline,
the manifest schema, sources, the import allowlist, and the conflict policy.

---

## The three plugin sources

Module: `glyfi/plugins/sources.py`. Each is a `PluginSource` whose `load()` yields a
`Registration` (commands + widgets) that the loader registers:

| source                     | how it contributes                                                  |
| -------------------------- | ------------------------------------------------------------------- |
| `InCodeSource`             | explicit in-code `CommandSpec`s + widget factories                  |
| `FilesystemManifestSource` | one manifest file per plugin in a `plugins.d`-style directory        |
| `SystemApiSource`          | GETs a JSON manifest from a configured URL (a `fetch` seam, injectable) |

Precedence (highest first): in-code → builtin manifests → user dir manifests (see
`glyfi/app.py::load_plugins`).

The user manifest directory is `GLYFI_PLUGINS`, defaulting to `~/.config/glyfi/plugins/`. A
missing directory is a no-op (first run is not an error). A present-but-malformed manifest
FAILS LOUD (located).

---

## Worked example: a copy-paste filesystem plugin

We'll register a `/greet <name>` command that pushes a line into the content view.

### Step 1 — write the handler module

A handler is **pure / return-only**: it receives the resolved `CommandInvocation` + a
scoped `CommandContext` and RETURNS a `CommandResult`. It does NOT touch the ViewModel.

The handler's module must be importable **on an allowlisted prefix**. The default allowlist
is `glyfi.plugins`, `glyfi.widgets`, `glyfi.contrib`. To use your own package, opt it in via
`GLYFI_PLUGIN_ALLOW` (below). For this example, place the module under `glyfi.plugins`:

```python
# glyfi/plugins/greetplugin.py
from glyfi.plugins.commands import CommandContext, CommandInvocation, CommandResult

ARG_NAME = 'name'
GREET_PREFIX = 'hello, '
GREET_STATUS = 'greeted'


def greet_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    """/greet <name> — push 'hello, <name>' into the content view."""
    name = invocation.arg(ARG_NAME, 'world')
    return CommandResult.of_lines([f'{GREET_PREFIX}{name}'], status=GREET_STATUS)
```

### Step 2 — write the manifest (JSON)

Drop this file into `~/.config/glyfi/plugins/greet.json`:

```json
{
  "plugin": "greet-example",
  "commands": [
    {
      "name": "greet",
      "description": "greet someone by name",
      "handler": "glyfi.plugins.greetplugin:greet_handler",
      "args": {
        "positionals": [
          {"name": "name", "required": false, "rest": true}
        ]
      }
    }
  ]
}
```

The `handler` is a dotted `module:callable` reference resolved at load time (import +
`getattr` + callable check), guarded by the allowlist.

### Step 3 — run it

```bash
glyfi --base-url http://127.0.0.1:8800
# in the app: press '/', then type:  greet Ada
# the content view shows:  hello, Ada
```

That's the whole loop: a file drop + a handler on an allowlisted prefix, zero core edits.

### YAML variant

The same manifest in the supported safe-YAML subset (`greet.yaml`):

```yaml
plugin: greet-example
commands:
  - name: greet
    description: greet someone by name
    handler: "glyfi.plugins.greetplugin:greet_handler"
    args:
      positionals:
        - {name: name, required: false, rest: true}
```

The YAML reader is a self-contained subset (no PyYAML). Supported: block/flow maps + seqs,
bare/quoted scalars, `true`/`false`/`null`, ints/floats, `#` comments. Explicitly
unsupported (fail loud): anchors/aliases, tags, multi-document `---`, block scalars
(`|`/`>`), merge keys, and tabs for indentation.

---

## The args → handler pipeline

Module: `glyfi/plugins/commands.py`. The most reuse-sensitive module — a single raw string
becomes a structured invocation a handler reads.

```
 raw "/greet Ada"  ──split_name──▶  ("greet", "Ada")
                   ──tokenize────▶  ["Ada"]            (quoted runs + escapes)
                   ──bind────────▶  CommandInvocation(positionals, flags, raw_tokens)
                   ──dispatch────▶  CommandResult       (handler runs; faults locate)
                   ──apply───────▶  events → lines → open_widget → status
```

### Arg schema

```python
@dataclass(frozen=True)
class ArgSpec:
    name: str
    required: bool = True
    rest: bool = False          # '*' — soaks up all remaining positionals (must be last)

@dataclass(frozen=True)
class ArgSchema:
    positionals: Tuple[ArgSpec, ...] = ()
    flags: Tuple[str, ...] = ()
```

A `rest` positional must be last, and a required positional may not follow an optional one
(enforced fail-loud in `__post_init__`).

### Reading args in a handler

```python
def my_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    text = invocation.arg('text', default='')     # a positional
    verbose = invocation.flag('verbose', default=False)
    ...
```

Flags are `--key=value` (NAMED `FLAG_PREFIX='--'`, `FLAG_KV_SEP='='`). The tokenizer
handles quoted runs (`"…"` / `'…'`) and `\`-escapes, failing loud on an unterminated quote.

### What a handler returns

```python
@dataclass(frozen=True)
class CommandResult:
    lines: Tuple[str, ...] = ()
    status: Optional[str] = None
    open_widget: Optional[str] = None
    events: Tuple[object, ...] = ()

CommandResult.of_status("done")
CommandResult.of_lines(["a", "b"], status="ok")
```

The `ResultApplier` applies a result through the injected caps in order: **events → lines →
open_widget → status**. (`open_widget` is the command → widget bridge — see how `/ask`
uses it in [openai-pane.md](openai-pane.md).)

### The `CommandContext` capabilities

A handler that needs to act beyond a declarative result calls scoped caps:

```python
@dataclass(frozen=True)
class CommandContext:
    push_lines: Callable[[List[str]], None]
    push_status: Callable[[str], None]
    open_widget: Callable[[str], None]
    emit: Callable[[object], None]
    scroll_to: Callable[[int], None]
    current_offset: Callable[[], int]
```

Prefer returning a `CommandResult`; the caps are for advanced cases.

---

## The manifest schema (reference)

Top-level keys: `plugin` (optional name), `commands`, `widgets`.

A **command** entry:

| key           | required | meaning                                          |
| ------------- | -------- | ------------------------------------------------ |
| `name`        | yes      | the command name (no leading `/`)                |
| `description` | yes      | the palette description                          |
| `handler`     | yes      | a dotted `module:callable` handler reference     |
| `args`        | no       | `{positionals: [...], flags: [...]}`             |

A positional: `{name, required (default true), rest (default false)}`.

A **widget** entry: `{name, factory}` where `factory` is a dotted `module:callable`
returning a fresh `Widget` (see [widgets.md](widgets.md)).

`validate_manifest(data, source=…)` turns a parsed dict into typed records, failing loud
and **located** on any bad field.

---

## The import allowlist

Module: `glyfi/plugins/handlers.py`. A manifest's handler/factory string is resolved by
import, GUARDED by a NAMED allowlist so a manifest cannot pull arbitrary system modules.

- Default allowed prefixes: `glyfi.plugins`, `glyfi.widgets`, `glyfi.contrib`.
- Widen it with `GLYFI_PLUGIN_ALLOW` (an `os.pathsep`-separated list of additional module
  prefixes the operator opts in):

```bash
export GLYFI_PLUGIN_ALLOW="mycompany.glyfi_plugins"
# now a manifest may reference  mycompany.glyfi_plugins.foo:handler
```

Resolution fails loud (located) at each step: a malformed ref, a forbidden prefix, an
unimportable module, a missing attribute, or a non-callable target.

---

## The conflict policy

Module: `glyfi/plugins/loader.py`. The loader runs sources in precedence order and
registers each `Registration`. On a cross-source **name collision**:

| policy        | constant     | behavior                                                |
| ------------- | ------------ | ------------------------------------------------------- |
| fail loud     | `FAIL_LOUD`  | raise `PluginConflictError` (default — no silent clobber) |
| skip later    | `SKIP_LATER` | the earlier precedence wins; the later registration is skipped and reported |

```python
from glyfi.plugins.loader import build_default_loader, SKIP_LATER
loader = build_default_loader(on_conflict=SKIP_LATER)
report = loader.load_all(sources)     # LoadReport(commands, widgets, skipped)
print(report.describe())
```

---

## The shipped reference

The clean reference plugin is `glyfi/plugins/refplugin.py` + the manifest
`glyfi/plugins/builtin/echo.json`:

- `echo_handler` — `/echo <text>` pushes `echo: <text>` into the content view (proves the
  args path).
- `ping_handler` — `/ping` pushes a `pong` status (an arg-less command).

The richer reference is the OpenAI context pane (a command + a widget) —
[openai-pane.md](openai-pane.md).
