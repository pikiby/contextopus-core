"""Procedure discovery must work for any enabled folder module."""
import json

import pytest

from contextopus.startup import Application


def install_fixture(app, root, module):
    folder = root / 'modules' / module
    package = folder / 'package'
    procedures = package / 'procedures'
    (procedures / 'reference').mkdir(parents=True)
    (procedures / 'edit.md').write_text('# Create or edit records\n\nFull editing rules.\n', encoding='utf-8')
    (procedures / 'reference' / 'hosts.md').write_text('# Native hosts\n\nHost rules.\n', encoding='utf-8')
    (package / 'entry.py').write_text(
        'def register(host):\n'
        '    host.procedure("' + module + '-special", lambda: {"content": "Provider rules"})\n', encoding='utf-8')
    (folder / 'module.json').write_text(json.dumps({
        'id': module, 'version': '1.0', 'procedures': 'procedures',
        'contribution': {'factory': 'entry.py:register'},
    }), encoding='utf-8')
    app.execute('core.module_install', {'module': module})


@pytest.mark.parametrize('module', ['agents', 'another_module'])
def test_namespace_and_unknown_procedure_offer_real_names(tmp_path, module):
    with Application(tmp_path, discover=False) as app:
        install_fixture(app, tmp_path, module)
        result = app.procedure(module)
        assert result['status'] == 'directory'
        entries = {row['name']: row['description'] for row in result['procedures']}
        assert entries[module + '/edit'] == 'Create or edit records'
        assert module + '/reference/hosts' in entries
        assert module + '-special' in entries
        assert 'content' not in result
        assert 'Do not proceed' in result['instruction']
        assert app.procedure(module + '/edit')['content'].endswith('Full editing rules.\n')
        assert app.procedure(module + '-special')['content'] == 'Provider rules'
        missing = app.procedure(module + '/typo')
        assert missing['status'] == 'not_found'
        assert missing['procedures'] == result['procedures']
        assert str(tmp_path) not in json.dumps(missing)
        global_missing = app.procedure('unknown-module')
        assert global_missing['status'] == 'not_found'
        assert module in global_missing['modules']
        assert 'modules' in [row['name'] for row in global_missing['procedures']]
        assert app.procedure('default')['name'] == 'modules'
        app.execute('core.module_disable', {'module': module})
        assert app.procedure(module)['status'] == 'not_found'
        assert module not in app.procedure(module)['modules']


@pytest.mark.parametrize('name', ['../secret', 'agents/../secret', '/absolute', 'agents\\edit', 'agents//edit'])
def test_invalid_procedure_paths_are_rejected(tmp_path, name):
    with Application(tmp_path, discover=False) as app:
        with pytest.raises(ValueError, match='Invalid procedure name'):
            app.procedure(name)
