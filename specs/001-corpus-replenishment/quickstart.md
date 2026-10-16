# Проверка решения: порядок и команды

> Последняя offline-проверка: [среднее по назначенным парам](../corpus-optimization/matched-pairs-mean-report.md). Положительные ранги улучшились, проявился риск одного совпадения; формула продукта прежняя.

> Последний тест: [семь запросов завершены](../corpus-optimization/remaining-quality-report.md);
> два новых фото после telemetry fix прошли, 116 guard OK. [Первичный визуальный разбор](../corpus-optimization/localization-review.md) также выполнен; [offline-исключение областей](../corpus-optimization/region-exclusion-report.md) выполнено, хорошего ранга не дало.
> Прежние «последние результаты» ниже сохранены как история.

> [Карта проекта](../../docs/project-map.md) · [Текущие результаты и следующий шаг](verification-followup-status.md).
> Документ объединяет порядок проверок и хронологию их исполнения. Все датированные
> «следующие шаги», PREPARED и разрешения ниже относятся к своему этапу, а не к новому
> допуску. B0 и задачи 001–051 завершены; старые команды не запускать автоматически.

**Последний пакет2026-10-15:** [20фотоOK, качествоPARTIAL, telemetryfixпроверен безML](verification-followup-status.md).
80checkpoints/336vectors, затем query5из7 и STOPтелеметрии.135postfix testsPASS;
50–100не запускались. Прежниеpackages после двух code changes не переиспользовать.


Последний результат2026-10-15: [полный цикл и две партии1+5+5](three-phase-runtime-report.md)
прошли в собственной временнойБД:11готовых товаров,44checkpoints/186векторов,
482guardOK/0WARNING/0STOP, прежний800/лимиты. Сохранность данных и cleanup
проверены; grants использованы, автоматический новый запуск не разрешён.


Изменение2026-10-15: [лёгкий журнал ресурсов](light-resource-logging.md) добавляет worker samples примерно1Гц, import boundaries и ротацию. Прежние frozen packages после изменения трёх инфраструктурных файлов не переиспользуются; новые ML-прогоны этим изменением не выполнены.

Последний результат2026-10-15: [пакет ошибок и повторов](error-retry-runtime-report.md) выполненOK за137,139с. Malformed image теперь изолирован как ошибка фото только в native adapter, hash/storage STOP сохранён; обновлены fingerprints двух продуктовых файлов.510replenishment tests и65пересекающихся image/build/payload testsPASS. Реальные ERROR/OK/NO_NAILS/ERROR, выборочный retry без перерасчёта готового, ожидаемый отказ публикации с сохранением active, retry и идемпотентность безML прошли.205guardallOK/5grantsconsumed/owncleanupPASS; нетworkingcutover/limitincrease/install/commit. Старые execution packages не переиспользуются после изменения кода.

Актуальное уточнение2026-10-15: [межфазный test gate](interphase-stop-diagnosis.md) ожидает≤5с вместо мгновенногоassert; unknown/persistent/late absence не открывают переход.57tests и8native casesPASS; новаяреальнаяSTART2→RESUME6 прошла за61,646с,1→4CP/30vectors/1pub/безповтораI.86guardallOK/owncleanupPASS. Продуктовый код/модели/лимиты прежние, точные исторические Assertion/resourceSTOP причины UNKNOWN.

v1 / APPROVED_BY_OWNER. Ниже — принятый порядок проверки и датированные
свидетельства реализации. Синтетические B1-проверки выполнены; реальная проба
по-прежнему требует отдельного пакета и разрешения. Команда сама по себе
не доказывает готовность, качество поиска или право на эксплуатацию.

## Сейчас: документный маршрут

Из корня проекта доступны:

```sh
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
git diff --check
```

Feature определяется .specify/feature.json. Поле BRANCH shell-script может содержать
имя feature_directory; actual git branch проверяется git branch --show-current,
для этой работы она codex/upload-optimiz.

## Исторические предпосылки: до реализации

Утвердить plan и contracts, затем tasks. Закрыть B0: сравнить checkout/source,
согласовать manifest, восстановить нужные baseline tests без ML. Наличие .venv
само по себе не доказывает наличие всех тестовых dependencies.

## Немодельный TDD после создания тестов

Реализованные tests (unit-команды требуют `PYTHONPATH=src:.`; process/DB —
действующий B1 и bounded wrapper, а не неограниченный полный pytest):

