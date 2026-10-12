# Повторный build100 после закрытия приложений

2026-10-11. **BUILD_INCOMPLETE: 6 OK, 94 PENDING.**
Владелец разрешил новую попытку и сообщил, что закрыл сторонние приложения, кроме
Codex. [План](build-retry-plan.md): те же100фото,3103admissions,3600s и прежние
RSS/storage/HTTP/freshness/STOPограничения; без публикации. Состояние приложений —
сообщение владельца, а не доказанная причина изменения результата.

## Выполнение и результаты

Перед запуском macOSpressure1, физическая память16GiB. Freshjob с новымrepresentation
и100новыми runtimecatalogphotoUUID; sourceRefs/records/ordinals/imageSHA/list001–100
сохранены. Прежняя [сборка](build-report.md) BUILDING/PENDING100 не перезаписана.
Новый model-freepreflight exit0/5.053s:100decode/target/runtime/parenthash/readiness,
noSDK. Затем один approvedpermit/claim и один supervisedexecute.

| Показатель | Наблюдение |
|---|---|
| Завершённые фото |6 OK;94 PENDING;NO_NAILS0/ERROR0 |
| Сохранённые результаты |31regions/93vectors в ownedtarget, то есть3vectors наregion |
| Состояние индекса |BUILDING, неREADY;activepointer0;не опубликован |
| STOP |RESOURCE_OBSERVATION_ERROR;terminalsample=null;точный тип исключения в старом trace UNKNOWN |
| Время / выход |55.112s;controllerexit3/ownedworkerexit-9 |
| Admissions |133reservedиз3103;reservation не означает успешно завершённыйcall |
| Замеры ресурсов |262events;validsamplespressure1/2, без наблюдавшегосяcritical4;Ipeak1399357440/backend993214464bytes |
| Наблюдавшееся storage |DB+artifactmax10568395bytes; последнийвалидйрованныйinterval≤0.319s;не считать это данными failedsample |
| Окончание |Finalworkerresult и I-specificexit UNKNOWN после forcedgroupkill |
| Postchecks |Ownedgroup0/live0;обеleases reacquired;pressure1;6OK/94PENDING/31regions93vectors/pointer0 сохранены |

Результат доказывает работу полной вычислительной цепочки на шести входах в этом
окне, но не качество выдачи или пригодность всех100. Незавершённый индекс не подключён
кручному тесту. Шестиминутная/часовая экстраполяция по этим данным не выполнялась.
Первая неудачная сборка, все входы и Googleотметки100строк сохранены. Повторное окно
израсходовано; третьего MLзапуска вэтойзадаче не было.

## Проверка отказа наблюдателя без моделей

HostStorageObserver перечислял файлы черезrglob и затем делалlstat. ImageStore
сохраняет/переименовывает временныеmanifestфайлы. На искусственных файлах воспроизведён
случай, когда перечисленная запись исчезает доlstat и корректный storage sample
превращается вFileNotFoundError/mandatoryobservationSTOP. Во время остановленного
run имелись временные файлы; точное исключение там не записано. Связь воспроизведённой
гонки с конкретным55sSTOP остаётся гипотезой, а не доказанным postmortem.

[Исправление](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_build_composition.py):
пропускается только путь отдельной записи, отсутствующий к моментуlstat;
storage остаётся sampledestimate, а не атомарным filesystem snapshot. Приrename
байты могут оставаться подновымименем; следующиеsamples проверяют текущиеentries;
rootdev/inode/UID повторно проверяются. Исчезновение/замена root,permission/symlink/
прочие ошибки остаются terminal. Пороги и freshness не увеличены. Trace сохраняет
error_class без приватного текста исключения; resource details больше не затираются
общим событием ошибки. MLcore/models/SDK/точность/batching не менялись.

[Тесты](../../../../../.codex/worktrees/candidate-i-http/Ai/tests/test_nail_build_composition.py):
2observedRED→GREEN (transientrace и потеряerrorclass),2negativecharacterization
(permission/rootremoval) сохраняютSTOP.52targetedPASS;final34safe suites369PASS/
46SKIP/2dependencywarnings. Nativeinference и fullprojectsuite не повторялись.
Code reviewPASS0Critical/0Major/0Minor, independently52safe tests;reviewer private/
source/DB/Docker/SDK не использовал.

## Снимки и подготовленная следующая попытка

До изменения кода сохранён archiveточного82filesource иactualrun evidence:
`3d3d464206e3efe86af151980c3404faf2c516d0ea4117fd8673b930646eef7e`.
ConsumedjobSHA: `dbec418f4d654263843574262d92631b002d483d84d6154628b5c65e5d80e75c`.

После исправления подготовлен отдельныйfreshpackage без approvedpermit:

- JobSHA: `3565030645e2fc2d284feb44d4a377450fef9f3924cc1d9ca98df89f2614911e`.
- CanonicalinventorySHA: `c39ee39b38dddaec2bc58a999712fb91e83c131b1d6804823e94a09118c14762`.
- Representationfingerprint: `36fc821adfc03fae932ed432b56a68ade96e106001e5c7bf74e5c0afb351c58c`.
- PreparedsourcearchiveSHA: `e8b5b0303893ad78fa2d37a132f70519757901fe32d98bfcfac4370aa5dc48a0`.

Те же100inputs/list, новые runtimephoto/representationIDs;partialbuilds не удалять
и неresume. Model-freecheck новогоjobexit0/4.982s:100decoded, noSDK/reserved0,
NOT_CREATED/0regionsvectorspointers,ownedIexit-15/backend0/leasesPASS. Private700/600,
фото/веса/векторы/полныеIDs/paths не опубликованы. Прежниеjob/codearchives сохранены.

Предложение следующего окна: одинfresh100build≤3103/3600s с темижеSTOP/no-publish
bounds. Требуется новый явный owner допуск после review;approvedpermit отсутствует,
execution.claim отсутствует. T051 `[ ]`, T052coverage иmanualqueries/READY закрыты.
Исследованиеускорения остаётсявbacklog доownerпроверкикачества.

Finalread-onlyreview0Critical/0Major/1Minor: уточнено, что отсутствие пути не доказывает
освобождениябайтов. Исправлено, selfchecklinks/status/diffPASS;1reviewfixcycle. Проверки links/markers/
diff и безопасных counters выполнены;actualprivate evidence reviewer не воспроизводит.
