"""Conservative, source-preserving edits to native Hermes YAML configuration.

PyYAML validates the complete document. Source marks let us insert one mapping
without rewriting unrelated settings, comments, or credential values. YAML
aliases, duplicate keys and complex/flow mappings that need editing are refused
so a preview can never silently reinterpret an existing configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.tokens import AliasToken, AnchorToken, TagToken

from .native import IntegrationConflict


def resolve_home(user_home: Path, explicit_home: str | Path | None = None) -> Path:
    """Mirror stable Hermes platform/env defaults without importing its runtime."""
    override = explicit_home if explicit_home is not None else os.environ.get("HERMES_HOME", "").strip()
    if override:
        return Path(os.path.expandvars(str(override))).expanduser().resolve()
    suffix = os.environ.get("HERMES_DATA_DIR_SUFFIX", "")
    if sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(appdata) if appdata else user_home / "AppData" / "Local"
        return (base / ("hermes" + suffix)).resolve()
    return (user_home / (".hermes" + suffix)).resolve()


def _validate(node):
    if isinstance(node, MappingNode):
        keys = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise IntegrationConflict("Hermes YAML requires string mapping keys; configuration was preserved")
            if key.value in keys:
                raise IntegrationConflict("Duplicate Hermes YAML mapping key; configuration was preserved")
            keys.add(key.value)
            _validate(value)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _validate(item)


def merge_config(original: bytes | None, server: dict) -> bytes:
    """Add the Contextopus HTTP server or return matching YAML byte-for-byte."""
    try:
        text = original.decode("utf-8") if original is not None else ""
        if any(isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in yaml.scan(text)):
            raise IntegrationConflict("Hermes YAML aliases, anchors and explicit tags require the native editor; configuration was preserved")
        node = yaml.compose(text)
        if node is not None:
            _validate(node)
        data = yaml.safe_load(text) if node is not None else {}
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise IntegrationConflict("Malformed or unsupported Hermes YAML; configuration was preserved") from error
    if not isinstance(data, dict) or (node is not None and not isinstance(node, MappingNode)):
        raise IntegrationConflict("Native Hermes configuration must be an object")
    if node is not None and node.flow_style and node.value:
        raise IntegrationConflict("Hermes YAML flow-style root requires the native editor; configuration was preserved")

    def finish(candidate):
        expected = {**data, "mcp_servers": {**data.get("mcp_servers", {}), "contextopus": server}}
        try:
            matches = yaml.safe_load(candidate) == expected
        except yaml.YAMLError:
            matches = False
        if not matches:
            raise IntegrationConflict("Unsupported Hermes YAML layout requires the native editor; configuration was preserved")
        return candidate.encode("utf-8")

    newline = "\r\n" if "\r\n" in text else "\n"
    def dump(value):
        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).replace("\n", newline)

    entry = dump({"contextopus": server})
    servers_node, servers_key = None, None
    if node is not None:
        servers_key, servers_node = next(((key, value) for key, value in node.value if key.value == "mcp_servers"), (None, None))
    if servers_node is not None:
        servers = data["mcp_servers"]
        if not isinstance(servers, dict) or not isinstance(servers_node, MappingNode):
            raise IntegrationConflict("Native mcp_servers must be an object")
        if "contextopus" in servers:
            existing = servers["contextopus"]
            if existing == server:
                return original
            # Upgrade the original URL-only adapter definition additively.
            # Explicit/custom tool filters and other server definitions remain
            # collisions; their meaning belongs to the user's native config.
            if existing != {"url": server["url"]}:
                raise IntegrationConflict("MCP name contextopus already has a different definition")
            contextopus_node = next(value for key, value in servers_node.value if key.value == "contextopus")
            if servers_node.flow_style or contextopus_node.flow_style:
                raise IntegrationConflict("Hermes YAML flow-style contextopus update requires the native editor; configuration was preserved")
            addition = dump({key: value for key, value in server.items() if key not in existing})
            indent = contextopus_node.start_mark.column
            position = text.rfind("\n", 0, contextopus_node.start_mark.index) + 1
            insertion = "".join(" " * indent + line for line in addition.splitlines(keepends=True))
            return finish(text[:position] + insertion + text[position:])
        if servers_node.flow_style and servers_node.value:
            raise IntegrationConflict("Hermes YAML flow-style mcp_servers requires the native editor; configuration was preserved")
        if servers_node.value:
            indent = servers_node.start_mark.column
            position = text.rfind("\n", 0, servers_node.start_mark.index) + 1
            insertion = "".join(" " * indent + line for line in entry.splitlines(keepends=True))
            return finish(text[:position] + insertion + text[position:])
        # Empty flow mapping: retain surrounding text, including inline comments.
        insertion = newline + "".join(" " * (servers_key.start_mark.column + 2) + line for line in entry.splitlines(keepends=True))
        return finish(text[:servers_node.start_mark.index] + insertion + text[servers_node.end_mark.index:])

    indent = node.start_mark.column if node is not None else 0
    insertion = "mcp_servers:" + newline + "".join(" " * (indent + 2) + line for line in entry.splitlines(keepends=True))
    if node is not None and node.flow_style:  # Empty root {}.
        return finish(text[:node.start_mark.index] + insertion + text[node.end_mark.index:])
    position = node.end_mark.index if node is not None else len(text)
    prefix = text[:position]
    if prefix and not prefix.endswith("\n"):
        prefix += newline
    return finish(prefix + " " * indent + insertion + text[position:])
