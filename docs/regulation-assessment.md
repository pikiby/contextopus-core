# Аудит текстовых регламентов PCW

> Historical assessment: the role assignments and native traces below describe earlier releases. They do not validate the current primary-only memory workflow or its assignment-level prohibition. Current validation is recorded in [primary-memory-assessment.md](primary-memory-assessment.md).


Дата: 2026-09-15. Область: `README.md`, `PLAN.md`, `skills/pcw/SKILL.md` и
ссылочные инструкции этого скила. Это сопоставление текста с
`plugin-update-design.md`. Отдельный раздел ниже проверяет narrow contract
`pcw_save_subagent_result` в runtime и MCP; документ не принимает нативные
выполнения.

## Вывод

Семь ранее обнаруженных точечных проблем исправлены и повторно сверены. В
проверенном тексте остальные рассмотренные требования руководящего документа
выражены без существенного противоречия.

### Guarded raw-save: отдельная проверка 2026-09-15

Эта проверка расширяет область данного документа только для
`pcw_save_subagent_result`; она не является приёмкой нативного workflow. Обычная
запись и guarded replacement соответствуют `plugin-update-design.md` §2 и
§13.2: `runtime.py:411` сохраняет переданный Markdown без преобразования,
`runtime.py:445` требует для замены того же filename-ID совпадающий
`expected_previous_revision`, а `runtime.py:438` — того же actual
`executor_session_id`. Успешная замена
сохраняет links, получает новую UTC `saved_at`, становится
`pending_preparation` и удаляет старые search rows. Точная повторная доставка
body от того же исполнителя возвращает `already_saved` с исходной отметкой
времени. Динамическая регистрация `server.py:77-95` публикует именно эту
сигнатуру как `pcw_save_subagent_result`.

`SKILL.md`, `native-assignments.md`, `memory-operations.md`,
`action-requirements.md` и README согласованно требуют primary save raw body,
затем `pcw_read`, до semantic decision или acceptance. Для memory/Git-return
инструкции также требуют affected filename-ID, Current path при изменении и
actual status; generic completion или устаревший список не принимаются.

Проверка `test_runtime.py:454-532` покрывает exact body, same executor, CAS,
links, новую timestamp, pending, stale revision, другой executor, ordinary
material, exact retry и отказ authoritative `_save`. Отдельный controlled repro
в `/tmp` искусственно прервал `_delete_rows` уже после `_save`. Этот вызов
вернул ошибку, а между вызовами оставил partial state: новый body/revision и
старую derived search row. Это не ложный публичный успех: первый последующий
`pcw_read`, `pcw_search` или exact retry входит в `_guard` и вызывает
`_reconcile`. `pcw_read` возвращает новый body как `pending_preparation`,
`pcw_search` не выдаёт старую row и сообщает pending, а exact retry возвращает
`already_saved`. Следовательно,
это recoverable partial-write limit, а не доказательство полного rollback
файла и LanceDB. Существующий тест не покрывает этот failure point, поэтому
полная транзакционность file+index не заявляется.

Переданный `expected_previous_revision` при отсутствующем `material_name` не
меняет ветку first save: `runtime.py:423-459` создаёт новый raw material и не
сверяет revision, потому что existing record отсутствует. Это не противоречит
зафиксированному контракту: guarded replacement описан только для существующего
raw-result material того же executor; создание и замена различны. Но параметр
не служит доказательством, что удалённый прежний material не был заново создан.
Если клиенту нужна именно проверка отсутствия удаления, это потребует отдельного
контракта, которого guide и текущие инструкции не устанавливают.

