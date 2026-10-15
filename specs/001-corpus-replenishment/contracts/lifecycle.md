# LLD: режимы, процессы и deadlines

v1 / APPROVED_BY_OWNER. Один supervisor владеет режимом. Web лёгкий; ML выполняют собственные
процессы группы запуска, I вызывается по прежнему HTTP-контракту.

## Исключение режимов

При старте единственный supervisor получает безопасный mode.lock через
LOCK_EX|LOCK_NB. Это владение всем локальным ML-контуром, не отдельной CLI-командой.
CLI посылает команды supervisor через owner-only Unix socket в private runtime root
(каталог0700, socket0600); второй supervisor при занятом lock не стартует.
Web/search и команды владельца проверяют один admission state supervisor.

Для управляющих переходов есть отдельный command_lock внутри supervisor.
Он не совпадает с mode/device/coordinator flock и не удерживается во время
длительного drain. Все изменения admission и выдача query permit сериализуются
этим lock; межпроцессный канал не выдаёт permit самостоятельно.

SEARCH → DRAINING → BUILD:

1. Проверить пакет/полномочие build. Под command_lock подтвердить SEARCH,
   установить DRAINING и закрыть выдачу новых query permits одной операцией.
   Конкурирующий поиск либо получил permit раньше и учитывается как текущий,
   либо получает TEMPORARILY_UNAVAILABLE. Второй build получает BUSY.
2. Освободить command_lock и bounded ждать завершения всех ранее выданных permits.
   Время ожидания ограничено end_at/cleanup reserve. Истечение не запускает BUILD.
3. Остановить собственные query/I-процессы; подтвердить выход всех handles и
   закрытие их inherited lock references. Фактическое освобождение ресурсов
   проверить свежим наблюдением. Неподтверждённый выход оставляет admission закрытым.
4. Supervisor сохраняет свой mode FD открытым: между режимами нет unlocked окна.
   Под command_lock и короткой DB транзакцией сверить ожидания, выдать новый
   fencing epoch/token и установить BUILD. Перед выдачей child permit повторно
   проверить пакет/ресурсы. Ошибка БД оставляет RECOVERY_REQUIRED, не SEARCH.
5. Запустить только BUILD children, передав им descriptor существующей mode lease.
   Они не unlock-ят его. После build teardown закрыть все child references;
   возврат SEARCH происходит симметрично через новый epoch и проверку допуска поиска.

Mode descriptor одной flock-блокировки явно передаётся собственным ML-процессам
через pass_fds и удерживается до их выхода. При parent crash close не должен снять
lock при живом ребёнке. Дети не вызывают LOCK_UN; supervisor не unlock-ит живых детей.
Текущий FileLease.release с LOCK_UN нельзя использовать для раннего cleanup.
Преемник получает lock только после выхода старых детей; admission на startup закрыт
до восстановления состояния. Unix socket содержит команды приложения, не новые
публичные Web-операции; IPC schema соответствует contracts/application.md.

Процессы запускаются с shell=False, start_new_session=True и проверенным argv;
process registry хранит run/token, process handle и группу, а не доверяет одному PID.
Внутри ML-операции остаётся device lease; HTTP parent не удерживает её вместо I.
Инвариант mode lock не заменяет device/coordinator leases и runtime identity.

## Fencing и авария родителя

DB commits выполняет только controller/supervisor, с epoch/token текущего owner.
ML-дети могут завершить файл, но не подтвердить COMPLETE/публикацию. При потере
supervisor UI закрывает admission; recovery может выдать новое epoch только
после подтверждённого отсутствия детей и получения mode lock. Все поздние результаты
старой попытки отвергаются. При недостоверности БД или процесса режим RECOVERY_REQUIRED.

## Таймеры

Один monotonic end_at применяется к drain, HTTP, encoder, DB и teardown.
В ExecutionPackage обязательны конечные stop_grace/kill_wait и deadlines adapter.
Перед началом тяжёлой операции проверить, что остаётся согласованный резерв cleanup;
его значение задаётся package, не изобретено в плане. Достигнут deadline — прекращение
новой работы, отмена/остановка своих процессов в пределах cleanup budget.

Warning не начинает новую тяжёлую операцию. Текущая остаётся под guard. Пауза
заканчивается не позже min(start_wait+300s, end_at-cleanup_reserve); для возобновления
30s свежих допустимых сигналов подряд. Warning сбрасывает устойчивость, но не end_wait.
При равенстве deadline продолжение запрещено. Critical/unknown/stale сразу hard STOP.
Часы ядра fake-able; adapter monotonic служит production-часами, wall clock только аудит.

## Завершение

Остановить свои группы мягко, ждать не дольше stop_grace, затем kill и ждать kill_wait;
подтвердить все handles/группы и закрытие lock references. SIGTERM/exit parent сам
по себе не доказывает выход детей. Неподтверждённый выход оставляет admission закрытым.
После teardown проверить свежие ресурсы; возврат SEARCH требует допустимого отдельного
профиля/разрешения поиска. После hard STOP нет автоматического ML-рестарта.

На Mac обязательна немодельная проверка наследования FD через exec и блокирования
другого режима при parent death. Пока она не проходит, model-backed gate закрыт.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.
