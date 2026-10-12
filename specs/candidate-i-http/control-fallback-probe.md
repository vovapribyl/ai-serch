# Candidate I — один diagnostic cold check старого runtime

2026-10-08. APPROVED_BY_OWNER: «Разрешаю, проведи» после
[read-only сравнения](experiment-http-runtime-comparison.md).

## План и границы

STANDARD: только диагностическое evidence, без принятия нового production profile.
Один admitted generated256×256 cold HTTP request; максимум20минут в свежем окне.
Existing control env Python3.12.14/Torch2.4.1/vision0.19.1, explicit CPU operator
fallback=1 перед child import. Те же веса, SDK revisions, prompt/thresholds/ROI;
не добавлять seed/deterministic initializer, которого не было в old CLI.
Функциональный результат source-frame DTO валидируется существующим HTTP wire.
Production binding/bootstrap и no-fallback profile не обходятся и не меняются:
отдельная test-only control assembly/fingerprint/launcher.

До ML: exact installed inventory/VCS/file manifest/config identity, actual leases,
normal memory pressure и свежий swap baseline; любое нарушение блокирует admission.
Мониторинг как в [MPS profiling](mps-footprint-report.md): host≈0.5с, MPS≈0.25с,
один optional vmmap owned child PID при warning. RSS/pressure/swap ceilings прежние.
Нет warm/provider/model repeats; первая failure → STOP, only owned child teardown,
external device/coordinator reacquire, безопасный aggregate report. Raw logs private,
unique label `control-fallback-20261008`, existing traces не overwrite.
Device/coordinator root сохраняется общим с I, чтобы не создать независимый lock domain.
Corpus/DB/J/install/download/other-process kills/commit/merge/push запрещены.

## Identity ruling до исполнения

Saved historical config168e5ddd... ссылается на historical lock61a8965d...,
но actual control lock теперьff813642... (это уже отражено исходным G4 bill).
Actual installed control89 соответствует текущему control lock; installation не
повторяется. Historical config не редактируется. Отдельный diagnostic config
меняет только dependency-lock fingerprint и собственный config fingerprint;
все остальные поля должны быть равны historical config, что проверяет launcher.
Полученная identity не выдаётся за exact reproduction historical run.

Test-only HTTP layer и controller отличаются от old CLI; old/current bundles
также не выполняются одновременно при одинаковом состоянии Mac. Поэтому outcome
покажет работоспособность и resource behavior control bundle сейчас, но не изолирует
причинный вклад только fallback/Torch. Фактический result пока NOT_RUN.

## Preflight implementation

Test-only bridge/guards5semantic RED→GREEN. Initial reviewer REWORK0C/1Major/0Minor:
readiness не должна читать caller-owned mutable expectations под прежним fingerprint.
Исправлено canonical snapshot manifest и copy files; actual assembly/health regression
200→503 после input mutation прошёл RED→GREEN. Scoped suite281PASS/46SKIP,
Ruff/diffPASS, known Starlette deprecation warning. Full suite не подтверждён.
Actual old env model-free bootstrapPASS/no Torch; control identity31files/89packages:
`3d17bcc51700cacd15ab077a3a2b835884eafe47e0a4d31777ba29d5e241392c`.
Production no-fallback manifest станет stale из-за test-only launcher source change;
после diagnostic refresh отдельно, без приписывания ему model evidence.

## Фактический cold result

Repeat preflight review PASS0C/0Major/0Minor; Major устранён до ML. Fresh start
1791483837.79232, raw pressure1, Swapouts99608. Shared external leases и новые trace
paths PASS. Один admitted request, без warm/providers/repeat. Identity3d17bcc5... выше.

