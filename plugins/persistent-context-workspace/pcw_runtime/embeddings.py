"""Embedding adapters; importing this module never loads or downloads a model.

The connection lives in ``provider`` and the vector-space settings in ``profile``.
The conservative identity also covers execution source: matching model names and
dimensions do not establish compatibility between different servers or runtimes.

Protocol references:
https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
https://sbert.net/docs/package_reference/sentence_transformer/model.html
https://docs.ollama.com/api/embed
https://developers.openai.com/api/reference/python/resources/embeddings/methods/create

An OpenAI-compatible server must reject oversized inputs, as the OpenAI protocol
requires. That protocol has no portable disable-truncation flag: a server which
silently shortens inputs is not a supported implementation of this adapter.
"""

from __future__ import annotations

import copy
import gc
import hashlib
import json
import math
import os
import re
import sys
import threading
from http.client import HTTPException
from numbers import Real
from typing import Any, Literal
from urllib import error, parse, request


Purpose = Literal["document", "query"]
QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
# An immutable model repository revision; never silently follow the main branch.
QWEN_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QUERY_INSTRUCTION = "Given a query, retrieve relevant technical documentation."
_TYPES = {"sentence-transformers", "ollama", "openai-compatible"}


class EmbeddingError(ValueError):
    """Configuration, input or response error safe to show without credentials."""


def default_config() -> dict[str, Any]:
    """Return a fresh default configuration, without loading dependencies."""
    return {
        "provider": {
            "type": "sentence-transformers",
            "device": "cpu",
            "cache_folder": None,
            "local_files_only": False,
        },
        "profile": {
            "model": QWEN_MODEL,
            "revision": QWEN_REVISION,
            "dimensions": 1024,
            "normalization": "l2",
            "input_format": "qwen3",
            "query_instruction": QUERY_INSTRUCTION,
            "max_input_tokens": 32768,
            "precision": "float32",
        },
    }


def _positive_int(value: Any, label: str) -> None:
    if type(value) is not int or value < 1:
        raise EmbeddingError(f"{label} must be a positive integer")


def _string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EmbeddingError(f"{label} must be a nonempty string")


