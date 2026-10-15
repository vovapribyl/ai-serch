# Приватная диагностика ошибки команды

2026-10-14. Реализована и проверена немодельно. Первопричина отказа79f709ee
остаётся UNKNOWN: прошлый traceback восстановить невозможно. Исправление этой
первопричины не заявляется; нового настоящего запуска не было.

## Что записывается

Native host передаёт callback в OwnerDispatcher и PrivateCommandServer.
Исключение в обработчике либо проверке протокола/ответа создаёт command-failure.json
в private root: тип ошибки, basename файла кода, имя функции, строка и цепочка
cause/context. До4исключений, последние32frames каждого, обход не более1024frames;
обрезка обозначается. Размер не больше owner IPC max_bytes —65536байт в предложении.
Root0700, file0600, O_EXCL/O_NOFOLLOW, fsync файла и каталога. Прежний файл и symlink
не перезаписываются. Сохраняется первая ошибка этого private запуска.

Message, исходный код, locals, значения аргументов, SQL, credentials, полные paths
и raw input не сериализуются. Запись не передаётся CLI/Web. Error mapping сохранён.
Если sink недоступен, публичный ответ сохраняет исходную ошибку; отсутствие файла
означает отсутствие подтверждённого diagnostic evidence, а не успешную запись.
Это диагностика owner command, не обещание traceback каждого SDK-процесса.

## TDD и проверка

[Test module](../../tests/test_replenishment_failure_diagnostics.py).
Два поведенческих RED: exception не передавался в sink в dispatcher и на socket
boundary. Callback wiring дал GREEN. Проверены permissions, отсутствие секретов,
cause chain, deep-stack/chain caps, overwrite/symlink refusal, недоступный sink,
сохранение публичного error и finite host wiring.

Финал: **127passed**,2DBcases исключены,0,94с, одно прежнее Starlette/httpx warning.
CLI/host/resources/workers/controller/waiting/lifecycle включены. Ruff/diff PASS.
Это выбранная регрессия, не полный suite. БД и ML не запускались; независимое review
не проводилось. Требования и зависимости не менялись.

## Следующая подготовленная проба

SHA: **7d89d5dae0c2793f65129df99e5c0db10b5431c8c6ff5c21112c7069ad240c78**.
Один прежний товар/фото, I→три encoders→checkpoints→READY→publication только новая
owned temporary DB; цель — проверить полный путь и при ошибке получить locations.
[Прежние пределы](post-review-runtime-proposal.md#прежние-пределы) сохранены:
1200с/330с operation/5сDB/30сcleanup, TERM/KILL5с/5с, RSS/MPS6GiB,
I6GiB/encoder5GiB, freshness5с/poll0,5с, heavy worker1, warning300с/stability30с.
DB512MiB/1CPU/128PID/tmpfs256MiB/loopback/pinned image/schema0010/seed1/1.
Working DSN не используется, NO_NAILS не разрешает заменять фото.

Новый root/nonce/target;77code hashes, input/permissions/DTO PASS. I metadata
manifest/inventory/VCS/runtime/assembly и3actualenv entrypoint refusals PASS безSDK.
Encoder87file byte checks сохранены с предыдущей подготовки; полного rehash сейчас
не было, native stage проверяет свой snapshot до загрузки.

**PREPARED / PENDING_OWNER_APPROVAL**. Grant/DB не созданы, inference не выполнялся.
Перед исполнением повторно проверяются live processes/pressure/owned target.
Прежние consumed grants не действуют на новый код. Новая партия, working Web/catalog,
качество, cutover/merge/push и owner acceptance этим предложением не разрешаются.

## Исход разрешённой пробы — 2026-10-14

Владелец разрешил7d89d5da; пакет использован на один START. [Результат](post-review-runtime-report.md):
**OK за82,661с**,4реальных стадии/4checkpoints/10regions/30vectors/1publication
в новую temporary DB; cleanup подтверждён.6WARNING/197OK,0STOP. Ошибка не повторилась,
failure record не создан; причина прежнего79f709ee остаётсяUNKNOWN.
Статус этого пакета теперь EXECUTED/CONSUMED, не PENDING_OWNER_APPROVAL.
Большая партия и working activation не выполнялись.
