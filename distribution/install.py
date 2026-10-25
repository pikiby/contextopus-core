"""Install a verified Contextopus bundle into a fresh root."""

from __future__ import annotations

import sys

# Bundle validation rejects unlisted files. Imports must not create bytecode.
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from bundle import BundleError, load_bundle
from install_support import (
    CLIENTS, InstallError, command, default_root, fresh_root, health,
    json_documents, preflight, require_modules, require_ok, require_owner,
    require_setup, save_receipt,
)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="New/empty persistent data directory")
    parser.add_argument("--client", action="append", choices=("none", *CLIENTS),
                        help="Optional native user adapter; repeat for several clients")
    parser.add_argument("--module", action="append", dest="modules",
                        help="Install a bundled module ID; repeat for a subset, or use none for Core only (default: all)")
    parser.add_argument("--skip-model", action="store_true",
                        help="Install the local runtime but defer model download; search will not be ready")
    parser.add_argument("--plan", action="store_true",
                        help="Read/validate the bundle and print a plan only; no commands, network or changes")
    parser.add_argument("--yes", action="store_true", help="Apply noninteractively with the selected options")
    return parser


def selected_clients(values):
    values = values or []
    if "none" in values and len(values) != 1:
        raise InstallError("--client none cannot be combined with another client")
    return list(dict.fromkeys(value for value in values if value != "none"))


def selected_manifest(manifest, values=None):
    """Keep one verified bundle format for full, subset and Core-only installs."""
    if values is None:
        return manifest
    if 'none' in values:
        if len(values) != 1:
            raise InstallError('--module none cannot be combined with another module')
        values = []
    wanted = set(values)
    available = {item['id'] for item in manifest['modules']}
    if wanted - available:
        raise InstallError('Module is not in this bundle: ' + ', '.join(sorted(wanted - available)))
    return {**manifest, 'modules': [item for item in manifest['modules'] if item['id'] in wanted]}


def choose(args, input_fn=input):
    if not args.yes and not args.plan:
        if args.root is None:
            entered = input_fn(f"New data directory [{default_root()}]: ").strip()
            args.root = Path(entered) if entered else default_root()
        if args.client is None:
            print("Native client (optional): 0 none, 1 Codex, 2 Claude Code, 3 Cursor, 4 OpenCode, 5 Crush, 6 Hermes")
            print("Enter names or numbers separated by commas; blank means none.")
            choices = {str(index + 1): name for index, name in enumerate(CLIENTS)}
            choices.update({name: name for name in CLIENTS})
            choices.update({"0": "none", "none": "none"})
            entered = input_fn("Client(s): ").strip().lower()
            try:
                args.client = [choices[part.strip()] for part in entered.split(",")] if entered else ["none"]
            except KeyError as exc:
                raise InstallError("Unknown client choice; rerun with a listed name or number") from exc
    original_root = args.root if args.root is not None else default_root()
    if original_root.expanduser().is_symlink():
        raise InstallError("The data root must not be a symlink")
    return {"root": str(original_root.expanduser().resolve()),
            "clients": selected_clients(args.client), "skip_model": args.skip_model,
            "device": "cpu"}


def make_plan(bundle_root, manifest, options):
    manifest = selected_manifest(manifest, options.get('modules'))
    root = options["root"]
    core = str(Path(bundle_root) / manifest["core"]["path"]) + "[local]"
    commands = [["uv", "tool", "install", "--python", manifest["python"],
                 "--torch-backend", "cpu", core], ["contextopus", "--root", root, "init"]]
    commands.extend(["contextopus", "--root", root, "modules", "install", item["id"]]
                    for item in manifest["modules"])
    if not options["skip_model"]:
        commands.extend([["contextopus", "--root", root, "setupmodel", "--device", "cpu"],
                         ["contextopus", "--root", root, "setupmodel", "--device", "cpu", "--apply"]])
    for client in options["clients"]:
        commands.extend([["contextopus", "--root", root, "integrate", client, "--user"],
                         ["contextopus", "--root", root, "integrate", client, "--user", "--apply"]])
    commands.append(["contextopus", "root", "--set", root])
    return {
        "acceptance": "Platform service, model and native-client readiness must be verified on the target machine",
        "bundle_version": manifest["bundle_version"], "options": options,
        "modules": [{"id": item["id"], "version": item["version"]} for item in manifest["modules"]],
        "effects": ["Fresh per-user Core tool environment and CPU local dependencies",
                    "New data root and copied module packages",
                    "Native user service installation/start at 127.0.0.1:8765",
                    "Explicit module storage preparation and activation",
                    "Model download/setup" if not options["skip_model"] else "Model deferred: search is not ready",
                    "Selected native user configuration/skills; client reload remains necessary",
                    "Default root binding written after successful verification"],
        "commands": commands,
        "limits": "Requires a fresh installation. Partial failures are retained with a receipt; automatic resume/rollback is not implemented.",
    }


