# Конечный пакет на23 незавершённых входа

2026-10-17. **CONSUMED — runner OK / postflight PASS**. Владелец
разрешил SHA всей серии; выполнены все5 START, обработаны23 входа.
17 готовы,6 deferred REGION_COUNT_LIMIT,0 PENDING/не начатых в этом пакете.
121 область/363 вектора. Архив сохранён, очистка подтверждена; повтор запрещён.
STANDARD: исполнение конечной серии, не приёмка качества или общего каталога.

## Один SHA на всю серию

`642b94726011ed50c43807586ace9d3088abcf08d7d592b9a7ed218e13f72b93`

| Граница | Подготовленное исполнение |
|---|---|
| Входы |3 PENDING из N05 consumed серии45, затем20 входов из N06–N09 без прежнего START.23 разных SHA, без повторов всех ранее обработанных входов и двухфотографической пробы |
| Порядок | N01: прежние N05 positions3–5; N02–N05: прежние N06–N09. Пять фаз3+5+5+5+5, накопленные префиксы3/8/13/18/23 |
| Идентичность | SHA/bytes/headers/decode/source product/photo mapping проверены.3 прежних PENDING не имеют regions/vectors; остальные20 не имеют grants/target/answer/resource logs.17 182 561 frozen bytes |
| Команды |5 новых START в одной собственной временной БД, по16 admissions в первой фазе и24 в каждой следующей, всего112. Это fresh START, не RESUME удалённой БД и не reuse старых grants |
| Approval | Один SHA покрывает всю серию; отдельных разрешений каждой партии не требуется. До утверждения SHA runtime не запускается |
| Время | Прежний общий предел3630с:3600с до внешнего cleanup reserve30с. Фаза1200с, включая внутренний reserve30с, и всегда в пределах общего дедлайна. Верхняя граница, не прогноз завершения всех23 |
| Модели / профиль | Прежние pinned I/GDINO/SAM и последовательные OpenCLIP/DINOv2/SigLIP2; модели, preprocessing, runtime profile, thresholds и формулы не менялись |
| Очистка / замеры | pre-SAM и post-photo cleanup true, load diagnostics true; sam.input пишет только формы RGB массивов и число боксов, не pixels/coordinates. Эффект снижения peak на всех23 UNKNOWN |
| Ресурсы | RSS I6GiB/encoder5GiB, MPS-driver6GiB. Прежние freshness/ResourceWait30с stable и300с window/deadline/latched STOP. Driver не заменяется на live; limits не повышаются |
| SQL | Один новый собственный временный контур; pinned image, tmpfs256MiB/контейнер512MiB, прежние CPU/PID limits. Рабочая БД не используется |
| Исходы | OK — полный путь3 моделей/checkpoints/временная публикация; NO_NAILS без embeddings; ERROR допустим только source-linked REGION_COUNT_LIMIT. Другой ERROR/PENDING/неполнота прекращают серию |
| Проверка фазы | Native OK/COMPLETED, host/monitor0, полный controller log и physical worker exit; счётчики по текущим3 или5, SQL/векторы/checkpoints по накопленному префиксу. Первый отказ останавливает следующие фазы |
| Диагностика | Новый verify_probe_files вызывается runner с фактическим числом фото и исходами из сохранённого экспорта. Для OK/deferred нужен SAM; ноль SAM допустим только при NO_NAILS. Порядок input→pre-cache→SAM→post-photo, известные metadata/counts и все обязательные границы |
| Footer | При отсутствии worker footer только matching controller expected SIGTERM/−15 с nonce/PID/head/complete batch/status/host closure; worker final status UNKNOWN. Существующий incomplete footer, rotation/truncation, missing events, unexpected/SIGKILL отказывают |
| Guards | Recovered WARNING допускается только при native completion, непустых OK/WARNING observations, финальном OK и boundary pressure1. Любой STOP сохраняется и не отменяется поздней очисткой |
| Экспорт | После каждой фазы накопленный prefix export до проверки исходов;40MiB reader, cumulative deferred list2MiB. Ошибка записи/receipt/верификации блокирует следующую фазу; partial export при доступном SQL сохраняется |
| Сохранность |941 прежний файл закреплён SHA, включая результаты/диагностику прежних серий и consumed pre-SAM пробы. Перед следующей фазой и после неё проверяются SQL checkpoints/members/vector values SHA, files и прошлый export SHA |
| Архив / cleanup | Mapping/lists/exports/diagnostics/logs/checkpoints fsync-архивируются до удаления своей БД. Credentials/targets/grants исключены. Postflight проверяет свои процессы/контейнер/locks и архивные SHA |
| Исключено | Любой retry после отказа/STOP, уже обработанные/deferred/NO_NAILS входы, новые фото, повышение caps, mask filtering, общий каталог, качество поиска, рабочий cutover, install/commit/push/merge |

