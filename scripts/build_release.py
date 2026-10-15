"""Build versioned client bundles and checksums after python -m build."""

from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"


def main():
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    skills = ROOT / "src/contextopus/resources/skills"
    for client in ("codex", "claude-code", "opencode", "crush"):
        archive = destination / f"contextopus-{client}-{VERSION}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("LICENSE", "NOTICE"):
                bundle.write(ROOT / name, name)
            for path in sorted(skills.rglob("*")):
                if path.is_file():
                    bundle.write(path, "skills/" + path.relative_to(skills).as_posix())
            bundle.writestr(
                "INSTALL.txt",
                f"Install contextopus_core-{VERSION}-py3-none-any.whl first.\nRun: contextopus service start\nRun: contextopus integrate {client} --project <project>\nReview paths, then repeat with --apply.\nNative clients connect to http://127.0.0.1:8765/mcp.\n",
            )
    assets = sorted(
        path
        for path in destination.iterdir()
        if path.name != "SHA256SUMS" and path.is_file() and (VERSION in path.name)
    )
    (destination / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in assets
        )
    )
    print("\n".join(path.name for path in assets))


if __name__ == "__main__":
    main()
