"""Parent capability tests with real temporary RAG and fake embedding models."""

import copy
import json
import os
import threading
from types import SimpleNamespace

import pytest

from contextopus.core.embeddings import default_config
from contextopus.core.module_management.core_access import ModuleCoreAccess
from contextopus.core.module_storage import ModuleStorage, ModuleStorageError
from contextopus.core.rag import RagIndex
from contextopus.core.resources import ProcessResources
from contextopus.core.storage import StorageLayout


class FakeProvider:
    def __init__(self, config):
        self.calls, self.closed = [], False
        self.started = self.finish = None

    def embed(self, texts, purpose="document"):
        self.calls.append((list(texts), purpose))
        if self.started is not None:
            self.started.set()
            assert self.finish.wait(2)
        return [[1., .5] for text in texts]

    def tokenizer(self):
        return lambda text, **kwargs: {"input_ids": [0] * (len(text.split()) + 1)}

    def close(self):
        self.closed = True


@pytest.fixture
def app(tmp_path):
    created = []

    def factory(config):
        provider = FakeProvider(config)
        created.append(provider)
        return provider

    layout = StorageLayout(tmp_path / "root")
    layout.configuration.mkdir(parents=True)
    (layout.configuration / "layout.json").write_text('{}')
    resources = ProcessResources(provider_factory=factory)
    config = default_config()
    config["profile"]["dimensions"] = 2
    index = RagIndex(layout, resources)
    index.embeddings = config
    with layout.guard():
        index._generic_table(create=True)
    storage = ModuleStorage(layout)
    package = tmp_path / "package"
    (package / "migrations").mkdir(parents=True)
    (package / "migrations/001-schema.sql").write_text('CREATE TABLE "{{module}}::items" (id INTEGER PRIMARY KEY);')
    contract = dict(engine="sqlite", schema_version=1, migrations="migrations", compatible_versions=dict(min=1, max=1))
    plan = storage.prepare("alpha", contract, package)
    storage.apply("alpha", contract, package, plan["revision"])
    value = SimpleNamespace(layout=layout, resources=resources, index=index,
                            module_storage=storage, created=created, config=config)
    yield value
    resources.close()


def access(app, module="alpha", **kwargs):
    return ModuleCoreAccess(app, module, storage_declared=True, rag_declared=True, **kwargs)


def document(module=None, ident="1"):
    key = dict(collection="blocks", id=ident)
    if module is not None:
        key["module"] = module
    return dict(key=key, revision="hash", text="hello source", location="module://blocks/" + ident,
                metadata=dict(type="block"))


def test_child_metadata_refresh_retains_vector_and_checks_revision(app):
    writer, reader = access(app), access(app, kind="query")
    try:
        item = document()
        writer.call("rag.put_vector", {"document": item, "vector": [1., .5], "profile": app.config})
        moved = {**item, "location": "profiles/renamed.md", "metadata": {"type": "profile", "description": "Changed"}}
        writer.call("rag.update_document", {"document": moved})
        rows = app.index.read_rows(app.index.table)
        assert rows[0]["path"] == "profiles/renamed.md"
        assert rows[0]["vector"] == [1., .5]
        with pytest.raises(ValueError, match="reindex"):
            writer.call("rag.update_document", {"document": {**moved, "revision": "stale"}})
        with pytest.raises(PermissionError):
            reader.call("rag.update_document", {"document": moved})
        with pytest.raises(PermissionError):
            writer.call("rag.update_document", {"document": document(module="other")})
    finally:
        writer.close()
        reader.close()


def test_child_instruction_chain_and_revision_checks(app):
    writer, reader = access(app), access(app, kind="query")
    try:
        base = writer.call("instructions.save", {"path": "base.md", "metadata": {"id": "base", "type": "instruction"}, "content": "Keep evidence."})
        writer.call("instructions.save", {"path": "main.md", "metadata": {"id": "main", "type": "instruction", "instructions": {"common": "[[base]]"}}, "content": "Use the selected team."})
        resolved = reader.call("instructions.resolve", {"references": ["[[main]]"]})
        assert [x["id"] for x in resolved["instructions"]] == ["base", "main"]
        writer.call("instructions.save", {"path": "base.md", "metadata": base["metadata"], "content": "Keep verified evidence.", "expected_revision": base["revision"]})
        assert reader.call("instructions.resolve", {"references": ["main"]})["revision"] != resolved["revision"]
        with pytest.raises(PermissionError):
            reader.call("instructions.save", {"path": "bad.md", "metadata": {"id": "bad", "type": "instruction"}, "content": "No"})
    finally:
        writer.close()
        reader.close()


