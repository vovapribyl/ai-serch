# G4 — раздельные runtime Candidate I и backend

Дата подготовки: 2026-10-08. Статус: **APPROVED_BY_OWNER** 2026-10-08.

Пакет подготовлен в T043 и принят владельцем ответом «Разрешаю все три пункта»:
утверждены exact bills и runtime profile; разрешены T044–T045; отдельно разрешены
T046–T048 в описанном bounded synthetic контуре. Доступ к corpus/рабочей БД,
build/publish/activation, Candidate J и Git publication не разрешён.

Входы: [tasks](tasks.md), [HTTP-контракт v0.1](../../docs/architecture/candidate-i-http-contract.md),
[план раздельного Mac-контура](../../docs/architecture/mac-common-environment-plan.md),
[G3](g3-storage-decisions.md) и [фактический handoff](execution-context.md).

## План-контракт и предел доказательства

Маршрут `STANDARD`: собрать фактические metadata двух контрольных ML-окружений и
тестового окружения кода, отделить наблюдения от исторических evidence, предложить
один конечный профиль для решения владельца и остановиться до реальных операций.

Ponytail full: не объединять locks, не вводить новый orchestration layer и не
устанавливать package только ради inventory. Переиспользовать точные контрольные
locks; отдельные окружения и shared device lease сохранить.

## Первоначальный read-only inventory T043 на 2026-10-08

Полные пути и полный package inventory остаются вне Git. Ниже приведены безопасные
агрегаты и первоначальные fingerprints. Точная сериализация первоначальных package
hashes не была сохранена; для последующего bootstrap используются повторно вычисленные
значения с однозначным алгоритмом в дополнении ниже. Импорт ML-модулей в T043 не выполнялся.

| Контур | Проверенный факт | Статус / ограничение |
|---|---|---|
| Платформа | Mac mini, Apple M4, arm64, 10 cores, 16 GB RAM; macOS 27.0.1; CPython 3.12.14 в проверенных окружениях | `VERIFIED`; serial/UUID не сохраняются |
| Test/code environment | 42 distributions; inventory `df570a962828f72d08a1c8b67a4e52eee4bfbaaa38b9e8a13386ea86fba4b4e1`; FastAPI 0.141.1, HTTPX 0.28.1, Pillow 11.3.0, Uvicorn 0.52.4, pytest 8.4.2, Ruff 0.16.5; Torch/three providers отсутствуют | `VERIFIED`; пригодно для fake/scoped tests, не для real providers |
| Backend ML control | Отдельное окружение Gate 3: 71 distributions; inventory `c62f73196f4bebd99cba4152e0a438e4a1f326dcaf4dcf8b73403f61d1855c4d`; lock `51d1459794ad9f59259fd6e5184092060154e48f3e86cf2adf13d9fbe9ce0f59` содержит 59 exact packages, ещё 12 — tooling; версии lock и установленных runtime packages совпадают | `VERIFIED`; checkout этого control — исторический `59087af`, поэтому он не является code identity текущей реализации |
| I control | 89 distributions; inventory `62c9103784f1293c73b9fe3d03c74c97a06fcff2910a4358f8b5a9fa76b8f31a`; текущий lock `ff813642a4150a635f8af7339585a742646126df70074029232eea451e858f46`: 87 exact packages + `lang-sam` и `sam-2` с exact VCS revisions; расхождений версий нет | `VERIFIED`; окружение сохраняется как control и не изменяется |
| Код Candidate I HTTP | Managed worktree detached HEAD `ba495046c80d25190a1745cb9f63384d00a42dd4`, dirty/untracked изменения сохранены; текущий composite hash релевантных I/nail Python sources `abd587c64c1fe294001f0f5671469fc82dd8c600bb407528c21fc0a0390a9fd4` | `VERIFIED`; `services/candidate_i/binding.py` ещё отсутствует, поэтому final code identity/fingerprint `UNKNOWN` |
| HTTP contract | OpenAPI v0.1 SHA-256 `227f68f7e13c30a958cbecde8ba67d7d03db3e8e9b021069d240a1d6aee1ceb1` | `VERIFIED`; принятые caps 20 MiB PNG, 8 KiB metadata, 20 MiB + 64 KiB body не меняются |

### I dependencies и модели

Фактический I control содержит: `torch 2.4.1`, `torchvision 0.19.1`,
`transformers 4.44.2`, `numpy 2.2.5`, `Pillow 11.3.0`, `lang-sam 0.2.1`,
`sam-2 1.0`, `FastAPI 0.141.1`, `Uvicorn 0.53.0`,
`python-multipart 0.0.32`, `HTTPX 0.28.1`. VCS metadata подтверждает:

- `lang-sam` — commit `918043ed4666eea04da88aa179eb8d27ef4b1a1d`;
- `sam-2` — commit `c2ec8e14a185632b0a5d8b161928ceb50197eddc`.

