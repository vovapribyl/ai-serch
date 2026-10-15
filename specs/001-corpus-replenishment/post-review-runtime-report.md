# Runtime-пробы после исправлений051

Актуальный результат2026-10-14: **7d89d5da — OK, полный цикл на одном фото**.
Предыдущий отказ79f709ee и UNKNOWN первопричина сохранены ниже.

## Предыдущий запуск79f709ee — ERROR / INFRASTRUCTURE_ERROR

## Разрешение и запуск

Владелец явно разрешил [пакет](post-review-runtime-proposal.md)
`79f709ee1dec6317e8a14f14b041f74dc42ef338b2c35d2370b8840ea550be4a`.
Перед исполнением code/input/package SHA совпали; прежних model services/probe
containers не обнаружено, pressure=1. Один START, выбранные товар/фото, новая
собственная temporary DB/schema0010/seed1/1 и свежий consumed grant.

Применены прежние пределы1200с,330с на worker operation,5с DB,30с cleanup reserve,
RSS/MPS6GiB, один heavy worker; workingDB и Web не переключались.
Внешний запуск с подготовкой и очисткой занял **50,074с**, host exit0.
Код0 означает завершение host, не успешную публикацию.

## Подтверждённый результат

Все четыре модельные стадии завершены: I HTTP →10crops/масок → OpenCLIP →
DINOv2 → SigLIP2. Photo outcome **OK**, сохранены4attempts/4checkpoints.
После стадий, до успешной публикации команда вернула ERROR/INFRASTRUCTURE_ERROR.

| Состояние DB перед удалением | Результат |
|---|---:|
| Revisions / photos |1 /1 |
| Revision / photo |OPEN / OK |
| Stage attempts / checkpoints |4 /4 |
| Materialized regions / vectors |0 /0 |
| Catalog snapshots / publications |0 /0 |
| Replenishment runs |2служебные записи, один START |

В checkpoint artifacts сохранены10областей и30vectors. Эти данные не стали
готовым публикуемым товаром: нулевые revision_vectors относятся к SQL-каталогу,
а не к содержимому checkpoint files.

Отдельная проверка сохранённых vectors: по10каждой модели, размеры512/768/768,
все значения конечные, нормы в допуске1e-4 от1. Это не оценка качества поиска
и не доказательство публикации.

81resource observation, все **OK**. Максимумы в успешных samples:
RSS1525039104байт (около1,42GiB), MPS4049272832байт (около3,77GiB).
Нельзя складывать RSS/MPS при unified memory. Журнал не показывает превышений;
это не доказывает отсутствие иных инфраструктурных ошибок.

## Диагностика и остающаяся неопределённость

Точная первопричина **UNKNOWN**: CLI сворачивает необработанные исключения в
INFRASTRUCTURE_ERROR, traceback этой команды не сохранён; host-output пуст.
По сохранённому состоянию нельзя надёжно назвать ошибку SQL, файлов, grant
или teardown. Предположение не объявляется фактом.

Добавлен немодельный интеграционный сценарий
`test_native_host_composition_publishes_fake_stages` в
[PostgreSQL integration tests](../../tests/test_replenishment_postgres_integration.py).
Он выполняет actual native host composition, application, FreshGrant/consume,
repository authorization checks и publication в owned synthetic DB; SDK и
workers заменены подставными результатами. Через подставной serve_owner команда
вызывает application напрямую, поэтому raw исключение не скрывается CLI.

Первый setup получил NameError отсутствующего digest import; это не behavioral RED.
После исправления import сценарий **1passed за2,25с**. Публикация в синтетической
связке проходит; именно ошибка real runtime не воспроизведена. Производственный
код при этой диагностике не менялся, исправление неизвестной причины не заявлено.
Новая настоящая проба не выполнялась и старый grant не использовался повторно.

## Очистка и следующий шаг

Новая temporary DB удалена по подтверждённой собственной метке. Secret env/target
удалены; private фото/checkpoints/vectors/result/resource/grant evidence сохранены.
Текущая отдельная проверка:0native host/worker/guardian,0probe и0B1containers,
owner.sock и его ownership marker отсутствуют. Synthetic diagnostic DB очищена.

