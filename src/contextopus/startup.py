"""Application assembly: explicit root/context, shared resources and module registry."""

from dataclasses import dataclass
from importlib import metadata, resources as package_resources
from pathlib import Path
from pydantic import ConfigDict, create_model
from .core.operations import OperationRegistry, OperationSpec
from .core.resources import ProcessResources
from .core.storage import StorageLayout
from .core.monitoring import RootServices


@dataclass(frozen=True)
class RequestContext:
    root: Path
    workspace: str | None = None


class Application:
    def __init__(self, root, context=None, *, resources=None, discover=True):
        self.layout = StorageLayout.resolve(root)
        self.context = RequestContext(self.layout.root, context)
        self.resources = resources or ProcessResources()
        self._owns_resources = resources is None
        from .core.analytics import OperationJournal

        self.journal = OperationJournal(self.layout)
        self.registry = OperationRegistry(self.journal)
        from .core.rag import RagIndex

        self.index = RagIndex(self.layout, self.resources)
        from .modules.workspace.source import WorkspaceEligibility

        self.index.register_source(
            "workspace", WorkspaceEligibility(self.layout, self.resources.acquire)
        )
        self.services = RootServices(self.layout, self.resources, self.registry)
        self._register_core()
        from .modules.workspace.operations import register_operations

        register_operations(self.registry, provider_factory=self.resources.acquire)
        from .modules.workspace.discovery import register as register_discovery
        register_discovery(self)
        self.registry.register_module(
            "workspace", available=True, state="available", open_tui=None
        )
        if discover:
            for entry in metadata.entry_points(group="contextopus.modules"):
                before = dict(self.registry._operations), dict(self.registry.modules)
                try:
                    entry.load()(self)
                except Exception as exc:
                    self.registry._operations, self.registry.modules = before
                    self.registry.register_module(entry.name, available=False,
                                                  state="error", error=str(exc))
        try:
            from .modules.session_search import SessionSearch

            module = SessionSearch()
            if "session_search" not in self.registry.modules and module.available():
                module.register(self.registry)
                self.registry.register_module(
                    "session_search",
                    available=True,
                    state="available",
                    open_tui="session_search.open_tui",
                )
        except ImportError:
            pass

        from .core.module_management import ModuleManager
        self.module_manager = ModuleManager(self)
        self._operation("core.modules", "query", self.module_manager.discover)
        for action in ("prepare", "enable", "disable"):
            self._operation("core.module_" + action, "execute", getattr(self.module_manager, action), {"module": (str, ...)})
        self._operation("core.module_update", "execute", self.module_manager.update, {"module": (str, ...), "source": (str, ...)})
        self._refresh_algorithms()
        self._register_search_tools()
        from .modules.workspace.base_context import register as register_base
        register_base(self)

    def _operation(self, name, kind, fn, fields=None):
        model = create_model(
            name.replace(".", "_") + "_arguments",
            __config__=ConfigDict(extra="forbid", strict=True),
            **(fields or {}),
        )
        self.registry.register(
            OperationSpec(
                name,
                kind,
                model,
                lambda request_context, **kw: fn(**kw),
                description=fn.__doc__ or name.replace("_", " ").replace(".", " "),
                guard_root=not name.startswith("core.relocation_"),
            )
        )

    def _register_core(self):
        self._operation("core.status", "query", self.services.status)
        self._operation(
            "core.search",
            "query",
            self.search,
            {
                "query": (str, ...),
                "module": (str | None, None),
                "collection": (str | None, None),
                "object_type": (str | None, None),
                "status": (str | None, None),
                "include_archived": (bool | None, None),
                "distance": (float | None, None),
                "limit": (int | None, None),
                "selection": (dict | None, None),
                "output": (str, "materials"),
                "candidate_limit": (int | None, None),
                "purpose": (str | None, None),
                "task_id": (str | None, None),
            },
        )
        self._operation("core.model_hardware", "query", self.model_hardware)
        self._operation(
            "core.model_plan",
            "query",
            self.model_plan,
            {
                "config": (dict | None, None),
                "chunking": (dict | None, None),
                "device": (str, "auto"),
            },
        )
        self._operation(
            "core.model_apply", "execute", self.model_apply, {"plan": (dict, ...)}
        )
        self._operation(
            "core.settings",
            "query",
            self.settings,
            {
                "module": (str | None, None),
                "context": (str | None, None),
                "request": (dict | None, None),
            },
        )
        self._operation(
            "core.settings_preview",
            "query",
            self.settings_preview,
            {
                "changes": (dict, ...),
                "module": (str | None, None),
                "context": (str | None, None),
                "request_only": (bool, False),
            },
        )
        self._operation(
            "core.settings_apply",
            "execute",
            self.settings_apply,
            {"preview_revision": (str, ...)},
        )
        self._operation("procedure", "query", self.procedure, {"name": (str, ...)})
        self._operation("core.init", "execute", self.initialize)
        self._operation("core.doctor", "query", self.doctor)
        self._operation("core.index_upgrade", "execute", self.index_upgrade)
        self._operation(
            "core.relocation_plan",
            "query",
            self.relocation_plan,
            {"destination": (str, ...), "include_manifest": (bool, False)},
        )
        self._operation(
            "core.relocation_apply",
            "execute",
            self.relocation_apply,
            {"plan": (dict | None, None), "plan_revision": (str | None, None)},
        )
        self._operation(
            "core.relocation_rollback",
            "execute",
            self.relocation_rollback,
            {"plan": (dict | None, None), "plan_revision": (str | None, None)},
        )

    def settings(self, module=None, context=None, request=None):
        self._refresh_algorithms()
        return self.services._settings.snapshot(module, context, request)

    def settings_preview(self, changes, module=None, context=None, request_only=False):
        self._refresh_algorithms()
        return self.services._settings.preview(changes, module, context, request_only)

    def settings_apply(self, preview_revision):
        self._refresh_algorithms()
        return self.services.apply_settings(preview_revision)

    def _refresh_algorithms(self):
        from .core.filtering import registry_for_layout
        registry = registry_for_layout(self.layout)
        self.index.algorithm_registry = registry
        self.services._settings.registry = registry

    def _register_search_tools(self):
        from .core.search_history import SearchHistory
        history = SearchHistory(self.journal, self.index.algorithm_registry)
        self._operation("core.search_events", "query", history.query, {
            "since": (str | None, None), "until": (str | None, None),
            "context": (str | None, None), "task_id": (str | None, None),
            "instructions_revision": (str | None, None), "offset": (int, 0), "limit": (int, 50)})
        self._operation("core.search_event", "query", history.read, {"event_id": (str, ...)})
        def replay(event_id, selection, relevant_keys=None):
            self._refresh_algorithms()
            return SearchHistory(self.journal, self.index.algorithm_registry).replay(event_id, selection, relevant_keys)
        self._operation("core.search_replay", "query", replay, {
            "event_id": (str, ...), "selection": (dict, ...), "relevant_keys": (list | None, None)})

        def catalog(query=None, semantic=False, limit=20):
            from .core.filtering import AlgorithmCatalog
            self._refresh_algorithms()
            return AlgorithmCatalog(self.index.algorithm_registry, self.index).search(query, limit, semantic)
        def refresh():
            from .core.filtering import AlgorithmCatalog
            self._refresh_algorithms()
            return AlgorithmCatalog(self.index.algorithm_registry, self.index).refresh()
        self._operation("core.algorithms", "query", catalog, {
            "query": (str | None, None), "semantic": (bool, False), "limit": (int, 20)})
        self._operation("core.algorithms_refresh", "execute", refresh)
        self._operation("core.index_stats", "query", self.index_stats, {
            "module": (str | None, None), "collection": (str | None, None)})

    def index_stats(self, module=None, collection=None):
        """Count stored fragments and unique objects without retrieving vectors."""
        table = self.index._generic_table()
        if table is None:
            return {"fragments": 0, "objects": 0, "module": module, "collection": collection}
        clauses = [name + "=" + self.index._quote(value) for name, value in
                   (("module", module), ("collection", collection)) if value is not None]
        rows = self.index.read_rows(table, ["module", "collection", "object_id"], " AND ".join(clauses) or None)
        return {"fragments": len(rows), "objects": len({(r["module"], r["collection"], r["object_id"]) for r in rows}),
                "module": module, "collection": collection, "basis": "stored_index_rows"}

    def active_profile(self):
        import json

        path = self.layout.workspace_rag / "active.json"
        return json.loads(path.read_text()) if path.is_file() else None

    def model_hardware(self):
        from .core.model_setup import detect_hardware

        return detect_hardware()

    def model_plan(self, config=None, chunking=None, device="auto"):
        from .core.model_setup import plan_embedding_setup

        return plan_embedding_setup(
            config, chunking, device, previous=self.active_profile()
        )

    def model_apply(self, plan):
        from .core.model_setup import apply

        result = apply(
            plan, apply_profile=self.apply_profile, read_active=self.active_profile
        )
        if result.get("status") == "ok":
            from .modules.workspace.base_context import prepare_setup
            result["setup"] = prepare_setup(self)
        return result

    def apply_profile(self, config, chunking):
        from .modules.workspace.server import runtime

        contexts = self.layout.workspace_base
        names = (
            [
                p.name
                for p in sorted(contexts.iterdir())
                if not p.name.startswith(".")
                and p.is_dir()
                and (p / "knowledge").is_dir()
            ]
            if contexts.is_dir()
            else []
        )
        if names:
            selected = (
                self.context.workspace if self.context.workspace in names else names[0]
            )
            engine = runtime(
                str(self.layout.root), selected, provider_factory=self.resources.acquire
            ).engine
            from .modules.workspace.runtime import SearchConfig

            search = (
                self.active_profile()["search"]
                if self.active_profile()
                else vars(SearchConfig())
            )
            return engine.switch_embeddings(config, search, chunking)
        active = self.active_profile()
        if active:
            from .core.rag import rebuild_profile

            self.index._generic_table()
            # A failed docs delivery may leave only rebuildable algorithm cards.
            # Preserve the refusal for every other module's source documents.
            derivative = "module = 'core' AND collection = 'search_algorithm'"
            if self.index.table.count_rows(f"module IS NULL OR collection IS NULL OR NOT ({derivative})"):
                raise ValueError(
                    "Profile switch requires module source adapters for existing documents"
                )
            result = rebuild_profile(
                self.index,
                previous=active,
                config=config,
                search=active["search"],
                chunking=chunking,
                documents=[],
                validate_snapshot=lambda: None,
                read_active=self.active_profile,
                write_active=self.write_active_profile,
                factory=self.resources.acquire,
            )
            provider = result.pop("_provider", None)
            if provider is not None:
                provider.close()
            self.index._provider = None
            self.index.embeddings = self.index.chunking = None
            return result
        # Initial setup verifies the actual adapter before publishing a pointer.
        from .core.rag import RagIndex

        provider = self.resources.acquire(config)
        try:
            RagIndex.vectors(
                provider,
                ["Embedding connection verification"],
                config["profile"]["dimensions"],
                "document",
            )
            self.initialize()
            self.index.embeddings, self.index.chunking = config, chunking
            self.index._generic_table(create=True)
            self.index._provider = provider
        except Exception:
            provider.close()
            raise
        return {"status": "ok", "active": self.active_profile(), "reembedded": False}

    def write_active_profile(self, active):
        import json, os
        from .core.storage import sync_directory

        path = self.layout.workspace_rag / "active.json"
        temporary = path.with_suffix(".tmp")
        with temporary.open("w") as stream:
            json.dump(active, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)

    def search(self, query, **options):
        self._refresh_algorithms()
        root_values = self.services.settings()["values"]
        selected_module = (
            options.get("module")
            or root_values.get("module")
            or ("workspace" if self.context.workspace else None)
        )
        selected_collection = (
            options.get("collection")
            or self.context.workspace
            or root_values.get("context")
        )
        snapshot = self.services._settings.snapshot(
            module=selected_module,
            context=selected_collection if selected_module else None,
        )
        values = snapshot["values"]
        defaults = {
            "module": selected_module or values.get("module"),
            "collection": selected_collection or values.get("context"),
            "object_type": values.get("object_type"),
            "include_archived": values.get("include_archived", False),
        }
        defaults.update({k: v for k, v in options.items() if v is not None})
        result = self.index.search_detailed(query, **defaults)
        parameters = result["diagnostics"]["effective_settings"]["parameters"]
        effective = {**defaults, "limit": next((parameters[name] for name in
                     ("N", "page_size", "top_k") if name in parameters), None)}
        return {**result, "effective": effective}

    def procedure(self, name):
        if name == "default-instructions":
            return {
                "name": name,
                "content": package_resources.files("contextopus.modules.workspace")
                .joinpath("default_instructions.md")
                .read_text(encoding="utf-8"),
            }
        if "/" in name and hasattr(self, "module_manager"):
            module, relative = name.split("/", 1)
            if module in self.module_manager.loaded:
                base = self.module_manager.sources(module, "procedures")
                path = self.module_manager._inside(base, relative + ".md")
                return {"name": name, "content": path.read_text(encoding="utf-8")}
        parts = name.split("/")
        if any(not p or p in {".", ".."} or "\\" in p for p in parts):
            raise ValueError("Invalid procedure name")
        path = package_resources.files("contextopus").joinpath(
            "resources", "procedures", *parts[:-1], parts[-1] + ".md"
        )
        return {"name": name, "content": path.read_text(encoding="utf-8")}

    def index_upgrade(self):
        if self.active_profile() is None:
            return {"status": "not_initialized", "root": str(self.layout.root)}
        self.index._generic_table(create=True)
        return {
            "status": "upgraded",
            "table": self.index.table.name,
            "columns": self.index.table.schema.names,
            "model_loaded": self.index._provider is not None,
        }

    def initialize(self):
        if (self.layout.root / ".pcw").is_dir():
            return {
                "status": "relocation_required",
                "root": str(self.layout.root),
                "next_action": "core.relocation_plan",
            }
        with self.layout.guard():
            for path in (
                self.layout.rag,
                self.layout.analytics,
                self.layout.configuration,
                self.layout.root / "modules/workspace/workspace_contexts",
                self.layout.root / "modules/workspace/control",
            ):
                path.mkdir(parents=True, exist_ok=True)
        from .modules.workspace.base_context import prepare_setup
        return {"status": "initialized", "root": str(self.layout.root),
                "setup": prepare_setup(self)}

    def doctor(self):
        return {
            "root": str(self.layout.root),
            "exists": self.layout.root.is_dir(),
            "frozen": (self.layout.root / ".contextopus-freeze.json").exists(),
            "layout": "legacy"
            if (self.layout.root / ".pcw").exists()
            else "contextopus",
            "model_loaded": bool(self.resources.providers._entries),
        }

    def relocation_plan(self, destination, include_manifest=False):
        from .core.relocation import RelocationPlans

        return RelocationPlans(self.layout.root).review(destination, include_manifest)

    def relocation_apply(self, plan=None, plan_revision=None):
        from .core.relocation import apply, RelocationPlans

        plan = RelocationPlans(self.layout.root).resolve(plan, plan_revision)
        from .modules.workspace.server import _runtimes, _cache_lock

        with _cache_lock:
            for key in [k for k in _runtimes if k[0] == str(self.layout.root)]:
                _runtimes.pop(key).close()
        self.index.table = self.index.db = None
        result = apply(plan)
        self.journal.rebind(StorageLayout(result["destination"]))
        return result

    def relocation_rollback(self, plan=None, plan_revision=None):
        from .core.relocation import rollback, RelocationPlans

        plan = RelocationPlans(self.layout.root).resolve(plan, plan_revision)
        result = rollback(plan)
        return result

    def query(self, operation, arguments=None):
        if operation == "describe":
            return self.registry.describe((arguments or {}).get("operation"))
        return self.registry.dispatch("query", operation, arguments, self.context)

    def execute(self, operation, arguments=None):
        return self.registry.dispatch("execute", operation, arguments, self.context)

    def close(self):
        if self._owns_resources:
            from .modules.workspace.server import _runtimes, _cache_lock

            with _cache_lock:
                selected = [
                    k
                    for k, runtime in _runtimes.items()
                    if k[0] == str(self.context.root)
                    and runtime.engine._factory == self.resources.acquire
                ]
                for key in selected:
                    _runtimes.pop(key).close()
            self.resources.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
