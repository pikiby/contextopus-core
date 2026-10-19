#!/usr/bin/env python3
"""Build a deterministic local Contextopus starter ZIP from explicit artifacts."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

if __package__:
    from .bundle import (BundleError, REQUIRED_FILES, OPTIONAL_FILES, check_module_license,
                         check_module_payload, load_bundle, module_metadata, safe_path,
                         tree_files, wheel_metadata)
else:
    from bundle import (BundleError, REQUIRED_FILES, OPTIONAL_FILES, check_module_license,
                        check_module_payload, load_bundle, module_metadata, safe_path,
                        tree_files, wheel_metadata)


HERE = Path(__file__).resolve().parent
CORE_ROOT = HERE.parent


def build_bundle(core_wheel, modules, output, bundle_version, *, distribution=HERE, core_root=CORE_ROOT):
    """Package supplied artifacts without installing, resolving or fetching code."""
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except ImportError as exc:
        raise BundleError("Building requires existing packaging; the installer validator uses only stdlib") from exc
    if not isinstance(bundle_version, str) or not bundle_version.strip():
        raise BundleError("An explicit bundle_version is required")
    try:
        Version(bundle_version)
    except ValueError as exc:
        raise BundleError("Invalid bundle version") from exc
    output = Path(output).expanduser().absolute()
    safe_path(output.name)
    if output.suffix.lower() != ".zip":
        raise BundleError("Output must be a .zip path")
    checksum = Path(str(output) + ".sha256")
    if output.exists() or output.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise BundleError("Refusing to overwrite output ZIP or checksum")
    core_wheel = Path(core_wheel)
    core = wheel_metadata(core_wheel)
    core_version = Version(core["version"])
    payload = {}
    distribution, core_root = Path(distribution), Path(core_root)
    for name in sorted(REQUIRED_FILES | OPTIONAL_FILES):
        source = ((CORE_ROOT / 'src/contextopus/core/module_management/module_files.py')
                  if name == 'module_files.py' else
                  (core_root if name in {"LICENSE", "NOTICE"} else distribution) / name)
        if name in OPTIONAL_FILES and not source.exists():
            continue
        if source.is_symlink() or not source.is_file():
            raise BundleError("Missing regular bundle support file: " + str(source))
        payload[name] = source.read_bytes()
    wheel_path = "packages/" + core_wheel.name
    payload[wheel_path] = core_wheel.read_bytes()
    declarations, ids = [], set()
    empty_directories = set()
    for folder in modules:
        folder = Path(folder)
        paths = tree_files(folder)
        check_module_payload(paths)
        check_module_license(folder, paths)
        info = module_metadata(folder)
        if info["id"].casefold() in ids:
            raise BundleError("Duplicate module ID: " + info["id"])
        ids.add(info["id"].casefold())
        try:
            Version(info["version"])
            constraint = SpecifierSet(info["core_requires"])
        except ValueError as exc:
            raise BundleError("Invalid module version or Core compatibility: " + info["id"]) from exc
        if not constraint.contains(core_version, prereleases=True):
            raise BundleError("Core version is incompatible with module: " + info["id"])
        prefix = "modules/" + info["id"]
        declarations.append(dict(info, path=prefix))
        for path in paths:
            payload[prefix + "/" + path] = (folder / path).read_bytes()
        # Preserve even a legitimately empty package directory.
        empty_directories.add(prefix + "/package")
    manifest = {
        "schema_version": 1,
        "bundle_version": bundle_version,
        "python": "3.12",
        "core": {"path": wheel_path, "version": core["version"]},
        "modules": sorted(declarations, key=lambda record: record["id"]),
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payload.items())},
    }
    payload["bundle.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # Exercise the same stdlib-only validator as the extracted installer, before publication.
    with tempfile.TemporaryDirectory(prefix="contextopus-bundle-check-") as temporary:
        staged = Path(temporary)
        for directory in empty_directories:
            (staged / directory).mkdir(parents=True, exist_ok=True)
        for name, content in payload.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        load_bundle(staged)
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    checksum_created = False
    try:
        with output.open("xb") as stream:
            created = True
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for directory in sorted(empty_directories):
                    info = zipfile.ZipInfo("contextopus/" + directory + "/", (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (0o40755 << 16) | 0x10
                    archive.writestr(info, b"")
                for name, content in sorted(payload.items()):
                    info = zipfile.ZipInfo("contextopus/" + name, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (0o100755 if name == "install.sh" else 0o100644) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, content, compresslevel=9)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        with checksum.open("x", encoding="utf-8", newline="\n") as stream:
            checksum_created = True
            stream.write(digest + "  " + output.name + "\n")
    except BaseException:
        if checksum_created:
            checksum.unlink()
        if created:
            output.unlink()
        raise
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-wheel", required=True, type=Path)
    parser.add_argument("--module", action="append", default=[], type=Path,
                        help="Already-built module folder; repeat for additional modules")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bundle-version", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_bundle(args.core_wheel, args.module, args.output, args.bundle_version)
    except (BundleError, OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(result)
    print(str(result) + ".sha256")


if __name__ == "__main__":
    main()
