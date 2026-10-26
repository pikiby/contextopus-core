"""File-authoritative shared instruction library; indexing is a derived view."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

import yaml

from ..rag import DocumentKey, IndexDocument
from ..storage import sync_directory
from .files import parse_document, read_document, scan_markdown
from .links import resolve_required
from .projection import reconcile_index
from .reconcile import SourceSnapshot


class InstructionLibrary:
    """Own Markdown/YAML documents in ``root/core/instructions``.

    Bodies are complete instruction text, including any user-supplied Markdown
    front matter. Only the outer YAML mapping is technical metadata. Reads never
    initialize directories, locks, embeddings, or an index.
    """

    def __init__(self, layout, index=None):
        self.layout, self.index = layout, index
        self.root = layout.root / "core" / "instructions"
        if index is not None:
            index.register_source("core", self)

    def _safe_root(self):
        for path in (self.layout.root / "core", self.root):
            if path.is_symlink():
                raise ValueError("Instruction directories cannot be symlinks")

    @staticmethod
    def _validate(document):
        metadata = document.metadata
        if metadata.get("type") != "instruction":
            raise ValueError("Instruction type must be instruction")
        for name in ("title", "description"):
            if name in metadata and not isinstance(metadata[name], str):
                raise ValueError(name + " must be text")
        if "config" in metadata and not isinstance(metadata["config"], dict):
            raise ValueError("config must be a mapping")
        required = metadata.get("instructions", {})
        if not isinstance(required, dict):
            raise ValueError("instructions must map roles to wikilinks")
        for role, reference in required.items():
            if not isinstance(role, str) or not isinstance(reference, str) or not (
                reference.startswith("[[") and reference.endswith("]]")
                and reference[2:-2].split("|", 1)[0].strip()
            ):
                raise ValueError("instructions must map roles to wikilinks")
        json.dumps(metadata, allow_nan=False)

    def _snapshot(self):
        self._safe_root()
        if not self.root.exists():
            return SourceSnapshot("core", "instructions", (), complete=True)
        return scan_markdown(self.root, module="core", collection="instructions",
                             validate=self._validate)

    def snapshot(self):
        """Capture validated instruction sources for a shared-index rebuild."""
        return self._snapshot()

    def _path(self, relative):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ValueError("Expected a relative Markdown path")
        value = PurePosixPath(relative)
        if (value.is_absolute() or any(part.startswith(".") or ":" in part for part in value.parts)
                or value.suffix != ".md"):
            raise ValueError("Expected a relative Markdown path")
        path = self.root.joinpath(*value.parts)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Instruction path must remain inside its source directory")
        if any(parent.is_symlink() for parent in (path, *path.parents)
               if parent != self.layout.root.parent):
            raise ValueError("Instruction symlinks are not supported")
        return path

    def _record(self, document):
        path = self._path(document.location)
        raw = path.read_bytes()
        current = read_document(path, root=self.root, module="core", collection="instructions")
        if current != document or raw != path.read_bytes():
            raise ValueError("Instruction changed during read; retry")
        metadata = document.metadata
        return {"id": document.key.id, "type": "instruction",
                "title": metadata.get("title", document.key.id),
                "description": metadata.get("description", ""),
                "path": document.location, "content": document.text,
                "revision": hashlib.sha256(raw).hexdigest(), "metadata": metadata}

    @staticmethod
    def _reference(reference):
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("Expected an instruction reference")
        if reference.startswith("[[") and reference.endswith("]]"):
            reference = reference[2:-2].split("|", 1)[0].strip()
        if not reference or "[[" in reference or "]]" in reference:
            raise ValueError("Invalid instruction reference")
        return reference

    def read(self, reference):
        """Read a complete body and full-file revision by exact ID or wikilink."""
        name = self._reference(reference)
        matches = [document for document in self._snapshot().documents if name in {
            document.key.id, document.location,
            str(PurePosixPath(document.location).with_suffix("")),
            PurePosixPath(document.location).stem}]
        if not matches:
            raise FileNotFoundError("Missing instruction: " + name)
        if len(matches) != 1:
            raise ValueError("Ambiguous instruction: " + name)
        return self._record(matches[0])

    def resolve(self, references, prepared=None):
        """Resolve exact required links recursively, dependencies first and once each."""
        if not isinstance(references, (list, tuple)):
            raise ValueError("references must be a list")
        references = ["[[" + self._reference(reference) + "]]" for reference in references]
        documents = list(self._snapshot().documents)
        pending = {}
        for item in prepared or []:
            document = parse_document(item["text"].encode("utf-8"), location=item["path"],
                                      module="core", collection="instructions")
            self._validate(document)
            matches = [d for d in documents if d.key == document.key or d.location == document.location]
            if matches:
                if (len(matches) != 1 or matches[0].key != document.key
                        or matches[0].location != document.location
                        or self._record(matches[0])["revision"] != item["revision"]):
                    raise ValueError("Prepared instruction conflicts with an existing document")
            else:
                documents.append(document)
                pending[document.key] = {key: value for key, value in item.items() if key != "text"}
        documents = resolve_required(documents, references)
        records = [pending[document.key] if document.key in pending else self._record(document)
                   for document in documents]
        revisions = [[record["id"], record["path"], record["revision"]] for record in records]
        revision = hashlib.sha256(json.dumps(revisions, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        return {"instructions": records, "revision": revision}

    def prepare_create(self, path, metadata, content):
        """Render a new instruction for an owner's review without saving it."""
        self._safe_root()
        target = self._path(path)
        if target.exists():
            raise ValueError("Instruction already exists; select it instead of creating it")
        if not isinstance(metadata, dict) or not isinstance(content, str):
            raise ValueError("Expected metadata mapping and instruction text")
        # Owners persist drafts as JSON; key order must survive that round trip.
        metadata = json.loads(json.dumps(metadata, sort_keys=True, allow_nan=False))
        raw = "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n" + content
        document = parse_document(raw.encode("utf-8"), location=path,
                                  module="core", collection="instructions")
        self._validate(document)
        if any(d.key == document.key for d in self._snapshot().documents):
            raise ValueError("Duplicate instruction identity: " + document.key.id)
        return {"id": document.key.id, "type": "instruction", "path": path,
                "title": metadata.get("title", document.key.id),
                "description": metadata.get("description", ""),
                "metadata": deepcopy(metadata), "content": content, "text": raw,
                "revision": hashlib.sha256(raw.encode("utf-8")).hexdigest()}

    def bind(self, metadata, role, reference, prepared=None):
        """Build one exact binding; the document owner reviews and persists it."""
        if not isinstance(metadata, dict) or not isinstance(role, str) or not role.strip():
            raise ValueError("Expected document metadata and a nonempty instruction role")
        result = deepcopy(metadata)
        bindings = result.setdefault("instructions", {})
        if not isinstance(bindings, dict):
            raise ValueError("instructions must map roles to wikilinks")
        selected = self.resolve([reference], prepared=prepared)["instructions"][-1]
        bindings[role] = "[[" + selected["id"] + "]]"
        resolved = self.resolve(list(bindings.values()), prepared=prepared)
        return {"metadata": result, **resolved}

    def list(self):
        """List instruction identities and descriptions without loading an embedding model."""
        return {"instructions": [{key: value for key, value in self._record(document).items()
                                  if key not in {"content", "metadata"}}
                                 for document in self._snapshot().documents]}

    def _index_configured(self):
        return (self.index is not None and (self.index.embeddings is not None
                or (self.layout.rag / "active.json").is_file()))

    def save(self, path, metadata, content, expected_revision=None):
        """Create or replace an instruction, requiring the prior full revision for updates."""
        self._safe_root()
        target = self._path(path)
        if not isinstance(metadata, dict) or not isinstance(content, str):
            raise ValueError("Expected metadata mapping and instruction text")
        if not isinstance(metadata.get("id"), str) or not metadata["id"].strip():
            raise ValueError("Instruction requires a text id")
        document = IndexDocument(DocumentKey("core", "instructions", metadata["id"]),
            hashlib.sha256(content.encode("utf-8")).hexdigest(), content,
            target.relative_to(self.root).as_posix(), metadata)
        self._validate(document)
        raw = ("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
               + "---\n" + content).encode("utf-8")
        document = parse_document(raw, location=document.location, module="core", collection="instructions")
        self._validate(document)
        with self.layout.guard():
            self._safe_root()
            target = self._path(path)
            snapshot = self._snapshot()
            for existing in snapshot.documents:
                if existing.key == document.key and existing.location != document.location:
                    raise ValueError("Duplicate instruction identity: " + document.key.id)
            previous = target.read_bytes() if target.exists() else None
            if ((previous is not None and expected_revision != hashlib.sha256(previous).hexdigest())
                    or (previous is None and expected_revision is not None)):
                raise ValueError("Instruction revision conflict")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                descriptor, temporary = tempfile.mkstemp(prefix=".instruction-", dir=target.parent)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if (target.read_bytes() if target.exists() else None) != previous:
                    raise ValueError("Instruction revision conflict")
                os.replace(temporary, target)
                temporary = None
                sync_directory(target.parent)
            finally:
                if temporary is not None:
                    os.unlink(temporary)
            result = self._record(document)
            result["index"] = {"status": "pending"}
            if self.index is not None and not self._index_configured():
                result["index"]["error"] = "Initialize the Core embedding profile before indexing"
            elif self.index is not None:
                try:
                    self.index.index(document)
                    result["index"] = {"status": "indexed"}
                except Exception as exc:
                    result["index"]["error"] = str(exc)
            return result

    def reconcile(self):
        """Explicitly rebuild the instruction projection from a complete file scan."""
        if self.index is None:
            return {"status": "pending", "error": "No shared index configured"}
        with self.layout.guard():
            self._safe_root()
            if not self.root.is_dir():
                raise ValueError("Instruction source directory is missing; reconciliation refused")
            if not self._index_configured():
                return {"status": "pending", "error": "Initialize the Core embedding profile before indexing"}
            return {"status": "indexed", **reconcile_index(self.index, self._snapshot())}

    def search(self, query, limit=None, selection=None, output="materials"):
        """Search the shared RAG restricted to Core instruction documents."""
        if self.index is None:
            raise RuntimeError("No shared index configured")
        return self.index.search_detailed(query, module="core", collection="instructions",
            object_type="instruction", limit=limit, selection=selection, output=output)

    def eligible_documents(self, rows):
        """Exclude deleted instructions while preserving other Core-owned collections."""
        documents = ({document.key: document for document in self._snapshot().documents}
                     if any(row["collection"] == "instructions" for row in rows) else {})
        for row in rows:
            if row["collection"] != "instructions":
                key = DocumentKey(row["module"], row["collection"], row["object_id"])
                documents[key] = IndexDocument(key, row.get("revision", ""), "", row["path"],
                    json.loads(row["metadata"] or "{}"))
        return documents
