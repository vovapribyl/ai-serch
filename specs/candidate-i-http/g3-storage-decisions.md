# G3 — хранение каталога, evidence и тестовая БД

Дата: 2026-10-07. **APPROVED_BY_OWNER**.

Основание подготовки: первое «Разрешаю» на предложение подготовить G3. После предъявления готового пакета и вопроса об утверждении схемы и создании отдельной тестовой БД владелец повторно ответил «Разрешаю». Это утверждает пакет и описанный disposable synthetic контур; download/install остаются отдельным разрешением. G3 здесь — локальный gate feature Candidate I, не исторический Gate 3 всего проекта.

## План-контракт

FULL: выделить schema/coverage/evidence/session правила из [LLD §9–12](../../docs/architecture/nail-search-lld.md#9-предлагаемая-физическая-модель) → проверить совместимость с реализованным US2 и legacy → независимое read-only review → исправления → решение владельца. В этой подготовке не создаются migration/repository, контейнеры или БД; не читаются рабочие credentials/данные.

Ponytail full: PostgreSQL/pgvector, существующие evaluation и маршруты Web; только необходимые шесть таблиц, обычные B-tree, без ANN, очереди и нового публичного API. Book-guidance Clean Architecture mini, commit `893a88a6fce3a80c565bf39ac65021b43a8b2990`: правила readiness принадлежат core/build use case, SQL и транзакции — внешнему адаптеру; ядро не получает ORM/session objects.

## Простыми словами

Сейчас поиск умеет работать с искусственным каталогом в памяти. Следующий этап должен научить его сохранять подготовленный каталог и читать его из БД. **Representation** — одна зафиксированная версия подготовки: какие исходные фото использовали, какие модели и настройки применили, какие маски и векторы получили.

Одна версия сначала собирается, затем проверяется и только отдельной разрешённой публикацией становится доступной поиску. Если новая версия не готова, поиск продолжает использовать прежнюю. После публикации её содержимое не редактируется: для других моделей или правил создаётся другая версия.

## Предлагаемая схема

Поля и связи берутся из LLD §9; этот пакет принимает именно перечисленные поля/ограничения, а не произвольные последующие дополнения.

| Таблица | Что хранит | Обязательные поля / ключи |
|---|---|---|
| `search_representations` | Версия подготовленного каталога | UUID `id`; `corpus_version_id` FK; unique SHA-256 `fingerprint`; `status` BUILDING/READY/FAILED; `profile` JSONB; `inventory_sha256`; `created_at`, `updated_at` timestamptz |
| `representation_models` | Точные модели этой версии | PK `(representation_id,model_key)`; FK representation; `revision`, `manifest_sha256`, `dimension`; unique `(representation_id,model_key,dimension)` |
| `catalog_photos` | Исходные фото товаров и исход обработки | UUID `id`; FK representation/product; положительный `ordinal`; `input_sha256`, private `source_locator`; `status` PENDING/OK/NO_NAILS/ERROR; nullable `error_code`; unique `(representation_id,product_record_id,ordinal)` и `(id,representation_id)` |
| `nail_regions` | Области одного фото | UUID `id`; `representation_id`, `catalog_photo_id`; положительный `ordinal`; `detector_box`, `crop_box` JSONB; private `mask_locator`, `crop_locator`; `crop_sha256`; composite FK фото/representation; unique `(catalog_photo_id,ordinal)` и `(id,representation_id)` |
| `nail_embeddings` | Вектор области от конкретной модели | PK `(representation_id,region_id,model_key)`; `dimension`, `embedding vector`; composite FK region/representation и model/representation/dimension; `vector_dims(embedding)=dimension` |
| `search_active_representations` | Какую готовую версию использовать новым сессиям | PK `mode`, для текущей feature `nail-search-v1`; FK `representation_id`; READY проверяется при публикации |

Все перечисленные поля NOT NULL, кроме `catalog_photos.error_code`. Формат SHA-256, геометрия, identity и полный набор моделей проверяются по принятому G2/HTTP и LLD; таблица не заменяет семантическую валидацию. Размерности фиксированных моделей — 512/768/768; произвольный неполный набор не становится READY.

`product_record_id` в существующей БД — integer FK, не внешний товарный код. Реализованный synthetic US2 использовал строковые fake ID. Для US3 предлагается выровнять только DTO внутреннего product record ID с integer и сохранить числовой tie-break `(-score,product_record_id)`; SQL-группы также идут по integer ID. Нельзя сортировать строковые «10» перед «2» и менять тем самым выбор при равных scores. Это необходимая коррекция интеграции, с RED→GREEN и регрессией US2, без переименования внешних товарных кодов или изменения схемы legacy ID.

Cross-table проверки: товар принадлежит той же версии корпуса, что representation; область/вектор принадлежат её фото/модели; evaluation относится к тому же corpus/representation/mode. Composite FK и constraint triggers обеспечивают связи; обычный CHECK не читает другие таблицы.

`error_code`: PENDING/OK → NULL; NO_NAILS → DETECTOR_NO_MATCH и без regions; ERROR → непустой код, без успешного частичного результата. OK → непустой набор областей с тремя корректными векторами на каждую. Cardinality/completeness проверяются в readiness transaction, а не только row CHECK.

## Сборка и готовность

1. Создать BUILDING и immutable inventory. Доступ/принадлежность исходников проверяются до разрешённого build; этот пакет не разрешает чтение реального корпуса.
2. Фото записать атомарно: внешние masks/crops в staging → checksums → atomic rename в собственный namespace → все строки областей/векторов и OK одной DB transaction. NO_NAILS — terminal запись без областей. DB отказ удаляет только производные данной незавершённой операции; crash cleanup использует ownership manifest.
3. Resume — только с теми же inventory/profile/lock fingerprint. Уже OK фото проверить по checksums/completeness, не пересчитывать. Retry ERROR требует явного решения, не автоматического повтора.
4. Готовность: хотя бы одно OK, нет PENDING/ERROR, все OK полны. Отдельный coverage report перечисляет товары без OK-фото. Их исключение принимает владелец перед реальной публикацией. Полностью пустую версию нельзя опубликовать даже с принятым coverage exception.
5. Build writes и publish блокируют родительскую representation `FOR UPDATE`. Publish повторно проверяет readiness, переводит в READY и атомарно меняет pointer с compare-and-set по ожидаемому прежнему pointer. Конкурентное изменение → отказ без частичной публикации.
6. READY profile/model/photo/region/vector неизменяемы, что защищают DB triggers. Сохранённая evaluation или active pointer запрещает удаление representation. Rollback меняет pointer/режим, сохраняя старые данные; не освобождает право на произвольное удаление.

**Условный пример:** товар A имеет OK-фото, товар B — только NO_NAILS. Версия может пройти техническую готовность, но B попадёт в coverage report и потребует решения владельца до реальной публикации. Если у A также нет OK, версию не публикуем вовсе. Это искусственный пример, не оценка текущего корпуса.

## Evidence и состояние Web

Принимаются additive изменения LLD §12:

- `evaluation_candidates`: `search_score` и `score_kind` обязательны после backfill. Legacy: `search_score=rrf_score`, `score_kind=rrf_v1`, прежний RRF сохранён. Nail: `rrf_score=NULL`, `score_kind=nail_assignment_mean_v1`, score в [0,1], `per_model_ranks={}`.
- `evaluation_examples`: `search_mode`, `representation_id` FK; legacy backfill whole-image без выдуманной representation.
- `evaluation_run_snapshots`: `search_mode`, `representation_id`, `score_kind`, versioned `search_payload` JSONB. Historical NULL допустим только для старых snapshots без нового payload. Новые writes требуют mode/score identity; conditional CHECK явно проверяют NOT NULL. Nail payload — object с `schema_version=1`; реальные model revisions сохраняются в существующей колонке, `photo_model_results={}`.
- Payload содержит fingerprint, ordered исходы/checksums входных фото, profile/revisions, ranks/scores финальных кандидатов, winning photo/pairs/missing regions. Без embeddings/raw crop pixels; хранение restricted в БД, не Git/лог.
- Example/candidates/annotations/snapshots сохраняются одной транзакцией. Отказ не завершает сессию. Existing retention сохраняется; новую политику удаления READY каталога не вводим.

Для US3 нужны также правила LLD §11: существующие routes/upload limits, mode из server config; NO_NAILS всех фото → NEED_MORE_PHOTOS, без NEW/finalize/успешной evaluation. Первый успешный rerun создаёт pending evaluation. `/additional` меняет входы; failed rerun сохраняет прежние candidates/labels, но stale finalize запрещён; успешный rerun заменяет выдачу и сбрасывает черновую разметку. Session/pending обновляются staged copy одним commit под lock; late результат не commit. В UI nail score называется «Сходство», не RRF или вероятность. Решение SAME_PRODUCT/NEW принимает владелец после просмотра.

## Миграция и конкретный тестовый контур

Миграция additive после **повторно проверенного** Alembic head. Read-only source inventory текущего worktree: цепочка заканчивается файлом `0008_gate4_multiphoto_v3.py`, revision `0008_gate4_multiphoto_v3`; это не проверка применённого head какой-либо БД. Существующие migrations, `product_embeddings` и `model_artifacts` не переписываются.

Downgrade разрешён только при отсутствии новых representations/active nail pointer/nail evidence. На пустой synthetic DB: upgrade→downgrade→upgrade. На заполненной synthetic DB: downgrade отказывает, данные сохраняются. Для БД с реальными данными downgrade не предлагается.

Read-only inventory на 2026-10-07: выбранный test interpreter имеет SQLAlchemy/psycopg/Alembic; Python package pgvector отсутствует; Docker CLI найден, psql/initdb/pg_ctl не найдены в PATH. Это не подтверждает daemon, сервер, extension или lock compatibility. Установки/запуски не выполнялись.

**Рекомендуемый контур:** один новый disposable PostgreSQL/pgvector контейнер со своими synthetic данными, отдельными случайными credentials, loopback endpoint и отдельным storage namespace. Никаких подключений/volumes действующей БД. Образ/revision/digest, доступность daemon и уже имеющиеся образы установить read-only после принятия пакета; неизвестный image не скачивать молча. По Ponytail существующий SQL vector mapping переиспользуется; отсутствие Python pgvector само по себе не основание установки.

Перед первым DB тестом runner сверяет разрешённые container/storage/database/role identities, уникальный marker тестового контура, endpoint и отсутствие рабочих данных. Несовпадение → STOP. Credentials не выводятся и не попадают в Git. Тесты используют только созданные для этой задачи fake corpus/product/evaluation records. Teardown удаляет только ресурсы подтверждённого тестового контура; existing volumes не трогаются. Точные resource identities формируются при создании, затем закрепляются в private execution context.

## Решение, которое требуется принять

Рекомендация: принять описанные schema/coverage/evidence/session правила для T032–T042 и разрешить создание/тестирование описанного отдельного disposable synthetic DB контура, включая его собственные migrations/teardown. Если понадобятся отсутствующий container image или Python dependency — сначала предъявить конкретный bill и получить отдельное разрешение; сейчас такой download/install не входит в пакет.

Утверждение не разрешает real corpus/build/publish, active pointer действующей системы, миграцию/очистку рабочей БД, real ML, Git publication или backlog. G4/G5 сохраняются. До утверждения G3 T032–T042 не начинаются.

Самопроверка: соответствие LLD/US3 и source migrations, локальные ссылки/маркеры/`git diff --check` PASS. Независимое read-only review `/root/g3_storage_review`: **PASS, 0 Critical / 0 Major / 1 Minor**. Minor — восстановить явный staging/checksum/atomic rename до DB transaction — исправлен и проверен исполнителем; повторное review не требуется по AGENTS.md. Reviewer не запускал Docker/DB/models/tests. Пакет утверждён владельцем; перед DB tests всё ещё обязательна проверка фактической identity нового контура.
