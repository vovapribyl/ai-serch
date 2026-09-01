# План завершения Gate 2: первоначальная загрузка рабочего корпуса

> [Текущий контекст](analysis/current-context.md) · [Gate 2 runbook](gate-2-runbook.md) · [Требования к данным](analysis/07-data-requirements.md) · [Критерии приёмки](analysis/09-acceptance-criteria-and-traceability.md)

| Поле | Значение |
|---|---|
| Версия | v0.1 |
| Дата | 2026-09-01 |
| Статус | `DRAFT_UNDER_REVIEW` |
| Целевая модель-исполнитель | `gpt-5.6-terra`, reasoning `medium` |
| Основание | `SRC-052`–`SRC-054`, `DEC-059`, owner approval поправки `SRC-053` |
| Цель | Однократно загрузить рабочую копию корпуса, доказать её пригодность для Gate 3 и передать результат владельцу на отдельный owner gate |
| Запрещённый переход | Gate 3 нельзя начинать до явного owner approval фактического результата Gate 2 |

## 1. Как использовать этот документ в новом чате

Модель Terra выступает единственным исполнителем: сама выполняет план, ведёт краткие обновления, меняет разрешённые файлы и проводит самопроверку. Отдельный агент-планировщик или агент-автор не создаётся. Один независимый reviewer подключается только после появления полного свидетельства Gate 2.

Перед началом исполнитель должен полностью прочитать:

1. `AGENTS.md`;
2. настоящий план;
3. `docs/analysis/current-context.md`;
4. `docs/gate-2-runbook.md`;
5. `docs/gate-2-handoff.md`.

Остальные документы открываются только по прямой ссылке из плана. Навык `sa-infostyle` не запускать: он разрешён только по явному запросу пользователя.

Запрос пользователя «выполни `docs/gate-2-completion-plan.md`» разрешает действия внутри этого плана: локальные проверки, создание изолированного runtime-контура вне репозитория, миграции и первоначальную загрузку утверждённого файла. Он не разрешает удалять существующие Docker volumes, менять `main`, публиковать данные, выполнять merge/push или начинать Gate 3.

## 2. Терминальное состояние

План завершён только когда выполнены все условия:

- точный бинарный файл `SRC-054` подтверждён по пути, размеру и SHA-256;
- создан отдельный локальный PostgreSQL-контур для первоначальной загрузки; старый `ai-database-1` не изменён;
- миграции `0001`–`0004` применены с нуля;
- перед загрузкой доказано отсутствие активного корпуса и товарных записей;
- `SRC-054` загружен ровно как первоначальный корпус либо операция корректно восстановлена по своему `operation_id`;
- активна ровно одна версия корпуса; число активных записей и файлов согласовано с агрегированным JSON-отчётом;
- restricted data не попали в Git, поставку, чат или review-документы;
- создано агрегированное свидетельство `docs/gate-2-completion-evidence.md`;
- авторские проверки и один независимый read-only review завершены без открытых `Critical` или `Major`;
- маршрутизирующие документы имеют статус `PENDING_OWNER_APPROVAL` результата Gate 2;
- владелец получил точный запрос на отдельное утверждение результата.

Owner approval результата не входит в полномочия модели. До ответа владельца Gate 2 остаётся `PENDING_OWNER_APPROVAL`, а Gate 3 не начинается.

## 3. Зафиксированные границы

### 3.1. Что требуется

- Использовать один рабочий XLSX и после успешной загрузки не заменять его новым снимком в MVP.
- Разрешён повтор технической попытки только до первого успешного завершения загрузки того же бинарного файла.
- Отчёт и проверка содержат только агрегаты, технические статусы и безопасные идентификаторы.
- Уже реализованный механизм versions/reconciliation можно использовать, но нельзя расширять ради сценариев плановой перезагрузки.

### 3.2. Что не требуется

- пользовательский экран загрузки;
- очистка рабочей БД перед каждым новым файлом;
- регулярное обновление или синхронизация;
- доказательство редких сценариев повторной замены корпуса;
- загрузка весов моделей или поиск по фотографии;
- изменение `ART-01`–`ART-10`;
- merge ветки в `main`.

## 4. Канонический вход

Для исполнения используется не исходный бинарный `SRC-045`, а его рабочая производная копия с добавленным `product_id`:

