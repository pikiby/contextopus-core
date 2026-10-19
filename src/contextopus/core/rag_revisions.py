"""Bounded revision lookups and snapshot-bound, object-key inventory pages.

Predicates stay inside LanceDB. An unindexed table may still scan filter columns
natively; these APIs never export a whole collection into Python for a lookup.
Inventory uses bounded TopK queries rather than retaining a sorted collection.
"""

import base64
import binascii
import hashlib
import json

DEFAULT_MAX_BYTES = 256 * 1024
MAX_BYTES = 768 * 1024
MAX_INPUT_BYTES = 256 * 1024
BATCH_SIZE = 256


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _text(value, label):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError(label + " must be a nonempty string of at most 4096 characters")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(label + " must contain valid UTF-8 text") from exc
    return value


def _budget(max_bytes):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError("max_bytes must be an integer from 1 to 786432")
    return max_bytes


def _fits(result, max_bytes):
    return len(_encoded(result)) <= max_bytes


def _bounded(result, max_bytes):
    if not _fits(result, max_bytes):
        raise ValueError("RAG revision result exceeds max_bytes; request fewer IDs or increase the byte budget")
    return result


def _ids(object_ids):
    if object_ids is None:
        raise ValueError("object_ids is required; use vector_revisions_page for collection inventory")
    if not isinstance(object_ids, (list, tuple)) or not 1 <= len(object_ids) <= 1000:
        raise ValueError("object_ids must contain from 1 to 1000 unique IDs")
    ids = [_text(value, "object_id") for value in object_ids]
    if len(set(ids)) != len(ids):
        raise ValueError("object_ids must not contain duplicates")
    if len(_encoded(ids)) > MAX_INPUT_BYTES:
        raise ValueError("Encoded object_ids exceed the 256 KiB input budget")
    return ids


def _scope(index, module, collection):
    _text(module, "module")
    _text(collection, "collection")
    root = hashlib.sha256(str(index.layout.root.resolve()).encode("utf-8")).hexdigest()
    return {"root": root, "module": module, "collection": collection}


def _cursor(scope, snapshot, after):
    return base64.urlsafe_b64encode(_encoded({"format": 1, **scope, **snapshot, "after": after})).decode("ascii")


def _decode_cursor(value, scope):
    if value is None:
        return None
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 131072:
            raise ValueError("invalid cursor length")
        state = json.loads(base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True))
        if not isinstance(state, dict) or set(state) != {"format", "root", "module", "collection", "table", "version", "after"}:
            raise ValueError("invalid cursor fields")
        if type(state["format"]) is not int or state["format"] != 1 or type(state["version"]) is not int or state["version"] < 1:
            raise ValueError("invalid cursor version")
        _text(state["table"], "cursor table")
        _text(state["after"], "cursor object_id")
    except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Invalid RAG revisions cursor") from exc
    if any(state.get(key) != value for key, value in scope.items()):
        raise ValueError("RAG revisions cursor belongs to another root, module or collection")
    return state


def _snapshot(index, current, state):
    if current is None:
        if state is not None:
            raise ValueError("RAG revisions cursor expired: the active table is absent; restart inventory")
        return None, None
    if state is not None and state["table"] != current.name:
        raise ValueError("RAG revisions cursor expired: the active table changed; restart inventory")
    version = state["version"] if state is not None else current.version
    # Never checkout the shared writable handle. A separate native view pins the
    # version without copying its rows or changing another caller's table state.
    table = index.db.open_table(current.name)
    try:
        table.checkout(version)
    except (ValueError, RuntimeError, OSError) as exc:
        raise ValueError("RAG revisions cursor snapshot is unavailable or expired; restart inventory") from exc
    return table, {"table": current.name, "version": version}


def _predicate(index, module, collection):
    return "module=" + index._quote(module) + " AND collection=" + index._quote(collection)


