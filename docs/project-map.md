# Карта проекта: что читать и где продолжать

Срез на 2026-10-15 для `codex/upload-optimiz`. Это навигация по существующим
источникам, а не новые требования или разрешения. [Обзор проекта](../README.md) ·
[Текущий контекст](../specs/corpus-optimization/project-context.md) ·
[Результат документного аудита](documentation-audit.md).

## Проект за минуту

Система должна помогать сотруднику находить ранее рассмотренный товар по фото
и данным карточки. Решение о совпадении остаётся человеку.
Текущая экспериментальная категория — накладные ногти; перенос на другие
категории не проверен. [Vision & Scope](analysis/01-vision-and-scope.md).

В рабочей ветке есть первоначальный XLSX-импорт, поиск по отдельным областям,
пополнение с checkpoints и наблюдаемость. Локализатор возвращает маски; код
создаёт кропы, три модели получают векторы, алгоритм сопоставляет и ранжирует.
Базовый Web пока остаётся заглушкой: готовность модулей не равна готовности продукта.

Ограниченные пакетные испытания пополнения прошли. Семь запросов обработаны
полностью, но ранги трёх положительных примеров слабые; отключение модели не принято.
Текущие числа, ограничения и следующий шаг — в
[статусе проверок](../specs/001-corpus-replenishment/verification-followup-status.md).

## Ветки и точки входа

