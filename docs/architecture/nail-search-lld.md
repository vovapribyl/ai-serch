# LLD — поиск товаров по выделенным ногтям на Mac

> Навигация: [карта проекта](../project-map.md). Паспорт и датированные статусы ниже относятся
> к своим версиям/контрактам; текущее исполнение и ограничения указаны в карте.

| Поле | Значение |
|---|---|
| Версия / дата | v0.4 / 2026-10-07 |
| Статус | Остальной LLD v0.4 PENDING_OWNER_APPROVAL; HTTP v0.1 и G2/G3 APPROVED_BY_OWNER; fake/synthetic US1–US3 проверены; real inference/corpus/working DB NOT_RUN |
| Владелец | Владелец проекта |
| Входы | [HLD v0.5](nail-search-hld.md), [анализ](../analysis/nail-search-v1/README.md), [план окружения](mac-common-environment-plan.md) |
| Маршрут | `FULL`: разработка технических контрактов |
| Следующий gate | Review → утверждение выбранных технических решений владельцем → немодельная реализация; ML и данные отдельно |

## Простыми словами

LLD — подробная инструкция по реализации предложенной архитектуры. Здесь описано, что получает и возвращает каждая часть, где сохраняются результаты и что делать при ошибке. Например, HLD говорит «сравнить ногти», а LLD определяет правила сопоставления, формулу оценки и ограничения данных.

Основные термины: **crop** — обрезка с одним ногтем; **embedding** — числовое описание этой обрезки; **representation** — отдельная версия подготовленного каталога; **fingerprint** — контрольная сумма состава и настроек, позволяющая обнаружить их изменение. **Fake** в проверках — заменитель модели с заранее заданным ответом.

**Условный пример предлагаемой оценки.** На фото запроса три ногтя, на фото из каталога два. Алгоритм выбирает допустимые пары с наибольшей общей оценкой; один каталожный ноготь нельзя использовать дважды. Допустим, после объединения оценок трёх моделей выбран такой результат:

| Ноготь запроса | Ноготь каталога | Оценка пары |
|---|---|---|
| Первый | Второй | 0.9 |
| Второй | Первый | 0.6 |
| Третий | Пары нет | 0 |

Оценка этой пары фото: `(0.9 + 0.6 + 0) / 3 = 0.5`. Если у товара несколько фото, выбирается лучшая оценка пары ракурсов. Числа придуманы для объяснения; это не результат модели и не порог приёмки. Среднее, missing0 и лучший ракурс приняты владельцем; cosine шкала, precision/solver детали приняты отдельно в [пакете G2](../../specs/candidate-i-http/g2-core-decisions.md).

Документ нужен при написании кода и проверке поведения. Порядок работы агента описан в [методе разработки](../development-method.md); какие части можно реализовать и какие проверки требуют отдельного разрешения — в §14–15 этого LLD.

## 1. План-контракт и статус содержания

План-контракт v0.3: сохранить алгоритм/схему/ошибки → определить порты приложения и plain-data DTO → разнести use cases, adapters и wiring → задать проверки направления зависимостей и контрактов → синхронизировать HLD/схемы → self-check → независимый read-only reviewer → исправления → предъявить владельцу. Реализация кода и любые runtime-операции не входят в задачу.

**Выбрано владельцем:** отдельный HTTP I на Mac и direct POST;  отдельный embedding каждого ногтя; все технически корректные области запроса с одинаковым весом; нет копий каталожных ногтей; лучшая пара фото; все доступные каталожные ракурсы; отсутствие резервного поиска целого фото при `NO_NAILS`; первая итерация без улучшений масок и ориентации.

**PROPOSED:** не принятые отдельно поля, физическая схема, numeric детали, runtime/deadline limits. HTTP-контракт v0.1 отдельно утверждён 2026-10-07. Владелец принял описанные в объяснении правила crop/участия областей/сопоставления/среднего missing0/лучшей пары и различения NO_NAILS/ошибки; это не утверждение полного LLD. Они детализируют HLD, но не утверждаются самим созданием документа. HLD/анализ ещё ожидают полного owner approval. Ни версии dependencies, ни работоспособность общего окружения здесь не установлены. Исходная точка кода — `ba495046c80d25190a1745cb9f63384d00a42dd4` в `codex/gate-4-manual-testing`; основной checkout остаётся на `813dd11`.

## 2. Область кода и ответственности

Файлы перечислены относительно `src/product_search`. Это предлагаемые изменения только нового поискового режима; legacy whole-image не переносится массово.

| Файл / область | Роль и допустимые зависимости |
|---|---|
| `search/nail_contracts.py` — новый | Immutable DTO и typed errors ядра; только стандартная библиотека |
| `search/nail_ports.py` — новый | Выходные `Protocol`, принадлежащие приложению; импортирует только DTO |
| `search/nail_image_processor.py` — новый | Read → localize → validate → mask/crop; получает порты через конструктор, не импортирует Pillow/эксперимент |
| `search/nail_matching.py` — новый | Чистое сопоставление и арифметика; без I/O и ports |
| `search/nail_service.py` — новый | `execute/execute_many`, ranking и DTO; использует порты/processor/matcher |
| `search/nail_catalog_build.py` — новый | Inventory/profile, terminal outcomes, coverage/readiness, разрешённая публикация через порт |
| `infrastructure/nail_ml_adapters.py` — новый | `HttpNailLocalizationAdapter` и `NailEmbeddingAdapter`; HTTP/PNG mapping и existing providers; backend не импортирует I/эксперимент |
| `infrastructure/nail_image_store.py` — новый | Read/decode/EXIF, RGB и запись производных PNG; validated roots, opaque refs, permissions |
| `infrastructure/nail_repository.py` — новый | `NailCatalogPort`: SQL read/build/publish, транзакции и физическая схема |
| `infrastructure/evaluation_repository.py` | Реализация `NailEvaluationPort` поверх существующего атомарного сохранения; mapper версии score |
| `main.py` / `core/settings.py` и внешний runtime runner | Проверка env/model roots/lock, сборка concrete adapters, verified context, executor/locks/leases; ядро не импортирует эти модули |
| `web/app.py` / `scripts/build_nail_representation.py` | Входные адаптеры: внешняя валидация и вызов сценария; перевод результата в HTTP/CLI |
| `search/multiphoto.py` / `search/evaluation.py` | Существующее состояние сессии и staged commit; new-mode решения используют plain данные ядра, concrete I/O выполняется снаружи |
| Новая Alembic migration после фактического head | Прежние additive таблицы/constraints; миграция не импортируется ядром |

