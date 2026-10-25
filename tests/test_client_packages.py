import importlib.util
import json
from pathlib import Path
import sys
import zipfile
import pytest
from test_starter_bundle import inputs, build, load_source, DISTRIBUTION
sys.path.insert(0,str(DISTRIBUTION))
try:
    client_builder=load_source('client_builder',DISTRIBUTION/'build_clients.py')
finally:sys.path.pop(0)

@pytest.mark.parametrize('client',list(client_builder.CLIENTS))
@pytest.mark.parametrize('platform',['unix','windows'])
def test_client_package_contains_shared_installer_and_native_files(inputs,client,platform):
    starter=build(inputs)
    output=client_builder.build(starter,inputs['tmp']/(client+'-'+platform+'.zip'),client,platform)
    with zipfile.ZipFile(output) as z:
        names=z.namelist()
        assert 'contextopus/install.py' in names
        assert 'contextopus/LICENSE' in names
        assert 'contextopus/NOTICE' in names
        assert 'contextopus/runtime/bundle.json' in names
        profile=json.loads(z.read('contextopus/client.json'))
        assert profile['client']==client
        if client in ('opencode','crush'):
            assert profile['delivery']=='files'
            assert not any('/skills/' in name for name in names)
        else:
            assert 'contextopus/skills/setup/SKILL.md' in names
            expected={'claude-code':'.claude-plugin/plugin.json','cursor':'.cursor-plugin/plugin.json'}.get(client,'plugin.json')
            plugin=json.loads(z.read('contextopus/'+expected))
            assert plugin['name']=='contextopus'
            if client in ('codex','hermes'):
                assert plugin['$schema']=='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
            mcp=json.loads(z.read('contextopus/'+('.mcp.json' if client in ('claude-code','cursor') else 'mcp.json')))
            assert mcp['mcpServers']['contextopus']['url']=='http://127.0.0.1:8765/mcp'
            if client in ('codex','hermes'):
                assert mcp['$schema']=='https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'
    assert Path(str(output)+'.sha256').is_file()


def test_client_package_rejects_escaping_zip(tmp_path):
    source=tmp_path/'evil.zip'
    with zipfile.ZipFile(source,'w') as z:z.writestr('../escape','bad')
    with pytest.raises(ValueError):client_builder.build(source,tmp_path/'output.zip','codex')
    assert not (tmp_path/'output.zip').exists()
