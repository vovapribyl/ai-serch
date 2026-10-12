# G4 rework — фактическое исполнение

2026-10-08. Итог: **T044 PASS; native SAM PASS; T048 RESOURCE REWORK**.
Owner утвердил исходный [rework bill](runtime-rework-bill.md) ответом «Разрешаю»,
затем [cached-wheel дополнение](runtime-rework-cached-wheels-bill.md) ответами «Lf»/«Да, разрешаю».

## Первая попытка — сохранённый stop до installation

| Этап | Наблюдение | Итог |
|---|---|---|
| Четыре exact wheel downloads | Только Torch2.13.0, torchvision0.28.0, protobuf5.28.3, sentencepiece0.2.0; суммарно114665405bytes; все SHA/bytes совпали | PASS |
| Новый private root | Новый каталог mode0700, wheelhouse и fresh venv Python3.12.14; не clone | PASS |
| Approved lock offline/no-build sync | antlr4-python3-runtime4.9.3: no usable wheels; source builds выключены | STOP |
| Actual installed distributions | 0, проверено metadata после failed sync | VERIFIED |
| Model load/calls/HTTP lifecycle | Не начаты | NOT_RUN |

Два previously cached built wheels antlr4/iopath имеют SHA, отличные от sdist hashes
approved lock. Дополнительные hashes и локальные find-links подготовлены в
[точном дополнении](runtime-rework-cached-wheels-bill.md). Diagnostic dry-run resolves89
packages; он не доказывает installation и не закрывает STOP.

Service lock, I/backend controls, unratified clone, corpus/working DB/J и Git history
не изменены. Скачанные четыре wheels и пустой env сохраняются private для продолжения;
повторное скачивание не требуется. Initial Candidate I REWORK по Torch2.4.1 остаётся
актуальным, новый model outcome пока UNKNOWN.

Дополнение прошло independent review PASS0/0/0. Исполнитель read-only сверил cached
payload с control: 59 antlr4 +14 iopath files совпали; одно antlr4 script body совпало
после исключения relocated shebang. Утверждение новых artifact hashes ещё требуется.

## Продолжение после approval дополнения

`uv` сначала выбрал registry URL вместо local Torch wheel и отказал offline.
Все artifacts присутствовали. Четыре уже SHA-verified wheels materialized в новый env
через exact local paths (`--offline --no-build --no-deps`), затем полный lock sync
установил оставшиеся85 packages без build/network. Это двухшаговая materialization
тех же утверждённых artifacts, без version/hash изменений и без env clone.

| Проверка | Фактический результат |
|---|---|
| Installed inventory | 89 distributions; SHA `42db16a29cc52385b230f5252b2adb3ce67ca64bcd1d9648f1a4cca9510d2a42` |
| Python | 3.12.14, новый отдельный prefix |
| Service lock | Approved cached-wheel lock SHA `013ba67fcd8688b2b4ec4ecd86bb802e8a3ac3b8b2d9bc016af984c178f5e93b`, скопирован после actual verification |
| VCS | lang-sam `918043ed4666eea04da88aa179eb8d27ef4b1a1d`, sam-2 `c2ec8e14a185632b0a5d8b161928ceb50197eddc`; direct_url совпали |
| Weights | Оба exact SHA/bytes из G4 повторно совпали |
| Frozen config | `dae475fa384688e813fa0abd782df5b893968a6b6276f95e3177bbf083e5e61e`: новый lock/версии; MPS/float32/no-fallback и существующий ROI profile |
| Actual bootstrap | 26 pinned files + actual metadata observers, settings/config/model paths; 0,478с; Torch не импортирован |
| Actual I probe fingerprint | `21696870563b8409de06c1fb1098daffc1dae9fb02aad37bc139f997e53cff32`; не final accepted runtime reference |

## Исправления binding и bootstrap

- Frozen ROI/large-box profile ранее игнорировался; regression `OK→NO_NAILS` RED→GREEN,
  существующий TwoPassRoiLocalizer переиспользован без изменения параметров.
- Frozen Torch seed/deterministic/default float32 применяются lazy initializer один
  раз перед load; отдельный RED→GREEN доказывает порядок и отсутствие eager import.
- Три bootstrap RED→GREEN: calculated fingerprint, изменённый config до ML и подмена
  model path. Required source paths, config/lock, full GDINO snapshot и SAM checkpoint
  связаны с одним immutable manifest. Actual metadata/VCS подтверждены новым env.

