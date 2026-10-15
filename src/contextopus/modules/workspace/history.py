"""Local permanent-data history with immutable snapshots for failed-commit retries."""

from __future__ import annotations

from .text_io import read_utf8

import json
import os
from pathlib import Path
import re
import subprocess

from .runtime import PCWError, _id, _revision
from .policies import policies
from .workspaces import encode


class HistoryMixin:
    def _history_root(self):
        path = self.control.root / "history"
        self.control.safe(path)
        return path

    def _permanent_files(self):
        result = {}
        for path in [
            self.engine.root / "INSTRUCTIONS.md",
            self.engine.root / "PROJECT.md",
            *sorted(self.engine.knowledge.rglob("*.md")),
        ]:
            self.engine._assert_safe(path)
            if path.is_file():
                result[path.relative_to(self.engine.root).as_posix()] = (
                    path.read_bytes().decode("utf-8")
                )
        return result

    def _history_git(self, *args, text=None, index=None, check=True):
        self.engine._assert_safe(self.engine.root / ".git")
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        if index is not None:
            self.control.safe(index)
            env["GIT_INDEX_FILE"] = str(index)
        command = [
            "git",
            "--literal-pathspecs",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "user.name=PCW",
            "-c",
            "user.email=pcw@localhost",
            "-C",
            str(self.engine.root),
            *args,
        ]
        result = subprocess.run(
            command,
            input=text.encode("utf-8") if text is not None else None,
            capture_output=True,
            env=env,
            timeout=60,
        )
        result.stdout = result.stdout.decode("utf-8")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
        if check and result.returncode:
            raise PCWError(result.stderr.strip() or "Git history operation failed")
        return result

    def _history_capture(self, operation_id, *, force=False):
        """Called under the workspace lock immediately after verified file writes."""
        if (
            not force
            and not policies(self._instructions()["content"])["git_history_enabled"]
        ):
            return None
        root = self._history_root()
        root.mkdir(parents=True, exist_ok=True)
        queue_path = root / "queue.json"
        self.control.safe(queue_path)
        queue = json.loads(read_utf8(queue_path)) if queue_path.exists() else []
        snapshot_path = root / (_id(operation_id) + ".json")
        self.control.safe(snapshot_path)
        if not snapshot_path.exists():
            data = self._permanent_files()
            snapshot = {
                "operation_id": operation_id,
                "files": data,
                "revision": _revision(encode(data)),
                "status": "pending",
            }
            self.control.write(snapshot_path, encode(snapshot))
        if operation_id not in queue:
            queue.append(operation_id)
            self.control.write(queue_path, encode(queue))
        return operation_id

    def _history_record(self, operation_id, *, force=False):
        operation = self._history_capture(operation_id, force=force)
        if operation is None:
            return {"status": "disabled"}
        return self._history_flush(operation)

    def _history_flush(self, requested=None):
        root = self._history_root()
        queue_path = root / "queue.json"
        self.control.safe(queue_path)
        if not queue_path.exists():
            return {"status": "empty"}
        queue = json.loads(read_utf8(queue_path))
        receipt = {"status": "empty"}
        for operation_id in queue:
            path = root / (_id(operation_id) + ".json")
            self.control.safe(path)
            snapshot = json.loads(read_utf8(path))
            if snapshot["revision"] != _revision(encode(snapshot["files"])):
                raise PCWError(
                    "Stored Git snapshot was changed; inspect before retrying"
                )
            if snapshot["status"] in {"committed", "unchanged"}:
                if requested == operation_id:
                    receipt = {
                        key: snapshot.get(key)
                        for key in ("status", "commit", "operation_id")
                    }
                continue
            try:
                if not (self.engine.root / ".git").exists():
                    self._history_git("-c", "init.templateDir=", "init", ".")
                self.engine._own_git()
                exclude = self.engine.root / ".git/info/exclude"
                self.engine._assert_safe(exclude)
                previous = read_utf8(exclude) if exclude.exists() else ""
                additions = [
                    value
                    for value in (
                        "/tmp/",
                        "/current/",
                        "/.pcw-runtime/",
                        "/.analytics/",
                    )
                    if value not in previous.splitlines()
                ]
                if additions:
                    self.engine._write(
                        exclude,
                        previous.rstrip("\n") + "\n" + "\n".join(additions) + "\n",
                    )
                head_result = self._history_git(
                    "rev-parse", "--verify", "HEAD", check=False
                )
                head = (
                    head_result.stdout.strip() if head_result.returncode == 0 else None
                )
                # An acknowledgement may be lost after update-ref. Never duplicate that commit.
                if snapshot.get("commit") and head == snapshot["commit"]:
                    snapshot["status"] = "committed"
                else:
                    index = root / (operation_id + ".index")
                    self.control.safe(index)
                    index.unlink(missing_ok=True)
                    self._history_git("read-tree", "--empty", index=index)
                    for relative, text in sorted(snapshot["files"].items()):
                        self._history_paths([relative])
                        blob = self._history_git(
                            "hash-object", "-w", "--stdin", text=text
                        ).stdout.strip()
                        self._history_git(
                            "update-index",
                            "--add",
                            "--cacheinfo",
                            "100644",
                            blob,
                            relative,
                            index=index,
                        )
                    tree = self._history_git("write-tree", index=index).stdout.strip()
                    index.unlink(missing_ok=True)
                    old_tree = (
                        self._history_git("rev-parse", head + "^{tree}").stdout.strip()
                        if head
                        else None
                    )
                    if tree == old_tree:
                        snapshot.update(status="unchanged", commit=head)
                    else:
                        parent = ["-p", head] if head else []
                        commit = self._history_git(
                            "commit-tree",
                            tree,
                            *parent,
                            text="PCW permanent data: " + operation_id + "\n",
                        ).stdout.strip()
                        snapshot["commit"] = commit
                        self.control.write(path, encode(snapshot))
                        self._history_git(
                            "update-ref", "HEAD", commit, head or "0" * 40
                        )
                        snapshot["status"] = "committed"
                # Keep the workspace's regular index consistent without changing any file.
                self._history_git("read-tree", "HEAD")
                self.control.write(path, encode(snapshot))
                receipt = {
                    key: snapshot.get(key)
                    for key in ("status", "commit", "operation_id")
                }
            except Exception as exc:
                return {
                    "status": "pending",
                    "operation_id": operation_id,
                    "error": str(exc),
                    "requested_operation": requested,
                    "next_action": "history_retry",
                    "snapshot_preserved": True,
                }
        if requested is not None:
            path = root / (requested + ".json")
            snapshot = json.loads(read_utf8(path))
            return {
                key: snapshot.get(key) for key in ("status", "commit", "operation_id")
            }
        return receipt

    def history_retry(self):
        self._require_format()
        with self.control.guard():
            return self._history_flush()

    def _history_paths(self, paths):
        if (
            not isinstance(paths, list)
            or not paths
            or any(not isinstance(value, str) for value in paths)
        ):
            raise PCWError("Supply exact permanent-data paths")
        for path in paths:
            if path in {"INSTRUCTIONS.md", "PROJECT.md"}:
                self.engine._assert_safe(self.engine.root / path)
            elif path.startswith("knowledge/"):
                self.engine._knowledge_path(path[len("knowledge/") :])
            else:
                raise PCWError(
                    "History includes only INSTRUCTIONS.md, PROJECT.md and knowledge/*.md"
                )
        return paths

    def _history_revision(self, commit):
        if not isinstance(commit, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.~^/-]*", commit
        ):
            raise PCWError("Invalid history revision")
        self.engine._own_git()
        return self._history_git(
            "rev-parse", "--verify", "--end-of-options", commit + "^{commit}"
        ).stdout.strip()

    def history_list(self, offset: int = 0, limit: int = 20):
        self._require_format()
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise PCWError("Use a nonnegative offset and limit between 1 and 100")
        with self.control.guard():
            if not (self.engine.root / ".git").exists():
                return {"versions": [], "status": "no_history"}
            self.engine._own_git()
            if self._history_git(
                "rev-parse", "--verify", "HEAD", check=False
            ).returncode:
                return {"versions": [], "status": "no_commits"}
            lines = self._history_git(
                "log",
                f"--skip={offset}",
                f"--max-count={limit}",
                "--format=%H%x09%aI%x09%s",
                "--",
                "knowledge/",
                "INSTRUCTIONS.md",
                "PROJECT.md",
            ).stdout.splitlines()
            return {
                "versions": [
                    dict(zip(("commit", "time", "subject"), line.split("\t", 2)))
                    for line in lines
                ]
            }

    def history_diff(self, before: str, after: str, paths: list[str] | None = None):
        self._require_format()
        with self.control.guard():
            old, new = self._history_revision(before), self._history_revision(after)
            selected = (
                self._history_paths(paths)
                if paths is not None
                else ["knowledge/", "INSTRUCTIONS.md", "PROJECT.md"]
            )
            return {
                "before": old,
                "after": new,
                "diff": self._history_git(
                    "diff", "--no-ext-diff", "--no-textconv", old, new, "--", *selected
                ).stdout,
            }

    def history_read(
        self,
        cycle_id: str | None = None,
        commit: str = "HEAD",
        paths: list[str] | None = None,
    ):
        self._require_format()
        with self.control.guard():
            if cycle_id is not None:
                with self._cycle(cycle_id):
                    pass
            selected = self._history_paths(paths)
            revision = self._history_revision(commit)
            return {
                "commit": revision,
                "materials": [
                    {
                        "path": path,
                        "text": self._history_git("show", revision + ":" + path).stdout,
                    }
                    for path in selected
                ],
            }
