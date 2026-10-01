"""Observed PCW calls and file revisions. No model calls or vector indexing."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from .runtime import PCWError


SECRET_KEY = re.compile(r"^(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|authorization|cookie|private[_-]?key)$", re.I)
SECRET_VALUE = re.compile(r"(?im)(\b(?:password|passwd|api[_-]?key|access[_-]?token|secret|authorization)\s*[:=]\s*)([^\r\n]+)")


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    """Known credential keys/patterns plus credentials explicitly held in the environment.

    Not a semantic classifier: unknown unlabelled secrets cannot be recognized.
    """
    count = 0
    known = [value for key, value in os.environ.items()
             if len(value) >= 8 and re.search(r"(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)$", key)]

    def clean(item):
        nonlocal count
        if isinstance(item, dict):
            result = {}
            for key, part in item.items():
                if SECRET_KEY.fullmatch(str(key)):
                    result[key] = "[REDACTED_SECRET]"
                    count += 1
                else:
                    result[key] = clean(part)
            return result
        if isinstance(item, (list, tuple)):
            return [clean(part) for part in item]
        if not isinstance(item, str):
            return item
        for secret in known:
            if secret in item:
                count += item.count(secret)
                item = item.replace(secret, "[REDACTED_SECRET]")
        item, n = re.subn(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----", "[REDACTED_SECRET]", item)
        count += n
        item, n = re.subn(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED_SECRET]", item)
        count += n
        item, n = re.subn(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED_SECRET]@", item)
        count += n
        item, n = SECRET_VALUE.subn(r"\1[REDACTED_SECRET]", item)
        count += n
        return item

    result = clean(value)
    return result, count


class EventStore:
    def __init__(self, work_root):
        root = Path(work_root)
        if not root.is_absolute() or not root.is_dir():
            raise PCWError("Analytics work_root must be an existing absolute directory")
        self.work_root = root.resolve()
        self.root = self.work_root / ".pcw/.analytics"
        self.path = self.root / "events.sqlite"

    def _safe(self):
        for path in (self.work_root / ".pcw", self.root, self.path,
                     Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            if path.is_symlink():
                raise PCWError("Symlinks are forbidden in the analytics store")

    @contextmanager
    def connect(self):
        self._safe()
        self.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS blobs (id TEXT PRIMARY KEY, text TEXT NOT NULL, redactions INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, tool TEXT NOT NULL, cycle_id TEXT, task_id TEXT,
              mode TEXT, started_at TEXT NOT NULL, finished_at TEXT, duration_ms REAL,
              state TEXT NOT NULL, params TEXT, result TEXT, error TEXT, result_bytes INTEGER,
              source TEXT NOT NULL DEFAULT 'mcp', source_event_id TEXT, import_id TEXT);
            CREATE INDEX IF NOT EXISTS events_scope ON events(workspace, cycle_id, task_id, started_at);
            CREATE TABLE IF NOT EXISTS versions (
              event_id TEXT, path TEXT, relation TEXT NOT NULL, before_hash TEXT, after_hash TEXT,
              before_blob TEXT, after_blob TEXT, PRIMARY KEY(event_id, path, relation));
            CREATE TABLE IF NOT EXISTS observed (workspace TEXT, path TEXT, hash TEXT, blob TEXT,
              PRIMARY KEY(workspace, path));
            CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, adapter TEXT NOT NULL,
              source_path TEXT, session_id TEXT, imported_at TEXT, records INTEGER);
            CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, created_at TEXT,
              criterion TEXT, assessment TEXT, evidence TEXT);
        """)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _blob(db, value):
        safe, redactions = redact(value)
        text = json.dumps(safe, ensure_ascii=False, sort_keys=True)
        ident = hashlib.sha256(text.encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?, ?)", (ident, text, redactions))
        return ident

    @staticmethod
    def snapshot(runtime):
        """Called under the same workspace lock as the tool, never through vector reads."""
        files = {}
        root = runtime.engine.root
        if not root.is_dir():
            return files
        for path in [root / "INSTRUCTIONS.md", root / "PROJECT.md",
                     *sorted((root / "knowledge").rglob("*.md")), *sorted((root / "current").glob("*.md"))]:
            runtime.engine._assert_safe(path)
            if path.is_file():
                raw = path.read_bytes()
                files[path.relative_to(root).as_posix()] = {"hash": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8")}
        return files

    def begin(self, workspace, tool, params, mode=None, task_id=None, before=None):
        ident = uuid.uuid4().hex
        with self.connect() as db:
            params_blob = self._blob(db, params)
            db.execute("INSERT INTO events(id,workspace,tool,cycle_id,task_id,mode,started_at,state,params) VALUES (?,?,?,?,?,?,?,?,?)",
                       (ident, workspace, tool, params.get("cycle_id"), task_id, mode, now(), "started", params_blob))
            # A change already present before this call has no established author.
            previous = {row["path"]: dict(row) for row in db.execute("SELECT * FROM observed WHERE workspace=?", (workspace,))} if before is not None else {}
            for path in previous.keys() | (before or {}).keys():
                old, current = previous.get(path), (before or {}).get(path)
                if old and current and old["hash"] == current["hash"]:
                    continue
                blob = self._blob(db, current["text"]) if current else None
                db.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?)", (ident, path, "observed_before_call",
                    old["hash"] if old else None, current["hash"] if current else None, old["blob"] if old else None, blob))
            if before is not None:
                self._observe(db, workspace, before)
        return ident

    def _observe(self, db, workspace, files):
        db.execute("DELETE FROM observed WHERE workspace=?", (workspace,))
        for path, content in files.items():
            db.execute("INSERT INTO observed VALUES (?,?,?,?)", (workspace, path, content["hash"], self._blob(db, content["text"])))

    def end(self, ident, workspace, started, before, after, result=None, error=None):
        with self.connect() as db:
            row = db.execute("SELECT tool FROM events WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise PCWError("Unknown analytics operation")
            result_bytes = len(json.dumps(result, ensure_ascii=False).encode()) if result is not None else 0
            # Do not recursively copy the journal into itself when it is queried.
            logged_result = {"analytics_response_bytes": result_bytes} if row["tool"].startswith("analytics_") else result
            db.execute("UPDATE events SET finished_at=?, duration_ms=?, state=?, result=?, error=?, result_bytes=? WHERE id=?",
                (now(), (time.monotonic() - started) * 1000, "error" if error is not None else "completed",
                 self._blob(db, logged_result), self._blob(db, error) if error is not None else None, result_bytes, ident))
            if isinstance(result, dict):
                db.execute("UPDATE events SET cycle_id=coalesce(cycle_id,?),task_id=coalesce(task_id,?) WHERE id=?",
                           (result.get("cycle_id"), result.get("task_id"), ident))
            for path in (before.keys() | after.keys()) if after is not None else ():
                old, current = before.get(path), after.get(path)
                if old and current and old["hash"] == current["hash"]:
                    continue
                db.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?)", (ident, path, "during_call",
                    old["hash"] if old else None, current["hash"] if current else None,
                    self._blob(db, old["text"]) if old else None, self._blob(db, current["text"]) if current else None))
            if after is not None:
                self._observe(db, workspace, after)

    def query(self, workspace=None, cycle_id=None, task_id=None, tool=None, since=None, until=None, offset=0, limit=50, import_id=None):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise PCWError("Use a nonnegative offset and limit between 1 and 100")
        where, args = [], []
        for name, value in {"workspace": workspace, "cycle_id": cycle_id, "task_id": task_id, "tool": tool, "import_id": import_id}.items():
            if value is not None:
                where.append(name + "=?")
                args.append(value)
        for op, value in ((">=", since), ("<=", until)):
            if value is not None:
                where.append("started_at" + op + "?")
                args.append(value)
        condition = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events" + condition + " ORDER BY started_at,id LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
            totals = dict(db.execute("SELECT count(*) AS calls, sum(state='error') AS errors, sum(state='started') AS unknown_outcomes, "
                "sum(duration_ms) AS duration_ms, sum(result_bytes) AS result_bytes FROM events" + condition, args).fetchone())
        return {"events": [dict(row) for row in rows], "totals": totals,
                "tokens": None, "cost": None, "measurement_limit": "PCW calls only; started events have an unconfirmed outcome"}

    def read(self, event_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            if row is None:
                raise PCWError("Unknown analytics event")
            result = dict(row)
            for field in ("params", "result", "error"):
                if result[field]:
                    blob = db.execute("SELECT * FROM blobs WHERE id=?", (result[field],)).fetchone()
                    result[field] = {"value": json.loads(blob["text"]), "redactions": blob["redactions"], "truncated": False}
            result["versions"] = [dict(value) for value in db.execute("SELECT * FROM versions WHERE event_id=?", (event_id,))]
            return result

    def blob_read(self, blob_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM blobs WHERE id=?", (blob_id,)).fetchone()
            if row is None:
                raise PCWError("Unknown analytics body")
            return {"id": blob_id, "value": json.loads(row["text"]), "redactions": row["redactions"], "truncated": False}


class AnalyticsMixin:
    def _events(self):
        return EventStore(self.engine.work_root)

    def analytics_query(self, target_workspace: str | None = None, cycle_id: str | None = None,
                        task_id: str | None = None, tool: str | None = None, since: str | None = None,
                        until: str | None = None, offset: int = 0, limit: int = 50, import_id: str | None = None):
        return self._events().query(target_workspace, cycle_id, task_id, tool, since, until, offset, limit, import_id)

    def analytics_read(self, event_id: str):
        return self._events().read(event_id)

    def analytics_blob_read(self, blob_id: str):
        return self._events().blob_read(blob_id)

    def analytics_evaluate(self, criterion: str, assessment: str, event_ids: list[str]):
        if not criterion.strip() or not assessment.strip() or not event_ids:
            raise PCWError("Evaluation requires a criterion, assessment and evidence event IDs")
        events = self._events()
        ident = uuid.uuid4().hex
        with events.connect() as db:
            for event_id in event_ids:
                if not db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone():
                    raise PCWError("Evaluation references an unknown event")
            clean, redactions = redact({"criterion": criterion, "assessment": assessment})
            db.execute("INSERT INTO evaluations VALUES (?,?,?,?,?)", (ident, now(), clean["criterion"], clean["assessment"], json.dumps(event_ids)))
        return {"evaluation_id": ident, "status": "saved", "redactions": redactions, "kind": "analysis_not_observed_fact"}

    def analytics_import(self, source_path: str, adapter: str, user_request: str, session_id: str | None = None):
        """Import one explicitly selected transcript. Never discover other sessions."""
        from .session_import import read_session
        if not isinstance(user_request, str) or not user_request.strip():
            raise PCWError("An explicit transcript import request is required")
        path = Path(source_path)
        if not path.is_absolute() or not path.is_file():
            raise PCWError("Select an existing absolute transcript path")
        if path.stat().st_size > 100 * 1024 * 1024:
            raise PCWError("Transcript exceeds 100 MiB; select an explicit smaller transcript export")
        parsed = read_session(path, adapter, session_id)
        store = self._events()
        # Re-importing a growing session adds new events, not duplicates of old ones.
        ident = hashlib.sha256(json.dumps([adapter, parsed["session_id"], str(path.resolve())]).encode()).hexdigest()
        inserted = 0
        with store.connect() as db:
            for record in parsed["records"]:
                clean, _ = redact(record)
                event_id = hashlib.sha256(json.dumps([ident, clean], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                timestamp = record["timestamp"] if isinstance(record["timestamp"], str) else "unknown"
                blob = store._blob(db, {"transcript_record": record, "session_id": parsed["session_id"],
                                       "correlation": "unmatched; no actor or MCP event inferred from timestamps"})
                cursor = db.execute("INSERT OR IGNORE INTO events(id,workspace,tool,mode,started_at,state,result,source,source_event_id,import_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (event_id, self.engine.root.name, "session:" + str(record["kind"]), "import", timestamp, "imported",
                     blob, adapter, record["id"], ident))
                inserted += cursor.rowcount
            db.execute("INSERT INTO imports VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET imported_at=excluded.imported_at,records=excluded.records",
                       (ident, adapter, str(path), parsed["session_id"], now(), len(parsed["records"])))
        return {"import_id": ident, "session_id": parsed["session_id"], "imported_events": inserted,
                "recognized_records": len(parsed["records"]), "ignored_records": parsed["ignored"], "status": "imported",
                "scope": "selected transcript only; its workspace association is analytical, not proven provenance"}
