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
        from .core.documents.instructions import InstructionLibrary

        self.instructions = InstructionLibrary(self.layout, self.index)
        from .core.module_storage import ModuleStorage
        self.module_storage = ModuleStorage(self.layout)
        self.services = RootServices(self.layout, self.resources, self.registry)
        self._register_core()
        if discover:
            for entry in metadata.entry_points(group="contextopus.modules"):
                before = dict(self.registry._operations), dict(self.registry.modules)
                try:
                    entry.load()(self)
                except Exception as exc:
                    self.registry._operations, self.registry.modules = before
                    self.registry.register_module(entry.name, available=False,
                                                  state="error", error=str(exc))
        from .core.module_management import ModuleManager
        self.module_manager = ModuleManager(self)
        self._operation("core.modules", "query", self.module_manager.discover)
        for action in ("prepare", "enable", "disable"):
            self._operation("core.module_" + action, "execute", getattr(self.module_manager, action), {"module": (str, ...)})
        self._operation("core.module_source_plan", "query", self.module_manager.source_plan,
                        {"module": (str, ...), "source": (str, ...)})
        self._operation("core.module_install", "execute", self.module_manager.install,
                        {"module": (str, ...), "source": (str | None, None), "source_revision": (str | None, None)})
        self._operation("core.module_update", "execute", self.module_manager.update, {"module": (str, ...), "source": (str, ...)})
        self._refresh_algorithms()
        self._register_search_tools()

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
                guard_root=not (name.startswith("core.relocation_") or name.startswith("core.module_")
                    or name in {"core.instructions_list", "core.instructions_read", "core.instructions_resolve", "core.instructions_search", "core.library"}),
            )
        )

    def _register_core(self):
        from .core.documents.library import browse_instructions
        self._operation("core.library", "query",
                        lambda **kw: browse_instructions(self.instructions, **kw),
                        {"action": (str, ...), "collection": (str, ""),
                         "query": (str, ""), "mode": (str, "text"), "type": (str, ""),
                         "offset": (int, 0), "limit": (int, 40), "id": (str, "")})
        self._operation("core.instructions_list", "query", self.instructions.list)
        self._operation("core.instructions_read", "query", self.instructions.read,
                        {"reference": (str, ...)})
        self._operation("core.instructions_resolve", "query", self.instructions.resolve,
                        {"references": (list[str], ...)})
        self._operation("core.instructions_save", "execute", self.instructions.save,
                        {"path": (str, ...), "metadata": (dict, ...), "content": (str, ...),
                         "expected_revision": (str | None, None)})
        self._operation("core.instructions_reconcile", "execute", self.instructions.reconcile)
        self._operation("core.instructions_search", "query", self.instructions.search,
                        {"query": (str, ...), "limit": (int | None, None),
                         "selection": (dict | None, None), "output": (str, "materials")})
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
                "fields": (list[str] | None, None),
                "agent": (str | None, None),
                "agent_model": (str | None, None),
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

    def settings(self, module=None, context=None, request=None, fields=None, agent=None, agent_model=None):
        if fields is None:
            self._refresh_algorithms()
        return self.services._settings.snapshot(module, context, request, fields=fields, agent=agent, agent_model=agent_model)

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

        path = self.layout.rag / "active.json"
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
            result["setup"] = self.module_manager.run_hooks('setup')
        return result

    def apply_profile(self, config, chunking):
        owners = sum(len(host.hooks.get('apply_profile', []))
                     for host in self.module_manager.contributions.values())
        if owners > 1:
            raise ValueError('Multiple modules contribute profile rebuilding; select one owner before changing the profile')
        results = self.module_manager.run_hooks('apply_profile', config, chunking)
        applied = [result for values in results.values() for result in values if result is not None]
        if len(applied) > 1:
            raise ValueError('Multiple modules attempted to own profile rebuilding')
        if applied:
            return applied[0]
        active = self.active_profile()
        if active:
            from .core.rag import rebuild_profile

            self.index._generic_table()
            # Core owns both algorithm descriptions and shared instruction files.
            # Other module sources still require their registered rebuild owner.
            derivative = "module = 'core' AND collection IN ('search_algorithm', 'instructions')"
            if self.index.table.count_rows(f"module IS NULL OR collection IS NULL OR NOT ({derivative})"):
                raise ValueError(
                    "Profile switch requires module source adapters for existing documents"
                )
            instruction_rows = self.index.table.count_rows("module = 'core' AND collection = 'instructions'")
            if instruction_rows and not self.instructions.root.is_dir():
                raise ValueError("Instruction source directory is unavailable; cannot rebuild its index")
            instruction_snapshot = self.instructions._snapshot()

            def validate_instructions():
                if self.instructions._snapshot() != instruction_snapshot:
                    raise ValueError("Instructions changed during profile rebuild; retry")

            result = rebuild_profile(
                self.index,
                previous=active,
                config=config,
                search=active["search"],
                chunking=chunking,
                documents=instruction_snapshot.documents,
                validate_snapshot=validate_instructions,
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

        path = self.layout.rag / "active.json"
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
            or (next(iter(self.index.source_adapters))
                if self.context.workspace and len(self.index.source_adapters) == 1 else None)
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

    def _procedure_directory(self, module=None):
        """Discover help without invoking module providers or loading their bodies."""
        rows = {}
        for name, (owner, provider) in self.module_manager.procedures.items():
            if module is None or owner == module:
                rows[name] = {"name": name, "description": "Registered procedure: " + name}
        modules = sorted(self.module_manager.loaded)
        for owner in modules:
            if module is not None and owner != module:
                continue
            base = self.module_manager.sources(owner, "procedures")
            if not base.is_dir():
                continue
            for candidate in sorted(base.rglob("*.md")):
                relative = candidate.relative_to(base)
                if any(part.startswith('.') for part in relative.parts):
                    continue
                path = self.module_manager._inside(base, str(relative))
                name = owner + "/" + relative.with_suffix("").as_posix()
                with path.open(encoding="utf-8") as stream:
                    heading = next((line.strip().lstrip('#').strip() for line in stream
                                    if line.startswith('# ')), name)
                rows.setdefault(name, {"name": name, "description": heading})
        if module is None:
            base = package_resources.files("contextopus").joinpath("resources", "procedures")
            def collect(directory, prefix=""):
                for path in directory.iterdir():
                    if path.name.startswith('.'):
                        continue
                    if path.is_dir():
                        collect(path, prefix + path.name + "/")
                    elif path.name.endswith('.md'):
                        name = prefix + path.name[:-3]
                        heading = next((line.lstrip('#').strip() for line in
                                        path.read_text(encoding="utf-8").splitlines()
                                        if line.startswith('# ')), name)
                        rows.setdefault(name, {"name": name, "description": heading})
            collect(base)
        return {
            "procedures": [rows[key] for key in sorted(rows)],
            "modules": modules if module is None else [module],
            "instruction": "This is a directory, not an action procedure. Before making changes, "
                "fetch and read the applicable procedure with guide(procedure=<exact name>). "
                "An operation signature does not replace the procedure. Do not proceed with "
                "changes until the applicable procedure has been obtained.",
        }

    def procedure(self, name):
        from .core.procedure_response import enrich_procedure
        result = self._procedure_text(name)
        return enrich_procedure(result, self.registry, self.normalize_operation)

    def _procedure_text(self, name):
        parts = name.split("/")
        if any(not p or p in {".", ".."} or "\\" in p for p in parts):
            raise ValueError("Invalid procedure name")
        self.module_manager.refresh()
        if name in self.module_manager.procedures:
            return self.module_manager.procedures[name][1]()
        if name in self.module_manager.loaded:
            return {"name": name, "status": "directory", **self._procedure_directory(name)}
        if "/" in name:
            module, relative = name.split("/", 1)
            if module in self.module_manager.loaded:
                base = self.module_manager.sources(module, "procedures")
                path = self.module_manager._inside(base, relative + ".md")
                if path.is_file():
                    return {"name": name, "content": path.read_text(encoding="utf-8")}
                return {"name": name, "status": "not_found",
                        "error": "Unknown procedure: " + name,
                        **self._procedure_directory(module)}
        if name == 'default':
            name = 'modules'
        parts = name.split("/")
        path = package_resources.files("contextopus").joinpath(
            "resources", "procedures", *parts[:-1], parts[-1] + ".md"
        )
        if not path.is_file():
            return {"name": name, "status": "not_found",
                    "error": "Unknown procedure: " + name, **self._procedure_directory()}
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
            ):
                path.mkdir(parents=True, exist_ok=True)
        self.module_manager.run_hooks('initialize')
        return {"status": "initialized", "root": str(self.layout.root),
                "setup": self.module_manager.run_hooks('setup')}

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
        from .core.module_management.lifecycle import module_lifecycle
        # Lifecycle -> runtime -> root: children finish their Core RPC before
        # relocation takes the filesystem guard and publishes the freeze.
        with module_lifecycle(self.layout.root), self.module_manager.runtime.lock:
            from .core.relocation import apply, RelocationPlans

            plan = RelocationPlans(self.layout.root).resolve(plan, plan_revision)
            self.module_manager.runtime.close()
            with self.module_manager.quiesce_contributions():
                self.module_manager.run_hooks('before_relocation')
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
        operation = self.normalize_operation(operation)
        if operation == "describe":
            selected = (arguments or {}).get("operation")
            return self.registry.describe(self.normalize_operation(selected) if selected is not None else None)
        return self.registry.dispatch("query", operation, arguments, self.context)

    def execute(self, operation, arguments=None):
        return self.registry.dispatch("execute", self.normalize_operation(operation), arguments, self.context)

    def normalize_operation(self, operation):
        self.module_manager.refresh()
        return self.module_manager.aliases.get(operation, (None, operation))[1]

    def close(self):
        failures = []
        try:
            self.module_manager.close_contributions()
        except Exception as exc:
            failures.append(exc)
        if self._owns_resources:
            try:
                self.resources.close()
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise ExceptionGroup('Application failed to close', failures)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
