# Исправление WARNING и пакет на оставшиеся45 фото

2026-10-17. **CONSUMED — FAILED / RESOURCE_STOP в N05**. Владелец
разрешил SHA всей серии9×5. Runner запущен один раз;5 START, четыре фазы
прошли внешнюю проверку, пятая остановлена native guard по MPS_LIMIT.
16 фото готовы,6 отложены,3 PENDING; следующие20 не запускались.
Архив сохранён, postflight/cleanup PASS. Пакет израсходован, повтор запрещён.
Маршрут STANDARD: исполнение конечного эксперимента без нового решения о приёмке.

## Что исправлено

[Предыдущая серия70](remaining70-execution-package.md#фактический-результат--2026-10-17)
остановилась после25 фото:22 готовы,3 deferred REGION_COUNT_LIMIT,
45 не запускались. N05 native OK/COMPLETED, но внешний all-OK assertion
отказал из-за четырёх WARNING pressure=2. Причина давления памяти UNKNOWN.
Старый подписанный runner и сохранённый FAILED не изменены.

В новом runner фазу можно принять, только если команда OK/COMPLETED,
журнал наблюдений непустой, все статусы OK либо WARNING, последний статус
OK и давление на границе следующей фазы normal=1. Отказы native-команды,
STOP в любой позиции, неизвестные статусы, пустой журнал или финальный
WARNING блокируют серию. Проверки host/monitor exits, журналов, данных,
checkpoints и сохранности прежнего префикса обязательны отдельно.
RESOURCE_GUARD и CAMPAIGN_DEADLINE теперь сохраняются точными error codes.

Действующая native-политика не меняется:
`ResourceWait` в `src/product_search/search/corpus_replenishment.py` блокирует
admission при WARNING и требует30 секунд последовательных свежих OK;
окно ожидания300 секунд, deadline и cleanup имеют прежний приоритет.
MacResourceObserver сохраняет freshness/RSS/MPS/pressure STOP и latched stop.
Новый внешний критерий не заменяет native-ожидание своим счётчиком.
Исправлена только private-обвязка эксперимента; код продукта не менялся.

## Один SHA на девять партий

`b08f7398430c06d2344094f5a0e595e6e92ddc880a4703a3e26bf5dd499f1224`

| Граница | Подготовленный пакет |
|---|---|
| Вход | Только45 frozen inputs прежних B08–B16 / N06–N14; новая серия N01–N09 по5. Все ранее обработанные20/B01/B02 и25 из серии70 исключены по SHA |
| Идентичность |45 разных SHA; size/decode/headers проверены, исходные product/photo ID сохранены в private mapping. Runtime product IDs новой собственной БД не подменяют исходные ID |
| Разрешение | Один SHA на все9 START, до24 admissions на фазу/216 на серию; без повторного approval каждой пятёрки. Approval получен на всю серию |
| Время | Прежний общий предел:3600с обработки+30с очистки, всего3630с; внутренняя фаза1200с с резервом30с и в пределах общего срока. Это верхняя граница, не прогноз |
| Модели / ресурсы | Прежние pinned локализатор и последовательные OpenCLIP/DINOv2/SigLIP2. RSS I6GiB/encoder5GiB, MPS6GiB; freshness/wait/STOP прежние |
| SQL | Одна новая собственная временная БД, pinned image; tmpfs256MiB/контейнер512MiB, прежние CPU/PID limits. Рабочая БД не используется |
| Исходы | OK — полный результат; NO_NAILS — без embeddings; ERROR допустим только сохранённый REGION_COUNT_LIMIT. Другие ошибки/PENDING/неполнота останавливают серию |
| Экспорт | Накопленный prefix export после каждой фазы, reader40MiB, cumulative deferred list2MiB; receipts/source mapping сохранены. Запись/дубликат/экспорт с ошибкой блокируют продолжение |
| Сохранность |542 прежних файла закреплены SHA, включая checkpoints, экспорты и списки серии70. Перед следующей фазой и после неё проверяются SQL checkpoints/members/vector hashes, files и SHA предыдущего экспорта |
| Отказ | Первый непредусмотренный error, STOP, невосстановившийся WARNING, нарушение сохранности, deadline, журнал или cleanup прекращает серию; retries и повышение лимитов исключены |
| Архив / cleanup | Prefix exports/lists/mapping/logs/checkpoints с fsync до удаления собственной БД; credentials/targets/grants не входят в архив. Partial export при отказе, если доступен SQL |
| Вне пакета | Повтор обработанных фото, восстановление раннего потерянного SQL, общий каталог, поисковые запросы/качество, формулы/маски, рабочий cutover, commit/push/merge |

Экспорты прежних20,5,22 готовых и будущей серии45 остаются отдельными.
45 входов не означают45 готовых: deferred/NO_NAILS/не начатые учитываются
отдельно. При первом отказе остаток не продолжается по старому разрешению.

## Проверки подготовки

- RED: семь отказов/восемь проходов на старом runner; в том числе сохранённая
  N05 воспроизвела ошибочный отказ на восстановившемся WARNING и потерю
  точного RESOURCE_GUARD. Часть RED-проверок дополнительно закрепляет
  самостоятельный отказ resource predicate при неуспешной native-команде;
  в старом runner её уже блокировала отдельная проверка COMMAND_NOT_OK.
- GREEN:15 проверок нового guard/error mapping, включая реальные наблюдения
  N05, recovered/all-OK, STOP с последующим OK, UNKNOWN/STALE/CRITICAL,
  пустой журнал, финальный WARNING, RESOURCE_STOP/WAIT_TIMEOUT/неполный ответ.
- Всего89 выбранных model-free тестов PASS: guard, накопленный verifier,
  native ResourceWait, MacResourceObserver/latched STOP и export reader.
  Полный suite и реальные SQL/ML не запускались — изменена private-обвязка.
- Девять последовательных SQLite-prefix exports в памяти PASS; тестовые
  итоги27 ready/9 NO_NAILS/9 deferred — fixture, не реальный результат45.
  Проверены исходные receipts, сохранность старого префикса и отказ повреждений.
  Условие журналов проверено отдельно для mixed/all-ready/no-ready фаз,
  текущие счётчики фазы не смешаны с накопленными.
- Все9 DTO/packages,88 code pins, frozen inputs, модели/metadata assembly
  и3 encoder manifests/files PASS без SDK/server. Frozen input bytes24 577 968.
  Live readiness NOT_RUN; проверяется после разрешения до создания БД.
- Runner без campaign approval отказывает до preflight/runtime/credentials/
  grants/START. Прежние542 файла и старый campaign SHA/runner не изменились.
  Самопроверка; независимое review не проводилось (STANDARD).

Приватные scripts/tests, inputs, manifests, frozen source и evidence:
`artifacts/corpus-replenishment/remaining45-preparation-20261017/` (ignored).
`prepared-summary.json` указывает локальный runtime root; `prepared/` хранит
копию пакета, `verification.json` и `test-results.json` — агрегаты проверок.
Сырые ID и изображения не публикуются. Пакет привязан к локальному окружению;
наличие копии не является разрешением.

## Фактический результат — 2026-10-17

Live preflight PASS: pressure1, конкурирующих ML/probe-контейнеров нет,
входы/код/модели сверены. Разрешение «Разрешаю» сохранено на SHA выше.
Один запуск,5 START, без retries и изменения подписанного runner/caps.

| Фаза | Готовы | Отложены | PENDING | Проверка |
|---|---|---|---|---|
| N01 |4|1|0| PASS |
| N02 |3|2|0| PASS |
| N03 |4|1|0| PASS |
| N04 |5|0|0| PASS |
| N05 |0|2|3| Native STOPPED / RESOURCE_STOP; partial export сохранён |
| N06–N09 | — | — | — | Не запускались:20 входов |

В частичном экспорте25 записей:16 OK,6 ERROR только REGION_COUNT_LIMIT,
3 PENDING,0 NO_NAILS/других photo errors. Терминальных исходов22;
незавершённых входов23 =3 PENDING +20 из не начатых фаз.25 записей экспорта
не означают25 обработанных фото. PENDING не имеют regions/vectors/checkpoints.
Готовые16:105 областей/315 векторов, по105 каждой модели;
64 checkpoints/322 файла. Экспорт N05 —2 732 564 bytes.

Первые четыре полных prefix exports проверены прежним verifier. Для N05
проверены идентичность всех исходов, source-linked receipts всех6 deferred,
полнота терминального поднабора22 и отсутствие данных у PENDING.
Все пять префиксов сохранили предыдущие photos/outcomes/regions/vectors/profile;
SHA архивных экспортов совпали. Неполный N05 не объявлен завершённой партией.

### Подтверждённая причина STOP

Первый `resource-stop.json`: stage localization, check RESOURCE_LIMITS,
reason MPS_LIMIT, sample_current=true. MPS6 487 310 336 bytes при
ceiling6 442 450 944 bytes (6GiB), превышение44 859 392 bytes (~42,8MiB).
RSS того же sample878 755 840 bytes, pressure2. Это превышение MPS cap,
а не отказ внешнего критерия на восстановившийся WARNING.
Причина роста памяти, OOM и связь с конкретной модельной ошибкой — UNKNOWN.
Показатели RSS и MPS не складываются.

Native-команда сохранила STOPPED / RESOURCE_STOP. Guards:736 OK,2 STOP,
0 WARNING; второй STOP сохраняет первую причину. Peak RSS1 523 204 096 bytes,
peak MPS6 487 310 336 bytes. Время358,397с (~5мин58с).

Outer runner сохранил FAILED / ReplenishmentError / UNCLASSIFIED_RUNNER_ERROR:
после сохранения экспорта `batch_summary` отказал PHOTO_NOT_DEFERRED из-за
3 PENDING, что воспроизведено read-only. Поэтому точную ресурсную причину
нужно брать из native answer и первого resource-stop, а не общего outer code.
Это оставшееся ограничение диагностики; подписанный runner и исторический
результат не менялись. Правильность native STOP не ставится под сомнение.
Восстановившихся WARNING в этой серии не было; новый критерий по-прежнему
проверен model-free/replay, не этим runtime-сценарием.

### Сохранность и очистка

Экспорты/lists/mapping/logs/checkpoints архивированы с fsync до удаления своей БД.
Postflight PASS: собственных контейнеров/процессов нет, locks свободны,
credentials/targets удалены, pressure после1. Прежние542 файла сохранили SHA.
`terminal-audit.json` дополнительно подтверждает терминальный поднабор,
23 незавершённых входа, source identities и отсутствие новых START.
Приватные evidence/scripts — в папке подготовки выше.

Прежние экспорты20/5/22 готовых и новые16 остаются отдельными. Общий каталог
не собирался, качество поиска не измерялось, рабочий cutover/commit/push отсутствуют.
Полный suite не повторялся: runtime исполнял замороженный код и runner;
проведены проверки фактических данных, причины STOP и cleanup.

## Точка продолжения

Сначала ограниченная диагностика роста MPS по сохранённым данным и уточнение
outer error code для неполного экспорта. Лимиты не повышать автоматически,
OOM/причину модели не объявлять без evidence. После диагностики — отдельный
конкретный пакет на23 незавершённых входа с сохранением уже готовых результатов.
Текущее разрешение израсходовано; новых retries/START/рабочей активации нет.

Уточнение 2026-10-17: [диагностика по сохранённым traces](mps-stop-diagnostics.md)
завершена без ML. Обе очистки N05 выполнены; STOP записан до очистки второго
фото около SAM. Driver позже снизился, latched STOP сохранён; утечка/OOM и
точный фактор размера пика не установлены. Ни одного нового START не было.