| Статус | Где | Ранее найденное расхождение | Подтверждённое исправление |
| --- | --- | --- | --- |
| Исправлено | `skills/pcw/references/prepare-search.md:5` | Инструкция безусловно задавала `fork_turns: "none"`, конкретный параметр Codex, хотя PCW рассчитан на разные агентские среды. | Теперь требуется чистый контекст, когда его поддерживает хост; `fork_turns: "none"` назван вариантом именно для Codex. |
| Исправлено | `README.md:38`, `PLAN.md:23`, `skills/pcw/references/memory-operations.md:15` | Текст говорил, что rename всегда меняет filename-ID и path, хотя при отдельном path перенос с тем же basename не меняет ID. | Текст различает обновление path/search rows в любом случае и смену ID/exact incoming links только при смене basename; пример `a.md` → `nested/a.md` сохраняет ID и links. |
| Исправлено | `skills/pcw/SKILL.md:37` | Краткое правило безусловно говорило, что rename переписывает exact incoming links, расходясь с same-basename move. | Теперь search path обновляется без re-embedding, incoming links меняются только при смене filename-ID, а пример `a.md` → `nested/a.md` сохраняет ID и links. |
| Исправлено | `pcw_runtime/server.py:53`, MCP description `rename` | Выдаваемое агенту описание также безусловно связывало rename со сменой filename-ID и links. | Описание различает перемещение с тем же basename и переименование с новым filename-ID; оно согласовано с правилами ID/path и не обещает re-embedding неизменного тела. |
| Исправлено | `skills/pcw/references/action-requirements.md:9` | `prepare_assignment` требовал только подтвердить Current, поэтому первая запись пяти полей могла быть отложена до research/helper/finish. | Теперь основной агент определяет все пять полей из пользовательской задачи, поручает сохранить их через `pcw_current_set` в самом первом native assignment, включая bounded research, и читает сохранённый Current через MCP. |
| Исправлено | `skills/pcw/references/action-requirements.md:67`, `skills/pcw/references/memory-operations.md:45` | Запрет либо отсутствие authority для source-project commit ошибочно интерпретировались как запрет local memory history и consolidation в temporary PCW work location. | Текст отделяет local Current/knowledge, необходимое по решению основного агента consolidation и точный `pcw_checkpoint` от source commit; actual PCW restrictions пользователя остаются обязательными. |
| Исправлено | `skills/pcw/SKILL.md:21`, `skills/pcw/references/action-requirements.md:11` | Стартовая инструкция обязывала обобщённо использовать search/read, но не выражала guide §4 step 3: при подтверждённо пустом knowledge не искать ещё не существующую память. | Оба текста теперь велят по `pcw_status` пропустить search при пустом knowledge и прямо назначить только нужное ограниченное исследование источников; поиск и навигация возвращаются после появления релевантных знаний. |

## Проверенные соответствия

### Роли и короткий цикл

`SKILL.md:8-33`, `references/action-requirements.md:3-11` и
`references/native-assignments.md:3-23` закрепляют, что основной агент сам
строит карту моделей, прямо назначает полноценные нативные поручения, а MCP не
является Controller, диспетчером или hook. Отдельного bootstrap-исследователя
или постоянных ролей не вводят. Первичный результат сохраняется исходным текстом
с фактической сессией и читается до содержательного решения.

Уточнение `references/action-requirements.md:9` делает этот порядок применимым
непосредственно перед `prepare_assignment`: ограниченное исследование назначается
только когда не хватает интерфейсов, взаимодействий, условий изменения или
проверки для конкретной реализации. Пути к исходникам и общая формулировка
пользователя не подменяют эти факты. Поэтому текст не вводит постоянное
исследование, не переносит подготовку на исполнителя и не добавляет зависимость
от Codex. В той же инструкции основной агент сам выбирает и обосновывает объект,
момент и наблюдаемые признаки промежуточной либо финальной проверки по сложности;
решение не отдаётся worker и не возникает из одного факта возврата.

Дополнительные примеры в `references/action-requirements.md:11` буквально
соответствуют трём случаям guide §9: простое локальное изменение с финальной
проверкой, несколько взаимодействующих компонентов с промежуточной и финальной
проверками, а также проверка исследовательского вывода до зависящей реализации.
Они оставляют основному агенту выбор точного момента и пересмотр плана при новых
фактах, поэтому не вводят обязательную проверку каждого возврата.

### Current

`SKILL.md:39`, `references/memory-operations.md:39-43`, `README.md:40` и
`PLAN.md:27` задают пять читаемых разделов, компактность и обновление шага либо
препятствия только при изменении решения или препятствия. HTML-маркер длины
дополняет видимый Markdown и не заменяет его.

`references/action-requirements.md:9` теперь также закрепляет timing guide §4
step 1: в составе первого native assignment основной агент передаёт worker все
пять определённых им полей на сохранение, включая случай первого bounded research.
Предшествующее чтение Current не даёт основания отложить эту запись; затем
сохранённый Current поступает основному агенту через MCP. Формулировка не меняет
правило последующих обновлений: их не делают после каждого возврата, а связывают
с изменением решения либо препятствия.

### Пустой knowledge

