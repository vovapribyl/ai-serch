# T051 — один разрешённый build100: остановка по памяти

2026-10-11. **STOP_RESOURCE_CRITICAL / BUILD_INCOMPLETE**.
Owner «Разрешаю» на одинrealMLrun100вownedisolatedDB, max60min/3103admissions,
соsameSTOPlimits, безpublish/READY/activation. [Контракт](build-run-plan.md),
[prepared100package](corpus-100-report.md). Разрешённое окно использовано один раз;
unusedbudget не даётновойпопытки. Повтор/resume/restart не выполнялись. T051 `[ ]`.

## Результат

| Показатель | Фактический результат |
|---|---|
| Execution |Controllerexit3; ownedworkerexit-9; watchdogelapsed26.610s |
| ОсновноеусловиеSTOP |Валидныйsystem sample: macOSpressure4, gate RESOURCE_CEILING |
| Watchdoglabel |RESOURCE_OBSERVATION_ERROR: genericguardian принял forwarded resource_observation_error event с reasonRESOURCE_CEILING; не подменять этимlabel причину pressure4 |
| Representation |Одна BUILDING, неREADY; данные сохранены |
| Outcomes |OK0/NO_NAILS0/ERROR0/PENDING100; завершённыхфото0из100 |
| Derivedresults |Regions0/vectors0/artifactpayload0; usableindex не получен |
| Admissions |Reserved2из3103 передcall, не счётчик успешно завершённыхmodeloperations |
| Publication |Activepointercount0; READY/publish/query/Webactivation не выполнялись |
| Worker/I final |Finalworkerresult и I-specificexitcode UNKNOWN послеforcedgroupkill |
| PostSTOPcleanup |Ownedprocessgroupmembers0/non-zombie0; device/coordinator leasesreacquired; hostpressureпослеexit1 |

PENDING означаетнезавершённуюобработку, неNO_NAILS/плохоекачество/исключение100товаров.
Coverage и качество поиска не оценены. Нельзя запускатьownermanualtest безготовогоиндекса.
Ни100фото, ниGoogleотметкивыбранныхстрок не менялись; рабочая/sourceGate2DB не использовались.

## Проверка и resourceevidence

Передpermit/run actual model-freepreflightexit0/5.836s:100decoded, exactjob/code/input/
parent/runtime/targetchecks, Iready/POST403, noSDK/reserved0/representationNOT_CREATED.
Private600approvedpermit привязан кjobSHA/expiry3600s; root700/exclusiveclaim/workerconsume.
Execution выполнен один раз штатнымfrozenargv; numericlimits/code/SDK/models не менялись.

Вexecution125sampleevents. СнимкидоSTOP имелиpressure1/2; terminalsample pressure4.
SampledIpeak1312227328bytes, backendpeak930807808bytes, maxsimultaneouscombined1660567552bytes.
В снятых замерах RSS не достиг acceptedI6/backend5/combined10GiB. Systempressure —
whole-host indicator; его нельзя свести кRSS этихдвухпроцессов или приписать конкретному
приложению. GPU/MPS allocator attribution, состояние остальныхприложений и точный
источник общего давления памяти UNKNOWN; runtimeprofiling сверхэтогоrun не проводился.

ObservedDB+artifactmax9206807bytes; minhostfree86228291584/minVMfree28891693056bytes.
Storagelimit32GiB/minfree16GiB не былprimarySTOP. Actualread-onlypostchecks подтвердили
BUILDING/PENDING100/0regionsvectorspointers, noownedliveprocesses и обеleasechecksPASS.
Outerheartbeat/guardian выполнилиограничениеSTOP; точноезавершение Iобработки/загрузки
embeddingprovider не подтверждено счётчикомreservations или отсутствующимfinalresult.

## Identity и сохранность

- JobSHA: `3a8b2962b917954b2665ccf15536599d3d8ea254d829f0aec6ff632fa41a4304`.
- Run evidence archiveSHA: `8452ccc306f66a4137fa01569b1cc8b8b19387b2c91b8f058831b523c23ba320`.
- Frozen100profile06d2d475.../inventory765b53c9.../canonicala97cd4f4... иuserlist unchanged.

Approvedpermit/command/claims, privateworker/I/controllerlogs, observationtrace/admission
counter/SQLprocessleasepostchecks сохраненывprivate700/600archive. Фото/векторы/rawIDs/
полныеpaths/credentials не опубликованы. Все82codepins иjobfiles hashes повторнопроверены
безSDK/load/inference. OldG4/674source/checkarchives, inputs/sheets/sourceXLSX сохранены.

## Review и следующая граница

FULL: исполнительсверилactualtoolresults/trace/postchecks/hasharchive иsafeaggregate report;
независимоеread-onlyreview PASS0Critical/0Major/0Minor; ссылки/status/diff согласованы,
private/DB/SDK/modelпроверки reviewer не повторял. Reviewfixcycles0.
Code не менялся — безопасныеsuites не повторялись безновойпричины; результаты прошлых
365PASS/46SKIP не считаются валидациейнеполученногоMLиндекса.

ПередновымMLrun нужно устранить или сузить ресурсныйблокер, подготовить отдельныйfresh
attempt/identity/bill иполучитьownerpermission. Не повышатьпороги/не закрыватьчужие
приложения/не запускатьмодели автоматически. Ускорениеалгоритма остаётсявbacklog до
проверкикачества; этотSTOP не разрешаетbatching/one-model/downscale/profileизменения.
T052 coverageacceptance иT053–T055queries/READY/publish остаютсязакрыты.
