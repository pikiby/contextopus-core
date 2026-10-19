"""Bounded search evidence and counterfactual selection, without source copies."""

from datetime import datetime, timedelta, timezone
from contextlib import closing
import hashlib
import json
import sqlite3

from .analytics import sanitize



def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS search_evidence (
        event_id TEXT PRIMARY KEY, query_hash TEXT, task_id TEXT, purpose TEXT,
        instructions_revision TEXT, diagnostics TEXT)""")


def begin(db, event_id, layout, context, operation, arguments, revision=None):
    query = arguments.get("query", "")
    db.execute("INSERT INTO search_evidence VALUES (?,?,?,?,?,NULL)", (
        event_id, hashlib.sha256(query.encode()).hexdigest(),
        json.dumps(sanitize(arguments.get("task_id"))),
        json.dumps(sanitize(arguments.get("purpose"))), revision,
    ))


def finish(db, event_id, result):
    if not isinstance(result, dict) or not isinstance(result.get("diagnostics"), dict):
        return False
    if not db.execute("SELECT 1 FROM search_evidence WHERE event_id=?", [event_id]).fetchone():
        return False
    diagnostics = result["diagnostics"]
    # Sanitize each small candidate separately: the general event summary keeps
    # only 100 entries, but replay must retain the declared bounded candidate pool.
    candidates = diagnostics.get("candidates", [])
    retained = []
    for row in candidates[:1000]:
        if not isinstance(row, dict):
            continue
        retained.append(sanitize({key: row.get(key) for key in (
            "input_index", "key", "revision", "distance", "selected", "part_index")}))
    metadata = sanitize({k: v for k, v in diagnostics.items() if k not in {
        "candidates", "nearby_rejected"}})
    metadata["candidates"] = retained
    if isinstance(result.get("analytics"), dict):
        metadata["module_event_id"] = result["analytics"].get("event_id")
    metadata["truncated"] = bool(metadata.get("truncated") or len(candidates) > 1000)
    db.execute("UPDATE search_evidence SET diagnostics=? WHERE event_id=?", (
        json.dumps(metadata, allow_nan=False), event_id))
    return True


def _instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Use timezone-aware ISO timestamps")
    return result.astimezone(timezone.utc)


class SearchHistory:
    def __init__(self, journal, registry=None):
        self.journal, self.registry = journal, registry

    def _read(self, sql, values):
        if not self.journal.path.exists():
            return []
        with closing(sqlite3.connect(self.journal.path.as_uri() + "?mode=ro", uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='search_evidence'").fetchone():
                return []
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, values)]

    def query(self, since=None, until=None, context=None, task_id=None,
              instructions_revision=None, offset=0, limit=50):
        """Freeze a bounded period; defaults to the previous seven days."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Use offset >= 0 and limit 1..100")
        end = _instant(until) if until else datetime.now(timezone.utc)
        start = _instant(since) if since else end - timedelta(days=7)
        if start > end:
            raise ValueError("since must precede until")
        clauses = ["julianday(o.started)>=julianday(?)", "julianday(o.started)<=julianday(?)"]
        values = [start.isoformat(), end.isoformat()]
        for column, value in (("o.context", context), ("s.task_id", json.dumps(task_id) if task_id else None),
                              ("s.instructions_revision", instructions_revision)):
            if value is not None:
                clauses.append(column + "=?")
                values.append(value)
        rows = self._read("SELECT s.event_id,o.started,o.context,o.operation,o.outcome,o.duration,"
                          "s.query_hash,s.task_id,s.instructions_revision,s.diagnostics "
                          "FROM search_evidence s JOIN operations o ON o.id=s.event_id WHERE "
                          + " AND ".join(clauses) + " ORDER BY o.started,s.event_id LIMIT ? OFFSET ?",
                          [*values, limit + 1, offset])
        for row in rows:
            diag = json.loads(row.pop("diagnostics") or "{}")
            row.update(algorithm=diag.get("algorithm"), counts=diag.get("counts"),
                       truncated=diag.get("truncated"), task_id=json.loads(row["task_id"]))
        return {"events": rows[:limit], "since": start.isoformat(), "until": end.isoformat(),
                "next_offset": offset + limit if len(rows) > limit else None,
                "scope": {"context": context, "task_id": task_id,
                          "instructions_revision": instructions_revision}}

    def read(self, event_id):
        rows = self._read("SELECT s.*,o.started,o.context,o.operation,o.outcome,o.duration "
                          "FROM search_evidence s JOIN operations o ON o.id=s.event_id WHERE s.event_id=?",
                          [event_id])
        if not rows:
            raise ValueError("Search evidence is unavailable for this event")
        row = rows[0]
        for key in ("diagnostics", "purpose", "task_id"):
            row[key] = json.loads(row[key]) if row[key] else None
        row["evidence_limits"] = ["Reading does not establish use or answer quality",
                                 "Query text is not retained; query_hash identifies exact repeats",
                                 "Instructions fingerprint is not historical instruction text"]
        return row

    def replay(self, event_id, selection, relevant_keys=None):
        """Re-select recorded candidates; never re-embed or silently query today's corpus."""
        from .filtering import select
        original = self.read(event_id)
        diagnostics = original["diagnostics"]
        if not diagnostics or not isinstance(diagnostics.get("candidates"), list):
            raise ValueError("No recorded candidates to replay")
        rows = diagnostics["candidates"]
        alternative = select(rows, selection, output=diagnostics.get("output", "materials"),
                             registry=self.registry)
        fragments = diagnostics.get("output") == "fragments"
        key = lambda row: json.dumps(
            {"key": row["key"], "part_index": row.get("part_index"), "revision": row.get("revision")}
            if fragments else row["key"], sort_keys=True)
        old = {key(row) for row in rows if row.get("selected")}
        new = {key(row) for row in alternative["results"]}
        desc = alternative["diagnostics"]
        counts = diagnostics.get("counts", {})
        snapshot_truncated = bool(diagnostics.get("truncated") or
                                  counts.get("considered_fragments", len(rows)) > len(rows))
        retrieval_truncated = bool(diagnostics.get("candidate_pool_truncated"))
        recorded_selected = counts.get("selected")
        original_selection_complete = (sum(bool(row.get("selected")) for row in rows) == recorded_selected
                                       if recorded_selected is not None else None)
        original_version = diagnostics.get("version")
        same_implementation = (diagnostics.get("algorithm") == desc["algorithm"] and
                               original_version == desc["version"] and
                               diagnostics.get("selection_contract") == desc["selection_contract"])
        judgments = None
        if relevant_keys is not None:
            if fragments:
                raise ValueError("Relevance labels currently score materials; use output=materials for label comparisons")
            if not isinstance(relevant_keys, list):
                raise ValueError("relevant_keys must be a list of caller-labelled relevant object keys")
            expected = {json.dumps(value, sort_keys=True) for value in relevant_keys}
            def score(chosen):
                hits = len(chosen & expected)
                return {"labelled_hits": hits, "labelled_missing": len(expected - chosen),
                        "precision": hits / len(chosen) if chosen else None,
                        "recall": hits / len(expected) if expected else None}
            judgments = {"basis": "caller_supplied_relevance_labels",
                         "scope": "recorded_candidates_only",
                         "original_selection_complete": original_selection_complete,
                         "original": score(old) if original_selection_complete is True else None,
                         "original_recorded_subset": score(old), "alternative": score(new)}
        return {"event_id": event_id, "scope": "recorded_candidates_only",
                "output": diagnostics.get("output", "materials"),
                "snapshot_truncated": snapshot_truncated or retrieval_truncated,
                "candidate_snapshot_truncated": snapshot_truncated,
                "retrieval_truncated": retrieval_truncated,
                "original_selection_complete": original_selection_complete,
                "replay_kind": "current_counterfactual",
                "same_implementation": same_implementation,
                "original_execution_reproduced": False,
                "original": {"algorithm": diagnostics.get("algorithm"), "version": diagnostics.get("version"),
                             "effective_settings": diagnostics.get("effective_settings"),
                             "selection_contract": diagnostics.get("selection_contract"),
                             "deduplication_order": diagnostics.get("deduplication_order"),
                             "counts": diagnostics.get("counts"),
                             "boundary": diagnostics.get("boundary")},
                "alternative": {k: desc[k] for k in ("algorithm", "version", "selection_contract", "effective_settings", "counts", "boundary")},
                "added": [json.loads(k) for k in sorted(new - old)],
                "removed": [json.loads(k) for k in sorted(old - new)],
                "quality_assessment": "not_established",
                "label_comparison": judgments,
                "limitations": ["Same candidate snapshot, current alternative implementation",
                                "Missing candidates outside the snapshot require a broader retrieval",
                                "Recorded selected flags describe the original result; the old algorithm is not rerun",
                                "Added and removed keys cover recorded candidates only; incomplete snapshots can omit original selections",
                                "Compare task/answer evidence and historical rules before judging relevance"]}