23 входа не означают23 готовых: OK/NO_NAILS/deferred/PENDING и не начатые
учитываются раздельно. Прежние экспорты20/5/22/16 готовых и будущий prefix23
остаются отдельными; готовность общего корпуса/поиска этим пакетом не утверждается.
Исторические FAILED пакетов и новый offline replay не переименовываются.

## Подготовка и проверки

- 7 RED cases на прежнем двухфотографическом API; GREEN с числом входов3/5
  и явно переданными исходами. Добавлены all-NO_NAILS без SAM и mixed
  NO_NAILS/OK/deferred без сдвига SAM call IDs; отсутствие SAM у OK отказывает.
- Всего91 выбранный model-free тест PASS: новые variable batches, lifecycle
  (включая настоящий owned SIGTERM), диагностический verifier и SAM/load code.
  В исполнявшемся тестовом дочернем процессе — shape-only callbacks, не ML.
- Из AST **настоящего подготовленного runner** выполнены поиск локализатора
  по control.json и вызов file verifier для3/5, в том числе all-NO_NAILS.
  Поиск больше не зависит от наличия sam.predict, поэтому нулевой SAM не
  делает корректную NO_NAILS-фазу «не найденным локализатором».
- Пять настоящих SQLite-prefix exports в памяти PASS:3→8→13→18→23,
  receipts/deferred/source mapping/сохранность старого префикса проверены.
 13 ready/5 NO_NAILS/5 deferred — синтетическая fixture, не результат23.
- Настоящий journal predicate runner проверен8 сценариями3/5:
  all-ready/all-deferred/all-no_nails/mixed и8 отказами неверного счётчика.
  Глобальные ready не используются вместо current phase count.
- 88 code pins/frozen source,5 DTO/packages, runtime/claims/profile/model/input
  hashes проверены. Metadata helper закреплён на новом root; identity/assembly
  локализатора и3 encoder manifests/files PASS без SDK/server. Live NOT_RUN,
  после разрешения повторяется до создания БД.
- Runner без campaign approval отказал до runtime/credentials/grants/START.
 941 прежний файл и старые signed пакеты/runner/verifier сохранили SHA.
  Полный suite не повторялся: продуктовый код в подготовке не менялся.
  Самопроверка; независимое review не проводилось (STANDARD).

Ограничение диагностики partial export сохраняется: outer код может быть
UNCLASSIFIED_RUNNER_ERROR при ReplenishmentError/PENDING. Native answer,
первый resource-stop и сам partial export сохраняются; это не основание
продолжить фазу или повторить ML. Отсутствующий footer не фабрикуется.

Приватная ignored-папка `artifacts/corpus-replenishment/remaining23-preparation-20261017/`:
prepared/, frozen-source/, scripts/tests, JUnit tests.xml и verification.json.
prepared-summary.json указывает локальный root. Исходные изображения и ID
не публикуются; копия пакета не переносит разрешение на другое окружение.

## Фактический результат — 2026-10-17

Владелец «Разрешаю» на SHA выше. Live preflight PASS: pressure1,
нет конкурирующих ML/probe-процессов/контейнеров, входы/код/модели совпали.
Один runner,5 START, без retries и изменения подписанного кода/caps.
Все native-команды OK/COMPLETED, host/monitor0, все checks_passed=true.

