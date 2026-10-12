# Диагностика остановки на фото №019

2026-10-11. **STOP: LOCALIZATION_STOP / RESOURCE_ERROR.**
Владелец разрешил одну диагностическую обработку фото №019. Окно использовано;
новых ML-запусков этот отчёт не разрешает. [План-контракт](photo019-diagnostic-plan.md).

## Измеренный результат

| Показатель | Результат |
|---|---|
| Job SHA256 | `3a51c9bf3a4615386e4e76100454e817c70764d83d029632ab7071fccb431c71` |
| Scope | Один неизменённый вход №019; ≤34 admissions / 360 s, без публикации |
| Preflight | model-free check: exit0, 4,452 s, без SDK/DB writes; один вход |
| Execute | 16,82 s; controller3 / worker3; reserved1 |
| Безопасная причина | `BuildStop: LOCALIZATION_STOP`, `NailProcessingError: RESOURCE_ERROR` |
| Результат в отдельном target | BUILDING; PENDING1; regions0 / vectors0 / active pointer0 |
| Наблюдатель | observation_stop=null, guardian stop_reason=null; 81 валидный sample, pressure1 |
| Выборочные RSS peaks | I: 1306378240 bytes; backend: 62767104 bytes |
| Завершение | I exit−15; независимый post-check: owned live0, оба lease повторно доступны |
| Сохранение | Все 82 code pins совпали; закрытый архив SHA256 `3f391e44e6e35d2ff5c243483479c3499dc964ddca3a935abe3cc2cd1fcce54c` |

`worker_result=UNKNOWN` в итоговом controller JSON: worker завершился через exception,
а безопасные reason/cause_type/cause_code сохранены отдельно в worker log. Код причины
прочитан из этого STOP-сообщения, а не восстановлен из общего названия остановки.

## Что подтверждено и что остаётся гипотезой

**Подтверждено:** фото №019 воспроизводит отказ локализации с кодом `RESOURCE_ERROR`.
В этой пробе не сработали наблюдатель и ресурсный guardian; давление памяти оставалось
normal. Эти данные не объясняют прежний critical-pressure STOP первой попытки.

**Наиболее вероятно:** локализатор вернул более 10 областей. В
`src/product_search/infrastructure/nail_wire.py`, `encode_result()` проверка
`len(result.regions) > limits.max_region_count` возвращает именно `RESOURCE_ERROR`.
Принятый лимит — 10. Количество найденных областей не сохранено: **UNKNOWN**.

Другие ветви этого кода проверены статически:

- `encode_result()` также возвращает `RESOURCE_ERROR` при JSON >40 MiB. Фото019 имеет
  246×328 pixels. Оценка десяти L8 PNG masks с base64 и запасом — около1,1 MiB;
  labels GroundingDINO получаются декодированием токенов короткого frozen prompt.
  Это делает превышение40 MiB маловероятным; фактический размер ответа не измерен.
- `services/candidate_i/app.py` выдаёт тот же код при ValueError создания/захвата
  device lease. Лог содержит предупреждение Torch, а RSS I достигает около1,3 GB:
  модель, вероятно, уже начала работу после захвата lease. Post-check lease успешен.
  Точная сработавшая серверная ветвь в текущем логе отсутствует.

Статический SDK-разбор выполнен чтением файлов LangSAM/GroundingDINO/Transformers,
без импорта Torch и без дополнительных вызовов модели. Он не является измерением
содержимого отклонённого результата.

## Последствие и следующий шаг

Сборка прекращает весь проход при таком отказе; фото019 остаётся PENDING.
Полный предыдущий проход сохранил17OK/1NO_NAILS/82PENDING,84 regions/252 vectors.
T051 открыт, полного индекса100 и результата пользовательского quality test нет.

Следующий минимальный шаг — подготовить безопасную серверную диагностику точной
ветви (`region_count` / `response_bytes` / `lease`) без масок, фото и приватных данных.
Её реализация и ещё один ML-прогон не выполнены в этом окне. Повышение лимита,
усечение результата, исключение фото и новый полный проход требуют отдельного
решения; ускорение остаётся в backlog до проверки качества.

Код, модель, SDK, лимиты, выбранные100, пользовательский список и отметки Google
Sheets не изменены. Старые partial builds сохранены. Queries/READY/publish отсутствуют.

## Проверка

Read-only post-check SQL агрегатов/process group/leases выполнен; ссылки, статусы и
`git diff --check` проверены: семь файлов, broken local links0 / conflict markers0. Нового программного изменения нет,
поэтому повторный suite372PASS/46SKIP не запускался; это историческая проверка
предыдущей правки безопасного логирования. Независимое read-only review: PASS,0 Critical /0 Major /0 Minor; reviewer не читал
private artifacts и не выполнял SDK/ML/DB/Docker/tests.

## Последующее уточнение,2026-10-11

В новом separately-approved [skip-photo проходе100](skip-photo-build-report.md)
с раздельными server codes фото019 вернуло REGION_COUNT_LIMIT. Превышение10regions
теперь подтверждено этим новым evidence; exact region_count остаётсяUNKNOWN.
Историческое исходное диагностическое окно не повторялось и сохраняет прежний
уровень доказательности.
