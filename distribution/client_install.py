"""One client package; reuse Core or run the shared fresh-install bootstrap."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def runtime():
    found=shutil.which('contextopus')
    if found:return found
    home=Path.home()
    candidate=home/'.local/bin'/('contextopus.exe' if os.name=='nt' else 'contextopus')
    return str(candidate) if candidate.is_file() else None


def bundled_modules(package, selected):
    # Validate the exact payload before running module code through Core.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(package / 'runtime'))
    from bundle import load_bundle
    manifest = load_bundle(package / 'runtime')
    modules = manifest['modules']
    if selected is not None:
        wanted = set(selected)
        if wanted == {'none'}:
            wanted = set()
        unknown = wanted - {m['id'] for m in modules}
        if unknown:
            raise ValueError('Unknown bundled modules: ' + ', '.join(sorted(unknown)))
        modules = [m for m in modules if m['id'] in wanted]
    return modules


def query(base, operation, arguments=None, *, mutate=False):
    command = base + ['execute' if mutate else 'query', operation]
    if arguments is not None:
        command += ['--arguments', json.dumps(arguments)]
    try:
        output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'{operation} failed: {exc.stderr or exc.stdout}') from exc
    result = json.loads(output)
    if isinstance(result, dict) and (result.get('error') or result.get('status') in ('error', 'not_found', 'failed')):
        raise RuntimeError(f'{operation} failed: {result}')
    return result


def ensure_modules(base, package, modules):
    inventory = query(base, 'core.modules')
    if not isinstance(inventory, list):
        raise RuntimeError('Invalid module inventory')
    installed = {m['id']: m for m in inventory}
    for module in modules:
        ident = module['id']
        current = installed.get(ident)
        if current is None:
            source = str(package / 'runtime' / module['path'])
            arguments = {'module': ident, 'source': source}
            preview = query(base, 'core.module_source_plan', arguments)
            print(json.dumps({'module_install_plan': preview}, indent=2))
            result = query(base, 'core.module_install',
                           dict(arguments, source_revision=preview['revision']), mutate=True)
            if result.get('state') != 'enabled':
                raise RuntimeError(f'Module {ident} was not enabled: {result}')
        elif current.get('state') != 'enabled':
            raise RuntimeError(f'Module {ident} is {current.get("state")}; explicit repair/enable required')
    installed = {m['id']: m for m in query(base, 'core.modules')}
    for module in modules:
        ident = module['id']
        current = installed.get(ident, {})
        if current.get('state') != 'enabled':
            raise RuntimeError(f'Module {ident} is not enabled after setup')
        source = package / 'runtime' / module['path']
        metadata = json.loads((source / 'module.json').read_text(encoding='utf-8'))
        missing = {op['name'] for op in metadata.get('operations', [])} - set(current.get('operations', []))
        if missing:
            raise RuntimeError(f'Installed module {ident} requires an update; missing operations: {sorted(missing)}')
        procedures = metadata.get('procedures')
        if procedures:
            for path in sorted((source / 'package' / procedures).rglob('*.md')):
                name = ident + '/' + path.relative_to(source / 'package' / procedures).with_suffix('').as_posix()
                response = query(base, 'procedure', {'name': name})
                if not response.get('content'):
                    raise RuntimeError(f'Procedure {name} returned no content')
    print(json.dumps({'modules_verified': [m['id'] for m in modules]}))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--yes',action='store_true')
    parser.add_argument('--plan',action='store_true')
    parser.add_argument('--skip-model',action='store_true')
    parser.add_argument('--module',action='append',dest='modules')
    args=parser.parse_args(argv)
    package=Path(__file__).resolve().parent
    profile=json.loads((package/'client.json').read_text(encoding='utf-8'))
    executable=runtime()
    if executable:
        modules = bundled_modules(package, args.modules)
        commands=[]
        base=[executable]+(['--root',str(args.root.expanduser().resolve())] if args.root else [])
        # Existing installations keep their modules, data and model selection.
        commands.append(base+['service','status'])
        if profile['delivery']=='files':
            commands.append(base+['integrate',profile['client'],'--user'])
            commands.append(base+['integrate',profile['client'],'--user','--apply'])
        print(json.dumps({'mode':'reuse','client':profile['client'],'commands':commands,
            'modules':[m['id'] for m in modules],
            'note':'Install missing selected modules through Core; preserve existing module data/model. Incompatible existing modules require an explicit update.'},indent=2))
        if args.skip_model:
            parser.error('--skip-model applies only to fresh installation; existing model is preserved')
        if args.plan:return 0
        if not args.yes and input('Connect this client to the existing Core? [y/N] ').lower() not in ('y','yes'):return 0
        status=subprocess.run(commands[0],check=True,capture_output=True,text=True)
        state=json.loads(status.stdout)
        if state.get('state')!='running':
            raise RuntimeError('Existing Core is not running; start/repair it explicitly before connecting')
        if args.root and Path(state.get('root','')).resolve()!=args.root.expanduser().resolve():
            raise RuntimeError('The running Core belongs to a different data root')
        ensure_modules(base, package, modules)
        for command in commands[1:]:subprocess.run(command,check=True)
        return 0
    command=([sys.executable,'-B',str(package/'runtime/install.py')])
    if args.root:command+=['--root',str(args.root)]
    command+=['--client',profile['client'] if profile['delivery']=='files' else 'none']
    for name in args.modules or []:command+=['--module',name]
    if args.yes:command+=['--yes']
    if args.skip_model:command+=['--skip-model']
    if args.plan:command+=['--plan']
    return subprocess.call(command)

if __name__=='__main__':raise SystemExit(main())
