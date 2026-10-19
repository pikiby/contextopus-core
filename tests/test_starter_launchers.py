"""Exercise the Unix launcher without downloads or an application installation."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "distribution/install.sh"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Unix shell launcher")


def prepare(tmp_path):
    folder = tmp_path / "starter with spaces"
    folder.mkdir()
    shutil.copy2(SOURCE, folder / "install.sh")
    (folder / "install.py").write_text(
        "import json, sys; print(json.dumps(sys.argv[1:]))\n", encoding="utf-8"
    )
    return folder


def test_plan_forwards_arguments_without_uv(tmp_path):
    folder = prepare(tmp_path)
    arguments = ["--plan", "--root", str(tmp_path / "data with spaces"), "--client", "codex"]
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    result = subprocess.run(
        ["sh", str(folder / "install.sh"), *arguments], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == arguments
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == before


def test_existing_uv_receives_exact_script_and_choices(tmp_path):
    folder = prepare(tmp_path)
    commands = tmp_path / "commands"
    commands.mkdir()
    uv = commands / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    uv.chmod(0o755)
    env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(
        ["sh", str(folder / "install.sh"), "--yes", "--root", str(tmp_path / "new data")],
        env=env, capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == [
        "run", "--no-project", "--no-config", "--python", "3.12", "python", "-B",
        str(folder / "install.py"), "--yes", "--root", str(tmp_path / "new data"),
    ]


def test_plan_without_python_does_not_bootstrap(tmp_path):
    folder = prepare(tmp_path)
    commands = tmp_path / "commands"
    commands.mkdir()
    for name in ("python", "python3"):
        executable = commands / name
        executable.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        executable.chmod(0o755)
    env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(
        ["sh", str(folder / "install.sh"), "--plan", "--yes"], env=env,
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Nothing was installed" in result.stderr
    assert "Download uv" not in result.stdout
