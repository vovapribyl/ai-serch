# Сравнение семи комбинаций embedding моделей

2026-10-12. FULL, ограниченный эксперимент. Владелец подтвердил «Приступай»
после согласования семи непустых комбинаций OpenCLIP/DINOv2/SigLIP2.

## План-контракт и scope

Три сохранённых фото с owner-confirmed expected goods; subset20 с прежними
336vectors. Запрос4 исключён из rank/top-k: владелец сообщил, что товара нет
в subset20. Один новый frozen прогон I и трёх embedding providers, затем
семь offline комбинаций без повторного inference для каждого варианта.

Существующую ручную сессию этого чата завершить перед тяжёлой обработкой;
только owned группа, без вмешательства в чужие процессы. Новые code/command/
assembly paths указывают на отдельный private runtime snapshot. Сохранённые
входы и каталог проверяются по SHA; старые consumed claims не переиспользуются.

Пределы нового окна: ровно три разрешённых query inputs, максимум96admissions
(3×(1localization+3×10regions)+3provider loads),600секунд; прежние pixels/bytes/
regions/solver/RSS/storage/pressure STOP. No auto retry/restart, build/publish,
DB write, model removal, SDK install или изменение моделей/preprocessing/dtype.
БД и Docker читаются только существующим resource observer.

## Расчёт

Каждую пару query/catalog нормализовать по текущей float32→float64 процедуре.
Сохранить cosine→(c+1)/2. Для выбранного набора моделей вычислить среднее
их pair scores, заново найти оптимальное assignment прежним solver; missing
query region=0, делитель — число query regions. Ранжировать все20 товаров,
с прежними best-photo и deterministic tie правилами. Baseline всех трёх
сверить с существующим match_photos по score и assignment.

Семь вариантов: все три; каждая из трёх пар; каждая отдельная модель.
Отчёт: ранги expected goods по трём запросам, top3/top10 как counts с denominator3,
улучшения/ухудшения относительно baseline. Не выдавать за официальную оценку
всего корпуса, приёмку или достаточное основание удалить модель.

## Проверка и evidence

TDD для набора комбинаций, повторного assignment, missing0/denominator,
tie и invalid inputs; baseline parity на сохранённых данных. Один независимый
read-only reviewer до нового ML. После запуска: complete3 capture, admissions,
resource trace/stop, exit и освобождение own группы/leases. При STOP сохранить
частичные результаты; не выполнять незаявленный повтор.

Все фото/векторы/owner labels/source IDs/runtime files вне Git,700/600.
В публичном отчёте только safe aggregate результаты. Код эксперимента отделён
от production алгоритма: Clean Architecture mini для границы расчёт/ML-файлы;
ponytail для переиспользования существующих normalization/solver/guards.
