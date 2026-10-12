# T051 — подготовленный actual native execution package

2026-10-11. Исторический674package. **SUPERSEDED_FOR_FIRST_TEST**: owner выбрал
[фиксированный100набор и новыйjob](corpus-100-report.md); граница ML execution остаётся закрытой.
Исходный результат674PREPARATION_PASS сохранён ниже.
Основание: «Приступай» на подготовку команды и параметров реальной сборки, после
[approved674 inputs](oversize-input-report.md). Это разрешение подготовки, не ML run.
FULL контракт: [план](native-execution-plan.md); один read-only reviewer, inline/TDD.
T051 `[ ]`. Модели, representation, vectors/READY/pointer не создавались.

## Конкретный пакет

- Job SHA: `917413320f2ccfe2a837cd39c26eafb95973729e97d5f7d6fbea2d5fa5198d2b`.
- Canonical BuildPhoto inventory SHA: `d9e427e45bc1385754bb0256d04d38da305251b925bc1b01f7644eb8a8c2e437`.
- Representation fingerprint: `110e2f720b3ce5d6c0af733d0b882f25060cd027c39a1f850346f711abf9dd14`.
- Source/job/command archive SHA: `54a1beccb9ea4e7b1c24466bbd7f4d6fc78c9ea8125e340a8ced14b06d2f57d4`.

Frozen private job содержит82code file refs, exact backend/I interpreters, accepted
assembly SHA70e0b2ad... и runtime6cccc473...,3model manifests/revisions/dimensions,
owned target descriptor, frozen input profile4a0b2bd9.../lineage11b4f5ee.../inventory
082e456f.../source names. File inventory hash и canonical BuildPhoto hash различны
по назначению. Новая representation ID только private; в БД ещё нет её строки.
Full private paths/credentials/IDs/job JSON, фото/веса/векторы не публикуются.

[Команда](../../../../../.codex/worktrees/candidate-i-http/Ai/scripts/run_nail_native_build.py):
actual argv/cwd/offline environment зафиксированы private в command.json. `--check`
проверяет job/code/metadata, target/parents/schema, backend inventory,3actual cache
manifests, actual I metadata readiness и674product decode; firewall запрещает POST.
`--execute` дополнительно требует отдельно pinned approved permit/jobSHA/expiry.
Пересборка job меняет hash и требует нового execution решения; незаметная замена
inputs/code/target/runtime/model hashes ведёт к STOP.

## Предлагаемый допуск одного ML run

Следующие bounds фиксированы в job как PROPOSED_FOR_OWNER_EXECUTION. До явного ответа
владельца approved permit не создаётся. При согласовании expiry задать перед стартом
на одно шестичасовое окно; неизрасходованный бюджет не разрешает второй запуск.

| Граница | Значение |
|---|---|
| Scope |Один build674primary inputs,673byte-identical+1approved1536copy; no retry/resume/restart |
| Admissions |≤20897:674I POST+3provider loads+20220single-crop encodes (674×10×3) |
| Длительность |≤21600seconds/6h от owned execution group start; фактическая длительность не предсказана |
| Последовательность |Одно фото/in-flight I,3providers последовательно; shared device/coordinator leases |
| Выходы |Одна BUILDING,≤6740regions/≤20220vectors512/768/768; ошибки/пустой индекс не READY |
| Storage STOP |Observed owned DB+artifacts≥32GiB либо host/VM free<16GiB; sampled threshold, не quota |
| RSS/наблюдения |I6/backend5/combined10GiB; warning/swap diagnostic,critical/unknown/error/stale>5s STOP |
| HTTP |connect1/write30/read300/overall330s; outer guardian независим от worker/observer |
| Existing limits |source20MiB,2359296pixels,10regions,40MiBresponse,16384solver; target memory1GiB/CPU2, VM не расширять |
| Закрытая граница |No publish/READY/active pointer/Web/query; working DB и source Gate2 не подключаются |

