"""Real temporary LanceDB revision reads, with no embedding model or live root."""

import base64
from datetime import timedelta
import json

import pytest

from contextopus.core.embeddings import default_config
from contextopus.core.rag import RagIndex
from contextopus.core import rag_revisions
from contextopus.core.storage import StorageLayout


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def index(tmp_path):
    index = RagIndex(StorageLayout(tmp_path / "root"))
    index.embeddings = default_config()
    index.embeddings["profile"]["dimensions"] = 2
    index._generic_table(create=True)
    return index


def row(ident, revision="r1", *, module="alpha", collection="blocks", part=0):
    return dict(material_id=ident, part_index=part, text="content", vector=[1., .5],
                path="module://" + str(ident), revision=revision, token_start=0,
                token_end=1, char_start=0, char_end=7, chunking_id="test",
                part_count=1, module=module, collection=collection, object_id=ident,
                metadata="{}", workspace="")


def add(index, *rows):
    index.table.add(list(rows))


def walk(index, **kwargs):
    pages, cursor = [], None
    while True:
        page = index.vector_revisions_page("alpha", "blocks", cursor=cursor, **kwargs)
        pages.append(page)
        cursor = page["next_cursor"]
        if cursor is None:
            return pages


def test_required_ids_and_invalid_inputs_fail_without_opening_database(tmp_path, monkeypatch):
    index = RagIndex(StorageLayout(tmp_path / "absent"))
    monkeypatch.setattr(index,"_generic_table",lambda: (_ for _ in ()).throw(AssertionError("must validate first")))
    with pytest.raises(ValueError, match="object_ids is required.*vector_revisions_page"):
        index.vector_revisions("alpha","blocks")
    for ids in ([], [""], ["a","a"], [None], "a", ["x" * 4097], ["\ud800"], [str(i) for i in range(1001)], [str(i) + "x" * 4090 for i in range(70)]):
        with pytest.raises(ValueError):
            index.vector_revisions("alpha","blocks",object_ids=ids)
    for max_bytes in (0,-1,True,786433,"1024"):
        with pytest.raises(ValueError, match="max_bytes"):
            index.vector_revisions("alpha","blocks",object_ids=["a"],max_bytes=max_bytes)
    assert not index.layout.root.exists()


def test_absent_index_reports_missing_without_creating_files(tmp_path):
    index = RagIndex(StorageLayout(tmp_path / "absent"))
    assert index.vector_revisions("alpha","blocks",object_ids=["a","b"]) == {
        "revisions":{},"missing":["a","b"],"conflicts":[],"snapshot":None}
    assert index.vector_revisions_page("alpha","blocks") == {
        "revisions":{},"conflicts":[],"snapshot":None,"next_cursor":None}
    assert not index.layout.root.exists()


def test_lookup_scopes_ids_and_deduplicates_fragments_without_arbitrary_conflict_winner(index):
    add(index,row("a"),row("a",part=1),row("bad","old"),row("bad","new",part=1),
        row("a","foreign",module="beta"),row("a","other",collection="other"),row("excluded"))
    result = index.vector_revisions("alpha","blocks",object_ids=["missing","a","bad"])
    assert result["revisions"] == {"a":"r1"}
    assert result["missing"] == ["missing"]
    assert result["conflicts"] == ["bad"]
    assert result["snapshot"]["table"] == index.table.name
    assert isinstance(result["snapshot"]["version"],int)


def test_lookup_uses_filtered_projected_batches_and_checks_late_fragments(index, monkeypatch):
    add(index,*(row("a",part=i) for i in range(600)),row("a","conflicting",part=600),row("unrequested"))
    from lancedb.query import LanceEmptyQueryBuilder
    batches = LanceEmptyQueryBuilder.to_batches
    observed = []
    def read(query, *args, **kwargs):
        observed.append((query._where, query._columns, kwargs.get("batch_size")))
        return batches(query,*args,**kwargs)
    monkeypatch.setattr(LanceEmptyQueryBuilder,"to_batches",read)
    monkeypatch.setattr(LanceEmptyQueryBuilder,"to_list",lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("unbounded Python export")))
    monkeypatch.setattr(index,"read_rows",lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("collection export")))
    result = index.vector_revisions("alpha","blocks",object_ids=["a"])
    assert result["conflicts"] == ["a"] and not result["revisions"]
    assert observed
    assert all("module='alpha'" in predicate and "collection='blocks'" in predicate and "object_id IN ('a')" in predicate
               and columns == ["object_id","revision"] and size == 256 for predicate,columns,size in observed)