| Фаза | Входов | Готовы | Deferred | Накопленный итог ready/deferred |
|---|---|---|---|---|
| N01 |3|2|1|2/1|
| N02 |5|5|0|7/1|
| N03 |5|3|2|10/3|
| N04 |5|3|2|13/5|
| N05 |5|4|1|17/6|

Итог:23 терминальных исхода —17 OK,6 ERROR только REGION_COUNT_LIMIT,
0 NO_NAILS/other errors/PENDING. Ни одного входа пакета не осталось не начатым.
6 deferred остаются без embeddings и не считаются готовыми фото.
121 область/363 вектора (по121 каждой модели),68 checkpoints/361 файл.
В собственной временной БД17 активных участников каталога/публикаций по
штатному пути; рабочая БД не использовалась. Последний экспорт3 146 875 bytes.

### Ресурсы и lifecycle

440,418с (~7мин20с). Guards849 OK,2 WARNING в N02,0 STOP.
После WARNING наблюдения вернулись к OK, native N02 завершилась успешно,
внешний критерий принял фазу. Фактическое ожидание ровно30с этим числом
наблюдений не доказывается; действующая native wait policy не менялась.
Peak RSS1 965 604 864 bytes, MPS-driver5 465 554 944 bytes; не складывать.
После pressure1. Снижение пиков относительно других входов/проб не является
причинным доказательством эффекта pre-SAM cleanup.

Новый file verifier прошёл во всех5 фазах. По фазам3/5/5/5/5 photo calls,
SAM calls3/6/5/6/5 (всего25, включая дополнительные проходы),
25 pre-SAM и23 post-photo cleanup pairs. Shapes/counts известны и порядок
проверен; NO_NAILS без SAM в этой реальной серии не встретился.
Все локализаторы штатно exited−15/SIGTERM, matching PID/nonce и controller
batch/status/host closure подтверждены. Worker footer отсутствовал во всех5,
worker_final_status UNKNOWN сохранён, completion source CONTROLLER_EXPECTED_SIGTERM.
Footer не подставлялся и не создавался. Это ограничение worker recorder,
а не отсутствие подтверждения обязательных событий и физического выхода.

### Данные и cleanup

Все5 immutable prefix exports3/8/13/18/23 повторно проверены: source mapping,
ordinal/input SHA, source-linked deferred receipts, полнота regions/models,
finite/unit-norm vectors и checkpoint manifests/payload SHA. Предыдущие
photos/outcomes/profile/regions/vectors сохраняются в следующем префиксе;
архивные SHA совпали. Подписанные runner/verifier и941 прежний файл неизменны.

Exports/lists/mapping/diagnostics/logs/checkpoints fsync-архивированы до удаления
своей БД. Read-only postflight PASS: своих процессов/контейнеров нет,
locks свободны, credentials/targets удалены. Последующий terminal-audit PASS
подтверждает все23 исхода и отсутствие PENDING. Runtime grants не повторялись.
Private postflight-summary.json/terminal-audit.json/runtime-result — в папке
подготовки выше, raw фото/ID не публикуются. Полный suite не повторялся:
исполнялся frozen код, проверены фактические data/lifecycle/cleanup.
Исторические FAILED прежних пакетов не заменены на PASS.

## Точка продолжения

Остаток23 закрыт по техническим исходам, включая6 deferred; это не означает,
что все23 или исходный целевой корпус готовы. Прежние exports20/5/22/16 и
новые17 готовых, а также отдельные ранние probe exports, пока раздельны.
Следующий шаг — инвентаризация этих экспортов и сборка единого оценочного
каталога с проверкой уникальности/source identity, списков deferred и ранних
пробелов сохранения. Не повторять ML для уже сохранённых результатов автоматически.
Новый SQL/runtime, переобработка deferred, качество поиска и рабочая активация
в текущий пакет не входят. Текущий SHA consumed, новых разрешённых START нет.
