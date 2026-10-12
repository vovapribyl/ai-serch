# T051 — actual native command package

2026-10-11. FULL: продолжение разрешённой подготовки команды, без model execution.
Вход: [approved674prepared](oversize-input-report.md), [native bindings](native-bindings-report.md),
[generic supervisor](build-composition-report.md). Исполнение inline, существующий
worktree/dirty state сохранить; один independent read-only review в конце.

- [x] TDD для pinned job/expiry/oneshot admission и model-free I firewall.
- [x] Реальный worker: отдельные accepted I/backend interpreters, owned loopback
  socket/process group, metadata-ready, actual input/runtime/target checks, lazy
  factories/budget/observer/device/coordinator, no publish/retry/resume.
- [x] CLI --check проходит actual model-free путь; --execute требует отдельно
  pinned approved permit на jobSHA/expiry и одноразовый claim. Подготовка не создаёт
  approved permit и не допускает ML автоматически.
- [x] Frozen job/code/input/runtime/bounds/command и safe check report; actual DB
  identity/counts/hostVMstorage, metadata HTTP и owned teardown без SDK.
- [x] Safe suites/fake failure boundaries, review/fixes, exact bill и journal.

Ruling: generic fake runner не менять, native command сделать отдельным; сохранить
existing admitted native ports/core/HTTP limits. Existing watchdog/supervisor reused,
никаких новых моделей/SDK/download/install. Предлагаемые20897/21600s/32GiB/16GiB и
G4RSS6/5/10GiB/freshness5s фиксируются в job как PROPOSED_FOR_OWNER_EXECUTION, не как
выданное runtime permission. Проверка тоже supervised: model-free60s ceiling, same
resource ceilings; копии/DB не записывать. Смена ephemeral loopback port не model
identity; новая assembly invocation задаёт новый private runtime_root, old roots
и accepted assembly bytes сохраняются. Query/Web/READY/pointer вне этого пакета.
