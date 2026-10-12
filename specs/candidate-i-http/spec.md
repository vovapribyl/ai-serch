# Входная спецификация плана Candidate I HTTP

| Поле | Значение |
|---|---|
| Дата / статус | 2026-10-07; индекс источников для speckit-plan, не новая нормативная спецификация |
| Основание | Просьба подготовить план и явно использовать speckit-plan |
| Утверждённый вход | [HTTP-контракт v0.1](../../docs/architecture/candidate-i-http-contract.md), [OpenAPI](../../docs/architecture/candidate-i-http.openapi.json) — APPROVED_BY_OWNER |
| Архитектурные проекты | [HLD v0.5](../../docs/architecture/nail-search-hld.md), [LLD v0.4](../../docs/architecture/nail-search-lld.md) — остальные детали сохраняют свои статусы |
| Эксплуатационный вход | [План Mac](../../docs/architecture/mac-common-environment-plan.md); значения runtime и bill требуют подготовки до реальных запусков |
| Правила процесса | [AGENTS](../../AGENTS.md), [governance](../../docs/analysis/governance.md), [метод TDD](../../docs/development-method.md) |

## Цель и граница

Подготовить план подключения отдельного HTTP-сервиса Candidate I к новому поисковому режиму через порт ядра. Первая исполнимая часть — HTTP-клиент с fake-сервисом по принятому wire-контракту. Последующие части включают I-service, подготовку crops/matcher, каталог, Web/session/evidence и ограниченные технические пробы, но стартуют только после своих явно обозначенных входов и разрешений.

Этот файл маршрутизирует существующие документы, не заменяет их. Для fields/HTTP codes/identity/mask formats каноничен контракт. Для новых core DTO/ports/schema/numeric деталей каноничен проект LLD, который нельзя принять молча через план. Утверждение HTTP не является утверждением всего ядра/миграций и не разрешает model calls или corpus build.

## Принятые решения и наблюдаемое поведение

- Два Python-окружения на Mac; I отделён от backend и получает изображение прямо в POST.
- Один синхронный вызов на нормализованное RGB PNG; metadata multipart; ответ JSON с full-frame PNG-масками Base64. Детали полностью в контракте.
- После валидных masks ядро делает отдельные crops с белым фоном, три embedding providers кодируют каждый ноготь.
- Все технически корректные области участвуют; pairs без повторов; среднее по моделям/ногтям, missing0, лучшая пара ракурсов, без бонуса количества.
- Тот же товар должен быть в top-10 на примерах владельца; top-3 желателен. Качество и NEW оценивает владелец вручную.
- Размеры Mac-фото владелец контролирует вручную в пределах ранее испытанных; точные исторические размеры не объявлены известными. Existing upload validation сохраняется.
- Technical error/timeout/INDEX_EMPTY/NO_NAILS не означает NEW и не включает автоматический fallback.

## Не входит

Sheets-импорт, VM/интернет, users/auth, universal categories, Candidate J, jobs/очередь, speculative ports/entities, автоматический threshold отсутствия товара, повтор старых calibration/evaluation, работа с данными или Git-публикация.

## Открытые входы исполнения

1. Target checkout/ref и безопасный способ сохранить existing dirty state выбираются до изменения product code.
2. Core DTO mapping, физическая schema и точные cosine/precision/solver/tie детали принимаются перед зависящими этапами; план их не переопределяет.
3. Runtime values — finite connect/write/read/overall deadlines, decoded pixels, region/response/solver/memory limits — готовятся в bill до model-backed стартов. В первой fake-части используются только явные тестовые значения.
4. Фактический I inventory, версии новых HTTP dependencies и resource residency получают проверяемые inputs до установки/model load. Здесь не создаётся фиктивный merged lock.

Это известные stage prerequisites, а не неразрешённые варианты дизайна Phase 0. Нельзя подставлять числа/approved статусы, чтобы сделать план выглядящим исполнимым целиком.

## Проверка полноты плана

Должны быть видны последовательность работ, outputs/test scenarios каждого этапа, gate перед I/models/DB/data, роли contract и архитектурных проектов и отсутствие требований backlog. tasks.md создаётся отдельным speckit-tasks; код не пишется в speckit-plan.

## Истории для декомпозиции speckit-tasks

Это группировка уже описанных результатов, не новые требования или нормативные ID. US1–US5 — локальные метки этого feature directory; P1–P5 — порядок подготовки increments, не изменение бизнес-приоритета владельца. TDD применяется по действующему методу; test tasks нужны явно.

| Метка / приоритет | Получатель и результат | Независимая проверка |
|---|---|---|
| US1 / P1 | Разработчик получает рабочую HTTP-границу с fake-I, не подключая реальные модели | Synthetic PNG → HTTP → валидные masks/NO_NAILS/errors; lease/timeout/no retry; core imports изолированы |
| US2 / P2 | Поисковый сценарий готовит crops и ранжирует synthetic товары в памяти | Fake image/localization/providers/catalog, independent matcher oracle, лучший ракурс и до десяти кандидатов |
| US3 / P3 | Оператор может готовить представление и работать с выдачей/разметкой через existing Web, synthetic DB | Readiness/publish/transaction constraints, legacy RRF/evidence, stale finalize и rerun через doubles |
| US4 / P4 | Раздельные реальные I/providers и HTTP-контур технически проверены на разрешённой синтетике | Exact bills/identity и detector/segmenter/provider/resource report, не утверждение качества товаров |
| US5 / P5 | Владелец получает разрешённое новое представление и оценивает поиск на своих примерах | Coverage, observed top-10/желательный top-3, ручной SAME_PRODUCT/NEW; activation отдельным решением |

Истории US2–US5 сохраняют входные gates плана. US1 — предлагаемый минимальный первый increment; он не считается готовым nail-search продуктом.
