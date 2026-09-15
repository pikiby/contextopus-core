# Независимая матрица покрытия guide PCW

> Примечание: личные пути и идентификаторы трасс/материалов обезличены; результаты измерений сохранены.

## Вывод

Реализация и регламенты покрывают обязательную модель работы из
[`plugin-update-design.md`](../.pcw/project-update/knowledge/plugin-update-design.md).
Сохранённые реальные traces подтверждают карту моделей, Current в первом поручении,
сохранение исходного raw-return с реальным ID, буквальную подготовку knowledge,
точные memory checkpoints и оба основания фактической проверки.

Multistage-прогон `060139` подтверждает исправленную ветку пустой памяти.
Содержательное уплотнение уже отдельно доказано в `prepare-context-only035538`:
там проверена сохранность условий, таблицы и кода. Его историческая ошибка metadata
относится к другому свойству — точности ID и порядка save/read, которое отдельно
подтверждено в stale trace. Guide не требует повторять независимое свойство
уплотнения на каждом кандидате или собирать все свойства в одном безошибочном запуске.

Продолжение `105645` подтвердило разрешённый checkpoint `e82b4b9` и точный
save/read его служебного возврата, затем было прервано перезагрузкой хоста.
Продолжение `112618` той же persistent thread завершило оставшиеся операции:
19 материалов подготовлены, Current и knowledge совпадают с memory Git HEAD
`573176b18ca6ad8f8718c82a7056512a413dc2fb`. Реально проверены четыре guarded
замены возвратов и два точных идемпотентных повтора после фактических проверок.
Незакрытых обязательных свойств в этом аудите не обнаружено.

Ошибочные worker-вызовы с отсутствующим profile сохранены как диагностика.
В `112618` оба запуска и все follow-ups primary предварены `ready:true`.
Выбор профиля Luna/medium подтверждён картой; аргументы модели фактического
launch в сохранённой части нового trace отсутствуют. Это граница свидетельства
данного запуска; ранее отдельно доказанное свойство explicit model сохраняется.

## Основания оценки

- Код и packaged регламенты: `plugins/persistent-context-workspace/`.
- Программное покрытие: `tests/test_runtime.py`, `tests/test_agent_workflow.py`,
  `tests/test_contracts.py`, `tests/test_mcp_workflow.py`, `tests/test_embeddings.py`
  и `tests/test_native_workflow.py`.
- Реальные native свидетельства: `stale-environment-map-20260915T052851Z` и
  `mismatch-before-planned-20260915T052929Z`, а также ранее сохранённые
  `fault-after-saved-return-20260915T044219Z`,
  `multistage-normalize-cli-20260915T045633Z`,
  `prepare-context-only-20260915T035538Z`, `simple-20260915T041550Z` и
  `multistage-normalize-cli-20260915T060139Z`.
- Прерванное продолжение той же persistent thread:
  `multistage-normalize-cli-thread-resume-20260915T105645Z/`;
  [независимая оценка прерывания](../.pcw/project-update/.pcw-runtime/verification/native/multistage-normalize-cli-thread-resume-20260915T105645Z/interruption-assessment.json)
  содержит точные event lines, SHA256, состав checkpoint и оставшиеся шаги.
- Завершённое продолжение `multistage-normalize-cli-thread-resume-20260915T112618Z/`:
  [независимая оценка](../.pcw/project-update/.pcw-runtime/verification/native/multistage-normalize-cli-thread-resume-20260915T112618Z/independent-assessment.json)
  проверяет 2931 actor-tagged notification, все восемь save/read возвратов,
  семь literal submissions, четыре checkpoint и конечные файлы.
- Финальные автоматические свидетельства текущей установки:
  `acceptance/install-20260915T112313Z/parity.json` — 34 совпадения;
  `acceptance/unit-20260915T112302Z.json` — exit 0, 121 passed, 73 subtests,
  6 skipped, 7 warnings, 13.27 s; `acceptance/host-qwen-20260915T112555Z.json` —
  fresh Codex/MCP, exit 0, 4/4, 0 skipped, 23.459 s, включая
  `expected_previous_revision`.

Seed старой карты в stale trace исключён из доказательств действий primary:
`seed-origin.json` прямо помечает его как harness-authored состояние до model turn.
Успех collector, MCP `ready`, факт наличия файла или worker claim сами по себе не
считались semantic acceptance.

## Матрица

