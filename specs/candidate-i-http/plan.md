# План реализации: Candidate I через HTTP

**Branch**: `codex/task-quality-journal` — ветка документов, не автоматически выбранная ветка product code. **Дата**: 2026-10-07. **Spec**: [входная спецификация](spec.md).

**Input**: spec.md маршрутизирует утверждённый HTTP v0.1 и остальные проектные документы. Статус плана: `DRAFT_FOR_OWNER_REVIEW`. План не разрешает реализацию, установки, model calls, БД или корпус. Подготовка — STANDARD, без новых нормативных решений.

## Summary

Подключить отдельный локальный сервис I через application-owned NailLocalizationPort. Начать с HTTP-клиента/fake-сервиса, затем серверная обвязка и guards, pure ядро, repository/Web doubles, отдельно разрешённая ML-стыковка и ручная оценка. Основная система формирует crops, embeddings и рейтинг; I только выделяет области. Backlog DEFERRED.

## Technical Context

| Поле шаблона | Основа / предел знания |
|---|---|
| Language/Version | Python >=3.12,<3.13 по product pyproject; installed patch проверяется в этапе 0 |
| Primary Dependencies | HTTPX client, Pillow codec, FastAPI server, pytest/Ruff. Source lock поиска: HTTPX 0.28.1, Pillow 11.3.0, FastAPI 0.141.1; это не installed I inventory |
| Storage | Fake часть — synthetic memory/temp fixtures; позже existing PostgreSQL/pgvector и private image-store за портами; I без SQL |
| Testing | TDD, fake HTTP/binding, semantic negative fixtures, AST imports, controlled concurrency/cleanup; synthetic DB отдельно; real ML/data после разрешения |
| Target Platform | Mac arm64, loopback, два Python процесса/lock, shared device/coordinator root |
| Project Type | Backend client, отдельная HTTP-обвязка I, новый use case в existing Python-проекте |
| Performance Goals | SLA не утверждён. Top-10 на примерах владельца обязателен, top-3 желателен; это качество выдачи, не latency benchmark |
| Constraints | PNG 20 MiB, metadata 8 KiB, body 20 MiB+64 KiB; finite operational values до real startup; без auto POST retry/jobs/silent CPU fallback |
| Scale/Scope | Один in-flight I; existing 1–4 фото одного товара; одинаковые query/catalog profiles; NEW вручную |

HTTPX declared только dev: runtime declaration и I HTTP bill готовятся отдельно. Operational values — явные inputs будущего запуска, а не придуманные defaults. Invalid/unset values блокируют real startup, fake tests используют свои values. В [research](research.md) архитектурные варианты разрешены; неполученные measurements и approvals не названы полученными.

## Constitution Check

`.specify/memory/constitution.md` — незаполненный, не ратифицированный шаблон. Его placeholders не нормативны, дополнительных применимых gates нет. Действуют [AGENTS](../../AGENTS.md), [governance](../../docs/analysis/governance.md), [TDD](../../docs/development-method.md); constitution не редактировалась.

| Gate до Phase 0 | Результат |
|---|---|
| Scope/authority | PASS в границе планирования: approved wire переиспользован, остальной LLD сохраняет статус |
| Без speculative backlog | PASS: J/Sheets/VM/users/categories исключены |
| Core-owned boundaries | PASS как план: текущие ports/DTO; SDK/HTTP/DB снаружи |
| Без restricted/runtime операций | PASS: read-only research, без моделей/БД/установки |
| Один автор | PASS: исполнитель пишет план, research agent только собирает evidence, не planner/author |
| Сохранение состояния | PASS: Git не переключался, feature.json не перезаписан |

Post-design check: те же gates PASS в границе планирования. Это не PASS ратифицированной constitution, real runtime или всех HLD/LLD решений. Ни один неизвестный operational input не обойдён: он указан ниже как stage prerequisite.

## Project Structure

### Documentation

```text
specs/candidate-i-http/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/README.md
```

[tasks.md](tasks.md) создан отдельным speckit-tasks после указания владельца «Продолжай»; задачи ещё не исполнялись. Approved contract/OpenAPI остаются в docs/architecture без независимой копии.

