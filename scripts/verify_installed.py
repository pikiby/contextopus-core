"""Verify an already installed candidate using temporary data, without model calls.

Run with the clean environment's interpreter. This script does not install,
start an OS service, modify native-client configuration or access a user context.
"""
import argparse
import atexit
import asyncio
from importlib import metadata
from importlib.util import find_spec
from importlib.resources import files
import inspect
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

def planned_skills(root):
    """Inspect a native integration preview without writing client configuration."""
    from contextopus.integrations import plan
    preview = plan('codex', root / 'client-preview', root=root)
    return {Path(item['path']).parent.name for item in preview['writes']
            if Path(item['path']).name == 'SKILL.md'}


def module_smoke(root, example):
    """Use installed MCP dispatch and child helpers with a real, closeable owner."""
    from contextopus.interfaces.mcp import server
    from unittest.mock import patch
    import venv

    destination = root / 'modules/catalog-demo'
    shutil.copytree(example, destination)
    venv.EnvBuilder(with_pip=False).create(destination / '.venv')
    interpreter = destination / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(interpreter), '-I', '-c',
        'import importlib.util; assert importlib.util.find_spec("contextopus") is None'], check=True)

    def decode(result):
        if isinstance(result, tuple):
            return result[1]
        if isinstance(result, dict):
            return result
        return json.loads(''.join(item.text for item in result if hasattr(item, 'text')))

    def use_owner(actions):
        owner = server.ServerOwner(root)
        try:
            # The real owner/application/resources remain in use. Capture only
            # construction so the verifier can close everything before cleanup.
            with patch.object(server, 'ServerOwner', return_value=owner):
                mcp = server.create_server(root)
            def call(tool, operation, arguments=None):
                return decode(asyncio.run(mcp.call_tool(tool, {'operation': operation,
                    'arguments': arguments or {}, 'work_root': str(root)})))
            return actions(call)
        finally:
            atexit.unregister(owner.close)
            owner.close()

    def populate(call):
        if call('read', 'core.modules')[0]['state'] != 'storage_pending':
            raise ValueError('Installed discovery did not expose pending schema')
        installed = call('write', 'core.module_install', {'module': 'catalog-demo'})
        if installed['state'] != 'enabled' or installed['storage']['current_version'] != 1:
            raise ValueError('Installed module schema/activation did not complete')
        call('write', 'catalog-demo.session_put', {'id': 's1', 'title': 'Installed wheel session'})
        call('write', 'catalog-demo.message_put', {'id': 'm1', 'session_id': 's1', 'body': 'Linked message'})
        if call('read', 'catalog-demo.sessions')['rows'] != [
                {'id': 's1', 'title': 'Installed wheel session', 'message_count': 1}]:
            raise ValueError('Installed child/storage roundtrip differs')
        return installed['storage']['current_version']

    schema = use_owner(populate)
    rows = use_owner(lambda call: call('read', 'catalog-demo.messages', {'session_id': 's1'})['rows'])
    if rows != [{'id': 'm1', 'session_id': 's1', 'title': 'Installed wheel session', 'body': 'Linked message'}]:
        raise ValueError('Installed module data did not survive owner restart')
    return {'module': 'catalog-demo', 'schema_version': schema, 'installed_via': 'MCP write',
            'saved_and_read_via': 'MCP/packaged child bridge', 'restart_preserved_linked_records': True,
            'module_venv_has_core': False}


def verify(expected_version, prefix=None, module_example=None):
    from contextopus.startup import Application
    from contextopus.interfaces.mcp.server import create_server
    from contextopus.core.filtering import AlgorithmRegistry

    installed = metadata.version('contextopus-core')
    if installed != expected_version:
        raise ValueError(f'Expected {expected_version}, installed {installed}')
    source = Path(inspect.getfile(Application)).resolve()
    executable = Path(sys.executable).parent / ('contextopus.exe' if os.name == 'nt' else 'contextopus')
    if prefix is not None and (not source.is_relative_to(Path(prefix).resolve())
                               or not executable.resolve().is_relative_to(Path(prefix).resolve())):
        raise ValueError('The installed check resolved outside the clean installation prefix')
    cli = subprocess.run([str(executable), '--version'], text=True, capture_output=True, check=True).stdout.strip()
    if cli != 'Contextopus ' + expected_version:
        raise ValueError('CLI version differs from installed package')
    subprocess.run([str(executable), '--help'], check=True, stdout=subprocess.DEVNULL)
    resources = files('contextopus').joinpath('resources')
    skills = sorted(path.name for path in resources.joinpath('skills').iterdir() if path.is_dir())
    if skills != ['modules']:
        raise ValueError('Core-only wheel must supply only the module-management skill')
    try:
        workspace_in_core = find_spec('contextopus.modules.workspace') is not None
    except ModuleNotFoundError:
        workspace_in_core = False
    if workspace_in_core or resources.joinpath('base_context').is_dir():
        raise ValueError('Core-only wheel contains optional Workspace code or documentation')
    algorithms = AlgorithmRegistry().catalog()
    if len(algorithms) != 5 or any(row['version'] != '2.0.0' for row in algorithms):
        raise ValueError('Installed search algorithm inventory is stale')
    with tempfile.TemporaryDirectory(prefix='contextopus-installed-check-') as temporary:
        temporary = Path(temporary)
        root = temporary / 'core-only'
        with Application(root, discover=False) as app:
            if app.query('procedure', {'name': 'default'})['name'] != 'modules':
                raise ValueError('Bare Core requires a module-independent default procedure')
            if 'workspace' in app.registry.modules or any(name.startswith('workspace.') for name in app.registry._operations):
                raise ValueError('Bare Core automatically registered Workspace')
            if app.query('describe', {'operation': 'core.module_install'})['kind'] != 'execute':
                raise ValueError('Installed module operation registry is stale')
            if app.query('core.modules') != [] or app.module_storage.path.exists():
                raise ValueError('Discovery unexpectedly created module storage')
            if planned_skills(root) != {'contextopus-modules'}:
                raise ValueError('Bare Core integration preview contains module-owned skills')
            if app.resources.providers._entries:
                raise ValueError('Resource inspection unexpectedly loaded an embedding model')
        example = module_example or Path(__file__).resolve().parents[1] / 'examples/modules/catalog-demo'
        smoke = module_smoke(temporary / 'catalog-installed', example)
        from contextopus.interfaces.mcp import server
        from unittest.mock import patch
        owner = server.ServerOwner(root)
        try:
            with patch.object(server, 'ServerOwner', return_value=owner):
                mcp = create_server(root)
            tools = sorted(tool.name for tool in asyncio.run(mcp.list_tools()))
            if tools != ['finish', 'guide', 'read', 'write']:
                raise ValueError('Installed default MCP surface is not guide/read/write/finish')
        finally:
            atexit.unregister(owner.close)
            owner.close()
    return {'version': installed, 'source': str(source), 'cli': cli, 'tools': tools,
            'core_skills': skills, 'core_only_verified': True, 'algorithms': len(algorithms),
            'module_smoke': smoke, 'model_loaded': False,
            'scope': 'temporary_data_only', 'model_behavior_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--module-example', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.expected_version, arguments.prefix, arguments.module_example), indent=2))
