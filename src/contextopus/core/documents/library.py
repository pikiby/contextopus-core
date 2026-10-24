"""Read-only library contribution for Core-owned instruction records."""
import re


def _summary(record):
    return {"key": ["core", "instructions", record["id"]],
            "title": record.get("title", record["id"]),
            "description": record.get("description", ""), "type": "instruction",
            "path": "core/instructions/" + record.get("path", ""),
            "revision": record.get("revision")}


def browse_instructions(library, action, collection="", query="", mode="text",
                        type="", offset=0, limit=40, id=""):
    """List, search or read shared instructions without modifying their sources."""
    if action not in {"collections", "records", "record"}:
        raise ValueError("Unknown library action")
    if mode not in {"text", "semantic"}:
        raise ValueError("Unknown search mode")
    if not 1 <= limit <= 100 or offset < 0 or offset > 100000:
        raise ValueError("Invalid pagination")
    if collection not in {"", "instructions"}:
        raise ValueError("Unknown Core collection")
    if action == "collections":
        return {"collections": [{"id": "instructions", "title": "Shared instructions"}]}
    if action == "record":
        if not id:
            raise ValueError("Record id is required")
        record = library.read(id)
        links = []
        refs = list(record.get("metadata", {}).get("instructions", {}).values())
        refs += re.findall(r"\[\[[^\[\]\n]+\]\]", record["content"])
        seen = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            try:
                name = ref[2:-2].split("|", 1)[0].split("#", 1)[0]
                name = name.removeprefix("core/instructions/")
                target = library.read(name)
                links.append({"key": ["core", "instructions", target["id"]],
                              "title": target["title"], "description": target["description"]})
            except (ValueError, FileNotFoundError):
                links.append({"title": ref, "reference": ref, "unavailable": True})
        return {**_summary(record), "content": record["content"],
                "metadata": record.get("metadata", {}), "links": links}
    if type and type != "instruction":
        return {"records": [], "total": 0, "has_more": False, "types": ["instruction"]}
    diagnostics = None
    if mode == "semantic" and query.strip():
        response = library.search(query)
        records = []
        for hit in response.get("results", []):
            metadata = hit.get("metadata", {})
            record = {"id": hit["key"][2], "title": metadata.get("title", hit["key"][2]),
                      "description": hit.get("description", metadata.get("description", "")),
                      "path": hit.get("path", ""), "revision": hit.get("revision")}
            records.append({**_summary(record), "distance": hit.get("distance")})
        diagnostics = response.get("diagnostics")
    else:
        records = [_summary(r) for r in library.list()["instructions"]]
        needle = query.strip().casefold()
        records = [r for r in records if needle in (r["title"] + " " + r["description"]).casefold()]
        records.sort(key=lambda r: (r["title"].casefold(), r["key"]))
    result = {"records": records[offset:offset + limit], "total": len(records),
              "has_more": offset + limit < len(records), "types": ["instruction"]}
    if diagnostics is not None:
        result["diagnostics"] = diagnostics
    return result