### Source Code — предлагаемые места в выбранном product checkout

Поздний код сейчас в `.codex/worktrees/1eaf/Ai`, HEAD ba49504; есть изменённые README/developer-guide/service docs. Это наблюдение, не разрешение писать поверх них.

| Область | Ответственность |
|---|---|
| `src/product_search/search/nail_contracts.py`, `nail_ports.py` | Минимальные DTO/localization port; остальные роли добавляются со своим этапом |
| `src/product_search/infrastructure/nail_ml_adapters.py` | HTTP client/codec, позднее embedding facade; fake import не загружает Torch/I |
| `services/candidate_i/app.py`, `settings.py`, `binding.py` | Server facade, readiness/admission, existing I binding, отдельный bill |
| `tests/support/candidate_i_fake_server.py`, `tests/test_candidate_i_http_loopback.py` | Test-only сервер с fake binding и управляемая loopback-проверка в отдельном процессе, без I/models |
| `src/product_search/infrastructure/nail_runtime.py` | Конкретные guards из approved контракта; предложенное место, не новый core port |
| `infrastructure/nail_image_store.py`, `search/nail_image_processor.py`, `search/nail_matching.py` внутри src/product_search | External decode/storage, core crops и pure solver |
| `search/nail_service.py`, `nail_catalog_build.py`, `infrastructure/nail_repository.py` | Orchestration/build/readiness и SQL adapter |
| `main.py`, `web/app.py`, `search/multiphoto.py`, `search/evaluation.py`, `infrastructure/evaluation_repository.py` | New-mode wiring/state/evidence при сохранённом legacy |
| `scripts/build_nail_representation.py`, новая migration после actual head | Разрешённый build и additive schema |

Existing main.py импортирует Torch/psycopg и создаёт DB инфраструктуру; fake tests не запускают его. Existing tests дают patterns, не готовое покрытие нового режима.

## Этапы реализации

| Этап | Вход / gate | Проверяемый результат |
|---|---|---|
| **0. Контекст исполнения** | План рассмотрен; выбран executor/checkout/ref | Actual HEAD/dirty state/права записи, test Python/dependencies и путь/version/hash approved контракта зафиксированы; existing изменения сохранены. Отсутствие dependency → bill, не auto install |
| **1. HTTP client + fake** | Approved wire; minimal core DTO mapping рассмотрен в рамках плана; модели/БД не нужны | `test_candidate_i_http_adapter.py`, `test_nail_dependency_boundaries.py`: PNG RGB round-trip, multipart/schema, identity/checksum/full-frame mask/bbox/ordinal, NO_NAILS vs error, no retry/unknown status, import guards |
| **2. I-server с fake binding** | Bill web/codec/test dependencies принят; I working среда не переписывается | `test_candidate_i_http_service.py`: два endpoints, bounded input/strict JSON, profile mismatch до binding, SEGMENTER_EMPTY не NO_NAILS, single executor, BUSY/health, безопасные errors/spool cleanup. `test_candidate_i_http_loopback.py` запускает support fake server subprocess, получает ephemeral loopback endpoint, проверяет real HTTP round-trip и гарантированно завершает процесс/удаляет private namespace |
| **3. Guards и runtime bill** | Private root и proposed finite inputs до real startup | `test_nail_runtime.py`: отдельные query/admission/device/coordinator guards, cross-process fake lease, нет parent lock во время HTTP, timeout/disconnect не освобождает actual resource, invalid config не ready. Read-only actual inventory/bill, не model smoke |
| **4. Crops/matcher/embedding facade с fake** | Приняты точные EXIF/RGB/bbox/cosine/precision/solver/tie детали LLD | `test_nail_image_processor.py`, `test_nail_matching.py`, `test_nail_embedding_adapter.py`: white crop, half-open bbox, invalid region → отказ фото, exhaustive oracle малых матриц/greedy trap, missing0/no repeats/ties, три полных model vectors, same profiles |
| **5. Catalog/repository/evidence** | Schema/coverage приняты; разрешена отдельная synthetic DB | `test_nail_repository.py`, `test_nail_migration_integration.py`, `test_nail_evidence.py`: actual-head additive migration, atomic writes/publish/finalize, all-NO_NAILS не publish, NULL/ownership/profile mismatch, READY immutability, empty upgrade/downgrade и populated отказ, legacy RRF сохранён |
| **6. Search/Web/session с doubles** | Предыдущие core/repository contracts; synthetic данные | `test_nail_service.py`, `test_nail_web.py`: up to 10, all-NO_NAILS NEED_MORE, pending после первого success, failed rerun сохраняет previous выдачу и блокирует stale finalize, success reset labels, final rollback, late response не commit |
| **7. Real ML стыковка** | Exact bills/locks/models/fingerprints/finite parameters и отдельные permissions | [План Mac](../../docs/architecture/mac-common-environment-plan.md): detector, synthetic segmenter, три providers, HTTP/device residency/cleanup в bounded серии. Exact profile report; fake/import PASS не подменяет результат |
| **8. Corpus и ручная оценка** | Inventory/data/build отдельно разрешены, coverage предъявлен | Отдельная representation/terminal outcomes/minimum OK; владелец оценивает top-10/top-3 и SAME_PRODUCT/NEW. Активация/rollback отдельным решением; без baseline mandatory run и старых claims |

