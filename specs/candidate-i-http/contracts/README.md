# Канонические контракты функции

- [HTTP v0.1](../../../docs/architecture/candidate-i-http-contract.md), APPROVED_BY_OWNER 2026-10-07.
- [OpenAPI 3.1](../../../docs/architecture/candidate-i-http.openapi.json): POST /v1/localizations и GET /health/ready.

Файлы не копируются: один источник fields/codes/formats и approval. Executor фиксирует actual version/SHA перед работой, а не создаёт независимую версию wire schema.

[LLD §4](../../../docs/architecture/nail-search-lld.md#4-внутренние-контракты) — proposed internal DTO/ports. Minimal mapping нужен первой части; остальные детали не становятся approved от ссылки. [Data model](../data-model.md) маршрутизирует данные.

Новых контрактов Sheets/VM/users/categories/J нет. Existing Web routes сохраняются и подключаются в позднем этапе после своих gates.