| Атрибут | Обязательное значение |
|---|---|
| ID исполнения | `SRC-054` |
| Путь | `/Users/v.pribylovskiy/Downloads/Разработка новинок — тестовая копия с product_id.xlsx` |
| Размер | `341702803` байта |
| SHA-256 | `03b9cce1326bc80181e48bc6636d580d5bf15871f470b7c480830e378ae63a3a` |
| Layout | `product-novelties` |
| Лист | `На рассм-е` |
| Заголовки | строка 2 |
| Данные | с строки 6 |
| `product_id` | колонка с заголовком `product_id` |
| Категория | `Категория` |
| Основное фото | `Фотография` |

Исходный `/Users/v.pribylovskiy/Downloads/Разработка новинок.xlsx` имеет размер `337804081` и SHA-256 `b914730a4c15eef732677da3f85c96e99e8b985c694652ff7465bbbcde0fbe81`. Его нельзя подставлять вместо `SRC-054`: это другой бинарный файл без утверждённой подготовки `product_id`.

Файл `~$Разработка новинок.xlsx` является временным lock-файлом Excel и никогда не используется.

## 5. Исходное состояние репозитория

- Репозиторий: `/Users/v.pribylovskiy/Documents/ChatGPT/Ai`.
- Рабочая ветка: `codex/gate-2-import-reliability`.
- Базовый HEAD на момент подготовки плана: `2fc59ff`.
- Реализация загрузчика: коммит `eb8bcd6`.
- `main` остаётся на `32287fb` и не должен меняться в рамках плана.
- В рабочем дереве ожидаются незакоммиченные документы текущего owner-gate цикла. Они принадлежат пользователю и предыдущему исполнителю: не сбрасывать, не checkout-ить и не перезаписывать массово.

Первое действие:

```bash
git status --short
git branch --show-current
git log -3 --oneline --decorate
```

Если активна другая ветка, HEAD не содержит `eb8bcd6` или обнаружены неожиданные изменения в коде загрузчика, остановиться и сообщить расхождение. Не выполнять `git reset`, `git checkout --`, stash, rebase или очистку.

## 6. Этап 1 — безопасная предпроверка

### 6.1. Подтвердить вход без чтения строк

```bash
WORKING_XLSX='/Users/v.pribylovskiy/Downloads/Разработка новинок — тестовая копия с product_id.xlsx'
stat -f '%z' "$WORKING_XLSX"
shasum -a 256 "$WORKING_XLSX"
```

Ожидаются точные значения из §4. При несовпадении пути, размера или SHA-256:

- не открывать файл целиком;
- не запускать импорт;
- не выбирать похожий файл по имени;
- сообщить владельцу фактические безопасные метаданные и запросить решение.

### 6.2. Проверить код до работы с restricted data

```bash
make test
make lint
make check-delivery
git diff --check
```

Ожидаемый baseline: `41 passed, 1 skipped`; PostgreSQL integration-тест пропускается без `GATE2_TEST_DATABASE_URL`. Любой новый failure блокирует загрузку. Deprecation warning сам по себе не блокирует, если набор тестов завершён успешно.

### 6.3. Проверить локальные ресурсы

```bash
docker version
docker compose version
df -h /Users/v.pribylovskiy/Downloads
df -h /Users/v.pribylovskiy
```

Утверждённый минимальный запас диска не установлен. Исполнитель фиксирует доступный объём в свидетельстве; если ОС сообщает недостаток места или runtime-каталог нельзя создать, останавливается без попытки очистить пользовательские данные.

## 7. Этап 2 — отдельный runtime-контур

### 7.1. Не использовать старый контейнер

Существующий `ai-database-1` ранее показал несовпадение учётных данных старого volume. Его нельзя удалять, пересоздавать или использовать для первоначальной загрузки. Создать отдельный Compose project:

```text
ai_gate2_one_time
```

Рекомендуемые пути вне репозитория:

```text
/Users/v.pribylovskiy/.local/share/ai-serch-mvp/runtime.env
/Users/v.pribylovskiy/.local/share/ai-serch-mvp/data
```

Если sandbox не разрешает запись туда, запросить точечное одобрение пользователя. Не переносить runtime-env или данные внутрь репозитория и `/tmp`.

Если sandbox не даёт доступ к Docker socket, запросить точечное разрешение на Docker-команды. Не обходить ограничение запуском другой БД, изменением старого volume или отключением проверок.

### 7.2. Создать или проверить runtime-env

Файл должен принадлежать текущему пользователю, иметь mode `600`, не быть symlink и содержать:

```dotenv
MVP_HOST=127.0.0.1
MVP_PORT=8000
MVP_POSTGRES_DB=mvp
MVP_POSTGRES_USER=mvp
MVP_POSTGRES_PASSWORD=<случайный локальный секрет>
MVP_POSTGRES_PORT=54331
MVP_DATA_DIR=/Users/v.pribylovskiy/.local/share/ai-serch-mvp/data
```

