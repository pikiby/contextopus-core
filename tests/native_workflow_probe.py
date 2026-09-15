"""Run and preserve evidence for one actual PCW native-agent workflow.

This is deliberately an app-server client, rather than a simulated MCP flow.
The prompt is a bounded user task and contains no extra developer policy.  The
resulting JSON-RPC notifications and thread items are retained so a failure is
inspectable after a reboot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback

from tests.test_codex_host import CodexHost, PLUGIN, PLUGIN_ID


REPOSITORY = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPOSITORY / ".pcw" / "project-update" / ".pcw-runtime" / "verification" / "native"
PRIMARY_MODEL = "gpt-6-astra"
DEFAULT_PRIMARY_EFFORT = "high"
PRIMARY_SELECTION_REASON = (
    "The task exercises the complete PCW primary workflow, including native capability discovery, "
    "map publication, delegation, and factual acceptance. The actual catalog calls Astra the most "
    "capable model and the selected supported reasoning effort plus v2 delegation support; two Terra/high traces "
    "received the selected skill but bypassed its required workflow."
)


@dataclass(frozen=True)
class FixtureScenario:
    """A bounded user task whose source facts remain visible after the turn."""

    name: str
    prompt: str
    files: dict[str, str]
    required_knowledge_markers: tuple[str, ...]
    followup_fact: str
    forbidden_paths: tuple[str, ...] = ()
    mutable_paths: tuple[str, ...] = ()
    mutable_directories: tuple[str, ...] = ()

    @property
    def workspace(self) -> str:
        return "native-" + self.name

    def permits_mutation(self, relative: str) -> bool:
        return relative in self.mutable_paths or any(
            relative.startswith(directory.rstrip("/") + "/")
            for directory in self.mutable_directories
        )


SIMPLE_SCENARIO = FixtureScenario(
    name="simple",
    prompt="""Используй выбранный навык PCW для простой задачи контекста в workspace
`native-simple`: установи и фактически подтверди маркер из `fixture.md` в
текущем рабочем корне. Этот файл — единственный проектный источник и должен
остаться без изменений; другие проектные файлы также не меняй. В области задачи
разрешены временные рабочие материалы PCW и обычный доступ native host к
метаданным возможностей и установленным ресурсам PCW, необходимый для работы.
Верни наблюдаемый маркер и фактическое подтверждение результата по файлу.
""",
    files={"fixture.md": "# Native PCW fixture\n\nAccepted marker: `VERIFIED-CONTEXT-42`.\n"},
    required_knowledge_markers=(),
    followup_fact="VERIFIED-CONTEXT-42",
)


STALE_ENVIRONMENT_MAP_SCENARIO = FixtureScenario(
    name="stale-environment-map",
    # This is deliberately the ordinary simple user request. The controlled
    # stale environment/map state is fixture setup, never text fed to the
    # model as a refresh recipe.
    prompt="""Используй выбранный навык PCW для простой задачи контекста в workspace
`native-stale-environment-map`: установи и фактически подтверди маркер из
`fixture.md` в текущем рабочем корне. Этот файл — единственный проектный
источник и должен остаться без изменений; другие проектные файлы также не
меняй. В области задачи разрешены временные рабочие материалы PCW и обычный
доступ native host к метаданным возможностей и установленным ресурсам PCW,
необходимый для работы. Верни наблюдаемый маркер и фактическое подтверждение
результата по файлу.
""",
    files={"fixture.md": "# Native PCW fixture\n\nAccepted marker: `VERIFIED-CONTEXT-42`.\n"},
    required_knowledge_markers=(),
    followup_fact="VERIFIED-CONTEXT-42",
)


PREPARE_CONTEXT_ONLY_SCENARIO = FixtureScenario(
    name="prepare-context-only",
    prompt="""Используй выбранный навык PCW в workspace `native-prepare-context-only`, чтобы подготовить и сохранить контекст для
последующего выполнения задачи из `sources/future-task.md`. Используй оба
документа `sources/context-a.md` и `sources/context-b.md`: сведи повторяющееся
описание без потери разных обязательных условий, таблицы и фрагмента кода.
Сейчас выполни только подготовку памяти: будущую реализацию не запускай, не
создавай и не изменяй `out/deployed.txt`, а исходники оставь неизменными.
В области задачи разрешены временные рабочие материалы PCW и обычный доступ
native host к метаданным возможностей и установленным ресурсам PCW, необходимый
для работы. Верни, какие факты подготовлены для будущей задачи.
""",
    files={
        "sources/future-task.md": """# Future task (not authorized in this turn)

Only after a later explicit user request, create `out/deployed.txt` for release
R-17. It must name the approved owner and the verified deployment site.
""",
        "sources/context-a.md": """# Release R-17 operating context

Release R-17 is a controlled deployment package. The same release background
appears in both context documents because later workers need a complete record:
the package moves only after its release owner approves the handoff, and the
deployment record must identify the verified site. This turn does not authorize
deployment or any output under `out/`.

Mandatory condition A: the approval owner is `release-manager`.

| verified site | latency budget (ms) |
| --- | ---: |
| eu-west | 30 |

The future implementation must retain the exact release key `R-17`.
""",
        "sources/context-b.md": """# Release R-17 validation context

Release R-17 is a controlled deployment package. The same release background
appears in both context documents because later workers need a complete record:
the package moves only after its release owner approves the handoff, and the
deployment record must identify the verified site. This turn does not authorize
deployment or any output under `out/`.

Mandatory condition B: reject a packet unless it carries the R-17 prefix.

```python
def validate_packet(value: str) -> bool:
    return value.startswith("R-17:")
```

The verified deployment site remains `eu-west`; no second site is approved.
""",
    },
    required_knowledge_markers=("R-17", "release-manager", "eu-west", "validate_packet"),
    followup_fact="R-17",
    forbidden_paths=("out/deployed.txt",),
)


MULTISTAGE_NORMALIZE_CLI_SCENARIO = FixtureScenario(
    name="multistage-normalize-cli",
    prompt="""Используй выбранный навык PCW в workspace `native-multistage-normalize-cli`:
заверши локальную pipeline из `data/events.json` по `spec/contract.md`.
Реализуй разрешённые app-компоненты, через CLI создай оба output-файла и
фактически подтверди результат. Изменять можно только `app/` и точные файлы
`out/normalized.json`, `out/summary.json`; `data/`, `spec/` и `checks/`
неизменны. В области задачи разрешены временные рабочие материалы PCW и обычный
доступ native host к метаданным возможностей и установленным ресурсам PCW,
необходимый для работы. Верни изменения, наблюдения и ограничения.
""",
    files={
        "data/events.json": """[
  {"id": "A", "label": " Alpha ", "amount": 10, "active": true},
  {"id": "B", "label": "beta", "amount": 0, "active": true},
  {"id": "A", "label": "duplicate", "amount": 9, "active": true},
  {"id": "C", "label": " gamma", "amount": 5, "active": false}
]
""",
        "spec/contract.md": """# Normalization contract

