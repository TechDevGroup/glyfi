"""plugins.sources -- the registration SOURCE ports + adapters (in-code / filesystem-manifest / system-API).

A SOURCE produces ``Registration``s (commands + widgets) the loader registers into the palette/widget registries.
The port is ``PluginSource.load() -> Registration`` -- open/closed: a new source adapter plugs in WITHOUT editing
the loader. The shipped adapters:
  * ``InCodeSource``      -- wraps an explicit list of in-code ``CommandSpec``s + widget factories (the existing
                            ``register_command``/``register_widget`` path, lifted behind the same port).
  * ``FilesystemManifestSource(dir)`` -- discovers manifest files in a NAMED ``plugins.d``-style directory (env
                            ``GLYFI_PLUGINS``, default ``~/.config/glyfi/plugins/``). EACH plugin is its OWN file
                            -> adding a plugin is a file drop, no shared-file edit. Parses by extension, validates
                            against the schema, resolves each handler/factory ref (fail loud, located).
  * ``SystemApiSource``   -- a PORT for registering from an EXTERNAL service. Ships a thin ``urllib`` reference
                            adapter that GETs a JSON manifest from a configured URL. A ``fetch`` seam is injectable
                            so a mock drives it in tests.

Each manifest entry's handler/factory STRING is resolved to a real callable via ``handlers.resolve_callable``
(guarded by the NAMED import allowlist). A manifest command becomes a ``CommandSpec``; a manifest widget becomes
a ``(name, factory)`` widget registration.

Self-contained: stdlib (``os`` / ``urllib``) + this package only.
"""
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple
from urllib.request import urlopen

from glyfi.plugins.commands import ArgSchema, ArgSpec, CommandSpec
from glyfi.plugins.handlers import resolve_callable
from glyfi.plugins.manifest import (
    EXT_JSON, EXT_YAML, EXT_YML, Manifest, ManifestCommand, format_for, validate_manifest,
)

# ---- NAMED env + default dir (no magic path) -- a ``plugins.d``-style dir: one file per plugin -------------
ENV_PLUGINS = 'GLYFI_PLUGINS'
DEFAULT_PLUGINS_REL = os.path.join('.config', 'glyfi', 'plugins')
# the manifest extensions the filesystem source discovers (the registered manifest formats).
MANIFEST_EXTENSIONS = (EXT_JSON, EXT_YAML, EXT_YML)

# ---- NAMED system-API fetch timeout (no unproven magic budget at the call site; the operator can override) --
ENV_SYSTEM_API_TIMEOUT = 'GLYFI_SYSTEM_API_TIMEOUT'
DEFAULT_SYSTEM_API_TIMEOUT = 10.0      # seconds; a NAMED default, overridable by the NAMED env


def default_plugins_dir() -> str:
    """The plugins dir -- ``$GLYFI_PLUGINS`` if set, else ``~/.config/glyfi/plugins/`` (NAMED)."""
    override = os.environ.get(ENV_PLUGINS)
    if override:
        return override
    return os.path.join(os.path.expanduser('~'), DEFAULT_PLUGINS_REL)


# ===== the registration bundle a source yields ============================================================

@dataclass(frozen=True)
class Registration:
    """What a source contributes -- resolved ``CommandSpec``s + ``(widget_name, factory)`` pairs, + a source label.

    The loader registers each into the palette/widget registries. ``source`` labels WHERE these came from (the
    adapter name / file) so a cross-source duplicate fails loud with both origins. Already RESOLVED: handler /
    factory refs are concrete callables by the time a Registration exists (the source did the fail-loud resolve).
    """
    source: str
    commands: Tuple[CommandSpec, ...] = field(default_factory=tuple)
    widgets: Tuple[Tuple[str, Callable], ...] = field(default_factory=tuple)


# ===== the SOURCE port ====================================================================================

class PluginSource:
    """The source PORT -- ``load() -> Registration`` + a ``name`` for diagnostics/precedence. Open/closed.

    A concrete source discovers/builds its registrations (resolving handler refs fail-loud). The loader runs each
    enabled source in PRECEDENCE order and registers the results. A source NEVER touches the registries itself --
    it only PRODUCES; the loader is the single registrar (SRP).
    """

    name: str = 'source'

    def load(self) -> Registration:
        raise NotImplementedError('PluginSource.load must produce a Registration')


# ===== adapter 1: in-code ================================================================================

class InCodeSource(PluginSource):
    """Wrap explicit in-code ``CommandSpec``s + widget factories behind the source port (the existing register path).

    The built-ins / first-party specs an app wires in code flow through the SAME loader as the manifest sources --
    so precedence + dedup are uniform. No import resolution needed (the callables are already concrete).
    """

    name = 'in-code'

    def __init__(self, commands: Optional[List[CommandSpec]] = None,
                 widgets: Optional[List[Tuple[str, Callable]]] = None):
        self._commands = tuple(commands or ())
        self._widgets = tuple(widgets or ())

    def load(self) -> Registration:
        return Registration(source=self.name, commands=self._commands, widgets=self._widgets)


