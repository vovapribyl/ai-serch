# B0 — baseline переноса

2026-10-13 / APPROVED_BY_OWNER — сообщение «Утверждаю бэйслайн».
Пункты001–003 выполнены; результаты в [отчёте переноса](baseline-transfer-report.md).
Ниже сохранён состав исходного предложения; manifest не изменён.

## Предложение

Исходный checkout corpus-optimization: HEADba49504 с dirty/untracked исходниками.
Целевой checkout: codex/upload-optimiz, HEADb38f07e, с сохранёнными изменениями
документации. По ранее выбранному владельцем маршруту работа остаётся в текущем
checkout; новые worktree/ветка не создавались.

[Manifest](baseline-manifest.json) фиксирует 80 отдельных файлов, source/target SHA,
Git-состояние source и основание включения. Его SHA256:
`5a89cf8b542fd4f186fbe84ebd2922341f5332ba03251bd2958d086bbe5c7c3e`.

| Действие | Число | Что означает |
|---|---|---|
| PROPOSE_ADD | 72 | Кандидаты на добавление исходников/тестов/DDL после утверждения |
| KEEP_IDENTICAL | 4 | Совпадают по SHA, перезапись не нужна |
| REFERENCE_ONLY | 2 | pyproject.toml и I requirements.lock; не копировать, не устанавливать ML extra |
| MERGE_REVIEW_REQUIRED | 2 | main.py и web/app.py; только интеграционные ссылки, не разрешение целой перезаписи |

Внутри PROPOSE_ADD — ядро/адаптеры поиска по ногтям, HTTP I, минимальное замыкание
статических импортов, выбранные тесты и migration chain0005–0009. В текущей ветке
есть chain0001–0004; только0009 переносить нельзя — down_revision требует0008.
DDL — код миграции, не разрешение применить её даже к test DB.

Не выбран целый checkout, raw данные, runtime snapshots, модели или env.
Исключены manual20/UI/web/evaluation тесты, real-provider/real-smoke и старые
scenario probes, не необходимые данному baseline. main/web не обходились рекурсивно:
их unrelated изменения остаются за интеграционной границей. Последующая минимальная
интеграция main/web потребует конкретного diff и проверки сохранения текущих функций.

## Проверка и ограничения

AST-проверка не исполняла source: статические и literal dynamic локальные импорты
выбранного baseline разрешены. Это не runtime import/collection успех; произвольные
dynamic imports и ссылки на fixtures проверяются отдельным test preflight.

[Зависимости](baseline-dependencies.json) получены из установленной metadata,
без импорта third-party библиотек. Python3.12.14, pytest/ruff/httpx и основной Web/DB
стек присутствуют. pgvector не установлен; source pyproject задаёт pgvector0.5.0
в ML extra. Подготовка немодельного DB-binding обсуждается отдельно, без установки
всего extra. Torch/open_clip/transformers отсутствуют; модельные тесты не запускаются.
Фактическая немодельная выборка тестов определяется после согласованного переноса,
без model/corpus/working-DB операций и без выдачи import failure за TDD RED.

Read-only повторная проверка:

```sh
.venv/bin/python specs/001-corpus-replenishment/verify_baseline.py
```

Проверка повторяет SHA всех source и исходного target. Изменение исходника или
target до переноса требует нового manifest/согласования, а не обхода ошибки.
После переноса проверка исходного target ожидаемо не подходит: нужен отдельный
post-transfer diff/hash и немодельный regression report.

## Следующая контрольная точка

Владелец утверждает этот manifest как исходный baseline. Это разрешает перейти
к пункт003 в рамках запроса реализации; merge-review entries не перезаписываются
целиком. Зависимости, test DB/native fake и ML scopes сохраняют отдельные допуски.
Модельные вызовы, корпуса, БД, установка пакетов, commit/merge/push здесь не выполнялись.
