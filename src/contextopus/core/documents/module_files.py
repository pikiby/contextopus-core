"""Scoped Markdown storage for native and child modules."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

import yaml

from ..module_storage.coordination import module_resource
from ..rag import DocumentKey, IndexDocument
from .files import read_document, scan_markdown, parse_document
from ..storage import sync_directory
from .reconcile import SourceSnapshot, plan


class ModuleDocuments:
    def __init__(self, layout, module):
        self.layout, self.module = layout, module
        self.root = layout.module_data(module)

    def _path(self, relative, *, markdown=False):
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or ":" in relative or relative.startswith("/")):
            raise ValueError("Expected a relative module data path")
        parts = relative.split("/")
        if any(not p or p in {".", ".."} or p.startswith(".") for p in parts):
            raise ValueError("Invalid module data path")
        path = self.root.joinpath(*parts)
        for parent in (path, *path.parents):
            if parent == self.layout.root:
                break
            if parent.is_symlink():
                raise ValueError("Module document paths cannot contain symlinks")
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Document escapes module data")
        if markdown and path.suffix != ".md":
            raise ValueError("Document path must end in .md")
        return path

    def _wire(self, document, root):
        path = root / document.location
        return {**asdict(document), "file_revision": hashlib.sha256(path.read_bytes()).hexdigest(),
                "path": str(path)}

    def prepare(self, directory):
        with module_resource(self.layout, self.module, "documents"):
            path = self._path(directory)
            path.mkdir(parents=True, exist_ok=True)
            return {"path": str(path)}

    def scan(self, directory, collection=None):
        root = self._path(directory)
        snapshot = scan_markdown(root, module=self.module, collection=collection or directory)
        documents = [self._wire(document, root) for document in snapshot.documents]
        # Full-file digests and parsed bodies must describe the same scan.
        check = scan_markdown(root, module=self.module, collection=collection or directory)
        if check != snapshot:
            raise ValueError("Module documents changed during scan; retry")
        return {"documents": documents, "complete": True}

    def write(self, directory, path, metadata, text, expected_revision=None, collection=None):
        if not isinstance(metadata, dict) or not isinstance(text, str):
            raise ValueError("Metadata must be an object and text must be a string")
        json.dumps(metadata, allow_nan=False)
        for name in ("id", "type"):
            if not isinstance(metadata.get(name), str) or not metadata[name].strip():
                raise ValueError("Document requires a text " + name)
        raw = ("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
               + "---\n" + text).encode("utf-8")
        if len(raw) > 524288:
            raise ValueError("Module document exceeds 512 KiB")
        parse_document(raw, location=path, module=self.module, collection=collection or directory)
        with module_resource(self.layout, self.module, "documents"):
            root, target = self._path(directory), self._path(directory + "/" + path, markdown=True)
            previous = target.read_bytes() if target.exists() else None
            actual = hashlib.sha256(previous).hexdigest() if previous is not None else None
            if expected_revision != actual:
                raise ValueError("Document changed; read its current revision")
            if root.exists():
                for existing in scan_markdown(root, module=self.module, collection=collection or directory).documents:
                    if existing.key.id == metadata["id"] and root / existing.location != target:
                        raise ValueError("Duplicate document identity: " + metadata["id"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".document-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if (target.read_bytes() if target.exists() else None) != previous:
                    raise ValueError("Document changed; read its current revision")
                os.replace(temporary, target)
                sync_directory(target.parent)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            document = read_document(target, root=root, module=self.module, collection=collection or directory)
            return self._wire(document, root)

    def delete(self, directory, path, expected_revision):
        with module_resource(self.layout, self.module, "documents"):
            target = self._path(directory + "/" + path, markdown=True)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected_revision:
                raise ValueError("Document changed; read its current revision")
            target.unlink()
            sync_directory(target.parent)
            return {"deleted": True, "path": str(target)}

    def plan(self, collection, documents, previous, complete=False):
        def decode(items):
            result = []
            for item in items:
                key = item["key"]
                if key.get("module", self.module) != self.module:
                    raise PermissionError("Document scope is restricted to the calling module")
                result.append(IndexDocument(DocumentKey(self.module, key["collection"], key["id"]),
                    item["revision"], item.get("text", ""), item["location"], item.get("metadata", {})))
            return tuple(result)
        result = plan(SourceSnapshot(self.module, collection, decode(documents), complete), decode(previous))
        return {"upsert": [asdict(x) for x in result.upsert],
                "refresh": [asdict(x) for x in result.refresh],
                "delete": [asdict(x) for x in result.delete],
                "unchanged": [asdict(x) for x in result.unchanged]}
