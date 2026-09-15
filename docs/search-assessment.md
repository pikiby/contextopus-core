# Оценка поиска PCW: frozen v2

## Решение

Стартовый профиль принят как калиброванный для **этого зафиксированного корпуса PCW**:

```json
{"N": 10, "d_max": 0.45, "min_jump": 0.01, "multiplier": 2.0, "metric": "cosine"}
```

Значения по умолчанию в продукте остаются прежними. Для другой модели, метрики или корпуса нужен отдельный зафиксированный набор запросов и новый подбор.

## Что проверялось

Профиль зафиксирован на CPU: `sentence-transformers`, `Qwen/Qwen3-Embedding-0.6B`, revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, 1024 измерения, `float32`, L2 normalization, `qwen3`, `local_files_only: true`. Запрос получает instruction `Given a query, retrieve relevant technical documentation.`

Корпус — 8 материалов и 84 буквальные части: `guide.md`, скил PCW и шесть справочных файлов. Части получены тестовым разделителем по заголовкам Markdown. Буквальная сохранность проверена; смысловое разделение настоящим субагентом проверяется отдельно.

Зафиксированная разметка содержит 24 калибровочных запроса (16 положительных, 8 отрицательных) и отдельные 12 отложенных запросов (8 положительных, 4 отрицательных). Положительный запрос засчитывается, когда выдача содержит хотя бы один полный `answer_set`; повторяющиеся guide/references входят в `exhaustive_relevant` только как диагностическая полнота. Два вопроса (`c12`, `h07`) требуют два материала, поскольку точные факты находятся в разных references.

Критерий выбора зафиксирован до оценки отложенных запросов: `0.5 × доля полных answer_set + 0.5 × доля отклонённых отрицательных запросов`; при равенстве — меньшее среднее число возвращённых материалов, `N`, затем лексикографически `d_max`, `min_jump`, `multiplier`. `exhaustive_material_recall`, старый eval и отложенные запросы не участвуют в выборе.

| Свидетельство | Инструмент | Фактический результат | Граница вывода |
| --- | --- | --- | --- |
| `.pcw/project-update/.pcw-runtime/verification/qwen/rerank-v2-corrected-20260915T032000Z/baseline_verification.json` | Проверка зафиксированного набора и LanceDB | SHA fixture и 8 source hashes совпали; 84 rows, vectors 1024D и finite | Использована сохранённая таблица; corpus заново не embedding-ился |
| `.pcw/project-update/.pcw-runtime/verification/qwen/rerank-v2-corrected-20260915T032000Z/{calibration_grid,report}.json` | 216 сочетаний параметров и отложенная оценка | Полный ответ / отклонение отрицательных / средняя оценка: калибровочные `0.875 / 0.625 / 0.75`; отложенные `0.75 / 1.0 / 0.875`. Русские положительные: `2/4`, английские: `4/4` | Три отрицательных калибровочных запроса вернули материалы; оценка ограничена этим набором |
| `.pcw/project-update/.pcw-runtime/verification/qwen/run-20260915T024000Z/report.json` | Базовый запуск на одном хосте | Доступны 32 CPU; запуск ограничен 4 потоками и 10 GiB адресного пространства. Пик оперативной памяти: `4,035,012 KiB`; загрузка модели: `4,583 ms`; индексирование 84 частей: `157,134 ms` | Измерения одного процесса на одном компьютере |
| `.pcw/project-update/.pcw-runtime/verification/qwen/{probe-20260915T025100Z,probe-batch1-verified-20260915T032100Z}/probe.json` | Product batch из 32 самых длинных частей | Первый запуск: allocator failure через 68 s, peak RSS `9,182,924 KiB`; verified запуск: `ok`, `116,441 ms`, peak RSS `4,006,292 KiB`, vectors within tolerance | Один воспроизведённый отказ и один успешный batch не объясняют reboot |

Selector в runtime применяет порядок `N → d_max → first median-positive-gap → material dedup`; assessment использует те же правила. См. `plugins/persistent-context-workspace/pcw_runtime/runtime.py` и `tests/qwen_search_assessment.py`.

## Память и reboot

Первый probe `.pcw/project-update/.pcw-runtime/verification/qwen/probe-20260915T025100Z/probe.json` воспроизвёл отказ выделения памяти в неизменённом product default batch из 32 частей: 4 threads, limit 10 GiB, 68 s от `started` до failure и peak RSS `9,182,924 KiB` (8.76 GiB). Внешний контракт сообщает `EmbeddingError`; альтернативный provider не использовался.

Отдельный поздний probe `.pcw/project-update/.pcw-runtime/verification/qwen/probe-batch1-20260915T031500Z/` сначала завершил encode: `events.jsonl` содержит `completed` c `wall_ms: 114678.056`, а затем упал на `NameError: name 'math' is not defined` в assessment instrumentation. Он не заменяет и не отменяет исходный memory failure. Следующий `.pcw/project-update/.pcw-runtime/verification/qwen/probe-batch1-verified-20260915T032100Z/probe.json` успешно завершил тот же batch и совпал с baseline vectors в пределах tolerance.

Ни неуспешный probe, ни успешный batch-32 probe не устанавливают причину reboot: в этих артефактах нет события reboot, kernel/OOM logs или корреляции с состоянием хоста. Допустимый вывод ограничен наблюдаемыми процессными измерениями выше.

## Воспроизведение

Runner: `tests/qwen_search_assessment.py`. Команды ниже приведены для будущего авторизованного запуска и **не исполнялись при подготовке этого отчёта**; каждая требует нового несуществующего output directory.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/qwen_search_assessment.py \
  --rerank-v2 \
  --baseline .pcw/project-update/.pcw-runtime/verification/qwen/run-20260915T024000Z \
  --v2-fixture .pcw/project-update/.pcw-runtime/verification/qwen/queries-v2-corrected-corpus-hash.json \
  --v2-fixture-sha256 2e217c01353b9e181c2020737ef97a354e03a1517f7ecd84cb448155ce64136c \
  --output ".pcw/project-update/.pcw-runtime/verification/qwen/rerank-v2-$(date -u +%Y%m%dT%H%M%SZ)"

PYTHONDONTWRITEBYTECODE=1 python3 tests/qwen_search_assessment.py \
  --probe-default-batch \
  --baseline .pcw/project-update/.pcw-runtime/verification/qwen/run-20260915T024000Z \
  --output ".pcw/project-update/.pcw-runtime/verification/qwen/probe-batch1-$(date -u +%Y%m%dT%H%M%SZ)"
```

`--rerank-v2` переиспользует зафиксированные baseline parts/vectors и embedding-ит только v2 queries. `--probe-default-batch` пропускает retrieval assessment и проверяет product-provider batch из 32 частей. Оба режима используют локальный pinned snapshot; не запускать их одновременно.

Этот отчёт покрывает только retrieval assessment и resource probes, а не приёмку всего проекта.
