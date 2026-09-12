#!/usr/bin/env python3
"""Launch the bundled runtime with explicitly installed, reusable dependencies."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def interpreter_path(environment: dict[str, str]) -> Path:
    explicit = environment.get("PCW_PYTHON")
    if explicit:
        return Path(explicit).expanduser()
    data_root = Path(environment.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    executable = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return data_root / "persistent-context-workspace" / "venv" / executable


def main() -> None:
    environment = dict(os.environ)
    interpreter = interpreter_path(environment)
    if not interpreter.is_absolute() or not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        print(
            "PCW runtime interpreter is unavailable: " + str(interpreter)
            + ". Install the plugin dependencies in the dedicated environment described in README.md,"
            " or set PCW_PYTHON to an absolute executable path. Startup never installs dependencies.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    plugin_root = Path(__file__).resolve().parents[1]
    environment["PYTHONPATH"] = str(plugin_root) + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if sys.argv[1:] == ["--check"]:
        action = (
            "import lancedb, pyarrow, yaml; import pcw_runtime.server\n"
            "print('PCW runtime dependencies import successfully; the embedding model was not loaded.')"
        )
        arguments = []
    else:
        action = "from pcw_runtime.__main__ import main\nmain()"
        arguments = sys.argv[1:]
    bootstrap = (
        "import sys\ntry:\n" + "\n".join("    " + line for line in action.splitlines())
        + "\nexcept ImportError as error:\n"
        "    print('PCW runtime dependency is unavailable: ' + str(error) + "
        "'. Install the plugin package in the selected environment as described in README.md; "
        "startup never installs dependencies.', file=sys.stderr)\n"
        "    raise SystemExit(2)\n"
    )
    command = [str(interpreter), "-c", bootstrap, *arguments]
    try:
        os.execve(str(interpreter), command, environment)
    except OSError as error:
        print("PCW runtime could not start: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
