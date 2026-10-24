"""Read Markdown/YAML sources with strict identity and fail-closed enumeration."""

import hashlib
import os
from pathlib import Path
import stat

import yaml

from ..rag import DocumentKey, IndexDocument
from .reconcile import SourceSnapshot


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_document(path, *, root, module, collection):
    path, root = Path(path), Path(root)
    relative = path.relative_to(root)
    if ".." in relative.parts or root.is_symlink():
        raise ValueError("Document must remain inside its source directory")
    if path.is_symlink() or any((root / Path(*relative.parts[:i])).is_symlink()
                                for i in range(1, len(relative.parts))):
        raise ValueError("Document symlinks are not supported")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular Markdown file")
    raw = path.read_bytes()
    return parse_document(raw, location=relative.as_posix(), module=module, collection=collection)


def parse_document(raw, *, location, module, collection):
    """Validate a rendered file before publication, using the reader's parser."""
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("Document requires YAML front matter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("Unterminated YAML front matter")
    metadata = yaml.load("".join(lines[1:end]), Loader=_UniqueLoader)
    if not isinstance(metadata, dict):
        raise ValueError("Document metadata must be a mapping")
    for name in ("id", "type"):
        if not isinstance(metadata.get(name), str) or not metadata[name].strip():
            raise ValueError("Document requires a text " + name)
    body = "".join(lines[end + 1:])
    # YAML remains metadata; it is not embedded as prompt/configuration text.
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return IndexDocument(DocumentKey(module, collection, metadata["id"]), digest,
                         body, location, metadata)


def _inventory(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source directory is missing or is a symlink")
    result = {}

    def failed(error):
        raise error

    for directory, dirs, files in os.walk(root, onerror=failed, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError("Source directory symlinks are not supported")
        for name in sorted(files):
            if name.startswith(".") or not name.endswith(".md"):
                continue
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Document symlinks are not supported")
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Expected a regular Markdown file")
            result[path] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return result


def scan_markdown(root, *, module, collection, validate=None):
    """Capture one source under its owner's lock; never return a failed empty scan.

    A module validator checks its own YAML schema. Concurrent external editors
    cannot be locked by this reader: an observed change aborts the scan and the
    owner must recheck before applying a deletion plan.
    """
    root = Path(root)
    before = _inventory(root)
    documents, ids = [], set()
    for path in before:
        document = read_document(path, root=root, module=module, collection=collection)
        if document.key.id in ids:
            raise ValueError("Duplicate document identity: " + document.key.id)
        ids.add(document.key.id)
        if validate is not None:
            validate(document)
        documents.append(document)
    if before != _inventory(root):
        raise ValueError("Source changed during scan; retry")
    return SourceSnapshot(module, collection, tuple(documents), complete=True)