| Наблюдение | Результат |
|---|---|
| Cold HTTP | OK,7 regions,13.363с |
| Whole window / controller |17.02с внутри controller; wrapper17.10с; exit1 по resource guard, не localization failure |
| Shared device / concurrent guards | BUSY checks PASS |
| Sampled RSS I/controller/combined |827981824 /46219264 /858144768 bytes; max combined sample не обязан равняться сумме отдельных peaks |
| Host pressure31 samples | normal1:21; warning2:9; critical4:1 |
| Whole-host swapouts |99608→203568, delta103960pages16KiB =1703280640bytes≈1.586GiB |
| First warning / critical |≈11.046с /16.493с отfreshstart; sampled points, не continuous duration |
| VMMap owned child |exit0; physical footprint2.2G и peak-to-snapshot2.2G; graphics17.4M resident; не whole-run peak |
| MPS telemetry |51samples:15not_imported/36unavailable AttributeError; active/driver/recommended peaks UNKNOWN |
| Teardown |owned child exited, external device/coordinator reacquirePASS, pgrep отсутствует, finalpressure1 |

CPU fallback не только enabled: private server warning прямо зафиксировал переход
`aten::upsample_bicubic2d.out` на CPU в Torch2.4.1. Также сохранён SDK warning о
non-writable NumPy array; read-only comparison не выдаёт его за доказанную memory cause.

MPS limitation: installed Torch2.4.1 имеет current/driver allocation APIs, но не
recommended_max_memory. Existing optional sampler собирает поля в одном try, поэтому
AttributeError не сохранил и первые два counters. Host monitoring/stop не зависели
от этого API и работали. Уже выполненный запрос не повторялся ради заполнения UNKNOWN;
перед любым будущим comparative run optional collector должен учитывать API capability.
Raw artifacts private: control-fallback-probe-20261008.log, server-control-fallback-20261008.log,
host-footprint-control-fallback-20261008.jsonl, mps-allocator-control-fallback-20261008.jsonl,
i-vmmap-warning-control-fallback-20261008.txt. Existing evidence не перезаписано.

## Сопоставление и ruling

| Показатель | Earlier newTorch/no-fallback | Current oldTorch/fallback |
|---|---|---|
| HTTP |OK/6regions/12.298с |OK/7regions/13.363с |
| I sampled RSS peak |1000144896bytes |827981824bytes |
| Pressure |1/2 |1/2/4 |
| Swapout delta |17824pages |103960pages |
| Resource profile acceptance |REWORK |REWORK |

В обоих bundles localization технически работает. В старом control bundle RSS ниже,
но strict resource outcome тоже REWORK. Это не доказательство большей/меньшей общей
памяти или того, что fallback ухудшает её: разные моменты запуска/host state, разные
initializer semantics, недоступные old Metal counters, несинхронный VMMap snapshot.
Регрессия относительно исторического30SUCCESS run по-прежнему UNKNOWN.

Возврат fallback сам по себе не подтверждён как устранение текущего resource stop.
Однако его functional работоспособность подтверждена, и старый успех не опровергнут:
SUCCESS и strict zero-swap/no-warning acceptance — разные критерии. Не следует
приписывать whole-host swap исключительно I или ставить закрытие Chrome/Telegram
условием сервиса. Новый model call не требуется автоматически из этого результата.
Перед изменением runtime/acceptance policy нужен отдельный owner выбор; T048/T049/G5
этим diagnostic не закрыты. One-call permission consumed, дальнейшая inference STOP.

После teardown private production no-fallback manifest refreshed только по shared
test launcher hash: current identity
`aa97bba712df1d86281facf8604f4dbac581b3bab6a925416f629ad566c50685`, model-free actual
bootstrap PASS/no Torch, model NOT_RUN. Diagnostic measured3d17bcc5... не подменён
этой identity. Saved newTorch measurement7bbb... остаётся историческим evidence.

Final independent read-only report review PASS0C/0Major/0Minor. Saved outcome/onecall/
teardown/resource assertions и4relative links PASS; markers/whitespace/diff PASS.
Reviewer не повторял tests/ML/install/private telemetry. Optional counter capability
limitation оставлена явным UNKNOWN, не поводом продлевать разрешение.