Прежняя успешная проба050 остаётся историческим свидетельством до исправлений051.
Зелёные194/300выборки и этот1diagnostic test не заменяют успешную post-review пробу.
Полный pipeline/рабочая активация/увеличение партии пока не подтверждены.

Следующий технический шаг — сохранить bounded private exception diagnostics
на границе owner command, без credentials/raw input в публичном ответе; проверить
это немодельно. После этого подготовить новый конкретный пакет для отдельного
диагностического runtime-допуска. Повторять тот же слепой запуск без новых
свидетельств не нужно. Требования, пределы и production gates не меняются.

## Последующая диагностика — 2026-10-14

[Private command diagnostics](runtime-failure-diagnostics.md) реализованы через
TDD,127selected tests PASS безDB/ML. Прошлая причина UNKNOWN. Новый пакет7d89d5da
подготовлен, не запускался; старый consumed допуск79f709ee к нему не относится.

## Следующая разрешённая диагностическая проба — OK,2026-10-14

Владелец явно разрешил пакет
7d89d5dae0c2793f65129df99e5c0db10b5431c8c6ff5c21112c7069ad240c78
из [описания диагностики](runtime-failure-diagnostics.md).
Один START, тот же выбранный товар/фото, свежий grant и новая собственная временная
DB/schema0010/seed1/1. Package/code/input SHA совпали; прежних model services/probe
containers нет, initial pressure=1. Прежние пределы сохранены.

Результат команды **OK**, host exit0, полный внешний запуск с подготовкой/очисткой
**82,661с** при1200с. Пройден actual исправленный путь:
I HTTP→10crops/масок→OpenCLIP→DINOv2→SigLIP2→4checkpoints→photoOK/revisionREADY→
publication только temporary DB.

| Сохранённое состояние до удаления DB | Результат |
|---|---:|
| Revisions / photos |1 /1 |
| Stage attempts / checkpoints |4 /4 |
| Revision / photo |READY / OK |
| Materialized regions / vectors |10 /30 |
| Catalog snapshots / revision publications |1 /1 |
| Replenishment runs |3служебные записи, один START |

Checkpoint vectors проверены отдельно:10/model, dimensions512/768/768,
finite numbers и L2-нормы в допуске1e-4 от1. Подтверждены формат/размеры pipeline,
не качество поиска либо parity с рабочим каталогом.

203resource observations:197OK/6WARNING/0STOP. Количество записей не равно
секундам ожидания: журнал включает несколько источников наблюдений.
Давление возвращалось кOK, пробы продолжались по действующим ограничениям.
Максимальные наблюдённые RSS1225326592байт (около1,14GiB) и MPS4042981376байт
(около3,77GiB); их нельзя складывать при unified memory. Это один вход, не
доказанная вместимость партии или причинный эффект оптимизации.

command-failure.json не создан: ошибка owner command в этой пробе не возникла.
Runtime fault logging здесь не сработало по причине отсутствия fault; способность
сохранить metadata проверена немодельными тестами ранее. Предыдущий отказ79f709ee
не воспроизведён, его причина остаётсяUNKNOWN. Успешный повтор не доказывает
исправление неизвестной причины или отсутствие intermittent fault.

Отдельная текущая проверка:0host/worker/guardian,0probe containers,
owner.sock и owner.socket.json отсутствуют. Owned temporary DB и secret env/target
удалены; private фото/checkpoints/vectors/results/resource/grant evidence сохранены.
Working DB/catalog/Web не менялись, consumed grant не переиспользуется.

Полный post-review pipeline текущего кода подтверждён **на одном фото**.
Большая партия, real crash/retry/resume, adverse grants/SQL timeout, quality oracle,
рабочая активация и production acceptance этой пробой не испытаны. Повторный
independent code review не проводился. Следующий предлагаемый шаг — подготовка
малой партии до5фото с новым input inventory/пакетом, не automatic execution.

## Последующая проба партии

Однофотный успех7d89d5da не переносится на партии автоматически.
Разрешённая партия cfe49786 из пяти фото остановилась по WAIT_TIMEOUT перед
фиксацией пятого checkpoint; публикаций нет. [Отдельный отчёт](batch-runtime-report.md).
