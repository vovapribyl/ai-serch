# Исследование решений для плана

v1 / 2026-10-12 / APPROVED_BY_OWNER. Решения ниже — предложения технического плана.
Они основаны на утверждённых [spec](spec.md) и [HLD](../corpus-optimization/hld.md).
Изучение источников не является проверкой runtime. Исследование выполнено автором;
по AGENTS используется один независимый reviewer, отдельные planner/author не создаются.

## Baseline и зависимости

**Решение:** начинать реализацию с проверяемого пакета переноса исходников поиска
по ногтям из сохранённого checkout, затем изменять его в текущей ветке.
**Основание:** рабочая ветка codex/upload-optimiz, HEAD b38f07e; сохранённый checkout
corpus-optimization, HEAD ba49504 с изменениями и untracked nail_* файлами.
Один git commit не описывает эти изменения. Нужен отдельный manifest выбранных
source/tests/migration с SHA-256 и проверкой изменений зависимостей.
**Альтернативы:** переносить checkout целиком — захват unrelated изменений;
писать заново — потеря проверенного алгоритма. Оба варианта отвергнуты.
**Gate:** B0 — до продуктового кода согласовать точный manifest и baseline.
Сам план не выполняет перенос и не принимает старые test reports как новые проверки.

pyproject.toml требует Python >=3.12,<3.13, FastAPI, psycopg, SQLAlchemy/Alembic;
локальная .venv показывает Python3.12.14. pytest/ruff заданы dev dependencies.
PyTorch/модели и I сохраняют отдельные принятые окружения: установки/обновления
пакетов не выполнялись. Native profile от прежней synthetic-пробы исчерпан и
не разрешает эту feature. Его числа не становятся production-бюджетами.

## Checkpoint

**Решение:** неизменяемый набор файлов попытки на одном частном томе; запись/проверка,
синхронизация и rename, затем fenced DB commit. Encoder vectors — bounded JSON
со строгой схемой и конечными числами, без pickle/нового формата с исполняемым содержимым.
Окончательные векторы редакции — в имеющемся pgvector.
**Основание:** промежуточные файлы нужны для resume; stdlib JSON позволяет начать
без новой зависимости. Атомарность имени не равна power-loss durability.
**Альтернативы:** общая file/DB транзакция не предоставляется; все crops в БД
увеличивают storage-интеграцию; файлы в RAM не переживают restart.
**Проверка:** аварии на каждой границе, орфанные файлы, повреждение, повтор commit,
конфликт хеша, соответствие JSON и опубликованных DB-векторов. См. [контракт](contracts/checkpoint.md).

## Владение режимом

**Решение:** отдельный mode.lock на весь срок резидентности и fencing epoch в БД.
Единственный supervisor держит mode FD при передаче SEARCH→DRAINING→BUILD;
CLI запрашивает переход через private IPC, command_lock атомарно закрывает admission.
Descriptor одной flock-блокировки явно передаётся собственным ML-процессам;
они не вызывают LOCK_UN. Supervisor также не unlock-ит живых детей.
**Основание:** прочитан локальный macOS man2flock: dup/fork создают ссылки на
одну блокировку, explicit unlock ребёнком снимает её и у родителя. Передача FD
не равна доказанному поведению реального процесса — нужен native fake probe.
**Альтернативы:** coordinator lock только вокруг вызова не гарантирует teardown;
флаг БД не удерживает живой orphan; поиск процессов по одному PID допускает PID reuse.
**Проверка:** supervisor crash с живым ребёнком, exec/наследование FD, kill-group,
неподтверждённый выход и stale commit. До успешной проверки на Mac ML-admission закрыт.

## Каталог и runtime binding

**Решение:** immutable product revision и snapshot состава; snapshot identity
отдельна от semantic profile identity. Snapshot-read adapter возвращает прежнюю
форму CatalogProduct/PhotoEmbeddings и порядок, сохраняя matching/scoring.
Текущая редакция определяется отдельным product head с CAS; retry и publication
сериализованы его lock. Publication attempts хранят FAILED/UNKNOWN отдельно от фото.
Новая VerifiedCatalogBinding связывает snapshot fingerprint, profile и проверенный
runtime-контекст; старый representation fingerprint не обходится и не переименовывается.
**Альтернативы:** полное копирование всех vectors после товара дорого; mutable
активные строки затрудняют единый состав запроса и rollback.
**Проверка:** одна snapshot identity на запрос, все редакции одного профиля,
поздняя активация, повтор commit и legacy→snapshot parity на синтетических матрицах.

