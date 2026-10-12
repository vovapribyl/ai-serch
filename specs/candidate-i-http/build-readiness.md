# T050 — inventory входов корпуса Gate 2

Дата: 2026-10-09. T050 выполнен для выбранной активной версии Gate 2 и её основных
фото. Inventory PASS в этом scope; разрешение на build T051 не выдано.

## Основание и scope

Владелец выбрал корпус Gate 2 («Да, используем»), затем ответил «да» на конкретное
предложение запустить существующий `ai_gate2_one_time-database-1` и выполнить один
read-only inventory: связи, файлы, hashes, приватный manifest. [Пакет разрешения](corpus-inventory-permission.md)
прошёл независимое review после исправления границ предыдущего permission.

FULL для фиксации разрешённого операционного перехода; исполнение — один проход по
выбранным входам, самопроверка manifest/агрегатов, один независимый read-only review
документов. Исходный XLSX, другие corpus versions и Candidate J не читались.

## Identity и фактические проверки

Colima запущена ранее; global Docker context остался `default`, команды использовали
явный `--context colima`. Запущен только найденный существующий контейнер Gate 2;
Compose project совпал с `ai_gate2_one_time`. PostgreSQL readiness PASS.

Точечный preflight SELECT выполнен в `BEGIN TRANSACTION READ ONLY`: одна активная
версия, expected import operation совпала с [Gate 2 dossier](../../docs/gate-2.md),
terminal state `SUCCEEDED / ACTIVE / COMPLETE / PUBLISHED`, 674 записи,
migration `0004_import_operations`, `transaction_read_only=on`.

Связи прочитаны один раз в `REPEATABLE READ READ ONLY`, с проверкой active count и
выбранной operation; snapshot сохранён только приватно. Первый вызов preflight
не передал stdin в `docker exec`, SQL не выполнялся; после добавления `-i` preflight
получен успешно. Этот исправленный вызов не был повторным проходом по фото.

| Проверка | Фактический результат |
|---|---|
| Записи выбранной версии / уникальные товары | 674 / 674 |
| Связанные фото / уникальные локаторы | 674 / 674, одно основное фото на товар |
| Читаемые непустые обычные файлы | 674 |
| Совпадение SHA-256 с БД | 674 из 674 |
| Пропуски / ошибки чтения / hash mismatch / изменения во время чтения | 0 / 0 / 0 / 0 |
| Лишние entries в выбранном каталоге / недостающие entries | 0 / 0 |
| Суммарный объём файлов | 339188320 bytes |
| Форматы по декларации БД | PNG 532, JPEG 142; не результат декодирования |
| Уникальные hashes содержимого | 667 |
| Повторяющиеся hashes | 7 групп по 2 фото: 14 фото, 7 дополнительных копий |

Перед чтением проверены один operation root внутри известного приватного runtime,
отсутствие symlink в пути, владелец каталога и однозначность product/photo locators.
Фото открывались только `O_RDONLY|O_NOFOLLOW`; hashes вычислены потоково, metadata
файла до/после чтения совпала. Обычные права исходных файлов и содержимое не менялись.

## Freeze входов

Новый приватный каталог вне Git: `700`; manifest и snapshot связей: `600`.
Manifest содержит фиксированный порядок record IDs, привязки к товарам, приватные
локаторы, declared/actual hashes, sizes, outcomes и accepted runtime fingerprint
из [T049 reference](runtime-profile-reference.md). Точные локаторы и IDs не публикуются.

Manifest SHA-256:
`c7645904d0e71666491f29ef27182c6bda6051e963c640ccb5596ab2af1dc1f5`.

После записи bytes/hash/permissions manifest повторно проверены. Snapshot фиксирует
наблюдаемые входы, не блокирует будущие изменения исходных файлов или active version.
Перед отдельным build нужно снова проверить эту identity и входы по manifest.

## Пробелы и границы следующего шага

- 7 пар одинаковых bytes не доказывают ошибку каталога или одинаковость товаров.
  Не удалять и не объединять записи автоматически; учитывать наблюдение в будущей
  ручной оценке SAME_PRODUCT/NEW.
- Проверена принадлежность по ссылке из каталога, а не визуальное соответствие фото
  товару. Другие возможные фото товаров вне Gate 2 primary scope — `UNKNOWN`.
- Декодирование, dimensions/EXIF, детекция ногтей, crop/vector outcomes, coverage
  новой representation и качество выдачи не проверялись. Inventory не означает READY.
- Build target DB/representation, допустимые записи в нём, actual build assembly,
  конечные operation/time/resource bounds и обработка STOP должны быть определены
  в отдельном пакете T051. Gate 2 schema `0004` не является доказательством готовности
  хранилища новой representation; migrate рабочую Gate 2 DB не разрешено.

Следующий шаг — подготовить конкретный T051 build bill на эти входы и принятый G4
runtime. ML/build/query/publish/activation требуют соответствующего отдельного
разрешения; новый model window не открыт. Запущенный по разрешению контейнер Gate 2
оставлен работающим; другие контейнеры намеренно не запускались.

## Итоговая проверка

Saved manifest integrity/permissions/674 outcomes, ссылки/таблицы/статусы/
conflict markers/whitespace PASS; `git diff --check` PASS для tracked diff,
изменённые untracked документы дополнительно проверены напрямую. T050 `[x]`,
T051–T057 `[ ]`. Independent final read-only review PASS: 0 Critical / 0 Major /
0 Minor; reviewer проверил документы и согласованность с предоставленным evidence,
не повторял Docker/БД/private manifest/фото/ML checks.
