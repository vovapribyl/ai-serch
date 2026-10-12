# Диагностика системной остановки по памяти

2026-10-11. STANDARD: read-only анализ [последнего прохода](skip-photo-build-report.md)
и текущего baseline. Owner: «ДАвай» на выяснение источника pressure.
Новый ML-прогон, изменения моделей/SDK/лимитов и управление чужими процессами
не выполнялись. Результат — уточнение доказательств, не исправление ресурсного blocker.

## Что установлено

**OBSERVATION / VERIFIED:** последняя остановка вызвана raw pressure4 от
`kern.memorystatus_vm_pressure_level`, при исправном sample. В ObservationGate
это RESOURCE_CEILING. Не превышены processRSS ceilings6/5/combined10GiB;
максимальная одновременная сумма I+backend RSS —1,753GiB.
В terminal sample I401997824 / backend102187008bytes, pressure4.
Storage: host84829921280 / VM28872032256bytes free; artifacts2055336 /
DB12065815bytes. Storage thresholds не причина этой остановки.

Код Apple sysctl отдаёт преобразованные dispatch flags, а не внутренний enum:
[handler/convert](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus_notify.c)
и [flags1/2/4](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/event_private.h).
Поэтому4 действительно critical. Таблица внутреннего enum0/1/2/3/4 описывает иной
интерфейс и не должна использоваться для переинтерпретации нашего sysctl.
Проверена логика upstream Apple; точный installed kernel source build не сопоставлялся.

| Момент относительно первого sample | pressure | I RSS,GiB | backend RSS,GiB | swapouts delta,pages |
|---|---:|---:|---:|---:|
| 0s |1|0,000|0,047|0|
| около20s |1|0,832|0,316|0|
| около40s |2|0,393|0,397|10432|
| около80s |1|0,390|0,099|10432|
| около110s |2|0,440|0,097|13012|
| terminal около115,3s |4|0,374|0,095|93424|

Первое warning около23,61s; далее неоднократные1↔2 и terminal4.
Whole-host swapouts выросли на93424pages. Текущий `vm_stat` page size16384bytes:
арифметический эквивалент —1,426GiB страниц. Размер страницы именно во время прогона
не записывался; расчёт использует текущую страницу на том же host. Это накопительный
трафик всего host, не уникальный объём памяти модели и не её персональная метрика.
СнижениеRSS сопровождает общесистемную выгрузку, но не доказывает, какие конкретно
страницы выгружались. RSS не равен полному footprint и не устанавливает расход GPU.

## Текущий baseline после завершения

Read-only sysctl/vm_stat/ps/top/dockerinfo/colimastatus:
physical RAM16GiB, pressure1(normal), top8863MiBused /6999MiBunused;
swap3335,56MiBused из4096MiB. Эти данные сняты после остановки, не во время inference.
Они не восстанавливают прошлую пиковую нагрузку; используемый swap может оставаться
при normalpressure.

В snapshottop VM около1305MiB; видимые Codex helper rows в сумме около2,1GiB.
Это текущие показатели, не attribution прошлой остановки и не полный подсчёт Codex.
Docker guest сообщает3,814GiB total: ёмкость guest, не фактически занятые4GiBhostRAM.
В `ps` и `top` значения расходятся: разные показатели/время измерения; нельзя
подменять physical footprint суммойRSS. Названия/аргументы/IDs прочих процессов
не перенесены в Git; private snapshot700/600 сохранён отдельно.

## Главный пробел наблюдения

**FACT_CLAIM / VERIFIED(source):** `native_factories()` размещает embedding providers
на MPS. `NailEmbeddingAdapter.providers` сохраняет все три экземпляра на протяжении
прохода; I работает в отдельном процессе на MPS. Device lease сериализует операции,
но не выгружает модели после вызова. Существующий код не записывает
`torch.mps.current_allocated_memory()` и `driver_allocated_memory()`.

[PyTorch tensor allocations](https://docs.pytorch.org/docs/stable/generated/torch.mps.current_allocated_memory)
не включают свободный allocator cache;
[Metal driver allocations](https://docs.pytorch.org/docs/main/generated/torch.mps.driver_allocated_memory.html)
включают allocator pools и MPS/MPSGraph. Это разные категории, их нельзя складывать
как независимые объёмы. Обе нужны для различения live tensors и cache/framework.
SDK читался статически: Torch/модель не импортировались ради baseline. В обоих
выбранных runtime доступны все три названныеmemoryAPI иsynchronize; это проверка
наличия методов, не их runtime-измерение.

**DRAFT_HYPOTHESIS / UNVERIFIED:** одновременно резидентные модели двух процессов,
их Metal/MPS pools/graphs и текущая фоновая нагрузка вместе исчерпывают запас памяти.
Это приоритетная гипотеза для проверки, не доказанный виновник. Memory leak,
виновность Docker/Codex и конкретного фото — UNKNOWN. Следующий PENDING номер023
621×842 имеет522882pixels, меньше cap2359296; отсутствие per-photo trace не позволяет
утверждать, какая операция выполнялась приSTOP. Input pixel cap не превышен.

## Следующая проверка, без изменения качества

Подготовить безопасную telemetry в обоих native процессах: после load и по границам
localize/encode записывать stage/model key/test number, current tensor bytes,
Metal driver bytes, и recommended memory; синхронно наблюдать host pressure,
vm_stat/compressor/swap и физический расход групп процессов. Только числа и safe
codes: без images/masks/vectors/sourceIDs/fullpaths. Метрики читать из уже загруженного
Torch, не создавать дополнительный CUDA/MPS context в внешнем monitor.

Такое измерение позволит выбрать между release unused cache, residency lifecycle
или фоновой нагрузкой по фактическому профилю. Ни одно из этих исправлений сейчас
не применяется, границы моделей/SDK/dtype/output/input/лимитов не ослабляются.
Это диагностика blocker, не отложенное исследованиеускорения.

Для воспроизведения роста по последовательности нужна отдельно подготовленная
одна controlled сборка тех же100≤3103admissions/3600s с действующейskip policy,
новой frozenidentity после telemetry change, no-publish/no-auto-retry и прежними
hardSTOP. Запуск здесь не выполнен и не разрешён данным read-only анализом.
Нет оснований объявлять ресурсный blocker устранённым или полный корпус готовым.

## Проверка и границы

Read-only trace533samples и код observer/guard/providers проверены; baseline commands
успешны. Productcode/tests/БД не изменялись; повторные suites не проводились.
Local links/conflicts/gitdiffcheck PASS:2files/0brokenlinks/0conflictmarkers.
PrivatebaselineSHA256 `6a6c6fbb7a39a756069831f17e4aaebe7b92301f67f2554773322b209a9728bb`. Независимое review не проводилось
(STANDARD). Сохранены прежние100/list/Sheetsmarkers/partial builds/архивevidence;
T051 открыт,78PENDING;новогоMLwindow/READY/query/publish нет.

## Последующее решение владельца

2026-10-11: владелец выбрал[ручнойqualityтест20](manual-quality20-report.md) перед
performance. Предложеннаявыше MPStelemetry/новое diagnosticMLокно отложены до owner
оценки качества; текущийmanual20session не является этой диагностическойпробой.


2026-10-11: после оценки «Ищет отлично» владелец возобновил анализ производительности
и памяти. [Новый анализ](memory-efficiency-proposal.md) выявил статический резерв
неиспользуемых текстовых весов≈1,288GiB; actualmemoryэкономия/виновникSTOPUNKNOWN.
Это предложение, не применённое исправление и не новыйMLrun.
