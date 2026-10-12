# T051 — подготовка без ML и выявленная граница входов

2026-10-09. Подготовительные операции отдельно разрешены owner «Разрешаю» на
runner, новую БД, выбранные parent rows и hash/decode проверки. **Native readiness:
BLOCKED_INPUT_POLICY**. T051 `[ ]`: нативная сборка не выполнена и не разрешена.

## План-контракт и результат

FULL: зафиксировать конкретный model-free permission → подготовить внешние runner/
source/target/admission boundaries через TDD → создать отдельный persistent target →
source READ ONLY copy и hash/decode preflight → fake/SQL/owned-worker проверки →
safe report, один independent read-only review → предъявить blocker владельцу.
Основание: [bill](build-execution-bill.md), [T050](build-readiness.md),
[G3 storage](g3-storage-decisions.md), [G4 reference](runtime-profile-reference.md).

| Проверка | Наблюдение |
|---|---|
| Target ownership | Новый container/volume, cached image совпал с G3; unique ownership label и volume mount проверены; loopback ephemeral endpoint |
| Persistence / ресурсы | Persistent volume, restart=no, container memory1GiB/CPUs2; existing Colima VM limits не менялись |
| Target SQL identity / schema | Current database/user совпали с приватным descriptor; empty target до migration; head `0009_nail_search_v1` |
| Source copy | Только выбранная Gate 2 версия и 674 records с исходными numeric IDs/обязательными полями; source snapshot в REPEATABLE READ READ ONLY, совпал с T050 |
| Target после проверок | 674 source records; real BUILDING representations0, active pointers0; Web/search не подключены |
| Повторный hash / bounded decode | 673 OK; одно SOURCE_PIXEL_LIMIT. ML не запускался |
| Единственное oversize фото | Header1802×1802 =3247204pixels; accepted cap2359296pixels. Header-only уточнение, oversize pixels не декодировались |
| Максимум успешно декодированных | 2250000pixels |
| Принудительный owned exit | Новый fake worker завершён external guardian по wall limit; synthetic BUILDING/PENDING сохранились, pointer отсутствовал, coordinator lease reacquire PASS |
| Очистка fake проверки | Удалены только созданные synthetic rows после проверки сохранности; source rows и persistent volume сохранены |

Hash сравнивался до проверки dimensions для всех 674 фото. Превышение cap не
трактуется как NO_NAILS, не скрывается пропуском товара и не меняет T050 inventory.
Оригиналы, их права, данные Gate 2 и accepted G4 source/config/weights не изменялись.
Точный Gate 2 DB ранее запущен по разрешению; новый target оставлен работающим.

## Изменение → код → проверка

| Изменение | Код | Проверка |
|---|---|---|
| Чтение Gate 2 по frozen basenames без изменения source permissions | [ManifestImageStore](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_build_runner.py) | White alpha, checksum/pixel limit/symlink/path escape, исходные bytes/права; actual674 hash/decode |
| Target допускается по pinned private descriptor и внешним Docker/SQL observations | `OwnedTarget` в том же модуле | Wrong marker/mutated descriptor отказ; actual container/image/volume/endpoint/database/role/schema verifier PASS |
| STOP terminal и не переводится обратно в photo ERROR | `AdmissionBudget`, `GuardedEmbedding`, `GuardedLocalization`, `admitted_provider` | Sticky resource/budget/deadline/I error; SDK translation не допускает следующих calls; отдельный admission на load/encode/I |
| Build без publish/resume и с освобождением coordinator | `run_admitted_build` вокруг existing `NailCatalogBuildService.execute` | Failed target/input/runtime → до BUILDING; finally после SystemExit; actual fake SQL NO_NAILS/FK rejection/rollback |
| Проверочный CLI без режима ML | [check_nail_build_preparation.py](../../../../../.codex/worktrees/candidate-i-http/Ai/scripts/check_nail_build_preparation.py) / `verify_preparation` | Frozen bundle/code/descriptor/source/inventory/decode/target bindings; actual exit3/BLOCKED_INPUT_POLICY |

Тесты: [test_nail_build_preparation.py](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_build_preparation.py).
Подготовлены внешние runner components и model-free проверочная команда, а не
готовый native launcher. Прямой `build_nail_representation.py` сохраняет отказ.
На момент этой initial preparation native composition/supervisor/resource/storage
wiring ещё не были завершены. Последующий [report](build-composition-report.md)
фиксирует проверенную generic composition/observers/fake command; actual native
bootstrap/SDK/DB-write binding и native command не допущены. Metadata
и typed DTO не заменяют actual readiness. Generic injected runner не утверждает
runtime по одному callback из теста.

