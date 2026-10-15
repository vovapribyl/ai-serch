# LLD: checkpoint файлов и состояния

v1 / APPROVED_BY_OWNER. Worker только пишет attempt-scoped staging и возвращает bounded manifest;
единственный controller проверяет и подтверждает состояние. Worker не commit-ит БД.

## Запись

1. Проверить вход/profile, попытку, бюджет и владение. Staging располагается на том
   же томе, что final; root принадлежит процессу/пользователю, symlink/path escape запрещены.
2. Записать masks/crops либо vectors.json; модельные ключи/region ordinals фиксированы.
   Manifest включает schema_version, attempt/identity, список файлов, размеры и SHA.
   JSON vectors: конечные числа, точная размерность, полный порядок; лимит bytes до parse.
3. Закрыть файлы, проверить состав/хеши/формат; синхронизировать файлы, rename всего
   завершённого каталога попытки в уникальное final место, синхронизировать parent directory.
   Поддержка sync на выбранном Mac-томе проверяется fake native test; при ошибке commit запрещён.
4. Controller делает fenced commit по data-model. Только DB receipt означает COMPLETE.

В final запрещён overwrite. Та же identity/hash возвращает существующий checkpoint;
иная под тем же attempt — ARTIFACT_CONFLICT. Вызовы ML/HTTP не находятся внутри DB transaction.

## Сбои и восстановление

| Граница | Результат |
|---|---|
| До rename | Staging не готов; изоляция частичного результата |
| После rename до commit | Final orphan не переиспользуется без DB checkpoint |
| Commit завершён, ответ потерян | Сверить attempt/identity/hash в БД; не повторять ML |
| Checkpoint есть, файл повреждён | CHECKPOINT_INVALID; перерасчёт по отдельному разрешению |
| Старый worker написал поздний файл | Новый owner не принимает его token; изоляция результата |

Перенос vectors в pgvector формирует PREPARED редакцию. Проверить значения, model
ключи, размерности и порядок относительно checkpoint перед READY; не считать
наличие DB rows доказательством полноты. БД/файлы не имеют общей транзакции.
Описанный sync/rename протокол требует проверки durability; документ её не доказывает.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.
