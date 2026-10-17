"""Three-tool transport and lossless presentation across the journal boundary."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from contextopus.interfaces.mcp.presentation import present
from contextopus.interfaces.mcp import server
from contextopus.integrations.reconnect import select_read_tool
from contextopus.integrations.remote import RemoteApplication


def material():
    return {'id': 'a', 'title': 'Useful material', 'path': 'knowledge/a.md', 'workspace': 'one',
            'description': 'Conditions for the requested action.', 'status': None,
            'content': 'Exact source body', 'links': ['b'],
            'link_targets': [{'id': 'b', 'title': 'Target', 'path': 'knowledge/b.md', 'workspace': 'two'}],
            'index_status': 'indexed', 'analytics': {'status': 'recorded', 'event_id': 'e'}}


def test_presentation_preserves_full_data_and_reviews_without_duplicate_links():
    source = {'materials': [material()], 'review_changes': [{'after': material()}],
              'settings': {'enabled': False, 'limit': 0, 'material_max_tokens': None},
              'warnings': [], 'history': {'status': 'pending', 'error': 'commit failure'}}
    original = copy.deepcopy(source)
    compact = present(source, operation='workspace.proposal_apply')
    assert source == original
    assert compact['materials'][0]['links'] == source['materials'][0]['link_targets']
    assert 'link_targets' not in compact['materials'][0]
    assert 'analytics' not in compact['materials'][0]
    assert 'index_status' not in compact['materials'][0]
    assert compact['materials'][0]['path'] == source['materials'][0]['path']
    assert compact['materials'][0]['workspace'] == 'one'
    assert compact['review_changes'] == original['review_changes']
    assert compact['settings'] == original['settings']
    assert compact['history'] == original['history']
    assert present(source, operation='workspace.proposal_apply', detail='full') is source


def test_compact_search_retains_fragment_text_when_explicit_and_all_faults():
    from contextopus.core.filtering import select
    row = {**material(), 'key': ['workspace', 'one', 'a'], 'distance': .1, 'excerpt': 'Matched part'}
    source = select([row], {'algorithm': 'nearest_n'})
    source.update(pending=['unindexed-id'], indexing={'status': 'failed', 'error': 'reason'})
    original = copy.deepcopy(source)
    compact = present(source, operation='workspace.search')
    assert 'excerpt' not in compact['results'][0]
    assert 'candidates' not in compact['diagnostics']
    assert compact['diagnostics']['counts']['selected_materials'] == 1
    assert compact['pending'] == ['unindexed-id']
    assert compact['indexing'] == source['indexing']
    explicit = present(source, operation='workspace.search', arguments={'output': 'fragments'})
    assert explicit['results'][0]['excerpt'] == 'Matched part'
    assert source == original
    compact['diagnostics']['counts']['selected_materials'] = 999
    assert source == original


def test_core_search_materials_retain_path_context_and_description():
    source = {'results': [{'key': ['workspace', 'one', 'a'], 'location': 'knowledge/a.md',
                           'metadata': {'description': 'Subject and conditions', 'custom': {'keep': None, 'enabled': False}}, 'distance': .1,
                           'excerpt': 'private fragment'}]}
    compact = present(source, operation='core.search')['results'][0]
    assert compact['path'] == 'knowledge/a.md'
    assert compact['workspace'] == 'one'
    assert compact['description'] == 'Subject and conditions'
    assert 'excerpt' not in compact
    assert compact['metadata'] == {'custom': {'keep': None, 'enabled': False}}
    assert 'location' not in compact


def fixture_server(monkeypatch, tmp_path, *, legacy_tools=False, app=None):
    app = app or SimpleNamespace(services=SimpleNamespace(runtime_mcp={}),
                          query=Mock(return_value={'ok': True}), execute=Mock(return_value={'ok': True}))
    owner = SimpleNamespace(application=Mock(return_value=app),
                            resources=SimpleNamespace(start_services=lambda: None),
                            current_root=lambda: str(tmp_path), close=lambda: None)
    monkeypatch.setattr(server, 'ServerOwner', lambda root: owner)
    return server.create_server(tmp_path, legacy_tools=legacy_tools), app


def value(result):
    if isinstance(result, tuple):
        return result[1]
    if isinstance(result, dict):
        return result
    return json.loads(''.join(item.text for item in result if hasattr(item, 'text')))


def test_default_tools_and_direct_guide_selectors(monkeypatch, tmp_path):
    mcp, app = fixture_server(monkeypatch, tmp_path)
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {'guide', 'read', 'write'}
    schemas = {t.name: t.inputSchema for t in tools}
    assert schemas['read']['properties']['detail']['enum'] == ['compact', 'full']
    asyncio.run(mcp.call_tool('guide', {}))
    app.query.assert_called_with('procedure', {'name': 'workspace'})
    asyncio.run(mcp.call_tool('guide', {'operation': 'search'}))
    app.query.assert_called_with('describe', {'operation': 'workspace.search'})
    asyncio.run(mcp.call_tool('guide', {'catalog': True}))
    app.query.assert_called_with('describe', {})
    before = app.query.call_count
    with pytest.raises(Exception, match='Choose procedure'):
        asyncio.run(mcp.call_tool('guide', {'procedure': 'workspace', 'catalog': True}))
    assert app.query.call_count == before


def test_legacy_aliases_are_explicit_full_responses(monkeypatch, tmp_path):
    mcp, app = fixture_server(monkeypatch, tmp_path, legacy_tools=True)
    assert {t.name for t in asyncio.run(mcp.list_tools())} == {
        'guide', 'read', 'write', 'contextopus_query', 'contextopus_execute', 'pcw_query', 'pcw_execute'}
    result = {'results': [dict(material(), excerpt='Retained body')]}
    app.query.return_value = result
    assert value(asyncio.run(mcp.call_tool('contextopus_query', {'operation': 'workspace.search'}))) == result


def test_transport_presents_only_after_operation_returns_and_retains_write_failures(monkeypatch, tmp_path):
    mcp, app = fixture_server(monkeypatch, tmp_path)
    result = {'results': [dict(material(), excerpt='Fragment')], 'search_event_id': 'e'}
    observed = []
    def query(operation, arguments):
        observed.append(copy.deepcopy(result))  # Stand-in for the completed journal.
        return result
    app.query.side_effect = query
    compact = value(asyncio.run(mcp.call_tool('read', {'operation': 'workspace.search'})))
    assert 'excerpt' not in compact['results'][0]
    assert observed[0]['results'][0]['excerpt'] == result['results'][0]['excerpt'] == 'Fragment'
    app.execute.side_effect = ValueError('Current confirmation is required')
    with pytest.raises(Exception, match='confirmation'):
        asyncio.run(mcp.call_tool('write', {'operation': 'workspace.proposal_apply'}))
    app.execute.assert_called_once()
    with pytest.raises(Exception):
        asyncio.run(mcp.call_tool('write', {'operation': 'workspace.proposal_apply', 'detail': 'invalid'}))
    app.execute.assert_called_once()


def test_coordinate_conflict_fails_before_dispatch(monkeypatch, tmp_path):
    mcp, app = fixture_server(monkeypatch, tmp_path)
    with pytest.raises(Exception, match='disagree'):
        asyncio.run(mcp.call_tool('read', {'operation': 'core.status', 'context': 'one', 'workspace': 'two'}))
    app.query.assert_not_called()


def test_native_tool_selection_and_remote_protocol_are_deliberate():
    assert select_read_tool(['guide', 'read', 'write']) == 'read'
    assert select_read_tool(['mcp__contextopus__read']) == 'mcp__contextopus__read'
    assert select_read_tool(['contextopus_query']) is None
    assert select_read_tool(['contextopus_query'], legacy_tools=True) == 'contextopus_query'
    for legacy, query, execute in [(False, 'read', 'write'), (True, 'contextopus_query', 'contextopus_execute')]:
        app = RemoteApplication('/tmp/fixture', legacy_tools=legacy)
        try:
            app._sync = Mock(return_value={})
            app.query('core.status')
            app._sync.assert_called_with(query, 'core.status', None)
            app.execute('core.init')
            app._sync.assert_called_with(execute, 'core.init', None)
        finally:
            app.close()


def test_unrelated_module_and_historical_payload_are_not_reinterpreted():
    payload = {'id': 'custom', 'path': 'own', 'status': None, 'links': ['raw'],
               'link_targets': [{'id': 'raw'}], 'pending': [], 'missing': False,
               'analytics': {'status': 'recorded'}}
    assert present(payload, operation='third.query') == payload
    assert present(payload, operation='workspace.analytics_read') == payload


def test_real_operation_journal_keeps_candidates_before_compact_transport(monkeypatch, tmp_path):
    from contextopus.startup import Application
    from contextopus.core.operations import OperationSpec
    from contextopus.core.filtering import select
    from contextopus.core.search_history import SearchHistory
    source = select([{'key': ['demo', 'one', str(i)], 'distance': i / 10,
                      'revision': 'r1', 'excerpt': 'Source fragment'} for i in range(2)],
                    {'algorithm': 'nearest_n'})
    with Application(tmp_path, discover=False) as app:
        app.registry._operations['core.search'] = OperationSpec(
            'core.search', 'query', {'type': 'object', 'properties': {'query': {'type': 'string'}},
                                     'required': ['query'], 'additionalProperties': False},
            lambda context, query: source)
        mcp, _ = fixture_server(monkeypatch, tmp_path, app=app)
        response = value(asyncio.run(mcp.call_tool('read', {
            'operation': 'core.search', 'arguments': {'query': 'Private query'}})))
        assert 'candidates' not in response['diagnostics']
        assert all('excerpt' not in item for item in response['results'])
        evidence = SearchHistory(app.journal).read(response['search_event_id'])
        assert len(evidence['diagnostics']['candidates']) == 2
        assert evidence['diagnostics']['counts'] == source['diagnostics']['counts']
        assert source['results'][0]['excerpt'] == 'Source fragment'
        assert 'candidates' in source['diagnostics']


def test_registered_lightweight_settings_schema_and_free_rule_template(tmp_path):
    from contextopus.startup import Application
    import yaml
    with Application(tmp_path, discover=False) as app:
        schema = app.query('describe', {'operation': 'core.settings'})['arguments_schema']['properties']
        assert {'fields', 'agent', 'agent_model'} <= schema.keys()
        assert app.query('describe', {'operation': 'workspace.settings_read'})['kind'] == 'query'
        assert app.query('describe', {'operation': 'workspace.settings_preview'})['kind'] == 'execute'
        assert app.query('describe', {'operation': 'workspace.settings_apply'})['kind'] == 'execute'
        defaults = app.query('procedure', {'name': 'default-instructions'})
        assert not defaults['content'].startswith('---')
        from contextopus.core.settings import WORKSPACE_CREATION_DEFAULTS
        assert defaults['creation_defaults'] == {**WORKSPACE_CREATION_DEFAULTS, 'reread_instructions': False}
        for name in ('w', 'w-search', 'w-settings', 'w-create', 'w-context', 'w-analyze', 'm'):
            from importlib.resources import files
            skill = files('contextopus').joinpath('resources', 'skills', name, 'SKILL.md').read_text()
            metadata = yaml.safe_load(skill.split('---', 2)[1])
            assert metadata['name'] == name and metadata['description']


def test_guide_exposes_runtime_proposal_change_contract(monkeypatch, tmp_path):
    from typing import get_type_hints
    from pydantic import ValidationError
    from contextopus.startup import Application
    from contextopus.modules.workspace.cycles import ProposalChange, PROPOSAL_CHANGE_FIELDS
    from contextopus.modules.workspace.operations import _ARGUMENT_MODELS

    with Application(tmp_path, discover=False) as app:
        mcp, _ = fixture_server(monkeypatch, tmp_path, app=app)
        result = value(asyncio.run(mcp.call_tool('guide', {
            'operation': 'workspace.proposal_prepare'})))
        schema = result['arguments_schema']
        ref = schema['properties']['changes']['items']['$ref'].rsplit('/', 1)[1]
        change_schema = schema['$defs'][ref]
        assert set(change_schema['properties']) == PROPOSAL_CHANGE_FIELDS == set(get_type_hints(ProposalChange))
        assert change_schema['additionalProperties'] is False
        assert 'title' not in change_schema['properties']
        assert 'heading' in change_schema['description']
        model = _ARGUMENT_MODELS['proposal_prepare']
        # Existing valid JSON inputs retain optional nulls, custom vocabulary,
        # empty lists and explicit false rather than being coerced or omitted.
        changes = [
            {'key': 'new', 'material_id': None, 'content': '# Heading',
             'description': 'Reviewed subject', 'type': 'custom-kind',
             'status': None, 'links': [], 'delete': False, 'path': 'custom.md'},
            {'material_id': 'existing', 'expected_revision': 'revision', 'status': None},
            {'material_id': 'existing', 'expected_revision': 'revision', 'delete': True},
        ]
        assert model.model_validate({'cycle_id': 'cycle', 'changes': changes}).changes == changes
        with pytest.raises(ValidationError, match='title'):
            model.model_validate({'cycle_id': 'cycle', 'changes': [
                {'key': 'new', 'content': '# Heading', 'title': 'Guessed field'}]})


@pytest.mark.parametrize('payload', [[], [{'id':'one'}], [{'id':'one'},{'id':'two'}], False, 0, None, 'ordinary text'])
def test_mcp_nonobject_json_results_keep_shape_in_one_content_block(monkeypatch, tmp_path, payload):
    mcp, app = fixture_server(monkeypatch, tmp_path)
    app.query.return_value = payload
    result = asyncio.run(mcp.call_tool('read', {'operation':'core.modules','detail':'full'}))
    assert len(result) == 1
    assert value(result) == payload


def test_remote_http_roundtrip_preserves_empty_single_many_and_scalars(tmp_path):
    """Exercise the real HTTP owner and RemoteApplication used by CLI/TUI."""
    import os
    from pathlib import Path
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    import urllib.request
    from test_module_install import release

    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    environment = dict(os.environ, CONTEXTOPUS_LEGACY_TOOLS='0')
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([sys.executable, '-c',
            'from contextopus.interfaces.mcp.server import run; import sys; run(sys.argv[1],port=int(sys.argv[2]))',
            str(tmp_path), str(port)], stdout=log, stderr=log, env=environment)
        remote = RemoteApplication(tmp_path, endpoint=f'http://127.0.0.1:{port}/mcp')
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.2):
                        break
                except Exception:
                    if process.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        pytest.fail('Isolated MCP did not start: ' + log.read().decode(errors='replace')[-2000:])
                    time.sleep(.05)
            assert remote.query('core.modules') == []
            path = tmp_path / 'modules/sample'
            manifest = release(path)
            with (path/'package/adapter.py').open('a') as handler:
                handler.write('\ndef scalar(args, core):\n    return args["value"]\n')
            manifest['operations'].append({'name':'sample.scalar','kind':'query',
                'handler':'adapter.py:scalar','protocol':'contextopus-core-v1'})
            (path/'module.json').write_text(json.dumps(manifest))
            assert len(remote.query('core.modules')) == 1
            second = tmp_path/'modules/second'
            other = release(second)
            other['id'] = 'second'
            for operation in other['operations']:
                operation['name'] = operation['name'].replace('sample.', 'second.')
            (second/'module.json').write_text(json.dumps(other))
            assert len(remote.query('core.modules')) == 2
            assert remote.execute('core.module_install', {'module':'sample'})['state'] == 'enabled'
            remote.execute('sample.save', {'id':'network','title':'Actual HTTP'})
            assert remote.query('sample.read')['rows'] == [{'id':'network','title':'Actual HTTP'}]
            for payload in (0, False, None, [], [1,2], {'unchanged':False}):
                assert remote.query('sample.scalar', {'value':payload}) == payload
            async def inspect_tools():
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client
                from jsonschema import Draft202012Validator
                async with streamable_http_client(remote.endpoint) as (read, write, _):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        assert {tool.name for tool in tools} == {'guide','read','write'}
                        for tool in tools:
                            Draft202012Validator.check_schema(tool.inputSchema)
                            if tool.outputSchema is not None:
                                Draft202012Validator.check_schema(tool.outputSchema)
            asyncio.run(inspect_tools())
        finally:
            remote.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