# ===== adapter 2: filesystem manifest (plugins.d-style dir, one file per plugin) ==========================

class FilesystemManifestSource(PluginSource):
    """Discover + load manifest files from a NAMED ``plugins.d``-style directory (one file per plugin).

    ``directory`` defaults to the NAMED ``GLYFI_PLUGINS`` dir. A MISSING dir yields an empty registration
    (first run -- no plugins is not an error); a present-but-malformed manifest FAILS LOUD (located). Each file
    is parsed by its extension's registered format, validated against the schema, and its handler/factory refs
    resolved to callables (fail loud). Files are loaded in SORTED filename order (a stable, NAMED precedence).
    """

    name = 'filesystem'

    def __init__(self, directory: Optional[str] = None):
        self._dir = directory or default_plugins_dir()

    @property
    def directory(self) -> str:
        return self._dir

    def discover(self) -> List[str]:
        """The manifest file paths in the dir (sorted, by a registered extension). Empty if the dir is absent."""
        if not os.path.isdir(self._dir):
            return []
        paths = []
        for entry in sorted(os.listdir(self._dir)):
            full = os.path.join(self._dir, entry)
            if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in MANIFEST_EXTENSIONS:
                paths.append(full)
        return paths

    def load(self) -> Registration:
        commands: List[CommandSpec] = []
        widgets: List[Tuple[str, Callable]] = []
        for path in self.discover():
            manifest = load_manifest_file(path)
            for mc in manifest.commands:
                commands.append(build_command_spec(mc, source=path))
            for mw in manifest.widgets:
                widgets.append((mw.name, resolve_callable(mw.factory)))
        return Registration(source=self.name, commands=tuple(commands), widgets=tuple(widgets))


# ===== adapter 3: system-API (external service -> a JSON manifest) ========================================

# the fetch SEAM: a URL -> the manifest TEXT. The default is a stdlib urllib GET; a test injects a mock.
SystemApiFetch = Callable[[str], str]


def _urllib_fetch(url: str) -> str:
    """The default system-API fetch -- a stdlib ``urllib`` GET of the manifest text."""
    timeout = float(os.environ.get(ENV_SYSTEM_API_TIMEOUT, DEFAULT_SYSTEM_API_TIMEOUT))
    with urlopen(url, timeout=timeout) as resp:        # noqa: S310 -- a configured plugin manifest URL
        return resp.read().decode('utf-8')


class SystemApiSource(PluginSource):
    """Register from an EXTERNAL service -- fetch a JSON manifest from a configured URL, validate + resolve it.

    The fetch is an INJECTABLE seam (``fetch(url) -> text``); the default is a stdlib ``urllib`` GET, a test
    passes a mock returning canned manifest text -- so the port is real + testable without a live endpoint. The
    fetched text is parsed as JSON (the wire format), validated against the schema, and its refs resolved fail-loud.
    """

    name = 'system-api'

    def __init__(self, url: str, *, fetch: Optional[SystemApiFetch] = None):
        if not url:
            raise ValueError('SystemApiSource requires a manifest URL')
        self._url = url
        self._fetch = fetch or _urllib_fetch

    def load(self) -> Registration:
        text = self._fetch(self._url)
        data = format_for('manifest' + EXT_JSON).parse(text)   # the system-API wire format is JSON
        manifest = validate_manifest(data, source=f'system-api:{self._url}')
        commands = tuple(build_command_spec(mc, source=f'system-api:{self._url}') for mc in manifest.commands)
        widgets = tuple((mw.name, resolve_callable(mw.factory)) for mw in manifest.widgets)
        return Registration(source=self.name, commands=commands, widgets=widgets)


# ===== manifest -> CommandSpec (shared by the filesystem + system-API adapters) ===========================

def load_manifest_file(path: str) -> Manifest:
    """Read + parse + validate a manifest FILE -> a typed ``Manifest`` (fail loud, located, at every stage)."""
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    fmt = format_for(path)
    data = fmt.parse(text)
    return validate_manifest(data, source=os.path.basename(path))


def build_command_spec(mc: ManifestCommand, *, source: str) -> CommandSpec:
    """Turn a validated ``ManifestCommand`` into a ``CommandSpec`` -- resolving its handler ref to a callable.

    The manifest arg fields become an ``ArgSchema``; the handler STRING resolves (guarded, fail-loud) to the
    ``CommandHandler`` callable. The resulting spec is what the loader registers + the pipeline dispatches.
    """
    schema = ArgSchema(
        positionals=tuple(ArgSpec(name=a.name, required=a.required, rest=a.rest) for a in mc.positionals),
        flags=tuple(mc.flags),
    )
    handler = resolve_callable(mc.handler)
    return CommandSpec(name=mc.name, description=mc.description, handler=handler, arg_schema=schema)
