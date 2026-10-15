"""Explicit root configuration with revision-bound previews."""

import hashlib
import json

DEFAULTS = {
    "include": ["**/*"],
    "exclude": [".git/**"],
    "provider": None,
    "model": None,
    "chunk_size": 512,
    "module": None,
    "context": None,
    "object_type": None,
    "include_archived": False,
    "searchN": 20,
    "distance": None,
}


class Settings:
    def __init__(self, layout):
        self.layout = layout
        self.path = layout.configuration / "settings.json"
        self._previews = {}

    def _read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _scope_path(self, module=None, context=None):
        if module is not None:
            self.layout._name(module)
        if context is not None:
            self.layout._name(context)
            if module is None:
                raise ValueError("A context setting requires a module")
        if context is not None:
            return self.layout.configuration / "contexts" / module / (context + ".json")
        if module is not None:
            return self.layout.configuration / "modules" / (module + ".json")
        return self.path

    def snapshot(self, module=None, context=None, request=None):
        self._scope_path(module, context)
        root = self._read()
        active_path = self.layout.workspace_rag / "active.json"
        active = json.loads(active_path.read_text()) if active_path.is_file() else None
        effective = dict(DEFAULTS)
        sources = {key: "default" for key in effective}
        if active:
            effective.update(
                searchN=active["search"]["N"], distance=active["search"]["d_max"]
            )
            sources.update(searchN="root.active_index", distance="root.active_index")
        layers = [("root", root)]
        for scope, selected_module, selected_context in (
            ("module", module, None),
            ("context", module, context),
        ):
            if (
                selected_module is None
                or scope == "context"
                and selected_context is None
            ):
                continue
            path = self._scope_path(selected_module, selected_context)
            layers.append(
                (scope, json.loads(path.read_text()) if path.is_file() else {})
            )
        for scope, layer in layers:
            effective.update(layer)
            sources.update({key: scope + ".configuration" for key in layer})
        configured = dict(effective)
        if request:
            self._validate_changes(request)
            effective.update(request)
            sources.update({key: "request" for key in request})
        if active:
            current = {
                "provider": active["config"]["provider"]["type"],
                "model": active["config"]["profile"]["model"],
                "chunk_size": active["chunking"]["chunk_size_tokens"],
            }
            effective.update(current)
            sources.update({key: "root.active_index" for key in current})
        encoded = json.dumps(
            [layers, active, request, {"module": module, "context": context}],
            sort_keys=True,
        ).encode()
        return {
            "values": effective,
            "scope": str(self.layout.root),
            "sources": sources,
            "selected_scope": {
                "module": module,
                "context": context,
                "request": request,
            },
            "active_embedding_config": active["config"] if active else None,
            "active_chunking": active["chunking"] if active else None,
            "pending_configuration": {
                key: configured[key]
                for key in ("provider", "model", "chunk_size")
                if configured[key] is not None and configured[key] != effective[key]
            },
            "revision": hashlib.sha256(encoded).hexdigest(),
        }

    @staticmethod
    def _validate_changes(changes):
        if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
            raise ValueError("Unknown configuration fields")
        for key in ("include", "exclude"):
            if key in changes and (
                not isinstance(changes[key], list)
                or any(not isinstance(p, str) or not p for p in changes[key])
            ):
                raise ValueError(f"{key} must be a list of nonempty patterns")
        for key in ("chunk_size", "searchN"):
            if key in changes and (type(changes[key]) is not int or changes[key] < 1):
                raise ValueError(f"{key} must be a positive integer")
        if (
            "include_archived" in changes
            and type(changes["include_archived"]) is not bool
        ):
            raise ValueError("include_archived must be boolean")
        if (
            "distance" in changes
            and changes["distance"] is not None
            and (
                type(changes["distance"]) not in (int, float)
                or not 0 <= changes["distance"] <= 2
            )
        ):
            raise ValueError("distance must be null or between 0 and 2")
        for key in ("provider", "model", "module", "context", "object_type"):
            if (
                key in changes
                and changes[key] is not None
                and not isinstance(changes[key], str)
            ):
                raise ValueError(f"{key} must be a string or null")

    def preview(self, changes, module=None, context=None, request_only=False):
        self._scope_path(module, context)
        self._validate_changes(changes)
        before = self.snapshot(module, context)
        revision = hashlib.sha256(
            json.dumps([before["revision"], changes], sort_keys=True).encode()
        ).hexdigest()
        preview = {
            "preview_revision": revision,
            "base_revision": before["revision"],
            "changes": dict(changes),
            "selected_scope": {"module": module, "context": context},
            "request_only": request_only,
            "effective": {**before["values"], **changes},
            "requires_reindex": bool(
                set(changes) & {"include", "exclude", "provider", "model", "chunk_size"}
            ),
            "consequences": "Future search requests use the saved filters. Model and chunk changes require reindex. Existing data is retained; no processing is started.",
            "running_process_applied": False,
        }
        self._previews[revision] = preview
        return preview

    def apply(self, revision):
        preview = self._previews.get(revision)
        if preview is None:
            raise ValueError("Preview is absent; preview changes before applying")
        scope = preview["selected_scope"]
        if preview["request_only"]:
            if self.snapshot(**scope)["revision"] != preview["base_revision"]:
                raise ValueError("Configuration changed; preview again")
            return {
                "saved": False,
                "request_only": True,
                "settings": self.snapshot(**scope, request=preview["changes"]),
            }
        with self.layout.guard():
            if self.snapshot(**scope)["revision"] != preview["base_revision"]:
                raise ValueError("Configuration changed; preview again")
            path = self._scope_path(**scope)
            existing = json.loads(path.read_text()) if path.is_file() else {}
            saved = {**existing, **preview["changes"]}
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(saved, indent=2) + "\n")
            temporary.replace(path)
        self._previews.clear()
        return {
            "saved": True,
            "running_process_applied": False,
            "settings": self.snapshot(**scope),
        }


def matches_location(location, settings):
    """Match source locations without opening or interpreting source files."""
    import fnmatch

    def match(pattern):
        return (
            pattern == "**/*"
            or fnmatch.fnmatchcase(location, pattern)
            or pattern.startswith("**/")
            and fnmatch.fnmatchcase(location, pattern[3:])
        )

    return any(
        match(pattern) for pattern in settings.get("include", ["**/*"])
    ) and not any(match(pattern) for pattern in settings.get("exclude", []))