def test_unicode_and_sql_literals_are_exact_and_max_char_id_is_supported(index):
    ids = ["русский🙂", "x' OR 1=1 --", "界" * 4096, "line\nnull\x00"]
    add(index,*(row(ident,"ревизия🙂") for ident in ids),row("other"))
    result = index.vector_revisions("alpha","blocks",object_ids=ids)
    assert result["revisions"] == dict.fromkeys(ids,"ревизия🙂")
    assert not result["missing"] and not result["conflicts"]


def test_lookup_checks_exact_complete_utf8_json_budget(index):
    add(index,row("ключ🙂","данные🙂"))
    result = index.vector_revisions("alpha","blocks",object_ids=["ключ🙂","нет"])
    size = len(encoded(result))
    assert index.vector_revisions("alpha","blocks",object_ids=["ключ🙂","нет"],max_bytes=size) == result
    with pytest.raises(ValueError,match="exceeds max_bytes"):
        index.vector_revisions("alpha","blocks",object_ids=["ключ🙂","нет"],max_bytes=size-1)
    assert len(json.dumps(result).encode()) > size


def test_page_inventory_is_complete_distinct_scoped_and_lexically_ordered(index):
    add(index,*(row("a",part=i) for i in range(300)),row("b","one"),row("b","two",part=1),
        row("c"),row("d"),row("not-ours",module="beta"),row("not-here",collection="other"))
    pages = walk(index,limit=2)
    assert len(pages) == 2
    assert pages[0]["revisions"] == {"a":"r1"}
    assert pages[0]["conflicts"] == ["b"]
    assert pages[1]["revisions"] == {"c":"r1","d":"r1"}
    assert pages[1]["conflicts"] == []
    assert pages[0]["snapshot"] == pages[1]["snapshot"]
    assert pages[0]["next_cursor"] and pages[1]["next_cursor"] is None


def test_page_maximum_limit_has_no_default_query_limit_truncation(index):
    add(index,*(row(f"{i:04}") for i in range(1005)))
    pages = walk(index,limit=1000)
    assert [len(page["revisions"]) for page in pages] == [1000,5]
    assert len({key for page in pages for key in page["revisions"]}) == 1005


def test_page_snapshot_remains_consistent_across_insert_delete_and_revision_changes(index):
    add(index,row("a"),row("b"),row("c"))
    first = index.vector_revisions_page("alpha","blocks",limit=1)
    index.table.delete("module='alpha' AND collection='blocks' AND object_id IN ('b','c')")
    add(index,row("b","new"),row("0","insert-before"),row("d","insert-after"))
    second = index.vector_revisions_page("alpha","blocks",cursor=first["next_cursor"],limit=10)
    assert first["revisions"] == {"a":"r1"}
    assert second["revisions"] == {"b":"r1","c":"r1"}
    assert second["snapshot"] == first["snapshot"]
    assert second["next_cursor"] is None
    fresh = index.vector_revisions_page("alpha","blocks")
    assert fresh["revisions"] == {"0":"insert-before","a":"r1","b":"new","d":"insert-after"}
    assert fresh["snapshot"]["version"] > first["snapshot"]["version"]
    # Snapshot checkout must not put the shared writer into a read-only state.
    add(index,row("e"))


def test_page_byte_budget_includes_snapshot_cursor_and_utf8(index):
    add(index,*(row(f"{i}-ключ🙂","данные🙂" * 25) for i in range(6)))
    sample = index.vector_revisions_page("alpha","blocks",limit=1)
    budget = len(encoded(sample))
    pages = walk(index,limit=6,max_bytes=budget)
    assert len(pages) > 1
    assert all(len(encoded(page)) <= budget for page in pages)
    assert {key for page in pages for key in page["revisions"]} == {f"{i}-ключ🙂" for i in range(6)}
    first = index.vector_revisions_page("alpha","blocks",limit=6,max_bytes=budget)
    assert len(first["revisions"]) == 1 and first["next_cursor"]
    with pytest.raises(ValueError,match="entry.*cursor.*max_bytes"):
        index.vector_revisions_page("alpha","blocks",limit=1,max_bytes=budget-1)


