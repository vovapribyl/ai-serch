# Phase 1: проверка после реализации

> Порядок проверок исторической feature; не автоматический сценарий продолжения. [Текущий контекст](../corpus-optimization/project-context.md) · [Карта проекта](../../docs/project-map.md).

Это будущие validation scenarios [плана](plan.md). Feature tests/service paths ниже ещё NOT_CREATED/NOT_RUN. Перед командами выполнить этап 0: выбран writable checkout, проверены HEAD/dirty state/interpreter/dependencies, зафиксирован approved contract. Ветка документов не содержит поздний product code.

Уточнение исполнения 2026-10-08: T001–T042 реализованы и проверены в fake/synthetic managed worktree; [фактический контекст](execution-context.md). Real I/actual verification factory/real CLI assembly/corpus ещё не выполнялись. Исходные пометки NOT_CREATED/NOT_RUN ниже относятся к моменту планирования; текущий статус определяется tasks.md и execution-context.

### Повтор фактического fake increment

Для существующего тестового окружения без установки пакетов:

```bash
export TEST_PYTHON="$DOCUMENTATION_ROOT/.venv/bin/python"
export PYTHONPATH="$IMPLEMENTATION_ROOT:$IMPLEMENTATION_ROOT/src:$IMPLEMENTATION_ROOT/.superpowers/sdd/plan/test-deps"
cd "$IMPLEMENTATION_ROOT"
PYTHONDONTWRITEBYTECODE=1 "$TEST_PYTHON" -B -m pytest tests/test_nail_contracts.py tests/test_nail_dependency_boundaries.py tests/test_candidate_i_http_adapter.py tests/test_candidate_i_http_service.py tests/test_nail_runtime.py tests/test_candidate_i_http_loopback.py -q -o addopts=''
```

Это использованный read-only interpreter/overlay, не предлагаемый lock реального I. Loopback использует только свой fake subprocess на ephemeral 127.0.0.1; в restricted sandbox может потребоваться разрешённая точечная execution escalation. Не считать неуспешный запуск из-за sandbox доказательством failed API behavior. Legacy test_web требует отсутствующий Torch; не устанавливать модели ради fake проверки.

## 1. Контекст

### Повтор synthetic US2

После определения IMPLEMENTATION_ROOT/DOCUMENTATION_ROOT использовать TEST_PYTHON и PYTHONPATH из примера выше. В code worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 "$TEST_PYTHON" -B -m pytest \
  tests/test_nail_contracts.py tests/test_nail_dependency_boundaries.py \
  tests/test_nail_image_store.py tests/test_nail_image_processor.py \
  tests/test_nail_matching.py tests/test_nail_embedding_adapter.py \
  tests/test_nail_service.py -q -o addopts='' -p no:cacheprovider
