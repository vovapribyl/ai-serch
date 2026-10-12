# T048 — MPS allocator и whole-host footprint

2026-10-08. **FUNCTIONAL PASS / RESOURCE REWORK**.

Основание: «РАзрешаю» после предложения измерить MPS/whole-host footprint.
Исполнение: instrumentation model-free RED→GREEN, затем один cold-only generated
request в новом окне максимум20минут. Warm/providers/install/corpus/DB/J не разрешены.
Limits/device/dtype/fallback и модельные artifacts сохраняются; при failure STOP.

Три instrumentation tests RED→GREEN: отсутствие Torch import до ML, раздельные
active/driver/recommended counters, explicit unavailable при partial import.
Instrumented model-free bootstrap/leases PASS. Diagnostic launcher/helper включены
в manifest: fingerprint `7bbb0936169d40b13822c5dcf5e039fa6a7874b52bb40e2a2348c5d3923fd21a`.
Production I binding/SDK/model/profile semantics не менялись.

Сбор: parent host timeline≈0,5с; I process MPS timeline≈0,25с; один read-only
`vmmap -summary` только для owned I PID при warning, timeout3с. VMMap failure обозначать
UNKNOWN; не считать optional diagnostic observation failure model compatibility error.
Все raw traces остаются private; в Git только безопасные aggregates/выводы.

## Фактический результат

Один admitted call в новом15,02-second window. HTTP `OK`,6 regions, cold12,298с.
Shared device/concurrent admission BUSY checks PASS; warm/providers не запускались.
Fresh Swapouts81784; final99608, delta17824pages16KiB (278,5MiB). Pressure1/2,
6 warning observations of27. RSS sampled peaks: I1000144896/controller41238528/
combined1038204928 bytes; ниже всех ceilings. Resource stop обязателен по warning и swap.
Owned I process exited; external device/coordinator reacquire PASS, final pressure1.

## MPS/physical footprint

| Наблюдение | Bytes / результат |
|---|---|
| MPS observations | 51:13 not_imported,3 unavailable во время partial import,35 ok |
| Peak active tensor allocation | 1523052800 bytes ≈1,418GiB |
| Peak Metal driver allocation | 2848309248 bytes ≈2,653GiB |
| Active at driver peak | 1245286144 bytes ≈1,160GiB |
| Driver-minus-active at that sample | 1603023104 bytes ≈1,493GiB; не объявляется полностью освобождаемым cache |
| Recommended working-set size | 12713115648 bytes ≈11,840GiB; device recommendation, не свободная память |
| vmmap при первом warning | exit0; physical footprint2,4G, peak-to-that-snapshot2,4G; IOAccelerator(graphics)1,5G |

Exact installed Torch2.13 MPS API docstrings подтверждают: active counter исключает
unused allocator cache; driver counter включает cache и MPS/MPSGraph allocations.
CPU RSS и Metal counters нельзя складывать как гарантированно независимые allocations.
vmmap snapshot при warning — не measurement whole-run physical-footprint maximum.

Timestamped traces теперь сохранены: первый sampled warning примерно10,967с отstart,
последний14,880с. Вблизи первого warning driver≈1,478GiB, active≈0,973GiB; максимум
driver пришёл около14,796с. Это временная корреляция, не доказательство одной причины
и не гарантированная continuous warning duration; vmmap сделал sampling interval нерегулярным.

## Whole-host context

В first host sample до load: free4983pages≈77,86MiB, inactive258805pages≈3,949GiB,
compressor333552pages≈5,090GiB, wired156352pages≈2,386GiB. В late warning sample:
compressor397905pages≈6,071GiB, wired314602pages≈4,800GiB; swap delta17824.
Inactive/compressed не трактуются как гарантированно доступный I headroom.

Read-only app-group RSS после teardown: Chrome25 processes3045081088bytes≈2,836GiB;
Telegram1 process532086784bytes≈0,496GiB; Codex33 processes1942208512bytes≈1,809GiB.
Это сумма RSS с возможным shared-page overlap, не physical footprint и не гарантированно
освобождаемая память. Process arguments/content не читались. Whole-host `footprint`
summary требует root и не получен; sudo/root privilege не запрашивались.

## Вывод и конкретный минимальный шаг

Наблюдения не показывают исчерпания MPS recommended working set или собственного RSS
ceiling I. Они согласуются с недостаточным whole-host headroom на уже нагруженном Mac;
это рабочая гипотеза, не sole-I/sole-Chrome causality proof.

Минимальный предложенный operational fix: владелец сохраняет свою работу и вручную
закрывает ненужные Chrome tabs/windows и, если не нужен, Telegram; Codex/VM/рабочая DB
не останавливаются ассистентом. После этого read-only baseline и отдельно разрешённый
один cold check покажут, исчезает ли warning без изменения модели/precision/profile.
Это проверка гипотезы освобождения фоновой RAM, а не обещание конкретного числа GiB.

ML-code cache purge/processor resize/quantization сейчас не внедряются: sampled
driver-minus-active включает framework allocations и не даёт основания выбрать
такие изменения без отдельной проверки. Strict profile сохранён, T048/T049/G5 открыты.
Новая package installation не требуется.

## Review и исправление диагностического контроллера

Первое independent read-only review: REWORK, 0 Critical / 1 Major / 0 Minor.
Major: создание trace внутри daemon могло оставить controller без resource sampling.
Исправлено test-only: host trace создаётся синхронно до socket/child launch;
admission требует первого успешного resource sample, живого sampler и отсутствия
violations. RESOURCE_CEILING фиксируется до optional VMMap; его exception остаётся
diagnostic UNKNOWN (`vmmap_error_type`), не меняет resource classification.
Child MPS trace создаётся до uvicorn serving; collision блокирует startup.

Два новых regression RED→GREEN (trace collision до Popen и first-sample/live/violation
admission). Safe scoped suite: 275 PASS / 46 SKIP; Ruff PASS; code diff check PASS.
Это не полный suite и не новый runtime acceptance. Реальные модели не повторялись.

Actual measured identity остаётся `7bbb0936169d40b13822c5dcf5e039fa6a7874b52bb40e2a2348c5d3923fd21a`.
После review refresh private manifest дал
`4fb204cc11c81a01d002a53406a1d9090602558041f61bef647a496ad65355e6`:
actual env model-free bootstrap PASS, Torch не импортирован. На этой новой identity
model run NOT_RUN; сохранённые traces относятся только к actual measured identity.
Fixed-name trace collisions теперь fail closed: перед следующим разрешённым запуском
нужен отдельный evidence-preserving выбор новых trace filenames/архивирования;
старые traces не удалять и не перезаписывать.

Повторное independent read-only review: PASS, 0 Critical / 0 Major / 0 Minor;
Major устранён. Reviewer: 6 safe tests PASS, Ruff/diff PASS, native/ML/install не
выполнялись. T048 resource acceptance остаётся REWORK; T049/G5 открыты.