Локально присутствуют и read-only сверены:

| Модель | Revision / artifact | Bytes | SHA-256 |
|---|---|---:|---|
| Grounding DINO base | `12bdfa3120f3e7ec7b434d90674b3396eccf88eb`, `model.safetensors` | 933400872 | `5548f844c928c4b6f411fa8cbcc2bfa8dbbba437cb1d513975519f93c2a9ed21` |
| SAM 2.1 Hiera Small | `sam2.1_hiera_small.pt` | 184416285 | `6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38` |

Последний сохранённый Candidate I run использовал code checkpoint `4079d39`, config
fingerprint `168e5ddddb4d99be1b1daa28fc507f09c6de59d03964a79014b4f2653d2235ef`,
device `mps` и operator fallback enabled. Его dependency lock fingerprint
`61a8965d9ed6647fcba63878032f655d02a83ed88851591a6d639e442447ab2f`
**не совпадает** с текущим lock. Этот run — историческое evidence; его extractor
fingerprint нельзя переиспользовать для G4.

### Backend models

Для backend предлагаются уже принятые model identities:

| model_key | Revision | Dimension | Historical manifest |
|---|---|---:|---|
| `openclip_b32` | `1a25a446712ba5ee05982a381eed697ef9b435cf` | 512 | `7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d` |
| `dinov2_b14` | `f9e44c814b77203eaa57a6bdbbd535f21ede1415` | 768 | `ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783` |
| `siglip2_b16_224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | 768 | `45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9` |

Это `PARTIAL`: revisions/manifests подтверждены историческим Gate 3, но в текущей
сессии `MVP_MODEL_DIR` не задан, а snapshots не найдены в проверенных project/output
roots. Их текущая доступность и неизменность — `UNKNOWN`; старый smoke не заменяет
повторную manifest-проверку перед T047.

## Предлагаемые exact bills

### Backend

1. Сохранить отдельный backend ML control lock с SHA-256
   `51d1459794ad9f59259fd6e5184092060154e48f3e86cf2adf13d9fbe9ce0f59`;
   не объединять его с I lock.
2. Добавить HTTPX в runtime dependencies проекта с выбранной версией
   `httpx==0.28.1`. В test environment эта версия уже установлена; изменение
   declaration само по себе не требует package install.
3. Для T047 использовать новый/отдельный backend runtime, собранный exact lock, либо
   read-only control с тем же inventory после повторной проверки. Source code берётся
   из текущего Candidate I worktree, не из исторического checkout Gate 3.
4. До model load проверить три manifests по таблице выше. Если snapshots отсутствуют,
   остановиться: download не входит в это предложение без отдельного разрешения.

### I-service

1. Сохранить существующий I control без изменений.
2. Создать отдельный каталог окружения mode `0700` из текущего exact lock
   `ff813642a4150a635f8af7339585a742646126df70074029232eea451e858f46`;
   direct VCS revisions — только два указанных commit. Использовать локальный package
   cache/offline; при отсутствии artifact остановиться без сети.
3. Зафиксировать этот exact lock как `services/candidate_i/requirements.lock`; не
   переносить backend ML packages в отдельный merged lock.
4. Повторно проверить 89-package inventory, два веса и frozen config до bootstrap.
   Import/freeze PASS не называть model smoke.

## Предлагаемый конечный runtime profile G4

Значения ниже — `APPROVED_BY_OWNER` 2026-10-08. Они не взяты из test fixtures и не
объявляются измеренными до фактической серии T046–T048.

Уточнение после owner «Да»: для нового full-scenario profile warning/swap являются
diagnostics, critical/RSS/error/timeout остаются STOP —
[отдельная policy](scenario-suitability-profile.md). Историческая таблица и результаты
strict runs ниже сохраняются. Новый execution budget принимается отдельно.

| Параметр | Значение | Поведение при превышении |
|---|---:|---|
| `connect_timeout_s` | `1` | весь run отклоняется, без retry |
| `write_timeout_s` | `30` | весь run отклоняется, без retry |
| `read_timeout_s` | `300` | backend прекращает ожидание; I lease удерживается до actual completion |
| `overall_timeout_s` | `330` | late result не commit |
| `max_source_bytes` / wire PNG | `20 MiB` | `RESOURCE_LIMIT` / `PAYLOAD_TOO_LARGE` |
| `max_decoded_pixels` | `2359296` (`1536 × 1536`) | до ML `INVALID_IMAGE`/`RESOURCE_LIMIT` |
| `max_region_count` | `10` | whole-photo `RESOURCE_ERROR`, без partial result |
| `max_response_bytes` | `40 MiB` | whole-photo `INVALID_OUTPUT`/resource failure; вмещает десять worst-case full-frame grayscale masks с Base64 overhead |
| `max_solver_states` | `16384` | отказ до numeric matrix allocation |
| `max_manifest_bytes` | `8 MiB` | build/resume artifact operation отклоняется |
| Два процесса: peak combined RSS | `10 GiB` | `REWORK`; дополнительно memory pressure не yellow/red и swapouts delta `0` |
| I process peak RSS | `6 GiB` | `REWORK` |
| Backend process peak RSS | `5 GiB` | `REWORK`; combined ceiling имеет приоритет |

Lifecycle: loopback only; один I process/одна instance; один in-flight inference;
I models загружаются только в разрешённом bootstrap/первом admitted call и остаются
resident в пределах серии; три embedding providers работают строго последовательно.
Shared device lease принадлежит исполняющему процессу; backend не держит её во время
HTTP. Device — `mps`, dtype — `float32`, automatic/silent CPU fallback запрещён.
Если обязательная MPS operation недоступна, результат `REWORK`, а не смена device.

Ограниченная серия T046–T048: только generated RGB/synthetic region, максимум 8
model-backed requests и 20 минут wall-clock; один cold и два warm I calls, по одному
encode каждой из трёх моделей, затем один bounded end-to-end lifecycle. Corpus,
рабочая БД, старые evaluation/calibration images и Candidate J не читаются.

## Fingerprints и readiness

До T045 final extractor fingerprint — `UNKNOWN`, потому что отсутствуют real binding,
новый I-service lock artifact и принятый runtime-profile hash. После разрешения он
строится по HTTP-контракту из:

- exact current binding/adapter/mapper code identity;
- I-service lock SHA-256 и 89-package inventory hash;
- двух model revisions и artifact SHA-256;
- frozen localization config hash;
- `mps`/`float32`/no-fallback и hash всей таблицы runtime profile.

Readiness проверяет inventory/fingerprint, но не загружает модели и не выполняет
inference. Любое несовпадение — `MODEL_NOT_READY`/`PROFILE_MISMATCH` до ML.

## UNKNOWN и stop points

- Текущее местоположение/доступность трёх backend model snapshots — `UNKNOWN`.
- Фактические cold/warm latency, peak RSS/MPS residency и соответствие предложенным
  ceilings — `UNKNOWN` до разрешённой серии.
- Совместимость MPS без operator fallback для Candidate I — `UNKNOWN`; исторический
  run выполнялся с explicit fallback enabled.
- Final I code/runtime/extractor fingerprint — `UNKNOWN` до T044–T045.
- Реальное качество top-10/top-3, corpus coverage и рабочая DB — вне G4.

## Решение владельца и оставшийся stop point

Владелец разрешил все три пункта 2026-10-08. T044–T045 выполняются с offline package
cache; T046–T048 — только на generated/synthetic inputs и в пределах таблицы выше.

Остаётся технический stop point: для T047 нужен существующий private
`MVP_MODEL_DIR` и повторная проверка manifests. Если snapshots отсутствуют, работа
останавливается без скачивания: download не входил в утверждённый exact bill.

Самопроверка T043: inventory metadata и source/lock/weight hashes сверены; обязательные
разделы/значения, относительные ссылки, таблицы, отсутствие conflict markers/private
paths/system identifiers и whitespace checks — **PASS**. Packages/models/DB не
запускались; `git diff --check` не подтверждает runtime.

## Дополнение после T044–T047 и review

Первоначальные наблюдения выше сохранены как snapshot T043. Текущее состояние и
измерения приведены в [runtime report](runtime-report.md): backend snapshots найдены,
manifests полностью совпали, три synthetic MPS providers PASS. Candidate I получил
REWORK на `aten::upsample_bicubic2d.out` в SAM2/Torch 2.4.1 при запрещённом fallback.
T044 PARTIAL/STOP; COW clone не ратифицирован. T048 NOT_RUN, final extractor UNKNOWN.

Повторная metadata-проверка 2026-10-08 фиксирует воспроизводимый package inventory
algorithm: name привести к lowercase и заменить каждый непрерывный набор `-_.` на
`-`; сформировать `name==version`; отсортировать полные строки лексикографически;
соединить LF, добавить один конечный LF, кодировать UTF-8 и вычислить SHA-256.

| Контур | Distributions | Inventory SHA-256 по уточнённому алгоритму |
|---|---:|---|
| Test/code | 42 | `3b8a35c414c663c7d3e205076edb3b640dcb695eeaafa8701ed07fb40f625f8d` |
| Backend control | 71 | `c6cfe4e969c342f48d5d1c27b93cb38502aaed6fe6e005237260d8632f5f7358` |
| I control | 89 | `fbef4ef5182224f25a9a4cf08525367cac97c2b3c94589f02382620377ad6224` |

Эта коррекция устраняет неоднозначность serialization; она не подтверждает новый
runtime profile, совместимость моделей или успешную install-from-lock.
