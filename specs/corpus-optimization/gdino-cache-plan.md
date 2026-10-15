# Проверка освобождаемой памяти после Grounding DINO

2026-10-15. STANDARD. Владелец согласовал продолжение исследования временных
выделений и кеша после [раздельного прогона](staged-resource-report.md).

Один fresh I process, то же фото/config/model/preprocessing/dtype/MPS.
Только диагностическая обёртка: после каждого успешного Grounding DINO predict
сначала synchronize, затем empty_cache. До/после каждой операции записать
MPS driver/live и ресурсы. Возвращаемый результат predict сохраняется тем же
объектом; при ошибке предсказания cleanup не вызывается. Оригинальный метод
восстанавливается по выходе из контекста. Постоянную production policy не менять.

Сверить SHA всех crops/масок с предыдущим staged I. Снижение driver после
empty_cache при неизменном live покажет освобождаемую часть выделений в этой
точке. Это не уменьшает задним числом пиковую память внутри predict и не
раскладывает все оставшиеся выделения по кешу/MPSGraph/прочим категориям.

Прежний допуск: до300с ожидания30с continuous normal pressure1, одно окно180с,
RSS/MPS≤6GiB, critical/freshness5с STOP, независимый watchdog. Samples1с плюс
границы, external trace≈0,5с;1MiB stages/4MiB trace. Новые package/code/input
SHA и одноразовый claim; без retry, DB/HTTP/embeddings/corpus/publication/install.

TDD helper:1ожидаемый RED/1PASS→2PASS; с существующим diagnostic suite30PASS.
Финальная копия helper с отдельным импортом recorder проверена2PASS доML.
Техническая правка alias модуля сделана до выдачи finalpackage/claim.
Проверить полное завершение own group, locks, сохранность frozen pins,
архивировать только privately; в Git агрегаты и методика. Review не проводилось.
