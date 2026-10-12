# T048 — полный synthetic lifecycle: preparation и exact run bill

Подготовка 2026-10-08; **APPROVED_BY_OWNER 2026-10-09**: «Разрешаю» после exact bill
и объяснения двух полных циклов. Новая resource policy утверждена отдельно
[owner решением](scenario-suitability-profile.md). Подготовка и model-free проверки
разрешены продолжением реализации. Это одно новое окно≤65ops/1200с, не разрешение
повторять failed series. Перед запуском identity/baseline/leases повторно проверены.

## Цель и последовательность

Один ограниченный execution window, два полных цикла одного generated256×256 RGB:
`cold I HTTP → все crops → OpenCLIP/DINOv2/SigLIP2`, затем
`warm I HTTP → все crops → те же cached providers`. Один in-flight inference,
две existing среды Mac, общий device/coordinator lease root, no POST retries.
I принимает direct PNG; genuine masks/region frames проверяются wire/core mapper.
Все crops из NailImageProcessor передаются каждому provider, не только первый.
NO_NAILS допустим как API outcome, но не доказывает full lifecycle: остановиться как
NOT_EXERCISED, без independent synthetic crop подмены. Partial vectors не принимать.
Размерности512/768/768, finite/nonzero/unit L2, количество rows равно количеству crops.

## Proposed конечные границы нового window

| Параметр | Значение и смысл |
|---|---|
| Полных циклов |2: cold и warm; не долгосрочный endurance/leak benchmark |
| Регионов на фото |≤10; прежний cap, без truncation |
| Model-backed budget |≤65:2 admitted I POST +3 provider loads +≤60 encode_image (3×10×2) |
| Смысл I counter |один admitted HTTP request включает frozen LangSAM/ROI flow; не счётчик внутренних tensor operations |
| Wall window |1200с, independent external watchdog; после forced exit только cleanup/reacquire, не новые модели |
| Mandatory resource sample freshness |5с, после чего STOP; sampling host≈0.5с |
| I/MPS и backend/MPS counters |≈0.25с, асинхронные optional samples; partial APIs не теряют доступные counters |
| RSS ceilings / I deadlines |6/5/10GiB и300/330с из G4, без изменений |
| Trace namespace |`scenario-suitability-20261009`, fresh files с exclusive create, old artifacts сохранить |

65 вместо прежних8 требуется из-за всех найденных regions: каждый provider.encode_image
учитывается отдельно, не маскируется одним batch/port call. Это proposed новый бюджет,
не расширение исчерпанных прошлых разрешений. Нет standalone bicubic/SAM/provider smoke,
третьего round, auto rerun или restart20minwindow. Real concurrent BUSY POST не выполнять:
health.busy не резервирует состояние, второй POST мог запустить неучтённую inference.
Shared device BUSY check сохраняется (parent удерживает lease); concurrency contract
покрыт controlled fake tests, не объявляется новым native concurrency evidence.

## Identity и safety перед native запуском

- I: existing fresh env89, frozen localization config/lock/weights; no fallback.
- Backend: existing env71, Python3.12.14/arm64, Torch2.13.0/vision0.28.0,
  Transformers5.16.1/NumPy2.5.3; read-only inventory canonical JSON SHA
  `d2b79438b84b4d86df2053385774704a3cf9f7d5afb46982d6c356bb226f147e`.
  Hash/Python/machine/no-fallback проверяются в controller до I launch.
- Три existing provider manifests и revisions проверяются до load; G4 artifacts
  сохраняются. Exact interpreter paths/assembly/profile/private logs остаются private.
- Snapshot code/files/package/VCS/model/profile identity через actual model-free I
  bootstrap; новый fingerprint не имеет ML evidence до execution.
- Fresh pressure/swap/RSS baseline и external leases; warning записать, critical/
  invalid observation/lock conflict блокируют launch/admission. Mandatory RSS tool
  failure не трактуется как zero memory. Optional backend MPS observer отдельный,
  чтобы не блокировать host guard. Clock bound watchdog monotonic.
- Единственный outer runner использует `run_owned_probe` (new session/process group).
  Critical/RSS/deadline/mandatory telemetry failure → kill только owned group;
  finally/self PID exit/внешнее reacquire обоих locks проверять даже при error.
  Graceful SDK refs/del не объявляются гарантированным освобождением accelerator RAM.
- HF/Transformers offline, no bytecode write into control envs. Никаких installs,
  download weights, corpus, SQL, Candidate J, чужих process kills, commit/merge/push.

## Файлы и model-free verification

Test-only: `candidate_i_runtime_probe.py` (mode/budget/host monitoring),
`candidate_i_scenario_probe.py` (real crops/counting/vector checks),
`candidate_i_probe_watchdog.py` (owned group hard stop),
`candidate_i_resource_metrics.py` (capability-aware counters) в worktree tests/support.
Core NailEmbeddingAdapter/HTTP service/binding не меняются; provider cache retained.
TDD: resource policy/counter partial support/all crops/load+encode accounting,
NO_NAILS/invalid vectors/no further SDK after admission failure; watchdog wall/critical/
final trace/nonfinite deadline/stale telemetry; actual fake HTTP2-round wiring.
Fake wiring поймало health.busy TOCTOU; badRSS regression поймала silentzero observation.
Это preparation evidence, не утверждение ML/full suite/production quality.

## Completion и handoff

Actual report должен содержать per-round status/region count/provider dimensions,
counters/timing/RSS/MPS samples/pressure/swap/teardown; raw images/masks/vectors не
сохранять и не публиковать. Technical PASS требует обоих genuine full rounds и guard
checks без hard stop. Полное качество top-10, корпус и обычный Mac workload не проверены.
После series — owner report/T049, не автоматическое G4 закрытие, build или activation.
Preparation final review PASS0C/0Major/0Minor; actual native run NOT_RUN.

Preparation initial review REWORK0C/1Major/0Minor: transient mandatory observation
failure должна доходить до watchdog, а не только локального violations. Исправление:
terminal resource_observation_error trace event; последующий normal sample не отменяет
STOP. Fake regression воспроизводит transient RSS failure во время synthetic encode,
после normal sample forwarded trace завершает работающий owned dummy worker.
Admission events печатаются/flush до SDK, поэтому forced kill не теряет счётчик
reserved operations; completion текущей операции при kill может остаться UNKNOWN.

После исправления independent repeat review PASS0C/0Major/0Minor (reviewer24safe
tests/Ruff/diffPASS, native/ML/private actual manifests не повторял). Scoped299PASS/
46SKIP, RuffPASS, known Starlette warning. Full suite не подтверждён: прежние
model-dependent collection blockers primary test env не устранены установкой Torch.
Actual model-free I bootstrap36files/89packages PASS/noTorch, proposed scenario identity
`6cccc4730294099738dcd440a22fe84d8db8082641e15cb57730088bb439234d`.
Base strict assembly refreshed56d2f0cd... тоже model-freePASS/noTorch/modelNOT_RUN.
Новая private profile/assembly0600, existing earlier assembly backup сохранён;
weights/packages/old traces не менялись. Эти identities не имеют actual ML acceptance.

2026-10-09 execution завершено один раз: [actual report](scenario-runtime-report.md),
2genuine rounds/36vectors/41operations/29.879с, watchdog exit0/noSTOP.
Technical PASS по выбранной policy; owner runtime acceptance/T049 остаётся отдельным.
Более ранние NOT_RUN/identity-only строки выше описывают preparation stage.
