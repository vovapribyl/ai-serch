# Candidate I — exact bill исправления runtime

2026-10-08. **APPROVED_BY_OWNER**. После предъявления exact bill владелец ответил
«Разрешаю»: утверждены четыре pinned downloads, новый env из lock и bounded synthetic
серия. Подготовка/model-free code ранее разрешены «Хорошо, разрешаю, стартуй».
Comments PENDING в immutable proposed locks отражают момент подготовки; их bytes/SHA
сохраняются, актуальный owner status задаёт этот bill.

## План-контракт и проверенные основания

Маршрут подготовки STANDARD: продолжение анализа конкретного G4 REWORK. Исправление
readiness исполняется inline с Ponytail/Superpowers/TDD по [плану](runtime-rework-plan.md).
Новый owner gate не закрывается фактом подготовки или code PASS.

Предлагается сохранить MPS/float32/no-fallback и все параметры [G4](runtime-bill.md),
заменив в I environment только `torch 2.4.1 → 2.13.0` и `torchvision 0.19.1 → 0.28.0`.
LangSAM `918043ed4666eea04da88aa179eb8d27ef4b1a1d`, SAM2
`c2ec8e14a185632b0a5d8b161928ceb50197eddc`, Transformers4.44.2 и оба веса сохраняются.

Основания:

- В [точном PyTorch v2.13.0 native registry](https://github.com/pytorch/pytorch/blob/v2.13.0/aten/src/ATen/native/native_functions.yaml)
  `upsample_bicubic2d.out` имеет `MPS: upsample_bicubic2d_out_mps`. Это source evidence;
  actual operation и весь SAM2 ещё `NOT_VERIFIED` в proposed I runtime.
- Installed metadata отдельного backend control подтверждает пару 2.13.0/0.28.0 и
  CPython3.12 compatibility. Проверка всех активных Requires-Dist для proposed 89
  distributions дала 0 metadata conflicts. Это не model smoke.
- I package cache содержит expanded artifacts старого набора, кроме protobuf5.28.3
  и sentencepiece0.2.0. Torch2.14.0 присутствует отдельно, но без matching torchvision;
  его не выбираем. Backend env не переносится и его lock не объединяется с I.

## Точный состав

[Полный proposed lock](requirements-rework.lock): 87 registry entries + два exact VCS
commits; SHA-256 `f72724b2d9403f636675574be7437776de0aff39f2de24911bf86ccad2ac4af9`.
Сравнение с текущим service lock подтверждает ровно две version changes и неизменные
остальные entries/VCS. Ожидаемый inventory: 89 distributions; SHA по уточнённому
алгоритму G4 `42db16a29cc52385b230f5252b2adb3ce67ca64bcd1d9648f1a4cca9510d2a42`.

Разрешение на сеть предлагается ограничить четырьмя exact wheels из
[download lock](runtime-rework-downloads.lock); transitive download и source builds запрещены.
Имена, размеры и SHA получены read-only из PyPI JSON metadata 2026-10-08.

| Wheel | Bytes | SHA-256 |
|---|---:|---|
| `torch-2.13.0-cp312-cp312-macosx_14_0_arm64.whl` | 111213045 | `2fe228aba290d14b9f31b049be550dbd469c3fd3013d7a19705b30454da97027` |
| `torchvision-0.28.0-cp312-cp312-macosx_14_0_arm64.whl` | 1856020 | `e9f54c30cd52e3ef7fd034cc69b7bb7e0964e1c8f8743e018ab92e95b40f9eee` |
| `protobuf-5.28.3-cp38-abi3-macosx_10_9_universal2.whl` | 414743 | `a3f6857551e53ce35e60b403b8a27b0295f7d6eb63d10484f12bc6879c715687` |
| `sentencepiece-0.2.0-cp312-cp312-macosx_11_0_arm64.whl` | 1181597 | `3212121805afc58d8b00ab4e7dd1f8f76c203ddb9dc94aa4079618a31cf5da0f` |

Всего 114665405 bytes. Источники: [Torch metadata](https://pypi.org/pypi/torch/2.13.0/json),
[torchvision metadata](https://pypi.org/pypi/torchvision/0.28.0/json),
[protobuf metadata](https://pypi.org/pypi/protobuf/5.28.3/json),
[sentencepiece metadata](https://pypi.org/pypi/sentencepiece/0.2.0/json).

Cached VCS wheels дополнительно сверены: lang-sam 13969 bytes,
SHA `f14b615656bc3dbd2fbe5992ae1918cb18424a3519685598f88d8df2a23f5263`;
sam-2 167288 bytes, SHA `ec3485cefb12386c617d9f055fd7511064006e967576477201f0b371e32ceb1b`.
Их exact source revisions закреплены в lock; actual direct_url commits проверяются после sync.

## Операции после утверждения

1. Новый private runtime root mode0700; точный путь — в private ledger. Existing control
   и unratified clone сохраняются. Создать новый empty venv Python3.12.14 без download Python.
2. Скачать только четыре wheels через download lock, `--no-deps --require-hashes`;
   проверить SHA и bytes. Веса не скачивать.
3. Offline sync полного proposed lock через existing I package cache + local wheelhouse,
   `--offline --no-build --no-python-downloads`. Registry hashes проверяются из lock;
   глобальный `--require-hashes` не применяется из-за exact VCS syntax, это явный метод
   этого bill. При отсутствующем artifact/необходимом build STOP, нового fallback нет.
4. Проверить exact 89-package inventory, Python, VCS direct_url, lock и model hashes.
   Только после этого заменить service lock на proposed lock и сформировать новый
   frozen config/runtime identity. Clone не ратифицируется этим способом.
5. Actual readiness assembly связывает весь relevant code/contract/lock/model/config/
   runtime-profile manifest с metadata observers; `extractor_fingerprint` вычисляется,
   а не принимается отдельной строкой. Hashing duration проверяется до HTTP bootstrap.
6. Новая bounded серия: MPS bicubic preflight; отдельный synthetic SAM; generated
   detector path; cold + два warm I HTTP calls; один I→crop→providers lifecycle.
   Максимум 8 model-backed операций и 20 минут; параметры memory/deadlines G4 сохраняются.
   Снять system memory pressure и swapouts delta. Первая ошибка → STOP/REWORK.

## Проверки, UNKNOWN и решение

Metadata/source compatibility — VERIFIED/PARTIAL в описанных пределах. Actual native
operation, SAM2/Transformers compatibility при новом Torch, full-frame masks, HTTP
lifecycle, combined RSS/system memory pressure и final fingerprint — UNKNOWN до серии.
Старые failure-characterization tests сохраняют диагностическое значение; acceptance
нового runtime требует successful SAM masks и корректный HTTP result.

Readiness implementation проверяется на synthetic manifests до install. Эти tests не
аттестуют actual env или модель. T044/T048 остаются открытыми до operational verification.

Code verification: 10 readiness/facade cases RED→GREEN; final scoped regression
256 PASS/44 SKIP, Ruff/diff PASS. Independent review PASS 0/0/0; отдельно 42 scoped
tests PASS. Actual observers/factory, operational manifest completeness, cache sync,
ML compatibility, hashing duration и lifecycle/resources reviewer не проверял.

Owner decision получен: exact bill, download четырёх wheels, создание нового env из
lock и описанная bounded synthetic серия разрешены. Corpus/working DB/J,
build/activation, commit/merge/push/publication остаются вне разрешения.
