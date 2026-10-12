# G4 — критерии пригодности полного synthetic-сценария

2026-10-08. Resource policy `scenario_suitability_v1`: **APPROVED_BY_OWNER** по «Да»
на точное предложение считать warning/swap диагностикой, сохранить critical/RSS/error/
timeout STOP. Written consolidation review PASS0/0/0; новый ML run этим не разрешён.

## План-контракт

FULL: записать уже выбранную owner policy → TDD test-only guards/полный probe →
самопроверка → один independent read-only reviewer → предъявление exact run bill.
Production API/core/SDK/cache behavior не меняются. Это критерии технической пригодности,
не утверждение качества поиска, G4 PASS или permission для corpus/build/activation.

| Наблюдение | Новая policy |
|---|---|
| Raw pressure1 | normal, допускается |
| Raw pressure2 | warning, сохранять в отчёте; не automatic REWORK |
| Положительный swapouts delta | сохранять whole-host показатель; не automatic REWORK |
| Raw pressure4 | critical, STOP |
| Неизвестный pressure/failed mandatory observation | STOP, не объявлять среду безопасной |
| I/backend/combined RSS выше6/5/10GiB | STOP; существующие ceilings не увеличиваются |
| Ошибка/timeout/invalid vectors/неполный результат | STOP, без retries и подмены входов |

CPU RSS и Metal allocations не складываются как независимая физическая память.
Pressure/swap — whole-host, не sole-I causality. Positive swap не доказывает memory leak.
Отрицательная delta после fresh baseline означает несопоставимые counters и STOP.
Optional Metal API недоступен — UNKNOWN/partial, не подмена обязательных host observations.

## Что сохраняется

Конечные byte/pixel/region/solver/manifest caps и I HTTP deadlines из
[G4 bill](runtime-bill.md) не ослабляются. Текущий installed
I Torch2.13.0/vision0.28.0, MPS/float32/no-fallback, веса/config/ROI сохраняются.
Новое правило не разрешает fallback, новые packages/weights, VM/working DB/J/data.
Первый сценарий — на Mac после ручного закрытия приложений владельцем. Это evidence
менее нагруженного режима, не обычной нагрузки со всеми приложениями и не SLA.

Исторические resource REWORK результаты остаются прежними; новая policy не превращает
их задним числом в acceptance. T048/T049/G5 открыты до новых actual evidence/owner gates.

## Реализация и проверка

Policy применяется только к отдельному hashed profile; absent policy остаётся strict
`strict_no_warning_no_swap_v1`. Test-only CLI scenario flag и profile должны совпадать.
Новая серия требует explicit owned-process watchdog; прямой случайный запуск запрещён.
Watchdog завершает только созданную им новую process group (backend controller+I),
не существующие приложения. Critical/hard ceiling наблюдение не ждёт окончания SDK.
Длительность, бюджет и freshness bound нового прогона — в отдельно принимаемом
[execution bill](scenario-probe-plan.md); approval policy не принимает эти новые values.
Векторизация проверяется для всех genuine I crops без усечения до одного.
Providers остаются cached как в существующем adapter: измеряем actual residency,
не выдаём последовательность вызовов за гарантированное освобождение каждой модели.
