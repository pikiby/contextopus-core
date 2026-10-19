"""Module-owned contracts shared by every interface."""

from dataclasses import dataclass
from contextlib import nullcontext
from typing import Callable


@dataclass(frozen=True)
class OperationSpec:
    name: str
    kind: str
    arguments_schema: object
    handler: Callable
    description: str = ""
    observer: Callable | None = None
    guard_root: bool = True


class OperationRegistry:
    def __init__(self, journal=None):
        self._operations = {}
        self.journal = journal
        self.modules = {}
        self.compatibility_adapters = {}
        self.active_operations = {}
        import threading

        self._activity_lock = threading.RLock()

    def register_module(self, name, **metadata):
        self.modules[name] = {"name": name, **metadata}

    def register(self, spec):
        if spec.kind not in {"query", "execute"} or spec.name in self._operations:
            raise ValueError(f"Invalid or duplicate operation: {spec.name}")
        self._operations[spec.name] = spec

    def register_compatibility_adapter(self, owner, register, **metadata):
        """Explicitly mark a replaceable adapter, preserving its whole contribution."""
        if owner in self.modules:
            raise ValueError('Module already registered: ' + owner)
        contribution = OperationRegistry()
        register(contribution)
        specs = list(contribution._operations.values())
        self.replace_owned(owner, specs)
        self.register_module(owner, **metadata)
        self.compatibility_adapters[owner] = (specs, dict(self.modules[owner]))

    def restore_compatibility_adapter(self, owner):
        specs, metadata = self.compatibility_adapters[owner]
        self.replace_owned(owner, specs)
        self.modules[owner] = dict(metadata)

    def replace_owned(self, owner, specs):
        """Validate a complete contribution before atomically publishing its operations."""
        specs = list(specs)
        names = [spec.name for spec in specs]
        owned = getattr(self, '_owned', {})
        previous = owned.get(owner, set())
        if len(names) != len(set(names)) or any(
            spec.kind not in {'query', 'execute'}
            or (spec.name in self._operations and spec.name not in previous)
            for spec in specs
        ):
            raise ValueError('Invalid or conflicting module operations')
        replacement = {k: v for k, v in self._operations.items() if k not in previous}
        replacement.update({spec.name: spec for spec in specs})
        self._operations = replacement
        self._owned = {**owned, owner: set(names)}

    def describe(self, operation=None):
        refresh = getattr(self, "refresh_modules", None)
        if refresh:
            refresh()
        if operation is None:
            return {
                "operations": {
                    kind: sorted(
                        s.name for s in self._operations.values() if s.kind == kind
                    )
                    for kind in ("query", "execute")
                }
            }
        if operation not in self._operations:
            raise ValueError(f"Unknown operation: {operation}; use describe")
        spec = self._operations[operation]
        schema = spec.arguments_schema
        return {
            "operation": spec.name,
            "kind": spec.kind,
            "description": spec.description,
            "arguments_schema": schema.model_json_schema()
            if hasattr(schema, "model_json_schema")
            else schema,
        }

    def dispatch(self, kind, operation, arguments=None, context=None):
        from .storage import StorageLayout
        from pathlib import Path

        root = getattr(context, "root", None)
        # Refresh may stop a stale child or wait for its Core calls. It must run
        # before any root guard, including when an operation was just removed.
        refresh = getattr(self, "refresh_modules", None)
        if refresh:
            refresh()
        while True:
            candidate = self._operations.get(operation)
            guard = (
                StorageLayout(root).guard()
                if root and Path(root).exists() and (candidate is None or candidate.guard_root)
                else nullcontext()
            )
            with guard:
                if self._operations.get(operation) is not candidate:
                    # A replacement may have a different root-admission policy.
                    # Release the old guard before dispatching the new handler.
                    continue
                if candidate is None:
                    raise ValueError(f"Unknown operation: {operation}; use describe")
                spec = candidate
                if kind != spec.kind:
                    raise ValueError(f"Operation {operation} requires {spec.kind}")
                arguments = {} if arguments is None else arguments
                schema = spec.arguments_schema
                if hasattr(schema, "model_validate"):
                    arguments = schema.model_validate(arguments).model_dump()
                else:
                    from jsonschema import Draft202012Validator
                    Draft202012Validator(schema).validate(arguments)
                return self._invoke(spec, arguments, context)

    def _invoke(self, spec, arguments, context):
        operation = spec.name
        import time

        started = time.monotonic()
        root = getattr(context, "root", None)
        observed = self.journal is not None and (
            root is None
            or __import__("pathlib").Path(root).exists()
            or spec.kind == "execute"
        )
        ident = self.journal.begin(context, operation, arguments) if observed else None
        activity_id = object()
        if operation not in {"core.status", "core.settings", "core.settings_preview"}:
            with self._activity_lock:
                self.active_operations[activity_id] = {
                    "operation": operation,
                    "started": started,
                }
        try:
            with (
                spec.observer(context, operation, arguments)
                if spec.observer
                else nullcontext()
            ):
                result = spec.handler(context, **arguments)
        except Exception as exc:
            if observed:
                self.journal.finish(
                    ident, error=exc, duration=time.monotonic() - started
                )
            raise
        finally:
            with self._activity_lock:
                self.active_operations.pop(activity_id, None)
        if observed:
            search_recorded = self.journal.finish(
                ident, result=result, duration=time.monotonic() - started
            )
            if search_recorded:
                result = {**result, "search_event_id": ident}
        return result
