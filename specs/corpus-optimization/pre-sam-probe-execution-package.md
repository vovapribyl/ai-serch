# Конечная проба очистки перед SAM на двух фото

2026-10-17. **CONSUMED — native OK/COMPLETED, runner FAILED**.
Владелец разрешил точный SHA; выполнен один START на двух фото.
Оба снова deferred REGION_COUNT_LIMIT,46 guard OK,0 WARNING/STOP.
Новые SAM input/cleanup события записаны. Внешняя проверка отказала из-за
отсутствующего worker diagnostic status-файла после ожидаемого SIGTERM.
Данные сохранены и проверены, postflight/cleanup PASS. Исторический FAILED
сохранён; повтор пакета запрещён. STANDARD: исполнение конечной пробы.

## Точный пакет

`c6d38648371091dda4e9aae70fb8f1e7f984f75d1de24f7ab9bef5a5debc62a2`

| Граница | Подготовленное исполнение |
|---|---|
| Цель | Проверить замеры числа боксов/форм и дополнительную очистку перед SAM на известных входах. Успех не доказывает устранение причины исторического STOP или способность обработать весь остаток |
| Входы | Только первые2 frozen фото N05 из consumed серии45, в том же порядке. Это намеренный повтор двух уже deferred REGION_COUNT_LIMIT, не продолжение23 и не reuse старого grant |
| Идентичность | SHA/bytes/headers/decode и source mapping совпали с историей; разные SHA двух фото,671146 frozen bytes. Исходные product/photo IDs сохранены privately; новые runtime IDs1/2 не подменяют исходные |
| Действие | Один новый START, максимум12 admissions; без автоматического retry и дополнительных фото |
| Время | Native-фаза1200с, включая30с внутреннего cleanup reserve; внешний предел1230с. Это верхняя граница, не прогноз |
| Модели / профиль | Те же pinned I/GDINO/SAM, runtime profile, детерминированные параметры и обработка фото; новых весов/зависимостей нет |
| Изменение | Закреплён новый код с sam.input metadata и empty_cache_before_sam=true; load_diagnostics=true и прежний empty_cache_after_photo=true. Старый STOP/история не переписываются |
| Ресурсы | RSS I6GiB/encoder5GiB, MPS driver6GiB; прежние freshness, ResourceWait30с stable/300с window, deadline и latched STOP. Показатель driver не заменён на live |
| SQL | Одна новая собственная временная БД: pinned image, tmpfs256MiB/контейнер512MiB, прежние CPU/PID limits. Рабочая БД исключена |
| Исходы | Ожидаются2 REGION_COUNT_LIMIT без embeddings. Если вернётся OK — штатные последовательные OpenCLIP/DINOv2/SigLIP2 и checkpoints в собственной БД; NO_NAILS без embeddings. Это разрешаемый объём будущей пробы, не наблюдённый исход |
| Отказ | RESOURCE_STOP, иной ERROR/PENDING, невосстановившийся WARNING, неполные данные/замеры, нарушение сохранности или deadline прекращают пробу. Recovered WARNING допустим лишь при native OK/COMPLETED, финальном OK и boundary pressure1 |
| Экспорт | До проверки итогов, reader40MiB; deferred list2MiB с исходными связями. Частичный export при отказе сохраняется, если SQL доступен; неполный исход не считается PASS |
| Диагностическая проверка | Два завершённых photo calls; на каждом минимум один SAM call, известные shapes/counts, pre-SAM cleanup before/after перед каждым predict, post-photo cleanup before/after. Status incomplete/rotation/truncation, пропуск/неверный порядок или UNKNOWN блокируют PASS |
| Сохранность |903 прежних файла закреплены SHA: checkpoints, exports/lists/mappings и traces, включая исторический MPS STOP. Старые результаты не изменяются |
| Архив / cleanup | Export/list/diagnostics/logs/checkpoints с fsync до удаления своей БД; credentials/targets/grants исключены. Read-only postflight проверяет собственные процессы/контейнер/locks/архивные SHA |
| Вне пакета | Остаток23, изменение caps/моделей/масок/формул, переоценка качества, сборка общего каталога, рабочая активация, установка, commit/push/merge |

