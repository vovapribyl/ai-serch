# T051 — подготовка и ограниченная сборка корпуса

Текущий проход2026-10-11: [owner-approved skip-photo build100](skip-photo-build-plan.md),
job9d1fa00b.../100inputs/3103admissions/3600s/no-publish. Изменены только wire error
classification и skip policy; новая extractor identity7c0b1914.../отдельная representation.
Safe383PASS46SKIP, independent reviewPASS; preflight4,803s/noSDK/100inputs/PASS.
[Один разрешённый ML-проход завершён](skip-photo-build-report.md):115,634s/pressure4STOP,
20OK/1NO_NAILS/1ERROR/78PENDING. Окно использовано; данныйbill не разрешает новуюпопытку.
Прежние записи ниже исторические.

Обновление2026-10-11: owner сократил первый тест до[100fixedinputs](corpus-100-report.md).
Job3a8b2962.../100inputs/3103admissions/60min был явно разрешён владельцем и
[исполнен один раз](build-report.md):26.61s/pressure4STOP/PENDING100. MLwindowconsumed;
этотbill не допускновойпопытки.
Затем владелецразрешил[новуюпопытку](build-retry-report.md):6OK/94PENDING/observerSTOP.
Текущийподготовленныйjob35650306...послеobserverfix также100/3103/3600s,
егоодинMLwindow затемразрешён и[исполнен](build-observerfix-run-report.md):17OK/1NO_NAILS/82PENDING/LOCALIZATION_STOP.
Новаяprepareddiagnosticпроба только019,job3a51c9bf.../1input/34admissions/360s
разрешена и[выполнена](photo019-diagnostic-report.md):16,82s/RESOURCE_ERROR.
Окно использовано; вероятный region-count limit, exact branch UNKNOWN. Полный100restart не разрешён. Прежний[674package](native-execution-package.md) сохранён
исторически; егоscope/budget/6h больше неcurrentfirsttestbill.

Дата первоначального bill: 2026-10-09. Подготовка без ML отдельно `APPROVED_BY_OWNER` по «Разрешаю» на
runner/новую БД/parent copy/hash/decode. Native часть — `DRAFT_FOR_OWNER_REVIEW`.
[Actual preparation report](build-preparation-report.md):673decodeOK/1pixel-limit
blocker, новый persistent target и tested outer runner components. T051 `[ ]`;
Real native assembly/command не готовы, model window не разрешён. Последующий
[model-free composition report](build-composition-report.md) подтверждает generic
wiring/observers/supervised fake command, не actual native execution.

## План-контракт и источники

STANDARD: сверить [T050 inventory](build-readiness.md), [G3 storage](g3-storage-decisions.md)
и [G4 reference](runtime-profile-reference.md) с текущими code boundaries → предложить
целевой контур, подготовку runner и конечный execution bill → самопроверка ссылок,
статусов и арифметики → предъявить владельцу. Новые нормативные решения не приняты.
Независимое review первоначального STANDARD bill не проводилось; actual подготовка
и permission проходят FULL review, результат — в preparation report.

Применение Ponytail: переиспользовать core build service, PostgreSQL adapter,
image store и existing G4 providers/guardian; не создавать второй алгоритм сборки.
Книжные наборы не применялись: границы core/ports и принятая schema не меняются.

## Исходный snapshot перед разрешением подготовки

Таблица фиксирует состояние до выполнения model-free подготовки. Актуальные
decode/target/guard результаты и blocker находятся в [actual report](build-preparation-report.md).

| Предпосылка | Наблюдение / следствие |
|---|---|
| Входы | Gate 2 primary scope: 674 записи/фото; T050 manifest SHA `c7645904d0e71666491f29ef27182c6bda6051e963c640ccb5596ab2af1dc1f5` |
| Содержимое | 674 hashes совпали с БД; 7 пар duplicate bytes сохраняются без dedup; decode/dimensions ещё NOT_RUN |
| Source DB | Gate 2 head `0004_import_operations`; не применять к ней nail migrations |
| Build entrypoint | [build_nail_representation.py](../../../../../.codex/worktrees/candidate-i-http/Ai/scripts/build_nail_representation.py) имеет injected `run_build(...)`; прямой CLI намеренно завершает процесс без сборки |
| Build core | [NailCatalogBuildService](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/search/nail_catalog_build.py) создаёт BUILDING и пишет исходы; `publish(...)` — отдельный метод |
| Storage | `PostgresNailCatalog` требует source parent rows в той же целевой БД и head `0009_nail_search_v1` |
| G3 helper | `tests/support/nail_db.py` — tmpfs + обязательное удаление контейнера; непригоден для сохранения реального build |
| Image | Прежний cached image SHA `ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` повторно найден read-only; server readiness нового target не проверена |
| Runtime | Принят G4 synthetic profile; окно 65 ops / 1200 s израсходовано. Не переносить его permission на 674 фото |
| Checkout | Existing product worktree, detached HEAD `ba495046c80d25190a1745cb9f63384d00a42dd4`, dirty; HEAD не полная code identity |

