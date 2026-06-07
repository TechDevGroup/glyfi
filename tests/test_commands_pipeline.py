"""Tests for the args->handler command PIPELINE: tokenizer, schema, dispatch, applier, pipeline."""
import pytest

from glyfi.plugins.commands import (
    ArgSchema, ArgSpec, ArgTokenizer, CommandContext, CommandDispatcher, CommandError,
    CommandInvocation, CommandPipeline, CommandResult, CommandSpec, ResultApplier,
)


# ===== the ARG TOKENIZER ===================================================================================

def test_tokenizer_splits_bare_words():
    assert ArgTokenizer().tokenize('add one two') == ['add', 'one', 'two']


def test_tokenizer_preserves_quoted_runs():
    assert ArgTokenizer().tokenize('add "buy milk" --all') == ['add', 'buy milk', '--all']
    assert ArgTokenizer().tokenize("note 'hello world'") == ['note', 'hello world']


def test_tokenizer_supports_escapes_inside_quotes():
    assert ArgTokenizer().tokenize(r'say "a \"quote\" in"') == ['say', 'a "quote" in']


def test_tokenizer_fails_loud_on_unterminated_quote():
    with pytest.raises(CommandError) as exc:
        ArgTokenizer().tokenize('add "unterminated')
    assert exc.value.where == '<tokenize>'


def test_tokenizer_empty_is_empty_list():
    assert ArgTokenizer().tokenize('') == []
    assert ArgTokenizer().tokenize('   ') == []


# ===== the SCHEMA ==========================================================================================

def test_arg_schema_rejects_non_last_rest():
    with pytest.raises(ValueError):
        ArgSchema(positionals=(ArgSpec('a', rest=True), ArgSpec('b')))


def test_arg_schema_rejects_required_after_optional():
    with pytest.raises(ValueError):
        ArgSchema(positionals=(ArgSpec('a', required=False), ArgSpec('b', required=True)))


def test_arg_schema_min_positionals_and_has_rest():
    schema = ArgSchema(positionals=(ArgSpec('a'), ArgSpec('b', required=False), ArgSpec('c', required=False, rest=True)))
    assert schema.min_positionals == 1
    assert schema.has_rest is True


# ===== the PIPELINE (parse -> dispatch -> apply) ===========================================================

def _spec(name='notes', schema=None, handler=None):
    return CommandSpec(name=name, description='d',
                       handler=handler or (lambda inv, ctx: CommandResult.of_status('ok')),
                       arg_schema=schema or ArgSchema())


def _stub_ctx():
    rec = {'lines': [], 'status': [], 'widget': [], 'events': []}
    ctx = CommandContext(
        push_lines=lambda ls: rec['lines'].extend(ls),
        push_status=lambda s: rec['status'].append(s),
        open_widget=lambda n: rec['widget'].append(n),
        emit=lambda e: rec['events'].append(e),
    )
    return ctx, rec


def test_pipeline_parses_name_and_structured_args():
    schema = ArgSchema(positionals=(ArgSpec('verb'), ArgSpec('text', rest=True)))
    captured = {}

    def handler(inv: CommandInvocation, ctx):
        captured['inv'] = inv
        return CommandResult.of_status('done')

    spec = _spec(schema=schema, handler=handler)
    pipe = CommandPipeline(resolve=lambda n: spec if n == 'notes' else None)
    ctx, rec = _stub_ctx()
    pipe.run('/notes add "buy milk"', ctx)
    inv = captured['inv']
    assert inv.name == 'notes'
    assert inv.arg('verb') == 'add'
    assert inv.arg('text') == 'buy milk'
    assert rec['status'] == ['done']


def test_pipeline_applies_result_lines_and_status():
    spec = _spec(handler=lambda inv, ctx: CommandResult.of_lines(['hello'], status='said'))
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, rec = _stub_ctx()
    pipe.run('/notes', ctx)
    assert rec['lines'] == ['hello']
    assert rec['status'] == ['said']


