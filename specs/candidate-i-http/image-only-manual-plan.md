# Полный ручной поиск с облегчённой загрузкой

2026-10-11. FULL. Владелец «Давай проверим» после предложения проверить полный
поиск с облегчёнными моделями на его примерах. Одна новая ограниченная manual
сессия: готовый immutable каталог20; новые PNG/JPEG/WebP запросы владельца;
image-only OpenCLIP/SigLIP2, прежний DINO и I; same weights/preprocessing/float32/
ranking. Catalog ML build/SQL READY/publish и обработка78PENDING сюда не входят.

План-контракт: проверить завершение прежнего own runtime → freeze актуального
reviewed code и тех же catalog20 inputs → read-only независимое review → cold
loopback bootstrap без query/SDK calls → открыть UI владельцу → сохранить его
оценки и existing host trace. Agent не выполняет запросы и не ставит owner labels.

Лимиты прежние:20поданных фото (повторы считаются),623admissions,3600s; bytes20MiB,
pixels2359296, regions10, pressure4/unknown/stale STOP, RSS6+5/combined10GiB,
storage32GiB/free16GiB. Никаких auto retry/restart или ослабления STOP.
Все labels/query/evidence остаются вне Git privately700/600.

Качество: владелец проверяет те же WB-фото/скриншоты, которые его устроили ранее;
ожидаемый товар и выдачу оценивает лично. Связь с прежними запросами без их
зафиксированного списка не считать доказанной. Ранее6vectors delta≤2,314e-08
на3crops поддерживает совместимость, но не заменяет full-search проверку.

Память: existing supervisor записывает host pressure, RSS групп, swapouts и
storage. Новая MPS stage telemetry здесь не добавляется; по одному RSS нельзя
доказать экономию полного physical footprint или ровно1,3GiB. Успешная manual
сессия не доказывает длительную стабильность corpus build.

[Реализация и малая проба](image-only-load-report.md),
[методика ручной оценки](manual-validation.md).

## Уточнение после проверки запуска

Первый bootstrap jobbce4988f... завершился за1,138s с I_READINESS_STOP,
без UI/queries/admissions; pressure1, leases reacquired. Model-free preflight
подтвердил: assembly manifest включает дополнительный код обоих embedding providers;
его2старых SHA не соответствуют новой reviewed реализации. Остальные non-model
files/runtime/packages/VCS/config/dependencies совпадают. Облегчённый provider не
является причиной ресурсной остановки: ML не вызывался.

Подготовлена корректировка без нового productcode: обновить только2manifest entries,
пересчитать честный extractor identityca9ccbd1...; создать отдельную test-only
catalog identity7adee48e... с pinned compatibility lineage. Все20products, vectors,
models и исходный catalog snapshot сохранены. OriginalSQL/READY/publish не меняются.
Новый согласованный jobfe200d99...,84pins, те же20/623/3600. Model-free assembly
PASS, Torch/Transformers/LangSAM не импортированы. Independent review выполняется
до нового запуска; это исправление failed cold bootstrap в разрешённой задаче,
не повтор ML по corpus и не обход прежнего STOP.

Финальный пакет после sourcepin correction: job9c5aace5..., identity/lineage те же.
ColdUI открыт; [актуальный отчёт](image-only-manual-report.md).
