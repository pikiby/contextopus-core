"""Reference-counted process sharing of identical embedding configurations."""
from __future__ import annotations

import json
import threading

from .embeddings import EmbeddingError, create_provider, validate_config


class ProviderPool:
    """One lazy adapter/model per normalized config, shared across workspaces.

    Leases remain held between calls. A switch or workspace close releases only
    its own lease, and the final release closes the underlying adapter/model.
    """

    def __init__(self, factory=create_provider):
        self._factory = factory
        self._lock = threading.RLock()
        self._entries = {}

    def acquire(self, config):
        normalized = validate_config(config)
        key = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        with self._lock:
            if key not in self._entries:
                self._entries[key] = [self._factory(normalized), 0]
            entry = self._entries[key]
            entry[1] += 1
            return _Lease(self, key, entry[0])

    def _release(self, key):
        with self._lock:
            entry = self._entries[key]
            entry[1] -= 1
            if entry[1] == 0:
                del self._entries[key]
                entry[0].close()


class _Lease:
    def __init__(self, pool, key, provider):
        self._pool, self._key, self._provider = pool, key, provider
        self._closed = False
        self._lock = threading.RLock()

    def embed(self, texts, purpose="document"):
        with self._lock:
            if self._closed:
                raise EmbeddingError("Embedding provider lease is closed")
            return self._provider.embed(texts, purpose=purpose)

    def tokenizer(self):
        with self._lock:
            if self._closed:
                raise EmbeddingError("Embedding provider lease is closed")
            return self._provider.tokenizer()

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._pool._release(self._key)


PROCESS_PROVIDERS = ProviderPool()
