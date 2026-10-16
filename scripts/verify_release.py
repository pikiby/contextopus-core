"""Verify release asset identity, contents and checksums without installing anything."""

from pathlib import Path, PurePosixPath
import hashlib
from email.parser import BytesParser
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
    skills = {"w", "w-search", "w-create", "w-settings", "w-context", "w-analyze"}
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        dist_info = f"{distribution}-{version}.dist-info"
        package_metadata = BytesParser().parsebytes(archive.read(f"{dist_info}/METADATA"))
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
        if tuple("pyproject.toml".split("/")) not in names:
            raise ValueError("sdist misses project metadata")
    source = ROOT / "src/contextopus/resources/skills"
    for client in ("codex", "claude-code", "opencode", "crush"):
        with zipfile.ZipFile(
            destination / f"contextopus-{client}-{version}.zip"
        ) as archive:
            bundled_skills = {PurePosixPath(n).parts[-2] for n in archive.namelist()
                              if n.startswith("skills/") and n.endswith("/SKILL.md")}
            if bundled_skills != skills:
                raise ValueError(f"Wrong {client} bundle skill set: {bundled_skills}")
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
