"""Validate portable module contracts and discover their ordered SQL files."""

import hashlib
from pathlib import Path, PurePosixPath
import re


class ModuleStorageError(ValueError):
    pass


def module_id(module):
    if not isinstance(module, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", module):
        raise ModuleStorageError("Invalid module ID; use lowercase letters, digits, '_' or '-' without ':'")
    return module


def validate_contract(contract):
    required = {"engine", "schema_version", "migrations", "compatible_versions"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ModuleStorageError("Storage contract requires exactly engine, schema_version, migrations and compatible_versions")
    if contract["engine"] != "sqlite":
        raise ModuleStorageError("Only the sqlite domain-storage engine is supported")
    target = contract["schema_version"]
    if type(target) is not int or target < 1:
        raise ModuleStorageError("schema_version must be a positive integer")
    versions = contract["compatible_versions"]
    if (not isinstance(versions, dict) or set(versions) != {"min", "max"}
            or any(type(versions[k]) is not int or versions[k] < 1 for k in ("min", "max"))
            or not versions["min"] <= target <= versions["max"]):
        raise ModuleStorageError("compatible_versions must contain min/max positive integers including schema_version")
    directory = contract["migrations"]
    if (not isinstance(directory, str) or not directory or "\\" in directory
            or ":" in directory or PurePosixPath(directory).is_absolute()
            or any(part in {".", ".."} for part in directory.split("/"))):
        raise ModuleStorageError("migrations must be a contained relative directory in the package")
    return {"engine": "sqlite", "schema_version": target, "migrations": directory,
            "compatible_versions": dict(versions)}


def migration_files(contract, package):
    package = Path(package).resolve(strict=True)
    directory = package / contract["migrations"]
    for ancestor in [directory, *directory.parents]:
        if ancestor == package:
            break
        if ancestor.is_symlink():
            raise ModuleStorageError("Migration paths cannot contain symlinks")
    if not directory.resolve().is_relative_to(package) or not directory.is_dir():
        raise ModuleStorageError("Migration directory is missing or escapes the package")
    result = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".sql":
            continue
        match = re.fullmatch(r"([0-9]{3,})[-_]([A-Za-z0-9][A-Za-z0-9_.-]*)\.sql", path.name)
        if not match or not path.is_file() or path.is_symlink():
            raise ModuleStorageError("Use regular numbered migration files such as 001-schema.sql")
        raw = path.read_bytes()
        try:
            sql = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ModuleStorageError("Migration SQL must be UTF-8") from exc
        result.append({"version": int(match[1]), "name": path.name,
                       "checksum": hashlib.sha256(raw).hexdigest(), "sql": sql})
    result.sort(key=lambda item: item["version"])
    if (len(result) != contract["schema_version"]
            or any(item["version"] != index for index, item in enumerate(result, 1))):
        raise ModuleStorageError("Migration files must contain exactly the continuous steps 1..schema_version")
    return result
