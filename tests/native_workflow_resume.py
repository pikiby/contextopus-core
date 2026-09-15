"""Continue timed-out PCW work without replaying its user task.

The historical mode starts a new persistent Codex thread only after a durable
`thread/resume` probe established that the original ephemeral thread cannot be
rejoined. A separate explicit mode resumes a later persistent thread by its
actual stored ID. That persistent-resume mode requires a separately supplied,
authorized user-continuation text; neither mode replays a transcript or
synthesizes returns.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.native_workflow_probe import EVIDENCE_ROOT, NativeWorkflowProbe, write_json
from tests.test_codex_host import CodexHost


DEFAULT_SOURCE = EVIDENCE_ROOT / "multistage-normalize-cli-20260915T060139Z"
DEFAULT_PERSISTENT_SOURCE = EVIDENCE_ROOT / "multistage-normalize-cli-resume-20260915T064127Z"
DEFAULT_TIMEOUT_SECONDS = 1200


class NativeWorkflowContinuation:
    """A persistent separate-session continuation with no direct PCW calls."""

    def __init__(self, source: Path = DEFAULT_SOURCE, evidence_root: Path = EVIDENCE_ROOT):
        self.source = source.resolve()
        self.evidence_root = evidence_root.resolve()
        self.probe = NativeWorkflowProbe(evidence_root)

    @staticmethod
    def _timeout(value: str | None = None) -> int:
        raw = value if value is not None else os.environ.get(
            "PCW_NATIVE_RESUME_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
        try:
            result = int(raw, 10)
        except (TypeError, ValueError) as error:
            raise AssertionError({"invalid_PCW_NATIVE_RESUME_TIMEOUT_SECONDS": raw}) from error
        if result <= 0 or str(result) != raw:
            raise AssertionError({"invalid_PCW_NATIVE_RESUME_TIMEOUT_SECONDS": raw})
        return result

    def _source_state(self) -> dict[str, object]:
        required = ("failure.json", "fixture-manifest.json", "run-config.json", "thread-start.json", "turn-start.json")
        missing = [name for name in required if not (self.source / name).is_file()]
        if missing:
            raise AssertionError({"source_evidence_missing": missing, "source": str(self.source)})
        failure = json.loads((self.source / "failure.json").read_text(encoding="utf-8"))
        if failure.get("error_type") != "TimeoutError":
            raise AssertionError({"source_is_not_timeout": failure})
        fixture = json.loads((self.source / "fixture-manifest.json").read_text(encoding="utf-8"))
        if fixture.get("scenario") != "multistage-normalize-cli":
            raise AssertionError({"source_is_not_multistage": fixture})
        config = json.loads((self.source / "run-config.json").read_text(encoding="utf-8"))
        thread = json.loads((self.source / "thread-start.json").read_text(encoding="utf-8"))
        original_thread = thread.get("thread", {})
        thread_id = original_thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise AssertionError({"source_thread_id_missing": thread})
        work = self.source / "work"
        if not work.is_dir():
            raise AssertionError({"source_work_missing": str(work)})
        workspace = "native-multistage-normalize-cli"
        if not (work / ".pcw" / workspace).is_dir():
            raise AssertionError({"source_pcw_workspace_missing": str(work / ".pcw" / workspace)})
        return {
            "work": work, "workspace": workspace, "fixture": fixture, "config": config,
            "original_thread_id": thread_id, "original_ephemeral": original_thread.get("ephemeral"),
            "original_turn_id": json.loads((self.source / "turn-start.json").read_text(encoding="utf-8"))
                .get("turn", {}).get("id"),
        }

    @staticmethod
    def _read_user_continuation(path: Path | None) -> tuple[Path, str]:
        if path is None:
            raise AssertionError("A separately authorized --user-continuation-file is required for a live model turn")
        resolved = path.resolve()
        if not resolved.is_file():
            raise AssertionError({"user_continuation_file_missing": str(resolved)})
        text = resolved.read_text(encoding="utf-8")
        if not text.strip():
            raise AssertionError({"user_continuation_file_empty": str(resolved)})
        return resolved, text

    def _persistent_state(self, source: Path) -> dict[str, object]:
        source = source.resolve()
        required = ("thread-start.json", "turn-start.json", "turn-completed.json", "summary.json",
                    "run-config.json", "resume-origin.json", "source-work-preservation.json")
        missing = [name for name in required if not (source / name).is_file()]
        if missing:
            raise AssertionError({"persistent_resume_evidence_missing": missing, "source": str(source)})
        thread = json.loads((source / "thread-start.json").read_text(encoding="utf-8"))
        persisted = thread.get("thread")
        if not isinstance(persisted, dict):
            raise AssertionError({"persistent_resume_thread_missing": thread})
        thread_id = persisted.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise AssertionError({"persistent_resume_thread_id_missing": thread})
        if persisted.get("ephemeral") is not False:
            raise AssertionError({"persistent_resume_requires_ephemeral_false": persisted.get("ephemeral")})
        origin = json.loads((source / "resume-origin.json").read_text(encoding="utf-8"))
        work_raw = origin.get("work_root")
        workspace = origin.get("workspace")
        if not isinstance(work_raw, str) or not isinstance(workspace, str) or not workspace:
            raise AssertionError({"persistent_resume_coordinates_missing": origin})
        work = Path(work_raw).resolve()
        if not work.is_dir() or not (work / ".pcw" / workspace).is_dir():
            raise AssertionError({"persistent_resume_workspace_missing": {"work": str(work), "workspace": workspace}})
        if persisted.get("cwd") != str(work):
            raise AssertionError({"persistent_resume_cwd_mismatch": {"thread": persisted.get("cwd"), "work": str(work)}})
        summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
        continuation = summary.get("continuation")
        if not isinstance(continuation, dict) or continuation.get("status") != "turn_completed":
            raise AssertionError({"persistent_resume_source_not_completed": summary})
        if continuation.get("thread_id") != thread_id:
            raise AssertionError({"persistent_resume_summary_thread_mismatch": continuation})
        turn = json.loads((source / "turn-start.json").read_text(encoding="utf-8"))
        turn_id = turn.get("turn", {}).get("id") if isinstance(turn.get("turn"), dict) else None
        if not isinstance(turn_id, str) or continuation.get("turn_id") != turn_id:
            raise AssertionError({"persistent_resume_turn_mismatch": {"turn": turn, "summary": continuation}})
        completed = json.loads((source / "turn-completed.json").read_text(encoding="utf-8"))
        completed_params = completed.get("params") if isinstance(completed, dict) else None
        completed_turn = completed_params.get("turn") if isinstance(completed_params, dict) else None
        if (not isinstance(completed_params, dict) or completed_params.get("threadId") != thread_id or
                not isinstance(completed_turn, dict) or completed_turn.get("id") != turn_id or
                completed_turn.get("status") != "completed" or completed_turn.get("error") is not None):
            raise AssertionError({"persistent_resume_completion_mismatch": completed})
        config = json.loads((source / "run-config.json").read_text(encoding="utf-8"))
        return {"source": source, "thread": persisted, "thread_id": thread_id, "turn_id": turn_id,
                "work": work, "workspace": workspace, "config": config, "summary": summary}

    @staticmethod
    def _thread_resume_request(thread_id: str, work: Path) -> dict[str, object]:
        return {"threadId": thread_id, "cwd": str(work), "excludeTurns": True,
                "approvalPolicy": "on-request", "sandbox": "workspace-write"}

    def _resume_existing_thread(self, host: object, thread_id: str, work: Path) -> dict[str, object]:
        """Call the native resume endpoint; deliberately never starts a replacement thread."""
        return host.call("thread/resume", self._thread_resume_request(thread_id, work))

    @staticmethod
    def _work_manifest(work: Path) -> dict[str, str]:
        """Hash task files only; `.pcw` is intentionally live continuation state."""
        return {
            path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(work.rglob("*"))
            if path.is_file() and ".pcw" not in path.relative_to(work).parts
        }

    @staticmethod
    def _full_work_manifest(work: Path) -> dict[str, str]:
        """Hash all pre-continuation state, including live PCW materials."""
        return {
            path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(work.rglob("*")) if path.is_file()
        }

    @staticmethod
    def _copy_json(source: Path, destination: Path, name: str) -> dict[str, object]:
        value = json.loads((source / name).read_text(encoding="utf-8"))
        write_json(destination / ("source-" + name), value)
        return value

    @staticmethod
    def _continuation_prompt() -> str:
        return """Продолжи исходную задачу `native-multistage-normalize-cli` в этом уже подготовленном workspace после прерывания предыдущего исполнителя. Используй сохранённое состояние и фактические материалы. Не повторяй pipeline и не изменяй существующие `app/`, `data/`, `spec/`, `checks/` или `out/` файлы. Выполни только незавершённые действия исходного workflow, если они действительно остаются; если продолжение невозможно, верни конкретный blocker и его основание."""

    def validate(self) -> dict[str, object]:
        state = self._source_state()
        return {
            "source": str(self.source), "work": str(state["work"]), "workspace": state["workspace"],
            "original_thread_id": state["original_thread_id"], "original_ephemeral": state["original_ephemeral"],
            "continuation_kind": "new persistent native thread; original thread/resume must not be claimed",
        }

    def validate_persistent_resume(self, source: Path = DEFAULT_PERSISTENT_SOURCE) -> dict[str, object]:
        """Validate stored persistent-thread evidence without starting an app-server."""
        state = self._persistent_state(source)
        return {
            "mode": "thread_resume", "source": str(state["source"]), "work": str(state["work"]),
            "workspace": state["workspace"], "thread_id": state["thread_id"],
            "thread_ephemeral": state["thread"].get("ephemeral"), "completed_turn_id": state["turn_id"],
            "continuation_kind": "resume this persistent thread; do not replay transcript or create replacement thread",
        }

    def run(self, timeout: int | None = None, user_continuation_file: Path | None = None) -> dict[str, object]:
        if os.environ.get("PCW_TEST_NATIVE") != "1":
            raise AssertionError("Set PCW_TEST_NATIVE=1 to start a continuation model turn")
        # This historical new-thread mode retains its ordinary, bounded prompt.
        # A separately supplied text file is required only by resume_persistent.
        user_continuation = self._continuation_prompt()
        state = self._source_state()
        timeout = self._timeout(str(timeout) if timeout is not None else None)
        started = datetime.now(timezone.utc)
        evidence = self.evidence_root / ("multistage-normalize-cli-resume-" + started.strftime("%Y%m%dT%H%M%SZ"))
        evidence.mkdir(parents=True, exist_ok=False)
        work = state["work"]
        before = self._work_manifest(work)
        write_json(evidence / "source-work-before.json", before)
        full_before = self._full_work_manifest(work)
        write_json(evidence / "source-work-timeout-manifest.json", full_before)
        timeout_snapshot = evidence / "source-work-timeout-snapshot"
        shutil.copytree(work, timeout_snapshot)
        snapshot_manifest = self._full_work_manifest(timeout_snapshot)
        if snapshot_manifest != full_before:
            raise AssertionError({"timeout_snapshot_hash_mismatch": {
                "source_files": len(full_before), "snapshot_files": len(snapshot_manifest),
            }})
        write_json(evidence / "source-work-timeout-snapshot-manifest.json", snapshot_manifest)
        self.probe._snapshot_harness_source(evidence)
        runner_source = Path(__file__)
        runner_snapshot = evidence / "harness-source" / runner_source.name
        shutil.copy2(runner_source, runner_snapshot)
        write_json(evidence / "continuation-runner-source.json", {
            "source": str(runner_source.resolve()), "snapshot": str(runner_snapshot),
            "source_sha256": hashlib.sha256(runner_source.read_bytes()).hexdigest(),
            "snapshot_sha256": hashlib.sha256(runner_snapshot.read_bytes()).hexdigest(),
        })
        write_json(evidence / "resume-origin.json", {
            "source_timeout_evidence": str(self.source), "original_thread_id": state["original_thread_id"],
            "original_turn_id": state["original_turn_id"], "original_ephemeral": state["original_ephemeral"],
            "continuation_kind": "new persistent native thread on same work root and PCW workspace after thread/resume failure",
            "thread_resume_probe": str(self.evidence_root / "resume-probe-20260915T063404Z"),
            "work_root": str(work), "workspace": state["workspace"],
            "timeout_state_snapshot": str(timeout_snapshot),
            "timeout_state_snapshot_manifest": "source-work-timeout-snapshot-manifest.json",
            "source_fixture_files_remain_untouched_by_harness": True,
        })
        for name in ("failure.json", "fixture-manifest.json", "run-config.json", "thread-start.json", "turn-start.json"):
            self._copy_json(self.source, evidence, name)
        source_model = state["config"].get("primary_model")
        source_effort = state["config"].get("primary_reasoning_effort")
        write_json(evidence / "run-config.json", {
            "continuation_kind": "new persistent native thread after an unsuccessful thread/resume probe",
            "timeout_seconds": timeout,
            "source_timeout_evidence": str(self.source),
            "source_thread_id": state["original_thread_id"],
            "continuation_thread_ephemeral": False,
            "primary_model": source_model,
            "primary_reasoning_effort": source_effort,
            "primary_selection_source": "source run-config; revalidated against this app-server model catalog before turn/start",
            "harness_source_manifest": "harness-source-manifest.json",
        })
        write_json(evidence / "continuation-request.json", {
            "kind": "ordinary continuation user task", "text": user_continuation,
            "does_not_claim": ["same original thread", "completion", "new implementation", "replacement raw returns"],
        })
        environment = self.probe._environment()
        installed_root = self.probe._installed_root(environment)
        self.probe._assert_installed_parity(installed_root)
        request_log = evidence / "server-requests.jsonl"
        decision_log = evidence / "server-decisions.jsonl"
        for path in (request_log, decision_log):
            with path.open("a", encoding="utf-8") as output:
                output.flush()
                os.fsync(output.fileno())
        host = CodexHost(
            environment, work, notification_sink=evidence / "notifications.jsonl",
            server_request_sink=request_log, server_decision_sink=decision_log,
            server_request_handler=self.probe._request_policy(work, installed_root),
        )
        write_json(evidence / "host-start.json", {"pid": host.process.pid,
                   "started_at": started.isoformat().replace("+00:00", "Z")})
        write_json(evidence / "request-policy.json", {
            "scope": "server-request handler for the existing temporary native fixture only",
            "approval_policy": "on-request",
            "handler": "NativeWorkflowProbe._request_policy",
            "allowed": {
                "file_changes": [str((work / ".pcw").resolve())],
                "permissions_read": [str(work.resolve()), str(installed_root.resolve())],
                "permissions_write": [str((work / ".pcw").resolve())],
            },
            "denied": ["network", "global or session grants", "unknown server requests", "user input", "MCP elicitation"],
        })
        failure = None
        try:
            initialized = host.call("initialize", {
                "clientInfo": {"name": "pcw_native_workflow_continuation", "version": "1"},
                "capabilities": {"experimentalApi": True},
            })
            write_json(evidence / "initialize.json", initialized)
            host.send({"method": "initialized", "params": {}})
            models = host.call("model/list", {})
            write_json(evidence / "models.json", models)
            model = state["config"].get("primary_model")
            effort = state["config"].get("primary_reasoning_effort")
            if not isinstance(model, str) or not isinstance(effort, str):
                raise AssertionError({"source_primary_selection_missing": state["config"]})
            if model != "gpt-6-astra":
                raise AssertionError({"continuation_model_must_match_supported_primary": model})
            write_json(evidence / "primary-selection.json", self.probe._primary_selection(models, effort))
            write_json(evidence / "run-config.json", {
                "continuation_kind": "new persistent native thread after an unsuccessful thread/resume probe",
                "timeout_seconds": timeout,
                "source_timeout_evidence": str(self.source),
                "source_thread_id": state["original_thread_id"],
                "continuation_thread_ephemeral": False,
                "primary_model": model,
                "primary_reasoning_effort": effort,
                "primary_reasoning_effort_catalog_validated": True,
                "primary_selection_source": "source run-config; revalidated against this app-server model catalog before turn/start",
                "harness_source_manifest": "harness-source-manifest.json",
            })
            skills = host.call("skills/list", {"cwds": [str(work)], "forceReload": True})
            write_json(evidence / "skills.json", skills)
            skill = self.probe._pcw_skill_input(skills)
            thread_request = {
                "cwd": str(work), "ephemeral": False, "approvalPolicy": "on-request",
                "sandbox": "workspace-write", "experimentalRawEvents": True, "model": model,
            }
            write_json(evidence / "thread-start-request.json", thread_request)
            thread = host.call("thread/start", thread_request)
            thread_id = thread["thread"]["id"]
            write_json(evidence / "thread-start.json", thread)
            turn_request = {"threadId": thread_id, "input": [skill, {"type": "text", "text": user_continuation}],
                            "model": model, "effort": effort, "approvalPolicy": "on-request"}
            write_json(evidence / "turn-request.json", turn_request)
            turn = host.call("turn/start", turn_request, timeout=60)
            turn_id = turn["turn"]["id"]
            write_json(evidence / "turn-start.json", turn)
            completed = host.wait_notification(
                lambda message: message.get("method") == "turn/completed"
                and message.get("params", {}).get("threadId") == thread_id
                and message.get("params", {}).get("turn", {}).get("id") == turn_id,
                timeout=timeout,
            )
            write_json(evidence / "turn-completed.json", completed)
            try:
                items = host.call("thread/items/list", {"threadId": thread_id, "limit": 500}, timeout=60)
                items_source = {"source": "thread/items/list"}
            except AssertionError as error:
                if "thread/items/list is not supported yet" not in str(error):
                    raise
                items = {"data": [message["params"]["item"] for message in host.notification_snapshot()
                                  if message.get("method") == "item/completed"
                                  and isinstance(message.get("params", {}).get("item"), dict)]}
                items_source = {"source": "item/completed notifications", "fallback_error": str(error)}
            write_json(evidence / "thread-items.json", items)
            write_json(evidence / "thread-items-source.json", items_source)
            outcome = {"status": "turn_completed", "thread_id": thread_id, "turn_id": turn_id}
        except BaseException as error:
            failure = error
            outcome = {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
            write_json(evidence / "failure.json", {**outcome, "traceback": traceback.format_exc(),
                       "stderr_tail": host.stderr_tail(), "notifications": len(host.notification_snapshot())})
        finally:
            host.close()
            after = self._work_manifest(work)
            changed_paths = ((set(before) ^ set(after)) |
                             {path for path in before.keys() & after.keys() if before[path] != after[path]})
            preservation = {"before": before, "after": after, "unchanged": before == after,
                            "changed_paths": sorted(changed_paths)}
            write_json(evidence / "source-work-preservation.json", preservation)
        write_json(evidence / "summary.json", {
            "scope": "raw observed continuation trace; independently assessed separately",
            "source_timeout_evidence": str(self.source), "original_thread_id": state["original_thread_id"],
            "continuation": outcome, "source_work_preserved": preservation["unchanged"],
            "changed_source_work_paths": preservation["changed_paths"],
        })
        if failure is not None:
            raise failure
        return outcome

    def resume_persistent(self, persistent_source: Path = DEFAULT_PERSISTENT_SOURCE,
                          timeout: int | None = None,
                          user_continuation_file: Path | None = None) -> dict[str, object]:
        """Start one new turn on an evidenced persistent thread, never a substitute thread."""
        if os.environ.get("PCW_TEST_NATIVE") != "1":
            raise AssertionError("Set PCW_TEST_NATIVE=1 to start a persistent-thread continuation turn")
        user_continuation_path, user_continuation = self._read_user_continuation(user_continuation_file)
        state = self._persistent_state(persistent_source)
        timeout = self._timeout(str(timeout) if timeout is not None else None)
        started = datetime.now(timezone.utc)
        evidence = self.evidence_root / ("multistage-normalize-cli-thread-resume-" + started.strftime("%Y%m%dT%H%M%SZ"))
        evidence.mkdir(parents=True, exist_ok=False)
        work = state["work"]
        before = self._work_manifest(work)
        full_before = self._full_work_manifest(work)
        write_json(evidence / "persistent-work-before.json", before)
        write_json(evidence / "persistent-work-manifest-before.json", full_before)
        snapshot = evidence / "persistent-work-snapshot-before"
        shutil.copytree(work, snapshot)
        snapshot_manifest = self._full_work_manifest(snapshot)
        if snapshot_manifest != full_before:
            raise AssertionError({"persistent_resume_snapshot_hash_mismatch": {
                "source_files": len(full_before), "snapshot_files": len(snapshot_manifest),
            }})
        write_json(evidence / "persistent-work-snapshot-manifest.json", snapshot_manifest)
        self.probe._snapshot_harness_source(evidence)
        runner_source = Path(__file__)
        runner_snapshot = evidence / "harness-source" / runner_source.name
        shutil.copy2(runner_source, runner_snapshot)
        write_json(evidence / "continuation-runner-source.json", {
            "source": str(runner_source.resolve()), "snapshot": str(runner_snapshot),
            "source_sha256": hashlib.sha256(runner_source.read_bytes()).hexdigest(),
            "snapshot_sha256": hashlib.sha256(runner_snapshot.read_bytes()).hexdigest(),
        })
        for name in ("thread-start.json", "turn-start.json", "turn-completed.json", "summary.json",
                     "run-config.json", "resume-origin.json", "source-work-preservation.json"):
            self._copy_json(state["source"], evidence, name)
        write_json(evidence / "persistent-resume-origin.json", {
            "persistent_source": str(state["source"]), "thread_id": state["thread_id"],
            "completed_turn_id": state["turn_id"], "work_root": str(work), "workspace": state["workspace"],
            "thread_ephemeral": False,
            "mode": "thread/resume of the same persistent native thread; no transcript replay or replacement thread",
            "pre_turn_snapshot": str(snapshot),
            "metadata_only_resume_probe": str(self.evidence_root / "persistent-resume-probe-20260915T072600Z"),
        })
        write_json(evidence / "user-continuation.json", {
            "kind": "separately supplied user continuation", "source_path": str(user_continuation_path),
            "text": user_continuation, "sha256": hashlib.sha256(user_continuation.encode("utf-8")).hexdigest(),
            "does_not_claim": ["replayed transcript", "prior completion", "replacement raw returns", "checkpoint authority"],
        })
        model = state["config"].get("primary_model")
        effort = state["config"].get("primary_reasoning_effort")
        if not isinstance(model, str) or not isinstance(effort, str):
            raise AssertionError({"persistent_resume_model_selection_missing": state["config"]})
        write_json(evidence / "run-config.json", {
            "mode": "thread_resume", "timeout_seconds": timeout, "persistent_source": str(state["source"]),
            "thread_id": state["thread_id"], "thread_ephemeral": False,
            "primary_model": model, "primary_reasoning_effort": effort,
            "harness_source_manifest": "harness-source-manifest.json",
        })
        environment = self.probe._environment()
        installed_root = self.probe._installed_root(environment)
        self.probe._assert_installed_parity(installed_root)
        request_log = evidence / "server-requests.jsonl"
        decision_log = evidence / "server-decisions.jsonl"
        for path in (request_log, decision_log):
            with path.open("a", encoding="utf-8") as output:
                output.flush()
                os.fsync(output.fileno())
        host = CodexHost(
            environment, work, notification_sink=evidence / "notifications.jsonl",
            server_request_sink=request_log, server_decision_sink=decision_log,
            server_request_handler=self.probe._request_policy(work, installed_root),
        )
        write_json(evidence / "host-start.json", {"pid": host.process.pid,
                   "started_at": started.isoformat().replace("+00:00", "Z")})
        write_json(evidence / "request-policy.json", {
            "scope": "server-request handler for the existing temporary native fixture only",
            "approval_policy": "on-request", "handler": "NativeWorkflowProbe._request_policy",
            "allowed": {"file_changes": [str((work / ".pcw").resolve())],
                        "permissions_read": [str(work.resolve()), str(installed_root.resolve())],
                        "permissions_write": [str((work / ".pcw").resolve())]},
            "denied": ["network", "global or session grants", "unknown server requests", "user input", "MCP elicitation"],
        })
        failure = None
        try:
            initialized = host.call("initialize", {
                "clientInfo": {"name": "pcw_persistent_thread_resume", "version": "1"},
                "capabilities": {"experimentalApi": True},
            })
            write_json(evidence / "initialize.json", initialized)
            host.send({"method": "initialized", "params": {}})
            models = host.call("model/list", {})
            write_json(evidence / "models.json", models)
            if model != "gpt-6-astra":
                raise AssertionError({"persistent_resume_model_must_match_supported_primary": model})
            write_json(evidence / "primary-selection.json", self.probe._primary_selection(models, effort))
            resume_request = self._thread_resume_request(state["thread_id"], work)
            write_json(evidence / "thread-resume-request.json", resume_request)
            resumed = self._resume_existing_thread(host, state["thread_id"], work)
            write_json(evidence / "thread-resume.json", resumed)
            resumed_thread = resumed.get("thread") if isinstance(resumed, dict) else None
            if not isinstance(resumed_thread, dict) or resumed_thread.get("id") != state["thread_id"]:
                raise AssertionError({"persistent_resume_returned_unexpected_thread": resumed})
            if resumed_thread.get("ephemeral") is not False:
                raise AssertionError({"persistent_resume_lost_persistence": resumed_thread.get("ephemeral")})
            skills = host.call("skills/list", {"cwds": [str(work)], "forceReload": True})
            write_json(evidence / "skills.json", skills)
            skill = self.probe._pcw_skill_input(skills)
            turn_request = {"threadId": state["thread_id"],
                            "input": [skill, {"type": "text", "text": user_continuation}],
                            "model": model, "effort": effort, "approvalPolicy": "on-request"}
            write_json(evidence / "turn-request.json", turn_request)
            turn = host.call("turn/start", turn_request, timeout=60)
            turn_id = turn["turn"]["id"]
            write_json(evidence / "turn-start.json", turn)
            completed = host.wait_notification(
                lambda message: message.get("method") == "turn/completed"
                and message.get("params", {}).get("threadId") == state["thread_id"]
                and message.get("params", {}).get("turn", {}).get("id") == turn_id,
                timeout=timeout,
            )
            write_json(evidence / "turn-completed.json", completed)
            try:
                items = host.call("thread/items/list", {"threadId": state["thread_id"], "limit": 500}, timeout=60)
                items_source = {"source": "thread/items/list"}
            except AssertionError as error:
                if "thread/items/list is not supported yet" not in str(error):
                    raise
                items = {"data": [message["params"]["item"] for message in host.notification_snapshot()
                                  if message.get("method") == "item/completed"
                                  and isinstance(message.get("params", {}).get("item"), dict)]}
                items_source = {"source": "item/completed notifications", "fallback_error": str(error)}
            write_json(evidence / "thread-items.json", items)
            write_json(evidence / "thread-items-source.json", items_source)
            outcome = {"status": "turn_completed", "thread_id": state["thread_id"], "turn_id": turn_id}
        except BaseException as error:
            failure = error
            outcome = {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
            write_json(evidence / "failure.json", {**outcome, "traceback": traceback.format_exc(),
                       "stderr_tail": host.stderr_tail(), "notifications": len(host.notification_snapshot())})
        finally:
            host.close()
            after = self._work_manifest(work)
            changed_paths = ((set(before) ^ set(after)) |
                             {path for path in before.keys() & after.keys() if before[path] != after[path]})
            preservation = {"before": before, "after": after, "unchanged": before == after,
                            "changed_paths": sorted(changed_paths)}
            write_json(evidence / "persistent-work-preservation.json", preservation)
        write_json(evidence / "summary.json", {
            "scope": "raw observed persistent-thread continuation trace; independently assessed separately",
            "persistent_source": str(state["source"]), "thread_id": state["thread_id"],
            "continuation": outcome, "task_work_preserved": preservation["unchanged"],
            "changed_task_work_paths": preservation["changed_paths"],
        })
        if failure is not None:
            raise failure
        return outcome


class PersistentThreadResumeRoutingTests(unittest.TestCase):
    """No-host routing check for the real persistent-resume method."""

    def _persistent_source(self, root: Path) -> tuple[Path, Path]:
        work = root / "work"
        workspace = "native-multistage-normalize-cli"
        (work / ".pcw" / workspace).mkdir(parents=True)
        (work / "task.txt").write_text("unchanged fixture", encoding="utf-8")
        source = root / "persistent-source"
        source.mkdir()
        thread_id = "thread-persistent-17"
        turn_id = "turn-completed-17"
        write_json(source / "thread-start.json", {"thread": {
            "id": thread_id, "cwd": str(work), "ephemeral": False,
        }})
        write_json(source / "turn-start.json", {"turn": {"id": turn_id}})
        write_json(source / "turn-completed.json", {"method": "turn/completed", "params": {
            "threadId": thread_id, "turn": {"id": turn_id, "status": "completed", "error": None},
        }})
        write_json(source / "summary.json", {"continuation": {
            "status": "turn_completed", "thread_id": thread_id, "turn_id": turn_id,
        }})
        write_json(source / "run-config.json", {
            "primary_model": "gpt-6-astra", "primary_reasoning_effort": "xhigh",
        })
        write_json(source / "resume-origin.json", {"work_root": str(work), "workspace": workspace})
        write_json(source / "source-work-preservation.json", {"unchanged": True})
        return source, work

    def test_persistent_mode_resumes_same_thread_and_uses_supplied_text(self):
        with tempfile.TemporaryDirectory(prefix="pcw-persistent-resume-unit-") as directory:
            root = Path(directory)
            source, work = self._persistent_source(root)
            supplied = root / "authorized-continuation.txt"
            supplied.write_text("Разрешён только локальный checkpoint указанных PCW записей.", encoding="utf-8")
            calls = []

            class StubProbe:
                def _environment(self): return {}
                def _installed_root(self, environment):
                    installed = root / "installed"
                    installed.mkdir(exist_ok=True)
                    return installed
                def _assert_installed_parity(self, installed): pass
                def _snapshot_harness_source(self, evidence):
                    target = evidence / "harness-source"
                    target.mkdir()
                    write_json(evidence / "harness-source-manifest.json", {"stub": True})
                def _request_policy(self, work_root, installed_root): return lambda request: None
                def _primary_selection(self, models, effort): return {"model": "gpt-6-astra", "effort": effort}
                def _pcw_skill_input(self, skills): return {"type": "skill", "name": "pcw"}

            class StubHost:
                def __init__(self, *args, **kwargs): self.process = SimpleNamespace(pid=17)
                def send(self, message): calls.append(("send", message))
                def call(self, method, params, **kwargs):
                    calls.append((method, params))
                    if method == "initialize": return {"ok": True}
                    if method == "model/list": return {"data": []}
                    if method == "thread/resume": return {"thread": {"id": "thread-persistent-17", "ephemeral": False}}
                    if method == "skills/list": return {"data": []}
                    if method == "turn/start": return {"turn": {"id": "turn-new-18"}}
                    if method == "thread/items/list": return {"data": []}
                    raise AssertionError(method)
                def wait_notification(self, predicate, timeout):
                    message = {"method": "turn/completed", "params": {
                        "threadId": "thread-persistent-17", "turn": {"id": "turn-new-18"},
                    }}
                    assert predicate(message)
                    return message
                def notification_snapshot(self): return []
                def stderr_tail(self): return ""
                def close(self): calls.append(("close", {}))

            runner = NativeWorkflowContinuation(source=root / "unused-source", evidence_root=root / "evidence")
            runner.probe = StubProbe()
            with patch.dict(os.environ, {"PCW_TEST_NATIVE": "1"}, clear=False), \
                    patch("tests.native_workflow_resume.CodexHost", StubHost):
                result = runner.resume_persistent(source, timeout=1, user_continuation_file=supplied)
            self.assertEqual({"status": "turn_completed", "thread_id": "thread-persistent-17", "turn_id": "turn-new-18"}, result)
            methods = [method for method, _ in calls]
            self.assertIn("thread/resume", methods)
            self.assertIn("turn/start", methods)
            self.assertNotIn("thread/start", methods)
            resume = next(params for method, params in calls if method == "thread/resume")
            self.assertEqual("thread-persistent-17", resume["threadId"])
            start = next(params for method, params in calls if method == "turn/start")
            self.assertEqual("thread-persistent-17", start["threadId"])
            self.assertEqual({"type": "skill", "name": "pcw"}, start["input"][0])
            self.assertEqual(supplied.read_text(encoding="utf-8"), start["input"][1]["text"])
            self.assertTrue(list((root / "evidence").glob("multistage-normalize-cli-thread-resume-*/summary.json")))

    def test_missing_user_file_stops_before_host_creation(self):
        with tempfile.TemporaryDirectory(prefix="pcw-persistent-resume-unit-") as directory:
            root = Path(directory)
            source, _ = self._persistent_source(root)
            runner = NativeWorkflowContinuation(source=root / "unused-source", evidence_root=root / "evidence")
            with patch.dict(os.environ, {"PCW_TEST_NATIVE": "1"}, clear=False), \
                    patch("tests.native_workflow_resume.CodexHost") as host:
                with self.assertRaisesRegex(AssertionError, "user_continuation_file_missing"):
                    runner.resume_persistent(source, timeout=1, user_continuation_file=root / "missing.txt")
            host.assert_not_called()


def main() -> None:
    parser = argparse.ArgumentParser(description="Continue PCW work without replaying a transcript")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--resume-persistent-from", type=Path,
                        help="Evidence directory whose thread-start.json proves ephemeral:false")
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--user-continuation-file", type=Path,
                        help="Required only with --resume-persistent-from; contains separately authorized user scope")
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    runner = NativeWorkflowContinuation(arguments.source)
    if arguments.validate_only:
        result = (runner.validate_persistent_resume(arguments.resume_persistent_from)
                  if arguments.resume_persistent_from else runner.validate())
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    result = (runner.resume_persistent(arguments.resume_persistent_from, arguments.timeout_seconds,
                                       arguments.user_continuation_file)
              if arguments.resume_persistent_from else runner.run(arguments.timeout_seconds,
                                                                   arguments.user_continuation_file))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
