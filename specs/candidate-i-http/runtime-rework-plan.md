# Candidate I runtime rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans inline. Existing Tnnn and ledger are retained; no new worktree or task-ID namespace.

**Goal:** устранить no-fallback MPS failure и подготовить verified readiness для T048.

**Architecture:** сохранить HTTP/core/binding и exact LangSAM/SAM2 revisions. Изменить только Torch/torchvision в отдельном I env; actual identity проверяет внешний model-free predicate. Control env сохраняется.

**Tech Stack:** Python 3.12.14, stdlib metadata/hashlib, existing FastAPI/HTTPX/Pillow.

**Spec:** [HTTP contract §6](../../docs/architecture/candidate-i-http-contract.md#6-readiness-и-fingerprint), [G4 bill](runtime-bill.md), [runtime report](runtime-report.md).

## Global Constraints

- MPS / float32; operator fallback false. Finite limits и lifecycle — без изменений G4.
- Новый exact bill утверждается до download/install/load. Corpus/working DB/J/build/activation/Git publication не разрешены.
- Existing managed code checkout и ledger сохраняются; canonical docs — primary checkout.
- Проверяемые code changes — RED→GREEN. Commit/merge/push/workspace cleanup не выполнять.

## Review Focus

- Подмена model/code/config/lock → ready false до binding.
- Missing/extra packages и VCS commit mismatch → ready false без ML import.
- Изменение expected manifest снаружи не меняет закреплённую identity.
- Изменение проверенного файла после bootstrap → ready false; fingerprint не берётся из request.
- Model smoke должен проверять успешные masks, а прежние failure probes не считаются acceptance.

## Task: новый exact bill, продолжение T044

**Files:** create `runtime-rework-bill.md`, proposed `requirements-rework.lock`; original service lock не менять до approval.

- [x] Сверить full metadata candidate: Torch 2.13.0 / torchvision 0.28.0, остальные 87 distributions сохраняются.
- [x] Подготовить полный proposed lock: base exact lock, только две замены; отдельно hashes четырёх отсутствующих wheels.
- [x] Предъявить download четырёх pinned wheels и install-from-lock в новый private env. Owner approved; четыре downloads SHA/bytes PASS, empty env создан. При additional missing artifact STOP соблюдён.
- [x] После approval: offline sync, actual inventory/VCS/lock verification, без clone env и без source builds/network resolution. Actual89 PASS, approved lock013ba67f... закреплён.

Первоначальный sync STOP сохранён как история: antlr4/iopath built wheel SHA
отсутствовали в первом lock. [Дополнение](runtime-rework-cached-wheels-bill.md)
утверждено, actual install89 завершён; следующие model checks остановлены уже по RAM.

## Task: verified readiness, продолжение T045/T048

**Files:** create code `services/candidate_i/readiness.py`; test `tests/test_candidate_i_readiness.py`.

**Interfaces:** `VerifiedReadiness(manifest, files, observe_inventory, observe_vcs, observe_runtime)`; callable returns bool; `extractor_fingerprint` derived from canonical manifest. File entries bind logical role, exact size and SHA; paths excluded. Runtime manifest binds Python/platform/device/dtype/fallback and finite profile via hashed file.

- [x] RED: valid synthetic inventory/files returns true and calculated identity; changed/missing/extra package, VCS, file, runtime returns false; facade returns MODEL_NOT_READY without binding.
- [x] GREEN: stdlib identity verifier и actual metadata-only observers/production bootstrap связаны; actual model-free26-file check0,478с PASS.
- [x] Run scoped readiness/binding/facade tests and Ruff: final 256 PASS/44 SKIP, Ruff PASS; independent review 0/0/0. Model-file hash cost измерить в operational bootstrap; не выдавать fake performance за actual.

## Task: bounded acceptance, продолжение T046/T048

- [x] После нового bill approval: MPS bicubic tensor preflight, без fallback — PASS.
- [x] Отдельный synthetic SAM box → finite, nonempty full-frame mask; затем generated detector call (NO_NAILS допустим). SAM PASS; cold HTTP validated result, exact cold status/count summary UNKNOWN после harness failure.
- [ ] Один cold и два warm I HTTP calls; reuse T047 results только при неизменном backend inventory/manifests, иначе отдельно разрешённые проверки.
- [ ] HTTP→crop→providers; device/coordinator lease ownership, timeout/cleanup; system memory pressure, swapouts delta и combined RSS двух процессов.
- [x] При первом resource failure STOP/REWORK:3 model calls, дальнейшие не запускались. Exact final wall acceptance NOT_VERIFIED из-за потерянного failed summary.
- [x] Сохранить report и probe fingerprint; independent review PASS0/0/0. Accepted runtime reference/owner acceptance остаётся незавершённым перед T049/G5.

Final safe regression270 PASS/46 SKIP, Ruff/diff PASS. Next:
[один cold resource profiling](resource-profiling-plan.md), требует нового разрешения.

Native execution уже выбран владельцем; отдельные planning/author agents не создаются.