## Разрешённая model series

| Этап | Наблюдение | Итог |
|---|---|---|
| MPS bicubic tensor | finite float32, shape1×1×8×8, actual device MPS, no fallback | PASS |
| Первый standalone SAM | source-frame shape256×256 и MPS/float32 получены; неверный harness assert ожидал bool dtype | HARNESS_ERROR |
| Исправленный standalone SAM | exact upstream `.float().cpu().numpy()` подтверждает float32 binary output; finite/nonempty0/1 mask256×256 и finite scores | PASS |
| Real cold HTTP | client вернул validated LocalizationResult; выполнение дошло до admission следующего warm call | PARTIAL: exact status/count/latency summary не сохранился |
| Следующий warm admission | resource sampler сообщил RESOURCE_CEILING; native call не начался | STOP |
| Два warm calls / providers / crop→providers | После resource failure не запускались | NOT_RUN |

Всего3 model-backed calls:2 standalone SAM (включая ошибочный dtype assert) и1 HTTP.
Первый standalone командный run17,07с/maxRSS849625088/peakFootprint2082719424 bytes;
исправленный5,81с/maxRSS849297408/peakFootprint2105919192 bytes. Оба process swaps0.
HTTP driver командный run27,56с; `/usr/bin/time` maxRSS1385283584 bytes. Эта величина
не доказывает отдельные sampled peaks двух процессов; они потеряны в failed harness.
Exact end timestamp/полная wall duration series также не сохранены; admission проверял
20-minute limit, но final wall acceptance остаётся NOT_VERIFIED.

## Ресурсный результат и teardown

System Swapouts66152→81784, delta15632 pages при page size16384 bytes (244,25MiB).
Требование delta0 нарушено. Это whole-host наблюдение; оно не доказывает причинный
вклад только I. Resource sampler зафиксировал12 RESOURCE_CEILING events; exact
pressure levels и per-process/combined sampled peaks старого run — UNKNOWN.
До/после series raw pressure level1; transient peak из потерянного массива не восстановлен.

Owned I server завершён; отдельная последующая проверка процесса не нашла, а device
и coordinator leases повторно приобретены/освобождены. Это external teardown evidence,
не утверждение, что post-finally assertions failed harness были выполнены.

Harness теперь печатает aggregate summary в finally, даже при failure. Model-free
bad-manifest probe подтвердил process_exited=true/model_calls0/failure summary;
models не загружались. Дополнительно swapout delta включён в admission resource guard
по RED→GREEN; будущий runner требует explicit initial call counter и swapout baseline.
Исправления harness не восстанавливают historical telemetry и не являются новым ML run.

## Следующая граница

Unsupported native MPS operator устранён; T044 installation и standalone SAM
подтверждены. T048 остаётся **REWORK** из-за выбранного resource profile. Следующий
model run требует нового bounded разрешения после оценки доступного Mac memory
headroom; новые packages для этого не требуются. Целесообразен сначала один
instrumented cold request с новым failure summary и baseline, не повтор всего suite.
Изменение ceilings, dtype/fallback или остановка сторонних процессов не выполнялись.
T049/G5/corpus/build/activation/Git publication не разрешены этим результатом.

Final code verification после всех fixes:270 PASS/46 SKIP, known Starlette warning,
Ruff/diff PASS. Independent combined review PASS0 Critical/0 Major/0 Minor; reviewer
47 scoped PASS/5 opt-in SKIP, затем1 new pure resource guard PASS. Install/models/
private telemetry reviewer самостоятельно не запускал; resource acceptance REWORK.

Готов [конкретный single-cold profiling plan](resource-profiling-plan.md). `--cold-only`
проверен на CLI/help/lint; actual model branch NOT_RUN. Новых model calls после
resource STOP не было; отдельное разрешение требуется для нового окна.

После отдельного owner permission выполнен [single-cold profiling](resource-profiling-report.md):
OK/6 regions/12,032с; total14,52с, один admitted call. Sampled I1395130368/combined1432010752
bytes, swapouts delta0; pressure raw2 в7 of29 samples нарушает strict no-warning condition.
Resource REWORK сохраняется, warm/providers не запускались. Это новое разрешённое окно,
не продление исходной series и не отмена старого swapout failure.
