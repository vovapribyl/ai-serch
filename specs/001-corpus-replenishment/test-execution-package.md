# B1 — пакет немодельных интеграционных проверок

2026-10-13 / APPROVED_BY_OWNER — сообщение «Утверждаю». Это допуск для
задачи004, не production ExecutionPackage и не разрешение использовать корпус.

## Что предлагается разрешить

После утверждения продолжить TDD supervisor, файловых checkpoints и PostgreSQL
адаптеров, включая запуск соответствующих тестов на Mac. Поведение проверяется
на синтетических входах, fake encoder/localizer и временных ресурсах.

| Часть | Конкретный объём |
|---|---|
| Процессы | Собственные fake Python children; flock/FD через exec, parent death, competing admission, graceful/forced teardown, deadline. Только группы и handles, созданные этим тестом |
| Файлы | Новая private временная папка под /private/tmp,0700; файлы0600. Staging/final на одном томе; sync/rename, corruption/path escape/symlink и receipt recovery. Удаление только собственной папки |
| БД | Новый контейнер с уникальным owner marker в Docker context colima; PostgreSQL16/pgvector из уже имеющегося образа. Только synthetic schema/fixtures и новые миграции в нём |
| Проверки БД | Constraints, fencing/epoch/version, concurrent updates, rollback/lost receipt, snapshot activation и сохранение остальных synthetic товаров. Baseline migrations0001–0009 и новая replenishment migration применяются только к новому контейнеру |
| Итоги | Private полный лог; в Git/чат — команды без DSN и сводки тестов. Credentials и paths корпуса не выводятся |

## Границы ресурса и времени

- Только один test DB container одновременно; --pull=never, --restart=no.
- Образ: sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b.
  Read-only inspect2026-10-13 подтвердил локальный tag pgvector/pgvector:pg16.
- DB caps:512MiB RAM,1CPU,pids128; storage tmpfs256MiB, без host volumes.
  Порт случайный, привязан только к127.0.0.1.
- Каждый процессный test case: до30с; fake child штатно до10с; teardown
  TERM2с + KILL3с. Максимум10fake children одновременно.
- Каждый DB test case: до60с; connect_timeout2с,lock_timeout2с,statement_timeout5с.
- Один test запуск до10мин, отдельный cleanup reserve30с. Контролирующий
  harness прекращает новые операции при deadline и завершает только owned ресурсы.
- При неподтверждённой очистке остановить проверки и сообщить владельцу;
  чужие процессы/контейнеры не останавливать. Не повторять автоматически упавший прогон.

Эти числа ограничивают синтетические тесты. Они не задают memory ceilings,
время обработки или другие разрешения для реального ML.

## Защита БД

Существующий DSN не принимается. Тестовый helper создаёт контейнер сам,
проверяет image/owner label, привязку localhost, отсутствие host mount и
пустую public schema. Затем создаёт synthetic owner marker. Credentials
генерируются для этого контейнера и хранятся только во временном private контуре.

Для миграций формируется отдельное очищенное окружение с полным набором
MVP_POSTGRES_* этого контейнера; fallback на рабочее окружение запрещён.
До SQL/миграций подтверждаются current_database/current_user и owner marker.
Удаление контейнера допускается только после проверки созданного owner label.

Baseline helper tests/support/nail_db.py служит образцом; его старый
неограниченный subprocess.run не запускается без отдельного bounded wrapper.
Новый helper/adapter сначала проверяется unit-тестами без Docker.

## Зависимости и исключения

Первоначально пакеты не включены в допуск. Оценка достаточности psycopg/Alembic/SQLAlchemy
оказалась неполной для migration0005: см. [дополнение](test-dependency-addendum.md).
Ниже исходная оценка сохранена как история: они достаточны
для текущего SQL-контракта: PostgresNailCatalog передаёт vectors через SQL,
без импорта Python pgvector или numpy. Их отсутствие само по себе не блокирует
SQL-операции текущего адаптера; DB extension находится в указанном образе.
Но migration0005 импортирует Pythonpgvector, поэтому baseline bootstrap
былblocked; владелец отдельно разрешил установку2026-10-13,
pgvector0.5.0 установлен, baseline bootstrap1passed. Если реализация
потребует нового Python dependency, сначала подготовить отдельный diff/обоснование.

Нет реальных I/encoder/weights, запросов к внешним ML сервисам, исходных
фото/товаров, рабочей БД, изменения существующих контейнеров, публикации
реального каталога, commit/push/merge. Эти scopes здесь не запрашиваются.

## Основание и следующий шаг

[Tasks004](tasks.md), [quickstart](quickstart.md),
[lifecycle](contracts/lifecycle.md) и [checkpoint](contracts/checkpoint.md)
требуют отдельного допуска для test DB/native fake. Ответ владельца «Разршаю»
разрешил продолжить unit TDD и подготовить этот конкретный пакет;
владелец утвердил данный состав сообщением «Утверждаю»2026-10-13.
Исполнение B1 разрешено в этих границах; realML/рабочаяDB scopes не меняются.