def test_child_search_uses_core_selection_diagnostics_and_cannot_escape_scope(app):
    alpha, beta = access(app), access(app, "beta")
    try:
        for capability in (alpha, beta):
            capability.call("rag.put_vector", dict(document=document(), vector=[1., .5], profile=app.config))
        result = alpha.call("rag.search", {"query": "source", "collection": "blocks"})
        assert [row["key"] for row in result["results"]] == [["alpha", "blocks", "1"]]
        assert result["diagnostics"]["algorithm"] == "distance_jump"
        assert result["diagnostics"]["scope"]["module"] == "alpha"
        assert result["diagnostics"]["scope"]["settings_context"] == "blocks"
        with pytest.raises(PermissionError):
            alpha.call("rag.search", {"query": "source", "module": "beta"})
        with pytest.raises(ValueError):
            alpha.call("rag.search", {"query": " "})
        with pytest.raises(ValueError):
            alpha.call("rag.search", {"query": "source", "limit": 1})
        with pytest.raises(PermissionError):
            ModuleCoreAccess(app, "alpha").call("rag.search", {"query": "source"})
    finally:
        alpha.close()
        beta.close()


def test_profile_loads_no_model_and_shared_pool_reuses_model_and_releases_own_leases(app):
    first, second = access(app), access(app)
    profile = first.call("embeddings.profile", {})
    assert profile == app.config and app.created == []
    assert first.call("embeddings.embed_documents", dict(texts=["a", "b"], profile=profile)) == [[1., .5], [1., .5]]
    assert second.call("embeddings.embed_query", dict(text="find", profile=profile)) == [1., .5]
    assert first.call("embeddings.count_tokens", dict(text="two words", profile=profile)) == 3
    assert len(app.created) == 1
    assert app.created[0].calls == [(["a", "b"], "document"), (["find"], "query")]
    assert len(app.resources._leases) == 0
    first.close()
    assert not app.created[0].closed
    second.close()
    assert app.created[0].closed and app.resources.providers._entries == {}


def test_rag_vector_round_trip_uses_existing_core_table_and_scoped_document_key(app):
    alpha, beta = access(app), access(app, "beta")
    profile = alpha.call("embeddings.profile", {})
    pointer = (app.layout.rag / "active.json").read_bytes()
    vector = alpha.call("embeddings.embed_documents", dict(texts=["hello source"], profile=profile))[0]
    assert alpha.call("rag.put_vector", dict(document=document(), vector=vector, profile=profile)) == dict(key=["alpha", "blocks", "1"], revision="hash")
    beta.call("rag.put_vector", dict(document=document(), vector=[.5, 1.], profile=profile))
    revisions = alpha.call("rag.vector_revisions", dict(collection="blocks", object_ids=["1", "missing"]))
    assert revisions["revisions"] == {"1": "hash"}
    assert revisions["missing"] == ["missing"] and revisions["conflicts"] == []
    inventory = alpha.call("rag.vector_revisions_page", dict(collection="blocks", limit=1))
    assert inventory["revisions"] == {"1": "hash"}
    assert inventory["next_cursor"] is None
    found = alpha.call("rag.search_vector", dict(collection="blocks", object_ids=["1"], vector=vector, profile=profile, limit=2))
    assert len(found) == 1 and found[0]["module"] == "alpha" and found[0]["object_id"] == "1"
    assert alpha.call("rag.search_vector", dict(collection="blocks", object_ids=["unselected"], vector=vector, profile=profile)) == []
    for method, args in [
        ("rag.put_vector", dict(document=document("beta"), vector=vector, profile=profile)),
        ("rag.delete_document", dict(key=document("beta")["key"])),
        ("rag.vector_revisions", dict(collection="blocks", object_ids=["1"], module="beta")),
        ("rag.vector_revisions_page", dict(collection="blocks", module="beta")),
        ("rag.search_vector", dict(collection="blocks", module="beta", object_ids=["1"], vector=vector, profile=profile)),
    ]:
        with pytest.raises(PermissionError, match="calling module"):
            alpha.call(method, args)
    alpha.call("rag.delete_document", dict(key=document()["key"]))
    removed = alpha.call("rag.vector_revisions", dict(collection="blocks", object_ids=["1"]))
    assert removed["revisions"] == {} and removed["missing"] == ["1"]
    assert beta.call("rag.vector_revisions", dict(collection="blocks", object_ids=["1"]))["revisions"] == {"1": "hash"}
    assert (app.layout.rag / "active.json").read_bytes() == pointer
    alpha.close()
    beta.close()


