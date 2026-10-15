# После Grounding DINO освобождается кеш, но пик почти сохраняется

2026-10-15. **COMPLETED_ONE_PHOTO_CACHE_PROBE; PRODUCTION_POLICY_UNCHANGED**.
[План](gdino-cache-plan.md), [раздельная проба без очистки внутри predict](staged-resource-report.md).
Владелец согласовал продолжение исследования временных выделений/кеша.

## Основной результат

После каждого успешного Grounding DINO predict диагностическая обёртка
выполнила synchronize, затем empty_cache. На том же фото I снова вернул3области.
Все6PNG (3маски и3crops) побитово совпали с предыдущим staged I.

| Точка | MPS driver до → после, ГБ | Освободилось, bytes | MPS live до → после, ГБ |
|---|---:|---:|---:|
| synchronize послеpredict1 |3,830 →3,830|0|1,117 →1,117|
| empty_cache послеpredict1 |3,830 →1,648|2181693440|1,117 →1,117|
| synchronize послеpredict2 |3,937 →3,937|0|1,293 →1,293|
| empty_cache послеpredict2 |3,937 →2,781|1156841472|1,293 →1,293|

ГБ =10⁹bytes. Падение driver произошло именно на empty_cache, после
synchronize, при неизменном числе занятых живыми тензорами bytes в каждой паре.
Это подтверждает значительную освобождаемую часть выделений после операции,
а не только арифметическую разность двух разных счётчиков.

Сам пик почти не изменился:3945807872bytes в предыдущей staged пробе и
3937353728bytes сейчас — около3,94ГБ в обоих случаях.
Очистка после вызова не устраняет уже состоявшийся пик внутри этого вызова.
После первой очистки SAM predict поднял driver с1,648 до2,846ГБ, затем второй
GDINO predict — до3,937ГБ. Освобождённая память вновь выделяется для вычислений.
После завершенияlocalizer.photo driver2773008384bytes, live1292608256bytes.
Состав оставшихся выделений отдельно не установлен.

## Что означают показатели

Проверены docstrings фактически установленного PyTorch2.13.0,
`torch/mps/__init__.py`: current_allocated_memory учитывает память тензоров,
driver_allocated_memory включает кеш allocator и выделения MPS/MPSGraph;
empty_cache освобождает незанятый кеш, synchronize ожидает завершения kernels.

В этом эксперименте live остался точно1117496576bytes на первой очистке
и1292608768bytes на второй. Разница между итоговымdriver иlive не объявляется
полностью кешем или утечкой: API не даёт такого разложения.
Большое удержание памяти послеpredict само по себе не доказывает утечку.
Проба показывает освобождаемую часть, но не доказывает оптимальность
пиковых allocations внутри модели или безопасность меньшего memory limit.

## Замеры и ограничения

Одно фото, fresh I process, тот же frozen profile/model/config/preprocessing,
float32/MPS, без operator fallback. Только обёртка послеуспешного GDINO predict;
входы/параметры/возвращаемый объект predict не изменяются. Без HTTP/БД и encoders.
Проверка normal pressure1 на30с перед запуском; прежние RSS/MPS≤6GiB,
freshness5с/critical/deadline STOP, независимый watchdog, без автоматического retry.

Worker18,254с; контур с baseline и очисткой48,316с.
Localizer.photo11,704с. synchronize0,079/0,081с,
empty_cache0,126/0,113с; интервалы включают диагностические замеры.
Предыдущий staged worker16,889с — это описательное сравнение разных запусков,
не контролируемая оценка замедления от очистки.

53stage records/incompletefalse;34external samples:22normal1/12warning2,
critical4 не наблюдался. MPS driver max3937353728bytes,
live max1545985792bytes; RSS own group max1318207488bytes.
Периодические samples1с плюс границы, external≈0,5с: краткий пик мог быть пропущен.
Whole-host swapouts delta0; причинное снижение swap не доказано, поскольку
системная нагрузка между запусками отличается. Историческая причина criticalSTOP
по-прежнемуUNKNOWN.

## Проверка и завершение

Helper по TDD:1ожидаемыйRED/1PASS→2PASS, затем сdiagnostic suite30PASS.
Финальная копия сalias модуля recorder проверена отдельно2PASS доML;
это пересекающиеся проверки. Alias исправлен доfinalpackage/claim.

Final package SHA-256
`d3ddfefdcf5fbc1d0f064e9dd49211f307e406f5f5e0b3e268667acc51d2f190`.
Один fresh consumed claim, один запуск; intermediate prepared SHA до alias
не исполнялся. Frozen pins неизменны до/после, PNGparity6/6, no embeddings.
Workerexit0/stopnull; независимый0ownedPG/bothlockstrue/pressure1.

Private ignored archive34files SHAverified; manifest SHA-256
`161880586ccbe3e88e2cd75869d7ee4c9f559d51a4a45ca1dc99ba3c27282fab`.
Фото/маски/crops/claims/подробные runtime данные внеGit.
Product code и действующая cache policy не менялись: текущая probe не включает
очистку послекаждого GDINO predict в рабочую обработку. Для прежнего отдельного
empty_cache_after_photo сохраняется его существующая семантика.
Нет DB/HTTP/corpus/publication/install/foreigncleanup/commit/push/merge.
Review не проводилось (STANDARD), нового вопроса модульных границ для книг нет.
Ссылки/markers/fences/git diff --check проверены.
