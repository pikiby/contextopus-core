"""Verify release asset identity, contents and checksums without installing anything."""

from pathlib import Path, PurePosixPath
import hashlib
from email.parser import BytesParser
import json
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ("codex", "claude-code", "opencode", "crush", "hermes")


def verify():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = metadata["version"]
    distribution = metadata["name"].replace("-", "_")
    destination = ROOT / "dist"
    wheel = destination / f"{distribution}-{version}-py3-none-any.whl"
    sdist = destination / f"{distribution}-{version}.tar.gz"
    expected = {
        wheel.name,
        sdist.name,
        *(
            f"contextopus-{client}-{version}.zip"
            for client in CLIENTS
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
    required = {
        "contextopus/startup.py",
        "contextopus/core/model_setup.py",
        "contextopus/core/analytics.py",
        "contextopus/core/search_history.py",
        "contextopus/core/module_storage/service.py",
        "contextopus/core/module_management/bridge.py",
        "contextopus/core/module_management/child.py",
        "contextopus/resources/procedures/modules.md",
        "contextopus/interfaces/mcp/presentation.py",
        "contextopus/modules/workspace/settings.py",
        "contextopus/modules/workspace/links.py",
        "contextopus/modules/workspace/default_instructions.md",
        "contextopus/resources/procedures/workspace.md",
    }
    skills = {"w", "w-search", "w-create", "w-settings", "w-context", "w-analyze", "m"}
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
        source_package = ROOT / "src/contextopus"
        for path in source_package.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".md", ".yaml"} and "__pycache__" not in path.parts:
                member = "contextopus/" + path.relative_to(source_package).as_posix()
                if member not in names or archive.read(member) != path.read_bytes():
                    raise ValueError(f"Wheel has missing or stale application content: {member}")
        packaged_skills = {PurePosixPath(n).parts[-2] for n in names
                           if n.startswith("contextopus/resources/skills/") and n.endswith("/SKILL.md")}
        if packaged_skills != skills:
            raise ValueError(f"Wrong wheel skill set: {packaged_skills}")
        if any(
            PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
            for name in names
        ):
            raise ValueError("Unsafe wheel member path")
    with tarfile.open(sdist) as archive:
        names = {PurePosixPath(name).parts[1:] for name in archive.getnames()}
        for name in ("LICENSE", "NOTICE"):
            member = archive.extractfile(f"{distribution}-{version}/{name}")
            if member is None or member.read() != (ROOT / name).read_bytes():
                raise ValueError(f"sdist misses the exact {name}")
        required_source = [ROOT / 'pyproject.toml', ROOT / 'README.md', ROOT / 'uv.lock',
                           ROOT / 'scripts/build_release.py', ROOT / 'scripts/verify_release.py',
                           ROOT / 'scripts/verify_installed.py',
                           ROOT / 'plugins/contextopus/.codex-plugin/plugin.json',
                           ROOT / 'tests/fixtures/released-short-skills.json',
                           ROOT / 'docs/releases' / (version + '.md')]
        required_source.extend((ROOT / 'docs').rglob('*.md'))
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
    source = ROOT / "src/contextopus/resources/skills"
    plugin_skills = ROOT / 'plugins/contextopus/skills'
    if {path.parent.name for path in plugin_skills.glob('*/SKILL.md')} != skills:
        raise ValueError('Client plugin skill inventory differs from canonical resources')
    for path in source.glob('*/SKILL.md'):
        if (plugin_skills / path.parent.name / 'SKILL.md').read_bytes() != path.read_bytes():
            raise ValueError('Stale client plugin skill copy: ' + path.parent.name)
    for client in CLIENTS:
        with zipfile.ZipFile(
            destination / f"contextopus-{client}-{version}.zip"
        ) as archive:
            bundled_skills = {PurePosixPath(n).parts[-2] for n in archive.namelist()
                              if n.startswith("skills/") and n.endswith("/SKILL.md")}
            if bundled_skills != skills:
                raise ValueError(f"Wrong {client} bundle skill set: {bundled_skills}")
            if any(PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
                   for name in archive.namelist()):
                raise ValueError(f'Unsafe {client} bundle member path')
            instructions = archive.read('INSTALL.txt').decode()
            if f'contextopus_core-{version}-py3-none-any.whl' not in instructions or 'guide, read, write, finish' not in instructions:
                raise ValueError(f'Stale {client} installation instructions')
            if client == "hermes":
                for required_text in (
                    "contextopus integrate hermes --user",
                    "--hermes-home <directory>",
                    "$HERMES_HOME/config.yaml",
                    "$HERMES_HOME/skills/",
                    "%LOCALAPPDATA%/hermes",
                    "HERMES_DATA_DIR_SUFFIX",
                ):
                    if required_text not in instructions:
                        raise ValueError("Incomplete Hermes installation instructions")
                if archive.read("HERMES.md") != (ROOT / "docs/integrations/hermes.md").read_bytes():
                    raise ValueError("Stale Hermes integration guide")
            for name in ("LICENSE", "NOTICE"):
                if archive.read(name) != (ROOT / name).read_bytes():
                    raise ValueError(f"{client} bundle misses the exact {name}")
            for skill in source.iterdir():
                if (
                    skill.is_dir()
                    and archive.read(f"skills/{skill.name}/SKILL.md")
                    != (skill / "SKILL.md").read_bytes()
                ):
                    raise ValueError(f"Stale {client} skill bundle: {skill.name}")
    for relative in ('plugins/contextopus/.codex-plugin/plugin.json', 'plugins/contextopus/plugin.json'):
        manifest = json.loads((ROOT / relative).read_text())
        if manifest['version'] != version or manifest['name'] != 'contextopus':
            raise ValueError('Client plugin identity differs from application: ' + relative)
    print(
        f"Verified {len(expected)} release assets and canonical packaged resources for {version}"
    )


if __name__ == "__main__":
    verify()