def test_revision_inventory_requires_explicit_selection_and_no_embedding_model(app):
    core = access(app, kind="query")
    try:
        with pytest.raises(ValueError, match="requires object_ids.*vector_revisions_page"):
            core.call("rag.vector_revisions", dict(collection="blocks"))
        with pytest.raises(ValueError):
            core.call("rag.vector_revisions", dict(collection="blocks", object_ids=[]))
        with pytest.raises(ValueError):
            core.call("rag.vector_revisions_page", dict(collection="blocks", max_bytes=1024 * 1024))
        result = core.call("rag.vector_revisions", dict(collection="blocks", object_ids=["missing"]))
        assert result["missing"] == ["missing"] and result["revisions"] == {}
        assert core.call("rag.vector_revisions_page", dict(collection="blocks"))["next_cursor"] is None
        assert app.created == []
    finally:
        core.close()


def test_request_permissions_and_transactions_are_separate_from_service_model_lifetime(app):
    service = access(app)
    for text in ("first", "second"):
        request = access(app, kind="query", provider_owner=service)
        profile = request.call("embeddings.profile", {})
        assert request.call("embeddings.embed_query", dict(text=text, profile=profile)) == [1., .5]
        with pytest.raises(PermissionError):
            request.call("storage.begin", {})
        request.close()
        assert not app.created[0].closed
    assert len(app.created) == 1
    token = service.call("storage.begin", {})
    request = access(app, kind="query", provider_owner=service)
    # Background transactions cannot be used by a query request.
    with pytest.raises(ModuleStorageError, match="inactive"):
        request.call("storage.query", dict(sql="SELECT 1", **token))
    with pytest.raises(ModuleStorageError, match="Finish the storage transaction"):
        request.call("embeddings.embed_query", dict(text="blocked", profile=profile))
    service.call("storage.rollback", token)
    request.close()
    service.close()
    assert app.created[0].closed


def test_declarations_query_writes_and_model_calls_inside_transaction_denied(app):
    none = ModuleCoreAccess(app, "alpha")
    with pytest.raises(PermissionError):
        none.call("embeddings.profile", {})
    with pytest.raises(PermissionError):
        none.call("storage.query", dict(sql="SELECT 1"))
    none.close()
    query = access(app, kind="query")
    for method in ("rag.put_vector", "rag.delete_document"):
        with pytest.raises(PermissionError, match="cannot write"):
            query.call(method, {})
    query.close()
    core = access(app)
    token = core.call("storage.begin", {})
    for method in ("embeddings.profile", "embeddings.embed_documents", "embeddings.embed_query", "embeddings.count_tokens",
                   "rag.put_vector", "rag.vector_revisions", "rag.vector_revisions_page", "rag.search_vector", "rag.delete_document"):
        with pytest.raises(ModuleStorageError, match="Finish the storage transaction"):
            core.call(method, {})
    core.call("storage.rollback", token)
    assert app.created == []
    core.close()


def test_profile_change_rejects_stale_vectors_and_releases_old_model(app):
    core = access(app)
    profile = core.call("embeddings.profile", {})
    core.call("embeddings.embed_query", dict(text="find", profile=profile))
    stale = copy.deepcopy(profile)
    stale["profile"]["dimensions"] = 3
    with pytest.raises(ValueError, match="profile changed"):
        core.call("embeddings.embed_query", dict(text="find", profile=stale))
    pointer = app.layout.rag / "active.json"
    active = json.loads(pointer.read_text())
    active["config"] = stale
    pointer.write_text(json.dumps(active))
    with pytest.raises(ValueError, match="profile changed"):
        core.call("embeddings.embed_query", dict(text="stale", profile=profile))
    assert app.created[0].closed
    with pytest.raises(ValueError, match="profile changed"):
        core.call("rag.put_vector", dict(document=document(), vector=[1., .5], profile=profile))
    core.close()


