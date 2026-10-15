# Проверка связки для первой runtime-пробы

2026-10-14. STANDARD, продолжение пункта049 после разрешения владельца.
Проверена подготовка исполняемой связки. Реальная модельная проба050 и review051
не выполнены; результаты ниже не являются приёмкой ML или оценкой качества поиска.

## Что реализовано

| Часть | Поведение | Код |
|---|---|---|
| Процессы стадий | I работает через прежний HTTP-контракт; затем отдельные процессы OpenCLIP, DINOv2 и SigLIP2. Следующий процесс допускается после подтверждённого завершения предыдущего | [workers](../../src/product_search/infrastructure/replenishment_workers.py) |
| Владелец запуска | Частный Unix socket, конечное число команд, общий deadline и shutdown. Рабочий DSN не применяется; проверяются метка собственного контейнера, ограничения, endpoint и SQL/schema identity | [host](../../src/product_search/infrastructure/replenishment_host.py) |
| Допуски | Выдача требует SHA явно утверждённого пакета; конечный срок, новая nonce и файл без перезаписи. BUILD привязан к owner/epoch и потребляется один раз. Разрешение переходов SEARCH проверяется отдельно | [guards](../../src/product_search/infrastructure/replenishment_runtime_binding.py) |
| Ресурсы | Ограниченные OS-команды для pressure/RSS, свежая MPS-телеметрия своего worker; неизвестное, просроченное или критическое наблюдение закрывает допуск. Наблюдения сериализованы и сохраняются в ограниченном private журнале | [guards](../../src/product_search/infrastructure/replenishment_runtime_binding.py) |
| Независимый сторож | Собственная группа и наследование mode/coordinator FD; при потере controller, недостоверных ресурсах или deadline — TERM и KILL в конечном окне | [worker entry](../../src/product_search/infrastructure/replenishment_worker_entry.py) |
| Данные | Перед допуском сверяются фактические bytes выбранных исходников. Source DTO читается только для текущей RUNNING-попытки с fencing; encoder получает проверенный crop-checkpoint. SQL commits выполняет controller | [repository](../../src/product_search/infrastructure/replenishment_repository.py) |

Entry points: [host](../../scripts/run_replenishment_host.py) и
[worker](../../scripts/run_replenishment_worker.py). Python запускается с `-I -B`,
проект подключается явно; модельные окружения и cache используются read-only.
В controller новые ML-зависимости не устанавливались.

## Свидетельства

- Итоговая выбранная регрессия:512passed, одно прежнее Starlette/httpx warning.
  Это443 прежних unit/Web и69 проверок runtime/files/processes;43 случая новые,
  26 проверок lifecycle уже существовали. Полный repository suite не запускался.
- Новый DB-сценарий:1passed в собственном временном контейнере. После завершения
  listing `replenishment-b1` пуст. Миграция0010 не развёртывалась в рабочей БД.
- Проверены запрет второй стадии до teardown, чужая попытка, поздний результат
  после STOP, наследование дополнительного coordinator FD, одноразовое потребление,
  подмена/удаление claim, расширение окна, source hash mismatch, сериализация
  observations и остановка при заполнении журнала.
- Проверен путь crop-checkpoint → выбранный encoder → vector-checkpoint с fake
  encoder. Известная ошибка фото отделена от HTTP timeout с неопределённым исходом.
- Entry points проверены в трёх существующих окружениях: отказ без допуска,
  совпадение package inventories, Torch/Transformers/OpenCLIP не импортированы.
- Metadata-only I readiness/constructor:PASS, без сервера/SDK/inference.
  Повторно проверены87 encoder manifest entries:39+18+30. Прежнее число89 было
  ошибкой подсчёта; идентичность трёх manifests от этого не меняется.
- Frozen input/package identities и права0700/0600 проверены;77 code files
  включены в свежий inventory. Ruff и diff checks — отдельно от runtime.

Первые ошибки отсутствующего implementation import не считаются функциональным
RED. Поведенческие RED наблюдались на интерфейсных заготовках и отдельных дефектах
до исправления: повторный допуск/подмена claim, чужая попытка, resource STOP,
checkpoint payload, границы окна, выдача grant, source mismatch и observation race.
Параметризованные отрицательные случаи дополнительно проверяют границы; не каждый
такой случай имеет отдельное свидетельство RED.

## Ошибки подготовки

Первая DB-команда не получила доступа к Docker socket в sandbox; дополнительная
ошибка diagnostic path возникла до старта контейнера. После scoped elevation
наблюдался ожидаемый RED source DTO, затем GREEN1. Полный DB-набор автоматически
не повторялся. Опечатка в имени test-файла остановила collection до выполнения;
имя исправлено, итоговая регрессия выполнена.

При пересборке сначала неверно сравнили полный model identity с encoder-only
списком; проверка исправлена на encoders+localization. Затем сериализация JSON
профиля I изменила его файловый SHA. Скопированы точные исходные bytes; manifest
не ослаблялся, readiness/assembly повторно прошли. Эти ошибки не являются TDD RED.

## Что ещё не подтверждено

Настоящие SDK/model load, MPS availability/peak, inference, физическое освобождение
ресурсов, runtime-совместимость vectors и публикация модельного результата — UNKNOWN.
Нет новой модельной БД, grant или execution claim для выбранного фото. Состояние
всех прежних ML-процессов перед050 ещё требуется проверить; отсутствие listener
на59994 само по себе не доказывает их отсутствие. Рабочий Web не переключался.

Независимое review не проводилось: STANDARD, самопроверка.051 остаётся открытым.
Новый пакет и точная граница разрешения описаны в [предложении пробы](runtime-probe-proposal.md).
