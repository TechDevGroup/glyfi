"""plugins.manifest -- the MANIFEST FORMAT port (JSON + safe-YAML-subset) + the manifest SCHEMA.

A plugin describes its commands/widgets in a MANIFEST file. This module is two things:
  * the ``ManifestFormat`` PORT (``parse(text) -> dict``) + two stdlib-only adapters -- ``JsonFormat`` (stdlib
    ``json``) and ``YamlFormat`` (a SELF-CONTAINED safe-YAML-SUBSET reader; NO PyYAML). Format is chosen by file
    extension via a NAMED mapping. Each adapter FAILS LOUD (located line/col) on a construct outside its grammar.
  * the manifest SCHEMA -- the fields a command / widget entry must/may have -- + a validator that turns a parsed
    dict into typed ``ManifestCommand`` / ``ManifestWidget`` records (fail loud, located, on any bad field).

THE SUPPORTED YAML SUBSET (documented + enforced -- anything else FAILS LOUD, no silent partial parse):
  * block mappings ``key: value`` (nesting by INDENTATION -- 2 spaces conventional, any consistent indent);
  * block sequences ``- item`` (items are scalars or nested mappings);
  * flow mappings ``{a: 1, b: 2}`` and flow sequences ``[1, 2, 3]`` (one line, no nesting inside flow);
  * scalars: bare, single-quoted, double-quoted; the bare scalars ``true``/``false``/``null`` + ints/floats;
  * ``#`` line comments + blank lines.
  EXPLICITLY UNSUPPORTED (fail loud): anchors/aliases (``&``/``*``), tags (``!``), multi-document (``---``),
  block scalars (``|`` / ``>``), merge keys (``<<``), and tabs for indentation. The subset is exactly what a
  command/widget manifest needs -- a registration spec, not a general YAML document.

Self-contained: stdlib ``json`` only + this module's own YAML reader. NO third-party deps.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---- NAMED manifest top-level keys (no bare strings on disk) ----------------------------------------------
KEY_COMMANDS = 'commands'
KEY_WIDGETS = 'widgets'
KEY_PLUGIN = 'plugin'                 # optional human plugin name (for diagnostics/precedence reporting)

# ---- NAMED command-entry keys ----------------------------------------------------------------------------
KEY_NAME = 'name'
KEY_DESCRIPTION = 'description'
KEY_HANDLER = 'handler'               # a dotted ``module:callable`` handler reference (resolved by import)
KEY_ARGS = 'args'                     # the arg schema: {positionals: [...], flags: [...]}
KEY_POSITIONALS = 'positionals'
KEY_FLAGS = 'flags'
KEY_REQUIRED = 'required'
KEY_REST = 'rest'

# ---- NAMED widget-entry keys -----------------------------------------------------------------------------
KEY_FACTORY = 'factory'              # a dotted ``module:callable`` widget-factory reference

# ---- NAMED format-by-extension mapping (no magic extension strings at a dispatch site) --------------------
EXT_JSON = '.json'
EXT_YAML = '.yaml'
EXT_YML = '.yml'

# the YAML bare-scalar keywords (NAMED) the reader coerces.
YAML_TRUE = 'true'
YAML_FALSE = 'false'
YAML_NULL = 'null'


class ManifestError(Exception):
    """A fail-loud manifest fault -- a parse error (located line/col) or a schema-validation error (located field)."""

    def __init__(self, where: str, detail: str):
        super().__init__(f'[{where}] {detail}')
        self.where = where
        self.detail = detail


# ===== the FORMAT port + adapters =========================================================================

class ManifestFormat:
    """The format PORT -- ``parse(text) -> dict``. Concrete adapters (JSON / YAML-subset) implement the body.

    A format turns manifest TEXT into a plain dict; the SCHEMA validation (below) is format-agnostic. Open/closed:
    a new format adapter is added + registered by extension WITHOUT editing the loader or the schema.
    """

    def parse(self, text: str) -> dict:
        raise NotImplementedError('ManifestFormat.parse must turn manifest text into a dict')


class JsonFormat(ManifestFormat):
    """The JSON manifest format -- stdlib ``json``. Fail loud (located) on malformed JSON (never a partial parse)."""

    def parse(self, text: str) -> dict:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f'{EXT_JSON}:{exc.lineno}:{exc.colno}', f'malformed JSON: {exc.msg}') from exc
        if not isinstance(data, dict):
            raise ManifestError(EXT_JSON, f'top-level must be a mapping/object, got {type(data).__name__}')
        return data


class YamlFormat(ManifestFormat):
    """The safe-YAML-SUBSET manifest format -- a SELF-CONTAINED reader (NO PyYAML). See the module docstring.

    Parses the documented subset (block/flow mappings + sequences, scalars, ``#`` comments, indentation nesting)
    and FAILS LOUD (located line/col) on any construct outside it. The result is a plain dict the schema validates.
    """

    def parse(self, text: str) -> dict:
        data = _YamlReader(text).read()
        if not isinstance(data, dict):
            raise ManifestError(EXT_YAML, f'top-level must be a mapping, got {type(data).__name__}')
        return data


# the format-by-extension registry (NAMED mapping; open/closed via register_format).
_FORMATS: Dict[str, ManifestFormat] = {}


def register_format(ext: str, fmt: ManifestFormat) -> None:
    """Register a ``ManifestFormat`` for a file extension (NAMED). Fail loud on a duplicate extension."""
    if ext in _FORMATS:
        raise ValueError(f'manifest format for {ext!r} already registered')
    _FORMATS[ext] = fmt


def format_for(path: str) -> ManifestFormat:
    """The registered format for ``path``'s extension -- fail loud (located) on an unsupported extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _FORMATS:
        raise ManifestError(os.path.basename(path),
                            f'unsupported manifest extension {ext!r} (known: {sorted(_FORMATS)})')
    return _FORMATS[ext]


def _register_formats() -> None:
    register_format(EXT_JSON, JsonFormat())
    register_format(EXT_YAML, YamlFormat())
    register_format(EXT_YML, YamlFormat())


_register_formats()


# ===== the safe-YAML-SUBSET reader (self-contained, fail-loud, located) ===================================

class _YamlReader:
    """A small indentation-driven reader for the documented YAML SUBSET. Stateful over a list of (indent, body) lines.

    It strips ``#`` comments + blank lines, then recursively reads block mappings/sequences by indentation, with
    flow ``{...}`` / ``[...]`` and quoted/bare scalars at the leaves. Every out-of-subset construct FAILS LOUD
    with a LOCATED ``ManifestError`` (line number + the offending text). Tabs in indentation are rejected.
    """

    def __init__(self, text: str):
        self._lines = self._prepare(text)
        self._i = 0

    def read(self) -> object:
        if not self._lines:
            return {}
        value = self._read_block(self._lines[0][1])
        if self._i < len(self._lines):
            ln, _, raw = self._lines[self._i]
            raise ManifestError(f'{EXT_YAML}:{ln}', f'unexpected trailing content {raw!r}')
        return value

    # ---- line prep ----------------------------------------------------------------------------------------
    def _prepare(self, text: str) -> List[Tuple[int, int, str]]:
        """-> [(line_no, indent, body)] for non-blank, non-comment lines. Reject tabs + unsupported markers."""
        out: List[Tuple[int, int, str]] = []
        for n, raw in enumerate(text.splitlines(), start=1):
            if '\t' in raw[:len(raw) - len(raw.lstrip())]:
                raise ManifestError(f'{EXT_YAML}:{n}', 'tab in indentation is not in the subset (use spaces)')
            stripped = raw.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped == '---' or stripped == '...':
                raise ManifestError(f'{EXT_YAML}:{n}', 'multi-document markers (--- / ...) are not in the subset')
            if stripped[0] in ('&', '*', '!') or stripped.startswith('<<'):
                raise ManifestError(f'{EXT_YAML}:{n}',
                                    f'anchors/aliases/tags/merge-keys are not in the subset: {stripped!r}')
            indent = len(raw) - len(raw.lstrip(' '))
            out.append((n, indent, raw[indent:].rstrip()))
        return out

    # ---- block readers ------------------------------------------------------------------------------------
    def _read_block(self, indent: int) -> object:
        """Read a block (mapping or sequence) at exactly ``indent`` -- dispatch on whether the first line is ``- ``."""
        ln, line_indent, body = self._lines[self._i]
        if body.startswith('- ') or body == '-':
            return self._read_sequence(indent)
        return self._read_mapping(indent)

    def _read_mapping(self, indent: int) -> dict:
        result: Dict[str, object] = {}
        while self._i < len(self._lines):
            ln, line_indent, body = self._lines[self._i]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise ManifestError(f'{EXT_YAML}:{ln}', f'unexpected indent (over-nested mapping): {body!r}')
            if body.startswith('- '):
                raise ManifestError(f'{EXT_YAML}:{ln}', f'sequence item where a mapping key was expected: {body!r}')
            key, sep, rest = self._split_key(ln, body)
            self._i += 1
            rest = rest.strip()
            if rest:
                result[key] = self._scalar_or_flow(ln, rest)
            else:
                # the value is a nested block on the following more-indented lines (or empty -> null).
                if self._i < len(self._lines) and self._lines[self._i][1] > indent:
                    result[key] = self._read_block(self._lines[self._i][1])
                else:
                    result[key] = None
        return result

    def _read_sequence(self, indent: int) -> list:
        items: List[object] = []
        while self._i < len(self._lines):
            ln, line_indent, body = self._lines[self._i]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise ManifestError(f'{EXT_YAML}:{ln}', f'unexpected indent in a sequence: {body!r}')
            if not (body == '-' or body.startswith('- ')):
                break
            item_body = '' if body == '-' else body[2:].strip()
            self._i += 1
            if not item_body:
                # nested block item on the following more-indented lines.
                if self._i < len(self._lines) and self._lines[self._i][1] > indent:
                    items.append(self._read_block(self._lines[self._i][1]))
                else:
                    items.append(None)
            elif ':' in item_body and not _looks_scalar(item_body):
                # an inline ``- key: value`` starts a mapping whose remaining keys are more-indented.
                items.append(self._read_inline_map_item(ln, indent, item_body))
            else:
                items.append(self._scalar_or_flow(ln, item_body))
        return items

    def _read_inline_map_item(self, ln: int, seq_indent: int, first_body: str) -> dict:
        """A ``- key: value`` sequence item -- the first pair is inline; subsequent keys are deeper-indented."""
        result: Dict[str, object] = {}
        key, sep, rest = self._split_key(ln, first_body)
        rest = rest.strip()
        result[key] = self._scalar_or_flow(ln, rest) if rest else None
        # continuation keys for THIS item are indented past the dash (the ``- `` adds 2 cols).
        item_key_indent = seq_indent + 2
        while self._i < len(self._lines):
            cln, cindent, cbody = self._lines[self._i]
            if cindent < item_key_indent or cbody.startswith('- '):
                break
            if cindent > item_key_indent:
                raise ManifestError(f'{EXT_YAML}:{cln}', f'unexpected indent in a sequence item: {cbody!r}')
            ckey, csep, crest = self._split_key(cln, cbody)
            self._i += 1
            crest = crest.strip()
            if crest:
                result[ckey] = self._scalar_or_flow(cln, crest)
            elif self._i < len(self._lines) and self._lines[self._i][1] > item_key_indent:
                result[ckey] = self._read_block(self._lines[self._i][1])
            else:
                result[ckey] = None
        return result

    # ---- scalar / flow leaves -----------------------------------------------------------------------------
    def _split_key(self, ln: int, body: str) -> Tuple[str, str, str]:
        if body.startswith(('"', "'")):
            key, after = self._read_quoted_scalar(ln, body)
            after = after.lstrip()
            if not after.startswith(':'):
                raise ManifestError(f'{EXT_YAML}:{ln}', f'expected \":\" after key in {body!r}')
            return key, ':', after[1:]
        if ':' not in body:
            raise ManifestError(f'{EXT_YAML}:{ln}', f'expected a \"key: value\" mapping line, got {body!r}')
        key, sep, rest = body.partition(':')
        return key.strip(), sep, rest

    def _scalar_or_flow(self, ln: int, text: str) -> object:
        text = text.strip()
        if text.startswith('{'):
            return self._read_flow_mapping(ln, text)
        if text.startswith('['):
            return self._read_flow_sequence(ln, text)
        return self._coerce_scalar(ln, text)

    def _read_flow_mapping(self, ln: int, text: str) -> dict:
        if not text.endswith('}'):
            raise ManifestError(f'{EXT_YAML}:{ln}', f'unterminated flow mapping {text!r}')
        inner = text[1:-1].strip()
        result: Dict[str, object] = {}
        if not inner:
            return result
        for part in _split_flow(inner, ln):
            if ':' not in part:
                raise ManifestError(f'{EXT_YAML}:{ln}', f'flow mapping entry missing \":\": {part!r}')
            k, _, v = part.partition(':')
            result[self._coerce_scalar(ln, k.strip())] = self._coerce_scalar(ln, v.strip())
        return result

    def _read_flow_sequence(self, ln: int, text: str) -> list:
        if not text.endswith(']'):
            raise ManifestError(f'{EXT_YAML}:{ln}', f'unterminated flow sequence {text!r}')
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [self._coerce_scalar(ln, p.strip()) for p in _split_flow(inner, ln)]

    def _read_quoted_scalar(self, ln: int, text: str) -> Tuple[str, str]:
        quote = text[0]
        i = 1
        out: List[str] = []
        while i < len(text):
            ch = text[i]
            if ch == '\\' and quote == '"' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                return ''.join(out), text[i + 1:]
            out.append(ch)
            i += 1
        raise ManifestError(f'{EXT_YAML}:{ln}', f'unterminated {quote!r}-quoted scalar {text!r}')

    def _coerce_scalar(self, ln: int, text: str) -> object:
        if not text:
            return None
        if text[0] in ('&', '*', '!'):
            raise ManifestError(f'{EXT_YAML}:{ln}',
                                f'anchors/aliases/tags are not in the subset: {text!r}')
        if text[0] in ('"', "'"):
            value, after = self._read_quoted_scalar(ln, text)
            if after.strip():
                raise ManifestError(f'{EXT_YAML}:{ln}', f'trailing content after a quoted scalar: {after!r}')
            return value
        low = text.lower()
        if low == YAML_TRUE:
            return True
        if low == YAML_FALSE:
            return False
        if low == YAML_NULL:
            return None
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return text


def _looks_scalar(text: str) -> bool:
    """True if ``text`` is plainly a quoted/flow scalar (so a ``:`` inside it is NOT a mapping key separator)."""
    return text.startswith(('"', "'", '{', '['))


def _split_flow(inner: str, ln: int) -> List[str]:
    """Split a flow body on top-level commas, respecting quotes (no nested flow inside flow in the subset)."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    quote = ''
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ''
            continue
        if ch in ('"', "'"):
            quote = ch
            buf.append(ch)
            continue
        if ch in ('{', '['):
            raise ManifestError(f'{EXT_YAML}:{ln}', 'nested flow inside flow is not in the subset')
        if ch == ',' and depth == 0:
            parts.append(''.join(buf))
            buf = []
            continue
        buf.append(ch)
    if quote:
        raise ManifestError(f'{EXT_YAML}:{ln}', f'unterminated quote in flow {inner!r}')
    parts.append(''.join(buf))
    return [p for p in (p.strip() for p in parts) if p != '']


# ===== the manifest SCHEMA -- typed records + a validator =================================================

@dataclass(frozen=True)
class ManifestArg:
    """A positional arg slot in a manifest (-> ``commands.ArgSpec``)."""
    name: str
    required: bool = True
    rest: bool = False


@dataclass(frozen=True)
class ManifestCommand:
    """A validated command entry from a manifest -- name, description, handler ref, + the arg schema fields."""
    name: str
    description: str
    handler: str                          # a dotted ``module:callable`` reference (resolved at load)
    positionals: Tuple[ManifestArg, ...] = ()
    flags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ManifestWidget:
    """A validated widget entry from a manifest -- the registry name + a dotted ``module:callable`` factory ref."""
    name: str
    factory: str


@dataclass(frozen=True)
class Manifest:
    """A whole validated manifest -- the optional plugin name + its command + widget entries."""
    plugin: str = ''
    commands: Tuple[ManifestCommand, ...] = field(default_factory=tuple)
    widgets: Tuple[ManifestWidget, ...] = field(default_factory=tuple)


def validate_manifest(data: dict, *, source: str = '<manifest>') -> Manifest:
    """Validate a parsed manifest dict against the SCHEMA -> a typed ``Manifest``. Fail loud (located) on a bad field.

    Required per entry: a command needs ``name`` + ``handler`` (description optional); a widget needs ``name`` +
    ``factory``. Unknown top-level keys / entry keys FAIL LOUD (a typo in a manifest is a fault, not ignored).
    """
    _require_mapping(data, source)
    allowed_top = {KEY_COMMANDS, KEY_WIDGETS, KEY_PLUGIN}
    for key in data:
        if key not in allowed_top:
            raise ManifestError(source, f'unknown top-level key {key!r} (allowed: {sorted(allowed_top)})')
    commands = tuple(_command(entry, source) for entry in data.get(KEY_COMMANDS, []) or [])
    widgets = tuple(_widget(entry, source) for entry in data.get(KEY_WIDGETS, []) or [])
    if not commands and not widgets:
        raise ManifestError(source, 'manifest registers nothing (needs at least one command or widget)')
    return Manifest(plugin=str(data.get(KEY_PLUGIN, '')), commands=commands, widgets=widgets)


def _command(entry: object, source: str) -> ManifestCommand:
    if not isinstance(entry, dict):
        raise ManifestError(source, f'a command entry must be a mapping, got {type(entry).__name__}')
    allowed = {KEY_NAME, KEY_DESCRIPTION, KEY_HANDLER, KEY_ARGS}
    for key in entry:
        if key not in allowed:
            raise ManifestError(source, f'unknown command key {key!r} (allowed: {sorted(allowed)})')
    name = _require_str(entry, KEY_NAME, source)
    handler = _require_str(entry, KEY_HANDLER, f'{source}:command {name!r}')
    description = str(entry.get(KEY_DESCRIPTION, ''))
    positionals, flags = _args(entry.get(KEY_ARGS), f'{source}:command {name!r}')
    return ManifestCommand(name=name, description=description, handler=handler,
                           positionals=positionals, flags=flags)


def _args(args: object, source: str) -> Tuple[Tuple[ManifestArg, ...], Tuple[str, ...]]:
    if args is None:
        return (), ()
    if not isinstance(args, dict):
        raise ManifestError(source, f'{KEY_ARGS} must be a mapping, got {type(args).__name__}')
    allowed = {KEY_POSITIONALS, KEY_FLAGS}
    for key in args:
        if key not in allowed:
            raise ManifestError(source, f'unknown args key {key!r} (allowed: {sorted(allowed)})')
    positionals: List[ManifestArg] = []
    for slot in args.get(KEY_POSITIONALS, []) or []:
        if not isinstance(slot, dict):
            raise ManifestError(source, f'a positional must be a mapping, got {type(slot).__name__}')
        pname = _require_str(slot, KEY_NAME, source)
        positionals.append(ManifestArg(name=pname,
                                       required=bool(slot.get(KEY_REQUIRED, True)),
                                       rest=bool(slot.get(KEY_REST, False))))
    flags = tuple(str(f) for f in (args.get(KEY_FLAGS, []) or []))
    return tuple(positionals), flags


def _widget(entry: object, source: str) -> ManifestWidget:
    if not isinstance(entry, dict):
        raise ManifestError(source, f'a widget entry must be a mapping, got {type(entry).__name__}')
    allowed = {KEY_NAME, KEY_FACTORY}
    for key in entry:
        if key not in allowed:
            raise ManifestError(source, f'unknown widget key {key!r} (allowed: {sorted(allowed)})')
    name = _require_str(entry, KEY_NAME, source)
    factory = _require_str(entry, KEY_FACTORY, f'{source}:widget {name!r}')
    return ManifestWidget(name=name, factory=factory)


def _require_mapping(data: object, source: str) -> None:
    if not isinstance(data, dict):
        raise ManifestError(source, f'manifest must be a mapping, got {type(data).__name__}')


def _require_str(entry: dict, key: str, source: str) -> str:
    if key not in entry:
        raise ManifestError(source, f'missing required field {key!r}')
    value = entry[key]
    if not isinstance(value, str) or not value:
        raise ManifestError(source, f'field {key!r} must be a non-empty string, got {value!r}')
    return value
