# Ядро: порты, правила партии и controller

2026-10-13. STANDARD, реализация принятого плана в codex/upload-optimiz.

## Результат

Пункты008–016: pure Clock/Progress/Artifacts/StageWorkers ports и plain DTO;
fake-clock окно с cleanup reserve; выбор только первой партии до5pending фото,
без automatic retry ошибок; готовность по всем выбранным фото + минимум одному OK.
Controller последовательно обрабатывает localization,openclip_b32,dinov2_b14,
siglip2_b16_224. После file verification получает checkpoint receipt и только
затем меняет исход фото. NO_NAILS не вызывает encoders; photo ERROR не блокирует
остальные фото, global store error завершает работу.

Семь фото: первые пять обработаны, оставшиеся два PENDING, редакция не READY.
После одной партии controller не выбирает следующую. Возвращается список готовых
редакций; фактическая публикация и supervisor wiring ещё не реализованы.

## TDD evidence

- Boundaries: scaffoldRED5failed/1passed; расширенныйRED5failed/12passed; GREEN17passed.
- Rules: RED16failed; GREEN16passed.
- Controller: RED5failed; GREEN5passed. Scope/ownership guards RED5failed/9passed.
- Late result: RED1failed/14passed; GREEN. Поправлен ранний test fixture: результат,
  пришедший после deadline, не должен commit-иться. Ожидание изменено с1на0checkpoint
  по уже утверждённому deadline-контракту, а не ради ослабления проверки.
- Attempt mismatch: RED1failed/15passed; GREEN.
- Финальная объединённая немодельная выборка:413passed, одно прежнее
  Starlette/httpx deprecation warning. New unit cases184 + baseline229.
- Ruff новых/изменённых replenishment core/test файлов:PASS; diff check:PASS.

Успех fake ports не доказывает SQL durability, ML качество, режимы реальных
процессов или возможность пополнять корпус. Полный suite не запускался:
process/DB scopes сохраняют отдельный допуск. Snapshot publication, recovery,
retry, resource observations/warning и CLI ещё впереди.

Подготовлен [B1](test-execution-package.md), не исполнен. Read-only Docker
image inspect подтвердил существующий образ. Pythonpgvector/numpy отсутствуют,
но текущий SQL-адаптер их не импортирует; установки не требуется.