[main](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/main.py), [web](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/web/app.py), [session store](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/search/multiphoto.py), [evaluation service](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/search/evaluation.py), [repository](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/infrastructure/evaluation_repository.py), [migration 0008](../../../../../.codex/worktrees/1eaf/Ai/migrations/versions/0008_gate4_multiphoto_v3.py) — исходная область изменений. [Существующий EmbeddingProvider](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/search/providers.py) использует Pillow: его интерфейс остаётся за новым адаптером. Новые файлы не созданы этой задачей.

`LangSAMAdapter`, `LazyLangSAMClient` и экспериментальные типы переиспользуются только в отдельном I-service. Новый `services/candidate_i` — HTTP-обвязка в своём dependency bill, не импорт ядра или основной инфраструктуры; клиент использует OpenAPI wire schema. Общая установка backend-пакета с его ML dependencies в I-service не требуется. Allowlist/model identity сохраняются при переносе личных путей в конфигурацию. CLI-runner эксперимента, campaign claims и J-verifier в приложение не переносятся. `NailImageProcessor` не создаёт concrete adapters и не импортирует `experiments` даже ради plain классов.

Book-guidance, Clean Architecture mini: ядро владеет ролью и контрактом, адаптер переводит детали. Ponytail: одна общая подготовка для каталога/запроса, один ML-adapter module, без DI-framework и универсального plugin registry.

## 3. Конфигурация и identity

Предлагаемые настройки: `search_mode=whole-image|nail-search-v1`, явно выбранный `device=cpu|mps`, внешний `model_root`, профиль I, `crop_profile`, каталог производных вне Git, `runtime_profile`, лимиты decoded pixels, регионов/solver states и памяти. Новые личные абсолютные пути не зашиваются в код. Старые loopback/storage проверки сохраняются.

`representation_fingerprint` = SHA-256 canonical JSON UTF-8 (sorted keys, separators `,`/`:`, finite numbers) со следующими входами: corpus version и inventory hash, revision кода, hashes полного backend lock и I-service lock, I config hash, I model manifests, crop profile, revisions/processor identities трёх моделей, numeric/solver/score profile и семантически значимый runtime_profile: device выделения и каждого provider, dtype, precision/backend options и разрешённая политика operator fallback; hash полного принятого runtime_profile также закрепляет проверенный lifecycle и ресурсные пределы. Сам fingerprint не включает себя. Config secrets/paths не входят в публичную identity; exact checksum private входов хранится restricted.

Профиль оценки `nail_assignment_mean_v1`, crop `mask_bbox_white_v1` и solver `subset_dp_v1` — названия проектных алгоритмов. Изменение любого из них создаёт новую representation; READY-версия immutable. Активный запрос закрепляет один ID, а сессия закрепляет ID/режим при первом обращении, чтобы повторные ракурсы не смешивали разные индексы. Смена active pointer действует на новые сессии.

В runtime_profile закрепляются отдельно backend/device lifecycle и actual extractor identity из [HTTP-контракта](candidate-i-http-contract.md). Health response без bootstrap/inventory проверки не считается доказательством actual состава.

Перед build (включая resume) и перед каждым поисковым заданием сравнить фактическую конфигурацию с закреплённой representation: manifests/revisions, I/crop, processor, полный lock, numeric/score/solver и runtime_profile. Проверка выполняется до ML, включая rerun существующей сессии. Различие → PROFILE_MISMATCH, без пересчёта вектора и без автоматической активации новой версии. Технически проверенный lifecycle закрепляется в profile; изменение размещения, влияющее на device/dtype/numeric semantics, требует новой representation. Смена кода возможна только при проверенном совпадении revision/profile либо отдельно утверждённой политике совместимости; первая версия такой политики не вводит.

Model keys: `openclip_b32` (512), `dinov2_b14` (768), `siglip2_b16_224` (768). Revisions берутся из закреплённого manifest, не подменяются строкой model key. До разрешённой проверки `runtime_profile` и точные раздельные locks — UNKNOWN.

## 4. Внутренние контракты

Все новые DTO объявляются в `nail_contracts.py` как immutable plain data. Bytes/tuple/int/float/строки допустимы; Pillow image, ndarray, tensor, ORM row, Request, runtime settings и открытый файл через порты не передаются. Данные остаются restricted и не логируются.

```text
PhotoInput
  photo_ordinal: int >= 1
  source_ref: opaque internal ArtifactRef
  input_sha256: 64 hex

RgbImage
  width, height: positive int
  pixels: immutable bytes       # exactly width * height * 3, RGB row-major

BinaryMask
  width, height: positive int
  pixels: immutable bytes       # exactly width * height, values 0/255

LocalizedRegion
  label, confidence, detector_box_xyxy, mask: BinaryMask

NailLocalization
  status: OK | NO_NAILS
  regions: tuple[LocalizedRegion, ...]

ProcessedPhoto
  photo_ordinal, input_sha256
  status: OK | NO_NAILS
  regions: tuple[RegionCrop, ...]

RegionCrop
  ordinal: int >= 1
  detector_box_xyxy: four finite floats
  crop_box_xyxy: four integers, half-open
  mask: BinaryMask              # source-frame mask
  rgb_crop: RgbImage            # white background applied

PhotoEmbeddings
  photo_ordinal, input_sha256
  region_ordinals: ordered tuple[int]
  vectors: model_key -> tuple[tuple[float, ...], ...]

PairMatch
  query_photo_ordinal, catalog_photo_id
  pairs: query_region_ordinal -> catalog_region_ordinal or null
  per_model_pair_scores: model_key -> score
  score: finite float [0,1]

SearchRequest
  photos: ordered tuple[PhotoInput, ...]  # 1–4
  representation_id: opaque ID
  verified_runtime: immutable identity/limits DTO

NailSearchExecution
  corpus_version_id, representation_id, representation_fingerprint
  model_keys, model_revisions, search_duration_ms
  status: OK | NEED_MORE_PHOTOS
  candidates: tuple[NailCandidate, ...]
  skipped_photo_ordinals, input_photos, snapshot
```