Секрет генерируется локально криптографическим генератором, не вставляется в чат, документацию, командный вывод или Git. Если порт `54331` занят, выбрать свободный loopback-порт, обновить только runtime-env и записать выбранный номер в свидетельство.

Проверка:

```bash
RUNTIME_ENV='/Users/v.pribylovskiy/.local/share/ai-serch-mvp/runtime.env'
MVP_ENV_FILE="$RUNTIME_ENV" make require-runtime-env
```

Каждый новый shell/exec-вызов, использующий настройки БД или `MVP_DATA_DIR`, должен начинаться одинаковым preamble; переменные из предыдущего вызова не считаются сохранёнными:

```bash
RUNTIME_ENV='/Users/v.pribylovskiy/.local/share/ai-serch-mvp/runtime.env'
set -a
. "$RUNTIME_ENV"
set +a
```

### 7.3. Запустить чистую БД

```bash
docker compose -p ai_gate2_one_time --env-file "$RUNTIME_ENV" up -d --wait database
set -a
. "$RUNTIME_ENV"
set +a
PYTHONPATH=src .venv/bin/python -m alembic upgrade head
```

Проверить применённую ревизию:

```bash
PYTHONPATH=src .venv/bin/python -m alembic current
```

Ожидается `0004_import_operations (head)`.

### 7.4. Доказать пустое начальное состояние

```bash
docker compose -p ai_gate2_one_time --env-file "$RUNTIME_ENV" exec -T database \
  psql -U "$MVP_POSTGRES_USER" -d "$MVP_POSTGRES_DB" -Atc \
  "select (select count(*) from corpus_versions), (select count(*) from product_records), (select count(*) from import_operations);"
```

Ожидается `0|0|0`. Любой ненулевой результат означает, что контур не является чистым. Остановиться: не очищать таблицы и не запускать замену.

## 8. Этап 3 — агрегированная предпроверка XLSX

Запустить только существующий parser и вывести агрегаты. Нельзя печатать `product_id`, номера строк, значения категорий или изображения.

```bash
PYTHONPATH=src .venv/bin/python -c 'from collections import Counter; from pathlib import Path; from product_search.corpus.xlsx_reader import PRODUCT_NOVELTIES_LAYOUT, inspect_workbook; r=inspect_workbook(Path("/Users/v.pribylovskiy/Downloads/Разработка новинок — тестовая копия с product_id.xlsx"), PRODUCT_NOVELTIES_LAYOUT); c=Counter(x.reason.value for x in r.rejected); print({"accepted_rows": len(r.accepted), "rejected_rows_count": len(r.rejected), "rejected_by_reason": dict(sorted(c.items())), "duplicate_product_ids_count": len(r.duplicate_product_ids)})'
```

Контрольный ориентир прежней проверки:

- `accepted_rows = 674`;
- `MISSING_PRIMARY_IMAGE = 861`;
- `duplicate_product_ids_count = 0`.

При совпадающем SHA-256 агрегаты должны совпасть. Если нет — остановиться и сохранить только фактические агрегаты как расхождение; импорт не начинать.

## 9. Этап 4 — первоначальная загрузка

### 9.1. Запустить ровно одну операцию

```bash
SNAPSHOT_NAME='src-054-working-corpus-v1'
set +e
IMPORT_OUTPUT=$(PYTHONPATH=src .venv/bin/python scripts/import_corpus.py \
  --xlsx "$WORKING_XLSX" \
  --snapshot "$SNAPSHOT_NAME" \
  --layout product-novelties 2>&1)
IMPORT_EXIT=$?
set -e
printf '%s\n' "$IMPORT_OUTPUT"
printf 'exit_code=%s\n' "$IMPORT_EXIT"
```

Вывод команды не содержит строк корпуса, но его всё равно не публиковать вне локального task-контекста. Из строки `operation_id=...` сохранить `operation_id` для проверки и возможного reconciliation.

Если команда завершилась не с кодом `4`, извлечь и проверить идентификатор:

```bash
if [ "$IMPORT_EXIT" -ne 4 ]; then
  OPERATION_ID=$(printf '%s\n' "$IMPORT_OUTPUT" | sed -n 's/.*operation_id=\([^;]*\).*/\1/p')
  if ! printf '%s\n' "$OPERATION_ID" | rg -q '^[0-9a-f]{32}$'; then
    echo 'Не удалось безопасно определить 32-символьный operation_id.' >&2
    exit 1
  fi
fi
```