def _endpoint(base_url: str, kind: str) -> str:
    base = base_url.rstrip("/")
    if kind == "ollama":
        return base if base.endswith("/api/embed") else base + "/api/embed"
    if base.endswith("/embeddings"):
        return base
    return base + ("/embeddings" if base.endswith("/v1") else "/v1/embeddings")


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy configuration without contacting any provider.

    Optional settings get explicit defaults. Unknown keys are rejected so keys,
    headers, ignored inference options and typos cannot enter a persisted config.
    ``precision`` records model computation precision (including remote variants);
    returned embeddings always contain floating-point values.
    """
    if not isinstance(config, dict) or set(config) != {"provider", "profile"}:
        raise EmbeddingError("Embedding configuration requires provider and profile objects")
    cfg = copy.deepcopy(config)
    connection, profile = cfg["provider"], cfg["profile"]
    if not isinstance(connection, dict) or not isinstance(profile, dict):
        raise EmbeddingError("Embedding provider and profile must be objects")
    kind = connection.get("type")
    if not isinstance(kind, str) or kind not in _TYPES:
        raise EmbeddingError("Unsupported embedding provider; use sentence-transformers, ollama or openai-compatible")
    profile_keys = {
        "model", "revision", "dimensions", "normalization", "input_format",
        "query_instruction", "max_input_tokens", "precision",
        "query_prefix", "document_prefix",
    }
    if set(profile) - profile_keys:
        raise EmbeddingError("Unsupported embedding profile setting")
    for key in ("model", "revision", "precision"):
        _string(profile.get(key), f"profile.{key}")
    _positive_int(profile.get("dimensions"), "profile.dimensions")
    _positive_int(profile.get("max_input_tokens"), "profile.max_input_tokens")
    if profile.get("normalization") not in ("l2", "none"):
        raise EmbeddingError("profile.normalization must be l2 or none")
    fmt = profile.get("input_format")
    if fmt not in ("qwen3", "raw", "prefix"):
        raise EmbeddingError("profile.input_format must be qwen3, raw or prefix")
    if fmt == "qwen3":
        _string(profile.get("query_instruction"), "profile.query_instruction")
        if "\n" in profile["query_instruction"] or "\r" in profile["query_instruction"]:
            raise EmbeddingError("profile.query_instruction must be a single line")
    elif profile.get("query_instruction") not in (None, ""):
        raise EmbeddingError("query_instruction is only supported with qwen3 input_format")
    if fmt == "prefix":
        for key in ("query_prefix", "document_prefix"):
            if not isinstance(profile.get(key), str):
                raise EmbeddingError(f"profile.{key} must be an explicit string")
    elif any(profile.get(key) not in (None, "") for key in ("query_prefix", "document_prefix")):
        raise EmbeddingError("Input prefixes require prefix input_format")

    if kind == "sentence-transformers":
        allowed = {"type", "device", "cache_folder", "local_files_only"}
        connection.setdefault("device", "cpu")
        connection.setdefault("cache_folder", None)
        connection.setdefault("local_files_only", False)
        _string(connection["device"], "provider.device")
        if connection["cache_folder"] is not None:
            _string(connection["cache_folder"], "provider.cache_folder")
        if type(connection["local_files_only"]) is not bool:
            raise EmbeddingError("provider.local_files_only must be a boolean")
        if profile["precision"] not in ("float32", "float16", "bfloat16"):
            raise EmbeddingError("Unsupported local model precision")
    else:
        allowed = {"type", "base_url", "api_key_env", "timeout_seconds", "send_dimensions"}
        connection.setdefault("api_key_env", None)
        connection.setdefault("timeout_seconds", 60)
        # Some compatible APIs only support the model's native dimension.
        connection.setdefault("send_dimensions", False)
        _string(connection.get("base_url"), "provider.base_url")
        try:
            url = parse.urlsplit(connection["base_url"])
            valid_url = (
                url.scheme in ("http", "https") and bool(url.hostname)
                and url.username is None and url.password is None
                and not url.query and not url.fragment
                and not any(ch.isspace() for ch in connection["base_url"])
            )
            url.port  # Validate the port without echoing a potentially secret URL.
        except ValueError:
            valid_url = False
        if not valid_url:
            raise EmbeddingError("base_url must be an HTTP(S) URL without credentials, query or fragment")
        connection["base_url"] = _endpoint(connection["base_url"], kind)
        env = connection["api_key_env"]
        if env is not None and (not isinstance(env, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env) is None):
            raise EmbeddingError("api_key_env must reference an environment variable name")
        timeout = connection["timeout_seconds"]
        try:
            valid_timeout = not isinstance(timeout, bool) and isinstance(timeout, Real) and math.isfinite(timeout) and timeout > 0
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise EmbeddingError("timeout_seconds must be a finite positive number")
        if type(connection["send_dimensions"]) is not bool:
            raise EmbeddingError("send_dimensions must be a boolean")
    if set(connection) - allowed:
        raise EmbeddingError("Unsupported provider setting; secrets must use api_key_env")
    return cfg


def embedding_identity(config: dict[str, Any]) -> str:
    """Return a stable identity; rotating a credential never changes this value."""
    cfg = validate_config(config)
    connection = {
        key: value for key, value in cfg["provider"].items()
        if key not in {"api_key_env", "timeout_seconds", "cache_folder", "local_files_only"}
    }
    payload = {"adapter_version": 1, "provider": connection, "profile": cfg["profile"]}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_vectors(vectors: Any, count: int, dimensions: int, normalization: str) -> list[list[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    if not isinstance(vectors, (list, tuple)) or len(vectors) != count:
        raise EmbeddingError("Embedding response has an incorrect vector count")
    result = []
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
            raise EmbeddingError("Embedding response has an incorrect vector dimension")
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in vector):
            raise EmbeddingError("Embedding response contains a non-numeric value")
        try:
            values = [float(value) for value in vector]
        except (ValueError, OverflowError):
            raise EmbeddingError("Embedding response contains an invalid numeric value") from None
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingError("Embedding response contains a non-finite value")
        scale = max(abs(value) for value in values)
        if scale == 0:
            raise EmbeddingError("Embedding response contains a zero vector")
        if normalization == "l2":
            # Scaling first avoids overflow and underflow for finite extremes.
            scaled = [value / scale for value in values]
            norm = math.sqrt(math.fsum(value * value for value in scaled))
            values = [value / norm for value in scaled]
        result.append(values)
    return result


class _Provider:
    def __init__(self, config: dict[str, Any]):
        self.config = validate_config(config)
        self.profile = self.config["profile"]
        self._closed = False
        self._lock = threading.RLock()

    def _prepare(self, texts: list[str], purpose: Purpose) -> list[str]:
        if self._closed:
            raise EmbeddingError("Embedding provider is closed")
        if purpose not in ("document", "query"):
            raise EmbeddingError("Embedding purpose must be document or query")
        if not isinstance(texts, list) or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError("Embedding input must be a list of nonempty strings")
        fmt = self.profile["input_format"]
        if fmt == "qwen3" and purpose == "query":
            prefix = f"Instruct: {self.profile['query_instruction']}\nQuery: "
            # Do not duplicate this adapter's instruction if an input was already
            # formatted by its caller. Other text remains literal query content.
            return [text if text.startswith(prefix) else prefix + text for text in texts]
        if fmt == "prefix":
            return [self.profile[f"{purpose}_prefix"] + text for text in texts]
        return list(texts)

    def _validate(self, vectors: Any, count: int) -> list[list[float]]:
        return _validate_vectors(vectors, count, self.profile["dimensions"], self.profile["normalization"])

    def close(self) -> None:
        with self._lock:
            self._closed = True


def _load_sentence_transformer(model: str, **kwargs: Any) -> Any:
    """The sole lazy import boundary, also used for dependency-free tests."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise EmbeddingError("Local embeddings require sentence-transformers and transformers>=4.51.0") from None
    return SentenceTransformer(model, **kwargs)


