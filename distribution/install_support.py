"""Standard-library helpers for the fresh-install starter candidate."""

from __future__ import annotations

import errno
import codecs
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request


class InstallError(RuntimeError):
    """A failed precondition or an incomplete installation."""


CLIENTS = ("codex", "claude-code", "cursor", "opencode", "crush", "hermes")
ENDPOINT = "http://127.0.0.1:8765"
MIN_UV = (0, 13, 1)


def default_root(*, platform=None, home=None, environment=None):
    platform, home = platform or sys.platform, Path(home or Path.home())
    environment = os.environ if environment is None else environment
    if platform == "win32":
        base = Path(environment.get("LOCALAPPDATA", home / "AppData/Local"))
    elif platform == "darwin":
        base = home / "Library/Application Support"
    else:
        base = Path(environment.get("XDG_DATA_HOME", home / ".local/share"))
    return base / "Contextopus"


def binding_path(*, platform=None, home=None, environment=None):
    platform, home = platform or sys.platform, Path(home or Path.home())
    environment = os.environ if environment is None else environment
    if platform == "win32":
        base = Path(environment.get("LOCALAPPDATA", home / "AppData/Local"))
    elif platform == "darwin":
        base = home / "Library/Application Support"
    else:
        base = Path(environment.get("XDG_CONFIG_HOME", home / ".config"))
    return base / "Contextopus/root.json"


def tool_paths(directory, bin_directory, *, platform=None):
    prefix = Path(directory) / "contextopus-core"
    windows = (platform or sys.platform) == "win32"
    executable = "contextopus.exe" if windows else "contextopus"
    return {
        "prefix": prefix,
        "python": prefix / ("Scripts/python.exe" if windows else "bin/python"),
        "executable": prefix / ("Scripts" if windows else "bin") / executable,
        "entrypoint": Path(bin_directory) / executable,
    }


def json_documents(text):
    """CLI preview/apply commands emit multiple complete JSON documents."""
    decoder, values, offset = json.JSONDecoder(), [], 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset == len(text):
            break
        try:
            value, offset = decoder.raw_decode(text, offset)
        except ValueError as exc:
            raise InstallError("The Core command returned invalid JSON output") from exc
        values.append(value)
    if not values:
        raise InstallError("The Core command returned no JSON result")
    return values


