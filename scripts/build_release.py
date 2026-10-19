"""Build versioned client bundles and checksums after python -m build."""

from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
CLIENTS = ("codex", "claude-code", "opencode", "crush", "hermes")


def build_core_installer(destination, wheel):
    subprocess.run([sys.executable, str(ROOT / 'distribution/build.py'),
                    '--core-wheel', str(wheel), '--bundle-version', VERSION,
                    '--output', str(destination / f'contextopus-core-{VERSION}.zip')], check=True)


def main(destination=None):
    destination = Path(destination) if destination is not None else ROOT / 'dist'
    destination.mkdir(parents=True, exist_ok=True)
    runtime_assets = [destination / f"contextopus_core-{VERSION}-py3-none-any.whl",
                      destination / f"contextopus_core-{VERSION}.tar.gz"]
    if not all(path.is_file() for path in runtime_assets):
        raise ValueError('Build the exact wheel and source archive before client bundles')
    build_core_installer(destination, runtime_assets[0])
    skills = ROOT / "src/contextopus/resources/skills"
    skill_sources = [skills]
    for client in CLIENTS:
        archive = destination / f"contextopus-{client}-{VERSION}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("LICENSE", "NOTICE"):
                bundle.write(ROOT / name, name)
            members = set()
            for source in skill_sources:
                for path in sorted(source.rglob('*')):
                    if path.is_file():
                        member = 'skills/' + path.relative_to(source).as_posix()
                        if member in members:
                            raise ValueError('Duplicate client skill: ' + member)
                        members.add(member)
                        bundle.write(path, member)
            installation = (
                "Preview: contextopus integrate hermes --user\n"
                "Apply the reviewed preview: contextopus integrate hermes --user --apply\n"
                "Hermes configuration: $HERMES_HOME/config.yaml.\n"
                "Default home: ~/.hermes on Linux/macOS; %LOCALAPPDATA%/hermes on Windows (fallback ~/AppData/Local/hermes).\n"
                "HERMES_DATA_DIR_SUFFIX appends to the platform-default home name; see HERMES.md.\n"
                "Native skills: $HERMES_HOME/skills/m/SKILL.md; enabled modules contribute additional skills.\n"
                "For another Hermes home/profile, pass --hermes-home <directory> to both commands.\n"
                "Follow HERMES.md for source verification, setup and client checks.\n"
                if client == "hermes"
                else f"Preview: contextopus integrate {client} --project <project>\n"
            )
            bundle.writestr(
                "INSTALL.txt",
                f"Verify contextopus_core-{VERSION}-py3-none-any.whl against SHA256SUMS before installation.\n"
                "Core supplies module management (m); obtain optional modules from their own repositories.\n"
                "Install a trusted built folder/ZIP through contextopus --root ROOT modules install ID --source PATH.\n"
                "For an existing root, follow docs/development.md: coherent backup, isolated migration test and reviewed client update.\n"
                "Preserve the existing root, extras, user rules, IDs and pending work.\n"
                + installation +
                "Review paths before repeating with --apply; custom skills are never overwritten.\n"
                "Native clients connect to http://127.0.0.1:8765/mcp.\n"
                "Default tools: guide, read, write, finish. Legacy aliases require explicit CONTEXTOPUS_LEGACY_TOOLS=1.\n",
            )
            if client == "hermes":
                bundle.write(ROOT / "docs/integrations/hermes.md", "HERMES.md")
    assets = sorted([*runtime_assets, destination / f'contextopus-core-{VERSION}.zip', *(
        destination / f"contextopus-{client}-{VERSION}.zip"
        for client in CLIENTS)])
    (destination / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in assets
        )
    )
    print("\n".join(path.name for path in assets))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, help='Directory containing the matching Core wheel and source archive')
    main(parser.parse_args().output_directory)
