# Полный поиск с облегчёнными моделями: стенд открыт

2026-10-11. UI_AVAILABLE; OWNER_QUALITY_PENDING.
[План](image-only-manual-plan.md), [изменение providers](image-only-load-report.md).
Владелец разрешил проверить полный поиск на своих примерах. Запросы выполняет
владелец; agent queries0. Наличие интерфейса не подтверждает качество выдачи.

## Запуск и устранённая причина отказа

Первый jobbce4988f... завершился за1,138s с I_READINESS_STOP до UI/загрузки ML.
Служба I вернула MODEL_NOT_READY: её assembly manifest включает код embedding
providers, контрольные суммы которых остались прежними. Model-free диагностика
подтвердила ровно2code mismatches; packages/VCS/runtime/config/dependencies и
остальные non-model files совпадают. Pressure1, leases reacquired true.
Не перепутать этот refusal с прошлым critical memory pressure.

Корректировка затронула только подготовку нового частного пакета. Обновлены
2manifest entries на reviewed image-only code, честно пересчитан extractor
fingerprint. Создана отдельная immutable test-only catalog identity с pinned
compatibility lineage. Все20products/vectors/models сравнивались и сохранены;
исходный catalog snapshot/SQL/build100/activepointer остаются прежними.

Первое source review подготовки PASS0/0/0; review корректировки0C/0Major/1Minor:
producer должен проверять source SHA до чтения/refreeze. Исправлено, negative
pin check отвергает подменённые bytes, lineage включён в job до hash. Model-free
assemble_service PASS с Torch/Transformers/LangSAM не импортированными. Нового
productcode/SDK/modelweights/preprocessing/dtype/ranking в этой задаче нет.

## Актуальный frozen пакет

JobSHA256 `9c5aace5b962fbe6cc56baca1b4319fc8969d3a7514a85b064f5221aa371e6e3`;
84 актуальных code pins, совпадающих с reviewed provider code.
Prepared archiveSHA256
`7616cf8c433f56323908d98d4502c60a1eaa6a69ae9c433816a4c3bbdceabcb3`.
AssemblySHA256 `d8cf96af53ff07aa6493bcc50821be2854f0b8e69dd193a1b7a971b1874ed98e`.
Extractor fingerprint
`ca9ccbd1d4288726a1a7bdf04404d3e00389c77d793f1e889e355f72f5c74da2`.
Test-only catalog snapshotSHA256
`bc829be3b2ccdc461479c1fa11c241cef237847e30ba33c962f4925c09b7bda6`;
manual fingerprint
`7adee48e4c929ed38f9dcd788f5ff7787643f8a61df23ca77dcb2687692dc18b`.

20фото/112regions/336vectors. Cold bootstrap: backend SDKfalse/reserved0,
pressure1/stopnull, HTTP UI показан в браузере. Новые PNG/JPEG/WebP допускаются;
данные и оценки сохраняются privately вне Git. No catalog ML build/SQL READY/publish.

Актуальный UI: http://127.0.0.1:57541/ . Сессия до23:59Moscow2026-10-11,
≤20поданных фото (повторы считаются),≤623admissions,≤3600s; все прежние hard STOP
и отсутствие автоматического рестарта сохранены. Controller active на момент
bootstrap; teardown текущей сессии ещё не применим.

## Проверка владельцем и ограничения измерений

Повторить прежние WB-фото/скриншоты и оценить ожидаемые товары и варианты в выдаче.
Без списка/оценок прежних запросов нельзя утверждать формальное сравнение coverage.
Оценка полного поиска с этим runtime пока UNKNOWN. Source category008 сохраняется;
ограничение business labels для временных татуировок остаётся в инструкции.

Supervisor сохраняет host pressure, RSS групп, swapouts и storage. MPS stage metrics
не добавлялись; полную экономию physical RAM нельзя вывести из одного RSS или
малой embedding пробы. После owner testing проанализировать фактический trace.
Успешный UI не доказывает длительную стабильность обработки оставшихся78фото.

Финальное независимое read-only review отчёта и границ PASS0Critical/0Major/0Minor.
