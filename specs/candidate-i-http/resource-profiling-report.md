# T048 — результат single-cold profiling

2026-10-08. **FUNCTIONAL PASS / RESOURCE REWORK**.
Основание: отдельное «Разрешаю» на [план](resource-profiling-plan.md).

## Проверенные результаты

| Поле | Наблюдение |
|---|---|
| Scope | Один admitted generated256×256 cold HTTP request; warm/providers/model installs NOT_RUN |
| Identity | Тот же I env89/lock013ba67f.../probe fingerprint21696870...; actual baseline manifest/inventory/leases проверены без Torch import |
| HTTP result | `OK`, 6 regions; клиент проверил approved wire/identity/full-frame binary masks |
| Cold duration | 12,032с, включая client/readiness/HTTP/inference; не inference-only latency |
| Total window | 14,52с, ровно1 model-backed call |
| Shared device guard | Parent-owned device lock → BUSY до ML; PASS |
| Concurrent admission | Второй запрос при actual work → BUSY; PASS, дополнительная inference не началась |
| I sampled peak RSS | 1395130368 bytes ≈1,30GiB, ниже6GiB |
| Controller sampled peak RSS | 46055424 bytes ≈43,92MiB; model-free, не loaded backend providers |
| Combined sampled peak RSS | 1432010752 bytes ≈1,33GiB, ниже10GiB; не сумма независимых peaks |
| Samples | 29, период≈0,5с; не continuous maximum guarantee |
| System pressure | Raw levels1/2;7 RESOURCE_CEILING observations; levels4 не наблюдались |
| Swapouts | Fresh baseline81784, после teardown81784, delta0 |
| Teardown | Owned I child exited; external device/coordinator reacquire PASS; pressure после teardown1 |

Ресурсный stop вызван pressure, не sampled RSS или swapouts: в этом run все RSS
ceilings и delta0 соблюдены. Системный сигнал не приписывается исключительно I.
GPU/Metal driver allocations и footprint всех приложений не измерены; память MPS
нельзя считать исчерпывающе описанной этими process RSS observations.

## Значение raw pressure

Не смешивать private kernel enum с sysctl result.
[Apple XNU sysctl handler](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus_notify.c)
возвращает dispatch flags через `convert_internal_pressure_level_to_dispatch_level`.
[Flags](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/event_private.h):
normal1, warning2, critical4; internal warning/urgent отображаются в warning.
Это source-grounded интерпретация raw2, а не измерение цвета UI Activity Monitor.

## Ограничения и UNKNOWN

- Full timestamped pressure/swap/RSS timeline не сохранён: текущий summary содержит
  aggregates/unique levels/count. Длительность и порядок warning samples UNKNOWN;
  нельзя умножать7 на0,5 и заявлять точную warning duration.
- Warning-only cold run не подтверждает warm/crop→providers residency или real quality.
- Предыдущий failed run с delta15632 и потерянными peaks остаётся отдельным evidence;
  новый delta0 не отменяет прошлый результат.
- G4 final runtime reference/owner acceptance и T049/G5 не закрыты.

## Минимальный следующий шаг

Замена ML packages/моделей или dtype по этим данным не обоснована: native I выполнил
операцию, его sampled RSS далеко от собственного ceiling. RSS-only sampling также
не доказывает отсутствие MPS/whole-host memory pressure причины.

Рекомендация: сохранить strict profile и сначала собрать read-only baseline
whole-host footprint вместе с доступными Metal/MPS allocator metrics в контролируемой
diagnostic instrumentation; для следующего model call требуется новое bounded
разрешение. Только после локализации пика выбирать конкретную оптимизацию load/cache.
Нельзя молча разрешать warning, отключать guard, менять dtype/fallback или завершать
чужие процессы. Вариант пересмотра whole-host warning policy — решение владельца,
а не исправление кода по одному успешному примеру.

Raw logs и previous server.log backup сохранены private вне Git. Маски/изображения/
vectors/corpus/working DB/J не публиковались и не использовались.

Самопроверка saved outcome/links/markers/diff PASS. Independent read-only review
report/statuses/source interpretation — PASS0 Critical/0 Major/0 Minor; reviewer
private telemetry/model/tests/install не повторял. Code unchanged, новый unit suite
не запускался; предыдущий scoped270 PASS/46 SKIP остаётся отдельной проверкой кода.