`SKILL.md:21` и `references/action-requirements.md:11` прямо реализуют ветку
guide §4 step 3. После `pcw_status`, подтвердившего пустой knowledge, основной
агент пропускает поиск по нему и назначает необходимое ограниченное исследование
реальных источников. Формулировка не делает исследование постоянным: при уже
достаточном пользовательском контексте оно не требуется, а search/read остаются
операциями для существующей релевантной памяти. Эта редакция установлена в
candidate `060111`. Сообщённый текущий multistage run `060139` уже применил
ветку без поиска пустой памяти, однако до его финальной независимой приёмки это
не является доказательством завершённого workflow. Ранний installed native run
со старым snapshot остаётся историческим фактом, а не результатом нового текста.

### Подготовка поиска и уплотнение

`references/prepare-search.md:11-25` ограничивает помощника буквальным
семантическим делением одного переданного материала: без исследования исходников,
выполнения пользовательской задачи, решений об уплотнении или навигации.
`SKILL.md:31`, `README.md:42`, `PLAN.md:25` и
`references/memory-operations.md:33-37` требуют сохранить смысл, условия,
неопределённость, таблицы и код при уплотнении, при этом не делают сохранение
атрибуции источника или provenance обязательным.

### Фактические проверки и setup

`SKILL.md:33`, `references/action-requirements.md:39-59` и
`references/native-assignments.md:25-29` назначают проверки в выбранные моменты
или при требующем внимания расхождении; один только возврат их не создаёт.
`references/setup.md:3-54` сначала использует уже доступные MCP-инструменты,
затем ограниченно диагностирует, требует конкретного разрешения на установку или
загрузку и не объявляет отсутствие иной установленной среды дефектом. Упоминания
Codex в `README.md:78-86` и `references/native-assignments.md:21` явно
ограничены проверенной интеграцией или примером хоста и сами по себе переносимости
не противоречат.

Уточнения `references/action-requirements.md:47` и
`references/native-assignments.md:33` требуют сначала зафиксировать фактическое
состояние существующего артефакта и лишь затем выполнять разрешённую регенерацию
либо замену. Это сохраняет наблюдаемое расхождение для проверки, остаётся в
пределах явно разрешённого действия и не добавляет hook или автоматическое
восстановление.

### Завершение memory-цикла

Новый абзац `references/action-requirements.md:65` текстово соответствует
порядку из guide §4, шаги 5, 6 и 10, §5 и §7: основной агент определяет
итоговое содержание и links, worker применяет решение и нужный Current,
отдельная небольшая модель готовит сохранённые новые либо изменённые материалы
для поиска, а worker создаёт checkpoint точных изменённых путей, если это не
запрещено пользователем. Это правильно охватывает и новые raw-материалы
проверяющего. Требование проверить status и оставить pending preparation либо
незавершённый checkpoint явным следующим шагом или blocker не подменяет
фактическое выполнение структурным ответом `ready`.

`references/prepare-search.md:11` и `references/action-requirements.md:69`
распространяют неизменный порядок `pcw_save_subagent_result` затем `pcw_read` на
фактические raw-возвраты технического helper, memory worker и checkpoint worker.
Это сохранение результата, а не новая фактическая проверка. Допущена только
точная повторная доставка уже актуального результата того же исполнителя под тем
же именем: она использует установленную идемпотентность без новой pending-копии;
новые факты, наблюдения, ошибки и расхождения скрывать нельзя.

Уточнения `references/action-requirements.md:67` и
`references/memory-operations.md:45` соответствуют guide §4 steps 5 и 10 и
§13.5: временное расположение PCW не отменяет Current, применимое consolidation
и историю точных изменённых Current/knowledge путей. Отсутствие authority для
source-project commit не переносится на отдельный local memory checkpoint;
напротив, явные ограничения пользователя именно на PCW memory продолжают
действовать. Это устраняет ложную причину пропустить consolidation/checkpoint, не
создавая authority для source commits, pushes или внешних действий.

### Идентификатор исполнителя до чтения материалов

Уточнение в `references/action-requirements.md:11,31-33`,
`references/native-assignments.md:19-21` и `references/prepare-search.md:5-7`
соответствует требованию передавать фактический идентификатор индивидуальной
сессии, а не имя материала, путь задания или сессию основного агента. Получение
этой служебной метки до чтения рабочих материалов не является фактической
проверкой пользовательского результата. Если метка отсутствует или конфликтует,
инструкция допускает только адресное уточнение личности до первичной записи;
исходный Markdown не интерпретируется и не изменяется до `pcw_save_subagent_result`.
Это не вводит проверку после каждого возврата: основания фактических проверок
остаются плановым моментом либо требующим внимания несоответствием.