| Guide | Обязательство | Код/регламент | Реальное свидетельство и вывод |
| --- | --- | --- | --- |
| §1, §2, §11 | Primary получает память через MCP, сам строит карту и напрямую запускает native workers; MCP не controller и не completion hook. Реальные источники, Current, изменения и checks выполняют workers. | `SKILL.md`, `native-assignments.md`, server descriptions и `agent_workflow.py` разделяют эти роли; packaged contract проверяет один explicit `$pcw` skill и отсутствие `$pcw-run`. | stale: primary `a38a` строит map; `a38c` читает fixture и записывает Current; `a38e` выполняет memory work. Ни один PCW tool не запускает worker. §11 — выполненные exclusions, не отдельные функции. |
| §2, §4.4, §13.2 | Worker формирует свободный raw Markdown; primary сначала сохраняет точный текст с `saved_at` и фактическим executor ID, затем читает его до содержательного решения. Повтор точного return идемпотентен. | `runtime.save_subagent_result` допускает новый raw того же исполнителя через guarded `expected_previous_revision`; server и регламенты требуют affected material IDs и status. Unit/host evidence выше покрывают API. | stale отдельно доказывает исходный save/read и recovery коллизии. `112618`: восемь фактических worker finals точно равны save/read; два initial saves, четыре guarded updates (1686/1691/2217/2222) и два `already_saved` (2762/2779). Updates сохраняют executor, меняют время и возвращают pending; repeats сохраняют время/revision/indexed. Каждый raw называет актуальный affected set; все версии сохранены в checkpoint history. Исторические ошибки IDs в mismatch/stale остаются историческими failures. |
| §2, §13.1, §13.6 | MCP выдаёт требования для `prepare_assignment`, `process_result`, `transition`, `finish`, сообщает missing prerequisites и проверяет наблюдаемые coordinates, но не принимает semantic decision. | `agent_workflow.py`, `action-requirements.md`; `test_agent_workflow.py` покрывает missing/ready и все четыре action. | stale/mismatch покрывают все четыре action. В `112618` primary 151 false → 167 true → launch 173; второй launch 240 true → 252. Все шесть follow-ups также после ready. Worker diagnostic false исправлены до ready (453/529/1310); worker launches отсутствуют. Finish 2808 декларирует исходные и новые проверки, final 2927 следует после status, raw-read и фактического Git-check. |
| §2, §4.7, §13.1 | Актуальная environment-bound map строится primary до launch; в profile указаны модель, reasoning, роли и conditions; stale revision нельзя использовать. | `environment_check`, `tools_map_get/publish`, canonical revision и profile validation; workflow tests покрывают stale publication/capabilities. | stale: old harness map read 160 → current discovery/refresh-required 247 → publish 262; уточнённый descriptor снова refresh-required 304 → publish 309 → первый launch 318 (`gpt-5.6-luna`, `low`, `fork_turns:none`). Это доказательство реального refresh, не «upgrade Codex». |
| §3, §8, §13.3 | Filename является единственным ID; links — точные navigation IDs. Rename/merge/reassign/delete сохраняют тела и переадресуют входящие links без самоссылок/дубликатов. | `runtime.py` operations, explicit legacy migration; tests rename failure/retry, merge-before-delete, delete incoming links, migration and link-only operations. | Реальная migration и body review сохранены в `verification/migration/`; отдельный native semantic-merge trace последней редакции отсутствует, но capability и literal preservation покрыты кодом. |
| §3, §5, §13.5 | Новый или изменённый body остаётся pending до `pcw_prepare` → small helper → literal `pcw_submit_parts`; revision/fidelity защищены; link-only change не re-embeds. | `prepare`, `submit_parts`, `reconcile`, `switch_embeddings`; runtime tests cover stale revision, omission/reordering/addition, target-only refresh and restore. `prepare-search.md` запрещает helper source research/rewriting. | stale и `prepare-context-only035538` независимо подтверждают подготовку и сохранность table/code. В `112618` отдельный helper a4d4 выполняет семь submissions, каждый — буквальное тело своего `pcw_prepare` с неизменённой revision. Guarded raw updates действительно требуют новой подготовки. Final 2794: 19 materials, pending 0, unregistered 0. |
| §3, §6 | Default local Qwen profile, LanceDB parts with material ID/path, bounded candidate selection `N → d_max → first median-positive-gap → dedup`; switching is atomic and does not silently reuse incompatible vectors. | `embeddings.py`, `runtime.select_candidates`, provider/switch tests. | `docs/search-assessment.md` records real pinned Qwen corpus/index and calibration; this bounds quality rather than claiming universal recall. stale status exposes active Qwen profile only after actual preparation. |
| §4.1, §13.4 | First native assignment includes the primary-decided five Current fields; worker writes readable Markdown, primary reads it. | `current_set/get`, legacy conversion tests; `action-requirements.md` makes first assignment explicit. | stale: first worker assignment 314 requires all five; `pcw_current_set` 433 precedes fixture source work; primary rereads 483. Current `060139` independently repeats the order: a3aa writes all five at 396 before sources at 403. mismatch likewise records all five at 329. Older late-Current traces remain historical failures, not evidence for current behavior. |
| §4.2–10 | Existing knowledge is searched/read through MCP; empty knowledge starts bounded source research; primary selects checks by task complexity, then workers apply content/Current/Git decisions. | `SKILL.md` and `action-requirements.md` say to skip search for established empty knowledge; memory operations keep durable mutations worker-owned. | `mismatch052929` reflects the former installed behavior and remains a historical failure. Current `060139` starts with `materials=0`, `pending=0` (event 100), publishes the map, launches bounded source research, and has no `pcw_search` before that launch; worker a3aa writes Current before source reading (396 → 403). |
| §7 | Primary decides actual consolidation after saved/read material; worker applies final content/links; preserve conditions, tables and code; do not manufacture summary-only duplicates. Cost comparison is conditional when a split/common body is proposed. | `merge/update/reassign/delete` plus literal preparation; runtime merge/link tests preserve bodies and navigation mechanics. | `prepare-context-only-20260915T035538Z` independently assessed meaningful consolidation and preservation of conditions/table/code. Its raw-ID metadata flaw is a distinct §2 property, not a reason to discard demonstrated semantic preservation. stale independently proves correct ID/save-read/checkpoint handling. No mandatory split is inferred when a task has no duplicate requiring it. |
| §8 | Links are untyped navigation, created/changed only from primary decision, exact IDs, no graph inference or global semantic traversal. | `links/reassign/rename/delete/merge` and tests; server descriptions prohibit automatic semantic merge. | Migration/runtime evidence covers exact rewrite and deletion. This behavior is conditional on a decision to link; it is not required in every native task. |
| §9, §13.6 | Planned checks have an object, expected observation and moment; mismatch before the planned moment causes an additional factual check; checker raw is saved/read; acceptance follows actual observations. No check merely because a return arrived. | `transition`/`finish` rules and coordinates in `agent_workflow.py`; assignments require check scope, signs and source boundaries. | `fault-after-saved-return` proves false-success detection by a planned check before acceptance and repair/recheck. `mismatch-before-planned` proves an additional checker after immutable `R-17` mismatch before planned final stage; it reports a concrete blocker and does not accept output. `045633` proves planned research, intermediate component and independent final checks. stale proves no-change source verification. |
| §9.3, §4.10 | Unresolved scope/authority issue is returned with established facts and concrete blocker; unproven result is not accepted. | `native-assignments.md` and finish instructions require blocker/current honesty. | mismatch: actual immutable `legacy` conflicts with contract; output/checker are intentionally not run, Current retains blocker and final reports non-acceptance. Resume `064127` records the auto-review refusal in Current and asks for authorization. In `105645`, the separately retained explicit user permission resolves that authority issue; interruption after checkpoint is remaining execution work. All nine protected source/output hashes still match the pre-turn snapshot. |
| §10, §12 | The CSV narrative is illustrative; inconspicuous knowledge-vs-reality mismatches remain explicitly deferred. | No product behavior is required by the example or deferred item. | Not applicable; no missing implementation is inferred. |
| §13.5 | Memory history is a worker's exact-path local checkpoint, separate from source-project Git authority. | `checkpoint/restore`, exact path validation and tests; `memory-operations.md` distinguishes temporary PCW from a user prohibition. | stale, `060139`, `064127` and `105645/e82b4b9` retain earlier exact history. `112618` adds `876866e`, `03a1cfe`, `d3f4989`, `573176b`: changed files are subsets of the exact requested memory sets; unchanged requested paths are verified. Final 2450 confirms Current/knowledge clean; independent Git audit confirms all 19 knowledge files and Current tracked and byte-equal HEAD. Only the three preserved baseline/repro files remain untracked. |