Следовательно, разрешение «собрать сейчас» пока не имеет проверенной команды.
Нужно отдельно подготовить настоящий runner и постоянный target, затем предъявить
их фактические identities и model-free checks перед нативным запуском.

## Предлагаемый целевой контур

Новая отдельная локальная БД для Candidate I G5, а не Gate 2 и не рабочий search DB.
Один новый контейнер из указанного cached image с `--pull=never`, `restart=no`,
loopback ephemeral port; отдельный persistent Docker volume. Уникальные имена,
ownership label, container/image/volume IDs, endpoint/database/role и credentials
фиксируются приватно. Target root `700`, descriptor/env/artifacts `600`.

Перед любой записью проверять target identity по приватному descriptor: Docker
container/image/volume/ownership label и SQL current database/current user. Не
принимать произвольный DB URL и не переиспользовать имеющийся volume по одному имени.
Миграции до `0009_nail_search_v1` выполняются только в этом новом owned target.

Для FK нужны parent `corpus_versions` и 674 `product_records`: после отдельного
разрешения повторно проверить source identity/manifest и в READ ONLY transaction
прочитать только выбранную версию и обязательные поля её записей. Сохранить source
numeric IDs и связь с исходной import operation; не копировать embeddings, evaluation,
другие версии или полные import reports. T050 mapping не содержит category и всех
полей parent row: дополнять их предположениями нельзя.

Копирование — запись в новый target, не новый импорт XLSX и не активация нового
корпуса в Gate 2. Original photos остаются read-only входами; новый image store пишет
только masks/crops своей representation в отдельный приватный root. Build target
не подключается к Web/search. При ошибке новые volume/artifacts сохранить для отчёта,
не удалять автоматически. Если имя уже занято — STOP, не recreate и не overwrite.

## Первое отдельное разрешение: подготовка без ML — принято владельцем

Owner «Разрешаю» отдельно разрешил следующие действия до предъявления native run bill:

1. В existing product worktree сохранить dirty state; подготовить admitted build
   runner вокруг `run_build`, `NailCatalogBuildService`, `PostgresNailCatalog`,
   `NailImageProcessor`, `NailImageStore` и существующих HTTP/embedding adapters.
   Зафиксировать реальные imports/signatures перед изменением; не менять algorithm,
   accepted model packages/weights/config и source archive G4.
2. Создать описанные owned container/volume/private roots, применить existing
   migrations только к новому target, скопировать разрешённые parent rows с provenance.
   Использовать existing SQL/Python packages; отсутствие зависимости → отдельный bill,
   без установки по этому пакету.
3. Повторно проверить все input hashes и выполнить bounded decode 674 фото без ML
   по accepted EXIF/RGB/source/pixel policy. Не resize, не truncate и не исключать
   неподходящие фото молча: несовпадение identity/hash или invalid/oversize input
   блокирует native запуск и фиксируется в безопасном отчёте.
4. Проверить fake wiring, новый target SQL и guard/teardown boundaries. Проверки
   проводить на отдельно обозначенных synthetic rows/namespace, без создания real
   BUILDING representation и без provider load/inference.
5. Сохранить точный private descriptor/runner/profile/command/fingerprints; предъявить
   actual preparation report и обновлённый native bill владельцу. Нативные модели
   этим первым разрешением не запускаются.

Проверки до реализации: TDD для проверяемой новой runner/guard логики. Зафиксировать
регрессии: неправильный target → отказ до записи; hash/profile mismatch → до ML;
STOP во время фото → ни одного следующего model admission; no-publish после успешной
сборки; partial build после forced owned-worker exit сохранён, pointer не изменён.
Synthetic migration/parent FK и rollback проверяются только на owned target.

## Предлагаемый native bill — после готовности runner

Все новые числовые bounds ниже — `DRAFT_PROPOSAL`, не измеренная длительность,
capacity, готовая policy или уже выданное разрешение. Они должны быть подтверждены
владельцем после фактической model-free подготовки.

