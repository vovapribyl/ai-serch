# Диагностика MPS STOP серии45

2026-10-17. STANDARD, наблюдения по сохранённым evidence, без ML/БД/START
и изменения кода. Основание — [исполнение серии45](remaining45-execution-package.md#фактический-результат--2026-10-17).

## Вывод

Причина защитного отказа подтверждена: MPS-driver превысил6GiB cap.
Пик локализован по временным меткам около второго вызова SAM в N05,
до очистки кэша этого фото. Очистка не была пропущена: она завершилась
и заметно уменьшила driver usage. Утечка, OOM, конкретная причина размера
пика и достаточность какого-либо исправления **не доказаны**.

В серии45:16 готовых,6 deferred REGION_COUNT_LIMIT,3 PENDING,
20 входов в не начатых фазах; всего23 незавершённых. Эти статусы не менялись.

## Что измеряется

Worker telemetry передаёт `torch.mps.driver_allocated_memory()`, observer
проверяет его по6GiB ceiling. Это память Metal-driver процесса, включающая
кэш и MPS/MPSGraph allocations. `current_allocated_memory()` отражает память
тензоров и не включает allocator cache; разность этих метрик нельзя целиком
объявлять освобождаемым кэшем. `empty_cache()` освобождает неиспользуемый кэш.
Определения проверены чтением исходника установленного torch2.13.0 без импорта
SDK; совпадают с доступной официальной документацией
[driver memory](https://docs.pytorch.org/docs/2.14/generated/torch.mps.driver_allocated_memory.html),
[tensor memory](https://docs.pytorch.org/docs/2.14/generated/torch.mps.current_allocated_memory.html),
[empty_cache](https://docs.pytorch.org/docs/2.14/generated/torch.mps.empty_cache.html).
Документация2.14 используется только для смысла API, не как версия runtime;
страницы2.13 через web-инструмент недоступны. RSS к MPS не прибавлялся.

## Сопоставление пяти фаз

| Фаза | Вызовы фото завершены | Очистки завершены | Peak MPS guard, bytes | Driver после последней очистки, bytes |
|---|---|---|---|---|
| N01 |5|5|5 170 184 192|2 749 054 976|
| N02 |5|5|4 023 861 248|2 776 317 952|
| N03 |5|5|5 347 115 008|2 770 026 496|
| N04 |5|5|2 875 457 536|2 805 678 080|
| N05 |2|2|6 487 310 336|3 013 296 128|

Пять разных localization worker PID подтверждают отдельный процесс на фазу.
Все22 вызова `localizer.photo` имеют before/after, все22 `mps.empty_cache`
имеют before/after. В worker traces measurement_ok=true; нет основания
считать отсутствие очистки причиной текущего STOP. «Завершённый вызов фото»
здесь означает возврат CandidateIBinding, включая последующий отказ HTTP
по REGION_COUNT_LIMIT, и не означает готовый каталожный результат.

## Последовательность N05

Время — от начала первого вызова фото N05, по локальным monotonic-меткам.
Точность событий ограничена длительностью получения метрик и раздельными
потоками worker diagnostics/телеметрии/observer; это не profiler trace GPU.

| Граница | Время, с | Driver, bytes | Tensor/live, bytes |
|---|---|---|---|
| После очистки фото1 |5,545|2 847 621 120|1 245 855 744|
| Перед GDINO фото2 |8,013|2 847 621 120|1 245 855 744|
| Перед SAM фото2 |9,595|3 930 341 376|1 245 861 120|
| После SAM фото2 |10,481|6 440 075 264|1 244 603 392|
| Первый resource STOP |10,597|6 487 310 336|UNKNOWN в этом sample|
| Перед empty_cache фото2 |12,622|6 440 075 264|1 244 598 016|
| После empty_cache фото2 |12,700|3 013 296 128|1 244 598 016|

Первый STOP: RESOURCE_LIMITS/MPS_LIMIT/sample_current=true,
pressure2; превышение6 442 450 944 bytes ceiling на44 859 392 bytes.
Он записан примерно через0,116с после границы SAM.after и за2,025с до
метки empty_cache.before. Worker затем завершил очистку, но latched STOP
не отменился; третьего вызова фото нет. Это соответствует защитному контракту.
Два STOP-наблюдения — сохранение первой причины, не два независимых пика.

Driver при очистке фото2 уменьшился на3 426 779 136 bytes при неизменной
live-памяти. Между очистками фото1 и фото2 live уменьшилась на1 257 728 bytes;
монотонного накопления живых тензоров на этих двух границах не видно.
Этого недостаточно, чтобы исключить любые утечки или объяснить весь driver peak.

## Проверка пути в коде

[Worker entry](../../src/product_search/infrastructure/replenishment_worker_entry.py):
telemetry читает driver memory, `empty_cache_after_photo=true` передаёт callback
в `instrument_localizer`.
[Diagnostics](../../src/product_search/infrastructure/replenishment_load_diagnostics.py):
`after_success` вызывает callback после успешного возврата CandidateIBinding.
[HTTP handler](../../services/candidate_i/app.py) вызывает `binding`, затем
[encode_result](../../src/product_search/infrastructure/nail_wire.py) проверяет
`max_region_count`. Поэтому этот REGION_COUNT_LIMIT возникает уже **после**
callback очистки. Логи N05 подтверждают две очистки и два сохранённых deferred.
Гипотеза «ошибка лимита пропустила empty_cache» для этих двух фото опровергнута.

Установленный `lang_sam.models.sam.SAM.predict_batch` вызывает
`set_image_batch(images_rgb)`, затем `predict_batch(box_batch=xyxy,
multimask_output=False)`. Число box prompts и эффективные размеры входа SAM
в текущих traces не записаны. Известные556×574 — размер исходника фото2,
не размер внутренних тензоров SAM; вывод о памяти только по нему недопустим.

## Что остаётся неизвестным и следующий шаг

Наблюдения согласуются с временным ростом driver allocations около SAM,
которые существенно освобождаются позже. Не установлены вклад числа боксов,
форм/внутренних изображений, allocator/framework caches и влияние предыдущего
фото. Restart на каждое фото не доказан как исправление внутривызовного пика.
Подмена driver memory на live memory, повышение cap или снятие latched STOP
не следуют из диагностики.

Следующий ограниченный шаг — подготовить model-free изменение диагностики:
число images/box prompts и размеры на входе SAM, замеры перед/после SAM.
Как отдельную гипотезу можно проверить дополнительный empty_cache **перед** SAM,
когда накопленный driver уже3,93GB; post-photo cleanup при этом сохраняется.
Снижение пика заранее не гарантируется. Изменение должно иметь TDD-проверку
порядка callback/ошибок и новые code/runtime pins; реальная проверка — только
отдельным конечным пакетом на конкретных входах с прежними caps.
Нового разрешения на такой runtime, обработку23 или изменение профиля нет.
Outer error для partial export по-прежнему общий; его исправление отдельно
от причинного диагноза MPS, native STOP/MPS_LIMIT сохранены.

## Воспроизводимость и ограничения

Приватная папка `artifacts/corpus-replenishment/mps-stop-diagnostics-20261017/`:
`analyze.py`, `analysis.json`, `evidence-pins.json`. Проверены ограниченные
resource/load-event traces пяти фаз, source pins, counts/timing и исходники;
в отчёт вынесены агрегаты без фото/сырого source ID/PID. Исходные logs не менялись.
Сохранённый SHA серии b08f7398, runner и542 прежних файла повторно проверены.
Код продукта/модели/профиль не менялись, тесты продукта и live probes не запускались.
Самопроверка; независимое review не проводилось (STANDARD).

Уточнение 2026-10-17: [model-free изменение](pre-sam-model-free-report.md)
реализовано и проверено145 тестами. Опция default-off, реальный эффект не измерен;
исторические pins/logs и результат MPS STOP сохранены без изменения.
