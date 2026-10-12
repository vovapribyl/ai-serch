# Первый тест: фиксированный корпус100 и список изображений

2026-10-11. Owner попросил отложить ускорение до проверки качества и сократить
корпус примерно до100, сохранив список для ручного тестирования именно этих фото.
**100INPUT_PREPARATION_PASS; ML_WINDOW_CONSUMED_STOP_RESOURCE_CRITICAL.**
Послеowner «Разрешаю» один[build100](build-report.md) остановленpressure4; usableindex
не получен, PENDING100. Нижеисторическаяподготовка, не permissionповторитьML.
FULL [контракт](corpus-100-plan.md): scope100 → private copies/list/manifest →
runner subset guards/TDD → actual model-free check → один independentread-only review.
Исследование ускорения записано в [бэклог](tasks.md#бэклог); сейчас не выполняется.

## Состав набора и пользовательский список

Из approved674prepared детерминированно отобраны100разных по input SHA фото.
Правило: для duplicatebytes взять запись с меньшимproduct_record_id, затем сортировать
уникальные SHA по SHA256("candidate-i-corpus100-v1"+NUL+inputSHA), выбратьпервые100,
привести кcanonicalproduct_record_id/photo_ordinalorder. Reversedinput даёттотже набор.
Это reproducible hash-rank sample без утверждения статистической репрезентативности
или покрытия всех видов товара. Никакие product IDs/оригинальные локаторы не публикуются.

В новом private700root сохранены100byte-identicalcopies от674prepared с именами
001…100 и фактическим jpg/png/webp extension. Source674/originals/manifests сохранились.
Внутри100 есть одна previouslyapproved1536copy; повторного resize не было.

- `images-100.csv`: номер001–100, относительныйfilename, SHA,width,height.
- `images-100.html`: тотже numberedlist, локальные изображения и links на тежефайлы,
  CSVdownload; external links/scripts/uploads отсутствуют. Это private user artifact,
  а не публичная страница. Передан в панель Codex(file/browser), toolstatusqueued.
- Privateinventory/source names/lineage связывают каждый номер с темжеphoto/catalog/
  productrecord и фактическими байтами будущего testindex.

Проверено100rows↔100inventoryitems↔100filenames↔100hashes, sequence001…100,
100uniqueSHA, HTML100records и соответствиеlinks. Повторный boundeddecode выполнен
вactualworker; все100входов прошли current20MiB/2359296pixel cap.

Тестировать этижефото можно как knownreference checks. Такиеqueries не подтверждают
качество на новых снимках товара; additionalqueries/ownerqualityacceptance ещё отдельны.

## Freeze и заменённый первый execution scope

- InputprofileSHA: `06d2d4752bfbdc9801b6cad7cf01f32fbaf21f3a78c10d8caef7bd48531464ab`.
- PrivateinventoryfileSHA: `765b53c9b7d8b5d5cf398eb681dab0e4bced9ec836453e279ba45fd306ce701f`.
- Canonical BuildPhoto SHA: `a97cd4f4d295afde967dc7a5059b129bde04f78ad833a5993502b7eee13a573c`.
- CSVlistSHA: `6f36298aa84f2547b5ef3c777da76ef1e17ac2dcb8fe4937ca1f92b3093c64ab`.
- HTMLlistSHA: `2791b49c9a0c2901dadaae94f485deef569cc6c889e70f3d80126b72cb87bdea`.
- NewjobSHA: `3a8b2962b917954b2665ccf15536599d3d8ea254d829f0aec6ff632fa41a4304`.
- Representationfingerprint: `d445cb4df55989e8a2fd2bcce6b162188d5c6443ffd98acec8ca083984343d38`.
- Private source/job/listarchiveSHA: `ba79cefb754958e63a650353fbf8f15261511c3456d8c59a2c378baf6cc9ee50`.

[Прежний674package](native-execution-package.md) сохраняется исторически. Первый
тест теперь100, old674job supersededдляfirsttest; послеcodechange он неcurrentcommand.
Новыйjob содержит82codefilepins иexactparent674count/hash: источник/parents674 остаются
вownedtarget, catalogrepresentation будеттолько100selectedphotos. Это не destructive
удаление остальных574records и не businessdecision изменить полныйкорпус.

## Новый предложенный bill

Действуют sameI/backendinterpreters/models/HTTP/wire/RSS/storage/observer/no-publish
boundaries прежнего [bill](build-execution-bill.md), меняются scope/fingerprint/budget.

| Параметр | Предложение новогоjob, ещё не execution permission |
|---|---|
| Входы |100frozenprimaryphotos, no retry/resume/restart |
| Budget |≤3103admissions:100I+3loads+3000encodes (100×10×3) |
| Максимальный выход |1000regions/3000vectors512/768/768 |
| Wall |≤3600s/60min; верхняяграница, не forecast длительности |
| STOP |I6/backend5/combined10GiB; critical/unknown/error/stale>5s; ownedDB+artifacts≥32GiB или host/VMfree<16GiB |
| Действие |ОднаBUILDING вsameownedtarget; no READY/pointer/publish/query/workingDB |

Expiry иclaim once-bound tojobSHA/runroot/controller остаются обязательными.
На момент подготовкипакета approvedpermit не был создан; строкаrepresentation отсутствовала, ML не запускался.
Затем oneownerwindow разрешён и[исполнен](build-report.md), остановленпоpressure4; повтор не разрешён.

## Actual check и проверка кода

Actual --check100exit0/5.104s;100decoded, actualIready/POST403, observedpackages/backend
manifests/ownedtargetfullparents/hash membership PASS. NoTorch/noTransformers обоими
процессами/reserved0, representationNOT_CREATED/photo0/region0/vector0/pointer0.
OwnedIterminated-15/backend0/device+coordinatorleasesreacquired.

[Job guards](../../../../../.codex/worktrees/candidate-i-http/Ai/src/product_search/infrastructure/nail_native_job.py):
count/budget/unique/canonicalinput, exactfullparenthash+selectedmembership, deterministic
selection. [Runner](../../../../../.codex/worktrees/candidate-i-http/Ai/scripts/run_nail_native_build.py)
берёт input_count изjob вместоhardcoded674, checkresult отражаетфактическое число.
Core/schema/MLalgorithm не менялись; profiling/batching/modelchoice не выполнялись.
3newbehaviourRED→GREEN; jobtests20PASS. Final34safe suites365PASS/46SKIP/
2dependencywarnings; native/DBopt-insclosed, fullproject/modelinference не запускался.
Ruff3touchedfiles/diff/local links/markers проверены. Archive600/roots700, все входы
и userlist600 внеGit; snapshots674/G4 сохранены.

Independentcode/scope reviewPASS0Critical/0Major/0Minor, independently20safe tests;
restrictedphoto/privatefiles/SDK/DB/Docker reviewer не проверял. Finaldocs reviewPASS0Critical/0Major/0Minor; links/status/арифметика/diff согласованы, reviewfixcycles0.

Один разрешённыйbuild100 выполнен иостановлен; новоеMLокно требует отдельного freshattempt/permission. Затем coverage
и изолированный READY/querysession/manualquality. Список100 уже зафиксирован и не
должен незаметно меняться между сборкой и ручнымиqueries.
