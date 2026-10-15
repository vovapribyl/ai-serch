# Итоговое code review пополнения корпуса

2026-10-14. Результат: **REWORK —0Critical /5Important /0Minor**.
Актуальное дополнение: все пять замечаний исправлены и проверены автором через TDD;
пункт051 выполнен. Первоначальный verdict и его основания сохранены ниже.
Повторного независимого PASS нет; рабочая активация не выполнялась.
Успешная ограниченная [проба050](runtime-probe-report.md) сохраняет свой результат.

## Объём и способ проверки

Один независимый ревьюер, read-only, по навыку requesting-code-review.
Ветка codex/upload-optimiz, HEAD `b38f07ee4e465efdce02eae6d3a89ba9c7658cf0`.
Проверено текущее незакоммиченное содержимое, включая untracked файлы;
диапазон HEAD..HEAD не представляет эту реализацию. Review package содержит
SHA37основных файлов; исходная реализация во время review не изменялась.

Прочитаны spec/plan/tasks/data-model, пять contracts и retained evidence/ledger;
production core/DTO/ports, replenishment adapters, migration, scripts, Web diff
и необходимые baseline search/native dependencies. Проверены существенные тесты
checkpoint, lifecycle, grants, CLI, resume/retry, publication и snapshot binding.
PostgreSQL fixtures/harness не читались целиком построчно.

Ревьюер тесты/процессы/БД/модели не запускал и файлов не менял. Исполнитель отдельно
проверил94выбранных немодельных/native tests: PASS0,90с, ruff/diff PASS.
Это не полный suite. Read-only Unicode diagnostic подтвердил расхождение hashes.

## Важные замечания

Статус на момент исходного review: все пять **OPEN**, исправления ещё не выполнялись.
Актуальный результат исправлений приведён в дополнении ниже.
Новые требования или разрешения на runtime из них не выводятся.

| Проблема | Триггер и последствие | Место в коде / необходимая проверка |
|---|---|---|
| Разрешение не расходуется при повторе публикации | RETRY_PUBLICATION пропускает worker factory, где расположен consume. Snapshot может активироваться, затем возврат SEARCH отклоняется; grant остаётся нерасходованным | [application](../../src/product_search/infrastructure/replenishment_application.py), [host](../../src/product_search/infrastructure/replenishment_host.py). Потребление должно относиться ко всем мутациям; нужна проверка native retry без ML с реальным FreshGrant |
| Grant не перепроверяется перед публикацией | После последнего teardown grant истёк/отозван, но monotonic окно ещё открыто. READY/active pointer могут записаться до позднего отказа SEARCH | [application](../../src/product_search/infrastructure/replenishment_application.py), [repository](../../src/product_search/infrastructure/replenishment_repository.py), [grant](../../src/product_search/infrastructure/replenishment_runtime_binding.py). Проверить expiry/revocation до мутации/commit; cleanup должен работать без grant |
| Stale Unix socket блокирует восстановление | После аварийного выхода остаётся owner.sock; mode lease освобождён, новый bind получает EADDRINUSE. Штатный resume не достигает supervisor | [CLI](../../src/product_search/infrastructure/replenishment_cli.py). Нужна безопасная сверка собственного stale endpoint под lease; живой endpoint, чужую замену и обычный файл удалять нельзя |
| SQL timeout использует старый остаток окна | При остатке2с первый lock wait занимает1,8с; второй запрос всё ещё может ждать исходные2с. Проверка после transaction приходит уже после расходования резерва | [repository](../../src/product_search/infrastructure/replenishment_repository.py). Пересчитывать timeout перед SQL ожиданием либо ограничивать transaction эквивалентно; тестировать последовательные задержки |
| Unicode даёт несовместимые SHA | Native canonical использует ensure_ascii=True, repository digest —False. Разрешённый source_ref с кириллицей либо Unicode в профиле нельзя согласовать одним SHA | [runtime binding](../../src/product_search/infrastructure/replenishment_runtime_binding.py), [repository](../../src/product_search/infrastructure/replenishment_repository.py). Нужна единая canonical encoding и Unicode regression |

Точные локаторы проверенной версии: application156/188–198, host264,
runtime_binding140/20–21, repository38/87–93/128–135, CLI482.
После исправления номера могут измениться; описание триггера остаётся основным локатором.

Read-only диагностический пример: для ASCII source_ref обе реализации SHA совпали,
для `фото.png` — нет. Это воспроизведение дефекта идентичности без модельного запуска.
Остальные выводы — статически подтверждённые пути исполнения; fault runtime
для этих пяти замечаний не запускался.

## Что сохранено и что не оценивалось

Положительные свойства реализации: core отделён от SQL/OS/ML; партия до пяти фото;
immutable checkpoints связаны с fenced DB receipts; publication проверяет current
head и атомарно сохраняет snapshot/pointer/receipt; потерянный ответ отделён от
подтверждённого результата; чужие process groups не присваиваются.

Ревьюер оставил вне оценки, исполнитель сохраняет эти границы:

- Working DB migration, Web/search cutover и эксплуатационное recovery требуют
  отдельных допусков; здесь проверялась их реализация статически, без развёртывания.
- Качество localization/ranking и бизнес-приёмка не входят в code review;
  один технический happy path не заменяет quality oracle.
- Real ML crash/retry/resume, несколько товаров и вместимость пяти фото
  не подтверждены успешной пробой одного фото.
- GC/retention, VM, новые категории, импорт и изменение CHECK-прав остаются вне scope.
- Наследованные baseline defects без установленного нового влияния не относятся
  автоматически к замечаниям051; обнаруженное влияние требует отдельной проверки.

