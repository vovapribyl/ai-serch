# Исходный800 после снижения фоновой нагрузки: один прогон прошёл

2026-10-15. STANDARD. **EXECUTED / OK_ONE_PHOTO**.
Владелец сообщил, что закрыл сторонние приложения, попросил один новый прогон
и явно выбрал: «Исходный800 — один прогон, прежние лимиты, без повторов».
Закрытие всех сторонних приложений — заявление владельца; состояние каждого
приложения отдельно не проверялось. Новый пакет:
`73ef43d15318a8c59fb3c51539ac70d4325a097ec27fad1e71407032a58fbc84`.

- Одно прежнее фото, SHA `1b55d41600db2cf4a74e38ca4e26340c236b67fbd22f0905fec5b3a89458040a`.
- Исходный processor800/1333, прежние веса/profile/ROI/dtype. Worker и runner
  побайтово совпали с [остановленным800](../001-corpus-replenishment/one-photo-observability-report.md).
- Новый приватный execution root/approval/claim,166pins; вход и source hashes
  проверены до и после. Старые consumed packages не переиспользовались.
- Прежние6GiB/criticalpressure/freshness5с/deadline guards; baseline≤300с,
  stability30с,worker≤300с. Диагностика worker1с+границы/host0,5с прежняя.

| Результат | Наблюдение |
|---|---|
| Baseline |56samples pressure1,30,174с |
| Worker / весь контур |15,669 /45,897с |
| Итог |OK,exit0,stop_reason=null,watchdogNONE |
| Локализация |3области,2завершённых GDINO predict |
| Host pressure |29normal1,0warning2,0critical4 |
| Наблюдаемый peak MPS driver |3965796352bytes,около3,97ГБ |
| Наблюдаемый peak MPS live |1487020288bytes |
| Наблюдаемый peak RSS I-группы |1439956992bytes |
| Whole-host swapouts delta |0страниц в наблюдениях |
| Worker журнал |38записей/21898bytes,все measurement_ok=true,incomplete=false |

Исходный800 способен завершить это фото при наблюдавшемся состоянии машины,
без увеличения лимита и изменения processor. Результат согласуется с влиянием
общей фоновой нагрузки, но один неконтролируемый повтор не доказывает точную
причину прежнего pressure4 или исключительную причинность закрытия приложений.
Длительная устойчивость и качество поиска этим не установлены.
Наблюдаемый driver не складывается с RSS; короткие пики могли быть пропущены.

Независимая проверка:0controllerPID/workerPID/процессов workerPGID, оба locks
получены и освобождены,166pins/input/package неизменны. Один claim использован;
повтора нет, чужие процессы не останавливались. Embeddings/БД/HTTP не запускались.
Маски не размечались, модельные настройки и продуктовый код не менялись.

Приватный ignored archive189копий/4021961bytes, manifestSHA:
`8e2438970a54d9f9c576383e22237f5189f97949953c6baf5ba57b9320e76045`.
Путь: `artifacts/corpus-observability/low-load-800-executed-20261015-73ef43d1/`.
Копии сверены поSHA, каталоги700/файлы600; raw input не добавлен вGit.
Проверены runtime evidence, cleanup, pins/archive, ссылки и diff.
Unit suite не повторялся: код не менялся. Review не проводилось;
новых инженерных вопросов для книг нет. Установок/корпуса/publish/cutover/
изменениялимитов/commit/push/merge нет. Следующий ML-прогон не разрешён этой записью.