Keep the first occurrence of each `id`, include only records where `active` is
true, and normalize `label` with `strip().casefold()`. Keep input order. The
normalized result is exactly A then B. The summary has `count: 2`,
`total_amount: 10`, and `zero_amount_ids: ["B"]`.

Run the pipeline as `python -m app.cli INPUT NORMALIZED SUMMARY` with three
positional paths: `INPUT` is `data/events.json`, `NORMALIZED` is
`out/normalized.json`, and `SUMMARY` is `out/summary.json`.
""",
        "checks/verify_contract.py": """import json
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: verify_contract.py NORMALIZED SUMMARY")

normalized = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
expected_normalized = [
    {"id": "A", "label": "alpha", "amount": 10},
    {"id": "B", "label": "beta", "amount": 0},
]
expected_summary = {"count": 2, "total_amount": 10, "zero_amount_ids": ["B"]}
if normalized != expected_normalized:
    raise SystemExit("normalized output does not satisfy contract: " + repr(normalized))
if summary != expected_summary:
    raise SystemExit("summary output does not satisfy contract: " + repr(summary))
""",
        "app/__init__.py": "",
        "app/normalize.py": """def normalize(records):
    raise NotImplementedError("implement normalization contract")
""",
        "app/report.py": """def build_summary(normalized):
    raise NotImplementedError("implement summary contract")
""",
        "app/cli.py": """raise SystemExit("implement CLI contract")
""",
    },
    required_knowledge_markers=(),
    followup_fact="normalized A and B records",
    mutable_paths=("app/__init__.py", "app/normalize.py", "app/report.py", "app/cli.py",
                   "out/normalized.json", "out/summary.json"),
    mutable_directories=("app",),
)


FAULT_AFTER_SAVED_RETURN_SCENARIO = FixtureScenario(
    name="fault-after-saved-return",
    prompt="""Используй выбранный навык PCW в workspace `native-fault-after-saved-return`:
реализуй `app/build_result.py` с функцией `build_result(release)`. Аргумент
`release` — объект из `data/release.json` ровно с полями `release: "R-17"` и
`active_components: ["api", "worker"]`. Функция должна вернуть
`{"release": release["release"], "count": len(release["active_components"])}`;
создай этим результатом `out/result.json`, то есть точный JSON
`{"release": "R-17", "count": 2}`, и фактически подтверди соответствие
`spec/contract.md`. Изменять можно только `app/` и `out/result.json`; `data/`,
`spec/` и `checks/` неизменны. В области задачи разрешены временные рабочие
материалы PCW и обычный доступ native host к метаданным возможностей и
установленным ресурсам PCW, необходимый для работы. Верни изменения,
наблюдения и ограничения.
""",
    files={
        "data/release.json": "{\n  \"release\": \"R-17\",\n  \"active_components\": [\"api\", \"worker\"]\n}\n",
        "spec/contract.md": """# Result contract

`out/result.json` must be exactly an object with `release` equal to `R-17` and
`count` equal to the number of active components: `2`.
""",
        "checks/verify_contract.py": """import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result != {"release": "R-17", "count": 2}:
    raise SystemExit("result does not satisfy contract: " + repr(result))
""",
        "app/build_result.py": """def build_result(release):
    raise NotImplementedError("implement result contract")
""",
    },
    required_knowledge_markers=(),
    followup_fact="R-17 result count",
    mutable_paths=("out/result.json",),
    mutable_directories=("app",),
)


MISMATCH_BEFORE_PLANNED_SCENARIO = FixtureScenario(
    name="mismatch-before-planned",
    prompt="""Используй выбранный навык PCW в workspace `native-mismatch-before-planned`:
реализуй `app/build_result.py` с функцией `build_result(release)`. Ожидаемый
выпуск имеет `release: "R-17"` и `active_components: ["api", "worker"]`.
Функция должна вернуть `{"release": release["release"], "count":
len(release["active_components"])}`; при соответствии создай `out/result.json`
этим результатом и затем выполни `checks/verify_contract.py`. Прочитай
`data/release.json` как фактический неизменяемый вход. Если в нём есть иной
компонент или фактический выпуск не соответствует `spec/contract.md`, остановись
до создания `out/result.json` и до его финальной контрактной проверки; не
удаляй и не игнорируй входной компонент, верни конкретное расхождение.
Изменять можно только `app/` и `out/result.json`; `data/`, `spec/` и `checks/`
неизменны. В области задачи разрешены временные рабочие материалы PCW и обычный
доступ native host к метаданным возможностей и установленным ресурсам PCW,
необходимый для работы. Верни изменения, наблюдения и ограничения.
""",
    files={
        "data/release.json": """{
  "release": "R-17",
  "active_components": ["api", "worker", "legacy"]
}
""",
        "spec/contract.md": """# Result contract

The expected R-17 release contains exactly the active components `api` and
`worker`. A corresponding `out/result.json` is exactly
`{"release": "R-17", "count": 2}`. No legacy component is approved.
""",
        "checks/verify_contract.py": """import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result != {"release": "R-17", "count": 2}:
    raise SystemExit("result does not satisfy contract: " + repr(result))
""",
        "app/build_result.py": """def build_result(release):
    raise NotImplementedError("implement result contract")