class Installer:
    def __init__(self, bundle_root, manifest, options, *, run=command, probe=health,
                 check=preflight, output=print):
        self.bundle_root, self.manifest, self.options = Path(bundle_root), selected_manifest(manifest, options.get('modules')), options
        self.root, self.run, self.probe, self.check, self.output = Path(options["root"]), run, probe, check, output
        self.receipt_path = self.root / ".contextopus-starter-install.json"
        self.receipt = None
        self.paths = None

    def cli(self, *args):
        return json_documents(self.run([self.paths["executable"], "--root", self.root, *args]))

    def step(self, name, operation):
        self.receipt["active_step"] = name
        save_receipt(self.receipt_path, self.receipt)
        self.output(f"[{name}]", flush=True)
        result = operation()
        self.receipt["completed_steps"].append(name)
        self.receipt["active_step"] = None
        save_receipt(self.receipt_path, self.receipt)
        return result

    def copy_modules(self):
        target = self.root / "modules"
        target.mkdir()
        for module in self.manifest["modules"]:
            shutil.copytree(self.bundle_root / module["path"], target / module["id"])

    def runtime(self):
        wheel = self.bundle_root / self.manifest["core"]["path"]
        self.run([self.paths["uv"], "tool", "install", "--python", self.manifest["python"],
                  "--torch-backend", "cpu", str(wheel) + "[local]"])
        if not self.paths["python"].is_file() or not self.paths["executable"].is_file():
            raise InstallError("uv did not create the expected private Core interpreter/entrypoint")
        probe = (
            "import importlib.metadata as m,json,pathlib; d=m.distribution('contextopus-core');"
            "print(json.dumps({'version':d.version,'source':str(pathlib.Path(d.locate_file('contextopus/startup.py')).resolve())}))"
        )
        value = json_documents(self.run([self.paths["python"], "-I", "-c", probe]))[-1]
        if (value.get("version") != self.manifest["core"]["version"]
                or not Path(value.get("source", "")).resolve().is_relative_to(self.paths["prefix"].resolve())):
            raise InstallError("Installed Core identity resolves outside its new tool environment")
        version = self.run([self.paths["executable"], "--version"]).strip()
        if version != "Contextopus " + self.manifest["core"]["version"]:
            raise InstallError("The private Core executable has an unexpected version")

    def initialize(self):
        value = self.cli("init")[-1]
        require_ok(value, label="Core initialization", allowed=("initialized",))
        require_owner(self.root, self.probe())

    def install_module(self, module):
        value = self.cli("modules", "install", module["id"])[-1]
        if not isinstance(value, dict) or value.get("id") != module["id"] or value.get("state") != "enabled":
            raise InstallError(f"Module {module['id']} installation did not return enabled")

    def model(self):
        preview = self.cli("setupmodel", "--device", "cpu")[-1]
        if not isinstance(preview, dict) or preview.get("applied") is not False or preview.get("selected_device") != "cpu":
            raise InstallError("Model setup did not return the requested CPU preview")
        self.output(json.dumps({"model_preview": preview}, ensure_ascii=False, indent=2))
        documents = self.cli("setupmodel", "--device", "cpu", "--apply")
        if len(documents) < 2:
            raise InstallError("Model apply did not return both its preview and result")
        result = documents[-1]
        require_ok(result, label="Model application")
        require_setup(result)
        search = self.cli("query", "core.search", "--arguments",
                          json.dumps({"query": "Contextopus installation verification", "limit": 1}))[-1]
        if not isinstance(search, dict) or not isinstance(search.get("results"), list):
            raise InstallError("The verified model did not complete a Core search read")

    def verify(self):
        require_owner(self.root, self.probe())
        rows = self.cli("query", "core.modules")[-1]
        require_modules(rows, self.manifest["modules"], self.bundle_root)
        procedure = self.cli("query", "procedure", "--arguments", '{"name":"modules"}')[-1]
        if not isinstance(procedure, dict) or procedure.get("name") != "modules" or not procedure.get("content"):
            raise InstallError("The installed Core module guide could not be read")
        status = self.cli("query", "core.status")[-1]
        if not isinstance(status, dict) or status.get("scope") != str(self.root) or status.get("state") == "error":
            raise InstallError("Core status does not confirm the selected healthy root")

    def client(self, client):
        preview = self.cli("integrate", client, "--user")[-1]
        if not isinstance(preview, dict) or preview.get("module_errors") or not isinstance(preview.get("files"), list):
            raise InstallError(f"Client {client} integration preview is incomplete")
        self.output(json.dumps({"integration_preview": preview}, ensure_ascii=False, indent=2))
        documents = self.cli("integrate", client, "--user", "--apply")
        if len(documents) < 2 or not isinstance(documents[-1], dict):
            raise InstallError(f"Client {client} did not return an integration result")
        applied_preview, result = documents[-2:]
        if (not isinstance(applied_preview, dict) or applied_preview.get("module_errors")
                or result.get("client") != client or not isinstance(result.get("written"), list)
                or not isinstance(result.get("removed"), list)):
            raise InstallError(f"Client {client} integration did not complete")

    def bind(self):
        require_owner(self.root, self.probe())
        binding = self.paths.get("binding_path")
        if binding is not None:
            current = hashlib.sha256(binding.read_bytes()).hexdigest() if binding.is_file() else None
            if binding.is_symlink() or current != self.paths["binding_fingerprint"]:
                raise InstallError("The default root binding changed during installation; it was preserved")
        value = self.cli("root", "--set", str(self.root))[-1]
        if not isinstance(value, dict) or value.get("root") != str(self.root):
            raise InstallError("The final default root binding was not confirmed")

    def apply(self):
        bundle_root = self.bundle_root.resolve()
        if self.root == bundle_root or self.root.is_relative_to(bundle_root):
            raise InstallError("Choose a data directory outside the extracted bundle")
        self.paths = self.check(self.root, self.run, self.probe, require_git=bool(self.manifest['modules']))
        # Recheck immediately before reserving ownership, after read-only probes.
        fresh_root(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipt = {
            "schema_version": 1, "status": "installing",
            "bundle_fingerprint": hashlib.sha256((self.bundle_root / "bundle.json").read_bytes()).hexdigest(),
            "bundle_version": self.manifest["bundle_version"], "options": self.options,
            "core_tool_directory": str(self.paths["prefix"]),
            "core_executable": str(self.paths["executable"]),
            "completed_steps": [], "active_step": None,
            "automatic_resume": False,
        }
        save_receipt(self.receipt_path, self.receipt, exclusive=True)
        try:
            self.step("copy_modules", self.copy_modules)
            self.step("install_runtime", self.runtime)
            self.step("initialize_core_and_user_service", self.initialize)
            for module in self.manifest["modules"]:
                self.step("install_module:" + module["id"], lambda module=module: self.install_module(module))
            if not self.options["skip_model"]:
                self.step("setup_cpu_model_and_search", self.model)
            self.step("verify_core_and_module_catalog", self.verify)
            for client in self.options["clients"]:
                self.step("integrate_client:" + client, lambda client=client: self.client(client))
            self.step("bind_default_root", self.bind)
            self.receipt.update(status="installed", search_ready=not self.options["skip_model"],
                                clients_require_reload=self.options["clients"])
            save_receipt(self.receipt_path, self.receipt)
            return self.receipt
        except BaseException as exc:
            self.receipt.update(status="failed", failed_step=self.receipt.get("active_step"),
                                error=str(exc), search_ready=False)
            try:
                save_receipt(self.receipt_path, self.receipt)
            except OSError:
                self.output(f"Could not update the receipt; retain the partial root at {self.root}")
            raise


def main(argv=None, *, bundle_root=None, input_fn=input):
    args = arguments().parse_args(argv)
    root = Path(bundle_root or Path(__file__).resolve().parent)
    try:
        manifest = load_bundle(root)
        options = choose(args, input_fn)
        options['modules'] = [item['id'] for item in selected_manifest(manifest, args.modules)['modules']]
        plan = make_plan(root, manifest, options)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        if args.plan:
            return 0
        if not args.yes:
            answer = input_fn("Install into this fresh root and apply these changes? [y/N]: ").strip().lower()
            if answer not in {"y", "yes"}:
                print("No installation changes were made.")
                return 0
        installer = Installer(root, manifest, options)
        try:
            result = installer.apply()
        except BaseException:
            if installer.receipt is not None:
                print(f"Partial installation retained. Receipt: {installer.receipt_path}", file=sys.stderr)
                print("Automatic resume and rollback are not implemented. Do not rerun a fresh install into this root; review the receipt and continue only with reviewed standard Contextopus commands.", file=sys.stderr)
            raise
        print("Installed: " + options["root"])
        print("CLI executable: " + str(installer.paths["executable"]))
        print("uv command directory: " + str(installer.paths["entrypoint"].parent)
              + " (add it to PATH if necessary; no PATH changes were made)")
        if not result["search_ready"]:
            print("Model setup was skipped. Search is NOT ready; review and run setupmodel --device cpu, then --apply, later.")
        if options["clients"]:
            print("Reload the selected clients and verify a real read. Writing configuration does not confirm client readiness.")
        print("Receipt: " + str(installer.receipt_path))
        return 0
    except (BundleError, InstallError, ValueError, OSError, KeyboardInterrupt, EOFError) as exc:
        print(f"Starter installation did not complete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
