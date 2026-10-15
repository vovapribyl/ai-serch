# Задачи: пополнение поискового корпуса

v1 / 2026-10-12 / подготовлено по утверждённому техническому плану; **baseline перенесён; реализация и проверки продолжаются по чекбоксам ниже**.
Входы: [spec](spec.md), [plan](plan.md), [data-model](data-model.md), [контракты](contracts/application.md).
Ветка codex/upload-optimiz. Все исходники/тесты ниже — предлагаемые пути из plan,
кроме выбранного baseline; задачи не заявляют наличие новой реализации.

Порядковые номера — локальные номера строк задач, не новое пространство T-*.
Метки историй используют существующие UC-007/008/009/010 вместо нового US*.
Это адаптация шаблона Spec Kit к AGENTS; чекбоксы и точные пути сохраняются.
[P] разрешает параллельную работу только после всех предшествующих зависимостей.

Каждая проверяемая единица следует RED→GREEN→REFACTOR. RED — ожидаемый отказ
из-за поведения, не ошибка импорта. Для запуска теста допустимы только согласованные
типы/порты и неисполняемый каркас; поведение реализуется после подтверждённого RED.
После GREEN сохранять evidence тестов. Не отмечать выполненным gate без его фактического основания.

## Фаза 1. Baseline и допуски

Общий prerequisite B0; никакого нового поведения до согласования source manifest.

- [x] 001 Подготовить specs/001-corpus-replenishment/baseline-manifest.json: hashes выбранных source/tests/migration из сохранённого checkout и соответствий текущей ветке; исключить unrelated dirty изменения и restricted данные.
- [x] 002 Зафиксировать owner approval manifest/baseline в specs/001-corpus-replenishment/research.md; без него перенос не выполнять. Отдельно определить немодельные test dependencies, без обновления ML locks.
- [x] 003 Перенести согласованный baseline src/product_search/search/nail_*.py, infrastructure/nail_*.py, services/candidate_i и связанные тесты строго по baseline-manifest.json; сначала diff, затем немодельные regression tests; источники не сбрасывать.
- [x] 004 Подготовить допуски временной test DB и native fake probe в specs/001-corpus-replenishment/quickstart.md; рабочий DSN/реальный корпус запрещены. Отсутствующий допуск блокирует соответствующие проверки, не весь unit TDD.

## Фаза 2. Общие контракты и foundation

Plain DTO/порты и зависимости ядра; foundation до всех историй.

- [x] 005 RED — DTO и проверка пакета: написать и запустить tests/test_replenishment_contracts.py; проверить ожидаемый отказ: missing/неположительные finite deadlines, invalid profile, invalid states; поля и ограничения data-model/ExecutionPackage.
- [x] 006 GREEN — реализовать DTO и проверка пакета в src/product_search/search/replenishment_contracts.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 007 REFACTOR — упростить src/product_search/search/replenishment_contracts.py при повторном проходе tests/test_replenishment_contracts.py и релевантных boundary/regression тестов.
- [x] 008 RED — граница core/ports: написать и запустить tests/test_replenishment_boundaries.py; проверить ожидаемый отказ: core не зависит от SQL/HTTP/OS/ML; plain DTO и fake clock по contracts/application.md.
- [x] 009 GREEN — реализовать граница core/ports в src/product_search/search/replenishment_ports.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 010 REFACTOR — упростить src/product_search/search/replenishment_ports.py при повторном проходе tests/test_replenishment_boundaries.py и релевантных boundary/regression тестов.

## Фаза 3. Обработка партии и публикация — P1

История spec1: UC-007 + UC-010. Независимая проверка: выбранный товар в одной партии проходит до публикации; fake adapters, затем отдельно интеграция.