def test_model_inference_does_not_hold_root_guard_or_catalog_writer(app):
    core, writer = access(app), access(app)
    profile = core.call("embeddings.profile", {})
    core.call("embeddings.embed_query", dict(text="first", profile=profile))
    model = app.created[0]
    model.started, model.finish = threading.Event(), threading.Event()
    failures = []

    def infer():
        try:
            core.call("embeddings.embed_query", dict(text="background", profile=profile))
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=infer)
    thread.start()
    assert model.started.wait(1)
    try:
        assert core.expire() is False
        assert writer.call("storage.execute", dict(sql='INSERT INTO "{{module}}::items" VALUES (1)'))["rowcount"] == 1
        with app.layout.guard():
            assert not model.finish.is_set()
    finally:
        model.finish.set()
        thread.join(2)
    assert failures == []
    core.close()
    writer.close()


def test_persistent_child_background_index_and_query_share_core_model_and_rag(app):
    """Exercise the actual child SDK and parent transport, including namespace."""
    from contextopus.startup import Application

    module = app.layout.root / "modules/remote"
    package = module / "package"
    package.mkdir(parents=True)
    (package / "adapter.py").write_text('''import os, threading
class Service:
    def __init__(self, core):
        self.core = core
        self.ready = threading.Event()
        self.error = None
        self.thread = None
    def start(self):
        def index():
            try:
                self.profile = self.core.embeddings.profile()
                vectors = self.core.embeddings.embed_documents(texts=['child source'], profile=self.profile)
                self.core.rag.put_vector(document={
                    'key': {'collection': 'blocks', 'id': '1'},
                    'revision': 'child-revision', 'text': 'child source',
                    'location': 'module://remote/1', 'metadata': {'type': 'block'}
                }, vector=vectors[0], profile=self.profile)
            except Exception as exc:
                self.error = str(exc)
            finally:
                self.ready.set()
        self.thread = threading.Thread(target=index)
        self.thread.start()
    def dispatch(self, operation, arguments, context):
        if not self.ready.wait(3):
            raise TimeoutError('Background indexing did not finish')
        if self.error:
            raise RuntimeError(self.error)
        if operation == 'remote.search':
            vector = self.core.embeddings.embed_query(text=arguments['query'], profile=self.profile)
            rows = self.core.rag.search_vector(collection='blocks', object_ids=['1'],
                                               vector=vector, profile=self.profile, limit=3)
            return {'pid': os.getpid(), 'rows': rows,
                    'revisions': self.core.rag.vector_revisions(collection='blocks', object_ids=['1', 'missing']),
                    'inventory': self.core.rag.vector_revisions_page(collection='blocks', limit=1)}
        if operation == 'remote.foreign':
            try:
                self.core.rag.vector_revisions(collection='blocks', object_ids=['1'], module='beta')
            except RuntimeError as exc:
                return {'denied': str(exc)}
            raise AssertionError('Foreign module namespace was accepted')
        raise ValueError(operation)
    def close(self):
        if self.thread:
            self.thread.join(2)
def create_service(core):
    return Service(core)
''')
    (module / "module.json").write_text(json.dumps(dict(
        id="remote", version="1", rag=True,
        service=dict(factory="adapter.py:create_service", ready_timeout=5, stop_timeout=1),
        operations=[dict(name="remote.search", kind="query", service=True),
                    dict(name="remote.foreign", kind="query", service=True)])))
    # The same collection and ID already belong to another module in Core.
    # Search through the child must retain its own caller module predicate.
    other = access(app, "beta")
    other.call("rag.put_vector", dict(document=document(), vector=[1., .5], profile=app.config))
    other.close()
    application = Application(app.layout.root, resources=app.resources, discover=False)
    try:
        application.execute("core.module_install", dict(module="remote"))
        assert app.created == []
        app.resources.start_services()
        first = application.query("remote.search", dict(query="find child source"))
        second = application.query("remote.search", dict(query="find it again"))
        assert first["pid"] == second["pid"]
        assert first["pid"] != os.getpid()
        assert len(first["rows"]) == 1
        assert first["rows"][0]["module"] == "remote"
        assert first["rows"][0]["object_id"] == "1"
        assert first["rows"][0]["text"] == "child source"
        assert first["revisions"]["revisions"] == {"1": "child-revision"}
        assert first["revisions"]["missing"] == ["missing"]
        assert first["inventory"]["revisions"] == {"1": "child-revision"}
        assert first["inventory"]["next_cursor"] is None
        assert len(app.created) == 1 and not app.created[0].closed
        assert app.created[0].calls == [(["child source"], "document"),
                                       (["find child source"], "query"),
                                       (["find it again"], "query")]
        denied = application.query("remote.foreign")
        assert "calling module" in denied["denied"]
    finally:
        application.execute("core.module_disable", dict(module="remote"))
        application.close()
    assert app.created[0].closed
