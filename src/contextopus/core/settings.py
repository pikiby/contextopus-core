"""Explicit root configuration with revision-bound previews."""

import hashlib
import json

WORKSPACE_POLICY_DEFAULTS = {
    "allow_implicit_updates": False,
    "knowledge_approval_required": True,
    "instructions_approval_required": True,
    "git_history_enabled": False,
    "material_max_tokens": None,
    "create_required_sources": False,
}
WORKSPACE_SETTINGS = {
    **WORKSPACE_POLICY_DEFAULTS,
    "reread_instructions": False,
    "instruction_profiles": [],
}
WORKSPACE_CREATION_DEFAULTS = {
    **WORKSPACE_POLICY_DEFAULTS,
    "knowledge_approval_required": False,
    "git_history_enabled": True,
    "material_max_tokens": 1024,
}
PROTECTED_FIELDS = frozenset(WORKSPACE_SETTINGS)

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
    "selection": {"algorithm": "distance_jump", "parameters": {}},
    **WORKSPACE_SETTINGS,
}


class Settings:
    def __init__(self, layout, registry=None):
        self.layout = layout
        self.registry = registry
        self.path = layout.configuration / "settings.json"
        self._previews = {}

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

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

    def _layers(self, module=None, context=None):
        self._scope_path(module, context)
        layers = [("root", self._read())]
        if module is not None:
            for origin, selected_context in (("module", None), ("context", context)):
                if origin == "context" and context is None:
                    continue
                path = self._scope_path(module, selected_context)
                layers.append((origin, json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}))
        return layers

    def workspace_snapshot(self, module="workspace", context=None, fields=None,
                           agent=None, agent_model=None):
        """Read policies without opening rules, the vector index or algorithm modules."""
        selected = list(WORKSPACE_SETTINGS) if fields is None else fields
        if (not isinstance(selected, list) or any(key not in WORKSPACE_SETTINGS for key in selected)):
            raise ValueError("Unknown workspace settings fields")
        for value in (agent, agent_model):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Explicit agent/model selectors must be nonempty strings")
        layers = self._layers(module, context)
        effective = json.loads(json.dumps(WORKSPACE_SETTINGS))
        sources = {key: "default" for key in effective}
        for origin, layer in layers:
            values = {key: value for key, value in layer.items() if key in WORKSPACE_SETTINGS}
            self._validate_changes(values)
            effective.update(values)
            sources.update({key: origin + ".configuration" for key in values})
        matches = []
        for profile in effective["instruction_profiles"]:
            if (("agent" not in profile or profile["agent"] == agent)
                    and ("model" not in profile or profile["model"] == agent_model)):
                matches.append((int("agent" in profile) + int("model" in profile), profile))
        if matches:
            specificity = max(score for score, _ in matches)
            winners = [profile for score, profile in matches if score == specificity]
            if len(winners) != 1:
                raise ValueError("Ambiguous instruction profiles; select an explicit agent/model pair")
            effective["reread_instructions"] = winners[0]["reread_instructions"]
            sources["reread_instructions"] = sources["instruction_profiles"] + ".profile"
        policy_layers = [(origin, {key: value for key, value in layer.items() if key in WORKSPACE_SETTINGS})
                         for origin, layer in layers]
        revision = hashlib.sha256(json.dumps([policy_layers, module, context], sort_keys=True).encode()).hexdigest()
        return {"values": {key: effective[key] for key in selected},
                "sources": {key: sources[key] for key in selected}, "revision": revision,
                "selected_scope": {"module": module, "context": context},
                "profile": {"agent": agent, "model": agent_model}}

    def snapshot(self, module=None, context=None, request=None, fields=None,
                 agent=None, agent_model=None):
        if fields is not None and (not isinstance(fields, list) or any(key not in DEFAULTS for key in fields)):
            raise ValueError("Unknown configuration fields")
        if fields is not None and set(fields) <= PROTECTED_FIELDS:
            if request and set(request) & PROTECTED_FIELDS:
                raise ValueError("Workspace policy request overrides are forbidden")
            return self.workspace_snapshot(module, context, fields, agent, agent_model)
        if request and set(request) & PROTECTED_FIELDS:
            raise ValueError("Workspace policy request overrides are forbidden")
        self._scope_path(module, context)
        root = self._read()
        active_path = self.layout.workspace_rag / "active.json"
        active = json.loads(active_path.read_text(encoding="utf-8")) if active_path.is_file() else None
        effective = json.loads(json.dumps(DEFAULTS))
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
                (scope, json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})
            )
        from .filtering import registry_for_layout
        registry = self.registry or registry_for_layout(self.layout)
        selection = {"algorithm": "distance_jump", "parameters": {}}
        selection_sources = {"algorithm": "default"}
        if active:
            selection["parameters"] = {k:v for k,v in active["search"].items() if k in ("N", "d_max", "min_jump", "multiplier")}
            selection_sources.update({"parameters." + k: "root.active_index" for k in selection["parameters"]})
        def merge_selection(layer, origin):
            nonlocal selection
            value = layer.get("selection")
            if value is not None:
                if not isinstance(value, dict):
                    raise ValueError("selection must be an object")
                algorithm = value.get("algorithm", selection["algorithm"])
                if algorithm != selection["algorithm"]:
                    selection = {"algorithm": algorithm, "parameters": {}}
                    selection_sources.clear()
                if "algorithm" in value:
                    selection_sources["algorithm"] = origin
                selection["parameters"].update(value.get("parameters", {}))
                selection_sources.update({"parameters." + k: origin for k in value.get("parameters", {})})
                selection["algorithm"] = algorithm
                if registry.contains(selection["algorithm"]):
                    registry.resolve(selection)
            defaults = registry.resolve(selection)[1]["defaults"] if registry.contains(selection["algorithm"]) else {}
            for old, new in (("searchN", "N"), ("distance", "d_max")):
                if old in layer and layer[old] is not None and new not in (value or {}).get("parameters", {}) and new in defaults:
                    selection["parameters"][new] = layer[old]
                    selection_sources["parameters." + new] = origin + ".legacy"
        for scope, layer in layers:
            self._validate_changes(layer, allow_unavailable=True)
            merge_selection(layer, scope + ".configuration")
            effective.update(layer)
            sources.update({key: scope + ".configuration" for key in layer})
        configured = dict(effective)
        if request:
            self._validate_changes(request)
            merge_selection(request, "request")
            effective.update(request)
            sources.update({key: "request" for key in request})
        if registry.contains(selection["algorithm"]):
            effective["selection"] = registry.resolve(selection)[0]
            selection_status = {"valid":True, "algorithm":selection["algorithm"]}
        else:
            effective["selection"] = selection
            selection_status = {"valid":False, "code":"algorithm_unavailable",
                "algorithm":selection["algorithm"], "next_action":"core.settings_preview",
                "message":"The saved algorithm is unavailable. Enable its prepared module again or preview/apply a replacement selection at the configured scope. A builtin request override can search without saving a replacement."}
        for key in effective["selection"]["parameters"]:
            selection_sources.setdefault("parameters." + key, "algorithm.default")
        sources.update({"selection." + key: value for key, value in selection_sources.items()})
        policy = self.workspace_snapshot(module, context, agent=agent, agent_model=agent_model)
        effective.update(policy["values"])
        sources.update(policy["sources"])
        if active:
            current = {
                "provider": active["config"]["provider"]["type"],
                "model": active["config"]["profile"]["model"],
                "chunk_size": active["chunking"]["chunk_size_tokens"],
            }
            effective.update(current)
            sources.update({key: "root.active_index" for key in current})
        encoded = json.dumps(
            [layers, active, request, {"module": module, "context": context,
                                      "agent": agent, "agent_model": agent_model}, registry.catalog()],
            sort_keys=True,
        ).encode()
        result = {
            "values": effective,
            "selection_status": selection_status,
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
        if fields is not None:
            return {"values": {key: effective[key] for key in fields},
                    "sources": {key: sources[key] for key in fields},
                    "revision": result["revision"], "selected_scope": result["selected_scope"]}
        return result

    def _validate_changes(self, changes, allow_unavailable=False):
        if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
            raise ValueError("Unknown configuration fields")
        for key in PROTECTED_FIELDS - {"material_max_tokens", "instruction_profiles"}:
            if key in changes and type(changes[key]) is not bool:
                raise ValueError(f"{key} must be boolean")
        if "material_max_tokens" in changes:
            value = changes["material_max_tokens"]
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError("material_max_tokens must be a positive integer or null")
        if "instruction_profiles" in changes:
            profiles = changes["instruction_profiles"]
            if not isinstance(profiles, list):
                raise ValueError("instruction_profiles must be a list")
            seen = set()
            for profile in profiles:
                if (not isinstance(profile, dict) or set(profile) - {"agent", "model", "reread_instructions"}
                        or not (set(profile) & {"agent", "model"})
                        or type(profile.get("reread_instructions")) is not bool
                        or any(not isinstance(profile[key], str) or not profile[key].strip()
                               for key in ("agent", "model") if key in profile)):
                    raise ValueError("An instruction profile needs explicit agent/model and boolean reread_instructions")
                identity = (profile.get("agent"), profile.get("model"))
                if identity in seen:
                    raise ValueError("Duplicate instruction profile")
                seen.add(identity)
        if "selection" in changes:
            from .filtering import registry_for_layout
            value = changes['selection']
            if not isinstance(value, dict) or set(value) - {'algorithm', 'parameters'} or not isinstance(value.get('parameters', {}),dict):
                raise ValueError('selection requires algorithm and parameters')
            if 'algorithm' in value:
                if not isinstance(value['algorithm'], str) or not value['algorithm']:
                    raise ValueError('selection.algorithm must be a nonempty string')
                registry = self.registry or registry_for_layout(self.layout)
                if not allow_unavailable or registry.contains(value['algorithm']):
                    registry.resolve(value)
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
        if set(changes) & PROTECTED_FIELDS:
            raise ValueError("Use workspace.settings_preview/settings_apply for workspace policies")
        before = self.snapshot(module, context)
        revision = hashlib.sha256(
            json.dumps([before["revision"], changes, {"request_only":request_only}], sort_keys=True).encode()
        ).hexdigest()
        preview = {
            "preview_revision": revision,
            "base_revision": before["revision"],
            "changes": json.loads(json.dumps(changes)),
            "selected_scope": {"module": module, "context": context},
            "request_only": request_only,
            "effective": self.snapshot(module, context, request=changes)["values"],
            "requires_reindex": bool(
                set(changes) & {"include", "exclude", "provider", "model", "chunk_size"}
            ),
            "consequences": "Future search requests use the saved filters. Model and chunk changes require reindex. Existing data is retained; no processing is started.",
            "running_process_applied": False,
        }
        self._previews[revision] = json.loads(json.dumps(preview))
        return preview

    def apply(self, revision):
        preview = self._previews.get(revision)
        if preview is None:
            raise ValueError("Preview is absent; preview changes before applying")
        if set(preview["changes"]) & PROTECTED_FIELDS:
            raise ValueError("Use workspace.settings_apply for workspace policies")
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
            existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            saved = {**existing, **preview["changes"]}
            if 'selection' in preview['changes']:
                old = existing.get('selection', {})
                new = preview['changes']['selection']
                if new.get('algorithm', old.get('algorithm')) == old.get('algorithm'):
                    saved['selection'] = {**old, **new, 'parameters': {**old.get('parameters', {}), **new.get('parameters', {})}}
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
