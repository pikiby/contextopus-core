"""Local Git transport; modules choose eligible objects and approval policy."""

import os
from pathlib import Path
import subprocess


class GitRepository:
    def __init__(self, root):
        self.root = Path(root)

    def command(self, *args, check=True):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        result = subprocess.run(
            [
                "git",
                "--literal-pathspecs",
                "-c",
                "core.hooksPath=" + os.devnull,
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(self.root),
                *args,
            ],
            env=environment,
            text=False,
            capture_output=True,
            check=False,
        )
        result.stdout = result.stdout.decode("utf-8")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
        if check and result.returncode:
            raise ValueError(
                result.stderr.strip() or result.stdout.strip() or "Git operation failed"
            )
        return result
