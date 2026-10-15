# Раздельная локализация и embeddings: диагностика одного фото

2026-10-15. STANDARD. Прямое поручение владельца проверить последовательность:
локализация → сохранение областей → завершение I → embeddings по одной модели.

Одно первое фото из нового owner-labelled набора. Те же frozen I config,
model revisions/preprocessing/dtype/MPS; не менять score или рабочий корпус.
Без HTTP/БД: измеряется ML-обработка и передача crops через приватные файлы.

Четыре fresh процесса строго последовательно: I, OpenCLIP, DINOv2, SigLIP2.
В первом — одна локализация (допустим штатный второй ROI-pass), затем crops
создаёт существующий NailImageProcessor по полученным маскам без повторного ML.
Сохранить маски/crops/manifest с SHA; проверить точность RGB round-trip.
До embeddings подтвердить физическое завершение всей process group I.
Каждый encoder загружает только свою модель, проверяет SHA сохранённых crops,
сохраняет векторы и завершается до следующего encoder. Нормы/размерности
проверяются, качество поиска по одному фото не оценивается.

Перед каждой фазой до300с ожидания30с непрерывного normal pressure1.
Окно ML до180с, один consumed claim на frozen package, без retry.
Общий контур≤2100с, не более четырёх фаз; STOP прерывает зависимые шаги.
Прежние RSS/MPS ceilings6GiB, critical pressure/freshness5с STOP.
Independent watchdog читает trace примерно0,5с, диагностический журнал стадий
пишет метрики примерно1с плюс границы операций. Максимум1MiB stage log/4MiB
host trace/1MiB baseline на фазу; вход≤20MiB/2359296pixels/≤10regions.
Во время identity/model validation MPS доSDK остаётся UNKNOWN.

Сохранить per-phase peaks/timing/pressure/swap и значение после завершения.
MPS driver/live не складывать с RSS. Whole-host swap не приписывать worker.
Сравнение с прежними пробами описательное: состояние машины/HTTP/БД/частота
диагностики отличаются. Не объявлять причинный эффект или исторический STOP
устранённым по одному успешному прогону.

Два RED→GREEN для crop persistence/изменённого файла;40релевантных checksPASS.
Production code не меняется, используются существующие адаптеры и recorder.
Все raw inputs/маски/crops/vectors/claims/logs privately внеGit; никакого install,
working SQL/corpus/publication, model removal, чужого process cleanup, commit/push.
Независимое review не проводилось (STANDARD).
