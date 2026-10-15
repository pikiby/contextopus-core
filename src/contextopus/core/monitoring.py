"""Bounded read-only observations of the central process and persisted stores."""

from datetime import datetime, timedelta, timezone
from contextlib import closing
import os
import sqlite3
import time
from pathlib import Path
from .settings import Settings


class RootServices:
    def __init__(self, layout, resources, registry):
        self.layout, self.resources, self.registry = layout, resources, registry
        self._settings = Settings(layout)
        self._cpu_sample = None
        self.runtime_mcp = {"server": "unknown", "verified_client": "unknown"}

    def _resources(self):
        result = {
            "owner": "Contextopus service",
            "pid": os.getpid(),
            "cpu_percent": None,
            "memory_bytes": None,
            "memory_percent": None,
        }
        try:
            fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            now = time.monotonic()
            online = sum(
                1
                for line in Path("/proc/stat").read_text().splitlines()
                if line.split()[0].startswith("cpu") and line.split()[0][3:].isdigit()
            )
            if self._cpu_sample and online:
                previous, stamp = self._cpu_sample
                if now > stamp:
                    result["cpu_percent"] = (
                        100
                        * (ticks - previous)
                        / os.sysconf("SC_CLK_TCK")
                        / (now - stamp)
                        / online
                    )
            self._cpu_sample = (ticks, now)
            result["memory_bytes"] = int(
                Path("/proc/self/statm").read_text().split()[1]
            ) * os.sysconf("SC_PAGE_SIZE")
            total = (
                int(
                    next(
                        line.split()[1]
                        for line in Path("/proc/meminfo").read_text().splitlines()
                        if line.startswith("MemTotal:")
                    )
                )
                * 1024
            )
            result["memory_percent"] = 100 * result["memory_bytes"] / total
        except (OSError, ValueError, IndexError, StopIteration):
            pass
        return result

    def _usage(self):
        result = {
            "period": "last_24_hours",
            "requests": None,
            "errors": None,
            "empty_results": None,
            "average_seconds": None,
        }
        path = self.layout.analytics / "operations.sqlite3"
        if not path.is_file():
            return result
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                count, errors, duration = db.execute(
                    "SELECT count(*),sum(CASE WHEN outcome='error' THEN 1 ELSE 0 END),avg(duration) FROM operations WHERE julianday(started)>=julianday(?) AND operation NOT IN ('core.status','core.settings')",
                    (since,),
                ).fetchone()
            result.update(requests=count, errors=errors or 0, average_seconds=duration)
        except sqlite3.Error as exc:
            result["error"] = str(exc)
        return result

    def _data(self):
        from .rag import RagIndex

        try:
            stored = RagIndex.stored_status(self.layout)
        except Exception as exc:
            stored = {
                "state": "error",
                "documents": None,
                "chunks": None,
                "error": str(exc),
            }
        directory = self.layout.workspace_rag
        size = (
            sum(
                p.stat().st_size
                for p in directory.rglob("*")
                if p.is_file() and not p.is_symlink()
            )
            if directory.is_dir()
            else None
        )
        return {
            "state": stored["state"],
            "stored_items": stored.get("documents"),
            "bytes": size,
            "chunks": stored.get("chunks"),
            "error": stored.get("error"),
        }

    def status(self):
        modules = [
            dict(metadata)
            for metadata in self.registry.modules.values()
            if metadata.get("available")
        ]
        with self.registry._activity_lock:
            activity = list(self.registry.active_operations.values())
        data = self._data()
        return {
            "state": "error" if data["error"] else "processing" if activity else "idle",
            "scope": str(self.layout.root),
            "database": data,
            "index": {
                "state": data["state"],
                "processed": data["stored_items"],
                "total": None,
                "remaining": None,
            },
            "resources": self._resources(),
            "processing": {
                "rate_per_minute": None,
                "seconds_per_item": None,
                "eta_seconds": None,
            },
            "usage": self._usage(),
            "mcp": dict(self.runtime_mcp),
            "modules": modules,
        }

    def settings(self):
        return self._settings.snapshot()

    def preview_settings(self, changes):
        return self._settings.preview(changes)

    def apply_settings(self, preview_revision):
        return self._settings.apply(preview_revision)
