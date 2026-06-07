"""Tests for the slash-command PALETTE: the registry + the pure filter/nav state machine."""
import pytest

from glyfi.plugins import palette as palette_mod
from glyfi.plugins.palette import (
    CMD_ABOUT, CMD_CLEAR, CMD_CONFIG, CMD_HELP, CMD_MODE, CMD_PROMPT, CMD_QUIT, Command,
    PALETTE_PREFIX, PaletteState, all_commands, command, command_spec, register_command,
    register_command_spec,
)
from glyfi.plugins.commands import ArgSchema, ArgSpec, CommandResult, CommandSpec
from glyfi.widgets.help_widget import WIDGET_HELP


# ===== built-ins ==========================================================================================

def test_builtins_registered():
    for name in (CMD_PROMPT, CMD_CLEAR, CMD_CONFIG, CMD_MODE, CMD_HELP, CMD_ABOUT, CMD_QUIT):
        assert command(name) is not None


def test_palette_prefix_is_slash():
    assert PALETTE_PREFIX == '/'


def test_about_opens_help_widget():
    calls = {}

    class VM:
        def open_widget(self, name):
            calls['widget'] = name

    command(CMD_ABOUT).action(VM())
    assert calls['widget'] == WIDGET_HELP


def test_builtin_actions_dispatch_to_vm():
    seen = []

    class VM:
        def request_prompt(self): seen.append('prompt')
        def clear_content(self): seen.append('clear')
        def open_config(self): seen.append('config')
        def cycle_mode(self): seen.append('mode')
        def push_help(self): seen.append('help')
        def request_quit(self): seen.append('quit')

    vm = VM()
    command(CMD_PROMPT).action(vm)
    command(CMD_CLEAR).action(vm)
    command(CMD_CONFIG).action(vm)
    command(CMD_MODE).action(vm)
    command(CMD_HELP).action(vm)
    command(CMD_QUIT).action(vm)
    assert seen == ['prompt', 'clear', 'config', 'mode', 'help', 'quit']


# ===== register_command / register_command_spec ===========================================================

def test_register_command_fails_loud_on_dup():
    with pytest.raises(ValueError):
        register_command(CMD_QUIT, 'dup', lambda vm: None)


def test_register_command_spec_lists_and_resolves():
    spec = CommandSpec(name='palette_test_cmd', description='a test command',
                       handler=lambda inv, ctx: CommandResult.of_status('ok'),
                       arg_schema=ArgSchema(positionals=(ArgSpec('text', rest=True),)))
    register_command_spec(spec)
    assert command_spec('palette_test_cmd') is spec
    assert command('palette_test_cmd') is not None     # also in the display registry


def test_register_command_spec_fails_loud_on_dup():
    spec = CommandSpec(name='palette_dup_cmd', description='d',
                       handler=lambda inv, ctx: CommandResult())
    register_command_spec(spec)
    with pytest.raises(ValueError):
        register_command_spec(spec)


def test_register_command_spec_collides_with_builtin():
    spec = CommandSpec(name=CMD_CLEAR, description='d', handler=lambda inv, ctx: CommandResult())
    with pytest.raises(ValueError):
        register_command_spec(spec)


# ===== PaletteState (pure) =================================================================================

def _cmds():
    return [
        Command('alpha', 'first', lambda vm: None),
        Command('beta', 'second', lambda vm: None),
        Command('alphabet', 'third', lambda vm: None),
    ]


def test_filter_term_strips_prefix():
    assert PaletteState(buffer='/al').filter_term == 'al'
    assert PaletteState(buffer='al').filter_term == 'al'


def test_filtered_substring_case_insensitive():
    st = PaletteState(buffer='/AL')
    names = [c.name for c in st.filtered(_cmds())]
    assert names == ['alpha', 'alphabet']


def test_filtered_empty_term_returns_all():
    st = PaletteState(buffer='/')
    assert len(st.filtered(_cmds())) == 3


def test_move_clamps_within_filtered():
    cmds = _cmds()
    st = PaletteState(buffer='/al')
    st.move_down(cmds)
    assert st.selected == 1
    st.move_down(cmds)            # only 2 filtered -> clamp at 1
    assert st.selected == 1
    st.move_up(cmds)
    assert st.selected == 0
    st.move_up(cmds)
    assert st.selected == 0


def test_select_exact_name_match_wins():
    cmds = _cmds()
    st = PaletteState(buffer='/beta', selected=0)
    assert st.select(cmds).name == 'beta'


def test_select_returns_selected_row_when_no_exact():
    cmds = _cmds()
    st = PaletteState(buffer='/al', selected=1)
    assert st.select(cmds).name == 'alphabet'


def test_select_none_when_empty():
    st = PaletteState(buffer='/zzz')
    assert st.select(_cmds()) is None


def test_all_commands_includes_builtins():
    names = [c.name for c in all_commands()]
    assert CMD_PROMPT in names and CMD_QUIT in names
