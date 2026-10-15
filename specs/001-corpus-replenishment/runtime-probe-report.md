# Runtime-пробы пополнения корпуса

Актуальный результат2026-10-14: **пятая проба OK, полный цикл на одном фото**.
Пункт050 выполнен; итоговое review051 открыто. Ниже сохранена история попыток.

## Первая проба: STOPPED / RESOURCE_STOP до моделей

Владелец разрешил один START для одного выбранного товара и одного фото,
настоящие модели последовательно и публикацию только в новую временную БД.
Утверждённый пакет:
`0cd821885cacef3add648cdfc9738642fbea3fdf2c6906d7f8b29943e3116d80`.
Пределы:1200с всего,330с на операцию,5с на DB,30с на очистку;
RSS собственного контура6GiB, MPS6GiB, один тяжёлый worker одновременно.

## Что произошло

Перед запуском совпали SHA пакета, кода и frozen input. Прежних модельных сервисов
не обнаружено; macOS pressure=1. Создана новая собственная БД: pinned image,
512MiB,1CPU,128PID, tmpfs256MiB, loopback endpoint. Миграция0010 и seed1/1
выполнены только в ней. Свежий grant выдан и однократно consumed.

Host принял команду START и вернул `STOPPED / RESOURCE_STOP`. Весь внешний запуск
вместе с подготовкой и очисткой занял1,720с; host завершился с кодом0.
Код0 означает завершение host, а не успешную обработку фото.

| Свидетельство перед удалением БД | Результат |
|---|---:|
| Product revisions / photos |1 /1 |
| Состояние revision / photo |OPEN / PENDING |
| Stage attempts / checkpoints |0 /0 |
| Regions / vectors |0 /0 |
| Catalog snapshots / publications |0 /0 |
| Replenishment runs |2 записи; это не два START или повторный ML-запуск |

Сохранены три ресурсных наблюдения: все OK, pressure=1, RSS контроллера
41566208–44531712байт, MPS=0 при отсутствии тяжёлого процесса. Это не измерение
потребления моделей. Модельные стадии не запущены, vectors не получены.

## Причина и исправление

После создания NativeStageDriver его `control` ещё равен None. Callback контекста
ресурсного журнала обращался к `control["stage_key"]` до первой стадии.
Ошибка формирования журнала переводила RecordingResourceObserver в STOP.
Это дефект связки наблюдения, а не свидетельство нехватки памяти.

Добавлена проверка actual host wiring
`test_host_records_resources_after_driver_creation_before_first_stage`:
при исправных ресурсных наблюдениях idle driver должен записывать OK до создания
control. До изменения кода тест получил STOP вместо OK; после минимальной проверки
`control is not None` прошёл. Сам механизм STOP при ошибке записи сохранён.

Итоговая выбранная немодельная регрессия: **91passed** за0,72с
(host, resource binding, workers, controller, waiting, lifecycle). Ruff и
`git diff --check` прошли. Первая команда теста без PYTHONPATH дала import error;
это не поведенческий RED. Отдельная ошибочно расширенная команда включила DB/socket
сценарии в sandbox:3FAILED и12ERROR, включая Docker setup и bind.
Она не является зелёным интеграционным прогоном; повторный DB-прогон не выполнялся.

## Очистка и ограничения

Временный контейнер удалён по подтверждённой собственной метке; секретный env и
его target descriptor удалены. Отдельная текущая проверка:0 probe containers,
0 native host/worker процессов, owner.sock отсутствует. Исходное фото, рабочий
каталог и Web не переключались. Private grant/claim и журналы сохранены как evidence;
повторно использовать их нельзя. Model inference, MPS availability, физический
teardown тяжёлого процесса и compatible vectors остаются UNKNOWN.

После исправления заморожен новый отдельный пакет с теми же фото, объёмом и пределами:
`65815b4dea8f72cce467769800b81e6ad103626a6e2c8a15c9eb5dadf55d54ff`.
Code/input SHA checks и metadata-only I readiness/assembly прошли без SDK import.
Для него grant/DB не созданы. Он **PENDING_OWNER_APPROVAL**: новый настоящий запуск
требует отдельного допуска владельца; предыдущий однократный допуск уже consumed.
Это граница утверждённого execution package, а не новая нормативная процедура.
Независимое review051 не проводилось; runtime acceptance не подтверждён.

