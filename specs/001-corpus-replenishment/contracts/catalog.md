# LLD: публикация и привязка каталога к runtime

v1 / APPROVED_BY_OWNER. Snapshot имеет свою identity и один semantic profile. Опубликованные
редакции, состав и vectors immutable; GC не входит в первую версию.

## Контракт чтения

resolve_active(mode) → SnapshotDescriptor(snapshot_id, content_sha, profile_sha).
read_snapshot(descriptor) → поток CatalogProduct/PhotoEmbeddings в прежнем порядке:
product_record_id, photo ordinal, region ordinal, модель по MODEL_DIMENSIONS.
Один descriptor закреплён на весь запрос; последующая смена active pointer не
меняет этот запрос. Фото без полного результата отсутствуют в опубликованных данных.

VerifiedCatalogBinding содержит descriptor + проверенный RuntimeIdentity +
полный EmbeddingProfile и разрешённый scope. Валидатор требует совпадения content_sha
с БД, profile со всеми редакциями и runtime model revisions/preprocessing/dtype.
Claim для query inputs и допустимого каталога проверяется отдельно. Ни snapshot_id,
ни одно совпадение model_key не подменяет старые проверки verified runtime.

NailSearchService/read_ready требуют отдельного snapshot path и обновлённых DTO;
legacy representation_id не переименовывается в snapshot_id. Оба пути за config
catalog_backend=legacy|snapshot до cutover; scoring/matching не меняются.

## Публикация

publish_revision(revision, expected_active, owner, run) → receipt / no-op / conflict.
Подготовить полный immutable результат товара, проверить все фото и единство
профиля. Состав нового snapshot — ссылки на прежние READY редакции плюс выбранную
редакцию товара; проверка профиля применяется также ко всем сохранённым товарам.

До activation сохранить publication_attempts(RUNNING). Ошибка известного rollback
записывается отдельно как FAILED/error; потерянный ответ требует reconciliation
receipt, а не автоматического retry. При недоступной БД state остаётся неразрешённым
и показывается как UNKNOWN; окончательная классификация после достоверного чтения.

Одна транзакция в порядке owner→run→product head→revision→active pointer: сверить epoch/token,
run не STOP/EXPIRED, deadline, head.current_revision_id/version и expected_active; закрепить
snapshot READY, publication receipt/SUCCEEDED attempt и новый active pointer. При конфликте rollback,
без автоматического retry. Все DB ожидания bounded. Блокировка защищает от гонок,
но решение о готовности принято ядром из версии состояния, проверяемой при commit.
Создание/retry использует тот же head lock и CAS. Изменившийся head означает
REVISION_SUPERSEDED; прежняя READY редакция не активируется новым commit.

Сигнал STOP сериализуется тем же owner/run lock: если STOP зафиксирован раньше
проверки допуска publication, транзакция не активируется; если commit уже выполнен,
receipt остаётся фактом. Нельзя гарантировать rollback успешно завершённого commit.
После неизвестного ответа read receipt устанавливает факт, без повторного ML.

Идемпотентность по revision_id/receipt: повтор того же результата no-op. Ошибки
публикации отделены от фото; ручной повтор в новом run. Неуспешная новая редакция
не меняет старую. Не публиковать нулевое coverage или незавершённый список.

## Миграция и rollback

После B0 в отдельной test DB создать новые таблицы, read adapter и базовый snapshot
из существующего совместимого READY representation без ML. Сверить состав/hash,
три модели и synthetic legacy/snapshot ranking parity. Рабочая БД и реальный корпус
не мигрируются этим планом. Cutover/rollback — отдельный пакет и owner approval.
Rollback выбирает legacy backend/pointer и закрывает незавершённый новый run;
новые таблицы/исходники не удаляются, новые товары могут отсутствовать в legacy.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.