## Бюджеты и deadlines

**Решение:** конечные числовые бюджеты обязательны во входном ExecutionPackage.
Никаких числовых defaults для RAM/HTTP/process teardown/размера wire не придумывается.
Дизайн параметризован: все операции используют один монотонный end_at и остаток
срока, более строгие caps действующего профиля сохраняются.
**Почему это разрешение исследования:** формат и проверка обязательных параметров
определены; неизвестные значения являются входом отдельной пробы, а не пробелом
алгоритма. Отсутствие параметра запрещает model-backed запуск.
**Отдельный gate:** подготовка/утверждение нового пакета и runtime identity перед ML/БД.

## Внешние первичные источники

- [Python3.12 subprocess](https://docs.python.org/3.12/library/subprocess.html): pass_fds и start_new_session на POSIX; не гарантия освобождения MPS.
- Локальные man2flock/man2close на целевом Mac — проверка владения дескрипторами;
  Linux flock-документация не использована как доказательство Mac-поведения.
- [Python os.replace](https://docs.python.org/3.12/library/os.html#os.replace): атомарность rename при успешном выполнении на подходящем томе.
- [PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locking;
  [изоляция транзакций](https://www.postgresql.org/docs/current/transaction-iso.html): видимость commit.

Новые численные NFR, библиотеки и бизнес-правила не установлены. Значения runtime,
baseline manifest и ресурсные результаты проверяются на своих операционных gates;
они не объявлены полученными этим документом.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.

## B0 — фактическая подготовка, 2026-10-13

Пункт001 выполнен: [baseline review](baseline-review.md), [manifest](baseline-manifest.json),
[metadata зависимостей](baseline-dependencies.json). SHA всех80 source/target записей
сверены, статические локальные imports разрешены; migration chain имеет9revision
и head0009. Это не выполнение импортов, тестов, миграций или inference.
Пункт002 ожидает согласования конкретного manifest владельцем; код не переносится.

## B0: утверждение владельца и перенос — 2026-10-13

Владелец сообщил «Утверждаю бэйслайн». Утверждён точный
[manifest](baseline-manifest.json), SHA256
`5a89cf8b542fd4f186fbe84ebd2922341f5332ba03251bd2958d086bbe5c7c3e`.
Manifest сохраняется неизменным как исходный снимок; его поле proposal отражает
момент подготовки, текущее утверждение зафиксировано здесь.

Перенесены 72 PROPOSE_ADD, 4 KEEP_IDENTICAL сохранены. Два REFERENCE_ONLY и
два MERGE_REVIEW_REQUIRED не перезаписывались. До записи проверены все исходные
и целевые SHA; после записи проверены все 80 целевых исходов. Исходный checkout
не изменён. Установка пакетов, применение миграций и запуск моделей не выполнялись.
Немодельные зависимости определены в baseline-dependencies.json; pgvector0.5.0
потребует отдельной подготовки, без установки ML extra.

Результаты переноса и первого TDD цикла: [отчёт](baseline-transfer-report.md).
Пункт003 закрыт после hash checks и229немодельных baseline tests.
Пункты005–007: проверка ExecutionPackage,135случаев; объединённая выборка364passed.

## B1 — частичный результат2026-10-13

Допуск утверждён владельцем. [Отчёт](b1-progress-report.md):26native/15files
и427unit/harness/baseline прошли. Три testDB bootstrap attempts остановились
на отсутствующемPythonpgvector migration0005; createdcontainers очищены.
[Одно dependency дополнение](test-dependency-addendum.md) ожидает утверждения,
установки нет; schema/state/publication и общийruntime wiring ещё не готовы.

Обновление2026-10-13: «Давай установим с ноля, как ты предлагал изначально»
разрешило толькоpgvector0.5.0. Установка изpipcache и importPASS;
B1baseline bootstrap1passed,контейнер очищен. Нет localcopy/MLextra.

## Схема и state adapter — 2026-10-13

Пункты020–022 выполнены: [отчёт](state-adapter-report.md). Миграция0010
и PostgreSQL-адаптер проверены в временной синтетической БД:25passed.
Общая выбранная выборка:431unit/harness/baseline+26native+15files+25DB=497passed.
Baseline80hashes сохранён. Реальная публикация, runtime wiring и ML не выполнены.

## Подготовка и публикация — 2026-10-14

Пункты026–028 выполнены: [отчёт](publication-report.md). Подготовка READY
и атомарная публикация проверены на синтетических файлах и временной БД.
Финал:23publication+25stateDB+431unit+26native+15files=520passed.
Автоматический runtime wiring, чтение снимка поиском и эксплуатационный запуск
ещё не выполнены; утверждённые требования и operational scopes сохранены.

## Чтение snapshot и runtime binding — 2026-10-14

Пункты029–031 выполнены: [отчёт](catalog-binding-report.md). Отдельные DTO,
query claim, независимое наблюдение runtime и поток по закреплённому descriptor.
Финал:21binding+23publication+25stateDB+431unit+26native+15files=541passed.
Два намеренных изменения baseline [зафиксированы с SHA](catalog-binding-baseline-changes.json);
78записей сохранены. Native/HTTP cutover не выполнен; реальный runtime остаётся
за отдельным gate. Следующий этап — CLI и вертикальный fake сценарий.

## CLI и вертикальный fake flow — 2026-10-14

Пункты032–035 выполнены: [отчёт](cli-flow-report.md). Частный IPC, start/status,
503 hook, сохранённая сводка и единый deadline проверены в B1. Финал582passed.
Грамматика resume/retry реализована, application logic пока NOT_IMPLEMENTED;
036–046 открыты. Постоянный supervisor host/настоящие workers и Web cutover
не запускались.77baseline записей сохранены,3намеренных изменения учтены с SHA.

## Resume, ожидание и recovery — 2026-10-14

Пункты036–042 реализованы: [отчёт](resume-recovery-report.md). Resume сохраняет
исходную партию и проверяет пригодные checkpoints до warmup. ERROR не повторяется;
warning ограничен300секундами, продолжение требует30секунд свежих OK-сигналов.
Финал601passed:158B1+443unit/Web. Контейнеры очищены. В отчёте отмечены
нарушение последовательности DB-прогонов, исправление harness и оговорка к TDD
дополнительных restart-сценариев.043–046 retry и049–051runtime/review открыты.

## Ручной retry — 2026-10-14

Пункты043–046 выполнены: [отчёт](retry-report.md). Retry-photo создаёт новую
редакцию и меняет только выбранную ERROR; прежние пригодные результаты и
публикации сохраняются. Retry-publication сверяет UNKNOWN и не вызывает ML.
Финал611passed:168B1+443unit/Web; контейнеры очищены. Ошибочный параллельный
unit-прогон столкнулся с глобальным lease; итоговый набор выполнен последовательно.
047–051 — трассировка, сквозные проверки, runtime и review — ещё открыты.

## Трассировка и сквозная проверка — 2026-10-14

047–048 выполнены: [отчёт](acceptance-verification-report.md),52строки FR→test
в ART-09.45 B1/7частичных свидетельств; это не приёмка эксплуатации.
Обнаруженный пробел FR-067/068 закрыт по TDD: сводка показывает состояние
товара и оставшиеся фото полной редакции.8новых сценариев подтвердили5+2,
input/profile revision, независимость товаров и downgrade/reupgrade миграции.
619различных успешных случаев:175B1+1диагностический+443unit/Web.
В общем B1 был1setup error readiness; причина UNKNOWN, cleanup подтверждён,
полный набор автоматически не повторялся. Runtime049–050 и review051 открыты.

## Первый этап runtime preparation049 — 2026-10-14, исторический PARTIAL

[Предложение](runtime-probe-proposal.md) фиксирует один выбранный owner вход,
свежие fingerprints и численные limits.89encoder files/36I manifest positions,
71code files, metadata inventory/VCS и модельно-свободная I assembly проверены.
Controller44distributions безTorch; существуют I90/encoder72 environments.
По сравнению с accepted I snapshot изменены3code entries и inventory — новая
identity обязательна. Приватный пакет и byte-identical input подготовлены;
authorization/execution.claim отсутствуют.049 ещё не закрыт: real StageWorkers,
host, mandatory observations/poll и свежие claim handlers не реализованы.
050 не запускался; новые установки, server/DB/ML/working catalog отсутствуют.

## Завершение подготовки049 — 2026-10-14

[Связка и проверка](runtime-binding-verification-report.md) подготовлены.512
выбранных unit/Web/native проверок и1 новый synthetic DB case; runtime scope
не исполнен. Число encoder entries уточнено:87, а не89. Новый private пакет
приведён в [предложении050](runtime-probe-proposal.md); прежний partial статус
и SHA сохранены как история.050 — отдельный owner gate,051 открыт.