def test_pipeline_arg_less_command_still_works():
    spec = _spec(name='clear', schema=ArgSchema(), handler=lambda inv, ctx: CommandResult.of_status('cleared'))
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, rec = _stub_ctx()
    pipe.run('/clear', ctx)
    assert rec['status'] == ['cleared']


def test_pipeline_unknown_command_is_located():
    pipe = CommandPipeline(resolve=lambda n: None)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError) as exc:
        pipe.run('/nope', ctx)
    assert exc.value.where == 'nope'


def test_pipeline_missing_required_arg_is_located():
    schema = ArgSchema(positionals=(ArgSpec('verb'),))
    spec = _spec(schema=schema)
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError) as exc:
        pipe.run('/notes', ctx)
    assert exc.value.where == 'notes' and 'missing required' in exc.value.detail


def test_pipeline_too_many_args_is_located():
    schema = ArgSchema(positionals=(ArgSpec('verb'),))
    spec = _spec(schema=schema)
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError) as exc:
        pipe.run('/notes a b c', ctx)
    assert 'too many args' in exc.value.detail


def test_pipeline_unknown_flag_is_located():
    schema = ArgSchema(positionals=(ArgSpec('verb'),), flags=('all',))
    spec = _spec(schema=schema)
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError) as exc:
        pipe.run('/notes add --bogus', ctx)
    assert 'unknown flag' in exc.value.detail


def test_pipeline_flag_value_binding():
    schema = ArgSchema(positionals=(ArgSpec('verb'),), flags=('limit', 'all'))
    captured = {}
    spec = _spec(schema=schema, handler=lambda inv, ctx: captured.update(inv=inv) or CommandResult())
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    pipe.run('/notes add --all --limit=10', ctx)
    inv = captured['inv']
    assert inv.flag('all') is True
    assert inv.flag('limit') == '10'


def test_pipeline_handler_fault_is_located_loud():
    def boom(inv, ctx):
        raise RuntimeError('kaboom')

    spec = _spec(handler=boom)
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError) as exc:
        pipe.run('/notes', ctx)
    assert exc.value.where == 'notes' and 'kaboom' in exc.value.detail


def test_dispatcher_rejects_non_result_return():
    spec = _spec(handler=lambda inv, ctx: 'not a result')
    pipe = CommandPipeline(resolve=lambda n: spec)
    ctx, _ = _stub_ctx()
    with pytest.raises(CommandError):
        pipe.run('/notes', ctx)


def test_split_name_no_command_name_is_located():
    pipe = CommandPipeline(resolve=lambda n: None)
    with pytest.raises(CommandError) as exc:
        pipe.split_name('/   ')
    assert exc.value.where == '<parse>'


# ===== the RESULT APPLIER order ============================================================================

def test_result_applier_order_events_lines_widget_status():
    order = []
    ctx = CommandContext(
        push_lines=lambda ls: order.append('lines'),
        push_status=lambda s: order.append('status'),
        open_widget=lambda n: order.append('widget'),
        emit=lambda e: order.append('event'),
    )
    result = CommandResult(lines=('x',), status='s', open_widget='w', events=(object(),))
    ResultApplier().apply(result, ctx)
    assert order == ['event', 'lines', 'widget', 'status']


def test_empty_result_applies_nothing():
    ctx, rec = _stub_ctx()
    ResultApplier().apply(CommandResult(), ctx)
    assert rec == {'lines': [], 'status': [], 'widget': [], 'events': []}


def test_dispatcher_binds_without_calling():
    schema = ArgSchema(positionals=(ArgSpec('verb'),))
    spec = _spec(schema=schema)
    inv = CommandDispatcher().bind(spec, ['go'])
    assert inv.name == 'notes' and inv.arg('verb') == 'go' and inv.raw_tokens == ('go',)
