# Phase 0: решения и основания плана

Дата: 2026-10-07. Read-only research; runtime/install/models/DB NOT_RUN. Исследователь `/root/http_plan_research` не редактировал файлы и не был planner/author.

## 1. Scope и контракт

**Decision:** approved HTTP v0.1 — вход первой части; HLD/LLD сохраняют pending details. spec.md — индекс источников.

**Rationale:** владелец утвердил wire и смысловые правила, не все physical/numeric/runtime детали. План не закрывает их своими строками.

**Alternatives considered:** считать весь HLD/LLD approved, создать универсальный spec. Отклонено из-за потери статусов/scope.

## 2. Spec Kit и constitution

**Decision:** `specs/candidate-i-http`, явный absolute FEATURE_DIRECTORY и NO_PERSIST, existing Git-ветка не меняется. Constitution template не имеет активных принципов; check по AGENTS/governance, без ратификации.

**Rationale:** первый setup дал ERROR отсутствующего feature context. Явная настройка устраняет setup-пробел и не перезаписывает feature.json других чатов. Placeholder constitution не нормативен.

**Alternatives considered:** новая бизнес-спецификация/constitution, Git branch только ради инструмента. Сейчас не требуются.

## 3. Dependencies

**Decision:** HTTPX client, Pillow codec, FastAPI server с injected binding; source pins как bill candidates, не installed/compatibility proof.

**Rationale:** product pyproject: Python >=3.12,<3.13, Pillow >=10,<12, FastAPI >=0.115,<1. HTTPX >=0.28,<1 только dev. Gate3 lock: HTTPX 0.28.1, Pillow 11.3.0, FastAPI 0.141.1. Pytest >=8.3,<9 и Ruff >=0.8,<1 declared, exact installed UNKNOWN. Production HTTPX needs runtime declaration/bill. main.py импортирует Torch/psycopg и собирает DB, не safe fake entry.

**Alternatives considered:** handwritten multipart/HTTP, новые installs сейчас, merged I/backend. Нет пользы для принятого контракта; не выполнялись.

Sources относительно product checkout: pyproject.toml, scripts/requirements-gate3-macos-arm64.lock, src/product_search/main.py. Lock не подтверждает пригодность любой комбинации. Library choice в плане не разрешает менять dependencies.

## 4. Test patterns

**Decision:** synthetic PNG/arrays, fake HTTP/binding, existing TestClient pattern; новый harness и AST/import tests нового core.

**Rationale:** tests/test_search_upload.py, test_web.py, test_v3_loopback_harness.py, test_multiphoto.py, test_evaluation.py, test_evaluation_retention.py дают doubles. V3 harness in-process ASGI, не готовый I-service. test_dependency_boundaries.py покрывает старую ограниченную границу, не новый core. tests/nail_localization/test_langsam_adapter_contract.py имеет fake I outputs. J tests не включаются.

**Alternatives considered:** старт с real I или считать existing suite полным покрытием. Смешивает contract/runtime/quality.

## 5. Неизвестные runtime значения

**Decision:** explicit validated operational inputs до real startup; fake fixtures имеют только test values, без production defaults.

**Rationale:** wire caps приняты; finite deadlines, decoded pixels, region/response/solver/memory и exact I inventory UNKNOWN. Их значения не нужны для параметризованного дизайна, но обязательны перед реальным запуском. Ручной контроль Mac-фото не численный memory/time ceiling.

**Alternatives considered:** произвольные числа для «закрытия» Phase 0, новая stress program, отсутствие caps. Не соответствуют scope/доказательности.

## 6. Leases

**Decision:** отдельные query/admission/coordinator/device guards; device lease у actual executor, никогда у backend при ожидании HTTP; no auto retry/jobs.

**Rationale:** [контракт §7](../../docs/architecture/candidate-i-http-contract.md#7-занятость-deadline-и-общий-ресурс-mac) исключает nested deadlock/early release. I работает со своими bytes; late response не commit. Device guard охватывает load/inference/unload обоих процессов.

**Alternatives considered:** parent device lock на весь pipeline и повторный lock I, retry queue. Первое deadlock, второе duplicate inference.

## Итог

Варианты конструкции Phase 0 разрешены. Неполученные operational inputs и approvals остаются [stage gates](plan.md), не названы результатами измерений. Phase 1 извлекает existing данные/контракты и validation guide; не принимает новый numeric/schema scope.
