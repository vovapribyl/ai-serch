# Gate 2: первоначальная загрузка рабочего корпуса

> Обязательный маршрут: [`AGENTS.md`](../AGENTS.md) → [`analysis/current-context.md`](analysis/current-context.md) → этот dossier.

| Поле | Значение |
|---|---|
| Статус | `APPROVED_BY_OWNER` (`SRC-056`) |
| Scope | Ровно одна первоначальная import operation рабочего `SRC-054`; без плановой перезагрузки |
| Нормативное основание | `SRC-052`–`SRC-055`, `DEC-059`–`DEC-060`; утверждённые `ART-00` v2.5 и `ART-06`–`ART-10` |
| Итог | Первоначальная загрузка выполнена, review `PASS`, результат утверждён владельцем; Gate 3 не начат |
| Режим данных | `RESTRICTED_PENDING_CLASSIFICATION`; в dossier допускаются только безопасные агрегаты |

## Границы и stop conditions

Не менять `main`, не merge/push, не удалять XLSX, runtime-контур, старые Docker volumes или `ai-database-1`. Gate 3 не входит в этот dossier и начинается только отдельной задачей. Не публиковать XLSX, строки, `product_id`, row locator, изображение, полный JSON-отчёт, runtime-env, пароль, runtime-data или секрет.

Немедленно остановиться с безопасным `BLOCKED_TECHNICAL`, если не совпали путь/размер/SHA-256, чистая БД не дала `0|0|0`, миграции не достигли `0004_import_operations`, агрегаты предпроверки расходятся, импорт/reconciliation не завершился, активных версий не ровно одна, DB/files/accepted расходятся, cleanup/report не завершены, обнаружена restricted-утечка либо нужна destructive/out-of-scope authority.

## Исполнимый маршрут

1. Проверить exact `SRC-054` без чтения строк:

   ```bash
   # Set WORKING_XLSX in the local session to the approved external SRC-054 binary.
   # Do not persist its path or the file in Git.
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
| Exact `SRC-054` (size + SHA-256) | `PASS`: `341702803`; SHA-256 совпал с `SRC-054` |
| `make test` / lint / delivery / diff-check | `PASS`: `41 passed, 1 skipped`; lint/delivery/diff-check успешны |
| Изолированный project, миграции и clean DB | `PASS`: `ai_gate2_one_time`, `0004_import_operations (head)`, до операции `0|0|0` |
| Предпроверка XLSX: accepted / rejected / reason / duplicates | `PASS`: `674` / `861` / `MISSING_PRIMARY_IMAGE` / `0` |
| Одна operation и reconciliation (если применимо) | `PASS`: `88805f5408894b5ba3617060dc115ea5`, exit `0`; reconciliation не требовался |
| Active version / DB / files / report aggregates | `PASS`: `1` / `674` / `674`; report `674` / `861` / `MISSING_PRIMARY_IMAGE` / `0`; `corpus_replaced=true`, `critical_error=null` |
| Restricted-data и Git-delivery check | `PASS`: delivery-check успешен; raw rows, изображения, полный report, runtime-env и секреты не добавлены |

### Исполнительское уточнение

Первая попытка команды остановилась до регистрации операции на safety-check прав нового пустого runtime-каталога. После явного разрешения владельца mode только этого каталога изменён на `700`; повторная проверка БД снова дала `0|0|0`. Успешная команда выше — единственная созданная import operation. Старые `ai-database-1` и его volumes не использовались и не изменялись.

## Передача на review

Независимый reviewer проверяет этот dossier, `current-context.md`, актуальный diff и точечно код/агрегированные команды, не читает raw rows и не редактирует файлы. Review выполнено до отдельного owner approval.

## Независимое review

`PASS`, 0 `Critical` / 0 `Major` / 0 `Minor`. Reviewer read-only проверил cleanup `33ea2c5` относительно checkpoint `b6a2142`, незакоммиченное evidence, ссылки, `git diff --check`, delivery-check, provenance утверждённых `ART-*` и читаемость личных skills. Direct Docker read-only lookup из sandbox был недоступен; это ограничение среды, не finding и не blocker.

## Owner approval

2026-09-04 владелец ответил «Утверждаю Гейт 2» (`SRC-056`). Утверждение закрывает Gate 2 ровно для первоначального импорта `SRC-054` с приведённым выше агрегированным evidence и review `PASS`. Оно не запускает Gate 3, не утверждает его scope и не расширяет доступ к restricted-данным.