```

Фактический scoped результат — 99 PASS; общий US1/US2/relevant legacy — 220 PASS, точная команда в [отчёте](execution-context.md#synthetic-us2--t020t031). Это fake/synthetic проверка, не real quality. Полный suite collect-only имеет четыре missing-Torch ошибки; до model/DB разрешений его выполнение не предлагается.

Задать IMPLEMENTATION_ROOT и DOCUMENTATION_ROOT как абсолютные пути выбранного product checkout и документации; не менять HOME/CODEX_HOME.

```bash
cd "$IMPLEMENTATION_ROOT"
test -x .venv/bin/python
export PYTHONPATH=src
export CANDIDATE_I_CONTRACT_PATH="$DOCUMENTATION_ROOT/docs/architecture/candidate-i-http.openapi.json"
test -f "$CANDIDATE_I_CONTRACT_PATH"
```

Отсутствующий interpreter/dependency → STOP до exact bill и разрешённой подготовки. Нет pip install/Docker/migrate/main запуска. Feature test loader читает этот contract path или проверенную копию в product checkout, не произвольный API по сети.

## 2. Первый результат: client + fake HTTP

После создания файлов этапа 1:

```bash
.venv/bin/python -m pytest tests/test_candidate_i_http_adapter.py tests/test_nail_dependency_boundaries.py -q
.venv/bin/python -m ruff check src/product_search/search/nail_contracts.py src/product_search/search/nail_ports.py src/product_search/infrastructure/nail_ml_adapters.py tests/test_candidate_i_http_adapter.py tests/test_nail_dependency_boundaries.py
```

Expected: PNG round-trip сохраняет RGB; exact metadata/identity, masks/bbox/ordinal; NO_NAILS отдельный outcome, error/timeout не retry; core не импортирует HTTP/Pillow/SDK. Реальные модели/БД не нужны. GREEN только после actual test output.

## 3. Server/guards с fake binding

После этапов 2–3 и принятой dependency подготовки:

```bash
.venv/bin/python -m pytest tests/test_candidate_i_http_service.py tests/test_nail_runtime.py -q
.venv/bin/python -m pytest tests/test_candidate_i_http_loopback.py -q
```

ASGI tests используют injected fake, не доказывают сеть/раздельную environment. Controlled concurrency проверяет BUSY/health/cancel; synthetic subprocesses — shared guard без ML. Profile/input failures не доходят до binding, private spool очищен, backend не держит device lease при HTTP.

Loopback test fixture запускает `tests/support/candidate_i_fake_server.py` с fake binding, disposable private root и ephemeral endpoint. Проверяет direct PNG POST/ответы через настоящий HTTP-клиент, затем завершает процесс и очищает только свой namespace. Production I app с реальными моделями не используется как fake runner. Это runnable сценарий после этапа 2, сейчас NOT_CREATED/NOT_RUN.

## 4. Core и Web doubles

После принятых точных деталей и этапов 4/6:

```bash
.venv/bin/python -m pytest tests/test_nail_image_processor.py tests/test_nail_matching.py tests/test_nail_embedding_adapter.py -q
.venv/bin/python -m pytest tests/test_nail_service.py tests/test_nail_web.py -q
```

Expected: same preprocessing, exhaustive oracle малых матриц, no repeats/missing0/mean, complete models, all-NO_NAILS NEED_MORE; failure rerun сохраняет previous candidates но блокирует stale finalize, late response не commit. Web создаётся с doubles, main.py не импортируется как runner.

## 5. Отдельные реальные gates

G3 synthetic DB уже разрешена и проверена, как указано в [US3 отчёте](execution-context.md#synthetic-us3--t032t042). Для повтора использовать его точную команду и `.superpowers/sdd/plan/g3-test-deps` вместе с прежним test-deps overlay. **303 scoped PASS**; helper всегда создаёт новый owned tmpfs контейнер из cached image `--pull=never`, проверяет marker и удаляет только свои ресурсы. Не подставлять рабочую DB или fixed-port legacy integration credentials. Прямой build CLI отказывает до real G4/G5 assembly; `run_build` используется только с уже допущенным injected runner.

| Проверка | Предусловие | Свидетельство |
|---|---|---|
| Synthetic DB/migration | Schema принята; отдельная DB операция разрешена, external env привязан к ней | test_nail_migration_integration.py после проверки DB identity; exact env/command готовится в этапе 5 без URL/secrets в плане |
| Real I/providers | Exact bills/locks/models/finite profiles и permissions | [План Mac](../../docs/architecture/mac-common-environment-plan.md); detector/segmenter/provider/HTTP/resource report |
| Corpus build | Inventory/data/build разрешены | CLI command после принятого профиля; coverage/readiness, без auto activation |
| Качество | Разрешённые примеры владельца и готовый режим | Top-10/top-3 наблюдения, ручной SAME_PRODUCT/NEW |

Не подставлять выдуманные env/model paths. Неисполненные gates не блокируют fake проверки, но блокируют свои real операции.

## 6. Проверка изменения

```bash
.venv/bin/python -m ruff check src tests
git diff --check
```

Relevant existing upload/multiphoto/evaluation regressions — в соответствующем этапе; весь integration suite без target DB проверки не запускается. Fake tests не доказывают качество/runtime. Handoff: actual commands/results, files, unresolved gates и следующий ограниченный шаг по [методу](../../docs/development-method.md).