Claim связан с job/run root/controllerPID, потребляется один раз до worker execution.
Каждый I/load/encode admission проверяет permit SHA/jobSHA/expiry/resource freshness;
reserved counter записывается до вызова модели. External guardian завершает только
owned process group; partial DB outcomes/artifacts/входы сохраняются. После STOP
unobserved worker result/teardown остаютсяUNKNOWN; controller проверяет actual target
counts и reacquires leases. One-shot attempt считается потраченным даже при отказе
перед созданием representation; автоматического возобновления нет.

## Actual model-free evidence

| Проверка | Фактический результат финальной code identity |
|---|---|
| `--check` |exit0,8.654s,42resource/storage samples; no observer/wall/resource STOP |
| Native paths |Actual separate backend/I interpreters, loopback inherited FD, I bootstrap/health ready; metadata-only POST403 |
| SDK/admissions |Torch/Transformers не импортированы обоими процессами; reserved0 |
| Inputs/target |674hash/boundeddecode, frozen profileunchanged; owned Docker/SQL/parent/schema prechecks PASS |
| DB |representationNOT_CREATED,photos0,regions0,vectors0,pointers0; read-only checks, no mutations |
| Teardown |Only owned I terminated (-15), backend exit0; external group cleanup; device/coordinator reacquired |
| Reject execution |Без permit exit3, execution.claim отсутствует; нет SDK/representation |
| Observed resources |pressure1; Ipeak76677120bytes/backendpeak174538752bytes; эти значения metadata-only, не ML peak |
| Observed storage |DB+artifactsmax9165847bytes; minhost88582520832bytes/minVM28891734016bytes; не гарантия free space на старте ML |

Прежниеjobs/logs сохранены. Один промежуточный check(jobcd7ff33b...) завершился
BuildStop без ML/DBwrites; точная причинаUNKNOWN, ранний лог содержал только class.
Safe stage/reason добавлены. Отдельная controlled regression воспроизвела atomic
observation replacement→openFDnlink0: ранее falseSTOP. Opt-in reading immutable
opened observation snapshot допускает nlink0/1; steady job/permit readers остаются
strict1, hardlink>1/symlink/owner600/size/freshness/STOP не ослаблены. Связь этой гонки
с конкретным промежуточным STOP — гипотеза, не установленный postmortem. Финальный
после исправления check PASS; старый failure не удалён и не выдан за PASS.

## Изменение → код → проверка

[Job gates](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_native_job.py):
pinned immutable files/runtime/target, expiry/one-shot claim, I firewall, observations.
Existing [native bindings](native-bindings-report.md) переиспользованы; core/schema/
accepted I assembly/config/models/environment не менялись. Existing supervisor/watchdog
переиспользованы; trace дополнен4storage fields, atomic snapshot opt-in только observation.
[Test](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_native_job.py):17new checks,
15observed behaviourRED→GREEN и2alias characterization;58targetedPASS.
Final34safe suites362PASS/46SKIP/2dependencywarnings (Starlette/httpx,anyio alias).
Full project/actualSDK/native inference suites не запускались; opt-ins закрыты.
Ruff4touchedfiles, links/markers/status/diff checks PASS. Private700/600 source archive
сверен с82file refs, не содержит source photos/weights/vectors.

Independent initial review0Critical/1Major/0Minor: cached encode не проверял expiry.
Исправление budget admission +expiry regression, mandatory re-reviewPASS0C/0Major/0Minor;
final trace/atomic changes такжеPASS, independently58safe tests. Reviewer private/
source/SDK/Docker/DB не использовал. Final doc review0C/0Major/1Minor: T051 legacyCLI заменён actual frozen nativeentry. Исправлено; ссылки/status/diff самопроверкаPASS. Повторное review после Minor не требовалось.

## Следующее действие владельца

Явно разрешить один realMLbuild по этому jobSHA/674inputs/20897admissions/6h и указанным
STOP/no-publish boundaries. После ответа — создать private approved permit с expiry,
повторить актуальные preflight checks и выполнить один supervised `--execute`.
Результат actual build/coverage/T052 и ручные queries/T053–T054 ещё не получены.
