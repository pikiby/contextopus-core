"""Deterministic source checks. Semantic judgments belong to the audit skill."""
from __future__ import annotations

from .runtime import PCWError, _parse, _revision


class AuditMixin:
    def audit(self, cycle_id: str | None = None, offset: int = 0, limit: int = 50):
        self._require_format()
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise PCWError("Use a nonnegative offset and limit between 1 and 100")
        with self._cycle(cycle_id) if cycle_id else self.control.guard():
            paths = sorted(self.engine.knowledge.rglob("*.md"))
            by_id, bodies, rows = {}, {}, []
            for path in paths:
                self.engine._assert_safe(path)
                ident = path.name
                text = path.read_bytes().decode("utf-8")
                issues = []
                try:
                    metadata, body = _parse(text)
                    links = metadata.get("links", [])
                    if not isinstance(links, list) or any(not isinstance(value, str) for value in links):
                        raise PCWError("links must be a list of filename IDs")
                    digest = _revision(body)
                    if digest in bodies and body.strip():
                        issues.append({"problem": "duplicate_body", "related_material": bodies[digest],
                                       "fragment": body, "basis": "Literal body equality; semantic merge is not inferred"})
                    bodies[digest] = ident
                except Exception as exc:
                    body, links = text, []
                    issues.append({"problem": "invalid_material", "fragment": text, "basis": str(exc)})
                if ident in by_id:
                    issues.append({"problem": "duplicate_id", "fragment": ident,
                                   "basis": "Filename IDs must be unique", "related_path": by_id[ident]})
                by_id[ident] = path.relative_to(self.engine.root).as_posix()
                rows.append({"material_id": ident, "path": by_id[ident], "revision": _revision(body),
                             "file_revision": _revision(text), "links": links, "issues": issues})
            selected = rows[offset:offset + limit]
            for row in selected:
                for target in row.pop("links"):
                    if target not in by_id:
                        row["issues"].append({"problem": "missing_link_target", "fragment": target,
                                              "basis": "No material with this exact filename ID exists"})
                for issue in row["issues"]:
                    issue["verification"] = "observed"
            return {"materials": selected, "total": len(rows),
                    "next_offset": offset + limit if offset + limit < len(rows) else None,
                    "scope": "literal format, filename identity, exact duplicates and link existence",
                    "semantic_audit": "Agent must assess requested meaning against current instructions and evidence; no automatic semantic verdict"}
