# T049 — принятый runtime Candidate I HTTP

2026-10-09. **APPROVED_BY_OWNER**: «Принимаю» на [actual report](scenario-runtime-report.md)
и закрепление проверенного runtime. G4 feature Candidate I HTTP принят в пределах
технического synthetic-сценария; G5/data/build/activation не разрешены этим решением.

## План-контракт и основание

FULL: зафиксировать owner acceptance без новых параметров → сверить actual hashes →
приватно сохранить принятые source/config/profile artifacts → canonical reference/
handoff/status → один independent read-only review. Native models и code не менять.
Источники: [resource policy](scenario-suitability-profile.md),
[approved execution bill](scenario-probe-plan.md), [reviewed report](scenario-runtime-report.md).
Результат:2genuine full rounds/36vectors/41operations/29.879с, no hardSTOP.
Этот документ фиксирует принятое состояние, не расширяет область измеренной пригодности.

## Exact identity

| Компонент | Принятое значение |
|---|---|
| Extractor/runtime fingerprint |`6cccc4730294099738dcd440a22fe84d8db8082641e15cb57730088bb439234d` |
| Private assembly bytes SHA-256 |`70e0b2adba4800b58293dbe5ca276fe78ed7b713c88f7d99164d99d96b4c8fb8` |
| Full runtime profile bytes SHA-256 |`21930c217ac72038792e8fbd688703e2b58a115f5acefb03d1ee38d47d7b4a03` |
| I frozen localization config fingerprint |`dae475fa384688e813fa0abd782df5b893968a6b6276f95e3177bbf083e5e61e` |
| I config file bytes SHA-256 |`b86c7705e712d6889920cba5ebb4205a1694fda6cb07692cde3cce6345fad120` |
| I lock SHA-256 |`013ba67fcd8688b2b4ec4ecd86bb802e8a3ac3b8b2d9bc016af984c178f5e93b` |
| I packages / files |89distributions,36manifestfiles; exact entries private |
| Backend inventory canonical JSON SHA-256 |`d2b79438b84b4d86df2053385774704a3cf9f7d5afb46982d6c356bb226f147e`,71packages |
| Runtime platforms |Python3.12.14/arm64, MPS/float32/no operator fallback |
| I Torch / vision / Transformers / NumPy |2.13.0 /0.28.0 /4.44.2 /2.2.5 |
| Backend Torch / vision / Transformers / NumPy |2.13.0 /0.28.0 /5.16.1 /2.5.3 |
| LangSAM / SAM2 commits |`918043ed4666eea04da88aa179eb8d27ef4b1a1d` /`c2ec8e14a185632b0a5d8b161928ceb50197eddc` |
| Code checkout |detached HEAD`ba495046c80d25190a1745cb9f63384d00a42dd4`,dirty; HEAD не полная code identity |
| Accepted source archive SHA-256 |`f7068fbcbc208cb2bcb12df8efcb91cb5745053a09c2895e88f65205f148265d`,24source files/34888bytes |

Все36 actual file hashes/sizes повторно совпали при фиксации. Приватный snapshot
`accepted-runtime-20261009` содержит source archive и5byte-identical metadata files:
assembly/profile/config/lock/contract. Exact paths — в private ledger; не публиковать
full private descriptor, environment paths, images/masks/vectors. Веса не дублировались,
остаются в existing read-only verified caches по model identities из G4/report.
Archive contents сверены с24code entries manifest; лишние macOS AppleDouble metadata
не включены в accepted code.tar.gz. Первый metadata-rich archive сохранён отдельно,
не удалялся и не считается reference. Snapshot фиксация не import/load/inference.

## Принятые правила и пределы

`scenario_suitability_v1`: warning/swap сохранять как whole-host diagnostics;
critical/неизвестный pressure/failed mandatory observation/RSS limit/error/timeout STOP.
RSS ceilings I6/backend5/combined10GiB; connect1/write30/read300/overall330seconds.
Source20MiB/decoded2359296pixels/regions10/response40MiB/solver16384/manifest8MiB
из frozen profile не увеличиваются. One in-flight I,loopback,no retries; provider calls
последовательны, существующий cache сохраняется. Guardian завершает только owned group.

65operations/1200seconds/2rounds/5second freshness — bounds принятого validation
window, не perpetual model permission или гарантированная production capacity.
Изменения code/SDK/config/models/semantically relevant profile требуют новой identity
и отдельного acceptance; молча переиспользовать этот fingerprint после изменений нельзя.
Для будущего G5 data execution нужны отдельные inputs/операционные bounds/permissions.

## Что не принято как доказанное

Не подтверждены realphoto/top-10 качество, полный диапазон1536×1536/10regions,
обычный workload со всеми приложениями, endurance/no-leak или latency SLA.
Historical strict REWORK остаются прежними. Native fault-injection не повторялась;
negative guards имеют отдельное controlledfake evidence. Full suite не подтверждён.
Window permission исчерпано, новые ML/corpus/working DB/J/commit/merge/push не выполнять
по одному этому acceptance. Следующий этап T050 — только после отдельного разрешения
read-only corpus inventory; это принятие не разрешает читать restricted corpus.

Фиксация hashes/source/metadata PASS; independent reference review PASS0Critical/
0Major/1Minor. Minor: dated reference pointer в нижней acceptance section actual
report добавлен; повторное review после Minor не требовалось. Hash/links/status/diff
проверки PASS. Reviewer не повторял private archive/hash/native/tests/install checks.