## Повторная разрешённая проба — 2026-10-14

Владелец явно разрешил повтор для пакета
`65815b4dea8f72cce467769800b81e6ad103626a6e2c8a15c9eb5dadf55d54ff`.
Перед запуском проверены code/input/package SHA, отсутствие прежних модельных
сервисов и pressure=1. Создана другая собственная временная БД; schema0010,
seed1/1 и новый grant относятся только к этой пробе.

START вернул **STOPPED / RECOVERY_REQUIRED**, host exit0, весь внешний запуск
занял2,266с. Процесс localization был запущен, но готовность не получена:
есть control.json и stage.claim, нет telemetry.json и ready.json.
Stage attempts/checkpoints/regions/vectors/catalog snapshots/publications —0;
фото PENDING, revision OPEN. Полный модельный путь не проверен.

Пять первых ресурсных наблюдений OK, pressure=1, RSS контроллера
42123264–50151424байт. Следующее наблюдение с PID localization стало STOP;
сохранённый last_sample — предшествующее измерение, а не замер памяти worker
в момент STOP. MPS=0 в ранних наблюдениях не подтверждает MPS availability.

### Диагностика порядка старта

Control создан в момент1791973034,1097734; stage.claim —1791973034,607762.
Первый poll выполняется через0,5с. После stage.claim выполнялись проверка runtime
inventory и только затем запись первой телеметрии. Отдельная read-only проверка
inventory заняла0,049с и совпала с frozen составом окружения; SDK не импортировались.
В момент poll обязательной телеметрии ещё не было, что закрывает допуск по правилам
MacResourceObserver. Гонка старта — наиболее вероятное объяснение этой остановки;
полный traceback worker не сохранён, поэтому иные ошибки до его готовности
этим запуском не исключены.

Поведенческий тест `test_native_entry_reports_pre_sdk_memory_before_runtime_inventory`
воспроизвёл дефект порядка: metadata callback получил отсутствующий telemetry.json.
Исправление: после проверки control/claim/owner процесс записывает одно наблюдение
нулевого MPS до импорта bootstrap и проверки inventory. На этом участке SDK ещё
не загружен; ноль не заменяет неизвестное потребление после импорта.
Несовпадающий inventory по-прежнему отказывает до SDK, bootstrap sample стареет
через прежние5с, ресурсные потолки/STOP и poll0,5с не изменены.

Итоговая немодельная регрессия — **92passed** за0,82с; ruff/diff PASS.
Это проверяет исправление порядка, но не доказывает готовность реального worker.
Текущая отдельная проверка очистки:0host/worker,0probe containers, socket отсутствует.
Временная БД и secret env/target удалены, private evidence сохранено.

### Следующий подготовленный пакет

Те же фото, один товар и численные пределы; новый root/nonce/target и код:
`1254eaea4c31a1603b623235686d28e6a73d5cd853e66f489c1c3b26e1a3d840`.
Code/input SHA и metadata-only I readiness/assembly PASS без SDK import.
Grant и DB для него не созданы; статус PENDING_OWNER_APPROVAL.
Повторный настоящий START не выполнялся. Пункт050 и review051 остаются открытыми.

## Третья разрешённая проба — 2026-10-14

Владелец явно разрешил пакет
`1254eaea4c31a1603b623235686d28e6a73d5cd853e66f489c1c3b26e1a3d840`.
Code/input/package SHA проверены; прежних model services/probe containers нет,
pressure=1. Один START, новая owned DB/schema0010/seed1/1 и свежий consumed grant.

Результат: **STOPPED / RECOVERY_REQUIRED**, host exit0, внешний запуск9,477с.
Localization process создан, control/stage.claim/telemetry есть; ready.json нет.
Stage attempts/checkpoints/regions/vectors/snapshots/publications —0; photo PENDING,
revision OPEN. Рабочий каталог и Web не переключались.

Ресурсный журнал содержит9OK, затем STOP. Максимальный RSS в успешных наблюдениях
собственного контура —317456384байт (около303MiB); pressure=1. Отдельная последняя
worker telemetry сообщает MPS475136байт и правильные PID/nonce. Это свидетельство
прохождения проверки MPS availability и работы telemetry после импорта Torch,
но не inference модели. Sample в записи STOP сохранён от прежнего успешного
наблюдения; actual memory в момент STOP UNKNOWN. Первая телеметрия теперь создана,
поэтому прежнее объяснение «не успел создать telemetry» к этой пробе не относится.

