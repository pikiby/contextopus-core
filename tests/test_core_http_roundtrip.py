"""Generic MCP HTTP result shapes, independent of optional modules."""
import asyncio
import json
import pytest
from contextopus.integrations.remote import RemoteApplication

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
                        assert {tool.name for tool in tools} == {'guide','read','write','finish'}
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