## Закрытие прежних gaps

Свидетельства распределены по реальным сценариям: `060139` доказывает актуальную
ветку пустой памяти, `prepare-context-only035538` — семантическую сохранность
уплотнения, stale — сохранение/чтение возврата и checkpoint. Это допустимое
раздельное доказательство независимых свойств.

Исторические defects §2 по **affected material ID** установлены: последний
exact-repeat в `mismatch052929` не называет `pcw-recovered.md`, а последний raw
`stale052851` называет `pcw-completion.md` вместо фактического
`pcw-final-status.md`. Регламенты теперь требуют актуальные affected IDs/status;
runtime/server поддерживают guarded replacement того же raw-material.
`acceptance/guarded-raw-save-review.json` завершён: независимый аудитор подтвердил
соответствие публичного save/read/search/retry и инструкций заявленному контракту,
отдельно записав восстановление после частичной записи при отказе индекса.
Конечная native-проверка исправленного механизма выполнена в `112618`.
`105645` отдельно подтвердил свежий raw с верными affected IDs и executor ID;
`112618` добавил guarded updates, подготовку изменённых тел и честные точные
повторы по тем же affected IDs после фактического checkpoint/read. Последние
save/read 2762/2772 и 2779/2789 возвращают `already_saved` и `indexed` с прежними
временем и revision. Это закрывает прежний gap без повторения остальных native свойств.