### Подтверждённый дефект actual localization assembly

В frozen binding часть i_files — строки, часть — objects с полем path.
`_serve_localization` выполнял Path(value) для всех values и получал TypeError
на object. Подготовительный metadata checker нормализовал paths отдельно,
поэтому его PASS не проверял actual worker conversion. Такой разрыв проверки
зафиксирован как дефект подготовки, а не ошибка модели.

Проверка frozen inputs без SDK воспроизвела TypeError. Затем тест
`test_localization_assembly_accepts_manifest_path_records_without_sdk` вызвал
actual `_serve_localization`: RED TypeError на смешанном представлении путей;
после чтения value["path"] для objects — GREEN, assembly получает правильные
Paths. В существующем I interpreter metadata-only assembly с фактическими путями
worker прошёл; Torch не импортирован. Полный traceback завершившегося worker
не сохранён (stderr DEVNULL), поэтому причинную цепочку его выхода нельзя
восстановить полностью; наличие этого детерминированного блокера подтверждено.

Итоговая регрессия: **93passed** за0,83с, выбранные host/resources/workers/controller/
waiting/lifecycle; ruff и diff PASS. Полный ML pipeline не проверен.

Очистка подтверждена отдельно:0host/workers,0probe containers, socket отсутствует;
temporary credentials/target удалены. Private grant/claims/evidence сохранены
как использованные; не переиспользуются. Нового реального запуска не было.

### Актуальное подготовленное предложение

Новый код, private root/nonce/target; фото, объём и численные пределы прежние:
`d0e4b79d50ea07c84adcba8b10f23f946ff0d56321e2cc484fd92e731524e58c`.
Code/input SHA и I metadata readiness/assembly PASS без SDK import.
Новый grant/DB не созданы. Статус PENDING_OWNER_APPROVAL;050/051 остаются открытыми.

## Четвёртая разрешённая проба — 2026-10-14

Владелец явно разрешил пакетd0e4b79d. Package/code/input SHA совпали,
старых model services/probe containers не обнаружено, initial pressure=1.
Один START на выбранном фото, новая owned DB/schema0010/seed1/1, свежий grant.

Впервые пройден настоящий путь I HTTP → обработка результата →10crops/масок →
сохранённый localization checkpoint. Manifest содержит region_count=10.
Это не owner-оценка качества локализации и не результат моделей эмбеддингов.

Итог: **STOPPED / RESOURCE_STOP**,187,022с с подготовкой и очисткой, host exit0.
DB:1stage attempt,1checkpoint,0revision regions/vectors/snapshots/publications;
photo PENDING, revision OPEN. Количество revision_regions=0 относится к целевому
каталогу и не отменяет10областей в localization manifest. Encoder stages не начаты.

Ресурсный журнал:654записи,150OK/502WARNING/2STOP. Эти количества включают
наблюдения из двух потоков и не являются секундами ожидания.
Максимум RSS собственного контура в успешных samples1439137792байт (около1,34GiB),
MPS4052598784байт (около3,77GiB). RSS/MPS не складываются механически.
Pressure был WARNING=2, затем вернулся к1; успешно пройдено ожидание стабильности,
checkpoint сохранён. Последние STOP samples содержат прежний last_sample, а не
подтверждённую память в момент ошибки. Ресурсные потолки не менялись.

### Гонка при штатном завершении стадии

После сохранения checkpoint код close_stage сначала останавливал owned worker,
а затем отключал monitor. Во время TERM/KILL monitor продолжал требовать live
worker/telemetry; штатное исчезновение процесса могло установить RESOURCE_STOP.
Это подтверждённый дефект порядка teardown; полный traceback исходного процесса
не сохранён, поэтому точная цепочка всех STOP в этой пробе ограничена журналом.

Тест `test_intentional_stage_teardown_stops_monitor_before_worker_disappears`
воспроизвёл RESOURCE_STOP при намеренном завершении и исчезновении обязательного
sample. После перестановки monitor stop/join перед registry stop — GREEN.
Bounded TERM/KILL, подтверждение физического завершения и guardian сохранены;
если monitor не завершился либо registry не подтвердил остановку, recovery
по-прежнему требуется. Ранее зафиксированный реальный STOP не сбрасывается.

