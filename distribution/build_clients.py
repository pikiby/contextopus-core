"""Build per-client packages from one validated starter ZIP; no installation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from bundle import load_bundle, safe_path

CLIENTS={'codex':'portable','claude-code':'claude','cursor':'cursor','hermes':'portable','opencode':'files','crush':'files'}
HERE=Path(__file__).resolve().parent


def unpack(archive, destination):
    with zipfile.ZipFile(archive) as z:
        seen=set()
        for entry in z.infolist():
            name=entry.filename.rstrip('/')
            safe_path(name)
            if name.casefold() in seen:raise ValueError('Duplicate bundle member')
            seen.add(name.casefold())
            if entry.file_size>512*1024*1024:raise ValueError('Oversized bundle member')
            if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Bundle symlink')
        z.extractall(destination)
    root=destination/'contextopus'
    load_bundle(root)
    return root


def build(archive,output,client,platform='unix'):
    if client not in CLIENTS or platform not in ('unix','windows'):raise ValueError('Unknown client/platform')
    output=Path(output)
    if output.exists():raise ValueError('Output already exists')
    with tempfile.TemporaryDirectory(prefix='contextopus-client-') as temporary:
        stage=Path(temporary)
        runtime=unpack(archive,stage/'input')
        manifest=load_bundle(runtime)
        package=stage/'contextopus'
        package.mkdir()
        shutil.copytree(runtime,package/'runtime')
        for legal in ('LICENSE','NOTICE'):
            shutil.copy2(runtime/legal,package/legal)
        kind=CLIENTS[client]
        (package/'client.json').write_text(json.dumps({'client':client,'platform':platform,'delivery':'files' if kind=='files' else 'plugin'}),encoding='utf-8')
        shutil.copy2(HERE/'client_install.py',package/'install.py')
        # Shared OS bootstrap prepares Python/uv, then runs the client installer.
        for name in ('install.sh','install.ps1'):
            shutil.copy2(runtime/name,package/name)
        if kind!='files':
            skills=package/'skills';skills.mkdir()
            collected={}
            with zipfile.ZipFile(runtime/manifest['core']['path']) as wheel:
                prefix='contextopus/resources/skills/'
                for item in wheel.namelist():
                    if item.startswith(prefix) and not item.endswith('/'):
                        rel=item[len(prefix):];safe_path(rel)
                        target=skills/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(wheel.read(item))
                collected.update({p.name.casefold():p.name for p in skills.iterdir()})
            for module in manifest['modules']:
                folder=runtime/module['path'];meta=json.loads((folder/'module.json').read_text())
                if not meta.get('skills'):continue
                source=folder/'package'/safe_path(meta['skills'])
                for skill in sorted(source.iterdir()):
                    if not skill.is_dir():continue
                    if skill.name.casefold() in collected:raise ValueError('Duplicate packaged skill '+skill.name)
                    collected[skill.name.casefold()]=skill.name
                    shutil.copytree(skill,skills/skill.name)
            # Setup is available even when Core has not yet been installed.
            setup=skills/'setup';setup.mkdir()
            var={'claude':'${CLAUDE_PLUGIN_ROOT}','cursor':'${CURSOR_PLUGIN_ROOT}','portable':'${PLUGIN_ROOT}'}[kind]
            (setup/'SKILL.md').write_text('---\nname: setup\ndescription: Install or connect Contextopus for this client.\n---\n\nRun the packaged installer at '+var+'/install.sh (Unix) or install.ps1 (Windows). Show its --plan first. Ask the user for the data directory, modules and whether to configure the model before applying. Existing Core/data must be reused; do not reset them. Reload the client after setup and verify a real MCP read. Do not copy plugin skills into ordinary client directories.\n',encoding='utf-8')
            # HTTP transport shares Core directly, without per-client databases.
            server={'mcpServers':{'contextopus':{'type':'http' if kind=='claude' else 'streamable-http','url':'http://127.0.0.1:8765/mcp'}}}
            if kind=='cursor':server['mcpServers']['contextopus'].pop('type')
            if kind=='claude':
                manifest_path=package/'.claude-plugin/plugin.json';mcp_name='.mcp.json'
                plugin={'name':'contextopus','version':manifest['core']['version'],'description':'Reusable context across agents and tools','skills':'./skills/','mcpServers':'./.mcp.json'}
            elif kind=='cursor':
                manifest_path=package/'.cursor-plugin/plugin.json';mcp_name='.mcp.json'
                plugin={'name':'contextopus','version':manifest['core']['version'],'description':'Reusable context across agents and tools','skills':'./skills/','mcpServers':'./.mcp.json'}
            else:
                manifest_path=package/'plugin.json';mcp_name='mcp.json'
                plugin={'name':'contextopus','version':manifest['core']['version'],'description':'Reusable context across agents and tools'}
                if client=='codex':plugin['extensions']={'com.openai':{'skills':'./skills/','mcpServers':'./mcp.json'}}
            if kind=='portable':
                plugin['$schema']='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
                server['$schema']='https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'
            plugin['license']='Apache-2.0'
            plugin['author']={'name':'Contextopus contributors'}
            manifest_path.parent.mkdir(parents=True,exist_ok=True)
            manifest_path.write_text(json.dumps(plugin,indent=2)+'\n')
            (package/mcp_name).write_text(json.dumps(server,indent=2)+'\n')
            if client=='codex':
                native=package/'.codex-plugin/plugin.json';native.parent.mkdir()
                native.write_text(json.dumps({'name':'contextopus','version':manifest['core']['version'],
                    'description':plugin['description'],'skills':'./skills/','mcpServers':'./mcp.json'},indent=2)+'\n')
                marketplace=package/'.agents/plugins/marketplace.json';marketplace.parent.mkdir(parents=True)
                marketplace.write_text(json.dumps({'name':'contextopus','plugins':[{'name':'contextopus',
                    'source':{'source':'local','path':'./'},'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]},indent=2)+'\n')
            elif client=='claude-code':
                (package/'.claude-plugin/marketplace.json').write_text(json.dumps({'name':'contextopus',
                    'owner':{'name':'Contextopus contributors'},'plugins':[{'name':'contextopus','source':'./'}]},indent=2)+'\n')
        native_steps={
            'codex':'From the extracted folder: `codex plugin marketplace add .`, then `codex plugin add contextopus@contextopus`.',
            'claude-code':'From the extracted folder: `claude plugin install contextopus --marketplace .`.',
            'cursor':'For local development, put this plugin folder under `~/.cursor/plugins/local/` and reload Cursor. Public distribution requires marketplace review.',
            'hermes':'Put this plugin folder under your selected Hermes home `plugins/contextopus/`, then run `hermes plugins enable contextopus`. Do not replace an existing folder without reviewing changes.',
        }.get(client,'The installer applies native MCP and skill files; reload the client.')
        (package/'README.md').write_text(f'''# Contextopus for {client}

This package contains the shared Core installer and {'native plugin skills/MCP configuration' if kind!='files' else 'native MCP/skill integration'}.

1. Extract the package outside a temporary plugin cache for initial setup.
2. Run `sh install.sh --plan` on Linux/macOS or `powershell -File install.ps1 --plan` on Windows (preview requires Python 3.12+).
3. Run the same command without `--plan`. Choose a persistent data folder, modules and model setup. To defer model downloads pass `--skip-model`; semantic search then remains unavailable.
4. {'Install this folder through the client native plugin manager, then reload.' if kind!='files' else 'Reload the client after the installer applies its native configuration.'}
5. Verify a real Contextopus MCP read.

{native_steps}

An existing Core is reused without modifying its modules/model. A stopped or incompatible existing installation requires explicit repair/update. Data is never stored in this plugin folder; uninstalling the plugin does not delete Core data.

Full skill names are provided. Short aliases are opt-in. For file delivery use `contextopus integrate {client} --user --alias workspace=w` and review before `--apply`. Plugin aliases use the client's own mechanism when supported; do not edit the plugin cache.

Package generation is not proof of runtime compatibility. See the main repository's client verification matrix before release.
''',encoding='utf-8')
        output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
            for file in sorted(package.rglob('*')):
                if file.is_file():z.write(file,'contextopus/'+file.relative_to(package).as_posix())
    Path(str(output)+'.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--client',choices=CLIENTS,required=True);p.add_argument('--platform',choices=('unix','windows'),default='unix')
    a=p.parse_args();print(build(a.bundle,a.output,a.client,a.platform))