```sh
.venv/bin/python -m pytest tests/test_replenishment_rules.py
.venv/bin/python -m pytest tests/test_replenishment_controller.py
.venv/bin/python -m pytest tests/test_replenishment_artifacts.py
.venv/bin/python -m pytest tests/test_replenishment_catalog_binding.py
.venv/bin/python -m pytest tests/test_replenishment_cli.py
```

Каждая единица: первый запуск ожидаемо RED по поведению; затем минимальная
реализация GREEN; после refactor повтор релевантных тестов. Фактические результаты
и оговорки TDD приведены в датированных отчётах реализации.
Expected: 5/7-photo boundaries, одна готовая фото достаточна после всех терминальных,
пауза300/30с с fake clock, no implicit retry/next batch, damaged checkpoint refusal,
snapshot consistency/parity, superseded revision refusal и actor boundaries. Эталоны из ФТ/ART-09, не из реализации.

## Интеграционные gates

На отдельно разрешённой временной test DB без данных корпуса проверить:
миграцию новых таблиц, commit/rollback, concurrent versions, fencing, publication
receipt и потерю ответа. Реализованный tests/test_replenishment_postgres_integration.py
использует B1 helper: создаёт собственный bounded контейнер, проверяет identity
и сам генерирует credentials. Default рабочий DSN или переданный сторонний DSN
не используется. Контейнеры создаются строго по одному.

На Mac с fake дочерними процессами проверить tests/test_replenishment_lifecycle.py:
exec/FD inheritance, crash parent, второй mode-lock contender, kill own groups,
deadline, поиск racing DRAINING, передача SEARCH→BUILD без unlocked окна
и запрет чужого PID/group. Никакие модели не загружаются. Новый процессный
код исполняется только после утверждения соответствующей немодельной проверки.

## Реальная проба отдельно