- [x] 011 [UC-007] RED — выбор/допуск/готовность: написать и запустить tests/test_replenishment_rules.py; проверить ожидаемый отказ: до5 фото, empty queue, limits, no auto next batch; все выбранные фото терминальны + хотя бы одно OK; 7 фото не публикуются после первых5.
- [x] 012 [UC-007] GREEN — реализовать выбор/допуск/готовность в src/product_search/search/corpus_replenishment.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 013 [UC-007] REFACTOR — упростить src/product_search/search/corpus_replenishment.py при повторном проходе tests/test_replenishment_rules.py и релевантных boundary/regression тестов.
- [x] 014 [UC-007] RED — controller стадий: написать и запустить tests/test_replenishment_controller.py; проверить ожидаемый отказ: I/encoder последовательно, stage checkpoint до признания COMPLETE, ERROR/NO_NAILS различаются, независимые фото продолжаются.
- [x] 015 [UC-007] GREEN — реализовать controller стадий в src/product_search/search/corpus_replenishment.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 016 [UC-007] REFACTOR — упростить src/product_search/search/corpus_replenishment.py при повторном проходе tests/test_replenishment_controller.py и релевантных boundary/regression тестов.
- [x] 017 [UC-007] RED — mode handoff и lifecycle: написать и запустить tests/test_replenishment_lifecycle.py; проверить ожидаемый отказ: поиск racing DRAINING, атомарный admission, bounded drain, все search/I holders вышли до BUILD, epoch/token; FD наследуется через exec, parent death не допускает второй режим.
- [x] 018 [UC-007] GREEN — реализовать mode handoff и lifecycle в src/product_search/infrastructure/replenishment_supervisor.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 019 [UC-007] REFACTOR — упростить src/product_search/infrastructure/replenishment_supervisor.py при повторном проходе tests/test_replenishment_lifecycle.py и релевантных boundary/regression тестов.
- [x] 020 [UC-007] RED — schema и state repository: написать и запустить tests/test_replenishment_postgres_integration.py; проверить ожидаемый отказ: отдельная разрешённая test DB: unique head(corpus,product), unique(snapshot,product), unique attempt(photo,stage,model,attempt_no), model_key localization пустая строка; FK revision принадлежит товару; immutable READY; epoch/head/version CAS.
- [x] 021 [UC-007] GREEN — реализовать schema и state repository в migrations/versions/corpus_replenishment_v1.py и src/product_search/infrastructure/replenishment_repository.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 022 [UC-007] REFACTOR — упростить migrations/versions/corpus_replenishment_v1.py и src/product_search/infrastructure/replenishment_repository.py при повторном проходе tests/test_replenishment_postgres_integration.py и релевантных boundary/regression тестов.
- [x] 023 [UC-007] RED — file checkpoint adapter: написать и запустить tests/test_replenishment_artifacts.py; проверить ожидаемый отказ: partial files, path escape/symlink, sync/rename/commit fault, hash conflict, duplicate receipt; bounded finite vectors и immutable final; последний commit только controller.
- [x] 024 [UC-007] GREEN — реализовать file checkpoint adapter в src/product_search/infrastructure/replenishment_artifacts.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 025 [UC-007] REFACTOR — упростить src/product_search/infrastructure/replenishment_artifacts.py при повторном проходе tests/test_replenishment_artifacts.py и релевантных boundary/regression тестов.
- [x] 026 [UC-010] RED — catalog publication transaction: написать и запустить tests/test_replenishment_publication.py; проверить ожидаемый отказ: в test DB после допуска: owner→run→head→revision→active; current head CAS; superseded READY rejected; STOP race, lost receipt, profile всех членов; SUCCEEDED/FAILED/UNKNOWN per revision; no duplicate/loss other products.
- [x] 027 [UC-010] GREEN — реализовать catalog publication transaction в src/product_search/infrastructure/replenishment_repository.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 028 [UC-010] REFACTOR — упростить src/product_search/infrastructure/replenishment_repository.py при повторном проходе tests/test_replenishment_publication.py и релевантных boundary/regression тестов.
- [x] 029 [UC-010] RED — snapshot runtime binding: написать и запустить tests/test_replenishment_catalog_binding.py; проверить ожидаемый отказ: один snapshot/query, content/profile/runtime/claims mismatch; synthetic legacy/snapshot CatalogProduct order и matching parity без изменения scoring.
- [x] 030 [UC-010] GREEN — реализовать snapshot runtime binding в src/product_search/search/replenishment_contracts.py и infrastructure/replenishment_repository.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 031 [UC-010] REFACTOR — упростить src/product_search/search/replenishment_contracts.py и infrastructure/replenishment_repository.py при повторном проходе tests/test_replenishment_catalog_binding.py и релевантных boundary/regression тестов.
- [x] 032 [UC-007] RED — CLI и unavailable представление: написать и запустить tests/test_replenishment_cli.py; проверить ожидаемый отказ: grammar/exit codes contracts/cli.md, private IPC к sole supervisor, help без БД/ML, busy mapping; role CHECK не запускает build.
- [x] 033 [UC-007] GREEN — реализовать CLI и unavailable представление в src/product_search/infrastructure/replenishment_cli.py и src/product_search/web/app.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 034 [UC-007] REFACTOR — упростить src/product_search/infrastructure/replenishment_cli.py и src/product_search/web/app.py при повторном проходе tests/test_replenishment_cli.py и релевантных boundary/regression тестов.
- [x] 035 [UC-007] Проверить вертикальный fake сценарий запуска→стадии→публикация→возврат поиска в tests/test_replenishment_flow.py; RED до интеграционного wiring, GREEN только после предыдущих циклов; сверить summary с сохранённым состоянием.

## Фаза 4. Продолжение — P1

История spec2 / UC-008; prerequisite общий controller/стадии. Отдельная проверка начинается с подготовленных checkpoints, не требует предыдущего реального ML.

