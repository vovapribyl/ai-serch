# Предложение первой пробы с настоящими моделями

2026-10-14. Пункт049: **PREPARED / PENDING_OWNER_APPROVAL_050**.
Подготовлены вход, отпечатки и численные пределы предложения. Связка подготовлена и прошла немодельные проверки;
новый execution package приведён ниже, пункт049 закрыт как подготовка. Это STANDARD-подготовка, без нового разрешения
на ML, БД, публикацию или эксплуатацию.

## Предлагаемый объём

Владелец выбрал одно уже выбранное фото из корпуса. Для предложения зафиксировано
одно фото: PNG,612×617,RGBA,469661байт. Текущий SHA совпал с прежним приватным
inventory; файл не менялся во время чтения. Декодирование, изменение исходника
и inference не выполнялись; проверены заголовок и bytes SHA. Подготовлена одна
byte-identical копия в отдельном private каталоге0700, файл0600; original644
не изменён. В inventory используется относительный source_ref. Oversize-preparation
для этого размера не требуется. Исходный файл остаётся read-only.

После отдельного разрешения: один новый запуск START, один товар/одно фото,
I → проверенные crops → OpenCLIP → DINOv2 → SigLIP2 → checkpoint → READY →
публикация только в новой изолированной БД. Никакого пополнения рабочего каталога,
нового Web cutover, следующей партии, automatic retry или проверки качества поиска.
Идентификаторы1/1 в пакете зарезервированы для будущей пустой БД; это не существующие
записи рабочей БД. Seed этой БД ещё не выполнен.

Если I вернёт NO_NAILS, фото завершается без encoders и публикации. Такой исход
не доказывает прохождение полного encoder-пути и не разрешает самовольно выбрать
другое фото. Неизвестный COMMIT требует сверки receipt, а не повторения ML.

## Подтверждённые факты

| Область | Что проверено сейчас | Что это не подтверждает |
|---|---|---|
| Host | macOS/arm64, физическая RAM16GiB | Свободную память и допустимую нагрузку на момент будущего запуска |
| Controller | Python3.12.14,44distribution metadata; Torch/Transformers/OpenCLIP отсутствуют | Работоспособность ML в этой .venv |
| I environment | Существующий interpreter,Python3.12.14/arm64;90distributions; Torch2.13.0,vision0.28.0,Transformers4.44.2,NumPy2.2.5 | Загрузку моделей, MPS availability и реальный inference |
| Encoder environment | Существующий отдельный interpreter,72distributions; Torch2.13.0,vision0.28.0,Transformers5.16.1,OpenCLIP3.3.0,NumPy2.5.3 | Совместимость обновлённого staged runtime после загрузки SDK |
| Encoder snapshots | Текущие байты87файлов трёх snapshots сверены с manifest;512/768/768 и прежние pinned revisions | Результат вычисления и качество vectors |
| I inputs/config/code |36позиций свежего manifest проверены; actual package inventory/VCS/runtime metadata совпали | ML-ready состояние сервера и нагрузку |
| I assembly | Новый manifest успешно собрал metadata-only FastAPI object; Torch и Transformers не импортированы; сервер не запускался | HTTP/inference, FD inheritance реального I и физический teardown |

Существующие окружения и cache предлагается использовать read-only: их не
копировали и не изменяли. Установка/скачивание не выполнялись. В текущем controller
нет ML-зависимостей, но их наличие в отдельных найденных окружениях проверено
по metadata; добавлять их в controller только ради запуска CLI не требуется.

## Предложенные пределы — ещё не утверждены

| Параметр | Значение предложения |
|---|---:|
| Общий запуск |1200с |
| Одна HTTP/worker операция |330с, дополнительно ограничена остатком общего окна |
| Одна DB операция |5с |
| TERM / KILL wait |5с /5с |
| Cleanup reserve |30с |
| Parent controller admissions |8: open/process для четырёх стадий одного фото |
| Фото / исходник / decoded pixels |1 /20MiB /2359296 |
| Regions на фото |10 |
| Wire/artifacts на операцию |40MiB |
| Vector JSON на одну encoder-стадию |1MiB |
| RSS ceiling собственного тяжёлого контура |6GiB; I не выше6GiB, encoder не выше5GiB |
| MPS ceiling собственного тяжёлого процесса |6GiB |
| Freshness / предлагаемый poll |5с /0,5с |

