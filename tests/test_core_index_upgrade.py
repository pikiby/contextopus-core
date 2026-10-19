"""Existing derived vectors gain namespaces without model loading or data loss."""

import json
from contextopus.core.chunking import default_chunking
from contextopus.core.embeddings import default_config
from contextopus.core.rag import RagIndex
from contextopus.core.resources import ProcessResources
from contextopus.core.storage import StorageLayout
from contextopus.startup import Application


def test_legacy_index_namespace_upgrade_preserves_vectors_and_is_idempotent(tmp_path):
    import lancedb
    import pyarrow as pa

    layout = StorageLayout(tmp_path)
    state = layout.rag
    state.mkdir(parents=True)
    config = default_config()
    config["profile"]["dimensions"] = 2
    schema = RagIndex.schema(2)
    generic = {"module", "collection", "object_id", "metadata"}
    legacy_schema = pa.schema([field for field in schema if field.name not in generic])
    original = {
        "material_id": "stable-id",
        "part_index": 0,
        "text": "literal original knowledge",
        "vector": [1.0, 0.0],
        "path": "knowledge/Descriptive title.md",
        "revision": "original-revision",
        "token_start": 0,
        "token_end": 26,
        "char_start": 0,
        "char_end": 26,
        "chunking_id": "old-chunking-id",
        "part_count": 1,
        "workspace": "alpha",
    }
    database = lancedb.connect(str(state / "lancedb"))
    table = database.create_table("retained_parts", schema=legacy_schema)
    table.add([original])
    active = {
        "config": config,
        "chunking": default_chunking(),
        "table": "retained_parts",
        "index_format": 2,
    }
    pointer = state / "active.json"
    pointer.write_text(json.dumps(active))
    before = pointer.read_bytes()

    def forbidden_factory(config):
        raise AssertionError("namespace migration loaded a model")

    with ProcessResources(forbidden_factory) as resources:
        with Application(tmp_path, resources=resources, discover=False) as app:
            result = app.execute("core.index_upgrade")
            assert result["status"] == "upgraded"
            assert result["model_loaded"] is False
            assert not resources.providers._entries
            assert pointer.read_bytes() == before
            rows = app.index.table.search().limit(None).to_list()
            assert len(rows) == 1
            for key, value in original.items():
                assert rows[0][key] == value
            assert {key: rows[0][key] for key in generic} == {
                "module": "workspace",
                "collection": "alpha",
                "object_id": "stable-id",
                "metadata": "{}",
            }
            assert app.execute("core.index_upgrade")["table"] == "retained_parts"
            assert app.index.table.search().limit(None).to_list() == rows
            assert pointer.read_bytes() == before
