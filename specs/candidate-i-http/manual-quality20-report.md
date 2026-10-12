# Стенд для ручной проверки полного поиска на20 фото

2026-10-11. **MANUAL_TEST_UI_AVAILABLE; OWNER_SATISFIED_ON_CHECKED_EXAMPLES**.
[Owner scope/план](manual-quality20-plan.md),[методика](manual-validation.md).
Владелец выбрал полный поиск через UI, сначала качество, затем производительность.

## Каталог

Номера001–010/012–018/020–022 исходного списка100:20OK,112regions,336vectors.
Read-only SQL извлечение/20sourceSHA/112mask-crop artifact verification PASS.
20byte-identical privatecopies иZIP2179180bytes; исходный100/list/Sheetsmarkers,
674/G4 ипрежниеpartialbuilds сохранены. Sourcecategories:19nails/008temporarytattoos;
категории не подменялись. Query008 можно выполнить, бизнес-разметка вне категории
ногтей ограничена прежними правилами; его качественное замечание фиксируем отдельно.

Immutableprivate20snapshot2862874bytes; SHA256
`fe913d0ebc09c7245526a66e588a43fd15e0e5fefdbe4c84a71f7e3815c30b27`;
selectionSHA256 `64738ecced57b3585c0bb73fb11123e943b97b02d8ab7977a85fdd9e9eb13ae5`.
Новая test-onlyrepresentationfingerprint
`d7cd441469ab492f8f628e4dcc8eb09b56af632cbe719b0ee7eae0119c5858cb`.
ReadyCatalog вread-onlyport относится только кcomplete20, не кнезавершённым100.
SQLREADY/activepointer/publish не изменялись. Catalog rebuildingML не выполнялся.

## Реализация и проверка

`nail_manual20.py`:immutable validated20port; exactinputSHAallowlist/max20submittedphotos;
file-backedownerlabels сprivateatomicfsync/no-overwritecommit; scopedmanualpermission;
reuse NailSearchService/NailQueryRunner/create_app, без смены алгоритма.
`run_nail_manual20.py`:existing nativeproviders/I/lazySDK/runtimepins иindependent
ownedguardian;loopbackUI/one-shotclaim/exactpermission; no query injection/cachedanswer.
Пользовательский input действительно проходит I→embeddings→matching.

8expectedbehaviorRED→GREEN, затем2reviewdefectRED→GREEN.
13newmanualtests/30targetedPASS;final35safe suites396PASS46SKIP/2existingdependencywarnings;
Ruff3filesPASS. Actual safe suites не импортировали realSDK/DBprobes.

Первое independentreview:2Major (ignoredfalseRuntimeVerifier, non-atomicownerfile).
Обаисправлены:verifiedfactory STOPbeforebudget/ports/UI; atomictemp→fsync→nooverwrite
link→directoryfsync/cleanup. Mandatoryre-reviewPASS0C/0Major/0Minor;independent30tests
вacceptedbackendinterpreter. Initialreview wrongdocvenv22PASS2FAIL4ERROR/multipart
limitation сохранено какошибка средыreview, не новыйдефектпродукта и не установка.

## Actual model-free bootstrap

JobSHA256 `cde4b386da5b54a26058a6640c3d7bc23efd28018a907d06825899f579a9b694`;
84codepins/unchangedextractor7c0b1914.../sameSDKweightsprofile.
PreparedsourcearchiveSHA256
`f8d5da202ca8478a7fb0f3ce32c585cf3a50cdb3d1dbabc0d43edd6adebc90b2`.
Scopedprivateapprovedpermit MANUAL_QUERY_SESSION_NO_PUBLISH/exclusiveclaim.
Один manualwindow20submittedphotos/623admissions/3600s; maxregion/source/HTTP/pixel/
solver/resourceSTOP неизменны. Повторы/failedsubmittedrequests считают attempts;
foreignfiles не вызывают ML. Owner annotations пишутся толькоoutsideGit/privatefiles.

Actualcoldbootstrap: I metadata Torch/Transformersfalse,backendSDKfalse,reserved0,
pressure1/stopnull. LoopbackHTTP GET /health / /manual-test200;rootbadge20подтверждён.
NativeIABtab4 отобразил форму загрузки,Найти,candidates иссылку инструкции; agent
не загружал queryimages. Контроллер продолжает supervisedmanualsession, teardown
доownercompletion/STOP/timeexpiry ещё не наступил. Наличие UI неqualityPASS.

## Порядок проверки владельцем

ОткрытьloopbackUI вCodex → «Список фото и инструкция» → скачатьZIP/распаковать →
загружатьпоодному → смотретьнайденныйисходныйтовар/ранг/варианты → сохранятьоценки.
После owner оценки решаем, удовлетворяетликачествоипереходимкperformance.
Оценка точных каталожныхвходов не доказываетnewangles/full100generalization.
Необработанные78 невыдаютсякаккорректныйNEW; автоматическогоqualitypercentage нет.

Контроллер активен толькоодновремя60min, hardSTOP/timeexpiry неauto-restart.
T051поfull100 остаётсяоткрыт;SQLpublish/fullcorpusactivation/ownerqualityacceptance
не получены. Следующийgate — фактическаяручнаяоценка,производительностьотложена.

Finaldocslinks/status/conflicts/diff PASS;independentreportreviewPASS0Critical/0Major/0Minor.
Reviewer не использовалprivate/ML/SDK/DB/Docker и не изменялcode.


## Исправление новых запросных фото — 2026-10-11

OWNER_DECISION / VERIFIED: «Да» на исправление и новый ручной стенд. Exact query
allowlist удалён, catalog20 fingerprint и336vectors сохранены. Новые PNG/JPEG/WebP
проверяются до inner runner: фактический формат, single-frame,20MiB/2359296pixels;
SHA целостности передаётся в прежний runner. UI принимает WebP и объясняет ошибки.

Regression:3 формата сначала422/415RED→GREEN; независимый review0C/0Major/1Minor
(RESOURCE_LIMIT перехватывался как ValueError) исправлен с точным RED→GREEN.
62 safe testsPASS/2existingwarnings, RuffPASS. Без agentMLquery/catalog rebuild.
Старая own group остановлена, lateownlive0; старые query/label файлы сохранены.

Новый job SHA037fe4002b7a4681226010ce5df755d2148dd2799a7b67040832a030a0a2ed87,
84pins; archivef6b87b1c439030a0cc56009091410caab15ecb26d8c9fd0b02d6f8e54809d9b3.
Cold UIhttp://127.0.0.1:55892/; catalog20/112regions/336vectors/reserved0;
SDKfalse/pressure1/stopnull. В браузере подтверждён новый banner и форма.
Ownerwindow≤20submittedphotos/623admissions/3600s, expiry20:54Moscow;
старыеresourceSTOP/noautorestart сохраняются. OwnerqualityUNKNOWN, performanceотложен.


## Оценка владельца — 2026-10-11

Владелец сообщил «Ищет отлично» после открытия стенда новых запросных фото.
Это положительная оценка проверенных примеров, без установленного числа запросов
и полного coverage20/100. Formal labels/полнота UNKNOWN; T051 не закрывается.
Владелец возобновил анализ памяти и попросил варианты изменения системы:
[предложение](memory-efficiency-proposal.md). НовыйMLrun этим анализом не выполнялся.
