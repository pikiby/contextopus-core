"""Transport-independent, parent-owned capabilities for a single module child."""

from contextlib import contextmanager
import json
import threading
import weakref

from ..module_storage.contract import module_id, ModuleStorageError
from ..module_storage.sql import check_deadline
from ..module_storage.transactions import StorageTransactions
from ..rag import DocumentKey, IndexDocument, RagIndex
from .protocol import encoded_json_size, response_result_budget


_INDEX_LOCKS = weakref.WeakKeyDictionary()
_INDEX_LOCKS_GUARD = threading.Lock()


class ModuleCoreAccess:
    """Capability session shared by one-shot and persistent child transports.

    ``deadline`` is an absolute monotonic deadline. Transports call ``expire``
    during idle polls and ``close`` on every exit/disconnect path. A provider
    call runs without the root guard; close waits for an in-flight call before
    releasing its lease. The transaction connection allows cleanup on another
    thread and is always protected by the session lock.
    """

    def __init__(self, app, module, *, kind="execute", storage_declared=False, rag_declared=False,
                 provider_owner=None):
        if kind not in {"execute", "query"}:
            raise ValueError("Invalid Core access operation kind")
        self.app, self.module, self.kind = app, module_id(module), kind
        self.storage_declared, self.rag_declared = storage_declared, rag_declared
        if provider_owner is not None and (provider_owner.app is not app or provider_owner.module != module
                                            or provider_owner._provider_owner is not None):
            raise ValueError("Provider owner must be a root session for the same application and module")
        self._provider_owner = provider_owner
        self._lock = threading.RLock()
        self._transactions = StorageTransactions(app.module_storage, module)
        self._closed = False
        self._lease = self._profile_config = None

    @staticmethod
    def _arguments(arguments, required=(), optional=()):
        if (not isinstance(arguments, dict) or set(arguments) - set(required) - set(optional)
                or set(required) - set(arguments)):
            raise ValueError("Invalid Core call arguments; required: " + ", ".join(required))

    @staticmethod
    def _text(value, name, *, empty=False, maximum=1048576):
        if not isinstance(value, str) or (not empty and not value) or len(value) > maximum:
            raise ValueError(name + " must be bounded text")
        return value

    def _scope(self, arguments):
        if arguments.get("module", self.module) != self.module:
            raise PermissionError("Core RAG access is restricted to the calling module")

    def _key(self, value):
        self._arguments(value, ("collection", "id"), ("module",))
        self._scope(value)
        return DocumentKey(self.module, self._text(value["collection"], "collection", maximum=4096),
                           self._text(value["id"], "id", maximum=4096))

    @contextmanager
    def _index(self):
        index = self.app.index
        with _INDEX_LOCKS_GUARD:
            lock = _INDEX_LOCKS.setdefault(index, threading.RLock())
        with lock:
            yield index

    def _profile(self, expected=None):
        if self._provider_owner is not None:
            with self._provider_owner._lock:
                if self._provider_owner._closed:
                    raise RuntimeError("Module embedding owner is closed")
                return self._provider_owner._profile(expected)
        with self._index() as index:
            config = index.profile()
        if self._profile_config is not None and self._profile_config != config:
            self._lease.close()
            self._lease = self._profile_config = None
            raise ValueError("Core embedding profile changed; restart the module")
        if expected is not None and expected != config:
            raise ValueError("Core embedding profile changed; restart the module")
        return config

    def _provider(self, expected):
        if self._provider_owner is not None:
            with self._provider_owner._lock:
                if self._provider_owner._closed:
                    raise RuntimeError("Module embedding owner is closed")
                return self._provider_owner._provider(expected)
        config = self._profile(expected)
        if self._lease is None:
            # Pool leases are owned by this capability session, not registered
            # as permanent ProcessResources leases for every short child call.
            self._lease = self.app.resources.providers.acquire(config)
            self._profile_config = config
        return self._lease, config

    def call(self, method, arguments, deadline=None):
        with self._lock:
            if self._closed:
                raise RuntimeError("Module Core access is closed")
            self.expire()
            if not isinstance(method, str):
                raise ValueError("Core method must be text")
            if method.startswith("storage."):
                try:
                    check_deadline(deadline)
                    return self._storage(method[8:], arguments, deadline)
                except BaseException:
                    if isinstance(arguments, dict):
                        self._transactions.abort_owned(arguments.get("transaction_id"))
                    raise
            check_deadline(deadline)
            if method.startswith(("documents.", "instructions.")):
                if self._transactions.active:
                    raise ModuleStorageError("Finish the storage transaction before document work")
                return self._documents(method, arguments, deadline)
            if method.startswith(("embeddings.", "rag.")):
                if not self.rag_declared:
                    raise PermissionError("Module has no declared Core RAG access")
                if self._transactions.active:
                    raise ModuleStorageError("Finish the storage transaction before model or RAG work")
                owner = self._provider_owner or self
                with owner._lock:
                    check_deadline(deadline)
                    if owner._transactions.active:
                        raise ModuleStorageError("Finish the storage transaction before model or RAG work")
                    if method.startswith("embeddings."):
                        return self._embeddings(method[11:], arguments, deadline)
                    return self._rag(method[4:], arguments, deadline)
            raise ValueError("Unknown Core method: " + method)

    def _documents(self, method, arguments, deadline):
        namespace, action = method.split(".", 1)
        contracts = {
            "documents.prepare": (("directory",), ()),
            "documents.scan": (("directory",), ("collection",)),
            "documents.write": (("directory", "path", "metadata", "text"), ("expected_revision", "collection")),
            "documents.delete": (("directory", "path", "expected_revision"), ()),
            "documents.plan": (("collection", "documents", "previous"), ("complete",)),
            "instructions.read": (("reference",), ()),
            "instructions.resolve": (("references",), ()),
            "instructions.save": (("path", "metadata", "content"), ("expected_revision",)),
            "instructions.list": ((), ()),
            "instructions.reconcile": ((), ()),
            "instructions.search": (("query",), ("selection",)),
        }
        if method not in contracts:
            raise ValueError("Unknown Core document method")
        self._arguments(arguments, *contracts[method])
        if action in {"write", "delete", "prepare", "save", "reconcile"} and self.kind != "execute":
            raise PermissionError("Query operations cannot write Core documents")
        if namespace == "documents":
            from ..documents.module_files import ModuleDocuments
            service = ModuleDocuments(self.app.layout, self.module)
            result = getattr(service, action)(**arguments)
        else:
            from ..documents.instructions import InstructionLibrary
            # The shared index is not thread-safe; use the same gate as RAG.
            with self._index() as index:
                result = getattr(InstructionLibrary(self.app.layout, index), action)(**arguments)
        check_deadline(deadline)
        if encoded_json_size(result) > response_result_budget():
            raise ValueError("Document response exceeds the module protocol budget; narrow the source directory")
        return result

    def _storage(self, method, arguments, deadline):
        if not self.storage_declared:
            raise PermissionError("Module has no declared Core storage")
        if method not in {"query", "execute", "begin", "commit", "rollback"}:
            raise ValueError("Unknown Core storage method")
        if method != "query" and self.kind != "execute":
            raise PermissionError("Query operations cannot write Core storage")
        if method == "begin":
            self._arguments(arguments, (), ("timeout_seconds",))
            return self._transactions.begin(arguments.get("timeout_seconds", 5), deadline=deadline)
        if method in {"commit", "rollback"}:
            self._arguments(arguments, ("transaction_id",))
            if method == "commit":
                return self._transactions.commit(arguments["transaction_id"], deadline=deadline)
            return self._transactions.rollback(arguments["transaction_id"])
        self._arguments(arguments, ("sql",), ("parameters", "transaction_id"))
        parameters = arguments.get("parameters", [])
        if not isinstance(parameters, (list, dict)):
            raise ValueError("SQL parameters must be an array or object")
        if "transaction_id" in arguments:
            return self._transactions.statement(arguments["transaction_id"], arguments["sql"], parameters,
                                                write=method == "execute", deadline=deadline)
        if method == "execute" and self._transactions.active:
            raise ModuleStorageError("Explicit transaction_id required for writes during an active transaction")
        return getattr(self.app.module_storage, method)(self.module, arguments["sql"], parameters, deadline=deadline)

    def _embeddings(self, method, arguments, deadline):
        if method == "profile":
            self._arguments(arguments)
            return self._profile()
        if method == "embed_documents":
            self._arguments(arguments, ("texts", "profile"))
            texts = arguments["texts"]
            if not isinstance(texts, list) or not 1 <= len(texts) <= 128:
                raise ValueError("texts must contain between 1 and 128 documents")
            for text in texts:
                self._text(text, "document")
            purpose = "document"
        elif method in {"embed_query", "count_tokens"}:
            self._arguments(arguments, ("text", "profile"))
            text = self._text(arguments["text"], "text", empty=method == "count_tokens")
            if method == "embed_query" and not text.strip():
                raise ValueError("Query must be nonempty text")
            texts, purpose = [text], "query"
        else:
            raise ValueError("Unknown Core embeddings method")
        if not isinstance(arguments["profile"], dict):
            raise ValueError("profile must be an active embedding configuration")
        provider, config = self._provider(arguments["profile"])
        check_deadline(deadline)
        if method == "count_tokens":
            result = len(provider.tokenizer()(texts[0], add_special_tokens=True, truncation=False)["input_ids"])
        else:
            result = RagIndex.vectors(provider, texts, config["profile"]["dimensions"], purpose)
            if method == "embed_query":
                result = result[0]
        check_deadline(deadline)
        self._profile(config)
        return result

    def _rag(self, method, arguments, deadline):
        if method == "capabilities":
            self._arguments(arguments)
            return {"search": True, "selection_contract": 2, "object_ids": True}
        if method == "search":
            # Child modules use the same settings, grouping and diagnostics as
            # native contributions. The caller cannot widen its module scope.
            self._arguments(arguments, ("query",), (
                "collection", "object_type", "status", "include_archived",
                "selection", "purpose", "task_id", "candidate_limit", "module", "object_ids",
            ))
            self._scope(arguments)
            query = self._text(arguments["query"], "query")
            if not query.strip():
                raise ValueError("Query must be nonempty text")
            options = {key: value for key, value in arguments.items()
                       if key not in {"query", "module"}}
            with self._index() as index:
                check_deadline(deadline)
                result = index.search_detailed(query, module=self.module, **options)
            if encoded_json_size(result) > response_result_budget():
                raise ValueError("Search response exceeds the module protocol budget; narrow the query scope")
            return result
        if method in {"put_vector", "delete_document", "update_document"} and self.kind != "execute":
            raise PermissionError("Query operations cannot write Core RAG")
        if method in {"vector_revisions", "vector_revisions_page"}:
            optional = (("object_ids", "max_bytes", "module") if method == "vector_revisions"
                        else ("cursor", "limit", "max_bytes", "module"))
            self._arguments(arguments, ("collection",), optional)
            self._scope(arguments)
            if method == "vector_revisions" and "object_ids" not in arguments:
                raise ValueError("vector_revisions requires object_ids; use vector_revisions_page for a full inventory")
            collection = self._text(arguments["collection"], "collection", maximum=4096)
            parameters = {key: value for key, value in arguments.items() if key not in {"module", "collection"}}
            with self._index() as index:
                result = getattr(index, method)(self.module, collection, **parameters)
            if encoded_json_size(result) > response_result_budget():
                raise ValueError("Revision response exceeds the module protocol budget; reduce object_ids or max_bytes")
            return result
        if method == "delete_document":
            self._arguments(arguments, ("key",))
            key = self._key(arguments["key"])
            with self._index() as index:
                index.delete_document(key)
            return {"deleted": True}
        if method in {"put_vector", "update_document"}:
            self._arguments(arguments, ("document", "vector", "profile") if method == "put_vector" else ("document",))
            if method == "put_vector" and not isinstance(arguments["profile"], dict):
                raise ValueError("profile must be an active embedding configuration")
            document = arguments["document"]
            self._arguments(document, ("key", "revision", "text", "location"), ("metadata",))
            key = self._key(document["key"])
            metadata = document.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ValueError("Document metadata must be an object")
            if len(json.dumps(metadata, allow_nan=False)) > 262144:
                raise ValueError("Document metadata exceeds 256 KiB")
            item = IndexDocument(key, self._text(document["revision"], "revision", maximum=4096),
                                 self._text(document["text"], "text", empty=True),
                                 self._text(document["location"], "location", maximum=16384), metadata)
            if method == "put_vector":
                self._profile(arguments["profile"])
            with self._index() as index:
                check_deadline(deadline)
                if method == "put_vector":
                    index.put_vector(item, arguments["vector"], profile=arguments["profile"])
                else:
                    index.update_document(item)
            return {"key": [key.module, key.collection, key.id], "revision": item.revision}
        if method == "search_vector":
            self._arguments(arguments, ("collection", "object_ids", "vector", "profile"), ("limit", "module"))
            if not isinstance(arguments["profile"], dict):
                raise ValueError("profile must be an active embedding configuration")
            self._scope(arguments)
            collection = self._text(arguments["collection"], "collection", maximum=4096)
            ids = arguments["object_ids"]
            if not isinstance(ids, list) or len(ids) > 10000:
                raise ValueError("object_ids must be an array of at most 10000 IDs")
            for ident in ids:
                self._text(ident, "object_id", maximum=4096)
            self._profile(arguments["profile"])
            with self._index() as index:
                return index.search_vector(arguments["vector"], module=self.module, collection=collection,
                                           object_ids=ids, profile=arguments["profile"], limit=arguments.get("limit", 20))
        raise ValueError("Unknown Core RAG method")

    def expire(self):
        # A slow model call cannot stall the host monitor's expiry of other
        # independent capability sessions. Busy SQL checks its own deadline.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            return self._transactions.expire()
        finally:
            self._lock.release()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._transactions.close()
            finally:
                if self._lease is not None:
                    self._lease.close()
                    self._lease = self._profile_config = None