Пределы — предложение для ограниченной пробы, не SLA, production defaults или
доказанная безопасная вместимость. RSS/MPS на unified memory не складываются
механически; фактические наблюдения обязательны. Warning300с/стабильность30с,
critical/unknown/stale STOP и no automatic restart остаются принятыми правилами.
Один тяжёлый worker одновременно; освобождение предыдущего подтверждается
до начала следующей стадии. Временная БД — отдельный owned контейнер; рабочий
DSN не применяется. Её запуск/seed/publication входят в будущий отдельный допуск050.

## Свежие отпечатки и приватный пакет

Полный input inventory, paths/interpreters,71code hashes, профиль, модельные pins,
runtime-binding proposal, permission proposal и ExecutionPackage JSON сохранены
в новом private каталоге0700; файлы0600. Raw paths/данные и полный descriptor
не добавлены в Git. ExecutionPackage прошёл DTO/finite-limit проверки;
связанные SHA и права повторно сверены. `execution.claim` не создавался.

Пакет-предложение SHA:
`53d9ac2acaa49b5e74196d7188b86c9bec2ccf96e9cc239a8a002f1b6c9955d1`.
Новый metadata-only I fingerprint:
`783fca1ad0dc9167a789e2a6ab1bc0c9b498ae5a1523abbdb189df038ed7d0a1`.
Он имеет статус PROPOSED, а не прежний APPROVED_BY_OWNER runtime.

По сравнению с принятым I snapshot изменены три code entries:
`nail_wire.py`, `openclip_provider.py`, `transformers_provider.py`;
изменился и installed inventory. Поэтому старый accepted fingerprint/consumed
validation window не использован. Новый I runtime profile отражает текущий
encoder inventory. Новая permission proposal имеет отдельный nonce, статус
PENDING_OWNER_APPROVAL и пустую authorization; это не действующий ML-допуск.

При доработке кода package/code/runtime hashes нужно заново заморозить.
Текущий пакет нельзя молча объявить runnable после изменения исходников.

## Связка подготовлена — 2026-10-14

Все четыре части реализованы и проверены без реальных моделей:
StageWorkers/child entry, supervisor host, resource observer/poll и fresh grant
issuer/consumer. [Отчёт проверки](runtime-binding-verification-report.md) содержит
точные свидетельства и ограничения. Пункт049 завершён как подготовка; это не
разрешение050 и не подтверждение ML-ready состояния.

Новый private пакет содержит77 code hashes, frozen input, профили, host/client
configuration и правила принадлежности будущей временной БД. `binding_ready=true`,
но `execution_ready=false`: действующего grant и БД ещё нет.

Актуальный SHA пакета:
`0cd821885cacef3add648cdfc9738642fbea3fdf2c6906d7f8b29943e3116d80`.
Предыдущий SHA выше — историческое предложение до изменения кода; он заменён.
I metadata fingerprint остался прежним: точные bytes его профиля сохранены.
Существующие окружения повторно проверены без SDK import. Encoder manifests
содержат87entries:39+18+30; прежнее число89 исправлено как ошибка подсчёта.

Перед050 обязательны отдельное утверждение этого пакета, новая собственная БД
со schema0010 и проверенное отсутствие пересечения с прежним поиском/ML-процессами.
Будущий target descriptor создаётся при подготовке этой БД; он должен соответствовать
зафиксированной private метке, image и endpoint policy. Рабочий DSN не применяется.
Разрешение переходов SEARCH относится к внутреннему режиму временного host;
запросы поиска и Web cutover этим предложением не разрешаются.

Ресурсный журнал ограничен40MiB; ошибка записи или превышение лимита закрывает
допуск. Сохраняются stage/model/PID, pressure, RSS и MPS observations. Это позволяет
разобрать будущую пробу; сейчас физических модельных наблюдений нет.

## Проверка подготовки и ограничения

Первый сборщик предложения выявил несовпадение старого code hash; source/runtime
не переписывались ради совпадения. Подготовлен новый manifest текущих файлов.
Metadata bootstrap сначала отказал из-за отсутствующего private runtime directory;
после создания собственного каталога0700 readiness/assembly прошли без SDK import.
Одна проверка DTO без PYTHONPATH дала import error; окружение команды исправлено,
SHA/schema/rights проверены. Это ошибки подготовки, не TDD RED продуктовой логики.

На первом этапе продуктовый код не менялся; после разрешения владельца
реализована связка, описанная выше. Модельные cache не менялись. В немодельной проверке использовалась
собственная synthetic DB; её очистка подтверждена. Реальные ML-серверы/inference,
новая модельная БД, grant для выбранного фото, установка, commit/push/merge
не выполнялись. Прежние619
синтетических свидетельств здесь не объявлены результатом реального runtime.
Независимое review не проводилось: STANDARD, самопроверка подготовки.