## Следующая работа

Исправить пять подтверждённых дефектов в пределах существующих контрактов:
сначала воспроизвести каждый тестом RED, затем минимальный GREEN и релевантная
регрессия. После исправления обновить этот отчёт результатами, не удаляя исходные
замечания. Только затем оценивать готовность051. Свежий код не наследует ранее
consumed ML grant; новые runtime/cutover/merge/push этим review не разрешены.

## Исправления по разрешению владельца — 2026-10-14

Владелец разрешил устранить все пять замечаний. **Все пять исправлены и проверены
исполнителем через TDD.** Первоначальный независимый verdict REWORK сохранён выше;
повторный независимый review не проводился. Это не независимый PASS нового diff.
Пункт051 выполнен как review, исправления и фиксация результата.

| Замечание | Исправление | Поведенческий RED → GREEN |
|---|---|---|
| Разрешение при retry-publication | Callback claim_build вызывается сразу после получения BUILD owner, перед register_profile/bind/publication; host consume больше не находится в ML factory | `test_native_publication_without_workers_consumes_grant_and_returns_search`, `test_application_claims_owner_before_first_mutation_without_worker_factory`: grant оставался нерасходованным/SEARCH false → consumed до мутации, SEARCH разрешён без ML |
| Истечение/отзыв перед commit | Native host передаёт в repository check_authorization. Grant/claim проверяются перед SQL и непосредственно перед commit; cleanup transactions не требуют действующего grant | `test_lost_authorization_before_commit_rolls_back_and_cleanup_stays_available` (expiry/grant/claim): commit допускался → отказ и возможность cleanup. Дополнительный synthetic DB тест `test_revoked_grant_before_checkpoint_commit_rolls_back`: checkpoint не сохранён, attempt RUNNING, служебное завершение доступно |
| Stale socket | Private owner.socket.json хранит PID, inode сокета и inode lease. После получения lease recovery сверяет proof и отсутствие живого PID. Без proof, при живом PID/чужом inode/file/symlink/другом lease — отказ | `test_crash_socket`: аварийный os._exit оставлял блокирующий сокет → следующий владелец восстановил IPC.5boundary cases `test_socket_foreign` плюс прежние защиты проходят |
| SQL deadline | Перед каждым execute и COMMIT timeout устанавливается из текущего остатка; потоковый cursor делает то же перед query/FETCH | `test_sql_budget_is_refreshed_between_sequential_waits`: второй lock получал2000ms вместо остатка≤200ms → актуальный timeout. Дополнительный `test_stream_cursor_refreshes_budget_before_each_fetch` RED→GREEN |
| Unicode SHA | Repository.digest использует общую canonical encoding UTF-8/ensure_ascii=False из runtime binding | `test_unicode_identities_use_same_canonical_encoding` (source_ref/profile): разные SHA → совпадающие SHA |

Callbacks не передают SQL/OS объекты в core; actual grant остаётся деталью native
composition. Применён book-guidance/Clean Architecture mini, upstream
`893a88a6fce3a80c565bf39ac65021b43a8b2990`: направление зависимостей и простая
граница проверки. Новые слои/зависимости и требования не вводились.

### Проверка и ошибки в процессе

Первый поведенческий набор дал6RED (Unicode2, SQL budget1, revoked/expired grant3).
Для native retry/claim получены ещё2поведенческих RED. В первом варианте fake
repository возвращал неизменный epoch и получил INVALID_OWNERSHIP; setup исправлен,
после чего наблюдён требуемый RED отсутствующего claim. Setup error не засчитан RED.

Два первых запуска crash socket теста получили отказ bind из-за слишком длинного
пути Unix socket в macOS; это не behavioral RED. На коротком private basetemp
воспроизведён именно отказ successor после crash, затем GREEN.

Первый общий прогон: **188passed/5failed** за199,10с. Изменённая SQL обёртка не
поддерживала cursor, что сломало5catalog reader scenarios. Причина исправлена:
добавлен bounded stream path и test query/FETCH budgets. Его первоначальный
AttributeError и пять реальных reader failures сохранены как регрессионное RED,
не переобъявлены успешными.

Финальный общий выбранный прогон: **194passed** за199,67с. Включены review fixes,
acceptance, retry/resume/recovery, flow, CLI/native lifecycle, files, snapshot readers,
publication и owned synthetic PostgreSQL integration; один прежний Starlette/httpx
warning. Дополнительная отдельная немодельная/native выборка: **300passed** за1,03с
(core rules/contracts/controller/waiting, boundaries/harness, resources/host/workers,
artifacts/stage payloads/dependency boundaries). Выборки пересекаются; их количества
не складываются в число различных тестов. Полный repository suite не запускался.
Ruff/diff PASS. Текущая проверка:0B1containers,0model host/worker процессов.

Все DB-прогоны использовали собственные synthetic fixtures, один контейнер
одновременно,512MiB/1CPU/128PID/tmpfs256MiB, loopback, bounded wrapper570с
с резервом очистки. WorkingDB/Web/cutover, модели, установка, commit/push/merge
не выполнялись.

### Практические границы после исправлений

Успешная проба050 относится к прежнему коду и consumed пакетуbbb3d386.
Исправленный код не прогонялся с настоящими моделями; старые fingerprints/claims
не разрешают новый runtime. Качество поиска, большие партии и production acceptance
остаются неподтверждёнными. Сокет старого выпуска без ownership proof либо socket
с живым/повторно использованным PID не удаляется автоматически: отказ сохраняет
защиту чужого endpoint. Генерация новых proposal/grant и рабочая активация в эту
задачу не входят.
