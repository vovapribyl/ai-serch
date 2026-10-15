# Перенос baseline и первая единица TDD

2026-10-13. Работа в codex/upload-optimiz, исходный checkout сохранён.

## Baseline

Владелец утвердил manifest SHA256
`5a89cf8b542fd4f186fbe84ebd2922341f5332ba03251bd2958d086bbe5c7c3e`.
Перед записью сверены все source/target hashes. Добавлены 72 выбранных файла;
четыре совпадающих файла, два reference и два merge-review файла не изменены.
После переноса повторно проверены все 80 целевых исходов. Manifest неизменен.

Первая попытка pytest без PYTHONPATH: четыре collection errors
`ModuleNotFoundError: product_search`; это setup failure, не TDD RED.
С `PYTHONPATH=src:.` выбранная немодельная регрессия: 93 + 136 = 229 passed.
Выборка: nail_contracts, nail_matching, nail_image_processor, candidate_i_binding,
langsam_adapter_contract, nail_dependency_boundaries, nail_service, nail_catalog_build,
nail_input_preparation, nail_embedding_adapter, candidate_i_http_adapter,
candidate_i_http_service, candidate_i_readiness. HTTP тестируется MockTransport/ASGI,
без отдельного сервера; localization/encoder используют test doubles.

## TDD: ExecutionPackage

Созданы tests/test_replenishment_contracts.py и
src/product_search/search/replenishment_contracts.py. До проверки поведения — только
immutable DTO/enum/error scaffold по согласованному плану.

RED: 129 failed / 3 passed; отказ — DID NOT RAISE для некорректных пакетов,
а не import failure. GREEN: 132 passed. Дополнительный случай malformed scope:
RED 2 failed / 133 passed (uncontrolled TypeError); GREEN после type guard.
После форматирования/refactor: объединённая выборка 364 passed,
ruff check новых двух файлов прошёл.

Проверяются обязательные positive finite сроки, positive integer caps, SHA identities,
schema/scope, достаточный cleanup reserve и adapter deadlines в доступном окне.
Числа fixture синтетические; production limits/default package не назначались.
Состояния фото и стадий заданы по data-model. Полнота runtime/package identities
проверяется последующими adapters; синтаксический SHA guard не подтверждает identity.

## Границы evidence

Это не полный suite и не готовность пополнения. Процессные/БД проверки не запускались:
для них сохраняются отдельные допуски задачи004. pgvector отсутствует, не устанавливался.
Есть одно предупреждение Starlette о deprecated httpx TestClient; зависимости не менялись.
ML/корпус/рабочая БД/миграции/публикация/commit/push не выполнялись.

Пункты001–003 и005–007 выполнены;004 и008–051 остаются открытыми.
