# Контракт локальной команды владельца

v1 / APPROVED_BY_OWNER. Предлагается CLI для первой версии; новых Web-операций пополнения
и новой модели авторизации нет. Команда исполняется владельцем локального контура и отправляет plain command
единственному supervisor через частный Unix socket. Она не захватывает mode lock
заново и не начинает независимый ML-процесс; status получает сохранённое состояние.

После реализации: python -m product_search.infrastructure.replenishment_cli
с подкомандами start, resume, retry-photo, retry-publication, status.
Start/resume/retry получают --execution-package <private-json> и ссылку на
зафиксированный inventory/run/revision/photo. Status читает только существующий run.
Предлагаемая грамматика (PACKAGE/INVENTORY — private пути, остальные аргументы — ссылки):

| Подкоманда | Обязательные параметры |
|---|---|
| start | --execution-package PACKAGE --inventory INVENTORY |
| resume | --execution-package PACKAGE --run RUN_UUID |
| retry-photo | --execution-package PACKAGE --revision REVISION_UUID --photo PHOTO_UUID --expected-version INTEGER |
| retry-publication | --execution-package PACKAGE --revision REVISION_UUID |
| status | --run RUN_UUID |

Неизвестные/повторные параметры отклоняются; help не подключает БД/ML.
Корпус/weights не передаются inline. Exit codes: 0 выполненная операция/status,
2 неверный ввод/пакет, 3 busy/conflict, 4 запуск остановлен по guard/deadline,
5 infrastructure error, 6 неизвестный результат commit до сверки receipt.
Запуск с завершёнными ERROR фото может завершиться штатно с кодом0: исходы явно
видны в summary, код0 не означает отсутствие ошибок отдельных фото.

Выход: RunSummary/PublicationReceipt JSON, без raw source paths/секретов; код0 только
при выполненной операции, отказ допуска/неподтверждённый исход — ненулевой код с причиной.
Успешная status-команда не означает успешный build. Файл пакета частный, schema/version/
права/identity проверяются до подключения моделей и мутаций. Нет --force, bypass или
автоматического retry. Текст help не выполняет операции.

Web показывает временную недоступность поиска; adapter переводит
TEMPORARILY_UNAVAILABLE в существующую обработку busy либо 503 с понятным текстом.
Выбор конкретной существующей ветки busy подтверждается при B0, семантика ФТ неизменна.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.
