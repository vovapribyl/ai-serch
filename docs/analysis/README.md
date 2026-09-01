# Навигация по аналитическим артефактам

> [Текущий контекст](current-context.md) · [Governance](governance.md) · [Статус проекта](../project-status.md)

## Выборочное чтение

| Задача | Читать |
|---|---|
| Продолжить аналитический пакет | [`current-context.md`](current-context.md) |
| Проверить режим работы или модель | [`governance.md`](governance.md) |
| Проверить состав конкретного `ART-*` или перенести чужое содержание | [`artifact-contracts.md`](artifact-contracts.md) |
| Найти источник `SRC-*` или ограничение данных | [`registers/sources.md`](registers/sources.md) |
| Найти решение `DEC-*` или legacy `FACT-*` | [`registers/decisions.md`](registers/decisions.md) |
| Найти `GAP-*` или статус пакета | [`registers/gaps-and-package.md`](registers/gaps-and-package.md) |
| Проверить историю `ART-00` | [`registers/history.md`](registers/history.md) |
| Найти план-контракт или review | [`reviews/README.md`](reviews/README.md) |

Корневой [`ART-00`](00-source-and-decision-register.md) — короткий индекс пакета. Полное чтение всех компонентов не требуется.

## Реестр артефактов

| ID | Артефакт | Статус |
|---|---|---|
| `ART-00` | [Источники и решения](00-source-and-decision-register.md) | v2.4 `APPROVED_BY_OWNER` (`SRC-051`) |
| `ART-01` | [Vision & Scope](01-vision-and-scope.md) | v1.1 `APPROVED_BY_OWNER`; `SRC-043`; review `PASS`, 0/0/0 |
| `ART-02` | [Стейкхолдеры и глоссарий](02-stakeholders-and-glossary.md) | v0.7 `APPROVED_BY_OWNER`; `SRC-043`; review `PASS`, 0/0/0 |
| `ART-03` | [AS-IS](03-as-is.md) | v0.3 `APPROVED_BY_OWNER` |
| `ART-04` | [TO-BE](04-to-be.md) | v0.7 `APPROVED_BY_OWNER`; `SRC-043`; review `PASS`, 0/0/0 |
| `ART-05` | [Бизнес-правила](05-business-rules.md) | v0.4 `APPROVED_BY_OWNER`; `SRC-043`; review `PASS`, 0/0/0 |
| `ART-06` | [Пользовательские сценарии и функциональные требования](06-user-scenarios-and-functional-requirements.md) | v0.7 `APPROVED_BY_OWNER` (`SRC-051`) |
| `ART-07` | [Требования к данным](07-data-requirements.md) | v0.5 `APPROVED_BY_OWNER` (`SRC-051`) |
| `ART-08` | [Нефункциональные требования MVP](08-non-functional-requirements.md) | v0.4 `APPROVED_BY_OWNER` (`SRC-051`) |
| `ART-09` | [Критерии приёмки и компактная трассировка](09-acceptance-criteria-and-traceability.md) | v0.4 `APPROVED_BY_OWNER` (`SRC-051`) |
| `ART-10` | [Активные риски, допущения и открытые вопросы](10-risks-assumptions-and-open-questions.md) | v0.4 `APPROVED_BY_OWNER` (`SRC-051`) |

## Исторические документы

`docs/discovery/*`, `docs/project-plan.md`, `docs/architecture.md` и корневой `README.md` созданы до утверждённого аналитического пакета. Они не являются нормативными и открываются только для конкретной исторической или технической гипотезы.

Ограниченный CSV не является стартовым контекстом. Его статус и правила использования находятся в [реестре источников](registers/sources.md).
