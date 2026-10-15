# B1 — дополнение по зависимости миграций

2026-10-13 / APPROVED_BY_OWNER — владелец выбрал установку через pip сообщением
«Давай установим с ноля, как ты предлагал изначально». Первоначальная оценка
«пакеты не нужны» была неполной: migration0005_gate3_search.py импортирует
pgvector.sqlalchemy.Vector. Полный baseline0001–0009 не применился без этого пакета.

## Рассмотренный вариант: локальная копия

По вопросу владельца проверены существующие окружения. В рабочей папке
candidate-i-http найден pgvector0.5.0:48файлов,80515байт,без.so/.dylib.
Хеши сверены с RECORD, содержимое package совпадает со второй копией изe727.
Read-only импорт pgvector.sqlalchemy.Vector текущим Python3.12/SQLAlchemy2.0.52
прошёл; Vector(512) даёт VECTOR(512). Использован Python-B, source не менялся.

Предлагается перенести только pgvector/ и pgvector-0.5.0.dist-info/
в текущую.venv по [локальному manifest](test-dependency-local-manifest.json).
Перед переносом сверить все hashes и отсутствие обоих target folders;
после — hashes, metadata и import, затем bounded B1 bootstrap.
Без сети, всего окружения, pycache, numpy/MLextra и изменения других packages.
Копирование пока не выполнялось; исходныйB1 не разрешал добавление dependencies.

## Предыдущий вариант: загрузка через pip

Владелец выбрал этот вариант2026-10-13: только pgvector==0.5.0 в project.venv,
без обновления остальных packages и MLextra. Локальная копия не переносится.
Фактический результат установки/проверки фиксируется ниже.

Установить только pgvector0.5.0 в текущую project.venv, без ML extra,
обновления существующих packages, изменения ML locks и установки numpy/torch.
Версия взята из pyproject исходного approved baseline.

```sh
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r specs/001-corpus-replenishment/requirements-test-db.txt
```

[Точный список](requirements-test-db.txt): одна строка pgvector==0.5.0.
Нужен сетевой доступ к PyPI для wheel. После установки проверить metadata версии
и импорт pgvector.sqlalchemy.Vector, затем повторить bounded B1 bootstrap
в новом synthetic контейнере. Existing containers/рабочая БД не затрагиваются.

[Официальный pyproject v0.5.0](https://raw.githubusercontent.com/pgvector/pgvector-python/v0.5.0/pyproject.toml)
не объявляет обязательных dependencies и требует Python>=3.10; .venv3.12 подходит.
[Официальный SQLAlchemy adapter](https://raw.githubusercontent.com/pgvector/pgvector-python/v0.5.0/pgvector/sqlalchemy/vector.py)
использует установленный SQLAlchemy; [Vector](https://raw.githubusercontent.com/pgvector/pgvector-python/v0.5.0/pgvector/vector.py)
поддерживает plain списки и импортирует numpy только для ndarray операций.
Наличие совместимых исходников не заменяет runtime import проверку.

## Статус и границы

Package не установлен. Три bootstrap попытки завершились одним setup failure
TEST_COMMAND_FAILED; две последующие добавляли диагностический лог,
не являлись автоматическим retry. Причина — ModuleNotFoundError:pgvector
в migration0005; не TDD RED и не успешное применение миграций.
Созданные контейнеры удалены helper, остатки проверяются отдельно поB1 labels.

Первоначальное B1 сохраняет действующие process/files/testDB допуски.
Установка packages требует данного дополнения: approvedB1 говорит
«Пакеты не устанавливаются» и «Если реализация потребует нового Python dependency,
сначала подготовить отдельный diff/обоснование».

## Выполнение2026-10-13

Установлен только pgvector0.5.0 командой выше (--no-deps,--only-binary).
Pip использовал cached metadata/wheel; других packages не устанавливал.
Metadata/import pgvector.sqlalchemy.Vector и Vector(512):PASS.
B1 bootstrap:1passed; baseline0001–0009 применены только к новому
ownedsynthetic PostgreSQL. Test assertions:version_num0009,
product_records/search_representations пусты. Контейнер удалён helper,
read-only B1label listing пуст. Рабочая БД/ML не запускались.
Локальное copy proposal не выполнялось и не выбрано владельцем.