Повторное чтение собственной native metadata непосредственно перед финальным
возвратом (`references/native-assignments.md:25`,
`references/prepare-search.md:7`) и разрешение collision с ID другого исполнителя
до save согласуются с обязательностью фактической сессии в guide §2. Упоминание
`CODEX_THREAD_ID` ограничено verified Codex shell; инструкция сохраняет другой
механизм и формат идентификатора для иных сред.

### Итоговая достаточность цикла

В проверенной редакции `SKILL.md:10-17` задаёт короткий цикл с одним действием
`pcw_action_requirements` непосредственно перед работой и повторным запросом до
следующего действия. `references/action-requirements.md:5-78` распределяет
конкретные требования между подготовкой поручения, обработкой raw-возврата,
переходом и завершением. Это достаточно отражает guide о выдаче применимых
инструкций через MCP и не превращает MCP в dispatcher или lifecycle hook.

`finish:63-67` требует завершить применимые memory-операции: решение основного
агента, worker для content/Current, отдельный малый helper для новых или
изменённых материалов, checkpoint точных путей и проверку итогового status. При
`pending_preparation` или отсутствии checkpoint работа продолжается в уже
разрешённых границах; завершение с незакрытой работой допустимо только при
конкретном препятствии, требующем решения либо authority пользователя. Это
соответствует циклу guide до выполнения или такого препятствия и не выдаёт
структурный `ready`, статус или один raw-возврат за подтверждение фактического
завершения.

Переносимость сохранена: общий текст использует нативный механизм хоста, а
`fork_turns` и `CODEX_THREAD_ID` обозначены как варианты проверенной Codex-среды.
Отдельная небольшая модель ограничена буквальным делением; решение об уплотнении
остаётся у основного агента, а сохранение provenance после уплотнения не
обязательно. Raw-возврат каждого работника, включая технического helper, должен
быть сохранён и прочитан; это не создаёт новую фактическую проверку без планового
момента либо требующего внимания несоответствия.

## Проверенная редакция README, skill и references

SHA256 прочитанных файлов для этой оценки:

| Файл | SHA256 |
| --- | --- |
| `.pcw/project-update/knowledge/plugin-update-design.md` | `f672ced41aa6fea7a2643f16794418a6cddb70bbf260c8acef03fc177fa635e1` |
| `PLAN.md` | `30c24dc9caed575ff5cb343ca4546a2ca35a10be06b0c8d05cb86c6453ad168a` |
| `README.md` | `e81987bbeb07bda8301b48e21630a129ef0d7a43c8d6863939c54e538dedb79e` |
| `skills/pcw/SKILL.md` | `3066986b129c2795ac1b51ff9d2183cf23d5850e9019a3e0f235f7f55a4b0c52` |
| `skills/pcw/references/action-requirements.md` | `59aca8eacecd8bd61eccc2df09fa6328711e0a667be03c71847fb1fcb49f6f96` |
| `skills/pcw/references/memory-operations.md` | `ece608bcb5c6c029cc7926172d872b91a0c736b477ea8458a1c7a67bd59d2bd2` |
| `skills/pcw/references/native-assignments.md` | `984938e03ded5a94a221991151f7009cbd44bc1c449b920597d7fde775f1f355` |
| `pcw_runtime/runtime.py` | `4798eb1289f37857c6bb177683de5a923e4df723e8fa5f6b67eccad152335942` |
| `pcw_runtime/server.py` | `f1051bf0bd8a06ab005b6e5dc44244bfdb6ca8ad9275ea66c7838c0810d2c2ab` |
| `tests/test_runtime.py` | `8445d1ca2b0997968c6dc42ba0aca06001f58f7f0eb15ea99c903b31c426c412` |
| `tests/test_mcp_workflow.py` | `8e142399ed355fdb164d12ac6ce733416ae8281e9dc4fcbf513e62413bfbf0bd` |
| `tests/test_contracts.py` | `427149b5fe4115e4b16fa84a87eebf2a9fb554173b67913f3b7e24687fb18158` |
| `tests/test_agent_workflow.py` | `ce59ba74443a9b16019624e0e616cd114c1dbf50624717f5d5844d5650b88ef5` |

## Границы