- [x] 036 [UC-008] RED — resume и reconciliation: написать и запустить tests/test_replenishment_resume.py; проверить ожидаемый отказ: reuse пригодных стадий, damaged/profile mismatch rejected, old live worker refusal, INTERRUPTED != ERROR, неизвестный commit сверить receipt без повторного ML.
- [x] 037 [UC-008] GREEN — реализовать resume и reconciliation в src/product_search/search/corpus_replenishment.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 038 [UC-008] REFACTOR — упростить src/product_search/search/corpus_replenishment.py при повторном проходе tests/test_replenishment_resume.py и релевантных boundary/regression тестов.
- [x] 039 [UC-008] RED — warning/STOP и clocks: написать и запустить tests/test_replenishment_waiting.py; проверить ожидаемый отказ: fake clock300s/30s, конец окна/cleanup reserve, warning без reset deadline, critical/unknown/stale приоритет, no new publication и no automatic restart.
- [x] 040 [UC-008] GREEN — реализовать warning/STOP и clocks в src/product_search/search/corpus_replenishment.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 041 [UC-008] REFACTOR — упростить src/product_search/search/corpus_replenishment.py при повторном проходе tests/test_replenishment_waiting.py и релевантных boundary/regression тестов.
- [x] 042 [UC-008] Проверить восстановление после завершения процесса в tests/test_replenishment_recovery_flow.py: RED до wiring recovery, затем GREEN; ready states переживают restart, supervisor startup закрыт до сверки; остановка чужих процессов запрещена.

## Фаза 5. Ручной повтор — P2

История spec3 / UC-009; отдельная проверка с фото ERROR либо publication FAILED/UNKNOWN. Не считать отсутствие автоматического retry пропущенной функцией.

- [x] 043 [UC-009] RED — ручной retry: написать и запустить tests/test_replenishment_retry.py; проверить ожидаемый отказ: только выбранные ошибки, новая current revision/head CAS после изменения terminal photo, старая published редакция сохранена; manual publication retry reuse ML и reconciliation UNKNOWN.
- [x] 044 [UC-009] GREEN — реализовать ручной retry в src/product_search/search/corpus_replenishment.py до прохождения предыдущих тестов; не ослаблять ожидаемые результаты.
- [x] 045 [UC-009] REFACTOR — упростить src/product_search/search/corpus_replenishment.py при повторном проходе tests/test_replenishment_retry.py и релевантных boundary/regression тестов.
- [x] 046 [UC-009] Интегрировать retry-photo/retry-publication команды через tests/test_replenishment_cli.py и src/product_search/infrastructure/replenishment_cli.py: новый RED для каждой ветки до её wiring, затем GREEN/REFACTOR; expected-version и все exit codes.

## Фаза 6. Сквозная проверка и операционные gates

Завершить все обязательные истории; первый MVP — fake вертикальная история1, не право начать рабочую публикацию.

- [x] 047 Сверить все52 FR с фактическими тестами/свидетельствами в docs/analysis/09-acceptance-criteria-and-traceability.md; не переносить planned cases в PASSED без запусков.
- [x] 048 Выполнить разрешённые fake/native/testDB проверки из specs/001-corpus-replenishment/quickstart.md, включая inherited lock/parent crash и migration rollback; ошибки возвращают к соответствующему TDD циклу.
- [x] 049 Подготовить новый конечный execution package и runtime binding в specs/001-corpus-replenishment/quickstart.md; owner отдельно разрешает ML/testinputs/БД/публикацию. Старые consumed claims не использовать.
- [x] 050 По отдельному разрешению выполнить ограниченную пробу и сохранить private evidence; сверить результат с ART-09, память/teardown и compatible vectors. Никакого automatic endurance/build100/cutover; отчёт-ссылка в specs/001-corpus-replenishment/quickstart.md.
- [x] 051 Провести итоговое code review и обновить specs/001-corpus-replenishment/plan.md/quickstart.md по факту; cutover/rollback и рабочая DB отдельно разрешаются, merge/push не включены.

## Зависимости и параллельная работа

Фаза1 → foundation → история1 → история2 → история3 → сквозные проверки.
Общие adapters/файлы не разрабатывать параллельно без разведения изменений.
Все циклы внутри истории следуют RED→GREEN→REFACTOR; указанный порядок консервативен.

Возможные параллельные проверки после foundation: RED files tests и RED native
lifecycle tests находятся в разных файлах и могут подготавливаться независимо;
GREEN каждой ветки зависит от её RED и соответствующего test gate. В истории2
RED fake-clock и RED resume могут готовиться независимо после истории1. В истории3
разбор сценариев ошибки фото и публикации допускается параллельно, но запись общего
controller/CLI выполняется последовательно. [P] не помечены: выбранный план
исполнения последовательный; эти возможности не являются командой спавнить агентов.

## Стратегия исполнения и адаптация Spec Kit

Первым получить fake вертикальный результат истории1, затем восстановление и ручной
повтор. Самостоятельная тестируемость историй не означает независимую deployment
или исключение общих prerequisites. Обязательные recovery/retry не вычёркиваются
из конечной приёмки ради первого demo.

По чекбоксам нельзя заключить, что пользователь разрешил эксплуатационный запуск.
Этот документ — план задач по согласованным правилам, не новый scope и не начало
реализации. Перед исполнением нужен запрос владельца; B0 и операционные допуски
остаются обязательными. Новых T-/US-/CHK-идентификаторов не создано.