При коде `4` `operation_id` ожидаемо отсутствует: обработать код по таблице ниже и не запускать parser.

### 9.2. Обработать код завершения

| Код | Смысл | Действие |
|---:|---|---|
| `0` | Корпус активирован, финализация завершена | Перейти к §10 |
| `2` | Импорт отклонён или не активирован, отчёт опубликован | Прочитать только агрегаты отчёта; не повторять автоматически; зафиксировать blocker |
| `3` | Требуется финализация отчёта или cleanup | Запустить reconciliation только для полученного `operation_id`; новый import не запускать |
| `4` | Журнал операций недоступен, импорт не начался | Исправить доступность чистой БД; после проверки `0|0|0` разрешён повтор того же файла |
| иной | Необработанная ошибка | Остановиться; сохранить безопасный error summary, не удалять runtime-контур |

Reconciliation для кода `3`:

```bash
PYTHONPATH=src .venv/bin/python scripts/reconcile_imports.py --operation "$OPERATION_ID"
```

Если reconciliation снова возвращает `3` или `4`, пометить Gate 2 как `BLOCKED_TECHNICAL` и передать владельцу безопасное описание. Не запускать вторую import-operation.

## 10. Этап 5 — проверка успешного результата

### 10.1. Проверить БД

Выполнить агрегированные запросы без вывода товарных ID:

```bash
docker compose -p ai_gate2_one_time --env-file "$RUNTIME_ENV" exec -T database \
  psql -U "$MVP_POSTGRES_USER" -d "$MVP_POSTGRES_DB" -Atc \
  "select count(*) from corpus_versions where is_active;"

docker compose -p ai_gate2_one_time --env-file "$RUNTIME_ENV" exec -T database \
  psql -U "$MVP_POSTGRES_USER" -d "$MVP_POSTGRES_DB" -Atc \
  "select count(*) from product_records p join corpus_versions c on c.id=p.corpus_version_id where c.is_active;"

docker compose -p ai_gate2_one_time --env-file "$RUNTIME_ENV" exec -T database \
  psql -U "$MVP_POSTGRES_USER" -d "$MVP_POSTGRES_DB" -Atc \
  "select outcome,activation_status,cleanup_status,report_status from import_operations where operation_id='${OPERATION_ID}';"
```

Ожидается:

- одна активная версия;
- `674` активные записи;
- `SUCCEEDED | ACTIVE | COMPLETE | PUBLISHED` в терминах фактических значений схемы. Если строковые значения отличаются только утверждённым внутренним представлением, свидетельство сохраняет фактические значения и ссылку на код; нельзя объявлять успех при pending/failed.

### 10.2. Проверить файлы и отчёт

```bash
find "$MVP_DATA_DIR/corpora/$OPERATION_ID" -type f | wc -l
REPORT_PATH="$MVP_DATA_DIR/reports/$OPERATION_ID.json"
jq '{snapshot_name, accepted_rows, rejected_rows_count, rejected_by_reason, duplicate_product_ids_count:(.duplicate_product_ids|length), corpus_replaced, critical_error}' "$REPORT_PATH"
```

Ожидается:

- число файлов равно числу активных записей;
- `accepted_rows = 674`;
- `rejected_rows_count = 861`;
- причина отклонения — `MISSING_PRIMARY_IMAGE`;
- дублей нет;
- `corpus_replaced = true` означает успешную первоначальную активацию в существующем техническом контракте, а не бизнес-требование будущей перезагрузки;
- `critical_error = null`.

Не выводить поле `rejected_rows`: оно содержит локаторы строк.

### 10.3. Повторить проверки поставки

```bash
make test
make lint
make check-delivery
git diff --check
git status --short
```

Рабочий XLSX, извлечённые изображения, runtime-env, JSON-отчёт и runtime data не должны появиться в Git.

## 11. Этап 6 — свидетельство Gate 2

Создать `docs/gate-2-completion-evidence.md` через `apply_patch`. В документ включить только:

- дату и ветку/HEAD;
- ID источника `SRC-054`, filename без копирования файла, размер и SHA-256;
- Compose project, образ PostgreSQL, выбранный loopback-порт без секрета;
- ревизию миграций;
- `operation_id` и snapshot name;
- агрегаты accepted/rejected/reasons/duplicates;
- число активных версий, записей и файлов;
- статусы операции, cleanup и отчёта;
- результаты `make test`, lint, delivery и `git diff --check`;
- явные границы: raw rows/images/report не в Git и не опубликованы;
- известные ограничения и отклонения от ожидаемых значений;
- вывод `READY_FOR_REVIEW` или конкретный blocker.