До запуска: отдельный owner gate, свежие code/model/config fingerprints, private
inventory и численные limits/deadlines/ceilings. Не использовать consumed claims.
Owner CLI start с новым private ExecutionPackage после реализации. Ожидаемый
результат сверяется с [ART-09](../../docs/analysis/09-acceptance-criteria-and-traceability.md#дополнение-пополнение-поискового-корпуса).

Сохранить фактическую сводку, модельные вызовы, host/MPS нагрузку, teardown и
совместимость vectors. Отдельно разрешать продолжение и рабочую DB publication.
Успешные unit/fake tests не заменяют runtime, качество поиска или разрешение cutover.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.

## Подготовленный допуск B1 — 2026-10-13

[Пакет немодельных проверок](test-execution-package.md) подготовлен для задачи004.
Статус APPROVED_BY_OWNER — сообщение «Утверждаю»2026-10-13.
Process/testDB проверки разрешены по конкретномуB1; результаты фиксируются отдельно.
Unit TDD продолжается независимо. Pythonpgvector/numpy не требуются текущему
SQL-адаптеру; установка dependencies не входит в пакет.

Уточнение2026-10-13: migration0005 требует Pythonpgvector. Bootstrap
пока BLOCKED; [одно dependency дополнение](test-dependency-addendum.md) подготовлено,
установка не выполнялась. Process/files scopesB1 остаются действующими.

Обновление2026-10-13: владелец выбрал установку толькоpgvector0.5.0;
metadata/importPASS, B1bootstrap1passed. Dependency блокер снят.
Следующий шаг — schema/state adapter по задачам020–022 через TDD.

## Фактическая немодельная проверка — 2026-10-14

Пункты047–048 выполнены: [отчёт](acceptance-verification-report.md).
Все52 FR сопоставлены с тестами в ART-09;45 имеют B1-свидетельство,
7 — частичное с остающимися runtime-границами. Новые acceptance-сценарии8passed,
включая5+2, независимость товаров, сводку и downgrade/upgrade0010→0009→0010
с сохранением синтетических legacy-записей. Native inherited FD/parent crash
входят в выбранную регрессию. Всего619 различных успешных случаев.

Общий B1:175passed/1setup error TEST_DB_READINESS; после диагностики только
ошибочного setup-случая —1passed. Это не один полностью зелёный общий прогон;
точная первоначальная причина UNKNOWN. Unit/Web443passed отдельно до B1.
Контейнеры очищены. Полный suite/realML/MPS/корпус/рабочаяDB не проверялись.
Следующий шаг049 — свежий runtime package/binding;050 требует отдельного owner
разрешения,051review открыт. Все прежние operational gates сохраняются.

## Первый этап049 — 2026-10-14, историческая запись

[Предложение первой пробы](runtime-probe-proposal.md): один выбранный товар/фото,
byte-identical private input, свежие code/model/runtime fingerprints и конечные
пределы подготовлены. Metadata-only I assembly проходит без SDK import/сервера.
Есть существующие отдельные I/encoder environments; установка не выполнялась.

Пакет PROPOSED_BLOCKED_BY_BINDING, execution_ready=false.049 остаётся открытым:
нужны настоящие StageWorkers factory, supervisor host, resource observer и
issuer/consumer свежих claims. Model-free wiring разрабатывается по TDD внутри049;
после изменения code/runtime пакет замораживается заново. Затем отдельное owner
разрешение050 на ML/testinputs/изолированнуюDB/publication. Старые consumed windows
не используются; передать текущий proposed JSON в start нельзя.

## Связка049 подготовлена — 2026-10-14

[Отчёт проверки](runtime-binding-verification-report.md):512 выбранных немодельных
проверок и1 новый DB-сценарий. StageWorkers/host/resources/claims связаны; новый
private пакет заморожен после изменения кода.049 выполнен как подготовка.

[Предложение050](runtime-probe-proposal.md) содержит актуальный SHA и пределы.
Grant не выдан; выбранное фото не обрабатывалось моделями, новая модельная БД
не создана. Реальный запуск050 требует отдельного утверждения пакета, проверки
прежних процессов и собственного DB target.051 и runtime acceptance открыты.

## Проба050 — 2026-10-14

[Отчёт пробы](runtime-probe-report.md): владелец разрешил утверждённый пакет;
новая временная БД подготовлена, grant consumed, START вернул RESOURCE_STOP до
первой модельной стадии. Причина — обращение журнала к ещё не созданному control.
Исправлено через TDD; итоговая выбранная регрессия91passed. Очистка подтверждена.
050 остаётся открытым: vectors/inference/тяжёлый teardown не проверены.
Новый пакет с исправлением подготовлен; повторный настоящий запуск требует
нового допуска на SHA из отчёта.051 review остаётся открытым.

Повтор050 разрешён и выполнен на пакете65815b4d: RECOVERY_REQUIRED до готовности
localization,0checkpoints/vectors/publication. Owned DB/process/socket cleanup
подтверждён. Найден дефект порядка первого telemetry sample; TDD RED→GREEN,
итог92selected model-free passed. Новый пакет1254eaea подготовлен, допуск pending;
050/051 не закрыты. Подробности и границы диагноза — в [отчёте пробы](runtime-probe-report.md).

Третья проба050 на явно разрешённом1254eaea вернула RECOVERY_REQUIRED до ready;
worker telemetry/Torch/MPS bootstrap достигнут,0checkpoints/vectors/publication.
Подтверждён TypeError смешанных строк/object path в actual `_serve_localization`;
исправлен через TDD.93selected tests и exact worker paths metadata assembly PASS.
Cleanup подтверждён. Новый пакетd0e4b79d подготовлен, допуск pending;050/051 открыты.
Полный worker traceback UNKNOWN; подробности в [отчёте](runtime-probe-report.md).

Четвёртая проба050 на разрешённомd0e4b79d: I HTTP обработал фото,10областей/crops/
масок,1saved localization checkpoint.187,022с, RESOURCE_STOP при teardown;
0vectors/publications. Pressure WARNING затемOK; ceilings не превышены в успешных
samples. Исправлена гонка остановки monitor/worker через TDD,94checks PASS;
cleanup подтверждён. Новыйbbb3d386 prepared/pending approval,050/051 открыты.
[Подробности](runtime-probe-report.md).

## Полный runtime-путь050 подтверждён — 2026-10-14

Разрешённыйbbb3d386: один START/товар/фото, **OK за49,690с** с подготовкой/очисткой.
I HTTP→10crops/масок→OpenCLIP→DINOv2→SigLIP2→4checkpoints→READY→publication
в новую temporary DB.10regions/30vectors/1snapshot/1publication; dimensions512/768/768,
finite/unit-norm checks PASS.84resource samples OK, peakRSS1,42GiB/MPS3,78GiB.
Ownedprocess/socket/container/secret cleanup подтверждён. WorkingDB/Web не менялись.
050 выполнен;051independent review остаётся. [Полный отчёт](runtime-probe-report.md).
Качество поиска/большие партии/real retry-resume/production acceptance не проверены.

## Итоговое независимое review051 — 2026-10-14

[Отчёт](final-code-review.md): REWORK,0Critical/5Important/0Minor.
Native retry-publication/grant consumption, expiry/revocation перед commit,
stale Unix socket после crash, общий SQL deadline и Unicode canonical hashes
требуют исправлений.94выбранных checks PASS не покрывают эти границы.
Код в review не изменялся;050 остаётся выполненной limited probe,
051 остаётся открытым до устранения важных замечаний. Интеграция не готова.

## Замечания051 исправлены — 2026-10-14

Владелец разрешил исправления; пять Important из [review](final-code-review.md)
устранены через TDD. Grant consume отделён от ML factory, проверка перед SQL/commit,
безопасный stale-socket recovery, свежий SQL/FETCH timeout и Unicode hashes.
Финал194selected B1/native passed + отдельно300selected model-free passed;
выборки пересекаются, это не сумма distinct tests и не полный suite. Промежуточные
188PASS/5FAIL зафиксированы, streaming cursor восстановлен. Owned cleanup/ruff/diff PASS.
051 выполнен; повторное независимое review не проводилось. Новый ML/workingDB/Web
запуск не выполнялся, ранее consumed package не применим к исправленному коду.

## Новая подготовка после051 — 2026-10-14

[Предложение](post-review-runtime-proposal.md): один прежний товар/фото, исправленный
код, прежние пределы и новая temporary DB. Пакет79f709ee подготовлен;77code hashes,
input bytes,87encoder files и I metadata assembly/3entrypoint refusals PASS безSDK.
Настоящая проба после исправлений ещё не выполнена. Статус PENDING_OWNER_APPROVAL,
grant/DB не созданы; текущая нагрузка проверяется непосредственно перед запуском.

## Проба исправлений051 — 2026-10-14

[Результат](post-review-runtime-report.md): пакет79f709ee явно разрешён и использован.
50,074с, все4модели/4checkpoints/photoOK,30finite/unit-norm checkpoint vectors;
ERROR INFRASTRUCTURE_ERROR до publication, revisionOPEN,0SQLvectors/snapshots.
81observationsOK, cleanup подтверждён. ПричинаUNKNOWN: command traceback отсутствует.
Немодельная actual host/grant/application/repository composition с fake stages
в owned synthetic DB —1passed; real error не воспроизведена. Production code не
изменялся, нового ML retry нет. Нужны private failure diagnostics и свежий пакет,
прежде чем утверждать полный post-review runtime success.

## Приватная диагностика команды — 2026-10-14

[Диагностика и новая проба](runtime-failure-diagnostics.md): dispatcher/socket
сохраняют private type/frame/cause metadata без messages/values/raw input.
2RED→GREEN,127selected model-free/native PASS,2DBcases исключены, ruff/diff PASS.
Причина прошлого отказа UNKNOWN. Новый7d89d5dapackage prepared/pendingapproval;
grant/DB/ML не создавались.

## Полный post-review runtime на одном фото — 2026-10-14

Разрешённый7d89d5da завершился **OK за82,661с**: I→три encoders→4checkpoints→
OK/READY→1snapshot/1publication,10regions/30finite/unit-norm vectors512/768/768.
203resource samples197OK/6WARNING/0STOP, RSSpeak1,14GiB/MPS3,77GiB.
Owned process/container/socket/marker/secret cleanup подтверждён. WorkingDB/Web
не менялись. [Отчёт с историей](post-review-runtime-report.md).
Ошибка79f709ee не повторилась, причина остаётсяUNKNOWN; repeat success не доказывает
её устранение. Следующий возможный шаг — отдельная подготовка партии до5фото,
не automatic build/cutover. Новый independent review/quality acceptance не проведены.

## Подготовка партии пяти фото — 2026-10-14

[Предложение запуска](batch-runtime-proposal.md): пять разных товаров × одно фото,
новый пакет cfe49786, 24 admissions, остальные пределы прежние.
Замороженные входы и существующий RGB-декодер проверены; metadata I и отказы
entrypoints без допуска проверены без ML. Grant/DB не созданы.
Статус PREPARED / PENDING_OWNER_APPROVAL; старый одноразовый допуск использован.

## Партия пяти фото: результат — 2026-10-14

Разрешённый cfe49786 использован одним START: **STOPPED / WAIT_TIMEOUT**, 404,117 с.
Пять localization manifest, четыре SQL checkpoints; SQL vectors/publications=0.
Ожидание ресурсов истекло перед фиксацией пятого checkpoint. 1448 samples:
297 OK / 1151 WARNING / 0 STOP, MPSpeak5,82GiB. Owned cleanup подтверждён,
рабочий каталог/Web не менялись; нового автоматического повтора нет.
[Отчёт партии](batch-runtime-report.md).

## Диагностика внутри I — подготовлена 2026-10-14

[Замеры и новый пакет](load-diagnostics-proposal.md): опциональные границы
GDINO/SAM2/проходов/encoder/admission/checkpoint, live tensors и MPS driver,
CPU/RSS собственных процессов, pressure/swap/pageouts и память own DB container.
90selected tests PASS, реальный OS-сборщик PASS без SDK. Алгоритмы и пороги прежние.
Пакет de3c9c6e PREPARED / PENDING_OWNER_APPROVAL, те же5фото/24admissions;
grant/DB/ML не созданы. Диагностика имеет собственные ограниченные приватные журналы;
ошибка измерения/отсутствие итогового status не является полной телеметрией.

## Диагностическая партия de3c9c6e — выполнена 2026-10-14

[Отчёт и источник нагрузки](load-diagnostics-report.md): один разрешённый START,
**OK89,322с**,5READY/20checkpoints/32regions/96vectors/5publications/5active members
во временной БД.201guard samplesallOK/pressure1, MPSdriverpeak5,83GiB.
Прирост driver сосредоточен между границами GDINO.predict, live после вызовов
около1,16GiB и почти стабильны.32crop/32mask bytes/SHA совпали с прошлой партией.
Parent diagnostic statuscomplete; final ML worker statusUNKNOWN. Owned cleanup
подтверждён,workingDB/Web не менялись,grant consumed. Нового retry/cache-fix нет.

## Проверка MPS-кеша — подготовлена 2026-10-14

[Пакет гипотезы](mps-cache-probe-proposal.md):99cea844, те же5фото/24admissions/
прежние пределы. Единственное изменение — opt-in empty_cache после успешной
локализации фото; no reset SAM/gc/resize/encoder changes. Before/after измеряются.
95selected tests PASS,metadata/3env отказа PASSnoSDK; новый grant/DB/ML отсутствуют.
Статус PREPARED/PENDING_OWNER_APPROVAL, реальный эффект и output equivalence UNKNOWN.

## Проверка MPS-кеша99cea844 — выполнена 2026-10-14

[Результат](mps-cache-probe-report.md): один разрешённый START,OK86,924с,
5READY/20checkpoints/32regions/96vectors/5publications/active members5 в own temp DB.
Driverpeak3,77GiB против5,83GiB базы (−35,33%); afterphoto5 —2,56GiB против5,80GiB
(−55,79%).5cachepairs/livebefore=after,64crop-mask actual bytes/SHA equal.
198guard samplesallOK/pressure1; owned cleanup подтверждён. Grant consumed.
Default-off сохранён, рабочего catalog/Web изменений и нового auto retry нет;
final MLworker footer/statusUNKNOWN остаётся ограничением диагностики.


Эксплуатационный журнал controller реализован отдельно от подробной диагностики; события, ограничения хранения и результаты synthetic checks описаны в [operation-logging.md](operation-logging.md). Результат частичной реальной пробы и последующего исправления описан ниже.


[Реальная проверка журнала](operation-log-probe-report.md): abb2da2b executed/stopped INFRASTRUCTURE_ERROR на проверке process group OpenCLIP,10SQLcheckpoints/0publications. Журнал55событий/incomplete=false, owned cleanup подтверждён. После прогона expected-stop logging исправлен RED→GREEN/151tests; причина EPERM неизвестна, новый код требует свежего пакета/разрешения перед ML.


[Диагностика проверки process group](process-group-diagnosis.md): краткий EPERM воспроизведён на synthetic worker+guardian, transient denial теперь сохраняет bounded ожидание до ESRCH; persistent denial блокирует продолжение.153tests PASS,20native teardown casesPASS. Реальная ML-партия после исправления не запускалась; нужен свежий пакет и отдельный owner допуск.


[Полный цикл с журналом](operation-log-confirmation-report.md):19ad687c EXECUTED/OK91,742с,5photoOK/5READY/20checkpoints/32regions/96vectors/5publications/5active members.115events31887bytes/incomplete=false,4worker exits expected=true;207guardallOK/pressure1. Crop/mask bytes совпали с99cea844, own cleanup подтверждён. Grantconsumed, нет auto retry/working cutover/увеличения партии; logging overhead отдельноUNKNOWN.


[Лёгкий терминальный монитор](light-monitoring.md) реализован: read-only once/watch каждые3сек, прогресс/стадия/длительность/heartbeat freshness/RSS-MPS/итог.163selected testsPASS и исторический19ad687c CLI-viewPASS. Logger расширен safe aggregates/photo_outcome; новыйMLrun не выполнялся, consumed пакет невалиден относительно нового кода.


[Монитор во время ML-партии](monitor-runtime-report.md):bf12dde3 EXECUTED/OK91,424с/host0/viewer0,5photoOK5READY20checkpoints32regions96vectors5publications5active members.31viewer snapshots/30fresh/WAITING→RUNNING→COMPLETED,125operationalevents/incomplete=false.200guardallOK/pressure1,crop-mask bytes equal99cea844,ownedcleanupPASS. Grantconsumed,noauto retry/workingcutover/увеличения партии; отдельный overheadUNKNOWN.


[Попытка двух последовательных партий](sequential-batches-report.md): разрешённая серия остановилась до START за21,309с из-за пути socket в тестовом runner. ML не начался, B не запускалась; временная БД/процессы/socket/секреты удалены, грант отозван. Runner исправлен и проверен без БД/ML; рост0→5→10 и resume остаются непроверенными. Автоматического повтора нет.


[Повтор двух последовательных партий](sequential-batches-repeat-proposal.md): PREPARED/PENDING_OWNER_APPROVAL, Afc15b466/B6ca13101, те же10фото/модели/лимиты/81codefiles. Общий socket проверен без ML, SQL tuple и ранние ошибки проверены; metadata2/refusals6PASS. DB/grants/START не создавались; exact двухпакетный допуск требуется отдельно.


[Повторная серия A/B](sequential-batches-repeat-report.md): EXECUTED/STOPPED_RESOURCE_STOP49,448с. Afc15b466 одинSTART/2localizationattempts/1SQLcheckpoint,0vectors/publications/active; B6ca13101 не запускалась.110guard:103OK5WARNING2STOP; exactSTOPcauseUNKNOWN, last_sample не доказывает состояние в момент сбоя.16operationevents/incompletefalse,17monitorframes→ERROR. Own cleanupPASS/Agrantconsumed; нет автоматического повтора/resume/увеличения лимитов. Рост0→5→10 не проверен.


[Диагностика resource STOP](resource-stop-diagnosis.md): первый STOP серии вызван mandatory observation failure; конкретная проверка UNKNOWN. Добавлены safe reason/check/error_type/sample_current в существующий private журнал, первая причина сохраняется. TDD5RED→GREEN/119testsPASS; лимиты/STOP-policy прежние. НовогоML/DB нет; runtime-код изменён, прежние frozen пакеты требуют замены перед отдельным допуском.


[Подготовка прогона с диагностикой STOP](resource-stop-diagnostic-proposal.md): PREPARED/PENDING_OWNER_APPROVAL A10882adb/B07a55b22, те же10inputs/models/limits/81files, изменён только diagnostic adapter. Code/input/DTO/permissionsPASS,metadata2/refusals6code5PASS; новыйML/DB/grants отсутствуют. Exact двухпакетный допуск нужен отдельно.


[Серия с новой диагностикой](resource-stop-diagnostic-report.md): A10882adb/B07a55b22 EXECUTED/OK175,831с,0→5→10READY/active,40SQLCP/59regions177vectors10pub. Первая партия members/SQLCP/vectorSHA/fileSHA сохранена после второй.395guardallOKpressure1/diagnosticcurrentOK; прошлыйSTOP не воспроизвёлся, exactcauseUNKNOWN. По30monitorframes/COMPLETED,125events/log each/incompletefalse; independent owncleanupPASS/2grantsconsumed. Нет thirdbatch/resume/workingcutover/limitincrease;DBудалена.


Владелец2026-10-15 прямо разрешил [пакетную кампанию](batch-verification-plan.md) без промежуточного подтверждения каждого изолированного запуска. Freshfreeze/SHA/limits остаются обязательными; exact выбранные пакеты покрыты общим допуском этой кампании. [Итог](batch-verification-report.md):501testsPASS, realRESUME послеADMISSION_LIMIT без повторенияI/4CP30vectors1pub; товар7фото обработан5+2/20→28CP/0→1pub. Первая runner-попытка отказала доRESUME, diagnosticconfirmation прошла/причинапервогоотказаUNKNOWN. Owncleanup3контуров/5consumedgrantsPASS;нетworkingcutover/limitincrease/commit.
