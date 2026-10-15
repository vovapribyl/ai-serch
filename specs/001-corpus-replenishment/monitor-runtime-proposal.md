# Проверка терминального мониторинга во время обработки

Дата: 2026-10-14. Статус: **EXECUTED / OK**.

Владелец разрешил подготовить свежий пакет для одного прогона на пяти фото с открытым монитором. После отдельного разрешения один START выполнен успешно, grant consumed, временная БД удалена. [Отчёт](monitor-runtime-report.md) содержит результат. Следующие разделы сохраняют исходные условия подготовки. [Терминальная сводка](light-monitoring.md) ранее проверена на synthetic данных и сохранённом результате, теперь нужно проверить её обновление во время настоящей обработки.

## Пакет

SHA-256:
`bf12dde3815aab77a016e0e102f5f78b19aaf66c9abd405273648f4aeafe0eae`.

Заморожен81файл кода, включая модуль reader и scripts/monitor_replenishment.py. Те же пять товаров по одному фото:1PNG+4JPEG,754307байт. Input/model/semantic hashes совпадают с успешной пробой99cea844; новый code/runtime/claims fingerprints и собственный target identity. Старые результаты19ad687c и consumed grant не переносятся.

Один START,24MLadmissions,1200с общего времени; ожидание ресурсов300с/стабильность30с. RSS/MPS6GiB,I RSS6GiB/encoder RSS5GiB,HTTP330с/DB5с/TERM5с/KILL5с/cleanup30с. Фото20MiB/2359296пикселей/10регионов;IPC40MiB/vectorJSON1MiB/error64KiB. Собственная временная PostgreSQL: схема0010, закреплённый образ,512MiB/1CPU/128PID/tmpfs256MiB/localhost.

Диагностика и empty_cache_after_photo включены как в успешных пробах. Журнал controller ограничен1MiB×3; новый viewer только читает данные раз в3секунды. Бизнес-правила, resource guard и process-group confirmation не менялись.

## Порядок проверки

После отдельного разрешения: проверить live quiescence и pressure, создать собственную БД и свежий грант, запустить host и отдельный read-only viewer, выполнить один START. Обновления viewer сохраняются в приватном monitor-output.log; при завершении или остановке viewer также закрывается. Рабочий каталог, БД и Web не затрагиваются.

Проверим:

- Во время обработки видны RUNNING, стадия, увеличивающиеся checkpoint и подтверждённые исходы фото; свежесть ресурсов указана явно.
- После возврата SQL-сводки показан подтверждённый итог и счётчики5/5/20checkpoints/5publications при успехе. При неизвестном результате отображается UNKNOWN, а не придуманный успех.
- Обработка даёт5photoOK/5READY/32региона/96векторов, по32каждой модели512/768/768, конечные значения и единичную норму;5publications/5active members.
- Crop/mask bytes/size/SHA сравниваются с предыдущей успешной партией; полнота operational journal, выход четырёх workers и итог viewer проверяются отдельно.
- После прогона нет собственных host/worker/viewer/process groups, probe-БД/socket/secrets. Приватные свидетельства сохраняются.

Если возникнет STOP/ошибка, записывается частичный результат; автоматического повтора или изменения лимитов не будет. Отсутствие progress/старый heartbeat не выдаётся за доказанную причину зависания. Точная CPU/I/O стоимость мониторинга по одному прогону не определяется.

## Подготовка

Code/input bytes/hashes/DTO/private permissions прошли проверку. I metadata/inventory/VCS/runtime/config и metadata-only assembly прошли без SDK/сервера. Три actual environment entrypoints отвергли proposed control с code5 без Torch/Transformers/OpenCLIP; inventories совпали. Полный повторный rehash encoder weights не выполнялся, native проверяет manifest перед загрузкой.

Последняя проверка реализации:163релевантных теста. После неё runtime-код не менялся; новый runner с запуском и очисткой viewer проверен по синтаксису, не исполнялся. Review не проводилось. Live resource/target preconditions проверяются перед разрешённым исполнением, сейчас их готовностьUNKNOWN.

Для этого пакета требуется отдельное разрешение владельца на исполнение по [quickstart](quickstart.md). Сотни фото, постоянный monitoring service, Web-интеграция, аварийные уведомления и рабочая активация не входят в scope.


Исполнение2026-10-14:OK91,424с/host0/viewer0,5OK5READY20checkpoints96vectors5publications.31viewer snapshots WAITING→RUNNING→COMPLETED,progress0→20checkpoints/0→5publications. Owned cleanup подтверждён; грант повторно не используется.