""",
    },
    required_knowledge_markers=("legacy",),
    followup_fact="legacy component",
    mutable_paths=("out/result.json",),
    mutable_directories=("app",),
)


SCENARIOS = {scenario.name: scenario for scenario in (
    SIMPLE_SCENARIO, STALE_ENVIRONMENT_MAP_SCENARIO, PREPARE_CONTEXT_ONLY_SCENARIO, MULTISTAGE_NORMALIZE_CLI_SCENARIO,
    FAULT_AFTER_SAVED_RETURN_SCENARIO, MISMATCH_BEFORE_PLANNED_SCENARIO,
)}


def write_json(path: Path, value: object) -> None:
    """Make a trace record durable before a potentially long next operation."""
    with path.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


class FaultAfterSavedReturn:
    """One temporary artifact fault after one proven primary save/read chain."""

    def __init__(self, evidence: Path, work: Path):
        self.target = work / "out" / "result.json"
        self.path = evidence / "fault-injection.json"
        self.main_thread_id = None
        self.child_threads: set[str] = set()
        self.child_finals: dict[str, str] = {}
        self.candidate = None
        self.state = {
            "scope": "test-only temporary artifact corruption; no MCP, return, session, or prompt interception",
            "status": "armed", "target": "out/result.json",
            "armed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "required_chain": "one actual child final text == saved raw result; main saves matching child session/material/revision/saved_at; main reads same raw bytes and metadata",
            "subagent_starts_after_injection": [],
        }
        write_json(self.path, self.state)

    def bind_main(self, thread_id: str) -> None:
        self.main_thread_id = thread_id
        self._write(main_thread_id=thread_id)

    @staticmethod
    def _event(message, index):
        params = message.get("params", {}) if isinstance(message.get("params"), dict) else {}
        item = params.get("item", {}) if isinstance(params.get("item"), dict) else {}
        return {"notification_index": index, "emitted_at_ms": message.get("emittedAtMs"),
                "method": message.get("method"), "actor_thread_id": params.get("threadId"),
                "item_id": item.get("id"), "tool": item.get("tool"), "item_type": item.get("type")}

    @staticmethod
    def _payload(item):
        try:
            text = next(part["text"] for part in item["result"]["content"] if part.get("type") == "text")
            return json.loads(text)
        except (KeyError, StopIteration, TypeError, json.JSONDecodeError):
            return None

    def _write(self, **values):
        self.state.update(values)
        write_json(self.path, self.state)

    def _inconclusive(self, reason, message=None, index=None, force=False):
        if self.state["status"] == "injected" and not force:
            return
        detail = {"status": "inconclusive", "reason": reason,
                  "concluded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        if message is not None:
            detail["decisive_event"] = self._event(message, index)
        if self.state["status"] == "injected":
            detail["prior_status"] = "injected"
        self._write(**detail)

    @staticmethod
    def _sha(data):
        return hashlib.sha256(data).hexdigest()

    def _inject(self, message, index, read):
        if len(self.child_threads) != 1:
            self._inconclusive("expected_exactly_one_prior_child", message, index)
            return
        if not self.target.is_file():
            self._inconclusive("target_is_missing_after_causal_chain", message, index)
            return
        before = self.target.read_bytes()
        try:
            if json.loads(before) != {"release": "R-17", "count": 2}:
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            self._inconclusive("target_was_not_correct_before_fault", message, index)
            return
        after = (json.dumps({"release": "R-17", "count": 3}, indent=2, sort_keys=True) + "\n").encode()
        temporary = self.target.with_name(self.target.name + ".fault-tmp")
        with temporary.open("wb") as output:
            output.write(after); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, self.target)
        directory_fd = os.open(self.target.parent, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        self._write(status="injected", trigger_event=self._event(message, index), read_metadata=read,
                    injected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    before={"base64": base64.b64encode(before).decode(), "sha256": self._sha(before)},
                    after={"base64": base64.b64encode(after).decode(), "sha256": self._sha(after)},
                    semantic_diff={"count": [2, 3]},
                    atomic_write="temporary file fsync followed by os.replace and directory fsync")

    def observe(self, message, index):
        """Called after raw notification fsync; its exceptions are forced inconclusive."""
        try:
            if self.state["status"] == "inconclusive" or not isinstance(message, dict): return
            params = message.get("params")
            if not isinstance(params, dict): return
            item = params.get("item")
            if not isinstance(item, dict): return
            actor = params.get("threadId")
            if item.get("type") == "subAgentActivity" and item.get("kind") == "started":
                child = item.get("agentThreadId")
                if isinstance(child, str): self.child_threads.add(child)
                if self.state["status"] == "injected":
                    self._write(subagent_starts_after_injection=[*self.state["subagent_starts_after_injection"], self._event(message, index)])
                return
            if item.get("type") == "agentMessage" and item.get("phase") == "final_answer" and isinstance(actor, str) and actor in self.child_threads:
                text = item.get("text")
                if isinstance(text, str): self.child_finals[actor] = text
                return
            if self.state["status"] == "injected" or message.get("method") != "item/completed": return
            if item.get("type") != "mcpToolCall" or item.get("server") != "pcw" or item.get("status") != "completed": return
            if actor != self.main_thread_id: return
            args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            if item.get("tool") == "pcw_save_subagent_result":
                raw = args.get("result"); child = args.get("executor_session_id"); material = args.get("material_name"); saved = self._payload(item)
                if not isinstance(raw, str) or raw not in self.child_finals.values(): return
                if len(self.child_threads) != 1 or child not in self.child_finals or self.child_finals[child].encode() != raw.encode():
                    self._inconclusive("saved_return_does_not_match_only_actual_child_final", message, index); return
                if not isinstance(material, str) or not material or not isinstance(saved, dict) or any(saved.get(key) != value for key, value in (("id", material), ("executor_session_id", child))) or not saved.get("revision") or not saved.get("saved_at"):
                    self._inconclusive("save_metadata_does_not_match_actual_child", message, index); return
                self.candidate = {"event": self._event(message, index), "material": material, "session": child,
                                  "raw": raw, "revision": saved["revision"], "saved_at": saved["saved_at"]}
                self._write(status="save_observed", causal_save={k:v for k,v in self.candidate.items() if k != "raw"})
                return
            if item.get("tool") == "pcw_read" and self.candidate:
                if args.get("material_id") != self.candidate["material"]:
                    return
                read = self._payload(item)
                if (not isinstance(read, dict) or read.get("id") != self.candidate["material"]
                        or read.get("revision") != self.candidate["revision"]
                        or read.get("saved_at") != self.candidate["saved_at"]
                        or read.get("executor_session_id") != self.candidate["session"]
                        or read.get("content", "").encode() != self.candidate["raw"].encode()):
                    self._inconclusive("read_does_not_match_saved_raw_result_and_metadata", message, index); return
                self._inject(message, index, {key: read[key] for key in ("id", "revision", "saved_at", "executor_session_id")})
        except Exception as error:
            self._inconclusive("observer_exception: " + repr(error), message, index, force=True)

    def observer_failed(self, errors):
        if errors:
            self._inconclusive("host_notification_observer_error", force=True)
            self._write(observer_errors=list(errors))

    def finalize(self):
        if self.state["status"] == "armed": self._inconclusive("no_matching_saved_raw_return_before_turn_end")
        elif self.state["status"] == "save_observed": self._inconclusive("no_matching_read_after_saved_return_before_turn_end")
        return dict(self.state)


class NativeWorkflowProbe:
    """A one-turn, actual-model proof for the simple final-check scenario."""

    def __init__(self, evidence_root: Path = EVIDENCE_ROOT):
        self.evidence_root = evidence_root

    @staticmethod
    def _harness_source_paths() -> tuple[Path, ...]:
        return (REPOSITORY / "tests" / "test_codex_host.py", Path(__file__),
                REPOSITORY / "tests" / "test_native_workflow.py")

    @classmethod
    def _snapshot_harness_source(cls, evidence: Path) -> dict[str, object]:
        """Preserve the exact runner sources once, before this run starts work."""
        destination = evidence / "harness-source"
        destination.mkdir(exist_ok=True)
        copied = []
        for source in cls._harness_source_paths():
            target = destination / source.name
            if not target.exists():
                shutil.copy2(source, target)
            copied.append({
                "name": source.name,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "snapshot_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
        manifest = {
            "purpose": "harness source as observed before this native run",
            "destination": str(destination), "files": copied,
        }
        write_json(evidence / "harness-source-manifest.json", manifest)
        return manifest

    @staticmethod
    def _environment() -> dict[str, str]:
        environment = dict(os.environ)
        for name in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PCW_PYTHON", "PCW_DEPENDENCIES"):
            environment.pop(name, None)
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
        return environment

    @staticmethod
    def _installed_root(environment: dict[str, str]) -> Path:
        configuration = json.loads(subprocess_run(["codex", "mcp", "get", "pcw", "--json"], environment))
        transport = configuration["transport"]
        if transport.get("command") != "sh" or len(transport.get("args", [])) != 1:
            raise AssertionError({"unexpected_pcw_transport": transport})
        launcher = Path(transport["args"][0])
        if not launcher.is_absolute() or not launcher.is_file():
            raise AssertionError({"invalid_pcw_launcher": transport})
        return launcher.parents[1]

    @staticmethod
    def _assert_installed_parity(installed_root: Path) -> None:
        fixed = [PLUGIN / "plugin.json", PLUGIN / ".codex-plugin" / "plugin.json", PLUGIN / "mcp.json", PLUGIN / "pyproject.toml"]
        trees = (PLUGIN / "pcw_runtime", PLUGIN / "scripts", PLUGIN / "skills")
        source_files = [path for path in fixed if path.is_file()]
        source_files.extend(path for tree in trees if tree.is_dir() for path in tree.rglob("*")
                            if path.is_file() and "__pycache__" not in path.parts)
        missing = []
        different = []
        for source in sorted(source_files):
            relative = source.relative_to(PLUGIN)
            candidate = installed_root / relative
            if not candidate.is_file():
                missing.append(relative.as_posix())
            elif source.read_bytes() != candidate.read_bytes():
                different.append(relative.as_posix())
        if missing or different:
            raise AssertionError({"installed_candidate_parity": "failed", "missing": missing, "different": different})

    @staticmethod
    def selected_scenario(name: str | None = None) -> FixtureScenario:
        selected = name or os.environ.get("PCW_NATIVE_SCENARIO", "simple")
        try:
            return SCENARIOS[selected]
        except KeyError as error:
            raise AssertionError({"unknown_native_scenario": selected, "available": sorted(SCENARIOS)}) from error

    @staticmethod
    def selected_timeout(value: int | None = None) -> int:
        """Use a visible, validated opt-in timeout for longer real workflows."""
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise AssertionError({"invalid_native_timeout_seconds": value})
            return value
        configured = os.environ.get("PCW_NATIVE_TIMEOUT_SECONDS")
        if configured is None:
            return 600
        try:
            timeout = int(configured, 10)
        except ValueError as error:
            raise AssertionError({"invalid_PCW_NATIVE_TIMEOUT_SECONDS": configured}) from error
        if timeout <= 0 or str(timeout) != configured:
            raise AssertionError({"invalid_PCW_NATIVE_TIMEOUT_SECONDS": configured})
        return timeout

    @staticmethod
    def selected_primary_effort(value: str | None = None) -> str:
        """Read an opt-in effort; catalog validation happens after models/list."""
        effort = value if value is not None else os.environ.get(
            "PCW_NATIVE_REASONING_EFFORT", DEFAULT_PRIMARY_EFFORT)
        if not isinstance(effort, str) or not effort or effort.strip() != effort:
            raise AssertionError({"invalid_PCW_NATIVE_REASONING_EFFORT": effort})
        return effort

    @staticmethod
    def diagnostic_prompt() -> str:
        """Optional diagnostic fixture, intentionally not used for acceptance.

        Keep detailed protocol experiments out of the ordinary user task: they
        would merely test whether a model can repeat instructions supplied by
        the test instead of whether the installed PCW skill supplies them.
        """
        return "Проверь fixture.md в режиме диагностики; область — только чтение файла."

    @staticmethod
    def _pcw_skill_input(skills: dict[str, object]) -> dict[str, str]:
        """Use the host's discovered selector; do not rely on text parsing."""
        matches = [
            skill for entry in skills.get("data", []) if isinstance(entry, dict)
            for skill in entry.get("skills", []) if isinstance(skill, dict)
            if skill.get("name") == "persistent-context-workspace:pcw"
            and skill.get("pluginId") == PLUGIN_ID and skill.get("enabled") is True
        ]
        if len(matches) != 1:
            raise AssertionError({"expected_one_enabled_pcw_skill": matches})
        skill = matches[0]
        if not isinstance(skill.get("path"), str):
            raise AssertionError({"pcw_skill_has_no_path": skill})
        return {"type": "skill", "name": skill["name"], "path": skill["path"]}

    @staticmethod
    def _primary_selection(models: dict[str, object], effort: str) -> dict[str, object]:
        available = models.get("data")
        if not isinstance(available, list):
            raise AssertionError({"model_list_has_no_data": models})
        selected = next((model for model in available if isinstance(model, dict) and model.get("id") == PRIMARY_MODEL), None)
        if not isinstance(selected, dict):
            raise AssertionError({"primary_model_is_unavailable": PRIMARY_MODEL})
        efforts = {item.get("reasoningEffort") for item in selected.get("supportedReasoningEfforts", []) if isinstance(item, dict)}
        if effort not in efforts:
            raise AssertionError({"primary_effort_is_unavailable": effort, "model": selected})
        return {"role": "primary", "model": PRIMARY_MODEL, "reasoning_effort": effort,
                "reason": PRIMARY_SELECTION_REASON, "catalog_entry": selected}

    @staticmethod
    def _mcp_content(result: dict[str, object]) -> dict[str, object]:
        """Decode an actual app-server MCP result without fabricating a fallback."""
        if result.get("isError"):
            raise AssertionError({"pcw_seed_mcp_error": result})
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content")
        if not isinstance(content, list):
            raise AssertionError({"pcw_seed_mcp_has_no_content": result})
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                parsed = json.loads(part["text"])
                if isinstance(parsed, dict):
                    return parsed
        raise AssertionError({"pcw_seed_mcp_has_no_object_content": result})

    @staticmethod
    def _stale_map_seed_plan(work: Path, workspace: str) -> dict[str, object]:
        """Schema-valid fixture state that differs from the actual host catalog."""
        snapshot = {
            "environment": "pcw-native-fixture-stale-map",
            "version": "fixture-pre-model-v1",
            "native": {"launch": {"supports_clean_context": True, "fork_turns": ["none"]}},
            "models": [{
                "id": "fixture-old-primary", "reasoning": {"effort": ["low"]},
                "launch_constraints": {"fork_turns": ["none"]},
            }],
        }
        profiles = [{
            "id": "fixture-old-primary-low", "model": "fixture-old-primary",
            "reasoning": {"effort": "low"}, "roles": ["investigation"],
            "suitable_when": ["controlled stale environment-map fixture"],
        }]
        return {
            "origin": "harness-authored controlled temporary fixture seed before any primary model turn",
            "work_root": str(work), "workspace": workspace,
            "environment_snapshot": snapshot, "profiles": profiles,
            "proof_limit": "This seeds stale PCW memory only; it is not an actual Codex upgrade and is not attributed to the primary or a subagent.",
        }

    def _seed_stale_environment_map(self, host: CodexHost, work: Path, scenario: FixtureScenario,
                                    evidence: Path) -> dict[str, object]:
        """Use actual host-to-PCW MCP calls before the primary model turn."""
        plan = self._stale_map_seed_plan(work, scenario.workspace)
        thread_request = {
            "cwd": str(work), "ephemeral": True, "approvalPolicy": "never",
            "sandbox": "workspace-write", "experimentalRawEvents": True,
        }
        seed_thread = host.call("thread/start", thread_request)
        seed_thread_id = seed_thread["thread"]["id"]
        calls = []

        def tool(name: str, **arguments: object) -> dict[str, object]:
            request = {
                "threadId": seed_thread_id, "server": "pcw", "tool": "pcw_" + name,
                "arguments": {"work_root": str(work), "workspace": scenario.workspace, **arguments},
            }
            response = host.call("mcpServer/tool/call", request)
            decoded = self._mcp_content(response)
            calls.append({"request": request, "response": response, "decoded_response": decoded})
            return decoded

        absent = tool("environment_get")
        if absent.get("status") != "absent":
            raise AssertionError({"stale_seed_requires_fresh_environment": absent})
        checked = tool("environment_check", environment_snapshot=plan["environment_snapshot"])
        revision = checked.get("environment_revision")
        if checked.get("status") != "updated" or not isinstance(revision, str) or not revision:
            raise AssertionError({"stale_seed_environment_check_failed": checked})
        published = tool("tools_map_publish", expected_environment_revision=revision, profiles=plan["profiles"])
        if published.get("status") != "published":
            raise AssertionError({"stale_seed_map_publish_failed": published})
        result = {
            **plan, "seed_thread_request": thread_request, "seed_thread_response": seed_thread,
            "seed_thread_id": seed_thread_id, "calls": calls,
            "seed_outcome": {"environment_status": checked.get("status"), "published_status": published.get("status"),
                             "environment_revision": revision},
        }
        write_json(evidence / "seed-origin.json", {
            "origin": plan["origin"], "seed_thread_id": seed_thread_id,
            "primary_model_turn_started": False, "proof_limit": plan["proof_limit"],
        })
        write_json(evidence / "stale-map-seed.json", result)
        return result

    @staticmethod
    def _is_within(candidate: Path, root: Path) -> bool:
        try:
            candidate.resolve(strict=False).relative_to(root.resolve())
        except ValueError:
            return False
        return True

    @classmethod
    def _request_policy(cls, work: Path, installed_root: Path):
        """Build the test host's narrow, per-request authorization policy.

        The ordinary fixture permits PCW's own state below ``work/.pcw`` and
        read-only inspection of the fixture and installed PCW metadata. Every
        other app-server request is recorded and declined. This is deliberately
        a test-client capability decision, not an instruction supplied to the
        model or a change to the user's global Codex policy.
        """
        work = work.resolve()
        pcw_root = (work / ".pcw").resolve()
        installed_root = installed_root.resolve()

        def in_read_scope(value: object, cwd: Path) -> bool:
            if not isinstance(value, str) or not value:
                return False
            path = Path(value)
            if not path.is_absolute():
                path = cwd / path
            return cls._is_within(path, work) or cls._is_within(path, installed_root)

        def in_write_scope(value: object, cwd: Path) -> bool:
            if not isinstance(value, str) or not value:
                return False
            path = Path(value)
            if not path.is_absolute():
                path = cwd / path
            return cls._is_within(path, pcw_root)

        def scoped_cwd(value: object) -> Path | None:
            if not isinstance(value, str) or not value:
                return None
            path = Path(value)
            if not path.is_absolute():
                return None
            resolved = path.resolve(strict=False)
            if cls._is_within(resolved, work) or cls._is_within(resolved, installed_root):
                return resolved
            return None

        def safe_command(params: dict[str, object]) -> bool:
            cwd = scoped_cwd(params.get("cwd"))
            command = params.get("command")
            actions = params.get("commandActions")
            if cwd is None or not isinstance(command, str) or not isinstance(actions, list) or not actions:
                return False
            # Command actions are only a best-effort display parse. Also reject
            # shell composition and accept a small read-only executable set.
            if any(character in command for character in (";", "|", "&", ">", "<", "`", "$", "\n", "\r")):
                return False
            try:
                tokens = shlex.split(command)
            except ValueError:
                return False
            if not tokens or Path(tokens[0]).name not in {"cat", "sed", "head", "tail", "rg", "find", "ls", "stat"}:
                return False
            for action in actions:
                if not isinstance(action, dict) or action.get("type") not in {"read", "listFiles", "search"}:
                    return False
                path = action.get("path")
                if path is None or not in_read_scope(path, cwd):
                    return False
            return True

        def safe_permissions(params: dict[str, object]) -> bool:
            cwd = scoped_cwd(params.get("cwd"))
            requested = params.get("permissions")
            if cwd is None or not isinstance(requested, dict):
                return False
            network = requested.get("network")
            if network is not None and (
                    not isinstance(network, dict)
                    or set(network) - {"enabled"}
                    or network.get("enabled") not in (None, False)):
                return False
            filesystem = requested.get("fileSystem")
            if not isinstance(filesystem, dict):
                return False
            if filesystem.get("globScanMaxDepth") not in (None,):
                return False
            entries = filesystem.get("entries")
            legacy_read = filesystem.get("read")
            legacy_write = filesystem.get("write")
            if not entries and not legacy_read and not legacy_write:
                return False
            if entries is not None:
                if not isinstance(entries, list):
                    return False
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get("access") not in {"read", "write"}:
                        return False
                    path = entry.get("path")
                    if not isinstance(path, dict) or path.get("type") != "path" or not isinstance(path.get("path"), str):
                        return False
                    allowed = in_read_scope(path["path"], cwd) if entry["access"] == "read" else in_write_scope(path["path"], cwd)
                    if not allowed:
                        return False
            for field, validator in (("read", in_read_scope), ("write", in_write_scope)):
                values = filesystem.get(field)
                if values is not None and (not isinstance(values, list) or not all(validator(value, cwd) for value in values)):
                    return False
            return True

        def deny(method: str) -> dict[str, object]:
            return {"error": {"code": -32001, "message": "PCW native fixture does not authorize " + method}}

        def handle(request: dict[str, object]) -> dict[str, object]:
            method = request.get("method")
            params = request.get("params")
            if not isinstance(method, str) or not isinstance(params, dict):
                return deny("malformed server request")
            if method == "item/commandExecution/requestApproval":
                return {"result": {"decision": "accept"}} if safe_command(params) else deny(method)
            if method == "item/fileChange/requestApproval":
                grant_root = params.get("grantRoot")
                return ({"result": {"decision": "accept"}}
                        if isinstance(grant_root, str) and Path(grant_root).resolve(strict=False) == pcw_root
                        else deny(method))
            if method == "item/permissions/requestApproval":
                return ({"result": {"permissions": params["permissions"], "scope": "turn"}}
                        if safe_permissions(params) else deny(method))
            # Do not fabricate user input, satisfy MCP elicitation, grant auth,
            # or run an unrecognized dynamic tool call on behalf of the model.
            return deny(method)

        return handle

    def run_simple(self, timeout: int | None = None) -> dict[str, object]:
        """Compatibility entry point for the default simple factual-check scenario."""
        return self.run_scenario("simple", timeout=timeout)

    def run_scenario(self, scenario_name: str | None = None, timeout: int | None = None,
                     followup: bool = False) -> dict[str, object]:
        """Run one ordinary user task and preserve its complete native trace."""
        if not shutil.which("codex"):
            raise AssertionError("actual Codex CLI is required")
        scenario = self.selected_scenario(scenario_name)
        timeout = self.selected_timeout(timeout)
        effort = self.selected_primary_effort()
        started = datetime.now(timezone.utc)
        run_name = scenario.name + "-" + started.strftime("%Y%m%dT%H%M%SZ")
        evidence = self.evidence_root / run_name
        evidence.mkdir(parents=True, exist_ok=False)
        harness_source = self._snapshot_harness_source(evidence)
        work = evidence / "work"
        work.mkdir()
        original_sources = {}
        for relative, content in scenario.files.items():
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            original_sources[relative] = path.read_bytes()
        write_json(evidence / "fixture-manifest.json", {
            "scenario": scenario.name,
            "immutable_source_paths": sorted(path for path in original_sources if not scenario.permits_mutation(path)),
            "mutable_paths": list(scenario.mutable_paths),
            "mutable_directories": list(scenario.mutable_directories),
            "forbidden_paths": list(scenario.forbidden_paths),
            "required_knowledge_markers": list(scenario.required_knowledge_markers),
        })
        write_json(evidence / "run-config.json", {
            "scenario": scenario.name, "timeout_seconds": timeout, "followup": followup,
            "primary_model": PRIMARY_MODEL, "primary_reasoning_effort": effort,
            "primary_reasoning_effort_source": "PCW_NATIVE_REASONING_EFFORT or default",
            "harness_source_manifest": "harness-source-manifest.json",
        })
        environment = self._environment()
        installed_root = self._installed_root(environment)
        self._assert_installed_parity(installed_root)
        request_log = evidence / "server-requests.jsonl"
        decision_log = evidence / "server-decisions.jsonl"
        # Create durable empty logs too, so a later review can distinguish no
        # requests from an interrupted run before trace setup.
        for path in (request_log, decision_log):
            with path.open("a", encoding="utf-8") as output:
                output.flush()
                os.fsync(output.fileno())
        fault_injection = (FaultAfterSavedReturn(evidence, work)
                           if scenario.name == "fault-after-saved-return" else None)
        host = CodexHost(
            environment, work, notification_sink=evidence / "notifications.jsonl",
            server_request_sink=request_log, server_decision_sink=decision_log,
            server_request_handler=self._request_policy(work, installed_root),
            notification_observer=fault_injection.observe if fault_injection else None,
        )
        write_json(evidence / "host-start.json", {"pid": host.process.pid, "started_at": started.isoformat().replace("+00:00", "Z")})
        write_json(evidence / "request-policy.json", {
            "scope": "server-request handler for the temporary native fixture only",
            "approval_policy": "on-request",
            "mcp_tool_approval": {
                "mechanism": "native thread/turn approvalPolicy",
                "client_callback": None,
                "schema_observation": "Codex app-server 0.154 ServerRequest has no MCP-tool approval request; observed dispatch scope must be assessed from this run's raw trace.",
            },
            "allowed": {
                "file_changes": [str((work / ".pcw").resolve())],
                "permissions_read": [str(work.resolve()), str(installed_root.resolve())],
                "permissions_write": [str((work / ".pcw").resolve())],
                "commands": "single read-only cat/sed/head/tail/rg/find/ls/stat command with a parsed path in read scope",
            },
            "denied": ["network", "global or session grants", "unknown server requests", "user input", "MCP elicitation"],
        })
        failure: BaseException | None = None
        stale_map_seed = {"status": "not_applicable"}
        try:
            print("native probe: app-server initialize", flush=True)
            initialized = host.call("initialize", {
                "clientInfo": {"name": "pcw_native_workflow_probe", "version": "1"},
                "capabilities": {"experimentalApi": True},
            })
            write_json(evidence / "initialize.json", initialized)
            host.send({"method": "initialized", "params": {}})
            models = host.call("model/list", {})
            write_json(evidence / "models.json", models)
            primary_selection = self._primary_selection(models, effort)
            write_json(evidence / "primary-selection.json", primary_selection)
            write_json(evidence / "run-config.json", {
                "scenario": scenario.name, "timeout_seconds": timeout, "followup": followup,
                "primary_model": PRIMARY_MODEL, "primary_reasoning_effort": effort,
                "primary_reasoning_effort_source": "PCW_NATIVE_REASONING_EFFORT or default",
                "primary_reasoning_effort_catalog_validated": True,
                "harness_source_manifest": "harness-source-manifest.json",
            })
            if scenario.name == "stale-environment-map":
                stale_map_seed = self._seed_stale_environment_map(host, work, scenario, evidence)
            skills = host.call("skills/list", {"cwds": [str(work)], "forceReload": True})
            write_json(evidence / "skills.json", skills)
            skill_input = self._pcw_skill_input(skills)
            print("native probe: discovered models; starting " + PRIMARY_MODEL + "/" + effort + " turn", flush=True)
            thread = host.call("thread/start", {
                "cwd": str(work), "ephemeral": True, "approvalPolicy": "on-request",
                "sandbox": "workspace-write", "experimentalRawEvents": True,
                "model": PRIMARY_MODEL,
            })
            thread_id = thread["thread"]["id"]
            if fault_injection:
                fault_injection.bind_main(thread_id)
            write_json(evidence / "thread-start.json", thread)
            turn_request = {
                "threadId": thread_id,
                "input": [skill_input, {"type": "text", "text": scenario.prompt}],
                "model": PRIMARY_MODEL, "effort": effort, "approvalPolicy": "on-request",
            }
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
            # Preserve the completed primary turn before an optional second
            # turn can fail or reach its own timeout.
            write_json(evidence / "turn-completed.json", completed)
            followup_result = None
            if followup:
                before_followup = len(host.notification_snapshot())
                followup_request = {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": (
                        "Уточни у того же исполнителя факт `" + scenario.followup_fact + "` по сохранённым данным; "
                        "нового исполнителя для этого не создавай. Если native host не даёт "
                        "адресовать именно этого исполнителя, сообщи конкретный blocker."
                    )}],
                    "model": PRIMARY_MODEL, "effort": effort, "approvalPolicy": "on-request",
                }
                write_json(evidence / "followup-turn-request.json", followup_request)
                followup_turn = host.call("turn/start", followup_request, timeout=60)
                followup_turn_id = followup_turn["turn"]["id"]
                write_json(evidence / "followup-turn-start.json", followup_turn)
                followup_completed = host.wait_notification(
                    lambda message: message.get("method") == "turn/completed"
                    and message.get("params", {}).get("threadId") == thread_id
                    and message.get("params", {}).get("turn", {}).get("id") == followup_turn_id,
                    timeout=timeout,
                )
                write_json(evidence / "followup-turn-completed.json", followup_completed)
                followup_result = {
                    "turn_id": followup_turn_id,
                    "completed": True,
                    "notification_start_index": before_followup,
                }
            print("native probe: turn completed; reading durable trace", flush=True)
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
            thread_after = {"source": "not requested; completed items are captured above"}
            notifications = host.notification_snapshot()
        except BaseException as error:
            failure = error
            notifications = host.notification_snapshot()
            write_json(evidence / "failure.json", {
                "error_type": type(error).__name__, "error": str(error),
                "traceback": traceback.format_exc(), "notifications": len(notifications),
                "stderr_tail": host.stderr_tail(),
            })
        finally:
            host.close()
            if fault_injection:
                fault_injection.observer_failed(host.notification_observer_errors)
                fault_state = fault_injection.finalize()
            else:
                fault_state = {"status": "not_applicable"}
        if failure is not None:
            raise failure
        ended = datetime.now(timezone.utc)
        write_json(evidence / "thread-items.json", items)
        write_json(evidence / "thread-items-source.json", items_source)
        write_json(evidence / "thread.json", thread_after)
        fixture_verification = self._verify_fixture(evidence, scenario, fault_state)
        write_json(evidence / "fixture-verification.json", fixture_verification)
        summary = self._summarize(
            evidence, thread_id, turn_id, started, ended, scenario, original_sources, followup_result,
            fixture_verification, fault_state, harness_source, stale_map_seed,
        )
        write_json(evidence / "summary.json", summary)
        return summary

    @staticmethod
    def _verify_fixture(evidence: Path, scenario: FixtureScenario,
                        fault_state: dict[str, object], verification_directory: str = "verification-work") -> dict[str, object]:
        """Reproduce multistage CLI behavior on a copy, never its model outputs."""
        if scenario.name == "mismatch-before-planned":
            actual = json.loads((evidence / "work" / "data" / "release.json").read_text(encoding="utf-8"))
            components = actual.get("active_components") if isinstance(actual, dict) else None
            source_contradiction = (actual.get("release") == "R-17" and components == ["api", "worker", "legacy"])
            output = evidence / "work" / "out" / "result.json"
            return {
                "status": "fixture_precondition_observed" if source_contradiction and not output.exists() else "fixture_precondition_not_observed",
                "expected_components": ["api", "worker"], "observed_components": components,
                "mismatch": {"unexpected_component": "legacy"},
                "final_output_absent": not output.exists(),
                "planned_output_contract_check": "not run by collector because the fixture precondition stops before output creation",
                "scope": "immutable source contradiction and output absence only; raw trace review determines whether primary scheduled an additional factual check and made an appropriate decision",
            }
        if scenario.name == "fault-after-saved-return":
            target = evidence / "work" / "out" / "result.json"
            checker = {"exit_code": None, "stdout": "", "stderr": ""}
            observed = None
            if target.is_file():
                completed = subprocess.run(
                    [sys.executable, "checks/verify_contract.py", str(target)],
                    cwd=evidence / "work", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                    text=True, capture_output=True, timeout=60, check=False,
                )
                checker = {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
                try:
                    observed = json.loads(target.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    observed = "invalid JSON"
            injected = fault_state.get("status") == "injected"
            detected = injected and observed == {"release": "R-17", "count": 3} and checker["exit_code"] != 0
            return {
                "status": "injected_requires_trace_review" if detected else "inconclusive",
                "fault_status": fault_state.get("status"), "observed_result": observed,
                "independent_contract_check": checker,
                "scope": "artifact corruption was test-only; independent checker observed the corrupted artifact, but raw native trace review must establish any primary detection or planned-check timing",
            }
        if scenario.name != "multistage-normalize-cli":
            return {"status": "not_applicable"}
        work = evidence / "work"
        verification_work = evidence / verification_directory
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def command(arguments: list[str], cwd: Path) -> dict[str, object]:
            completed = subprocess.run(arguments, cwd=cwd, env=environment, text=True,
                                       capture_output=True, timeout=60, check=False)
            return {"arguments": arguments, "cwd": str(cwd), "exit_code": completed.returncode,
                    "stdout": completed.stdout, "stderr": completed.stderr}

        primary_check = None
        repeat_cli = None
        repeat_check = None
        try:
            shutil.copytree(work / "app", verification_work / "app")
            shutil.copytree(work / "data", verification_work / "data")
            shutil.copytree(work / "checks", verification_work / "checks")
            primary_normalized = work / "out" / "normalized.json"
            primary_summary = work / "out" / "summary.json"
            primary_check = command(
                [sys.executable, "checks/verify_contract.py", str(primary_normalized), str(primary_summary)],
                verification_work,
            )
            repeat_out = verification_work / "out"
            repeat_out.mkdir()
            repeat_cli = command([
                sys.executable, "-m", "app.cli", "data/events.json",
                "out/normalized.json", "out/summary.json",
            ], verification_work)
            missing_outputs = [name for name in ("normalized.json", "summary.json")
                               if not (repeat_out / name).is_file()]
            if missing_outputs:
                return {
                    "status": "failed", "verification_work": str(verification_work),
                    "primary_contract_check": primary_check, "repeat_cli": repeat_cli,
                    "repeat_contract_check": repeat_check, "missing_repeat_outputs": missing_outputs,
                    "scope": "collector reproduction failure; command output is retained above",
                }
            repeat_check = command(
                [sys.executable, "checks/verify_contract.py", "out/normalized.json", "out/summary.json"],
                verification_work,
            )
            expected_normalized = [
                {"id": "A", "label": "alpha", "amount": 10},
                {"id": "B", "label": "beta", "amount": 0},
            ]
            expected_summary = {"count": 2, "total_amount": 10, "zero_amount_ids": ["B"]}
            primary_data = {
                "normalized": json.loads(primary_normalized.read_text(encoding="utf-8")),
                "summary": json.loads(primary_summary.read_text(encoding="utf-8")),
            }
            repeated_data = {
                "normalized": json.loads((repeat_out / "normalized.json").read_text(encoding="utf-8")),
                "summary": json.loads((repeat_out / "summary.json").read_text(encoding="utf-8")),
            }
            exact_outputs = primary_data == {"normalized": expected_normalized, "summary": expected_summary}
            repeat_matches_primary = repeated_data == primary_data
            passed = all(item["exit_code"] == 0 for item in (primary_check, repeat_cli, repeat_check)) \
                and exact_outputs and repeat_matches_primary
            return {
                "status": "passed" if passed else "failed", "verification_work": str(verification_work),
                "primary_contract_check": primary_check, "repeat_cli": repeat_cli,
                "repeat_contract_check": repeat_check, "primary_data": primary_data,
                "repeated_data": repeated_data, "exact_outputs": exact_outputs,
                "repeat_matches_primary": repeat_matches_primary,
            }
        except Exception as error:
            return {"status": "failed", "verification_work": str(verification_work),
                    "primary_contract_check": primary_check, "repeat_cli": repeat_cli,
                    "repeat_contract_check": repeat_check,
                    "error_type": type(error).__name__, "error": str(error)}

    def reassess_saved_multistage(self, evidence: Path) -> dict[str, object]:
        """Post-hoc collector-only reassessment in a fresh copy of saved work."""
        evidence = evidence.resolve()
        base_name = "posthoc-verification-work"
        sequence = 1
        verification_directory = base_name
        while (evidence / verification_directory).exists():
            sequence += 1
            verification_directory = base_name + "-" + str(sequence)
        scenario = SCENARIOS["multistage-normalize-cli"]
        result = self._verify_fixture(
            evidence, scenario, {"status": "not_applicable"},
            verification_directory=verification_directory,
        )
        record = {
            "label": "posthoc_collector_fix",
            "purpose": "reproduce the saved actual fixture after fixing the collector CLI invocation",
            "original_fixture_verification": "fixture-verification.json",
            "result": result,
            "scope": "No model turn or saved model artifact was changed; this is a fresh independent collector work copy.",
        }
        write_json(evidence / "corrected-fixture-verification.json", record)
        return record

    @staticmethod
    def _summarize(evidence: Path, thread_id: str, turn_id: str, started: datetime, ended: datetime,
                   scenario: FixtureScenario, original_sources: dict[str, bytes],
                   followup: dict[str, object] | None, fixture_verification: dict[str, object],
                   fault_state: dict[str, object], harness_source: dict[str, object],
                   stale_map_seed: dict[str, object]) -> dict[str, object]:
        def jsonl(path: Path) -> list[object]:
            if not path.exists():
                return []
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

        raw_notifications = jsonl(evidence / "notifications.jsonl")
        items = json.loads((evidence / "thread-items.json").read_text(encoding="utf-8")).get("data", [])
        if not isinstance(items, list):
            raise AssertionError("thread/items/list did not return data")
        mcp_items = [item for item in items if item.get("type") == "mcpToolCall"]
        mcp_names = [item.get("tool") or item.get("toolName") or item.get("name") for item in mcp_items]
        collab_items = [item for item in items if item.get("type") == "collabAgentToolCall"]
        spawned = [item for item in collab_items if item.get("tool") == "spawnAgent"]
        actor_threads = sorted({thread_id} | {
            candidate for item in collab_items
            for candidate in [item.get("senderThreadId"), *(item.get("receiverThreadIds") or [])]
            if isinstance(candidate, str)
        })
        work = evidence / "work"
        knowledge_paths = sorted(path for path in work.glob(".pcw/*/knowledge/**/*.md") if path.is_file())
        knowledge = [path.relative_to(work).as_posix() for path in knowledge_paths]
        marker_locations = {marker: [] for marker in scenario.required_knowledge_markers}
        for path in knowledge_paths:
            content = path.read_text(encoding="utf-8")
            relative = path.relative_to(work).as_posix()
            for marker in marker_locations:
                if marker in content:
                    marker_locations[marker].append(relative)
        server_requests = jsonl(evidence / "server-requests.jsonl")
        server_decisions = jsonl(evidence / "server-decisions.jsonl")
        mcp_observations = []
        subagent_activities = []
        notification_threads = {thread_id}
        for notification_index, notification in enumerate(raw_notifications):
            if not isinstance(notification, dict):
                continue
            params = notification.get("params")
            if not isinstance(params, dict):
                continue
            actor_thread_id = params.get("threadId")
            if isinstance(actor_thread_id, str):
                notification_threads.add(actor_thread_id)
            item = params.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") == "mcpToolCall" and notification.get("method") == "item/completed":
                mcp_observations.append({
                    "notification_index": notification_index,
                    "emitted_at_ms": notification.get("emittedAtMs"),
                    "thread_id": actor_thread_id,
                    "id": item.get("id"), "tool": item.get("tool"),
                    "status": item.get("status"), "duration_ms": item.get("durationMs"),
                })
            if item.get("type") == "subAgentActivity":
                child_thread = item.get("agentThreadId")
                if isinstance(child_thread, str):
                    notification_threads.add(child_thread)
                subagent_activities.append({
                    "notification_index": notification_index,
                    "event": notification.get("method"),
                    "emitted_at_ms": notification.get("emittedAtMs"),
                    "parent_thread_id": actor_thread_id,
                    "agent_path": item.get("agentPath"),
                    "agent_thread_id": child_thread,
                    "activity_kind": item.get("kind"),
                    "activity_id": item.get("id"),
                })
        immutable_sources = {
            relative: (work / relative).is_file() and (work / relative).read_bytes() == original
            for relative, original in original_sources.items() if not scenario.permits_mutation(relative)
        }
        forbidden_paths_absent = {relative: not (work / relative).exists() for relative in scenario.forbidden_paths}
        unexpected_project_paths = sorted(
            path.relative_to(work).as_posix() for path in work.rglob("*")
            if path.is_file() and ".pcw" not in path.relative_to(work).parts
            and path.relative_to(work).as_posix() not in original_sources
            and not scenario.permits_mutation(path.relative_to(work).as_posix())
        )
        if followup is not None:
            new_starts = [activity for activity in subagent_activities
                          if activity["event"] == "item/started"
                          and activity["activity_kind"] == "started"
                          and activity["notification_index"] >= followup["notification_start_index"]]
            followup = {**followup, "new_subagent_start_count": len(new_starts),
                        "new_subagent_starts": new_starts}
        result = {
            "scope": "raw observed trace; independently assessed separately",
            "scenario": scenario.name,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "ended_at": ended.isoformat().replace("+00:00", "Z"),
            "thread_id": thread_id,
            "turn_id": turn_id,
            "mcp_tool_count": len(mcp_items),
            "mcp_tools": mcp_names,
            "mcp_tool_trace": mcp_observations,
            "collaboration_item_count": len(collab_items),
            "spawn_item_count": len(spawned),
            "actor_thread_ids": sorted(notification_threads),
            "collaboration_referenced_thread_ids": actor_threads,
            "collaboration_items": collab_items,
            "subagent_activities": subagent_activities,
            "observed_native_executor_thread_ids": sorted({
                activity["agent_thread_id"] for activity in subagent_activities
                if isinstance(activity.get("agent_thread_id"), str)
            }),
            "notification_thread_ids": sorted(notification_threads),
            "server_request_count": len(server_requests),
            "server_request_methods": [request.get("method") for request in server_requests if isinstance(request, dict)],
            "server_decision_count": len(server_decisions),
            "knowledge_markdown": knowledge,
            "knowledge_marker_locations": marker_locations,
            "required_knowledge_markers_present": {
                marker: bool(locations) for marker, locations in marker_locations.items()
            },
            "immutable_sources": immutable_sources,
            "forbidden_paths_absent": forbidden_paths_absent,
            "unexpected_project_paths": unexpected_project_paths,
            "fixture_unchanged": all(immutable_sources.values()),
            "fixture_verification": fixture_verification,
            "fault_injection": fault_state,
            "harness_source": harness_source,
            "controlled_stale_map_seed": stale_map_seed,
            "followup": followup,
        }
        return result


def subprocess_run(arguments: list[str], environment: dict[str, str]) -> str:
    """Small isolated command helper that does not write configuration."""
    import subprocess
    completed = subprocess.run(arguments, env=environment, text=True, capture_output=True, timeout=30, check=True)
    return completed.stdout


if __name__ == "__main__":
    print(json.dumps(NativeWorkflowProbe().run_simple(), ensure_ascii=False, indent=2, sort_keys=True))
