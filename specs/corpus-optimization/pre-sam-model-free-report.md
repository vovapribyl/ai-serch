# Замеры SAM и опция очистки перед вызовом

2026-10-17. **MODEL_FREE_VERIFIED — REAL_RUNTIME_NOT_RUN**. STANDARD.
Основание — «Приступай» после [диагностики MPS STOP](mps-stop-diagnostics.md):
подготовить замеры числа боксов/размеров и проверить гипотезу pre-SAM cleanup
без моделей. Это не разрешение продолжить23 входа и не доказательство
снижения пика памяти.

## Изменение

В [модуле диагностики](../../src/product_search/infrastructure/replenishment_load_diagnostics.py)
`wrap_sam` записывает `sam.input` перед вызовом SAM: известность формы,
число изображений, суммарное число боксов и для каждого изображения
height/width/channels/boxes. Читаются только `.shape` входных массивов;
пиксели, координаты боксов, изображения и исходные ID в событие не попадают.
Пределы описателя:1–16 изображений, размеры1–65536, RGB3,0–65536 боксов
на изображение с4 координатами. Это границы **диагностики**, не ограничения
самого предсказания: иная форма даёт known=false/incomplete, аргументы
по-прежнему передаются в исходный SAM без подмены.

Сводка описывает массивы на входе `lang_sam.models.sam.SAM.predict_batch`,
а не внутренние resized tensors/predictor features. Недостающие внутренние
формы не объявлены измеренными. Модели/numpy/torch для сводки не импортируются.
Событие использует прежний приватный журнал, лимит4096 bytes/event,
max_bytes/rotation/status и проверки численных ресурсных метрик.

Опция `empty_cache_before_sam` — bool, по умолчанию false. Она допустима
только с `empty_cache_after_photo=true` и `load_diagnostics=true`.
Неверный тип/отсутствие предпосылок даёт RUNTIME_MISMATCH при проверке binding
до SDK, а [worker entry](../../src/product_search/infrastructure/replenishment_worker_entry.py)
дополнительно требует настоящий callback и diagnostics при включённой опции.
Опция входит в runtime binding; будущий пакет должен иметь новые runtime/code pins.

Порядок при включении:

1. `sam.input` — сводка и текущий ресурсный sample.
2. `mps.pre_sam_cache.before/after` — дополнительная очистка.
3. `sam.predict.before/after` либо error — исходный SAM.
4. После успешного CandidateIBinding — прежняя `mps.empty_cache` очистка фото.

Если pre-SAM callback отказал, SAM не вызывается, ошибка сохраняется.
Если SAM отказал, его ошибка сохраняется; прежний post-photo after_success
не превращается в finally и не объявляется выполненным. HTTP REGION_COUNT_LIMIT
после успешного binding остаётся после post-photo cleanup, как прежде.
Возвращаемые объекты, аргументы, kwargs и исходные исключения не подменяются;
методы восстанавливаются при выходе из instrument_localizer.

Ограничения RSS/MPS, driver-based guard, freshness, wait/latched STOP,
HTTP region cap, модели, профиль и формулы поиска не менялись. Включение опции
в реальные binding/grants не выполнялось. Дополнительные события и cleanup
меняют накладные расходы; их runtime-влияние пока UNKNOWN.

## Проверки

- RED14: нового описателя/обёртки/флага ещё нет, проверки обнаружили отсутствие
  поведения и отказа неверных предпосылок. GREEN14 на реальном bounded JSON sink,
  shape-only объектах и обычных вызовах без SDK: positional/keyword identity,
  возвращаемый объект, счётчики,0 боксов, unknown/malformed/oversize metadata,
  cache-before-SAM, отказ cache/SAM с сохранением исходной ошибки.
- Для native wiring отдельно: без подключения callback опция true дала RED
  (2 PASS/1 FAIL), после подключения все три состояния PASS: обе очистки off,
  только post-photo, pre-SAM+post-photo. Uvicorn/socket/model boundaries заменены;
  worker composition, порядок вызовов и число очисток проверяются настоящие.
- Итог145 PASS/0 FAIL/0 ERROR/0 SKIP: load diagnostics, новый SAM test,
  runtime binding/observer, ResourceWait, export reader, worker binding и monitor.
  Ruff PASS, diff/ссылки/таблицы/синтаксис проверены.
- Полный suite не запускался: содержит PostgreSQL/runtime fixtures вне
  разрешённой model-free проверки и известный missing candidate_i_fake_server.py.
  ML, новая БД, новые grants/START, изменение окружений, commit/push отсутствуют.
  Самопроверка; независимое review не проводилось (STANDARD).

Evidence: ignored `artifacts/corpus-replenishment/pre-sam-model-free-20261017/`:
JUnit `tests.xml`, `verification.json`, source snapshots/SHA. Исторические
подписанные пакеты и542 сохранённых файла не изменены. Текущие изменённые
source files уже не совпадут с code inventory израсходованного пакета45;
его повтор недопустим, для будущей проверки нужен новый пакет.

## Следующая точка

Подготовить конечную реальную пробу на двух конкретных фото N05, где был
зафиксирован пик: те же входы/профиль/guard/caps, новая опция и замеры,
новые source/runtime pins, один запуск без повторов. Оба фото ранее получили
REGION_COUNT_LIMIT; их повторная диагностическая обработка должна быть явно
указана в новом пакете и отдельно разрешена. Такая проба проверит гипотезу
на известных входах, а не готовность обработать весь остаток23.
Ни проба, ни продолжение корпуса сейчас не запущены и не разрешены.

Уточнение 2026-10-17: [конкретная проба двух фото N05](pre-sam-probe-execution-package.md)
подготовлена без ML/БД. Новые pins и SHA закреплены; owner approval ещё нет.

Уточнение исполнения 2026-10-17: проба израсходована. Native OK/COMPLETED,
оба deferred,46 OK/0 STOP; новый guard peak5 415 075 840 bytes. Формальный runner
FAILED из-за отсутствующего diagnostic footer при SIGTERM; [результат и ограничения](pre-sam-probe-execution-package.md#фактический-результат--2026-10-17).
Это не превращает предыдущие model-free проверки в доказательство runtime-эффекта.