| Контекст | Где смотреть | Как понимать |
|---|---|---|
| Обзор всей системы | [Корневой README](../README.md) | Назначение и состав текущей ветки |
| Продолжение разработки | [Контекст](../specs/corpus-optimization/project-context.md) | Рабочее место, Git-вехи, реализованное и ограничения |
| Текущий результат испытаний | [Статус](../specs/001-corpus-replenishment/verification-followup-status.md) | Что завершено, что осталось, какой следующий шаг |
| Аналитические правила и артефакты | [AGENTS](../AGENTS.md), [индекс ART](analysis/README.md) | Действующие маршруты и канонические документы |
| Главная ветка | [README main](https://github.com/vovapribyl/ai-serch/blob/main/README.md) | Отдельный состав кода; обновление README не переносит поиск и пополнение |
| Предыдущие этапы | [История контекста](../specs/corpus-optimization/project-context-history.md), [история локализатора](../specs/candidate-i-http/execution-context.md) | Датированные результаты; старые «следующие шаги» не являются текущим планом |

Для конкретной задачи достаточно строки маршрута ниже и её зависимостей.
Эта карта не вводит обязательное чтение всего набора и не меняет FAST_PATH.

## Маршруты по задачам

| Задача | Основной источник | Детализация |
|---|---|---|
| Понять бизнес и scope | [Vision](analysis/01-vision-and-scope.md) | [ART-06: сценарии и индекс возможностей](analysis/06-user-scenarios-and-functional-requirements.md) |
| Проверить нормативное основание | [Реестр ART-00](analysis/00-source-and-decision-register.md) | [Решения](analysis/registers/decisions.md), [источники](analysis/registers/sources.md), [governance §4](analysis/governance.md#4-источники-и-доказательность) |
| Изменить поведение пополнения | [ФТ](../specs/corpus-optimization/functional-requirements.md) | [TO-BE](../specs/corpus-optimization/to-be.md), [критерии ART-09](analysis/09-acceptance-criteria-and-traceability.md#дополнение-пополнение-поискового-корпуса) |
| Разобраться в архитектуре пополнения | [HLD](../specs/corpus-optimization/hld.md) | [План и выборочный LLD](../specs/001-corpus-replenishment/plan.md), [контракты](../specs/001-corpus-replenishment/contracts/application.md) |
| Разобраться в локализаторе и поиске | [HLD поиска](architecture/nail-search-hld.md) | [LLD](architecture/nail-search-lld.md), [HTTP-контракт](architecture/candidate-i-http-contract.md); статусы частей читать в самих документах |
| Диагностировать ресурсы или STOP | [Статус проверок](../specs/001-corpus-replenishment/verification-followup-status.md) | [STOP observability](../specs/001-corpus-replenishment/stop-observability-report.md), [atomic telemetry fix](../specs/001-corpus-replenishment/telemetry-atomic-snapshot-fix.md) |
| Оценить модели | [Семь запросов полностью](../specs/corpus-optimization/remaining-quality-report.md) | [Разбор локализации](../specs/corpus-optimization/localization-review.md), [исключение областей](../specs/corpus-optimization/region-exclusion-report.md), [лидеры выдачи](../specs/corpus-optimization/top-candidates-review.md), [среднее по парам](../specs/corpus-optimization/matched-pairs-mean-report.md), [раннее сравнение](../specs/corpus-optimization/model-ablation-report.md), [гипотезы](../specs/corpus-optimization/hypotheses.md) |
| Подготовить проверку | [План качества на растущем корпусе](../specs/corpus-optimization/corpus-scale-quality-test-plan.md) (DRAFT), [Quickstart](../specs/001-corpus-replenishment/quickstart.md) | [Метод разработки: TDD и виды проверок](development-method.md); конкретный runtime-пакет и допуск определяются отдельно |

## От требования к коду и доказательству

Это выборочная навигация, а не новая полная матрица покрытия. Приёмочные
формулировки остаются в [ART-09](analysis/09-acceptance-criteria-and-traceability.md),
а история исполнения — в [tasks](../specs/001-corpus-replenishment/tasks.md) и отчётах.

| Область | Требование / проект | Код | Проверка / ограничение |
|---|---|---|---|
| Подготовка областей | [LLD §5](architecture/nail-search-lld.md#5-точная-подготовка-фото--g2-approved_by_owner) | [NailImageProcessor](../src/product_search/search/nail_image_processor.py), [binding локализатора](../services/candidate_i/binding.py) | [Тесты](../tests/test_nail_image_processor.py), [раздельная runtime-проба](../specs/corpus-optimization/staged-resource-report.md) |
| Стадии и сохранение | [ФТ](../specs/corpus-optimization/functional-requirements.md), [checkpoint LLD](../specs/001-corpus-replenishment/contracts/checkpoint.md) | [Ядро пополнения](../src/product_search/search/corpus_replenishment.py), [репозиторий](../src/product_search/infrastructure/replenishment_repository.py) | [Тесты RESUME](../tests/test_replenishment_resume.py), [покрытие восстановления](../specs/001-corpus-replenishment/recovery-coverage-review.md) |
| Публикация | [ФТ](../specs/corpus-optimization/functional-requirements.md), [catalog LLD](../specs/001-corpus-replenishment/contracts/catalog.md) | [Приложение пополнения](../src/product_search/infrastructure/replenishment_application.py), [репозиторий](../src/product_search/infrastructure/replenishment_repository.py) | [Тесты публикации](../tests/test_replenishment_publication.py), [20 фото](../specs/001-corpus-replenishment/four-batches-runtime-report.md); рабочий cutover отдельно |
| Процессы и ожидание | [ФТ](../specs/corpus-optimization/functional-requirements.md), [lifecycle LLD](../specs/001-corpus-replenishment/contracts/lifecycle.md) | [Supervisor](../src/product_search/infrastructure/replenishment_supervisor.py), [workers](../src/product_search/infrastructure/replenishment_workers.py) | [Тесты lifecycle](../tests/test_replenishment_lifecycle.py), [тесты ожидания](../tests/test_replenishment_waiting.py) |
| Ресурсное наблюдение | [ФТ](../specs/corpus-optimization/functional-requirements.md), [разбор telemetry fix](../specs/001-corpus-replenishment/telemetry-atomic-snapshot-fix.md) | [MacResourceObserver](../src/product_search/infrastructure/replenishment_runtime_binding.py), [private_json](../src/product_search/infrastructure/replenishment_cli.py) | [Тесты binding](../tests/test_replenishment_runtime_binding.py); [Два фото после исправления прошли](../specs/corpus-optimization/remaining-quality-report.md); точная причина прошлого STOP не доказана |
| Монитор и журнал | [Операционный журнал](../specs/001-corpus-replenishment/operation-logging.md), [лёгкий монитор](../specs/001-corpus-replenishment/light-monitoring.md) | [Монитор](../src/product_search/infrastructure/replenishment_monitor.py), [журнал](../src/product_search/infrastructure/replenishment_operation_log.py) | [Тесты монитора](../tests/test_replenishment_monitor.py), [runtime-отчёт](../specs/001-corpus-replenishment/monitor-runtime-report.md) |
| Сопоставление и ранг | [LLD §6–8](architecture/nail-search-lld.md#6-векторы-и-формула) | [nail_matching](../src/product_search/search/nail_matching.py), [nail_service](../src/product_search/search/nail_service.py) | [Оценка семи запросов](../specs/corpus-optimization/remaining-quality-report.md); балл не является вероятностью |

## Как читать статусы

Статус утверждённого требования, выполнение задачи, успешный синтетический тест,
реальный ML-прогон и приёмка качества отвечают на разные вопросы.
Правила доказательности определены в [governance](analysis/governance.md#4-источники-и-доказательность).

HLD поиска и пакет `nail-search-v1` содержат собственные статусы документов и
отдельно утверждённых контрактов. Более поздняя реализация сама по себе не
переводит весь проект документа в APPROVED_BY_OWNER. G2/G3 feature локализатора
также не равны историческим Gate 2/Gate 3 всего проекта.

В истории кодовое имя `Candidate I` и обозначение `I` означают локализатор;
путь `services/candidate_i/` остаётся точным идентификатором кода.
Grounding DINO внутри локализатора и embedding-модель DINOv2 — разные компоненты.

Для нового изменения сначала определяется владелец содержания: требования,
данные, NFR, архитектура или проверка. Канонический документ выбирается по
[контрактам артефактов](analysis/artifact-contracts.md); сводки дают ссылки,
а не вторую нормативную формулировку. История не выдаёт повторный runtime-допуск.
