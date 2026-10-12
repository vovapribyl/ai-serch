# T048 — результат полного synthetic-сценария

Owner acceptance2026-10-09: «Принимаю». T049 completed —
[принятый runtime reference](runtime-profile-reference.md). Ограничения evidence ниже
сохраняются; это не разрешение новых моделей/data/build/activation.

2026-10-09, старт08:28:47 Europe/Moscow. **TECHNICAL PASS в проверенном сценарии**.
Основание: owner «Разрешаю» после [exact bill](scenario-probe-plan.md) и объяснения
двух полных циклов. [Resource policy](scenario-suitability-profile.md): warning/swap
diagnostics; critical/RSS/error/timeout STOP. G4/T049 acceptance остаётся у владельца.

## Фактическая цепочка

Один новый window, generated256×256 RGB, существующие I/backend среды. Каждый genuine
HTTP result → все mask crops через NailImageProcessor → каждый crop через три модели.
Без независимого crop substitute, truncation и retry.

| Проверка | Cold cycle | Warm cycle |
|---|---|---|
| I HTTP status / regions |OK /6 |OK /6 |
| I localization latency |11.825с |3.571с |
| OpenCLIP rows / dimension |6 /512 |6 /512 |
| DINOv2 rows / dimension |6 /768 |6 /768 |
| SigLIP2 rows / dimension |6 /768 |6 /768 |
| Cached providers |3 |3, повторное использование |

Все36 vectors прошли finite/nonzero/unit-L2 checks; row count равен crop count.
2localization calls +3provider loads +36encode_image =41 reserved operations из65;
admission log содержит1…41, оба rounds завершились. Это high-level budget, не число
внутренних tensor forwards LangSAM/ROI. Controller29.36с, watchdog29.879с (<1200),
exit0/stop_reason=null. Shared device BUSY PASS. Native concurrent POST NOT_RUN;
negative concurrency/timeout/observer cases — controlled model-free tests, не fault
injection на настоящих моделях этого window.

## Ресурсы

| Наблюдение | Результат |
|---|---|
| I sampled RSS peak |1427472384bytes≈1.329GiB, ниже6GiB |
| Backend sampled RSS peak |598949888bytes≈0.558GiB, ниже5GiB |
| Combined sampled RSS peak |1492058112bytes≈1.390GiB, ниже10GiB |
| Host pressure49 samples |normal1:44; warning2:5; critical4 не наблюдался |
| Whole-host swapouts |210039→252283, delta42244pages16KiB=692125696bytes≈660.063MiB |
| I MPS peak active / driver |1582686720 /2848374784bytes≈1.474 /2.653GiB |
| Backend MPS sampled peak active / driver |2465867520 /2521595904bytes≈2.297 /2.348GiB |
| Recommended working set |12713115648bytes≈11.840GiB, не свободная RAM |
| VMMap owned I при warning |exit0; footprint3.6G/peak-to-snapshot3.7G; graphics2.6G; не whole-window peak |

I trace105 samples:13not_imported,3partial-import unavailable,89ok. Backend counters
асинхронные; host≈0.5с, с нерегулярными intervals из-за system calls/одного VMMap.
Peaks не continuous maxima. Combined RSS не равен сумме разновременных отдельных peaks;
CPU RSS и Metal allocations нельзя складывать как независимые physical RAM объёмы.
Pressure/swap whole-host; sole-I/backend causality не доказана. First sampled warning
около20.952с отstart. Hard RSS/critical/error/stale/deadline violations отсутствуют
в сохранённых наблюдениях, watchdog не выполнял STOP.

## Identity и teardown

Code checkoutba495046... detached/dirty; canonical813dd11.../dirty сохранены.
Actual I manifest36files/89packages/bootstrap проверен доML; identity
`6cccc4730294099738dcd440a22fe84d8db8082641e15cb57730088bb439234d`.
Backend71 canonical JSON inventory SHA
`d2b79438b84b4d86df2053385774704a3cf9f7d5afb46982d6c356bb226f147e`, Python3.12.14/
arm64 и3modelmanifestsPASS. MPS/float32/no-fallback профиль сохранялся.
Freshstart1791523727.496634/pressure1/swap210039. Source/config/weights/env versions
не менялись. Владелец ранее сообщил о закрытии приложений; конкретный набор во время
window не инвентаризирован. Это не обычный workload benchmark или гарантированный headroom.

Owned I завершён, backend controller exited0; внешнее reacquire обоих locks PASS.
Read-only process inventory послеwindow не нашёл I/control/controller processes;
finalpressure1/swap252283. Exit/del не объявляем мгновенным освобождением всей Metal RAM.
Raw logs/traces/VMMap private0600; старые artifacts не перезаписаны. Real images/masks/
vectors не сохранялись/публиковались; только synthetic processing и технические traces.

## Acceptance и границы

I→all genuine crops→three models работоспособны в обоих rounds и уложились в новую
suitability policy. Warning/swap не скрыты и не трактуются как OOM. Подтверждён T048
technical scenario, не качество top-10, corpus readiness, worst-case1536×1536/10regions,
endurance или отсутствие memory leak. User photos/обычные приложения/latency SLA UNKNOWN.
После предъявления отчёта owner2026-10-09 ответил «Принимаю»: T049 и technical G4
runtime закреплены в [reference](runtime-profile-reference.md). G5/data/build/activation
и новые model calls этим не разрешены. Window permission исчерпано; оставшиеся24
операции — не новое разрешение.
No installs/downloads/corpus/working DB/J/commit/merge/push. Saved2rounds/36vectors/
41admissions/teardown/nohardSTOP assertions PASS. Initial independent report review
REWORK0C/1Major/0Minor: current headers противоречили actual PASS. Исправлено только
status routing, historical strict REWORK сохранён. Repeat review PASS0C/0Major/0Minor;
header/status/links/markers/diff checks PASS. Code не менялся, suite/model smoke и
private telemetry reviewer не повторял. Full suite не подтверждён предыдущим fake PASS.