class LocalProvider(_Provider):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._model = None

    def _load(self) -> Any:
        if self._model is None:
            connection = self.config["provider"]
            try:
                self._model = _load_sentence_transformer(
                    self.profile["model"], revision=self.profile["revision"],
                    device=connection["device"], cache_folder=connection["cache_folder"],
                    local_files_only=connection["local_files_only"], trust_remote_code=False,
                    model_kwargs={"torch_dtype": self.profile["precision"]},
                )
            except EmbeddingError:
                raise
            except Exception:
                raise EmbeddingError("Local embedding model failed to load; check dependencies, model revision and cache") from None
        return self._model

    def _check_lengths(self, model: Any, texts: list[str]) -> None:
        try:
            tokenizer = model.tokenizer
            lengths = [self.profile["max_input_tokens"]]
            for limit in (getattr(model, "max_seq_length", None), getattr(tokenizer, "model_max_length", None)):
                if isinstance(limit, int) and 0 < limit < 1_000_000_000:
                    lengths.append(limit)
            max_tokens = min(lengths)
            tokens = tokenizer(
                texts, add_special_tokens=True, truncation=False,
                padding=False, return_attention_mask=False,
            )["input_ids"]
            if len(tokens) != len(texts):
                raise ValueError("Unexpected tokenizer result")
            for index, token_ids in enumerate(tokens):
                if len(token_ids) > max_tokens:
                    raise EmbeddingError(
                        f"Embedding input {index} has {len(token_ids)} tokens; limit is {max_tokens}. "
                        "Split the source into smaller semantic parts; input was not truncated."
                    )
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("Could not verify local embedding token limits") from None

    def embed(self, texts: list[str], purpose: Purpose = "document") -> list[list[float]]:
        with self._lock:
            prepared = self._prepare(texts, purpose)
            if not prepared:
                return []
            model = self._load()
            self._check_lengths(model, prepared)
            try:
                # An explicit empty prompt disables saved/default prompts. PCW
                # already formatted queries, and documents remain unchanged.
                vectors = model.encode(
                    prepared, prompt="", show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=False,
                    precision="float32",
                )
            except Exception:
                raise EmbeddingError("Local embedding computation failed; no alternative provider was used") from None
            return self._validate(vectors, len(prepared))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            model, self._model = self._model, None
            if model is not None:
                del model
                gc.collect()
                # Releasing tensors leaves reusable accelerator allocations in
                # PyTorch's cache; let a switched model reuse that device memory.
                torch = sys.modules.get("torch")
                device = self.config["provider"]["device"].split(":", 1)[0]
                allocator = getattr(torch, device, None) if device in {"cuda", "mps"} else None
                if allocator is not None and callable(getattr(allocator, "empty_cache", None)):
                    try:
                        allocator.empty_cache()
                    except Exception:
                        # Cleanup must not invalidate an already-published switch.
                        # The model's references were released above regardless.
                        pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        # Do not forward a bearer credential or knowledge to a redirected host.
        return None


