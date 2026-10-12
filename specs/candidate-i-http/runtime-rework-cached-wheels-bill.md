# Дополнение G4 — два существующих cached wheels

2026-10-08. **APPROVED_BY_OWNER**: ответ «Lf» (русская раскладка «Да») на точный
вопрос об утверждении двух local wheel hashes. Это дополнение к
[утверждённому rework bill](runtime-rework-bill.md), без новых package versions,
downloads, source builds или смены device/profile.

## Фактический stop и причина

Четыре разрешённых wheels скачаны; exact bytes/SHA совпали. Новый empty Python3.12.14
env создан из выбранного interpreter. Offline/no-build sync остановилась на
`antlr4-python3-runtime==4.9.3` до установки; actual installed distributions = 0.

Source lock содержит для antlr4 и iopath SHA исходных архивов. Уже существующие в
I package cache wheels собраны ранее и имеют иные bytes/SHA; `--no-build` не может
использовать их как wheel artifacts по sdist hashes. Первоначальный read-only cache
inventory проверил наличие built wheels, но не их пригодность по approved hashes —
это упущение подготовки bill, а не новый model failure.

## Точное дополнение

Разрешить использовать два конкретных локальных wheels из прежнего I package cache.
Exact private paths сохранены в ledger. Ни cache files, ни control env не изменяются.

| Wheel | Bytes | SHA-256 |
|---|---:|---|
| `antlr4_python3_runtime-4.9.3-py3-none-any.whl` | 144590 | `33ffca1b9ecfcad073911dd82a814e26e9eddb4ea5de565222848454db113c31` |
| `iopath-0.1.10-py3-none-any.whl` | 31598 | `bd245e6ba11296e8e3751b83f2f9d8f8e65346c6af2cd892076c2f7c6c0b99e2` |

[Updated proposed lock](requirements-rework-cached-wheels.lock), SHA
`013ba67fcd8688b2b4ec4ecd86bb802e8a3ac3b8b2d9bc016af984c178f5e93b`:
добавлены только эти два wheel hashes к соответствующим exact version entries;
все 89 versions/VCS commits и expected inventory SHA исходного bill сохранены.
Старый approved lock не перезаписан, service lock не изменён.

## Проверка до решения владельца

Diagnostic `uv pip sync --dry-run --offline --no-build --no-python-downloads` с новым
proposed lock и двумя дополнительными local find-links разрешил 89 packages за61ms.
Это resolver PASS; installation, direct_url/actual inventory и model compatibility
ещё NOT_VERIFIED. Формулировка uv `Would download 6 packages` относится к materialization
четырёх local downloaded wheels и двух local cached wheels; команда offline,
dry-run не выполнил installation/download/build.

Read-only сравнение wheel payload с сохранённым control env: antlr4 59 обычных files
совпали byte/hash и одно script body совпало после исключения installer-relocated
shebang; iopath 14 files совпали. RECORD исключён как installer-owned. Это проверяет
согласованность с control, но не является воспроизводимой сборкой wheel из sdist.

Независимое review дополнения: PASS0 Critical/0 Major/0 Minor; reviewer проверил
ровно два hash additions, неизменные versions/VCS, STOP/NOT_RUN и document diff.
Private wheel bytes/provenance, actual resolver logs и operational install/ML
самостоятельно reviewer не проверял.

## Следующее действие

После явного утверждения: повторить real offline/no-build sync с тем же lock и local
find-links; затем actual89 inventory/VCS/lock/model checks и разрешённая bounded
synthetic серия исходного bill. Любой additional missing artifact/build requirement
снова STOP. Ни новый env clone, ни build без утверждения не предлагаются.

Два local wheel hashes и updated exact lock разрешены владельцем. Прежнее
разрешение четырёх downloads и bounded series сохраняется и повторно не запрашивается.