`060139` остановился лимитом collector после продуктовой приёмки. Continuation
`064127` подготовил все материалы (`pending_count=0`) и завершился с честным
blocker: auto-review не разрешил ещё один локальный checkpoint служебных записей.
В `105645/user-continuation.json` сохранён прямой ответ пользователя:
«Разрешаю checkpoint этой тестовой памяти, включая служебные возвраты».
Это разрешение уже применено: checkpoint `e82b4b9` содержит ровно `current.md`,
`knowledge/resume-final-checkpoint.md`, `knowledge/resume-checkpoint-blocker.md`
и `knowledge/resume-blocker-current.md`; рабочие файлы совпадают с commit.
Три прежних service bodies сохранены буквально. `baseline.json` и два файла
`verification-repro-01a0a3b4/` остались неизменными разрешёнными untracked
артефактами вне требуемого checkpoint.

Последний доказанный шаг `105645`: primary сохранил и прочитал
`authorized-memory-checkpoint.md` с `saved_at=2026-09-15T11:03:31.585346Z`,
затем после `prepare_assignment ready:true` запустил search helper
`trace-redacted-02` (900 → 906). Trace заканчивается
в `2026-09-15T11:04:49.745Z`; результат helper, `pcw_prepare/pcw_submit_parts`
после сохранения raw и завершение основного turn отсутствуют.
`host-restart-observation.json` подтверждает потерю прежнего процесса после
перезагрузки; причину перезагрузки эта оценка не устанавливает.

Эти оставшиеся шаги завершены в `112618`: восемь raw returns сохранены и
прочитаны, все текущие тела подготовлены, Current и knowledge зафиксированы.
Основной turn `trace-redacted-03` той же thread
`trace-redacted-01` завершён за 927659 ms без ошибки.
Смысловая приёмка основана на raw/checkpoint/status и независимой проверке
файлов; terminal collector сам по себе не служит приёмкой.

В новом snapshot все 159 файлов совпадают с manifest. Все девять файлов `app/`,
`data/`, `spec/`, `checks/`, `out/` сохраняют исходные SHA256; 17 прежних
knowledge files не изменены. Изменены Current и добавлены ровно два материала:
`restart-memory-checkpoint.md`, `restart-memory-preparation.md`.

В прежнем аудите `105645` после первого точного сравнения 151 файла снимка изменились байты
его `.git/index`; повторное чтение подтверждает прежние 14 tracked paths,
режимы и blob IDs из snapshot HEAD. Это ограничение целостности Git-метаданных
записано в assessment; исходные файлы и тела памяти по отдельным хешам сохранны.

## Limits

This review does not claim a full retrieval-recall guarantee, an actual external
embedding-service test, a universal freshness detector, or an automatic proof that
every future primary follows the skill. Those are either expressly outside the guide
or must be evaluated from the next real trace.

`112618/thread-items.json` contains only the first 100 items from an older turn,
with a nonempty `nextCursor`. This audit therefore uses the complete retained
2931-line notifications stream and explicit `params.threadId` for actor attribution.
The stream records current profile selection and actual child IDs but omits native
launch model/reasoning arguments. The historical independent explicit-model
evidence remains applicable; no extra all-properties native rerun is inferred.
