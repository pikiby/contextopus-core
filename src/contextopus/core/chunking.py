"""Deterministic token windows over literal source text; no language-model calls."""

from __future__ import annotations

import copy
import hashlib
import json

from .embeddings import EmbeddingError, embedding_identity


def default_chunking():
    # Engineering defaults, configurable and not claimed to be retrieval-optimal.
    return {
        "chunk_size_tokens": 512,
        "overlap_tokens": 64,
        "tokenizer": {"type": "provider"},
    }


def validate_chunking(value, embedding_config):
    if not isinstance(value, dict) or set(value) != {
        "chunk_size_tokens",
        "overlap_tokens",
        "tokenizer",
    }:
        raise EmbeddingError(
            "Chunking requires chunk_size_tokens, overlap_tokens and tokenizer"
        )
    result = copy.deepcopy(value)
    size, overlap = result["chunk_size_tokens"], result["overlap_tokens"]
    if type(size) is not int or type(overlap) is not int or not 0 < overlap < size:
        raise EmbeddingError(
            "Chunking requires integer 0 < overlap_tokens < chunk_size_tokens"
        )
    if size > embedding_config["profile"]["max_input_tokens"]:
        raise EmbeddingError("Chunk size exceeds the embedding input limit")
    tokenizer = result["tokenizer"]
    if not isinstance(tokenizer, dict):
        raise EmbeddingError("tokenizer must be an explicit object")
    kind = tokenizer.get("type")
    if kind == "provider":
        if (
            set(tokenizer) != {"type"}
            or embedding_config["provider"]["type"] != "sentence-transformers"
        ):
            raise EmbeddingError(
                "Remote embeddings require an explicit compatible tokenizer"
            )
    elif kind == "huggingface":
        if set(tokenizer) - {
            "type",
            "model",
            "revision",
            "cache_folder",
            "local_files_only",
        }:
            raise EmbeddingError("Unsupported Hugging Face tokenizer setting")
        for key in ("model", "revision"):
            if not isinstance(tokenizer.get(key), str) or not tokenizer[key].strip():
                raise EmbeddingError(
                    "Hugging Face tokenizer requires model and revision"
                )
        tokenizer.setdefault("local_files_only", False)
        tokenizer.setdefault("cache_folder", None)
        if type(tokenizer["local_files_only"]) is not bool:
            raise EmbeddingError("tokenizer.local_files_only must be boolean")
        if tokenizer["cache_folder"] is not None and not isinstance(
            tokenizer["cache_folder"], str
        ):
            raise EmbeddingError("tokenizer.cache_folder must be a path or null")
    elif kind == "tiktoken":
        if (
            set(tokenizer) != {"type", "encoding"}
            or not isinstance(tokenizer["encoding"], str)
            or not tokenizer["encoding"]
        ):
            raise EmbeddingError("tiktoken requires an encoding name")
    else:
        raise EmbeddingError(
            "Unsupported tokenizer: use provider, huggingface or tiktoken"
        )
    return result


