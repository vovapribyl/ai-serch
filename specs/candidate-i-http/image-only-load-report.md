# Результат облегчения загрузки моделей

2026-10-11. Первый шаг реализован и проверен небольшой пробой.
Полный поиск с новым runtime и длительная сборка корпуса ещё не проверены.
[План и границы](image-only-load-plan.md), [анализ вариантов](memory-efficiency-proposal.md).
Владелец разрешил начать с image-only загрузки; выбранная исполнителем проверка
ограничена двумя моделями и тремя сохранёнными обрезками фото001.

## Что изменилось

В worktree `candidate-i-http`, файлы `openclip_provider.py` и
`transformers_provider.py`: полный checkpoint сначала читается на CPU, затем
сохраняется только исходный image encoder. Родительская модель удаляется до
переноса image encoder на MPS. OpenCLIP использует прежний `visual`, включая
projection; SigLIP2 — прежний `vision_model` с тем же pooling. DINO остаётся
тем же объектом. Публичный `encode_image`, веса, preprocessing, float32,
размерности, нормализация и алгоритм ранжирования сохранены.

Это устраняет постоянное хранение неиспользуемой текстовой части и её перенос
на MPS. Текстовые параметры временно создаются при чтении полного checkpoint
на CPU. Пик загрузки не устранён; direct vision-only loader — отдельный следующий
вариант при необходимости. Полный footprint не равен объёму параметров.

## Проверка кода

Model-free regression: OpenCLIP/SigLIP сначала2RED из-за живого parent → GREEN;
DINO уже GREEN. Weakrefs проверяют освобождение parent, сохранение исходного
image object и перенос только image object на device. Путь encode сохраняет
нормализацию и выходной контракт. Общие safe suites:403PASS/46SKIP и2 прежних
dependency warnings. Для локальных socket tests потребовалось разрешённое
исполнение вне sandbox; их sandbox denial не был дефектом продукта.
Два существующих provider unit-теста также PASS на CPU с установленным SDK,
без загрузки настоящих весов. Ruff по5 затронутым файлам и `git diff --check` PASS.

Независимое code review:0Critical/0Major/0Minor. Проверен установленный исходник
OpenCLIP: `encode_image(normalize=False)` возвращает `self.visual(image)`.
Первые замечания к отдельной private пробе:1Major/2Minor (неполный claim handshake,
недолговечный admission counter, ложный success controller). Исправлены до запуска;
обязательное повторное source review PASS0/0/0. Проба переиспользует существующие
owned watchdog, resource observation, runtime verifier, leases и RecordingBudget.

## Реальная малая проба

Новый frozen job SHA256:
`5264cecc33e71ecc219936e848c9c64fad4f961c3e5cb7f11afb47d25baef13f`.
85 code pins, prepared archive SHA256:
`9c9e3871f01bea040222f6dedc25cea4e56e3f5e1857c035955fe2c2f8b10958`.
Private inputs/results/logs сохранены вне Git с правами700/600.

Три lossless RGB crops из существующего каталога; эталон — ранее сохранённые
векторы этих же crops. Только OpenCLIP и SigLIP2, без новых localization calls,
новых фото, catalog build, writes БД, активации индекса или публикации.
Предел8 admissions/600s, те же memory/storage/pressure STOP; no auto retry.

| Показатель | OpenCLIP | SigLIP2 |
|---|---:|---:|
| Проверено crops |3|3|
| Максимальная абсолютная разница компонентов со старым сохранённым вектором |1,4752496779735225e-08|2,31326222621675e-08|
| Побитово совпавшие строки |0|0|
| Удерживаемые параметры image encoder, bytes |351396864|371536896|
| MPS live tensors после load, bytes |351396864|371538688|
| Metal driver после load, bytes |377978880|422264832|
| Metal driver после последнего encode, bytes |388743168|422297600|

Модели проверялись последовательно, освобождались между стадиями. Эти показатели
нельзя выдавать за память одновременно загруженных моделей полного поиска.
Разница векторов очень мала, но точного равенства нет. Причина разницы отдельно
не установлена; rounding сохранённых vectors — возможное объяснение, не факт.
Результат поддерживает сохранение image path на данном небольшом наборе, но
не доказывает качество всех запросов или идентичность всей выдачи.

Проба:7,846s, worker/controller exit0,8/8 reserved, stop_reason null,
observation_stop null.36 samples: только pressure1, swapouts delta0;
peak backend RSS972472320bytes. Финальная own live group0,
device lease reacquired true. Приёмка полной системы этим не подменяется.

## Что можно утверждать о памяти

В реальной пробе image model parameters составляют≈335MiB OpenCLIP и≈354MiB
SigLIP2 — соответствуют сохранённым image ветвям. Неиспользуемые текстовые ветви
не остаются в provider. Их payload в выбранных весах суммарно≈1,288GiB.
Это резерв устранённых параметров, не измеренная разница общей физическойRAM:
старый и новый полный runtime с одинаковыми запросами ещё не сравнивались.
Текущая схема всё ещё хранит три image providers и отдельный I process.

## Следующий шаг

Подготовить новый ограниченный полный поиск с теми же owner примерами и stage
memory metrics в обоих процессах. Сравнить ожидаемые товары/top10 и время/память
первого и повторных запросов; затем принять новый runtime профиль владельцем.
Если pressure сохраняется — рассмотреть стадийную сборку или direct vision-only
load вместо повторной большой сборки без наблюдений. Новый полный manual window
и запуск оставшихся78фото в этой задаче не выполнены.

Предыдущий manual session завершился по WALL_CLOCK_LIMIT3600s с освобождёнными
leases. Его код не менялся в живом процессе; автоматического рестарта не было.
Исходные100/list/Sheetsmarkers, partial catalog и прошлые оценки сохранены.

Финальное независимое read-only review отчёта и границ: PASS,0Critical/0Major/0Minor.
