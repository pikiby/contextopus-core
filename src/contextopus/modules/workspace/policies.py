"""Machine-readable workspace settings. Missing permissions stay restrictive."""

from __future__ import annotations

import yaml

from .runtime import PCWError


DEFAULTS = {
    "allow_implicit_updates": False,
    "knowledge_approval_required": True,
    "git_history_enabled": False,
    "material_max_tokens": None,
    "create_required_sources": False,
}


def policies(content: str, *, creation: bool = False) -> dict:
    if not isinstance(content, str):
        raise PCWError("INSTRUCTIONS content must be text")
    result = dict(DEFAULTS)
    supplied = set()
    lines = content.splitlines()
    if lines and lines[0] == "---":
        try:
            end = lines.index("---", 1)
            node = yaml.compose("\n".join(lines[1:end]), Loader=yaml.SafeLoader)
        except (ValueError, yaml.YAMLError) as exc:
            raise PCWError("Invalid INSTRUCTIONS.md frontmatter") from exc
        if node is not None and not isinstance(node, yaml.MappingNode):
            raise PCWError("INSTRUCTIONS.md frontmatter must be a mapping")
        for key, value in node.value if node else []:
            if not isinstance(key, yaml.ScalarNode) or key.value not in DEFAULTS:
                continue
            name = key.value
            if name in supplied:
                raise PCWError(f"Duplicate setting: {name}")
            supplied.add(name)
            if name == "material_max_tokens":
                if (
                    isinstance(value, yaml.ScalarNode)
                    and value.tag == "tag:yaml.org,2002:null"
                ):
                    result[name] = None
                elif (
                    isinstance(value, yaml.ScalarNode)
                    and value.tag == "tag:yaml.org,2002:int"
                    and value.value.isascii()
                    and value.value.isdecimal()
                    and int(value.value) > 0
                ):
                    result[name] = int(value.value)
                else:
                    raise PCWError(
                        "material_max_tokens must be a positive integer or null"
                    )
            else:
                if (
                    not isinstance(value, yaml.ScalarNode)
                    or value.tag != "tag:yaml.org,2002:bool"
                    or value.value.lower() not in {"true", "false"}
                ):
                    raise PCWError(f"{name} must be one boolean true or false")
                result[name] = value.value.lower() == "true"
    if creation and supplied != set(DEFAULTS):
        raise PCWError(
            "Creation requires all five settings explicitly supplied in INSTRUCTIONS, including the source-link choice: "
            + ", ".join(DEFAULTS)
        )
    return result