## Freeze и фактическая проверочная команда

Новый private root700: target descriptor/env/source-parent snapshot/prepared inventory/
bundle/command/logs600; artifact root700. Точные IDs/paths/credentials остаются приватно.
Opaque source references связаны с source numeric IDs и T050 hashes; копии исходных
фото не создавались. Canonical BuildPhoto inventory hash отдельно от T050 manifest.

- Preparation bundle SHA: `229839da4cacd81abee69ea2b47602c5c075d4cd860e4de8d00368b889f2470f`.
- Canonical BuildPhoto inventory SHA: `c399077c766669de3c8f0ee5869b98d3454385853286f023dc177d609f07158f`.
- Exact argv/cwd/PYTHONPATH сохранены в private `preparation-command.json`.

Без публикации private locator командная форма:

```text
python -B scripts/check_nail_build_preparation.py --bundle <private bundle> --expected-sha256 <frozen SHA>
```

Actual результат: exit3, target_records674, decode_ok673, decode_blocked1,
preparation_status BLOCKED_INPUT_POLICY, native_launch NOT_APPROVED_OR_ASSEMBLED,
ml_executed false. Это успешное выявление blocker, не PASS native preparation.
Проверка читает сохранённый decode snapshot, а не заново все pixels; перед будущим
native run потребуются fresh input/runtime/resource checks и новая identity при
изменении code/inputs/profile.

## TDD и verification

18 новых behavioural tests наблюдались RED на явных missing-behaviour stubs, затем
GREEN. Из них source/runner12, target/provider3, I guard2, bundle pinning1.
Первый source preflight остановился до фото из-за private-root требований existing
image store; внешний adapter исправляет несовместимость формата источника без chmod.
Первый временный SQL harness использовал неверные имена DTO summary fields; исправлен
по фактическому контракту, synthetic transaction откатилась. Эти ошибки не являются
дефектами source corpus и не считаются независимыми review findings.

Final relevant subset: **296 PASS / 46 SKIP**,30testfiles; native и synthetic DB
opt-ins явно выключены. Один прежний Starlette HTTPX deprecation warning, без
установки нового HTTPX. Full project suite не запускался; actual owned SQL и forced
exit checks выполнены отдельно. Ruff трёх новых файлов PASS; tracked diff check PASS,
новые untracked файлы проверены напрямую. Existing tracked dirty entries сохранены.
Применены Ponytail, TDD, verification-before-completion; Clean Architecture mini,
source commit `893a88a6fce3a80c565bf39ac65021b43a8b2990`: wiring/SQL/filesystem во внешнем
адаптере, core/ports/schema не менялись. Новых Python dependencies нет.

## Отложенный вопрос по входам и следующий шаг

Один input не проходит принятый cap. Возможный следующий шаг — отдельно разрешить
подготовку уменьшенной копии1802×1802 →1536×1536 вне Gate 2 с сохранением original,
original SHA и lineage, новым input hash/manifest/profile. Это **предложение**, не
принятая нормализация и не выполненное преобразование. Альтернатива — явное изменение
scope/coverage либо отдельная переоценка pixel limit; исключение и увеличение limit
не разрешены автоматически. Владелец отложил вопрос 2026-10-09: ничего с фото пока
не делать, задача внесена в [бэклог](tasks.md#бэклог). Оригинал, input policy и manifest входов
сохранить. Следующий независимый шаг — завершить model-free native composition,
resource/storage observer wiring и exact command на fake данных в уже разрешённых
пределах. Этот независимый шаг выполнен — [composition report](build-composition-report.md).
Реальная сборка674 остаётся заблокированной до отдельного решения по входам.
20897ops/6h/32GiB по-прежнему
DRAFT_PROPOSAL, нового native window нет. T052–T055, качество и activation закрыты.

## Независимое review и исправления

PASS с замечаниями:0Critical/0Major/2Minor. Minor1 — current header не отражал
разрешённый model-free T051, а таблица bill выглядела текущей при старых NOT_RUN
значениях; header исправлен, таблица явно помечена как исходный snapshot.
Minor2 — negative target fixture мог отказать из-за неполной metadata до marker
check; fixture дополнен, единственный неверный marker проверяется с zero SQL calls.
Один цикл исправления; после него18unitPASS/RuffPASS. Production code не менялся,
bundle code fingerprints сохраняются;296/46 — scoped run до fixture correction.
Повторное review после Minor не требуется по AGENTS. Reviewer independently18unitPASS
и tracked diff PASS; actual source/SQL/private/ML checks не повторял.
