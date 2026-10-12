# T051 — model-free composition: план выполнения

2026-10-09. Owner «Хорошо, приступай» разрешил следующий независимый шаг из
[handoff](execution-context.md): wiring/observers/supervisor/exact command на fake
данных. Oversize-фото и manifest входов отложены в [бэклог](tasks.md#бэклог).
Новый native window, обработка корпуса, publish и activation не разрешены.

Исполнитель работает inline в существующем product worktree; один финальный
read-only reviewer. TDD/самопроверка до claims. Commit/push/merge не входят в scope.
Clean Architecture mini и Ponytail: concrete wiring/OS/SQL во внешнем composition
root, existing core/build/crop/schema не менять; без новых dependencies.

- [x] Добавить tests и RED для immutable runtime comparison, terminal resource/
  storage/freshness guard и composition существующего core с тремя fake providers.
- [x] Реализовать внешний `nail_build_composition.py`: runtime gate, observation
  gate, `compose_build`, owned supervisor. Подключить existing admission/source/
  target/lease/embedding adapters; no publish и no implicit native execution.
- [x] Добавить отдельный fake worker/CLI: synthetic namespace, реальные bounded
  image-store/crop/vector checks, I/load/encode admissions, atomic guardian sample,
  external owned-process teardown. Native mode в этом этапе не исполняется.
- [x] Проверить successful/critical/low-space/storage-limit/stale/error/wall/partial
  fake сценарии; actual OS+owned target storage observation без source rows/photos.
  Сохранить новый private snapshot/command/aggregate report; не переписывать старые
  bundle/input manifests. Relevant tests/Ruff/links/diff → один review → corrections.

Review focus: transient invalid sample не возобновляет admissions; зависший observer
не блокирует external wall/freshness STOP; cached immutable expected runtime не
меняется caller-ом; process group/lease teardown затрагивает только новый worker;
наблюдение VM free space не подменяется host free space. Fake verification не доказывает
native bootstrap, ресурсную пригодность674photos или качество поиска.

Итог: final324PASS/46SKIP/Ruff/diff/directchecksPASS; independent reviewPASS0/0/0,
46safe tests независимо. Native window и paused input issue не открывались.
