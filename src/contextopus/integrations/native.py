"""Merge native MCP configuration and Agent Skills without replacing other entries.

Project scope is explicit. TOML comments survive; JSONC is refused rather than
rewritten incorrectly. A differing existing server or skill is a collision.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
import os
from importlib.resources import files
from pathlib import Path
import tempfile


class IntegrationConflict(ValueError):
    pass


CLIENTS = {
    "codex": (".codex/config.toml", ".agents/skills", "mcp_servers"),
    "claude-code": (".mcp.json", ".claude/skills", "mcpServers"),
    "opencode": ("opencode.json", ".opencode/skills", "mcp"),
    "crush": ("crush.json", ".agents/skills", "mcp"),
}


def _digest(content: bytes | None) -> str:
    return hashlib.sha256(content).hexdigest() if content is not None else "missing"


def plan(
    client: str,
    project: str | Path,
    *,
    scope: str = "project",
    install_skills: bool = True,
    native_plugin: bool = False,
    legacy_skills: str | Path | None = None,
    endpoint: str = "http://127.0.0.1:8765/mcp",
) -> dict:
    if client not in CLIENTS:
        raise ValueError(f"Unknown client: {client}")
    project = Path(project).expanduser().resolve()
    if scope not in {"project", "user"}:
        raise ValueError("Integration scope must be project or user")
    config_name, skills_name, section = CLIENTS[client]
    if scope == "user":
        config_base = (
            Path(os.environ.get("LOCALAPPDATA", str(project / "AppData/Local")))
            if os.name == "nt"
            else Path(os.environ.get("XDG_CONFIG_HOME", str(project / ".config")))
        )
        user_paths = {
            "codex": (project / ".codex/config.toml", project / ".agents/skills"),
            "claude-code": (project / ".claude.json", project / ".claude/skills"),
            "opencode": (
                config_base / "opencode/opencode.json",
                config_base / "opencode/skills",
            ),
            "crush": (config_base / "crush/crush.json", config_base / "crush/skills"),
        }
        config, skills_root = user_paths[client]
    else:
        config, skills_root = project / config_name, project / skills_name
    if client == "opencode" and config.with_suffix(".jsonc").exists():
        config = config.with_suffix(".jsonc")
    server = {"url": endpoint}
    if client == "claude-code":
        server["type"] = "http"
    elif client == "opencode":
        server = {"type": "remote", "url": endpoint, "enabled": True}
    elif client == "crush":
        server["type"] = "http"
    original = config.read_bytes() if config.exists() else None
    if client == "codex":
        import tomlkit

        data = tomlkit.parse(original.decode() if original is not None else "")
    else:
        try:
            data = json.loads(original) if original else {}
        except json.JSONDecodeError:
            raise IntegrationConflict(
                "JSONC comments/trailing commas require the native client editor; configuration was preserved"
            ) from None
    if not isinstance(data, dict):
        raise IntegrationConflict("Native configuration must be an object")
    if native_plugin and (client != "codex" or scope != "user"):
        raise ValueError(
            "Native plugin cutover applies only to Codex user configuration"
        )
    servers = data.setdefault(section, {})
    if not isinstance(servers, dict):
        raise IntegrationConflict(f"Native {section} must be an object")
    if "contextopus" in servers and servers["contextopus"] != server:
        raise IntegrationConflict(
            "MCP name contextopus already has a different definition"
        )
    if native_plugin:
        # Plugin manager installs the new cache first. Only configuration is
        # changed here; removing the old plugin through CLI would delete cache.
        installed = (
            project
            / f".codex/plugins/cache/contextopus/contextopus/{version('contextopus-core')}/.codex-plugin/plugin.json"
        )
        if (
            not installed.is_file()
            or json.loads(installed.read_text()).get("name") != "contextopus"
        ):
            raise IntegrationConflict(
                "Install contextopus@contextopus through the native Codex plugin manager before cutover"
            )
        servers.pop("contextopus", None)
        plugins = data.setdefault("plugins", {})
        plugins.setdefault(
            "persistent-context-workspace@persistent-context-workspace", {}
        )["enabled"] = False
        plugins.setdefault("contextopus@contextopus", {})["enabled"] = True
        data.get("marketplaces", {}).pop("persistent-context-workspace", None)
        install_skills = False
    else:
        servers["contextopus"] = server
    if client == "codex":
        content = tomlkit.dumps(data).encode()
    else:
        content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    writes = [(config, original, content)]
    managed_path = project / ".contextopus" / (client + "-integration.json")
    managed_prior = managed_path.read_bytes() if managed_path.exists() else None
    managed = json.loads(managed_prior) if managed_prior else {"skills": {}}
    hashes = dict(managed.get("skills", {}))
    source = files("contextopus").joinpath("resources", "skills")
    known = json.loads(files("contextopus").joinpath("resources", "legacy_skill_hashes.json").read_text())
    for skill in (
        sorted(source.iterdir(), key=lambda item: item.name) if install_skills else []
    ):
        if not skill.is_dir():
            continue
        target = skills_root / skill.name / "SKILL.md"
        skill_content = skill.joinpath("SKILL.md").read_bytes()
        prior = target.read_bytes() if target.exists() else None
        relative = (
            target.relative_to(project).as_posix()
            if target.is_relative_to(project)
            else str(target)
        )
        hashes[relative] = _digest(skill_content)
        if (
            prior is not None
            and prior != skill_content
            and managed.get("skills", {}).get(relative) != _digest(prior)
            and _digest(prior.replace(b"\r\n", b"\n")) not in known.get(skill.name, [])
        ):
            raise IntegrationConflict(f"Skill name collision: {skill.name} at {target}")
        writes.append((target, prior, skill_content))
    retired, preserved = [], []
    canonical_names = {item.name for item in source.iterdir() if item.is_dir()}
    legacy_roots = {skills_root} if install_skills or native_plugin else set()
    if legacy_skills is not None:
        legacy_roots.add(Path(legacy_skills).expanduser().resolve())
    for legacy_root in sorted(legacy_roots):
        if {".codex", "plugins", "cache"} <= set(legacy_root.parts):
            raise IntegrationConflict(
                "Active plugin caches must be preserved; update through the native plugin manager"
            )
        known = json.loads(
            files("contextopus")
            .joinpath("resources", "legacy_skill_hashes.json")
            .read_text()
        )
        for name, accepted in known.items():
            if install_skills and legacy_root == skills_root and name in canonical_names:
                continue
            target = legacy_root / name / "SKILL.md"
            if not target.exists():
                continue
            prior = target.read_bytes()
            relative = (
                target.relative_to(project).as_posix()
                if target.is_relative_to(project)
                else str(target)
            )
            if (
                _digest(prior.replace(b"\r\n", b"\n")) not in accepted
                and managed.get("skills", {}).get(relative) != _digest(prior)
            ):
                preserved.append({"path": str(target), "reason": "user_modified_or_unrecognized"})
                continue
            retired.append({"path": str(target), "expected": _digest(prior)})
            hashes.pop(relative, None)
    managed_content = (
        json.dumps({"skills": hashes}, sort_keys=True, indent=2) + "\n"
    ).encode()
    writes.append((managed_path, managed_prior, managed_content))
    return {
        "client": client,
        "scope": scope,
        "project": str(project),
        "removals": retired,
        "preserved": preserved,
        "writes": [
            {
                "path": str(path),
                "expected": _digest(prior),
                "content": content.decode(),
                "changed": prior != content,
            }
            for path, prior, content in writes
        ],
    }


def integrate(preview: dict) -> dict:
    """Apply an explicitly reviewed plan, rejecting stale inputs before any write."""
    for item in preview["writes"] + preview.get("removals", []):
        path = Path(item["path"])
        current = path.read_bytes() if path.exists() else None
        if _digest(current) != item["expected"]:
            raise IntegrationConflict(f"Configuration changed after preview: {path}")
    written = []
    for item in preview["writes"]:
        if not item["changed"]:
            continue
        path = Path(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".contextopus-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(item["content"])
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        written.append(str(path))
    removed = []
    for item in preview.get("removals", []):
        path = Path(item["path"])
        path.unlink()
        # Keep supporting/user files; remove the folder only when truly empty.
        if not any(path.parent.iterdir()):
            path.parent.rmdir()
        removed.append(str(path))
    return {"client": preview["client"], "written": written, "removed": removed,
            "preserved": preview.get("preserved", [])}
