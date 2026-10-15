# Межфазная остановка: диагноз и ограниченное ожидание

Дата:2026-10-15. Статус: FIX_VERIFIED / HISTORICAL_CAUSE_UNKNOWN.

Владелец разрешил разобраться в остановках и попробовать устранить проблему; действует общий пакетный допуск. STANDARD: критерии и продуктовые правила не меняются. Применены systematic-debugging/TDD/ponytail. Новое ожидание относится только к тестовому runner, не к поиску или бизнес-таймаутам.

## Разные остановки

| Событие | Что установлено |
|---|---|
| ADMISSION_LIMIT в controlled START | Намеренная остановка после localization checkpoint, необходимая для испытания RESUME; это не дефект |
| AssertionError между фазами первой кампании | R grant/host не создавались. В старом runner были разовый ps-predicate и SQLcheckpoint predicate; мгновенная причина не сохранена. Последующая серия с теми же условиями прошла. Точная историческая причинаUNKNOWN |
| Прежний RESOURCE_STOP на пяти фото | Mandatory observation failure; конкретная проверкаUNKNOWN, component RSS ceiling не исключён. Это отдельная история, не причина межфазного AssertionError |

## Воспроизведённая хрупкость runner

Одноразовый ps-predicate отказывает при наличии совпадающего процесса без ожидания его скорого штатного завершения. На собственных fake Python children воспроизводится отказ старого predicate, даже если процесс исчезает через доли секунды. Это подтверждает дефект устойчивости тестового orchestration; не доказывает, что он вызвал конкретный исторический отказ.

В tests/support/replenishment_probe.py добавлена read-only проверка с ограниченным ожиданием максимум5секунд: повторное чтение ps, подтверждённое отсутствие всех совпадений, либо PROCESS_TIMEOUT/OBSERVATION_FAILED. Сохранены прежние root/script predicates, отсутствуют сигналы/остановка/adoption чужих PID. Неизвестный снимок или отсутствие, подтверждённое после deadline, не открывает переход. Поля evidence: check/status/polls/elapsed/error_type и bounded PID/PGID/role кандидатов; argv/paths/error messages не пишутся.

При нативной проверке обнаружена дополнительная проблема нового parser: ps может выводить переносы строк внутри аргумента посторонней shell-команды. Она воспроизведена отдельным RED-тестом и исправлена: нерелевантные продолжения игнорируются только при наличии корректных process headers; непарсируемая релевантная строка и полностью недостоверный снимок по-прежнему отказывают. Ошибка чтения ps по короткому сроку также сохраняет запрет, а не ошибочно считается отсутствием.

Новые тесты: transient clearing, persistent candidate, command failure, malformed observation, already absent/other root, late absence, unrelated multiline command. Первые5тестов RED по отсутствию helper→GREEN; multiline отдельноRED→GREEN. Проверка late absence добавлена как регрессия уже реализованной deadline-проверки. Native probe использует только свои кратковременные fake children; не ML/DB.

## Подключение и реальная проверка

Runner получает структурированную причину межфазного отказа вместо безымянного assert. SQLcheckpoint проверка сохраняет expected/actual и отдельный CHECKPOINT_PRESERVATION_FAILED; в exception evidence сохраняется номер строки. SHA helper закрепляется в runner отдельно от81файла неизменного продуктового inventory.

Подготовлена свежая серия START `ed1201b195a5f489829113088be13d892777d4b8f0375c185093b814b8f21175`/RESUME `df1d5f37bcb72dc968f3ad052a737f1fd0d1eadd7443f16fe0203ce9968df30d`: один ранее успешный input,2+6admissions, shared ownDB/runtime/checkpoints,1200с/package и2520с/контур. Сначала stop-state и физическое завершение, затем RESUME без локализации, исходныеCP/filesSHA сохраняются, итог4CP/1pub. Model/semantic/limits прежние, profile bytes сохранены точно; оба code/input/metadata/noSDK refusal preflightPASS. Отдельного owner-вопроса нет по общему допуску.

После исполнения собственная БД/процессы/socket/секреты удаляются. Рабочий корпус/Web, лимиты и продуктовый код не меняются, commit/push/merge не выполняются. Результат этой пробы добавляется ниже; первоначальные неуспешные evidence не переписываются.

## Подтверждённый результат

57 релевантных тестов прошли, включая 7 новых сценариев. Первые пять дали RED по отсутствующему helper, затем GREEN; multiline отдельно RED→GREEN. Late absence проверена регрессионным тестом. Ruff и форматирование прошли.

Финальная native-выборка: 8 собственных fake children; 6 transient→QUIESCENT и 2 persistent→PROCESS_TIMEOUT. Все дети завершены и reaped. Старый one-shot predicate отказал бы во всех восьми случаях. Это воспроизведение механизма, а не восстановление исторического ps-снимка.

Промежуточный native запуск выявил multiline parser дефект. В другом отрицательном случае сама команда ps не уложилась в короткий срок: OBSERVATION_FAILED вместо ожидаемого PROCESS_TIMEOUT. Оба исхода правильно закрывают admission; ожидание пробы уточнено, helper ради него не ослаблялся. Подготовительные пробы не прибавлены к финальным восьми.

Реальная START/RESUME серия завершилась OK за 61,646 с. START штатно остановилась по ADMISSION_LIMIT: 1 localization checkpoint, 0 vectors/publications. Gate подтвердил QUIESCENT за 1 poll/0,029465 с, кандидатов не было. RESUME: 4 SQL-checkpoint, 10 регионов, 30 конечных unitnorm vectors размерностей512/768/768, 1 READY/publication/active. Исходный checkpoint и SHA файлов сохранены, локализация не повторялась. Host/viewer exits0 в обеих фазах.

В реальной серии процессы уже отсутствовали при первом наблюдении; ветка ожидания transient подтверждена native-пробами. 86 guard-наблюдений, все OK; MPSpeak4058890240/RSS1528856576 байт. Предыдущий resource failure не воспроизвёлся.

Независимая очистка: 0 собственных процессов/групп/test-контейнеров/socket/secret env/target descriptors; 2 grants consumed, временная БД удалена, private evidence сохранены. Product81code inventory unchanged; helper отдельно закреплён SHA в runner.

Исправлены воспроизведённая хрупкость разовой проверки и найденный дефект parser. Точная причина первого исторического AssertionError остаётся UNKNOWN, как и причина старого RESOURCE_STOP. Эти события не объявляются устранёнными задним числом. Review не проводилось; прежний501-тестовый suite не повторялся, поскольку продуктовый код не менялся.
