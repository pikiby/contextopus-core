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
        self.active_operations = {}
        import threading

        self._activity_lock = threading.RLock()

    def register_module(self, name, **metadata):
        self.modules[name] = {"name": name, **metadata}

    def register(self, spec):
        if spec.kind not in {"query", "execute"} or spec.name in self._operations:
            raise ValueError(f"Invalid or duplicate operation: {spec.name}")
        self._operations[spec.name] = spec

    def describe(self, operation=None):
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
        if operation not in self._operations:
            raise ValueError(f"Unknown operation: {operation}; use describe")
        spec = self._operations[operation]
        if kind != spec.kind:
            raise ValueError(f"Operation {operation} requires {spec.kind}")
        arguments = {} if arguments is None else arguments
        schema = spec.arguments_schema
        if hasattr(schema, "model_validate"):
            arguments = schema.model_validate(arguments).model_dump()
        else:
            from jsonschema import Draft202012Validator

            Draft202012Validator(schema).validate(arguments)
        from .storage import StorageLayout
        from pathlib import Path

        root = getattr(context, "root", None)
        guard = (
            StorageLayout(root).guard()
            if root and Path(root).exists() and spec.guard_root
            else nullcontext()
        )
        with guard:
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
            self.journal.finish(
                ident, result=result, duration=time.monotonic() - started
            )
        return result
