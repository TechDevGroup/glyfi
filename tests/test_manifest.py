"""Tests for the manifest FORMATS (JSON + safe-YAML-subset) and the manifest SCHEMA validator."""
import pytest

from glyfi.plugins.manifest import (
    JsonFormat, ManifestError, YamlFormat, format_for, validate_manifest,
)


# ===== JSON ================================================================================================

def test_json_format_parses():
    data = JsonFormat().parse('{"commands": [{"name": "x", "handler": "m:f"}]}')
    assert data['commands'][0]['name'] == 'x'


def test_json_format_fails_loud_located():
    with pytest.raises(ManifestError) as exc:
        JsonFormat().parse('{bad json')
    assert ':1:' in exc.value.where


def test_json_top_level_must_be_mapping():
    with pytest.raises(ManifestError):
        JsonFormat().parse('[1, 2, 3]')


# ===== the safe-YAML SUBSET ================================================================================

def test_yaml_subset_block_mapping_and_sequence():
    text = (
        'plugin: ref\n'
        'commands:\n'
        '  - name: echo\n'
        '    description: say it\n'
        '    handler: m:f\n'
        '    args:\n'
        '      positionals:\n'
        '        - name: text\n'
        '          required: true\n'
        '          rest: true\n'
    )
    data = YamlFormat().parse(text)
    assert data['plugin'] == 'ref'
    cmd = data['commands'][0]
    assert cmd['name'] == 'echo' and cmd['handler'] == 'm:f'
    assert cmd['args']['positionals'][0] == {'name': 'text', 'required': True, 'rest': True}


def test_yaml_subset_scalars_and_flow():
    data = YamlFormat().parse('a: 1\nb: true\nc: null\nd: [1, 2, 3]\ne: {x: 1, y: two}\nf: "quoted: colon"\n')
    assert data == {'a': 1, 'b': True, 'c': None, 'd': [1, 2, 3],
                    'e': {'x': 1, 'y': 'two'}, 'f': 'quoted: colon'}


def test_yaml_subset_comments_and_blanks_ignored():
    data = YamlFormat().parse('# a comment\n\nk: v\n')
    assert data['k'] == 'v'


def test_yaml_empty_is_empty_mapping():
    assert YamlFormat().parse('# only a comment\n') == {}


@pytest.mark.parametrize('bad,reason', [
    ('a: &anchor 1\n', 'anchor'),
    ('--- \nk: v\n', 'multi-document'),
    ('a: !tag x\n', 'anchors/aliases/tags'),
    ('a:\n\tb: 1\n', 'tab'),
    ('a: {x: {y: 1}}\n', 'nested flow'),
    ('a: [1\n', 'unterminated'),
    ('a: "open\n', 'unterminated'),
])
def test_yaml_subset_fails_loud_on_out_of_subset(bad, reason):
    with pytest.raises(ManifestError) as exc:
        YamlFormat().parse(bad)
    assert reason.split()[0] in str(exc.value).lower()


# ===== format_for ==========================================================================================

def test_format_for_by_extension():
    assert isinstance(format_for('x.json'), JsonFormat)
    assert isinstance(format_for('x.yaml'), YamlFormat)
    assert isinstance(format_for('x.yml'), YamlFormat)
    with pytest.raises(ManifestError):
        format_for('x.toml')


# ===== the SCHEMA validator ================================================================================

def test_validate_full_manifest():
    data = {
        'plugin': 'p',
        'commands': [{'name': 'echo', 'handler': 'm:f',
                      'args': {'positionals': [{'name': 'text', 'rest': True}]}}],
        'widgets': [{'name': 'w', 'factory': 'm:W'}],
    }
    man = validate_manifest(data, source='t')
    assert man.plugin == 'p'
    assert man.commands[0].name == 'echo' and man.commands[0].positionals[0].rest is True
    assert man.widgets[0].factory == 'm:W'


def test_schema_fails_loud_on_unknown_top_key():
    with pytest.raises(ManifestError) as exc:
        validate_manifest({'bogus': 1}, source='t')
    assert 'unknown top-level key' in str(exc.value)


def test_schema_fails_loud_on_unknown_command_key():
    with pytest.raises(ManifestError):
        validate_manifest({'commands': [{'name': 'x', 'handler': 'm:f', 'bogus': 1}]}, source='t')


def test_schema_fails_loud_on_missing_handler():
    with pytest.raises(ManifestError):
        validate_manifest({'commands': [{'name': 'x'}]}, source='t')


def test_schema_fails_loud_on_missing_widget_factory():
    with pytest.raises(ManifestError):
        validate_manifest({'widgets': [{'name': 'w'}]}, source='t')


def test_schema_fails_loud_on_empty_manifest():
    with pytest.raises(ManifestError):
        validate_manifest({}, source='t')


def test_json_and_yaml_round_trip_to_same_schema():
    json_data = JsonFormat().parse(
        '{"commands": [{"name": "echo", "handler": "m:f", "args": {"positionals": [{"name": "text", "rest": true}]}}]}'
    )
    yaml_data = YamlFormat().parse(
        'commands:\n  - name: echo\n    handler: m:f\n    args:\n      positionals:\n'
        '        - name: text\n          rest: true\n'
    )
    j = validate_manifest(json_data, source='j')
    y = validate_manifest(yaml_data, source='y')
    assert [c.name for c in j.commands] == [c.name for c in y.commands] == ['echo']
    assert j.commands[0].positionals[0].rest is y.commands[0].positionals[0].rest is True