Итог94selected model-free/native passed за0,87с; ruff/diff PASS.
Это не успешный реальный переход I→OpenCLIP: его ещё предстоит проверить.
Текущая отдельная проверка cleanup:0host/worker/guardian,0probe containers,
socket отсутствует; secret env/target удалены. Checkpoint/claims/private logs
сохранены как evidence; временная БД удалена, RESUME к ней невозможен.

Новый отдельный пакет, тот же вход/объём/пределы:
`bbb3d386e828edb26fdd9901ed18a2ea05d9724003fdf86c40b18def861aabff`.
Metadata-only I readiness/assembly PASS без SDK import; новый grant/DB не созданы,
PENDING_OWNER_APPROVAL.050 остаётся открытым: compatible vectors/publication и
реальное переключение тяжёлых стадий не подтверждены.051review не проводилось.

## Пятая разрешённая проба — полный цикл, 2026-10-14

Владелец явно разрешил пакет
`bbb3d386e828edb26fdd9901ed18a2ea05d9724003fdf86c40b18def861aabff`.
Перед запуском package/code/input SHA совпали, прежних model services/probe
containers нет, pressure=1. Один START, один выбранный товар/фото, новая собственная
DB/schema0010/seed1/1, свежий grant. Рабочий каталог и Web не переключались.

Результат команды **OK**, host exit0. Внешний запуск вместе с подготовкой и очисткой
занял **49,690с** при лимите1200с. Впервые пройдён полный реальный путь:
I HTTP →10crops/масок → OpenCLIP → DINOv2 → SigLIP2 →4checkpoints →
photo OK/revision READY → publication в новую временную БД.

| Сохранённое состояние БД перед удалением | Результат |
|---|---:|
| Product revisions / photos |1 /1 |
| Revision / photo |READY / OK |
| Stage attempts / checkpoints |4 /4 |
| Revision regions / vectors |10 /30 |
| Catalog snapshots / revision publications |1 /1 |
| Replenishment runs |3служебные записи; один START, не три модельных запуска |

Проверены сохранённые vector artifacts после завершения: по10vectors каждой
модели, OpenCLIP512, DINOv2768, SigLIP2768. Все значения конечные числовые;
L2-нормы0,9999999999999999–1,0 (допуск проверки1e-4). Совместимость подтверждена
для размеров и формата frozen pipeline/его publication; качество поиска,
паритет выдачи с рабочим каталогом и owner-оценка найденных областей не проверялись.
JSON не хранит dtype отдельным полем, поэтому эти проверки не являются замером
runtime dtype каждого tensor.

### Ресурсы и завершение

84записи ресурсного журнала, все **OK**, без WARNING/STOP. Максимальный наблюдённый
RSS собственного контура1527382016байт (около1,42GiB), MPS4055564288байт
(около3,78GiB). Значения не складываются: используется unified memory.
Журнал содержит localization и все три encoder stages. Результат относится
к одному фото в этом запуске; он не доказывает вместимость большой партии.

Переходы между четырьмя стадиями прошли с требуемыми проверками owned teardown.
Отдельная текущая проверка:0host/worker/guardian,0probe containers, owner.sock
отсутствует. Temporary DB удалена по проверенной собственной метке, secret env
и target descriptor удалены. Private input/checkpoints/vector/resource/result/
cleanup evidence и consumed grant сохранены; grant повторно не используется.
Рабочие БД/cache/исходное фото не менялись, новый runtime не активирован в Web.

### Сопоставление с приёмкой и статус плана

Проверено runtime-свидетельство для одного фото: локализация/crops и последовательные
три модели, durable checkpoints, READY после завершения всех выбранных фото,
publication целого готового товара, конечное окно и освобождение собственного
модельного контура. Это дополняет немодельные свидетельства ART-09 и отчёта047–048;
не превращает остальные сценарии в PASSED. Retry/resume, несколько партий,
несколько товаров, предел300с ожидания, сбои commit/rollback/parent crash и
рабочий search cutover настоящими моделями в этой пробе не выполнялись.

Пункт050 выполнен как ограниченная проба и фиксация evidence. Независимое review051
остаётся открытым. Owner acceptance всего решения, рабочий cutover, увеличение
корпуса, merge/push отдельно не подтверждены и этой пробой не разрешаются.
Предыдущие четыре неуспешные попытки сохраняются выше; успешный запуск их не отменяет.