## Актуальный результат и пакет после пробы050 — 2026-10-14

Предыдущие разделы сохраняют историю подготовки. Владелец утвердил пакет
`0cd821885cacef3add648cdfc9738642fbea3fdf2c6906d7f8b29943e3116d80`;
его однократная проба завершилась RESOURCE_STOP до моделей.
[Результат, исправление и очистка](runtime-probe-report.md).

**Текущий пакет для отдельного допуска повторной пробы:**
`65815b4dea8f72cce467769800b81e6ad103626a6e2c8a15c9eb5dadf55d54ff`.
Объём, выбранное фото и численные пределы сохранены. Исправлена проверка контекста
ресурсного журнала до создания первой стадии. Новый private root, target marker
и proposal nonce; прежние consumed claims не переиспользованы.91 немодельная
проверка проходит, metadata-only I readiness/assembly проходит без SDK import.
Новый grant/БД не созданы, статус PENDING_OWNER_APPROVAL. Повторный START не выполнен.

## Текущий пакет после второго допуска050 — 2026-10-14

Пакет65815b4d был явно разрешён и однократно выполнен: RECOVERY_REQUIRED до
готовности localization, без checkpoints/vectors/publication. Очистка подтверждена.
[Отчёт и ограничения диагностики](runtime-probe-report.md#повторная-разрешённая-проба--2026-10-14).

Исправлен порядок начальной телеметрии до проверки runtime inventory;
92 немодельные проверки проходят. Объём и пределы прежние.
**Актуальный отдельный пакет для допуска:**
`1254eaea4c31a1603b623235686d28e6a73d5cd853e66f489c1c3b26e1a3d840`.
Статус PENDING_OWNER_APPROVAL, новый grant/БД не созданы. Прежние допуски consumed.

## Актуальное предложение после третьей пробы050 — 2026-10-14

Пакет1254eaea был отдельно разрешён и выполнен: RECOVERY_REQUIRED до localization
ready. Телеметрия создана, Torch/MPS bootstrap достигнут; inference/checkpoints/
vectors/publication не подтверждены. Owned cleanup проверен.
[Подробности](runtime-probe-report.md).

Исправлен подтверждённый TypeError actual worker: i_files содержит строки и
объекты с path, теперь оба представления преобразуются в Path. Тест actual
assembly RED→GREEN,93selected tests PASS; exact worker paths metadata assembly
PASS без SDK. Предыдущий подготовительный checker не покрывал эту конверсию.

**Текущий пакет:**
`d0e4b79d50ea07c84adcba8b10f23f946ff0d56321e2cc484fd92e731524e58c`.
Те же фото/объём/пределы, новые private root/nonce/target; PENDING_OWNER_APPROVAL,
новый grant/БД отсутствуют. Прежние consumed допуски не действуют на новый код.

## Текущий пакет после реальной localization стадии — 2026-10-14

Разрешённыйd0e4b79d однократно выполнен:10областей/crops/масок и1localization
checkpoint, затем RESOURCE_STOP при штатном teardown до encoders. Cleanup
подтверждён. Исправление monitor stop/join перед worker termination прошло TDD;
94selected checks PASS. [Свидетельства и ограничения](runtime-probe-report.md).

**Новый пакет:**
`bbb3d386e828edb26fdd9901ed18a2ea05d9724003fdf86c40b18def861aabff`.
Фото, объём и численные пределы прежние; новые code hash/root/nonce/target.
PENDING_OWNER_APPROVAL, grant/DB не созданы. Новая ML-проба не выполнялась.

## Последний статус — проба выполнена, 2026-10-14

Владелец разрешилbbb3d386, fresh grant consumed ровно на один START.
Результат **OK**,49,690с: полный I→три encoders→4checkpoints→READY→publication
только temporary DB. Cleanup подтверждён. [Отчёт](runtime-probe-report.md).
Этот пакет уже использован, а не ожидает нового допуска и не даёт права повторить
пробу. Новое предложение после успешного запуска не создавалось.050 выполнен,
051review открыт; рабочая активация/пополнение этим результатом не разрешены.

## Пакет после исправлений051 — 2026-10-14

[Новая подготовленная проба](post-review-runtime-proposal.md) относится к текущему
исправленному коду: SHA79f709ee1dec6317e8a14f14b041f74dc42ef338b2c35d2370b8840ea550be4a.
То же фото/объём/пределы; новый private root/nonce/target. Metadata/bytes/permissions/
entrypoint guards PASS без моделей. Grant/DB не созданы, PENDING_OWNER_APPROVAL.
Предыдущий успехbbb3d386 не переобъявлен проверкой исправленного кода.
