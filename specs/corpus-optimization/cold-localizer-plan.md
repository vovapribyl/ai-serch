# Диагностика холодного локализатора на одном фото

2026-10-15. STANDARD. Владелец ответил «Разрешаю» на отдельную диагностику
cold I после [остановки семи запросов](quality-seven-report.md).

Гипотеза: критическое давление возникло при холодной загрузке или первом
предсказании I. Предыдущий trace показал pressure4 до получения результата,
но не позволял различить импорт SDK, загрузку Grounding DINO/SAM и predict.

Проба: одно ранее переданное фото, тот же frozen I config/model/code identity.
Отдельный fresh process, без HTTP/БД и embedding providers. Проверить model-free
assembly, затем измерить импорт Torch/LangSAM, gdino.load/sam.load,
gdino.predict/sam.predict и localizer.pass/photo. Существующий LoadDiagnostics
и instrument_localizer оборачивают операции, не меняя их аргументы/результаты.
Это измеряет ML-ядро I; HTTP overhead и полный поиск сюда не входят.

Допуск: 30 непрерывных секунд pressure1 в окне до300 секунд. Warning/UNKNOWN
сбрасывает стабильность. Затем одно окно локализации до300 секунд, без retry.
STOP при critical pressure, RSS/MPS более6 GiB, неизвестном/устаревшем более5с
обязательном наблюдении. Начальное отсутствие MPS до импорта Torch — UNKNOWN,
не измеренный ноль. После импорта MPS записывается in-process каждые0,5с.
Внешний watchdog собирает RSS/pressure/swap также примерно каждые0,5с.
Whole-host swap не приписывать процессу. Лимиты не повышаются.

Новые package/source/input SHA frozen до запуска, одноразовый claim.
Private stages≤1MiB, host trace≤4MiB, baseline≤1MiB. По завершении проверить
собственную process group и leases; никакие чужие приложения не закрывать.
Фото/векторы/source IDs вне Git. Dependency install, corpus/SQL writes,
model removal, commit/push/merge исключены.

Проверка: TDD стабильного допуска и классификации STOP; существующие тесты
LoadDiagnostics/instrument_localizer. Производственный код не меняется.
Независимое review не проводилось. Нового инженерного вопроса для книг нет.
