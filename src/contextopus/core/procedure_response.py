"""Attach live operation contracts to procedure text without executing operations."""
import yaml


def enrich_procedure(result, registry, normalize):
    if not isinstance(result, dict) or not isinstance(result.get("content"), str):
        return result
    result = dict(result)
    content = result["content"]
    names = result.pop("operation_names", None)
    if content.startswith("---\n"):
        parts = content.split("---\n", 2)
        if len(parts) != 3:
            raise ValueError("Procedure YAML header is missing its closing delimiter")
        _, header, body = parts
        metadata = yaml.safe_load(header) or {}
        if isinstance(metadata, dict) and "operations" in metadata:
            names = metadata["operations"]
            result["content"] = body.lstrip("\n")
    if names is None:
        return result  # Older third-party procedures remain readable.
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError("Procedure operations must be a list of registered operation names")
    definitions, missing = [], []
    for name in dict.fromkeys(normalize(n) for n in names):
        spec = registry._operations.get(name)
        if spec is None:
            missing.append(name)
        else:
            definitions.append(registry._describe_spec(spec))
    result["operations"] = definitions
    result["call_contract"] = {
        "coordinates": "Pass the selected context name outside arguments. Storage is configured by the server; do not pass a filesystem path.",
        "parameters": "For read/write, put operation parameters inside arguments. For finish, pass them directly to the finish tool.",
        "instruction": "Use the attached definitions. Obtain a missing signature through guide(operation=...). A signature does not replace a procedure or grant approval.",
    }
    if missing:
        result["status"] = "incomplete"
        result["unavailable_operations"] = missing
        result["warning"] = "Do not guess or execute unavailable operations. Check module availability and obtain a compatible procedure."
    return result
