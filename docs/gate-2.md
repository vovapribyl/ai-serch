# Gate 2: первоначальная загрузка рабочего корпуса

> Обязательный маршрут: [`AGENTS.md`](../AGENTS.md) → [`analysis/current-context.md`](analysis/current-context.md) → этот dossier.

| Поле | Значение |
|---|---|
| Статус | `IN_PROGRESS` |
| Scope | Ровно одна первоначальная import operation рабочего `SRC-054`; без плановой перезагрузки |
| Нормативное основание | `SRC-052`–`SRC-055`, `DEC-059`–`DEC-060`; утверждённые `ART-00` v2.5 и `ART-06`–`ART-10` |
| Результат до review | Только `READY_FOR_REVIEW`; Gate 3 остаётся запрещённым |
| Режим данных | `RESTRICTED_PENDING_CLASSIFICATION`; в dossier допускаются только безопасные агрегаты |

## Границы и stop conditions

Не менять `main`, не merge/push, не удалять XLSX, runtime-контур, старые Docker volumes или `ai-database-1`; не начинать Gate 3. Не публиковать XLSX, строки, `product_id`, row locator, изображение, полный JSON-отчёт, runtime-env, пароль, runtime-data или секрет.

Немедленно остановиться с безопасным `BLOCKED_TECHNICAL`, если не совпали путь/размер/SHA-256, чистая БД не дала `0|0|0`, миграции не достигли `0004_import_operations`, агрегаты предпроверки расходятся, импорт/reconciliation не завершился, активных версий не ровно одна, DB/files/accepted расходятся, cleanup/report не завершены, обнаружена restricted-утечка либо нужна destructive/out-of-scope authority.

## Исполнимый маршрут

1. Проверить exact `SRC-054` без чтения строк:

   ```bash
   WORKING_XLSX='/Users/v.pribylovskiy/Downloads/Разработка новинок — тестовая копия с product_id.xlsx'
   stat -f '%z' "$WORKING_XLSX"
   shasum -a 256 "$WORKING_XLSX"
   ```

   Ожидание: `341702803` байта и `03b9cce1326bc80181e48bc6636d580d5bf15871f470b7c480830e378ae63a3a`.

2. Выполнить `make test`, `make lint`, `make check-delivery`, `git diff --check`; затем подтвердить Docker, Compose и доступное место. Новый failure блокирует импорт.
3. Создать отдельный Compose project `ai_gate2_one_time` вне репозитория. Runtime-env принадлежит текущему пользователю, mode `600`, не symlink; данные — вне Git. Старый `ai-database-1` и его volume не использовать.
4. Применить Alembic `0001`–`0004`, подтвердить `0004_import_operations (head)` и пустое состояние `0|0|0` для `corpus_versions`, `product_records`, `import_operations`.
5. Существующим parser получить только агрегаты `SRC-054`: ожидаются accepted `674`, rejected `861` (`MISSING_PRIMARY_IMAGE`), duplicates `0`. При расхождении импорт не запускать.
6. Запустить ровно одну `scripts/import_corpus.py --layout product-novelties`. При exit `3` разрешён только `scripts/reconcile_imports.py --operation <того же operation_id>`; при `4` допустима проверка доступности чистой БД и повтор, поскольку операция не началась. При `2` или ином коде — blocker без автоматической повторной операции.
7. Успех требует: одна активная версия, `674` активных записей, `674` файлов, operation `SUCCEEDED / ACTIVE / COMPLETE / PUBLISHED` (либо фактические согласованные значения схемы), published report с accepted `674`, rejected `861`, только `MISSING_PRIMARY_IMAGE`, duplicates `0`, `corpus_replaced=true`, `critical_error=null`.

## Безопасное evidence

Заполняется исполнителем только после успешных проверок; без raw values и секретов.

| Проверка | Результат |
|---|---|
| Exact `SRC-054` (size + SHA-256) | `PENDING` |
| `make test` / lint / delivery / diff-check | `PENDING` |
| Изолированный project, миграции и clean DB | `PENDING` |
| Предпроверка XLSX: accepted / rejected / reason / duplicates | `PENDING` |
| Одна operation и reconciliation (если применимо) | `PENDING` |
| Active version / DB / files / report aggregates | `PENDING` |
| Restricted-data и Git-delivery check | `PENDING` |

## Передача на review

Когда все строки evidence заполнены успешно, заменить статус на `READY_FOR_REVIEW`. Независимый reviewer проверяет только этот dossier, `current-context.md`, актуальный diff и точечно код/агрегированные команды, не читает raw rows и не редактирует файлы. Owner approval остаётся отдельным будущим действием.