def chunking_identity(config, embeddings):
    value = validate_chunking(config, embeddings)
    tokenizer = value["tokenizer"]
    for key in ("cache_folder", "local_files_only"):
        tokenizer.pop(key, None)
    if tokenizer["type"] == "provider":
        tokenizer["embedding_identity"] = embedding_identity(embeddings)
    value["algorithm_version"] = 1
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class TokenChunker:
    def __init__(self, config, embeddings, provider):
        self.config = validate_chunking(config, embeddings)
        self.embeddings = embeddings
        self.provider = provider
        self._tokenizer = None

    def _load(self):
        if self._tokenizer is None:
            spec = self.config["tokenizer"]
            try:
                if spec["type"] == "provider":
                    self._tokenizer = self.provider.tokenizer()
                elif spec["type"] == "huggingface":
                    from transformers import AutoTokenizer

                    self._tokenizer = AutoTokenizer.from_pretrained(
                        spec["model"],
                        revision=spec["revision"],
                        use_fast=True,
                        trust_remote_code=False,
                        local_files_only=spec["local_files_only"],
                        cache_dir=spec["cache_folder"],
                    )
                else:
                    import tiktoken

                    self._tokenizer = tiktoken.get_encoding(spec["encoding"])
            except Exception:
                raise EmbeddingError(
                    "Tokenizer unavailable; check its configured model, revision, dependencies and cache"
                ) from None
        return self._tokenizer

    def _offsets(self, text):
        tokenizer = self._load()
        if self.config["tokenizer"]["type"] == "tiktoken":
            ids = tokenizer.encode(text, disallowed_special=())
            # Byte tokens may divide a Unicode codepoint. Offsets deliberately
            # overlap that character so windows cannot emit replacement glyphs.
            raw = text.encode("utf-8")
            owners = [i for i, char in enumerate(text) for _ in char.encode("utf-8")]
            cursor, offsets = 0, []
            for ident in ids:
                part = tokenizer.decode_single_token_bytes(ident)
                if not part or raw[cursor : cursor + len(part)] != part:
                    raise EmbeddingError("Tokenizer bytes do not preserve the source")
                offsets.append((owners[cursor], owners[cursor + len(part) - 1] + 1))
                cursor += len(part)
            if cursor != len(raw):
                raise EmbeddingError("Tokenizer did not cover the source")
        else:
            try:
                encoded = tokenizer(
                    text,
                    add_special_tokens=False,
                    truncation=False,
                    return_offsets_mapping=True,
                    return_attention_mask=False,
                )
                offsets = [tuple(pair) for pair in encoded["offset_mapping"]]
            except Exception:
                raise EmbeddingError(
                    "Chunking requires a tokenizer with source offsets"
                ) from None
            if len(offsets) != len(encoded["input_ids"]):
                raise EmbeddingError("Tokenizer returned inconsistent offsets")
        previous = -1
        for start, end in offsets:
            if not 0 <= start < end <= len(text) or start < previous:
                raise EmbeddingError("Tokenizer returned invalid source offsets")
            previous = start
        return offsets

    def _check_input(self, text):
        profile = self.embeddings["profile"]
        prepared = (
            profile.get("document_prefix", "")
            if profile["input_format"] == "prefix"
            else ""
        ) + text
        tokenizer = self._load()
        if self.config["tokenizer"]["type"] == "tiktoken":
            count = len(tokenizer.encode(prepared, disallowed_special=()))
        else:
            count = len(
                tokenizer(
                    prepared,
                    add_special_tokens=True,
                    truncation=False,
                    return_attention_mask=False,
                )["input_ids"]
            )
        limit = profile["max_input_tokens"]
        actual = getattr(tokenizer, "model_max_length", None)
        if type(actual) is int and 0 < actual < 1_000_000_000:
            limit = min(limit, actual)
        if count > limit:
            raise EmbeddingError(
                "Chunk plus document formatting exceeds the model input limit; reduce chunk_size_tokens"
            )

    def count(self, text):
        """Count literal body tokens using the exact indexing tokenizer."""
        if not isinstance(text, str):
            raise EmbeddingError("Token source must be text")
        return len(self._offsets(text)) if text else 0

    def split(self, text):
        if not isinstance(text, str):
            raise EmbeddingError("Chunk source must be text")
        if not text:
            return []
        offsets = self._offsets(text)
        if not offsets:
            raise EmbeddingError("Tokenizer produced no tokens for nonempty source")
        size, overlap = self.config["chunk_size_tokens"], self.config["overlap_tokens"]
        count = len(offsets)

        def safe(position):
            return (
                position in (0, count)
                or offsets[position - 1][1] <= offsets[position][0]
            )

        start, result = 0, []
        while start < count:
            end = min(start + size, count)
            while end > start and not safe(end):
                end -= 1
            if end <= start:
                raise EmbeddingError(
                    "Chunk window cannot fit a complete Unicode character"
                )
            char_start = 0 if start == 0 else offsets[start][0]
            char_end = len(text) if end == count else offsets[end][0]
            fragment = text[char_start:char_end]
            self._check_input(fragment)
            result.append(
                {
                    "text": fragment,
                    "token_start": start,
                    "token_end": end,
                    "char_start": char_start,
                    "char_end": char_end,
                }
            )
            if end == count:
                break
            next_start = end - overlap
            while next_start > start and not safe(next_start):
                next_start -= 1
            if next_start <= start:
                raise EmbeddingError(
                    "Overlap leaves no progress at a Unicode boundary; use a larger window or smaller overlap"
                )
            start = next_start
        return result
