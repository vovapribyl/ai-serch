# G4 runtime report — Candidate I HTTP

Дата: 2026-10-08. Статус серии: **REWORK**.

Обновление2026-10-09: отдельный [полный synthetic scenario](scenario-runtime-report.md)
получил TECHNICAL PASS по новой owner-approved resource policy. Ниже сохраняются
исторические результаты прежней серии; они не пересмотрены задним числом. Принятие
actual runtime profile/T049 принято owner «Принимаю»2026-10-09:
[runtime reference](runtime-profile-reference.md). G5/data/build/activation закрыты.

Отчёт относится только к разрешённым T044–T048 на generated/synthetic inputs.
Corpus, рабочая БД, Candidate J code/runners/data, build/activation и Git publication
не использовались.
Сырые изображения, masks, vectors и private runtime paths не сохраняются.

## Идентичность серии

| Поле | Фактическое значение |
|---|---|
| Код | detached HEAD `ba495046c80d25190a1745cb9f63384d00a42dd4` + сохранённые uncommitted T001–T047 changes |
| I lock | `ff813642a4150a635f8af7339585a742646126df70074029232eea451e858f46` |
| I runtime | Python 3.12.14; 89 distributions; exact `lang-sam`/`sam-2` commits из [G4 bill](runtime-bill.md) |
| Technical config | производный от последнего Candidate I config: текущий lock, `mps`, `float32`, operator fallback `false`; fingerprint `a0275494ec08accbfa03004d6006f244a3d8f2cfef57be2a4c97084ca769b277` |
| Code identity фактического model probe | `3c331844a0f1dc39040e6c9f5064d1778d788642bba47cdee62e67966ce72890` |
| Current code identity после review fix | `24ef8bd60f125898cb969e15240d2f7316d5ef94a4cfda2e340b62d8b24b2222`; model smoke для этой identity `NOT_RUN` |
| Approved profile hash | `2dd6ae778fbe084f616ba6b8ccfd6e05cc8fbcbde6dc81c2b351b675ec77605b` |
| Probe extractor fingerprint | `e4cd6aeb3fde91b1d2b22ef6cfd916ec3e726c0b9bbcff890da7e653442d6550` |

Probe fingerprint не становится final runtime reference: T046 получил `REWORK`, T048
не выполнен, а review fix изменил code identity. Current extractor fingerprint —
`UNKNOWN`. Technical config фиксирует проверенный runtime input, но не новое
утверждение качества или production-порогов.

## T044–T045 — environment и binding

- Runtime HTTPX зафиксирован как `httpx==0.28.1`; I lock хранится отдельно от backend.
- Strict offline sync остановилась до установки: две exact VCS-записи не имеют wheel
  hashes для глобального `--require-hashes`; затем выявлен отсутствующий в разрешённом
  cache artifact `protobuf==5.28.3`. Сеть/download не использовались.
- После stop был создан private copy-on-write clone сверенного control env. Проверены
  отдельный `sys.prefix`, mode `0700`, 89 distributions, versions и два VCS commit.
  Независимый review установил, что такой fallback не входит в утверждённый bill:
  T044 остаётся `PARTIAL/STOP`, clone не считается принятым I-service runtime.
- Lazy binding: 5 semantic RED→GREEN cases; общий scoped прогон binding/adapter/
  service/loopback — 46 PASS; Ruff PASS. Profile mismatch останавливается до ML;
  config/model paths/allowlist внешние; CPU и MPS fallback запрещены. Binding не
  выдаёт readiness: authoritative inventory/hash/fingerprint predicate остаётся
  внешней обязательной частью будущего bootstrap.

## T046 — Candidate I

| Проверка | Наблюдение | Итог |
|---|---|---|
| Preflight | Torch 2.4.1; MPS built/available; `PYTORCH_ENABLE_MPS_FALLBACK` отсутствует | PASS |
| Fingerprint mismatch | вызов остановлен до import/load модели | PASS |
| Generated detector path | локальные Grounding DINO и SAM2.1 загрузились; detector передал один region в SAM | PARTIAL |
| SAM через binding | exception санитизирован в `MODEL_ERROR` | REWORK |
| Отдельный synthetic SAM box | та же ошибка до получения mask | REWORK |
| Source-frame mask | mask не получена | NOT_VERIFIED |

Root cause воспроизведён в batch и single-image SAM: Torch 2.4.1 не реализует на MPS
операцию `aten::upsample_bicubic2d.out`. Upstream предлагает CPU fallback, но он
запрещён утверждённым профилем. Автоматический или скрытый fallback не включался.

Первый bounded call: 19,11 с wall; max RSS 994639872 bytes; peak memory footprint
4119627816 bytes; swaps 0. Диагностический повтор: 8,17 с; max RSS 753401856 bytes;
peak footprint 4081387608 bytes; swaps 0. Процессные ceilings соблюдены, но системные
memory-pressure colour и swapouts delta не снимались и остаются `UNKNOWN`.

## T047 — backend providers

| model_key | Revision | Manifest | MPS synthetic encode |
|---|---|---|---|
| `openclip_b32` | `1a25a446712ba5ee05982a381eed697ef9b435cf` | `7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d` | PASS, finite L2, dim 512 |
| `dinov2_b14` | `f9e44c814b77203eaa57a6bdbbd535f21ede1415` | `ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783` | PASS, finite L2, dim 768 |
| `siglip2_b16_224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | `45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9` | PASS, finite L2, dim 768 |

Manifests повторно прочитаны и полностью сверены до model load. Providers выполнялись
последовательно, offline, без operator fallback. Три теста PASS за 9,62 с; max RSS
1096105984 bytes; peak footprint 2449180856 bytes; swaps 0. Transformers выдал два
предупреждения о legacy BOS/EOS значениях SigLIP config; vector contract выполнен.

## T048 и решение

T048 **NOT_RUN**: actual HTTP I→crop→providers lifecycle требует успешный Candidate I,
а no-fallback SAM завершает запрос `MODEL_ERROR`. Fake HTTP regressions не заменяют
actual lifecycle evidence. Общая bounded серия осталась ниже 8 model-backed операций
и 20 минут.

Boundary note: один широкий read-only поиск по ранее сохранённым outputs вывел строку
worker metadata Candidate J. Файл не изменялся, J code/runner/model не запускались и
его evidence не использовалось для quality claims; последующие проверки выполнялись
только по backend model directory. Это отклонение от запрошенной границы зафиксировано.

Решение G4 series: **REWORK**. До нового owner decision допустимы только анализ и
новый exact bill. Возможные изменения — совместимый Torch/SAM runtime либо явное
изменение device/fallback profile — не утверждены и автоматически не выполняются.
