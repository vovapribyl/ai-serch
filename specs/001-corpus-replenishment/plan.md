# Технический план: пополнение поискового корпуса

**Ветка:** codex/upload-optimiz | **Дата:** 2026-10-12 | **Спецификация:** [spec.md](spec.md)\
**Версия / статус:** v1 / APPROVED_BY_OWNER — утверждено владельцем 2026-10-12 сообщением «Утверждаю».

## Краткое описание

Один controller обрабатывает до 5 фото по стадиям, закрепляет промежуточный
прогресс и публикует готовые товары. Search/build исключаются на весь срок ML-резидентности.
Immutable редакции товаров и snapshots состава обеспечивают публикацию без
пересчёта остальных vectors. [HLD v1.1](../corpus-optimization/hld.md) утверждён;
этот план деталирует его четыре сложных участка, без отдельного большого LLD.

## Технический контекст

| Область | Выбор / основание |
|---|---|
| Язык | Python >=3.12,<3.13 из pyproject; локальная .venv3.12.14 проверена |
| Зависимости | Существующие FastAPI, psycopg, Alembic/SQLAlchemy, Pillow; ML/I отдельные locks, без обновления |
| Хранение | PostgreSQL/pgvector; private файлы на одном томе; промежуточные vectors JSON |
| Тесты | pytest, fake ports/clock; test PostgreSQL отдельно; fake process lifecycle на Mac; real ML отдельно |
| Платформа / тип | Один macOS host, локальное Web-приложение и owner CLI |
| Производительность | SLA/RAM savings не установлены; пределы задаёт новый execution package до реального запуска |
| Ограничения | 5 фото, warning300s/стабильность30s; профиль/claims/STOP и конечные budgets сохраняются |
| Scope | Существующий выбранный корпус; без VM, новых моделей/категорий/импорта и retention/GC |

Числа deadlines/RSS/admissions для runtime — обязательные входные параметры,
а не неразрешённые defaults архитектуры. Старое validation window использовать нельзя.
[Research](research.md) обосновывает выбор и gates подготовки входов.

## Проверка принципов и gates

Конституция .specify — незаполненный шаблон. Действуют AGENTS/governance и
[метод разработки](../../docs/development-method.md). До/после design проверено:

- Spec и критерии согласованы; HLD и ФТ APPROVED_BY_OWNER.
- Нет дублирования нормативных FR; [ART-09](../../docs/analysis/09-acceptance-criteria-and-traceability.md#дополнение-пополнение-поискового-корпуса) задаёт критерии.
- Core использует application ports; SQL/HTTP/OS/ML за адаптерами.
- TDD для логики: наблюдаемый RED по требованию, минимальный GREEN, затем REFACTOR.
- B0 закрывается manifest/согласованием baseline до продуктового кода.
- Этот пакет утверждён владельцем; test DB/native fake/ML/рабочая БД имеют свои допуски.
- Hooks before_plan/after_plan отсутствуют; отдельные research agents не создаются по AGENTS.

## Структура проекта

### Документы функции

spec.md; plan.md; research.md; data-model.md; quickstart.md;
contracts/application.md, checkpoint.md, lifecycle.md, catalog.md, cli.md;
checklists/requirements.md. tasks.md создаётся позже через speckit-tasks после approval плана.

### Предлагаемые исходники после B0

```text
src/product_search/search/
  replenishment_contracts.py
  replenishment_ports.py
  corpus_replenishment.py
  nail_*                         # проверенный перенос выбранного baseline
src/product_search/infrastructure/
  replenishment_repository.py
  replenishment_artifacts.py
  replenishment_supervisor.py
  replenishment_cli.py
  nail_*                         # сохранённые адаптеры, точные файлы по B0
migrations/versions/corpus_replenishment_v1.py
 tests/test_replenishment_*.py
```

Новые файлы — проект, не существующая реализация. Состав переноса включает нужные
nail search/core/adapters, HTTP I service, model-provider изменения и связанные тесты;
все выбранные файлы согласуются по hashes, unrelated dirty изменения не переносятся.
Alembic parent проверяется после B0; filename не выбирает head автоматически.

## Фаза 0 — исследование

[research.md](research.md) завершает выбор вариантов: source baseline, checkpoint,
mode lock/fencing, snapshot/runtime binding и обязательные execution-параметры.
Конкретные hashes baseline и цифры нового runtime задаются на named gates до исполнения,
не объявляются установленными сейчас. Нормативные решения не переоткрываются.

## Фаза 1 — design и контракты

- [Модель данных](data-model.md): состояния, связи, identities и ограничения.
- [Checkpoint](contracts/checkpoint.md): immutable artifacts, sync/rename, fenced commit, recovery.
- [Lifecycle](contracts/lifecycle.md): descriptor ownership, группы, orphan recovery, clocks/deadlines.
- [Каталог](contracts/catalog.md): publication transaction, race STOP/commit, snapshot binding, rollback.
- [Приложение](contracts/application.md) и [CLI](contracts/cli.md): plain commands/results и actor boundary.
- [Quickstart](quickstart.md): проверки и будущие команды, без запуска inference здесь.

## Порядок реализации по TDD

| Шаг | RED перед кодом | GREEN и проверка | Gate |
|---|---|---|---|
| B0 baseline | Не TDD: diff/manifest/source mapping | Изолированный перенос и свежие немодельные baseline checks | Точный manifest и исходные зависимости согласованы |
| Правила/сценарии | Готовность across batches, no automatic retry, лимиты, fake clock | Минимальное core поведение через fake ports | Немодельные тесты, boundary check |
| Checkpoint | Сбои file/DB, hash conflict, повтор receipt | Artifact adapter и state contract | Test filesystem и отдельно допущенная test DB |
| Mode/lifecycle | Query racing drain, выдача permit, bounded search teardown, parent death, живой child, stale epoch | Supervisor/leases и bounded shutdown | Native fake probe на Mac до ML |
| Каталог | Current head CAS/retry, superseded READY publication, atomic visibility, profile mismatch, STOP race, lost receipt | Repository/snapshot adapter + synthetic matching parity | Миграция только test DB после допуска |
| CLI/Web glue | Parser, private input validation, unavailable mapping | Реальные адаптеры вызывают те же сценарии | Без модельной/корпусной работы |
| Ограниченная ML-проверка | Сначала согласованные oracle/criteria и пакет | Запуск по отдельному разрешению, измерение memory/teardown/совместимости | Новая runtime identity и finite окно |

Тесты не выводят expected из проверяемого алгоритма и не ослабляются ради GREEN.
Для адаптеров integration-тест пишется до реализации соответствующего контракта;
отказ импорта/отсутствие окружения не считается нужным RED. Документы и manifest
проверяются своим способом; ML-эксперимент не называется unit TDD.

## Complexity tracking

Нарушений принципов не выявлено. Нового брокера/сервиса/общего ML lockfile нет.
Snapshot metadata копируется O(N) при публикации; GC и оптимизация отдельно,
пока фактическая цена не оправдывает усложнение. Fencing/mode inheritance нужны
для сохранения запрещённого пересечения режимов при аварии; file/DB receipt нужен
для корректного resume. Эти механизмы не убираются как «лишние».

## Проверка плана и следующий этап

Одно независимое read-only review → исправления → owner approval всего пакета.
Далее speckit-tasks формирует зависимости и явный RED/GREEN/REFACTOR порядок.
Этот план не переносит код, не устанавливает dependencies, не мигрирует рабочую БД
и не исполняет модельные пробы. Полнота source manifest и эксплуатационные параметры
являются обязательными gates до своих действий, а не свидетельствами готового runtime.


### Результат проверки v1

Первое независимое read-only review: REWORK, 0 Critical / 2 Major / 1 Minor.
Исправлены переход SEARCH→DRAINING→BUILD, канонический product head и хранение
publication attempts/error/UNKNOWN. Повторное review того же reviewer: PASS,
0 Critical / 0 Major / 0 Minor. Проверены ссылки/anchors, таблицы, routing и diff.
Review относится ко всему пакету plan/research/data-model/contracts/quickstart.
Статус APPROVED_BY_OWNER по сообщению «Утверждаю» 2026-10-12. Процессы, БД и модели не запускались.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.

## Фактическая ограниченная runtime-проба — 2026-10-14

Пункт050 выполнен: [отчёт](runtime-probe-report.md). Явно разрешённыйbbb3d386,
один товар/фото; реальный I→OpenCLIP→DINOv2→SigLIP2,4checkpoints, READY и publication
только новая disposable DB,49,690с. Vector dimensions/finite/unit-norm checks PASS;
owned cleanup подтверждён. Это ограниченное runtime evidence, не изменение scope
или утверждение всего решения.051independent code review остаётся открытым;
workingDB/Web cutover/большая партия/merge/push отдельно не выполнялись.

## Итоговое code review051 — 2026-10-14

Независимое read-only [review](final-code-review.md) завершено с REWORK:
0Critical/5Important/0Minor. Требуются исправления уже принятых контрактов:
fresh grant для retry-publication и commits, recovery stale socket,
актуальный SQL budget и единая Unicode canonical encoding.
Объём/требования не менялись;051 открыт до TDD-исправлений и регрессии.
Проба050 остаётся успешным ограниченным свидетельством; merge/cutover не разрешены.

## Завершение исправлений051 — 2026-10-14

Все пять Important исправлены по разрешению владельца и проверены TDD:
[свидетельства](final-code-review.md#исправления-по-разрешению-владельца--2026-10-14).
194selected B1/native PASS и отдельно300selected model-free PASS (пересечение
выборок, не полный suite), ruff/diff/cleanup PASS.051 выполнен. Исходный independent
REWORK сохранён, повторного independent PASS нет. Новые требования не вводились;
working runtime/cutover/owner acceptance/merge/push остаются отдельными шагами.

## Ограниченное подтверждение исправленного runtime — 2026-10-14

[Проба7d89d5da](post-review-runtime-report.md) явно разрешена и завершена OK:
один товар/фото,4модельные стадии/4checkpoints/30vectors/1publication в temporary DB,
82,661с; cleanup подтверждён. Это подтверждает полный current happy path на одном
входе. Прежняя причина INFRASTRUCTURE_ERROR остаётсяUNKNOWN, а успешный повтор
не доказывает её исправление. Рабочая активация/партия/качество/production acceptance
остаются отдельными этапами; новый independent PASS не получен.
