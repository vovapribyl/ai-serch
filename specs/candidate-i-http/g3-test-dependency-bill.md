# G3 — один недостающий пакет для migration tests

Дата подготовки: 2026-10-07. Статус: **INSTALLED_TEST_ONLY**. После предъявления этого bill владелец ответил «Разрешаю»; установлен только SHA-pinned pgvector 0.5.0 в указанном target. G3 schema и отдельная synthetic БД также утверждены.

## Конкретное препятствие

Существующая migration `0005_gate3_search.py` импортирует `pgvector.sqlalchemy.Vector`. Test interpreter Python 3.12.14 уже содержит SQLAlchemy 2.0.52, psycopg 3.3.4, Alembic 1.19.1 и pytest 8.4.2, но не Python pgvector. Цепочку migrations до принятого head нельзя проверить без этого импорта. Старую migration не переписываем и пакет не имитируем через sys.modules.

`pgvector==0.5.0` уже закреплён в extra gate3-ml проекта. Установлен только этот пакет для отдельного test overlay, без установки всего ML extra; Vector import PASS. NumPy не понадобился, bundled environment не добавлялась в путь.

## Bill и команда

| Позиция | Значение |
|---|---|
| Пакет | `pgvector==0.5.0` |
| Артефакт | `pgvector-0.5.0-py3-none-any.whl`, 30 958 bytes |
| Wheel SHA-256 | `fedc9800894e6da2be51358d7b7c574bf34f247ca741a5a09513622135f5964f` |
| Источник | [PyPI metadata 0.5.0](https://pypi.org/pypi/pgvector/0.5.0/json), requires_python >=3.10, requires_dist отсутствует |
| Requirements | [Точный test-only файл](g3-test-requirements.txt) |
| Куда | `.superpowers/sdd/plan/g3-test-deps` в managed code worktree; отдельный target, не существующая .venv |
| Что сохраняется | Текущие .venv backend/I, dependencies/locks и model packages не изменяются |

Предлагаемая операция из code worktree, только после разрешения:

```bash
/Users/v.pribylovskiy/Documents/ChatGPT/Ai/.venv/bin/python -B -m pip install \
  --isolated --disable-pip-version-check --no-cache-dir --no-deps \
  --only-binary=:all: --require-hashes --index-url https://pypi.org/simple \
  --target .superpowers/sdd/plan/g3-test-deps \
  -r /Users/v.pribylovskiy/Documents/ChatGPT/Ai/specs/candidate-i-http/g3-test-requirements.txt
```

После установки проверить version/location и import migration Vector; добавить только этот target в test PYTHONPATH. Bundled Python той же версии уже имеет NumPy 2.3.5; при необходимости разрешено переиспользовать только этот installed package через test-only overlay, без скачивания/замены NumPy и без добавления всей bundled environment в путь. Runtime compatibility устанавливается actual import/test, не этой таблицей.

## Что уже проверено с БД

Docker CLI сначала не имел running server. Запущен существующий stopped Colima default с `--activate=false`; global Docker context остаётся default. Использован явный `--context colima`. Старт существующей VM выполнил штатный runtime provisioning; новых Python dependencies или container image downloads не было.

Cached image ID/digest: `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b`. Disposable container запущен по этому ID с `--pull=never`, restart=no, loopback ephemeral port и tmpfs вместо persistent volume. Проверены unique ownership label/image/mount/endpoint и current database/role, public schema изначально пустая. Созданы только synthetic ownership marker и vector extension; никаких рабочих credentials/данных не читали.

Фактически: **PostgreSQL 16.15, vector extension 0.8.6**, SQL vector dimension probe PASS. Тестовый контейнер удалён после проверки, tmpfs утрачен, секретный env удалён. Colima оставлен запущенным для продолжения; другие контейнеры/volumes не удалялись. Безопасный report сохранён в private scratch code worktree. Это server/identity/SQL preflight, не GREEN новой migration/repository, не T032–T042 completion.

## Разрешение

Указанная операция отдельно разрешена владельцем и выполнена; existing .venv не изменялись. Разрешение G3 на synthetic migrations/tests также получено; перед каждым новым DB запуском identity проверяется заново. Real ML/corpus/working DB/Git publication не входят в операцию.
