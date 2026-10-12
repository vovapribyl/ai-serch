# T048 — один instrumented cold request

2026-10-08. **APPROVED_BY_OWNER**: «Разрешаю» на один новый cold profiling request
после resource STOP.

Цель: сохранить peak samples и swap/pressure timeline одного cold I request, чтобы
выбрать исправление памяти по наблюдению. Package/model/code I identity, MPS/float32/
no-fallback и ceilings исходного G4 сохраняются. Новая установка не нужна.

## Проверенное исходное состояние

- Fresh I env89, exact lock013ba67f..., current I probe fingerprint21696870...;
  [полный результат](runtime-rework-report.md).
- Native bicubic и отдельный SAM PASS. Cold HTTP series остановлена resource guard;
  whole-host Swapouts delta15632pages нарушает0. Historical sampled peaks UNKNOWN.
- Read-only Mac snapshot после teardown:16GiB RAM, pressure raw1, free11962,
  inactive272933, speculative1775, wired162462, compressor291566 pages; page size16KiB.
  Эти категории не объявляются гарантированным доступным headroom для I. Snapshot
  не доказывает причину prior swapouts исключительно в I.

## Точная предлагаемая операция

1. Новое отдельное окно максимум20минут, максимум1 admitted model-backed HTTP call.
   Не продлевать остановленную series. `--initial-model-calls 0`, свежие `--started-at`
   и `--swapouts-baseline` снимаются непосредственно перед launch.
2. Read-only baseline: normal pressure, swapouts, available system counters, leases,
   current manifest/inventory. При уже нарушенном состоянии не начинать model call.
3. [Existing probe](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/support/candidate_i_runtime_probe.py)
   с `--cold-only`: один generated256×256 RGB, busy/device probes без дополнительной ML;
   warm/providers не запускаются. Parent — model-free controller, отдельный I process.
4. Снимать RSS каждого процесса/combined, pressure и swapouts delta с периодом≈0,5с.
   Эти sampled peaks не выдаются за гарантированное continuous maximum. `finally`
   сохраняет aggregate outcome даже при failure: status/count/cold duration/counter/
   violations/process-exit. Изображения/masks/embeddings не сохранять в отчёт.
5. Первая resource/functional error → STOP; завершить только owned I child, проверить
   внешнее reacquire device/coordinator и final system counters. Scope не даёт права
   остановить Colima/чужие процессы или менять approved ceilings/dtype/fallback.
6. Сохранить результат и предложить конкретное минимальное memory исправление.
   Отдельный cold probe не закрывает warm/provider lifecycle или T049/G5.

## Команда после разрешения

Из code worktree, exact private paths — в ledger:

```bash
env -u PYTORCH_ENABLE_MPS_FALLBACK HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src "$CONTROLLER_PYTHON" -B \
  tests/support/candidate_i_runtime_probe.py \
  --assembly "$PRIVATE_ASSEMBLY" --i-python "$I_PYTHON" --models "$EXISTING_MODELS" \
  --started-at "$FRESH_START_EPOCH" --initial-model-calls 0 \
  --swapouts-baseline "$FRESH_SWAPOUTS" --cold-only
```

До исполнения CLI/help/lint проверены без ML. Owner разрешил только этот один новый
bounded cold request; прошлые installation approvals сохраняются. Результат — ниже.

Исполнение завершено: [report](resource-profiling-report.md). Один call14,52с total,
HTTP OK/6 regions12,032с; sampled I1,30GiB/combined1,33GiB, swap delta0, pressure2
нарушает strict policy. RESOURCE REWORK; cold-only actual branch выполнен, teardown PASS.
Следующий model run этим одноразовым разрешением не разрешён.