def test_single_oversized_revision_is_never_silently_truncated(index):
    add(index,row("a","x" * 10000))
    with pytest.raises(ValueError,match="exceeds max_bytes"):
        index.vector_revisions("alpha","blocks",object_ids=["a"],max_bytes=1000)
    with pytest.raises(ValueError,match="entry.*max_bytes"):
        index.vector_revisions_page("alpha","blocks",max_bytes=1000)


def test_malformed_wrong_scope_and_wrong_root_cursors_fail_explicitly(index,tmp_path):
    add(index,row("a"),row("b"))
    cursor = index.vector_revisions_page("alpha","blocks",limit=1)["next_cursor"]
    for invalid in ("not base64!", "", "e30=", 7, cursor[:-1], "a" * 131073):
        with pytest.raises(ValueError,match="cursor"):
            index.vector_revisions_page("alpha","blocks",cursor=invalid)
    for module,collection in (("beta","blocks"),("alpha","other")):
        with pytest.raises(ValueError,match="another root, module or collection"):
            index.vector_revisions_page(module,collection,cursor=cursor)
    other = RagIndex(StorageLayout(tmp_path / "different"))
    with pytest.raises(ValueError,match="another root"):
        other.vector_revisions_page("alpha","blocks",cursor=cursor)


def test_expired_native_snapshot_does_not_restart_on_latest_version(index):
    add(index,row("a"),row("b"))
    first = index.vector_revisions_page("alpha","blocks",limit=1)
    add(index,row("c"))
    with pytest.warns(UserWarning,match="removes every version"):
        index.table.optimize(cleanup_older_than=timedelta(seconds=0),delete_unverified=True)
    with pytest.raises(ValueError,match="snapshot.*expired"):
        index.vector_revisions_page("alpha","blocks",cursor=first["next_cursor"])


def test_replaced_active_table_invalidates_inventory_cursor(index):
    add(index,row("a"),row("b"))
    cursor = index.vector_revisions_page("alpha","blocks",limit=1)["next_cursor"]
    replacement = index.create_table("replacement",2)
    pointer = index.layout.rag / "active.json"
    active = json.loads(pointer.read_text())
    active["table"] = replacement.name
    pointer.write_text(json.dumps(active))
    with pytest.raises(ValueError,match="active table changed"):
        index.vector_revisions_page("alpha","blocks",cursor=cursor)


@pytest.mark.parametrize("ident",[None,""])
def test_inventory_rejects_invalid_stored_identity_instead_of_omitting_it(index,ident):
    add(index,row(ident),row("a"))
    with pytest.raises(ValueError,match="Stored object_id"):
        index.vector_revisions_page("alpha","blocks",limit=1)


def test_invalid_stored_revision_is_not_reported_as_missing(index):
    add(index,row("a",None))
    with pytest.raises(ValueError,match="Stored RAG revision"):
        index.vector_revisions("alpha","blocks",object_ids=["a"])


def test_invalid_page_limits_scopes_and_budgets_fail_before_open(index,monkeypatch):
    monkeypatch.setattr(index,"_generic_table",lambda: (_ for _ in ()).throw(AssertionError("must validate first")))
    for limit in (0,1001,True,"10"):
        with pytest.raises(ValueError,match="limit"):
            index.vector_revisions_page("alpha","blocks",limit=limit)
    for module,collection in (("","blocks"),("alpha","\ud800")):
        with pytest.raises(ValueError):
            index.vector_revisions_page(module,collection)
    with pytest.raises(ValueError,match="max_bytes"):
        index.vector_revisions_page("alpha","blocks",max_bytes=786433)


def test_lookup_accepts_maximum_unique_id_count_without_truncation(index):
    ids=[f"object-{i:04}" for i in range(1000)]
    add(index,*(row(ident) for ident in ids))
    result=index.vector_revisions("alpha","blocks",object_ids=ids)
    assert result['revisions']==dict.fromkeys(ids,'r1')
    assert not result['missing'] and not result['conflicts']
