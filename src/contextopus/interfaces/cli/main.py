"""CLI transport: all domain operations use Application's shared registry."""

from __future__ import annotations
import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys


def parser():
    result = argparse.ArgumentParser(
        prog="contextopus",
        description="Persistent context for people and coding agents",
    )
    result.add_argument("--version", action="version", version="Contextopus " + version("contextopus-core"))
    result.add_argument(
        "--root", type=Path, help="Persistent data root (or CONTEXTOPUS_ROOT)"
    )
    result.add_argument("--workspace", help="Explicitly selected Workspace")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "doctor", "mcp", "tui"):
        commands.add_parser(name)
    modules = commands.add_parser("modules", help="List and manage root-local modules")
    module_actions = modules.add_subparsers(dest="module_action")
    for action in ("install", "prepare", "enable", "disable", "update"):
        command = module_actions.add_parser(action)
        command.add_argument("module")
        if action == "update":
            command.add_argument("--source", required=True, type=Path)
    root_binding = commands.add_parser(
        "root", help="Inspect or explicitly bind the persistent default data root"
    )
    root_binding.add_argument("--set", dest="new_root", type=Path)
    service = commands.add_parser("service")
    service.add_argument("action", choices=("start", "stop", "restart", "status", "install"))
    reconnect = commands.add_parser("reconnect", help="Refresh an existing native client connection")
    reconnect.add_argument("client", choices=("codex", "claude-code", "opencode", "crush"))
    reconnect.add_argument("--socket", type=Path)
    reconnect.add_argument("--thread", dest="thread_id")
    reconnect.add_argument("--client-url", help="Existing OpenCode server URL")
    reconnect.add_argument("--directory", type=Path, help="Project in the existing OpenCode server")
    settings = commands.add_parser("settings")
    settings.add_argument(
        "--set", dest="changes", help="JSON object of proposed values"
    )
    settings.add_argument(
        "--apply", action="store_true", help="Apply the displayed preview"
    )
    model = commands.add_parser(
        "setupmodel", help="Inspect hardware or preview/apply atomic embedding setup"
    )
    model.add_argument(
        "--hardware",
        action="store_true",
        help="Explicit PyTorch/CUDA/MPS diagnostic; no weights loaded",
    )
    model.add_argument(
        "--config", type=Path, help="Validated embedding provider/profile JSON file"
    )
    model.add_argument(
        "--chunking", type=Path, help="Explicit tokenizer/chunking JSON file"
    )
    model.add_argument(
        "--device",
        default="auto",
        help="auto, cpu, cuda[:index] or mps; remote providers use auto",
    )
    model.add_argument(
        "--apply",
        action="store_true",
        help="Apply reviewed settings through an atomic index rebuild",
    )
    relocation = commands.add_parser("relocation")
    relocation.add_argument("destination", type=Path)
    relocation.add_argument("--apply", action="store_true")
    integration = commands.add_parser("integrate")
    integration.add_argument(
        "client", choices=("codex", "claude-code", "opencode", "crush")
    )
    integration_scope = integration.add_mutually_exclusive_group(required=True)
    integration_scope.add_argument("--project", type=Path)
    integration_scope.add_argument(
        "--user", action="store_true", help="Merge the native user configuration"
    )
    integration.add_argument(
        "--native-plugin",
        action="store_true",
        help="Codex user cutover after native plugin installation; preserve old cache",
    )
    integration.add_argument(
        "--config-only",
        action="store_true",
        help="Reuse already discoverable shared skills; install no second copy",
    )
    integration.add_argument(
        "--legacy-skills",
        type=Path,
        help="Explicit old manually installed skill directory to upgrade; never a plugin cache",
    )
    integration.add_argument("--apply", action="store_true")
    for name in ("query", "execute"):
        operation = commands.add_parser(name)
        operation.add_argument("operation")
        operation.add_argument("--arguments", default="{}")
    return result


def root_binding_path():
    from platformdirs import user_config_path

    return user_config_path("Contextopus", appauthor=False) / "root.json"


def default_root():
    from platformdirs import user_data_path

    if os.environ.get("CONTEXTOPUS_ROOT"):
        return Path(os.environ["CONTEXTOPUS_ROOT"])
    binding = root_binding_path()
    if binding.is_file():
        value = json.loads(binding.read_text(encoding="utf-8"))
        selected = Path(value["root"])
        if not selected.is_absolute():
            raise ValueError("Configured root must be absolute")
        return selected
    return user_data_path("Contextopus", appauthor=False)


