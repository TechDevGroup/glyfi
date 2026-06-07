"""plugins.refplugin -- the reference plugin handlers that PROVE the manifest->loader->pipeline path end to end.

This is the minimal proof that a command can be REGISTERED FROM A MANIFEST (json or yaml), flow through the
args->handler PIPELINE with structured args, and produce an app effect -- with ZERO edits to any core file. The
fixture / builtin manifests name these handlers via a dotted ``module:callable`` ref:
  * ``echo_handler``  -- ``/echo <text>`` pushes ``echo: <text>`` into the content view (proves args + content);
  * ``ping_handler``  -- ``/ping`` pushes a status (proves an arg-less command + a status effect).

A handler is PURE/return-only: it receives the resolved ``CommandInvocation`` + the scoped ``CommandContext`` and
RETURNS a ``CommandResult`` (it does not touch the ViewModel). The applier applies the result through the caps.

Self-contained: this package's command types + stdlib only.
"""
from glyfi.plugins.commands import CommandContext, CommandInvocation, CommandResult

# ---- NAMED arg + status literals (no bare strings at a render site) ----------------------------------------
ARG_TEXT = 'text'                       # the ``/echo`` positional REST slot name (must match the manifest schema)
ECHO_PREFIX = 'echo: '                  # the content line the echo command emits
ECHO_STATUS = 'echoed to the content view'
PING_STATUS = 'pong'


def echo_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    """``/echo <text>`` -- push ``echo: <text>`` into the content view + a confirming status (proves args path)."""
    text = invocation.arg(ARG_TEXT, '')
    return CommandResult.of_lines([f'{ECHO_PREFIX}{text}'], status=ECHO_STATUS)


def ping_handler(invocation: CommandInvocation, ctx: CommandContext) -> CommandResult:
    """``/ping`` -- push a ``pong`` status (proves an arg-less command + a status-only effect through the pipeline)."""
    return CommandResult.of_status(PING_STATUS)