## Что будет означать результат

Технический PASS: native OK/COMPLETED, допустимые сохранённые исходы обоих фото,
полные новые замеры и правильный порядок callbacks, целые прежние файлы,
архив и подтверждённая очистка. Снижение пика относительно исторических
6 487 310 336 bytes фиксируется отдельно как наблюдение одного запуска;
причинный эффект не доказывается без отдельного метода сравнения. Сравнительного
повторного прогона без новой опции в этом пакете нет.

При STOP фиксируются первая причина, peak driver/live по своим streams,
готовые/deferred/PENDING и не начатые входы. Поздний empty_cache не снимает
latched STOP. Общий outer error при partial export может остаться
UNCLASSIFIED_RUNNER_ERROR; native answer и первый resource-stop сохраняются
и имеют приоритет для диагноза. Это известное ограничение, не основание retry.

## Проверки подготовки

- 11 новых model-free проверок diagnostic verifier: RED на отсутствии проверок,
  GREEN с полной парой фото; отказ missing/UNKNOWN metadata, неправильных
  counts, потерянной/переставленной pre-SAM очистки, пропуска post-photo,
  незавершённого фото и incomplete/rotation/truncation.
- Всего56 выбранных тестов PASS: новый verifier, SAM diagnostics и load diagnostics.
  Прежние145 model-free PASS относятся к реализации кода; код продукта в этой
  подготовке не менялся. Полный suite/реальные SQL/ML не запускались.
- Настоящий journal predicate нового runner проверен на2 deferred, mixed,
  2 ready и NO_NAILS+deferred; неверный счётчик отказал во всех четырёх случаях.
  Эти fixtures не являются результатами реальных фото.
-88 code pins/frozen source, input/runtime/claims/model/profile hashes и DTO
  сверены; оба opt-in флага и prerequisite диагностики true. Metadata identity/
  assembly локализатора и3 encoder manifests/files PASS без SDK/server.
  Live readiness NOT_RUN; после разрешения повторяется до создания БД.
- Настоящий runner без campaign approval отказал до runtime/credentials/grants/
  START. SHA старого consumed пакета/runner и903 preserved files не изменились.
  Самопроверка; независимое review не проводилось (STANDARD).

Приватные scripts/tests, manifests, source snapshots, prepared/ и evidence:
`artifacts/corpus-replenishment/pre-sam-probe-preparation-20261017/` (ignored).
`prepared-summary.json` указывает локальный runtime root;
`verification.json` и JUnit `tests.xml` содержат агрегаты проверок.
Сырые фото/ID и содержимое model arguments не публикуются. Копия пакета
не переносит разрешение на другой runtime.

## Фактический результат — 2026-10-17

Владелец «Разрешаю» на SHA выше; live preflight PASS/pressure1.
Один runner/один START, прежние код/pins/caps в ходе исполнения не менялись.
Native-команда OK/COMPLETED, host/monitor exits0; оба фото ERROR только
REGION_COUNT_LIMIT с исходными source-linked receipts.0 OK/NO_NAILS/PENDING,
0 regions/vectors/checkpoints. Обработка этих ранее deferred фото не добавила
готовых входов и не сократила остаток23.

Operation log PASS:2 photo.before/2 photo.error,2 сохранённых outcomes,
один ожидаемый worker exit SIGTERM/returncode−15; host.closed записан.
Всего34,655с. Guards46 OK,0 WARNING/STOP. Peak RSS1 522 745 344 bytes,
peak MPS-driver5 415 075 840 bytes; RSS и MPS не складываются.

### Наблюдаемые замеры

