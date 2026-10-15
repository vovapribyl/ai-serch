# Результат сравнения семи комбинаций моделей

2026-10-12. **COMPLETED_BOUNDED_EXPERIMENT; MODEL_REMOVAL_NOT_DECIDED**.
[План](model-ablation-plan.md), [исходные данные и разметка](model-ablation-inventory.md).

## Результат

На трёх owner-confirmed запросах каждая из семи комбинаций поставила правильный
товар на первое место среди20 товаров. Ухудшений или улучшений ранга относительно
трёхмодельного baseline нет.

| Модели | Запрос1 | Запрос2 | Запрос3 | Top3 | Top10 |
|---|---:|---:|---:|---:|---:|
| OpenCLIP + DINOv2 + SigLIP2 |1|1|1|3/3|3/3|
| OpenCLIP + DINOv2 |1|1|1|3/3|3/3|
| OpenCLIP + SigLIP2 |1|1|1|3/3|3/3|
| DINOv2 + SigLIP2 |1|1|1|3/3|3/3|
| Только OpenCLIP |1|1|1|3/3|3/3|
| Только DINOv2 |1|1|1|3/3|3/3|
| Только SigLIP2 |1|1|1|3/3|3/3|

Числа3/3 относятся только к этим трём примерам. Запрос4 исключён: владелец
указал отсутствие товара в subset20. Официальные метрики корпуса не рассчитаны.

## Что выполнено

Один новый inference pass:3query photos →15regions(5/6/4) →45vectors.
Векторы сохранены privately и переиспользованы для семи offline расчётов.
Для каждой комбинации построено среднее выбранных моделей, заново найдено
assignment, применены missing0/query denominator и прежние ranking/tie правила.
Все20 товаров ранжировались до определения позиции expected goods.
Трёхмодельный score и assignment совпали с исходным core на всех60 парах фото.

Входные SHA трёх запросов отличаются от SHA соответствующих каталожных фото.
Это исключает побитовое совпадение исходных файлов, но не доказывает независимость
снимков, различие ракурсов или сложность выборки.

## Проверки и runtime evidence

Новый job SHA-256
`b1abbedbaa8be7e54bc064edb9deb73bf0bb5c19d19f3aff71f38de9f0049be4`.
Catalog SHA-256
`bc829be3b2ccdc461479c1fa11c241cef237847e30ba33c962f4925c09b7bda6`.
Модели/revisions/preprocessing/dtype/manifest и исходные336catalog vectors
сохранены. Experimental capture/runner frozen отдельно от product кода.

Прогон34,039секунды,51/96admissions, worker/controller exit0,
stop_reason/observation_stop null; I own exit−15.159resource samples:
pressure1 —135, pressure2 —24, critical4 не наблюдалось. Warningpressure
не скрывается: эта короткая проба не доказывает длительную стабильность.
Финальная own group0, device/coordinator leases reacquiredtrue.

TDD:12experiment checks PASS; ранее64safe checks PASS включали11experiment
и53manual/bootstrap/native-job/resource/watchdog tests. Scoped Ruff PASS.
Checks сохранены [отдельно от штатного suite](experiments/test_compare_nail_models.py):
в текущей ветке нет полного runtime, для этих тестов требуется frozen src
на PYTHONPATH. [Расчёт](../../scripts/compare_nail_models.py).

Independent read-only review перед capture:0Critical/0Major/1Minor
(offline rank/report driver ещё отсутствовал). Minor исправлен: rank_combinations
добавлен с TDD и fresh baseline parity на реальных сохранённых данных.
Повторное review не требовалось по FULL-маршруту для Minor.

Прежняя ручная сессия завершена перед пробой. После SIGTERM controller
вернул sanitized PermissionError и не записал session-result; это не выдаётся
за успешный прежний teardown. Отдельно подтверждены отсутствие её own группы
и свободные locks. Новая проба завершилась с полным session-result.

## Вывод и предел решения

На этом наборе DINOv2 не хуже OpenCLIP/SigLIP2 по рангу правильного товара.
Удаление любой модели не изменило этот показатель, но набор не различает
качество вариантов. Историческое full-image отставание DINOv2 не переносится
автоматически на текущие per-nail crops и иной каталог.

Следующая содержательная проверка — новые сложные запросы с другими ракурсами,
близкими дизайнами и большим покрытием корпуса. Набор и размер остаются выбором
владельца; нового ML-окна этот отчёт не открывает. Для удаления модели нужно
отдельное решение и изменение принятого model/score contract.

Ни модель, ни рабочая формула не отключались/не менялись. Корпус не строился,
SQL/active pointer/publication не менялись. Экономия RAM и скорость runtime
каждой комбинации не измерялись. Все inputs/vectors/source IDs/owner labels
и подробные ranking rows сохранены вне Git privately.

Evidence перенесено из временного runtime в постоянный частный каталог:
19файлов сверены по SHA; manifest SHA-256
`c002f9d36c1d1cc088c2485e3f0b05410a282e9cdaaf53d4a53886912ded0d84`.
Это архив результатов, не исполняемый job и не разрешение повторить окно.
