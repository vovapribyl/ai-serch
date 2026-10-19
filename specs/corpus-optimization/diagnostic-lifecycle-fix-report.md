# Проверка диагностического журнала при штатном SIGTERM

2026-10-17. **MODEL_FREE_VERIFIED — SAVED_PROBE_REPLAY_PASS**. STANDARD.
Поручение «Приступай» после [отказа проверки реальной пробы](pre-sam-probe-execution-package.md#фактический-результат--2026-10-17).
Нового ML/БД/START нет. Продуктовый код и подписанный исторический пакет не менялись.

## Причина и исправление

Старый runner обязательным чтением `load-events.status.json` завершился
FileNotFoundError. Штатная остановка worker через SIGTERM/−15 не гарантирует
выполнение worker context manager/LoadDiagnostics.close, который пишет footer.
При этом контроллер независимо сохраняет ожидаемый worker exit и своё завершение.
Эта особенность уже предусмотрена существующим
[test_controller_records_exit_even_without_worker_footer](../../tests/test_replenishment_worker_binding.py).

Новая версия verifier хранится отдельно в ignored-папке
`artifacts/corpus-replenishment/diagnostic-lifecycle-fix-20261017/verify_diagnostics.py`.
Точка входа для будущего runner — `verify_probe_files(stage_root, operation_log_root)`.
Она проверяет файлы и связывает controller evidence с конкретным worker;
не следует заменять её прямым вызовом низкоуровневого parser с придуманным status.
В будущем пакете вместо чтения отсутствующего footer используется:

```python
result['sam_diagnostics'] = verify_probe_files(diagnostic_path.parent, folder)
```

Здесь folder — уже найденный controller-owned журнал текущего native START;
новый файл verifier и вызов должны получить новые pins/SHA. Израсходованный
runner не переподписывался, нового готового runtime-пакета в этой задаче нет.

## Обязательные доказательства

- Контроллер: свой финальный status, incomplete=false, rotations=0,
  events_attempted равен числу строк, непрерывная sequence от1. Журнал начинается
  host.before и заканчивается host.closed; есть host.after с cleanup_confirmed.
  Одна batch.before/after на2 фото с completed_photos=2 и COMPLETED.
- Идентичность: ready/control nonce совпадают, READY, localization/пустой model_key;
  PID ready совпадает с PID worker в заголовке load log и единственным
  localization exit контроллера. Все worker exits expected=true.
- Нет footer: допускается только ожидаемый exit−15/signal15. Возвращается
  source=CONTROLLER_EXPECTED_SIGTERM, worker_footer=MISSING,
  worker_final_status=UNKNOWN. Итоговое состояние worker recorder не выдумывается.
- Footer есть: incomplete/rotation/history_truncated проверяются; controller
  evidence всё равно обязательно. Чистый exit0 допустим с настоящим footer.
  Неполный footer не игнорируется ради fallback.
- События: worker.before в начале файла, все measurement_ok, два завершённых
  фото; SAM metadata known=true/counts совпадают, полные pre-cache→SAM→post-cache
  границы с правильными call IDs. Пропуск, перестановка, UNKNOWN и error — отказ.
- Файлы: только приватные обычные файлы владельца, без symlink/hardlink,
  bounded read до1MiB для JSONL, полная последняя строка. Ротационные файлы,
  повреждённый JSON/последовательность, отсутствие status контроллера — отказ.

Это подтверждает полноту обязательных событий конкретной двухфотографической
пробы и выход её worker. Это не сертификат отсутствия любой потерянной
периодической метрики: финальное состояние worker recorder без footer остаётся
UNKNOWN. Ресурсные guards, native completion и cleanup по-прежнему проверяются
отдельно; verifier не отменяет RESOURCE_STOP и не решает готовность корпуса.

## Проверки

RED: старая обязательная загрузка footer воспроизвела FileNotFoundError,
включая настоящий owned child process после SIGTERM;15 FAIL/1 PASS.
GREEN: новая проверка и отказные варианты прошли. Всего94 PASS/0 FAIL/ERROR/SKIP:
новый lifecycle verifier, прежние diagnostic cases, worker binding,
SAM diagnostics/load diagnostics. Полный suite не запускался: продуктовый код
не менялся, SQL/runtime fixtures с моделями вне scope.

Настоящий lifecycle test использует ProcessStageWorkers/Supervisor/OperationLog
и настоящий LoadDiagnostics в дочернем процессе с shape-only SAM callback.
Два вызова фото записывают события, затем worker ожидает; контроллер штатно
завершает его SIGTERM, подтверждает физический выход и пишет final log.
Footer действительно отсутствует, новая проверка проходит, файл не создаётся
задним числом. Torch/модели/сеть/БД этому тесту не нужны.

Отказы проверены для unexpected/SIGKILL/неверного PID/nonce, дубликата exit,
нарушенной sequence, incomplete/rotation/отсутствующего controller status,
truncated JSONL, пропуска события/заголовка worker, неполного footer,
exit0 без footer и небезопасных файлов. Валидный настоящий footer проверен
с ожидаемым−15 и чистым0.

Read-only replay на сохранённых файлах реальной пробы PASS:15/37 боксов,
2 pre-SAM и2 post-photo очистки; completion от контроллера, footer MISSING,
worker_final_status UNKNOWN. **Исторический runner остаётся FAILED**.
Это новый offline-результат проверки evidence, а не повтор обработки фото,
не изменение исходов и не доказательство причинного эффекта памяти.

Evidence в папке исправления: tests.xml, verification.json, replay.json и tests.
Signed c6d38648/runner/старый verifier,903 preserved files и исходные logs
проверены без изменения. Приватные файлы700/600; сырые фото/ID не публикуются.
Самопроверка; независимое review не проводилось (STANDARD).

## Следующая точка

Подготовить отдельный конкретный пакет на23 незавершённых входа с новой
точкой входа verifier, соответствующим числу входов контролем событий,
свежими code/runtime/input pins и прежними guards/caps. Текущий verifier
строго рассчитан на двухфотографическую пробу: число23 нельзя молча передать
в её условия. Нового runtime-допуска, повторного ML или commit/push нет.

Уточнение 2026-10-17: [пакет23](remaining23-execution-package.md) подготовлен
с явным числом входов3/5 и допустимым отсутствием SAM только для NO_NAILS.
Новый код verifier закреплён SHA; runtime не запущен, historical files не изменены.

Уточнение исполнения 2026-10-17: [серия23](remaining23-execution-package.md#фактический-результат--2026-10-17)
завершилась runner/postflight PASS; variable verifier подтвердил5 controller-owned
SIGTERM без worker footer с сохранением final status UNKNOWN.17 ready/6 deferred,
0 PENDING. Это runtime evidence новой проверки, не переписывание старого FAILED.
