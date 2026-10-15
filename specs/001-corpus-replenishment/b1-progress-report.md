# B1: native lifecycle и файловые checkpoints

2026-10-13 / PARTIAL. Владелец утвердил исходныйB1 сообщением «Утверждаю».
Scope process/files/testDB открыт; dependency дополнение ожидает ответа владельца.
Работа в codex/upload-optimiz; исходный baseline80целевых hashes сохранён.

## Реализовано и проверено

Tasks017–019: безопасный private ModeLease, один modeFD через
SEARCH/DRAINING/BUILD, atomic query admission и bounded drain; новый owner epoch
приходит от отдельного callback-адаптера. Fresh resource/ownership/child guards,
owned registry с проверенным argv/shell=False/start_new_session/pass_fds;
TERM/KILL только собственных зарегистрированных handles. После утраты живого
leader неизвестные группы не усыновляются поPID, неподтверждённый выход блокирует
admission. CLOSE во времяDRAINING не освобождает modeFD.

На Mac проверены: inheritedFD послеexec, parent death при живом ребёнке,
конкурирующий lease, завершение своих children без вмешательства в отдельную
незарегистрированную test group, TERM-ignoring worker→KILL, cutoff/unknown
resource signals и failure DB-epoch callback. Native suite:26passed.

Tasks023–025: stage-scoped private staging/final, canonical manifest+SHA,
expectedidentity/profile и exact file set; finite/dimension/order vectors,
PNG crop/mask pairs, mask values/pixels caps; file anddirectory fsync, rename
и parent sync. Идемпотентность и отказoverwrite; corruption/symlink/escape,
sync/rename/parent-sync faults и commit failure. Files suite:15passed.

После rename до подтверждения DB возможны orphan files. Наличие final не
означаетCOMPLETE; controller commit failure оставляет фотоPENDING.
Будущий DB/worker binding обязан читать только файлы, подтверждённые checkpoint
receipt актуальной редакции; полныйruntime wiring ещё не реализован.

StageAttempt получил обязательный expectedidentity_sha (полеidentity_sha);
это plainDTO, schema формирования identity проверяется будущим state adapter.

## TDD и проверки

- Harness RED4failed→GREEN4passed; container guardRED9failed/4passed→GREEN13passed;
  private migration diagnosticRED1failed/13passed→GREEN14passed.
- LeaseRED3failed→GREEN3passed; handoffRED8failed/5passed→GREEN13passed;
  close raceRED1failed/14passed→GREEN15passed; owned processRED2failed/15passed→GREEN17passed.
- Deadline guardsRED4failed/18passed→GREEN22passed; child admissionRED2failed/23passed→GREEN25passed;
  oversized resource timestampRED1failed/25passed→GREEN26passed.
- FilesRED11failed→GREEN11passed; big integer guardRED1failed/13passed→GREEN14passed;
  controller commit-fault integration case→15passed.
- Итог после исправлений:427unit/harness/baseline tests +26native +15files =468passed.
  Одно прежнееStarlette/httpx deprecation warning в427выборке. Ruff/diff checksPASS.

Setup failures и дефекты scaffolding отдельно отRED: первоначальный thread fixture
встретил неисполняемый query_permit и cleanup join ещё не запущенного thread;
после правки scaffolding наблюдался поведенческийRED. В процессе GREEN один
syntax error и пропущенное сохранение _build_package исправлены. Необработанный
OverflowError превращён в контролируемыйRESOURCE_STOP/CHECKPOINT_INVALID.
Эти промежуточные ошибки не объявляются корректнымRED или успешной проверкой.

## БД: фактический блокер

Создан bounded SyntheticDatabase helper: uniqueowner label/image/caps,localhost
port,tmpfs,privategeneratedcredentials,emptypublicschema/owner-marker guards;
sanitized migration environment без рабочегоDSN; commandtimeout и cleanup30с.
Статические/unit guard проверки выполнены до запускаDocker.

Три bootstrap attempts завершились setup failure; два следующих прогона
добавляли/исправляли приватный logger для диагноза, не были автоматическимretry.
Причина: migration0005_gate3_search.py импортирует pgvector.sqlalchemy.Vector,
а Pythonpgvector отсутствует. Bootstrap0001–0009 не завершён; это неTDDRED.
Рабочая БД/корпус не использовались. Созданные контейнеры удалены helper;
read-only проверка отсутствия B1containers выполнена отдельно.

Первоначальное заключение «Pythonpgvector не нужен» относится только к
PostgresNailCatalog SQL adapter и было неполным для migration chain.
[Dependency дополнение](test-dependency-addendum.md) предлагает только
pgvector0.5.0, без MLextra/numpy/обновлений, и покаPENDING_OWNER_APPROVAL.
Ничего не устанавливалось. Unit bootstrap test существует, но не прошёл setup.
Tasks020–022/026–051 ещё открыты; новаяschema/state/publication не реализованы.

## Практические границы

Supervisor и file adapter проверены отдельно. Пока отсутствуют DBfencing adapter,
связь общего deadline supervisor/controller, CLI/IPC и real stage workers.
Сумма468passed не доказывает эти интеграции, качествоML или готовность пополнения.
RealML,рабочаяDB/каталог,weights,commit/push/merge не выполнялись.

## Обновление2026-10-13: dependency блокер снят

Владелец явно выбрал первоначальную установкучерезpip. Установлен только
pgvector0.5.0 (--no-deps); использован cachedwheel. Metadata/importPASS.
Один новый boundedB1 bootstrap завершился1passed: baseline0001–0009 применён
в ownedsyntheticDB, рабочие records/representations не использовались.
Созданный контейнер удалён; B1label listing пуст.
Предыдущие setupfailures сохраняются как история, но более не блокируют
следующий цикл schema/stateTDD. Задачи020–022 остаются открытыми.
