"""Build client-specific installers from reviewed Core/module artifacts."""
from pathlib import Path
import argparse
import hashlib
import subprocess
import sys
import tomllib

ROOT=Path(__file__).resolve().parents[1]
VERSION=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
CLIENTS=('codex','claude-code','cursor','hermes','opencode','crush')


def build_core_installer(destination,wheel,modules=()):
    command=[sys.executable,str(ROOT/'distribution/build.py'),'--core-wheel',str(wheel),
        '--bundle-version',VERSION,'--output',str(destination/f'contextopus-core-{VERSION}.zip')]
    for module in modules:command+=['--module',str(module)]
    subprocess.run(command,check=True)


def build_client_installer(starter,output,client,platform):
    subprocess.run([sys.executable,str(ROOT/'distribution/build_clients.py'),str(starter),str(output),
        '--client',client,'--platform',platform],check=True)


def main(destination=None,modules=()):
    destination=Path(destination or ROOT/'dist');destination.mkdir(parents=True,exist_ok=True)
    assets=[destination/f'contextopus_core-{VERSION}-py3-none-any.whl',destination/f'contextopus_core-{VERSION}.tar.gz']
    if not all(p.is_file() for p in assets):raise ValueError('Build the exact wheel and source archive first')
    build_core_installer(destination,assets[0],modules)
    starter=destination/f'contextopus-core-{VERSION}.zip';assets.append(starter)
    for client in CLIENTS:
        for platform in ('unix','windows'):
            output=destination/f'contextopus-{client}-{platform}-{VERSION}.zip'
            build_client_installer(starter,output,client,platform);assets.append(output)
    (destination/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(assets)),encoding='utf-8')
    print('\n'.join(p.name for p in assets))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path)
    parser.add_argument('--module',action='append',type=Path,default=[])
    args=parser.parse_args();main(args.output_directory,args.module)
