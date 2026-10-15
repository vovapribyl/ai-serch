# Контракты приложения

v1 / APPROVED_BY_OWNER. Plain DTO принадлежат ядру; SQL cursors, tensors, HTTP responses,
file descriptors и PID handles в ядро не проходят. Имена — предлагаемые сигнатуры.

| Операция | Вход | Результат / ошибки |
|---|---|---|
| start_build | SelectedInventory, ExecutionPackage | RunSummary / INVALID_PACKAGE, BUSY, RESOURCE_STOP |
| resume_build | saved_run_ref, ExecutionPackage | RunSummary; ERROR фото не выбирается без ручного retry |
| retry_photo | revision_ref, photo_ref, expected_version, ExecutionPackage | новая редакция/попытка и RunSummary; unchanged ready artifacts reuse |
| retry_publication | revision_ref, ExecutionPackage | PublicationReceipt; без ML если данные пригодны |
| search | QueryInput, VerifiedCatalogBinding | прежний NailSearchResult либо TEMPORARILY_UNAVAILABLE/PROFILE_MISMATCH |
| read_summary | run_ref | сохранённый RunSummary / NOT_FOUND |

ExecutionPackage содержит согласованные input/profile/code/model identities,
конечные overall/HTTP/DB/shutdown deadlines, limits источников/pixels/regions/
wire/vectors/admissions, ceilings памяти и freshness policy, разрешённый scope.
Все значения обязательны/положительны там, где применимо; более широкие caps
не отменяют ограничения действующего профиля. В документе нет default production-пакета.

RunSummary: run/revision refs, выбранные/завершённые фото и исходы, оставшиеся стадии,
публикации и ошибки публикации, причина завершения, состояние поиска. Public вывод
не содержит raw input paths, weights или секреты; private отчёт следует data policy.

Команды не дают роль CHECK право пополнять корпус. ML-нагрузка запускается только
через supervisor; unit-тест использует fake ports. Все изменения состояния идут
через приложение, с expected version и fencing token, а не произвольный adapter CRUD.

Утверждено в составе технического пакета сообщением владельца «Утверждаю»
2026-10-12 после повторного review PASS0/0/0; операционные gates сохраняются.
