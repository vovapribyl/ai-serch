# T051 — model-free composition и supervised fake command

2026-10-09. Owner «Хорошо, приступай» на независимое wiring/observers/teardown на
fake данных. **Model-free composition проверена; native execution CLOSED.**
T051 `[ ]`: corpus build не выполнен. Oversize-фото и manifest входов остаются
в [бэклоге](tasks.md#бэклог), без изменений.

## Scope и concrete wiring

[План](build-composition-plan.md) выполнен inline, без commit/push/merge.
Новый [composition root](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_build_composition.py)
связывает existing `NailCatalogBuildService`/`NailImageProcessor`, image/localization/
embedding ports, `GuardedLocalization`/`GuardedEmbedding`/`admitted_provider`,
coordinator/device leases и target/input/runtime predicates. Existing core, crop
policy, schema и G4 source/config/packages/weights не менялись.

`RuntimeVerifier` сравнивает полный независимо полученный metadata snapshot с
immutable expected copy; wrong revisions/observations не допускают build. В actual
fake run проверены fake metadata и actual Python/package inventory выбранного
интерпретатора. Это не current verification реальных I/backend G4 environments.
`OwnedTarget` сохраняет independent Docker/SQL gate; новые actual вызовы — только
SELECT metadata, без source rows, migration или real representation writes.

## Guard и supervisor

| Изменение → код | Проверка / фактическая граница |
|---|---|
| ObservationGate → pressure/RSS/storage/freshness | Critical/unknown/invalid/stale/missing mandatory sample terminal; warning допустим; caller не меняет cloned limits |
| HostStorageObserver → ps/sysctl/vm_stat/owned SQL/VM df | RSS только нового process group: leader как backend, другие owned members как descendant aggregate; это не измеренные native I6/backend5 процессы |
| Host/VM free и payload | Host disk free и `df -Pk` внутри verified target измеряются отдельно; DB logical size + owned artifact bytes, no VM→host fallback |
| supervisor + existing `run_owned_probe` | External guardian не ждёт зависший observer; wall/freshness STOP завершает только созданную owned group |
| Atomic observation channel | Private600 control files и trace; transient failed observation передаётся guardian до worker notification; normal sample не отменяет STOP |
| RecordingBudget → before-operation record | Reserved ordinal сохраняется до I/load/encode; record failure запрещает операцию; forced exit не маскируется счётчиком0 |
| Finish state | Late/unfinished mandatory sample не превращается в PASS из-за exit0; leases проверяются после owned group teardown |

Actual CLI наблюдает whole-host pressure/swap diagnostics. В injected unit observer
fixtures отсутствующий swap counter — явно помеченный synthetic compatibility value,
не actual zero-swap evidence. Storage — observed logical threshold, не filesystem
quota; overshoot между samples возможен. Нет claims endurance/no-leak/native capacity.

## Проверочный CLI и actual series

[run_nail_build.py](../../../../../.codex/worktrees/candidate-i-http/Ai/scripts/run_nail_build.py)
имеет explicit `--mode fake`; `--mode native` возвращает exit4 /
NATIVE_EXECUTION_NOT_AUTHORIZED до чтения job и SDK construction.
[Test-only worker](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/support/nail_build_fake_worker.py)
использует только два newly generated2×2 PNG в fresh namespace: fake I через реальный
HTTP adapter/ASGI wire, genuine crop/image-store code, три fake providers512/768/768.
Реального I process/SDK/MPS/inference в этой series нет; socket сеть не проверялась.

Fake catalog — private JSON checkpoints, не PostgreSQL `search_representations`.
Target DB используется только для independent identity/storage observations. Native
bindings/bootstrap/weighted SDK factories/реальная DB write composition ещё требуют
отдельного model-free рассмотрения и проверок перед native run; fake wiring их не
подменяет. Generic composition принимает эти ports явно, не импортирует модели.

| Scenario | Actual outcome |
|---|---|
| Final success | exit0;1OK/1NO_NAILS/0PENDING,8reserved admissions (2I+3loads+3encodes), no publish; worker SDK import probe false; elapsed0.382s |
| Provider error | controlled STOP/exit3;2PENDING,3reserved; exception translation не продолжила серию |
| Critical pressure | injected critical; owned exit-9, RESOURCE_CEILING recorded; coarse guardian reason RESOURCE_OBSERVATION_ERROR |
| Storage threshold | injected overflow; owned exit-9, STORAGE_CEILING recorded |
| Stuck observer | owned exit-9/freshness STOP≈1.05s; observer не удержал main teardown |
| Final wall | fake provider sleeps; owned exit-9 at1.023s,2PENDING, durable3reserved; worker final SDK probe UNKNOWN из-за kill |

Везде coordinator/device leases reacquired. При отсутствии reservation/result file
значение NOT_OBSERVED/UNKNOWN, не0/успех. Negative scenarios — controlled fake faults,
не native fault injection. Их private artifacts сохранены, не auto retry native run.
Initial/final fake verification повторялась только после code/guard changes;
сравнительных прогонов «с правилами/без правил» не было.

Exact fake argv/cwd и job SHA сохранены приватно. Командная форма без private locators:

```text
python -B scripts/run_nail_build.py --mode fake --target <owned descriptor> --target-sha256 <pinned SHA> --private-parent <private parent> --locator <fresh private locator>
```

Final success job SHA:
`0326b3a94d1b08ac6981e2b49b43220f098b6f2ae8aa646a64b38dd7eead7193`.
Final wall job SHA:
`8ef5548c03f1ed9f11a03b2aeaab6571f92ce316951026efcdcd8c8b8796eb87`.
Job/control/log/checkpoint files600, namespace/inputs/artifacts/runtime dirs700.
Новый16file source archive SHA:
`b14b0f5dedc6cfedb53b462781e5e77689d7239d93012e11d3148cbf4fb1ad06`;
payload hashes, archive contents и permissions проверены. Новые source snapshots
сохраняются отдельно; старые T050/preparation bundles не
переписываются. Source photos и input manifest не читались/не изменялись этим запуском.

## Tests и review

[test_nail_build_composition.py](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_build_composition.py)
проверяет resource/runtime/composition/supervisor/native-entry/before-SDK recording.
TDD серии:16core-gate tests +6supervisor +2direct OS boundary +1native entry +1recording;
дополнительно combined/sample-schema characterization и deterministic late-finish
RED→GREEN. OS sampler первоначально реализован до direct seam tests: тело удалено,
после2semanticRED реализовано заново, без выдачи первого green за TDD evidence.
Finish race сначала не воспроизводилась timing-only fixture; тест синхронизирован
реальным guardian return/event, observed RED затем исправлен.

Relevant subset до finish-race fix:323PASS/46SKIP/1existingStarlettewarning,31files.
После fix targeted53PASS, final broader **324PASS/46SKIP/1existingStarlettewarning**,
31testfiles. Ruff четырёх новых файлов PASS; оба tracked diff и direct new-file
whitespace/link/status checks PASS. Existing tracked dirty entries сохранены.
Full project/native/working DB suite
не запускался; safety opt-ins выключены. Применены Ponytail/TDD/verification и Clean
Architecture mini, commit893a88a6fce3a80c565bf39ac65021b43a8b2990: concrete wiring наружу,
existing core не меняется. Новых dependencies и установок нет.

Independent read-only review **PASS0Critical/0Major/0Minor**:46safe tests и оба
tracked diff/link checks выполнены независимо. Reviewer не читал private snapshots/
source data и не повторял actual Docker/DB/native series. Findings/fix cycles review0;
предшествующие internal RED→GREEN corrections не считаются review findings.

## Native boundary

Model-free command и generic wiring готовы в указанном fake scope. Это не разрешение
или доказательство готовности real native assembly. Corpus674, отдельное source input
решение, actual G4/current runner binding и exact native window остаются gated.
20897ops/6h/32GiB — прежнее DRAFT_PROPOSAL; Fake thresholds64MiB payload/16MiB free,
5s window (1s wall fault),1s freshness,8fake admissions — только пределы synthetic test.
Сборка673вместо674, resize/exclude/cap change, model calls, публикация и activation
не выполнялись и не разрешены. Фото в бэклоге не возобновляется по этому PASS.
