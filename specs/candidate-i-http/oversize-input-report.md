# Отдельный набор674: результат offline подготовки

2026-10-11. Способ утверждён владельцем ответом «разрешаю» на [предложение](oversize-input-proposal.md).
**INPUT_PREPARATION_PASS:**674bounded decodeOK;673byte-identical копии и1transformed.
T051 `[ ]`: индекс не строился, runtime window не запускался.

## Контракт и выполненное действие

FULL: approved offline copy → synthetic tests/implementation → actual private copy,
lineage/hashes/product decode → safe suites → один independent read-only review.
Набор содержит все674 позиции исходного Gate2 primary scope; subset673 не выбран.
Оригиналы, исходный manifest, исходный prepared-inventory, working DB и previous
bundles/source snapshots сохранены. Это отдельный набор входов каталога, не новая
общая политика обработки query. Реальные SDK, DB mutations, build/publish отсутствуют.

## Наблюдаемый результат

| Проверка | Результат |
|---|---|
| Новые входы |674files,673byte-identical/1transformed; исключённых позиций0 |
| Преобразование одного фото |1802×1802→1536×1536; EXIF transpose, white alpha composite, RGB/LANCZOS/PNG без metadata; Pillow11.3.0 |
| Decode |Все674 через ManifestImageStore/DecodeProfile(20971520,2359296), как при продуктовой сборке |
| Сохранность originals |Все original SHA повторно совпали; inode/mtime/ctime/mode сохранены. Исходный manifest и inventory SHA unchanged |
| Private storage |Новый root/inputs/artifacts700; input/metadata/source/logs600; всё вне Git |
| Provenance |original SHA и actual input SHA различаются только для transformed input; source_ref/product/catalog joins сохранены private |
| ML/БД |Не импортировались/не загружались модели, native_admission=false; БД в этой задаче не подключалась |

Технический decode PASS не доказывает пригодность уменьшенного фото для локализации
или поиска. Потеря мелких деталей остаётся предметом actual ML и owner testing.
Source admissibility по пикселям устранена только для нового набора; старый manifest674
по-прежнему описывает исходное1802×1802фото и не переписан задним числом.

## Freeze

Private lineage manifest содержит связь original→input и параметры преобразования.
Отдельный input profile/fingerprint и inventory фиксируют фактические новые входы;
старые native descriptors не менялись и не выдаются за descriptor нового набора.

- Profile SHA: `4a0b2bd9dfcf8e05270a3c0e051781158349988581a46bbd37bd842e3070026d`.
- Lineage manifest SHA: `11b4f5eee4e33e77c5e0cbc8699c0eeec3f996460b6152673395714c23cd3000`.
- Prepared inventory SHA: `082e456ffb9161e5601f2581d62dbfc87fd1a01dba5f9fe8470be1eb6ee2eb5e`.
- Private preparation source archive SHA: `c14279bec91c9234eac36c8c5c978abe7c0298b0a34565dba2ed6c4b0a668e61`.

Полные source paths/record IDs/private locators и фото не публикуются.

## Изменение → код → проверка

[Утилита](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_input_preparation.py)
проверяет bounded bytes/frames/pixels/source SHA/stability, пишет O_EXCL/O_NOFOLLOW
без перезаписи и с600. [Synthetic tests](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_input_preparation.py)
проверяют byte identity/сохранность source,1536RGB/alpha/newhash, EXIF orientation,
неверный SHA, symlink, existing destination, unapproved shape и pixel cap.
Тесты написаны до реализации; первоначальные8missing-module failures — scaffolding
failure, не поведенческий RED. Итог8syntheticPASS; совместно с preparation26PASS.
Релевантные33safe suites:345PASS/46SKIP/2dependencywarnings (Starlette/httpx,anyio alias).
Native/DB opt-ins выключены; full project suite не запускался из-за действующих scoped
операционных границ. Ruff2newfiles/diff/links/markers проверены; допуски не расширены.

Code independent review PASS0Critical/0Major/0Minor, independently8syntheticPASS.
Reviewer restricted/private/SDK/DB не использовал; actual674 отражены по controlled
execution evidence исполнителя. Final doc review:0Critical/0Major/1Minor — исторические pending input фразы в native report без даты. Добавлена историческая маркировка2026-10-10 и текущая зависимость worker/bill. Самопроверка ссылок/status/diff PASS; один цикл исправления Minor.

## Следующая зависимость

Подготовить actual native worker/команду и новый execution package на этом profile:
новые input/code/target/runtime fingerprints, frozen bounds/observers/teardown,
no publish. Только затем scoped execution gate до SDK/model/build. Старые draft
20897ops/6h/32GiB не являются автоматически утверждённым runtime window.
