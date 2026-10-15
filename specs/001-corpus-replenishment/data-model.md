# Модель данных пополнения

v1 / 2026-10-12 / APPROVED_BY_OWNER. Логические сущности и предлагаемые ограничения миграции;
проект не применён к БД. Существующие таблицы legacy не получают новую семантику.
Имена новых таблиц ниже — проектные; FK связываются с baseline после B0.

| Сущность / таблица | Основные поля | Ограничения и связи |
|---|---|---|
| Владение режимом / replenishment_owner | singleton_key, epoch bigint, owner_token UUID, mode, version, updated_at | Одна запись на локальный контур; generation растёт при выдаче/отзыве владения |
| Запуск / replenishment_runs | id UUID, package_sha, owner_token, epoch, status, reason, started_at, finished_at | Пакет immutable; сроки вычисляются из monotonic, wall timestamps только аудит |
| Профиль / processing_profiles | semantic_profile_sha, schema_version, canonical_payload | Immutable; модели/revisions/dimensions/preprocessing/dtype/crop version; SHA проверяет payload |
| Текущая редакция / replenishment_product_heads | corpus_version_id, product_record_id, current_revision_id, version | Unique(corpus_version_id,product_record_id); единственный канонический pointer текущего выбранного списка/профиля; FK revision принадлежит этому товару |
| Редакция товара / product_revisions | id UUID, corpus_version_id, product_record_id, input_set_sha, semantic_profile_sha, version, state | Фиксированный список фото; READY/опубликованная редакция immutable; смена завершённого исхода создаёт новую редакцию |
| Фото / revision_photos | id UUID, revision_id, ordinal, source_ref, input_sha, outcome, error_code | Unique(revision_id,ordinal); PENDING/RUNNING не терминальны; OK/NO_NAILS/ERROR терминальны для текущей редакции |
| Попытка / stage_attempts | id UUID, photo_id, stage_key, model_key, run_id, epoch, state, attempt_no | Unique(photo_id,stage_key,model_key,attempt_no); для локализации model_key пустая строка (не SQL NULL); PENDING→RUNNING→COMPLETE/ERROR/INTERRUPTED |
| Checkpoint / stage_checkpoints | attempt_id, identity_sha, manifest_ref, manifest_sha, profile_sha, completed_at | Unique(attempt_id); COMPLETE только после проверенных файлов и fenced commit |
| Готовые области/векторы | revision_photo_id, region_ordinal, mask_ref, crop_ref, crop_sha, model_key, vector | Отдельные новые данные/таблицы; unique(photo,region,model); FK не дают привязать vector к чужой редакции |
| Снимок / catalog_snapshots | id UUID, semantic_profile_sha, content_sha, state | PREPARED→READY; после READY состав immutable |
| Состав / catalog_snapshot_members | snapshot_id, product_record_id, revision_id | Unique(snapshot_id,product_record_id); только READY совместимые редакции |
| Активный каталог / active_catalog_snapshots | mode_key, snapshot_id, version | Unique(mode_key); новый pointer отдельно от legacy search_active_representations |
| Попытка публикации / publication_attempts | id UUID, revision_id, run_id, epoch, expected_active, state, error_code, receipt_id | RUNNING→SUCCEEDED/FAILED/UNKNOWN; независима от исходов фото; UNKNOWN не даёт автоматический retry |
| Публикация / revision_publications | revision_id, snapshot_id, run_id, published_at | Unique(revision_id); запись в той же транзакции, что active pointer |

Модель не включает удаление исходных записей, retention/GC и смену бизнес-статуса товара.
Ссылки на входы/файлы доступны только частному контуру; raw JSON и source locators
не включаются в Git. Права runtime-каталогов 0700 и файлов 0600 сохраняются.

## Жизненный цикл

Фото OK означает полный согласованный результат, а не наличие crop. NO_NAILS
не содержит encoder vectors. ERROR записывает причину и требует ручного выбора.
INTERRUPTED — отсутствие завершённого результата после остановки, допустимо при resume.
Все фото терминальны + минимум одно OK → редакция READY. Все ERROR/NO_NAILS →
NOT_PUBLISHABLE, а не ошибочная публикация. ERROR публикации хранится отдельно.

При ручном retry терминального фото старая опубликованная редакция не изменяется:
создаётся новая редакция и полный выбранный список, пригодные результаты ссылаются
на прежние immutable artifacts; выбранное фото снова ожидает нужную работу.
Повтор публикации не создаёт новую редакцию, если данные не менялись.

Текущая редакция определяется только replenishment_product_heads, не max(version)
и не активным snapshot. Создание/retry фиксируют новую редакцию и CAS head в одной
транзакции под lock head. Все записи попыток и публикация сверяют head/version;
старую READY редакцию после supersede заново публиковать нельзя. Старый опубликованный
snapshot остаётся доступным до готовности новой текущей редакции.

Попытка публикации RUNNING сохраняется до начала activation transaction. SUCCEEDED
и receipt фиксируются в activation commit вместе с pointer. После известного rollback
отдельная fenced транзакция записывает FAILED/error. Если commit/сохранение error
не подтверждены, RUNNING трактуется как UNKNOWN; reconciliation читает receipt:
есть receipt → SUCCEEDED, нет при подтверждённом rollback → FAILED, неизвестно → UNKNOWN.
Сводка берёт per-revision error/state из publication_attempts, а не только run.reason.
UNKNOWN сначала сверяется; новый ML и автоматический повтор запрещены.

## Identity

Checkpoint identity связывает input_sha, crop_profile/version, region order,
model key/revision/dimension, dtype/preprocessing, semantic profile и попытку.
Полная идентичность определяется hash канонической JSON-формы с версией схемы.
Числа vectors не округляются ради hash. Profile mismatch — отказ, а не silent reuse.

Snapshot content hash содержит упорядоченные product_record_id→revision_id и
semantic_profile_sha. Профиль всех участников сравнивается до PREPARED→READY.
Source baseline MODEL_DIMENSIONS: openclip_b32=512, dinov2_b14=768,
siglip2_b16_224=768; значения сверяются повторно при B0 и не меняют утверждённые модели.

## Транзакции

- Выдача owner epoch + создание run — короткая транзакция; длительную flock держит ОС.
- Checkpoint: lock owner/run/head/revision/attempt, сверить epoch/token/head/version и состояние,
  insert immutable checkpoint, COMPLETE. Несовпадение хеша существующей попытки — конфликт.
- Создание/retry редакции: lock owner→run→head; insert revision и выбранные фото, CAS current_revision_id/version.
- Фото OK: lock owner→run→head→revision→attempt; проверка полноты всех стадий и commit итогового исхода.
- Publication: lock owner/run/head/current revision/active pointer в фиксированном порядке;
  проверить пакет/STOP/expected versions, insert READY snapshot и publication, переключить pointer.
  Проверка текущей редакции не допускает публикацию старой после ручного retry.

Все SQL ожидания ограничены lock_timeout/statement_timeout из остатка deadline.
Типы vector и FK целиком определяются миграцией после B0; существующий published
representation никогда не меняется на месте. Unit-инварианты и adapter-интеграция
проверяются раздельно по TDD.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.

## Статус реализации — 2026-10-13

Миграция0010 создаёт отдельные таблицы этой модели. Защита ключей, неизменности
и версий, фиксация запуска/очереди/стадий проверены на синтетической БД.
[Отчёт](state-adapter-report.md) отделяет реализованные операции от подготовки
готовой редакции, наполнения снимка и публикации, которые ещё предстоят.
В рабочей БД миграция не применялась; утверждённая модель не изменена.
