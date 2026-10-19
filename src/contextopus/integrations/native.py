"""Merge native MCP configuration and Agent Skills without replacing other entries.

Project scope is explicit; Hermes uses native user/profile homes. TOML and YAML
comments survive; unsupported formats are refused rather than rewritten
incorrectly. A differing existing server or skill is a collision.
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
    "hermes": ("config.yaml", "skills", "mcp_servers"),
}


def _digest(content: bytes | None) -> str:
    return hashlib.sha256(content).hexdigest() if content is not None else "missing"


def _encoded_content(content):
    try:
        return {"content": content.decode('utf-8')}
    except UnicodeDecodeError:
        import base64
        return {"content_base64": base64.b64encode(content).decode('ascii')}


def plan(
    client: str,
    project: str | Path,
    *,
    scope: str = "project",
    install_skills: bool = True,
    native_plugin: bool = False,
    legacy_skills: str | Path | None = None,
    endpoint: str = "http://127.0.0.1:8765/mcp",
    root: str | Path | None = None,
    hermes_home: str | Path | None = None,
) -> dict:
    if client not in CLIENTS:
        raise ValueError(f"Unknown client: {client}")
    module_skills_requested = install_skills and root is not None
    project = Path(project).expanduser().resolve()
    if scope not in {"project", "user"}:
        raise ValueError("Integration scope must be project or user")
    if hermes_home is not None and client != "hermes":
        raise ValueError("--hermes-home applies only to Hermes")
    if client == "hermes" and scope != "user":
        raise ValueError("Hermes supports user scope; use --user and optionally --hermes-home for a native profile")
    config_name, skills_name, section = CLIENTS[client]
    if client == "hermes":
        from .hermes import resolve_home

        native_home = resolve_home(project, hermes_home)
        config, skills_root = native_home / config_name, native_home / skills_name
    elif scope == "user":
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
    if client == "hermes":
        # Hermes otherwise fabricates resource/prompt tools even when the MCP
        # server intentionally provides only its four operation tools.
        server["tools"] = {"resources": False, "prompts": False}
    elif client == "claude-code":
        server["type"] = "http"
    elif client == "opencode":
        server = {"type": "remote", "url": endpoint, "enabled": True}
    elif client == "crush":
        server["type"] = "http"
    original = config.read_bytes() if config.exists() else None
    if client == "hermes":
        from .hermes import merge_config

        # Validate before planning any skill changes; preserve the original YAML.
        content = merge_config(original, server)
        data = {}
    elif client == "codex":
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
    elif client != "hermes":
        content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    writes = [(config, original, content)]
    managed_base = native_home if client == "hermes" else project
    managed_path = managed_base / ".contextopus" / (client + "-integration.json")
    managed_prior = managed_path.read_bytes() if managed_path.exists() else None
    managed = json.loads(managed_prior) if managed_prior else {"skills": {}}
    hashes = dict(managed.get("skills", {}))
    source = files("contextopus").joinpath("resources", "skills")
    known = json.loads(files("contextopus").joinpath("resources", "legacy_skill_hashes.json").read_text())
    canonical_names = set()
    for skill in (
        sorted(source.iterdir(), key=lambda item: item.name) if install_skills else []
    ):
        if not skill.is_dir():
            continue
        canonical_names.add(skill.name)
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
    module_hashes = {}
    module_errors = []
    if module_skills_requested:
        from contextopus.core.module_management import ModuleManifestReader
        from contextopus.core.storage import StorageLayout
        directories, _, module_errors = ModuleManifestReader(StorageLayout(root)).inspect_sources('skills')
        occupied_names = {item.name.casefold() for item in source.iterdir() if item.is_dir()}
        for directory in directories:
            if not directory.is_dir():
                continue
            for skill in sorted(directory.iterdir()):
                if not skill.is_dir() or not (skill / 'SKILL.md').is_file():
                    continue
                if skill.name.casefold() in occupied_names:
                    raise IntegrationConflict('Module skill name collision: ' + skill.name)
                occupied_names.add(skill.name.casefold())
                canonical_names.add(skill.name)
                for asset in sorted(skill.rglob('*')):
                    if not asset.is_file():
                        continue
                    target = skills_root / skill.name / asset.relative_to(skill)
                    content = asset.read_bytes()
                    prior = target.read_bytes() if target.exists() else None
                    relative = target.relative_to(project).as_posix() if target.is_relative_to(project) else str(target)
                    known_entrypoint = (asset == skill / 'SKILL.md' and prior is not None
                        and _digest(prior.replace(b'\r\n', b'\n')) in known.get(skill.name, []))
                    if prior is not None and prior != content and managed.get('skills', {}).get(relative) != _digest(prior) and not known_entrypoint:
                        raise IntegrationConflict('Module skill file collision: ' + str(target))
                    hashes[relative] = module_hashes[relative] = _digest(content)
                    writes.append((target, prior, content))
    retired, preserved = [], []
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
            if legacy_root == skills_root and name in canonical_names:
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
    if module_skills_requested:
        for relative in sorted(set(managed.get('module_skills', {})) - set(module_hashes)):
            target = Path(relative) if Path(relative).is_absolute() else project / relative
            if not target.is_relative_to(skills_root):
                raise IntegrationConflict('Managed module skill path escapes skill directory')
            if not target.is_file():
                hashes.pop(relative, None)
                continue
            prior = target.read_bytes()
            if _digest(prior) != managed['module_skills'][relative]:
                preserved.append({'path': str(target), 'reason': 'user_modified_or_unrecognized'})
            else:
                retired.append({'path': str(target), 'expected': _digest(prior)})
                hashes.pop(relative, None)
    else:
        module_hashes = dict(managed.get('module_skills', {}))
    # A former built-in skill can also appear in the module ownership receipt.
    # Its removal must be applied once after the module is disabled.
    retired = list({item['path']: item for item in retired}.values())
    managed_content = (
        json.dumps({"skills": hashes, "module_skills": module_hashes}, sort_keys=True, indent=2) + "\n"
    ).encode()
    writes.append((managed_path, managed_prior, managed_content))
    return {
        "client": client,
        "scope": scope,
        "project": str(project),
        "removals": retired,
        "preserved": preserved,
        "module_errors": module_errors,
        "writes": [
            {
                "path": str(path),
                "expected": _digest(prior),
                **_encoded_content(content),
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
            with os.fdopen(fd, "wb") as stream:
                if "content_base64" in item:
                    import base64
                    stream.write(base64.b64decode(item["content_base64"]))
                else:
                    stream.write(item["content"].encode("utf-8"))
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