def _lookup(index, table, module, collection, ids, snapshot):
    revisions, conflicts, present = {}, set(), set()
    if table is not None:
        predicate = _predicate(index, module, collection) + " AND object_id IN (" + ",".join(index._quote(value) for value in ids) + ")"
        query = table.search().where(predicate).select(["object_id", "revision"]).limit(None)
        requested = set(ids)
        for batch in query.to_batches(batch_size=BATCH_SIZE):
            for row in batch.to_pylist():
                ident, revision = row["object_id"], row["revision"]
                if ident not in requested:
                    raise ValueError("RAG revision query returned an object outside the requested scope")
                if not isinstance(revision, str):
                    raise ValueError("Stored RAG revision must be a string for object_id " + repr(ident))
                try:
                    revision.encode("utf-8")
                except UnicodeError as exc:
                    raise ValueError("Stored RAG revision is not valid UTF-8") from exc
                present.add(ident)
                if ident in conflicts:
                    continue
                if ident in revisions and revisions[ident] != revision:
                    del revisions[ident]
                    conflicts.add(ident)
                else:
                    revisions[ident] = revision
    return {"revisions": {ident: revisions[ident] for ident in ids if ident in revisions},
            "missing": [ident for ident in ids if ident not in present],
            "conflicts": [ident for ident in ids if ident in conflicts], "snapshot": snapshot}


def lookup(index, module, collection, *, object_ids=None, max_bytes=DEFAULT_MAX_BYTES):
    ids, max_bytes = _ids(object_ids), _budget(max_bytes)
    _scope(index, module, collection)
    if not (index.layout.rag / "active.json").is_file():
        return _bounded(_lookup(index, None, module, collection, ids, None), max_bytes)
    with index.layout.guard():
        table, snapshot = _snapshot(index, index._generic_table(), None)
        return _bounded(_lookup(index, table, module, collection, ids, snapshot), max_bytes)


def _candidates(index, table, module, collection, after, limit):
    from lancedb.query import ColumnOrdering

    result = []
    while len(result) < limit:
        count = min(BATCH_SIZE, limit - len(result))
        predicate = _predicate(index, module, collection)
        if after is not None:
            predicate += " AND object_id>" + index._quote(after)
        query = (table.search().where(predicate).select(["object_id"])
                 .order_by([ColumnOrdering(column_name="object_id", nulls_first=True)]).limit(count))
        rows = 0
        previous = after
        for batch in query.to_batches(batch_size=BATCH_SIZE):
            for row in batch.to_pylist():
                rows += 1
                ident = _text(row["object_id"], "Stored object_id")
                if ident != previous:
                    result.append(ident)
                previous = ident
        if not rows or rows < count:
            break
        after = previous
    return result


def inventory(index, module, collection, *, cursor=None, limit=100, max_bytes=DEFAULT_MAX_BYTES):
    max_bytes = _budget(max_bytes)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")
    scope = _scope(index, module, collection)
    state = _decode_cursor(cursor, scope)
    if not (index.layout.rag / "active.json").is_file():
        if state is not None:
            raise ValueError("RAG revisions cursor expired: the active table is absent; restart inventory")
        return _bounded({"revisions": {}, "conflicts": [], "snapshot": None, "next_cursor": None}, max_bytes)
    with index.layout.guard():
        table, snapshot = _snapshot(index, index._generic_table(), state)
        if table is None:
            return _bounded({"revisions": {}, "conflicts": [], "snapshot": None, "next_cursor": None}, max_bytes)
        ids = _candidates(index, table, module, collection, state["after"] if state else None, limit + 1)
        checked = ids[:limit]
        found = _lookup(index, table, module, collection, checked, snapshot) if checked else {"revisions": {}, "conflicts": []}
        if found.get("missing"):
            raise ValueError("RAG snapshot inventory changed while reading its objects")
        revisions, conflicts = {}, []
        result = {"revisions": revisions, "conflicts": conflicts, "snapshot": snapshot, "next_cursor": None}
        for position, ident in enumerate(checked):
            if ident in found["revisions"]:
                revisions[ident] = found["revisions"][ident]
            else:
                conflicts.append(ident)
            continuation = _cursor(scope, snapshot, ident) if position + 1 < len(ids) else None
            candidate = {**result, "next_cursor": continuation}
            if not _fits(candidate, max_bytes):
                revisions.pop(ident, None)
                if conflicts and conflicts[-1] == ident:
                    conflicts.pop()
                if position == 0:
                    raise ValueError("A RAG revision entry and its continuation cursor exceed max_bytes")
                break
            result = candidate
        return _bounded(result, max_bytes)
