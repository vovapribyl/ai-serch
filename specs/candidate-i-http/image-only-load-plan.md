# Облегчённая загрузка image providers

2026-10-11. FULL. Владелец: «Давай попробуем начать с этого» после объяснения
сохранения image processing и удаления unusedtext. Scope: existingOpenCLIP/SigLIP
vision branches, sameweights/preprocess/float32/dimensions/normalization/ranking;
DINO unchanged. Нет нового catalogbuild/READY/publication/SDKinstall/download.

План-контракт: проверить окончание прежнейmanualsession → regressionREDбезSDK →
загрузить fullcheckpointнаCPU, сохранить imagebranch, удалить rootmodel доMPStransfer →
GREEN/model-freecontracts → независимый read-onlyreview → подготовить конкретную
bounded equivalence/memoryprobe на существующих crops/vectors → reviewable результат.
Реальный сравнительный запуск требует точного зафиксированного probe/budget; этот
контракт не разрешает повторную обработку100 или бесконечнуюmanualsession.

Минимальный loader сохраняет текущую реализацию image encoder, включая projection
OpenCLIP и pooling SigLIP. CPUtext временно создаётся: устранение loadpeak потребует
отдельного directvisionloader; первая правка устраняет steady-state text residency
и перенос unusedtext наMPS, не заявляет отсутствие textallocation при load.

Прежнийmanualwindow завершён WALL_CLOCK_LIMIT3600, leasesreacquiredtrue.
Новыйruntimecode меняет frozenidentity; старые claimedjobs не переиспользовать.
Проверять numericequivalence и realmemory отдельно: synthetic не доказывает качества.


## Подготовленная и выполненная малая проверка

Исполнитель ограничил проверку: фото001, его3 существующих RGB crops,
2изменённых providers,8admissions,600s. Эталон — сохранённые catalog vectors.
После source review и исправления замечаний выполнено одно окно; noI/noDBwrites/
noPublish, прежние resource STOP. [Результат](image-only-load-report.md).
Общее качество/полный runtime ещё не приняты; повторные окна отдельно.
