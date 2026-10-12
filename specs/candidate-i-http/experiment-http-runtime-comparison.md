# Candidate I — сравнение эксперимента и HTTP runtime

2026-10-08. STANDARD, read-only исследование по просьбе владельца «Хорошо, сравнивай».
Новые модели, inference, installs и изменения runtime-профиля не выполнялись.

## Основания

Из сохранённого private run-summary взяты только технические поля и aggregates:
Candidate I COMPLETED, 30 SUCCESS / 0 LOCALIZATION_FAILED / 0 TECHNICAL_ERROR,
RESOURCE_ERROR=0. Clean checkpoint `067adb8737eab4db5d32088fde5e66f20392f8d7`,
config `168e5ddddb4d99be1b1daa28fc507f09c6de59d03964a79014b4f2653d2235ef`.
Этот actual завершённый run точнее исходной исторической ссылки `4079d39` в
[G4 bill](runtime-bill.md); предыдущую ссылку не переобозначаем задним числом.
Старый config: private `nail-localization-v1/config/calibration-i-auto-roi-c.json`.
Current config: private `candidate-i-http-runtime-rework-20261008/runtime-config.json`.
Raw images, locators, per-photo результаты и Candidate J не читались.

## Проверенные различия

| Область | Завершённый эксперимент | Текущий HTTP runtime |
|---|---|---|
| Python | 3.12.14 в saved config | 3.12.14 в saved config и actual bootstrap |
| Torch / torchvision | 2.4.1 / 0.19.1 | 2.13.0 / 0.28.0 |
| Package inventories | 89 distributions | 89; metadata сравнение выявило ровно эти две version differences |
| Device / operator fallback | MPS, `PYTORCH_ENABLE_MPS_FALLBACK=1` перед lazy import | MPS, fallback запрещён config/binding/bootstrap/controller |
| SDK / model revisions | LangSAM `918043ed…`, SAM2 `c2ec8e14…`, DINO `12bdfa31…` | Те же revisions; те же local weight paths и ранее verified hashes |
| Prompt / thresholds | `artificial nails`, box0.25/text0.2/mask0.5 | Совпадают |
| ROI / large-box filtering | TwoPassRoiLocalizer, limit0.3, nested ROI | Те же параметры; roi.py и roi_localizer.py byte-identical историческому checkpoint |
| SDK image transforms | DINO shortest800/longest1333; SAM1024×1024 | Те же local artifacts; SAM transforms.py byte-identical |
| Model lifecycle | Один lazy client и одна LangSAM instance на CLI run, повторно используемые для фото | Одна binding/client/instance на service process; max_workers1 и admission guards |
| Seed / determinism / dtype | Declared seed20260920/deterministic=true; CLI/runner/client не применяют эти настройки явно; default Torch float32 по installed source | Lazy initializer явно задаёт seed, deterministic algorithms и default float32 до model load |
| Resource acceptance | Runner фиксирует resource/artifact failures; нет sysctl/RSS/swapout sampling и запрета transient warning | RSS ceilings плюс любой pressure≠1 или swapout delta≠0 → REWORK |
| Последний outcome | 30 фото технически обработаны; memory timeline отсутствует | Generated cold256×256 HTTP OK/6 regions, но pressure warning/swap → RESOURCE REWORK |

Старый runner выполнял EXIF transpose/RGB decode без resize; declared max_side1536
в config сам по себе не доказывает resize. В HTTP wire передаются RGB pixels без
EXIF/alpha, binding восстанавливает PIL без resize; external image store выполняет
EXIF/RGB/alpha-on-white preparation. Synthetic cold bypasses source-image store.
Нет основания объяснять новый расход «двумя моделями» или internal upscaling как
нововведением: оба существовали в эксперименте. HTTP добавляет process/controller,
wire buffers и worker, но source trace не показывает создание второй LangSAM instance
внутри I или параллельный inference. Runtime утечка этим read-only анализом не исключена.

## Что объяснено, а что UNKNOWN

Подтверждена цепочка [initial runtime failure](runtime-report.md) →
[approved rework](runtime-rework-bill.md): при Torch2.4.1 и запрете fallback SAM
останавливался на `aten::upsample_bicubic2d.out`; новый Torch устранил native MPS error.
Успешный старый режим и текущий режим поэтому не эквивалентны.

Подтверждено и отличие критериев: старый SUCCESS не доказывает отсутствие transient
pressure/swap, а текущий REWORK не означает OOM или провал localization.
[Последнее измерение](mps-footprint-report.md) — HTTP OK, driver peak2.653GiB,
warning/swapouts delta17824pages. Сопоставимых old memory counters нет.
Причинный вклад Torch upgrade, распределения CPU/MPS operations, explicit determinism,
thread/process execution и фоновой нагрузки — UNKNOWN. Увеличение peak относительно
эксперимента не доказано. Пользовательское «проблем не было» сохраняется как наблюдение
работоспособности, не подменяется утверждением, что прежний runtime тоже не проходил.

## Минимальный предложенный следующий шаг, не разрешение

Не менять приложения пользователя или production profile как условие исправления.
Сначала предложить отдельно разрешённый generated-only cold check на сохранённом
control env Torch2.4.1/torchvision0.19.1 с explicit fallback=1, теми же model artifacts,
prompt/ROI, input fixture и сопоставимой resource telemetry. Рабочий corpus/DB/J
не нужны, packages/weights не устанавливаются. Cold-only, свежий bounded window,
неизменные ресурсные stop limits, evidence-preserving новые trace paths.

Это сравнение двух runtime bundles, не изолированный причинный тест только fallback.
Просто включить fallback в Torch2.13 недостаточно для восстановления старого режима:
операция уже имеет native MPS реализацию и разрешение fallback не принуждает её к CPU.
Current binding/readiness намеренно запрещают fallback; их нельзя обходить для такого
check. Нужен явно согласованный test-only diagnostic launcher/identity для control env.
Фактическое изменение approved runtime profile — отдельное owner решение, не результат
этой записки. T048 RESOURCE REWORK и T049/G5 остаются открытыми.

Самопроверка: saved config/run metadata, package metadata diff, Git source comparison,
SDK file SHA и relevant source trace; Markdown links/markers/whitespace.
Независимое review не проводилось (STANDARD); новый model-free suite не запускался,
поскольку executable code не менялся. Ponytail: existing control env/adapter reuse;
Superpowers systematic-debugging: comparison before selecting runtime fix.