Все тестовые имена выше — будущие файлы в tests выбранного checkout, NOT_CREATED сейчас. Реализация один раз, TDD; review по AGENTS, не новая церемония на каждый assert. Read-only bill этапа 3 можно готовить независимо от fake частей. Commit/push/merge автоматически не разрешены.

## Входы и стоп-точки исполнения

| Неизвестное / не принято | Перед какой работой закрыть | Не блокирует |
|---|---|---|
| Writable checkout/ref и сохранение dirty | Этап 0 | Планирование |
| Minimal DTO mapping, остальные LLD решения | Review плана/соответствующего контракта; не расширять wire approval на весь пакет | Read-only research и wire fixtures |
| Declared/source pins vs installed | Inventory, exact bill и разрешение до установки | Fake тесты при реально доступных dependencies |
| Finite deadlines/decoded pixels/regions/response/solver/memory | Runtime bill до real startup, test values не defaults | Parameterized fake components |
| I lock/new web packages/residency | Раздельная техническая проверка | HTTP fake и pure matcher |
| Physical schema/coverage/DB/data permission | Этапы 5/8 | In-memory doubles |

## Review Focus и self-review

| Риск | Проверка плана |
|---|---|
| Формально decoded, но неверные mask pixels/identity | Этапы 1–2: semantic negative fixtures, отказ фото |
| Timeout вызвал повтор или early unlock | Этапы 1/3/6: controlled concurrency/late commit |
| Родительская device lease блокирует I | Этап 3: два synthetic процесса, non-blocking guards |
| Добавлены фото, сохраняется старый run | Этап 6: input revision/checksum, stale finalize |
| Empty/partial representation или mixed evidence | Этапы 5–6: readiness/ownership/transaction regressions |

Self-review: spec coverage есть по stages, типы/роли берутся из канонических contract/LLD, pending inputs видны, no backlog/generalized model, commands/проверки относятся к будущей реализации. Technical Context не оставлен шаблоном; operational inputs не названы результатами измерений.

## Complexity Tracking

Применимые project gates не нарушены. Раздельный сервис и ports уже выбраны. nail_runtime.py реализует существующие concrete guards, не универсальную платформу. Дополнительных constitution требований нет; её template не выдаётся за нормативный документ.

## Completion Report

Phase 0: [research](research.md). Phase 1: [data model](data-model.md), [contracts](contracts/README.md), [quickstart](quickstart.md). Speckit-plan закончился до code execution. Далее владелец разрешил speckit-tasks; [чек-лист](tasks.md) подготовлен отдельно с сохранением всех stage gates. Создание задач не означает их выполнение.


Фактическое исполнение T001–T019: [execution-context](execution-context.md); 146 tests PASS в объявленном fake/relevant regression scope, independent review PASS. Следующие stages не начаты.