| Граница | Предложение |
|---|---|
| Входы и число попыток | Один новый build, ровно 674 frozen primary photos в manifest order; каждое фото ≤1 I admission, без retry/resume/restart |
| Representation | Одна новая BUILDING; model/crop/inventory identity frozen. READY и active pointer в этом run не меняются |
| Model-backed budget | ≤20897: ≤674 I POST + ≤3 provider loads + ≤20220 single-crop encodes (674 × 10 × 3) |
| Максимум результатов | ≤6740 regions и ≤20220 vectors размерностей 512/768/768; NO_NAILS допустим и уменьшает actual work |
| Wall window | ≤21600 s (6 h) от старта owned execution group; цель пройти весь manifest, завершение за это время не гарантировано |
| Параллелизм | Одно фото in-flight, один I request; providers последовательны, existing cache retained; shared device/coordinator leases |
| Target DB | Proposed container memory ≤1 GiB, CPUs ≤2; лимиты existing Colima VM не увеличивать; OOM/DB failure → STOP, данные сохранить |
| Derived storage | STOP при observed owned DB + artifact payload ≥32 GiB или free space <16 GiB; проверять host и VM filesystem отдельно до run и в ходе run |
| Resource policy | G4 warning/swap diagnostics; critical/unknown pressure, mandatory observation failure/staleness >5 s, RSS/error/timeout → STOP |
| RSS / HTTP deadlines | Сохранить I6/backend5/combined10 GiB, connect1/write30/read300/overall330 s; не считать DB/VM память частью этих двух-process RSS |
| Decode / wire limits | Source20 MiB, decoded2359296pixels, regions10, response40 MiB, solver16384, model artifact manifest8 MiB; не увеличивать |

20897 — арифметический максимум внешних admissions, не внутренних tensor operations.
В I POST включён frozen localization flow; каждый provider `encode_image` учитывается
отдельно. Весь бюджет общий для окна; unused operations не дают второго запуска.
Storage STOP — порог наблюдения, не filesystem quota; overshoot между samples возможен,
поэтому ограничение freshness и журнал sampled sizes обязательны. Снимок свободного
места host при подготовке: 88883200000 bytes; это не проверка свободного места VM
или гарантия наличия этого объёма перед run.

## Identity, STOP и выходы

Сохранить accepted G4 source/config/weights/locks без изменения. Новый build runner
и operational profile имеют отдельную identity; не выдавать старый G4 fingerprint
за доказательство нового assembly. Проверять exact I readiness через actual observer,
три provider manifests/revisions, backend package inventory и соответствие
BuildIdentity/SearchProfile. T050 manifest SHA не является автоматически
`BuildIdentity.inventory_sha256`: fingerprint canonical BuildPhoto inventory
фиксируется отдельно с проверенной связью к T050 и parent IDs.

Прямой CLI должен быть допущен только после model-free verification factory и
actual target identity; typed DTO сам по себе не свидетельствует readiness.
`NailCatalogBuildService` ловит `NailProcessingError` и может продолжить после ERROR.
Поэтому resource/budget/timeout STOP должен быть terminal для outer runner/guardian
и запрещать дальнейшие admissions; запись ERROR не даёт права перейти к следующему
фото после terminal STOP. Не объявлять существующий catch достаточной hard-stop защитой.

External guardian завершает только owned execution group. Target DB сохраняется;
никаких kill чужих процессов, удаления исходных данных/volumes или auto retry/resume.
На STOP — safe partial counts и actual exit/lease checks; PENDING не скрываются.
Непроверенное после forced exit остаётся UNKNOWN.

После run: будущий файл `build-report.md` должен содержать counts OK/NO_NAILS/
ERROR/PENDING, regions/vectors, complete/coverage, actual admissions/time/resource/
storage/teardown. Пока файла нет, этот путь — будущий output, не evidence. Representation
остаётся BUILDING даже при `summary.complete=true`: `publish` переводит READY и меняет
pointer только по отдельному разрешению. Полностью пустой/неполный каталог не READY.
Coverage и 7 duplicate byte pairs предъявляются владельцу в T052; качество — T053/T054,
publish/activation — T055. Safe report не содержит IDs, paths, images/masks/vectors
или credentials. Установки, download, J, Git publication и Web activation не входят
ни в подготовку, ни в proposed native run.

## Исходное решение по подготовке и текущий stop point

Владелец согласовал только раздел «Первое отдельное разрешение: подготовка без ML»:
runner + новый persistent target + выбранные parent rows/hash/decode preflight +
fake/SQL checks. После actual подготовки предъявить exact native command и отдельное
разрешение на новый window. Не утверждать этим решением предложенные 6 h/20897 ops
как уже разрешённый запуск. Actual preflight выявил одно oversize фото; требуется
отдельное решение по input policy перед реальной сборкой. Вопрос отложен владельцем
в [бэклог](tasks.md#бэклог); независимая model-free composition на fake данных может
продолжаться без изменения фото/manifest входов. См. [preparation report](build-preparation-report.md).
Исходные параметры native bill
ниже/выше сохраняют статус предложения.

Самопроверка: существование code pointers/class names и безопасный direct CLI exit
подтверждены чтением исходников без imports; ссылки/таблица/статусы/арифметика/
markers/whitespace PASS, tracked `git diff --check` PASS. Untracked документы
проверены напрямую. Это проверка пакета, не runner/DB/runtime readiness.
