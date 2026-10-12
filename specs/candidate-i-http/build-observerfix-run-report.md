# Build100 с исправленным наблюдателем: остановка локализации

2026-10-11. **BUILD_INCOMPLETE:17OK/1NO_NAILS/82PENDING.**
Владелец ответил «Разрешаю» на одинновыйпрогон100фото ≤60min/3103operations,
безpublish. [План](build-observerfix-run-plan.md), [reviewedobserverfix](build-retry-report.md).
Одноapprovedwindow исполнено; четвёртого MLrun/автоматическогоповтора не было.

## Результаты и остановка

| Показатель | Наблюдение |
|---|---|
| Preflight |Model-freeexit0/4.938s;100decode/pins/target/runtime/readiness/noSDK |
| Завершено |18из100:17OK,1NO_NAILS;82PENDING,ERROR0 |
| Сохранённые данные |84regions/252vectors вownedDB;3vectors наregion |
| Representation |BUILDING,неREADY;activepointer0;no publish/activation/queries |
| Время/выход |100.579s;controllerexit3/workerexit3;guardianSTOPreason=null |
| Причина наouterboundary |Workerlog:BuildStop,reasonLOCALIZATION_STOP |
| Первичная причина |HTTP/domaincode иточныйexternalexception не сохранены;UNKNOWN, не выдаётся заregionlimit илиmodelqualitydefect |
| Resourceobserver |472validsamples,pressure1/2,terminalobservation_stop=null;нетнаблюдавшегосяcriticalpressure/observerSTOP |
| RSS |SampledIpeak1285734400/backend1002520576bytes;не достигsampledceilings |
| Admissions |Reserved274из3103, не счётчик завершённыхвызовов |
| Teardown |OwnedIexit-15/terminated,worker3,ownliveprocesses0;device/coordinatorleasesreacquired;postpressure1 |

ОднаNO_NAILSзапись не означаетготовностьпокрытиятовара илиправильныйNEWответ.
Индекснеполон, ручное тестированиепоиска иT052coverageacceptance не выполнялись.
Данныепрежнихattempts, входы/sourceXLSX/Google100markers не изменялись.

Порядокcore — последовательныйcanonicalinventory. После18terminaloutcomes первым
незавершённымвходом являетсяномер019фиксированного списка. Это вывод изпорядка
исполнения/statuses/counter, не восстановленныйper-calltrace. Фото не исключено и
не изменено; выбранныйкорпус остаётся100.

## Безопасная диагностика без повторного ML

Точнаяпричина потерялась припереводе исключения вобщийLOCALIZATION_STOP. Исправлено
во внешнемguard: сохраняютсяcause_type иallowlistedcause_code (wirecodes иизвестные
mappeddomaincodes INVALID_OUTPUT/RESOURCE_LIMIT). Текст/reason/privatepath/unknown
code не выводятся;budget.stopped иterminalBuildStop остаются. CLIпишеттолько эти
безопасные поля. Core/MLadapter/model/config/SDK/пороги/алгоритм не менялись.

3observedRED→GREEN: knowncode retained,unknowncode/privatecause filtered,CLIfields.
73targetedPASS;final34safe suites372PASS46SKIP/2dependencywarnings. Code reviewPASS
0Critical/0Major/0Minor,independently73safe tests; private/DB/SDK/native reviewer не проверял.
Actualстарыйprimarycause не восстановлен этими изменениями.

Доpatch frozenexact82source+execution evidence archiveSHA:
`ff40d1d75c6f8f58bc8bbe6284b91c3d88e44f35c8b34d12c6d6fd6d697e0c63`.
ConsumedjobSHA: `3565030645e2fc2d284feb44d4a377450fef9f3924cc1d9ca98df89f2614911e`.
Private700/600;новыефото/веса/векторы/rawIDs/полныеpaths вGit/chat не публиковались.

## Подготовленная проба только фото019

Чтобы не повторять18входов радиустановлениясбоя, подготовлен отдельныйexistingCLI
one-photobuild диагностическогоназначения; это proposal, не executedMLprobe:

- Одиннеизменённыйinput №019 из100;новые runtimephoto/representationUUID;fullparent674identity.
- ≤34admissions (1I+3loads+≤30encodes),≤360s/6min — upperbound,неforecast.
- SameRSS/storage/HTTP/freshness/regioncap10/pixel/source/wirelimits;no retries,
  truncation/exclusion/limitincrease/READY/pointer/publish. Еслиlocalizationуспешна,
  проверяетсяexistingembeddingchainдляэтогоодногофото; nofull100restart.
- JobSHA: `3a51c9bf3a4615386e4e76100454e817c70764d83d029632ab7071fccb431c71`.
- Source/job/checkarchiveSHA: `49f1cce2a4740cbf097fb9aed645c0127e8c52f5f79048aaf31871f4a461a1c3`.

Model-freecheck1inputexit0/4.381s,actualready/POST403/noSDK/reserved0/NOT_CREATED/
0resultcounts/leasesreacquired. Approvedpermit иexecution.claim отсутствуют.
Проба может не воспроизвести сбой; её результат не будет гарантией завершения100.
Перед пробой нужен отдельныйownerдопуск на этотjob/scope/bounds. Старые17OK/1NO_NAILS/
82PENDING иselected100list сохраняются. Ускорениевbacklogостаётсяотложенным.

Finalread-onlyreview PASS0Critical/0Major/0Minor, scopes/counts/links/diff согласованы;
reviewfixcycles0, private/DB/SDK/probe reviewer не повторял. Links/markers/status/diff/Ruff проверены;
T051[ ],никакаяновая MLpermission не выведена извыполненныхпроверок.

## Последующая разрешённая диагностика

Предложение выше затем разрешено владельцем и[исполнено один раз](photo019-diagnostic-report.md).
Фото019 воспроизвело RESOURCE_ERROR за16,82s; probable >10regions, exact branch UNKNOWN.
Prepared permit/claim состояние выше историческое; окно теперь использовано.
