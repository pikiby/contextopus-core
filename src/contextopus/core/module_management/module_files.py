"""Portable built-module file validation shared by Core and install bundles.

This module deliberately uses only the standard library. Distribution builders
copy this exact source into extracted bundles for validation before Core exists.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata

class PackageError(ValueError):
    """A module artifact contains unsafe, mutable or inconsistent files."""

_DEVICE = re.compile(r"(?:con|prn|aux|nul|conin\$|conout\$|clock\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?", re.I)
_MODULE_ID = re.compile(r"[a-z][a-z0-9_-]*\Z")

def safe_path(value):
    """Validate a portable relative POSIX path without normalizing its spelling."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise PackageError("Expected a nonempty relative POSIX path")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise PackageError("Paths must contain valid UTF-8 text") from exc
    for part in value.split("/"):
        if (part in {"", ".", ".."} or part.endswith((".", " "))
                or any(ord(c) < 32 or ord(c) == 127 or c in '<>:"|?*' for c in part)
                or _DEVICE.fullmatch(part)):
            raise PackageError("Unsafe or nonportable path: " + repr(value))
    return value


def _collision_key(value):
    return unicodedata.normalize("NFC", value).casefold()


def _unique_paths(paths):
    """Also compare implicit parent directories and detect file/directory overlap."""
    seen = {}
    files = set()
    directories = set()
    for value in paths:
        safe_path(value)
        parts = value.split("/")
        for length in range(1, len(parts) + 1):
            spelling = "/".join(parts[:length])
            key = _collision_key(spelling)
            if key in seen and seen[key] != spelling:
                raise PackageError("Case-insensitive path collision: " + spelling)
            seen[key] = spelling
            (files if length == len(parts) else directories).add(key)
    if files & directories:
        raise PackageError("A payload file is also used as a directory")


def tree_files(root):
    """List regular files; reject symlinks, special files and unsafe directories."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise PackageError("Expected a real bundle/module directory: " + str(root))
    files, names = [], []

    def visit(directory):
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            safe_path(relative)
            names.append(relative)
            if entry.is_symlink():
                raise PackageError("Symlinks are not permitted: " + relative)
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                visit(path)
            elif stat.S_ISREG(mode):
                files.append(relative)
            else:
                raise PackageError("Special files are not permitted: " + relative)

    visit(root)
    by_case = {}
    for name in names:
        key = _collision_key(name)
        if key in by_case:
            raise PackageError("Case-insensitive path collision: " + name)
        by_case[key] = name
    _unique_paths(files)
    return sorted(files)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_object_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError("Cannot read JSON: " + str(path)) from exc
    if not isinstance(value, dict):
        raise PackageError("Expected a JSON object: " + str(path))
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise PackageError(label + " must be nonempty text")
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def module_metadata(root):
    root = Path(root)
    value = read_json(root / "module.json")
    ident = value.get("id")
    if not isinstance(ident, str) or not _MODULE_ID.fullmatch(ident) or ident == "core":
        raise PackageError("Invalid module ID")
    safe_path(ident)
    _text(value.get("version"), "Module version")
    _text(value.get("core_requires"), "Module core_requires")
    if not (root / "package").is_dir():
        raise PackageError("Module requires a package directory: " + ident)
    return {key: value[key] for key in ("id", "version", "core_requires")}


def check_module_payload(paths):
    """Fail rather than silently dropping mutable state or model artifacts."""
    for relative in paths:
        parts = relative.split("/")
        lower = [part.casefold() for part in parts]
        root = lower[0]
        if root in {"data", "config", "contexts", "workspace_contexts", "sessions", "archived_sessions", ".releases", ".current.json", ".tmp", "tmp", ".backups", "backups"}:
            raise PackageError("Module input contains live state: " + relative)
        if any(root == name or root.startswith(name + ".") for name in
               (".env", "credentials", ".credentials", "secrets", ".secrets")):
            raise PackageError("Module input contains sensitive root configuration: " + relative)
        if root.startswith(".") and root.endswith((".bak", ".backup", ".old", ".orig", ".swp", ".swo", "~")):
            raise PackageError("Module input contains a hidden root backup: " + relative)
        if any(part in {".git", "__pycache__", ".venv", "venv", ".cache"} for part in lower):
            raise PackageError("Module input contains a cache/environment: " + relative)
        if (Path(relative).suffix.casefold() in {".pyc", ".jsonl", ".sqlite", ".sqlite3", ".db", ".safetensors", ".gguf", ".ggml", ".pt", ".pth", ".onnx", ".ckpt"}
                or lower[-1] in {"pytorch_model.bin", "model.bin"}
                or re.search(r"\.(?:sqlite3?|db|jsonl)(?:-(?:wal|shm|journal)|\.(?:gz|bz2|xz|zst|zip))$", lower[-1])):
            raise PackageError("Module input contains data/model artifacts: " + relative)


def check_module_license(root, paths):
    licenses = [name for name in paths if "/" not in name and
                (name.upper() == "LICENSE" or name.upper().startswith("LICENSE."))]
    if not licenses or not any((Path(root) / name).stat().st_size for name in licenses):
        raise PackageError("Module input requires a nonempty LICENSE or LICENSE.* file")