Не оценивались embedding/search алгоритмы вне guarded raw-save recovery,
model-map/action mechanics, результаты Qwen или нативные тесты. В этой редакции
проверены `runtime.py` и динамическая регистрация `server.py` только в пределах
`pcw_save_subagent_result`; это не доказывает и не требует общей транзакции
файла и LanceDB. В частности, установленная текстовая достаточность finish-инструкции не доказывает
фактическое завершение цикла: в сообщённом simple native audit новые raw-материалы
остались `pending`, Current и checkpoint не были выполнены. Для подтверждения
полного цикла нужен отдельный native run, который действительно применит
содержание/Current, подготовит материалы и создаст checkpoint, затем проверит
полученный status. Отдельно, live run `045633` использовал прежнюю установленную
инструкцию; создание Current в первом поручении по новому тексту ещё не
подтверждено фактическим выполнением. Также native run `045633` завершился без
`pcw_checkpoint`; новое текстовое уточнение не доказывает его фактическое
исполнение в следующем запуске.

## Уточнение готовности поручения: отдельная проверка 2026-09-15

Статическое чтение итоговых точечных изменений не выявило блокирующих замечаний.
`prepare_assignment` теперь явно требует исправить недостающие предпосылки и
повторить проверку полного поручения до нативного запуска. Это уточняет guide
§2, а `ready: true` по-прежнему подтверждает только проверяемые данные.

Реальная адресная ошибка исправлена в `agent_workflow.py:565`: отсутствующая
карта при уже сохранённом окружении требует `publish_tools_map`; при отсутствии
окружения требуется `environment_check`. Новые тесты в
`tests/test_agent_workflow.py:202-265` описывают исправление профиля с повторной
проверкой, выдачу инструкций без готового поручения и обе ветки отсутствующей карты.

Цикла, запрещающего создание предпосылок, в этих изменениях нет. Требование
`ready: true` ограничено `prepare_assignment` перед запуском; описание MCP
явно оставляет создание и сохранение данных доступными. `process_result`
сохраняет порядок raw save → read, `transition` допускает получение назначенных
проверок, а `finish` требует завершить нужные проверки и операции памяти.
Новые поручения для этой работы проходят собственную проверку подготовки.

Учтён исправленный отдельный audit `interruption-assessment.json` для
`multistage-normalize-cli-thread-resume-20260915T105645Z`: primary получил
`ready: true` на строке 239 до запуска 245 и на 900 до запуска 906.
Отказы 333/357 относятся к уже запущенному worker и не предшествуют новому
запуску с его стороны. Первоначальное обвинение primary в запуске после этих
отказов не подтверждается. Здесь прочитан сохранённый раздел
`prelaunch_readiness`; raw trace повторно не исследовался.

Полный отчёт, координаты и SHA256 отдельного actor audit сохранены в
[`readiness-response-review.json`](../.pcw/project-update/.pcw-runtime/verification/acceptance/readiness-response-review.json).
Тесты, модель, MCP и native host этим reviewer не запускались; выполнение
инструкций в новом нативном запуске не подтверждается этой статической проверкой.

SHA256 редакций, прочитанных в этой проверке:

| Файл | SHA256 |
| --- | --- |
| `.pcw/project-update/knowledge/plugin-update-design.md` | `f672ced41aa6fea7a2643f16794418a6cddb70bbf260c8acef03fc177fa635e1` |
| `plugins/persistent-context-workspace/pcw_runtime/agent_workflow.py` | `451ffe3895ff809927ce5acc59c70793e0124224c3aa3340dddad74504b032ad` |
| `plugins/persistent-context-workspace/pcw_runtime/server.py` | `36c42de20a88fd9df421c476c0ab1264ec3bf374f69c9691ed6d99d9aad2bd43` |
| `tests/test_agent_workflow.py` | `1c984ca788ad39611c9ab804e2fc9140c52167d7eada128bc180eb457d0a8301` |
| `plugins/persistent-context-workspace/skills/pcw/SKILL.md` | `2c4bead7a269d6d5ec178949e44559af4138e63eb70996f16094cdbd0b2c53d4` |
| `plugins/persistent-context-workspace/skills/pcw/references/native-assignments.md` | `6bd58f2fbcb8de69c6839db998fc8ec01a8469f2d83634730a8274bf08978cc2` |
| `plugins/persistent-context-workspace/skills/pcw/references/action-requirements.md` | `8926f9a67f8e00aaa04150587c07fe486369c733025b009619ed76c5bea753e5` |
| `README.md` | `96113f28caf08354c9a11a1050d9dd5a8c43f084414f8bf3ab0aa74db886eff3` |
| `PLAN.md` | `8a192e2c5107219651175db943e7da500e7cd3a7d1169cdf3d7b313cabed382c` |
