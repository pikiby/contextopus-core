"""Bounded operation observations independent of module authoring or cycles.

Source/chat fields such as content, text and prompt are represented by size.
Secret-bearing fields are redacted before serialization. Failure
records contain only the exception class, not a potentially sensitive message.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import re
import sqlite3
import uuid
import threading

_CONTROLLERS = {}
_CONTROLLERS_LOCK = threading.Lock()


def _controller(root):
    key = str(root.resolve())
    with _CONTROLLERS_LOCK:
        return _CONTROLLERS.setdefault(
            key, {"lock": threading.RLock(), "destination": None}
        )


_SECRET_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
    "apikey",
    "cookie",
)
_TEXT_KEYS = {
    "content",
    "text",
    "body",
    "query",
    "prompt",
    "instruction",
    "instructions",
    "userrequest",
    "confirmation",
    "excerpt",
}


def sanitize(value, key="", _depth=0):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if any(part in normalized for part in _SECRET_PARTS):
        return "[REDACTED_SECRET]"
    if _depth > 12:
        return {"retained": False, "reason": "depth_limit"}
    if isinstance(value, str):
        if normalized in _TEXT_KEYS or len(value) > 4096:
            return {"retained": False, "characters": len(value)}
        if re.search(
            r"(?i)\b(?:bearer|basic)\s+\S+|://[^/\s]+@|[?&](?:api[_-]?key|token|password|secret)=",
            value,
        ):
            return "[REDACTED_SECRET]"
        return value
    if isinstance(value, dict):
        result = {
            str(k): sanitize(v, k, _depth + 1) for k, v in list(value.items())[:100]
        }
        if len(value) > 100:
            result["__omitted_entries__"] = len(value) - 100
        return result
    if isinstance(value, (list, tuple)):
        result = [sanitize(v, _depth=_depth + 1) for v in value[:100]]
        if len(value) > 100:
            result.append({"omitted_entries": len(value) - 100})
        return result
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None
    # Arbitrary object reprs can contain credentials or source material.
    return {"retained": False, "type": type(value).__name__}


class OperationJournal:
    def __init__(self, layout):
        self.layout = layout
        self._original_path = layout.analytics / "operations.sqlite3"
        self._controller = _controller(layout.root)

    @property
    def path(self):
        return self._controller["destination"] or self._original_path

    def rebind(self, destination_layout):
        """Forward subsequent observations after a verified relocation receipt.

        Relocation owns the root-wide lock and coherent observer snapshot. This
        method never buffers events; old journal objects share the forwarding
        target so an in-flight operation's finish reaches the new database.
        """
        with self._controller["lock"]:
            self._controller["destination"] = (
                destination_layout.analytics / "operations.sqlite3"
            )
            self.layout = destination_layout

    def _write(self, sql, parameters):
        with self._controller["lock"]:
            with self.connect() as db:
                db.execute(sql, parameters)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, started TEXT, operation TEXT, module TEXT, context TEXT, parameters TEXT, outcome TEXT, duration REAL, result TEXT, error TEXT)"
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS operations_started ON operations(started)"
                )
                from .search_history import initialize
                initialize(db)
                yield db
        finally:
            db.close()

    def begin(self, context, operation, parameters):
        ident = uuid.uuid4().hex
        from .search_history import begin
        with self._controller["lock"], self.connect() as db:
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)", (
                ident,
                datetime.now(timezone.utc).isoformat(),
                operation,
                operation.split(".")[0],
                getattr(context, "workspace", None),
                json.dumps(sanitize(parameters), allow_nan=False),
                "started",
                None,
                None,
                None,
            ))
            begin(db, ident, self.layout, context, operation, parameters)
        return ident

    def finish(self, ident, result=None, error=None, duration=None):
        from .search_history import finish
        if (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration < 0
        ):
            duration = None
        with self._controller["lock"], self.connect() as db:
            recorded = error is None and finish(db, ident, result)
            if recorded:
                # Candidate metadata has one owner; the generic event links it.
                result = {**result, "diagnostics": {
                    k: v for k, v in result["diagnostics"].items()
                    if k not in {"candidates", "nearby_rejected"}}, "search_event_id": ident}
            db.execute("UPDATE operations SET outcome=?,duration=?,result=?,error=? WHERE id=?", (
                "error" if error is not None else "ok",
                duration,
                json.dumps(sanitize(result), allow_nan=False)
                if error is None
                else None,
                type(error).__name__ if error is not None else None,
                ident,
            ))
        return bool(recorded)

    def summary(self):
        if not self.path.exists():
            return {
                "requests": None,
                "errors": None,
                "average_seconds": None,
                "period": "unknown",
            }
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            n, errors, duration = db.execute(
                "SELECT COUNT(*),SUM(CASE WHEN outcome='error' THEN 1 ELSE 0 END),"
                "AVG(CASE WHEN outcome IN ('ok','error') THEN duration END) "
                "FROM operations WHERE julianday(started) >= julianday(?)",
                (cutoff,),
            ).fetchone()
        finally:
            db.close()
        return {
            "requests": n,
            "errors": errors if n else 0,
            "average_seconds": duration,
            "period": "24h",
        }
