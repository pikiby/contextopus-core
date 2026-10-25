"""Verify release asset identity, contents and checksums without installing anything."""

from pathlib import Path, PurePosixPath
import argparse
import hashlib
from email.parser import BytesParser
import json
import stat
import sys
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ("codex", "claude-code", "cursor", "opencode", "crush", "hermes")


def verify(destination=None):
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = metadata["version"]
    distribution = metadata["name"].replace("-", "_")
    destination = Path(destination) if destination is not None else ROOT / 'dist'
    wheel = destination / f"{distribution}-{version}-py3-none-any.whl"
    sdist = destination / f"{distribution}-{version}.tar.gz"
    expected = {
        wheel.name,
        sdist.name,
        f'contextopus-core-{version}.zip',
        *(
            f"contextopus-{client}-{platform}-{version}.zip"
            for client in CLIENTS for platform in ("unix", "windows")
        ),
    }
    observed = {}
    for line in (destination / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        if name in observed or Path(name).name != name:
            raise ValueError("Invalid checksum manifest name")
        observed[name] = checksum
    if set(observed) != expected:
        raise ValueError(
            "Release asset manifest is incomplete or includes unexpected assets"
        )
    for name, checksum in observed.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Checksum mismatch: {name}")
    sys.path.insert(0, str(ROOT))
    from distribution.bundle import load_bundle, safe_path
    with tempfile.TemporaryDirectory(prefix='contextopus-core-release-check-') as temporary:
        with zipfile.ZipFile(destination / f'contextopus-core-{version}.zip') as archive:
            for info in archive.infolist():
                name = info.filename.rstrip('/')
                safe_path(name)
                if not name.startswith('contextopus/') or stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFDIR, stat.S_IFREG}:
                    raise ValueError('Unsafe Core installer archive member')
            archive.extractall(temporary)
        bundle = load_bundle(Path(temporary) / 'contextopus')
        if bundle['core']['version'] != version:
            raise ValueError('Core-only installer has inconsistent contents')
    required = {
        "contextopus/startup.py",
        "contextopus/core/model_setup.py",
        "contextopus/core/analytics.py",
        "contextopus/core/search_history.py",
        "contextopus/core/module_storage/service.py",
        "contextopus/core/module_management/bridge.py",
        "contextopus/core/module_management/child.py",
        "contextopus/core/module_management/contributions.py",
        "contextopus/core/module_management/services.py",
        "contextopus/core/module_management/source.py",
        "contextopus/core/module_management/module_files.py",
        "contextopus/core/module_storage/trusted.py",
        "contextopus/resources/procedures/modules.md",
        "contextopus/interfaces/mcp/presentation.py",
    }
    skills = {'modules'}
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        dist_info = f"{distribution}-{version}.dist-info"
        package_metadata = BytesParser().parsebytes(archive.read(f"{dist_info}/METADATA"))
        if package_metadata['Name'] != metadata['name'] or package_metadata['Version'] != version:
            raise ValueError('Wheel package identity does not match the source release')
        entrypoints = archive.read(f'{dist_info}/entry_points.txt').decode()
        if 'contextopus = contextopus.interfaces.cli.main:main' not in entrypoints:
            raise ValueError('Wheel misses the real CLI entrypoint')
        if package_metadata["License-Expression"] != "Apache-2.0":
            raise ValueError("Wheel license metadata is missing or inconsistent")
        if set(package_metadata.get_all("License-File", [])) != {"LICENSE", "NOTICE"}:
            raise ValueError("Wheel license file declarations are incomplete")
        for name in ("LICENSE", "NOTICE"):
            if archive.read(f"{dist_info}/licenses/{name}") != (ROOT / name).read_bytes():
                raise ValueError(f"Wheel misses the exact {name}")
        if not required <= names:
            raise ValueError("Wheel misses required application modules/resources")
        forbidden = ('contextopus/modules/', 'contextopus/resources/base_context/',
                     'workspace/', 'modules/workspace/')
        if any(name.startswith(forbidden) for name in names):
            raise ValueError('Core wheel contains optional Workspace code or documentation')
        if any(name.startswith('contextopus/resources/procedures/')
               and name != 'contextopus/resources/procedures/modules.md'
               and not name.endswith('/') for name in names):
            raise ValueError('Core wheel contains module-owned procedures')
        source_package = ROOT / "src/contextopus"
        for path in source_package.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".md", ".yaml"} and "__pycache__" not in path.parts:
                member = "contextopus/" + path.relative_to(source_package).as_posix()
                if member not in names or archive.read(member) != path.read_bytes():
                    raise ValueError(f"Wheel has missing or stale application content: {member}")
        packaged_skills = {PurePosixPath(n).parts[-2] for n in names
                           if n.startswith("contextopus/resources/skills/") and n.endswith("/SKILL.md")}
        if packaged_skills != {'modules'}:
            raise ValueError(f"Wrong wheel skill set: {packaged_skills}")
        if any(
            PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
            for name in names
        ):
            raise ValueError("Unsafe wheel member path")
    with tarfile.open(sdist) as archive:
        names = {PurePosixPath(name).parts[1:] for name in archive.getnames()}
        if any(parts and (parts[0] == 'modules' or parts[:2] == ('plugins', 'persistent-context-workspace')) for parts in names):
            raise ValueError('Core source archive contains optional module source')
        for name in ("LICENSE", "NOTICE"):
            member = archive.extractfile(f"{distribution}-{version}/{name}")
            if member is None or member.read() != (ROOT / name).read_bytes():
                raise ValueError(f"sdist misses the exact {name}")
        required_source = [ROOT / 'pyproject.toml', ROOT / 'README.md', ROOT / 'CHANGELOG.md', ROOT / 'uv.lock',
                           ROOT / 'scripts/build_release.py', ROOT / 'scripts/verify_release.py',
                           ROOT / 'scripts/verify_installed.py',
                           ROOT / 'tests/fake_embeddings.py',
                           ROOT / 'plugins/contextopus/.codex-plugin/plugin.json',
                           ROOT / 'docs/releases' / (version + '.md')]
        required_source.extend((ROOT / 'docs').rglob('*.md'))
        required_source.extend((ROOT / 'scripts').glob('*.py'))
        required_source.extend(path for path in (ROOT / 'tests').rglob('*')
                               if path.is_file() and path.suffix in {'.py', '.md', '.json', '.jsonl', '.yaml'}
                               and '__pycache__' not in path.parts)
        required_source.extend(path for path in (ROOT / 'examples/modules/catalog-demo').rglob('*')
                               if path.is_file() and path.suffix in {'.py', '.json', '.sql'})
        required_source.extend(path for path in (ROOT / 'plugins/contextopus').rglob('*')
                               if path.is_file() and path.suffix in {'.md', '.json'})
        required_source.extend(path for path in (ROOT / 'src/contextopus').rglob('*')
                               if path.is_file() and path.suffix in {'.py', '.md', '.json', '.yaml'}
                               and '__pycache__' not in path.parts)
        for path in required_source:
            member = archive.extractfile(f'{distribution}-{version}/' + path.relative_to(ROOT).as_posix())
            if member is None or member.read() != path.read_bytes():
                raise ValueError(f'sdist has missing or stale source content: {path.relative_to(ROOT)}')
    skill_sources = [ROOT / 'src/contextopus/resources/skills']
    source_skills = {path.parent.name: path for source in skill_sources for path in source.glob('*/SKILL.md')}
    if set(source_skills) != skills:
        raise ValueError('Core skill inventory is incomplete')
    plugin_skills = ROOT / 'plugins/contextopus/skills'
    if {path.parent.name for path in plugin_skills.glob('*/SKILL.md')} != skills:
        raise ValueError('Client plugin skill inventory differs from canonical resources')
    for path in source_skills.values():
        if (plugin_skills / path.parent.name / 'SKILL.md').read_bytes() != path.read_bytes():
            raise ValueError('Stale client plugin skill copy: ' + path.parent.name)
    for client in CLIENTS:
        for platform in ('unix', 'windows'):
            with tempfile.TemporaryDirectory(prefix='contextopus-client-check-') as temporary:
                with zipfile.ZipFile(destination / f'contextopus-{client}-{platform}-{version}.zip') as archive:
                    for info in archive.infolist():
                        safe_path(info.filename.rstrip('/'))
                        if stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFDIR, stat.S_IFREG}:
                            raise ValueError('Unsafe client archive member')
                    archive.extractall(temporary)
                package = Path(temporary) / 'contextopus'
                client_data = json.loads((package / 'client.json').read_text())
                if client_data['client'] != client or client_data['platform'] != platform:
                    raise ValueError('Client identity mismatch')
                runtime = load_bundle(package / 'runtime')
                if runtime['core'] != bundle['core'] or runtime['modules'] != bundle['modules']:
                    raise ValueError('Client runtime differs from starter')
                for name in ('LICENSE', 'NOTICE'):
                    if (package / name).read_bytes() != (ROOT / name).read_bytes():
                        raise ValueError('Client license mismatch')
                if client_data['delivery'] == 'plugin':
                    expected_skills = dict(source_skills)
                    for module in runtime['modules']:
                        folder = package / 'runtime' / module['path']
                        manifest = json.loads((folder / 'module.json').read_text())
                        if manifest.get('skills'):
                            for skill in (folder / 'package' / manifest['skills']).glob('*/SKILL.md'):
                                expected_skills[skill.parent.name] = skill
                    actual = {p.parent.name for p in (package / 'skills').glob('*/SKILL.md')}
                    if actual != set(expected_skills) | {'setup'}:
                        raise ValueError('Client skill inventory mismatch')
                    for name, source in expected_skills.items():
                        if (package / 'skills' / name / 'SKILL.md').read_bytes() != source.read_bytes():
                            raise ValueError('Stale bundled skill: ' + name)
    for relative in ('plugins/contextopus/.codex-plugin/plugin.json', 'plugins/contextopus/plugin.json'):
        manifest = json.loads((ROOT / relative).read_text())
        if manifest['version'] != version or manifest['name'] != 'contextopus':
            raise ValueError('Client plugin identity differs from application: ' + relative)
    print(
        f"Verified {len(expected)} release assets and canonical packaged resources for {version}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, help='Directory containing release artifacts and SHA256SUMS')
    verify(parser.parse_args().output_directory)