`ArtifactRef` — непрозрачный внутренний ключ, разрешаемый файловым адаптером внутри validated root; не HTTP-путь. Каталожные raw locators из §9 остаются private полями БД/адаптера. Профили — immutable plain DTO/hash, без secrets и файловых путей. `verified_runtime` создаётся только внешним runner после фактической проверки, не принимается из HTTP и не вычисляется по одному заявленному fingerprint. Revision/code/lock/device проверки сохраняются до каждого задания (§3).

### Выходные порты приложения

Сигнатуры ниже — проектные контракты, не исполнимый Python и не готовые классы. Реализация может использовать `typing.Protocol`; методы с группой DTO не требуют отдельного порта на каждый шаг.

| Порт | Операции и гарантия |
|---|---|
| `NailImageStorePort` | `read_rgb(PhotoInput, DecodeProfile) → RgbImage`; проверка checksum, decode/EXIF/alpha и resource limits по §5. `write_derivatives(build_id, ProcessedPhoto) → tuple[ArtifactRef, ...]`; PNG/permissions/ownership, без изменения mask/crop policy |
| `NailLocalizationPort` | `localize(RgbImage, LocalizationProfile) → NailLocalization`; OK непустой, NO_NAILS пустой, technical failure — typed error. Реализация Candidate I преобразует existing результат |
| `NailEmbeddingPort` | `encode(model_key, tuple[RgbImage, ...], EmbeddingProfile) → tuple[tuple[float, ...], ...]`; один вектор на crop, исходный порядок, конкретная model identity; общий полный набор из трёх моделей контролирует use case |
| `NailCatalogPort` | `read_ready(id)`, `iter_photo_groups(id)`, `begin_build(BuildIdentity)`, `write_photo_outcome(BuildPhotoResult)`, `read_build_summary(id)`, `publish(id, expected_active_id)`; только plain DTO, атомарная запись фото с его регионами/векторами и атомарная compare-and-set публикация с повторной readiness-проверкой |
| `NailEvaluationPort` | `save_finalized(EvaluationBundle) → SavedEvaluation`; example/candidates/annotations/snapshots сохраняются одной транзакцией или не сохраняются совсем. Новый score и legacy mapping остаются явными |

Use cases владеют eligibility/readiness/score правилами; адаптеры повторно обеспечивают DB-инварианты и технические ограничения. Read DTO возвращают полный набор из трёх моделей и ownership/profile либо typed error, а не ленивый ORM iterator. Публикация — отдельный разрешённый вызов, `begin_build`/завершение вычисления не активируют версию автоматически.

### Candidate I и ошибки

`HttpNailLocalizationAdapter` реализует `NailLocalizationPort` без импорта I. Он передаёт нормализованный RgbImage как PNG multipart и получает JSON/PNG-маски согласно [контракту](candidate-i-http-contract.md) / [OpenAPI](candidate-i-http.openapi.json). Multipart/HTTP/Base64 остаются внешними деталями. PNG round-trip должен сохранять RGB bytes; original input checksum и checksum wire PNG различаются.

Внутри I-service существующий LangSAMAdapter и normalize_result преобразуют SUCCESS в OK, только DETECTOR_NO_MATCH в NO_NAILS; остальные исходы — Problem Details. HTTP-клиент проверяет schema/identity/request_id/checksum/размеры/все маски и переводит их в immutable DTO. Любая неверная область или повреждённый ответ отклоняет всё фото, без partial OK. NO_NAILS не выдаётся по confidence threshold.

Mapping ошибок определяется контрактом §5; публичные HTTP-ответы /search остаются по §11 этого LLD, internal status не пересылается без перевода. Connection/read timeout не является NO_NAILS и не запускает повторный POST. Service model load и package changes требуют отдельного разрешения; создание схемы этого не разрешает.