| Фото в пробе | SAM RGB shape H×W×C | Боксов | Driver до pre-cache, bytes | После pre-cache / до SAM | После SAM |
|---|---|---|---|---|---|
|1|466×468×3|15|2 793 717 760|1 652 244 480|2 929 246 208|
|2|574×556×3|37|2 856 599 552|2 822 455 296|5 367 840 768|

Все2 sam.input known=true; обе pre-SAM и обе post-photo очистки имеют
before/after. В записанных событиях порядок input→pre-cache→SAM→post-cache→
photo.after подтверждён; measurement_ok=true. Внутренние тензорные размеры
SAM не измерялись. Пик по guard5 415 075 840 bytes ниже прежнего
6 487 310 336 на1 072 234 496 bytes (16,528%). Это наблюдение одного запуска
с новыми событиями/cleanup и иной текущей host state; причинное снижение
и прохождение всех23 не доказаны. Box counts исторического запуска не были
записаны, поэтому равенство фактических внутренних batches не подтверждается
одним совпадением входных SHA.

### Отказ внешней проверки

Runner FAILED / FileNotFoundError / UNCLASSIFIED_RUNNER_ERROR,
completed_phases пуст. Он дошёл до чтения `load-events.status.json`, которого
нет. Native-обработка, экспорт и resource checks к этому моменту выполнены;
финальная checks_passed не выставлена.

Worker был штатно остановлен SIGTERM после обработки. Controller-owned
operation log фиксирует ожидаемый exit−15 независимо от worker footer;
этот путь уже предусмотрен test_controller_records_exit_even_without_worker_footer
в [worker binding tests](../../tests/test_replenishment_worker_binding.py).
LoadDiagnostics.close пишет footer при завершении своего context manager;
пакет ошибочно сделал его наличие обязательным для такого lifecycle.
При подготовке эта связь не была проверена: fixtures verifier всегда имели
status-файл, а native composition test заменял server, не воспроизводя teardown.

Сохранённые boundaries/source identities проверены отдельным read-only аудитом.
Но diagnostic final status остаётся UNKNOWN: статус incomplete/rotation не
придуман и отсутствующий footer не подставлен как false/0. Старый verifier,
подписанный runner и FAILED не исправлялись задним числом; вся проба не
объявлена PASS. MPS STOP и ошибка этой проверки — разные события.

### Сохранность и cleanup

Экспорт1343 bytes, deferred list, mapping и diagnostics/logs архивированы
с fsync до удаления своей БД. Postflight PASS: собственных процессов/контейнеров
нет, locks свободны, credentials/targets удалены, pressure после1.
903 прежних файла сохранили SHA; архивные export/list/load-event SHA совпали.
Последующий runtime-audit проверил source mapping обоих deferred и порядок
записанных событий; новых START не было.

Private evidence: `postflight-summary.json`, `runtime-audit.json`,
`runtime-result/` в папке подготовки выше. Не публикуются исходные фото,
ID/координаты/пиксели; содержимое SAM inputs не сериализовалось.
Полный suite не повторялся: исполнялся frozen код, проверены фактические данные,
причина отказа и cleanup. Commit/push/рабочей активации не было.

## Точка продолжения

Исправить model-free проверку завершения диагностики с учётом ожидаемого
SIGTERM и controller-owned evidence; добавить тест на настоящий lifecycle
без worker footer. Не заменять UNKNOWN выдуманным статусом и не снимать
отказы на неполные/потерянные events. Повторный ML для исправления этой
проверки не требуется. После проверки — отдельный новый пакет для дальнейшей
работы;23 пока не запускались, текущий SHA израсходован.

Уточнение 2026-10-17: [новый lifecycle verifier](diagnostic-lifecycle-fix-report.md)
прошёл94 model-free теста и read-only replay этой пробы. Controller подтверждает
выход worker и обязательные события при отсутствующем footer; worker final status
остаётся UNKNOWN. Этот consumed SHA/runner/исторический FAILED не изменены.
