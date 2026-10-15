# Одно фото: STOP по давлению памяти сохранён в итоговой сводке

2026-10-15. **EXECUTED / STOPPED_PRESSURE_CRITICAL**.
[Условия пакета](one-photo-observability-proposal.md),
[доработка диагностики](stop-observability-report.md).
Владелец отдельно разрешил один запуск сообщением «разрешаю» после предъявления
конкретного пакета. Его SHA-256:
`3e7ef09a9717bf846428037dcf2233a0f978f82e972b8c4782fc217d09660889`.
Разрешение использовано; повтор не выполнялся и не разрешён этой записью.

## Результат

До запуска сверены94pins, SHA фото/пакета, interpreter и приватные права.
Подтверждено отсутствие других соответствующих Python probe-процессов.
Перед выдачей approval создан отсутствовавший приватный runtime-каталог700;
код и package bytes не менялись. Это подготовка каталога, не исправление ML.

Baseline:56измерений pressure1,30,239с от первого до последнего. Затем один
fresh I-worker был остановлен watchdog через10,548с. Полный контур40,869с.
Сохранённый итог:

```json
{
  "status": "STOPPED",
  "exit_code": -9,
  "stop_reason": "PRESSURE_CRITICAL",
  "termination_action": "SIGKILL_OWNED_GROUP"
}
```

Последнее событие операции — `gdino.predict / before`, первый вызов;
соответствующего `after` нет. Перед этим завершились identity/import,
загрузка SAM и Grounding DINO. Нет `photo-result.json`, поэтому успешной
локализации, областей и результата поиска эта проба не дала.

## Что сохранила диагностика

| Наблюдение | Значение |
|---|---|
| Host trace |20samples:12normal1,7warning2,1critical4 |
| STOP sample: RSS I-группы |774668288bytes |
| STOP sample: RSS controller |20250624bytes |
| STOP sample: MPS driver, последнее доступное worker-измерение |2733522944bytes |
| Наблюдавшийся максимум RSS I-группы |989413376bytes |
| Наблюдавшийся максимум MPS driver |2733522944bytes, около2,73ГБ |
| Наблюдавшийся максимум MPS live |1179216384bytes |
| Whole-host swapouts delta в STOP sample |85576страниц; не расход памяти конкретной модели |
| Worker stage log |22записи,12631bytes, все measurement_ok=true |
| Host trace / baseline log |5897 /17895bytes |

RSS/MPS не складываются. Наблюдавшиеся значения ниже потолков; превышение
RSS/MPS лимитов в сохранённых измерениях не зарегистрировано. Guard остановил
пробу по pressure4. MPS в STOP sample получен из последней доступной worker
записи, а не измерен одновременно с host pressure4. Короткие пики между
измерениями могли быть пропущены.

У worker нет финального `stages.status.json` и footer: watchdog отправил
SIGKILL. Поэтому полнота всей worker-истории UNKNOWN, хотя22сохранившиеся
записи читаются и имеют measurement_ok=true. Отсутствие footer не скрывает
код/причину/действие внешнего watchdog. Итоговые сведения записал controller.

Это подтверждает работу новой передачи первичного кода при реальном STOP:
он не заменён общим `RESOURCE_OBSERVATION_ERROR`. Проба воспроизвела critical
pressure в окне первого GDINO predict. Она не доказывает, что только этот
вызов, модель или приложение вызвали системное давление. Точную причину
исторических STOP задним числом не устанавливаем. Накладные расходы нового
логирования на ML и качество поиска остаются UNKNOWN.

## Независимая проверка завершения

После выхода controller отдельная OS-проверка подтвердила0PID controller/worker
и0процессов worker PGID. Оба собственных locks заново получены и освобождены.
94pins, SHA input/package неизменны. Claim присутствует и использован.
Чужие процессы не останавливались; DB/container/HTTP/embeddings не запускались.

Приватный архив113копий файлов,2084242bytes: runtime evidence и frozen sources,
проверенные по manifest. Каталог700, файлы600, Git ignore подтверждён.
Путь: `artifacts/corpus-observability/one-photo-20261015-3e7ef09a/`.
Manifest SHA-256:
`d73e341785ee0e56c9987e1af26e4e9035b9e9ef6968081c8dbb55c26fd77ab0`.
Модельные веса не копировались. Исходные журналы не исправлялись задним числом.

## Проверка и границы

Продуктовый код и тесты в этой задаче не менялись; unit-регрессия повторно
не запускалась. Выполнены проверки результата/чисел, pins/SHA, процесса/группы,
locks, размера/читаемости файлов, archive manifest, ссылок и diff.
Независимое review не проводилось (STANDARD).

Холодный I-only runner проверяет worker diagnostics/watchdog; production
`RecordingResourceObserver` и терминальный монитор пополнения он не использует.
Их реальная связка с БД этой пробой не проверена.

Следующее обсуждение — отдельная сравнительная проба меньшего входа Grounding
DINO processor с проверкой памяти и локализации по
[ранее предложенным вариантам](../corpus-optimization/resource-architecture-options.md).
Изменение параметра и новый ML-запуск здесь не выполнялись. Рабочий корпус,
публикация/cutover, лимиты, зависимости, commit/push/merge не менялись.