class HTTPProvider(_Provider):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._opener = request.build_opener(_NoRedirect())

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        connection = self.config["provider"]
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        env = connection["api_key_env"]
        if env is not None:
            token = os.environ.get(env)
            if not token or any(ord(char) < 32 or ord(char) > 126 for char in token):
                raise EmbeddingError("Embedding API credential is missing or invalid in the configured environment variable")
            headers["Authorization"] = "Bearer " + token
        req = request.Request(
            connection["base_url"], data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with self._opener.open(req, timeout=connection["timeout_seconds"]) as response:
                payload = json.load(response)
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            # Response bodies, URLs, headers and underlying exception strings can
            # contain credentials or document text; never expose them in errors.
            raise EmbeddingError(f"Embedding endpoint rejected the request (HTTP {code})") from None
        except (OSError, ValueError, error.URLError, HTTPException):
            raise EmbeddingError("Embedding endpoint request failed or returned invalid JSON") from None
        if not isinstance(payload, dict) or "error" in payload:
            raise EmbeddingError("Embedding endpoint returned an invalid response or provider error")
        return payload

    def embed(self, texts: list[str], purpose: Purpose = "document") -> list[list[float]]:
        with self._lock:
            prepared = self._prepare(texts, purpose)
            if not prepared:
                return []
            connection = self.config["provider"]
            body = {"model": self.profile["model"], "input": prepared}
            if connection["send_dimensions"]:
                body["dimensions"] = self.profile["dimensions"]
            if connection["type"] == "ollama":
                body["truncate"] = False
                return self._validate(self._post(body).get("embeddings"), len(prepared))
            body["encoding_format"] = "float"
            data = self._post(body).get("data")
            if not isinstance(data, list) or len(data) != len(prepared):
                raise EmbeddingError("Embedding response has an incorrect data count")
            ordered: list[Any] = [None] * len(prepared)
            for entry in data:
                if not isinstance(entry, dict):
                    raise EmbeddingError("Embedding response contains an invalid data entry")
                index = entry.get("index")
                if type(index) is not int or not 0 <= index < len(prepared) or ordered[index] is not None:
                    raise EmbeddingError("Embedding response indices must cover every input exactly once")
                if "embedding" not in entry or entry["embedding"] is None:
                    raise EmbeddingError("Embedding response data entry is missing its vector")
                ordered[index] = entry["embedding"]
            return self._validate(ordered, len(prepared))

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._opener.close()


def create_provider(config: dict[str, Any]) -> LocalProvider | HTTPProvider:
    """Create a provider with no model download or API request until embed()."""
    cfg = validate_config(config)
    if cfg["provider"]["type"] == "sentence-transformers":
        return LocalProvider(cfg)
    return HTTPProvider(cfg)
