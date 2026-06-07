"""plugins -- the PLUGGABLE slash-command + widget REGISTRATION framework.

The extension seam a widget/command plugin ships AGAINST -- with ZERO edits to any core file. Five NAMED pieces:

  * ``commands``  -- the COMMAND model + the args->handler PIPELINE. ``CommandSpec{name, description, arg_schema,
                     handler}``; the operator's raw input is TOKENIZED into structured args and piped
                     ``parse -> dispatch -> apply`` to the handler (which returns a declarative ``CommandResult``).
  * ``manifest``  -- the ``ManifestFormat`` PORT (``JsonFormat`` + a self-contained safe-YAML-SUBSET ``YamlFormat``,
                     stdlib-only) + the manifest SCHEMA + its validator (fail loud, located).
  * ``handlers``  -- resolve a dotted ``module:callable`` handler/factory REFERENCE to a real callable (guarded by
                     a NAMED import allowlist; fail loud).
  * ``sources``   -- the registration SOURCE ports + adapters: ``InCodeSource`` / ``FilesystemManifestSource``
                     (NAMED ``GLYFI_PLUGINS`` plugins.d dir, one file per plugin) / ``SystemApiSource``.
  * ``loader``    -- the ``PluginLoader`` that runs enabled sources in NAMED precedence + registers them.

THE PLUGIN-AUTHOR RECIPE (what a plugin drops in -- no core edit):
  1. write a handler module (a ``CommandHandler`` callable and/or a ``Widget`` factory) on an allowed import
     prefix (the plugins/widgets/contrib tree, or widen via the ``GLYFI_PLUGIN_ALLOW`` env);
  2. drop a manifest file (``<plugin>.json`` or ``<plugin>.yaml``) into the ``GLYFI_PLUGINS`` dir naming the
     command (name/description/args/handler-ref) and/or widget (name/factory-ref);
  3. the ``PluginLoader`` at bootstrap discovers + validates + resolves + registers it. Done.

Self-contained: this package + stdlib only. NO third-party deps.
"""
from glyfi.plugins.commands import (
    ArgSchema, ArgSpec, ArgTokenizer, CommandContext, CommandDispatcher, CommandError, CommandHandler,
    CommandInvocation, CommandPipeline, CommandResult, CommandSpec, ResultApplier,
)
from glyfi.plugins.manifest import (
    JsonFormat, Manifest, ManifestArg, ManifestCommand, ManifestError, ManifestFormat, ManifestWidget,
    YamlFormat, format_for, register_format, validate_manifest,
)
from glyfi.plugins.handlers import (
    ENV_PLUGIN_ALLOW, HandlerResolveError, allowed_prefixes, resolve_callable,
)
from glyfi.plugins.sources import (
    ENV_PLUGINS, FilesystemManifestSource, InCodeSource, PluginSource, Registration, SystemApiSource,
    build_command_spec, default_plugins_dir, load_manifest_file,
)
from glyfi.plugins.loader import (
    FAIL_LOUD, LoadReport, PluginConflictError, PluginLoader, SKIP_LATER, build_default_loader,
)

__all__ = [
    "ArgSchema", "ArgSpec", "ArgTokenizer", "CommandContext", "CommandDispatcher", "CommandError",
    "CommandHandler", "CommandInvocation", "CommandPipeline", "CommandResult", "CommandSpec", "ResultApplier",
    "JsonFormat", "Manifest", "ManifestArg", "ManifestCommand", "ManifestError", "ManifestFormat",
    "ManifestWidget", "YamlFormat", "format_for", "register_format", "validate_manifest",
    "ENV_PLUGIN_ALLOW", "HandlerResolveError", "allowed_prefixes", "resolve_callable",
    "ENV_PLUGINS", "FilesystemManifestSource", "InCodeSource", "PluginSource", "Registration",
    "SystemApiSource", "build_command_spec", "default_plugins_dir", "load_manifest_file",
    "FAIL_LOUD", "LoadReport", "PluginConflictError", "PluginLoader", "SKIP_LATER", "build_default_loader",
]
