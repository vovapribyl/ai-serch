# Проход100 с пропуском отказов результата

2026-10-11. **STOP: RESOURCE_CEILING / pressure4; BUILD_INCOMPLETE**. [Утверждённый план](skip-photo-build-plan.md).
Owner разрешил skip аналогичных фото и последующее продолжение корпуса.

Изменение: HTTP503 REGION_COUNT_LIMIT/RESPONSE_SIZE_LIMIT относятся только к
encode_result; device RESOURCE_ERROR и прочие unknown/model/budget/observer failures
terminal. GuardedLocalization передаёт только два photo-limit кода как
NailProcessingError, core пишет ERROR без region/vector и продолжает. Complete при
ERROR остаётсяfalse, публикации нет. Лимиты/SDK/weights/model config не изменены.

4 поведенческих RED (отсутствующие HTTP codes/guard continuation) → GREEN;
118 targetedPASS;34safe suites383PASS46SKIP/2existingdependencywarnings.
Synthetic chain проверяет ERROR первого фото и обработку второго, budget accounting
и отсутствие publish. Independent reviewPASS0C/0Major/0Minor; reviewer отдельно118tests.

Job SHA256 `9d1fa00b70faedb26081c707465829c943ba47cbe662f90cecd391c6e962edc6`.
Новый extractor SHA256 `7c0b19146661c05b95aa26558f89abc48cf33469654cacb3a584b2df3b098873`;
assembly SHA256 `4d37dfa0ea54a84f7e4f82379a7dd0830502cdc08674f5c54de4fe4f24e9c252`.
82frozen codepins, отдельная representation100; input/list/Sheetsmarkers unchanged.
Prepared source archive SHA256 `e95f4572bd5750c4de3c54aabceb3f6bbff250c6e8b1ec57205ff20cf2d62e1f`.
Model-freepreflight4,803s/exit0/noSDK/100inputs/noDBwrites/reserved0.
Privateapprovedpermit3600s/exclusiveonceclaim;одинactualrun запущен.

Промежуточный read-only aggregate:20OK/1NO_NAILS/1ERROR/78PENDING,112regions/336vectors,
pointer0. Фото019 имеет REGION_COUNT_LIMIT: превышение10regions подтверждено новым
проходом; exact count UNKNOWN. Прежняя one-photodiagnostic имела только RESOURCE_ERROR,
поэтому её inference исторически не переписывается. Старые partial builds сохранены.

## Финальный результат

Единственный approved проход завершён через115,634s. Worker exit−9/controller3;
Guardian generic label RESOURCE_OBSERVATION_ERROR, фактический observation reason
RESOURCE_CEILING с pressure4 (critical). Это новая системная остановка, не отказ фото.
Reserved362,20OK/1NO_NAILS/1ERROR/78PENDING,112regions/336vectors/pointer0.
Фото019 пропущено с REGION_COUNT_LIMIT, фото011 NO_NAILS; остальные исходные100
не удалены и не заменены. Приватный processing-status-100.csv сохраняет номер,
статус и причину для каждого из100, включая PENDING.

533 валидных samples,pressure1/2/4. Sampled I peak1421197312bytes,
backend/controller peak990511104bytes; они ниже processRSS ceilings, но общесистемный
pressure critical. Источник общесистемного давления UNKNOWN; это не доказательство
утечки модели и не основание повысить лимит. I exit и worker result UNKNOWN послеkill.
Controller immediate leases check=false; независимый поздний post-check:
owned live0, обаlease доступны, SQLcounts unchanged. Противоречие временных checks
сохранено, immediate teardown не объявлен успешным задним числом.

Все82runtime codepins совпали после запуска. Execution evidence archive SHA256
`a4f318ceb0b0707637335852385ef63464ef3cc127572c82ce37086ae9f53b99`.
Ruff6changedfiles PASS после локальной import-format правки толькоsynthetic теста;
runtime files во время запуска не менялись. git diff --check и local links PASS:7files/brokenlinks0/conflictmarkers0.
Финальный independent read-only report review:PASS0Critical/0Major/0Minor;
reviewer не использовал private artifacts/ML/DB/tests.

## Следующий шаг

Окно использовано; автоматического restart/resume нет. Skip-photo задача технически
работает, но формирование100 не завершено. Следующий blocker — общесистемное давление
памяти; его диагностика/подготовка нового ограниченного окна не равна отложенному
исследованию ускорения. До новогоMLwindow нужны устранение/контроль этогоblocker и
отдельный execution bill. T051 открыт;coverage/manualquality/READY/publish не получены.