def command(argv, *, timeout=7200):
    """Stream progress on stderr while retaining a separate JSON stdout stream."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"}}
    try:
        process = subprocess.Popen(
            list(map(str, argv)), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, env=environment,
        )
    except OSError as exc:
        raise InstallError(f"Could not complete {Path(str(argv[0])).name}: {exc}") from exc

    stdout, stderr_tail, errors = [], bytearray(), []

    def drain(stream, progress):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while data := stream.read1(4096):
                if progress:
                    stderr_tail.extend(data)
                    del stderr_tail[:-8192]
                    sys.stderr.write(decoder.decode(data))
                    sys.stderr.flush()
                else:
                    stdout.append(data)
            if progress:
                sys.stderr.write(decoder.decode(b"", final=True))
                sys.stderr.flush()
        except (OSError, ValueError) as exc:
            errors.append(exc)

    readers = [threading.Thread(target=drain, args=(process.stdout, False), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, True), daemon=True)]
    for reader in readers:
        reader.start()
    interrupted = None
    try:
        process.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        interrupted = exc
        process.kill()
        process.wait()
    finally:
        for reader in readers:
            reader.join(timeout=3)
        for stream in (process.stdout, process.stderr):
            stream.close()
    if isinstance(interrupted, KeyboardInterrupt):
        raise interrupted
    if interrupted:
        raise InstallError(f"{Path(str(argv[0])).name} timed out; partial state was retained") from interrupted
    if errors or any(reader.is_alive() for reader in readers):
        raise InstallError("Could not read complete command output; partial state was retained")
    if process.returncode:
        detail = stderr_tail.decode("utf-8", errors="replace").strip()[-3000:]
        raise InstallError(
            f"{Path(str(argv[0])).name} exited with status {process.returncode}"
            + (": " + detail if detail else "")
        )
    return b"".join(stdout).decode("utf-8", errors="replace")


def health():
    """Probe only loopback. An occupied/non-Contextopus port is never 'free'."""
    try:
        connection = socket.create_connection(("127.0.0.1", 8765), timeout=2)
    except ConnectionRefusedError:
        return None
    except OSError as exc:
        if exc.errno == errno.ECONNREFUSED:
            return None
        raise InstallError(f"Cannot establish whether local port 8765 is free: {exc}") from exc
    connection.close()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(ENDPOINT + "/health", timeout=3) as response:
            value = json.loads(response.read(65537))
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise InstallError("Local port 8765 is occupied; this installer will not replace its owner") from exc
    if (not isinstance(value, dict) or not isinstance(value.get("root"), str)
            or type(value.get("pid")) is not int or value["pid"] <= 0):
        raise InstallError("Local port 8765 has an unrecognized owner")
    return value


def require_owner(root, value):
    if value is None or Path(value.get("root", "")).resolve() != Path(root).resolve():
        raise InstallError("The MCP owner does not match the selected data root")
    if type(value.get("pid")) is not int or value["pid"] <= 0:
        raise InstallError("The MCP owner has no valid process identity")


def fresh_root(root):
    root = Path(root)
    if root.is_symlink():
        raise InstallError("The data root must not be a symlink")
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        receipt = root / ".contextopus-starter-install.json"
        suffix = f" Review the retained receipt: {receipt}." if receipt.is_file() else ""
        raise InstallError("This candidate requires a new or empty data root." + suffix
                           + " Existing installations are not overwritten or migrated.")


def native_preflight(run, *, platform=None, home=None, environment=None):
    """Refuse singleton service definitions and check the native user manager."""
    platform, home = platform or sys.platform, Path(home or Path.home())
    environment = os.environ if environment is None else environment
    if platform.startswith("linux"):
        path = Path(environment.get("XDG_CONFIG_HOME", home / ".config")) / "systemd/user/contextopus.service"
        if path.exists() or path.is_symlink():
            raise InstallError(f"An existing native service definition must be reviewed first: {path}")
        run(["systemctl", "--user", "show-environment"], timeout=30)
    elif platform == "darwin":
        path = home / "Library/LaunchAgents/org.contextopus.mcp.plist"
        if path.exists() or path.is_symlink():
            raise InstallError(f"An existing native service definition must be reviewed first: {path}")
        run(["launchctl", "print", f"gui/{os.getuid()}"], timeout=30)
    elif platform == "win32":
        # Query's nonzero exit is expected when this named task is absent.
        try:
            result = subprocess.run(["schtasks", "/Query", "/TN", "Contextopus MCP"],
                                    capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError(f"Cannot inspect the native Task Scheduler: {exc}") from exc
        if result.returncode == 0:
            raise InstallError("An existing Contextopus MCP scheduled task must be reviewed first")
        # Confirm the manager works, distinguishing a missing task from access failure.
        run(["schtasks", "/Query", "/FO", "CSV", "/NH"], timeout=30)
    else:
        raise InstallError("This candidate supports Linux, macOS and Windows native user services only")


def preflight(root, run=command, probe=health, *, require_git=True):
    fresh_root(root)
    binding = binding_path()
    if binding.is_symlink():
        raise InstallError(f"Existing root binding symlink must be reviewed first: {binding}")
    binding_fingerprint = hashlib.sha256(binding.read_bytes()).hexdigest() if binding.is_file() else None
    if binding.exists():
        try:
            value = json.loads(binding.read_text(encoding="utf-8"))
            bound = Path(value["root"]).expanduser()
            if not bound.is_absolute():
                raise ValueError("not absolute")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise InstallError(f"Existing root binding must be reviewed first: {binding}") from exc
        if bound.exists() or bound.is_symlink():
            raise InstallError(f"The default binding already points to an existing root: {bound}")
    overridden = os.environ.get("CONTEXTOPUS_ROOT")
    if overridden and Path(overridden).expanduser().resolve() != root:
        raise InstallError("CONTEXTOPUS_ROOT points elsewhere; review it before a fresh installation")
    if require_git:
        git = shutil.which("git")
        if not git:
            raise InstallError("Git is required by the selected module bundle. Install Git separately and retry; this installer does not install it.")
        try:
            git_version = run([git, "--version"], timeout=30).strip()
        except InstallError as exc:
            raise InstallError("Git must be working before this starter bundle is installed; check git --version and retry") from exc
        if not re.match(r"git version \d+\.", git_version):
            raise InstallError("Git did not report a recognizable version; check git --version before retrying")
    uv = shutil.which("uv")
    if not uv:
        raise InstallError("uv >= 0.13.1 must be available on PATH")
    version = run([uv, "--version"], timeout=30).strip()
    match = re.match(r"uv (\d+)\.(\d+)\.(\d+)(?:\s|$)", version)
    if not match or tuple(map(int, match.groups())) < MIN_UV:
        raise InstallError("This installer requires uv >= 0.13.1")
    directory = Path(run([uv, "tool", "dir"], timeout=30).strip()).expanduser()
    bin_directory = Path(run([uv, "tool", "dir", "--bin"], timeout=30).strip()).expanduser()
    if not directory.is_absolute() or not bin_directory.is_absolute():
        raise InstallError("uv returned nonabsolute tool directories")
    paths = tool_paths(directory, bin_directory)
    prefix = paths["prefix"].resolve()
    if root == prefix or root.is_relative_to(prefix) or prefix.is_relative_to(root):
        raise InstallError("Keep the persistent data root outside the Core tool environment")
    if paths["prefix"].exists() or paths["prefix"].is_symlink():
        raise InstallError(f"The Core tool environment already exists: {paths['prefix']}")
    for path in (paths["entrypoint"],):
        if path.exists() or path.is_symlink():
            raise InstallError(f"A contextopus executable already exists: {path}")
    conflict = shutil.which("contextopus")
    if conflict:
        raise InstallError(f"A contextopus executable is already on PATH: {conflict}")
    owner = probe()
    if owner is not None:
        raise InstallError(f"An MCP owner already uses local port 8765 (root {owner.get('root')}); no takeover is attempted")
    native_preflight(run)
    return {"uv": uv, "binding_path": binding,
            "binding_fingerprint": binding_fingerprint, **paths}


def require_ok(value, *, label, allowed=("ok",)):
    if not isinstance(value, dict) or value.get("status") not in allowed:
        status = value.get("status") if isinstance(value, dict) else type(value).__name__
        raise InstallError(f"{label} did not complete successfully (status {status!r})")


def require_setup(value):
    """Check all module hook results without naming any module in the installer."""
    good = {"ok", "ready", "installed", "current", "initialized", "complete", "completed"}

    def visit(item, path):
        if isinstance(item, dict):
            if item.get("error") or item.get("errors"):
                raise InstallError(f"Module setup is incomplete at {path}")
            if "status" in item and item["status"] not in good:
                raise InstallError(f"Module setup is incomplete at {path}: {item['status']}")
            for key, child in item.items():
                visit(child, path + "." + key)
        elif isinstance(item, list):
            for number, child in enumerate(item):
                visit(child, f"{path}[{number}]")
    setup = value.get("setup")
    if not isinstance(setup, dict):
        raise InstallError("Model application did not report module setup results")
    visit(setup, "setup")


def require_modules(rows, modules, bundle_root):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise InstallError("Core returned an invalid module catalog")
    indexed = {row.get("id"): row for row in rows}
    for module in modules:
        row = indexed.get(module["id"], {})
        if (row.get("state") != "enabled" or row.get("version") != module["version"]
                or row.get("error")):
            raise InstallError(f"Module {module['id']} is not enabled at the bundled version")
        storage = row.get("storage", {})
        if storage.get("errors") or storage.get("compatible") is False or storage.get("needs_migration"):
            raise InstallError(f"Module {module['id']} storage is not ready")
        manifest = json.loads((Path(bundle_root) / module["path"] / "module.json").read_text(encoding="utf-8"))
        if "service" in manifest:
            service = row.get("service", {})
            if service.get("state") != "running" or service.get("error"):
                raise InstallError(f"Module {module['id']} service is not running")


def save_receipt(path, value, *, exclusive=False):
    """Persist partial state, never remove or claim to roll back user resources."""
    if exclusive:
        with Path(path).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        return
    fd, temporary = tempfile.mkstemp(prefix=".starter-receipt-", dir=Path(path).parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