Не включать:

- пароль или полный runtime-env;
- сырые строки, `product_id`, номера строк, изображения;
- полный JSON-отчёт;
- содержимое таблиц БД;
- утверждение, что Gate 3 разрешён.

После readback свидетельства обновить без дублирования истории:

- `docs/gate-2-runbook.md`;
- `docs/gate-2-handoff.md`;
- `docs/project-status.md`;
- `docs/analysis/current-context.md`.

До review статус результата — `READY_FOR_REVIEW`, не `APPROVED_BY_OWNER`.

## 12. Этап 7 — независимый review

Это переход evidence/gate, поэтому нужен один независимый read-only reviewer. Рекомендуемый режим reviewer по governance: `gpt-5.6-sol`, reasoning `high`.

Reviewer проверяет:

- точное соответствие `SRC-054` по checksum;
- чистое начальное состояние БД;
- миграции `0001`–`0004`;
- непротиворечивость агрегатов XLSX, БД, файлов и отчёта;
- финальные статусы operation/activation/cleanup/report;
- отсутствие restricted data в Git и документах;
- отсутствие плановой перезагрузки и преждевременного Gate 3;
- воспроизводимость команд и выводов.

Reviewer не редактирует файлы и не читает сырые строки. Findings классифицируются `Critical / Major / Minor`. После `Critical` или `Major` исполнитель исправляет замечания и запускает повторное review. После финального `PASS` исполнитель переводит результат Gate 2 в `PENDING_OWNER_APPROVAL` и фиксирует отчёт review в `docs/analysis/reviews/`.

## 13. Этап 8 — отдельный owner gate результата

Владельцу показывают краткий итог:

- какой бинарный файл загружен и совпал ли checksum;
- сколько записей принято и отклонено;
- почему строки отклонены;
- активна ли ровно одна версия;
- согласованы ли DB, файлы и отчёт;
- результаты тестов и независимого review;
- какие данные не публиковались;
- остаётся ли какой-либо blocker.

Точная формулировка запроса:

> Утверждаете результат Gate 2: рабочая копия `SRC-054` однократно загружена, агрегированное свидетельство и независимое review прошли, а плановая перезагрузка исключена? Это утверждение закроет Gate 2 и разрешит только подготовку следующего шага Gate 3.

До ответа владельца:

- не ставить `APPROVED_BY_OWNER` результату Gate 2;
- не начинать Gate 3;
- не загружать модели;
- не выполнять merge/push/commit без отдельного запроса;
- не удалять runtime-контур или исходный файл.

После явного утверждения создать новый `SRC-*` owner approval, синхронизировать текущий контекст, статус проекта, runbook и handoff. Само утверждение не запускает реализацию Gate 3 без отдельного запроса владельца.

## 14. Stop conditions

Исполнитель немедленно останавливается и сообщает владельцу, если:

- checksum или размер `SRC-054` не совпали;
- исходная БД непустая;
- требуется удалить или изменить старый Docker volume;
- миграции не достигают `0004_import_operations`;
- агрегированная предпроверка расходится с контрольными значениями при совпадающем checksum;
- импорт вернул необработанный код либо reconciliation не завершил ту же операцию;
- активны ноль или больше одной версии;
- число DB-записей, файлов и accepted rows различается;
- отчёт не опубликован или cleanup не завершён;
- restricted data появились в Git/поставке;
- требуется изменить утверждённые требования;
- выполнение требует merge, push, удаления данных или иной власти за пределами плана.

Blocker не переводится в `PASS` и не маскируется повторной загрузкой другого файла.

## 15. Короткий prompt для нового чата

```text
Работай в /Users/v.pribylovskiy/Documents/ChatGPT/Ai на текущей ветке и выполни docs/gate-2-completion-plan.md от начала до конца. Сохрани все существующие незакоммиченные изменения, не используй sa-infostyle, не публикуй restricted data и не начинай Gate 3. Доведи выполнение через агрегированное свидетельство, независимое read-only review и статус PENDING_OWNER_APPROVAL результата Gate 2. При stop condition не импровизируй и не меняй файл или контур — зафиксируй blocker и запроси решение владельца.
```

## 16. Что передать владельцу в конце

- ссылка на `docs/gate-2-completion-evidence.md`;
- итог review с количеством `Critical / Major / Minor`;
- безопасные агрегаты загрузки;
- текущий статус Gate 2;
- один точный запрос owner approval результата;
- явное подтверждение, что Gate 3 не начат.
