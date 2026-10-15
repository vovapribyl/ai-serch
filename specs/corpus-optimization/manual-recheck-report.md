# Стенд поиска для уточнения ожидаемых товаров

2026-10-12. **UI_AVAILABLE; EXPECTED_GOODS_PENDING**.
[План и границы](manual-recheck-plan.md). Владелец попросил запустить поиск,
чтобы перепроверить четыре сохранённых фото. Агент запросы не выполнял.

## Что запущено

Одна новая ручная сессия на immutable каталоге20/112regions/336vectors;
image-only OpenCLIP/SigLIP2 и прежние DINO/I, без изменения ranking.
UI: http://127.0.0.1:59994/ . Пределы20поданных фото/623admissions/3600s
и прежние resource STOP; автоматического restart нет.
Расчётное окончание часового окна — 2026-10-12 16:18 по Москве;
resource STOP может завершить сессию раньше.

Рабочая ветка чата остаётся `codex/upload-optimiz`. Код продукта в ней не
переносился: runtime использует отдельный private temporary snapshot ранее
проверенного кода. Все84 code pins и assembly code SHA проверены; пути
command/PYTHONPATH/assembly указывают на этот snapshot, не на старый checkout.

Новый job SHA-256
`aa2365d3bceeab9fb007d119ccb2fc51f1fb78226804d2016acc0c846919c270`.
Catalog SHA-256
`bc829be3b2ccdc461479c1fa11c241cef237847e30ba33c962f4925c09b7bda6`.
Extractor fingerprint
`ca9ccbd1d4288726a1a7bdf04404d3e00389c77d793f1e889e355f72f5c74da2`.
Каталог, models/vectors, manifest, runtime inventory и лимиты сохранены.
Старые claims не переиспользовались; новый controller создал one-shot claim.

## Проверки

Model-free I assembly PASS, Torch/Transformers/LangSAM не импортированы.
Backend load_job/permission/RuntimeVerifier/snapshot PASS; разрешение для
неверного job отвергнуто. Существующие manual/bootstrap/native-job/resource/
watchdog tests:53PASS/2existingwarnings. Первичный collection отказ вызван
пропущенной тестовой фикстурой; её byte-identical копирование устранило отказ.
Runtime code ради этого не менялся.

Независимый read-only review подготовки:0Critical/0Major/0Minor,
`/root/manual_recheck_review`. Это review перед запуском, не quality approval.

Actual cold bootstrap: backend SDKfalse, I Torch/Transformersfalse,
reserved0, own grouptrue. HTTP /health, /, /manual-test ответили200.
В in-app browser подтверждены catalog20 banner, upload и кнопка «Найти».
Docker/resource checks потребовали исполнения вне sandbox; Docker доступен,
initial pressure1. Нулевые admissions не доказывают поиск: запросы делает владелец.

## Следующий шаг и ограничения

Владелец загружает нужные фото, сверяет найденные изображения и сообщает
expected goods для запросов1–4 либо «нет»/«не уверен». Результат поиска сам
по себе не становится ground truth. Сохранённые четыре запроса также собраны
в отдельный частный ZIP с понятными именами query-1.png … query-4.png.

Новый стенд сохраняет прежнюю политику query/evaluation; это не реализация
сохранения query vectors для ablation. Сравнение двух/трёх моделей NOT_RUN.
Полный build100/READY/publication не выполнялись; качество и экономия RAM
этим bootstrap не подтверждены. Контроллер активен на момент проверки,
teardown применяется при окончании окна или STOP.