Последовательность — [HLD](nail-search-hld.md#выделение-через-адаптер--sequence), [PlantUML](diagrams/nail-search-localization.puml). Сервис возвращает full-frame маски; crop policy принадлежит ядру и остаётся одинаковой для каталога/запроса.

### Входные сценарии и сборка

`NailSearchService.execute(PhotoInput, representation_id, verified_runtime)` делегирует `execute_many(SearchRequest)` с одним фото. `NailImageProcessor.process(PhotoInput, ProcessingProfile)` вызывает image-store/localization порты и чистое формирование crops. `NailCatalogBuildService` использует ту же подготовку и embedding порт, затем вызывает image-store порт для записи каталожных производных; решение о readiness принадлежит ему. `BuildRequest` содержит разрешённый immutable inventory, BuildIdentity и verified_runtime, без private paths или утверждений из HTTP. Финализация existing evaluation use case вызывает `NailEvaluationPort` после проверки актуальности session inputs.

Web/CLI преобразуют внешние входы в DTO; внешняя проверка upload/доступа остаётся до ядра, бизнес-решения об актуальности выдачи/readiness не переносятся в контроллер. `main.py` создаёт image-store, HTTP localization, embedding, catalog и evaluation adapters и внедряет их в use cases. Внешний runner организует один ML executor/lock и leases по §13 и передаёт проверенные identity/time данные. `search_duration_ms` измеряет внешний runner и добавляет в итоговый DTO/evidence до staged commit; часы ядро не читает. Ядро не выбирает CPU/MPS, не открывает env и не управляет threads; выбранный runtime_profile задаёт разрешённое исполнение адаптеров.

Чистые расчёты и новые use cases не импортируют legacy modules с framework/Pillow/I/O. Existing session/evaluation wrappers переводят состояние в plain DTO, вызывают ядро и выполняют технический staged commit/locks снаружи; политика stale-finalize и атомарность сохраняются в §11–13. Замена реального порта fake-реализацией не меняет сценарий или формулу.

## 5. Точная подготовка фото — G2 APPROVED_BY_OWNER

1. Входной и image-store адаптеры сохраняют/проверяют SHA-256 исходных bytes. Проверить допустимость загрузки до ML. Каталожный inventory проходит ту же проверку декодирования/ресурсных пределов.
2. `NailImageStorePort.read_rgb` должен применить EXIF orientation к декодированному изображению, затем привести к RGB; прозрачность PNG составить поверх белого фона. Вернуть нормализованный `RgbImage` ядру; localization-адаптер передаёт этот кадр I. Размер mask/координаты относятся к этому кадру, не к исходным EXIF dimensions.
3. Ядро проверяет BinaryMask, после проверки existing результата внешним адаптером: `width*height` bytes, значения только 0/255, непустая mask для каждой detection; box в кадре. Сохранить deterministic detection order `(-confidence,x0,y0,x1,y1,label)`; exact duplicates сохраняют upstream order. Не фильтровать detections по качеству.
4. Для каждого region найти минимальный axis-aligned прямоугольник ненулевых mask pixels: `(min_x,min_y,max_x+1,max_y+1)`. Это **crop box по маске**, отличающийся от detector box; хранить оба. Padding 0, поворота нет.
5. Crop RGB и mask по одному box. Pixels вне mask заменить `(255,255,255)`; не исправлять mask, не сглаживать границу. Ядро формирует `RgbImage`; при сохранении каталога image-store адаптер записывает производную PNG без EXIF и lossy compression. В query path PNG на диск не записывается.
6. Через `NailEmbeddingPort` передать crop каждому существующему provider; его resize/normalization не дублировать вручную. Закрепить processor revision и preprocessing fingerprint одинаково для каталога/запроса.

Нулевая mask, неверная геометрия и превышение ресурсного лимита — отказ, не невидимый пропуск «неудачного ногтя». Значения decoded pixel/region limits открыты до проверки Mac: запуск профиля с незаданными обязательными лимитами запрещён. Точные EXIF/RGB/bbox детали приняты владельцем в пакете G2; PNG wire serialization принят HTTP-контрактом; ресайз меняется только через processor identity.

## 6. Векторы и формула

В каталоге `vector` pgvector хранит численное представление; query vectors приводятся к той же float32 precision до сравнения. Для вычисления cosine обе стороны переводятся в float64 и L2-нормируются с проверкой finite/nonzero. Это обеспечивает одинаковую численную подготовку, но не гарантирует идентичные embeddings CPU/MPS.

Для query region i и catalog region j, модели k:

```text
c[k,i,j] = clamp(dot(normalized_q, normalized_c), -1, 1)
s[k,i,j] = (c[k,i,j] + 1) / 2
S[i,j]   = mean(s[k,i,j] for the three fixed models)
```

Никакого порога отбрасывания пар нет. При n query и m catalog regions нужно min(n,m) реальных пар, каждый индекс максимум один раз. Остальные query regions имеют вклад 0. Score фото = сумма выбранных `S` / n. Лишние catalog regions не добавляются в знаменатель. n=0 — фото пропускается до solver; m=0 — каталожное фото не является `OK`, в solver не попадает.

Одна общая assignment определяется по S, а не три разные assignment по моделям. Diagnostic `per_model_pair_scores[k]` = сумма `s[k]` тех же пар / n. Это не вероятность и не калиброванный confidence. Владелец принял среднее трёх моделей и отсутствие пары=0; точное преобразование cosine в шкалу, precision и solver/tie детали приняты в пакете G2. Весь LLD не утверждён.

## 7. Оптимальное сопоставление без новой зависимости

В gate3 lock SciPy отсутствует. Для малых наборов предлагаем точный subset-DP стандартной библиотекой, а не добавление solver dependency и не жадный алгоритм. Размер состояния зависит от меньшего набора:

- n≤m: последовательно обходить catalog columns; состояние — mask уже назначенных query rows. Переход: пропустить catalog column либо назначить её одной свободной query row. Финал — все n query rows назначены.
- n>m: последовательно обходить query rows; состояние — mask уже использованных catalog columns. Переход: оставить query row без пары (0) либо назначить свободную catalog column. Финал — все m catalog columns использованы.

На каждое состояние хранить лучшую сумму и assignment. По равенству суммы выбрать лексикографически меньший tuple назначений в порядке query ordinal; реальные catalog ordinals раньше null. Обход ordinals возрастающий. Не добавлять epsilon к сходствам ради tie-break. Сравнение float64, точное равенство вычисленных сумм; допускаемое отличие от high-precision reference в тесте 1e-12, не UI rounding.

Оценка сложности: `O(max(n,m) * min(n,m) * 2^min(n,m))`, плюс хранение assignment. До обхода вычислить число ожидаемых states и проверить принятый лимит; превышение — `RESOURCE_LIMIT`, не truncation областей. Лимиты необходимо выбрать по synthetic ресурсной проверке. Если DP не помещается в принятые пределы, новый polynomial solver — отдельное техническое решение; первая версия не делает fallback молча.

Пример, показывающий отличие от greedy:

```text
S = [[0.90, 0.80],
     [0.85, 0.10]]
optimal pairs: q1->c2, q2->c1
photo score = (0.80 + 0.85) / 2 = 0.825
```

Missing example: три query regions, два catalog, лучшие неповторяющиеся вклады 0.9/0.6 → `(0.9+0.6+0)/3=0.5`. Это синтетические матрицы, не outputs модели.

## 8. Ракурсы, чтение каталога и top-10

Repository читает все `OK` фото закреплённой READY representation, сортировка `(product_record_id, photo_ordinal, region_ordinal, model_key)`. Для каждого фото получен полный набор моделей. Если READY representation не содержит ни одного OK фото, вернуть INDEX_EMPTY до inference: candidates не публикуются, успешный evaluation run не создаётся, NEW недоступен. Это защитная проверка на чтении даже при наличии publish validation. Нет shortlist 50 по одному ногтю: он мог бы потерять лучший набор. Читать группами одного товара; удерживать только текущий товар и query vectors, не весь restricted индекс.

Для каждой пары query/catalog photos вычислить PairMatch. Score товара — максимум scores. При одинаковом score внутри товара выбрать минимальный query ordinal, затем catalog ordinal. Товары ранжируются по `(-score,product_record_id)`; выдача до 10 уникальных товаров. Поддерживать ограниченный top-10 accumulator; в внутренний snapshot сохранять исходы query photos и диагностику финальных кандидатов, не полный массив всех сравнений.

Дополнительные фото не дают отдельный бонус. Exact duplicate upload отклоняется существующим SHA-правилом; если эквивалентный ракурс всё же обработан, максимум не повышается из-за количества. Риск: одно удачное совпадение может превосходить несколько чуть менее сильных; специального бонуса числа ногтей нет.

## 9. Физическая модель — G3 APPROVED_BY_OWNER

Схема принята ограниченным пакетом G3; ниже сохранено её архитектурное описание. Migration `0009_nail_search_v1` и repository реализованы/проверены на synthetic DB, но к рабочей БД не применялись. PostgreSQL/pgvector переиспользуются; raw models/inputs/crops вне Git, SQL содержит private runtime locators.

| Таблица | Поля и ограничения |
|---|---|
| `search_representations` | `id uuid PK`, `corpus_version_id int FK`, `fingerprint char(64) UNIQUE NOT NULL`, `status text CHECK BUILDING/READY/FAILED`, `profile jsonb NOT NULL`, `inventory_sha256 char(64)`, timestamps |
| `representation_models` | `(representation_id uuid,model_key text) PK`, `revision text`, `manifest_sha256 char(64)`, `dimension int CHECK >0`; FK representation |
| `catalog_photos` | `id uuid PK`, `representation_id uuid FK`, `product_record_id int FK`, `ordinal int CHECK >0`, `input_sha256 char(64)`, `source_locator text`, `status text CHECK PENDING/OK/NO_NAILS/ERROR`, `error_code text NULL`; UNIQUE(rep,product,ordinal), UNIQUE(id,rep) |
| `nail_regions` | `id uuid PK`, `representation_id uuid`, `catalog_photo_id uuid`, `ordinal int CHECK >0`, `detector_box jsonb`, `crop_box jsonb`, `mask_locator text`, `crop_locator text`, `crop_sha256 char(64)`; FK(photo_id,rep) to catalog_photos(id,rep); UNIQUE(photo,ordinal), UNIQUE(id,rep) |
| `nail_embeddings` | `representation_id uuid`, `region_id uuid`, `model_key text`, `dimension int`, `embedding vector NOT NULL`; PK(rep,region,model); composite FK(region,rep), FK(rep,model), FK(rep,model,dimension) to model dimension identity |
| `search_active_representations` | `mode text PK`, `representation_id uuid FK NOT NULL`; одна строка для nail-search-v1, READY проверяется publish transaction |

Для всех шести новых таблиц **все перечисленные поля обязательны и NOT NULL**, кроме явно nullable `catalog_photos.error_code`; `error_code` разрешён только для NO_NAILS/ERROR и запрещён для PENDING/OK. Это включает PK/FK, representation/model identity, status, dimension, ordinal, checksums, locators, profile и timestamps. Отсутствие полей у неполученных областей выражается отсутствием строк regions/embeddings, а не NULL в ownership. Поля старого evaluation расширяются по отдельной nullability §12.

Для dimension FK добавить UNIQUE(rep,model,dimension) в representation_models. CHECK `vector_dims(embedding)=dimension`; соответствие размерности модели дополнительно обеспечено composite FK. Это использует документированную возможность [pgvector](https://github.com/pgvector/pgvector#can-i-store-vectors-with-more-precision); constraints проектируются согласно [PostgreSQL](https://www.postgresql.org/docs/current/ddl-constraints.html), версию установленного расширения проверить до migration.

Связь товара с версией корпуса проверяется FK плюс constraint trigger при записи catalog photo: `product_records.corpus_version_id` должен совпасть с representation.corpus_version_id. Обычный CHECK не должен читать другую таблицу. Region/embedding таблицы не допускают смешения representation благодаря composite FK. Delete representation запрещён при active pointer или сохранённом evidence; cascade внутри непубличного build только через явную разрешённую cleanup операцию.

`OK` photo: error_code NULL и regions>0 с полными embeddings; `NO_NAILS`: error_code `DETECTOR_NO_MATCH`, regions=0; ERROR: непустой code, непубликуемые производные. Cardinality и completeness между таблицами проверяются readiness transaction, а не ненадёжным row CHECK. Все build writes и publish берут `FOR UPDATE` lock родительской representation, затем проверяют status; это предотвращает запись, начатую до publish и законченную после. READY запрещает изменения profile/photo/region/model/vector через DB trigger; исключение только controlled retention запрещено для каталога без отдельной политики удаления.

## 10. Build и миграции

Build создаёт одну BUILDING representation и immutable inventory. Успешное фото: записать crops/masks во внешний staging → checksum → atomic rename в собственный namespace → транзакционно записать regions, все три embeddings и OK. Ошибка DB: удалить только файлы данной незавершённой photo operation; crash-orphans удаляются по ownership manifest, не по произвольному пути. NO_NAILS имеет terminal запись без regions.

Resume разрешён только для того же inventory/config/lock fingerprint; существующие OK проверяются checksums/completeness, не пересчитываются. Partial фото не становится OK. ERROR после уточнения причины требует явного build retry, не автоматически открывает старый claim эксперимента. Готовность: есть хотя бы одно OK фото, нет PENDING/ERROR, все OK полны, coverage report отдельно перечисляет товары без OK. Последнее исключение принимает владелец до publish. Полностью пустое представление не публикуется: INDEX_EMPTY, BUILDING остаётся неактивным; принятие coverage-исключений не отменяет этот запрет.

Publish под блокировкой representation в одной DB transaction повторно проверяет completeness, устанавливает READY и обновляет active pointer. Старый pointer запоминается в отчёте; откат изменяет pointer/режим, не удаляет старые записи.

Миграция добавляется после реального Alembic head в целевой ветке; номер здесь не резервируется. В одной additive migration: шесть таблиц и constraints/триггеры выше, дополнительные evaluation-поля из §12. Новые индексы — обычные B-tree по FK/ключам обхода; ANN не вводится. Существующие `product_embeddings` и `model_artifacts` не перезаписываются.

Downgrade отказывает, если есть active nail pointer, новая representation или nail evaluation evidence: нельзя удалить данные ради отката кода. На пустой synthetic DB проверить upgrade→downgrade→upgrade; на synthetic заполненной — отказ downgrade без потери данных. Действующая БД мигрируется только отдельной разрешённой операцией.

## 11. HTTP и состояние сессии

Переиспользовать `/search`, `/search/additional`, `/search/rerun`, существующие endpoints разметки; отдельный публичный API выделения не добавлять. Режим выбирается server config, а не произвольным полем upload. Существующие лимиты: JPEG/PNG, 20 MiB на файл, 4 фото, 80 MiB на сессию, staging TTL 2 часа; [upload validation](../../../../../.codex/worktrees/1eaf/Ai/src/product_search/web/upload_validation.py) и session store — источник. Изменение этих limits не входит в LLD.

Предложение ответа успешного нового режима:

```json
{
  "status": "OK",
  "search_mode": "nail-search-v1",
  "score_kind": "nail_assignment_mean_v1",
  "representation_id": "<opaque UUID>",
  "evaluation_token": "<opaque token>",
  "photo_count": 2,
  "skipped_photo_ordinals": [1],
  "labels_reset": true,
  "candidates": [{
    "candidate_id": "<internal product record id>",
    "rank": 1,
    "score": 0.825,
    "display_photo_ordinal": 2
  }]
}
```

Пример схематический, ID placeholders, не реальный payload. В runtime candidate_id остаётся int. `score_notice`: «Оценка сходства не является вероятностью». `display_photo_ordinal` указывает query фото лучшей пары; карточка товара продолжает показывать разрешённое основное фото через существующий endpoint. ID catalog photo и пары регионов не публикуются в обычном UI.

Все NO_NAILS: HTTP 200, `status=NEED_MORE_PHOTOS`, candidates=[], photo_count, token и пояснение. Это **не успешная пустая выдача**: кнопки `NEW` и финализации отключены, evaluation run не регистрируется. Сессия сохраняется до TTL/добавления/отказа. При первом успешном rerun зарегистрировать PendingEvaluation, если раньше её не было; `/additional` не должен требовать ещё отсутствующую evaluation запись.

Действующие upload отказы 413/415 сохраняются. Технический отказ после upload: INVALID_OUTPUT — 422; BUSY/MODEL/RESOURCE/PROFILE_MISMATCH/INDEX_NOT_READY/INDEX_EMPTY — 503; сессионный конфликт — 409. Санитизированный code/message; нет automatic whole-image fallback. HTTP timeout не прерывает native ML.

Валидный `/additional` атомарно добавляет исходные фото, но не считается выполненным новым поиском. Если rerun не удался, последнюю выдачу оставить видимой с отметкой «не обновлена». Финализация запрещена, пока ordered photo checksums текущей сессии не совпадают с input list последнего успешного run. Иначе можно сохранить разметку старых кандидатов как результат новых фото.

После успешного rerun заменить candidates и сбросить черновую разметку. При отказе не сбрасывать прошлую разметку и не дописывать новый успешный run; финализация всё равно disabled до согласованного run. Фото/token/paths не входят в журналы ошибок.

## 12. Совместимость score и evidence

Существующий UI выводит `RRF`, repository обращается к `candidate["rrf_score"]`, а `_v3_snapshot` сохраняет только model revisions и photo-model results. Нельзя вставить новый float в `rrf_score` и считать изменение совместимым.

Additive изменения:

- `evaluation_candidates`: `search_score` double precision и `score_kind` text, после backfill оба NOT NULL; legacy rrf_score становится nullable. Старые строки backfill `score_kind=rrf_v1`, `search_score=rrf_score`; legacy значения сохраняются. CHECK: score_kind=rrf_v1 требует rrf_score, nail score требует rrf_score NULL и search_score в [0,1]. `per_model_ranks` для nail режима пустой map, а не выдуманные ранги.
- `evaluation_examples`: nullable `search_mode` и `representation_id` FK; legacy backfill режим whole-image, без representation.
- `evaluation_run_snapshots`: nullable `search_mode`, `representation_id` FK, `score_kind`, `search_payload jsonb`. Старые model_revisions/photo_model_results остаются неизменными; новые nail snapshots заполняют versioned search_payload, не выдавая свою диагностику за legacy ранги. Для обязательных существующих колонок model_revisions содержит реальные revisions трёх моделей, photo_model_results содержит пустой JSON object {}; nail diagnostics находятся только в search_payload.

Для новых evaluation writes mode/score_kind обязательны; допустимые значения ограничены whole-image/nail-search-v1 и rrf_v1/nail_assignment_mean_v1. Legacy NULL допускается только для исторических snapshots без нового payload. Conditional constraints: nail example требует representation_id; nail snapshot требует representation_id, nail score_kind и non-null object search_payload с schema_version=1; whole-image не имеет nail representation/payload и использует rrf_v1. Явные IS NOT NULL обязательны, чтобы CHECK не пропускал NULL. Constraint trigger проверяет соответствие corpus версии representation и example; snapshot имеет ту же representation/mode, что example; candidate score_kind согласован с режимом его example. Проверки выполняются для INSERT/UPDATE всех вовлечённых строк; referenced READY representation immutable и защищена от удаления. Старые historical строки не получают выдуманную representation.

В search_payload: `schema_version=1`, fingerprint, ordered input checksums/outcomes, profile/model revisions, top-10 ranks/scores, winning photo identity и pairs/missing regions. Сохранять JSON только restricted в БД, не Git/лог. Не сохранять embeddings или raw crop pixels в snapshot. Evidence не даёт восстановить потерянные transient query crops; durable исходные фото сохраняются действующим evaluation lifecycle и позволяют пересчитать только по отдельному разрешению.

Generic score DTO mapper: whole-image legacy выводит существующий `rrf_score` и дополнительно score_kind/score; nail mode выводит только новую семантику. UI показывает «Сходство» для nail mode, не «RRF» или процент вероятности. Evaluation repository ветвится по score_kind; ни новый формат, ни legacy не читаются через эвристическое отсутствие поля.

Сессия и pending evaluation обновляются staged copy под session lock: подготовить DTO/run, проверить invariants, затем единым commit присвоить обе версии in-memory state. Не повторять текущий порядок «дописать session.run → упасть при обновлении pending». Финальная запись example/candidates/annotations/snapshots в одной DB transaction; failure не завершает сессию. После success очищаются временные производные и pending data; durable evidence удаляется только существующей retention-политикой.

## 13. Модели, исполнение и cleanup

Основное приложение держит process-local query lock, non-blocking до executor, BUSY без очереди. I-service держит собственный admission lock/единственный inference executor. Runtime I отделён; backend не загружает его библиотеки/веса. Native ML не блокирует HTTP event loop. Cancel backend не освобождает locks I-service до actual completion.

Межпроцессная device lease охватывает actual load/inference/unload I и model load/encode/unload embeddings. Её получает исполняющий процесс; backend не держит её, ожидая POST, поэтому нет вложенного deadlock. Отдельная coordinator lease app/batch не захватывается HTTP-сервисом I. Формат/private root/безопасный file lock и cleanup задаёт внешний runner, не ядро. Ошибка общего ресурса может затронуть оба процесса; memory residency двух окружений и временных PNG/Base64 копий ещё не измерена.

Одна instance I на service процесс; embedding providers используются последовательно. Runtime_profile содержит две environment identities, actual extractor fingerprint и выбранный lifecycle. del/перезапуск не объявляются доказательством освобождения accelerator memory. На add/rerun пересчитывается весь накопленный запрос, persistent feature cache не добавляется.

Query RGB/crops/masks остаются restricted в памяти задания; client/server освобождают references и SDK/Pillow buffers в finally. I не сохраняет input/output. Framework spool требует private namespace и cleanup по контракту. Catalog производные сохраняет image-store adapter с прежними 0700/root/symlink проверками. HTTP не принимает private paths.

Session operation lease удерживает используемые исходные фото до завершения локального задания и закрытия HTTP передачи. I работает с собственной копией bytes: после прекращения upload он не зависит от исходного file path. При потере клиента backend не публикует новый run, service продолжает/заканчивает отдельно. Late response не дописывает snapshot; перед staged commit проверяются актуальность сессии и input revision. TTL/discard, stale finalize и atomic evidence из §11–12 сохраняются.

Timeout/request_id/retry/readiness и restart I — по [контракту §7](candidate-i-http-contract.md#7-занятость-deadline-и-общий-ресурс-mac). Restart I не очищает каталог/БД/evidence. NO_NAILS sessions имеют TTL. Новая очередь/jobs и автоматическая CPU policy не вводятся. Model-backed launch пока NOT_RUN; обязательные finite limits/deadlines подготавливаются в runtime bill, ручной контроль размеров фото владельцем сохранён.

## 14. Проверки реализации — NOT_RUN

| Группа | Существенные сценарии и ожидаемый результат |
|---|---|
| Processor | EXIF/alpha/white background, half-open mask bbox, одинаковый crop fingerprint для обеих сторон; неправильная mask отклоняет всё фото |
| Направление зависимостей | AST/import проверка новых core файлов: только стандартная библиотека, nail DTO/ports/core; нет experiments/Pillow/ML/DB/web/settings/I/O imports, включая импорты ради type hints; fake use cases запускаются без ML/DB frameworks |
| Контракты портов | Один набор synthetic contract cases для fake и внешнего mapper: byte lengths, mask 0/255, порядок, typed errors, model dimensions, отсутствие SDK объектов в DTO; реальные adapter smoke отдельно NOT_RUN |
| Adapter | HTTP strict schema/identity/checksum, fake server и real service mapper; Mapping SUCCESS/DETECTOR_NO_MATCH/SEGMENTER_EMPTY/MODEL_ERROR; технический исход не становится NO_NAILS; временные объекты закрыты, fingerprint/device совпадает |
| Solver | Пример greedy trap; n<m/n=m/n>m; все равные/нулевые сходства; global optimum vs independent exhaustive enumeration малых synthetic матриц; no duplicates; missing0; reproducible ties |
| Score | Float32 input и float64 cosine; finite/dimension/norm checks; mean общего assignment; число моделей ровно три |
| Ракурсы | Лучший позже добавленный ракурс, дубликат, каталог с несколькими фото, stable ties; no bonus числа фото |
| Repository | NULL обязательных identity/ownership/status/dimension/profile/ordinal/locator/checksum полей отклонён; Cross-representation/corpus/dimension отказ; incomplete фото не READY; READY immutability; all-NO_NAILS build не публикуется, защитный INDEX_EMPTY не создаёт run/NEW; publish/rollback атомарны |
| Migration | Пустой upgrade/downgrade/upgrade; NOT NULL и правила nullable error_code проверены на каждой новой таблице; populated отказ downgrade; legacy RRF сохранён; новый score не записан как RRF |
| HTTP/session | Все NO_NAILS → NEED_MORE, нет NEW; первый success после NO_NAILS создаёт pending; неуспешный rerun сохраняет старую выдачу, но блокирует stale finalize; successful rerun reset labels |
| Lifecycle | BUSY без очереди; cancel/timeout не освобождает service/device lease; backend не держит device lease при HTTP; actual identity mismatch до inference; app/batch coordinator конфликт; буферы/spool cleanup |
| Evidence | Generic score mapping; final transaction rollback; отказ nail evidence без mode/representation/payload и при несогласованном corpus/score_kind; обязательные legacy JSON колонки явно заполнены; правильный fingerprint/input list; старые snapshots читаются по старой semantics |

Проверки без реальных моделей используют fake adapters/providers и synthetic matrices/files. Model smoke и synthetic segmenter/providers выполняются только по плану раздельного Mac/HTTP-контура после отдельного разрешения. Restricted corpus, качество, пороги, активация и runtime latency — отдельные gates. Unit tests не доказывают улучшение выдачи.

## 15. Остаточные решения и порядок реализации

| Открыто | Влияние / закрытие |
|---|---|
| Раздельные locks, HTTP deadline/device lifecycle | Раздельный runtime bill → технический результат HTTP-контура → принятие; реальные модели пока не интегрировать |
| Decoded pixels, MAX_REGION_COUNT, solver-state/memory/time budget | Нужны заранее принятые resource limits; отсутствие значений блокирует запуск, не немодельное ядро |
| Crop, mean/fusion, missing0 и отсутствие бонуса | Правила и точные numeric/precision/solver/tie детали приняты в G2; synthetic US2 проверен. Остальные поля LLD вне G2 сохраняют статус проекта |
| Ошибки, покрытие каталога, stale finalize, schema миграция | Утвердить предложения документа; ограничения старого результата не меняются молча |
| Inventory всех доступных фото | Проверить доступность/принадлежность до build; число основных фото не равно числу всех ракурсов |
| Качество и уверенное завершение Mac-тестирования | Принят top-10/желательный top-3 и ручная оценка; состав примеров UNKNOWN. COMPATIBLE_HTTP_PROFILE не равно готовому продукту |

После утверждения выбранных контрактов: DTO/ports + чистый matcher + processor с fake портами → схема/repository на synthetic БД → HTTP/session/evidence → раздельный Mac/HTTP profile → разрешённый synthetic ML smoke → отдельно разрешённый build и ручная оценка владельца. Изменения утверждённых аналитических требований синхронизировать в их канонических ART и актуальных реестрах целевой ветки; этот LLD не меняет их статусы сам.

Перед реализацией сверить целевой checkout, ветку, HEAD и незакоммиченные изменения. Описанные исходники относятся к `codex/gate-4-manual-testing` в `1eaf/Ai`; основной checkout с документацией не содержит весь поздний поисковый код. Исторические HEAD выше не подменяют проверку текущего состояния. Это применение действующих границ работы, а не выбор новой целевой ветки.

| Этап | Что проверять перед переходом дальше |
|---|---|
| Чистое ядро и заменители моделей | TDD на синтетических матрицах и заранее заданных ответах; независимый эталон для оптимума и негативные сценарии §14 |
| Схема и repository | Инварианты и миграции на отдельной разрешённой тестовой БД; действующая БД не является стендом |
| HTTP, сессии и evidence | Поведение без реальных моделей: отсутствие ногтей, отказ пересчёта, запрет сохранения устаревшей выдачи и атомарность записи |
| Раздельные среды, HTTP и реальные модели | Проверки [плана Mac](mac-common-environment-plan.md) после разрешения на конкретную сборку и модельные вызовы |
| Каталог и качество | Отдельно разрешённая подготовка и оценка по согласованным выборке и критериям |

Команды проверки выбираются по фактическому коду и окружению целевого checkout. Существующие `make test` и `make lint` сами по себе не подтверждают покрытие нового режима. Завершённый этап передаётся следующему чату с результатом, выполненными проверками и оставшимися ограничениями по [методу разработки](../development-method.md#обвязка-агента-и-передача-контекста).

Книжные правила: APoSD mini для скрытия preprocessing/orchestration; Clean Architecture mini для чистого solver; commit `893a88a6fce3a80c565bf39ac65021b43a8b2990`. Ponytail: стандартная библиотека для малых assignment, existing providers/DB/UI; экспоненциальный предел DP назван явно.

## 16. Историческая проверка документа v0.1 — 2026-10-04

Self-check: PASS — 44 относительные ссылки в LLD/HLD/навигации, таблицы, Markdown fences, маркеры и `git diff --check`; это проверка документа, не runtime. Независимое read-only review `/root/nail_search_docs_review`: первое REWORK — 0 Critical / 1 Major / 0 Minor (неполная nullability схемы); обязательные NOT NULL и проверки отказа уточнены. Повторное review: PASS — 0 Critical / 0 Major / 0 Minor, 2026-10-04. Один цикл исправления дефекта. История v0.1: подготовлен проект LLD, код/миграции не написаны, зависимости не установлены, модели/БД не запускались.


Актуальная сквозная проверка и история исправлений: [отчёт аудита пакета](nail-search-documents-review.md). Предыдущие локальные review выше являются историческими.


Метод выполнения последующей разработки утверждён отдельно: [TDD по умолчанию и способы проверки](../development-method.md). Это не утверждение технических предложений LLD.


## 17. Редакция v0.3 — гексагональная граница, 2026-10-06

Book-guidance: основной набор Clean Architecture `mini`, commit `893a88a6fce3a80c565bf39ac65021b43a8b2990`. Прямой concrete I-вызов и Pillow в provider contract заменены на application-owned ports и внешние mappers; проверка — ограничение импортов, fake use cases и contract cases §14. APoSD не подключался повторно: прежняя запись относится к истории v0.1. Формула, schema, lifecycle restrictions и операционные gates сохранены. Порты/DTO на момент v0.4 были PROPOSED; последующее ограниченное утверждение G2 указано ниже. Новый self-check/review находится в [отчёте](nail-search-documents-review.md).

### Утверждение G2 и synthetic реализация — 2026-10-07

Владелец утвердил [ограниченный пакет G2](../../specs/candidate-i-http/g2-core-decisions.md) после объяснения правил. Приняты точные §5–8 и минимальные plain DTO/порты §4 только для US2; schema/build/evaluation/runtime values остаются отложенными. Общие формулировки PROPOSED/PENDING этого документа не отменяют отдельное утверждение G2.

Реализованы T020–T031: файловый адаптер, общий pure processor, matcher, embedding facade с injected factories и ranking use case. Текущий `NailSearchResult` — минимальный synthetic результат, не полный persisted execution/evaluation snapshot; внешний verified runner ещё не реализован. Производные принадлежат создавшему экземпляру store; persisted build ownership/resume относится к US3. Подробные проверки и ограничения — [execution-context](../../specs/candidate-i-http/execution-context.md#synthetic-us2--t020t031). Real модели/DB/corpus и продуктовый Web не запускались.

### G3 и реализованные границы — 2026-10-08

Владелец отдельно утвердил [schema/coverage/evidence/session пакет G3](../../specs/candidate-i-http/g3-storage-decisions.md), disposable synthetic DB и test-only pgvector0.5.0 install. Общие исторические PROPOSED/PENDING формулировки выше не отменяют эти конкретные approvals. Остальной LLD, real runtime profile/bills и operating limits не утверждаются автоматически.

T032–T042 реализованы: additive migration/repository, build/resume/coverage, durable artifact ownership, `NailEvaluationPort.save_finalized(EvaluationBundle)`, native query executor и Web/session/pending staged update. Model-free main assembly принимает injected runner; actual context verification factory, device binding и real CLI assembly остаются G4/G5. Для новой DB schema выбирается `score_schema=True`, включая legacy RRF writes; default False сохраняет старую schema. Internal product record ID в new DTO integer, сортировка числовая. Build inventory должен быть канонически упорядочен до persistence; decode/region/solver/manifest/memory/deadline production values требуют отдельной проверки.

Новый результат и evidence по-прежнему не являются вероятностью или автоматическим NEW. [Отчёт с командами/ограничениями](../../specs/candidate-i-http/execution-context.md#synthetic-us3--t032t042): 303 scoped tests PASS, final review PASS 0/0/0; full collection blocked тремя model-dependent modules. Diagram rendering, real models/corpus/search quality и working DB migration/activation не проверялись.


## 18. Редакция v0.4 — HTTP-контракт, 2026-10-07

Отдельный сервис и direct POST выбраны владельцем; [API поля/форматы/lifecycle v0.1](candidate-i-http-contract.md) утверждены владельцем 2026-10-07. Остальная техническая спецификация сохраняет свой статус. Принятые правила поиска не разрешают новую schema/установку/inference автоматически. Top-10 обязателен на проверенных владельцем примерах, top-3 желателен; NEW определяется владельцем после просмотра. Backlog не обобщает ядро. Новый review — в [отчёте](nail-search-documents-review.md).
