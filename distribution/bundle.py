"""Read-only starter-bundle validation, using only the Python standard library."""

from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import zipfile


# The canonical stdlib helper is shared with Core; the builder copies it into
# extracted bundles. Source checkout readers load the same file directly.
import importlib.util
import sys
_helper = Path(__file__).with_name('module_files.py')
if not _helper.is_file():
    _helper = Path(__file__).resolve().parents[1] / 'src/contextopus/core/module_management/module_files.py'
_key = '_contextopus_module_files_' + hashlib.sha256(str(_helper.resolve()).encode()).hexdigest()
if _key not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_key, _helper)
    _shared = importlib.util.module_from_spec(_spec)
    sys.modules[_key] = _shared
    _spec.loader.exec_module(_shared)
_shared = sys.modules[_key]
BundleError = _shared.PackageError
for _name in ('safe_path', '_collision_key', '_unique_paths', 'tree_files',
              '_object_pairs', 'read_json', '_text', 'sha256_file',
              'module_metadata', 'check_module_payload', 'check_module_license'):
    globals()[_name] = getattr(_shared, _name)

REQUIRED_FILES = frozenset({
    "install.py", "install.sh", "install.ps1", "bundle.py", "README.md", "LICENSE", "NOTICE", "module_files.py",
})
OPTIONAL_FILES = frozenset({"install_support.py", "constraints.txt"})


def wheel_metadata(path):
    """Check the wheel name and archive metadata without importing its code."""
    path = Path(path)
    safe_path(path.name)
    if path.is_symlink() or not path.is_file() or path.suffix != ".whl":
        raise BundleError("Expected a regular Core wheel")
    parts = path.name[:-4].split("-")
    if len(parts) not in (5, 6):
        raise BundleError("Invalid Core wheel filename")
    distribution, filename_version = parts[:2]
    if re.sub(r"[-_.]+", "-", distribution).lower() != "contextopus-core":
        raise BundleError("Wheel distribution must be contextopus-core")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename.rstrip("/") for info in infos]
            if len(names) != len(set(names)):
                raise BundleError("Duplicate wheel archive member")
            if len(names) != len({_collision_key(name) for name in names}):
                raise BundleError("Case-insensitive wheel archive collision")
            _unique_paths(info.filename for info in infos if not info.is_dir())
            for info in infos:
                safe_path(info.filename.rstrip("/"))
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise BundleError("Wheel symlinks are not permitted")
                if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise BundleError("Wheel special files are not permitted")
                if info.flag_bits & 1:
                    raise BundleError("Encrypted wheel members are not permitted")
            metadata = [info for info in infos if re.fullmatch(r"[^/]+\.dist-info/METADATA", info.filename)]
            if len(metadata) != 1:
                raise BundleError("Core wheel must have exactly one METADATA file")
            if metadata[0].file_size > 1024 * 1024:
                raise BundleError("Core wheel METADATA is oversized")
            message = BytesParser().parsebytes(archive.read(metadata[0]))
            if len(message.get_all("Name", [])) != 1 or len(message.get_all("Version", [])) != 1:
                raise BundleError("Wheel METADATA must declare one Name and Version")
            name, version = message["Name"], message["Version"]
            if re.sub(r"[-_.]+", "-", name).lower() != "contextopus-core":
                raise BundleError("Wheel METADATA distribution does not match Core")
            _text(version, "Core version")
            if version != filename_version:
                raise BundleError("Wheel filename and METADATA versions differ")
            directory = metadata[0].filename.split("/")[0][:-len(".dist-info")]
            if directory != distribution + "-" + version:
                raise BundleError("Wheel dist-info identity differs from its filename")
            return {"name": name, "version": version}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise BundleError("Cannot read Core wheel: " + str(path)) from exc


def load_bundle(root):
    """Validate a complete extracted bundle before installer planning or actions."""
    root = Path(root)
    actual = set(tree_files(root))
    if "bundle.json" not in actual:
        raise BundleError("Missing bundle.json")
    manifest = read_json(root / "bundle.json")
    if set(manifest) != {"schema_version", "bundle_version", "python", "core", "modules", "files"}:
        raise BundleError("Unexpected or missing bundle manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise BundleError("Unsupported bundle schema_version")
    if manifest["python"] != "3.12":
        raise BundleError("Bundle Python must be exactly 3.12")
    _text(manifest["bundle_version"], "Bundle version")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise BundleError("Bundle files must be a nonempty hash map")
    _unique_paths(files)
    if "bundle.json" in files:
        raise BundleError("bundle.json cannot hash itself")
    if not REQUIRED_FILES.issubset(files):
        raise BundleError("Missing required installer, documentation or license file")
    if actual != set(files) | {"bundle.json"}:
        raise BundleError("Bundle file set differs from the declared payload")
    for name, digest in files.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BundleError("Invalid SHA-256 for " + name)
        if sha256_file(root / name) != digest:
            raise BundleError("SHA-256 mismatch: " + name)
    core = manifest["core"]
    if not isinstance(core, dict) or set(core) != {"path", "version"}:
        raise BundleError("Invalid Core artifact declaration")
    safe_path(core["path"])
    if not core["path"].startswith("packages/") or core["path"].count("/") != 1 or core["path"] not in files:
        raise BundleError("Core wheel must be one declared file under packages/")
    if wheel_metadata(root / core["path"])["version"] != core["version"]:
        raise BundleError("Core version differs from bundle manifest")
    modules = manifest["modules"]
    if not isinstance(modules, list):
        raise BundleError("Bundle modules must be an array")
    seen = set()
    declared_roots = set()
    for record in modules:
        if not isinstance(record, dict) or set(record) != {"id", "version", "path", "core_requires"}:
            raise BundleError("Invalid module artifact declaration")
        ident = record["id"]
        if not isinstance(ident, str):
            raise BundleError("Invalid module ID")
        key = _collision_key(ident)
        if key in seen:
            raise BundleError("Duplicate module ID: " + ident)
        seen.add(key)
        safe_path(record["path"])
        if record["path"] != "modules/" + ident:
            raise BundleError("Module artifact path must match its ID")
        prefix = record["path"] + "/"
        paths = [name[len(prefix):] for name in files if name.startswith(prefix)]
        if not paths:
            raise BundleError("Module artifact is missing: " + ident)
        check_module_payload(paths)
        check_module_license(root / record["path"], paths)
        expected = {key: record[key] for key in ("id", "version", "core_requires")}
        if module_metadata(root / record["path"]) != expected:
            raise BundleError("Module manifest differs from bundle: " + ident)
        declared_roots.add(record["path"])
    allowed = REQUIRED_FILES | OPTIONAL_FILES | {core["path"]}
    for name in files:
        if name not in allowed and not any(name.startswith(prefix + "/") for prefix in declared_roots):
            raise BundleError("Payload file has no declared owner: " + name)
    return manifest