def bind_root(root):
    import tempfile
    from contextopus.core.storage import StorageLayout

    root = StorageLayout.resolve(root).root
    path = root_binding_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".root-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"root": str(root)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "root": str(root),
        "binding": str(path),
        "environment_override": bool(os.environ.get("CONTEXTOPUS_ROOT")),
    }


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = (
            (
                args.root
                or (
                    args.new_root
                    if args.command == "root" and args.new_root
                    else default_root()
                )
            )
            .expanduser()
            .resolve()
        )
        if args.command == "root":
            emit(
                bind_root(args.new_root)
                if args.new_root
                else {"root": str(root), "binding": str(root_binding_path())}
            )
            return 0
        if args.command == "service":
            from contextopus.integrations import service

            emit(getattr(service, args.action)(root))
            return 0
        if args.command == "reconnect":
            from contextopus.integrations.reconnect import reconnect
            emit(reconnect(args.client, root, socket=args.socket, thread_id=args.thread_id,
                           client_url=args.client_url, directory=args.directory))
            return 0
        if args.command == "integrate":
            from contextopus.integrations import plan, integrate

            preview = plan(
                args.client,
                Path.home() if args.user else args.project,
                scope="user" if args.user else "project",
                install_skills=not args.config_only,
                native_plugin=args.native_plugin,
                legacy_skills=args.legacy_skills,
                root=root,
            )
            # Configuration content may contain credentials from other entries.
            emit(
                {
                    "client": args.client,
                    "removals": preview.get("removals", []),
                    "preserved": preview.get("preserved", []),
                    "module_errors": preview.get("module_errors", []),
                    "files": [
                        {"path": item["path"], "changed": item["changed"]}
                        for item in preview["writes"]
                    ],
                }
            )
            if args.apply:
                emit(integrate(preview))
            return 0
        if args.command == "mcp":
            from contextopus.interfaces.mcp.server import run

            run(root=root, transport="streamable-http", host="127.0.0.1", port=8765)
            return 0
        from contextopus.integrations.service import start, status
        from contextopus.integrations.remote import RemoteApplication

        if args.command == "init":
            from contextopus.integrations.service import install
            install(root)
        elif (
            args.command in ("status", "doctor") and status(root)["state"] == "stopped"
        ):
            emit({**status(root), "root_exists": root.is_dir(), "root": str(root)})
            return 0
        app = RemoteApplication(root, context=args.workspace)
        if args.command == "tui":
            from contextopus.interfaces.tui import run

            try:
                run(app)
            finally:
                app.close()
            return 0
        try:
            if args.command == "setupmodel":
                if args.hardware:
                    if args.apply or args.config or args.chunking:
                        raise ValueError(
                            "--hardware is a diagnostic; use a separate setup preview/apply"
                        )
                    emit(app.query("core.model_hardware"))
                else:
                    arguments = {"device": args.device}
                    if args.config:
                        arguments["config"] = json.loads(
                            args.config.read_text(encoding="utf-8")
                        )
                    if args.chunking:
                        arguments["chunking"] = json.loads(
                            args.chunking.read_text(encoding="utf-8")
                        )
                    preview = app.query("core.model_plan", arguments)
                    emit(preview)
                    if args.apply:
                        emit(app.execute("core.model_apply", {"plan": preview}))
            elif args.command == "settings":
                if args.changes:
                    preview = app.services.preview_settings(json.loads(args.changes))
                    emit(preview)
                    if args.apply:
                        emit(app.services.apply_settings(preview["preview_revision"]))
                elif args.apply:
                    raise ValueError("--apply requires --set")
                else:
                    emit(app.services.settings())
            elif args.command in ("query", "execute"):
                emit(
                    getattr(app, args.command)(
                        args.operation, json.loads(args.arguments)
                    )
                )
            elif args.command == "relocation":
                preview = app.query(
                    "core.relocation_plan",
                    {"destination": str(args.destination.resolve())},
                )
                emit(preview)
                if args.apply:
                    emit(
                        app.execute(
                            "core.relocation_apply",
                            {"plan_revision": preview["revision"]},
                        )
                    )
            elif args.command == "modules":
                if args.module_action:
                    arguments = {"module": args.module}
                    if args.module_action == "update":
                        arguments["source"] = str(args.source.expanduser().resolve())
                    emit(app.execute("core.module_" + args.module_action, arguments))
                else:
                    emit(app.query("core.modules"))
            elif args.command in ("init", "doctor"):
                emit(
                    app.execute("core.init")
                    if args.command == "init"
                    else app.query("core.doctor")
                )
            else:
                emit(app.services.status())
        finally:
            app.close()
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"contextopus: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
