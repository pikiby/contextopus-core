"""Verify release asset identity, contents and checksums without installing anything."""

from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
            for client in ("codex", "claude-code", "opencode", "crush")
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
        "contextopus/modules/workspace/default_instructions.md",
        "contextopus/resources/procedures/workspace.md",
    }
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        if not required <= names:
            raise ValueError("Wheel misses required application modules/resources")
        if any(
            PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
            for name in names
        ):
            raise ValueError("Unsafe wheel member path")
    with tarfile.open(sdist) as archive:
        names = {PurePosixPath(name).parts[1:] for name in archive.getnames()}
        if tuple("pyproject.toml".split("/")) not in names:
            raise ValueError("sdist misses project metadata")
    source = ROOT / "src/contextopus/resources/skills"
    for client in ("codex", "claude-code", "opencode", "crush"):
        with zipfile.ZipFile(
            destination / f"contextopus-{client}-{version}.zip"
        ) as archive:
            for skill in source.iterdir():
                if (
                    skill.is_dir()
                    and archive.read(f"skills/{skill.name}/SKILL.md")
                    != (skill / "SKILL.md").read_bytes()
                ):
                    raise ValueError(f"Stale {client} skill bundle: {skill.name}")
    manifest = json.loads(
        (ROOT / "plugins/contextopus/.codex-plugin/plugin.json").read_text()
    )
    if manifest["version"] != version:
        raise ValueError("Client plugin version differs from application")
    print(
        f"Verified {len(expected)} release assets and canonical packaged resources for {version}"
    )


if __name__ == "__main__":
    verify()
