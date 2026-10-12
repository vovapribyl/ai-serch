# T051 — actual native bindings, без ML

2026-10-10. Owner «Разрешаю, начинай» на подготовку к ручному тестированию.
**Bindings/model-free checks PASS.** На2026-10-10 input scope ожидал owner choice;
2026-10-11 утверждён и подготовлен [отдельный набор674](oversize-input-report.md). Corpus build,
query inference, READY/publish/activation не выполнялись. T051 `[ ]`.

## Scope и план

[План](native-bindings-plan.md): реальные SDK/PostgreSQL/HTTP/build/query ports,
actual G4 metadata/interpreters/model manifests, metadata-only I startup. Исполнитель
inline/TDD, один independent read-only reviewer. Исходные фото, их права, исходный
manifest674, old source/config/env/weights/G4 fingerprints не менять.

Историческое состояние2026-10-10: отдельно задан owner вопрос — первый временный test subset673 без oversize фото либо
ожидание всего корпуса674. Ответ ещё не получен; subset/новый input manifest не
созданы, exclusion/resize/cap change не выполнялись. Предложение673 не является
утверждённым scope или coverage exception.

## Actual model-free evidence

| Проверка | Фактический результат |
|---|---|
| I assembly bytes | SHA70e0b2adba4800b58293dbe5ca276fe78ed7b713c88f7d99164d99d96b4c8fb8 совпал с T049 reference |
| I profile bytes | SHA21930c217ac72038792e8fbd688703e2b58a115f5acefb03d1ee38d47d7b4a03 совпал |
| Interpreters | Actual I89packages/backend71packages, Python3.12.14/arm64; backend canonical packageSHA d2b79438... совпал, actual SQL driver psycopg3.3.5 |
| I actual bootstrap | Настоящий `assemble_service` в I environment успешно сконструировал app и проверил manifest; Torch/Transformers не импортированы |
| Три backend manifests | Actual bytes совпали с accepted manifests OpenCLIP/DINOv2/SigLIP2; без SDK imports/load/inference |
| I HTTP readiness | Actual temporary loopback server GET /health/ready200, readytrue и fingerprint6cccc473... совпали; metadata-only POST403 до binding |
| Teardown I | Завершён только созданный process, old runtime/server/logs не перезаписаны; health-entry startup probe noTorch/noTransformers |
| Actual backend ports | В accepted backend71 env сконструированы реальные Postgres/HTTP/build/query adapters; actual target Docker/SQL identity PASS, representations0/pointers0; SDK imports отсутствуют |

Поиск exact приватных locators выполнялся по точному историческому runtime rollout,
после чего все перечисленные факты проверены live; старое evidence не подменяет
эти checks. Из18existing historical interpreter candidates выбраны exact package
matches; aliases не считаются разными измеренными environments. Полные private
paths/IDs/descriptors/credentials не публикуются.

## Изменение → код → проверка

| Изменение | Код / проверка |
|---|---|
| Lazy реальные provider factories | [nail_native_bindings.py](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_native_bindings.py): accepted revisions/manifests/dimensions, local roots/MPS. Default permit closed; actual manifest digest/bytes проверяются до SDK import; admitted constructor seam проверен test doubles, не реальными loads |
| Real catalog/build/search/query ports | PostgresNailCatalog, ManifestImageStore/NailImageStore, HTTP adapter, existing build/search services и NailQueryRunner; preparation constructors не читают source photos/не создают BUILDING |
| Execution entry | `execute_build` требует native permit и explicit input/runtime checks; target gate и shared coordinator до core execute. I request/provider load также gated; public build facade проходит этот же entry, catalog/search catalog read-only, publish не экспортируется |
| READY query context | `ready_query_context` фиксирует representation/corpus/profile; wrong requested ID/BUILDING/not-ready не допускает query input processing; revisions дополнительно проверяет existing search core |
| Metadata-only I endpoint | [health_entry.py](../../../../../.codex/worktrees/candidate-i-http/Ai/services/candidate_i/health_entry.py): actual pinned assembly/loopback FD; только GET /health/ready, все остальные routes/methods403 |

[Tests](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_native_bindings.py):
13новых checks: прежние11 плюс прямой обход build/catalog/publish и изменённый local manifest до SDK import.
Фактическая weighted SDK construction не проверена; preparation не выдаётся за ML
compatibility/quality или новый runtime acceptance.

## Private freeze

New root700, metadata/logs/descriptors/source archive600, old artifacts сохранены.
Descriptor содержит actual I assembly/interpreters/model-root/target/current code
identities, `native_admission=false`, `input_scope=PENDING_OWNER_CHOICE_673_OR_674`.

- Descriptor SHA: `eec4e495b02a72c2786177dfad1e9879deec36faa4adc6e50484aecd00d0f4b7`.
- Verified source archive v3 SHA: `de34d866f8dcc4040575f4ad012bc14964920c0ae2341ec71a411dc9f60cf812`.

V1/v2 snapshots сохранены отдельно, v3 фиксирует исправление review. Actual model-free I log/backend report private;
исходные manifests не переписывались. Тестовый source inventory/representation ID,
точный native worker job и execution permit пока не сформированы: зависят от source
scope/actual command/bounds, не от произвольного default.

## Verification и следующая зависимость

Observed RED→GREEN для новых boundaries; targeted59PASS, final relevant337PASS/46SKIP,
32files,2dependency warnings (Starlette/httpx и anyio alias). Native/DB smoke opt-ins выключены; actual I metadata
HTTP и target counts проверены отдельно. Ruff3newfiles/diff PASS. Full project/native
inference suite не запускался, installs/downloads/SDK/model operations отсутствуют.
Ponytail/TDD/verification; Clean Architecture mini commit893a88a6fce3a80c565bf39ac65021b43a8b2990:
concrete SDK/HTTP/SQL construction снаружи existing core, без новой schema/алгоритма.

Independent review: initial REWORK0Critical/1Major/0Minor — raw build/catalog позволяли обход entry. Исправление facade и две регрессии RED→GREEN; обязательное повторное code review PASS0Critical/0Major/0Minor, independently44safe tests PASS. Reviewer не проверял private/source/Docker/DB/SDK. Один цикл исправления. Финальная сверка report/plan/context/journal и ссылок reviewer: PASS0Critical/0Major/0Minor.

Обновление2026-10-11: input choice и frozen674prepared закрыты в [input report](oversize-input-report.md). Следующий шаг —
actual native worker/command/bill на новом input profile и review до model execution; затем actual build и
coverage T052. Прежние20897/6h/32GiB остаются DRAFT_PROPOSAL, не выполненный/допущенный
run. Query session и test READY/pointer decision для изолированной БД согласуются
после coverage; final production activation сохраняет отдельную границу T055.
